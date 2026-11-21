"""Refuse special CSV files without waiting for a producer."""

import io
import os
import socket
import subprocess
import sys
import unittest
from contextlib import redirect_stderr, redirect_stdout
from unittest.mock import patch

from rankbounds import BoundsError, audit, compare
from rankbounds.__main__ import main
from rankbounds.core import _rows
from test_bounds import Fixture


class RegularInputTests(Fixture):
    def test_regular_file_and_regular_symlink_keep_reports(self):
        before = self.call()
        alias = self.root / "alias.csv"
        try:
            alias.symlink_to(self.u)
        except OSError as exc:
            self.skipTest(str(exc))
        self.assertEqual(audit(alias, self.r, self.j, k=3), before)
        self.assertEqual(self.call(), before)

    def test_directory_missing_and_dangling_links_are_path_free(self):
        dangling = self.root / "dangling"
        try:
            dangling.symlink_to(self.root / "does-not-exist")
        except OSError:
            pass
        for path in (self.root, self.root / "missing", dangling):
            with self.subTest(path=path), self.assertRaises(BoundsError) as caught:
                list(_rows(path, ("query_id", "document_id"), 100))
            self.assertNotIn(str(self.root), str(caught.exception))

    @unittest.skipUnless(hasattr(os, "mkfifo"), "requires FIFOs")
    def test_fifo_refused_in_bounded_subprocess(self):
        fifo = self.root / "no-writer.csv"
        os.mkfifo(fifo)
        script = """
import sys
from rankbounds import BoundsError
from rankbounds.core import _rows
try:
    list(_rows(sys.argv[1], ('query_id', 'document_id'), 100))
except BoundsError as exc:
    assert str(exc) == 'CSV input must be a regular file'
else:
    raise AssertionError('FIFO was accepted')
"""
        completed = subprocess.run(
            [sys.executable, "-c", script, str(fifo)],
            capture_output=True,
            text=True,
            timeout=3,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        with patch("rankbounds.core.os.open") as opening:
            with self.assertRaisesRegex(BoundsError, "regular file"):
                list(_rows(fifo, ("query_id", "document_id"), 100))
            opening.assert_not_called()

    @unittest.skipUnless(hasattr(os, "mkfifo"), "requires FIFOs")
    def test_all_single_and_paired_input_roles_use_regular_reader(self):
        fifo = self.root / "no-writer.csv"
        os.mkfifo(fifo)
        single = [self.u, self.r, self.j]
        paired = [self.u, self.r, self.r, self.j]
        for function, paths in ((audit, single), (compare, paired)):
            for i in range(len(paths)):
                args = paths.copy()
                args[i] = fifo
                with self.subTest(function=function.__name__, role=i):
                    with self.assertRaisesRegex(BoundsError, "regular file"):
                        function(*args, k=3)
            for option in ("totals", "total_ranges", "query_weights"):
                with self.subTest(function=function.__name__, option=option):
                    with self.assertRaisesRegex(BoundsError, "regular file"):
                        function(*paths, k=3, **{option: fifo})

    @unittest.skipUnless(hasattr(os, "mkfifo"), "requires FIFOs")
    def test_cli_fifo_has_no_partial_json(self):
        fifo = self.root / "no-writer.csv"
        os.mkfifo(fifo)
        args = [
            "--universe",
            str(fifo),
            "--ranking",
            str(self.r),
            "--judgments",
            str(self.j),
            "--k",
            "3",
        ]
        with redirect_stdout(io.StringIO()) as output:
            with redirect_stderr(io.StringIO()) as errors:
                self.assertEqual(main(args), 2)
        self.assertEqual(output.getvalue(), "")
        self.assertIn("regular file", errors.getvalue())
        self.assertNotIn(str(fifo), errors.getvalue())

    @unittest.skipUnless(hasattr(os, "O_NONBLOCK"), "requires nonblocking open")
    def test_swapped_fifo_refused_without_waiting_and_descriptor_closed(self):
        script = """
import os, sys
from unittest.mock import patch
from rankbounds import BoundsError
from rankbounds.core import _rows
path = sys.argv[1]
real_open = os.open
fds = []
def swap(p, flags):
    os.unlink(p)
    os.mkfifo(p)
    fd = real_open(p, flags)
    fds.append(fd)
    return fd
with patch('rankbounds.core.os.open', side_effect=swap):
    try:
        list(_rows(path, ('query_id', 'document_id'), 100))
    except BoundsError as exc:
        assert str(exc) == 'CSV input must be a regular file'
    else:
        raise AssertionError('swapped FIFO was accepted')
assert len(fds) == 1
try:
    os.fstat(fds[0])
except OSError:
    pass
else:
    raise AssertionError('descriptor leaked')
"""
        completed = subprocess.run(
            [sys.executable, "-c", script, str(self.u)],
            capture_output=True,
            text=True,
            timeout=3,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)

    @unittest.skipUnless(hasattr(os, "mkfifo"), "requires FIFOs")
    def test_symlink_to_fifo_refused_before_open(self):
        fifo = self.root / "fifo"
        os.mkfifo(fifo)
        alias = self.root / "alias"
        alias.symlink_to(fifo)
        with patch("rankbounds.core.os.open") as opening:
            with self.assertRaisesRegex(BoundsError, "regular file"):
                list(_rows(alias, ("query_id", "document_id"), 100))
            opening.assert_not_called()

    def test_fstat_and_fdopen_errors_close_descriptor(self):
        real_open = os.open
        for target in ("fstat", "fdopen"):
            fds = []

            def opening(path, flags):
                fd = real_open(path, flags)
                fds.append(fd)
                return fd

            with patch("rankbounds.core.os.open", side_effect=opening):
                with patch(
                    "rankbounds.core.os." + target, side_effect=OSError("private")
                ):
                    with self.assertRaises(BoundsError) as caught:
                        list(_rows(self.u, ("query_id", "document_id"), 100))
            self.assertNotIn("private", str(caught.exception))
            self.assertEqual(len(fds), 1)
            with self.assertRaises(OSError):
                os.fstat(fds[0])

    def test_early_reader_close_closes_descriptor(self):
        real_open = os.open
        fds = []

        def opening(path, flags):
            fd = real_open(path, flags)
            fds.append(fd)
            return fd

        with patch("rankbounds.core.os.open", side_effect=opening):
            reader = _rows(self.u, ("query_id", "document_id"), 100)
            next(reader)
            reader.close()
        with self.assertRaises(OSError):
            os.fstat(fds[0])

    @unittest.skipUnless(hasattr(socket, "AF_UNIX"), "requires Unix sockets")
    def test_unix_socket_refused_before_open(self):
        with socket.socket(socket.AF_UNIX) as listener:
            path = self.root / "socket"
            try:
                listener.bind(str(path))
            except OSError as exc:
                self.skipTest(str(exc))
            with self.assertRaisesRegex(BoundsError, "regular file"):
                list(_rows(path, ("query_id", "document_id"), 100))
