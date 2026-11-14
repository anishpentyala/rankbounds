"""Exact discrete extremizers under binary labels, with floating point scores."""

import csv
import math
from pathlib import Path

METRICS = ("precision", "recall", "rr", "ap_total", "ndcg")


class BoundsError(ValueError):
    """Invalid, contradictory or over-budget declared inputs."""


def _positive(value, name):
    if type(value) is not int or not 1 <= value <= 1_000_000_000:
        raise BoundsError(name + " must be an integer from one through 1000000000")


def _integer(text, name, minimum=0):
    if not text or len(text) > 18 or not text.isascii() or not text.isdecimal():
        raise BoundsError(
            name + " must be an ASCII decimal integer of at most 18 digits"
        )
    value = int(text)
    if value < minimum:
        raise BoundsError(name + " is below its minimum")
    return value


def _rows(path, columns, max_rows):
    # Names and error messages omit actual identifiers and filesystem paths.
    try:
        with Path(path).open(encoding="utf-8-sig", newline="") as stream:
            reader = csv.reader(stream, strict=True)
            header = next(reader, None)
            if header != list(columns):
                raise BoundsError("expected CSV header: " + ",".join(columns))
            for index, row in enumerate(reader, 1):
                if index > max_rows:
                    raise BoundsError("input row limit exceeded")
                if len(row) != len(columns) or any(
                    not cell or cell != cell.strip() or "\x00" in cell for cell in row
                ):
                    raise BoundsError(
                        "invalid cell or row width at data row " + str(index)
                    )
                yield row
    except (OSError, UnicodeError, csv.Error, OverflowError) as exc:
        raise BoundsError("cannot read valid UTF-8 CSV input") from exc


def _score(bits, total, k):
    hits = 0
    ap_terms = []
    dcg_terms = []
    first = 0
    for rank, relevant in enumerate(bits, 1):
        if relevant:
            hits += 1
            first = first or rank
            ap_terms.append(hits / rank)
            dcg_terms.append(1 / math.log2(rank + 1))
    ideal = math.fsum(1 / math.log2(i + 1) for i in range(1, min(total, k) + 1))
    return {
        "precision": hits / k,
        "recall": hits / total if total else 0.0,
        "rr": 1 / first if first else 0.0,
        "ap_total": math.fsum(ap_terms) / total if total else 0.0,
        "ndcg": math.fsum(dcg_terms) / ideal if ideal else 0.0,
    }


def _metric_scores(hits, first, ap, dcg, ideal, total, k):
    return {
        "precision": hits / k,
        "recall": hits / total if total else 0.0,
        "rr": 1 / first if first else 0.0,
        "ap_total": ap / total if total else 0.0,
        "ndcg": dcg / ideal if ideal else 0.0,
    }


def _query(ordered, judgments, universe_size, k, total, examples):
    top = ordered[:k]
    unknown = [i for i, doc in enumerate(top) if doc not in judgments]
    known = [judgments.get(doc, 0) for doc in top]
    known_rel = sum(judgments.values())
    unknown_all = universe_size - len(judgments)
    outside = unknown_all - len(unknown)
    if total is not None and not known_rel <= total <= known_rel + unknown_all:
        raise BoundsError("total relevant count contradicts judgments or universe")
    # Prefix fixed positives and suffix fixed reciprocal-rank contributions.
    prefix = [0]
    for bit in known:
        prefix.append(prefix[-1] + bit)
    suffix = [0.0] * (len(top) + 1)

    # Compensated accumulation avoids quadratic re-summing of growing lists.
    def accumulator(initial=0.0):
        value = initial
        correction = 0.0

        def add(term):
            nonlocal value, correction
            adjusted = term - correction
            new = value + adjusted
            correction = (new - value) - adjusted
            value = new
            return value

        return add

    suffix_add = accumulator()
    for position in range(len(top) - 1, -1, -1):
        suffix[position] = suffix_add(known[position] / (position + 1))
    ideal = [0.0]
    ideal_add = accumulator()
    for rank in range(1, min(k, universe_size) + 1):
        ideal.append(ideal_add(1 / math.log2(rank + 1)))
    base_ap = math.fsum(prefix[i + 1] / (i + 1) for i, bit in enumerate(known) if bit)
    base_dcg = math.fsum(1 / math.log2(i + 2) for i, bit in enumerate(known) if bit)
    base_first = next((i + 1 for i, bit in enumerate(known) if bit), 0)
    # [AP accumulator, DCG accumulator, selected reciprocal suffix, first hit]
    states = {
        direction: [
            accumulator(base_ap),
            accumulator(base_dcg),
            accumulator(),
            base_first,
        ]
        for direction in ("lower", "upper")
    }
    ap = {direction: base_ap for direction in states}
    dcg = {direction: base_dcg for direction in states}
    selected_suffix = 0.0
    ends = {m: {"lower": None, "upper": None} for m in METRICS}
    choices = {m: {} for m in METRICS}
    min_total = None
    max_total = None
    for count in range(len(unknown) + 1):
        if count:
            for direction, position in (
                ("lower", unknown[-count]),
                ("upper", unknown[count - 1]),
            ):
                state = states[direction]
                rank = position + 1
                # Earliest-first additions have count-1 selected positives before
                # rank, none after. Latest-first has them all after, none before.
                earlier = count - 1 if direction == "upper" else 0
                later = selected_suffix if direction == "lower" else 0.0
                ap[direction] = state[0](
                    (prefix[position] + earlier + 1) / rank
                    + suffix[position + 1]
                    + later
                )
                dcg[direction] = state[1](1 / math.log2(rank + 1))
                state[3] = min(state[3], rank) if state[3] else rank
                if direction == "lower":
                    selected_suffix = state[2](1 / rank)
        low = known_rel + count
        high = low + outside
        if total is not None:
            if not low <= total <= high:
                continue
            low = high = total
        min_total = low if min_total is None else min(min_total, low)
        max_total = high if max_total is None else max(max_total, high)
        for direction, relevant_total in (("lower", high), ("upper", low)):
            hits = prefix[-1] + count
            first = states[direction][3]
            denom = ideal[min(relevant_total, k)]
            scores = _metric_scores(
                hits, first, ap[direction], dcg[direction], denom, relevant_total, k
            )
            for metric, score in scores.items():
                previous = ends[metric][direction]
                better = previous is None or (
                    score < previous if direction == "lower" else score > previous
                )
                if better:
                    ends[metric][direction] = score
                    choices[metric][direction] = (count, relevant_total)
    # Re-score the at most ten selected completions using the original fsum
    # evaluator. Recurrences choose extrema, but emitted scores stay bound to
    # an actual completion rather than accumulated roundoff (e.g. 1+epsilon).
    final_scores = {}
    for metric in METRICS:
        for direction in ("lower", "upper"):
            count, relevant_total = choices[metric][direction]
            positions = (
                unknown[:count]
                if direction == "upper"
                else unknown[len(unknown) - count :]
                if count
                else []
            )
            key = (tuple(positions), relevant_total)
            if key not in final_scores:
                bits = known.copy()
                for position in positions:
                    bits[position] = 1
                final_scores[key] = _score(bits, relevant_total, k)
            ends[metric][direction] = final_scores[key][metric]
    baseline_valid = total is None or total == known_rel
    result = {
        "universe_documents": universe_size,
        "judged_documents": len(judgments),
        "known_relevant": known_rel,
        "unjudged_documents": unknown_all,
        "returned_documents": len(ordered),
        "top_documents": len(top),
        "unjudged_top_documents": len(unknown),
        "feasible_total_relevant": {"lower": min_total, "upper": max_total},
        "metrics": ends,
        "all_unjudged_nonrelevant": {
            "compatible": baseline_valid,
            "metrics": _score(known, known_rel, k) if baseline_valid else None,
        },
    }
    if examples:
        witnesses = {m: {} for m in METRICS}
        for metric in METRICS:
            for direction in ("lower", "upper"):
                count, relevant_total = choices[metric][direction]
                positions = (
                    unknown[:count]
                    if direction == "upper"
                    else unknown[len(unknown) - count :]
                    if count
                    else []
                )
                witnesses[metric][direction] = {
                    "total_relevant": relevant_total,
                    "unjudged_top_relevant": [top[p] for p in positions],
                    "unjudged_outside_relevant_count": relevant_total
                    - known_rel
                    - count,
                }
        result["endpoint_examples"] = witnesses
    return result


def audit(
    universe,
    ranking,
    judgments,
    *,
    k,
    totals=None,
    examples=0,
    max_rows=1_000_000,
    max_work=5_000_000,
):
    """Read strict CSVs and audit every declared query. See FORMAT.md.

    max_rows caps each input separately; max_work caps the sum of
    (unjudged_top+1)*(top_length+min(k,universe_length)+1), before scoring.
    Neither is a hard RAM or wall-time bound. IDs stay literal, case-sensitive.
    examples is the number of lexical query IDs whose endpoint examples to emit.
    """
    for value, name in ((k, "k"), (max_rows, "max_rows"), (max_work, "max_work")):
        _positive(value, name)
    if type(examples) is not int or not 0 <= examples <= 20:
        raise BoundsError("examples must be an integer from 0 through 20")
    inventory = {}
    for qid, doc in _rows(universe, ("query_id", "document_id"), max_rows):
        docs = inventory.setdefault(qid, set())
        if doc in docs:
            raise BoundsError("duplicate universe document")
        docs.add(doc)
    if not inventory:
        raise BoundsError("universe must declare at least one query/document pair")
    runs = {qid: {} for qid in inventory}
    seen = {qid: set() for qid in inventory}
    for qid, doc, rank_text in _rows(
        ranking, ("query_id", "document_id", "rank"), max_rows
    ):
        if qid not in inventory or doc not in inventory[qid]:
            raise BoundsError("ranking document is outside declared query universe")
        rank = _integer(rank_text, "rank", 1)
        if rank in runs[qid] or doc in seen[qid]:
            raise BoundsError("duplicate ranking rank or document")
        runs[qid][rank] = doc
        seen[qid].add(doc)
    ordered = {}
    for qid, run in runs.items():
        if sorted(run) != list(range(1, len(run) + 1)):
            raise BoundsError("ranking ranks must be contiguous starting at one")
        ordered[qid] = [run[r] for r in range(1, len(run) + 1)]
    labels = {qid: {} for qid in inventory}
    for qid, doc, rel_text in _rows(
        judgments, ("query_id", "document_id", "relevant"), max_rows
    ):
        if qid not in inventory or doc not in inventory[qid]:
            raise BoundsError("judgment document is outside declared query universe")
        relevant = _integer(rel_text, "relevant")
        if relevant > 1:
            raise BoundsError("relevant must be binary zero or one")
        if doc in labels[qid]:
            raise BoundsError("duplicate judgment")
        labels[qid][doc] = relevant
    counts = {}
    if totals is not None:
        for qid, count_text in _rows(totals, ("query_id", "total_relevant"), max_rows):
            if qid not in inventory or qid in counts:
                raise BoundsError("unknown or duplicate total query")
            counts[qid] = _integer(count_text, "total_relevant")
        if set(counts) != set(inventory):
            raise BoundsError("totals must cover every declared query exactly once")
    work = 0
    for qid in inventory:
        top = ordered[qid][:k]
        unjudged = sum(doc not in labels[qid] for doc in top)
        work += (unjudged + 1) * (len(top) + min(k, len(inventory[qid])) + 1)
        if work > max_work:
            raise BoundsError("scoring work limit exceeded")
    queries = []
    for index, qid in enumerate(sorted(inventory)):
        row = _query(
            ordered[qid],
            labels[qid],
            len(inventory[qid]),
            k,
            counts.get(qid),
            index < examples,
        )
        queries.append({"query_id": qid, **row})
    macro = {
        metric: {
            direction: math.fsum(q["metrics"][metric][direction] for q in queries)
            / len(queries)
            for direction in ("lower", "upper")
        }
        for metric in METRICS
    }
    return {
        "schema_version": 1,
        "mode": "finite_binary_compatibility",
        "k": k,
        "query_count": len(queries),
        "scoring_work_units": work,
        "macro": macro,
        "queries": queries,
    }
