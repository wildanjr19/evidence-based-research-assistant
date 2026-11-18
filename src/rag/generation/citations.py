import json

from rag.ids import is_valid_chunk_id


class ResponseFormatError(ValueError):
    """The response is not the agreed claims JSON format."""


def _unique_object(pairs: list[tuple[str, object]]) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ResponseFormatError("Duplicate JSON object key")
        result[key] = value
    return result


def _reject_constant(value: str) -> None:
    raise ResponseFormatError("Non-finite JSON constant")


def parse_claims(
    raw: str, corpus_ids: set[str], context_ids: set[str]
) -> tuple[list[dict], list[dict]]:
    try:
        data = json.loads(raw, object_pairs_hook=_unique_object, parse_constant=_reject_constant)
    except (ValueError, TypeError, RecursionError) as exc:
        raise ResponseFormatError("Response must be a JSON object with a claims list") from exc
    if (
        not isinstance(data, dict)
        or set(data) != {"claims"}
        or not isinstance(data["claims"], list)
    ):
        raise ResponseFormatError("Response must contain only a claims list")
    claims, rejected = [], []
    for ordinal, item in enumerate(data["claims"], 1):
        if (
            not isinstance(item, dict)
            or not {"text", "citations"} <= item.keys()
            or item.keys() - {"text", "citations", "unsupported"}
            or not isinstance(item["text"], str)
            or not item["text"].strip()
            or not isinstance(item["citations"], list)
            or any(not isinstance(key, str) for key in item["citations"])
            or ("unsupported" in item and type(item["unsupported"]) is not bool)
        ):
            raise ResponseFormatError(f"Invalid claim structure at ordinal {ordinal}")
        try:
            item["text"].encode("utf-8")
        except UnicodeError as exc:
            raise ResponseFormatError("Claim contains invalid Unicode") from exc
        valid = []
        for key in dict.fromkeys(item["citations"]):
            reason = None
            if not is_valid_chunk_id(key):
                reason = "invalid_id"
            elif key not in corpus_ids:
                reason = "not_in_corpus"
            elif key not in context_ids:
                reason = "not_in_context"
            if reason:
                rejected.append({"claim_order": ordinal, "chunk_id": key, "reason": reason})
            else:
                valid.append(key)
        claims.append(
            {
                "text": item["text"],
                "citations": valid,
                "unsupported": item.get("unsupported", False) or not valid,
            }
        )
    return claims, rejected
