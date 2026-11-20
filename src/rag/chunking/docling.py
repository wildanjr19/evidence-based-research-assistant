"""Chunk checked Docling content without splitting table rows or their context."""

import json
import re
from collections.abc import Callable
from dataclasses import replace

from rag.chunking.core import TOKEN_PATTERN, Chunk, chunk_document
from rag.config import ChunkingConfig
from rag.ids import make_chunk_id
from rag.parsing.docling_adapter import AdaptedPaper
from rag.parsing.pdf import ParsedPaper, TextBlock


def _row_text(values: list[str]) -> str:
    return " | ".join(
        json.dumps(v, ensure_ascii=False) if any(c in v for c in '|\n\r"') else v for v in values
    )


def chunk_adapted(
    document: AdaptedPaper,
    config: ChunkingConfig,
    token_count: Callable[[str], int],
    max_model_tokens: int,
) -> tuple[list[Chunk], list[dict]]:
    """Repeat all table context; hold whole tables when even one row cannot fit."""
    chunks, events, narrative = [], [], []

    def append(text: str, page: int, section: str | None, order: int | None) -> None:
        ordinal = len(chunks) + 1
        chunks.append(
            Chunk(
                make_chunk_id(document.paper_id, page, ordinal),
                document.paper_id,
                page,
                page,
                section,
                order,
                ordinal,
                text,
                len(re.findall(TOKEN_PATTERN, text)),
                "ok",
            )
        )

    def flush() -> None:
        if not narrative:
            return
        parsed = ParsedPaper(document.paper_id, document.page_count, list(narrative), 0)
        result = chunk_document(
            parsed, config, fits_model=lambda text: token_count(text) <= max_model_tokens
        )
        events.append(dict(kind="narrative", dropped_lexical_tokens=result.dropped_tokens))
        for chunk in result.chunks:
            if token_count(chunk.text) > max_model_tokens:
                events.append(
                    dict(
                        kind="held_narrative",
                        page=chunk.page_start,
                        reason="model_token_limit",
                        text=chunk.text,
                    )
                )
                continue
            ordinal = len(chunks) + 1
            chunks.append(
                replace(
                    chunk,
                    chunk_order=ordinal,
                    chunk_id=make_chunk_id(document.paper_id, chunk.page_start, ordinal),
                )
            )
        narrative.clear()

    for block in document.blocks:
        if isinstance(block, TextBlock):
            narrative.append(block)
            continue
        flush()
        prefix = f"{block.caption}\n" + _row_text(block.header) + "\n"
        suffix = "\n" + block.notes if block.notes else ""
        batches, current = [], []
        for index, row in enumerate(block.rows):
            line = _row_text(row)
            if block.row_contexts and block.row_contexts[index]:
                line = "[" + block.row_contexts[index] + "]\n" + line
            candidate = prefix + "\n".join([*current, line]) + suffix
            if current and (
                token_count(candidate) > max_model_tokens
                or len(re.findall(TOKEN_PATTERN, candidate)) > config.target_tokens
            ):
                batches.append(prefix + "\n".join(current) + suffix)
                current = []
            current.append(line)
        if current:
            batches.append(prefix + "\n".join(current) + suffix)
        if any(
            token_count(text) > max_model_tokens
            or len(re.findall(TOKEN_PATTERN, text)) > config.target_tokens
            for text in batches
        ):
            events.append(dict(kind="held_table", ref=block.ref, reason="row_or_context_too_long"))
            continue
        for text in batches:
            append(text, block.page, block.caption, 1)
        events.append(dict(kind="table", ref=block.ref, rows=len(block.rows), chunks=len(batches)))
    flush()
    return chunks, events
