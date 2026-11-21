"""Mask solver compatibility and operation-count regressions."""

import itertools
import random
import unittest
from unittest.mock import patch

import rankbounds.reciprocal as rr


def literal(left, right, labels, size, total):
    unknown = sorted(set(left) | set(right) | set(labels))
    unknown = [doc for doc in unknown if doc not in labels]
    outside = size - len(labels) - len(unknown)
    known = {doc for doc, value in labels.items() if value}
    scores = []
    for mask in itertools.product((0, 1), repeat=len(unknown)):
        selected = known | {doc for doc, value in zip(unknown, mask) if value}
        low, high = len(selected), len(selected) + outside
        if total is not None:
            a, b = total if isinstance(total, tuple) else (total, total)
            low, high = max(low, a), min(high, b)
        if low > high:
            continue
        values = [
            next((1 / rank for rank, doc in enumerate(run, 1) if doc in selected), 0.0)
            for run in (left, right)
        ]
        scores.append(values[0] - values[1])
    return {"lower": min(scores), "upper": max(scores)}


class MaskTests(unittest.TestCase):
    def test_independent_completions_with_count_ranges_and_outside(self):
        rng = random.Random(784321)
        for case in range(350):
            docs = [str(i) for i in range(rng.randint(1, 8))]
            left, right = [
                rng.sample(docs, rng.randrange(len(docs) + 1)) for _ in range(2)
            ]
            labels = {doc: rng.randrange(2) for doc in docs if rng.randrange(3) == 0}
            a = rng.randint(
                sum(labels.values()), len(docs) - len(labels) + sum(labels.values())
            )
            b = rng.randint(a, len(docs) - len(labels) + sum(labels.values()))
            for total in (None, a, (a, b)):
                with self.subTest(case=case, total=total):
                    result, witnesses = rr._reciprocal_bounds(
                        left, right, labels, len(docs), total, True
                    )
                    self.assertEqual(
                        result, literal(left, right, labels, len(docs), total)
                    )
                    for direction, witness in witnesses.items():
                        selected = set(witness["unjudged_union_relevant"])
                        positive = selected | {doc for doc in labels if labels[doc]}
                        relevant = (
                            len(positive)
                            + witness["unjudged_outside_union_relevant_count"]
                        )
                        self.assertEqual(relevant, witness["total_relevant"])
                        if total is not None:
                            low, high = (
                                total if isinstance(total, tuple) else (total, total)
                            )
                            self.assertLessEqual(low, relevant)
                            self.assertLessEqual(relevant, high)
                        values = [
                            next(
                                (
                                    1 / rank
                                    for rank, doc in enumerate(run, 1)
                                    if doc in positive
                                ),
                                0.0,
                            )
                            for run in (left, right)
                        ]
                        self.assertEqual(result[direction], values[0] - values[1])
                        self.assertLessEqual(
                            witness["unjudged_outside_union_relevant_count"],
                            len(docs) - len(set(left) | set(right) | set(labels)),
                        )

    def test_native_and_python39_popcount_paths_identical(self):
        args = (
            ["a", "b", "c"],
            ["d", "c", "a"],
            {"b": 0, "z": 1},
            1_000_000,
            (5, 500_000),
            True,
        )
        native = rr._reciprocal_bounds(*args)
        with patch.object(rr, "_NATIVE_POPCOUNT", None):
            self.assertEqual(rr._reciprocal_bounds(*args), native)
            for value in (0, 1, 2**129 + 2**65 + 1):
                self.assertEqual(rr._count_bits(value), bin(value).count("1"))
        self.assertEqual(native[1]["lower"]["total_relevant"], 5)

    def test_multiword_masks_with_overlap_and_outside_known_labels(self):
        docs = ["doc" + str(i) for i in range(180)]
        labels = {doc: i % 2 for i, doc in enumerate(docs) if i % 11 == 0}
        labels["outside"] = 1
        args = (docs[:130], docs[50:][::-1], labels, 1_000_000, (100, 500_000), True)
        native = rr._reciprocal_bounds(*args)
        with patch.object(rr, "_NATIVE_POPCOUNT", None):
            self.assertEqual(rr._reciprocal_bounds(*args), native)
        swapped = rr._reciprocal_bounds(args[1], args[0], *args[2:])[0]
        self.assertEqual(native[0]["lower"], -swapped["upper"])
        self.assertEqual(native[0]["upper"], -swapped["lower"])

    def test_document_hashing_not_repeated_per_first_hit_pair(self):
        class Counted(str):
            calls = 0

            def __hash__(self):
                Counted.calls += 1
                return super().__hash__()

        docs = [Counted(str(i)) for i in range(40)]
        left, right = docs[:20], docs[20:]
        Counted.calls = 0
        result, _ = rr._reciprocal_bounds(left, right, {}, 40, None, True)
        self.assertEqual(result, {"lower": -1.0, "upper": 1.0})
        # Baseline repeatedly hashes thousands of prefix/eligible IDs. A dense
        # mask solver hashes only while building inputs and final witnesses.
        self.assertLess(Counted.calls, 1200)

    def test_no_examples_omits_expansion_and_same_tie_order(self):
        args = (["b", "a"], ["a", "c"], {}, 5, 4)
        result, witness = rr._reciprocal_bounds(*args, True)
        self.assertEqual(rr._reciprocal_bounds(*args, False), (result, {}))
        self.assertEqual(witness["lower"]["unjudged_union_relevant"], ["a", "c"])
        self.assertEqual(witness["lower"]["unjudged_outside_union_relevant_count"], 2)


if __name__ == "__main__":
    unittest.main()
