"""clausal.modules.py.scipy_constants — physical constants from scipy.constants.

Named constants are plain ``Quantity`` values importable directly::

    -import_from(scipy_constants, [SpeedOfLight, PlanckConstant,
                                    ReducedPlanckConstant, GravitationalConstant,
                                    AvogadroConstant, BoltzmannConstant,
                                    ElementaryCharge, ElectronMass, ProtonMass,
                                    ElectronVolt, StandardAtmosphere,
                                    Kilo, Mega, Giga])

Use them in expressions exactly like the constants from ``py.units``::

    C is SpeedOfLight
    E is ++(ElectronMass * SpeedOfLight ** 2)
    has_units(BoltzmannConstant, joule / kelvin)

Numeric values come from the installed scipy CODATA release.

CODATA database access (plain floats / strings):
    Value(NAME, RESULT)                     — value (float) by CODATA name
    Unit(NAME, RESULT)                      — SI unit string
    Precision(NAME, RESULT)                 — relative uncertainty
    Lookup(NAME, VALUE, UNIT, UNCERTAINTY)  — all three in one call
    Find(SUBSTRING, NAMES)                  — search names by substring
    AllNames(NAMES)                         — all CODATA constant names
"""

from __future__ import annotations

import threading as _threading
from typing import Callable

from clausal.logic.variables import deref, unify
from clausal.logic.trampoline import DONE
from clausal.modules.py import ModulePredicate


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


def _lookup_fn(call: Callable) -> Callable:
    def dispatch(this_generator, _proceed, _fail, _catcher, *args):
        trail = args[-1]
        result_var = args[-2]
        inputs = [deref(x) for x in args[:-2]]
        try:
            out = call(*inputs)
        except Exception:
            yield (_fail, DONE)
            return
        if bool(unify(result_var, out, trail)):
            yield (_proceed, None)
        yield (_fail, DONE)
    return dispatch


def _pred(name: str, *arity_fns) -> ModulePredicate:
    p = ModulePredicate(name)
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


def _lookup_dispatch(this_generator, _proceed, _fail, _catcher, name, value_var, unit_var, uncertainty_var, trail):
    name = deref(name)
    try:
        val, unit_str, uncertainty = _sc().physical_constants[name]
    except KeyError:
        yield (_fail, DONE)
        return
    if (bool(unify(value_var, val, trail))
            and bool(unify(unit_var, unit_str, trail))
            and bool(unify(uncertainty_var, uncertainty, trail))):
        yield (_proceed, None)
    yield (_fail, DONE)


class _LookupPredicate:
    def _get_dispatch(self): return _lookup_dispatch
    def __repr__(self): return "scipy.constants.Lookup/4"

Lookup = _LookupPredicate()


def _find_dispatch(this_generator, _proceed, _fail, _catcher, substring, names_var, trail):
    try:
        names = _sc().find(deref(substring), disp=False)
    except Exception:
        yield (_fail, DONE)
        return
    if bool(unify(names_var, list(names), trail)):
        yield (_proceed, None)
    yield (_fail, DONE)


def _find_all_dispatch(this_generator, _proceed, _fail, _catcher, names_var, trail):
    try:
        names = list(_sc().physical_constants.keys())
    except Exception:
        yield (_fail, DONE)
        return
    if bool(unify(names_var, names, trail)):
        yield (_proceed, None)
    yield (_fail, DONE)


class _FindPredicate:
    def _get_dispatch(self): return _find_dispatch
    def __repr__(self): return "scipy.constants.Find/2"

class _AllNamesPredicate:
    def _get_dispatch(self): return _find_all_dispatch
    def __repr__(self): return "scipy.constants.AllNames/1"

Find = _FindPredicate()
AllNames = _AllNamesPredicate()


# ── Physical constants as Quantity values ──────────────────────────────────
#
# Initialized eagerly at first import of this module.  scipy.constants is a
# pure-Python file (just a dict lookup) so loading it is negligible.
# Unit predicate objects from py.units are used as dimension keys, matching
# the convention in py.units itself.

def _init_quantities():
    """Build and register all Quantity constants into this module's globals."""
    import sys
    from clausal.terms import Quantity
    from clausal.modules.py import units as u

    sc = _sc()
    mod = sys.modules[__name__]

    def q(attr, unit):
        return Quantity(float(getattr(sc, attr)), unit)

    mod.SpeedOfLight          = q("c",    u.metre / u.second)
    mod.PlanckConstant        = q("h",    u.joule * u.second)
    mod.ReducedPlanckConstant = q("hbar", u.joule * u.second)
    mod.GravitationalConstant = q("G",    u.metre**3 / u.kilogram / u.second**2)
    mod.AvogadroConstant      = q("N_A",  u.mole**-1)
    mod.BoltzmannConstant     = q("k",    u.joule / u.kelvin)
    mod.ElementaryCharge      = q("e",    u.coulomb)
    mod.ElectronMass          = q("m_e",  u.kilogram)
    mod.ProtonMass            = q("m_p",  u.kilogram)
    mod.ElectronVolt          = q("eV",   u.joule)
    mod.StandardAtmosphere    = q("atm",  u.pascal)

    mod.Pi = float(sc.pi)

    mod.Kilo = float(sc.kilo)
    mod.Mega = float(sc.mega)
    mod.Giga = float(sc.giga)


_init_quantities()
