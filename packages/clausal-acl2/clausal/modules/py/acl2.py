"""clausal.modules.py.acl2 — ACL2 from Clausal, through the ACL2 Bridge.

`ACL2 <https://www.cs.utexas.edu/~moore/acl2/>`_ is a theorem prover for an
applicative Common Lisp.  This module talks to a real ACL2 through its
`ACL2 Bridge <https://www.cs.utexas.edu/~moore/acl2/manuals/current/manual/?topic=CENTAUR____BRIDGE>`_
(``books/centaur/bridge``): a socket server that evaluates Lisp forms and
prints the results.  Lisp forms and results cross as Clausal TERMS::

    -import_from(py.acl2, [acl2, acl2_mv, event, thm, use_acl2])

Predicates
----------
- ``acl2(Form, Value)``, ``acl2(Form, Value, Output)`` -- evaluate a form;
  its first value, and the text ACL2 printed while evaluating it
- ``acl2_mv(Form, Values)`` -- every value, as a list
- ``event(Form)``, ``event(Form, Output)`` -- submit an event (``defun``,
  ``defthm``, ``in-theory``, ...) through ``ld``; fails if ACL2 rejects it
- ``thm(Term)``, ``thm(Term, Output)`` -- prove ``Term``; fails if ACL2
  cannot (an unproved theorem is a failure, not an error)
- ``acl2_text(Term, Text)`` -- a term and its ACL2 text, either way: parse
  ``Text`` when it is bound, else print ``Term`` (``if`` and other Python
  keywords cannot be functors in the seam, but can be written in text)
- ``use_acl2(Options)`` -- which ACL2: ``{"socket": Path}`` or
  ``{"host": H, "port": N}`` for a running bridge, or ``{"command": Cmd}``
  to start one (``acl2`` on PATH by default, also on first use);
  ``timeout`` bounds connecting, ``startup_timeout`` a started ACL2's
  start.  A started ACL2 is stopped, with its process group, by the next
  ``use_acl2/1`` or when Python exits

Terms (the boundary mapping; one term per ACL2 object)
------------------------------------------------------
=====================  =======================================================
ACL2                   Clausal term
=====================  =======================================================
``FOO`` (ACL2 pkg)     atom ``foo``; ``NIL``/``T`` are ``nil``/``t``
``:FOO``               atom ``':foo'``
``PKG::FOO``           atom ``'pkg::foo'``
``|foo|`` (lowercase)  atom ``'|foo|'`` (the exact name between bars)
integer, rational      ``int``, ``Fraction``
``#C(a b)``            ``('$complex', a, b)``
string                 a string (``('$chars', s)``)
``#\\a``                ``('$char', 'a')``
``(f a b ...)``        the cell ``('f', a, b, ...)`` -- symbol head, 2+ items
other proper list      ``('()', e1, ..., en)``
``(a . b)``            ``('$cons', a, b)``
=====================  =======================================================

So an ACL2 term is a Prolog compound -- ``thm(implies('true-listp'(x),
equal(rev(rev(x)), x)))`` -- and a Clausal list ``[a, b]`` crosses out as the
Lisp list ``(A B)`` too (it comes back as the canonical term above).

Errors (raise, never fail)
--------------------------
``instantiation_error`` for an unbound part of a form;
``type_error(acl2_term, C)`` for a term with no ACL2 object;
``existence_error(acl2_bridge, Where)`` when no bridge answers, or the
bridge goes away mid-call (the next call connects again);
``error(acl2_error(Message), _)`` when ACL2 signals an error evaluating a form;
``syntax_error(acl2_text)`` for text that is not exactly one ACL2 object;
``domain_error(acl2_option, Name)`` for an option ``use_acl2/1`` does not
take, and ``type_error``/``domain_error`` for an option value of the wrong
kind.  A theorem or event ACL2 does not accept FAILS.
"""

from __future__ import annotations

import os as _os
import re as _re
import shutil as _shutil
import signal as _signal
import socket as _socket
import subprocess as _subprocess
import tempfile as _tempfile
import threading as _threading
import time as _time
import weakref as _weakref
from fractions import Fraction

from clausal.logic.cells import TUPLE_TAG, chars, chars_text, is_chars
from clausal.logic.exceptions import (
    LogicException, domain_error, existence_error, instantiation_error, type_error,
)
from clausal.logic.variables import deref, is_var, unify, walk
from clausal.modules.py import (
    ModulePredicate, expect_type, has_option, option, simple_to_trampoline,
    syntax_error_term, text_result, to_text,
)

CONS_TAG, CHAR_TAG, COMPLEX_TAG = "$cons", "$char", "$complex"


# ── Terms -> ACL2 text ───────────────────────────────────────────────────

_PLAIN_SYMBOL = _re.compile(r"[A-Z0-9*+\-/<>=!?%&$^_~@.:{}\[\]]+")
_NUMBERISH = _re.compile(r"[+-]?(\d+(/\d+)?|\d*\.\d+)\.?")


def _symbol_text(name: str) -> str:
    """CL text for a symbol NAME (no package), escaped when it would not
    read back as itself."""
    if _PLAIN_SYMBOL.fullmatch(name) and not _NUMBERISH.fullmatch(name) \
            and name not in (".",):
        return name
    return "|" + name.replace("\\", "\\\\").replace("|", "\\|") + "|"


def _atom_text(atom: str) -> str:
    if atom in ("", "[]"):
        return "NIL"
    if len(atom) > 2 and atom[0] == "|" and atom[-1] == "|":
        return _symbol_text(atom[1:-1])
    if atom.startswith(":") and len(atom) > 1:
        return ":" + _symbol_text(atom[1:].upper())
    if "::" in atom:
        pkg, name = atom.split("::", 1)
        return _symbol_text(pkg.upper()) + "::" + _symbol_text(name.upper())
    if atom != atom.lower():                 # an atom with capitals: exact
        return "|" + atom.replace("\\", "\\\\").replace("|", "\\|") + "|"
    return _symbol_text(atom.upper())


def _string_text(s: str) -> str:
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'


_CHAR_NAMES = {" ": "Space", "\n": "Newline", "\t": "Tab", "\r": "Return",
               "\f": "Page", "\x7f": "Rubout", "\x08": "Backspace"}


def to_lisp(term, pred="acl2/2") -> str:
    """The ACL2 text of a Clausal term (the mapping above, reversed)."""
    term = walk(term)
    if is_var(term):
        raise LogicException(instantiation_error(pred))
    if type(term) is bool:
        raise LogicException(type_error("acl2_term", term, pred))
    if isinstance(term, int):
        return str(term)
    if isinstance(term, Fraction):
        return f"{term.numerator}/{term.denominator}"
    if type(term) is str:
        return _atom_text(term)
    if is_chars(term):
        return _string_text(chars_text(term))
    if isinstance(term, list):
        return "(" + " ".join(to_lisp(x, pred) for x in term) + ")" if term else "NIL"
    if type(term) is tuple and term:
        head = term[0]
        if head == CHAR_TAG and len(term) == 2 and type(term[1]) is str and len(term[1]) == 1:
            c = term[1]
            return "#\\" + _CHAR_NAMES.get(c, c)
        if head == COMPLEX_TAG and len(term) == 3:
            return f"#C({to_lisp(term[1], pred)} {to_lisp(term[2], pred)})"
        if head == CONS_TAG and len(term) == 3:
            return f"({to_lisp(term[1], pred)} . {to_lisp(term[2], pred)})"
        if head == TUPLE_TAG:
            items = term[1:]
        else:
            items = term                     # a cell (f a ...) is the list
        return "(" + " ".join(to_lisp(x, pred) for x in items) + ")"
    raise LogicException(type_error("acl2_term", term, pred))


# ── ACL2 text -> terms ───────────────────────────────────────────────────

def _make_list(items, tail="nil"):
    if tail != "nil":
        out = tail
        for x in reversed(items):
            out = (CONS_TAG, x, out)
        return out
    if not items:
        return "nil"
    if type(items[0]) is str and len(items) >= 2:
        return tuple(items)
    return (TUPLE_TAG, *items)


def _name_atom(name: str) -> str:
    return name.lower() if name == name.upper() else "|" + name + "|"


class _ReadError(ValueError):
    """Text that is not the printed form of one ACL2 object."""


class _Reader:
    """Reads what ACL2 prints with ``prin1`` (*package* ACL2): conses,
    symbols (packages, bars, escapes), keywords, strings, characters,
    integers, ratios, ``#C`` complexes, and ``'x``.  Anything else is a
    ``_ReadError`` naming what was wrong and where."""

    def __init__(self, text):
        self.s, self.i = text, 0

    def _ws(self):
        while self.i < len(self.s) and self.s[self.i] in " \t\r\n\f":
            self.i += 1

    def _peek(self, what):
        """The next character, which must exist (*what* is being read)."""
        if self.i >= len(self.s):
            raise _ReadError(f"the text ends inside {what}")
        return self.s[self.i]

    def read(self, what="an object"):
        self._ws()
        s, c = self.s, self._peek(what)
        if c == "(":
            start = self.i
            self.i += 1
            items = []
            while True:
                self._ws()
                c = self._peek(f"the list opened at offset {start}")
                if c == ")":
                    self.i += 1
                    return _make_list(items)
                if c == "." and s[self.i + 1:self.i + 2] in (" ", "\t", "\r", "\n", "\f", "(", ")", ""):
                    if not items:
                        raise _ReadError(f"a dot with nothing before it at offset {self.i}")
                    self.i += 1
                    tail = self.read(f"the dotted list opened at offset {start}")
                    self._ws()
                    if self._peek(f"the list opened at offset {start}") != ")":
                        raise _ReadError(
                            f"more than one object after the dot at offset {self.i}")
                    self.i += 1
                    return _make_list(items, tail)
                items.append(self.read(f"the list opened at offset {start}"))
        if c == ")":
            raise _ReadError(f"an unmatched ')' at offset {self.i}")
        if c == "'":
            self.i += 1
            return _make_list(["quote", self.read("a quoted object")])
        if c == '"':
            start = self.i
            out, j = [], self.i + 1
            while True:
                if j >= len(s):
                    raise _ReadError(f"the string opened at offset {start} is not closed")
                if s[j] == '"':
                    break
                if s[j] == "\\":
                    j += 1
                    if j >= len(s):
                        raise _ReadError(f"the string opened at offset {start} is not closed")
                out.append(s[j]); j += 1
            self.i = j + 1
            return chars("".join(out))
        if s.startswith("#\\", self.i):
            if self.i + 2 >= len(s):
                raise _ReadError(f"a character with no name at offset {self.i}")
            j = self.i + 3
            while j < len(s) and s[j] not in " \t\r\n()":
                j += 1
            name = s[self.i + 2:j]
            if len(name) == 1:
                self.i = j
                return (CHAR_TAG, name)
            named = {v.lower(): k for k, v in _CHAR_NAMES.items()}
            named.update({"linefeed": "\n", "nul": "\x00", "null": "\x00"})
            if name.lower() not in named:
                raise _ReadError(f"an unknown character name #\\{name} at offset {self.i}")
            self.i = j
            return (CHAR_TAG, named[name.lower()])
        if s.startswith(("#C(", "#c("), self.i):
            start = self.i
            self.i += 2
            parts = _list_items(self.read("a complex number"))
            if len(parts) != 2 or not all(
                    isinstance(p, (int, Fraction)) and type(p) is not bool for p in parts):
                raise _ReadError(
                    f"the complex number at offset {start} is not #C(real imaginary)")
            return (COMPLEX_TAG, parts[0], parts[1])
        if c == "#":
            raise _ReadError(f"unsupported # syntax at offset {self.i}")
        return self._token()

    def _token(self):
        s, j = self.s, self.i
        start = j
        pkg, name, barred = None, [], False
        while j < len(s) and s[j] not in " \t\r\n\f()'\"":
            if s[j] == "|":
                k = j + 1
                while True:
                    if k >= len(s):
                        raise _ReadError(f"the |...| name opened at offset {j} is not closed")
                    if s[k] == "|":
                        break
                    if s[k] == "\\":
                        k += 1
                        if k >= len(s):
                            raise _ReadError(
                                f"the |...| name opened at offset {j} is not closed")
                    name.append(s[k]); k += 1
                barred, j = True, k + 1
            elif s[j] == "\\":
                if j + 1 >= len(s):
                    raise _ReadError(f"a backslash at the end of the text (offset {j})")
                name.append(s[j + 1]); j += 2
                barred = True
            elif s[j] == ":":
                if pkg is not None:
                    raise _ReadError(f"a symbol with two package markers at offset {start}")
                pkg = "".join(name)
                name, barred = [], False
                j += 2 if s.startswith("::", j) else 1
            else:
                name.append(s[j].upper()); j += 1
        if j == start:
            raise _ReadError(f"unexpected {s[j]!r} at offset {j}")
        self.i = j
        text = "".join(name)
        if pkg is None and not barred:
            if text == ".":
                raise _ReadError(f"a dot outside a list at offset {start}")
            if _re.fullmatch(r"[+-]?\d+\.?", text):
                return int(text.rstrip("."))
            if _re.fullmatch(r"[+-]?\d+/\d+", text):
                q = Fraction(text)
                return int(q) if q.denominator == 1 else q
        if pkg == "":
            return ":" + _name_atom(text)
        if pkg is not None and pkg.upper() not in ("ACL2", "COMMON-LISP"):
            return _name_atom(pkg) + "::" + _name_atom(text)
        return _name_atom(text)


def _list_items(term):
    if term == "nil":
        return []
    if type(term) is tuple and term and term[0] == TUPLE_TAG:
        return list(term[1:])
    return list(term)


def from_lisp(text: str):
    """The Clausal term for ACL2's printed text of exactly one object;
    ``_ReadError`` (a ``ValueError``) for anything else."""
    reader = _Reader(text)
    if not text.strip():
        raise _ReadError("no object in the text")
    term = reader.read()
    reader._ws()
    if reader.i != len(text):
        raise _ReadError(f"more text after the object, at offset {reader.i}")
    return term


# ── The bridge connection ────────────────────────────────────────────────

class BridgeError(Exception):
    """ACL2 sent an ERROR message."""


class _BridgeLost(ConnectionError):
    """The connection to the bridge broke: closed, reset, or garbled."""


class _Bridge:
    """One connection to an ACL2 Bridge server.  Messages are
    ``TYPE LEN\\nCONTENT\\n`` with LEN in characters (bridge-raw.lsp).

    *timeout* bounds the handshake only; once the bridge has said hello,
    reads wait as long as ACL2 takes (a proof can run for minutes)."""

    def __init__(self, sock: _socket.socket, where: str, timeout=None):
        self.where = where
        self._sock = sock
        self._r = sock.makefile("r", encoding="utf-8", newline="")
        self._w = sock.makefile("w", encoding="utf-8", newline="")
        self._lock = _threading.Lock()
        sock.settimeout(timeout)
        kind, self.hello = self._message()
        if kind != "ACL2_BRIDGE_HELLO":
            raise BridgeError(f"not an ACL2 bridge: first message {kind!r}")
        sock.settimeout(None)

    def _message(self):
        header = self._r.readline()
        if not header:
            raise _BridgeLost(f"the ACL2 bridge at {self.where} closed the connection")
        try:
            kind, length = header.rstrip("\n").split(" ")
            length = int(length)
        except ValueError:
            raise _BridgeLost(
                f"the ACL2 bridge at {self.where} sent a malformed message") from None
        content = self._r.read(length)
        if len(content) < length or self._r.read(1) != "\n":
            raise _BridgeLost(f"the ACL2 bridge at {self.where} closed the connection")
        return kind, content

    def command(self, kind: str, text: str):
        """Send one command; ``(output, returned_text)``.  Raises
        ``BridgeError`` on an ERROR reply, ``OSError`` (``_BridgeLost``
        among them) when the connection breaks."""
        with self._lock:
            try:
                kind_, _ = self._message()
                while kind_ != "READY":              # stray output before READY
                    kind_, _ = self._message()
                self._w.write(f"{kind} {len(text)}\n{text}\n")
                self._w.flush()
                output = []
                while True:
                    kind_, content = self._message()
                    if kind_ == "RETURN":
                        return "".join(output), content
                    if kind_ == "ERROR":
                        raise BridgeError(content)
                    output.append(content)           # STDOUT, STDERR, ...
            except ValueError as exc:                # I/O on a closed file
                raise _BridgeLost(f"the ACL2 bridge at {self.where}: {exc}") from exc

    def close(self):
        for f in (self._r, self._w, self._sock):
            try:
                f.close()
            except (OSError, ValueError):
                pass


def _connect(socket_path=None, host=None, port=None, timeout=None):
    """A bridge connection; *timeout* bounds connecting and the handshake."""
    if socket_path is not None:
        sock = _socket.socket(_socket.AF_UNIX, _socket.SOCK_STREAM)
        where = socket_path
        try:
            sock.settimeout(timeout)
            sock.connect(socket_path)
        except BaseException:
            sock.close()
            raise
    else:
        where = f"{host or '127.0.0.1'}:{int(port or 55432)}"
        sock = _socket.create_connection((host or "127.0.0.1", int(port or 55432)), timeout)
    try:
        return _Bridge(sock, where, timeout)
    except BaseException:
        sock.close()
        raise


def _leader_exited(proc) -> bool:
    """Whether a started process has ended, WITHOUT reaping it where the
    platform allows (``waitid`` with ``WNOWAIT``): an unreaped leader keeps
    its process-group id reserved, so the group can still be signalled
    safely after the leader died."""
    if proc.returncode is not None:
        return True
    if hasattr(_os, "waitid"):
        try:
            return _os.waitid(_os.P_PID, proc.pid,
                              _os.WEXITED | _os.WNOHANG | _os.WNOWAIT) is not None
        except ChildProcessError:
            return True
    return proc.poll() is not None


def _stop_process(proc, folder):
    """Stop a started ACL2 and everything in its process group, and remove
    its socket folder.  Safe to call more than once; also run at interpreter
    exit (``weakref.finalize``) when nothing called it before."""
    try:
        if proc.stdin is not None:
            proc.stdin.close()
    except OSError:
        pass
    # Signal the group only while its leader is unreaped: until then the
    # group id cannot have been handed to anything else.
    if proc.returncode is None:
        try:
            _os.killpg(proc.pid, _signal.SIGTERM)
            deadline = _time.monotonic() + 2.0
            while not _leader_exited(proc) and _time.monotonic() < deadline:
                _time.sleep(0.05)
            if proc.returncode is None:
                _os.killpg(proc.pid, _signal.SIGKILL)   # stragglers too
        except (ProcessLookupError, PermissionError):
            pass
        try:
            proc.wait(5.0)
        except _subprocess.TimeoutExpired:
            pass
    _shutil.rmtree(folder, ignore_errors=True)


class _Launched:
    """An ACL2 process started here, serving the bridge on a Unix socket in
    a private folder.  It runs in its own process group (an ``acl2`` script
    may start Lisp as a child), which is stopped by ``close`` or, failing
    that, when the interpreter exits."""

    def __init__(self, command="acl2", startup_timeout=300.0):
        exe = _shutil.which(command)
        if exe is None:
            raise FileNotFoundError(f"no executable {command!r}")
        self._dir = _tempfile.mkdtemp(prefix="clausal_acl2_")
        self.socket_path = _os.path.join(self._dir, "bridge.sock")
        try:
            self.proc = _subprocess.Popen(
                [exe], stdin=_subprocess.PIPE, stdout=_subprocess.DEVNULL,
                stderr=_subprocess.DEVNULL, text=True, start_new_session=True)
        except BaseException:
            _shutil.rmtree(self._dir, ignore_errors=True)
            raise
        self._finalizer = _weakref.finalize(self, _stop_process, self.proc, self._dir)
        try:
            # ACL2 keeps reading its REPL from stdin after the bridge starts,
            # so stdin stays open; closing it would end the session.
            self.proc.stdin.write(
                '(include-book "centaur/bridge/top" :dir :system)\n'
                f'(bridge::start "{self.socket_path}")\n')
            self.proc.stdin.flush()
            deadline = _time.monotonic() + startup_timeout
            while not _os.path.exists(self.socket_path):
                if _leader_exited(self.proc) or _time.monotonic() > deadline:
                    raise ConnectionError(
                        f"{command} did not start an ACL2 bridge at {self.socket_path}")
                _time.sleep(0.2)
        except BaseException:
            self.close()
            raise

    def exited(self, wait=0.0) -> bool:
        """Whether the process has ended (waiting up to *wait* seconds);
        it is not reaped, so ``close`` can still stop its group."""
        deadline = _time.monotonic() + wait
        while not _leader_exited(self.proc):
            if _time.monotonic() >= deadline:
                return False
            _time.sleep(0.05)
        return True

    def close(self):
        self._finalizer()


_bridge = None
_launched = None
_settings: dict = {}
_lock = _threading.Lock()


def _names_a_bridge(opts) -> bool:
    return "socket" in opts or "host" in opts or "port" in opts


def _where(opts) -> str:
    """The bridge the settings name, as errors report it."""
    if "socket" in opts:
        return str(opts["socket"])
    if _names_a_bridge(opts):
        return f"{opts.get('host', '127.0.0.1')}:{opts.get('port', 55432)}"
    return str(opts.get("command", "acl2"))


def _get_bridge(pred):
    """The current bridge: connect on first use, starting ACL2 if no
    running bridge was named (``use_acl2/1``).  After a connection was lost
    this connects again, to the started ACL2 if it is still running, else
    to a newly started one."""
    global _bridge, _launched
    bridge = _bridge
    if bridge is not None:
        return bridge
    with _lock:
        if _bridge is None:
            opts = dict(_settings)
            try:
                if _names_a_bridge(opts):
                    _bridge = _connect(opts.get("socket"), opts.get("host"),
                                       opts.get("port"), opts.get("timeout"))
                else:
                    if _launched is not None and _launched.exited():
                        _launched.close()
                        _launched = None
                    if _launched is None:
                        _launched = _Launched(opts.get("command", "acl2"),
                                              float(opts.get("startup_timeout", 300.0)))
                    _bridge = _connect(_launched.socket_path, timeout=opts.get("timeout"))
            except (OSError, BridgeError) as exc:
                raise LogicException(existence_error(
                    "acl2_bridge", text_result(_where(opts)), f"{pred}: {exc}")) from exc
        return _bridge


def _lost(bridge, pred, exc):
    """Forget a connection that broke (stopping a started ACL2 that has
    died); the ``existence_error`` to raise."""
    global _bridge, _launched
    with _lock:
        bridge.close()
        if _bridge is bridge:
            _bridge = None
            if _launched is not None and _launched.exited(wait=1.0):
                _launched.close()
                _launched = None
        where = _where(_settings)
    return LogicException(existence_error(
        "acl2_bridge", text_result(where), f"{pred}: {exc}"))


def _reset(settings=None, bridge=None):
    """Forget the current bridge (closing what this module started)."""
    global _bridge, _launched, _settings
    with _lock:
        if _bridge is not None and bridge is None:
            _bridge.close()
        if _launched is not None:
            _launched.close()
        _bridge, _launched, _settings = bridge, None, dict(settings or {})


def _acl2_error(message, pred):
    return LogicException((
        "error", ("acl2_error", text_result(message.strip())), text_result(pred)))


def _call(kind, text, pred):
    """Send one command to the current bridge: ``(output, returned_text)``."""
    bridge = _get_bridge(pred)
    try:
        return bridge.command(kind, text)
    except BridgeError as exc:
        raise _acl2_error(str(exc), pred) from exc
    except OSError as exc:
        raise _lost(bridge, pred, exc) from exc


def _result(text, pred):
    """The term for what the bridge returned."""
    try:
        return from_lisp(text)
    except _ReadError as exc:
        raise _acl2_error(f"ACL2 returned text that is not an ACL2 object ({exc}): "
                          f"{text[:200]}", pred) from exc


def _run(kind, form, pred):
    return _call(kind, to_lisp(form, pred), pred)


# ── Predicates ───────────────────────────────────────────────────────────

def _acl2_2(form, value, trail, k):
    _out, returned = _run("LISP", form, "acl2/2")
    if unify(value, _result(returned, "acl2/2"), trail):
        yield None


def _acl2_3(form, value, output, trail, k):
    out, returned = _run("LISP", form, "acl2/3")
    if unify(value, _result(returned, "acl2/3"), trail) and unify(output, chars(out), trail):
        yield None


def _acl2_mv_2(form, values, trail, k):
    _out, returned = _run("LISP_MV", form, "acl2_mv/2")
    if unify(values, _list_items(_result(returned, "acl2_mv/2")), trail):
        yield None


def _ld_form(event_text: str) -> str:
    """``ld`` of one event, quiet, in ACL2's MAIN thread
    (``bridge::in-main-thread``): the bridge evaluates commands in worker
    threads, and memoization and hons -- which proofs use -- belong to the
    main thread (books/centaur/bridge/top.lisp).

    With ``:ld-error-action :return!``, ``ld`` returns ``(mv nil :eof
    state)`` when it read every form without an error, and ``(mv nil
    (:stop-ld n) state)`` when a form was rejected -- ERP is NIL BOTH ways;
    a non-NIL ERP is ``ld`` itself refusing its arguments (ACL2 8.7,
    ``ld-return-error`` and ``ld-read-eval-print`` in ld.lisp)."""
    return (f"(bridge::in-main-thread (ld '({event_text}) :ld-pre-eval-print nil"
            f" :ld-post-eval-print nil :ld-verbose nil :ld-error-action :return!))")


def _ld_accepted(values) -> bool:
    """Whether ``ld``'s answer ``(erp val state)`` says every form was
    accepted: ERP is NIL and the reason ``ld`` stopped is ``:eof``."""
    return len(values) >= 2 and values[0] == "nil" and values[1] == ":eof"


def _event(form, pred):
    out, returned = _call("LISP_MV", _ld_form(to_lisp(form, pred)), pred)
    return out, _ld_accepted(_list_items(_result(returned, pred)))


def _event_1(form, trail, k):
    _out, ok = _event(form, "event/1")
    if ok:
        yield None


def _event_2(form, output, trail, k):
    out, ok = _event(form, "event/2")
    if ok and unify(output, chars(out), trail):
        yield None


def _thm_1(term, trail, k):
    _out, ok = _event(_make_list(["thm", deref(term)]), "thm/1")
    if ok:
        yield None


def _thm_2(term, output, trail, k):
    out, ok = _event(_make_list(["thm", deref(term)]), "thm/2")
    if ok and unify(output, chars(out), trail):
        yield None


def _acl2_text_2(term, text, trail, k):
    pred = "acl2_text/2"
    text_val = deref(text)
    if not is_var(text_val):
        source = to_text(text_val)
        if source is None:
            expect_type(text_val, str, pred, arg=2)
        try:
            parsed = from_lisp(source)
        except _ReadError as exc:
            raise LogicException(syntax_error_term("acl2_text", pred, str(exc))) from exc
        if unify(term, parsed, trail):
            yield None
        return
    if unify(text, chars(to_lisp(term, pred)), trail):
        yield None


# The options use_acl2/1 takes, and the kind of value each holds.
_OPTIONS = {"socket": "text", "host": "text", "command": "text", "port": "port",
            "timeout": "seconds", "startup_timeout": "seconds"}


def _option_value(name, value, pred):
    kind = _OPTIONS[name]
    if kind == "text":
        text = to_text(value)
        if text is None:
            raise LogicException(type_error("text", value, pred))
        return text
    if type(value) is bool or not isinstance(value, (int, float, Fraction)):
        raise LogicException(type_error("integer" if kind == "port" else "number",
                                        value, pred))
    if kind == "port":
        if type(value) is not int:
            raise LogicException(type_error("integer", value, pred))
        if not 0 < value < 65536:
            raise LogicException(domain_error("port_number", value, pred))
        return value
    if not value > 0 or value != value or value == float("inf"):
        raise LogicException(domain_error("positive_number", value, pred))
    return float(value)


def _use_acl2_1(options, trail, k):
    pred = "use_acl2/1"
    options = deref(options)
    from clausal.terms import DictTerm  # noqa: PLC0415
    if not isinstance(options, (dict, DictTerm)):
        expect_type(options, dict, pred, arg=1)
    for key in list(options.keys()):
        key = deref(key)
        if to_text(key) not in _OPTIONS:
            raise LogicException(domain_error(
                "acl2_option", key, f"{pred}: the options are {', '.join(_OPTIONS)}"))
    settings = {}
    for name in _OPTIONS:
        if has_option(options, name):
            settings[name] = _option_value(name, deref(option(options, name)), pred)
    _reset(settings)
    yield None


acl2 = ModulePredicate("acl2")
acl2._register(2, simple_to_trampoline(_acl2_2))
acl2._register(3, simple_to_trampoline(_acl2_3))

acl2_mv = ModulePredicate("acl2_mv")
acl2_mv._register(2, simple_to_trampoline(_acl2_mv_2))

event = ModulePredicate("event")
event._register(1, simple_to_trampoline(_event_1))
event._register(2, simple_to_trampoline(_event_2))

thm = ModulePredicate("thm")
thm._register(1, simple_to_trampoline(_thm_1))
thm._register(2, simple_to_trampoline(_thm_2))

acl2_text = ModulePredicate("acl2_text")
acl2_text._register(2, simple_to_trampoline(_acl2_text_2))

use_acl2 = ModulePredicate("use_acl2")
use_acl2._register(1, simple_to_trampoline(_use_acl2_1))
