"""Conservative Docling JSON adapter; held content never enters searchable chunks."""

import math
import re
import unicodedata
from collections import Counter
from dataclasses import dataclass

from rag.parsing.pdf import ParsedPaper, TextBlock


@dataclass(frozen=True)
class QualityPolicy:
    native_word_coverage: float = 0.8
    header_center_tolerance: float = 0.25

    def __post_init__(self) -> None:
        if not 0 < self.native_word_coverage <= 1:
            raise ValueError("native_word_coverage must be in (0, 1]")
        if not 0 < self.header_center_tolerance <= 0.5:
            raise ValueError("header_center_tolerance must be in (0, 0.5]")


@dataclass(frozen=True)
class TableBlock:
    page: int
    caption: str
    header: list[str]
    rows: list[list[str]]
    notes: str
    ref: str
    row_contexts: tuple[str, ...] = ()


@dataclass(frozen=True)
class AdaptedPaper:
    paper_id: str
    page_count: int
    blocks: list[TextBlock | TableBlock]
    decisions: list[dict]


def words(text: str) -> list[str]:
    return re.findall(r"\w+", unicodedata.normalize("NFKC", text).casefold())


def word_coverage(text: str, native: str) -> float:
    actual, source = Counter(words(text)), Counter(words(native))
    if not actual:
        return float(" ".join(text.split()) == " ".join(native.split()))
    return sum((actual & source).values()) / max(1, sum(actual.values()))


def _cell_tokens(text: str) -> list[str]:
    return re.findall(r"\w+|[^\w\s]", unicodedata.normalize("NFKC", text))


def text_reasons(text: str, native: str, policy: QualityPolicy) -> list[str]:
    reasons = []
    if not text.strip():
        reasons.append("empty_text")
    if "\ufffd" in text or any(unicodedata.category(c) == "Cc" and c not in "\n\r\t" for c in text):
        reasons.append("corrupt_characters")
    if native.strip():
        if word_coverage(text, native) < policy.native_word_coverage:
            reasons.append("native_text_mismatch")
        if Counter(re.findall(r"\d+", text)) - Counter(re.findall(r"\d+", native)):
            reasons.append("native_number_mismatch")
    else:
        # shortcut: OCR has no independent text comparator; retain it for audit until validated.
        reasons.append("no_native_comparator")
    return reasons


def _checked_table(
    data: dict, ref: str, native: dict[str, str], policy: QualityPolicy
) -> tuple[list[str], list[list[str]], tuple[str, ...]]:
    height, width = data["num_rows"], data["num_cols"]
    cells = data["table_cells"]
    if type(height) is not int or type(width) is not int or min(height, width) < 2:
        raise ValueError("missing_grid_or_simple_header")
    header_end = max((c["end_row_offset_idx"] for c in cells if c.get("column_header")), default=0)
    if not 0 < header_end < height:
        raise ValueError("missing_grid_or_simple_header")
    if height * width > sum(c["row_span"] * c["col_span"] for c in cells) + header_end * width:
        raise ValueError("missing_grid_or_simple_header")
    grid = [[None] * width for _ in range(height)]
    boxes, origins, sections = {}, set(), {}
    for i, cell in enumerate(cells):
        row, end_row = cell["start_row_offset_idx"], cell["end_row_offset_idx"]
        col, end_col = cell["start_col_offset_idx"], cell["end_col_offset_idx"]
        if (
            any(type(v) is not int for v in (row, end_row, col, end_col))
            or not (0 <= row < end_row <= height and 0 <= col < end_col <= width)
            or end_row - row != cell["row_span"]
            or end_col - col != cell["col_span"]
        ):
            raise ValueError("overlapping_or_outside_cells")
        if row < header_end < end_row:
            raise ValueError("span_crosses_header_and_body")
        if row >= header_end:
            if cell.get("row_section"):
                if row + 1 != end_row or col != 0 or end_col != width:
                    raise ValueError("unsupported_body_span")
                sections[row] = cell["text"]
            elif end_col - col > 1 or (
                end_row - row > 1 and (col != 0 or not cell.get("row_header"))
            ):
                raise ValueError("unsupported_body_span")
        box = cell.get("bbox") or {}
        if (
            box.get("coord_origin") not in {"TOPLEFT", "BOTTOMLEFT"}
            or any(
                type(box.get(k)) not in (int, float) or not math.isfinite(box[k])
                for k in ("l", "t", "r", "b")
            )
            or box["l"] >= box["r"]
            or box["t"] == box["b"]
        ):
            raise ValueError("missing_or_invalid_cell_geometry")
        origins.add(box["coord_origin"])
        top, bottom = sorted((box["t"], box["b"]))
        if box["coord_origin"] == "BOTTOMLEFT":
            top, bottom = -bottom, -top
        boxes[i] = (box["l"], top, box["r"], bottom)
        value = cell["text"].strip()
        source = native.get(f"{ref}/cell/{i}", "")
        if (
            value
            and text_reasons(value, source, policy)
            or _cell_tokens(value) != _cell_tokens(source)
        ):
            raise ValueError("cell_native_mismatch")
        for r in range(row, end_row):
            for c in range(col, end_col):
                if grid[r][c] is not None:
                    raise ValueError("overlapping_or_outside_cells")
                grid[r][c] = i
    if len(origins) != 1:
        raise ValueError("mixed_cell_coordinates")
    if any(i is None for row in grid[header_end:] for i in row):
        raise ValueError("missing_grid_or_simple_header")
    anchors, bands = [], []
    for row in range(height):
        own = [
            boxes[i]
            for i, c in enumerate(cells)
            if c["start_row_offset_idx"] == row and c["end_row_offset_idx"] == row + 1
        ]
        if not own:
            raise ValueError("cell_row_or_column_alignment")
        top, bottom = max(b[1] for b in own), min(b[3] for b in own)
        if top >= bottom:
            raise ValueError("cell_row_or_column_alignment")
        anchors.append((top + bottom) / 2)
        bands.append((min(b[1] for b in own), max(b[3] for b in own)))
        if row and anchors[-1] <= anchors[-2]:
            raise ValueError("cell_row_order")
        ordered = [boxes[i] for i in dict.fromkeys(grid[row]) if i is not None]
        if any(a[2] > b[0] for a, b in zip(ordered, ordered[1:], strict=False)):
            raise ValueError("cell_row_or_column_alignment")
    for i, cell in enumerate(cells):
        start, end = cell["start_row_offset_idx"], cell["end_row_offset_idx"]
        box = boxes[i]
        if any(
            box[1] <= anchor <= box[3]
            for row, anchor in enumerate(anchors)
            if not start <= row < end
        ):
            raise ValueError("cell_crosses_unassigned_row")
        if not bands[start][0] <= (box[1] + box[3]) / 2 <= bands[end - 1][1]:
            raise ValueError("cell_row_or_column_alignment")
        if start < header_end and cell["col_span"] > 1:
            children = [
                grid[header_end - 1][col]
                for col in range(cell["start_col_offset_idx"], cell["end_col_offset_idx"])
            ]
            if any(j is None or cells[j]["col_span"] != 1 for j in children):
                raise ValueError("ambiguous_header_geometry")
            child_boxes = [boxes[j] for j in children]
            centres = [(b[0] + b[2]) / 2 for b in child_boxes]
            pitch = min(b - a for a, b in zip(centres, centres[1:], strict=False))
            expected = (child_boxes[0][0] + child_boxes[-1][2]) / 2
            if abs((box[0] + box[2]) / 2 - expected) > pitch * policy.header_center_tolerance:
                raise ValueError("header_span_alignment")
    # Native text can agree with a bad crop that already includes the adjacent row.
    if any(a[1] > b[0] for a, b in zip(bands, bands[1:], strict=False)):
        raise ValueError("adjacent_row_bands_overlap")
    header = []
    for col in range(width):
        lineage = [
            i for i in dict.fromkeys(grid[row][col] for row in range(header_end)) if i is not None
        ]
        names = [cells[i]["text"].strip() for i in lineage]
        if not names or any(not name for name in names):
            raise ValueError("missing_header_or_row_label")
        header.append(" / ".join(names))
    rows, contexts, context = [], [], ""
    for row in range(header_end, height):
        if row in sections:
            context = sections[row]
            continue
        values = [cells[i]["text"].strip() for i in grid[row]]
        if not values[0]:
            raise ValueError("missing_header_or_row_label")
        rows.append(values)
        contexts.append(context)
    if not rows:
        raise ValueError("no_table_data_rows")
    return header, rows, tuple(contexts)


def adapt_document(
    raw: dict,
    paper_id: str,
    page_count: int,
    native_regions: dict[str, str],
    policy: QualityPolicy,
) -> AdaptedPaper:
    """Accept explicit PDF pages, native-checked text, and validated table spans."""
    nodes = {
        item["self_ref"]: item
        for name in ("texts", "tables", "groups", "pictures", "key_value_items", "form_items")
        for item in raw.get(name, [])
    }
    blocks, decisions = [], []
    seen = set()
    section, section_order = None, 0
    previous_page = 0

    def overlaps_table(item: dict) -> bool:
        for provenance in item.get("prov", []):
            for table in raw.get("tables", []):
                for other in table.get("prov", []):
                    if provenance.get("page_no") != other.get("page_no"):
                        continue
                    a, b = provenance.get("bbox", {}), other.get("bbox", {})
                    if not a or not b or a.get("coord_origin") != b.get("coord_origin"):
                        return True
                    if max(a["l"], b["l"]) < min(a["r"], b["r"]) and max(
                        min(a["t"], a["b"]), min(b["t"], b["b"])
                    ) < min(max(a["t"], a["b"]), max(b["t"], b["b"])):
                        return True
        return False

    def page_of(item: dict) -> int:
        provenance = item.get("prov", [])
        pages = {p.get("page_no") for p in provenance}
        if len(pages) != 1:
            raise ValueError("ambiguous_or_missing_pdf_page")
        page = pages.pop()
        if type(page) is not int or not 1 <= page <= page_count:
            raise ValueError("page_outside_original_pdf")
        return page

    def linked_text(item: dict, key: str, page: int) -> str:
        result = []
        for link in item.get(key, []):
            node = nodes[link["$ref"]]
            if page_of(node) != page:
                raise ValueError("table_context_on_other_page")
            value = node["text"]
            if text_reasons(value, native_regions.get(node["self_ref"], ""), policy):
                raise ValueError("table_context_mismatch")
            result.append(value)
        return "\n".join(result)

    def visit(ref: str) -> None:
        nonlocal section, section_order, previous_page
        if ref in seen:
            raise ValueError("duplicate_or_cyclic_body_reference")
        seen.add(ref)
        if ref not in nodes:
            raise ValueError(f"unresolved_body_reference: {ref}")
        item = nodes[ref]
        if ref.startswith("#/groups/"):
            for child in item.get("children", []):
                visit(child["$ref"])
            return
        label = item.get("label", "unknown")
        decision = dict(ref=ref, label=label, status="held", reasons=[])
        decisions.append(decision)
        try:
            page = page_of(item)
            decision["page"] = page
            if page < previous_page:
                raise ValueError("body_page_order")
            previous_page = page
            if label in {"caption", "footnote", "page_header", "page_footer"}:
                decision.update(status="excluded", reasons=["context_or_furniture"])
                return
            if label == "table":
                header, rows, contexts = _checked_table(item["data"], ref, native_regions, policy)
                caption = linked_text(item, "captions", page)
                if not caption:
                    raise ValueError("missing_caption")
                notes = linked_text(item, "footnotes", page)
                blocks.append(TableBlock(page, caption, header, rows, notes, ref, contexts))
            elif label in {"text", "paragraph", "list_item", "section_header", "title"}:
                if overlaps_table(item):
                    raise ValueError("text_overlaps_table")
                text = item["text"]
                decision["native_word_coverage"] = word_coverage(text, native_regions.get(ref, ""))
                reasons = text_reasons(text, native_regions.get(ref, ""), policy)
                if reasons:
                    decision["reasons"] = reasons
                    return
                if label in {"section_header", "title"}:
                    section, section_order = text, section_order + 1
                blocks.append(TextBlock(page, text, section, section_order or None))
            else:
                raise ValueError("unsupported_block_type")
            decision["status"] = "passed"
        except (ValueError, KeyError, TypeError, IndexError) as exc:
            decision["reasons"] = [str(exc)]

    for child in raw["body"]["children"]:
        visit(child["$ref"])
    # Validate the unchanged ID/page contract even when every block is held.
    ParsedPaper(paper_id, page_count, [TextBlock(1, "validation", None, None)], 0)
    return AdaptedPaper(paper_id, page_count, blocks, decisions)
