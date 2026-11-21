"""Feasible-cardinality pruning without changing AP mask order or witnesses."""

import itertools
import math
import random
import unittest

import rankbounds.average_precision as ap


def literal(left, right, labels, size, total):
    unknown = sorted((set(left) | set(right)) - set(labels))
    outside = size - len(labels) - len(unknown)
    fixed = {doc for doc, value in labels.items() if value}
    values = []
    for bits in itertools.product((0, 1), repeat=len(unknown)):
        selected = fixed | {doc for doc, bit in zip(unknown, bits) if bit}
        for outside_count in range(outside + 1):
            relevant = len(selected) + outside_count
            if total is not None:
                low, high = total if isinstance(total, tuple) else (total, total)
                if not low <= relevant <= high:
                    continue
            scores = []
            for run in (left, right):
                hits = 0
                terms = []
                for rank, doc in enumerate(run, 1):
                    if doc in selected:
                        hits += 1
                        terms.append(hits / rank)
                scores.append(math.fsum(terms) / relevant if relevant else 0.0)
            values.append(scores[0] - scores[1])
    return {"lower": min(values), "upper": max(values)}


class APPruningTests(unittest.TestCase):
    def test_every_small_count_interval_preserves_integer_mask_order(self):
        for width in range(10):
            for low in range(width + 1):
                for high in range(low, width + 1):
                    expected = [
                        mask
                        for mask in range(1 << width)
                        if low <= bin(mask).count("1") <= high
                    ]
                    self.assertEqual(
                        list(ap._feasible_masks(width, low, high)), expected
                    )
        self.assertEqual(list(ap._feasible_masks(28, 0, 0)), [0])
        self.assertEqual(list(ap._feasible_masks(28, 28, 28)), [(1 << 28) - 1])

    def test_independent_full_labels_and_outside_count_oracle(self):
        rng = random.Random(147215)
        for case in range(260):
            docs = [str(i) for i in range(rng.randint(1, 8))]
            left, right = [
                rng.sample(docs, rng.randrange(len(docs) + 1)) for _ in range(2)
            ]
            labels = {doc: rng.randrange(2) for doc in docs if rng.randrange(3) == 0}
            low = rng.randint(
                sum(labels.values()), len(docs) - len(labels) + sum(labels.values())
            )
            high = rng.randint(low, len(docs) - len(labels) + sum(labels.values()))
            for total in (None, low, (low, high)):
                with self.subTest(case=case, total=total):
                    bounds, witnesses = ap._average_precision_bounds(
                        left, right, labels, len(docs), total, True
                    )
                    self.assertEqual(
                        bounds, literal(left, right, labels, len(docs), total)
                    )
                    for direction, witness in witnesses.items():
                        selected = set(witness["unjudged_union_relevant"])
                        self.assertFalse(selected & set(labels))
                        self.assertLessEqual(selected, set(left) | set(right))
                        relevant = (
                            sum(labels.values())
                            + len(selected)
                            + witness["unjudged_outside_union_relevant_count"]
                        )
                        self.assertEqual(relevant, witness["total_relevant"])
                        self.assertGreaterEqual(
                            witness["unjudged_outside_union_relevant_count"], 0
                        )
                        self.assertLessEqual(
                            witness["unjudged_outside_union_relevant_count"],
                            len(docs) - len(set(left) | set(right) | set(labels)),
                        )
                        if total is not None:
                            a, b = total if isinstance(total, tuple) else (total, total)
                            self.assertLessEqual(a, relevant)
                            self.assertLessEqual(relevant, b)
                        self.assertEqual(
                            bounds[direction],
                            witness["left_score"] - witness["right_score"],
                        )

    def test_zero_total_skips_impossible_label_set_construction(self):
        class Counted(str):
            calls = 0

            def __hash__(self):
                Counted.calls += 1
                return super().__hash__()

        docs = [Counted(str(i)) for i in range(14)]
        Counted.calls = 0
        result = ap._average_precision_bounds(docs, docs[::-1], {}, 14, 0, True)
        self.assertEqual(result[0], {"lower": 0.0, "upper": 0.0})
        self.assertLess(Counted.calls, 500)

    def test_counts_include_fixed_and_free_outside_documents(self):
        args = (["a", "b"], ["b", "c"], {"outside": 1, "a": 0}, 8, (4, 5))
        bounds, witnesses = ap._average_precision_bounds(*args, True)
        self.assertEqual(bounds, literal(*args))
        self.assertEqual(ap._average_precision_bounds(*args, False), (bounds, {}))
        for witness in witnesses.values():
            self.assertIn(witness["total_relevant"], (4, 5))


if __name__ == "__main__":
    unittest.main()
