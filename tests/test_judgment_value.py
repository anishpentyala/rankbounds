"""Independent complete-labeling checks for hypothetical judgment values."""

import io
import itertools
import json
import os
import random
from contextlib import redirect_stderr, redirect_stdout
from unittest.mock import patch

from rankbounds import BoundsError
from rankbounds.__main__ import main
from test_bounds import Fixture, literal_metrics


class JudgmentValueTests(Fixture):
    def setUp(self):
        super().setUp()
        self.c = self.root / "candidates.csv"
        self.write(self.c, ("query_id", "document_id"), [("q", "a"), ("q", "d")])

    def analysis(self, **options):
        return self.call(judgment_candidates=self.c, **options)

    def test_precision_top_and_outside_candidates(self):
        report = self.analysis(k=1)
        top, outside = report["judgment_value"]["candidates"]
        self.assertEqual(
            report["judgment_value"]["scope"], "single_query_interval_width"
        )
        self.assertEqual(top["document_id"], "a")
        self.assertEqual(
            top["metrics"]["precision"],
            {
                "before_width": 1.0,
                "after_width_by_label": {"0": 0.0, "1": 0.0},
                "guaranteed_reduction": 1.0,
                "best_case_reduction": 1.0,
            },
        )
        self.assertEqual(
            outside["metrics"]["precision"],
            {
                "before_width": 1.0,
                "after_width_by_label": {"0": 1.0, "1": 1.0},
                "guaranteed_reduction": 0.0,
                "best_case_reduction": 0.0,
            },
        )
        self.assertNotIn("endpoint_examples", top)

    def test_guaranteed_and_best_case_are_distinct_and_metric_specific(self):
        top, outside = self.analysis()["judgment_value"]["candidates"]
        self.assertEqual(top["metrics"]["recall"]["guaranteed_reduction"], 0.0)
        self.assertAlmostEqual(top["metrics"]["recall"]["best_case_reduction"], 1 / 6)
        self.assertEqual(outside["metrics"]["recall"]["guaranteed_reduction"], 0.25)
        self.assertEqual(outside["metrics"]["recall"]["best_case_reduction"], 0.5)
        self.assertEqual(outside["metrics"]["precision"]["best_case_reduction"], 0.0)
        self.assertEqual(top["metrics"]["rr"]["guaranteed_reduction"], 0.5)

    def test_independent_labeling_oracle(self):
        rng = random.Random(835497)
        for case in range(80):
            universe, runs, known, ranges, candidates, expected = [], [], [], [], [], {}
            k = rng.randint(1, 7)
            for qid in ("a", "b"):
                docs = list("uvwxyz"[: rng.randint(1, 6)])
                run = rng.sample(docs, rng.randint(0, len(docs)))
                labels = {
                    d: rng.randrange(2) for d in docs[1:] if rng.randrange(3) == 0
                }
                unknown = sorted(set(docs) - set(labels))
                positives = {d for d, label in labels.items() if label}
                feasible_total = len(positives) + rng.randrange(len(unknown) + 1)
                lo, hi = (
                    rng.randrange(feasible_total + 1),
                    rng.randint(feasible_total, len(docs)),
                )
                if case % 3 == 0:
                    lo = hi = feasible_total
                completions = []
                for bits in itertools.product((0, 1), repeat=len(unknown)):
                    full = positives | {d for d, bit in zip(unknown, bits) if bit}
                    if lo <= len(full) <= hi:
                        completions.append((full, literal_metrics(run, full, k)))
                expected[qid] = completions
                universe.extend((qid, d) for d in docs)
                runs.extend((qid, d, i) for i, d in enumerate(run, 1))
                known.extend((qid, d, label) for d, label in labels.items())
                ranges.append((qid, lo, hi))
                candidates.extend((qid, d) for d in unknown)
            self.write(self.u, ("query_id", "document_id"), universe)
            self.write(self.r, ("query_id", "document_id", "rank"), runs)
            self.write(self.j, ("query_id", "document_id", "relevant"), known)
            self.write(self.t, ("query_id", "min_relevant", "max_relevant"), ranges)
            self.write(self.c, ("query_id", "document_id"), reversed(candidates))
            report = self.analysis(k=k, total_ranges=self.t)
            self.assertEqual(
                [
                    (r["query_id"], r["document_id"])
                    for r in report["judgment_value"]["candidates"]
                ],
                sorted(candidates),
            )
            for row in report["judgment_value"]["candidates"]:
                completions = expected[row["query_id"]]
                outcomes = {
                    str(label): [
                        scores
                        for full, scores in completions
                        if (row["document_id"] in full) == bool(label)
                    ]
                    for label in (0, 1)
                }
                outcomes = {
                    label: scores for label, scores in outcomes.items() if scores
                }
                self.assertEqual(set(row["outcomes"]), set(outcomes))
                for metric, values in row["metrics"].items():
                    before = [scores[metric] for _, scores in completions]
                    width = max(before) - min(before)
                    remaining = {}
                    for label, possibilities in outcomes.items():
                        scores = [p[metric] for p in possibilities]
                        ends = row["outcomes"][label][metric]
                        self.assertAlmostEqual(ends["lower"], min(scores), places=12)
                        self.assertAlmostEqual(ends["upper"], max(scores), places=12)
                        remaining[label] = max(scores) - min(scores)
                        self.assertAlmostEqual(
                            values["after_width_by_label"][label],
                            remaining[label],
                            places=12,
                        )
                    self.assertAlmostEqual(values["before_width"], width, places=12)
                    self.assertAlmostEqual(
                        values["guaranteed_reduction"],
                        width - max(remaining.values()),
                        places=12,
                    )
                    self.assertAlmostEqual(
                        values["best_case_reduction"],
                        width - min(remaining.values()),
                        places=12,
                    )

    def test_forced_outcomes_are_omitted_not_zero_scored(self):
        for total, allowed in ((1, {"0"}), (4, {"1"})):
            report = self.analysis(totals=self.total(total))
            for row in report["judgment_value"]["candidates"]:
                self.assertEqual(set(row["outcomes"]), allowed)
                for metric in row["metrics"].values():
                    self.assertAlmostEqual(metric["guaranteed_reduction"], 0.0)
                    self.assertAlmostEqual(metric["best_case_reduction"], 0.0)

    def test_default_none_old_reports_and_weights_unchanged(self):
        baseline = self.call(examples=1)
        self.assertEqual(baseline, self.call(examples=1, judgment_candidates=None))
        weights = self.root / "weights.csv"
        self.write(weights, ("query_id", "weight"), [("q", 999)])
        for options in ({}, {"query_weights": weights}):
            old = self.call(examples=1, **options)
            new = self.analysis(examples=1, **options)
            new.pop("judgment_value")
            new["scoring_work_units"] = old["scoring_work_units"]
            self.assertEqual(old, new)

    def test_zero_weight_query_candidates_are_not_skipped(self):
        self.write(
            self.u,
            ("query_id", "document_id"),
            [("q", d) for d in "abcd"] + [("other", "z")],
        )
        weights = self.root / "weights.csv"
        self.write(weights, ("query_id", "weight"), [("q", 0), ("other", 1)])
        before = self.analysis()
        weighted = self.analysis(query_weights=weights)
        self.assertEqual(before["judgment_value"], weighted["judgment_value"])
        self.assertEqual(len(weighted["judgment_value"]["candidates"]), 2)

    def test_conservative_work_admitted_before_solver(self):
        baseline = self.call()["scoring_work_units"]
        required = baseline * 5
        for options in ({}, {"totals": self.total(1)}):
            with patch("rankbounds.core._query") as solver:
                with self.assertRaisesRegex(BoundsError, "work limit"):
                    self.analysis(max_work=required - 1, **options)
                solver.assert_not_called()
            self.assertEqual(
                self.analysis(max_work=required, **options)["scoring_work_units"],
                required,
            )

    def test_work_refusal_with_real_solvers(self):
        required = self.call()["scoring_work_units"] * 5
        with self.assertRaisesRegex(BoundsError, "work limit"):
            self.analysis(max_work=required - 1)
        self.assertEqual(
            self.analysis(max_work=required)["scoring_work_units"], required
        )

    def test_invalid_candidates_fail_before_solver(self):
        rows = [
            [],
            [("q", "b")],
            [("missing", "a")],
            [("q", "no")],
            [("q", "a"), ("q", "a")],
        ]
        for candidates in rows:
            self.write(self.c, ("query_id", "document_id"), candidates)
            with patch("rankbounds.core._query") as solver:
                with self.assertRaises(BoundsError):
                    self.analysis()
                solver.assert_not_called()
        self.write(self.c, ("document_id", "query_id"), [("a", "q")])
        with self.assertRaises(BoundsError):
            self.analysis()
        with self.assertRaises(BoundsError):
            self.call(judgment_candidates=self.root / "missing")

    def test_candidate_limit_and_input_row_limit(self):
        self.write(
            self.u, ("query_id", "document_id"), [("q", str(i)) for i in range(201)]
        )
        self.write(self.r, ("query_id", "document_id", "rank"), [])
        self.write(self.j, ("query_id", "document_id", "relevant"), [])
        self.write(
            self.c, ("query_id", "document_id"), [("q", str(i)) for i in range(201)]
        )
        with patch("rankbounds.core._query") as solver:
            with self.assertRaisesRegex(BoundsError, "at most 200"):
                self.analysis()
            solver.assert_not_called()
        self.write(
            self.u, ("query_id", "document_id"), [("q", str(i)) for i in range(200)]
        )
        self.write(
            self.c, ("query_id", "document_id"), [("q", str(i)) for i in range(200)]
        )
        self.assertEqual(len(self.analysis(k=1)["judgment_value"]["candidates"]), 200)
        self.write(self.u, ("query_id", "document_id"), [("q", "0"), ("q", "1")])
        self.write(
            self.c, ("query_id", "document_id"), [("q", "0"), ("q", "1"), ("q", "0")]
        )
        with self.assertRaisesRegex(BoundsError, "row limit"):
            self.analysis(max_rows=2)

    def test_cli_single_and_invalid_no_json(self):
        args = [
            "--universe",
            str(self.u),
            "--ranking",
            str(self.r),
            "--judgments",
            str(self.j),
            "--k",
            "3",
            "--judgment-candidates",
            str(self.c),
        ]
        with redirect_stdout(io.StringIO()) as output:
            self.assertEqual(main(args), 0)
        self.assertIn("judgment_value", json.loads(output.getvalue()))
        self.write(self.c, ("query_id", "document_id"), [])
        for extra in (["--comparison-ranking", str(self.r)], []):
            with (
                redirect_stdout(io.StringIO()) as output,
                redirect_stderr(io.StringIO()),
            ):
                self.assertEqual(main(args + extra), 2)
            self.assertEqual(output.getvalue(), "")

    def test_candidates_literal_bom_and_row_permutation(self):
        self.write(self.c, ("query_id", "document_id"), [("q", "d"), ("q", "a")])
        before = self.analysis()
        self.c.write_text("\ufeffquery_id,document_id\nq,a\nq,d\n", encoding="utf8")
        self.assertEqual(before, self.analysis())
        self.c.write_bytes(b"query_id,document_id\nq,\xff\n")
        with self.assertRaises(BoundsError):
            self.analysis()
        self.write(self.c, ("query_id", "document_id"), [("q", "A")])
        with self.assertRaises(BoundsError):
            self.analysis()

    def test_special_candidate_file_refused(self):
        if not hasattr(os, "mkfifo"):
            self.skipTest("requires FIFO")
        self.c.unlink()
        os.mkfifo(self.c)
        with self.assertRaisesRegex(BoundsError, "regular file"):
            self.analysis()
