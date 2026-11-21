"""Bit-tagged AP scoring must preserve every score term and lexical witness."""

import math
import unittest

import rankbounds.average_precision as ap


class APBitTests(unittest.TestCase):
    def test_rank_terms_match_literal_membership_for_every_mask(self):
        # Zero tags are judged negatives; bit 16 is the always-positive tag.
        tags = [16, 1, 0, 8, 2, 16, 4]
        for mask in range(16):
            hits = 0
            terms = []
            for rank, tag in enumerate(tags, 1):
                if tag == 16 or (tag and mask & tag):
                    hits += 1
                    terms.append(hits / rank)
            self.assertEqual(ap._ap_numerator(tags, mask | 16), math.fsum(terms))
        self.assertEqual(ap._ap_numerator([], 1), 0.0)

    def test_known_outside_labels_do_not_become_top_hits(self):
        bounds, witnesses = ap._average_precision_bounds(
            ["a", "no", "b"], ["b", "a"], {"no": 0, "elsewhere": 1}, 5, 1, True
        )
        self.assertEqual(bounds, {"lower": 0.0, "upper": 0.0})
        for witness in witnesses.values():
            self.assertEqual(witness["unjudged_union_relevant"], [])
            self.assertEqual(witness["total_relevant"], 1)
            self.assertEqual(witness["left_score"], 0.0)
            self.assertEqual(witness["right_score"], 0.0)

    def test_zero_unknown_still_scores_fixed_positives(self):
        result, witnesses = ap._average_precision_bounds(
            ["a", "b"], ["b", "a"], {"a": 1, "b": 0}, 2, 1, True
        )
        self.assertEqual(result, {"lower": 0.5, "upper": 0.5})
        for witness in witnesses.values():
            self.assertEqual(witness["unjudged_union_relevant"], [])
            self.assertEqual(witness["left_score"], 1.0)
            self.assertEqual(witness["right_score"], 0.5)

    def test_identical_runs_keep_first_numeric_mask_witness(self):
        _, witnesses = ap._average_precision_bounds(
            ["b", "a", "c"], ["b", "a", "c"], {}, 4, (1, 2), True
        )
        for witness in witnesses.values():
            self.assertEqual(witness["unjudged_union_relevant"], [])
            self.assertEqual(witness["unjudged_outside_union_relevant_count"], 1)
            self.assertEqual(witness["total_relevant"], 1)

    def test_broad_ranges_do_not_hash_labels_per_subset(self):
        class Counted(str):
            calls = 0

            def __hash__(self):
                Counted.calls += 1
                return super().__hash__()

        docs = [Counted(str(i)) for i in range(12)]
        Counted.calls = 0
        bounds, witnesses = ap._average_precision_bounds(
            docs, docs[::-1], {}, 12, None, False
        )
        self.assertLess(Counted.calls, 500)
        self.assertLess(bounds["lower"], 0)
        self.assertGreater(bounds["upper"], 0)
        self.assertEqual(witnesses, {})


if __name__ == "__main__":
    unittest.main()
