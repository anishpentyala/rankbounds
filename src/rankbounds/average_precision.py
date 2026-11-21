"""Budgeted shared-label enumeration for paired AP with total-R denominator."""

import math

from .core import _total_limits


def _ap_numerator(run_bits, positive_mask):
    hits = 0
    terms = []
    for rank, bit in enumerate(run_bits, 1):
        if bit & positive_mask:
            hits += 1
            terms.append(hits / rank)
    return math.fsum(terms)


def _feasible_masks(width, lower, upper):
    """Yield ascending masks whose popcount is in the inclusive count range."""
    if lower == 0 and upper == width:
        yield from range(1 << width)
        return

    def visit(bits, low, high, prefix):
        if low > bits or high < 0:
            return
        if low <= 0 and high >= bits:
            yield from range(prefix, prefix + (1 << bits))
            return
        # Highest remaining bit off before on preserves the old integer order.
        yield from visit(bits - 1, low, high, prefix)
        yield from visit(bits - 1, low - 1, high - 1, prefix | (1 << (bits - 1)))

    yield from visit(width, lower, upper, 0)


def _average_precision_bounds(left, right, labels, size, total, examples):
    """Only called after whole-audit exponential-work admission succeeds."""
    unknown = sorted((set(left) | set(right)) - set(labels))
    fixed = {doc for doc, value in labels.items() if value}
    outside = size - len(labels) - len(unknown)
    total_low, total_high = _total_limits(total, len(fixed), size - len(labels))
    bounds = {"lower": None, "upper": None}
    witnesses = {}
    # A union subset with c positives is feasible iff its total interval
    # [known+c, known+c+outside] intersects the declared total interval.
    count_low = max(0, total_low - len(fixed) - outside)
    count_high = min(len(unknown), total_high - len(fixed))
    # Unknown bits retain the lexical subset indices used by _feasible_masks.
    # A separate always-on bit represents every known-positive document.
    fixed_bit = 1 << len(unknown)
    bits = {doc: 1 << index for index, doc in enumerate(unknown)}
    run_bits = [
        [bits.get(doc, fixed_bit if labels.get(doc) == 1 else 0) for doc in run]
        for run in (left, right)
    ]
    popcount = getattr(int, "bit_count", None)
    for mask in _feasible_masks(len(unknown), count_low, count_high):
        count = popcount(mask) if popcount else bin(mask).count("1")
        low = len(fixed) + count
        high = low + outside
        union_relevant = low
        low, high = max(low, total_low), min(high, total_high)
        if low > high:
            continue
        # For this shared union assignment only the common denominator varies.
        totals = (low,) if low == high else (low, high)
        numerators = [_ap_numerator(run, mask | fixed_bit) for run in run_bits]
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
                            "unjudged_union_relevant": [
                                doc
                                for index, doc in enumerate(unknown)
                                if mask & (1 << index)
                            ],
                            "unjudged_outside_union_relevant_count": relevant
                            - union_relevant,
                            "left_score": scores[0],
                            "right_score": scores[1],
                        }
    return bounds, witnesses
