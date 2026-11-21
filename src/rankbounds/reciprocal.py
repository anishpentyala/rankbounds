"""Paired reciprocal-rank extrema by feasible first-relevant positions."""

from .core import _total_limits

_NATIVE_POPCOUNT = getattr(int, "bit_count", None)


def _count_bits(mask):
    """Native popcount where available, with the same result on Python 3.9."""
    return _NATIVE_POPCOUNT(mask) if _NATIVE_POPCOUNT else bin(mask).count("1")


def _prefix_masks(run, bits):
    prefixes = [0]
    for doc in run:
        prefixes.append(prefixes[-1] | bits[doc])
    return prefixes, [bits[doc] for doc in run] + [0]


def _reciprocal_bounds(left, right, labels, size, total, examples):
    """Runs are already truncated to k; every feasible first-hit pair is tried."""
    # Dense indices cover only the top-k union, not the full document universe.
    union = sorted(set(left) | set(right))
    bits = {doc: 1 << index for index, doc in enumerate(union)}
    positive = negative = unknown = 0
    for doc in union:
        if doc not in labels:
            unknown |= bits[doc]
        elif labels[doc]:
            positive |= bits[doc]
        else:
            negative |= bits[doc]
    known_count = sum(labels.values())
    unknown_count = _count_bits(unknown)
    outside = size - len(labels) - unknown_count
    total_low, total_high = _total_limits(total, known_count, size - len(labels))
    left_prefix, left_one = _prefix_masks(left, bits)
    right_prefix, right_one = _prefix_masks(right, bits)
    bounds = {"lower": None, "upper": None}
    choices = {}
    for i in range(len(left) + 1):
        for j in range(len(right) + 1):
            # Index len(run) denotes no relevant retrieved document.
            zero = left_prefix[i] | right_prefix[j]
            one = left_one[i] | right_one[j]
            if zero & (one | positive) or one & negative:
                continue
            selected = one & unknown
            low = known_count + _count_bits(selected)
            eligible = unknown & ~(zero | selected)
            high = low + _count_bits(eligible) + outside
            low_feasible, high_feasible = max(low, total_low), min(high, total_high)
            if low_feasible > high_feasible:
                continue
            scores = [
                1 / (index + 1) if index < len(run) else 0.0
                for index, run in ((i, left), (j, right))
            ]
            value = scores[0] - scores[1]
            for direction in ("lower", "upper"):
                previous = bounds[direction]
                if previous is None or (
                    value < previous if direction == "lower" else value > previous
                ):
                    bounds[direction] = value
                    if examples:
                        # Preserve scan/tie order; expand only final witnesses.
                        choices[direction] = (
                            selected,
                            eligible,
                            low,
                            low_feasible,
                            scores,
                        )
    witnesses = {}
    for direction, (selected, eligible, low, relevant, scores) in choices.items():
        extra = min(relevant - low, _count_bits(eligible))
        selected_docs = []
        for doc in union:
            if selected & bits[doc]:
                selected_docs.append(doc)
            elif extra and eligible & bits[doc]:
                selected_docs.append(doc)
                extra -= 1
        witnesses[direction] = {
            "total_relevant": relevant,
            "unjudged_union_relevant": selected_docs,
            "unjudged_outside_union_relevant_count": relevant
            - known_count
            - len(selected_docs),
            "left_score": scores[0],
            "right_score": scores[1],
        }
    return bounds, witnesses
