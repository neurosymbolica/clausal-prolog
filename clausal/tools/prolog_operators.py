"""Prolog operator table — ISO 13211-1 defaults plus SWI/Scryer extensions."""

from __future__ import annotations

import threading
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class OpEntry:
    precedence: int   # 1–1200
    specifier: str    # xf, yf, xfx, xfy, yfx, fy, fx
    name: str         # operator name (atom)


#: Guards every change to, and every walk of, an operator table, and makes
#: op/3's check-then-define one step: ``with op_lock:`` around
#: :func:`op_error` and the ``define`` calls it clears.  Re-entrant, so
#: ``define`` and ``entries`` take it themselves.  One lock for all tables
#: (a table change is rare and short).
op_lock = threading.RLock()


class OperatorTable:
    """Mutable operator table with ISO defaults + dialect extensions."""

    def __init__(self):
        self._ops: dict[str, list[OpEntry]] = {}
        self._default_names: set[str] = set()
        #: Bumped by every :meth:`define`: a reader of the table can cache
        #: what it computed from it and recompute only when this moves.
        self.version = 0

    def copy(self) -> "OperatorTable":
        """An independent table with the same operators (a reader that
        must not change this one -- ``read/1`` of an ``op/3`` directive --
        reads with a copy)."""
        with op_lock:
            new = OperatorTable()
            new._ops = {k: list(v) for k, v in self._ops.items()}
            new._default_names = set(self._default_names)
            new.version = self.version
        return new

    def define(self, prec: int, spec: str, name: str) -> None:
        """Set *name*'s operator of *spec*'s class (prefix, infix or
        postfix) to *prec*, or remove it when *prec* is 0.  Unchecked: the
        ISO permission checks are :func:`op_error`'s, which ``op/3`` makes
        before it gets here (a dialect table may hold what ISO refuses)."""
        with op_lock:
            self._define(prec, spec, name)

    def _define(self, prec: int, spec: str, name: str) -> None:
        self.version += 1
        # Replace any existing entry of the same specifier class.
        kind = _specifier_kind(spec)
        if name in self._ops:
            self._ops[name] = [
                e for e in self._ops[name]
                if _specifier_kind(e.specifier) != kind
            ]
        if prec == 0:
            # op(0, Spec, Name) REMOVES the operator of this kind rather than
            # defining a priority-0 one (ISO 8.14.3.4) — F038.
            if name in self._ops and not self._ops[name]:
                del self._ops[name]
            return
        self._ops.setdefault(name, []).append(OpEntry(prec, spec, name))

    def lookup_infix(self, name: str) -> OpEntry | None:
        for e in self._ops.get(name, []):
            if e.specifier in ("xfx", "xfy", "yfx"):
                return e
        return None

    def lookup_prefix(self, name: str) -> OpEntry | None:
        for e in self._ops.get(name, []):
            if e.specifier in ("fx", "fy"):
                return e
        return None

    def lookup_postfix(self, name: str) -> OpEntry | None:
        for e in self._ops.get(name, []):
            if e.specifier in ("xf", "yf"):
                return e
        return None

    def entries(self):
        """Every operator in the table, as :class:`OpEntry` s: a snapshot
        list, so a define in another thread (or between two answers) cannot
        disturb the walk."""
        with op_lock:
            return [e for es in list(self._ops.values()) for e in es]

    def is_operator(self, name: str) -> bool:
        return name in self._ops and len(self._ops[name]) > 0

    def user_defined(self) -> list[OpEntry]:
        result = []
        for name, entries in self._ops.items():
            if name not in self._default_names:
                result.extend(entries)
        return result

    def _define_default(self, prec: int, spec: str, name: str) -> None:
        """Define an operator and mark it as a default (not user-defined)."""
        self.define(prec, spec, name)
        self._default_names.add(name)

    @classmethod
    def iso_default(cls) -> OperatorTable:
        t = cls()
        _load_iso(t)
        return t

    @classmethod
    def swi_default(cls) -> OperatorTable:
        t = cls()
        _load_iso(t)
        _load_swi(t)
        return t

    @classmethod
    def scryer_default(cls) -> OperatorTable:
        t = cls()
        _load_iso(t)
        _load_scryer(t)
        return t

    @classmethod
    def scryer_builtin_default(cls) -> OperatorTable:
        """What Scryer's toplevel has with NO library loaded: ISO plus
        ``+`` fy 200, ``div`` and ``rdiv`` yfx 400 (each verified against
        Scryer).  ``scryer_default`` adds library(clpz)'s operators, which a
        consulted file imports; this table is what an uncaught error prints
        with, so it has none of them."""
        t = cls()
        _load_iso(t)
        _load_scryer_builtin(t)
        return t

    @classmethod
    def gprolog_default(cls) -> OperatorTable:
        t = cls()
        _load_iso(t)
        _load_gprolog(t)
        return t

    @classmethod
    def trealla_default(cls) -> OperatorTable:
        t = cls()
        _load_iso(t)
        _load_trealla(t)
        return t


#: ISO 8.14.3's operator specifiers.
SPECIFIERS = ("xfx", "xfy", "yfx", "fy", "fx", "xf", "yf")


def op_error(table: "OperatorTable | None", prec: int, spec: str,
             names: list) -> "tuple | None":
    """The ISO 8.14.3.3 error ``op(prec, spec, names)`` raises, as a tuple
    of its formal's name and arguments, or ``None`` when it may be applied.

    The caller has made the instantiation and type checks: *prec* is an
    int, *spec* and every one of *names* an atom's spelling (``'[]'`` for
    the empty list).  Checked here, in this order (ISO 7.12 leaves the
    order open; it is not Scryer's in every case):

    * ``,`` cannot be changed: ``permission_error(modify, operator, ',')``,
      whatever the priority and specifier (8.14.3.3 h, i);
    * ``domain_error(operator_priority, P)`` outside 0..1200 and
      ``domain_error(operator_specifier, S)`` for any other atom (f, g);
    * ``permission_error(create, operator, N)`` (j, k, and Cor.2) when *N*
      is ``[]`` or ``{}``; when it is ``|`` and the operator is not infix
      with priority 1001 or more (``op(0, _, '|')`` removes, and is
      allowed); and when the operator would leave *N* both infix and
      postfix (6.3.4.3) in *table* -- not checked when *table* is None.
    """
    if "," in names:
        return ("permission_error", "modify", "operator", ",")
    if not 0 <= prec <= 1200:
        return ("domain_error", "operator_priority", prec)
    if spec not in SPECIFIERS:
        return ("domain_error", "operator_specifier", spec)
    kind = _specifier_kind(spec)
    for n in names:
        if n in ("[]", "{}"):
            return ("permission_error", "create", "operator", n)
        if n == "|" and prec != 0 and (kind != "infix" or prec < 1001):
            return ("permission_error", "create", "operator", n)
        if prec != 0 and table is not None and kind != "prefix":
            other = (table.lookup_postfix(n) if kind == "infix"
                     else table.lookup_infix(n))
            if other is not None:
                return ("permission_error", "create", "operator", n)
    return None


def _specifier_kind(spec: str) -> str:
    if spec in ("fx", "fy"):
        return "prefix"
    if spec in ("xf", "yf"):
        return "postfix"
    return "infix"


# ── ISO 13211-1 Table 7 ─────────────────────────────────────────────

def _load_iso(t: OperatorTable) -> None:
    d = t._define_default
    d(1200, "xfx", ":-")
    d(1200, "xfx", "-->")
    d(1200, "fx", ":-")
    d(1200, "fx", "?-")
    d(1100, "xfy", ";")
    d(1050, "xfy", "->")
    d(1000, "xfy", ",")
    d(900, "fy", "\\+")
    d(700, "xfx", "=")
    d(700, "xfx", "\\=")
    d(700, "xfx", "==")
    d(700, "xfx", "\\==")
    d(700, "xfx", "is")
    d(700, "xfx", "=:=")
    d(700, "xfx", "=\\=")
    d(700, "xfx", "<")
    d(700, "xfx", ">")
    d(700, "xfx", ">=")
    d(700, "xfx", "=<")
    d(700, "xfx", "=..")
    # Standard-order-of-terms comparison (ISO Table 7) — F026.
    d(700, "xfx", "@<")
    d(700, "xfx", "@>")
    d(700, "xfx", "@=<")
    d(700, "xfx", "@>=")
    d(600, "xfy", ":")
    # ^ — bagof/setof existential quantifier and integer power (F026).
    d(200, "xfy", "^")
    d(500, "yfx", "+")
    d(500, "yfx", "-")
    d(500, "yfx", "/\\")
    d(500, "yfx", "\\/")
    d(400, "yfx", "*")
    d(400, "yfx", "/")
    d(400, "yfx", "//")
    d(400, "yfx", "rem")
    d(400, "yfx", "mod")
    d(400, "yfx", "<<")
    d(400, "yfx", ">>")
    d(200, "xfx", "**")
    d(200, "fy", "-")
    d(200, "fy", "\\")


# ── SWI additions ────────────────────────────────────────────────────

def _load_swi(t: OperatorTable) -> None:
    d = t._define_default
    d(200, "fy", "+")       # prefix plus
    d(700, "xfx", ">:<")   # dict partial unification
    d(700, "xfx", ":<")    # dict unification
    d(500, "yfx", "xor")
    d(400, "yfx", "rdiv")
    d(400, "yfx", "div")    # floored integer division (F026)
    # Prefix directive operators (1150 fx) so `:- dynamic p/1.` parses in the
    # documented bare-prefix form, not only `:- dynamic(p/1).` (F027).
    for _name in ("dynamic", "discontiguous", "multifile", "module_transparent",
                  "initialization", "volatile", "public", "meta_predicate",
                  "table"):
        d(1150, "fx", _name)
    # Parsed so the AST is built and the translator emits the designed
    # rejection, rather than generic token soup (F041).
    d(1050, "xfy", "*->")   # soft cut
    d(700, "xfx", "=@=")    # variant equivalence
    d(700, "xfx", "\\=@=")  # not variant


# ── Scryer additions ────────────────────────────────────────────────

def _load_scryer(t: OperatorTable) -> None:
    d = t._define_default
    # CLP(Z) operators (loaded via library(clpz))
    d(700, "xfx", "#=")
    d(700, "xfx", "#\\=")
    d(700, "xfx", "#<")
    d(700, "xfx", "#>")
    d(700, "xfx", "#=<")
    d(700, "xfx", "#>=")


def _load_scryer_builtin(t: OperatorTable) -> None:
    d = t._define_default
    d(200, "fy", "+")
    d(400, "yfx", "div")
    d(400, "yfx", "rdiv")


# ── GNU Prolog additions ──────────────────────────────────────────────

def _load_gprolog(t: OperatorTable) -> None:
    d = t._define_default
    # FD constraint operators (built-in, no library import needed)
    d(700, "xfx", "#=")
    d(700, "xfx", "#\\=")
    d(700, "xfx", "#<")
    d(700, "xfx", "#>")
    d(700, "xfx", "#=<")
    d(700, "xfx", "#>=")
    d(700, "xfx", "#=#")    # FD equality (reified)
    d(700, "xfx", "#\\=#")  # FD disequality (reified)


def _load_trealla(t: OperatorTable) -> None:
    d = t._define_default
    # CLP(Z) operators (same as Scryer — loaded via library(clpz))
    d(700, "xfx", "#=")
    d(700, "xfx", "#\\=")
    d(700, "xfx", "#<")
    d(700, "xfx", "#>")
    d(700, "xfx", "#=<")
    d(700, "xfx", "#>=")


# ── the run-time table ───────────────────────────────────────────────

#: The process-wide operator table ``op/3`` and ``current_op/3`` act on
#: (ISO 8.14.3: one table, which every op/3 changes).  A ``.pl`` file
#: applies to it what is global in Scryer: the ``op/3`` directives of a
#: file that is not a module, and the ops a module EXPORTS (a module's own
#: unexported ``op/3`` stays in the table that file is read with).  Each
#: file is still READ with its own fresh table (``iso_l3.reader_op_table``).
_RUNTIME: "OperatorTable | None" = None
_RUNTIME_DEFAULT_VERSION = 0


def runtime_op_table() -> OperatorTable:
    """The process-wide run-time operator table, created on first use with
    the defaults the native reader reads with (Scryer's table with no
    library loaded, ``scryer_builtin_default``).  Always the same object:
    :func:`reset_runtime_op_table` resets it in place."""
    global _RUNTIME, _RUNTIME_DEFAULT_VERSION
    if _RUNTIME is None:
        _RUNTIME = OperatorTable.scryer_builtin_default()
        _RUNTIME_DEFAULT_VERSION = _RUNTIME.version
    return _RUNTIME


def reset_runtime_op_table() -> None:
    """Put the run-time table back to its defaults (in place, so a held
    reference stays good; its ``version`` moves on, so a cache keyed on it
    is invalidated)."""
    global _RUNTIME_DEFAULT_VERSION
    t = runtime_op_table()
    fresh = OperatorTable.scryer_builtin_default()
    with op_lock:
        t._ops = fresh._ops
        t._default_names = fresh._default_names
        t.version += 1
        _RUNTIME_DEFAULT_VERSION = t.version


def runtime_op_table_is_default() -> bool:
    """True when nothing has been defined in the run-time table since it was
    created or last reset -- a cheap test (no walk of the table).  An op
    defined and then removed again counts as a change."""
    return runtime_op_table().version == _RUNTIME_DEFAULT_VERSION
