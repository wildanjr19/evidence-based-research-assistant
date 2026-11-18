"""Load the experiment configuration without initializing models or clients."""

import math
import re
from dataclasses import MISSING, dataclass, fields
from pathlib import Path
from typing import TypeVar

import yaml


class ConfigError(ValueError):
    """The configuration cannot be read or contains invalid values."""


@dataclass(frozen=True)
class IngestionConfig:
    query: str
    max_papers: int
    page_size: int
    request_delay_seconds: float
    timeout_seconds: float
    max_pdf_bytes: int
    allowed_licenses: list[str]


@dataclass(frozen=True)
class ParsingConfig:
    margin_ratio: float = 0.08
    repeated_margin_ratio: float = 0.6
    min_repeated_pages: int = 2
    heading_max_words: int = 16


@dataclass(frozen=True)
class ChunkingConfig:
    target_tokens: int
    overlap_tokens: int
    min_tokens: int
    short_chunk_policy: str = "merge"
    tokenizer: str = "lexical-v1"


@dataclass(frozen=True)
class EmbeddingConfig:
    model: str
    batch_size: int
    device: str
    revision: str = "a5beb1e3e68b9ab74eb54cfd186867f64f240e1a"
    max_tokens: int = 512


@dataclass(frozen=True)
class RetrievalConfig:
    dense_top_k: int
    bm25_top_k: int
    rrf_k: int
    rerank_candidates: int
    final_top_k: int
    use_reranker: bool
    reranker_model: str
    query_prefix: str = "Represent this sentence for searching relevant passages: "
    reranker_revision: str = "2cfc18c9415c912f9d8155881c133215df768a70"
    reranker_max_tokens: int = 512
    reranker_batch_size: int = 16


@dataclass(frozen=True)
class GenerationConfig:
    provider: str
    model: str
    temperature: float
    max_calls_per_run: int
    max_output_tokens: int = 2048
    timeout_seconds: float = 60.0
    base_url: str = ""
    thinking: bool = False


@dataclass(frozen=True)
class VerificationConfig:
    minicheck_model: str
    judge_model: str
    judge_provider: str
    judge_sample_rate: float
    seed: int
    minicheck_revision: str = "96eafd01cee2d16cf81aaa2fb226b14f422a37b3"
    max_tokens: int = 512
    batch_size: int = 4
    device: str = "cpu"
    support_threshold: float = 0.5
    judge_max_calls_per_run: int = 50
    judge_base_url: str = ""


@dataclass(frozen=True)
class EvaluationConfig:
    ks: list[int]
    dataset_path: str
    gold_labels_path: str
    output_dir: str


@dataclass(frozen=True)
class PathsConfig:
    raw_dir: str
    parsed_dir: str
    index_dir: str
    cache_dir: str
    db_path: str


@dataclass(frozen=True)
class Config:
    ingestion: IngestionConfig
    parsing: ParsingConfig
    chunking: ChunkingConfig
    embedding: EmbeddingConfig
    retrieval: RetrievalConfig
    generation: GenerationConfig
    verification: VerificationConfig
    evaluation: EvaluationConfig
    paths: PathsConfig


T = TypeVar("T")


def _parse_value(value: object, expected: object, key: str) -> object:
    if (
        expected is str
        and isinstance(value, str)
        and (
            value.strip()
            or key
            in {"retrieval.query_prefix", "generation.base_url", "verification.judge_base_url"}
        )
    ):
        return value
    if expected is bool and type(value) is bool:
        return value
    if expected is int and type(value) is int:
        return value
    if expected is float and type(value) in (int, float):
        try:
            number = float(value)
        except OverflowError as exc:
            raise ConfigError(f"{key}: expected a finite number") from exc
        if math.isfinite(number):
            return number
    if (
        expected == list[int]
        and isinstance(value, list)
        and value
        and all(type(item) is int and item > 0 for item in value)
    ):
        return value
    if (
        expected == list[str]
        and isinstance(value, list)
        and value
        and all(isinstance(item, str) and item.strip() for item in value)
    ):
        return value
    raise ConfigError(f"{key}: expected {expected}, with a non-empty, finite value")


def _section(raw: dict, name: str, section_type: type[T]) -> T:
    section_fields = fields(section_type)
    section = raw.get(name)
    if name not in raw and all(field.default is not MISSING for field in section_fields):
        section = {}
    if not isinstance(section, dict):
        raise ConfigError(f"{name}: required section must be a mapping")
    names = {field.name for field in section_fields}
    if unknown := section.keys() - names:
        raise ConfigError(f"{name}: unknown keys: {', '.join(sorted(map(str, unknown)))}")
    values = {}
    for field in section_fields:
        key = f"{name}.{field.name}"
        if field.name not in section and field.default is MISSING:
            raise ConfigError(f"{key}: required key is missing")
        value = _parse_value(section.get(field.name, field.default), field.type, key)
        if field.type is int:
            minimum = 0 if field.name in {"overlap_tokens", "rrf_k", "seed"} else 1
            if value < minimum:
                raise ConfigError(f"{key}: must be >= {minimum}")
        values[field.name] = value
    return section_type(**values)


def load_config(path: str | Path = "configs/config.yaml") -> Config:
    """Read YAML into typed sections; relative paths remain relative to the working directory."""
    try:
        with Path(path).open(encoding="utf-8") as stream:
            raw = yaml.safe_load(stream)
    except (OSError, UnicodeError, yaml.YAMLError) as exc:
        raise ConfigError(f"Cannot read configuration at {path}: {exc}") from exc

    if not isinstance(raw, dict):
        raise ConfigError("Configuration root must be a mapping")
    names = {field.name for field in fields(Config)}
    if unknown := raw.keys() - names:
        raise ConfigError(f"Unknown configuration sections: {', '.join(sorted(map(str, unknown)))}")

    config = Config(
        ingestion=_section(raw, "ingestion", IngestionConfig),
        parsing=_section(raw, "parsing", ParsingConfig),
        chunking=_section(raw, "chunking", ChunkingConfig),
        embedding=_section(raw, "embedding", EmbeddingConfig),
        retrieval=_section(raw, "retrieval", RetrievalConfig),
        generation=_section(raw, "generation", GenerationConfig),
        verification=_section(raw, "verification", VerificationConfig),
        evaluation=_section(raw, "evaluation", EvaluationConfig),
        paths=_section(raw, "paths", PathsConfig),
    )
    if config.ingestion.request_delay_seconds < 3:
        raise ConfigError("ingestion.request_delay_seconds: must be >= 3 (arXiv rate limit)")
    if config.ingestion.timeout_seconds <= 0:
        raise ConfigError("ingestion.timeout_seconds: must be > 0")
    if not 0 < config.parsing.margin_ratio < 0.5:
        raise ConfigError("parsing.margin_ratio: must be between 0 and 0.5 (exclusive)")
    if not 0 < config.parsing.repeated_margin_ratio <= 1:
        raise ConfigError("parsing.repeated_margin_ratio: must be > 0 and <= 1")
    if config.parsing.min_repeated_pages < 2:
        raise ConfigError("parsing.min_repeated_pages: must be >= 2")
    if config.chunking.short_chunk_policy not in {"merge", "drop"}:
        raise ConfigError("chunking.short_chunk_policy: must be merge or drop")
    if config.chunking.tokenizer != "lexical-v1":
        raise ConfigError("chunking.tokenizer: only lexical-v1 is available in M2")
    if config.chunking.overlap_tokens >= config.chunking.target_tokens:
        raise ConfigError("chunking.overlap_tokens: must be < chunking.target_tokens")
    if config.chunking.min_tokens > config.chunking.target_tokens:
        raise ConfigError("chunking.min_tokens: must be <= chunking.target_tokens")
    if not re.fullmatch(r"[0-9a-f]{40}", config.embedding.revision):
        raise ConfigError("embedding.revision: must be a pinned 40-character commit SHA")
    if not re.fullmatch(r"[0-9a-f]{40}", config.retrieval.reranker_revision):
        raise ConfigError("retrieval.reranker_revision: must be a pinned 40-character commit SHA")
    if not re.fullmatch(r"cpu|cuda(?::[0-9]+)?", config.embedding.device):
        raise ConfigError("embedding.device: must be cpu, cuda, or cuda:<index>")
    if config.generation.temperature < 0:
        raise ConfigError("generation.temperature: must be >= 0")
    if config.generation.timeout_seconds <= 0:
        raise ConfigError("generation.timeout_seconds: must be > 0")
    if config.generation.provider not in {"deepseek", "openai"}:
        raise ConfigError("generation.provider: must be deepseek or openai")
    if config.generation.base_url:
        from urllib.parse import urlsplit

        try:
            url = urlsplit(config.generation.base_url)
            _ = url.port
        except ValueError as exc:
            raise ConfigError("generation.base_url: invalid HTTPS URL") from exc
        if (
            url.scheme != "https"
            or not url.hostname
            or url.username
            or url.password
            or url.query
            or url.fragment
        ):
            raise ConfigError(
                "generation.base_url: use an HTTPS URL without credentials/query/fragment"
            )
    if not 0 <= config.verification.judge_sample_rate <= 1:
        raise ConfigError("verification.judge_sample_rate: must be between 0 and 1")
    if not re.fullmatch(r"[0-9a-f]{40}", config.verification.minicheck_revision):
        raise ConfigError("verification.minicheck_revision: must be a pinned commit SHA")
    if not re.fullmatch(r"cpu|cuda(?::[0-9]+)?", config.verification.device):
        raise ConfigError("verification.device: must be cpu, cuda, or cuda:<index>")
    if not 0 < config.verification.support_threshold < 1:
        raise ConfigError("verification.support_threshold: must be between 0 and 1 exclusive")
    if config.verification.judge_provider not in {"deepseek", "openai", "surplus"}:
        raise ConfigError("verification.judge_provider: must be deepseek, openai, or surplus")
    if config.verification.judge_base_url and config.verification.judge_provider != "surplus":
        raise ConfigError("verification.judge_base_url: supported only for Surplus decisions")
    if (
        config.retrieval.use_reranker
        and config.retrieval.final_top_k > config.retrieval.rerank_candidates
    ):
        raise ConfigError("retrieval.final_top_k: must be <= retrieval.rerank_candidates")
    return config
