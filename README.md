# rankbounds

How much can incomplete binary relevance judgments change a retrieval score?

`rankbounds` reports the **attainable minimum and maximum** of precision@k,
recall@k, reciprocal rank@k, AP@k with total-relevant denominator, and binary
nDCG@k, over all labelings consistent with a declared finite document universe
and the judgments you have. You can also require an exact total-relevant count
per query.

This is a compatibility interval, **not a confidence interval, score estimate,
relevance predictor or correction for judgment-pool bias**. Wide intervals can
be the honest answer. The completeness of the universe and correctness of labels
are your claims, not facts the tool can discover.

## Run locally

Python 3.9+; no runtime dependencies or network access. Source installation:

```sh
python -m pip install .
rankbounds --universe examples/universe.csv --ranking examples/ranking.csv \
  --judgments examples/judgments.csv --k 3
```

Optional exact totals, and endpoint examples for the first lexical query:

```sh
rankbounds --universe examples/universe.csv --ranking examples/ranking.csv \
  --judgments examples/judgments.csv --totals examples/totals.csv \
  --k 3 --examples 1
```

All files are read-only. Success writes one JSON document to stdout, exit 0.
Invalid/contradictory/over-budget input writes an error to stderr and no JSON,
exit 2. There is no pass/fail quality threshold or claim that your ranking is
safe to deploy. JSON always includes query IDs and counts. `--examples 1..20`
also discloses selected unjudged document IDs; default 0 omits those examples.
Do not publish reports with sensitive identifiers.

## Why an interval rather than two naive scores?

Treating every unjudged document as nonrelevant is a convention, not always a
lower bound: unjudged documents **outside** the retrieved top-k can be relevant,
increasing recall/AP/nDCG denominators without improving their numerators.
Treating them all as relevant need not give the upper bound either. For example,
if rank 1 is relevant, rank 2 nonrelevant, and rank 3 unjudged, the best nDCG@3
completion may leave rank 3 nonrelevant. Changing the ideal ranking matters.

The tool handles these numerator/denominator dependencies together, does not
condense ranks, and includes unreturned documents in the total-relevant count.
The all-unjudged-nonrelevant convention is reported separately only when it is
compatible with any supplied totals.

Use `ir_measures`, `ranx` or `trec_eval` for general evaluation, graded metrics,
TREC formats and established incomplete-judgment estimators such as bpref/infAP.
This tool has a smaller purpose: deterministic binary sensitivity to missing
labels under a user-declared finite universe. It does not claim a new retrieval
metric, research method, package ecosystem, or universal improvement over those
tools. [Sources and distinctions](EVIDENCE.md).

## Semantics

- Explicit universe rows `(query_id,document_id)` define each query's entire
  candidate set. This can be a finite benchmark pool, but results then describe
  **that pool**, not all documents on the web or in a larger collection.
- Ranking is a partial ordered list, contiguous ranks starting at 1, no ties or
  repeated documents. A missing query ranking is an empty run, not a skipped
  query. Every declared query is included in the equal-weight macro average.
- Binary judgments are exactly 0 or 1; unjudged is represented by no row.
- Precision divides by k even for short runs. Recall and `ap_total` divide by
  the completed universe's total relevant count R, not `min(R,k)`. AP sums
  precision at relevant returned ranks up to k and divides by R. This naming
  avoids silently choosing among AP@k conventions.
- nDCG uses gains 0/1 and discount `1/log2(rank+1)`. Its ideal ranking has
  `min(R,k)` relevant documents, including relevant documents not returned.
- RR is zero if no relevant document appears by k. Recall/AP/nDCG are defined
  as zero when R is zero. These queries are included, not dropped.
- Each metric endpoint is individually attainable. Different endpoints can
  require different label completions. A vector of endpoints need not be jointly
  attainable, and separate runs' intervals are **not paired score-difference
  bounds**. Do not infer a system comparison by subtracting these endpoints as
  though the extremizing judgments were identical.
- Unknown labels are not sampled or assigned probabilities. Correlations across
  documents/queries are not modeled. Totals are exact caller constraints, never
  estimated by the tool. Discrete optimization is exact; reported scores use
  ordinary double-precision arithmetic, not certified outward-rounded intervals.

[FORMAT.md](FORMAT.md) covers validation, output and resource limits.
[DESIGN.md](DESIGN.md) explains incremental extremizer scoring and its cost.
The existing conservative work-admission rule remains unchanged. Near-tied
candidate selection can change endpoint examples **and emitted values** by
floating-point roundoff versus the prior full scan. Each emitted endpoint remains
a feasible completion score, without exact numeric baseline-parity or certified
outward-rounding guarantees. Examples are hypothetical witnesses, not stable
label advice.

## Python API

```python
from rankbounds import audit, BoundsError
report = audit("universe.csv", "ranking.csv", "judgments.csv", k=10)
```

Same semantics and validation as the CLI. No automatic file discovery, writes,
telemetry, statistical inference, model calls or repairs.

## Development

```sh
python -m pip install . ruff==0.15.0 build
python -m unittest discover -s tests -v
ruff check .
ruff format --check .
python -m build
```

Tests enumerate independent complete binary labelings for small universes and
check every endpoint against literal metrics. They also reconstruct endpoint
examples, exercise exact totals, empty/short runs, zero-positive queries,
query-local document identity, row-order stability and fail-closed parsing.
These tests do not establish that a real inventory or judgment set is correct.
MIT license. Source distribution only; no hosted service or data upload.
