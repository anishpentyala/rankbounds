# Fixed query-weighted aggregates

## Purpose and scope

Equal-query macro averages answer a different question from a traffic-weighted average. The optional query_weights CSV supplies fixed nonnegative integer counts or declared importance weights. It adds query_weighted without changing macro, query inclusion, metric definitions, hypothetical completions or work admission. Both rankings in paired mode use the same weights. No traffic is inferred, estimated or fetched.

This is not a query-mixture sensitivity optimizer, micro-averaged document metric, confidence interval or cross-query relevance budget. All finite-universe, binary-label, floating-point and privacy caveats still apply. Counts are user assumptions. Weight zero does not make an invalid query admissible or remove its work charge.

## Input and output

The exact header is query_id,weight. Every universe query must appear exactly once. A weight is an ASCII decimal integer with at most 18 digits, no sign, whitespace, decimal point or exponent; zero padding is accepted and canonicalized. Weights may be zero, but their sum must be positive. The standard UTF-8/BOM, strict CSV, literal ID and per-file max_rows rules apply. All weight parsing and coverage checks finish before either query solver is called.

The added query_weighted object has:

- total_weight: the exact integer sum as a decimal string.
- weights: lexical query-ID mapping to canonical decimal count strings.
- metrics: lower/upper floating-point endpoints for each metric included by that mode.

Weights and their sum are strings because either can exceed the exact-integer range of common JSON number consumers. No input path is echoed. Opting in reveals the declared query weights in addition to the query IDs and per-query values already present. Omission or query_weights=None leaves prior reports unchanged, byte-for-byte in the validation cases.

For metric m and direction d, let e[q,m,d] be the existing emitted per-query endpoint. The new aggregate computes math.fsum(e[q,m,d] * (w[q] / sum(w)) for q in lexical order). The ordinary macro retains its original arithmetic. Uniform weights are mathematically equal to macro, but rounding and arithmetic order can produce different last bits. This is not rational score arithmetic or certified outward rounding. A very small weight contribution can disappear in the final floating-point result.

## Why independent endpoints suffice

For fixed nonnegative w and independent per-query completion sets C_q, every completion satisfies sum(w_q f_q(c_q)) >= sum(w_q min(f_q)), and the individual minimizing completions can all be chosen together. Thus equality is attainable in real arithmetic. The same argument with maxima gives the upper endpoint. Dividing by the positive sum preserves the ordering. Queries with weight zero impose no objective preference but their declared constraints still have to be feasible. Per-query scopes remain distinct even when document IDs repeat across query IDs.

For paired results, each f_q is already a left-minus-right score evaluated on the same labels within that query. Do not give left and right separate query weights or subtract independently weighted single-run endpoints. Different metrics or directions may still need different hypothetical completions; the report is not a jointly attainable endpoint vector. Existing near-tie and numerical-extremum caveats remain.

## Cost

For Q queries and M included metrics, the new count mapping and disclosed weights add O(Q) memory/output, and aggregation adds O(Q*M) floating-point arithmetic. Scoring_work_units retains the existing solver admission estimate, not a count of all parsing, report construction or aggregate work. Zero-weight queries are fully scored and charged. Per-file max_rows applies to the weight CSV too. These are not OS-enforced time or memory limits.

## Validation

- 135 tests pass on Python 3.9 through 3.15. Nine new tests cover analytic unequal/zero weights; separate unchanged macro; joint complete-labeling oracles for 60 seeded two-query cases in both single and paired RR/AP modes; default and None parity; invalid/duplicate/unknown/missing/all-zero weights before solvers; zero-weight constraint and admission preservation; 18-digit weights and larger exact totals; zero padding and row permutation; CSV/UTF-8/row-cap failures; CLI success and invalid-input no-JSON behavior.
- The independent oracle enumerates joint products of complete labelings and computes literal metrics independently, then directly weighs each attainable combined score. It does not call the production aggregation helper.
- 450 complete reports from isolated base and candidate package imports are byte-identical without weights. They include single, paired-default and paired-RR/AP modes, count ranges, empty runs and examples. Adding weights then removing only query_weighted also preserves each full old report.
- Four behavioral mutants were caught and their failure assertions inspected: ignored weights, wrong normalization, accepted duplicate weights with real solvers, and zero-weight work-admission bypass. The duplicate mutant also causes mocked-solver errors, but those errors are not its evidence; direct real-solver tests show the missing rejection.
- The same-target base lacks the opt-in API and fails that check. This is an additive-feature negative control, not a claim of an old scoring bug.
- A wheel was built, installed into a separate Python 3.9 environment and tested from a neutral directory with no local package import: 135 tests pass. Ruff check and format pass.

The example under examples/weighted has two fully judged queries. Their left precision@1 scores are 1 and 0. With weights 9 and 1, ordinary macro is 0.5 and query-weighted precision is 0.9. The right ranking reverses those scores, so paired macro is 0 and weighted difference is 0.8. These are deterministic examples, not adoption or deployment evidence.
