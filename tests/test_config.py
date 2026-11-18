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
        ("retrieval", "use_reranker", "false"),
        ("retrieval", "final_top_k", 51),
        ("generation", "temperature", float("nan")),
        ("generation", "temperature", float("inf")),
        ("generation", "temperature", -0.1),
        ("generation", "temperature", False),
        ("generation", "max_calls_per_run", 0),
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
