"""Independent full-universe oracle for opt-in paired AP."""

import io
import itertools
import json
import random
from contextlib import redirect_stderr, redirect_stdout
from unittest.mock import patch

import test_paired
from test_bounds import Fixture, literal_metrics

from rankbounds import BoundsError, compare
from rankbounds.__main__ import main


class PairedAPTests(Fixture):
    ranking = test_paired.PairedTests.ranking
    check_witness = test_paired.PairedTests.check_witness

    def setUp(self):
        super().setUp()
        self.right = self.root / "right.csv"
        self.ranking(self.right, {"q": list("cba")})

    def paired(self, **options):
        return compare(
            self.u,
            self.r,
            self.right,
            self.j,
            k=options.pop("k", 3),
            include_ap=True,
            **options,
        )

    def test_full_label_oracle_and_witnesses(self):
        rng = random.Random(618395)
        for case in range(400):
            docs = list("abcdefgh"[: rng.randint(1, 8)])
            left, right = [
                rng.sample(docs, rng.randint(0, len(docs))) for _ in range(2)
            ]
            labels = {doc: rng.randrange(2) for doc in docs if rng.randrange(3) == 0}
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
            for total in (
                None,
                rng.randint(sum(labels.values()), sum(labels.values()) + len(unknown)),
            ):
                differences = []
                for bits in itertools.product((0, 1), repeat=len(unknown)):
                    positives = {d for d, v in labels.items() if v} | {
                        d for d, v in zip(unknown, bits) if v
                    }
                    if total is not None and len(positives) != total:
                        continue
                    a, b = [
                        literal_metrics(run, positives, k)["ap_total"]
                        for run in (left, right)
                    ]
                    differences.append(a - b)
                row = self.paired(
                    k=k,
                    totals=self.total(total) if total is not None else None,
                    examples=1,
                )["queries"][0]
                for direction, reducer in (("lower", min), ("upper", max)):
                    with self.subTest(case=case, total=total, direction=direction):
                        self.assertAlmostEqual(
                            row["metrics"]["ap_total"][direction],
                            reducer(differences),
                            places=12,
                        )
                        self.check_witness(
                            row, docs, left, right, labels, k, "ap_total", direction
                        )

    def test_default_unchanged_and_options_combine(self):
        old = compare(
            self.u, self.r, self.right, self.j, k=3, include_rr=True, examples=1
        )
        new = self.paired(include_rr=True, examples=1)
        self.assertNotIn("ap_total", old["macro"])
        new["macro"].pop("ap_total")
        for row in new["queries"]:
            row["metrics"].pop("ap_total")
            row["endpoint_examples"].pop("ap_total")
        new["scoring_work_units"] = old["scoring_work_units"]
        self.assertEqual(new, old)

    def test_budget_and_bad_boolean(self):
        report = self.paired()
        work = report["scoring_work_units"]
        old = compare(self.u, self.r, self.right, self.j, k=3)
        row = report["queries"][0]
        charge = (
            (1 << row["unjudged_top_union_documents"])
            * 2
            * (row["left_top_documents"] + row["right_top_documents"] + 1)
        )
        self.assertEqual(work - old["scoring_work_units"], charge)
        self.assertEqual(self.paired(max_work=work), report)
        with patch(
            "rankbounds.paired._paired_query",
            side_effect=AssertionError("scored too early"),
        ):
            with self.assertRaisesRegex(BoundsError, "work limit"):
                self.paired(max_work=work - 1)
        for value in (1, 0, None, "yes", [], {}):
            with (
                self.subTest(value=value),
                self.assertRaisesRegex(BoundsError, "boolean"),
            ):
                compare(self.u, self.r, self.right, self.j, k=3, include_ap=value)

    def test_identical_runs_zero_and_swap_reverses_bounds(self):
        self.ranking(self.right, {"q": list("abc")})
        self.assertEqual(self.paired()["macro"]["ap_total"], {"lower": 0, "upper": 0})
        self.ranking(self.right, {})
        a = self.paired()["macro"]["ap_total"]
        b = compare(self.u, self.right, self.r, self.j, k=3, include_ap=True)["macro"][
            "ap_total"
        ]
        self.assertEqual(a["lower"], -b["upper"])
        self.assertEqual(a["upper"], -b["lower"])

    def test_empty_runs_zero_and_large_union_rejected_before_solver(self):
        self.ranking(self.r, {})
        self.ranking(self.right, {})
        self.assertEqual(
            self.paired(k=10**9)["macro"]["ap_total"], {"lower": 0, "upper": 0}
        )
        docs = [str(i) for i in range(300)]
        self.write(self.u, ("query_id", "document_id"), [("q", d) for d in docs])
        self.ranking(self.r, {"q": docs})
        self.write(self.j, ("query_id", "document_id", "relevant"), [])
        with patch(
            "rankbounds.paired._paired_query",
            side_effect=AssertionError("scored too early"),
        ):
            with self.assertRaisesRegex(BoundsError, "work limit"):
                self.paired(k=300)

    def test_cli_optin_and_wrong_mode_fail_without_json(self):
        args = [
            "--universe",
            str(self.u),
            "--ranking",
            str(self.r),
            "--judgments",
            str(self.j),
            "--k",
            "3",
            "--paired-ap",
        ]
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = main(args)
        self.assertEqual(code, 2)
        self.assertEqual(out.getvalue(), "")
        self.assertIn("requires --comparison-ranking", err.getvalue())
        out = io.StringIO()
        with redirect_stdout(out):
            code = main(args + ["--comparison-ranking", str(self.right), "--paired-rr"])
        self.assertEqual(code, 0)
        report = json.loads(out.getvalue())
        self.assertIn("ap_total", report["macro"])
        self.assertIn("rr", report["macro"])

    def test_outside_positives_change_denominator_not_numerator(self):
        self.ranking(self.r, {"q": ["a"]})
        self.ranking(self.right, {})
        self.write(self.j, ("query_id", "document_id", "relevant"), [("q", "a", 1)])
        self.assertEqual(
            self.paired()["macro"]["ap_total"], {"lower": 0.25, "upper": 1.0}
        )
        self.assertEqual(
            self.paired(totals=self.total(2))["macro"]["ap_total"],
            {"lower": 0.5, "upper": 0.5},
        )

    def test_later_query_budget_rejects_before_any_scoring(self):
        self.write(self.u, ("query_id", "document_id"), [("a", "d"), ("z", "d")])
        self.ranking(self.r, {"a": ["d"], "z": ["d"]})
        self.ranking(self.right, {})
        self.write(self.j, ("query_id", "document_id", "relevant"), [])
        work = self.paired()["scoring_work_units"]
        with patch(
            "rankbounds.paired._paired_query",
            side_effect=AssertionError("scored too early"),
        ):
            with self.assertRaisesRegex(BoundsError, "work limit"):
                self.paired(max_work=work - 1)
