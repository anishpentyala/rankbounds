# Inclusive constraints on total relevant counts

This adds an optional caller-declared count range to the existing finite binary
compatibility calculation. It is not a new metric, relevance estimator or
statistical procedure. Exact totals and unconstrained totals retain their old
input formats and reports.

## Feasibility

Let J be the number of known positives and U the number of unjudged documents
in the entire query universe. With no extra constraint every integer in
[J,J+U] is attainable, because unjudged documents have independent binary labels.
Intersect this with the declared inclusive interval [a,b]. An empty intersection
is contradictory. The loader validates this for every query before scoring.

For a fixed assignment of unknown documents in the top-k set, or the union of
two top-k sets, let C be J plus the newly selected positives, and O the number
of unknown documents outside that set. Intersect [C,C+O] with the effective
query interval. Every integer in this intersection remains feasible. Outside
positive counts for witnesses must subtract C, not the intersected lower bound.
Clamping the denominator must not change how many positives were already chosen.

## Endpoints

For single-run metrics and a fixed count of positive unknown top-k documents,
the previous earliest/latest-position extrema remain valid. Their numerators
are nonnegative. Recall/AP divide by the total relevant count; nDCG divides by
an increasing ideal gain; precision/RR do not depend on outside labels. Thus the
feasible high total suffices for the lower endpoint and the feasible low total
for the upper endpoint, retaining the zero-total convention.

Paired precision, recall and nDCG retain their sorted signed-coefficient solver.
For a fixed selected-positive count, a positive signed numerator moves toward
zero as the denominator increases; a negative numerator moves toward zero from
below. The same sign-aware endpoint choice works after interval intersection.
Precision's denominator is k and does not vary with that interval.

Paired RR enumerates possible first hits in both runs. The forced positive and
negative assignments are feasible precisely when their attainable total interval
intersects the query constraint. Any total in that intersection gives the same
RR difference. Choose its lower endpoint and fill remaining unconstrained union
positives before outside positives when constructing the witness.

Paired AP still enumerates all unknown-union assignments, within its existing
work budget. Each assignment fixes both AP numerators. The difference divides
their signed difference by a common total, so evaluating the feasible low and
high totals suffices. The zero-total convention is retained. Outside subsets
and intermediate totals need not be enumerated.

These statements concern the discrete feasible completions. The implementation
uses ordinary floating-point metric scores, not certified outward-rounded
bounds; the existing near-tie and witness-selection caveats still apply.

## Checks

- The new test suite enumerates every complete binary labeling for 65 seeded
  small universes, checking every inclusive interval within each universe for
  single-run and paired metrics, including opt-in RR and AP. Each admitted
  endpoint is compared with literal metrics on all compatible completions.
- Every emitted example is reconstructed independently, including outside
  positives, to check its total, fixed labels, scores and range membership.
- Singleton ranges are checked for full report equality with exact totals.
  Full-universe ranges are checked against unconstrained reports.
- Invalid integers, ordering, universe bounds, inconsistent labels, duplicate,
  missing and unknown queries, exclusive input modes, CLI no-partial-JSON
  behavior and all-query validation before scoring have explicit tests.
- A separate 500-case legacy-mode probe compares 2,000 full reports between the
  unchanged baseline and this implementation, using no total or an exact total,
  single and paired modes, witnesses and all optional metrics.

No claim is made about whether caller bounds match a real document collection.
Count constraints are independent per query, not a global cross-query budget.
