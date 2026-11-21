"""Read-only local CSV command line."""

import argparse
import json
import sys

from .core import BoundsError, audit
from .paired import compare


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Binary retrieval metric compatibility intervals, not confidence intervals."
    )
    parser.add_argument("--universe", required=True)
    parser.add_argument("--ranking", required=True)
    parser.add_argument("--judgments", required=True)
    parser.add_argument(
        "--comparison-ranking",
        help="Right ranking for shared-label left-minus-right bounds",
    )
    parser.add_argument(
        "--paired-rr",
        action="store_true",
        help="Also bound paired reciprocal rank; requires --comparison-ranking",
    )
    parser.add_argument(
        "--paired-ap",
        action="store_true",
        help="Also bound paired AP/total-R by budgeted enumeration; requires --comparison-ranking",
    )
    constraints = parser.add_mutually_exclusive_group()
    constraints.add_argument("--totals")
    constraints.add_argument("--total-ranges")
    parser.add_argument(
        "--query-weights",
        help="CSV query_id,weight for an additional fixed-weight aggregate",
    )
    parser.add_argument(
        "--judgment-candidates",
        help="CSV query_id,document_id for single-run hypothetical judgment values",
    )
    parser.add_argument("--k", type=int, required=True)
    parser.add_argument("--examples", type=int, default=0)
    parser.add_argument("--max-rows", type=int, default=1_000_000)
    parser.add_argument("--max-work", type=int, default=5_000_000)
    args = parser.parse_args(argv)
    try:
        if args.paired_rr and not args.comparison_ranking:
            raise BoundsError("--paired-rr requires --comparison-ranking")
        if args.paired_ap and not args.comparison_ranking:
            raise BoundsError("--paired-ap requires --comparison-ranking")
        options = (
            {"include_rr": args.paired_rr, "include_ap": args.paired_ap}
            if args.comparison_ranking
            else {}
        )
        if args.judgment_candidates is not None:
            if args.comparison_ranking:
                raise BoundsError("--judgment-candidates requires single-run mode")
            options["judgment_candidates"] = args.judgment_candidates
        function = compare if args.comparison_ranking else audit
        inputs = [args.universe, args.ranking]
        if args.comparison_ranking:
            inputs.append(args.comparison_ranking)
        inputs.append(args.judgments)
        report = function(
            *inputs,
            k=args.k,
            totals=args.totals,
            total_ranges=args.total_ranges,
            query_weights=args.query_weights,
            examples=args.examples,
            max_rows=args.max_rows,
            max_work=args.max_work,
            **options,
        )
    except BoundsError as exc:
        print("rankbounds: " + str(exc), file=sys.stderr)
        return 2
    print(json.dumps(report, sort_keys=True, indent=2, allow_nan=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
