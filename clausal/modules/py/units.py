"""clausal.modules.py.units — Physical units and dimensional analysis.

Provides named-unit constructor predicates and dimension-check predicates
for use with ``Dimensioned`` values.

All values are stored internally in SI base units (m, kg, s, A, K, mol, cd).
Non-SI unit predicates (Kilometer, Gram, Hour, …) scale on the way in and out.

Usage in .clausal files::

    -import_from(py.units, [Meter, Newton, Watt, IsForce, IsEnergy, ...])

Usage from Python::

    from clausal.modules.py.units import Meter, Newton, IsForce
    from clausal import query
    results = list(query(Newton(10, 'D'), 'D'))

Named unit predicates (arity 2):  UnitName(Number, Dimensioned)
    Number ↔ Dimensioned conversion, bidirectional.

Dimension-check predicates (arity 1): IsXxx(Dimensioned)
    Succeed iff the argument is a Dimensioned with the expected dimension dict.

Utility predicates:
    DimensionOf(Dimensioned, Dims)   — extract dims as DictTerm
    ValueOf(Dimensioned, Value)      — extract numeric value
    MakeDimensioned(Value, Dims, D)  — construct from value + DictTerm dims
    StripDimensions(Dimensioned, V)  — alias for ValueOf
"""

from __future__ import annotations

from typing import Callable

from clausal.terms import Dimensioned, UnitsMismatch
from clausal.logic.variables import deref, is_var, unify
from clausal.logic.trampoline import DONE


# ── Trampoline helper ────────────────────────────────────────────────────────


def _simple_to_trampoline(simple_fn: Callable) -> Callable:
    """Wrap a simple-mode generator fn(*args, trail, k=None) → trampoline."""
    def trampoline_fn(this_generator, parent, *args):
        for _ in simple_fn(*args, None):
            yield (parent, None)
        yield (parent, DONE)
    return trampoline_fn


# ── Predicate adapter (supports multi-arity) ─────────────────────────────────


class _UnitsPredicate:
    """Adapter providing ``_get_dispatch()`` for a units predicate.

    Also callable as a Python expression when ``_dims`` is set:
    ``Kilogram(5)`` returns ``Dimensioned(5, {'kg': 1})`` directly, for use
    in Python arithmetic expressions via the ``++`` escape in .clausal files::

        E := ++(Kilogram(1) * SpeedOfLight ** 2)
    """

    __slots__ = ("_name", "_dispatch_fns", "_dims", "_scale")

    def __init__(self, name: str) -> None:
        self._name = name
        self._dispatch_fns: dict[int, Callable] = {}
        self._dims: dict | None = None
        self._scale: float = 1.0

    def _register(self, arity: int, fn: Callable) -> None:
        self._dispatch_fns[arity] = fn

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

    def __call__(self, value) -> "Dimensioned":
        """Return ``Dimensioned(value * scale, dims)`` directly.

        For use in Python-level arithmetic expressions, not as a Clausal goal.
        """
        if self._dims is None:
            raise TypeError(f"{self._name} does not support direct construction")
        return Dimensioned(
            value * self._scale if self._scale != 1.0 else value,
            self._dims,
        )

    def __repr__(self) -> str:
        arities = sorted(self._dispatch_fns)
        return f"units.{self._name}/{arities}"


# ── Unit constructor factory ─────────────────────────────────────────────────


def _make_unit_pred(name: str, dims: dict, scale: float = 1.0) -> _UnitsPredicate:
    """Build a bidirectional unit predicate UnitName(Number, Dimensioned).

    Forward  — Number is ground: D = Dimensioned(Number * scale, dims)
    Reverse  — D is a Dimensioned with matching dims: Number = D.value / scale
    Mixed    — scale=1 and Number is Var: wrap Var inside Dimensioned
    """
    frozen_dims = {k: v for k, v in dims.items() if v != 0}

    def _impl(x, d, trail, k):
        v = deref(x)
        dv = deref(d)
        if not is_var(v):
            # Forward: given a concrete number (or Dimensioned scalar), produce D.
            raw = v._value if isinstance(v, Dimensioned) and not v.dims else v
            target = Dimensioned(raw * scale if scale != 1.0 else raw, frozen_dims)
            if unify(dv, target, trail):
                yield None
        elif isinstance(dv, Dimensioned) and dv.dims == frozen_dims:
            # Reverse: extract the number from a fully-ground Dimensioned.
            raw_val = dv.value
            if not is_var(raw_val):
                result = raw_val / scale if scale != 1.0 else raw_val
                if unify(v, result, trail):
                    yield None
            else:
                # Value inside D is still a logic variable; wrap it bidirectionally.
                scaled_var = raw_val  # scale=1 assumed; non-1 scale with var unsupported
                if scale == 1.0 and unify(v, scaled_var, trail):
                    yield None
        elif is_var(v) and is_var(dv) and scale == 1.0:
            # Both unbound: bind D to Dimensioned(X, dims) — X stays free.
            target = Dimensioned(v, frozen_dims)
            if unify(dv, target, trail):
                yield None
        # else: cannot determine — fail silently

    pred = _UnitsPredicate(name)
    pred._dims = frozen_dims
    pred._scale = scale
    pred._register(2, _simple_to_trampoline(_impl))
    return pred


# ── Dimension-check predicate factory ────────────────────────────────────────


def _make_is_dim_pred(name: str, dims: dict) -> _UnitsPredicate:
    """Build an IsXxx(D) predicate: succeed iff D is Dimensioned with dims."""
    frozen_dims = {k: v for k, v in dims.items() if v != 0}

    def _impl(d, trail, k):
        dv = deref(d)
        if isinstance(dv, Dimensioned) and dv.dims == frozen_dims:
            yield None

    pred = _UnitsPredicate(name)
    pred._register(1, _simple_to_trampoline(_impl))
    return pred


# ═════════════════════════════════════════════════════════════════════════════
# SI base unit predicates
# ═════════════════════════════════════════════════════════════════════════════

# Length
Metre        = _make_unit_pred("Metre",        {"m": 1})
Meter        = Metre   # American spelling alias
# Mass
Kilogram     = _make_unit_pred("Kilogram",     {"kg": 1})
# Time
Second       = _make_unit_pred("Second",       {"s": 1})
# Electric current
Ampere       = _make_unit_pred("Ampere",       {"A": 1})
# Thermodynamic temperature (ratio scale only — no Celsius/Fahrenheit)
Kelvin       = _make_unit_pred("Kelvin",       {"K": 1})
# Amount of substance
Mole         = _make_unit_pred("Mole",         {"mol": 1})
# Luminous intensity
Candela      = _make_unit_pred("Candela",      {"cd": 1})
# Dimensionless (empty dims) — wraps a plain number as Dimensioned({})
Dimensionless = _make_unit_pred("Dimensionless", {})

# ═════════════════════════════════════════════════════════════════════════════
# Scaled length units  (all normalise to metres)
# ═════════════════════════════════════════════════════════════════════════════

Kilometer    = _make_unit_pred("Kilometer",    {"m": 1}, scale=1_000.0)
Centimeter   = _make_unit_pred("Centimeter",   {"m": 1}, scale=1e-2)
Millimeter   = _make_unit_pred("Millimeter",   {"m": 1}, scale=1e-3)
Micrometer   = _make_unit_pred("Micrometer",   {"m": 1}, scale=1e-6)
Nanometer    = _make_unit_pred("Nanometer",    {"m": 1}, scale=1e-9)
Inch         = _make_unit_pred("Inch",         {"m": 1}, scale=0.0254)
Foot         = _make_unit_pred("Foot",         {"m": 1}, scale=0.3048)
Yard         = _make_unit_pred("Yard",         {"m": 1}, scale=0.9144)
Mile         = _make_unit_pred("Mile",         {"m": 1}, scale=1_609.344)
NauticalMile = _make_unit_pred("NauticalMile", {"m": 1}, scale=1_852.0)
LightYear    = _make_unit_pred("LightYear",    {"m": 1}, scale=9.461e15)
AstronomicalUnit = _make_unit_pred("AstronomicalUnit", {"m": 1}, scale=1.496e11)

# ═════════════════════════════════════════════════════════════════════════════
# Scaled mass units  (all normalise to kilograms)
# ═════════════════════════════════════════════════════════════════════════════

Gram         = _make_unit_pred("Gram",         {"kg": 1}, scale=1e-3)
Milligram    = _make_unit_pred("Milligram",    {"kg": 1}, scale=1e-6)
Microgram    = _make_unit_pred("Microgram",    {"kg": 1}, scale=1e-9)
Tonne        = _make_unit_pred("Tonne",        {"kg": 1}, scale=1_000.0)
Pound        = _make_unit_pred("Pound",        {"kg": 1}, scale=0.45359237)
Ounce        = _make_unit_pred("Ounce",        {"kg": 1}, scale=0.028349523125)

# ═════════════════════════════════════════════════════════════════════════════
# Scaled time units  (all normalise to seconds)
# ═════════════════════════════════════════════════════════════════════════════

Millisecond  = _make_unit_pred("Millisecond",  {"s": 1}, scale=1e-3)
Microsecond  = _make_unit_pred("Microsecond",  {"s": 1}, scale=1e-6)
Nanosecond   = _make_unit_pred("Nanosecond",   {"s": 1}, scale=1e-9)
Minute       = _make_unit_pred("Minute",       {"s": 1}, scale=60.0)
Hour         = _make_unit_pred("Hour",         {"s": 1}, scale=3_600.0)
Day          = _make_unit_pred("Day",          {"s": 1}, scale=86_400.0)
Week         = _make_unit_pred("Week",         {"s": 1}, scale=604_800.0)
JulianYear   = _make_unit_pred("JulianYear",   {"s": 1}, scale=31_557_600.0)

# ═════════════════════════════════════════════════════════════════════════════
# Named derived SI units
# ═════════════════════════════════════════════════════════════════════════════

# Mechanics
Newton   = _make_unit_pred("Newton",   {"kg": 1, "m": 1, "s": -2})          # N  = kg·m/s²
Joule    = _make_unit_pred("Joule",    {"kg": 1, "m": 2, "s": -2})          # J  = N·m
Watt     = _make_unit_pred("Watt",     {"kg": 1, "m": 2, "s": -3})          # W  = J/s
Pascal   = _make_unit_pred("Pascal",   {"kg": 1, "m": -1, "s": -2})         # Pa = N/m²
Hertz    = _make_unit_pred("Hertz",    {"s": -1})                            # Hz = 1/s
Gray     = _make_unit_pred("Gray",     {"m": 2, "s": -2})                   # Gy = J/kg
Sievert  = _make_unit_pred("Sievert",  {"m": 2, "s": -2})                   # Sv = J/kg

# Electromagnetism
Volt     = _make_unit_pred("Volt",     {"kg": 1, "m": 2, "s": -3, "A": -1}) # V  = W/A
Coulomb  = _make_unit_pred("Coulomb",  {"A": 1, "s": 1})                    # C  = A·s
Farad    = _make_unit_pred("Farad",    {"kg": -1, "m": -2, "s": 4, "A": 2}) # F  = C/V
Ohm      = _make_unit_pred("Ohm",      {"kg": 1, "m": 2, "s": -3, "A": -2}) # Ω  = V/A
Siemens  = _make_unit_pred("Siemens",  {"kg": -1, "m": -2, "s": 3, "A": 2}) # S  = 1/Ω
Weber    = _make_unit_pred("Weber",    {"kg": 1, "m": 2, "s": -2, "A": -1}) # Wb = V·s
Tesla    = _make_unit_pred("Tesla",    {"kg": 1, "s": -2, "A": -1})         # T  = Wb/m²
Henry    = _make_unit_pred("Henry",    {"kg": 1, "m": 2, "s": -2, "A": -2}) # H  = Wb/A

# Photometry
Lumen    = _make_unit_pred("Lumen",    {"cd": 1})                            # lm = cd·sr (sr dimensionless)
Lux      = _make_unit_pred("Lux",      {"cd": 1, "m": -2})                  # lx = lm/m²

# Chemistry / thermodynamics
Katal    = _make_unit_pred("Katal",    {"mol": 1, "s": -1})                 # kat = mol/s

# Scaled pressure
Bar      = _make_unit_pred("Bar",      {"kg": 1, "m": -1, "s": -2}, scale=1e5)
Millibar = _make_unit_pred("Millibar", {"kg": 1, "m": -1, "s": -2}, scale=100.0)
Atmosphere = _make_unit_pred("Atmosphere", {"kg": 1, "m": -1, "s": -2}, scale=101_325.0)
PoundsPerSquareInch = _make_unit_pred(
    "PoundsPerSquareInch", {"kg": 1, "m": -1, "s": -2}, scale=6_894.757
)

# Scaled energy
Electronvolt = _make_unit_pred("Electronvolt", {"kg": 1, "m": 2, "s": -2}, scale=1.602176634e-19)
Calorie      = _make_unit_pred("Calorie",      {"kg": 1, "m": 2, "s": -2}, scale=4.184)
Kilocalorie  = _make_unit_pred("Kilocalorie",  {"kg": 1, "m": 2, "s": -2}, scale=4_184.0)
KilowattHour = _make_unit_pred("KilowattHour", {"kg": 1, "m": 2, "s": -2}, scale=3_600_000.0)

# Scaled power
Kilowatt     = _make_unit_pred("Kilowatt",     {"kg": 1, "m": 2, "s": -3}, scale=1_000.0)
Horsepower   = _make_unit_pred("Horsepower",   {"kg": 1, "m": 2, "s": -3}, scale=745.69987)

# Scaled speed
KilometerPerHour = _make_unit_pred(
    "KilometerPerHour", {"m": 1, "s": -1}, scale=1.0 / 3.6
)
MilePerHour  = _make_unit_pred("MilePerHour",  {"m": 1, "s": -1}, scale=0.44704)
Knot         = _make_unit_pred("Knot",         {"m": 1, "s": -1}, scale=1_852.0 / 3600.0)

# ═════════════════════════════════════════════════════════════════════════════
# Dimension-type predicates
# ═════════════════════════════════════════════════════════════════════════════

IsLength               = _make_is_dim_pred("IsLength",               {"m": 1})
IsArea                 = _make_is_dim_pred("IsArea",                  {"m": 2})
IsVolume               = _make_is_dim_pred("IsVolume",                {"m": 3})
IsMass                 = _make_is_dim_pred("IsMass",                  {"kg": 1})
IsTime                 = _make_is_dim_pred("IsTime",                  {"s": 1})
IsFrequency            = _make_is_dim_pred("IsFrequency",             {"s": -1})
IsVelocity             = _make_is_dim_pred("IsVelocity",              {"m": 1, "s": -1})
IsAcceleration         = _make_is_dim_pred("IsAcceleration",          {"m": 1, "s": -2})
IsForce                = _make_is_dim_pred("IsForce",                 {"kg": 1, "m": 1, "s": -2})
IsEnergy               = _make_is_dim_pred("IsEnergy",                {"kg": 1, "m": 2, "s": -2})
IsPower                = _make_is_dim_pred("IsPower",                 {"kg": 1, "m": 2, "s": -3})
IsPressure             = _make_is_dim_pred("IsPressure",              {"kg": 1, "m": -1, "s": -2})
IsElectricCurrent      = _make_is_dim_pred("IsElectricCurrent",       {"A": 1})
IsVoltage              = _make_is_dim_pred("IsVoltage",               {"kg": 1, "m": 2, "s": -3, "A": -1})
IsCharge               = _make_is_dim_pred("IsCharge",                {"A": 1, "s": 1})
IsResistance           = _make_is_dim_pred("IsResistance",            {"kg": 1, "m": 2, "s": -3, "A": -2})
IsCapacitance          = _make_is_dim_pred("IsCapacitance",           {"kg": -1, "m": -2, "s": 4, "A": 2})
IsInductance           = _make_is_dim_pred("IsInductance",            {"kg": 1, "m": 2, "s": -2, "A": -2})
IsMagneticFlux         = _make_is_dim_pred("IsMagneticFlux",          {"kg": 1, "m": 2, "s": -2, "A": -1})
IsMagneticFluxDensity  = _make_is_dim_pred("IsMagneticFluxDensity",   {"kg": 1, "s": -2, "A": -1})
IsTemperature          = _make_is_dim_pred("IsTemperature",           {"K": 1})
IsAmountOfSubstance    = _make_is_dim_pred("IsAmountOfSubstance",     {"mol": 1})
IsLuminousIntensity    = _make_is_dim_pred("IsLuminousIntensity",     {"cd": 1})
IsIlluminance          = _make_is_dim_pred("IsIlluminance",           {"cd": 1, "m": -2})


def _is_dimensionless_impl(d, trail, k):
    """IsDimensionless: succeed for Dimensioned with no dims, or plain numbers."""
    dv = deref(d)
    if isinstance(dv, Dimensioned) and not dv.dims:
        yield None
    elif isinstance(dv, (int, float)) and not isinstance(dv, bool):
        yield None


def _is_dimensioned_impl(d, trail, k):
    """IsDimensioned: succeed for any Dimensioned value."""
    dv = deref(d)
    if isinstance(dv, Dimensioned):
        yield None


IsDimensionless = _UnitsPredicate("IsDimensionless")
IsDimensionless._register(1, _simple_to_trampoline(_is_dimensionless_impl))

IsDimensioned = _UnitsPredicate("IsDimensioned")
IsDimensioned._register(1, _simple_to_trampoline(_is_dimensioned_impl))


# ═════════════════════════════════════════════════════════════════════════════
# Unit vectors: Dimensioned(1, ...) values for building expressions
# ═════════════════════════════════════════════════════════════════════════════

# Powers of base units
Metre2    = Metre(1)**2
Metre3    = Metre(1)**3
Second2   = Second(1)**2
Second3   = Second(1)**3
Ampere2   = Ampere(1)**2
Kelvin4   = Kelvin(1)**4

# Named derived SI units aliased to their Dimensioned unit vector
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
SI_Area         = Metre2
SI_Volume       = Metre3
SI_Velocity     = Metre(1) / Second(1)
SI_Acceleration = Metre(1) / Second2


# ═════════════════════════════════════════════════════════════════════════════
# Physical constants  (2019 SI exact definitions where available)
# ═════════════════════════════════════════════════════════════════════════════
#
# These are plain Dimensioned values, not predicates.  Use them in Python
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
GravitationalConstant = 6.67430e-11       * Metre3 / Kilogram(1) / Second2
AtomicMassUnit        = 1.66053906660e-27 * Kilogram(1)
ElectronMass          = 9.1093837015e-31  * Kilogram(1)
ProtonMass            = 1.67262192369e-27 * Kilogram(1)
VacuumPermeability    = 1.25663706212e-6  * Kilogram(1) * Metre(1) / Second2 / Ampere2
VacuumPermittivity    = 8.8541878128e-12  * Second2 * Second2 / Kilogram(1) / Metre3 * Ampere2
StefanBoltzmann       = 5.670374419e-8    * SI_Power / Metre2 / Kelvin4


# ═════════════════════════════════════════════════════════════════════════════
# Utility predicates
# ═════════════════════════════════════════════════════════════════════════════


def _dimension_of_impl(d, dims_out, trail, k):
    """DimensionOf(Dimensioned, Dims): unify Dims with a dict of the dimensions."""
    from clausal.terms import DictTerm
    dv = deref(d)
    if not isinstance(dv, Dimensioned):
        return
    dims_term = DictTerm(dv.dims)
    if unify(deref(dims_out), dims_term, trail):
        yield None


def _value_of_impl(d, value_out, trail, k):
    """ValueOf(Dimensioned, Value): unify Value with the numeric component."""
    dv = deref(d)
    if not isinstance(dv, Dimensioned):
        return
    if unify(deref(value_out), dv.value, trail):
        yield None


def _make_dimensioned_impl(value, dims_in, d_out, trail, k):
    """MakeDimensioned(Value, Dims, D): construct Dimensioned from value + dims dict."""
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
    target = Dimensioned(v, raw_dims)
    if unify(deref(d_out), target, trail):
        yield None


DimensionOf = _UnitsPredicate("DimensionOf")
DimensionOf._register(2, _simple_to_trampoline(_dimension_of_impl))

ValueOf = _UnitsPredicate("ValueOf")
ValueOf._register(2, _simple_to_trampoline(_value_of_impl))

StripDimensions = _UnitsPredicate("StripDimensions")
StripDimensions._register(2, _simple_to_trampoline(_value_of_impl))  # alias

MakeDimensioned = _UnitsPredicate("MakeDimensioned")
MakeDimensioned._register(3, _simple_to_trampoline(_make_dimensioned_impl))
