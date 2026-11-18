import json
import math
from pathlib import Path
from typing import Protocol

from rag.config import Config
from rag.files import atomic_write
from rag.indexing.embedding import text_hash


class Reranker(Protocol):
    def score(self, pairs: list[tuple[str, str]]) -> list[float]: ...


class BGEReranker:
    def __init__(self, config: Config) -> None:
        import torch
        from transformers import AutoModelForSequenceClassification, AutoTokenizer

        if config.embedding.device.startswith("cuda") and not torch.cuda.is_available():
            raise ValueError("CUDA is unavailable; use embedding.device: cpu or install CUDA")
        torch.manual_seed(config.verification.seed)
        self.device = config.embedding.device
        self.max_tokens = config.retrieval.reranker_max_tokens
        options = {
            "revision": config.retrieval.reranker_revision,
            "cache_dir": str(Path(config.paths.cache_dir) / "models"),
            "trust_remote_code": False,
        }
        self.tokenizer = AutoTokenizer.from_pretrained(config.retrieval.reranker_model, **options)
        self.model = AutoModelForSequenceClassification.from_pretrained(
            config.retrieval.reranker_model, **options
        ).to(self.device)
        self.model.eval()
        if self.max_tokens > self.tokenizer.model_max_length:
            raise ValueError("reranker_max_tokens exceeds the model tokenizer limit")

    def score(self, pairs: list[tuple[str, str]]) -> list[float]:
        import torch

        # Keep the complete question; only the reranker's document view may be shortened.
        for question, _ in pairs:
            tokens = len(self.tokenizer.encode(question, add_special_tokens=False))
            if tokens + self.tokenizer.num_special_tokens_to_add(pair=True) >= self.max_tokens:
                raise ValueError("Question exceeds the reranker pair limit")
        encoded = self.tokenizer(
            [question for question, _ in pairs],
            [text for _, text in pairs],
            padding=True,
            truncation="only_second",
            max_length=self.max_tokens,
            return_tensors="pt",
        ).to(self.device)
        with torch.inference_mode():
            scores = self.model(**encoded).logits
        if scores.ndim != 2 or scores.shape[1] != 1:
            raise ValueError("Reranker must return one relevance logit per pair")
        return scores[:, 0].float().cpu().tolist()


def reranker_identity(config: Config) -> dict:
    return {
        "model": config.retrieval.reranker_model,
        "revision": config.retrieval.reranker_revision,
        "max_tokens": config.retrieval.reranker_max_tokens,
        "truncation": "only_second",
        "score": "raw_logit",
    }


def rerank(
    question: str, chunks: list[dict], config: Config, model: Reranker | None
) -> tuple[list[tuple[str, float]], Reranker | None, dict]:
    identity = reranker_identity(config)
    scores = {}
    pending = {}
    chunk_keys = []
    for chunk in chunks:
        provenance = {
            "identity": identity,
            "question_sha256": text_hash(question),
            "text_sha256": text_hash(chunk["text"]),
        }
        key = text_hash(json.dumps(provenance, sort_keys=True))
        chunk_keys.append((chunk["chunk_id"], key))
        path = Path(config.paths.cache_dir) / "reranking" / f"{key}.json"
        if path.exists():
            cached = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(cached, dict) or cached.get("provenance") != provenance:
                raise ValueError(f"Invalid reranker cache: {path}")
            score = cached.get("score")
            if type(score) not in (int, float) or not math.isfinite(score):
                raise ValueError(f"Invalid reranker cache score: {path}")
            scores[key] = float(score)
        else:
            pending[key] = (chunk["text"], provenance, path)
    cache_hits = len(scores)
    keys = list(pending)
    for offset in range(0, len(keys), config.retrieval.reranker_batch_size):
        batch = keys[offset : offset + config.retrieval.reranker_batch_size]
        if model is None:
            model = BGEReranker(config)
        values = model.score([(question, pending[key][0]) for key in batch])
        if len(values) != len(batch) or any(
            type(value) not in (int, float) or not math.isfinite(value) for value in values
        ):
            raise ValueError("Reranker returned invalid scores")
        for key, value in zip(batch, values, strict=True):
            _, provenance, path = pending[key]
            atomic_write(
                path,
                json.dumps({"provenance": provenance, "score": value}, allow_nan=False).encode(),
            )
            scores[key] = float(value)
    hits = [(identifier, scores[key]) for identifier, key in chunk_keys]
    return (
        sorted(hits, key=lambda hit: (-hit[1], hit[0])),
        model,
        {
            "reranker_cache_hits": cache_hits,
            "computed_pairs": len(pending),
        },
    )
