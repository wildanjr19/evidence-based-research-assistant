import re
import unicodedata
from collections.abc import Callable
from dataclasses import dataclass
from itertools import groupby

from rag.config import ChunkingConfig
from rag.ids import make_chunk_id
from rag.parsing.pdf import ParsedPaper

TOKEN_PATTERN = r"\w+|[^\w\s]"


@dataclass(frozen=True)
class Chunk:
    chunk_id: str
    paper_id: str
    page_start: int
    page_end: int
    section: str | None
    section_order: int | None
    chunk_order: int
    text: str
    n_tokens: int
    quality_flag: str


@dataclass(frozen=True)
class ChunkingResult:
    chunks: list[Chunk]
    dropped_tokens: int


def _windows(
    length: int,
    config: ChunkingConfig,
    fits_model: Callable[[int, int], bool] | None = None,
) -> tuple[list[tuple[int, int]], int]:
    windows: list[tuple[int, int]] = []
    start = 0
    while start < length:
        end = min(start + config.target_tokens, length)
        while fits_model and end > start + 1 and not fits_model(start, end):
            end -= 1
        if end == length and end - start < config.min_tokens:
            if (
                windows
                and config.short_chunk_policy == "merge"
                and (fits_model is None or fits_model(windows[-1][0], end))
            ):
                windows[-1] = (windows[-1][0], end)
                return windows, 0
            if fits_model is None or config.short_chunk_policy == "drop" or not windows:
                return windows, length - (windows[-1][1] if windows else 0)
        windows.append((start, end))
        if end == length:
            break
        start = end - min(config.overlap_tokens, end - start - 1)
    return windows, 0


def chunk_document(
    document: ParsedPaper,
    config: ChunkingConfig,
    *,
    fits_model: Callable[[str], bool] | None = None,
) -> ChunkingResult:
    if not 0 <= config.overlap_tokens < config.target_tokens:
        raise ValueError("overlap_tokens must be >= 0 and < target_tokens")
    if not 1 <= config.min_tokens <= config.target_tokens:
        raise ValueError("min_tokens must be >= 1 and <= target_tokens")
    if config.short_chunk_policy not in {"merge", "drop"} or config.tokenizer != "lexical-v1":
        raise ValueError("unsupported chunking policy or tokenizer")
    chunks = []
    dropped = 0
    for (section, section_order), group in groupby(
        document.blocks, key=lambda block: (block.section, block.section_order)
    ):
        parts = []
        positions: list[tuple[int, int, int]] = []
        offset = 0
        for block in group:
            parts.append(block.text)
            # shortcut: lexical counts differ from model tokens; enforce embedding limits in M3.
            positions.extend(
                (offset + match.start(), offset + match.end(), block.page)
                for match in re.finditer(TOKEN_PATTERN, block.text)
            )
            offset += len(block.text) + 1
        text = "\n".join(parts)

        def fits(start: int, end: int, source=text, spans=positions) -> bool:
            return fits_model(source[spans[start][0] : spans[end - 1][1]])

        windows, lost = _windows(len(positions), config, fits if fits_model else None)
        dropped += lost
        for start, end in windows:
            page_start, page_end = positions[start][2], positions[end - 1][2]
            content = text[positions[start][0] : positions[end - 1][1]]
            corrupted = "\ufffd" in content or any(
                unicodedata.category(character) == "Cc" and character not in "\n\r\t"
                for character in content
            )
            ordinal = len(chunks) + 1
            chunks.append(
                Chunk(
                    make_chunk_id(document.paper_id, page_start, ordinal),
                    document.paper_id,
                    page_start,
                    page_end,
                    section,
                    section_order,
                    ordinal,
                    content,
                    end - start,
                    "low_quality" if corrupted else "ok",
                )
            )
    return ChunkingResult(chunks, dropped)
