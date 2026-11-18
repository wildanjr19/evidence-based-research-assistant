from dataclasses import replace

import pytest

from rag.chunking.core import chunk_document
from rag.config import ChunkingConfig
from rag.ids import is_valid_chunk_id
from rag.parsing.pdf import ParsedPaper, TextBlock

PAPER_ID = "arxiv:2401.12345v1"
CONFIG = ChunkingConfig(
    target_tokens=6,
    overlap_tokens=2,
    min_tokens=3,
    short_chunk_policy="merge",
    tokenizer="lexical-v1",
)


def document(*blocks: TextBlock) -> ParsedPaper:
    return ParsedPaper(PAPER_ID, max(block.page for block in blocks), list(blocks), 0)


def test_deterministic_chunks_preserve_overlap_and_cross_page_citations() -> None:
    source = document(
        TextBlock(1, "one two three four five six", "Methods", 1),
        TextBlock(2, "seven eight nine ten eleven twelve", "Methods", 1),
    )
    result = chunk_document(source, CONFIG)
    assert result == chunk_document(source, CONFIG)
    assert [chunk.chunk_id for chunk in result.chunks] == [
        f"{PAPER_ID}:p1:c01",
        f"{PAPER_ID}:p1:c02",
        f"{PAPER_ID}:p2:c03",
    ]
    assert [(chunk.page_start, chunk.page_end) for chunk in result.chunks] == [
        (1, 1),
        (1, 2),
        (2, 2),
    ]
    assert [chunk.n_tokens for chunk in result.chunks] == [6, 6, 4]
    assert result.chunks[1].text == "five six\nseven eight nine ten"
    assert all(is_valid_chunk_id(chunk.chunk_id) for chunk in result.chunks)
    assert result.dropped_tokens == 0


def test_sections_do_not_mix_and_repeated_titles_keep_their_order() -> None:
    source = document(
        TextBlock(1, "one two three four", "Methods", 1),
        TextBlock(1, "five six seven eight", "Methods", 2),
    )
    result = chunk_document(source, CONFIG)
    assert [chunk.section_order for chunk in result.chunks] == [1, 2]
    assert [chunk.chunk_order for chunk in result.chunks] == [1, 2]
    assert [chunk.text for chunk in result.chunks] == ["one two three four", "five six seven eight"]


def test_short_tail_merges_or_drops_only_new_tokens_according_to_config() -> None:
    source = document(TextBlock(1, "one two three four five six seven eight", None, None))
    config = replace(CONFIG, overlap_tokens=1, min_tokens=4)
    merged = chunk_document(source, config)
    dropped = chunk_document(source, replace(config, short_chunk_policy="drop"))
    assert [chunk.n_tokens for chunk in merged.chunks] == [8]
    assert merged.dropped_tokens == 0
    assert [chunk.n_tokens for chunk in dropped.chunks] == [6]
    assert dropped.dropped_tokens == 2


@pytest.mark.parametrize("policy", ["merge", "drop"])
def test_short_section_is_dropped_without_contaminating_other_sections(policy: str) -> None:
    source = document(
        TextBlock(1, "one two", "Short", 1), TextBlock(1, "three four five six", "Long", 2)
    )
    result = chunk_document(source, replace(CONFIG, short_chunk_policy=policy))
    assert result.dropped_tokens == 2
    assert [chunk.section for chunk in result.chunks] == ["Long"]
    assert result.chunks[0].chunk_id == f"{PAPER_ID}:p1:c01"


def test_punctuation_and_quotes_remain_in_source_form() -> None:
    source = document(TextBlock(1, "RRF improves recall.", None, None))
    result = chunk_document(source, CONFIG)
    assert result.chunks[0].text == "RRF improves recall."
    assert result.chunks[0].n_tokens == 4


def test_replacement_characters_are_flagged_without_inventing_evidence() -> None:
    source = document(TextBlock(1, "The damaged \ufffd text remains.", None, None))
    result = chunk_document(source, CONFIG)
    assert result.chunks[0].quality_flag == "low_quality"
    assert "\ufffd" in result.chunks[0].text


def test_invalid_overlap_cannot_create_an_infinite_loop() -> None:
    source = document(TextBlock(1, "one two three four", None, None))
    with pytest.raises(ValueError, match="overlap_tokens"):
        chunk_document(source, replace(CONFIG, overlap_tokens=6))
