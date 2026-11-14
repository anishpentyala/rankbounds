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


def _query(ordered, judgments, universe_size, k, total, examples):
    top = ordered[:k]
    unknown = [i for i, doc in enumerate(top) if doc not in judgments]
    known = [judgments.get(doc, 0) for doc in top]
    known_rel = sum(judgments.values())
    unknown_all = universe_size - len(judgments)
    outside = unknown_all - len(unknown)
    ends = {m: {"lower": None, "upper": None} for m in METRICS}
    witnesses = {m: {} for m in METRICS}
    feasible = 0
    min_total = None
    max_total = None
    # Enumerate only the unknown-relevant count in the top-k, not 2**unknown_all
    # completions or all possible outside totals. At a fixed count, moving a
    # positive earlier never lowers any supported numerator. The denominator
    # is monotone in total relevance, so only feasible total endpoints matter.
    for count in range(len(unknown) + 1):
        low = known_rel + count
        high = low + outside
        if total is not None:
            if not low <= total <= high:
                continue
            low = high = total
        feasible += 1
        min_total = low if min_total is None else min(min_total, low)
        max_total = high if max_total is None else max(max_total, high)
        for direction, positions, relevant_total in (
            ("lower", unknown[len(unknown) - count :] if count else [], high),
            ("upper", unknown[:count], low),
        ):
            bits = known.copy()
            for position in positions:
                bits[position] = 1
            scores = _score(bits, relevant_total, k)
            for metric, score in scores.items():
                previous = ends[metric][direction]
                better = previous is None or (
                    score < previous if direction == "lower" else score > previous
                )
                if better:
                    ends[metric][direction] = score
                    if examples:
                        witnesses[metric][direction] = {
                            "total_relevant": relevant_total,
                            "unjudged_top_relevant": [top[p] for p in positions],
                            "unjudged_outside_relevant_count": (
                                relevant_total - known_rel - count
                            ),
                        }
    if not feasible:
        raise BoundsError("total relevant count contradicts judgments or universe")
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
