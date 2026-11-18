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
