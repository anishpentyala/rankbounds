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

## Compare two rankings under the same missing labels

Separate single-run endpoints generally use different hypothetical judgments.
Subtracting those endpoints can therefore exaggerate the possible difference.
For precision, recall and binary nDCG, `compare` optimizes the difference while
requiring both rankings to use the **same label for each document**:

```python
from rankbounds import compare

report = compare(
    "universe.csv", "left.csv", "right.csv", "judgments.csv", k=10,
    # totals="totals.csv",  # Optional exact per-query relevant counts.
    examples=1,
)
print(report["macro"]["ndcg"])  # Attainable left-minus-right endpoints.
```

```sh
rankbounds --universe universe.csv --ranking left.csv \
  --comparison-ranking right.csv --judgments judgments.csv --k 10
```

Both rankings use the existing ranking CSV format and the same cutoff. Each
must reference the declared universe, including rows below the cutoff. A missing
query ranking is empty, never omitted from the macro average. Identical rankings
have zero paired difference even when their separate intervals are wide.

By default, paired mode reports **precision, recall and binary nDCG**.
Opt in to paired reciprocal rank with `compare(..., include_rr=True)` or
`--paired-rr` together with `--comparison-ranking`. Use the separate opt-in `--paired-ap` for budgeted paired AP/total-R bounds.
A positive difference favors the left ranking under the stated metric, but these are compatibility intervals, not
statistical evidence, confidence intervals, or a significance test. There is no
automatic winner decision, tolerance threshold or guaranteed outward rounding.
The finite universe and known labels are still caller claims. Endpoint examples
are hypothetical shared completions, not new judgments; IDs are disclosed only
when examples are requested, apart from the query IDs always in the report.
Single-run mode and its five metrics remain available without
`--comparison-ranking`. [Paired format and limits](FORMAT.md#paired-mode).

### Optional paired reciprocal rank

```sh
rankbounds --universe universe.csv --ranking left.csv \
  --comparison-ranking right.csv --judgments judgments.csv --k 10 --paired-rr
```

RR is the reciprocal of the first relevant rank at or before k, or zero if
there is no such rank. Opt-in mode adds `rr` bounds and endpoint examples using
the same report layout. `include_rr` must be an actual boolean; default False
preserves the prior metrics and work-admission calculation. The CLI flag without
a comparison ranking is an input error, not a request for single-run RR.

The solver enumerates possible first relevant positions in both truncated runs,
rejects incompatible shared labels and totals, and constructs a feasible shared
completion. It does not subtract separate RR intervals. Exact totals constrain
all documents, including those outside the top-k union. RR is insensitive to
labels after both first hits, but those labels still matter for feasibility.

This explicit enumeration has a conservative extra work-admission charge of
`(L + 1) * (R + 1) * (L + R + 1)` per query, where L/R are the truncated run
lengths. It can reject large cutoffs admitted by default mode; it is not intended
as a fast large-k solver. The existing `max_work` limit covers both charges,
checked for every query before any scoring. These are not hard time/RAM limits.
No confidence, significance, winner, or outward-rounding guarantee is added.
[Proof and checks](RECIPROCAL_VALIDATION.md).


### Optional paired AP with shared labels

```sh
rankbounds --universe universe.csv --ranking left.csv \
  --comparison-ranking right.csv --judgments judgments.csv --k 10 --paired-ap
```

`compare(..., include_ap=True)` adds `ap_total` to paired results. This is AP@k
with the **completed universe's total relevant count** as denominator, not
`min(R, k)`. It compares the same completion on both rankings. Separate AP
intervals cannot be subtracted as though their extremizing labels were shared.
The existing no-relevant-documents convention gives AP zero when R is zero.

This option enumerates every assignment to the unjudged top-k union, so its
cost is exponential in that union's unknown-document count. Outside-union labels
only affect the shared denominator; the solver checks its feasible endpoints
(or the supplied exact total) instead of enumerating outside subsets. The
existing `--max-work` admission rule includes this extra cost and can refuse even
moderate top-k unions. Nothing is sampled or silently dropped to fit. Default
paired output and work units are unchanged without the opt-in. It combines with
`--paired-rr`. This is an addition to an existing tool, not a new retrieval metric
or claim of a new optimization method. Ordinary floating-point and witness
privacy limits still apply. [AP format and cost](FORMAT.md#opt-in-paired-ap).


## Declared ranges for total relevant counts

An exact count is not required when you can only declare a lower and upper bound
on the number of relevant documents in each finite query universe. Supply a
separate CSV with the exact header `query_id,min_relevant,max_relevant`, one row
per query:

```csv
query_id,min_relevant,max_relevant
q1,20,35
q2,0,8
```

```sh
rankbounds --universe universe.csv --ranking ranking.csv \
  --judgments judgments.csv --total-ranges ranges.csv --k 10
```

Both APIs accept `total_ranges="ranges.csv"`. It also works with
`--comparison-ranking`, `--paired-rr` and `--paired-ap`. Use either `totals` or
`total_ranges`, never both. Existing exact-total CSVs and default reports remain
supported without changes. A singleton range is equivalent to an exact total;
a full `0..universe_size` range adds no information.

Bounds are inclusive, nonnegative integers, ordered and at most the query's
universe size. Each range is intersected with what the known judgments permit.
An empty intersection is an input error, not an omitted query. For example, a
range of 2..5 with three known positives admits 3..5, provided enough unjudged
documents exist. Effective bounds appear in `feasible_total_relevant` and every
endpoint example obeys them. The all-unjudged-negative convention is compatible
only when the known-positive count lies in the declared range.

These are caller-declared constraints, not estimated counts or a confidence
interval. The tool does not verify that a real collection satisfies them. They
constrain the whole finite universe, including unreturned and below-cutoff
documents. Counts remain query-local: a shared cross-query relevance budget is
not modeled. Row/work admission rules, floating-point limits and example-ID
privacy rules are unchanged. [Count-range reasoning and checks](TOTAL_RANGES.md).
