"""Read-only local CSV command line."""

import argparse
import json
import sys

from .core import BoundsError, audit
from .paired import compare


def _write_text(stream, text):
    if stream is None:
        raise OSError("output stream is unavailable")
    written = stream.write(text)
    if type(written) is not int or written != len(text):
        raise OSError("output stream did not accept the complete text")
    stream.flush()


class _ArgumentParser(argparse.ArgumentParser):
    def _print_message(self, message, file=None):
        # Recent argparse versions suppress immediate write errors. Keep them
        # visible to main's error boundary, including unbuffered --help output.
        if message:
            _write_text(sys.stderr if file is None else file, message)


def _error(message):
    """Diagnostics are best effort; a broken stderr must not hide failure."""
    try:
        _write_text(sys.stderr, "rankbounds: " + message + "\n")
    except (OSError, ValueError):
        pass
    return 2


def _parser():
    parser = _ArgumentParser(
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
        help="CSV query_id,document_id for hypothetical own-query judgment values",
    )
    parser.add_argument("--k", type=int, required=True)
    parser.add_argument("--examples", type=int, default=0)
    parser.add_argument("--max-rows", type=int, default=1_000_000)
    parser.add_argument("--max-work", type=int, default=5_000_000)
    return parser


def main(argv=None):
    try:
        args = _parser().parse_args(argv)
    except (OSError, ValueError) as exc:
        return _error("output failed: " + str(exc))
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
        return _error(str(exc))
    payload = json.dumps(report, sort_keys=True, indent=2, allow_nan=False) + "\n"
    try:
        _write_text(sys.stdout, payload)
    except (OSError, ValueError) as exc:
        return _error("output failed: " + str(exc))
    return 0


def cli(argv=None):
    """Process entry point, including help/error exits and final stream flushes."""
    try:
        status = main(argv)
    except SystemExit as exc:
        status = exc.code if isinstance(exc.code, int) else 0 if exc.code is None else 1
    for name in ("stdout", "stderr"):
        stream = getattr(sys, name)
        if stream is None:
            continue
        try:
            stream.flush()
        except (OSError, ValueError) as exc:
            if name == "stdout" and status == 0:
                _error("output failed: " + str(exc))
            # This wrapper is only for the terminating CLI process. Do not let
            # Python retry a failed flush at shutdown and replace exit 2 with 120.
            setattr(sys, name, None)
            status = 2
    return status


if __name__ == "__main__":
    sys.exit(cli())
