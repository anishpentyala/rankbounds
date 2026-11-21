"""Fixed query-traffic weights, separate from the equal-query macro."""

import io
import itertools
import json
import random
from contextlib import redirect_stderr, redirect_stdout
from unittest.mock import patch

from rankbounds import BoundsError, audit, compare
from rankbounds.__main__ import main
from test_bounds import Fixture, literal_metrics


class QueryWeightTests(Fixture):
    def setUp(self):
        super().setUp()
        self.right = self.root / "right.csv"
        self.weights = self.root / "weights.csv"
        self.write(
            self.u,
            ("query_id", "document_id"),
            [(q, d) for q in ("a", "b") for d in ("x", "y")],
        )
        for path, docs in ((self.r, ("x", "x")), (self.right, ("y", "y"))):
            self.write(
                path,
                ("query_id", "document_id", "rank"),
                [(q, d, 1) for q, d in zip(("a", "b"), docs)],
            )
        self.write(
            self.j,
            ("query_id", "document_id", "relevant"),
            [("a", "x", 1), ("a", "y", 0), ("b", "x", 0), ("b", "y", 1)],
        )
        self.set_weights(9, 1)

    def set_weights(self, a, b):
        self.write(self.weights, ("query_id", "weight"), [("a", a), ("b", b)])

    def call_mode(self, paired=False, **options):
        function = compare if paired else audit
        inputs = [self.u, self.r] + ([self.right] if paired else []) + [self.j]
        return function(*inputs, k=options.pop("k", 1), **options)

    def test_weighted_and_equal_macro_are_separate(self):
        for paired, expected in ((False, 0.9), (True, 0.8)):
            report = self.call_mode(paired, query_weights=self.weights)
            self.assertEqual(
                report["macro"]["precision"],
                {"lower": 0.0 if paired else 0.5, "upper": 0.0 if paired else 0.5},
            )
            for side in ("lower", "upper"):
                self.assertAlmostEqual(
                    report["query_weighted"]["metrics"]["precision"][side], expected
                )
            self.assertEqual(report["query_weighted"]["weights"], {"a": "9", "b": "1"})
            self.assertEqual(report["query_weighted"]["total_weight"], "10")
        self.set_weights(1, 0)
        for paired in (False, True):
            report = self.call_mode(paired, query_weights=self.weights)
            self.assertEqual(report["query_count"], 2)
            self.assertEqual(len(report["queries"]), 2)
            self.assertEqual(
                report["query_weighted"]["metrics"]["precision"]["lower"], 1.0
            )

    def test_joint_completion_oracle_single_and_paired(self):
        rng = random.Random(522086)
        for case in range(60):
            specs = []
            universe, left_rows, right_rows, known_rows = [], [], [], []
            for qid in ("a", "b"):
                docs = list("wxyz"[: rng.randint(1, 4)])
                left, right = [
                    rng.sample(docs, rng.randrange(len(docs) + 1)) for _ in range(2)
                ]
                labels = {d: rng.randrange(2) for d in docs if rng.randrange(3) == 0}
                weight = rng.randrange(1, 11)
                specs.append((qid, docs, left, right, labels, weight))
                universe.extend((qid, d) for d in docs)
                left_rows.extend((qid, d, i) for i, d in enumerate(left, 1))
                right_rows.extend((qid, d, i) for i, d in enumerate(right, 1))
                known_rows.extend((qid, d, label) for d, label in labels.items())
            self.write(self.u, ("query_id", "document_id"), universe)
            self.write(self.r, ("query_id", "document_id", "rank"), left_rows)
            self.write(self.right, ("query_id", "document_id", "rank"), right_rows)
            self.write(self.j, ("query_id", "document_id", "relevant"), known_rows)
            self.set_weights(specs[0][-1], specs[1][-1])
            k = rng.randrange(1, 6)
            for paired in (False, True):
                options = {"include_ap": True, "include_rr": True} if paired else {}
                report = self.call_mode(
                    paired, k=k, query_weights=self.weights, **options
                )
                possibilities = []
                for qid, docs, left, right, labels, weight in specs:
                    unknown = sorted(set(docs) - set(labels))
                    fixed = {d for d, label in labels.items() if label}
                    choices = []
                    for bits in itertools.product((0, 1), repeat=len(unknown)):
                        positives = fixed | {d for d, bit in zip(unknown, bits) if bit}
                        scores = literal_metrics(left, positives, k)
                        if paired:
                            other = literal_metrics(right, positives, k)
                            scores = {
                                metric: value - other[metric]
                                for metric, value in scores.items()
                            }
                        choices.append(scores)
                    possibilities.append(choices)
                for metric, ends in report["query_weighted"]["metrics"].items():
                    values = [
                        (a[metric] * specs[0][-1] + b[metric] * specs[1][-1])
                        / sum(s[-1] for s in specs)
                        for a, b in itertools.product(*possibilities)
                    ]
                    self.assertAlmostEqual(ends["lower"], min(values), places=12)
                    self.assertAlmostEqual(ends["upper"], max(values), places=12)

    def test_default_and_existing_fields_unchanged(self):
        for paired in (False, True):
            baseline = self.call_mode(paired)
            self.assertEqual(baseline, self.call_mode(paired, query_weights=None))
            report = self.call_mode(paired, query_weights=self.weights)
            report.pop("query_weighted")
            self.assertEqual(report, baseline)
        self.set_weights(1, 1)
        for paired in (False, True):
            report = self.call_mode(paired, query_weights=self.weights)
            self.assertEqual(report["query_weighted"]["metrics"], report["macro"])

    def test_invalid_weights_fail_before_any_solver(self):
        bad_rows = [
            [],
            [("a", 1)],
            [("a", 1), ("b", 1), ("b", 2)],
            [("a", 1), ("unknown", 1)],
            [("a", 0), ("b", 0)],
        ]
        bad_rows += [
            [("a", value), ("b", 1)]
            for value in ("-1", "+1", "1.0", "1e2", " 1", "1 ", "", "١", "1" * 19)
        ]
        for rows in bad_rows:
            self.write(self.weights, ("query_id", "weight"), rows)
            with (
                patch("rankbounds.core._query") as single,
                patch("rankbounds.paired._paired_query") as paired,
            ):
                for mode in (False, True):
                    with (
                        self.subTest(rows=rows, paired=mode),
                        self.assertRaises(BoundsError),
                    ):
                        self.call_mode(mode, query_weights=self.weights)
                single.assert_not_called()
                paired.assert_not_called()
        self.write(self.weights, ("weight", "query_id"), [(1, "a"), (1, "b")])
        with self.assertRaises(BoundsError):
            self.call_mode(query_weights=self.weights)

    def test_duplicate_weights_rejected_with_real_solvers(self):
        self.write(self.weights, ("query_id", "weight"), [("a", 1), ("b", 1), ("b", 2)])
        for paired in (False, True):
            with self.subTest(paired=paired), self.assertRaises(BoundsError):
                self.call_mode(paired, query_weights=self.weights)

    def test_zero_weight_does_not_hide_bad_inputs_or_reduce_admission(self):
        self.set_weights(1, 0)
        self.write(self.t, ("query_id", "total_relevant"), [("a", 1), ("b", 0)])
        for paired in (False, True):
            with self.assertRaises(BoundsError):
                self.call_mode(paired, query_weights=self.weights, totals=self.t)
            work = self.call_mode(paired)["scoring_work_units"]
            with self.assertRaises(BoundsError):
                self.call_mode(paired, query_weights=self.weights, max_work=work - 1)
            self.assertEqual(
                self.call_mode(paired, query_weights=self.weights, max_work=work)[
                    "scoring_work_units"
                ],
                work,
            )

    def test_large_integer_weights_padding_and_order(self):
        big = 10**18 - 1
        self.set_weights(big, big)
        first = self.call_mode(query_weights=self.weights)
        self.assertEqual(first["query_weighted"]["total_weight"], str(2 * big))
        self.write(self.weights, ("query_id", "weight"), [("b", big), ("a", big)])
        self.assertEqual(first, self.call_mode(query_weights=self.weights))
        self.set_weights("0009", "01")
        self.assertEqual(
            self.call_mode(query_weights=self.weights)["query_weighted"]["weights"],
            {"a": "9", "b": "1"},
        )

    def test_csv_errors_and_per_file_row_limit(self):
        for content in (
            "query_id,weight\na,1\nb,1\na,2\n",
            'query_id,weight\na,"1\nb,1\n',
        ):
            self.weights.write_text(content)
            with self.assertRaises(BoundsError):
                self.call_mode(query_weights=self.weights, max_rows=4)
        self.weights.write_bytes(b"query_id,weight\na,1\nb,\xff\n")
        with self.assertRaises(BoundsError):
            self.call_mode(query_weights=self.weights)
        with self.assertRaises(BoundsError):
            self.call_mode(query_weights=self.root / "missing.csv")
        self.write(self.u, ("query_id", "document_id"), [("a", "x"), ("b", "x")])
        self.write(self.r, ("query_id", "document_id", "rank"), [])
        self.write(self.j, ("query_id", "document_id", "relevant"), [])
        self.write(self.weights, ("query_id", "weight"), [("a", 1), ("b", 1), ("a", 1)])
        with self.assertRaisesRegex(BoundsError, "row limit"):
            self.call_mode(query_weights=self.weights, max_rows=2)

    def test_cli_both_modes_and_no_partial_json_on_invalid_weights(self):
        args = [
            "--universe",
            str(self.u),
            "--ranking",
            str(self.r),
            "--judgments",
            str(self.j),
            "--k",
            "1",
            "--query-weights",
            str(self.weights),
        ]
        for extra in (
            [],
            ["--comparison-ranking", str(self.right), "--paired-ap", "--paired-rr"],
        ):
            with redirect_stdout(io.StringIO()) as output:
                self.assertEqual(main(args + extra), 0)
            report = json.loads(output.getvalue())
            self.assertIn("query_weighted", report)
        self.set_weights(0, 0)
        with redirect_stdout(io.StringIO()) as output, redirect_stderr(io.StringIO()):
            self.assertEqual(main(args), 2)
        self.assertEqual(output.getvalue(), "")
