from pathlib import Path

import pytest
import yaml

from rag.config import ConfigError, load_config

DEFAULT_CONFIG = Path(__file__).resolve().parents[1] / "configs" / "config.yaml"


@pytest.fixture
def config_data() -> dict:
    return yaml.safe_load(DEFAULT_CONFIG.read_text(encoding="utf-8"))


def write_config(tmp_path: Path, data: object) -> Path:
    path = tmp_path / "config.yaml"
    path.write_text(yaml.safe_dump(data), encoding="utf-8")
    return path


def test_load_repository_config() -> None:
    config = load_config(DEFAULT_CONFIG)
    assert config.chunking.target_tokens == 400
    assert config.embedding.device == "cpu"
    assert config.retrieval.use_reranker is True
    assert config.verification.seed == 42
    assert config.evaluation.ks == [5, 10, 20]
    assert config.paths.db_path == "data/index/corpus.db"
    assert config.ingestion.max_papers == 10


@pytest.mark.parametrize(
    "section",
    [
        "ingestion",
        "chunking",
        "embedding",
        "retrieval",
        "generation",
        "verification",
        "evaluation",
        "paths",
    ],
)
def test_missing_section_is_clear(config_data: dict, tmp_path: Path, section: str) -> None:
    del config_data[section]
    with pytest.raises(ConfigError, match=section):
        load_config(write_config(tmp_path, config_data))


def test_missing_key_is_clear(config_data: dict, tmp_path: Path) -> None:
    del config_data["generation"]["max_calls_per_run"]
    with pytest.raises(ConfigError, match=r"generation\.max_calls_per_run"):
        load_config(write_config(tmp_path, config_data))


@pytest.mark.parametrize(
    ("section", "key", "value"),
    [
        ("parsing", "margin_ratio", 0.5),
        ("parsing", "margin_ratio", 0),
        ("parsing", "repeated_margin_ratio", 0),
        ("parsing", "repeated_margin_ratio", 1.1),
        ("parsing", "min_repeated_pages", 1),
        ("parsing", "heading_max_words", 0),
        ("chunking", "short_chunk_policy", "keep"),
        ("chunking", "tokenizer", "unknown"),
        ("ingestion", "max_papers", 0),
        ("ingestion", "page_size", 0),
        ("ingestion", "request_delay_seconds", 2.9),
        ("ingestion", "timeout_seconds", 0),
        ("ingestion", "max_pdf_bytes", -1),
        ("ingestion", "allowed_licenses", []),
        ("ingestion", "allowed_licenses", ["CC-BY-4.0", 5]),
        ("chunking", "target_tokens", True),
        ("chunking", "target_tokens", "400"),
        ("chunking", "target_tokens", 0),
        ("chunking", "overlap_tokens", -1),
        ("chunking", "overlap_tokens", 400),
        ("chunking", "min_tokens", 401),
        ("embedding", "batch_size", 0),
        ("embedding", "model", "  "),
        ("embedding", "revision", "main"),
        ("embedding", "max_tokens", 0),
        ("embedding", "device", "gpu"),
        ("retrieval", "use_reranker", "false"),
        ("retrieval", "reranker_revision", "main"),
        ("retrieval", "reranker_max_tokens", 0),
        ("retrieval", "reranker_batch_size", 0),
        ("retrieval", "final_top_k", 51),
        ("generation", "temperature", float("nan")),
        ("generation", "temperature", float("inf")),
        ("generation", "temperature", -0.1),
        ("generation", "temperature", False),
        ("generation", "max_calls_per_run", 0),
        ("generation", "max_output_tokens", 0),
        ("generation", "timeout_seconds", 0),
        ("generation", "provider", "unknown"),
        ("generation", "base_url", "http://example.invalid"),
        ("generation", "base_url", "https://key@example.invalid"),
        ("generation", "base_url", "https://example.invalid?key=secret"),
        ("generation", "base_url", "https://[invalid"),
        ("verification", "judge_sample_rate", 1.1),
        ("verification", "judge_sample_rate", -0.1),
        ("verification", "seed", -1),
        ("evaluation", "ks", []),
        ("evaluation", "ks", [5, True]),
        ("evaluation", "ks", [0, 10]),
        ("evaluation", "ks", "5,10,20"),
        ("paths", "db_path", None),
    ],
)
def test_invalid_values_are_clear(
    config_data: dict, tmp_path: Path, section: str, key: str, value: object
) -> None:
    config_data[section][key] = value
    with pytest.raises(ConfigError, match=rf"{section}\.{key}"):
        load_config(write_config(tmp_path, config_data))


def test_zero_boundaries_and_integer_temperature(config_data: dict, tmp_path: Path) -> None:
    config_data["chunking"]["overlap_tokens"] = 0
    config_data["retrieval"]["rrf_k"] = 0
    config_data["generation"]["temperature"] = 0
    config_data["verification"]["seed"] = 0
    config_data["verification"]["judge_sample_rate"] = 0
    config = load_config(write_config(tmp_path, config_data))
    assert config.chunking.overlap_tokens == 0
    assert config.generation.temperature == 0.0
    assert type(config.generation.temperature) is float


@pytest.mark.parametrize("section", [None, "retrieval"])
def test_unknown_keys_are_rejected(config_data: dict, tmp_path: Path, section: str | None) -> None:
    target = config_data if section is None else config_data[section]
    target["typo"] = 5
    with pytest.raises(ConfigError, match="typo"):
        load_config(write_config(tmp_path, config_data))


@pytest.mark.parametrize("data", [None, [], "not a mapping", 3])
def test_non_mapping_root_is_rejected(tmp_path: Path, data: object) -> None:
    with pytest.raises(ConfigError, match="root must be a mapping"):
        load_config(write_config(tmp_path, data))


def test_non_mapping_section_is_rejected(config_data: dict, tmp_path: Path) -> None:
    config_data["chunking"] = []
    with pytest.raises(ConfigError, match="chunking"):
        load_config(write_config(tmp_path, config_data))


def test_malformed_yaml_and_missing_file(tmp_path: Path) -> None:
    path = tmp_path / "config.yaml"
    with pytest.raises(ConfigError, match="Cannot read configuration"):
        load_config(path)
    path.write_text("chunking: [", encoding="utf-8")
    with pytest.raises(ConfigError, match="Cannot read configuration"):
        load_config(path)


def test_relative_data_paths_do_not_depend_on_config_location(
    config_data: dict, tmp_path: Path
) -> None:
    config = load_config(write_config(tmp_path, config_data))
    assert config.paths.raw_dir == "data/raw"


def test_m1_configs_load_with_explicit_m2_defaults(config_data: dict, tmp_path: Path) -> None:
    del config_data["parsing"]
    del config_data["chunking"]["short_chunk_policy"]
    del config_data["chunking"]["tokenizer"]
    config = load_config(write_config(tmp_path, config_data))
    assert config.parsing == load_config(DEFAULT_CONFIG).parsing
    assert config.chunking.short_chunk_policy == "merge"
    assert config.chunking.tokenizer == "lexical-v1"


def test_null_parsing_section_does_not_silently_use_defaults(
    config_data: dict, tmp_path: Path
) -> None:
    config_data["parsing"] = None
    with pytest.raises(ConfigError, match="parsing"):
        load_config(write_config(tmp_path, config_data))


def test_old_embedding_config_uses_pinned_defaults(config_data: dict, tmp_path: Path) -> None:
    del config_data["embedding"]["revision"]
    del config_data["embedding"]["max_tokens"]
    config = load_config(write_config(tmp_path, config_data))
    assert len(config.embedding.revision) == 40
    assert config.embedding.max_tokens == 512


def test_old_retrieval_configs_use_m4_defaults_and_prefix_can_be_disabled(
    config_data: dict, tmp_path: Path
) -> None:
    for key in ("query_prefix", "reranker_revision", "reranker_max_tokens", "reranker_batch_size"):
        del config_data["retrieval"][key]
    config = load_config(write_config(tmp_path, config_data))
    assert len(config.retrieval.reranker_revision) == 40
    assert config.retrieval.reranker_max_tokens == 512
    config_data["retrieval"]["query_prefix"] = ""
    assert load_config(write_config(tmp_path, config_data)).retrieval.query_prefix == ""


def test_old_generation_configs_get_m5_limits(config_data: dict, tmp_path: Path) -> None:
    for key in ("max_output_tokens", "timeout_seconds", "base_url"):
        del config_data["generation"][key]
    config = load_config(write_config(tmp_path, config_data))
    assert config.generation.max_output_tokens == 2048
    assert config.generation.timeout_seconds == 60.0
    assert config.generation.base_url == ""
