"""Prolog operator table — ISO 13211-1 defaults plus SWI/Scryer extensions."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class OpEntry:
    precedence: int   # 1–1200
    specifier: str    # xf, yf, xfx, xfy, yfx, fy, fx
    name: str         # operator name (atom)


class OperatorTable:
    """Mutable operator table with ISO defaults + dialect extensions."""

    def __init__(self):
        self._ops: dict[str, list[OpEntry]] = {}
        self._default_names: set[str] = set()

    def define(self, prec: int, spec: str, name: str) -> None:
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
