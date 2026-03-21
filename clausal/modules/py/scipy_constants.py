"""clausal.modules.py.scipy_constants — scipy.constants predicates for Clausal.

Provides physical constants and unit conversions from ``scipy.constants``
as importable predicate objects for use in .clausal files via::

    -import_from(scipy_constants, [Value, Unit, Precision, Lookup,
                                    Find, AllNames,
                                    SpeedOfLight, PlanckConstant,
                                    ReducedPlanckConstant, GravitationalConstant,
                                    AvogadroConstant, BoltzmannConstant,
                                    ElementaryCharge, ElectronMass, ProtonMass,
                                    ElectronVolt, StandardAtmosphere,
                                    Kilo, Mega, Giga])

All predicates are **Tier 1 — pure**: no computation; direct attribute
lookups or CODATA-database queries.

Predicate catalogue
-------------------
CODATA lookup by name string (445 constants from physical_constants dict):
    Value(NAME, RESULT)                          — value (float)
    Unit(NAME, RESULT)                           — unit string
    Precision(NAME, RESULT)                      — relative uncertainty
    Lookup(NAME, VALUE, UNIT, UNCERTAINTY)       — all three in one call
    Find(SUBSTRING, NAMES)                       — names matching a substring
    AllNames(NAMES)                              — all 445 CODATA constant names

Physical constants (no input arguments):
    SpeedOfLight(RESULT)          — c = 299 792 458 m s⁻¹
    PlanckConstant(RESULT)        — h = 6.626 070 15 × 10⁻³⁴ J s
    ReducedPlanckConstant(RESULT) — ℏ = h / (2π)
    GravitationalConstant(RESULT) — G = 6.674 3 × 10⁻¹¹ N m² kg⁻²
    AvogadroConstant(RESULT)      — Nₐ = 6.022 140 76 × 10²³ mol⁻¹
    BoltzmannConstant(RESULT)     — k = 1.380 649 × 10⁻²³ J K⁻¹
    ElementaryCharge(RESULT)      — e = 1.602 176 634 × 10⁻¹⁹ C
    ElectronMass(RESULT)          — mₑ = 9.109 383 7139 × 10⁻³¹ kg
    ProtonMass(RESULT)            — mₚ = 1.672 621 925 95 × 10⁻²⁷ kg

Unit conversion / SI prefix factors:
    ElectronVolt(RESULT)       — 1 eV in joules
    StandardAtmosphere(RESULT) — 1 atm in pascals
    Kilo(RESULT)               — 1 × 10³
    Mega(RESULT)               — 1 × 10⁶
    Giga(RESULT)               — 1 × 10⁹
"""

from __future__ import annotations

import threading as _threading
from typing import Callable

from clausal.logic.variables import deref, unify
from clausal.logic.trampoline import DONE


# ── Lazy scipy.constants import ────────────────────────────────────────────

_scipy_constants = None
_constants_lock = _threading.Lock()


def _ensure_constants():
    global _scipy_constants
    if _scipy_constants is not None:
        return
    with _constants_lock:
        if _scipy_constants is not None:
            return
        from clausal.modules.py import _import_stdlib
        _scipy_constants = _import_stdlib("scipy.constants")


def _sc():
    _ensure_constants()
    return _scipy_constants


# ── Predicate adapter ──────────────────────────────────────────────────────

class _ConstantsPredicate:
    """Dispatch adapter for a scipy.constants predicate.

    Supports multiple arities via ``_register(arity, fn)``.
    Arity counts include RESULT but not trail.
    """

    __slots__ = ("_name", "_dispatch_fns")

    def __init__(self, name: str) -> None:
        self._name = name
        self._dispatch_fns: dict[int, Callable] = {}

    def _register(self, arity: int, fn: Callable) -> "_ConstantsPredicate":
        self._dispatch_fns[arity] = fn
        return self

    def _get_dispatch(self) -> Callable:
        if len(self._dispatch_fns) == 1:
            return next(iter(self._dispatch_fns.values()))
        return self._multi_dispatch

    def _multi_dispatch(self, this_generator, parent, *args):
        arity = len(args) - 1  # exclude trail
        fn = self._dispatch_fns.get(arity)
        if fn is None:
            yield (parent, DONE)
            return
        yield from fn(this_generator, parent, *args)

    def __repr__(self) -> str:
        arities = sorted(self._dispatch_fns)
        return f"scipy.constants.{self._name}/{arities}"


# ── Dispatch helpers ───────────────────────────────────────────────────────

def _lookup_fn(call: Callable) -> Callable:
    """Return a trampoline dispatch function that calls call(*inputs) → RESULT."""
    def dispatch(this_generator, parent, *args):
        trail = args[-1]
        result_var = args[-2]
        inputs = [deref(x) for x in args[:-2]]
        try:
            out = call(*inputs)
        except Exception:
            yield (parent, DONE)
            return
        ok = bool(unify(result_var, out, trail))
        if ok:
            yield (parent, None)
        yield (parent, DONE)
    return dispatch


def _constant_fn(attr_name: str) -> Callable:
    """Return a trampoline dispatch for a zero-input constant attribute."""
    def dispatch(this_generator, parent, result_var, trail):
        try:
            out = getattr(_sc(), attr_name)
        except Exception:
            yield (parent, DONE)
            return
        ok = bool(unify(result_var, out, trail))
        if ok:
            yield (parent, None)
        yield (parent, DONE)
    return dispatch


def _pred(name: str, *arity_fns) -> _ConstantsPredicate:
    p = _ConstantsPredicate(name)
    for arity, fn in arity_fns:
        p._register(arity, fn)
    return p


# ── CODATA lookup predicates ───────────────────────────────────────────────

Value = _pred("Value",
    (2, _lookup_fn(lambda name: _sc().value(name))),
)

Unit = _pred("Unit",
    (2, _lookup_fn(lambda name: _sc().unit(name))),
)

Precision = _pred("Precision",
    (2, _lookup_fn(lambda name: _sc().precision(name))),
)


def _lookup_dispatch(this_generator, parent, name, value_var, unit_var, uncertainty_var, trail):
    name = deref(name)
    try:
        val, unit_str, uncertainty = _sc().physical_constants[name]
    except KeyError:
        yield (parent, DONE)
        return
    if not bool(unify(value_var, val, trail)):
        yield (parent, DONE)
        return
    if not bool(unify(unit_var, unit_str, trail)):
        yield (parent, DONE)
        return
    if not bool(unify(uncertainty_var, uncertainty, trail)):
        yield (parent, DONE)
        return
    yield (parent, None)
    yield (parent, DONE)


class _LookupPredicate:
    """Lookup(NAME, VALUE, UNIT, UNCERTAINTY) — access all three CODATA fields at once."""
    def _get_dispatch(self):
        return _lookup_dispatch
    def __repr__(self):
        return "scipy.constants.Lookup/4"


Lookup = _LookupPredicate()


def _find_dispatch(this_generator, parent, substring, names_var, trail):
    substring = deref(substring)
    try:
        names = _sc().find(substring, disp=False)
    except Exception:
        yield (parent, DONE)
        return
    if not bool(unify(names_var, list(names), trail)):
        yield (parent, DONE)
        return
    yield (parent, None)
    yield (parent, DONE)


def _find_all_dispatch(this_generator, parent, names_var, trail):
    try:
        names = list(_sc().physical_constants.keys())
    except Exception:
        yield (parent, DONE)
        return
    if not bool(unify(names_var, names, trail)):
        yield (parent, DONE)
        return
    yield (parent, None)
    yield (parent, DONE)


class _FindPredicate:
    """Find(SUBSTRING, NAMES) — list of CODATA constant names containing SUBSTRING."""
    def _get_dispatch(self):
        return _find_dispatch
    def __repr__(self):
        return "scipy.constants.Find/2"


class _AllNamesPredicate:
    """AllNames(NAMES) — list of all 445 CODATA constant names."""
    def _get_dispatch(self):
        return _find_all_dispatch
    def __repr__(self):
        return "scipy.constants.AllNames/1"


Find = _FindPredicate()
AllNames = _AllNamesPredicate()


# ── Physical constants (no input arguments) ────────────────────────────────

SpeedOfLight = _pred("SpeedOfLight",
    (1, _constant_fn("c")),
)

PlanckConstant = _pred("PlanckConstant",
    (1, _constant_fn("h")),
)

ReducedPlanckConstant = _pred("ReducedPlanckConstant",
    (1, _constant_fn("hbar")),
)

GravitationalConstant = _pred("GravitationalConstant",
    (1, _constant_fn("G")),
)

AvogadroConstant = _pred("AvogadroConstant",
    (1, _constant_fn("N_A")),
)

BoltzmannConstant = _pred("BoltzmannConstant",
    (1, _constant_fn("k")),
)

ElementaryCharge = _pred("ElementaryCharge",
    (1, _constant_fn("e")),
)

ElectronMass = _pred("ElectronMass",
    (1, _constant_fn("m_e")),
)

ProtonMass = _pred("ProtonMass",
    (1, _constant_fn("m_p")),
)


# ── Unit conversion / SI prefix factors ───────────────────────────────────

ElectronVolt = _pred("ElectronVolt",
    (1, _constant_fn("eV")),
)

StandardAtmosphere = _pred("StandardAtmosphere",
    (1, _constant_fn("atm")),
)

Kilo = _pred("Kilo",
    (1, _constant_fn("kilo")),
)

Mega = _pred("Mega",
    (1, _constant_fn("mega")),
)

Giga = _pred("Giga",
    (1, _constant_fn("giga")),
)
