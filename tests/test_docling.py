from pathlib import Path

import pymupdf

from rag.evaluation.docling import check_table_cells, rasterize_page


def test_cell_check_keeps_row_column_and_value_together() -> None:
    grid = [["Model", "Accuracy", "F1"], ["A", "90", "85"], ["B", "92", "88"]]
    checks = [
        dict(row="B", column="F1", value="88"),
        dict(row="B", column="F1", value="92"),
        dict(row="A", column="F1", value="88"),
        dict(row="B", column="Missing", value="88"),
    ]
    assert [r["passed"] for r in check_table_cells([grid], checks)] == [True, False, False, False]


def test_raster_control_removes_native_text_and_preserves_page_size(tmp_path: Path) -> None:
    source, target = tmp_path / "source.pdf", tmp_path / "scan.pdf"
    with pymupdf.open() as document:
        document.new_page(width=300, height=400).insert_text((20, 40), "Known OCR control")
        document.save(source)
    rasterize_page(source, 1, target, 100)
    with pymupdf.open(target) as result:
        assert len(result) == 1
        assert result[0].get_text() == ""
        assert result[0].rect.width == 300 and result[0].rect.height == 400
        assert result[0].get_images()


def test_same_row_and_value_in_another_table_do_not_pass() -> None:
    grids = [
        [["Model", "F1"], ["A", "70"]],
        [["Model", "F1"], ["A", "90"]],
    ]
    check = dict(row="A", column="F1", value="90")
    assert not check_table_cells(grids, [check])[0]["passed"]
    assert check_table_cells(grids, [dict(check, table_index=1)])[0]["passed"]
