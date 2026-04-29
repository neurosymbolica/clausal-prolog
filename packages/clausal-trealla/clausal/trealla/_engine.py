"""Low-level ctypes wrapper for the Trealla Prolog shared library.

Wraps the C API (pl_create, pl_consult, pl_eval, pl_query, pl_redo)
and provides stdout capture for reading Prolog output.
"""

from __future__ import annotations

import ctypes
import os
import shutil
import tempfile
from pathlib import Path

# ── Locate the shared library ────────────────────────────────────

_LIB_SEARCH_PATHS = [
    # Relative to the trealla-prolog source checkout
    Path(__file__).resolve().parent.parent.parent.parent / "trealla-prolog" / "libtpl.so",
    # Common install locations
    Path("/usr/local/lib/libtpl.so"),
    Path("/usr/lib/libtpl.so"),
]

_TPL_BINARY_SEARCH_PATHS = [
    Path(__file__).resolve().parent.parent.parent.parent / "trealla-prolog" / "tpl",
]


def _find_lib() -> str | None:
    for p in _LIB_SEARCH_PATHS:
        if p.exists():
            return str(p)
    return None


def _find_tpl() -> str | None:
    # Check search paths first
    for p in _TPL_BINARY_SEARCH_PATHS:
        if p.exists():
            return str(p)
    # Fall back to PATH
    return shutil.which("tpl")


_LIB_PATH = _find_lib()
TPL_BINARY = _find_tpl()


def _load_lib() -> ctypes.CDLL | None:
    if _LIB_PATH is None:
        return None
    try:
        lib = ctypes.CDLL(_LIB_PATH)
    except OSError:
        return None

    # Set up function signatures
    lib.pl_create.restype = ctypes.c_void_p
    lib.pl_create.argtypes = []

    lib.pl_destroy.restype = None
    lib.pl_destroy.argtypes = [ctypes.c_void_p]

    lib.pl_consult.restype = ctypes.c_bool
    lib.pl_consult.argtypes = [ctypes.c_void_p, ctypes.c_char_p]

    lib.pl_consult_fp.restype = ctypes.c_bool
    lib.pl_consult_fp.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_char_p]

    lib.pl_eval.restype = ctypes.c_bool
    lib.pl_eval.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_bool]

    lib.pl_query.restype = ctypes.c_bool
    lib.pl_query.argtypes = [
        ctypes.c_void_p,
        ctypes.c_char_p,
        ctypes.POINTER(ctypes.c_void_p),
        ctypes.c_uint,
    ]

    lib.pl_redo.restype = ctypes.c_bool
    lib.pl_redo.argtypes = [ctypes.c_void_p]

    lib.pl_done.restype = ctypes.c_bool
    lib.pl_done.argtypes = [ctypes.c_void_p]

    lib.get_status.restype = ctypes.c_bool
    lib.get_status.argtypes = [ctypes.c_void_p]

    lib.get_error.restype = ctypes.c_bool
    lib.get_error.argtypes = [ctypes.c_void_p]

    lib.get_halt.restype = ctypes.c_bool
    lib.get_halt.argtypes = [ctypes.c_void_p]

    lib.did_dump_vars.restype = ctypes.c_bool
    lib.did_dump_vars.argtypes = [ctypes.c_void_p]

    lib.set_quiet.restype = None
    lib.set_quiet.argtypes = [ctypes.c_void_p]

    return lib


_lib = _load_lib()

# libc for fflush
try:
    _libc = ctypes.CDLL(None)
    _libc.fflush.argtypes = [ctypes.c_void_p]
except OSError:
    _libc = None

AVAILABLE = _lib is not None


_singleton_pl = None


def _get_singleton():
    """Return the process-global Trealla prolog* handle.

    Trealla uses global state internally, so pl_destroy() corrupts
    shared structures and makes subsequent pl_create() calls crash.
    We work around this by keeping a single instance alive for the
    lifetime of the process.
    """
    global _singleton_pl
    if _singleton_pl is None:
        if _lib is None:
            raise ImportError(
                "Trealla shared library (libtpl.so) not found.\n"
                "Build it with: cd trealla-prolog && make NOFFI=1 NOSSL=1 "
                "NOTHREADS=1 ISOCLINE=1 CFLAGS+=-fPIC && "
                "cc -shared -o libtpl.so *.o src/*.o library/*.o -lm"
            )
        _singleton_pl = _lib.pl_create()
        if not _singleton_pl:
            raise RuntimeError("Failed to create Trealla Prolog instance")
        _lib.set_quiet(_singleton_pl)
    return _singleton_pl


class TreallaMachine:
    """Low-level wrapper around a Trealla Prolog instance.

    All TreallaMachine instances share a single process-global
    ``prolog*`` handle (Trealla's global state does not support
    multiple independent instances).  Calling ``destroy()`` marks
    this wrapper as closed but does NOT free the underlying C
    instance — it stays alive for the process lifetime.
    """

    def __init__(self):
        self._pl = _get_singleton()

    def destroy(self):
        """Mark this wrapper as closed.  Does not free C resources."""
        self._pl = None

    def __del__(self):
        pass  # No cleanup — singleton lives for process lifetime

    def _check_open(self):
        if self._pl is None:
            raise RuntimeError("This Trealla instance has been closed")

    def consult_file(self, path: str) -> bool:
        """Consult a Prolog source file."""
        self._check_open()
        return _lib.pl_consult(self._pl, path.encode())

    def consult_string(self, source: str) -> bool:
        """Consult Prolog source from a string (via temp file)."""
        self._check_open()
        with tempfile.NamedTemporaryFile(
            suffix=".pl", mode="w", encoding="utf-8", delete=False
        ) as f:
            f.write(source)
            f.flush()
            try:
                return _lib.pl_consult(self._pl, f.name.encode())
            finally:
                os.unlink(f.name)

    def _capture_stdout(self, func):
        """Run *func* with stdout redirected to a pipe, return captured text."""
        read_fd, write_fd = os.pipe()
        saved_stdout = os.dup(1)
        os.dup2(write_fd, 1)
        try:
            result = func()
            if _libc is not None:
                _libc.fflush(None)
        finally:
            os.dup2(saved_stdout, 1)
            os.close(saved_stdout)
            os.close(write_fd)

        output = b""
        while True:
            chunk = os.read(read_fd, 65536)
            if not chunk:
                break
            output += chunk
        os.close(read_fd)
        return result, output.decode("utf-8", errors="replace")

    def eval_capture(self, goal: str) -> tuple[bool, str]:
        """Evaluate a goal, capturing stdout output.

        Returns (success, captured_output).
        """
        self._check_open()
        return self._capture_stdout(
            lambda: _lib.pl_eval(self._pl, goal.encode(), False)
        )

    def query_iter(self, goal: str):
        """Start a query and yield (status, output) for each solution.

        Uses pl_query/pl_redo for true lazy iteration — each next()
        call resumes Prolog backtracking for one more solution.
        """
        self._check_open()
        subq = ctypes.c_void_p()

        # First solution
        first_ok, first_out = self._capture_stdout(
            lambda: _lib.pl_query(
                self._pl, goal.encode(), ctypes.byref(subq), 0
            )
        )
        yield first_ok, first_out

        if not first_ok:
            return

        # Subsequent solutions via redo
        while True:
            ok, out = self._capture_stdout(
                lambda: _lib.pl_redo(subq)
            )
            yield ok, out
            if not ok:
                return
