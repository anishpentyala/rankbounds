# Input, output and limits

UTF-8 CSV, optional initial UTF-8 BOM; exact ordered headers:

| File | Header | Meaning |
| --- | --- | --- |
| universe | `query_id,document_id` | Unique pair, defines finite candidate set |
| ranking | `query_id,document_id,rank` | Unique document and rank per query |
| judgments | `query_id,document_id,relevant` | Unique pair, binary 0/1 |
| totals (optional) | `query_id,total_relevant` | Exactly one row per universe query |

All IDs are literal and case-sensitive. No trimming, normalization, inferred
negative labels or score-based tie breaking. CSV quoting and internal Unicode
are supported. Empty cells, leading/trailing whitespace, NUL, bad UTF-8,
malformed CSV, blank data rows, extra/missing cells, wrong headers and duplicates
are rejected. Integer cells use ASCII digits only, at most 18 digits, no sign or
decimal point; zero padding is accepted. Rank must be positive; per-query ranks
must be exactly 1..n. Input row order does not affect output. Rankings and
judgments must reference an existing universe pair, even below cutoff k.

The universe cannot be empty and cannot express a query with no documents.
Ranking/judgment files may have only their headers. A query absent from the
ranking gets an empty run. Totals cannot omit any query or add an unknown query.
Totals below known positives or above known positives plus unjudged documents
are contradictory and rejected. All validation completes before JSON is emitted.

## JSON schema v1

- `mode`: `finite_binary_compatibility`; `k`; `query_count`.
- `scoring_work_units`: deterministic admission estimate (see below).
- `macro`: each metric's lower/upper endpoint, equal weight over all queries.
- `queries`: lexical query ID order. Each row contains `query_id`, inventory,
  judgment, relevance, returned/top/unjudged counts; feasible total-relevant
  interval; five metric intervals; and the compatible conventional all-unknown-
  negative score (or `compatible:false,metrics:null`).
- Optional `endpoint_examples` for at most the first N lexical query IDs gives
  per-metric/per-direction `total_relevant`, `unjudged_top_relevant` document IDs
  in ranking order, and `unjudged_outside_relevant_count`. These are **hypothetical
  completions, not proposed judgments**. All known labels remain fixed. All
  unlisted unjudged top-k documents are negative. Choose any stated count of
  unjudged documents outside the top-k to be positive; all other unknown labels
  are negative. Documents ranked below k count as outside. The count never
  selects known-positive or known-negative documents. No outside IDs are emitted.

Each emitted endpoint is a feasible completion score under the declared binary
constraints, subject to normal floating-point rounding. Near-tied selection can
also shift emitted endpoints by roundoff versus the prior full-scan evaluator.
There is no exact numeric baseline-parity, floating-point-extremum or certified
outward-rounding guarantee. Observed small differences do not prove a universal
drift size or direction. They do not cover label errors, missing
universe members, relevance grades, dependent-query constraints or alternative
metric conventions.

## Admission and resource limits

`--max-rows` defaults to 1,000,000 **per input**, including rows below k.
`--max-work` defaults to 5,000,000. For query q, let L be the returned length
clipped at k, M its unjudged count there, and C its universe size. Work units are
`(M+1)*(L+min(k,C)+1)`. The sum over queries is checked before scoring starts.
Exact boundary is allowed; exceeding it fails rather than truncates. This v1
admission estimate is retained for compatibility after incremental scoring
removed its quadratic scan; it is not a current operation counter.

These are row/work admission caps, **not hard memory or wall-time bounds**.
Parsing and in-memory inventories are needed before the work check. Inputs,
strings and reports can be large. CSV parser field-size limits also apply;
oversized fields fail. Use trusted local inputs and OS-level isolation for
untrusted large files. No disk scratch or network calls are used.

`k`, `max_rows`, `max_work` must be integers from 1 through 1,000,000,000;
`examples` is 0..20, default 0. Boolean API arguments are rejected as integers.
There is no runtime override to silently skip bad rows or incomplete totals.

## Paired mode

`compare(universe, left_ranking, right_ranking, judgments, k=..., ...)` and CLI
`--comparison-ranking RIGHT.csv` use the same strict files, optional totals,
option ranges and per-file row cap as single-run mode. The existing `--ranking`
is the left run. Both rankings are validated in full before scoring; malformed
or contradictory input, including below-cutoff rows in either ranking, yields
an error with no report JSON. Neither API writes or changes input files.

Paired schema version 1 uses the distinct mode
`finite_binary_paired_compatibility`, `difference: left_minus_right`, `k`,
`query_count`, `scoring_work_units`, `macro`, and lexical `queries`. Metrics are
by default `precision`, `recall`, `ndcg`, each with lower/upper differences.
Opt-in `include_rr=True` adds `rr` as described below. Scores
use the same conventions as single-run mode, including zero recall/nDCG when
there are no relevant documents and precision's denominator k for short runs.
A query row also has universe/judgment/known-relevant/unjudged counts,
left/right top counts, top-union and unjudged-top-union counts, and feasible
relevant-total bounds. There is no pass/fail or statistical significance field.

For the first `examples` lexical queries, each endpoint has `left_score`,
`right_score`, `total_relevant`, lexical `unjudged_union_relevant` IDs and an
`unjudged_outside_union_relevant_count`. Keep known labels fixed, assign listed
unknown union documents positive and all other unknown union documents negative.
Choose any stated number of unknown documents outside BOTH top-k sets to be
positive; all other unknown labels are negative. This single completed labeling
reproduces both scores and their difference, subject to floating-point rounding.
Ranked-below-cutoff documents are outside unless present in the other top-k.
Outside IDs are never emitted. Different metrics/directions can use different
completions; all endpoints are not claimed jointly attainable.

Let L and T be the two clipped ranking lengths, M the number of unknown documents
in their union, and C the universe size. Paired work admission units per query are
`(M+1)*(L+T+min(k,C)+1)`. Sum across all queries; exact cap equality is allowed.
Default `max_work` is 5,000,000. This is an admission estimate, not an operation,
hard memory or wall-time bound. Parsing, identifier storage and report generation
can still be large. Compared with single-run mode, there is one extra fully
validated ranking input. There is no scan of all binary label assignments.

Coefficient sums, normalizers and endpoint selection use ordinary double
precision with compensated or fsum accumulation where appropriate. Selected
completions are re-scored on each run and subtracted. Near ties or cancellation
can affect endpoint choice/value by roundoff. No guarantee of the exact extrema
of all floating-point computations, outward rounding, or numerical separation
from zero is made. Do not treat a tiny signed endpoint as a certified ranking.

### Opt-in paired reciprocal rank

`compare(..., include_rr=True)` or CLI `--paired-rr` adds `rr` to paired `macro`,
per-query `metrics`, and (when requested) `endpoint_examples`. Default False
leaves all report fields and admission units unchanged. That option alone does not add paired AP; use the separate `include_ap` opt-in.
The same k, known labels, exact totals and finite universe apply; RR is zero
without a relevant returned document at or before k.

Add `(L+1)*(R+1)*(L+R+1)` units per query to the existing paired charge. Work is
checked across the whole query set before calling either scoring solver. The
charge conservatively models first-position pair enumeration and prefix/union
set work, not exact CPU operations or a hard resource bound. Endpoint witnesses
use the existing shared-completion layout and disclosure rules.


### Opt-in paired AP

`compare(..., include_ap=True)` or CLI `--paired-ap` (with
`--comparison-ranking`) adds `ap_total` to paired macro, per-query metrics and
requested endpoint examples. Defaults remain unchanged. AP sums precision at
each relevant retrieved rank through k, divided by the completed universe's
total relevant count R; R=0 gives zero. This is not AP divided by min(R,k).

Let U be the number of unjudged documents in the top-k union, and L and Rlen
the two truncated ranking lengths. Add `2**U * 2 * (L + Rlen + 1)` work units
per query to the existing paired charge (and RR charge, if requested). The
whole query set is checked before any solver runs. A bit-length guard rejects
obviously excessive exponent sizes without first constructing the huge integer.
These admission units model enumerated assignments and rank scans, not exact
CPU operations, a wall-clock promise or a hard memory limit.

For each union assignment, both AP numerators are fixed. Outside-union unknown
positives change only the shared denominator. Its feasible low and high totals
suffice for both signed-difference extrema; when an exact total is supplied,
only compatible assignments and that total are scored. Witnesses use the same
shared-label format as other paired metrics. Each endpoint is attainable, but
different metrics/directions can require different completions. Scores use
ordinary double precision, not certified outward-rounded intervals. Work-limit
failure emits no partial JSON. No AP quality threshold or deployment claim.
