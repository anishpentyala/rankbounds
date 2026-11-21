# Regular-file CSV input refusal

## Problem

The shared CSV reader previously opened every supplied path directly. A named pipe with no writer could wait indefinitely at open, before header validation, row limits, or scoring work admission. A bounded subprocess against the immediately preceding public base, 0b75260442de9e1899cca6ca352736072b56c567, timed out after two seconds and was killed and waited. The same input against this candidate promptly raises the path-free BoundsError for a nonregular file. This is an input-liveness bug, not a score correction or a claim that every read now has a time limit.

## Reader contract

Every required or optional CSV path passes through the same reader. Only OS-reported regular files are accepted. Symlinks are followed if their target is a regular file. Directory, FIFO, socket and device inputs are refused. Missing paths and broken symlinks still fail without echoing their filesystem paths in the public error. Inputs are read-only. No output, scratch file, network request or global CSV setting is added.

The implementation checks the path metadata before opening, opens read-only with O_NONBLOCK when the platform supplies it and O_BINARY when required, then checks the actual opened descriptor's file type. The second check matters because the path can change between stat and open. On POSIX, a FIFO substituted during that interval does not wait for a writer: the nonblocking open succeeds, fstat detects the FIFO, and the descriptor closes before text reading.

After checks, os.fdopen wraps that same descriptor as UTF-8 with optional initial BOM and newline handling unchanged. Ownership transfers to the text stream only after the wrapper succeeds. A finally block closes descriptors when the opened-type check or wrapper setup fails. The stream's context closes it on success, parse failure and explicit early generator close. File descriptors remain non-inheritable under Python's normal os.open behavior; this code does not change that behavior.

## Limits

This is not an immutable snapshot, a trusted-root/path-sandbox rule, protection against changes to regular-file contents, or a hard I/O deadline. Symlinks to regular files deliberately remain accepted. Different regular files substituted during the metadata/open interval may be read. Regular files can change while being read. Network, pseudo and user-space filesystems may still block at metadata lookup, open or read even when their files report as regular. Devices are rejected by type, not opened for content.

When O_NONBLOCK is unavailable, path and opened-descriptor checks still apply, but the blocking substitution-race guarantee does not. The demonstrated FIFO substitution test runs only on platforms exposing O_NONBLOCK. These platform-specific tests were exercised on Linux, not Windows or macOS. This is a narrow liveness hardening, not a cross-platform arbitrary-filesystem safety claim.

No scoring, query ordering, weighted aggregate, JSON schema, exit status or solver work-admission calculation changes for accepted inputs. Files that were nonregular are intentionally no longer supported. Applications generating CSV through a pipe should write a bounded regular file first. Extra metadata and descriptor checks add constant per-file work. Existing row, CSV-field and solver limits remain estimates/admission rules rather than hard total RAM, I/O or wall-time caps.

## Validation

- 145 tests pass on CPython 3.9 through 3.15 on Linux. Ten new tests cover ordinary files and regular symlinks, missing/dangling/directory errors, bounded FIFO refusal, every single/paired input role including totals/ranges/weights, no-partial-JSON CLI behavior, deterministic FIFO substitution, descriptor cleanup after fstat/fdopen failures and explicit early generator close, symlink-to-FIFO refusal, and Unix sockets.
- The same-target public base hangs on the FIFO with no writer. A bounded two-second subprocess captures the failure, terminates it and waits. This is direct baseline evidence of the original symptom.
- Four mutants were caught and failure evidence inspected: removed metadata precheck, removed opened-type check, removed O_NONBLOCK, and omitted error-path descriptor close. The no-O_NONBLOCK mutant times out specifically in the deterministic FIFO-substitution subprocess after three seconds. That timeout is the intended liveness failure, not an import/setup error. The descriptor mutant reaches the explicit leaked-descriptor assertion. The opened-type mutant reaches a wrong CSV-header error rather than refusing the FIFO and also fails the injected fstat-error test. The precheck mutant violates before-open refusal; actual socket refusal also changes.
- 450 baseline/candidate generated fixture comparisons produce byte-identical complete default reports, and the corresponding 450 weighted reports also match completely. They cover single, paired-default and paired-RR/AP modes, count ranges, empty/short rankings, hypothetical examples and varying cutoffs.
- A built wheel installed into a separate Python 3.9 environment passes all 145 tests from a neutral directory, with no local source package import. Ruff check and format pass. No external adoption or deployment claimed.
