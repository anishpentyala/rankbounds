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
Single-run audit makes no claim of joint attainability across metrics or
score-difference optimization. The separate paired API below optimizes three
shared-label metric differences.

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

## Shared-label paired differences

Paired precision, recall and binary nDCG have a common denominator for two runs
under the same completed labels: respectively k, total relevance R, or ideal
DCG(min(R,k)). Their difference numerator is a weighted sum of document labels.
A document's coefficient is its left-minus-right inclusion indicator for
precision/recall, or its left-minus-right rank discount for nDCG. A document
present in both runs has ONE label and the difference of its two coefficients.
Known labels contribute a fixed sum. Unknown documents outside both top-k sets
have zero coefficient but can change R. AP's numerator is not linear in labels;
this method makes no paired AP claim. RR is also excluded from this API.

Let t be the number of unknown positive labels in the union of the top-k sets.
At fixed t, sum the t smallest coefficients to minimize the numerator, or the
t largest to maximize it. An exchange from a larger selected coefficient to a
smaller unselected one cannot increase the sum. R ranges from known positives
plus t through that count plus unknown documents outside the union, intersected
with any exact total. An empty intersection is skipped. Unlike single-run
nonnegative scores, this numerator is SIGNED: for the lower endpoint, choose
small R for a negative numerator and large R for a positive numerator; reverse
those choices for the upper endpoint. Zero denominators imply zero total
relevance and explicitly yield zero scores. Precision ignores R.

Scan every feasible t for each metric/direction, retain the best candidate,
then re-score each selected labeling on BOTH runs with the existing score
function. Outside unknown positives need only a count because neither run
retrieves them above cutoff. This supplies actual shared-label witnesses.
Independent queries can attain their endpoints independently, so equal-weight
averages give per-metric macro extrema. Floating-point qualifications from
FORMAT.md still apply; this is not a certified numeric optimizer.

For one query, coefficient construction costs O(L+T), sorting O(M log M),
normalizer precomputation O(min(k,C)), and candidate scanning O(M). A fixed six
endpoint rescoring operations add O(L+T+min(k,C)). Transient storage is linear
in those sizes, plus stored inputs, known labels and requested witnesses.
These are algorithmic bounds, not demonstrated speedups or hard memory limits.
