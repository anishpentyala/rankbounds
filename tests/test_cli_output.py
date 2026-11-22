"""Report success must mean the complete JSON reached a flushed text stream."""

import errno
import importlib.metadata
import io
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import sysconfig
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout

import rankbounds
from rankbounds import audit, compare
from rankbounds.__main__ import main


class CountStream(io.StringIO):
    def __init__(self, count):
        super().__init__()
        self.count = count

    def write(self, text):
        result = self.count(text)
        accepted = result if type(result) is int else 0
        super().write(text[: max(0, min(len(text), accepted))])
        return result


class FailingStream(io.StringIO):
    def __init__(self, stage, failure):
        super().__init__()
        self.stage = stage
        self.failure = failure

    def write(self, text):
        if self.stage == "write":
            raise self.failure
        return super().write(text)

    def flush(self):
        if self.stage == "flush":
            raise self.failure
        return super().flush()


class CLIOutputTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.universe = root / "universe.csv"
        self.left = root / "left.csv"
        self.right = root / "right.csv"
        self.judgments = root / "judgments.csv"
        self.universe.write_text(
            "query_id,document_id\nq,a\nq,b\nq,c\n", encoding="utf-8"
        )
        self.left.write_text(
            "query_id,document_id,rank\nq,a,1\nq,b,2\n", encoding="utf-8"
        )
        self.right.write_text(
            "query_id,document_id,rank\nq,c,1\nq,a,2\n", encoding="utf-8"
        )
        self.judgments.write_text(
            "query_id,document_id,relevant\nq,a,1\n", encoding="utf-8"
        )
        self.args = [
            "--universe",
            str(self.universe),
            "--ranking",
            str(self.left),
            "--judgments",
            str(self.judgments),
            "--k",
            "2",
        ]

    def invoke(self, out, extra=(), err=None):
        if err is None:
            err = io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            try:
                status = main(self.args + list(extra))
            except Exception as exc:
                status = type(exc).__name__
        return status, err

    def test_complete_output_matches_api_single_and_paired(self):
        cases = [
            ([], audit(self.universe, self.left, self.judgments, k=2)),
            (
                ["--comparison-ranking", str(self.right)],
                compare(self.universe, self.left, self.right, self.judgments, k=2),
            ),
            (
                ["--comparison-ranking", str(self.right), "--paired-rr", "--paired-ap"],
                compare(
                    self.universe,
                    self.left,
                    self.right,
                    self.judgments,
                    k=2,
                    include_rr=True,
                    include_ap=True,
                ),
            ),
        ]
        for extra, expected in cases:
            with self.subTest(extra=extra):
                out = io.StringIO()
                status, err = self.invoke(out, extra)
                self.assertEqual(status, 0)
                self.assertEqual(err.getvalue(), "")
                expected_text = (
                    json.dumps(expected, sort_keys=True, indent=2, allow_nan=False)
                    + "\n"
                )
                self.assertEqual(out.getvalue(), expected_text)
                self.assertEqual(json.loads(out.getvalue()), expected)
                self.assertFalse(out.closed)

    def test_short_writes_do_not_report_success(self):
        for count in [0, 1, 7]:
            with self.subTest(count=count):
                out = CountStream(lambda text: min(count, len(text)))
                status, err = self.invoke(out)
                self.assertEqual(status, 2)
                self.assertIn("output", err.getvalue().lower())
                self.assertFalse(out.closed)
        status, _ = self.invoke(CountStream(lambda text: len(text) - 1))
        self.assertEqual(status, 2)

    def test_invalid_write_counts_do_not_report_success(self):
        for count in [None, True, False, -1, 1.0, "1"]:
            with self.subTest(count=count):
                status, _ = self.invoke(CountStream(lambda text: count))
                self.assertEqual(status, 2)
        status, _ = self.invoke(CountStream(lambda text: len(text) + 1))
        self.assertEqual(status, 2)

    def test_write_errors_are_returned_without_replacing_caller_streams(self):
        for failure in [
            BrokenPipeError(errno.EPIPE, "closed pipe"),
            OSError(errno.EIO, "write failed"),
            ValueError("closed stream"),
        ]:
            with self.subTest(failure=type(failure).__name__):
                out = FailingStream("write", failure)
                before_out, before_err = sys.stdout, sys.stderr
                status, err = self.invoke(out)
                self.assertEqual(status, 2)
                self.assertIn("output", err.getvalue().lower())
                self.assertFalse(out.closed)
                self.assertIs(sys.stdout, before_out)
                self.assertIs(sys.stderr, before_err)

    def test_delayed_flush_errors_do_not_report_success(self):
        for failure in [
            OSError(errno.ENOSPC, "full output"),
            ValueError("closed stream"),
        ]:
            with self.subTest(failure=type(failure).__name__):
                out = FailingStream("flush", failure)
                status, _ = self.invoke(out)
                self.assertEqual(status, 2)
                self.assertTrue(out.getvalue())
                self.assertFalse(out.closed)

    def test_missing_standard_streams_still_return_failure(self):
        with redirect_stdout(None), redirect_stderr(None):
            try:
                status = main(self.args)
            except Exception as exc:
                status = type(exc).__name__
        self.assertEqual(status, 2)

    def test_closed_stdout_is_an_output_error(self):
        out = io.StringIO()
        out.close()
        status, err = self.invoke(out)
        self.assertEqual(status, 2)
        self.assertIn("output", err.getvalue().lower())

    def test_failed_diagnostic_does_not_hide_failure_status(self):
        for stage in ["write", "flush"]:
            with self.subTest(stage=stage):
                out = FailingStream("write", BrokenPipeError())
                err = FailingStream(stage, OSError(errno.ENOSPC, "full diagnostic"))
                status, _ = self.invoke(out, err=err)
                self.assertEqual(status, 2)

    def test_input_errors_still_write_no_report(self):
        self.judgments.write_text(
            "query_id,document_id,relevant\nq,a,3\n", encoding="utf-8"
        )
        out = io.StringIO()
        status, err = self.invoke(out)
        self.assertEqual(status, 2)
        self.assertEqual(out.getvalue(), "")
        self.assertTrue(err.getvalue())
        status, _ = self.invoke(out, err=FailingStream("flush", OSError()))
        self.assertEqual(status, 2)

    def test_help_checks_message_writes(self):
        streams = [
            CountStream(lambda text: 0),
            CountStream(lambda text: min(7, len(text))),
            CountStream(lambda text: None),
            CountStream(lambda text: True),
            CountStream(lambda text: len(text) + 1),
            FailingStream("write", OSError(errno.ENOSPC, "full help output")),
            FailingStream("flush", OSError(errno.ENOSPC, "full help output")),
        ]
        for index, stream in enumerate(streams):
            with self.subTest(stream=index):
                err = io.StringIO()
                with redirect_stdout(stream), redirect_stderr(err):
                    try:
                        status = main(["--help"])
                    except SystemExit as exc:
                        status = exc.code
                    except Exception as exc:
                        status = type(exc).__name__
                self.assertEqual(status, 2)
                self.assertIn("output", err.getvalue().lower())
                self.assertFalse(stream.closed)
        out = io.StringIO()
        with redirect_stdout(out), redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit) as caught:
                main(["--help"])
        self.assertEqual(caught.exception.code, 0)
        self.assertIn("usage:", out.getvalue())

    def launchers(self):
        project = Path(__file__).resolve().parents[1] / "pyproject.toml"
        if project.is_file():
            entry = re.search(
                r'^rankbounds\s*=\s*"([^"]+)"', project.read_text(), re.M
            ).group(1)
        else:
            entry = next(
                point.value
                for point in importlib.metadata.distribution("rankbounds").entry_points
                if point.group == "console_scripts" and point.name == "rankbounds"
            )
            self.assertEqual(entry, "rankbounds.__main__:cli")
            if os.name != "nt":
                script = Path(sysconfig.get_path("scripts")) / "rankbounds"
                self.assertTrue(script.is_file(), "installed console script is missing")
                return [
                    [sys.executable, "-m", "rankbounds"],
                    [sys.executable, str(script)],
                ]
        module, name = entry.split(":")
        code = (
            "import importlib,sys; "
            "module=sys.argv.pop(1); name=sys.argv.pop(1); "
            "sys.exit(getattr(importlib.import_module(module),name)())"
        )
        return [
            [sys.executable, "-m", "rankbounds"],
            [sys.executable, "-c", code, module, name],
        ]

    def subprocess_env(self):
        return dict(
            os.environ, PYTHONPATH=str(Path(rankbounds.__file__).resolve().parents[1])
        )

    def buffering_mode(self, launcher, mode):
        command = list(launcher)
        env = self.subprocess_env()
        env.pop("PYTHONUNBUFFERED", None)
        if mode == "flag":
            command.insert(1, "-u")
        elif mode == "environment":
            env["PYTHONUNBUFFERED"] = "1"
        return command, env

    @unittest.skipUnless(Path("/dev/full").exists(), "requires /dev/full")
    def test_real_full_output_and_help_exit_two_without_shutdown_traceback(self):
        for launcher in self.launchers():
            for args in [self.args, ["--help"]]:
                for buffering in ["default", "flag", "environment"]:
                    command, env = self.buffering_mode(launcher, buffering)
                    with self.subTest(
                        launcher=launcher[:3], args=args, buffering=buffering
                    ):
                        with open("/dev/full", "w", encoding="utf-8") as full:
                            result = subprocess.run(
                                command + args,
                                stdout=full,
                                stderr=subprocess.PIPE,
                                text=True,
                                env=env,
                                timeout=10,
                            )
                        self.assertEqual(result.returncode, 2, result.stderr)
                        self.assertNotIn("Traceback", result.stderr)
                        self.assertNotIn("Exception ignored", result.stderr)

    @unittest.skipUnless(hasattr(os, "pipe"), "requires pipes")
    def test_real_closed_pipe_exits_two_without_shutdown_traceback(self):
        for launcher in self.launchers():
            for args in [self.args, ["--help"]]:
                for buffering in ["default", "flag", "environment"]:
                    command, env = self.buffering_mode(launcher, buffering)
                    with self.subTest(
                        launcher=launcher[:3], args=args, buffering=buffering
                    ):
                        read_fd, write_fd = os.pipe()
                        os.close(read_fd)
                        try:
                            result = subprocess.run(
                                command + args,
                                stdout=write_fd,
                                stderr=subprocess.PIPE,
                                text=True,
                                env=env,
                                timeout=10,
                            )
                        finally:
                            os.close(write_fd)
                        self.assertEqual(result.returncode, 2, result.stderr)
                        self.assertNotIn("Traceback", result.stderr)
                        self.assertNotIn("Exception ignored", result.stderr)

    @unittest.skipUnless(Path("/dev/full").exists(), "requires /dev/full")
    def test_real_full_diagnostic_stays_exit_two(self):
        for launcher in self.launchers():
            with self.subTest(launcher=launcher[:3]):
                with open("/dev/full", "w", encoding="utf-8") as full:
                    result = subprocess.run(
                        launcher,
                        stdout=subprocess.PIPE,
                        stderr=full,
                        text=True,
                        env=self.subprocess_env(),
                        timeout=10,
                    )
                self.assertEqual(result.returncode, 2)
                self.assertEqual(result.stdout, "")
