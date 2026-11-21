"""Budgeted shared-label enumeration for paired AP with total-R denominator."""

import math

from .core import _total_limits


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
    total_low, total_high = _total_limits(total, len(fixed), size - len(labels))
    bounds = {"lower": None, "upper": None}
    witnesses = {}
    for mask in range(1 << len(unknown)):
        selected = {doc for index, doc in enumerate(unknown) if mask & (1 << index)}
        low = len(fixed) + len(selected)
        high = low + outside
        union_relevant = low
        low, high = max(low, total_low), min(high, total_high)
        if low > high:
            continue
        # For this shared union assignment only the common denominator varies.
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
                            "unjudged_outside_union_relevant_count": relevant
                            - union_relevant,
                            "left_score": scores[0],
                            "right_score": scores[1],
                        }
    return bounds, witnesses
