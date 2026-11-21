"""Complete-labeling oracles for paired judgment-candidate sensitivity."""

import io
import itertools
import json
import random
from contextlib import redirect_stderr, redirect_stdout
from unittest.mock import patch

from rankbounds import BoundsError, compare
from rankbounds.__main__ import main
from test_bounds import Fixture, literal_metrics


class PairedJudgmentValueTests(Fixture):
    def setUp(self):
        super().setUp()
        self.right = self.root / "right.csv"
        self.c = self.root / "candidates.csv"
        self.ranking(self.right, {"q": list("cba")})
        self.write(self.c, ("query_id", "document_id"), [("q", "a"), ("q", "d")])

    def ranking(self, path, runs):
        self.write(
            path,
            ("query_id", "document_id", "rank"),
            [(q, d, i) for q, run in runs.items() for i, d in enumerate(run, 1)],
        )

    def paired(self, **options):
        return compare(
            self.u, self.r, self.right, self.j, k=options.pop("k", 3), **options
        )

    def analysis(self, **options):
        return self.paired(judgment_candidates=self.c, **options)

    def test_identical_runs_have_no_width_despite_wide_single_intervals(self):
        self.ranking(self.right, {"q": list("abc")})
        report = self.analysis(include_rr=True, include_ap=True, examples=1)
        self.assertEqual(
            report["judgment_value"]["scope"],
            "single_query_paired_difference_interval_width",
        )
        for row in report["judgment_value"]["candidates"]:
            for metric in row["metrics"].values():
                self.assertEqual(metric["before_width"], 0)
                self.assertEqual(metric["after_width_by_label"], {"0": 0, "1": 0})
                self.assertEqual(metric["guaranteed_reduction"], 0)
                self.assertEqual(metric["best_case_reduction"], 0)
            self.assertNotIn("endpoint_examples", row)

    def test_disjoint_top_one_is_paired_difference_not_separate_scores(self):
        self.ranking(self.right, {"q": ["c"]})
        report = self.analysis(k=1)
        top, outside = report["judgment_value"]["candidates"]
        values = top["metrics"]["precision"]
        self.assertEqual(values["before_width"], 2)
        self.assertEqual(values["after_width_by_label"], {"0": 1, "1": 1})
        self.assertEqual(values["guaranteed_reduction"], 1)
        self.assertEqual(top["outcomes"]["0"]["precision"], {"lower": -1, "upper": 0})
        self.assertEqual(top["outcomes"]["1"]["precision"], {"lower": 0, "upper": 1})
        self.assertEqual(outside["metrics"]["precision"]["guaranteed_reduction"], 0)

    def test_independent_shared_completion_oracle(self):
        rng = random.Random(329711)
        for case in range(100):
            inventory, left_rows, right_rows, labels_rows, ranges, candidates = (
                [],
                [],
                [],
                [],
                [],
                [],
            )
            expected = {}
            k = rng.randint(1, 8)
            for qid in ("a", "b"):
                docs = list("uvwxyz"[: rng.randint(1, 6)])
                left, right = [
                    rng.sample(docs, rng.randint(0, len(docs))) for _ in range(2)
                ]
                labels = {
                    d: rng.randrange(2) for d in docs[1:] if rng.randrange(3) == 0
                }
                unknown = sorted(set(docs) - set(labels))
                known = {d for d, v in labels.items() if v}
                total = len(known) + rng.randrange(len(unknown) + 1)
                low, high = rng.randrange(total + 1), rng.randint(total, len(docs))
                if case % 3 == 0:
                    low = high = total
                completions = []
                for bits in itertools.product((0, 1), repeat=len(unknown)):
                    positives = known | {d for d, bit in zip(unknown, bits) if bit}
                    if not low <= len(positives) <= high:
                        continue
                    a, b = [literal_metrics(run, positives, k) for run in (left, right)]
                    completions.append((positives, {m: a[m] - b[m] for m in a}))
                expected[qid] = completions
                inventory.extend((qid, d) for d in docs)
                left_rows.extend((qid, d, i) for i, d in enumerate(left, 1))
                right_rows.extend((qid, d, i) for i, d in enumerate(right, 1))
                labels_rows.extend((qid, d, v) for d, v in labels.items())
                ranges.append((qid, low, high))
                candidates.extend((qid, d) for d in unknown)
            self.write(self.u, ("query_id", "document_id"), inventory)
            self.write(self.r, ("query_id", "document_id", "rank"), left_rows)
            self.write(self.right, ("query_id", "document_id", "rank"), right_rows)
            self.write(self.j, ("query_id", "document_id", "relevant"), labels_rows)
            self.write(self.t, ("query_id", "min_relevant", "max_relevant"), ranges)
            self.write(self.c, ("query_id", "document_id"), reversed(candidates))
            report = self.analysis(
                k=k, total_ranges=self.t, include_rr=True, include_ap=True
            )
            rows = report["judgment_value"]["candidates"]
            self.assertEqual(
                [(r["query_id"], r["document_id"]) for r in rows], sorted(candidates)
            )
            for row in rows:
                completions = expected[row["query_id"]]
                subsets = {
                    str(label): [
                        scores
                        for pos, scores in completions
                        if (row["document_id"] in pos) == bool(label)
                    ]
                    for label in (0, 1)
                }
                subsets = {label: scores for label, scores in subsets.items() if scores}
                self.assertEqual(set(row["outcomes"]), set(subsets))
                for metric, values in row["metrics"].items():
                    before = [s[metric] for _, s in completions]
                    width = max(before) - min(before)
                    remaining = {}
                    for label, possibilities in subsets.items():
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

    def test_enabled_metric_combinations_default_and_report_parity(self):
        for rr, ap in itertools.product((False, True), repeat=2):
            options = {"include_rr": rr, "include_ap": ap, "examples": 1}
            baseline = self.paired(**options)
            self.assertEqual(baseline, self.paired(judgment_candidates=None, **options))
            result = self.analysis(**options)
            rows = result.pop("judgment_value")["candidates"]
            result["scoring_work_units"] = baseline["scoring_work_units"]
            self.assertEqual(result, baseline)
            metrics = (
                {"precision", "recall", "ndcg"}
                | ({"rr"} if rr else set())
                | ({"ap_total"} if ap else set())
            )
            for row in rows:
                self.assertEqual(set(row["metrics"]), metrics)
                for ends in row["outcomes"].values():
                    self.assertEqual(set(ends), metrics)

    def test_total_forced_outcomes_omitted_not_zero_scored(self):
        for total, expected in ((1, {"0"}), (4, {"1"})):
            report = self.analysis(
                totals=self.total(total), include_rr=True, include_ap=True
            )
            for row in report["judgment_value"]["candidates"]:
                self.assertEqual(set(row["outcomes"]), expected)
                for metric in row["metrics"].values():
                    self.assertAlmostEqual(metric["guaranteed_reduction"], 0)
                    self.assertAlmostEqual(metric["best_case_reduction"], 0)

    def test_work_includes_each_enabled_solver_before_any_scoring(self):
        for rr, ap in itertools.product((False, True), repeat=2):
            options = {"include_rr": rr, "include_ap": ap}
            required = self.paired(**options)["scoring_work_units"] * 5
            for constrained in ({}, {"totals": self.total(1)}):
                with patch("rankbounds.paired._paired_query") as solver:
                    with self.assertRaisesRegex(BoundsError, "work limit"):
                        self.analysis(max_work=required - 1, **options, **constrained)
                    solver.assert_not_called()
                self.assertEqual(
                    self.analysis(max_work=required, **options, **constrained)[
                        "scoring_work_units"
                    ],
                    required,
                )

    def test_real_solver_work_refusal_all_metric_modes(self):
        for rr, ap in itertools.product((False, True), repeat=2):
            options = {"include_rr": rr, "include_ap": ap}
            required = self.paired(**options)["scoring_work_units"] * 5
            with self.assertRaisesRegex(BoundsError, "work limit"):
                self.analysis(max_work=required - 1, **options)
            self.assertEqual(
                self.analysis(max_work=required, **options)["scoring_work_units"],
                required,
            )

    def test_per_query_work_not_whole_report_and_candidates_not_cumulative(self):
        original = self.analysis(include_ap=True)
        base_work = self.paired(include_ap=True)["scoring_work_units"]
        self.write(
            self.u,
            ("query_id", "document_id"),
            [("q", d) for d in "abcd"] + [("z", "a")],
        )
        self.assertEqual(
            self.analysis(include_ap=True)["judgment_value"], original["judgment_value"]
        )
        report = self.analysis(include_ap=True)
        self.assertEqual(report["scoring_work_units"], base_work * 5 + 4)

    def test_weights_do_not_scale_or_omit_own_query_values(self):
        self.write(
            self.u,
            ("query_id", "document_id"),
            [("q", d) for d in "abcd"] + [("z", "a")],
        )
        w = self.root / "weights.csv"
        self.write(w, ("query_id", "weight"), [("q", 0), ("z", 1)])
        baseline = self.analysis(include_rr=True, include_ap=True)
        report = self.analysis(query_weights=w, include_rr=True, include_ap=True)
        self.assertEqual(report["judgment_value"], baseline["judgment_value"])
        self.assertEqual(report["scoring_work_units"], baseline["scoring_work_units"])

    def test_invalid_candidates_fail_before_solver(self):
        for rows in (
            [],
            [("q", "b")],
            [("x", "a")],
            [("q", "x")],
            [("q", "a"), ("q", "a")],
        ):
            self.write(self.c, ("query_id", "document_id"), rows)
            with patch("rankbounds.paired._paired_query") as solver:
                with self.assertRaises(BoundsError):
                    self.analysis()
                solver.assert_not_called()
        self.write(
            self.u, ("query_id", "document_id"), [("q", str(i)) for i in range(201)]
        )
        self.ranking(self.r, {})
        self.ranking(self.right, {})
        self.write(self.j, ("query_id", "document_id", "relevant"), [])
        self.write(
            self.c, ("query_id", "document_id"), [("q", str(i)) for i in range(201)]
        )
        with self.assertRaisesRegex(BoundsError, "200"):
            self.analysis()

    def test_shortlist_entries_are_independent_and_literal_row_order_is_stable(self):
        full = self.analysis(include_rr=True, include_ap=True)["judgment_value"]
        self.write(self.c, ("query_id", "document_id"), [("q", "d"), ("q", "a")])
        self.assertEqual(
            self.analysis(include_rr=True, include_ap=True)["judgment_value"], full
        )
        for row in full["candidates"]:
            self.write(
                self.c,
                ("query_id", "document_id"),
                [(row["query_id"], row["document_id"])],
            )
            self.assertEqual(
                self.analysis(include_rr=True, include_ap=True)["judgment_value"][
                    "candidates"
                ],
                [row],
            )
        self.c.write_text("\ufeffquery_id,document_id\nq,d\nq,a\n", encoding="utf8")
        self.assertEqual(
            self.analysis(include_rr=True, include_ap=True)["judgment_value"], full
        )

    def test_200_limit_empty_runs_and_per_file_row_limit(self):
        self.write(
            self.u, ("query_id", "document_id"), [("q", str(i)) for i in range(200)]
        )
        self.ranking(self.r, {})
        self.ranking(self.right, {})
        self.write(self.j, ("query_id", "document_id", "relevant"), [])
        self.write(
            self.c, ("query_id", "document_id"), [("q", str(i)) for i in range(200)]
        )
        report = self.analysis(include_rr=True, include_ap=True)
        self.assertEqual(len(report["judgment_value"]["candidates"]), 200)
        self.assertEqual(report["scoring_work_units"], 7 * 401)
        self.write(self.u, ("query_id", "document_id"), [("q", "a"), ("q", "b")])
        self.write(
            self.c, ("query_id", "document_id"), [("q", "a"), ("q", "b"), ("q", "a")]
        )
        with self.assertRaisesRegex(BoundsError, "row limit"):
            self.analysis(max_rows=2)

    def test_cli_paired_success_and_invalid_has_no_json(self):
        args = [
            "--universe",
            str(self.u),
            "--ranking",
            str(self.r),
            "--comparison-ranking",
            str(self.right),
            "--judgments",
            str(self.j),
            "--judgment-candidates",
            str(self.c),
            "--k",
            "3",
            "--paired-rr",
            "--paired-ap",
        ]
        with redirect_stdout(io.StringIO()) as out:
            self.assertEqual(main(args), 0)
        self.assertEqual(
            json.loads(out.getvalue()), self.analysis(include_rr=True, include_ap=True)
        )
        self.write(self.c, ("query_id", "document_id"), [])
        with redirect_stdout(io.StringIO()) as out, redirect_stderr(io.StringIO()):
            self.assertEqual(main(args), 2)
        self.assertEqual(out.getvalue(), "")
