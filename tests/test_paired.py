"""Paired exhaustive label oracle independent of coefficient optimization."""

from contextlib import redirect_stdout, redirect_stderr
import io
import itertools
import json
import random
import unittest
from unittest.mock import patch

from rankbounds import BoundsError, audit, compare
from rankbounds.__main__ import main
from test_bounds import Fixture, literal_metrics

METRICS = ("precision", "recall", "ndcg")


class PairedTests(Fixture):
    def setUp(self):
        super().setUp()
        self.right = self.root / "right.csv"
        self.ranking(self.right, {"q": list("cba")})

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

    def check_witness(self, row, docs, left, right, labels, k, metric, direction):
        witness = row["endpoint_examples"][metric][direction]
        chosen = witness["unjudged_union_relevant"]
        union = set(left[:k]) | set(right[:k])
        self.assertEqual(chosen, sorted(set(chosen)))
        self.assertTrue(set(chosen) <= union - set(labels))
        outside = sorted(set(docs) - union - set(labels))
        count = witness["unjudged_outside_union_relevant_count"]
        self.assertLessEqual(0, count)
        self.assertLessEqual(count, len(outside))
        positives = (
            {d for d, label in labels.items() if label}
            | set(chosen)
            | set(outside[:count])
        )
        self.assertEqual(witness["total_relevant"], len(positives))
        a, b = [literal_metrics(run, positives, k)[metric] for run in (left, right)]
        self.assertAlmostEqual(a, witness["left_score"], places=12)
        self.assertAlmostEqual(b, witness["right_score"], places=12)
        self.assertAlmostEqual(a - b, row["metrics"][metric][direction], places=12)

    def test_seeded_exhaustive_shared_completion_oracle_and_witnesses(self):
        rng = random.Random(623195)
        for case in range(300):
            docs = list("abcdefgh"[: rng.randint(1, 8)])
            left, right = [
                rng.sample(docs, rng.randint(0, len(docs))) for _ in range(2)
            ]
            labels = {d: rng.randrange(2) for d in docs if rng.randrange(3) == 0}
            k = rng.randint(1, len(docs) + 3)
            self.write(self.u, ("query_id", "document_id"), [("q", d) for d in docs])
            self.ranking(self.r, {"q": left})
            self.ranking(self.right, {"q": right})
            self.write(
                self.j,
                ("query_id", "document_id", "relevant"),
                [("q", d, v) for d, v in labels.items()],
            )
            unknown = sorted(set(docs) - set(labels))
            possible_totals = [
                None,
                rng.randint(sum(labels.values()), sum(labels.values()) + len(unknown)),
            ]
            for total in possible_totals:
                observed = {m: [] for m in METRICS}
                for bits in itertools.product((0, 1), repeat=len(unknown)):
                    positive = {d for d, label in labels.items() if label} | {
                        d for d, b in zip(unknown, bits) if b
                    }
                    if total is not None and len(positive) != total:
                        continue
                    a, b = [literal_metrics(run, positive, k) for run in (left, right)]
                    for metric in METRICS:
                        observed[metric].append(a[metric] - b[metric])
                row = self.paired(
                    k=k,
                    totals=self.total(total) if total is not None else None,
                    examples=1,
                )["queries"][0]
                for metric in METRICS:
                    for direction, func in (("lower", min), ("upper", max)):
                        with self.subTest(
                            case=case, total=total, metric=metric, direction=direction
                        ):
                            self.assertAlmostEqual(
                                row["metrics"][metric][direction],
                                func(observed[metric]),
                                places=12,
                            )
                            self.check_witness(
                                row, docs, left, right, labels, k, metric, direction
                            )

    def test_identical_runs_exact_zero_despite_wide_unpaired_intervals(self):
        self.ranking(self.right, {"q": list("abc")})
        single = audit(self.u, self.r, self.j, k=3)
        self.assertLess(
            single["macro"]["ndcg"]["lower"], single["macro"]["ndcg"]["upper"]
        )
        for bounds in self.paired()["macro"].values():
            self.assertEqual(bounds, {"lower": 0.0, "upper": 0.0})

    def test_negative_difference_uses_small_denominator_for_lower(self):
        self.ranking(self.r, {"q": []})
        self.ranking(self.right, {"q": ["b"]})
        row = self.paired(k=1, examples=1)["queries"][0]
        self.assertEqual(row["metrics"]["recall"], {"lower": -1.0, "upper": -0.25})
        self.assertEqual(
            row["endpoint_examples"]["recall"]["lower"]["total_relevant"], 1
        )

    def test_positive_difference_uses_small_denominator_for_upper(self):
        self.ranking(self.r, {"q": ["b"]})
        self.ranking(self.right, {"q": []})
        self.assertEqual(
            self.paired(k=1)["macro"]["recall"], {"lower": 0.25, "upper": 1.0}
        )

    def test_empty_runs_zero_total_short_run_and_large_k(self):
        self.ranking(self.r, {"q": []})
        self.ranking(self.right, {"q": []})
        self.write(self.j, ("query_id", "document_id", "relevant"), [])
        for total in (0, 4):
            result = self.paired(k=1_000_000_000, totals=self.total(total))
            self.assertTrue(
                all(e == {"lower": 0.0, "upper": 0.0} for e in result["macro"].values())
            )

    def test_macro_includes_missing_rankings_lexical_order(self):
        self.write(self.u, ("query_id", "document_id"), [("z", "a"), ("a", "b")])
        self.ranking(self.r, {"z": ["a"]})
        self.ranking(self.right, {})
        self.write(
            self.j,
            ("query_id", "document_id", "relevant"),
            [("z", "a", 1), ("a", "b", 1)],
        )
        result = self.paired(k=1, examples=1)
        self.assertEqual([q["query_id"] for q in result["queries"]], ["a", "z"])
        self.assertEqual(result["macro"]["ndcg"], {"lower": 0.5, "upper": 0.5})
        self.assertIn("endpoint_examples", result["queries"][0])
        self.assertNotIn("endpoint_examples", result["queries"][1])

    def test_swap_reverses_bounds(self):
        a = self.paired()["macro"]
        b = compare(self.u, self.right, self.r, self.j, k=3)["macro"]
        for metric in METRICS:
            self.assertAlmostEqual(a[metric]["lower"], -b[metric]["upper"])
            self.assertAlmostEqual(a[metric]["upper"], -b[metric]["lower"])

    def test_paired_work_exact_boundary_and_no_scoring_on_failure(self):
        work = self.paired()["scoring_work_units"]
        self.assertEqual(self.paired(max_work=work)["scoring_work_units"], work)
        with patch(
            "rankbounds.paired._paired_query",
            side_effect=AssertionError("must not score"),
        ):
            with self.assertRaises(BoundsError):
                self.paired(max_work=work - 1)

    def test_right_rows_validated_below_cutoff_and_at_late_failure(self):
        cases = [
            [("q", "a", 1), ("q", "x", 2)],
            [("q", "a", 1), ("q", "a", 2)],
            [("q", "a", 1), ("q", "b", 3)],
            [("q", "a", 1), ("x", "b", 2)],
            [("q", "a", 1), ("q", "b", "٢")],
        ]
        for rows in cases:
            self.write(self.right, ("query_id", "document_id", "rank"), rows)
            with self.subTest(rows=rows), self.assertRaises(BoundsError):
                self.paired(k=1)

    def test_right_format_and_read_errors_fail_closed(self):
        for data in (
            b"bad,header\n",
            b"query_id,document_id,rank\nq,a,1\n\xff",
            b'query_id,document_id,rank\nq,"oops,1\n',
            b"query_id,document_id,rank\nq,a,1\n\n",
            b"query_id,document_id,rank\nq,\x00,1\n",
        ):
            self.right.write_bytes(data)
            with self.subTest(data=data), self.assertRaises(BoundsError):
                self.paired()
        self.right.unlink()
        with self.assertRaises(BoundsError):
            self.paired()

    def test_invalid_options_totals_and_per_input_row_limit(self):
        for name in ("k", "max_rows", "max_work", "examples"):
            for value in (True, 1.5, "1", -1):
                with (
                    self.subTest(name=name, value=value),
                    self.assertRaises(BoundsError),
                ):
                    self.paired(**{name: value})
        for total in (0, 5):
            with self.subTest(total=total), self.assertRaises(BoundsError):
                self.paired(totals=self.total(total))
        with self.assertRaises(BoundsError):
            self.paired(max_rows=3)

    def test_no_witness_identifiers_by_default_and_explicit_metric_scope(self):
        result = self.paired()
        self.assertNotIn("endpoint_examples", result["queries"][0])
        self.assertEqual(set(result["macro"]), set(METRICS))
        self.assertEqual(result["difference"], "left_minus_right")
        self.assertEqual(result["mode"], "finite_binary_paired_compatibility")

    def test_cli_paired_mode_and_late_error_without_json(self):
        args = [
            "--universe",
            str(self.u),
            "--ranking",
            str(self.r),
            "--comparison-ranking",
            str(self.right),
            "--judgments",
            str(self.j),
            "--k",
            "3",
        ]
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            self.assertEqual(main(args), 0)
        self.assertEqual(json.loads(out.getvalue()), self.paired())
        self.right.write_text("query_id,document_id,rank\nq,a,1\nq,x,2\n")
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            self.assertEqual(main(args), 2)
        self.assertEqual(out.getvalue(), "")
        self.assertNotEqual(err.getvalue(), "")


if __name__ == "__main__":
    unittest.main()
