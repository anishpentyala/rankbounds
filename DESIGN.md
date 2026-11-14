# Extremizers

For one query, let A be the known-relevant count in the entire declared
universe, M the unjudged count in the returned top-k, and O the unjudged count
outside that top-k. Fix t, the number of the M unknown top-k labels that become
positive. Then total relevance R ranges from A+t through A+t+O, intersected
with an optional exact total. An empty intersection is infeasible.

At a fixed t, choose the earliest t unjudged ranks for the largest numerator and
the latest t for the smallest. Moving an unknown positive earlier across an
unknown negative leaves hits unchanged, improves or preserves first-relevant
rank and DCG, and improves AP's numerator: its own precision term improves and
any intervening fixed positives see one more earlier positive. Other fixed
positives' contributions do not worsen. Repeated exchanges establish earliest
and latest extremizers without enumerating 2**M assignments.

At fixed t, the numerator does not depend on unknown outside labels. Recall/AP
have denominator R; nDCG has the monotone ideal DCG for min(R,k) positives.
Thus use the smallest feasible R for upper candidates and the largest for lower
candidates. Precision and RR ignore outside labels, so these choices also
provide compatible examples for them. The R=0 case has explicit all-zero scores.

Enumerate t=0..M, score both extremizers, and retain each metric's minimum and
maximum. Equal floating-point candidate values keep the first encountered t. This enumeration also permits exact
totals that force positives into top-k or outside it. For multiple queries,
constraints are independent and macro is linear, so averaging per-query minima
and maxima yields attainable macro endpoints *for each individual metric*.
No claim of joint attainability across metrics or score-difference optimization.

## Incremental scoring

Build a prefix count of fixed positives and a suffix sum of their reciprocal
ranks. Adding an unknown positive at rank r contributes its own precision
`(fixed_before + selected_before + 1)/r` to the AP numerator. It also adds
`sum(1/j)` for fixed and already selected positives after r. Earliest-first
additions have all previously selected positives before r; latest-first
additions have them all after. A compensated running sum maintains that latter
suffix. DCG adds one discount term and first-hit rank updates by minimum.
Ideal DCG is precomputed once as a compensated prefix over discount terms.

The candidate scan compares scores from these incremental states. After it
chooses endpoints, it re-scores at most ten selected completions using the
original `math.fsum` evaluator. Identical selected completions share this final
calculation. Examples are constructed only after selection, not every time an
endpoint improves. Reported scores are thus tied to actual finite completions,
not the incremental sums alone.

## Cost and compatibility

Scoring is O(L + min(k,C) + M) time, with a fixed at-most-ten rescoring factor,
and O(L + min(k,C)) transient space plus input/report storage. L is the
returned length clipped at k, M its unknown count, and C the universe size.
No quadratic bit-vector rebuild, full score scan or repeated ideal summation
occurs for every t. Stored input dictionaries/sets remain proportional to rows
and identifier bytes. This is not a hard memory or runtime bound.

The v1 `scoring_work_units` formula, `max_work` acceptance set, JSON schema,
input validation and metric conventions are deliberately unchanged. Its
quadratic estimate is now a conservative compatibility admission rule rather
than a model of current operation count. Faster scoring does not silently
accept larger workloads. Users can explicitly raise the existing cap within
its supported range. No new option or file format is introduced.

The optimization can be slower when almost everything is judged: precomputing
recurrence state has overhead without many candidate counts to amortize it.
Local synthetic timings do not promise any portable speedup.

## Numerical limits

Candidate score terms use Python doubles and compensated running sums; final
selected completions use the original `math.fsum` evaluator. Discrete extremizer selection
is exact mathematically, but close floating-point candidates can tie or differ
by roundoff. Near-tied candidate selection can shift emitted endpoints by floating-point
roundoff relative to the prior full-scan evaluator, not only select a different
witness. Final rescoring binds each emitted endpoint to a feasible completion's
score, but does not guarantee the exact extremum of all floating-point scores,
exact numeric baseline parity, or outward rounding. Small sampled differences
do not establish a universal bound or direction of drift.
No epsilon-based system
ranking, confidence interpretation or decision threshold is provided.
