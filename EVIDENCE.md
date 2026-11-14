# Sources and scope, checked 2026-11-14

This tool implements an explicit finite-binary completion problem. It does not
claim a new research metric, a new missing-judgment method, or that worst-case
intervals are preferable to established estimators for every study.

The following sources were fetched and their relevant definitions/method
descriptions inspected while choosing the scope. Quotes below are limited to
short method/definition excerpts; production code is original.

1. [ir-measures measure reference](https://ir-measur.es/en/latest/measures.html).
   Its AP `judged_only` parameter says "ignore returned documents that do not
   have relevance judgments". It also distinguishes recall from Success@k and
   documents nDCG discount/gain options. We keep original ranks and explicitly
   document our particular binary/log2/total-AP conventions instead of claiming
   all-library parity.
2. [ranx metrics](https://amenra.github.io/ranx/metrics/).
   Recall is the ratio of retrieved relevant documents to total relevant
   documents. It describes bpref as "designed for situations where relevance
   judgments are known to be incomplete." Use that established evaluator when
   it answers your question; rankbounds is not a new bpref implementation.
3. [NIST trec_eval infAP implementation](https://github.com/usnistgov/trec_eval/blob/main/m_infap.c).
   The measure's comment says "Assume a judgment pool with a random subset that
   has been judged." That estimator's sampling assumptions differ from our
   adversarial compatibility problem with no probabilities.
4. [Froebe et al., Bootstrapped nDCG Estimation in the Presence of Unjudged Documents (2023)](https://downloads.webis.de/publications/papers/froebe_2023a.pdf).
   The abstract contrasts condensed lists, naive bounds and bootstrapping;
   naive bounds are described as often very "loose". We accept wide intervals
   rather than predict likely relevance. This paper is context, not evidence
   that our implementation reproduces its experimental results.
5. [Sakai and Kando, On information retrieval metrics designed for evaluation with incomplete relevance assessments (2008)](https://link.springer.com/article/10.1007/s10791-008-9059-7).
   The authors evaluate condensed metrics and report favorable robustness in
   their studied collections. This is a reason **not** to claim our fixed-rank
   sensitivity audit replaces condensed metrics or settles incomplete-judgment
   evaluation generally. Different questions and assumptions remain useful.
6. [Aslam, Pavlu and Yilmaz, A Sampling Technique for Efficiently Estimating Measures of Query Retrieval Performance Using Incomplete Judgments (2005)](https://www.ccs.neu.edu/home/jaa/papers/AslamPaYi05.pdf).
   The paper notes that unretrieved relevant documents' precisions are zero,
   with the retrieved precision sum "divided by R". It proposes random-sampling
   estimators. We use the total-relevant denominator, but do not implement its
   estimator, claim unbiased estimation, or borrow its empirical accuracy.

Worst-case bounds do not discover the real label distribution, fix biased
judgments, model dependence, determine statistical significance, or establish
which ranker is better. Finite pool bounds only describe the declared pool.
