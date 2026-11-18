def retrieval_metrics(ranked_ids: list[str], gold_ids: list[str], ks: list[int]) -> dict:
    """MRR uses the supplied ranking depth; unanswerable questions have undefined recall/MRR."""
    if len(set(ranked_ids)) != len(ranked_ids) or len(set(gold_ids)) != len(gold_ids):
        raise ValueError("Metric inputs must contain unique chunk IDs")
    if not ks or any(type(k) is not int or k < 1 for k in ks):
        raise ValueError("Metric cutoffs must be positive integers")
    gold = set(gold_ids)
    metrics = {
        f"recall@{k}": len(set(ranked_ids[:k]) & gold) / len(gold) if gold else None for k in ks
    }
    metrics["mrr"] = (
        next((1 / rank for rank, key in enumerate(ranked_ids, 1) if key in gold), 0.0)
        if gold
        else None
    )
    return metrics


def cohens_kappa(expected: list[str], predicted: list[str]) -> float | None:
    if len(expected) != len(predicted):
        raise ValueError("Kappa requires paired labels")
    if not expected:
        return None
    size = len(expected)
    observed = sum(a == b for a, b in zip(expected, predicted, strict=True)) / size
    chance = (
        sum(
            expected.count(label) * predicted.count(label)
            for label in set(expected) | set(predicted)
        )
        / size**2
    )
    return (observed - chance) / (1 - chance) if chance < 1 else None


def citation_metrics(records: list[dict]) -> dict:
    claims = [(r, c) for r in records for c in r["generation"]["claims"]]
    pairs = [v for r in records for v in r["verification"] if v["verifier"] == "minicheck"]
    supported = {
        (v["claim_id"], v["chunk_id"])
        for r in records
        if r["qtype"] != "unanswerable"
        for v in r["verification"]
        if v["verifier"] == "minicheck" and v["label"] == "supported"
    }
    supported_claims = sum(
        not claim["unsupported"]
        and any((claim["claim_id"], key) in supported for key in claim["citations"])
        for _, claim in claims
    )
    rejected = sum(len(r["generation"]["rejected_citations"]) for r in records)
    total_citations = sum(len(c["citations"]) for _, c in claims) + rejected
    unresolved = sum(v["label"] is None for v in pairs)
    failed = sum(r["generation"]["status"] == "failed" for r in records)
    unanswerable = [r for r in records if r["qtype"] == "unanswerable"]
    complete = not unresolved and not failed
    return {
        "citation_precision": len(supported) / len(pairs) if pairs and complete else None,
        "citation_recall": supported_claims / len(claims) if claims and complete else None,
        "faithfulness": supported_claims / len(claims) if claims and complete else None,
        "hallucinated_citation_rate": rejected / total_citations if total_citations else None,
        "abstention_accuracy": sum(
            not r["generation"]["claims"] and r["generation"]["status"] != "failed"
            for r in unanswerable
        )
        / len(unanswerable)
        if unanswerable
        else None,
        "claim_count": len(claims),
        "citation_pair_count": len(pairs),
        "supported_pair_count": len(supported),
        "unverified_pair_count": unresolved,
        "failed_question_count": failed,
        "unanswerable_count": len(unanswerable),
        "unanswerable_claim_count": sum(len(r["generation"]["claims"]) for r in unanswerable),
    }
