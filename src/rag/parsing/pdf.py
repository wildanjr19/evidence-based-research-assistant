import math
import re
import unicodedata
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path

import pymupdf

from rag.config import ParsingConfig
from rag.ids import is_valid_paper_id


@dataclass(frozen=True)
class TextLine:
    page: int
    text: str
    bbox: tuple[float, float, float, float]
    font_size: float
    bold: bool


@dataclass(frozen=True)
class PageText:
    page: int
    width: float
    height: float
    lines: list[TextLine]


@dataclass(frozen=True)
class TextBlock:
    page: int
    text: str
    section: str | None
    section_order: int | None

    def __post_init__(self) -> None:
        if type(self.page) is not int or not 1 <= self.page <= 9999:
            raise ValueError("block page must be between 1 and 9999")
        if not isinstance(self.text, str) or not self.text.strip():
            raise ValueError("text block must not be empty")
        if self.section is None:
            if self.section_order is not None:
                raise ValueError("unsectioned block must not have a section order")
        elif (
            not isinstance(self.section, str)
            or not self.section.strip()
            or type(self.section_order) is not int
            or self.section_order < 1
        ):
            raise ValueError("section requires a name and positive order")


@dataclass(frozen=True)
class ParsedPaper:
    paper_id: str
    page_count: int
    blocks: list[TextBlock]
    removed_margin_lines: int

    def __post_init__(self) -> None:
        if not is_valid_paper_id(self.paper_id):
            raise ValueError("invalid parsed paper ID")
        if type(self.page_count) is not int or not 1 <= self.page_count <= 9999:
            raise ValueError("PDF page count must be between 1 and 9999")
        previous = 0
        for block in self.blocks:
            if not previous <= block.page <= self.page_count:
                raise ValueError("parsed blocks must follow PDF page order")
            previous = block.page
        if not self.blocks:
            raise ValueError("no extractable text; scanned PDFs require OCR (outside M2)")


def _normalize(text: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", text).replace("\u00ad", "").split())


def reading_order(lines: list[TextLine], width: float) -> list[TextLine]:
    """Read two columns within bands separated by full-width lines."""
    middle = width / 2
    left = [line for line in lines if line.bbox[2] <= middle]
    right = [line for line in lines if line.bbox[0] >= middle]
    if (
        not left
        or not right
        or max(min(line.bbox[1] for line in left), min(line.bbox[1] for line in right))
        >= min(max(line.bbox[3] for line in left), max(line.bbox[3] for line in right))
    ):
        return sorted(lines, key=lambda line: (line.bbox[1], line.bbox[0]))
    spanning = sorted(
        (line for line in lines if line.bbox[0] < middle < line.bbox[2]),
        key=lambda line: (line.bbox[1], line.bbox[0]),
    )
    remaining = left + right
    ordered = []
    for separator in spanning:
        band = [line for line in remaining if line.bbox[1] < separator.bbox[1]]
        ordered.extend(
            sorted(band, key=lambda line: (line.bbox[0] >= middle, line.bbox[1], line.bbox[0]))
        )
        remaining = [line for line in remaining if line.bbox[1] >= separator.bbox[1]]
        ordered.append(separator)
    ordered.extend(
        sorted(remaining, key=lambda line: (line.bbox[0] >= middle, line.bbox[1], line.bbox[0]))
    )
    return ordered


def normalize_pages(paper_id: str, pages: list[PageText], config: ParsingConfig) -> ParsedPaper:
    occurrences: dict[tuple[str, str], set[int]] = defaultdict(set)
    margins: dict[tuple[int, int], tuple[str, str]] = {}
    normalized: list[PageText] = []
    for page in pages:
        lines = []
        for original in page.lines:
            text = _normalize(original.text)
            if not text:
                continue
            line = TextLine(original.page, text, original.bbox, original.font_size, original.bold)
            index = len(lines)
            lines.append(line)
            region = (
                "top"
                if line.bbox[3] <= page.height * config.margin_ratio
                else "bottom"
                if line.bbox[1] >= page.height * (1 - config.margin_ratio)
                else None
            )
            if region:
                key = (region, re.sub(r"\d+", "#", text.casefold()))
                margins[(page.page, index)] = key
                occurrences[key].add(page.page)
        normalized.append(PageText(page.page, page.width, page.height, lines))
    threshold = max(config.min_repeated_pages, math.ceil(len(pages) * config.repeated_margin_ratio))
    repeated = {key for key, page_numbers in occurrences.items() if len(page_numbers) >= threshold}
    font_counts: Counter[float] = Counter()
    for page in normalized:
        for index, line in enumerate(page.lines):
            if margins.get((page.page, index)) not in repeated:
                font_counts[line.font_size] += len(line.text)
    body_size = font_counts.most_common(1)[0][0] if font_counts else 0
    blocks = []
    section = None
    section_order = 0
    removed = 0
    known_heading = re.compile(
        r"(?:abstract|introduction|background|related work|methods?|results|discussion|"
        r"conclusions?|references|acknowledg(?:e)?ments|appendix(?: [A-Z])?)[:.]?",
        re.I,
    )
    for page in normalized:
        lines = []
        for index, line in enumerate(page.lines):
            if margins.get((page.page, index)) in repeated:
                removed += 1
            else:
                lines.append(line)
        for line in reading_order(lines, page.width):
            numbered = re.match(r"(?:[0-9]+(?:\.[0-9]+)*\.?|[A-Z])\s+\S", line.text)
            if len(line.text.split()) <= config.heading_max_words and (
                known_heading.fullmatch(line.text)
                or numbered
                and (line.bold or line.font_size > body_size)
            ):
                section = line.text
                section_order += 1
            blocks.append(TextBlock(page.page, line.text, section, section_order or None))
    return ParsedPaper(paper_id, len(pages), blocks, removed)


def parse_pdf(path: Path, paper_id: str, config: ParsingConfig) -> ParsedPaper:
    pages = []
    with pymupdf.open(path) as document:
        if not document.is_pdf or document.needs_pass:
            raise ValueError("expected an unencrypted PDF")
        if not 1 <= document.page_count <= 9999:
            raise ValueError("PDF page count exceeds the chunk ID format")
        for page in document:
            lines = []
            for block in page.get_text("dict")["blocks"]:
                if block.get("type") != 0:
                    continue
                for line in block["lines"]:
                    spans = line["spans"]
                    text = "".join(span["text"] for span in spans)
                    if text.strip():
                        lines.append(
                            TextLine(
                                page.number + 1,
                                text,
                                tuple(line["bbox"]),
                                round(max(span["size"] for span in spans), 1),
                                all(span["flags"] & 16 for span in spans if span["text"].strip()),
                            )
                        )
            pages.append(PageText(page.number + 1, page.cropbox.width, page.cropbox.height, lines))
    return normalize_pages(paper_id, pages, config)
