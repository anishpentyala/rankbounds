"""Independent complete-labeling oracle, validation and CLI regressions."""

import csv
import io
import itertools
import json
import math
import os
from pathlib import Path
import random
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout, redirect_stderr

from rankbounds import BoundsError, audit
from rankbounds.__main__ import main

NAMES = ("precision", "recall", "rr", "ap_total", "ndcg")


def literal_metrics(run, positives, k):
    # Deliberately uses set intersections and pair counts, not production loops.
    found = set(run[:k]) & positives
    n = len(positives)
    ranks = [i + 1 for i, doc in enumerate(run[:k]) if doc in positives]
    return dict(
        zip(
            NAMES,
            (
                len(found) / k,
                len(found) / n if n else 0,
                1 / min(ranks) if ranks else 0,
                sum(sum(r2 <= r for r2 in ranks) / r for r in ranks) / n if n else 0,
                sum(math.log(2) / math.log(r + 1) for r in ranks)
                / sum(math.log(2) / math.log(r + 1) for r in range(1, min(k, n) + 1))
                if n
                else 0,
            ),
        )
    )


class Fixture(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.u = self.root / "universe.csv"
        self.r = self.root / "ranking.csv"
        self.j = self.root / "judgments.csv"
        self.t = self.root / "totals.csv"
        self.write(self.u, ("query_id", "document_id"), [("q", d) for d in "abcd"])
        self.write(
            self.r,
            ("query_id", "document_id", "rank"),
            [("q", d, i) for i, d in enumerate("abc", 1)],
        )
        self.write(self.j, ("query_id", "document_id", "relevant"), [("q", "b", 1)])

    def write(self, path, header, rows):
        with path.open("w", encoding="utf8", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(header)
            writer.writerows(rows)

    def call(self, **kw):
        return audit(self.u, self.r, self.j, k=kw.pop("k", 3), **kw)

    def total(self, n):
        self.write(self.t, ("query_id", "total_relevant"), [("q", n)])
        return self.t


class OracleTests(Fixture):
    def test_exhaustive_binary_completions_random_queries(self):
        rng = random.Random(82117)
        for case in range(240):
            size = rng.randrange(1, 9)
            docs = ["d" + str(i) for i in range(size)]
            run = rng.sample(docs, rng.randrange(size + 1))
            labels = {d: rng.randrange(2) for d in docs if rng.random() < 0.5}
            k = rng.randrange(1, size + 4)
            unknown = [d for d in docs if d not in labels]
            completions = [
                set(d for d, v in labels.items() if v)
                | set(d for d, bit in zip(unknown, bits) if bit)
                for bits in itertools.product((0, 1), repeat=len(unknown))
            ]
            fixed = None if case % 3 == 0 else len(rng.choice(completions))
            compatible = [p for p in completions if fixed is None or len(p) == fixed]
            self.write(
                self.u, ("query_id", "document_id"), [("q", d) for d in reversed(docs)]
            )
            self.write(
                self.r,
                ("query_id", "document_id", "rank"),
                [("q", d, i) for i, d in reversed(list(enumerate(run, 1)))],
            )
            self.write(
                self.j,
                ("query_id", "document_id", "relevant"),
                [("q", d, v) for d, v in labels.items()],
            )
            row = self.call(
                k=k, totals=self.total(fixed) if fixed is not None else None, examples=1
            )["queries"][0]
            metrics = [literal_metrics(run, p, k) for p in compatible]
            with self.subTest(case=case):
                for metric in NAMES:
                    self.assertAlmostEqual(
                        row["metrics"][metric]["lower"],
                        min(m[metric] for m in metrics),
                        places=12,
                    )
                    self.assertAlmostEqual(
                        row["metrics"][metric]["upper"],
                        max(m[metric] for m in metrics),
                        places=12,
                    )
                    for direction in ("lower", "upper"):
                        witness = row["endpoint_examples"][metric][direction]
                        selected = set(witness["unjudged_top_relevant"])
                        self.assertFalse(selected & set(labels))
                        self.assertTrue(selected <= set(run[:k]))
                        outside = sorted(set(unknown) - set(run[:k]))
                        count = witness["unjudged_outside_relevant_count"]
                        self.assertTrue(0 <= count <= len(outside))
                        completed = (
                            set(d for d, v in labels.items() if v)
                            | selected
                            | set(outside[:count])
                        )
                        self.assertEqual(len(completed), witness["total_relevant"])
                        self.assertIn(completed, compatible)
                        self.assertAlmostEqual(
                            literal_metrics(run, completed, k)[metric],
                            row["metrics"][metric][direction],
                            places=12,
                        )

    def test_fixed_count_earliest_latest_not_arbitrary(self):
        self.write(self.u, ("query_id", "document_id"), [("q", d) for d in "abc"])
        row = self.call(totals=self.total(2), examples=1)["queries"][0]
        self.assertAlmostEqual(row["metrics"]["ap_total"]["lower"], (1 / 2 + 2 / 3) / 2)
        self.assertEqual(row["metrics"]["ap_total"]["upper"], 1.0)
        self.assertEqual(
            row["endpoint_examples"]["ap_total"]["lower"]["unjudged_top_relevant"],
            ["c"],
        )
        self.assertEqual(
            row["endpoint_examples"]["ap_total"]["upper"]["unjudged_top_relevant"],
            ["a"],
        )

    def test_rr_cutoff_does_not_use_later_known_positive(self):
        row = self.call(k=1)["queries"][0]
        self.assertEqual(row["metrics"]["rr"], {"lower": 0.0, "upper": 1.0})
        self.write(
            self.j,
            ("query_id", "document_id", "relevant"),
            [("q", "a", 0), ("q", "b", 1)],
        )
        self.assertEqual(self.call(k=1)["macro"]["rr"], {"lower": 0.0, "upper": 0.0})

    def test_ap_total_is_not_ap_min_total_k(self):
        self.write(
            self.j,
            ("query_id", "document_id", "relevant"),
            [("q", d, 1) for d in "abcd"],
        )
        row = self.call(k=1)["queries"][0]
        self.assertEqual(row["metrics"]["ap_total"], {"lower": 0.25, "upper": 0.25})

    def test_aggregate_bounds_attained_with_independent_queries(self):
        self.write(
            self.u,
            ("query_id", "document_id"),
            [(q, d) for q in ("q", "z") for d in "abcd"],
        )
        self.write(
            self.r,
            ("query_id", "document_id", "rank"),
            [(q, d, i) for q in ("q", "z") for i, d in enumerate("abc", 1)],
        )
        self.write(
            self.j,
            ("query_id", "document_id", "relevant"),
            [("q", "b", 1), ("z", "a", 0)],
        )
        report = self.call()
        per_query = []
        for labels in ({"b": 1}, {"a": 0}):
            unknown = sorted(set("abcd") - set(labels))
            scores = []
            for bits in itertools.product((0, 1), repeat=len(unknown)):
                positives = {d for d, v in labels.items() if v} | {
                    d for d, v in zip(unknown, bits) if v
                }
                scores.append(literal_metrics(list("abc"), positives, 3))
            per_query.append(scores)
        for metric in NAMES:
            combinations = [
                (a[metric] + b[metric]) / 2 for a, b in itertools.product(*per_query)
            ]
            self.assertAlmostEqual(report["macro"][metric]["lower"], min(combinations))
            self.assertAlmostEqual(report["macro"][metric]["upper"], max(combinations))

    def test_complete_labels_collapse(self):
        self.write(
            self.j,
            ("query_id", "document_id", "relevant"),
            [("q", d, int(d in "bd")) for d in "abcd"],
        )
        row = self.call()["queries"][0]
        expected = literal_metrics(list("abc"), set("bd"), 3)
        for name in NAMES:
            self.assertAlmostEqual(row["metrics"][name]["lower"], expected[name])
            self.assertEqual(
                row["metrics"][name]["lower"], row["metrics"][name]["upper"]
            )

    def test_no_judgments(self):
        self.write(self.j, ("query_id", "document_id", "relevant"), [])
        row = self.call()["queries"][0]
        for name in NAMES:
            self.assertEqual(row["metrics"][name], {"lower": 0.0, "upper": 1.0})

    def test_all_negative_zero_denominators(self):
        self.write(
            self.j,
            ("query_id", "document_id", "relevant"),
            [("q", d, 0) for d in "abcd"],
        )
        for interval in self.call()["macro"].values():
            self.assertEqual(interval, {"lower": 0.0, "upper": 0.0})

    def test_no_ranking_still_in_macro(self):
        self.write(self.r, ("query_id", "document_id", "rank"), [])
        for interval in self.call()["macro"].values():
            self.assertEqual(interval, {"lower": 0.0, "upper": 0.0})

    def test_short_run_precision_uses_k(self):
        self.write(self.r, ("query_id", "document_id", "rank"), [("q", "b", 1)])
        self.assertEqual(
            self.call(k=10)["macro"]["precision"], {"lower": 0.1, "upper": 0.1}
        )

    def test_unknown_outside_changes_denominators(self):
        self.write(self.r, ("query_id", "document_id", "rank"), [("q", "b", 1)])
        row = self.call(k=1)["queries"][0]
        self.assertEqual(row["metrics"]["recall"], {"lower": 0.25, "upper": 1.0})
        self.assertEqual(row["metrics"]["ap_total"], {"lower": 0.25, "upper": 1.0})

    def test_naive_all_nonrelevant_not_lower_ndcg(self):
        # Known relevant rank2; unknown outside can enlarge IDCG without DCG.
        row = self.call()["queries"][0]
        self.assertLess(
            row["metrics"]["ndcg"]["lower"],
            row["all_unjudged_nonrelevant"]["metrics"]["ndcg"],
        )

    def test_naive_all_relevant_not_upper_ndcg(self):
        self.write(
            self.j,
            ("query_id", "document_id", "relevant"),
            [("q", "a", 1), ("q", "b", 0)],
        )
        row = self.call()["queries"][0]
        self.assertLess(
            literal_metrics(list("abc"), set("acd"), 3)["ndcg"],
            row["metrics"]["ndcg"]["upper"],
        )

    def test_fixed_total_forces_top_unknown_positive(self):
        row = self.call(totals=self.total(4))["queries"][0]
        self.assertEqual(row["metrics"]["precision"], {"lower": 1.0, "upper": 1.0})
        self.assertFalse(row["all_unjudged_nonrelevant"]["compatible"])
        self.assertIsNone(row["all_unjudged_nonrelevant"]["metrics"])

    def test_fixed_known_total_all_unknown_negative(self):
        row = self.call(totals=self.total(1))["queries"][0]
        self.assertTrue(row["all_unjudged_nonrelevant"]["compatible"])
        for name in NAMES:
            self.assertEqual(
                row["metrics"][name]["lower"], row["metrics"][name]["upper"]
            )

    def test_macro_equal_query_weight_not_documents(self):
        self.write(
            self.u,
            ("query_id", "document_id"),
            [("q", d) for d in "abcd"] + [("z", "a")],
        )
        self.write(
            self.j,
            ("query_id", "document_id", "relevant"),
            [("q", d, 1) for d in "abcd"] + [("z", "a", 1)],
        )
        report = self.call()
        self.assertEqual(report["query_count"], 2)
        self.assertEqual(report["macro"]["precision"], {"lower": 0.5, "upper": 0.5})

    def test_namespace_query_document_pairs(self):
        self.write(self.u, ("query_id", "document_id"), [("q", "a"), ("z", "a")])
        self.write(
            self.r, ("query_id", "document_id", "rank"), [("q", "a", 1), ("z", "a", 1)]
        )
        self.write(
            self.j,
            ("query_id", "document_id", "relevant"),
            [("q", "a", 1), ("z", "a", 0)],
        )
        self.assertEqual(
            self.call(k=1)["macro"]["precision"], {"lower": 0.5, "upper": 0.5}
        )

    def test_examples_default_off_and_lexical_query_selection(self):
        self.assertNotIn("endpoint_examples", self.call()["queries"][0])
        self.write(
            self.u,
            ("query_id", "document_id"),
            [("z", "a")] + [("q", d) for d in "abcd"],
        )
        result = self.call(examples=1)
        self.assertEqual([q["query_id"] for q in result["queries"]], ["q", "z"])
        self.assertIn("endpoint_examples", result["queries"][0])
        self.assertNotIn("endpoint_examples", result["queries"][1])

    def test_permutation_byte_stability(self):
        baseline = json.dumps(self.call(examples=1), sort_keys=True)
        self.write(self.u, ("query_id", "document_id"), [("q", d) for d in "dcba"])
        self.write(
            self.r,
            ("query_id", "document_id", "rank"),
            [("q", d, i) for i, d in reversed(list(enumerate("abc", 1)))],
        )
        self.assertEqual(json.dumps(self.call(examples=1), sort_keys=True), baseline)


class ValidationTests(Fixture):
    def rejected(self, path, header, rows):
        self.write(path, header, rows)
        with self.assertRaises(BoundsError):
            self.call()

    def test_duplicate_universe(self):
        self.rejected(self.u, ("query_id", "document_id"), [("q", "a")] * 2)

    def test_empty_universe(self):
        self.rejected(self.u, ("query_id", "document_id"), [])

    def test_unknown_ranking_query(self):
        self.rejected(self.r, ("query_id", "document_id", "rank"), [("x", "a", 1)])

    def test_unknown_ranking_document(self):
        self.rejected(self.r, ("query_id", "document_id", "rank"), [("q", "x", 1)])

    def test_duplicate_rank(self):
        self.rejected(
            self.r, ("query_id", "document_id", "rank"), [("q", "a", 1), ("q", "b", 1)]
        )

    def test_duplicate_ranked_document(self):
        self.rejected(
            self.r, ("query_id", "document_id", "rank"), [("q", "a", 1), ("q", "a", 2)]
        )

    def test_gapped_ranks(self):
        self.rejected(self.r, ("query_id", "document_id", "rank"), [("q", "a", 2)])

    def test_bad_ranks(self):
        for rank in ("0", "-1", "+1", "1.0", "１", "9" * 10000):
            with self.subTest(rank=rank[:10]):
                self.rejected(
                    self.r, ("query_id", "document_id", "rank"), [("q", "a", rank)]
                )

    def test_duplicate_judgments_even_equal(self):
        self.rejected(
            self.j, ("query_id", "document_id", "relevant"), [("q", "b", 1)] * 2
        )

    def test_conflicting_judgments(self):
        self.rejected(
            self.j,
            ("query_id", "document_id", "relevant"),
            [("q", "b", 1), ("q", "b", 0)],
        )

    def test_bad_judgments(self):
        for rel in ("-1", "2", "0.5", "true", "１"):
            with self.subTest(rel=rel):
                self.rejected(
                    self.j, ("query_id", "document_id", "relevant"), [("q", "b", rel)]
                )

    def test_unknown_judgment(self):
        self.rejected(self.j, ("query_id", "document_id", "relevant"), [("q", "x", 1)])

    def test_unknown_judgment_query(self):
        self.rejected(self.j, ("query_id", "document_id", "relevant"), [("x", "a", 1)])

    def test_wrong_header(self):
        for header in (
            ("document_id", "query_id"),
            ("query_id", "document_id", "extra"),
            ("query_id", "query_id"),
        ):
            with self.subTest(header=header):
                self.rejected(self.u, header, [])

    def test_empty_file(self):
        self.u.write_text("")
        with self.assertRaises(BoundsError):
            self.call()

    def test_row_widths(self):
        for row in (("q",), ("q", "a", "extra"), ()):
            with self.subTest(row=row):
                self.rejected(self.u, ("query_id", "document_id"), [row])

    def test_empty_whitespace_nul_cells(self):
        for cell in ("", " a", "a ", " "):
            with self.subTest(cell=cell):
                self.rejected(self.u, ("query_id", "document_id"), [("q", cell)])

    def test_nul_cell(self):
        self.u.write_bytes(b"query_id,document_id\nq,a\x00b\n")
        with self.assertRaises(BoundsError):
            self.call()

    def test_malformed_csv(self):
        self.u.write_text('query_id,document_id\nq,"unclosed\n')
        with self.assertRaises(BoundsError):
            self.call()

    def test_invalid_utf8(self):
        self.u.write_bytes(b"query_id,document_id\nq,\xff\n")
        with self.assertRaises(BoundsError):
            self.call()

    def test_missing_file(self):
        self.u.unlink()
        with self.assertRaises(BoundsError):
            self.call()

    def test_bom_and_quoted_unicode_identifiers(self):
        docs = ["a,b", 'quote"doc', "資料"]
        self.write(self.u, ("query_id", "document_id"), [("q", d) for d in docs])
        self.u.write_bytes(b"\xef\xbb\xbf" + self.u.read_bytes())
        self.write(self.r, ("query_id", "document_id", "rank"), [])
        self.write(self.j, ("query_id", "document_id", "relevant"), [])
        self.assertEqual(self.call()["queries"][0]["universe_documents"], 3)

    def test_case_sensitive_ids(self):
        self.rejected(self.r, ("query_id", "document_id", "rank"), [("Q", "a", 1)])

    def test_totals_missing_query(self):
        self.write(self.t, ("query_id", "total_relevant"), [])
        with self.assertRaises(BoundsError):
            self.call(totals=self.t)

    def test_totals_duplicate(self):
        self.write(self.t, ("query_id", "total_relevant"), [("q", 1)] * 2)
        with self.assertRaises(BoundsError):
            self.call(totals=self.t)

    def test_totals_unknown(self):
        self.write(self.t, ("query_id", "total_relevant"), [("x", 1)])
        with self.assertRaises(BoundsError):
            self.call(totals=self.t)

    def test_total_below_known_positive(self):
        with self.assertRaises(BoundsError):
            self.call(totals=self.total(0))

    def test_total_above_universe(self):
        with self.assertRaises(BoundsError):
            self.call(totals=self.total(5))

    def test_total_contradicts_known_negative(self):
        self.write(
            self.j,
            ("query_id", "document_id", "relevant"),
            [("q", "a", 0), ("q", "b", 1)],
        )
        with self.assertRaises(BoundsError):
            self.call(totals=self.total(4))

    def test_option_validation(self):
        for kw in (
            {"k": 0},
            {"k": True},
            {"k": 1.0},
            {"k": 10**500},
            {"examples": -1},
            {"examples": 21},
            {"examples": True},
            {"max_rows": 0},
            {"max_work": 0},
        ):
            with self.subTest(kw=str(kw)[:50]):
                with self.assertRaises(BoundsError):
                    self.call(**kw)

    def test_row_cap_boundary(self):
        self.assertEqual(self.call(max_rows=4)["query_count"], 1)
        with self.assertRaises(BoundsError):
            self.call(max_rows=3)

    def test_work_cap_boundary(self):
        work = self.call()["scoring_work_units"]
        try:
            self.call(max_work=work)
        except BoundsError as exc:
            self.fail("exact work boundary must be accepted: " + str(exc))
        with self.assertRaises(BoundsError):
            self.call(max_work=work - 1)

    def test_ranking_rows_after_cutoff_still_validated(self):
        self.write(
            self.r, ("query_id", "document_id", "rank"), [("q", "a", 1), ("q", "x", 2)]
        )
        with self.assertRaises(BoundsError):
            self.call(k=1)

    def test_no_id_or_path_in_errors(self):
        self.u.rename(self.root / "secret.csv")
        with self.assertRaises(BoundsError) as raised:
            self.call()
        self.assertNotIn(str(self.root), str(raised.exception))
        self.assertNotIn("universe.csv", str(raised.exception))


class CliTests(Fixture):
    def args(self):
        return [
            "--universe",
            str(self.u),
            "--ranking",
            str(self.r),
            "--judgments",
            str(self.j),
            "--k",
            "3",
        ]

    def invoke(self, args):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = main(args)
        return code, out.getvalue(), err.getvalue()

    def test_success_json(self):
        code, out, err = self.invoke(self.args())
        self.assertEqual(code, 0)
        self.assertFalse(err)
        self.assertEqual(json.loads(out), self.call())

    def test_failure_no_partial_json(self):
        self.total(0)
        code, out, err = self.invoke(self.args() + ["--totals", str(self.t)])
        self.assertEqual(code, 2)
        self.assertEqual(out, "")
        self.assertIn("contradicts", err)
        self.assertNotIn("Traceback", err)

    def test_cli_examples(self):
        code, out, err = self.invoke(self.args() + ["--examples", "1"])
        self.assertEqual(code, 0)
        self.assertIn("endpoint_examples", json.loads(out)["queries"][0])

    def test_cli_invalid_budget(self):
        code, out, err = self.invoke(self.args() + ["--max-work", "1"])
        self.assertEqual((code, out), (2, ""))

    def test_module_and_hashseed_stability(self):
        outs = []
        for seed in ("0", "1", "927"):
            env = dict(os.environ, PYTHONHASHSEED=seed)
            p = subprocess.run(
                [sys.executable, "-m", "rankbounds"]
                + self.args()
                + ["--examples", "1"],
                env=env,
                capture_output=True,
                text=True,
            )
            self.assertEqual(p.returncode, 0, p.stderr)
            self.assertFalse(p.stderr)
            outs.append(p.stdout)
        self.assertEqual(len(set(outs)), 1)


if __name__ == "__main__":
    unittest.main()
