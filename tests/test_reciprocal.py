"""Independent full-label enumeration for opt-in paired reciprocal rank."""

import itertools
import io
import json
import random
from contextlib import redirect_stderr, redirect_stdout
from unittest.mock import patch

from rankbounds import BoundsError, compare
from rankbounds.__main__ import main
from rankbounds.reciprocal import _reciprocal_bounds
from test_bounds import Fixture, literal_metrics
import test_paired


class ReciprocalTests(Fixture):
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
            include_rr=True,
            **options,
        )

    def test_exhaustive_shared_labels_endpoints_and_witnesses(self):
        rng = random.Random(902651)
        for case in range(1000):
            docs = list("abcdefgh"[: rng.randint(1, 8)])
            left, right = [
                rng.sample(docs, rng.randint(0, len(docs))) for _ in range(2)
            ]
            labels = {doc: rng.randrange(2) for doc in docs if rng.randrange(3) == 0}
            unknown = sorted(set(docs) - set(labels))
            k = rng.randint(1, len(docs) + 3)
            self.write(self.u, ("query_id", "document_id"), [("q", d) for d in docs])
            self.ranking(self.r, {"q": left})
            self.ranking(self.right, {"q": right})
            self.write(
                self.j,
                ("query_id", "document_id", "relevant"),
                [("q", d, v) for d, v in labels.items()],
            )
            totals = [
                None,
                rng.randint(sum(labels.values()), sum(labels.values()) + len(unknown)),
            ]
            for total in totals:
                scores = []
                for bits in itertools.product((0, 1), repeat=len(unknown)):
                    positive = {d for d, v in labels.items() if v} | {
                        d for d, v in zip(unknown, bits) if v
                    }
                    if total is not None and len(positive) != total:
                        continue
                    a, b = [
                        literal_metrics(run, positive, k)["rr"] for run in (left, right)
                    ]
                    scores.append(a - b)
                row = self.paired(
                    k=k,
                    totals=self.total(total) if total is not None else None,
                    examples=1,
                )["queries"][0]
                for direction, reducer in (("lower", min), ("upper", max)):
                    with self.subTest(case=case, total=total, direction=direction):
                        self.assertEqual(
                            row["metrics"]["rr"][direction], reducer(scores)
                        )
                        self.check_witness(
                            row, docs, left, right, labels, k, "rr", direction
                        )

    def test_overlap_disallows_incompatible_first_hits(self):
        # Same first document cannot be both relevant on left and nonrelevant on right.
        bounds, _ = _reciprocal_bounds(["a", "b"], ["a", "c"], {}, 3, None, False)
        self.assertEqual(bounds, {"lower": -0.5, "upper": 0.5})

    def test_known_labels_block_prefix_and_candidate(self):
        bounds, _ = _reciprocal_bounds(
            ["a", "b"], ["c", "a"], {"a": 1, "c": 0}, 3, None, False
        )
        self.assertEqual(bounds, {"lower": 0.5, "upper": 0.5})

    def test_total_forces_later_hits_and_no_hit_case(self):
        self.write(self.j, ("query_id", "document_id", "relevant"), [])
        self.ranking(self.r, {"q": ["a", "b"]})
        self.ranking(self.right, {"q": ["b", "c"]})
        self.assertEqual(
            self.paired(totals=self.total(0))["macro"]["rr"], {"lower": 0, "upper": 0}
        )
        self.assertEqual(
            self.paired(totals=self.total(4))["macro"]["rr"], {"lower": 0, "upper": 0}
        )

    def test_witness_fills_union_then_outside_to_exact_total(self):
        for total in range(5):
            self.write(self.j, ("query_id", "document_id", "relevant"), [])
            self.ranking(self.r, {"q": ["a"]})
            self.ranking(self.right, {})
            row = self.paired(k=1, totals=self.total(total), examples=1)["queries"][0]
            for direction in ("lower", "upper"):
                self.check_witness(row, list("abcd"), ["a"], [], {}, 1, "rr", direction)

    def test_identical_empty_swap_and_macro(self):
        self.ranking(self.right, {"q": list("abc")})
        self.assertEqual(self.paired()["macro"]["rr"], {"lower": 0, "upper": 0})
        self.ranking(self.right, {})
        a = self.paired()["macro"]["rr"]
        b = compare(self.u, self.right, self.r, self.j, k=3, include_rr=True)["macro"][
            "rr"
        ]
        self.assertEqual(a["lower"], -b["upper"])
        self.assertEqual(a["upper"], -b["lower"])
        self.ranking(self.r, {})
        self.assertEqual(self.paired(k=10**9)["macro"]["rr"], {"lower": 0, "upper": 0})
        self.write(self.u, ("query_id", "document_id"), [("z", "a"), ("a", "b")])
        self.ranking(self.r, {"z": ["a"]})
        self.write(
            self.j,
            ("query_id", "document_id", "relevant"),
            [("z", "a", 1), ("a", "b", 1)],
        )
        self.assertEqual(self.paired()["macro"]["rr"], {"lower": 0.5, "upper": 0.5})

    def test_old_metrics_and_default_report_unchanged(self):
        old = compare(self.u, self.r, self.right, self.j, k=3, examples=1)
        new = self.paired(examples=1)
        self.assertNotIn("rr", old["macro"])
        new["macro"].pop("rr")
        for row in new["queries"]:
            row["metrics"].pop("rr")
            row["endpoint_examples"].pop("rr")
        new["scoring_work_units"] = old["scoring_work_units"]
        self.assertEqual(new, old)

    def test_additional_work_boundary_before_any_scoring(self):
        old = compare(self.u, self.r, self.right, self.j, k=3)
        new = self.paired()
        self.assertEqual(
            new["scoring_work_units"] - old["scoring_work_units"], 4 * 4 * 7
        )
        work = new["scoring_work_units"]
        self.assertEqual(self.paired(max_work=work), new)
        with patch(
            "rankbounds.paired._paired_query",
            side_effect=AssertionError("scored too early"),
        ):
            with self.assertRaisesRegex(BoundsError, "work limit"):
                self.paired(max_work=work - 1)

    def test_bad_bool_and_infeasible_totals(self):
        for value in (1, 0, None, "yes", [], {}):
            with (
                self.subTest(value=value),
                self.assertRaisesRegex(BoundsError, "boolean"),
            ):
                compare(self.u, self.r, self.right, self.j, k=3, include_rr=value)
        for total in (0, 5):
            with self.assertRaises(BoundsError):
                self.paired(totals=self.total(total))

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
            "--paired-rr",
        ]
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            self.assertEqual(main(args), 2)
        self.assertEqual(out.getvalue(), "")
        self.assertIn("requires --comparison-ranking", err.getvalue())
        out = io.StringIO()
        with redirect_stdout(out):
            self.assertEqual(main(args + ["--comparison-ranking", str(self.right)]), 0)
        self.assertIn("rr", json.loads(out.getvalue())["macro"])

    def test_identifiers_only_disclosed_when_examples_enabled(self):
        report = self.paired()
        self.assertNotIn("endpoint_examples", report["queries"][0])
        self.assertNotIn("unjudged_union_relevant", json.dumps(report))
