import json
import math
from pathlib import Path
from typing import Protocol

from rag.config import Config
from rag.files import atomic_write
from rag.indexing.embedding import text_hash

MODEL = "lytang/MiniCheck-Flan-T5-Large"


class SupportBackend(Protocol):
    def score(self, pairs: list[tuple[str, str]]) -> list[float]:
        """Return support probabilities for (claim, evidence) pairs."""
        ...


class MiniCheck:
    def __init__(self, config: Config) -> None:
        self.config = config
        self.model = None
        self.tokenizer = None

    def score(self, pairs: list[tuple[str, str]]) -> list[float]:
        import torch
        from transformers import AutoModelForSeq2SeqLM, AutoTokenizer

        cfg = self.config.verification
        if cfg.minicheck_model != MODEL:
            raise ValueError("This adapter implements only the verified MiniCheck Flan-T5 model")
        if not pairs:
            return []
        if self.model is None:
            options = {
                "revision": cfg.minicheck_revision,
                "cache_dir": str(Path(self.config.paths.cache_dir) / "models"),
                "trust_remote_code": False,
            }
            self.tokenizer = AutoTokenizer.from_pretrained(MODEL, **options)
            self.model = AutoModelForSeq2SeqLM.from_pretrained(MODEL, **options).to(cfg.device)
            self.model.eval()
        texts = [
            f"predict: {evidence}{self.tokenizer.eos_token}{claim}" for claim, evidence in pairs
        ]
        counts = self.tokenizer(texts, truncation=False, padding=False)["input_ids"]
        limit = min(cfg.max_tokens, self.model.config.n_positions)
        if any(len(tokens) > limit for tokens in counts):
            raise ValueError("MiniCheck input exceeds token limit; evidence was not truncated")
        scores = []
        for start in range(0, len(texts), cfg.batch_size):
            inputs = self.tokenizer(
                texts[start : start + cfg.batch_size],
                truncation=False,
                padding=True,
                return_tensors="pt",
            ).to(cfg.device)
            decoder = torch.full(
                (inputs["input_ids"].shape[0], 1),
                self.model.config.decoder_start_token_id,
                dtype=torch.long,
                device=cfg.device,
            )
            with torch.inference_mode():
                logits = self.model(**inputs, decoder_input_ids=decoder).logits[:, 0, :]
                # Upstream MiniCheck uses token IDs 3 (negative) and 209 (positive).
                probabilities = logits[:, [3, 209]].float().softmax(dim=-1)[:, 1]
            scores.extend(probabilities.cpu().tolist())
        return scores


class CachedVerifier:
    def __init__(self, config: Config, backend: SupportBackend | None = None) -> None:
        self.config = config
        self.backend = backend if backend is not None else MiniCheck(config)
        self.cache_hits = 0
        self.computed_pairs = 0
        cfg = config.verification
        self.identity = {
            "model": cfg.minicheck_model,
            "revision": cfg.minicheck_revision,
            "max_tokens": cfg.max_tokens,
            "device": cfg.device,
            "threshold": cfg.support_threshold,
            "adapter": "minicheck-flan-t5-pair-v1-no-truncation",
            "backend": f"{type(self.backend).__module__}.{type(self.backend).__qualname__}",
        }

    def verify(self, claim: str, evidence: str) -> dict:
        if not all(isinstance(text, str) and text.strip() for text in (claim, evidence)):
            raise ValueError("Verification requires non-empty claim and evidence")
        provenance = dict(
            self.identity, claim_sha256=text_hash(claim), text_sha256=text_hash(evidence)
        )
        path = (
            Path(self.config.paths.cache_dir)
            / "verification"
            / (text_hash(json.dumps(provenance, sort_keys=True)) + ".json")
        )
        if path.exists():
            try:
                cached = json.loads(path.read_text(encoding="utf-8"))
                if cached["provenance"] != provenance:
                    raise ValueError("Verifier cache provenance differs")
                score = cached["score"]
                self._validate_score(score)
                if cached["sha256"] != text_hash(json.dumps(score)):
                    raise ValueError("Verifier cache checksum differs")
            except (ValueError, KeyError, TypeError) as exc:
                raise ValueError(
                    "Invalid verifier cache; preserve it and use a new cache_dir"
                ) from exc
            self.cache_hits += 1
        else:
            values = self.backend.score([(claim, evidence)])
            if len(values) != 1:
                raise ValueError("Verifier must return one probability per pair")
            score = values[0]
            self._validate_score(score)
            self.computed_pairs += 1
            atomic_write(
                path,
                json.dumps(
                    {
                        "provenance": provenance,
                        "score": score,
                        "sha256": text_hash(json.dumps(score)),
                    },
                    allow_nan=False,
                ).encode(),
            )
        return {
            "verifier": "minicheck",
            "model": self.identity["model"] + "@" + self.identity["revision"],
            "label": "supported"
            if score >= self.config.verification.support_threshold
            else "not_supported",
            "score": score,
            "rationale": None,
        }

    @staticmethod
    def _validate_score(score: object) -> None:
        if type(score) not in (float, int) or not math.isfinite(score) or not 0 <= score <= 1:
            raise ValueError("Verifier probability must be finite and between 0 and 1")
