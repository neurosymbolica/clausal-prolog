"""clausal.modules.units — Physical units and dimensional analysis.

Provides SI unit predicates, SI prefix constants, and utility predicates.

All values are stored internally in SI base units (m, kg, s, A, K, mol, cd).

Two distinct styles are provided:

**SI unit predicates** — used with the ``n(Unit)`` sugar in ``.clausal`` files::

    D := 5(Metre)          # Quantity(5,   {Metre: 1})
    F := 9.8(Newton)       # Quantity(9.8, {kg:1, m:1, s:-2})
    V := 10(m/s)           # Quantity(10,  {Metre:1, Second:-1})

The argument to the parentheses *must* be an SI unit predicate (or a compound
expression of them).  SI prefix names are plain numbers — they are **not**
predicates and cannot appear inside the ``n(Unit)`` parentheses.

**SI prefix constants** — plain Python numbers, multiply against unit vectors::

    5 * kilo * Newton(1)        # 5 kN  →  Quantity(5000, {kg:1, m:1, s:-2})
    100 * nano * Second(1)      # 100 ns →  Quantity(1e-7, {Second:1})
    1 * mega * Hertz(1)         # 1 MHz  →  Quantity(1e6, {Second:-1})

Imperial and non-SI unit vectors live in ``imperial``::

    -import_from(py.imperial, [inch, foot, pound_mass, mph])

Usage in .clausal files::

    -import_from(py.units, [Metre, Newton, Watt, kilo, StripUnits])

    D := 5(Metre)                        # SI sugar
    F := 9.8(Newton)                     # SI sugar
    BIG := ++(5 * kilo * Newton(1))      # prefix via ++
    StripUnits(D, V)                     # extract numeric value
"""

from __future__ import annotations

from typing import Callable

from clausal.terms import Quantity, UnitsMismatch  # noqa: F401
from clausal.logic.variables import deref, is_var, unify, get_attr
from clausal.logic.trampoline import DONE
from clausal.modules.py import ModulePredicate


# ── Trampoline helper ────────────────────────────────────────────────────────
# Units simple-mode functions take (*args, trail) — no k parameter — so we
# need a variant of simple_to_trampoline that doesn't append None.


def _simple_to_trampoline(simple_fn: Callable) -> Callable:
    """Wrap a simple-mode generator fn(*args, trail) → trampoline."""
    def trampoline_fn(this_generator, parent, *args):
        for _ in simple_fn(*args):
            yield (parent, None)
        yield (parent, DONE)
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
    expression when ``_dims`` is set, e.g. ``Kilogram(5)`` returns
    ``Quantity(5, {'kg': 1})`` directly, for use in Python arithmetic
    expressions via the ``++`` escape in .clausal files::

        E := ++(Kilogram(1) * SpeedOfLight ** 2)
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

    def __pow__(self, exp: int | float) -> "_UnitsPredicate":
        if not isinstance(exp, (int, float)):
            return NotImplemented
        result = _UnitsPredicate(f"({self._name}**{exp})")
        result._dims = {k: v * exp for k, v in (self._dims or {}).items() if v * exp != 0}
        return result

    def __repr__(self) -> str:
        arities = sorted(self._dispatch_fns)
        return f"units.{self._name}/{arities}"


# ── Unit constructor factories ───────────────────────────────────────────────


def _make_unit_pred_base(name: str) -> _UnitsPredicate:
    """Create a base SI unit predicate that uses itself as the dimension key.

    We construct the pred object first so it can appear as its own key in the
    ``dims`` dict — e.g. ``{Metre: 1}`` — without a circular-definition problem.
    """
    pred = _UnitsPredicate(name)
    frozen_dims = {pred: 1}   # pred already exists; self-referential key is fine
    pred._dims = frozen_dims
    return pred


def _make_unit_pred(name: str, dims: dict) -> _UnitsPredicate:
    """Build a unit predicate callable from Python.

    ``Unit(value)`` returns ``Quantity(value, dims)`` directly, for use in
    Python arithmetic expressions via the ``++`` escape::

        D := ++(Metre(5))          # explicit form
        D := 5(Metre)              # n(Unit) sugar, equivalent
    """
    frozen_dims = {k: v for k, v in dims.items() if v != 0}
    pred = _UnitsPredicate(name)
    pred._dims = frozen_dims
    return pred



# ═════════════════════════════════════════════════════════════════════════════
# SI base unit predicates
# ═════════════════════════════════════════════════════════════════════════════
# Each base unit uses itself as the dimension key: Metre gives {Metre: 1}.
# This avoids stringly-typed dimension dicts.

# Length
Metre        = _make_unit_pred_base("Metre")
# Mass
Kilogram     = _make_unit_pred_base("Kilogram")
# Time
Second       = _make_unit_pred_base("Second")
# Electric current
Ampere       = _make_unit_pred_base("Ampere")
# Thermodynamic temperature (ratio scale only — no Celsius/Fahrenheit)
Kelvin       = _make_unit_pred_base("Kelvin")
# Amount of substance
Mole         = _make_unit_pred_base("Mole")
# Luminous intensity
Candela      = _make_unit_pred_base("Candela")
# Dimensionless (empty dims) — wraps a plain number as Quantity({})
Dimensionless = _make_unit_pred("Dimensionless", {})
# Digital information (IEC 80000-13)
Bit          = _make_unit_pred_base("Bit")

# ═════════════════════════════════════════════════════════════════════════════
# SI prefix constants
# ═════════════════════════════════════════════════════════════════════════════
# Plain numbers — multiply against unit vectors in ++ expressions:
#
#     ++(5 * kilo * Newton(1))       # 5 kN
#     ++(100 * nano * Second(1))     # 100 ns
#     ++(2.4 * giga * Hertz(1))      # 2.4 GHz
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
#     ++(4 * gibi * Byte(1))        # 4 GiB  →  Quantity(4_294_967_296 * 8, {Bit: 1})
#     ++(100 * mebi * Byte(1))      # 100 MiB
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
#     ++(5 * Kilometer)    → Quantity(5000, {Metre: 1})
#     ++(200 * Gram)       → Quantity(0.2,  {Kilogram: 1})
# Or use unit annotation sugar:  5(Kilometer), 200(Gram)

# ── Scaled length (store as metres) ──────────────────────────────────────────

Kilometer    = Quantity(1_000,   {Metre: 1})
Centimeter   = Quantity(1e-2,    {Metre: 1})
Millimeter   = Quantity(1e-3,    {Metre: 1})
Micrometer   = Quantity(1e-6,    {Metre: 1})
Nanometer    = Quantity(1e-9,    {Metre: 1})

# ── Scaled mass (store as kilograms) ─────────────────────────────────────────

Gram         = Quantity(1e-3,    {Kilogram: 1})
Milligram    = Quantity(1e-6,    {Kilogram: 1})
Microgram    = Quantity(1e-9,    {Kilogram: 1})
Tonne        = Quantity(1_000,   {Kilogram: 1})

# ── Scaled time (store as seconds) ───────────────────────────────────────────

Millisecond  = Quantity(1e-3,    {Second: 1})
Microsecond  = Quantity(1e-6,    {Second: 1})
Nanosecond   = Quantity(1e-9,    {Second: 1})
Minute       = Quantity(60,      {Second: 1})
Hour         = Quantity(3_600,   {Second: 1})
Day          = Quantity(86_400,  {Second: 1})
Week         = Quantity(604_800, {Second: 1})
JulianYear   = Quantity(31_557_600, {Second: 1})

# ── Information (stored as bits) ──────────────────────────────────────────────
# Bit is the IEC 80000-13 base unit; all values are normalised to bits.

Byte         = Quantity(8,       {Bit: 1})

# Decimal (SI-prefixed) multiples
Kilobyte     = Quantity(8_000,           {Bit: 1})
Megabyte     = Quantity(8_000_000,       {Bit: 1})
Gigabyte     = Quantity(8_000_000_000,   {Bit: 1})
Terabyte     = Quantity(8_000_000_000_000, {Bit: 1})

Kilobit      = Quantity(1_000,           {Bit: 1})
Megabit      = Quantity(1_000_000,       {Bit: 1})
Gigabit      = Quantity(1_000_000_000,   {Bit: 1})

# Binary (IEC-prefixed) multiples
Kibibyte     = Quantity(8 * 2**10,  {Bit: 1})
Mebibyte     = Quantity(8 * 2**20,  {Bit: 1})
Gibibyte     = Quantity(8 * 2**30,  {Bit: 1})
Tebibyte     = Quantity(8 * 2**40,  {Bit: 1})

Kibibit      = Quantity(2**10,  {Bit: 1})
Mebibit      = Quantity(2**20,  {Bit: 1})
Gibibit      = Quantity(2**30,  {Bit: 1})

# ═════════════════════════════════════════════════════════════════════════════
# Named derived SI unit predicates
# ═════════════════════════════════════════════════════════════════════════════

# Mechanics
Newton   = _make_unit_pred("Newton",   {Kilogram: 1, Metre: 1, Second: -2})          # N  = kg·m/s²
Joule    = _make_unit_pred("Joule",    {Kilogram: 1, Metre: 2, Second: -2})          # J  = N·m
Watt     = _make_unit_pred("Watt",     {Kilogram: 1, Metre: 2, Second: -3})          # W  = J/s
Pascal   = _make_unit_pred("Pascal",   {Kilogram: 1, Metre: -1, Second: -2})         # Pa = N/m²
Hertz    = _make_unit_pred("Hertz",    {Second: -1})                                 # Hz = 1/s
Gray     = _make_unit_pred("Gray",     {Metre: 2, Second: -2})                       # Gy = J/kg
Sievert  = _make_unit_pred("Sievert",  {Metre: 2, Second: -2})                       # Sv = J/kg

# Electromagnetism
Volt     = _make_unit_pred("Volt",     {Kilogram: 1, Metre: 2, Second: -3, Ampere: -1})  # V  = W/A
Coulomb  = _make_unit_pred("Coulomb",  {Ampere: 1, Second: 1})                           # C  = A·s
Farad    = _make_unit_pred("Farad",    {Kilogram: -1, Metre: -2, Second: 4, Ampere: 2})  # F  = C/V
Ohm      = _make_unit_pred("Ohm",      {Kilogram: 1, Metre: 2, Second: -3, Ampere: -2}) # Ω  = V/A
Siemens  = _make_unit_pred("Siemens",  {Kilogram: -1, Metre: -2, Second: 3, Ampere: 2}) # S  = 1/Ω
Weber    = _make_unit_pred("Weber",    {Kilogram: 1, Metre: 2, Second: -2, Ampere: -1}) # Wb = V·s
Tesla    = _make_unit_pred("Tesla",    {Kilogram: 1, Second: -2, Ampere: -1})            # T  = Wb/m²
Henry    = _make_unit_pred("Henry",    {Kilogram: 1, Metre: 2, Second: -2, Ampere: -2}) # H  = Wb/A

# Photometry
Lumen    = _make_unit_pred("Lumen",    {Candela: 1})                                # lm = cd·sr (sr dimensionless)
Lux      = _make_unit_pred("Lux",      {Candela: 1, Metre: -2})                     # lx = lm/m²

# Chemistry / thermodynamics
Katal    = _make_unit_pred("Katal",    {Mole: 1, Second: -1})                       # kat = mol/s

# Scaled SI pressure (stored as Pascal)
Bar        = Quantity(1e5,              {Kilogram: 1, Metre: -1, Second: -2})
Millibar   = Quantity(100,             {Kilogram: 1, Metre: -1, Second: -2})
Atmosphere = Quantity(101_325,         {Kilogram: 1, Metre: -1, Second: -2})

# Scaled SI energy (stored as Joule)
Electronvolt = Quantity(1.602176634e-19, {Kilogram: 1, Metre: 2, Second: -2})

# Scaled SI power (stored as Watt)
Kilowatt     = Quantity(1_000,         {Kilogram: 1, Metre: 2, Second: -3})

# ═════════════════════════════════════════════════════════════════════════════
# SI standard abbreviation aliases
# ═════════════════════════════════════════════════════════════════════════════
# Lowercase aliases for the SI base units whose standard symbols are safe to
# use as Clausal identifiers (i.e. not all-uppercase, which would be parsed
# as logic variables).
#
# Safe to alias:  m, kg, s, mol, cd
# Not aliased:    A (Ampere) and K (Kelvin) — single uppercase letters are
#                 logic variables in Clausal; use the full names instead.

m   = Metre
kg  = Kilogram
s   = Second
mol = Mole
cd  = Candela

# ── Scaled SI unit abbreviations ─────────────────────────────────────────────
# Quantity constants — multiply by a scalar: ++(5 * km)

km  = Kilometer
cm  = Centimeter
mm  = Millimeter
um  = Micrometer    # μm — μ is not a valid identifier
nm  = Nanometer

mg  = Milligram
ug  = Microgram     # μg

ms  = Millisecond
us  = Microsecond   # μs
ns  = Nanosecond
min = Minute        # shadows Python builtin; import explicitly if needed
hr  = Hour

# ── SI prefix abbreviations ───────────────────────────────────────────────────
# Plain numbers — same as the full names above.
# Uppercase SI symbols (M, G, T, P, E, Z, Y) are logic variables in Clausal
# and cannot be used.  The following lowercase symbols are safe:

k  = kilo    # 1e3   (standard SI symbol)
h  = hecto   # 1e2
da = deca    # 1e1   (two-char: safe)
d  = deci    # 1e-1
c  = centi   # 1e-2
# milli's SI symbol 'm' clashes with Metre — use 'milli' or 'ms'/'mg'/'mm'
n  = nano    # 1e-9
p  = pico    # 1e-12
f  = femto   # 1e-15
a  = atto    # 1e-18


# ═════════════════════════════════════════════════════════════════════════════
# Unit vectors: Quantity(1, ...) values for building expressions
# ═════════════════════════════════════════════════════════════════════════════

# Named derived SI units aliased to their Quantity unit vector
SI_Frequency            = Hertz(1)
SI_Force                = Newton(1)
SI_Energy               = Joule(1)
SI_Power                = Watt(1)
SI_Pressure             = Pascal(1)
SI_Voltage              = Volt(1)
SI_Charge               = Coulomb(1)
SI_Capacitance          = Farad(1)
SI_Resistance           = Ohm(1)
SI_Conductance          = Siemens(1)
SI_MagneticFlux         = Weber(1)
SI_MagneticFluxDensity  = Tesla(1)
SI_Inductance           = Henry(1)
SI_LuminousFlux         = Lumen(1)
SI_Illuminance          = Lux(1)

# Unnamed compound SI dimensions
SI_Area         = Metre(1)**2
SI_Volume       = Metre(1)**3
SI_Velocity     = Metre(1) / Second(1)
SI_Acceleration = Metre(1) / Second(1)**2


# ═════════════════════════════════════════════════════════════════════════════
# Physical constants  (2019 SI exact definitions where available)
# ═════════════════════════════════════════════════════════════════════════════
#
# These are plain Quantity values, not predicates.  Use them in Python
# expressions via the ++ escape::
#
#     E := ++(Kilogram(1) * SpeedOfLight ** 2)

SpeedOfLight          = 299_792_458       * SI_Velocity
PlanckConstant        = 6.62607015e-34    * SI_Energy * Second(1)
ReducedPlanck         = 1.054571817e-34   * SI_Energy * Second(1)
BoltzmannConstant     = 1.380649e-23      * SI_Energy / Kelvin(1)
AvogadroConstant      = 6.02214076e23     / Mole(1)
ElementaryCharge      = 1.602176634e-19   * SI_Charge
StandardGravity       = 9.80665           * SI_Acceleration
GravitationalConstant = 6.67430e-11       * Metre(1)**3 / Kilogram(1) / Second(1)**2
AtomicMassUnit        = 1.66053906660e-27 * Kilogram(1)
ElectronMass          = 9.1093837015e-31  * Kilogram(1)
ProtonMass            = 1.67262192369e-27 * Kilogram(1)
VacuumPermeability    = 1.25663706212e-6  * Kilogram(1) * Metre(1) / Second(1)**2 / Ampere(1)**2
VacuumPermittivity    = 8.8541878128e-12  * Second(1)**4 / Kilogram(1) / Metre(1)**3 * Ampere(1)**2
StefanBoltzmann       = 5.670374419e-8    * SI_Power / Metre(1)**2 / Kelvin(1)**4


# ═════════════════════════════════════════════════════════════════════════════
# Utility predicates
# ═════════════════════════════════════════════════════════════════════════════


def _dimension_of_impl(d, dims_out, trail):
    """DimensionOf(D, Dims): unify Dims with the dimension dict of D.

    Works for ground Quantity values and for uninstantiated AttVars that
    carry a dimensional constraint.
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
        if state is not None:
            dims_term = DictTerm(state.dims)
            if unify(deref(dims_out), dims_term, trail):
                yield None


def _strip_dimensions_impl(d, value_out, trail):
    """StripUnits(Quantity, Value): unify Value with the numeric component."""
    dv = deref(d)
    if not isinstance(dv, Quantity):
        return
    if unify(deref(value_out), dv.value, trail):
        yield None


def _make_dimensioned_impl(value, dims_in, d_out, trail):
    """MakeQuantity(Value, Dims, D): construct Quantity from value + dims dict."""
    from clausal.terms import DictTerm
    v = deref(value)
    di = deref(dims_in)
    if is_var(v) or is_var(di):
        return
    if isinstance(di, DictTerm):
        raw_dims = dict(di.data)
    elif isinstance(di, dict):
        raw_dims = di
    else:
        return
    target = Quantity(v, raw_dims)
    if unify(deref(d_out), target, trail):
        yield None


DimensionOf = _UnitsPredicate("DimensionOf")
DimensionOf._register(2, _simple_to_trampoline(_dimension_of_impl))

StripUnits = _UnitsPredicate("StripUnits")
StripUnits._register(2, _simple_to_trampoline(_strip_dimensions_impl))

MakeQuantity = _UnitsPredicate("MakeQuantity")
MakeQuantity._register(3, _simple_to_trampoline(_make_dimensioned_impl))

# Register the "units" attribute hook for AttVar-based dimensional variables.
import clausal.logic.units_constraint as _units_constraint  # noqa: F401
