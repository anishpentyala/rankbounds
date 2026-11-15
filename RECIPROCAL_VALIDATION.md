# Opt-in paired reciprocal rank: proof and validation

## Model and proof

This extends the shared-label paired mode, not the finite universe, binary label,
ranking, exact-total or zero-relevant conventions. RR at cutoff k is 1 divided
by the first relevant rank, or zero if no returned document is relevant by k.
The endpoint is a difference of two RRs under one completed labeling.

For each run of clipped length L, enumerate indices 0 through L. Index L means
no relevant document; an earlier index means that document is the first hit.
For a candidate pair of indices, every preceding document in either run must be
nonrelevant, and the selected hit documents must be relevant. Reject a pair if
a required-zero document is also required-one or known relevant, or if a
required-one document is known nonrelevant. This covers documents shared at
different ranks, including the case in which both first hits are the same ID.

The remaining unknown documents are unconstrained for RR: changing a label
after both relevant prefixes cannot change either first hit. Let B be the
number of known relevant documents plus required-one unknowns. Let F be the
number of unknowns not forced zero or one, including those outside both runs.
A supplied exact total T is feasible iff B <= T <= B+F. Without a total, B
itself is feasible. Assign enough free unknowns positive to realize T (or B),
keeping all known labels fixed. The emitted witness uses lexical free union
IDs first and an outside count for the rest; it never reveals outside IDs.

Every feasible complete labeling has a first-hit index pair considered by the
solver. Every admitted pair has a complete labeling constructed as above.
Thus minimizing/maximizing the difference over admitted pairs gives attainable
RR-difference extrema in this discrete model. Arithmetic uses ordinary Python
floating-point reciprocals and subtraction, not certified outward rounding.
The pre-existing precision/recall/nDCG solver is unchanged.

## Work and compatibility

RR is opt-in through actual boolean `include_rr=True` or CLI `--paired-rr` with
`--comparison-ranking`. No new work is done by default. For clipped lengths
L/R, the added admission estimate is `(L+1)*(R+1)*(L+R+1)` per query. This bounds
the shape of explicit pair enumeration and set/list processing conservatively;
it is not a literal CPU count, time guarantee or RAM limit. Long rankings can
be rejected before scoring, including fully judged rankings. All queries'
combined work is checked before scoring any query. Parsing still happens first.

Default full reports, including scoring-work units and endpoint witnesses,
matched 200 seeded complete public-API reports from the unchanged released
0.2.0 source in separate processes exactly. The only new report fields are `rr`
metric entries when opted in; the version changes to 0.2.1. No paired AP,
confidence intervals, significance test, quality threshold or winner decision.

## Actual local checks

- 92 unittest methods: the 81 existing methods retained, plus 11 new methods.
  All passed on Python 3.9, 3.10, 3.11, 3.13, 3.14 and 3.15.
- New seeded oracle method tests 1,000 cases, each with unconstrained and exact
  totals. It enumerates every unknown binary label, computes literal RR for
  both runs, checks both endpoints and reconstructs the shared witnesses.
- Separate exhaustive script: all 256 pairs of partial rankings over a/b/c,
  all 81 ternary known-zero/known-one/unknown label states over a/b/c/d, and all
  feasible totals plus no-total. All 69,120 trials and 138,240 endpoint-witness
  checks passed. Document d is outside both runs, testing total completion.
- Tests cover conflicting shared first hits, known-zero candidates, known-one
  prefixes, identical/empty/short runs, huge k clipped to actual run lengths,
  exact zero/full totals, outside completions, swap symmetry, macro inclusion,
  no identifier disclosure without examples, strict opt-in type validation,
  CLI wrong-mode fail-closed behavior, exact work boundary and pre-score guard.
- Four deliberate mutations were caught by assertion failures with zero test
  errors: ignore shared-label conflicts (655 failures), ignore known negatives
  (409), ignore total feasibility (654), and use 1/(rank+1) (2,963). Restored
  source passed. These are targeted negative controls, not a coverage claim.
- Ruff 0.15.0 check and format check passed. Wheel and source-distribution checks
  are recorded in the private release packet, not an assertion of publication.

All fixtures are synthetic. These tests do not establish completeness of a
real document universe, correctness of real relevance labels, outside adoption,
statistical validity or performance on arbitrary workloads.
