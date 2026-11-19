import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Protocol

from rag.config import Config
from rag.files import atomic_write
from rag.indexing.embedding import text_hash

PROVIDERS = {
    "deepseek": ("https://api.deepseek.com", "DEEPSEEK_API_KEY"),
    "openai": ("https://api.openai.com/v1", "OPENAI_API_KEY"),
    "surplus-chat": ("https://api.surplusintelligence.ai/v1", "SURPLUS_API_KEY"),
}


class LLMError(ValueError):
    """A bounded request, cache, or provider response failed."""


@dataclass(frozen=True)
class Completion:
    content: str
    model: str
    input_tokens: int | None
    output_tokens: int | None
    finish_reason: str = "stop"


class LLMBackend(Protocol):
    def complete(self, messages: list[dict[str, str]], config: Config) -> Completion: ...


def _api_key(variable: str) -> str:
    key = os.environ.get(variable)
    if key is None:
        try:
            lines = Path(".env").read_text(encoding="utf-8-sig").splitlines()
        except FileNotFoundError:
            lines = []
        except (OSError, UnicodeError):
            raise LLMError(
                "Cannot read .env; use UTF-8 or set the provider environment variable"
            ) from None
        # Read only the selected provider key; never execute or expand .env values.
        for line in lines:
            name, separator, value = line.strip().removeprefix("export ").partition("=")
            if not separator or name.strip() != variable:
                continue
            value = value.strip()
            if value.startswith(("'", '"')):
                value, closed, suffix = value[1:].partition(value[0])
                if not closed or (suffix.strip() and not suffix.lstrip().startswith("#")):
                    raise LLMError(f"Invalid single-line value for {variable} in .env")
            else:
                value = value.split("#", 1)[0].rstrip()
            key = value
    if not key or not key.strip():
        raise LLMError(f"Missing {variable}; set it in the environment or .env")
    return key


class OpenAIBackend:
    def complete(self, messages: list[dict[str, str]], config: Config) -> Completion:
        from openai import OpenAI

        endpoint, variable = PROVIDERS[config.generation.provider]
        key = _api_key(variable)
        parameters = {
            "model": config.generation.model,
            "messages": messages,
            "temperature": config.generation.temperature,
            "response_format": {"type": "json_object"},
        }
        token_parameter = (
            "max_completion_tokens" if config.generation.provider == "openai" else "max_tokens"
        )
        parameters[token_parameter] = config.generation.max_output_tokens
        if config.generation.provider == "deepseek":
            parameters["extra_body"] = {
                "thinking": {"type": "enabled" if config.generation.thinking else "disabled"}
            }
        # SDK retries must not bypass the experiment's call budget.
        with OpenAI(
            api_key=key,
            base_url=config.generation.base_url or endpoint,
            timeout=config.generation.timeout_seconds,
            max_retries=0,
        ) as client:
            response = client.chat.completions.create(**parameters)
        choice = response.choices[0] if response.choices else None
        usage = response.usage
        return Completion(
            choice.message.content or "" if choice else "",
            response.model,
            usage.prompt_tokens if usage else None,
            usage.completion_tokens if usage else None,
            choice.finish_reason if choice else "missing_choice",
        )


def _validate_response(response: Completion) -> None:
    if (
        not isinstance(response.content, str)
        or not isinstance(response.model, str)
        or not response.model
        or not isinstance(response.finish_reason, str)
        or any(type(n) is not int or n < 0 for n in (response.input_tokens, response.output_tokens))
    ):
        raise LLMError("Provider response or token usage is missing/invalid")
    try:
        response.content.encode("utf-8")
        response.model.encode("utf-8")
    except UnicodeError as exc:
        raise LLMError("Provider returned invalid Unicode") from exc


class CachedLLM:
    def __init__(
        self, config: Config, backend: LLMBackend | None = None, allow_api: bool = False
    ) -> None:
        self.config = config
        self.backend = backend
        self.allow_api = allow_api
        self.calls = 0
        self.attempts: list[dict] = []
        model = backend if backend is not None else OpenAIBackend()
        self.backend_name = f"{type(model).__module__}.{type(model).__qualname__}"

    def complete(self, messages: list[dict[str, str]]) -> Completion:
        config = self.config
        endpoint = config.generation.base_url or PROVIDERS[config.generation.provider][0]
        provenance = {
            "provider": config.generation.provider,
            "endpoint": endpoint,
            "model": config.generation.model,
            "temperature": config.generation.temperature,
            "max_output_tokens": config.generation.max_output_tokens,
            "thinking": config.generation.thinking
            if config.generation.provider == "deepseek"
            else None,
            "backend": self.backend_name,
            "messages": messages,
        }
        key = text_hash(json.dumps(provenance, sort_keys=True, ensure_ascii=False))
        path = Path(config.paths.cache_dir) / "llm" / f"{key}.json"
        if path.exists():
            try:
                cached = json.loads(path.read_text(encoding="utf-8"))
                if cached["provenance"] != provenance or cached["response_sha256"] != text_hash(
                    json.dumps(cached["response"], sort_keys=True)
                ):
                    raise ValueError("cache provenance/checksum differs")
                response = Completion(**cached["response"])
                _validate_response(response)
            except (ValueError, KeyError, TypeError) as exc:
                raise LLMError(
                    "Invalid LLM response cache; preserve it and use a separate cache_dir"
                ) from exc
            self.attempts.append(
                dict(
                    asdict(response),
                    cache_hit=True,
                    billed_input_tokens=0,
                    billed_output_tokens=0,
                    request_sha256=key,
                )
            )
            return response
        if (
            self.backend is None or getattr(self.backend, "requires_api", False)
        ) and not self.allow_api:
            raise LLMError(
                "API calls are disabled; pass --allow-api explicitly to make a paid request"
            )
        if self.calls >= config.generation.max_calls_per_run:
            raise LLMError("generation.max_calls_per_run exhausted")
        self.calls += 1
        attempt = {
            "cache_hit": False,
            "request_sha256": key,
            "billed_input_tokens": None,
            "billed_output_tokens": None,
        }
        self.attempts.append(attempt)
        try:
            response = (self.backend or OpenAIBackend()).complete(messages, config)
        except LLMError:
            attempt["error"] = "provider_configuration_error"
            raise
        except Exception as exc:
            attempt["error"] = type(exc).__name__
            raise LLMError(f"LLM request failed ({type(exc).__name__})") from None
        if not isinstance(response, Completion):
            raise LLMError("Provider returned an invalid completion object")
        attempt.update(
            content=response.content if isinstance(response.content, str) else None,
            model=response.model if isinstance(response.model, str) else None,
            finish_reason=response.finish_reason
            if isinstance(response.finish_reason, str)
            else None,
            input_tokens=response.input_tokens
            if type(response.input_tokens) is int and response.input_tokens >= 0
            else None,
            output_tokens=response.output_tokens
            if type(response.output_tokens) is int and response.output_tokens >= 0
            else None,
        )
        _validate_response(response)
        attempt.update(
            billed_input_tokens=response.input_tokens, billed_output_tokens=response.output_tokens
        )
        payload = asdict(response)
        atomic_write(
            path,
            json.dumps(
                {
                    "provenance": provenance,
                    "response": payload,
                    "response_sha256": text_hash(json.dumps(payload, sort_keys=True)),
                },
                ensure_ascii=False,
                allow_nan=False,
            ).encode("utf-8"),
        )
        return response
