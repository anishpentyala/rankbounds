# Bit-tagged paired AP scoring

This is an implementation follow-up to cardinality pruning, not a new metric. Its base is `fe7328e6a489c348a53cab217ec2178010263834`.

## What changes

Cardinality pruning avoids impossible subsets. For every remaining subset, the prior implementation still constructs a string set, unions it with known positives twice, and hashes each ranked document while calculating two AP numerators. This version precomputes integer tags for each ranked position. The subset keeps the exact same lexical bit numbering. One additional always-on bit represents known positives; judged negatives have tag zero. Numerator scoring then uses integer intersection instead of string-set membership.

Total relevant counts use the subset popcount. Python 3.10+ uses the native integer operation; Python 3.9 uses the same binary-string count convention as the existing RR solver. The string list for an endpoint example is constructed only when that endpoint changes, never for examples=0. No new dependency or cache is introduced.

The exact ascending subset order, denominator endpoint order, hit counts, rank division order, `math.fsum` term order, strict endpoint comparisons, lexical witnesses and work-admission charge are unchanged. Known positives outside either ranking affect the denominator but never become ranked hits. Extra memory is O(L+R+U) tag/index references with up to U+1 bits per integer tag, conservatively O((L+R+U)*(U+1)) bits plus Python object overhead. This is not an unbounded label cache. Exponential enumeration remains exponential. This does not admit any previously refused input.

## Compatibility evidence

- All 126 tests pass on Python 3.9 through 3.15. Five new targeted tests cover exhaustive rank-tag numerator parity, known positive/negative separation, known outside positives, no unknowns, first-mask witness ties, and broad-range string-hash work.
- Existing independent full-label AP oracles remain in the suite, including 260 seeded cardinality-range cases, complete outside-label enumeration, witness reconstruction, and budget refusal cases.
- Same-process differential: 4,500 complete helper results exactly match the base, including all scores and witness tie choices. Another 360 full public compare JSON reports are byte-identical, including RR/AP combinations, effective total ranges, work units, macro fields and examples.
- A broad-range 12-unknown case does 122,904 counted string hashes on the base and 84 on the candidate, examples disabled. The same regression test fails on the base and passes on the candidate. This is a work proxy, not a claim about every Python implementation or workload.
- Five behavioral mutants caught: inverted mask test, missing always-positive tag, incorrect total count, judged negatives treated as positive, and reversed witness labels. Inspected evidence includes wrong literal scores, lost fixed-positive scores, nonlexical witnesses, and incorrect-count failures. The incorrect-count mutant also triggers downstream exceptions, so its process exit alone is not the evidence.

## Local timings and tradeoff

Three runs per point, median, Python 3.10 on this machine. Both rankings contain the same unknown union in opposite order; examples enabled. These are illustrative local measurements, not throughput promises or universal speedups.

| Unknown union | Total constraint | Base seconds | Candidate seconds | Base/candidate |
| --- | --- | --- | --- | --- |
| 8 | none | 0.000746 | 0.000570 | 1.31x |
| 14 | none | 0.065190 | 0.047186 | 1.38x |
| 16 | none | 0.288701 | 0.201219 | 1.43x |
| 14 | exact 7 | 0.018672 | 0.014667 | 1.27x |
| 16 | exact 8 | 0.073751 | 0.057576 | 1.28x |
| 14 | range 1..13 | 0.067207 | 0.049476 | 1.36x |
| 16 | range 1..15 | 0.291750 | 0.208361 | 1.40x |
| 14 | exact 0 | 0.000011 | 0.000016 | 0.74x |
| 14 | exact 14 | 0.000012 | 0.000016 | 0.80x |

Tag setup adds roughly a few microseconds to cases that cardinality pruning already reduces to one subset. Very small unions and restrictive totals may not benefit. The purpose is reducing the remaining exponential hot-path work, not improving those near-empty searches. No input caps or resource guarantees change.
