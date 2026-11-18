from collections import defaultdict


def reciprocal_rank_fusion(rankings: list[list[str]], k: int) -> list[tuple[str, float]]:
    """Use 1-based ranks, count each ID once per list, and break score ties by ID."""
    if type(k) is not int or k < 0:
        raise ValueError("RRF k must be a non-negative integer")
    scores: dict[str, float] = defaultdict(float)
    for ranking in rankings:
        unique = dict.fromkeys(ranking)
        for rank, identifier in enumerate(unique, 1):
            scores[identifier] += 1 / (k + rank)
    return sorted(scores.items(), key=lambda hit: (-hit[1], hit[0]))
