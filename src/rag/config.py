"""Load the experiment configuration without initializing models or clients."""

import math
from dataclasses import dataclass, fields
from pathlib import Path
from typing import TypeVar

import yaml


class ConfigError(ValueError):
    """The configuration cannot be read or contains invalid values."""


@dataclass(frozen=True)
class ChunkingConfig:
    target_tokens: int
    overlap_tokens: int
    min_tokens: int


@dataclass(frozen=True)
class EmbeddingConfig:
    model: str
    batch_size: int
    device: str


@dataclass(frozen=True)
class RetrievalConfig:
    dense_top_k: int
    bm25_top_k: int
    rrf_k: int
    rerank_candidates: int
    final_top_k: int
    use_reranker: bool
    reranker_model: str


@dataclass(frozen=True)
class GenerationConfig:
    provider: str
    model: str
    temperature: float
    max_calls_per_run: int


@dataclass(frozen=True)
class VerificationConfig:
    minicheck_model: str
    judge_model: str
    judge_provider: str
    judge_sample_rate: float
    seed: int


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
    chunking: ChunkingConfig
    embedding: EmbeddingConfig
    retrieval: RetrievalConfig
    generation: GenerationConfig
    verification: VerificationConfig
    evaluation: EvaluationConfig
    paths: PathsConfig


T = TypeVar("T")


def _parse_value(value: object, expected: object, key: str) -> object:
    if expected is str and isinstance(value, str) and value.strip():
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
    raise ConfigError(f"{key}: expected {expected}, with a non-empty, finite value")


def _section(raw: dict, name: str, section_type: type[T]) -> T:
    section = raw.get(name)
    if not isinstance(section, dict):
        raise ConfigError(f"{name}: required section must be a mapping")
    section_fields = fields(section_type)
    names = {field.name for field in section_fields}
    if unknown := section.keys() - names:
        raise ConfigError(f"{name}: unknown keys: {', '.join(sorted(map(str, unknown)))}")
    values = {}
    for field in section_fields:
        key = f"{name}.{field.name}"
        if field.name not in section:
            raise ConfigError(f"{key}: required key is missing")
        value = _parse_value(section[field.name], field.type, key)
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
        chunking=_section(raw, "chunking", ChunkingConfig),
        embedding=_section(raw, "embedding", EmbeddingConfig),
        retrieval=_section(raw, "retrieval", RetrievalConfig),
        generation=_section(raw, "generation", GenerationConfig),
        verification=_section(raw, "verification", VerificationConfig),
        evaluation=_section(raw, "evaluation", EvaluationConfig),
        paths=_section(raw, "paths", PathsConfig),
    )
    if config.chunking.overlap_tokens >= config.chunking.target_tokens:
        raise ConfigError("chunking.overlap_tokens: must be < chunking.target_tokens")
    if config.chunking.min_tokens > config.chunking.target_tokens:
        raise ConfigError("chunking.min_tokens: must be <= chunking.target_tokens")
    if config.generation.temperature < 0:
        raise ConfigError("generation.temperature: must be >= 0")
    if not 0 <= config.verification.judge_sample_rate <= 1:
        raise ConfigError("verification.judge_sample_rate: must be between 0 and 1")
    if (
        config.retrieval.use_reranker
        and config.retrieval.final_top_k > config.retrieval.rerank_candidates
    ):
        raise ConfigError("retrieval.final_top_k: must be <= retrieval.rerank_candidates")
    return config
