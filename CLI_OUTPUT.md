# CLI output handling

On a report command, exit 0 means the CLI rendered one report, its text stream
accepted every character, and an explicit flush completed. Successful `--help`
retains its usual exit 0, without a JSON report. The report bytes, indentation,
trailing newline and metric semantics are unchanged. Both `rankbounds` and
`python -m rankbounds` use the same process entry point. Parser help/error messages
also use checked writes, so immediate unbuffered failures cannot be hidden by
argparse's own error suppression.

A short or invalid write count, unavailable/closed stdout, write error, or delayed
flush error returns exit 2. The CLI does not retry a partial write: a stream might
already have accepted part of the report, and retrying could duplicate data.
Discard stdout whenever the exit status is nonzero. This is not atomic output,
a storage-durability guarantee, or proof that a downstream consumer read or
accepted the JSON. For durable reports, callers must also manage their destination
and its own storage/transaction rules.

Input errors still produce no report and return exit 2. Error diagnostics are
best effort. A closed/full/unavailable stderr must not turn a failure into success
or cause a diagnostic traceback.

## Library calls and process shutdown

`rankbounds.__main__.main(argv)` borrows the caller's streams. It checks report
writes and flushes, but never closes or replaces either stream. It retains the
usual `argparse` `SystemExit` behavior for help and argument errors. The `audit`
and `compare` Python APIs are unchanged and do not write reports.

The console script and module launcher call `cli(argv)` instead. This process-only
wrapper also handles help/argument-error exits and final standard-stream flushes.
When a flush fails, it disables that failed standard-stream slot for the process
that is about to exit. This prevents Python's shutdown retry from replacing the
chosen exit 2 with exit 120 or printing an ignored-flush traceback. Do not use
`cli` as an embedding API: use `main`, `audit`, or `compare` instead.

## Checks

`tests/test_cli_output.py` checks unchanged single-run/paired JSON, short and
invalid write counts, immediate and delayed errors, absent/closed streams,
best-effort diagnostics and borrowed-stream ownership. Subprocess checks cover
both launchers against a readerless pipe. On systems with `/dev/full`, they also
cover full report/help output and full argument-error diagnostics. Report/help
failures are checked with default buffering, `-u`, and `PYTHONUNBUFFERED=1`.
Neutral installed-wheel runs exercise the actual console-script file on POSIX,
not only an emulated entry-point import. These are
output-contract checks, not additional mathematical-oracle tests or proof of
all platform/stream implementations.
