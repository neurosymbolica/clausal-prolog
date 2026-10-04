"""clausal.modules.py.scipy_constants — physical constants from scipy.constants.

Named constants are plain ``Quantity`` values (the SI prefixes and ``pi``
plain floats), importable directly::

    -import_from(scipy_constants, [scipy_speed_of_light, scipy_planck_constant,
                                   scipy_reduced_planck_constant,
                                   scipy_gravitational_constant,
                                   scipy_avogadro_constant,
                                   scipy_boltzmann_constant,
                                   scipy_elementary_charge, scipy_electron_mass,
                                   scipy_proton_mass, scipy_electron_volt,
                                   scipy_standard_atmosphere, scipy_pi,
                                   scipy_kilo, scipy_mega, scipy_giga])

Use them in expressions like the constants from ``py.units``::

    C is scipy_speed_of_light
    E is ++(scipy_electron_mass * scipy_speed_of_light ** 2)
    has_units(scipy_boltzmann_constant, joule / kelvin)

The names are lower_snake_case with a ``scipy_`` prefix (renamed from
TitleCase ``SpeedOfLight``, ... with no aliases; see docs/RENAMES.md).  The
prefix keeps them apart from ``py.units``' exact ``speed_of_light``,
``kilo``, ... and the arithmetic ``pi``: these are SciPy's float values, and
a file may import both.

Numeric values come from the installed scipy CODATA release.

CODATA database access (plain floats / strings):
    value(NAME, RESULT)                     — value (float) by CODATA name
    unit(NAME, RESULT)                      — SI unit, a STRING ("m s^-1")
    precision(NAME, RESULT)                 — relative uncertainty
    lookup(NAME, VALUE, UNIT, UNCERTAINTY)  — all three in one call
    find(SUBSTRING, NAMES)                  — search names by substring
    all_names(NAMES)                         — all CODATA constant names

A constant NAME is an atom ('speed of light in vacuum'): it is the key
value/2, lookup/4 and the rest take, and find/2 and all_names/1 answer
atoms.  A unit is free-form text and comes back as a string (ruled
2026-10-04).  A NAME or SUBSTRING argument may be an atom or a string.
"""

from __future__ import annotations

import threading as _threading
from typing import Callable

from clausal.logic.variables import deref, unify
from clausal.modules.py._helpers import _text_arg
from clausal.logic.trampoline import DONE
from clausal.modules.py import ModulePredicate, text_result


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


def _lookup_fn(call: Callable, text: bool = False) -> Callable:
    """*text*: the result is free-form text (a unit string), answered as a
    string ``('$chars', s)``; otherwise it is unified as it comes."""
    def dispatch(this_generator, _proceed, _fail, _catcher, *args):
        trail = args[-1]
        result_var = args[-2]
        inputs = [_text_arg(x) for x in args[:-2]]
        try:
            out = call(*inputs)
        except Exception:
            yield (_fail, DONE)
            return
        if text:
            out = text_result(out)
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

value = _pred("value",
    (2, _lookup_fn(lambda name: _sc().value(name))),
)

unit = _pred("unit",
    (2, _lookup_fn(lambda name: _sc().unit(name), text=True)),
)

precision = _pred("precision",
    (2, _lookup_fn(lambda name: _sc().precision(name))),
)


def _lookup_dispatch(this_generator, _proceed, _fail, _catcher, name, value_var, unit_var, uncertainty_var, trail):
    name = _text_arg(name)
    try:
        val, unit_str, uncertainty = _sc().physical_constants[name]
    except KeyError:
        yield (_fail, DONE)
        return
    if (bool(unify(value_var, val, trail))
            and bool(unify(unit_var, text_result(unit_str), trail))
            and bool(unify(uncertainty_var, uncertainty, trail))):
        yield (_proceed, None)
    yield (_fail, DONE)


class _LookupPredicate:
    def _get_dispatch(self): return _lookup_dispatch
    def __repr__(self): return "scipy.constants.lookup/4"

lookup = _LookupPredicate()


def _find_dispatch(this_generator, _proceed, _fail, _catcher, substring, names_var, trail):
    try:
        names = _sc().find(_text_arg(substring), disp=False)
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
    def __repr__(self): return "scipy.constants.find/2"

class _AllNamesPredicate:
    def _get_dispatch(self): return _find_all_dispatch
    def __repr__(self): return "scipy.constants.all_names/1"

find = _FindPredicate()
all_names = _AllNamesPredicate()


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

    mod.scipy_speed_of_light          = q("c",    u.metre / u.second)
    mod.scipy_planck_constant         = q("h",    u.joule * u.second)
    mod.scipy_reduced_planck_constant = q("hbar", u.joule * u.second)
    mod.scipy_gravitational_constant  = q("G",    u.metre**3 / u.kilogram / u.second**2)
    mod.scipy_avogadro_constant       = q("N_A",  u.mole**-1)
    mod.scipy_boltzmann_constant      = q("k",    u.joule / u.kelvin)
    mod.scipy_elementary_charge       = q("e",    u.coulomb)
    mod.scipy_electron_mass           = q("m_e",  u.kilogram)
    mod.scipy_proton_mass             = q("m_p",  u.kilogram)
    mod.scipy_electron_volt           = q("eV",   u.joule)
    mod.scipy_standard_atmosphere     = q("atm",  u.pascal)

    mod.scipy_pi                      = float(sc.pi)

    mod.scipy_kilo                    = float(sc.kilo)
    mod.scipy_mega                    = float(sc.mega)
    mod.scipy_giga                    = float(sc.giga)


_init_quantities()
