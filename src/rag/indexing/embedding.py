import hashlib
import json
import math
from pathlib import Path
from typing import Protocol

from rag.config import Config
from rag.files import atomic_write


class Embedder(Protocol):
    dimension: int
    max_tokens: int

    def token_counts(self, texts: list[str]) -> list[int]: ...

    def encode(self, texts: list[str]) -> list[list[float]]: ...


class SentenceEmbedder:
    def __init__(self, config: Config) -> None:
        import torch
        from sentence_transformers import SentenceTransformer

        if config.embedding.device.startswith("cuda") and not torch.cuda.is_available():
            raise ValueError(
                "CUDA is unavailable; install a CUDA build or use embedding.device: cpu"
            )
        torch.manual_seed(config.verification.seed)
        self.model = SentenceTransformer(
            config.embedding.model,
            revision=config.embedding.revision,
            device=config.embedding.device,
            cache_folder=str(Path(config.paths.cache_dir) / "models"),
            trust_remote_code=False,
        )
        self.dimension = self.model.get_embedding_dimension()
        self.max_tokens = min(config.embedding.max_tokens, self.model.max_seq_length)
        self.model.max_seq_length = self.max_tokens
        self.batch_size = config.embedding.batch_size

    def token_counts(self, texts: list[str]) -> list[int]:
        encoded = self.model.tokenizer(
            texts, add_special_tokens=True, truncation=False, padding=False
        )
        return [len(tokens) for tokens in encoded["input_ids"]]

    def encode(self, texts: list[str]) -> list[list[float]]:
        return self.model.encode(
            texts,
            batch_size=self.batch_size,
            normalize_embeddings=True,
            precision="float32",
            prompt="",
            show_progress_bar=False,
            convert_to_numpy=True,
        ).tolist()


def text_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def embedding_identity(config: Config, embedder: Embedder) -> dict:
    return {
        "model": config.embedding.model,
        "revision": config.embedding.revision,
        "dimension": embedder.dimension,
        "max_tokens": embedder.max_tokens,
        "normalize_embeddings": True,
        "precision": "float32",
        "document_prompt": "",
    }


def validate_vector(vector: object, dimension: int) -> None:
    if (
        not isinstance(vector, list)
        or len(vector) != dimension
        or any(type(value) not in (int, float) or not math.isfinite(value) for value in vector)
        or not math.isclose(sum(value * value for value in vector), 1.0, abs_tol=1e-4)
    ):
        raise ValueError(
            "Invalid embedding: expected a finite, normalized vector of model dimension"
        )


def embed_chunks(
    chunks: list[dict], config: Config, embedder: Embedder
) -> tuple[list[list[float]], dict]:
    identity = embedding_identity(config, embedder)
    counts = []
    batch_size = config.embedding.batch_size
    for offset in range(0, len(chunks), batch_size):
        texts = [chunk["text"] for chunk in chunks[offset : offset + batch_size]]
        batch_counts = embedder.token_counts(texts)
        if len(batch_counts) != len(texts) or any(
            type(n) is not int or n < 1 for n in batch_counts
        ):
            raise ValueError("Embedder returned invalid token counts")
        counts.extend(batch_counts)
    oversized = [
        f"{chunk['chunk_id']} ({count})"
        for chunk, count in zip(chunks, counts, strict=True)
        if count > embedder.max_tokens
    ]
    if oversized:
        raise ValueError(
            f"Chunks exceed model limit {embedder.max_tokens} tokens including special tokens: "
            + ", ".join(oversized)
            + ". Use smaller chunks in a separate database; existing text was not truncated."
        )

    unique = {}
    keys = []
    for chunk, count in zip(chunks, counts, strict=True):
        digest = text_hash(chunk["text"])
        key = text_hash(json.dumps([identity, digest], sort_keys=True))
        keys.append(key)
        unique.setdefault(key, (chunk["text"], count, digest))
    vectors = {}
    pending = []
    cache_dir = Path(config.paths.cache_dir) / "embeddings"
    for key, (_text, count, digest) in unique.items():
        path = cache_dir / f"{key}.json"
        if not path.exists():
            pending.append(key)
            continue
        try:
            cached = json.loads(path.read_text(encoding="utf-8"))
            if (
                cached["identity"] != identity
                or cached["text_sha256"] != digest
                or cached["model_tokens"] != count
            ):
                raise ValueError("cache provenance differs")
            validate_vector(cached["vector"], embedder.dimension)
            vectors[key] = cached["vector"]
        except (ValueError, KeyError, TypeError) as exc:
            raise ValueError(f"Invalid embedding cache {path}: {exc}") from exc
    cache_hits = len(vectors)
    for offset in range(0, len(pending), batch_size):
        batch = pending[offset : offset + batch_size]
        encoded = embedder.encode([unique[key][0] for key in batch])
        if len(encoded) != len(batch):
            raise ValueError("Embedder returned the wrong number of vectors")
        for vector in encoded:
            validate_vector(vector, embedder.dimension)
        for key, vector in zip(batch, encoded, strict=True):
            _, count, digest = unique[key]
            cached = {
                "identity": identity,
                "text_sha256": digest,
                "model_tokens": count,
                "vector": vector,
            }
            path = cache_dir / f"{key}.json"
            atomic_write(path, json.dumps(cached, allow_nan=False).encode("utf-8"))
            vectors[key] = vector
    return [vectors[key] for key in keys], {
        "unique_texts": len(unique),
        "cache_hits": cache_hits,
        "computed_embeddings": len(pending),
        "model_tokens": sum(counts),
        "computed_tokens": sum(unique[key][1] for key in pending),
        "max_chunk_model_tokens": max(counts, default=0),
    }
