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

Intervals are attainable under the declared binary constraints, subject to
normal floating-point rounding. They do not cover label errors, missing
universe members, relevance grades, dependent-query constraints or alternative
metric conventions.

## Admission and resource limits

`--max-rows` defaults to 1,000,000 **per input**, including rows below k.
`--max-work` defaults to 5,000,000. For query q, let L be the returned length
clipped at k, M its unjudged count there, and C its universe size. Work units are
`(M+1)*(L+min(k,C)+1)`. The sum over queries is checked before scoring starts.
Exact boundary is allowed; exceeding it fails rather than truncates.

These are row/work admission caps, **not hard memory or wall-time bounds**.
Parsing and in-memory inventories are needed before the work check. Inputs,
strings and reports can be large. CSV parser field-size limits also apply;
oversized fields fail. Use trusted local inputs and OS-level isolation for
untrusted large files. No disk scratch or network calls are used.

`k`, `max_rows`, `max_work` must be integers from 1 through 1,000,000,000;
`examples` is 0..20, default 0. Boolean API arguments are rejected as integers.
There is no runtime override to silently skip bad rows or incomplete totals.
