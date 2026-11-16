"""Budgeted shared-label enumeration for paired AP with total-R denominator."""

import math


def _ap_numerator(run, positives):
    hits = 0
    terms = []
    for rank, doc in enumerate(run, 1):
        if doc in positives:
            hits += 1
            terms.append(hits / rank)
    return math.fsum(terms)


def _average_precision_bounds(left, right, labels, size, total, examples):
    """Only called after whole-audit exponential-work admission succeeds."""
    unknown = sorted((set(left) | set(right)) - set(labels))
    fixed = {doc for doc, value in labels.items() if value}
    outside = size - len(labels) - len(unknown)
    bounds = {"lower": None, "upper": None}
    witnesses = {}
    for mask in range(1 << len(unknown)):
        selected = {doc for index, doc in enumerate(unknown) if mask & (1 << index)}
        low = len(fixed) + len(selected)
        high = low + outside
        if total is not None:
            if not low <= total <= high:
                continue
            totals = (total,)
        else:
            # With the union labeling fixed, the signed numerator is fixed.
            # Outside labels only change the common denominator. Its two
            # endpoints suffice; no outside subsets are enumerated.
            totals = (low,) if low == high else (low, high)
        numerators = [_ap_numerator(run, fixed | selected) for run in (left, right)]
        for relevant in totals:
            scores = [value / relevant if relevant else 0.0 for value in numerators]
            value = scores[0] - scores[1]
            for direction in ("lower", "upper"):
                previous = bounds[direction]
                if previous is None or (
                    value < previous if direction == "lower" else value > previous
                ):
                    bounds[direction] = value
                    if examples:
                        witnesses[direction] = {
                            "total_relevant": relevant,
                            "unjudged_union_relevant": sorted(selected),
                            "unjudged_outside_union_relevant_count": relevant - low,
                            "left_score": scores[0],
                            "right_score": scores[1],
                        }
    return bounds, witnesses
