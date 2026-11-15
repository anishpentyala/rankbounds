# Private paired-mode validation

This file records local evidence, not hosted CI or external use.

- Existing 68 tests remain unchanged and pass after extracting the same strict
  ranking/input readers for reuse. Single-run report/schema and five metric
  conventions are unchanged.
- Thirteen new test methods include 300 seeded small-universe fixtures. Each
  fixture is checked both without a total and with an attainable exact total.
  An independent complete-label enumeration computes all three paired extrema;
  every emitted endpoint witness is replayed on both rankings under one shared
  completed labeling. Comparisons use 12 decimal places, not bitwise identity.
- Direct controls cover identical rankings with wide separate intervals, sign-
  dependent denominator selection, swapped run symmetry, zero/large totals,
  empty/short runs and very large k without a k-sized allocation, missing query
  runs in the macro average, lexical example limits, exact work-cap boundaries,
  late invalid right-run rows below cutoff, malformed UTF-8/CSV/NUL, missing
  files, invalid option types, contradictory totals and CLI no-JSON failure.
- All 81 test methods pass on actual Python 3.9, 3.10, 3.11, 3.13 and 3.14.
- 160 complete single-run reports match the unchanged released source in
  separate processes, including exact JSON values, endpoint examples, totals,
  work admission counts and schema. This is sampled parity, not a proof for
  all possible inputs.
- Four deliberate mutants are caught by assertion failures with no test setup
  errors: wrong signed denominator choice, overwrite rather than subtract a
  shared document coefficient, ignore exact totals, and skip right-run validation.
  The restored source passes all 81 tests.
- Ruff 0.15.0 check/format and wheel/sdist builds pass. Fresh neutral installed
  wheel tests and byte comparisons are recorded in the review packet.
- No hosted checks or public completion are claimed by this private document.

No statistical significance, outward-rounding, external adoption or performance
claim is made. The source's public references concern established metric
conventions; this addition's coefficient argument is in DESIGN.md.
