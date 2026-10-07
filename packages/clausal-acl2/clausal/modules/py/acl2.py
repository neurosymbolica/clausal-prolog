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
  cannot
- ``acl2_text(Term, Text)`` -- a term and its ACL2 text, either way: parse
  ``Text`` when it is bound, else print ``Term`` (``if`` and other Python
  keywords cannot be functors in the seam, but can be written in text)
- ``use_acl2(Options)`` -- which ACL2: ``{"socket": Path}`` or
  ``{"host": H, "port": N}`` for a running bridge, or ``{"command": Cmd}``
  to start one (``acl2`` on PATH by default, also on first use)

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
``existence_error(acl2_bridge, Where)`` when no bridge answers;
``error(acl2_error(Message), _)`` when ACL2 signals an error evaluating a form.
"""

from __future__ import annotations

import os as _os
import re as _re
import shutil as _shutil
import socket as _socket
import subprocess as _subprocess
import tempfile as _tempfile
import threading as _threading
import time as _time
from fractions import Fraction

from clausal.logic.cells import TUPLE_TAG, chars, chars_text, is_chars
from clausal.logic.exceptions import (
    LogicException, existence_error, instantiation_error, type_error,
)
from clausal.logic.to_python import to_python
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


class _Reader:
    """Reads what ACL2 prints with ``prin1`` (*package* ACL2): conses,
    symbols (packages, bars, escapes), keywords, strings, characters,
    integers, ratios, ``#C`` complexes, and ``'x``."""

    def __init__(self, text):
        self.s, self.i = text, 0

    def _ws(self):
        while self.i < len(self.s) and self.s[self.i] in " \t\r\n\f":
            self.i += 1

    def read(self):
        self._ws()
        s, c = self.s, self.s[self.i]
        if c == "(":
            self.i += 1
            items, tail = [], "nil"
            while True:
                self._ws()
                if s[self.i] == ")":
                    self.i += 1
                    return _make_list(items, tail)
                if s[self.i] == "." and s[self.i + 1] in " \t\r\n()":
                    self.i += 1
                    tail = self.read()
                    continue
                items.append(self.read())
        if c == "'":
            self.i += 1
            return _make_list(["quote", self.read()])
        if c == '"':
            out, j = [], self.i + 1
            while s[j] != '"':
                if s[j] == "\\":
                    j += 1
                out.append(s[j]); j += 1
            self.i = j + 1
            return chars("".join(out))
        if s.startswith("#\\", self.i):
            j = self.i + 3
            while j < len(s) and s[j] not in " \t\r\n()":
                j += 1
            name = s[self.i + 2:j]
            self.i = j
            if len(name) == 1:
                return (CHAR_TAG, name)
            named = {v.lower(): k for k, v in _CHAR_NAMES.items()}
            named.update({"linefeed": "\n", "nul": "\x00", "null": "\x00"})
            return (CHAR_TAG, named.get(name.lower(), name[0]))
        if s.startswith(("#C(", "#c("), self.i):
            self.i += 2
            re_, im = _list_items(self.read())
            return (COMPLEX_TAG, re_, im)
        return self._token()

    def _token(self):
        s, j = self.s, self.i
        parts, pkg, name, barred = [], None, [], False
        while j < len(s) and s[j] not in " \t\r\n()'\"":
            if s[j] == "|":
                k = j + 1
                while s[k] != "|":
                    if s[k] == "\\":
                        k += 1
                    name.append(s[k]); k += 1
                barred, j = True, k + 1
            elif s[j] == "\\":
                name.append(s[j + 1]); j += 2
                barred = True
            elif s[j] == ":":
                pkg = "".join(name)
                name, barred = [], False
                j += 2 if s.startswith("::", j) else 1
            else:
                name.append(s[j].upper()); j += 1
        self.i = j
        text = "".join(name)
        if pkg is None and not barred:
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
    """The Clausal term for ACL2's printed text of one object."""
    return _Reader(text).read()


# ── The bridge connection ────────────────────────────────────────────────

class BridgeError(Exception):
    """ACL2 sent an ERROR message."""


class _Bridge:
    """One connection to an ACL2 Bridge server.  Messages are
    ``TYPE LEN\\nCONTENT\\n`` with LEN in characters (bridge-raw.lsp)."""

    def __init__(self, sock: _socket.socket, where: str):
        self.where = where
        self._sock = sock
        self._r = sock.makefile("r", encoding="utf-8", newline="")
        self._w = sock.makefile("w", encoding="utf-8", newline="")
        self._lock = _threading.Lock()
        kind, self.hello = self._message()
        if kind != "ACL2_BRIDGE_HELLO":
            raise BridgeError(f"not an ACL2 bridge: first message {kind!r}")

    def _message(self):
        header = self._r.readline()
        if not header:
            raise ConnectionError(f"the ACL2 bridge at {self.where} closed the connection")
        kind, length = header.rstrip("\n").split(" ")
        content = self._r.read(int(length))
        self._r.read(1)                      # the newline after the content
        return kind, content

    def command(self, kind: str, text: str):
        """Send one command; ``(output, returned_text)``.  Raises
        ``BridgeError`` on an ERROR reply."""
        with self._lock:
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

    def close(self):
        try:
            self._sock.close()
        except OSError:
            pass


def _connect(socket_path=None, host=None, port=None, timeout=None):
    if socket_path is not None:
        sock = _socket.socket(_socket.AF_UNIX, _socket.SOCK_STREAM)
        sock.settimeout(timeout)
        sock.connect(socket_path)
        return _Bridge(sock, socket_path)
    sock = _socket.create_connection((host or "127.0.0.1", int(port or 55432)), timeout)
    return _Bridge(sock, f"{host}:{port}")


class _Launched:
    """An ACL2 process started here, serving the bridge on a Unix socket."""

    def __init__(self, command="acl2", startup_timeout=300.0):
        exe = _shutil.which(command)
        if exe is None:
            raise FileNotFoundError(command)
        self._dir = _tempfile.mkdtemp(prefix="clausal_acl2_")
        self.socket_path = _os.path.join(self._dir, "bridge.sock")
        self.proc = _subprocess.Popen(
            [exe], stdin=_subprocess.PIPE, stdout=_subprocess.DEVNULL,
            stderr=_subprocess.DEVNULL, text=True)
        # ACL2 keeps reading its REPL from stdin after the bridge starts, so
        # stdin stays open; closing it would end the session.
        self.proc.stdin.write(
            '(include-book "centaur/bridge/top" :dir :system)\n'
            f'(bridge::start "{self.socket_path}")\n')
        self.proc.stdin.flush()
        deadline = _time.monotonic() + startup_timeout
        while not _os.path.exists(self.socket_path):
            if self.proc.poll() is not None or _time.monotonic() > deadline:
                self.close()
                raise ConnectionError(
                    f"{command} did not start an ACL2 bridge at {self.socket_path}")
            _time.sleep(0.2)

    def close(self):
        if self.proc.poll() is None:
            self.proc.terminate()
        _shutil.rmtree(self._dir, ignore_errors=True)


_bridge = None
_launched = None
_settings: dict = {}
_lock = _threading.Lock()


def _get_bridge(pred):
    """The current bridge: connect on first use, starting ACL2 if no
    running bridge was named (``use_acl2/1``)."""
    global _bridge, _launched
    if _bridge is not None:
        return _bridge
    with _lock:
        if _bridge is None:
            opts = dict(_settings)
            where = opts.get("socket") or (
                f"{opts['host']}:{opts.get('port', 55432)}" if "host" in opts or "port" in opts
                else opts.get("command", "acl2"))
            try:
                if "socket" in opts or "host" in opts or "port" in opts:
                    _bridge = _connect(opts.get("socket"), opts.get("host"),
                                       opts.get("port"), opts.get("timeout"))
                else:
                    _launched = _Launched(opts.get("command", "acl2"),
                                          float(opts.get("startup_timeout", 300.0)))
                    _bridge = _connect(_launched.socket_path)
            except (OSError, ConnectionError, BridgeError) as exc:
                raise LogicException(existence_error(
                    "acl2_bridge", text_result(str(where)), f"{pred}: {exc}")) from exc
    return _bridge


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


def _run(kind, form, pred):
    text = to_lisp(form, pred)
    try:
        return _get_bridge(pred).command(kind, text)
    except BridgeError as exc:
        raise _acl2_error(str(exc), pred) from exc


# ── Predicates ───────────────────────────────────────────────────────────

def _acl2_2(form, value, trail, k):
    _out, returned = _run("LISP", form, "acl2/2")
    if unify(value, from_lisp(returned), trail):
        yield None


def _acl2_3(form, value, output, trail, k):
    out, returned = _run("LISP", form, "acl2/3")
    if unify(value, from_lisp(returned), trail) and unify(output, chars(out), trail):
        yield None


def _acl2_mv_2(form, values, trail, k):
    _out, returned = _run("LISP_MV", form, "acl2_mv/2")
    if unify(values, _list_items(from_lisp(returned)), trail):
        yield None


def _ld_form(event_text: str) -> str:
    """``ld`` of one event, quiet, returning (mv erp val state) -- ERP is
    NIL exactly when the event was accepted.  In ACL2's MAIN thread
    (``bridge::in-main-thread``): the bridge evaluates commands in worker
    threads, and memoization and hons -- which proofs use -- belong to the
    main thread (books/centaur/bridge/top.lisp)."""
    return (f"(bridge::in-main-thread (ld '({event_text}) :ld-pre-eval-print nil"
            f" :ld-post-eval-print nil :ld-verbose nil :ld-error-action :return!))")


def _event(form, pred):
    text = _ld_form(to_lisp(form, pred))
    try:
        out, returned = _get_bridge(pred).command("LISP_MV", text)
    except BridgeError as exc:
        raise _acl2_error(str(exc), pred) from exc
    values = _list_items(from_lisp(returned))
    return out, bool(values) and values[0] == "nil"


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
        except (IndexError, ValueError) as exc:
            raise LogicException(syntax_error_term("acl2_text", pred, str(exc))) from exc
        if unify(term, parsed, trail):
            yield None
        return
    if unify(text, chars(to_lisp(term, pred)), trail):
        yield None


_OPTIONS = ("socket", "host", "port", "command", "timeout", "startup_timeout")


def _use_acl2_1(options, trail, k):
    options = deref(options)
    from clausal.terms import DictTerm  # noqa: PLC0415
    if not isinstance(options, (dict, DictTerm)):
        expect_type(options, dict, "use_acl2/1", arg=1)
    settings = {}
    for name in _OPTIONS:
        if has_option(options, name):
            value = deref(option(options, name))
            text = to_text(value)
            settings[name] = text if text is not None else to_python(value)
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
