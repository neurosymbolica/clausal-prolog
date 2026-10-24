"""The ISO stream table (ISO 13211-1 §7.10, §8.11): the process's open
streams, their aliases, and the current input and output.

A stream term is the opaque cell ``'$stream'(N)``; a stream may also be
named by an alias atom (``user_input``, ``user_output``, ``user_error``, or
an ``alias(A)`` option of ``open/4``).  The three standard streams are rows
0, 1 and 2 and stand for *whatever* ``sys.stdin``/``sys.stdout``/
``sys.stderr`` are when they are used -- so ``write/1`` keeps writing to
the Python process's stdout (a replaced or captured one included), as it
did before streams existed, and ``close/1`` of a standard stream is a
no-op.

A :class:`Stream` wraps a Python text file (UTF-8, no newline translation)
or binary file.  Input keeps a small push-back buffer for ``peek_char/2``
and for the term reader's read-ahead; positions are the opaque term
``'$stream_position'(Chars, Lines, LinePos, Cookie)`` where *Cookie* is the
Python file's ``tell()`` cookie, so ``set_stream_position/2`` is one
``seek``.  The current input and output are PROCESS-GLOBAL (as ISO has
them), not thread-local: two threads that ``set_output/1`` share one
setting.  This module raises no Prolog errors of its own: the builtins in
``clausal/logic/builtins/streams_io.py`` check the arguments and the
stream's mode, turn a failed open into the ISO error term, and wrap an
OS error from a stream operation (``OSError``/``ValueError``/
``AttributeError`` -- a file closed underneath, a stdin that is None, a
full disk) into ``error(system_error(io), PI)`` in one place
(``io_errors``).  A standard stream is flushed after each write only when
it is a terminal; a file stream is flushed by ``flush_output`` and
``close``.
"""

from __future__ import annotations

import io as _io
import sys as _sys
import threading as _threading

STREAM_TAG = "$stream"
POSITION_TAG = "$stream_position"

MODES = ("read", "write", "append")
EOF_ACTIONS = ("error", "eof_code", "reset")

_STD_FILES = {"stdin": lambda: _sys.stdin, "stdout": lambda: _sys.stdout,
              "stderr": lambda: _sys.stderr}


class Stream:
    """One open stream.  ``mode`` is ``read``/``write``/``append``;
    ``kind`` is ``text`` or ``binary``; ``std`` names a standard stream
    (``stdin``/``stdout``/``stderr``) resolved through ``sys`` at each use,
    else ``_f`` is the Python file object."""

    __slots__ = ("id", "term", "mode", "kind", "file_name", "aliases",
                 "eof_action", "reposition", "std", "_f", "_buf",
                 "past_eof", "char_count", "line_count", "line_pos",
                 "_anchor", "closed", "_tty")

    def __init__(self, ident: int, f, *, mode: str, kind: str = "text",
                 file_name=None, aliases=(), eof_action: str = "eof_code",
                 reposition: bool = False, std=None):
        self.id = ident
        self.term = (STREAM_TAG, ident)
        self.mode = mode
        self.kind = kind
        self.file_name = file_name
        self.aliases = list(aliases)
        self.eof_action = eof_action
        self.reposition = reposition
        self.std = std
        self._f = f
        self._buf = b"" if kind == "binary" else ""
        self.past_eof = False
        self.char_count = 0
        self.line_count = 0
        self.line_pos = 0
        self.closed = False
        self._tty = None             # (file object, is a terminal) cache
        cookie = 0
        if std is None and f is not None:
            try:
                cookie = f.tell()
            except (OSError, ValueError):
                cookie = 0
        self._anchor = (cookie, 0)

    # ── identity ──────────────────────────────────────────────────────────

    @property
    def is_input(self) -> bool:
        return self.mode == "read"

    @property
    def is_output(self) -> bool:
        return self.mode != "read"

    @property
    def is_binary(self) -> bool:
        return self.kind == "binary"

    @property
    def fileobj(self):
        if self.std is not None:
            return _STD_FILES[self.std]()
        return self._f

    def __repr__(self) -> str:
        return f"<Stream {self.id} {self.mode} {self.kind} {self.file_name or self.std}>"

    # ── counting ──────────────────────────────────────────────────────────

    def _count(self, text) -> None:
        n = len(text)
        self.char_count += n
        if self.kind == "binary":
            return
        lines = text.count("\n")
        if lines:
            self.line_count += lines
            self.line_pos = n - text.rfind("\n") - 1
        else:
            self.line_pos += n

    # ── output ────────────────────────────────────────────────────────────

    def _is_tty(self, f) -> bool:
        """Whether the standard stream's current file object is a terminal
        (cached per object: ``sys.stdout`` may be replaced at any time)."""
        cache = self._tty
        if cache is not None and cache[0] is f:
            return cache[1]
        isatty = getattr(f, "isatty", None)
        try:
            tty = bool(isatty()) if isatty is not None else False
        except (OSError, ValueError):
            tty = False
        self._tty = (f, tty)
        return tty

    def write(self, text: str) -> None:
        """Write *text* (a str) to a text stream.  A standard stream on a
        terminal is flushed after each write (so a prompt appears); a
        standard stream on a pipe or file is left to its own buffering,
        and a file stream is counted for its position."""
        f = self.fileobj
        f.write(text)
        if self.std is None:
            self._count(text)
        elif self._is_tty(f):
            flush = getattr(f, "flush", None)
            if flush is not None:
                flush()

    def write_bytes(self, data: bytes) -> None:
        f = self.fileobj
        f.write(data)
        if self.std is None:
            self.char_count += len(data)
        elif self._is_tty(f):
            flush = getattr(f, "flush", None)
            if flush is not None:
                flush()

    def flush(self) -> None:
        """Flush the stream; an OS error propagates (``flush_output/1``
        reports it as ``system_error(io)``)."""
        flush = getattr(self.fileobj, "flush", None)
        if flush is not None:
            flush()

    # ── input ─────────────────────────────────────────────────────────────

    def _read1(self):
        """One char (str) or byte (int) from the underlying file; ``None``
        at end of file."""
        f = self.fileobj
        if self.kind == "binary":
            b = f.read(1)
            if not b:
                return None
            return b[0]
        c = f.read(1)
        if c == "":
            return None
        return c

    def get(self):
        """Consume and return one char (str) / byte (int); ``None`` at end
        of file, which marks the stream past its end."""
        buf = self._buf
        if buf:
            x = buf[0]
            self._buf = buf[1:]
        else:
            x = self._read1()
            if x is None:
                self.past_eof = True
                return None
        if self.kind == "binary":
            self.char_count += 1
        else:
            self._count(x)
        return x

    def peek(self):
        """The next char / byte without consuming it; ``None`` at end of
        file (the stream is then *at* its end, not past it)."""
        buf = self._buf
        if buf:
            return buf[0]
        x = self._read1()
        if x is None:
            return None
        self._buf = bytes((x,)) if self.kind == "binary" else x
        return x

    def read_chunk(self) -> str:
        """Text for the term reader: the push-back buffer if any, else the
        next line of the file; ``""`` at end of file.  Nothing is counted
        as consumed until :meth:`consume`."""
        buf = self._buf
        if buf:
            self._buf = ""
            return buf
        return self.fileobj.readline()

    def consume(self, text: str) -> None:
        """Account *text*, handed out by :meth:`read_chunk`, as read."""
        self._count(text)

    def unread(self, text: str) -> None:
        """Push *text* back so the next read sees it first."""
        if text:
            self._buf = text + self._buf

    def end_of_stream(self) -> str:
        """``not`` / ``at`` / ``past`` (the ``end_of_stream`` property)."""
        if self.is_output:
            return "not"
        if self.past_eof:
            return "past"
        if self.std is not None:
            return "not"         # never block on a terminal to find out
        return "at" if self.peek() is None else "not"

    # ── positions ─────────────────────────────────────────────────────────

    def seekable(self) -> bool:
        if self.std is not None or self._f is None:
            return False
        try:
            return bool(self._f.seekable())
        except (OSError, ValueError):
            return False

    def position(self):
        """The position term, or ``None`` when the stream has none."""
        if not self.seekable():
            return None
        f = self._f
        try:
            if self.is_output:
                f.flush()
            elif self._buf:
                # Re-synchronise the file with the logical position: back
                # to the last point where nothing was pushed back, then
                # forward over what has been consumed since.
                cookie0, chars0 = self._anchor
                f.seek(cookie0)
                n = self.char_count - chars0
                if n:
                    f.read(n)
                self._buf = b"" if self.kind == "binary" else ""
            cookie = f.tell()
        except (OSError, ValueError):
            return None
        if self.is_input:
            self._anchor = (cookie, self.char_count)
        return (POSITION_TAG, self.char_count, self.line_count,
                self.line_pos, cookie)

    def seek_to(self, pos) -> None:
        """Reposition to *pos*, a term :meth:`position` gave (validated by
        the caller)."""
        _, chars, lines, line_pos, cookie = pos
        f = self._f
        if self.is_output:
            f.flush()
        f.seek(cookie)
        self.char_count, self.line_count, self.line_pos = chars, lines, line_pos
        self._buf = b"" if self.kind == "binary" else ""
        self.past_eof = False
        self._anchor = (cookie, chars)

    # ── closing ───────────────────────────────────────────────────────────

    def close_file(self) -> None:
        if self.std is None and self._f is not None:
            self._f.close()


# ── the table ───────────────────────────────────────────────────────────────

_lock = _threading.RLock()

USER_INPUT = Stream(0, None, mode="read", aliases=("user_input",),
                    eof_action="reset", std="stdin")
USER_OUTPUT = Stream(1, None, mode="append", aliases=("user_output",),
                     std="stdout")
USER_ERROR = Stream(2, None, mode="append", aliases=("user_error",),
                    std="stderr")

_streams: dict = {0: USER_INPUT, 1: USER_OUTPUT, 2: USER_ERROR}
_aliases: dict = {"user_input": USER_INPUT, "user_output": USER_OUTPUT,
                  "user_error": USER_ERROR}
_next_id = 3
_current_input: Stream = USER_INPUT
_current_output: Stream = USER_OUTPUT


def current_input() -> Stream:
    return _current_input


def current_output() -> Stream:
    return _current_output


def set_current_input(s: Stream) -> None:
    global _current_input
    _current_input = s


def set_current_output(s: Stream) -> None:
    global _current_output
    _current_output = s


def by_term(term):
    """The open stream of the cell ``'$stream'(N)``, or None."""
    if type(term) is tuple and len(term) == 2 and term[0] == STREAM_TAG:
        s = _streams.get(term[1])
        if s is not None and not s.closed:
            return s
    return None


def by_alias(name):
    """The open stream the alias atom *name* names, or None."""
    return _aliases.get(name)


def is_stream_term(term) -> bool:
    return (type(term) is tuple and len(term) == 2 and term[0] == STREAM_TAG
            and type(term[1]) is int)


def alias_in_use(name) -> bool:
    return name in _aliases


def open_streams() -> list:
    """Every open stream, in creation order."""
    return [s for _, s in sorted(_streams.items())]


def is_position_term(term) -> bool:
    return (type(term) is tuple and len(term) == 5 and term[0] == POSITION_TAG
            and all(type(x) is int for x in term[1:]))


class OpenFailed(Exception):
    """``open/4`` could not open the file: ``why`` is ``existence`` (no such
    source/sink) or ``permission`` (anything else the OS refused)."""

    def __init__(self, why: str):
        super().__init__(why)
        self.why = why


class AliasInUse(Exception):
    """``open/4`` asked for an alias another open stream has (checked and
    registered under the table's lock, so two openers cannot both win)."""

    def __init__(self, alias: str):
        super().__init__(alias)
        self.alias = alias


def open_stream(file_name: str, mode: str, *, kind: str = "text",
                aliases=(), eof_action: str = "eof_code",
                reposition=None) -> Stream:
    """Open *file_name* and register the stream.  *reposition* None means
    "if the file allows it" (a seekable file not opened for append).
    Raises :class:`OpenFailed`, :class:`AliasInUse`, or
    ``ValueError("reposition")`` when ``reposition(true)`` was asked of a
    stream that cannot be repositioned (the caller's
    ``permission_error(open, source_sink, reposition(true))``).
    """
    pymode = {"read": "r", "write": "w", "append": "a"}[mode]
    global _next_id
    with _lock:
        # The alias check and the registration under ONE lock: a second
        # opener of the same alias sees it taken, not a race.
        for a in aliases:
            if a in _aliases:
                raise AliasInUse(a)
        try:
            if kind == "binary":
                f = open(file_name, pymode + "b")
            else:
                f = open(file_name, pymode, encoding="utf-8", newline="")
        except (FileNotFoundError, NotADirectoryError):
            raise OpenFailed("existence") from None
        except IsADirectoryError:
            raise OpenFailed("existence" if mode == "read" else "permission") from None
        except OSError:
            raise OpenFailed("permission") from None
        try:
            seekable = bool(f.seekable())
        except (OSError, ValueError):
            seekable = False
        if reposition is None:
            # An append stream is not repositioned unless asked (Scryer).
            reposition = seekable and mode != "append"
        elif reposition and not seekable:
            f.close()
            raise ValueError("reposition")
        ident = _next_id
        _next_id += 1
        s = Stream(ident, f, mode=mode, kind=kind, file_name=file_name,
                   aliases=aliases, eof_action=eof_action,
                   reposition=reposition)
        _streams[ident] = s
        for a in s.aliases:
            _aliases[a] = s
    return s


def close_stream(s: Stream, force: bool = False) -> None:
    """Close *s* and drop it from the table.  A standard stream stays open
    (ISO 8.11.6: closing one has no effect).  Without *force* an OS error
    on close propagates as the OSError it was."""
    global _current_input, _current_output
    if s.std is not None:
        return
    with _lock:
        _streams.pop(s.id, None)
        for a in s.aliases:
            if _aliases.get(a) is s:
                del _aliases[a]
        s.closed = True
        if _current_input is s:
            _current_input = USER_INPUT
        if _current_output is s:
            _current_output = USER_OUTPUT
    try:
        s.close_file()
    except OSError:
        if not force:
            raise


def reset_for_tests() -> None:
    """Close every non-standard stream and restore the current streams --
    for test suites that leave the table as they found it."""
    global _next_id
    for s in list(_streams.values()):
        if s.std is None:
            close_stream(s, force=True)
    set_current_input(USER_INPUT)
    set_current_output(USER_OUTPUT)
    _next_id = 3


__all__ = [
    "STREAM_TAG", "POSITION_TAG", "MODES", "EOF_ACTIONS", "Stream",
    "OpenFailed", "AliasInUse", "USER_INPUT", "USER_OUTPUT", "USER_ERROR",
    "current_input", "current_output", "set_current_input",
    "set_current_output", "by_term", "by_alias", "is_stream_term",
    "alias_in_use", "open_streams", "is_position_term", "open_stream",
    "close_stream", "reset_for_tests",
]
