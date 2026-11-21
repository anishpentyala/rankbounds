# Paired reciprocal-rank mask implementation

This is a performance change to the existing `include_rr=True` solver, not a
new retrieval metric or a new bound. Parsing, validation, admission units,
accepted inputs, CLI behavior, output schema and disclosure rules are unchanged.

## Representation and equivalence

Map the sorted union of the two clipped top-k runs to dense bit positions.
Build each run's prefix masks once. A candidate first-hit pair forms the same
required-zero and required-one sets as the prior solver, using bitwise OR.
Known positives and negatives reject precisely the same conflicts. Unknown
required-one bits contribute to the minimum positive count; remaining eligible
unknown bits and the outside-unknown count determine the maximum. Count-range
intersection and candidate scores use the previous arithmetic and scan order.

Keep only the winning masks and scores while scanning. Expand the two final
witnesses in sorted document order. Free union documents are made positive
before any outside count, exactly as before. Comparisons remain strict, so
first-encountered ties keep the same witness. No score formula changes or
floating-point recurrence is introduced.

Python 3.10+ uses `int.bit_count`; Python 3.9 uses `bin(mask).count('1')`. Both
paths are tested, including masks spanning multiple machine words. Dense indices
cover only the clipped union, never the whole declared universe.

## Cost and memory tradeoff

There are still `(L+1)*(R+1)` candidate pairs. Integer mask operations and
population counts depend on mask bit length; they are not constant-time for
arbitrary U, the union size. The main scan avoids repeatedly hashing document
IDs and building Python prefix/eligible sets. At most two witness expansions
cost O(U) identifier visits after selection.

Prefix masks and the per-document bit table can retain O((L+R+U)*U) bits in the
worst case, plus Python-object/input overhead. This is a time-for-memory
tradeoff, not a linear-memory claim or a hard resource guarantee. The previous
cubic-shaped admission estimate is retained as a compatibility guard. The
change does not silently admit larger workloads; explicitly raised work limits
still require care. A large universe outside the clipped union does not make
mask indices larger, although the ordinary input storage remains proportional
to that universe.

## Local synthetic timings

Python 3.10.12, one process, same generated inputs, median of five solver calls,
endpoint examples enabled. These exclude CSV parsing, other metrics and import
cost; they are not portable speed promises. The complete old/new solver result,
including witnesses, was equal before timing each case.

| Documents per run | Shape | Prior median | Mask median |
| --- | --- | --- | --- |
| 10 | Disjoint, all unknown | 0.522 ms | 0.120 ms |
| 50 | Disjoint, all unknown | 76.3 ms | 2.30 ms |
| 100 | Disjoint, all unknown | 975 ms | 9.08 ms |
| 100 | Same documents, reversed order | 201 ms | 5.02 ms |
| 100 | Disjoint, known first hits | 26.6 ms | 1.06 ms |
| 200 | Disjoint, all unknown | 13.7 s | 38.6 ms |

The 100-document cases fit the default work cap when called through paired
mode. The 200-document case needs an explicitly raised cap; it does not become
newly admissible. Small runs, different label patterns, Python versions and
machines can have different overheads and ratios.

## Validation

- Existing 112 tests retained; five new methods bring the suite to 117.
- New independent complete-label oracle: 350 seeded small universes, each with
  unconstrained, exact and inclusive-range counts. Endpoints and shared witness
  feasibility checked; existing larger RR oracle retained.
- A separate baseline comparison checks 6,000 complete solver results,
  including exact lexical witnesses and tie order.
- Multiword masks, known labels outside both runs, million-document universe
  counts with a small clipped union, fallback/native popcounts and absent
  examples are covered.
- Deterministic hash-count regression: the old implementation makes 27,340
  identifier hash calls in the selected 20+20 disjoint fixture and fails the
  1,200-call ceiling. The new implementation passes. This detects the targeted
  repeated set work without a noisy timing threshold.
- Five compiling negative controls trigger behavioral assertions: lost known
  positive prefix constraint, omitted outside known positives, forbidden
  eligible labels, wrong first hit and incorrect outside witness count.

These synthetic checks do not establish real labels, benchmark completeness,
adoption, statistical significance or exhaustive correctness.
