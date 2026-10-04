"""clausal.modules.units — Physical units and dimensional analysis.

Provides SI unit predicates, SI prefix constants, and utility predicates.

All values are stored internally in SI base units (m, kg, s, A, K, mol, cd).

Two distinct styles are provided:

**SI unit predicates** — used with the ``n(Unit)`` sugar in ``.clausal`` files::

    eval_(5(metre), D)          # Quantity(5,   {metre: 1})
    eval_(9.8(newton), F)       # Quantity(9.8, {kg:1, m:1, s:-2})
    eval_(10(m/s), V)           # Quantity(10,  {metre:1, second:-1})

The argument to the parentheses *must* be an SI unit predicate (or a compound
expression of them).  SI prefix names are plain numbers — they are **not**
predicates and cannot appear inside the ``n(Unit)`` parentheses.

Unit names are lowercase identifiers — ``metre``, ``newton``, ``kilometre`` —
like the currency names and the symbol forms (``m``, ``s``); the physical
constants are snake_case (``speed_of_light``).  The TitleCase spellings
(``Metre``, ``Newton``, ``SpeedOfLight``) and the American ``kilometer``
family are deprecated aliases; see the end of this module.

**SI prefix constants** — plain Python numbers, multiply against unit vectors::

    5 * kilo * newton(1)        # 5 kN  →  Quantity(5000, {kg:1, m:1, s:-2})
    100 * nano * second(1)      # 100 ns →  Quantity(1e-7, {second:1})
    1 * mega * hertz(1)         # 1 MHz  →  Quantity(1e6, {second:-1})

Imperial and non-SI unit vectors live in ``imperial``::

    -import_from(py.imperial, [inch, foot, pound_mass, mph])

Usage in .clausal files::

    -import_from(py.units, [metre, newton, watt, kilo, strip_units, quantity_number])

    eval_(5(metre), D)                   # SI sugar
    eval_(9.8(newton), F)                # SI sugar
    BIG is ++(5 * kilo * newton(1))      # prefix via ++
    strip_units(D, V)                     # extract numeric value
    quantity_number(T, Q)  # transfer term <-> object; writing T in source needs -private([quantity(A, B), unit(A, B), dimensions(A), metre(A), dimensionless, decimal(A, B)])
"""

from __future__ import annotations

from decimal import Decimal
from typing import Callable

from clausal.terms import (  # noqa: F401
    Quantity, UnitsMismatch, _dims_str, _colliding_dim_names)
from clausal.lint_warnings import ClausalDeprecatedSpellingWarning
from clausal.logic.variables import deref, is_var, unify, get_attr
from clausal.logic.trampoline import DONE
from clausal.logic.exceptions import LogicException, instantiation_error, type_error
from clausal.modules.py import ModulePredicate, simple_to_trampoline


# ── Trampoline helper ────────────────────────────────────────────────────────
# Units simple-mode functions take (*args, trail) — no k parameter — so we
# need a variant of simple_to_trampoline that doesn't append None.


def _simple_to_trampoline(simple_fn: Callable) -> Callable:
    """Wrap a simple-mode generator fn(*args, trail) → trampoline."""
    def trampoline_fn(this_generator, _proceed, _fail, _catcher, *args):
        for _ in simple_fn(*args):
            yield (_proceed, None)
        yield (_fail, DONE)
    return trampoline_fn


# ── Predicate adapter (supports multi-arity + unit algebra) ──────────────────


def _dims_combine(dims1: dict, dims2: dict, sign: int = 1) -> dict:
    result = dict(dims1)
    for k, v in dims2.items():
        result[k] = result.get(k, 0) + sign * v
    return {k: v for k, v in result.items() if v != 0}


class _UnitsPredicate(ModulePredicate):
    """Adapter providing ``_get_dispatch()`` for a units predicate.

    Extends ModulePredicate with dimensional algebra: callable as a Python
    expression when ``_dims`` is set, e.g. ``kilogram(5)`` returns
    ``Quantity(5, {'kg': 1})`` directly, for use in Python arithmetic
    expressions via the ``++`` escape in .clausal files::

        E is ++(kilogram(1) * speed_of_light ** 2)
    """

    __slots__ = ("_dims",)

    def __init__(self, name: str) -> None:
        super().__init__(name)
        self._dims: dict | None = None

    def __call__(self, value) -> "Quantity":
        """Return ``Quantity(value, dims)`` directly.

        For use in Python-level arithmetic expressions, not as a Clausal goal.
        """
        if self._dims is None:
            raise TypeError(f"{self._name} does not support direct construction")
        return Quantity(value, self._dims)

    def __mul__(self, other: "_UnitsPredicate") -> "_UnitsPredicate":
        if not isinstance(other, _UnitsPredicate):
            return NotImplemented
        result = _UnitsPredicate(f"({self._name}*{other._name})")
        result._dims = _dims_combine(self._dims or {}, other._dims or {})
        return result

    def __truediv__(self, other: "_UnitsPredicate") -> "_UnitsPredicate":
        if not isinstance(other, _UnitsPredicate):
            return NotImplemented
        result = _UnitsPredicate(f"({self._name}/{other._name})")
        result._dims = _dims_combine(self._dims or {}, other._dims or {}, sign=-1)
        return result

    def __pow__(self, exp: int) -> "_UnitsPredicate":
        # Integer exponents only: a fractional exponent would build fractional
        # dimensions that Quantity.__pow__ itself refuses, so nothing else can
        # produce or consume them consistently (F057).
        if not isinstance(exp, int) or isinstance(exp, bool):
            return NotImplemented
        result = _UnitsPredicate(f"({self._name}**{exp})")
        result._dims = {k: v * exp for k, v in (self._dims or {}).items() if v * exp != 0}
        return result

    def __repr__(self) -> str:
        arities = sorted(self._dispatch_fns)
        return f"units.{self._name}/{arities}"


# ── Unit constructor factories ───────────────────────────────────────────────


def _register(name: str) -> None:
    """Record a non-currency unit in the atom-keyed registry.

    Imported locally so this module keeps its one-way dependency: the registry
    is data-only and must never import back into `units`, which would build 84
    Quantity constants and turn the CLP units side channel on for the process.
    """
    from clausal.modules import _unit_registry          # noqa: PLC0415
    _unit_registry.register(name, _unit_registry.UnitInfo(name=name))


def _make_unit_pred_base(name: str) -> _UnitsPredicate:
    """Create a base SI unit predicate that uses itself as the dimension key.

    We construct the pred object first so it can appear as its own key in the
    ``dims`` dict — e.g. ``{metre: 1}`` — without a circular-definition problem.
    """
    pred = _UnitsPredicate(name)
    # Keyed by the ATOM, not by `pred`. A unit was never a predicate: it is a
    # named entry in the registry and the atom is its name. This is also what
    # makes _dims marshal and makes sorted() work on it.
    pred._dims = {name: 1}
    _register(name)
    return pred


def _make_unit_pred(name: str, dims: dict) -> _UnitsPredicate:
    """Build a unit predicate callable from Python.

    ``Unit(value)`` returns ``Quantity(value, dims)`` directly, for use in
    Python arithmetic expressions via the ``++`` escape::

        D is ++(metre(5))          # explicit form
        eval_(5(metre), D)         # n(Unit) sugar, equivalent
    """
    from clausal.terms import atom_keyed_dims           # noqa: PLC0415
    # Callers still pass {kilogram: 1, metre: 1, second: -2} -- predicate
    # objects, because that is how the definitions read.
    frozen_dims = atom_keyed_dims(dims)
    pred = _UnitsPredicate(name)
    pred._dims = frozen_dims
    _register(name)
    return pred



# ═════════════════════════════════════════════════════════════════════════════
# SI base unit predicates
# ═════════════════════════════════════════════════════════════════════════════
# Each base unit uses itself as the dimension key: metre gives {metre: 1}.
# This avoids stringly-typed dimension dicts.

# Length
metre        = _make_unit_pred_base("metre")
# Mass
kilogram     = _make_unit_pred_base("kilogram")
# Time
second       = _make_unit_pred_base("second")
# Electric current
ampere       = _make_unit_pred_base("ampere")
# Thermodynamic temperature (ratio scale only — no Celsius/Fahrenheit)
kelvin       = _make_unit_pred_base("kelvin")
# Amount of substance
mole         = _make_unit_pred_base("mole")
# Luminous intensity
candela      = _make_unit_pred_base("candela")
# dimensionless (empty dims) — wraps a plain number as Quantity({})
dimensionless = _make_unit_pred("dimensionless", {})
# Digital information (IEC 80000-13)
bit          = _make_unit_pred_base("bit")

# ═════════════════════════════════════════════════════════════════════════════
# SI prefix constants
# ═════════════════════════════════════════════════════════════════════════════
# Plain numbers — multiply against unit vectors in ++ expressions:
#
#     ++(5 * kilo * newton(1))       # 5 kN
#     ++(100 * nano * second(1))     # 100 ns
#     ++(2.4 * giga * hertz(1))      # 2.4 GHz
#
# These are NOT predicates and cannot appear inside n(Unit) parentheses.
# The standard SI symbols for ×10^3…×10^24 are uppercase letters (k is the
# exception), which are logic variables in Clausal — use the full names.
# Single-letter abbreviations are provided below for contexts where they are
# unambiguous; import them explicitly.

yotta = 10**24
zetta = 10**21
exa   = 10**18
peta  = 10**15
tera  = 10**12
giga  = 10**9
mega  = 10**6
kilo  = 1_000
hecto = 100
deca  = 10
deci  = 1e-1
centi = 1e-2
milli = 1e-3
micro = 1e-6
nano  = 1e-9
pico  = 1e-12
femto = 1e-15
atto  = 1e-18
zepto = 1e-21
yocto = 1e-24

# ── IEC binary prefix constants (powers of 1024) ──────────────────────────────
# Plain numbers — multiply against unit vectors in ++ expressions:
#
#     ++(4 * gibi * byte(1))        # 4 GiB  →  Quantity(4_294_967_296 * 8, {bit: 1})
#     ++(100 * mebi * byte(1))      # 100 MiB
#
# These are NOT predicates and cannot appear inside n(Unit) parentheses.

kibi = 2**10    # 1_024
mebi = 2**20    # 1_048_576
gibi = 2**30    # 1_073_741_824
tebi = 2**40
pebi = 2**50
exbi = 2**60

# ═════════════════════════════════════════════════════════════════════════════
# Scaled SI unit constants  (plain Quantity values in SI base units)
# ═════════════════════════════════════════════════════════════════════════════
# These are Quantity constants, not predicates.  Multiply by a scalar:
#     ++(5 * kilometre)    → Quantity(5000, {metre: 1})
#     ++(200 * gram)       → Quantity(0.2,  {kilogram: 1})
# Or use unit annotation sugar:  5(kilometre), 200(gram)

# ── Scaled length (store as metres) ──────────────────────────────────────────

kilometre    = Quantity(1_000,   {metre: 1})
centimetre   = Quantity(Decimal("1e-2"),    {metre: 1})
millimetre   = Quantity(Decimal("1e-3"),    {metre: 1})
micrometre   = Quantity(Decimal("1e-6"),    {metre: 1})
nanometre    = Quantity(Decimal("1e-9"),    {metre: 1})

# ── Scaled mass (store as kilograms) ─────────────────────────────────────────

gram         = Quantity(Decimal("1e-3"),    {kilogram: 1})
milligram    = Quantity(Decimal("1e-6"),    {kilogram: 1})
microgram    = Quantity(Decimal("1e-9"),    {kilogram: 1})
tonne        = Quantity(1_000,   {kilogram: 1})

# ── Scaled time (store as seconds) ───────────────────────────────────────────

millisecond  = Quantity(Decimal("1e-3"),    {second: 1})
microsecond  = Quantity(Decimal("1e-6"),    {second: 1})
nanosecond   = Quantity(Decimal("1e-9"),    {second: 1})
minute       = Quantity(60,      {second: 1})
hour         = Quantity(3_600,   {second: 1})
day          = Quantity(86_400,  {second: 1})
week         = Quantity(604_800, {second: 1})
julian_year  = Quantity(31_557_600, {second: 1})

# ── Information (stored as bits) ──────────────────────────────────────────────
# bit is the IEC 80000-13 base unit; all values are normalised to bits.

byte         = Quantity(8,       {bit: 1})

# Decimal (SI-prefixed) multiples
kilobyte     = Quantity(8_000,           {bit: 1})
megabyte     = Quantity(8_000_000,       {bit: 1})
gigabyte     = Quantity(8_000_000_000,   {bit: 1})
terabyte     = Quantity(8_000_000_000_000, {bit: 1})

kilobit      = Quantity(1_000,           {bit: 1})
megabit      = Quantity(1_000_000,       {bit: 1})
gigabit      = Quantity(1_000_000_000,   {bit: 1})

# Binary (IEC-prefixed) multiples
kibibyte     = Quantity(8 * 2**10,  {bit: 1})
mebibyte     = Quantity(8 * 2**20,  {bit: 1})
gibibyte     = Quantity(8 * 2**30,  {bit: 1})
tebibyte     = Quantity(8 * 2**40,  {bit: 1})

kibibit      = Quantity(2**10,  {bit: 1})
mebibit      = Quantity(2**20,  {bit: 1})
gibibit      = Quantity(2**30,  {bit: 1})

# ═════════════════════════════════════════════════════════════════════════════
# Ratio units — dimensionless, scaled
# ═════════════════════════════════════════════════════════════════════════════
# A ratio is a pure number written at a scale: 300 basis points IS the ratio
# 0.03, and 5.25 percent IS 0.0525. Declaring the scale where the ENGINE can
# read it is what lets a rulebase stop carrying it in a parameter's NAME:
#
#     -constant_number_units(min_leverage, 300, basis_point)
#
# stores 0.03 while `constant_number_units/3` still answers `300,
# basis_point`, so the statutory "300 basis points" stays recoverable. Same
# shape as a minor currency unit, against the dimensionless base rather than
# a currency, so it needs no special case in the directive, in the annotation
# sugar or in arithmetic.
#
# Being dimensionless, `300 (basis_point)` and `3 (percent)` are the same
# quantity and compare equal -- which is the point, and also why
# `compatible_units/2` refuses a BARE number against a ratio unit: once a
# ratio is dimensionless, a bare 0.03 would otherwise satisfy every ratio
# claim there is.

# The table itself lives in `clausal.modules._ratio_data`, a data-only module,
# because the scale-in-a-name lint reads it on every transform and must not
# import THIS module to do so -- importing it builds 84 Quantity constants,
# which turns the CLP units side channel on for the whole process. See that
# module's docstring. Re-exported here so `units.RATIO_UNITS` keeps working.
from clausal.modules._ratio_data import RATIO_UNITS       # noqa: E402


def _make_ratio_unit(name: str) -> Quantity:
    """A dimensionless scaled unit of ``10**-RATIO_UNITS[name]``.

    The factor is a ``Decimal`` built with ``scaleb``, never a float
    literal, and that is the whole safety argument. A scaled unit returns
    early from ``Quantity.__init__`` and never reaches the currency
    coercion, so exactness here comes from ``_num_pair`` reading a float
    magnitude beside a ``Decimal`` factor as ``Decimal(str(f))``. Give the
    factor a float and that stops: ``gram = Quantity(1e-3, {kilogram: 1})``
    was why ``7 gram`` was not exactly 0.007 -- every SI-fraction factor is an
    exact Decimal since 2026-09-18 (Q6, option C). A ratio multiplies against money
    and against the thresholds that decide a case, so it is the last place
    to reintroduce binary floating point.
    """
    return Quantity(Decimal(1).scaleb(-RATIO_UNITS[name]), {})


percent     = _make_ratio_unit("percent")
basis_point = _make_ratio_unit("basis_point")

# ═════════════════════════════════════════════════════════════════════════════
# Named derived SI unit predicates
# ═════════════════════════════════════════════════════════════════════════════

# Mechanics
newton   = _make_unit_pred("newton",   {kilogram: 1, metre: 1, second: -2})          # N  = kg·m/s²
joule    = _make_unit_pred("joule",    {kilogram: 1, metre: 2, second: -2})          # J  = N·m
watt     = _make_unit_pred("watt",     {kilogram: 1, metre: 2, second: -3})          # W  = J/s
pascal   = _make_unit_pred("pascal",   {kilogram: 1, metre: -1, second: -2})         # Pa = N/m²
hertz    = _make_unit_pred("hertz",    {second: -1})                                 # Hz = 1/s
gray     = _make_unit_pred("gray",     {metre: 2, second: -2})                       # Gy = J/kg
sievert  = _make_unit_pred("sievert",  {metre: 2, second: -2})                       # Sv = J/kg

# Electromagnetism
volt     = _make_unit_pred("volt",     {kilogram: 1, metre: 2, second: -3, ampere: -1})  # V  = W/A
coulomb  = _make_unit_pred("coulomb",  {ampere: 1, second: 1})                           # C  = A·s
farad    = _make_unit_pred("farad",    {kilogram: -1, metre: -2, second: 4, ampere: 2})  # F  = C/V
ohm      = _make_unit_pred("ohm",      {kilogram: 1, metre: 2, second: -3, ampere: -2}) # Ω  = V/A
siemens  = _make_unit_pred("siemens",  {kilogram: -1, metre: -2, second: 3, ampere: 2}) # S  = 1/Ω
weber    = _make_unit_pred("weber",    {kilogram: 1, metre: 2, second: -2, ampere: -1}) # Wb = V·s
tesla    = _make_unit_pred("tesla",    {kilogram: 1, second: -2, ampere: -1})            # T  = Wb/m²
henry    = _make_unit_pred("henry",    {kilogram: 1, metre: 2, second: -2, ampere: -2}) # H  = Wb/A

# Photometry
lumen    = _make_unit_pred("lumen",    {candela: 1})                                # lm = cd·sr (sr dimensionless)
lux      = _make_unit_pred("lux",      {candela: 1, metre: -2})                     # lx = lm/m²

# Chemistry / thermodynamics
katal    = _make_unit_pred("katal",    {mole: 1, second: -1})                       # kat = mol/s

# Scaled SI pressure (stored as pascal)
bar        = Quantity(Decimal("1e5"),              {kilogram: 1, metre: -1, second: -2})
millibar   = Quantity(100,             {kilogram: 1, metre: -1, second: -2})
atmosphere = Quantity(101_325,         {kilogram: 1, metre: -1, second: -2})

# Scaled SI energy (stored as joule)
electronvolt = Quantity(Decimal("1.602176634e-19"), {kilogram: 1, metre: 2, second: -2})

# Scaled SI power (stored as watt)
kilowatt     = Quantity(1_000,         {kilogram: 1, metre: 2, second: -3})

# ═════════════════════════════════════════════════════════════════════════════
# SI standard abbreviation aliases
# ═════════════════════════════════════════════════════════════════════════════
# Lowercase aliases for the SI base units whose standard symbols are safe to
# use as Clausal identifiers (i.e. not all-uppercase, which would be parsed
# as logic variables).
#
# Safe to alias:  m, kg, s, mol, cd
# Not aliased:    A (ampere) and K (kelvin) — single uppercase letters are
#                 logic variables in Clausal; use the full names instead.

m   = metre
kg  = kilogram
s   = second
mol = mole
cd  = candela

# ── Scaled SI unit abbreviations ─────────────────────────────────────────────
# Quantity constants — multiply by a scalar: ++(5 * km)

km  = kilometre
cm  = centimetre
mm  = millimetre
um  = micrometre    # μm — μ is not a valid identifier
nm  = nanometre

mg  = milligram
ug  = microgram     # μg

ms  = millisecond
us  = microsecond   # μs
ns  = nanosecond
min = minute        # shadows Python builtin; import explicitly if needed
hr  = hour

# ── SI prefix abbreviations ───────────────────────────────────────────────────
# Plain numbers — same as the full names above.
# Uppercase SI symbols (M, G, T, P, E, Z, Y) are logic variables in Clausal
# and cannot be used.  The following lowercase symbols are safe:

k  = kilo    # 1e3   (standard SI symbol)
h  = hecto   # 1e2
da = deca    # 1e1   (two-char: safe)
d  = deci    # 1e-1
c  = centi   # 1e-2
# milli's SI symbol 'm' clashes with metre — use 'milli' or 'ms'/'mg'/'mm'
n  = nano    # 1e-9
p  = pico    # 1e-12
f  = femto   # 1e-15
a  = atto    # 1e-18


# ═════════════════════════════════════════════════════════════════════════════
# Unit vectors: Quantity(1, ...) values for building expressions
# ═════════════════════════════════════════════════════════════════════════════

# Named derived SI units aliased to their Quantity unit vector
si_frequency             = hertz(1)
si_force                 = newton(1)
si_energy                = joule(1)
si_power                 = watt(1)
si_pressure              = pascal(1)
si_voltage               = volt(1)
si_charge                = coulomb(1)
si_capacitance           = farad(1)
si_resistance            = ohm(1)
si_conductance           = siemens(1)
si_magnetic_flux         = weber(1)
si_magnetic_flux_density = tesla(1)
si_inductance            = henry(1)
si_luminous_flux         = lumen(1)
si_illuminance           = lux(1)

# Unnamed compound SI dimensions
si_area                  = metre(1)**2
si_volume                = metre(1)**3
si_velocity              = metre(1) / second(1)
si_acceleration          = metre(1) / second(1)**2


# ═════════════════════════════════════════════════════════════════════════════
# Physical constants  (2019 SI exact definitions where available)
# ═════════════════════════════════════════════════════════════════════════════
#
# These are plain Quantity values, not predicates.  Use them in Python
# expressions via the ++ escape::
#
#     E is ++(kilogram(1) * speed_of_light ** 2)

speed_of_light          = 299_792_458       * si_velocity
planck_constant        = 6.62607015e-34    * si_energy * second(1)
reduced_planck         = 1.054571817e-34   * si_energy * second(1)
boltzmann_constant     = 1.380649e-23      * si_energy / kelvin(1)
avogadro_constant      = 6.02214076e23     / mole(1)
elementary_charge      = 1.602176634e-19   * si_charge
standard_gravity       = 9.80665           * si_acceleration
gravitational_constant = 6.67430e-11       * metre(1)**3 / kilogram(1) / second(1)**2
atomic_mass_unit       = 1.66053906660e-27 * kilogram(1)
electron_mass          = 9.1093837015e-31  * kilogram(1)
proton_mass            = 1.67262192369e-27 * kilogram(1)
vacuum_permeability    = 1.25663706212e-6  * kilogram(1) * metre(1) / second(1)**2 / ampere(1)**2
vacuum_permittivity    = 8.8541878128e-12  * second(1)**4 / kilogram(1) / metre(1)**3 * ampere(1)**2
stefan_boltzmann       = 5.670374419e-8    * si_power / metre(1)**2 / kelvin(1)**4


# ═════════════════════════════════════════════════════════════════════════════
# Utility predicates
# ═════════════════════════════════════════════════════════════════════════════


def _dimension_of_impl(d, dims_out, trail):
    """dimension_of(D, Dims): unify Dims with the dimension dict of D.

    Works for ground Quantity values and for uninstantiated AttVars that
    carry a dimensional constraint.

    Ruling 2026-10-02: a plain unbound variable (no dimensional constraint)
    is ``instantiation_error`` and a bound non-quantity is
    ``type_error(quantity, D)`` -- both used to fail silently.  RULED
    2026-10-02: a bare NUMBER is a dimensionless quantity, so its dimension
    is the empty dict -- the dims ``dimensionless`` itself carries.
    """
    from clausal.terms import DictTerm
    from clausal.logic.units_constraint import UNITS_KEY
    dv = deref(d)
    if isinstance(dv, Quantity):
        dims_term = DictTerm(dv.dims)
        if unify(deref(dims_out), dims_term, trail):
            yield None
    elif is_var(dv):
        state = get_attr(dv, UNITS_KEY)
        if state is None:
            raise LogicException(instantiation_error("dimension_of/2"))
        dims_term = DictTerm(state.dims)
        if unify(deref(dims_out), dims_term, trail):
            yield None
    elif _is_bare_number(dv):
        if unify(deref(dims_out), DictTerm({}), trail):
            yield None
    else:
        raise LogicException(type_error("quantity", dv, "dimension_of/2"))


def _is_bare_number(v) -> bool:
    """A plain number of the engine's tower (never a bool: true/false are
    atoms, D35) -- what dimension_of/2 and strip_units/2 read as a
    dimensionless quantity (RULED 2026-10-02)."""
    from clausal.modules.py import NUMBER_TYPES
    return isinstance(v, NUMBER_TYPES) and type(v) is not bool


def _strip_dimensions_impl(d, value_out, trail):
    """strip_units(Quantity, Value): unify Value with the numeric component.

    Unbound -> instantiation_error; a bare number is a dimensionless
    quantity and strips to itself (RULED 2026-10-02); anything else ->
    ``type_error(quantity, D)`` (both used to fail silently)."""
    dv = deref(d)
    if is_var(dv):
        raise LogicException(instantiation_error("strip_units/2"))
    if _is_bare_number(dv):
        if unify(deref(value_out), dv, trail):
            yield None
        return
    if not isinstance(dv, Quantity):
        raise LogicException(type_error("quantity", dv, "strip_units/2"))
    if unify(deref(value_out), dv.value, trail):
        yield None


def _make_dimensioned_impl(value, dims_in, d_out, trail):
    """make_quantity(Value, Dims, D): construct Quantity from value + dims dict."""
    from clausal.terms import DictTerm
    v = deref(value)
    di = deref(dims_in)
    if is_var(v) or is_var(di):          # ruling 2026-10-02: was a silent no
        raise LogicException(instantiation_error("make_quantity/3"))
    if isinstance(di, DictTerm):
        raw_dims = dict(di.data)
    elif isinstance(di, dict):
        raw_dims = di
    else:
        raise LogicException(type_error("dict", di, "make_quantity/3: argument 2"))
    target = Quantity(v, raw_dims)
    if unify(deref(d_out), target, trail):
        yield None


def _quantity_number_impl(term, number, trail):
    """quantity_number(QuantityTerm, Number): the EXPLICIT conversion between
    a quantity's transfer term and the object (spec 2026-09-16, §4).

    In Clausal ``Number`` is the OBJECT: a quantity stands in for a number
    and must reach ``#=/2`` as itself. A Prolog with no units binds the
    magnitude scaled to the standard unit instead; that half lives in the
    exporter's per-dialect prelude, not here.

    Modes: (-T, +Q) emits, ratio 1; (+T, -Q) reads, ratio multiplied
    through; (+T, +Q) compares by value; (-, -) instantiation_error; a
    bound but malformed T is a type_error -- RAISED, because a malformed
    term that failed quietly would be the "goal just stops holding" shape.

    A bound non-Quantity ``Number`` FAILS rather than raising, by ruling
    (spec §4): the relation simply does not hold, and the emit direction
    has nothing to convert.
    """
    from clausal.logic.exceptions import (  # noqa: PLC0415
        LogicException, instantiation_error, type_error)
    from clausal.logic.python_terms import from_transfer, to_transfer  # noqa: PLC0415
    from clausal.logic.solve import _deref_walk  # noqa: PLC0415

    t, n = deref(term), deref(number)
    if is_var(t):
        if is_var(n):
            raise LogicException(instantiation_error("quantity_number/2"))
        if not isinstance(n, Quantity):
            return                              # the relation does not hold
        if unify(t, to_transfer(n), trail):
            yield None
        return
    if isinstance(t, Quantity):
        built = t                               # the object, taken as itself
    else:
        walked = _deref_walk(t)                 # bound vars inside the term
        if _holds_var(walked):
            raise LogicException(instantiation_error("quantity_number/2"))
        built = from_transfer(walked)
        if not isinstance(built, Quantity):
            raise LogicException(type_error("quantity", walked, "quantity_number/2"))
    if unify(n, built, trail):
        yield None


def _holds_var(term) -> bool:
    """True if an UNBOUND variable sits inside a walked term's tuple/list/dict
    structure. Engine term instances (DictTerm, ...) are not
    walked: inside a quantity term they are malformed anyway, and the
    caller's type_error is the loud answer there."""
    if is_var(term):
        return True
    if isinstance(term, (tuple, list)):
        return any(_holds_var(e) for e in term)
    if isinstance(term, dict):
        return any(_holds_var(k) or _holds_var(v) for k, v in term.items())
    return False


def _unit_dims(unit):
    """The dims a UNIT expression denotes: a base or derived predicate, a
    scaled unit (``kilometre``, ``usd_cent`` -- both ``Quantity``), or a
    compound. Returns None when *unit* is not a unit at all."""
    dims = getattr(unit, "_dims", None)
    if dims is None:
        dims = getattr(unit, "dims", None)
    return None if dims is None else dict(dims)


def compatible_units_check(value, unit) -> bool:
    """Assert that *value* is a quantity whose dimension is *unit*'s.

    Raises ``UnitsMismatch`` when it is not, and that is the whole point:
    ``has_units/2`` answers the same relation by SUCCEEDING or FAILING, and a
    goal failure is swallowed -- a guard that fails just makes the rule not
    fire, so a caller who passed the wrong thing gets "no" rather than "you
    passed the wrong thing".

    **Scale is ignored**, because by here it has already been applied: a
    scaled unit normalises at construction, so ``155000 usd_cent`` IS
    ``Decimal('1550.00') usd`` and ``5 kilometre`` is 5000 metres. What is
    left to check is the dimension, and `usd_cent` and `usd` name the same
    one. That is also what makes ratios work: ``basis_point`` and
    ``percent`` are both dimensionless with a scale factor, so both normalise
    and ``300 basis_point`` compares equal to ``3 percent``. (Written here on
    2026-09-11 before either unit existed; they landed 2026-09-12 and this
    paragraph is now describing behaviour rather than anticipating it.)

    **A bare number is never compatible -- not even with ``dimensionless``**
    (operator, 2026-09-11). The engine lets a bare number add to a
    dimensionless quantity, so this is deliberately stricter than the
    arithmetic: the predicate asserts that a value IS a quantity carrying a
    unit, and a bare number satisfies no unit claim. It is the only version
    that closes the hole for RATIOS -- once bps and percent are
    dimensionless, a bare ``0.03`` would otherwise pass as "dimensionless"
    and the check would wave through exactly the case it exists to catch.
    """
    want = _unit_dims(unit)
    if want is None:
        raise TypeError(
            f"compatible_units: {unit!r} is not a unit — the second argument "
            f"names the unit the first is asserted to carry.")
    if not isinstance(value, Quantity):
        named = _dims_str(want) if want else "dimensionless"
        raise UnitsMismatch(
            f"compatible_units: {value!r} carries no unit, so it cannot be "
            f"{named}. A bare number is never compatible, not even with "
            f"dimensionless — write the quantity (`{value!r}({named})`), or "
            f"declare it with -constant_number_currency.")
    got = dict(value.dims)
    if got != want:
        # Reuse the collision logic rather than write a second copy: two
        # same-NAMED dimensions would otherwise render "expected dollar, got
        # dollar" here, which is the defect `_require_same_dims` was fixed for
        # this morning and which this path reproduced immediately. A new
        # message path is a new chance to make the same mistake.
        collide = _colliding_dim_names(want, got)
        expected = _dims_str(want, qualify=collide) if want else "1"
        actual = _dims_str(got, qualify=collide) if got else "1"
        raise UnitsMismatch(
            f"compatible_units: expected {expected}, got {actual}")
    return True


def _compatible_units_impl(value, unit, trail):
    """compatible_units(Quantity, Unit) — succeeds, or raises UnitsMismatch."""
    v, u = deref(value), deref(unit)
    if is_var(v) or is_var(u):
        raise UnitsMismatch(
            "compatible_units: both arguments must be bound — an unbound "
            "argument asserts nothing, and a check that cannot fail is not "
            "a check.")
    compatible_units_check(v, u)
    yield None


dimension_of = _UnitsPredicate("dimension_of")
dimension_of._register(2, _simple_to_trampoline(_dimension_of_impl))

strip_units = _UnitsPredicate("strip_units")
strip_units._register(2, _simple_to_trampoline(_strip_dimensions_impl))

make_quantity = _UnitsPredicate("make_quantity")
make_quantity._register(3, _simple_to_trampoline(_make_dimensioned_impl))

quantity_number = _UnitsPredicate("quantity_number")
quantity_number._register(2, _simple_to_trampoline(_quantity_number_impl))

# Register the "units" attribute hook for AttVar-based dimensional variables.
import clausal.logic.units_constraint as _units_constraint  # noqa: F401

# Re-export has_units/2 so the documented `-import_from(py.units, [...,
# has_units, ...])` quick-start line resolves. It is also registered as a
# global builtin; this importable wrapper shares the same implementation (F059).
# _has_units is builtin-style — fn(d, unit_pred, trail, k) — so it needs the
# py-module simple_to_trampoline (which appends k=None), NOT the local
# _simple_to_trampoline for k-less units functions: the latter left every
# call through the imported name raising a missing-argument error.
has_units = _UnitsPredicate("has_units")
has_units._register(2, simple_to_trampoline(_units_constraint._has_units))

# The RAISING sibling of has_units/2. Same relation, opposite failure mode:
# has_units/2 fails silently, which a guard position swallows.
compatible_units = _UnitsPredicate("compatible_units")
compatible_units._register(2, _simple_to_trampoline(_compatible_units_impl))


# ═════════════════════════════════════════════════════════════════════════════
# Deprecated spellings
# ═════════════════════════════════════════════════════════════════════════════
# Unit names are lowercase identifiers (``metre``, ``newton``), like the
# currency names (``euro``) and the symbol forms (``m``, ``s``); the length
# family is spelled like ``metre`` (``kilometre``); the physical constants
# are snake_case (``speed_of_light``).  The spellings they replaced — the
# TitleCase names and the American ``kilometer`` family — still resolve,
# through this table, but warn: once per process per name from Python
# attribute access (the module ``__getattr__`` below), once per file from a
# ``-import_from(py.units, …)`` list (the seam rewrites the import to the
# current name; see ``_handle_import_from_directive`` in
# clausal/templating/term_rewriting.py).  Both will be removed in a future
# release.

_DEPRECATED_UNIT_NAMES: dict[str, str] = {
    # SI base units
    "Metre": "metre", "Kilogram": "kilogram", "Second": "second",
    "Ampere": "ampere", "Kelvin": "kelvin", "Mole": "mole",
    "Candela": "candela", "Bit": "bit", "Dimensionless": "dimensionless",
    # Named derived SI units
    "Newton": "newton", "Joule": "joule", "Watt": "watt", "Pascal": "pascal",
    "Hertz": "hertz", "Gray": "gray", "Sievert": "sievert", "Volt": "volt",
    "Coulomb": "coulomb", "Farad": "farad", "Ohm": "ohm", "Siemens": "siemens",
    "Weber": "weber", "Tesla": "tesla", "Henry": "henry", "Lumen": "lumen",
    "Lux": "lux", "Katal": "katal",
    # Scaled unit constants
    "Kilometer": "kilometre", "Centimeter": "centimetre",
    "Millimeter": "millimetre", "Micrometer": "micrometre",
    "Nanometer": "nanometre",
    "Gram": "gram", "Milligram": "milligram", "Microgram": "microgram",
    "Tonne": "tonne",
    "Millisecond": "millisecond", "Microsecond": "microsecond",
    "Nanosecond": "nanosecond", "Minute": "minute", "Hour": "hour",
    "Day": "day", "Week": "week", "JulianYear": "julian_year",
    "Byte": "byte", "Kilobyte": "kilobyte", "Megabyte": "megabyte",
    "Gigabyte": "gigabyte", "Terabyte": "terabyte",
    "Kilobit": "kilobit", "Megabit": "megabit", "Gigabit": "gigabit",
    "Kibibyte": "kibibyte", "Mebibyte": "mebibyte", "Gibibyte": "gibibyte",
    "Tebibyte": "tebibyte",
    "Kibibit": "kibibit", "Mebibit": "mebibit", "Gibibit": "gibibit",
    "Bar": "bar", "Millibar": "millibar", "Atmosphere": "atmosphere",
    "Electronvolt": "electronvolt", "Kilowatt": "kilowatt",
    # American spellings of the length family (the family follows ``metre``)
    "kilometer": "kilometre", "centimeter": "centimetre",
    "millimeter": "millimetre", "micrometer": "micrometre",
    "nanometer": "nanometre",
    # Physical constants (snake_case)
    "SpeedOfLight": "speed_of_light", "PlanckConstant": "planck_constant",
    "ReducedPlanck": "reduced_planck",
    "BoltzmannConstant": "boltzmann_constant",
    "AvogadroConstant": "avogadro_constant",
    "ElementaryCharge": "elementary_charge",
    "StandardGravity": "standard_gravity",
    "GravitationalConstant": "gravitational_constant",
    "AtomicMassUnit": "atomic_mass_unit", "ElectronMass": "electron_mass",
    "ProtonMass": "proton_mass", "VacuumPermeability": "vacuum_permeability",
    "VacuumPermittivity": "vacuum_permittivity",
    "StefanBoltzmann": "stefan_boltzmann",
    # SI dimension vectors (ruled 2026-10-04, D16-X2): snake_case
    "SI_Frequency": "si_frequency",
    "SI_Force": "si_force",
    "SI_Energy": "si_energy",
    "SI_Power": "si_power",
    "SI_Pressure": "si_pressure",
    "SI_Voltage": "si_voltage",
    "SI_Charge": "si_charge",
    "SI_Capacitance": "si_capacitance",
    "SI_Resistance": "si_resistance",
    "SI_Conductance": "si_conductance",
    "SI_MagneticFlux": "si_magnetic_flux",
    "SI_MagneticFluxDensity": "si_magnetic_flux_density",
    "SI_Inductance": "si_inductance",
    "SI_LuminousFlux": "si_luminous_flux",
    "SI_Illuminance": "si_illuminance",
    "SI_Area": "si_area",
    "SI_Volume": "si_volume",
    "SI_Velocity": "si_velocity",
    "SI_Acceleration": "si_acceleration",
}

for _old, _new in _DEPRECATED_UNIT_NAMES.items():
    assert _new in globals(), f"deprecated alias {_old} -> {_new}: no such unit"
del _old, _new

# Names already warned about through ``__getattr__`` — once per process per
# name, so a Python caller reading ``units.Metre`` in a loop is told once.
_warned_deprecated_unit_names: set[str] = set()


def _resolve_deprecated_name(name: str, module_name: str):
    """Resolve a deprecated spelling for ``module_name``'s ``__getattr__``.

    ``stacklevel=3`` names the line that READ the attribute: 1 is this
    function, 2 the module ``__getattr__`` that called it (ours, or the
    ``clausal.modules.py.units`` forwarder), 3 the reader — importlib's own
    frames are skipped by ``warnings``, so a ``from … import Metre`` is
    attributed to the import statement.
    """
    new = _DEPRECATED_UNIT_NAMES.get(name)
    if new is None:
        raise AttributeError(
            f"module {module_name!r} has no attribute {name!r}")
    if name not in _warned_deprecated_unit_names:
        _warned_deprecated_unit_names.add(name)
        import warnings  # noqa: PLC0415
        warnings.warn(
            f"units.{name} is the old spelling of units.{new}. Rename "
            f"`{name}` -> `{new}`; the old spelling still works but will be "
            f"removed in a future release",
            ClausalDeprecatedSpellingWarning,
            stacklevel=3,
        )
    return globals()[new]


def __getattr__(name: str):
    return _resolve_deprecated_name(name, __name__)
