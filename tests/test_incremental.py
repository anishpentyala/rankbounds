"""Regression probes for incremental extremizer bookkeeping."""

import math
from unittest.mock import patch

import rankbounds.core as core
from test_bounds import Fixture, literal_metrics


class IncrementalTests(Fixture):
    def test_latest_addition_updates_selected_suffix(self):
        self.write(self.j, ("query_id", "document_id", "relevant"), [])
        self.write(self.t, ("query_id", "total_relevant"), [("q", 3)])
        row = self.call(totals=self.t)["queries"][0]
        # Outside d can be the third positive; latest top positives b,c.
        self.assertAlmostEqual(row["metrics"]["ap_total"]["lower"], (1 / 2 + 2 / 3) / 3)

    def test_fixed_positive_suffix_after_unknown(self):
        self.write(
            self.j,
            ("query_id", "document_id", "relevant"),
            [("q", "c", 1), ("q", "d", 0)],
        )
        row = self.call(totals=self.total(2))["queries"][0]
        self.assertAlmostEqual(row["metrics"]["ap_total"]["upper"], (1 + 2 / 3) / 2)
        self.assertAlmostEqual(row["metrics"]["ap_total"]["lower"], (1 / 2 + 2 / 3) / 2)

    def test_fixed_positive_prefix_before_unknown(self):
        self.write(
            self.j,
            ("query_id", "document_id", "relevant"),
            [("q", "a", 1), ("q", "d", 0)],
        )
        row = self.call(totals=self.total(2))["queries"][0]
        self.assertEqual(row["metrics"]["ap_total"]["upper"], 1)
        self.assertAlmostEqual(row["metrics"]["ap_total"]["lower"], (1 + 2 / 3) / 2)

    def test_recurrence_runs_through_infeasible_counts(self):
        self.write(self.j, ("query_id", "document_id", "relevant"), [])
        row = self.call(totals=self.total(4))["queries"][0]
        self.assertEqual(row["metrics"]["precision"], {"lower": 1.0, "upper": 1.0})
        self.assertEqual(row["metrics"]["ap_total"], {"lower": 0.75, "upper": 0.75})

    def test_no_top_hits_reciprocal_zero(self):
        self.write(
            self.j,
            ("query_id", "document_id", "relevant"),
            [("q", d, 0) for d in "abc"],
        )
        row = self.call(totals=self.total(1))["queries"][0]
        self.assertEqual(row["metrics"]["rr"], {"lower": 0.0, "upper": 0.0})

    def test_logarithm_calls_linear_with_examples(self):
        docs = [str(i) for i in range(500)]
        self.write(self.u, ("query_id", "document_id"), [("q", d) for d in docs])
        self.write(
            self.r,
            ("query_id", "document_id", "rank"),
            [("q", d, i) for i, d in enumerate(docs, 1)],
        )
        self.write(self.j, ("query_id", "document_id", "relevant"), [])
        with patch.object(core.math, "log2", wraps=math.log2) as logs:
            row = self.call(k=500, examples=1)["queries"][0]
        self.assertLessEqual(logs.call_count, 26 * 500)
        self.assertEqual(row["metrics"]["precision"], {"lower": 0.0, "upper": 1.0})
        self.assertEqual(row["metrics"]["ap_total"], {"lower": 0.0, "upper": 1.0})

    def test_every_recurrence_state_against_literal_completion(self):
        run = list("abcdefgh")
        labels = {"a": 1, "c": 1, "e": 0, "g": 1}
        unknown = [d for d in run if d not in labels]
        observed = []
        original = core._metric_scores

        def capture(*args):
            scores = original(*args)
            observed.append(scores)
            return scores

        with patch.object(core, "_metric_scores", side_effect=capture):
            core._query(run, labels, 8, 8, None, False)
        self.assertEqual(len(observed), 2 * (len(unknown) + 1))
        for count in range(len(unknown) + 1):
            for offset, selected in enumerate(
                (unknown[-count:] if count else [], unknown[:count])
            ):
                positives = {d for d, v in labels.items() if v} | set(selected)
                expected = literal_metrics(run, positives, 8)
                for metric, score in expected.items():
                    with self.subTest(count=count, offset=offset, metric=metric):
                        self.assertAlmostEqual(
                            observed[2 * count + offset][metric], score, places=12
                        )

    def test_final_scores_bind_to_completion(self):
        row = core._query(
            ["7", "5", "2", "0", "9", "6"], {"0": 1, "1": 0}, 10, 7, None, True
        )
        self.assertEqual(row["metrics"]["ndcg"]["upper"], 1.0)

    def test_near_tied_ap_selection_emits_feasible_not_float_extremum(self):
        run = ["3", "0", "1", "2", "4"]
        labels = {"0": 0, "1": 0, "4": 1}
        row = core._query(run, labels, 5, 6, None, True)
        score = row["metrics"]["ap_total"]["upper"]
        witness = row["endpoint_examples"]["ap_total"]["upper"]
        positives = {"4"} | set(witness["unjudged_top_relevant"])
        self.assertEqual(witness["unjudged_outside_relevant_count"], 0)
        self.assertEqual(len(positives), witness["total_relevant"])
        attained = core._score([int(d in positives) for d in run], len(positives), 6)
        self.assertEqual(score, attained["ap_total"])
        self.assertAlmostEqual(score, 0.7, places=12)
        # These real-number extrema are both 7/10, yet their evaluated floats
        # need not agree. Do not assert exact parity with the full-scan maximum.
        full_scan = max(
            core._score(bits, sum(bits), 6)["ap_total"]
            for bits in (
                [0, 0, 0, 0, 1],
                [1, 0, 0, 0, 1],
                [0, 0, 0, 1, 1],
                [1, 0, 0, 1, 1],
            )
        )
        self.assertAlmostEqual(score, full_scan, places=12)

    def test_legacy_work_admission_unchanged(self):
        # Faster implementation does not silently widen the accepted input set.
        self.assertEqual(self.call()["scoring_work_units"], 21)
        self.call(max_work=21)
        with self.assertRaises(core.BoundsError):
            self.call(max_work=20)
