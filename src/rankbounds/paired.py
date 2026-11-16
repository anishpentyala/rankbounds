"""Shared-label paired bounds for binary retrieval metrics."""

import math

from .average_precision import _average_precision_bounds
from .core import BoundsError, _load_inputs, _load_ranking, _positive, _score
from .reciprocal import _reciprocal_bounds

PAIRED_METRICS = ("precision", "recall", "ndcg")


def _paired_query(
    left, right, judgments, size, k, total, examples, include_rr=False, include_ap=False
):
    left, right = left[:k], right[:k]
    union = sorted(set(left) | set(right))
    unknown = [doc for doc in union if doc not in judgments]
    known_rel = sum(judgments.values())
    unknown_all = size - len(judgments)
    outside = unknown_all - len(unknown)
    if total is not None and not known_rel <= total <= known_rel + unknown_all:
        raise BoundsError("total relevant count contradicts judgments or universe")
    hit_weights = {doc: 0 for doc in union}
    dcg_parts = {doc: [] for doc in union}
    for sign, run in ((1, left), (-1, right)):
        for rank, doc in enumerate(run, 1):
            hit_weights[doc] += sign
            dcg_parts[doc].append(sign / math.log2(rank + 1))
    dcg_weights = {doc: math.fsum(parts) for doc, parts in dcg_parts.items()}
    ideal = [0.0]
    # A compensated prefix avoids an O(k**2) repeated fsum.
    value = correction = 0.0
    for rank in range(1, min(k, size) + 1):
        term = 1 / math.log2(rank + 1) - correction
        new = value + term
        correction = (new - value) - term
        value = new
        ideal.append(value)
    ends = {metric: {"lower": None, "upper": None} for metric in PAIRED_METRICS}
    choices = {metric: {} for metric in PAIRED_METRICS}
    for metric in PAIRED_METRICS:
        weights = dcg_weights if metric == "ndcg" else hit_weights
        order = sorted(unknown, key=lambda doc: (weights[doc], doc))
        fixed = math.fsum(weights[doc] for doc in union if judgments.get(doc) == 1)
        # Prefix sums of a fixed sorted coefficient sequence give the extremum
        # for each possible number of positive labels in the top-k union.
        prefixes = {"lower": [fixed], "upper": [fixed]}
        for direction, sequence in (("lower", order), ("upper", order[::-1])):
            value, correction = fixed, 0.0
            for doc in sequence:
                term = weights[doc] - correction
                new = value + term
                correction = (new - value) - term
                value = new
                prefixes[direction].append(value)
        for count in range(len(order) + 1):
            low = known_rel + count
            high = low + outside
            if total is not None:
                if not low <= total <= high:
                    continue
                low = high = total
            for direction in ("lower", "upper"):
                numerator = prefixes[direction][count]
                # For a signed difference, increasing the common denominator
                # moves a negative value UP and a positive value DOWN.
                small = (numerator < 0) if direction == "lower" else (numerator > 0)
                relevant = low if small else high
                denominator = (
                    k
                    if metric == "precision"
                    else relevant
                    if metric == "recall"
                    else ideal[min(relevant, k)]
                )
                score = numerator / denominator if denominator else 0.0
                previous = ends[metric][direction]
                if previous is None or (
                    score < previous if direction == "lower" else score > previous
                ):
                    ends[metric][direction] = score
                    choices[metric][direction] = (order, count, relevant)
    witnesses = {metric: {} for metric in PAIRED_METRICS}
    for metric in PAIRED_METRICS:
        for direction in ("lower", "upper"):
            order, count, relevant = choices[metric][direction]
            chosen = order[:count] if direction == "lower" else order[::-1][:count]
            positives = {doc for doc, label in judgments.items() if label} | set(chosen)
            # Re-score both rankings on the SAME selected completion. Unnamed
            # outside positives affect only the shared relevance denominator.
            scores = [
                _score([int(doc in positives) for doc in run], relevant, k)[metric]
                for run in (left, right)
            ]
            ends[metric][direction] = scores[0] - scores[1]
            if examples:
                witnesses[metric][direction] = {
                    "total_relevant": relevant,
                    "unjudged_union_relevant": sorted(chosen),
                    "unjudged_outside_union_relevant_count": relevant
                    - known_rel
                    - count,
                    "left_score": scores[0],
                    "right_score": scores[1],
                }
    if include_rr:
        ends["rr"], witnesses["rr"] = _reciprocal_bounds(
            left, right, judgments, size, total, examples
        )
    if include_ap:
        ends["ap_total"], witnesses["ap_total"] = _average_precision_bounds(
            left, right, judgments, size, total, examples
        )
    result = {
        "universe_documents": size,
        "judged_documents": len(judgments),
        "known_relevant": known_rel,
        "unjudged_documents": unknown_all,
        "left_top_documents": len(left),
        "right_top_documents": len(right),
        "top_union_documents": len(union),
        "unjudged_top_union_documents": len(unknown),
        "feasible_total_relevant": {
            "lower": known_rel if total is None else total,
            "upper": known_rel + unknown_all if total is None else total,
        },
        "metrics": ends,
    }
    if examples:
        result["endpoint_examples"] = witnesses
    return result


def compare(
    universe,
    left_ranking,
    right_ranking,
    judgments,
    *,
    k,
    totals=None,
    examples=0,
    max_rows=1_000_000,
    max_work=5_000_000,
    include_rr=False,
    include_ap=False,
):
    """Attainable left-minus-right metric bounds under shared binary labels.

    Precision, recall and binary nDCG; optional reciprocal rank and budgeted AP.
    Every query, including empty runs, contributes equally to macro endpoints.
    """
    if type(include_rr) is not bool:
        raise BoundsError("include_rr must be a boolean")
    if type(include_ap) is not bool:
        raise BoundsError("include_ap must be a boolean")
    metrics = (
        PAIRED_METRICS
        + (("rr",) if include_rr else ())
        + (("ap_total",) if include_ap else ())
    )
    for value, name in ((k, "k"), (max_rows, "max_rows"), (max_work, "max_work")):
        _positive(value, name)
    if type(examples) is not int or not 0 <= examples <= 20:
        raise BoundsError("examples must be an integer from 0 through 20")
    inventory, left, labels, counts = _load_inputs(
        universe, left_ranking, judgments, totals, max_rows
    )
    right = _load_ranking(right_ranking, inventory, max_rows)
    work = 0
    for qid in inventory:
        union = set(left[qid][:k]) | set(right[qid][:k])
        unknown = sum(doc not in labels[qid] for doc in union)
        work += (unknown + 1) * (
            len(left[qid][:k]) + len(right[qid][:k]) + min(k, len(inventory[qid])) + 1
        )
        if include_rr:
            a, b = len(left[qid][:k]), len(right[qid][:k])
            work += (a + 1) * (b + 1) * (a + b + 1)
        if include_ap:
            # Refuse before creating a huge power-of-two integer or solving any
            # query. Even one unit per labeling would exceed the whole budget.
            if unknown >= max_work.bit_length():
                raise BoundsError("paired AP scoring work limit exceeded")
            work += (1 << unknown) * 2 * (len(left[qid][:k]) + len(right[qid][:k]) + 1)
        if work > max_work:
            raise BoundsError("paired scoring work limit exceeded")
    queries = [
        {
            "query_id": qid,
            **_paired_query(
                left[qid],
                right[qid],
                labels[qid],
                len(inventory[qid]),
                k,
                counts.get(qid),
                index < examples,
                include_rr,
                include_ap,
            ),
        }
        for index, qid in enumerate(sorted(inventory))
    ]
    return {
        "schema_version": 1,
        "mode": "finite_binary_paired_compatibility",
        "difference": "left_minus_right",
        "k": k,
        "query_count": len(queries),
        "scoring_work_units": work,
        "macro": {
            metric: {
                direction: math.fsum(q["metrics"][metric][direction] for q in queries)
                / len(queries)
                for direction in ("lower", "upper")
            }
            for metric in metrics
        },
        "queries": queries,
    }
