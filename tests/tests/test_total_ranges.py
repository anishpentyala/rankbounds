"""Full-label oracles for caller-declared relevance-count ranges."""

import io
import itertools
import json
import random
from contextlib import redirect_stderr, redirect_stdout
from unittest.mock import patch

from test_bounds import Fixture, literal_metrics
from rankbounds import BoundsError, audit, compare
from rankbounds.__main__ import main


class TotalRangeTests(Fixture):
    def setUp(self):
        super().setUp()
        self.ranges = self.root / "ranges.csv"
        self.right = self.root / "right.csv"
        self.write(self.right, ("query_id", "document_id", "rank"), [])

    def constraint(self, low, high):
        self.write(
            self.ranges,
            ("query_id", "min_relevant", "max_relevant"),
            [("q", low, high)],
        )
        return self.ranges

    def paired(self, **options):
        return compare(self.u, self.r, self.right, self.j, k=3, **options)

    def set_case(self, docs, left, right, labels):
        self.write(self.u, ("query_id", "document_id"), [("q", d) for d in docs])
        for file, run in ((self.r, left), (self.right, right)):
            self.write(
                file,
                ("query_id", "document_id", "rank"),
                [("q", d, n) for n, d in enumerate(run, 1)],
            )
        self.write(
            self.j,
            ("query_id", "document_id", "relevant"),
            [("q", d, v) for d, v in labels.items()],
        )

    def assert_witness(self, row, docs, left, right, labels, k, metric, direction):
        witness = row["endpoint_examples"][metric][direction]
        paired = right is not None
        top = set(left[:k]) | (set(right[:k]) if paired else set())
        selected = witness[
            "unjudged_union_relevant" if paired else "unjudged_top_relevant"
        ]
        self.assertEqual(len(selected), len(set(selected)))
        self.assertTrue(set(selected) <= top - set(labels))
        outside = sorted(set(docs) - top - set(labels))
        count = witness[
            "unjudged_outside_union_relevant_count"
            if paired
            else "unjudged_outside_relevant_count"
        ]
        self.assertGreaterEqual(count, 0)
        self.assertLessEqual(count, len(outside))
        positives = (
            {d for d, v in labels.items() if v} | set(selected) | set(outside[:count])
        )
        self.assertEqual(len(positives), witness["total_relevant"])
        feasible = row["feasible_total_relevant"]
        self.assertLessEqual(feasible["lower"], len(positives))
        self.assertLessEqual(len(positives), feasible["upper"])
        score = literal_metrics(left, positives, k)[metric]
        if paired:
            other = literal_metrics(right, positives, k)[metric]
            self.assertAlmostEqual(witness["left_score"], score, places=12)
            self.assertAlmostEqual(witness["right_score"], other, places=12)
            score -= other
        self.assertAlmostEqual(row["metrics"][metric][direction], score, places=12)

    def test_every_interval_against_full_label_oracle(self):
        rng = random.Random(382904)
        for case in range(65):
            docs = list("abcdefg"[: rng.randint(1, 7)])
            left, right = [
                rng.sample(docs, rng.randint(0, len(docs))) for _ in range(2)
            ]
            labels = {d: rng.randrange(2) for d in docs if rng.randrange(3) == 0}
            k = rng.randint(1, len(docs) + 2)
            self.set_case(docs, left, right, labels)
            unknown = sorted(set(docs) - set(labels))
            fixed = {d for d, v in labels.items() if v}
            completions = [
                fixed | {d for d, bit in zip(unknown, bits) if bit}
                for bits in itertools.product((0, 1), repeat=len(unknown))
            ]
            for low in range(len(docs) + 1):
                for high in range(low, len(docs) + 1):
                    compatible = [p for p in completions if low <= len(p) <= high]
                    for paired in (False, True):
                        args = (
                            (self.u, self.r, self.right, self.j)
                            if paired
                            else (self.u, self.r, self.j)
                        )
                        options = (
                            {"include_rr": True, "include_ap": True} if paired else {}
                        )
                        function = compare if paired else audit
                        with self.subTest(case=case, low=low, high=high, paired=paired):
                            if not compatible:
                                with self.assertRaises(BoundsError):
                                    function(
                                        *args,
                                        k=k,
                                        total_ranges=self.constraint(low, high),
                                        **options,
                                    )
                                continue
                            row = function(
                                *args,
                                k=k,
                                total_ranges=self.constraint(low, high),
                                examples=1,
                                **options,
                            )["queries"][0]
                            self.assertEqual(
                                row["feasible_total_relevant"],
                                {
                                    "lower": min(map(len, compatible)),
                                    "upper": max(map(len, compatible)),
                                },
                            )
                            scores = [literal_metrics(left, p, k) for p in compatible]
                            other = (
                                [literal_metrics(right, p, k) for p in compatible]
                                if paired
                                else None
                            )
                            for metric in row["metrics"]:
                                values = [
                                    s[metric] - other[n][metric]
                                    if paired
                                    else s[metric]
                                    for n, s in enumerate(scores)
                                ]
                                for direction, reducer in (
                                    ("lower", min),
                                    ("upper", max),
                                ):
                                    self.assertAlmostEqual(
                                        row["metrics"][metric][direction],
                                        reducer(values),
                                        places=12,
                                    )
                                    self.assert_witness(
                                        row,
                                        docs,
                                        left,
                                        right if paired else None,
                                        labels,
                                        k,
                                        metric,
                                        direction,
                                    )
                            if not paired:
                                self.assertEqual(
                                    row["all_unjudged_nonrelevant"]["compatible"],
                                    low <= len(fixed) <= high,
                                )

    def test_singleton_ranges_exact_total_report_parity(self):
        for total in range(1, 5):
            for paired in (False, True):
                function = self.paired if paired else self.call
                options = {"include_rr": True, "include_ap": True} if paired else {}
                exact = function(totals=self.total(total), examples=1, **options)
                ranged = function(
                    total_ranges=self.constraint(total, total), examples=1, **options
                )
                self.assertEqual(exact, ranged)

    def test_full_range_report_parity(self):
        for function in (self.call, self.paired):
            self.assertEqual(
                function(examples=1),
                function(total_ranges=self.constraint(0, 4), examples=1),
            )

    def test_inputs_unchanged(self):
        self.constraint(1, 3)
        paths = (self.u, self.r, self.right, self.j, self.ranges)
        before = [p.read_bytes() for p in paths]
        self.paired(total_ranges=self.ranges, include_rr=True, include_ap=True)
        self.assertEqual(before, [p.read_bytes() for p in paths])

    def test_invalid_ranges_fail_closed(self):
        cases = [
            (3, 2),
            (0, 5),
            (-1, 2),
            ("1.0", 2),
            (" 1", 2),
            ("١", 2),
            (0, "1" * 19),
            (0, 0),
        ]
        for low, high in cases:
            for function in (self.call, self.paired):
                with self.subTest(low=low, high=high, function=function):
                    with self.assertRaises(BoundsError):
                        function(total_ranges=self.constraint(low, high))

    def test_coverage_duplicates_and_unknown_queries(self):
        for rows in ([], [("q", 0, 4), ("q", 1, 2)], [("private-query", 0, 2)]):
            self.write(self.ranges, ("query_id", "min_relevant", "max_relevant"), rows)
            for function in (self.call, self.paired):
                with self.assertRaises(BoundsError) as caught:
                    function(total_ranges=self.ranges)
                self.assertNotIn("private-query", str(caught.exception))
                self.assertNotIn(str(self.ranges), str(caught.exception))

    def test_range_row_cap_and_header_validation(self):
        self.write(
            self.ranges, ("query_id", "max_relevant", "min_relevant"), [("q", 4, 0)]
        )
        with self.assertRaises(BoundsError):
            self.call(total_ranges=self.ranges)
        self.constraint(0, 4)
        with self.assertRaises(BoundsError):
            self.call(total_ranges=self.ranges, max_rows=1)

    def test_mutually_exclusive_api_even_before_reading_files(self):
        for function in (self.call, self.paired):
            with self.assertRaisesRegex(BoundsError, "mutually exclusive"):
                function(totals="missing", total_ranges="also missing")

    def test_all_query_constraints_checked_before_scoring(self):
        self.write(self.u, ("query_id", "document_id"), [("q", "a"), ("z", "b")])
        self.write(self.r, ("query_id", "document_id", "rank"), [])
        self.write(self.j, ("query_id", "document_id", "relevant"), [("z", "b", 1)])
        self.write(
            self.ranges,
            ("query_id", "min_relevant", "max_relevant"),
            [("q", 0, 1), ("z", 0, 0)],
        )
        with (
            patch("rankbounds.core._query", side_effect=AssertionError("scored")),
            patch(
                "rankbounds.paired._paired_query", side_effect=AssertionError("scored")
            ),
        ):
            for function in (self.call, self.paired):
                with self.assertRaises(BoundsError):
                    function(total_ranges=self.ranges)

    def test_cli_success_and_error_no_partial_json(self):
        base = [
            "--universe",
            str(self.u),
            "--ranking",
            str(self.r),
            "--judgments",
            str(self.j),
            "--k",
            "3",
            "--total-ranges",
            str(self.constraint(1, 3)),
        ]
        for extra in (
            [],
            ["--comparison-ranking", str(self.right), "--paired-rr", "--paired-ap"],
        ):
            out, err = io.StringIO(), io.StringIO()
            with redirect_stdout(out), redirect_stderr(err):
                self.assertEqual(main(base + extra), 0)
            self.assertEqual(
                json.loads(out.getvalue())["queries"][0]["feasible_total_relevant"],
                {"lower": 1, "upper": 3},
            )
            self.assertEqual(err.getvalue(), "")
        self.constraint(0, 0)
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            self.assertEqual(main(base), 2)
        self.assertEqual(out.getvalue(), "")
        self.assertIn("contradicts", err.getvalue())
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit) as caught:
                main(base + ["--totals", str(self.t)])
        self.assertEqual(caught.exception.code, 2)

    def test_macro_query_local_ranges_with_empty_run(self):
        self.write(
            self.u,
            ("query_id", "document_id"),
            [(q, d) for q in ("q", "z") for d in ("a", "b")],
        )
        self.write(self.r, ("query_id", "document_id", "rank"), [("q", "a", 1)])
        self.write(self.j, ("query_id", "document_id", "relevant"), [])
        self.write(
            self.ranges,
            ("query_id", "min_relevant", "max_relevant"),
            [("z", 1, 2), ("q", 1, 1)],
        )
        row = self.call(k=1, total_ranges=self.ranges)
        self.assertEqual(row["query_count"], 2)
        self.assertEqual(row["macro"]["precision"], {"lower": 0.0, "upper": 0.5})
        self.assertEqual(row["macro"]["recall"], {"lower": 0.0, "upper": 0.5})
        self.assertEqual(
            [q["feasible_total_relevant"] for q in row["queries"]],
            [{"lower": 1, "upper": 1}, {"lower": 1, "upper": 2}],
        )

    def test_default_range_report_omits_document_examples(self):
        self.set_case(
            ["private-doc-a", "private-doc-b"], ["private-doc-a"], ["private-doc-b"], {}
        )
        for function in (self.call, self.paired):
            report = function(total_ranges=self.constraint(1, 2))
            self.assertNotIn("private-doc", json.dumps(report))
            self.assertNotIn("endpoint_examples", report["queries"][0])
