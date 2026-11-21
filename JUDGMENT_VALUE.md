# Hypothetical judgment-value analysis

## Question and scope

Given a single retrieval ranking and incomplete binary judgments, how much narrower would a query's metric interval become if one particular currently unjudged document were labeled? The optional judgment_candidates CSV asks that question for an explicit shortlist. It does not predict labels, assign probabilities, optimize a batch, select a metric, model annotation cost or claim optimal active learning. Candidates are evaluated one at a time against the original judgments and original count constraints.

Only audit / single-run CLI mode supports it. This is intentionally not a paired score-difference analysis. It is query-local even when fixed query weights are present; no cross-query priority or weighted importance is inferred. A narrow interval is not an accurate score estimate unless the declared universe, labels and other assumptions are correct.

## Input and output

The candidate file has exact ordered header query_id,document_id. It must have 1 to 200 unique pairs. Each pair must exist in the declared universe and not already have a judgment. Other queries need not be represented. IDs are literal and case-sensitive; row order does not matter. The shared regular-file, UTF-8/BOM, strict CSV, cell-validation and max_rows rules apply. Invalid candidates fail before any original or hypothetical solver call.

The ordinary report is preserved, except that scoring_work_units includes the extra conservative work reservation. The added judgment_value object contains:

- scope = single_query_interval_width.
- candidates: list ordered lexically by query ID and document ID.
- Each candidate: query_id, document_id, outcomes, metrics.
- outcomes: label strings 0 and/or 1 mapped to all five metric endpoint pairs. Impossible outcomes are absent, not null, zero-valued or assumed equally likely.
- metrics: for each metric, before_width, after_width_by_label, guaranteed_reduction and best_case_reduction.

Every requested document ID is disclosed when this option is used, regardless of examples=0. This is deliberate opt-in output, not an automatic scan of unjudged documents. Neither labels nor inputs are written, and hypothetical endpoint document examples are not added. Existing --examples behavior remains separate. The full endpoint report for each feasible label lets a reader distinguish a narrowed interval from a shifted interval.

## Feasibility and width definitions

Let C be the original feasible binary completions for this query. For candidate d and label b, C_b contains the completions in C with d=b. These sets partition C. The original validated query has at least one completion, so at least one C_b is nonempty. With K known positives and U unknown documents before the hypothetical judgment, label b is feasible exactly when the original total-relevant range intersects [K+b, K+b+U-1]. This is the same finite-universe count-feasibility test already used by the solver. An exact total is a singleton range. Without a declared count constraint, both outcomes are possible.

The original total/range is retained, not reduced by b: the solver receives a new known label, so it already incorporates that known positive when checking the whole-universe total. Every feasible outcome is scored using the existing single-query solver with a separate label dictionary. A hypothetical label from one candidate never becomes input to another candidate.

For each metric f, let W be max_C f - min_C f, and W_b be max_(C_b) f - min_(C_b) f for each feasible outcome. Then:

- guaranteed_reduction = W - max_b W_b.
- best_case_reduction = W - min_b W_b.

In real arithmetic, a subset's width cannot exceed its parent's, so 0 <= guaranteed_reduction <= best_case_reduction <= W. These are worst/best conditional reductions, not expected reductions. A forced label, already implied by the count constraints, cannot remove a feasible completion and has zero mathematical reduction. Each metric/direction can need a different completion. No joint endpoint vector is promised.

Production scores remain ordinary floating-point values from the existing solver. The new widths and reductions subtract those emitted endpoints. Near-tie selection and rounding can produce small negative reductions or differences from exact-arithmetic identities. Values are not clipped, certified outward-rounded or ranked with a hidden tolerance. Do not treat last-bit differences as meaningful annotation priorities.

## Example

Universe a,b,c,d; returned ranking a,b,c; only b is known relevant; k=3. Candidates a and unreturned d are unjudged.

| Candidate | Metric | Guaranteed width reduction | Best-case width reduction |
| --- | --- | --- | --- |
| a | precision | about 0.33333 | about 0.33333 |
| a | recall | 0 | about 0.16667 |
| a | reciprocal rank | 0.5 | 0.5 |
| d | precision | 0 | 0 |
| d | recall | 0.25 | 0.5 |

The original recall interval width is 0.5. Learning d=0 makes recall certain for this finite universe, whereas d=1 leaves width 0.25. An unreturned document can therefore matter more for recall uncertainty than the first returned document. This is not a predicted label, a reason to skip unreturned documents generally, or a claim about annotation cost. The files under examples/judgment-value and the actual CLI output reproduce this case.

## Admission and cost

For original per-query work estimate W_q, the opt-in admission sum is sum_q W_q + 2*sum_candidates W_(candidate query). Both hypothetical calls are reserved before any scoring, even when a count constraint will make one outcome impossible. This conservative estimate avoids making the admission limit depend on skipping forced labels. There are at most two additional solver calls per candidate, and no more than 200 candidates. A caller can lower max_work or use a smaller shortlist.

The estimate is not a complete operation count or an OS resource limit. Parsing, copying known-label dictionaries, validation, report construction, integer/ID sizes and aggregation have costs outside that solver formula. Extra mappings use O(Q) entries, reports use O(C*M) endpoint/metric records plus ID bytes, and each temporary label copy uses O(L_q) entries; each hypothetical also needs the existing query solver's workspace. Here Q is query count, C<=200 candidate count, M=5 metric count and L_q is that query's known-label count. No I/O deadline, total output-byte cap or hard wall-time/RAM guarantee is introduced.

## Validation

- 158 tests pass on Python 3.9 through 3.15. Thirteen new tests cover analytic top/returned-versus-unreturned behavior; worst/best-case distinction; 80 seeded two-query exhaustive completion oracles; exact/range counts and forced labels; None/default/weighted/report parity including zero-weight query candidates; work boundary and before-solver refusal; invalid/duplicate/known/missing candidates; 200/201 limits; row limit; BOM/order/literal ID/UTF-8 rules; single-only CLI and no partial JSON; and special candidate files.
- The independent oracle enumerates every binary completion, computes literal metric scores, and groups these completions by the candidate's true label. It compares all conditional endpoints, feasible outcome sets, widths and both reductions. It does not call the production candidate helper or production solver for expected values.
- Five behavioral mutants are caught with actual assertion failures inspected: optimistic best-case substituted for the guarantee, impossible outcome included, shared input labels mutated, analysis work omitted and label zero used twice. The work omission also triggers mocked-solver errors, but a separate real-solver refusal assertion supplies its evidence. Mutation of shared labels also has direct wrong-metric assertions, not only later exceptions.
- 450 complete default and 450 complete weighted reports match isolated current-public-base imports. For the 150 single-run cases, removing judgment_value and restoring only the old scoring_work_units yields the same weighted report. Default None leaves the report unchanged.
- The same-target base does not support this new opt-in API. Its expected TypeError is an additive-feature negative control, not a claim of an old numerical bug.
- A built wheel installed into a separate Python 3.9 environment passes 158 tests from a neutral directory with no local package import. Ruff check and format pass. The actual README CLI example is checked. No external adoption, annotation campaign or deployment claimed.
