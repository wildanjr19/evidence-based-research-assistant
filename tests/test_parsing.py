from dataclasses import replace
from pathlib import Path

import pymupdf
import pytest

from rag.config import load_config
from rag.parsing.pdf import PageText, TextLine, normalize_pages, parse_pdf

PAPER_ID = "arxiv:2401.12345v1"


def line(
    text: str,
    y: float,
    *,
    page: int = 1,
    x: float = 50,
    width: float = 200,
    size: float = 11,
    bold: bool = False,
) -> TextLine:
    return TextLine(page, text, (x, y, x + width, y + 12), size, bold)


def test_two_columns_follow_reading_order_around_full_width_lines() -> None:
    config = load_config().parsing
    lines = [
        line("right bottom", 170, x=330),
        line("left bottom", 170),
        line("right top", 140, x=330),
        line("left top", 140),
        line("Full width title", 90, x=150, width=300),
        line("Full width caption", 220, width=500),
        line("second right", 300, x=330),
        line("second left", 300),
    ]
    document = normalize_pages(PAPER_ID, [PageText(1, 600, 800, lines)], config)
    assert [block.text for block in document.blocks] == [
        "Full width title",
        "left top",
        "left bottom",
        "right top",
        "right bottom",
        "Full width caption",
        "second left",
        "second right",
    ]


def test_repeated_margins_are_removed_but_repeated_body_text_survives() -> None:
    pages = []
    for number in range(1, 4):
        pages.append(
            PageText(
                number,
                600,
                800,
                [
                    line("Synthetic conference 2024", 10, page=number),
                    line("Repeated body evidence", 100, page=number),
                    line(f"Page {number}", 770, page=number),
                ],
            )
        )
    document = normalize_pages(PAPER_ID, pages, load_config().parsing)
    assert document.removed_margin_lines == 6
    assert [block.text for block in document.blocks] == ["Repeated body evidence"] * 3
    assert [block.page for block in document.blocks] == [1, 2, 3]


def test_heading_sections_carry_across_pages_and_roman_body_is_not_a_heading() -> None:
    pages = [
        PageText(
            1,
            600,
            800,
            [
                line("1 Introduction", 100, size=14, bold=True),
                line("The evidence remains on page one.", 140),
            ],
        ),
        PageText(
            2,
            600,
            800,
            [
                line("Continued evidence on page two.", 100, page=2),
                line("2 Methods", 160, page=2, size=14, bold=True),
                line("1 ordinary list item", 200, page=2),
            ],
        ),
    ]
    document = normalize_pages(PAPER_ID, pages, load_config().parsing)
    assert [block.section for block in document.blocks] == [
        "1 Introduction",
        "1 Introduction",
        "1 Introduction",
        "2 Methods",
        "2 Methods",
    ]
    assert [block.section_order for block in document.blocks] == [1, 1, 1, 2, 2]


def test_normalization_retains_page_numbers_and_normalizes_ligatures() -> None:
    document = normalize_pages(
        PAPER_ID,
        [
            PageText(
                1,
                600,
                800,
                [
                    line("  An   of\ufb01ce\u00ad example  ", 100),
                ],
            )
        ],
        load_config().parsing,
    )
    assert document.blocks[0].text == "An office example"
    assert document.blocks[0].page == 1
    assert document.blocks[0].section is None


def test_page_without_two_overlapping_columns_stays_in_vertical_order() -> None:
    document = normalize_pages(
        PAPER_ID,
        [
            PageText(
                1,
                600,
                800,
                [
                    line("first body line", 100, width=450),
                    line("short body line", 140),
                    line("right aligned footer", 300, x=330),
                ],
            )
        ],
        load_config().parsing,
    )
    assert [block.text for block in document.blocks] == [
        "first body line",
        "short body line",
        "right aligned footer",
    ]


def test_actual_pdf_extraction_with_two_columns_and_repeated_margins(tmp_path: Path) -> None:
    path = tmp_path / "synthetic.pdf"
    with pymupdf.open() as document:
        for number in range(1, 4):
            page = document.new_page(width=600, height=800)
            page.insert_text((50, 25), "Synthetic running header", fontsize=10)
            page.insert_text((50, 100), "1 Introduction", fontsize=14, fontname="hebo")
            page.insert_text((330, 140), "right top evidence", fontsize=11)
            page.insert_text((50, 140), "left top evidence", fontsize=11)
            page.insert_text((330, 170), "right bottom evidence", fontsize=11)
            page.insert_text((50, 170), "left bottom evidence", fontsize=11)
            page.insert_text((280, 780), f"Page {number}", fontsize=10)
        path.write_bytes(document.tobytes())
    result = parse_pdf(path, PAPER_ID, load_config().parsing)
    assert result.page_count == 3
    assert result.removed_margin_lines == 6
    page_one = [block.text for block in result.blocks if block.page == 1]
    assert page_one == [
        "1 Introduction",
        "left top evidence",
        "left bottom evidence",
        "right top evidence",
        "right bottom evidence",
    ]


def test_image_only_pdf_requires_ocr_and_corrupt_pdf_fails(tmp_path: Path) -> None:
    path = tmp_path / "blank.pdf"
    with pymupdf.open() as document:
        document.new_page()
        path.write_bytes(document.tobytes())
    with pytest.raises(ValueError, match="OCR"):
        parse_pdf(path, PAPER_ID, load_config().parsing)
    path.write_bytes(b"%PDF-1.7 broken fixture")
    with pytest.raises((ValueError, RuntimeError)):
        parse_pdf(path, PAPER_ID, load_config().parsing)


def test_heading_limit_is_configurable() -> None:
    config = replace(load_config().parsing, heading_max_words=1)
    document = normalize_pages(
        PAPER_ID,
        [
            PageText(
                1,
                600,
                800,
                [
                    line("1 Introduction", 100, size=14, bold=True),
                ],
            )
        ],
        config,
    )
    assert document.blocks[0].section is None


def test_numbered_list_with_inline_bold_is_not_a_new_section(tmp_path: Path) -> None:
    path = tmp_path / "inline-bold.pdf"
    with pymupdf.open() as document:
        page = document.new_page(width=600, height=800)
        page.insert_text((50, 100), "1 Introduction", fontsize=14, fontname="hebo")
        label = "1. Claim: "
        end = 50 + pymupdf.get_text_length(label, fontname="hebo", fontsize=11)
        page.insert_text((50, 140), label, fontsize=11, fontname="hebo")
        page.insert_text((end, 140), "This evidence belongs to the introduction.", fontsize=11)
        page.insert_text((50, 170), "Ordinary body text supports the same section.", fontsize=11)
        path.write_bytes(document.tobytes())
    parsed = parse_pdf(path, PAPER_ID, load_config().parsing)
    claim = next(block for block in parsed.blocks if block.text.startswith("1. Claim"))
    assert claim.section == "1 Introduction"
    assert claim.section_order == 1
