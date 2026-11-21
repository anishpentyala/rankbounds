# Pruning impossible paired-AP label counts

This is a performance change to the existing opt-in paired AP solver. It does
not change AP's total-relevant denominator, report layout, score arithmetic,
shared-label constraints, witness tie order, input validation or work admission.
It does not make the exponential worst case polynomial.

## Feasible cardinalities

Let K be the number of known-positive documents in the whole query universe,
U the number of unjudged documents in the two clipped rankings' union, and O
the number of unjudged documents outside that union. A subset with c positive
union labels can realize every integer total from K+c through K+c+O. The
existing total-count constraint, after intersection with known labels, is an
inclusive interval [Tlow, Thigh]. Their intersection is nonempty exactly when

```
max(0, Tlow - K - O) <= c <= min(U, Thigh - K).
```

Previously, the solver built all `2**U` subsets before rejecting impossible
counts. Now it traverses the binary decision tree and prunes a branch when the
remaining bits cannot meet this inclusive cardinality interval. It visits the
highest remaining bit unset before set, preserving ascending numeric-mask order
from the prior `range(1 << U)` loop. If all remaining cardinalities are allowed,
it yields that contiguous mask interval directly. The unconstrained whole range
uses the original `range` path without recursive traversal.

For each yielded mask the original feasibility check, numerator evaluator,
denominator endpoints, strict endpoint comparisons and witness construction
remain in place. Therefore the same candidates are evaluated in the same order,
with the same arithmetic. First-encountered tie witnesses are preserved. Known
positives outside both runs and freely assignable outside documents still
constrain total relevance; neither is discarded.

## Cost and limits

Only feasible-cardinality masks need label-set construction and scoring. The
generator keeps O(U) recursive frames rather than a list of feasible subsets.
Each retained prefix integer can occupy O(U) bits, so this is not a claim of
O(U) total bit storage. Per-yield recursion and generator overhead can still cost time; broad
but nontrivial intervals can be slightly slower than the old full scan. The
worst case still enumerates all `2**U` labelings. Integer/rational count logic is
exact; AP scores still use ordinary Python floating point, not certified
outward-rounded bounds.

The pre-existing conservative exponential admission charge is unchanged, even
when only one assignment can satisfy the declared count. This preserves which
inputs are admitted and still checks the whole audit before any scoring. No
larger workload is silently admitted, sampled or partially evaluated. The
admitted union width is bounded by that existing charge; this is not a general
unbounded-width generator API or a hard runtime/RAM guarantee.

## Local timings

Python 3.10.12, same process, median of five solver calls with endpoint examples
on. The two runs contain the same 14 unjudged documents in reverse order, no
outside documents or known labels. Full old/new solver results were compared
before timing. This fixture fits the unchanged default paired work cap.

| Total constraint | Prior median | Pruned median |
| --- | --- | --- |
| None | 66.5 ms | 66.8 ms |
| Exactly 0 | 19.2 ms | 0.0130 ms |
| Exactly 1 | 19.2 ms | 0.0887 ms |
| Exactly 7 | 30.1 ms | 18.9 ms |
| Inclusive 1..13 | 66.8 ms | 69.5 ms |
| Exactly 13 | 19.3 ms | 0.116 ms |
| Exactly 14 | 19.3 ms | 0.0131 ms |

These are synthetic solver-only measurements, excluding CSV parsing, other
metrics and import time. They are not portable or end-to-end speed promises.
The broad 1..13 range regresses about 4% locally; the intended gain is for
informative count constraints. Different versions, shapes and machines can
change both gains and overheads.

## Validation

- All 117 existing tests retained. Four new methods bring the suite to 121.
- Exhaustive generator check for every inclusive cardinality interval at widths
  0 through 9: exact mask membership and ascending order. Extreme-count width28
  cases check pruning without iterating the full power set.
- Independent full-label/outside-count oracle for 260 seeded universes, each
  with unconstrained, exact and inclusive-range counts. Endpoint differences
  and witness feasibility checked.
- 4,500 complete helper results compared exactly to the prior solver, including
  witness dictionaries and tie order; 360 full public compare reports checked
  byte-identical with default/AP/AP+RR combinations, macro averaging, examples,
  empty runs, ranges and admission units.
- Deterministic same-target hash-count regression: the prior zero-total solver
  makes 114,744 identifier hash calls in a 14-document fixture and fails the
  500-call ceiling; the new solver passes. No timing assertion is used.
- Five targeted mutations are caught by inspected assertion failures: omit
  outside capacity, subtract outside capacity from the upper count, lose an
  inclusive boundary, use the wrong bit position, and scan every subset again.

These tests are synthetic. They do not establish real labels, inventory
completeness, statistical significance, adoption or exhaustive correctness.
