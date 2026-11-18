import html
import re


def _escape(text: str) -> str:
    return re.sub(r"([\\`*_{}\[\]()#+.!|>~-])", r"\\\1", html.escape(text))


def render_answer(claims: list[dict], chunks: list[dict]) -> dict:
    by_id = {chunk["chunk_id"]: chunk for chunk in chunks}
    references = []
    numbers = {}
    lines = []
    for claim in claims:
        citations = []
        for identifier in claim["citations"]:
            if identifier not in by_id:
                raise ValueError("Cannot render a citation outside the provided context")
            if identifier not in numbers:
                chunk = by_id[identifier]
                numbers[identifier] = len(references) + 1
                references.append(
                    {
                        "number": numbers[identifier],
                        "chunk_id": identifier,
                        "paper_id": chunk["paper_id"],
                        "title": chunk["title"],
                        "page_start": chunk["page_start"],
                        "page_end": chunk["page_end"],
                        "section": chunk["section"],
                        "quote": chunk["text"],
                    }
                )
            citations.append(f"[{numbers[identifier]}]")
        label = "**tidak ada bukti**: " if claim["unsupported"] else ""
        text = _escape(claim["text"]).replace("\n", " ")
        lines.append(f"- {label}{text}" + (" " + " ".join(citations) if citations else ""))
    if not lines:
        lines.append("Tidak ada bukti pada korpus.")
    if references:
        lines += ["", "Dukungan klaim belum diverifikasi.", "", "Referensi:"]
    for reference in references:
        page = str(reference["page_start"])
        if reference["page_end"] != reference["page_start"]:
            page += f"-{reference['page_end']}"
        section = ", " + _escape(reference["section"]) if reference["section"] else ""
        lines += [
            "",
            f"[{reference['number']}] {_escape(reference['title'])}, p.{page}{section}",
            f"`{reference['chunk_id']}`",
            "",
        ]
        lines += ["> " + _escape(line) for line in reference["quote"].splitlines()]
    return {"markdown": "\n".join(lines), "references": references}
