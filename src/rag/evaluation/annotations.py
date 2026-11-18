import hashlib
import json
from pathlib import Path

from rag.indexing.embedding import text_hash
from rag.verification.judge import LABELS


def load_manual_labels(path: Path, chunks: dict[str, dict]) -> tuple[dict, str | None]:
    if not path.exists():
        return {}, None
    content = path.read_bytes()
    labels = {}
    for number, line in enumerate(content.decode("utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            item = json.loads(line)
            key = (text_hash(item["claim"]), item["chunk_id"], item["text_sha256"])
            if (
                item["label"] not in LABELS
                or not isinstance(item.get("annotator"), str)
                or not item["annotator"].strip()
                or not item["claim"].strip()
                or item["chunk_id"] not in chunks
                or text_hash(chunks[item["chunk_id"]]["text"]) != item["text_sha256"]
                or key in labels
            ):
                raise ValueError("Invalid, duplicate, or stale manual label")
            labels[key] = item["label"]
        except (KeyError, TypeError, ValueError, AttributeError) as exc:
            raise ValueError(f"Invalid manual annotation at {path}:{number}") from exc
    return labels, hashlib.sha256(content).hexdigest()


def export_annotations(records: list[dict], chunks: dict[str, dict], path: Path) -> int:
    """Export evidence only under ignored data/, never alongside committed evaluation reports."""
    data_root = Path("data").resolve()
    if not path.resolve().is_relative_to(data_root):
        raise ValueError("Annotation evidence must be stored under data/")
    path.parent.mkdir(parents=True, exist_ok=True)
    seen = set()
    with path.open("x", encoding="utf-8") as stream:
        for record in records:
            for claim in record["generation"]["claims"]:
                for chunk_id in claim["citations"]:
                    evidence = chunks[chunk_id]["text"]
                    key = (text_hash(claim["text"]), chunk_id, text_hash(evidence))
                    if key in seen:
                        continue
                    seen.add(key)
                    item = {
                        "claim": claim["text"],
                        "claim_id": claim["claim_id"],
                        "chunk_id": chunk_id,
                        "text_sha256": key[2],
                        "evidence": evidence,
                        "label": None,
                        "annotator": None,
                    }
                    stream.write(json.dumps(item, ensure_ascii=False) + "\n")
    return len(seen)
