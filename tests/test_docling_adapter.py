from copy import deepcopy
from pathlib import Path

import pymupdf
import pytest

from rag.chunking.docling import chunk_adapted
from rag.config import ChunkingConfig
from rag.parsing.docling_adapter import QualityPolicy, adapt_document
from rag.parsing.docling_backend import native_regions


def structured_fixture(specs: list[tuple], height: int, width: int) -> tuple[dict, dict]:
    raw, native = fixture()
    cells = []
    for row, col, rows, cols, text, header, row_header, section in specs:
        cells.append(
            dict(
                start_row_offset_idx=row,
                end_row_offset_idx=row + rows,
                start_col_offset_idx=col,
                end_col_offset_idx=col + cols,
                row_span=rows,
                col_span=cols,
                text=text,
                column_header=header,
                row_header=row_header,
                row_section=section,
                bbox=dict(
                    l=10 + 100 * col,
                    r=100 * (col + cols) - 10,
                    t=10 + 20 * row,
                    b=20 * (row + rows),
                    coord_origin="TOPLEFT",
                ),
            )
        )
        native[f"#/tables/0/cell/{len(cells) - 1}"] = text
    raw["tables"][0]["data"] = dict(num_rows=height, num_cols=width, table_cells=cells)
    return raw, native


def hierarchical_fixture() -> tuple[dict, dict]:
    return structured_fixture(
        [
            (0, 0, 2, 1, "Model", True, False, False),
            (0, 1, 1, 2, "Metrics", True, False, False),
            (1, 1, 1, 1, "F1", True, False, False),
            (1, 2, 1, 1, "Recall", True, False, False),
            (2, 0, 1, 1, "Alpha", False, False, False),
            (2, 1, 1, 1, "90", False, False, False),
            (2, 2, 1, 1, "80", False, False, False),
        ],
        3,
        3,
    )


def fixture() -> tuple[dict, dict]:
    provenance = [dict(page_no=3, bbox=dict(l=10, t=10, r=200, b=100, coord_origin="TOPLEFT"))]
    texts = [
        dict(self_ref="#/texts/0", label="caption", text="Table 1. Scores (%)", prov=provenance),
        dict(
            self_ref="#/texts/1",
            label="text",
            text="Narrative evidence is independent.",
            prov=provenance,
        ),
        dict(self_ref="#/texts/2", label="footnote", text="Unit: percent", prov=provenance),
    ]
    texts[1]["prov"] = [
        dict(page_no=3, bbox=dict(l=10, t=200, r=200, b=250, coord_origin="TOPLEFT"))
    ]
    cells = []
    grid = [["Model", "F1"], ["Alpha", "90"], ["Beta", "80"], ["Gamma", "70"]]
    native = {t["self_ref"]: t["text"] for t in texts}
    for row, values in enumerate(grid):
        for col, text in enumerate(values):
            cells.append(
                dict(
                    text=text,
                    row_span=1,
                    col_span=1,
                    start_row_offset_idx=row,
                    end_row_offset_idx=row + 1,
                    start_col_offset_idx=col,
                    end_col_offset_idx=col + 1,
                    column_header=row == 0,
                    bbox=dict(
                        l=10 + col * 100,
                        r=90 + col * 100,
                        t=10 + row * 20,
                        b=20 + row * 20,
                        coord_origin="TOPLEFT",
                    ),
                )
            )
            native[f"#/tables/0/cell/{len(cells) - 1}"] = text
    table = dict(
        self_ref="#/tables/0",
        label="table",
        prov=provenance,
        captions=[{"$ref": "#/texts/0"}],
        footnotes=[{"$ref": "#/texts/2"}],
        data=dict(num_rows=4, num_cols=2, table_cells=cells),
    )
    raw = dict(
        texts=texts,
        tables=[table],
        body=dict(children=[{"$ref": "#/tables/0"}, {"$ref": "#/texts/1"}]),
    )
    return raw, native


def test_table_chunks_repeat_context_keep_rows_pages_and_ids() -> None:
    raw, native = fixture()
    adapted = adapt_document(raw, "pmc:fixture", 4, native, QualityPolicy())
    config = ChunkingConfig(18, 0, 1)
    chunks, events = chunk_adapted(adapted, config, len, 100)
    tables = [c for c in chunks if "Table 1" in c.text]
    assert len(tables) >= 2
    for chunk in tables:
        assert "Model | F1" in chunk.text and "Unit: percent" in chunk.text
        assert chunk.page_start == chunk.page_end == 3
        assert chunk.chunk_id.startswith("pmc:fixture:p3:c")
    for label in ("Alpha | 90", "Beta | 80", "Gamma | 70"):
        assert sum(label in c.text for c in tables) == 1
    assert [c.chunk_order for c in chunks] == list(range(1, len(chunks) + 1))
    assert chunk_adapted(adapted, config, len, 100) == (chunks, events)


@pytest.mark.parametrize(
    "mutation,reason",
    [
        ("merged", "overlapping_or_outside_cells"),
        ("number", "cell_native_mismatch"),
        ("header", "missing_grid_or_simple_header"),
        ("caption", "missing_caption"),
        ("scan", "cell_native_mismatch"),
        ("missing_cell", "missing_grid_or_simple_header"),
        ("outside", "page_outside_original_pdf"),
        ("multipage", "ambiguous_or_missing_pdf_page"),
    ],
)
def test_suspect_table_never_reaches_chunks(mutation: str, reason: str) -> None:
    raw, native = fixture()
    table = raw["tables"][0]
    if mutation == "merged":
        table["data"]["table_cells"][2]["row_span"] = 2
    elif mutation == "number":
        table["data"]["table_cells"][3]["text"] = "99"
    elif mutation == "header":
        table["data"]["table_cells"][0]["column_header"] = False
        table["data"]["table_cells"][1]["column_header"] = False
    elif mutation == "caption":
        table["captions"] = []
    elif mutation == "scan":
        native.clear()
        native["#/texts/1"] = raw["texts"][1]["text"]
    elif mutation == "missing_cell":
        table["data"]["table_cells"].pop()
    elif mutation == "outside":
        table["prov"] = [dict(page_no=8)]
    else:
        original = table["prov"][0]
        table["prov"] = [dict(original, page_no=2), dict(original, page_no=3)]
    adapted = adapt_document(raw, "pmc:fixture", 4, native, QualityPolicy())
    assert adapted.decisions[0]["status"] == "held"
    assert reason in adapted.decisions[0]["reasons"]
    chunks, _ = chunk_adapted(adapted, ChunkingConfig(30, 0, 1), len, 100)
    assert chunks and all("Alpha" not in c.text and "90" not in c.text for c in chunks)


def test_oversize_row_holds_entire_table_without_truncation() -> None:
    raw, native = fixture()
    adapted = adapt_document(raw, "pmc:fixture", 4, native, QualityPolicy())
    chunks, events = chunk_adapted(adapted, ChunkingConfig(200, 0, 1), len, 45)
    assert all("Table 1" not in c.text for c in chunks)
    assert any(e["kind"] == "held_table" for e in events)


def test_flattened_table_cannot_bypass_hold_as_narrative() -> None:
    raw, native = fixture()
    raw["tables"][0]["data"]["table_cells"][0]["row_span"] = 2
    raw["texts"][1]["prov"] = raw["tables"][0]["prov"]
    adapted = adapt_document(raw, "pmc:fixture", 4, native, QualityPolicy())
    assert not adapted.blocks
    assert adapted.decisions[1]["reasons"] == ["text_overlaps_table"]


def test_numeric_cell_on_another_row_is_held_even_when_native_text_matches() -> None:
    raw, native = fixture()
    cell = raw["tables"][0]["data"]["table_cells"][3]
    cell["bbox"].update(t=70, b=80)
    adapted = adapt_document(raw, "pmc:fixture", 4, native, QualityPolicy())
    assert adapted.decisions[0]["reasons"] == ["cell_row_or_column_alignment"]


def test_bad_body_reference_is_not_silently_lost() -> None:
    raw, native = fixture()
    raw["body"]["children"].append({"$ref": "#/texts/999"})
    with pytest.raises(ValueError, match="unresolved"):
        adapt_document(raw, "pmc:fixture", 4, native, QualityPolicy())


def test_corrupt_narrative_held_and_source_unchanged() -> None:
    raw, native = fixture()
    raw["texts"][1]["text"] += "\ufffd"
    before = deepcopy(raw)
    adapted = adapt_document(raw, "pmc:fixture", 4, native, QualityPolicy())
    assert raw == before
    assert "corrupt_characters" in adapted.decisions[1]["reasons"]


def test_native_pdf_coordinate_origins_and_absent_page(tmp_path: Path) -> None:
    path = tmp_path / "native.pdf"
    with pymupdf.open() as doc:
        doc.new_page(width=300, height=400).insert_text((30, 60), "Alpha 90")
        doc.save(path)
    raw = dict(
        texts=[
            dict(
                self_ref="#/texts/0",
                prov=[dict(page_no=1, bbox=dict(l=20, t=40, r=150, b=70, coord_origin="TOPLEFT"))],
            ),
            dict(
                self_ref="#/texts/1",
                prov=[
                    dict(page_no=1, bbox=dict(l=20, t=360, r=150, b=330, coord_origin="BOTTOMLEFT"))
                ],
            ),
            dict(self_ref="#/texts/2", prov=[dict(page_no=2, bbox={})]),
        ]
    )
    regions, pages = native_regions(raw, path)
    assert regions["#/texts/0"] == regions["#/texts/1"] == "Alpha 90"
    assert regions["#/texts/2"] == ""
    assert pages[0]["native_characters"] > 0


def test_hierarchical_header_keeps_qualified_columns() -> None:
    raw, native = hierarchical_fixture()
    adapted = adapt_document(raw, "pmc:fixture", 4, native, QualityPolicy())
    assert adapted.decisions[0]["status"] == "passed"
    table = adapted.blocks[0]
    assert table.header == ["Model", "Metrics / F1", "Metrics / Recall"]
    chunks, _ = chunk_adapted(adapted, ChunkingConfig(60, 0, 1), len, 200)
    assert "Metrics / F1 | Metrics / Recall" in chunks[0].text
    assert "Alpha | 90 | 80" in chunks[0].text


def test_misaligned_header_span_is_held() -> None:
    raw, native = hierarchical_fixture()
    raw["tables"][0]["data"]["table_cells"][1]["bbox"].update(l=160, r=340)
    adapted = adapt_document(raw, "pmc:fixture", 4, native, QualityPolicy())
    assert adapted.decisions[0]["reasons"] == ["header_span_alignment"]


def test_explicit_row_label_span_repeats_only_its_declared_group() -> None:
    raw, native = structured_fixture(
        [
            (0, 0, 1, 1, "Task", True, False, False),
            (0, 1, 1, 1, "Model", True, False, False),
            (0, 2, 1, 1, "F1", True, False, False),
            (1, 0, 2, 1, "Lapt14", False, True, False),
            (1, 1, 1, 1, "Alpha", False, False, False),
            (1, 2, 1, 1, "90", False, False, False),
            (2, 1, 1, 1, "Beta", False, False, False),
            (2, 2, 1, 1, "80", False, False, False),
        ],
        3,
        3,
    )
    adapted = adapt_document(raw, "pmc:fixture", 4, native, QualityPolicy())
    assert adapted.decisions[0]["status"] == "passed"
    assert adapted.blocks[0].rows == [["Lapt14", "Alpha", "90"], ["Lapt14", "Beta", "80"]]


def test_section_heading_repeated_with_each_row_after_chunk_split() -> None:
    raw, native = structured_fixture(
        [
            (0, 0, 1, 1, "Model", True, False, False),
            (0, 1, 1, 1, "F1", True, False, False),
            (1, 0, 1, 2, "Adapted models", False, False, True),
            (2, 0, 1, 1, "Alpha", False, False, False),
            (2, 1, 1, 1, "90", False, False, False),
            (3, 0, 1, 1, "Beta", False, False, False),
            (3, 1, 1, 1, "80", False, False, False),
        ],
        4,
        2,
    )
    adapted = adapt_document(raw, "pmc:fixture", 4, native, QualityPolicy())
    assert adapted.decisions[0]["status"] == "passed"
    chunks, _ = chunk_adapted(adapted, ChunkingConfig(22, 0, 1), len, 200)
    tables = [c for c in chunks if "Table 1" in c.text]
    assert len(tables) == 2
    assert all("[Adapted models]" in c.text for c in tables)


@pytest.mark.parametrize(
    "value,native_value,passed",
    [
        ("-", "-", True),
        ("-", "", False),
        ("-90", "90", False),
        ("90 -80", "-90 80", False),
        ("1.25", "12.5", False),
        ("0.90", "0.90", True),
        ("|Train|", "|Train|", True),
        ("Alpha\nBeta", "Alpha Beta", True),
        ("won't", "won\ufffdt", False),
    ],
)
def test_cell_punctuation_and_signs_are_preserved(value, native_value, passed) -> None:
    raw, native = fixture()
    raw["tables"][0]["data"]["table_cells"][3]["text"] = value
    native["#/tables/0/cell/3"] = native_value
    adapted = adapt_document(raw, "pmc:fixture", 4, native, QualityPolicy())
    assert (adapted.decisions[0]["status"] == "passed") is passed
    if passed:
        chunks, _ = chunk_adapted(adapted, ChunkingConfig(100, 0, 1), len, 300)
        if "|" in value or "\n" in value:
            import json

            assert json.dumps(value, ensure_ascii=False) in chunks[0].text
        else:
            assert value in chunks[0].text


def test_merged_text_without_declared_span_cannot_cross_another_row() -> None:
    raw, native = fixture()
    cell = raw["tables"][0]["data"]["table_cells"][2]
    cell.update(text="Alpha Beta")
    cell["bbox"].update(t=30, b=60)
    native["#/tables/0/cell/2"] = "Alpha Beta"
    adapted = adapt_document(raw, "pmc:fixture", 4, native, QualityPolicy())
    assert adapted.decisions[0]["reasons"] == ["cell_crosses_unassigned_row"]


def test_adjacent_rows_cannot_overlap_between_columns_despite_matching_native() -> None:
    raw, native = structured_fixture(
        [(r, c, 1, 1, f"Cell {r} {c}", r == 0, False, False) for r in range(3) for c in range(3)],
        3,
        3,
    )
    cells = raw["tables"][0]["data"]["table_cells"]
    cells[4]["bbox"].update(t=25, b=49)
    cells[8]["bbox"].update(t=48, b=65)
    before = deepcopy(raw)
    adapted = adapt_document(raw, "pmc:fixture", 4, native, QualityPolicy())
    assert adapted.decisions[0]["reasons"] == ["adjacent_row_bands_overlap"]
    assert all(not hasattr(block, "rows") for block in adapted.blocks)
    assert raw == before


def test_model_overlong_narrative_splits_without_changing_table_budget() -> None:
    raw, native = fixture()
    adapted = adapt_document(raw, "pmc:fixture", 4, native, QualityPolicy())
    config = ChunkingConfig(100, 0, 1)
    baseline, _ = chunk_adapted(adapted, config, len, 100)

    def count(text):
        return len(text) if text.startswith("Table 1") else 3 * len(text)

    chunks, events = chunk_adapted(adapted, config, count, 100)
    assert all(count(chunk.text) <= 100 for chunk in chunks)
    assert all(e["kind"] != "held_narrative" for e in events)
    assert any("Narrative evidence" in chunk.text for chunk in chunks)
    assert [c.text for c in chunks if c.text.startswith("Table 1")] == [
        c.text for c in baseline if c.text.startswith("Table 1")
    ]
    assert len(chunks) > len(baseline)


def test_unsplittable_narrative_token_stays_held_without_losing_following_text() -> None:
    from rag.parsing.docling_adapter import AdaptedPaper
    from rag.parsing.pdf import TextBlock

    document = AdaptedPaper("pmc:fixture", 1, [TextBlock(1, "x" * 30 + " safe", None, None)], [])
    chunks, events = chunk_adapted(document, ChunkingConfig(20, 5, 1), len, 10)
    assert [chunk.text for chunk in chunks] == ["safe"]
    assert any(e["kind"] == "held_narrative" and e["text"] == "x" * 30 for e in events)
