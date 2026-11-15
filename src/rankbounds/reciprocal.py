"""Paired reciprocal-rank extrema by feasible first-relevant positions."""


def _reciprocal_bounds(left, right, labels, size, total, examples):
    """Runs are already truncated to k; every feasible first-hit pair is tried."""
    union = set(left) | set(right)
    known_positive = {doc for doc, label in labels.items() if label}
    known_negative = set(labels) - known_positive
    unknown_union = sorted(union - set(labels))
    unknown_outside = size - len(labels) - len(unknown_union)
    bounds = {"lower": None, "upper": None}
    choices = {}
    for i in range(len(left) + 1):
        for j in range(len(right) + 1):
            # Index len(run) denotes no relevant retrieved document.
            zero = set(left[:i]) | set(right[:j])
            one = set(left[i : i + 1]) | set(right[j : j + 1])
            if zero & (one | known_positive) or one & known_negative:
                continue
            selected = one - known_positive
            eligible = [doc for doc in unknown_union if doc not in zero | selected]
            low = len(known_positive) + len(selected)
            high = low + len(eligible) + unknown_outside
            if total is not None and not low <= total <= high:
                continue
            relevant = low if total is None else total
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
                        # Fill unconstrained union labels first, then outside.
                        extra = min(relevant - low, len(eligible))
                        choices[direction] = {
                            "total_relevant": relevant,
                            "unjudged_union_relevant": sorted(
                                selected | set(eligible[:extra])
                            ),
                            "unjudged_outside_union_relevant_count": relevant
                            - low
                            - extra,
                            "left_score": scores[0],
                            "right_score": scores[1],
                        }
    return bounds, choices
