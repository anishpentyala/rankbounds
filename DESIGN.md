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
maximum. Ties keep the first encountered t. This enumeration also permits exact
totals that force positives into top-k or outside it. For multiple queries,
constraints are independent and macro is linear, so averaging per-query minima
and maxima yields attainable macro endpoints *for each individual metric*.
No claim of joint attainability across metrics or score-difference optimization.

## Cost

For query q scoring costs O((M+1)*(L+min(k,C))) time, O(L+min(k,C)) transient
space plus report examples, and stored input dictionaries/sets O(total input
rows and identifier bytes). The implementation does not enumerate outside
assignments or iterate all possible corpus-positive totals. This remains
quadratic in an unjudged top-k length. The work admission cap is there to reject
such expensive requests, not disguise the cost as linear. Default output has
no document-ID examples but always contains query IDs. Example output can store
up to ten lists of length L per selected query.

## Numerical limits

Score terms use Python doubles and `math.fsum`. Discrete extremizer selection
is exact mathematically, but close floating-point candidates can tie or differ
by roundoff. The output is not an interval-arithmetic certificate. Independent
exhaustive tests compare within 12 decimal places. No epsilon-based system
ranking, confidence interpretation or decision threshold is provided.
