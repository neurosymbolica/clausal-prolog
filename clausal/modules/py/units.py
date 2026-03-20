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
    StripDimensions(Dimensioned, V)  — extract numeric value
    MakeDimensioned(Value, Dims, D)  — construct from value + DictTerm dims
"""

from __future__ import annotations

from typing import Callable

from clausal.terms import Dimensioned, UnitsMismatch
from clausal.logic.variables import deref, is_var, unify, get_attr
from clausal.logic.trampoline import DONE


# ── Trampoline helper ────────────────────────────────────────────────────────


def _simple_to_trampoline(simple_fn: Callable) -> Callable:
    """Wrap a simple-mode generator fn(*args, trail) → trampoline."""
    def trampoline_fn(this_generator, parent, *args):
        for _ in simple_fn(*args):
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


# ── Unit constructor factories ───────────────────────────────────────────────


def _make_unit_pred_base(name: str) -> _UnitsPredicate:
    """Create a base SI unit predicate that uses itself as the dimension key.

    We construct the pred object first so it can appear as its own key in the
    ``dims`` dict — e.g. ``{Metre: 1}`` — without a circular-definition problem.
    """
    pred = _UnitsPredicate(name)
    frozen_dims = {pred: 1}   # pred already exists; self-referential key is fine
    pred._dims = frozen_dims

    def _impl(x, d, trail):
        from clausal.logic.units_constraint import constrain_var_dims
        v = deref(x)
        dv = deref(d)
        if not is_var(v):
            raw = v._value if isinstance(v, Dimensioned) and not v.dims else v
            target = Dimensioned(raw, frozen_dims)
            if unify(dv, target, trail):
                yield None
        elif isinstance(dv, Dimensioned) and dv.dims == frozen_dims:
            if unify(v, dv.value, trail):
                yield None
        elif is_var(v) and is_var(dv):
            if constrain_var_dims(dv, frozen_dims, trail):
                yield None

    pred._register(2, _simple_to_trampoline(_impl))
    return pred


def _make_unit_pred(name: str, dims: dict, scale: float = 1.0) -> _UnitsPredicate:
    """Build a bidirectional unit predicate UnitName(Number, Dimensioned).

    Forward  — Number is ground: D = Dimensioned(Number * scale, dims)
    Reverse  — D is a Dimensioned with matching dims: Number = D.value / scale
    Mixed    — scale=1 and Number is Var: wrap Var inside Dimensioned
    """
    frozen_dims = {k: v for k, v in dims.items() if v != 0}

    def _impl(x, d, trail):
        from clausal.logic.units_constraint import constrain_var_dims
        v = deref(x)
        dv = deref(d)
        if not is_var(v):
            # Forward: given a concrete number (or Dimensioned scalar), produce D.
            raw = v._value if isinstance(v, Dimensioned) and not v.dims else v
            target = Dimensioned(raw * scale if scale != 1.0 else raw, frozen_dims)
            if unify(dv, target, trail):
                yield None
        elif isinstance(dv, Dimensioned) and dv.dims == frozen_dims:
            # Reverse: extract the number from a ground Dimensioned.
            result = dv.value / scale if scale != 1.0 else dv.value
            if unify(v, result, trail):
                yield None
        elif is_var(v) and is_var(dv):
            # Both unbound: post a dimensional constraint on D.
            if constrain_var_dims(dv, frozen_dims, trail):
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

    def _impl(d, trail):
        dv = deref(d)
        if isinstance(dv, Dimensioned) and dv.dims == frozen_dims:
            yield None

    pred = _UnitsPredicate(name)
    pred._register(1, _simple_to_trampoline(_impl))
    return pred


# ═════════════════════════════════════════════════════════════════════════════
# SI base unit predicates
# ═════════════════════════════════════════════════════════════════════════════
# Each base unit predicate is its own dimension key: Metre(5, D) gives
# Dimensioned(5, {Metre: 1}).  This avoids stringly-typed dimension dicts.

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
# Dimensionless (empty dims) — wraps a plain number as Dimensioned({})
Dimensionless = _make_unit_pred("Dimensionless", {})

# ═════════════════════════════════════════════════════════════════════════════
# Scaled length units  (all normalise to metres)
# ═════════════════════════════════════════════════════════════════════════════

Kilometer    = _make_unit_pred("Kilometer",    {Metre: 1}, scale=1_000.0)
Centimeter   = _make_unit_pred("Centimeter",   {Metre: 1}, scale=1e-2)
Millimeter   = _make_unit_pred("Millimeter",   {Metre: 1}, scale=1e-3)
Micrometer   = _make_unit_pred("Micrometer",   {Metre: 1}, scale=1e-6)
Nanometer    = _make_unit_pred("Nanometer",    {Metre: 1}, scale=1e-9)
Inch         = _make_unit_pred("Inch",         {Metre: 1}, scale=0.0254)
Foot         = _make_unit_pred("Foot",         {Metre: 1}, scale=0.3048)
Yard         = _make_unit_pred("Yard",         {Metre: 1}, scale=0.9144)
Mile         = _make_unit_pred("Mile",         {Metre: 1}, scale=1_609.344)
NauticalMile = _make_unit_pred("NauticalMile", {Metre: 1}, scale=1_852.0)
LightYear    = _make_unit_pred("LightYear",    {Metre: 1}, scale=9.461e15)
AstronomicalUnit = _make_unit_pred("AstronomicalUnit", {Metre: 1}, scale=1.496e11)

# ═════════════════════════════════════════════════════════════════════════════
# Scaled mass units  (all normalise to kilograms)
# ═════════════════════════════════════════════════════════════════════════════

Gram         = _make_unit_pred("Gram",         {Kilogram: 1}, scale=1e-3)
Milligram    = _make_unit_pred("Milligram",    {Kilogram: 1}, scale=1e-6)
Microgram    = _make_unit_pred("Microgram",    {Kilogram: 1}, scale=1e-9)
Tonne        = _make_unit_pred("Tonne",        {Kilogram: 1}, scale=1_000.0)
Pound        = _make_unit_pred("Pound",        {Kilogram: 1}, scale=0.45359237)
Ounce        = _make_unit_pred("Ounce",        {Kilogram: 1}, scale=0.028349523125)

# ═════════════════════════════════════════════════════════════════════════════
# Scaled time units  (all normalise to seconds)
# ═════════════════════════════════════════════════════════════════════════════

Millisecond  = _make_unit_pred("Millisecond",  {Second: 1}, scale=1e-3)
Microsecond  = _make_unit_pred("Microsecond",  {Second: 1}, scale=1e-6)
Nanosecond   = _make_unit_pred("Nanosecond",   {Second: 1}, scale=1e-9)
Minute       = _make_unit_pred("Minute",       {Second: 1}, scale=60.0)
Hour         = _make_unit_pred("Hour",         {Second: 1}, scale=3_600.0)
Day          = _make_unit_pred("Day",          {Second: 1}, scale=86_400.0)
Week         = _make_unit_pred("Week",         {Second: 1}, scale=604_800.0)
JulianYear   = _make_unit_pred("JulianYear",   {Second: 1}, scale=31_557_600.0)

# ═════════════════════════════════════════════════════════════════════════════
# Named derived SI units
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

# Scaled pressure
Bar      = _make_unit_pred("Bar",      {Kilogram: 1, Metre: -1, Second: -2}, scale=1e5)
Millibar = _make_unit_pred("Millibar", {Kilogram: 1, Metre: -1, Second: -2}, scale=100.0)
Atmosphere = _make_unit_pred("Atmosphere", {Kilogram: 1, Metre: -1, Second: -2}, scale=101_325.0)
PoundsPerSquareInch = _make_unit_pred(
    "PoundsPerSquareInch", {Kilogram: 1, Metre: -1, Second: -2}, scale=6_894.757
)

# Scaled energy
Electronvolt = _make_unit_pred("Electronvolt", {Kilogram: 1, Metre: 2, Second: -2}, scale=1.602176634e-19)
Calorie      = _make_unit_pred("Calorie",      {Kilogram: 1, Metre: 2, Second: -2}, scale=4.184)
Kilocalorie  = _make_unit_pred("Kilocalorie",  {Kilogram: 1, Metre: 2, Second: -2}, scale=4_184.0)
KilowattHour = _make_unit_pred("KilowattHour", {Kilogram: 1, Metre: 2, Second: -2}, scale=3_600_000.0)

# Scaled power
Kilowatt     = _make_unit_pred("Kilowatt",     {Kilogram: 1, Metre: 2, Second: -3}, scale=1_000.0)
Horsepower   = _make_unit_pred("Horsepower",   {Kilogram: 1, Metre: 2, Second: -3}, scale=745.69987)

# Scaled speed
KilometerPerHour = _make_unit_pred(
    "KilometerPerHour", {Metre: 1, Second: -1}, scale=1.0 / 3.6
)
MilePerHour  = _make_unit_pred("MilePerHour",  {Metre: 1, Second: -1}, scale=0.44704)
Knot         = _make_unit_pred("Knot",         {Metre: 1, Second: -1}, scale=1_852.0 / 3600.0)

# ═════════════════════════════════════════════════════════════════════════════
# Dimension-type predicates
# ═════════════════════════════════════════════════════════════════════════════

IsLength               = _make_is_dim_pred("IsLength",               {Metre: 1})
IsArea                 = _make_is_dim_pred("IsArea",                  {Metre: 2})
IsVolume               = _make_is_dim_pred("IsVolume",                {Metre: 3})
IsMass                 = _make_is_dim_pred("IsMass",                  {Kilogram: 1})
IsTime                 = _make_is_dim_pred("IsTime",                  {Second: 1})
IsFrequency            = _make_is_dim_pred("IsFrequency",             {Second: -1})
IsVelocity             = _make_is_dim_pred("IsVelocity",              {Metre: 1, Second: -1})
IsAcceleration         = _make_is_dim_pred("IsAcceleration",          {Metre: 1, Second: -2})
IsForce                = _make_is_dim_pred("IsForce",                 {Kilogram: 1, Metre: 1, Second: -2})
IsEnergy               = _make_is_dim_pred("IsEnergy",                {Kilogram: 1, Metre: 2, Second: -2})
IsPower                = _make_is_dim_pred("IsPower",                 {Kilogram: 1, Metre: 2, Second: -3})
IsPressure             = _make_is_dim_pred("IsPressure",              {Kilogram: 1, Metre: -1, Second: -2})
IsElectricCurrent      = _make_is_dim_pred("IsElectricCurrent",       {Ampere: 1})
IsVoltage              = _make_is_dim_pred("IsVoltage",               {Kilogram: 1, Metre: 2, Second: -3, Ampere: -1})
IsCharge               = _make_is_dim_pred("IsCharge",                {Ampere: 1, Second: 1})
IsResistance           = _make_is_dim_pred("IsResistance",            {Kilogram: 1, Metre: 2, Second: -3, Ampere: -2})
IsCapacitance          = _make_is_dim_pred("IsCapacitance",           {Kilogram: -1, Metre: -2, Second: 4, Ampere: 2})
IsInductance           = _make_is_dim_pred("IsInductance",            {Kilogram: 1, Metre: 2, Second: -2, Ampere: -2})
IsMagneticFlux         = _make_is_dim_pred("IsMagneticFlux",          {Kilogram: 1, Metre: 2, Second: -2, Ampere: -1})
IsMagneticFluxDensity  = _make_is_dim_pred("IsMagneticFluxDensity",   {Kilogram: 1, Second: -2, Ampere: -1})
IsTemperature          = _make_is_dim_pred("IsTemperature",           {Kelvin: 1})
IsAmountOfSubstance    = _make_is_dim_pred("IsAmountOfSubstance",     {Mole: 1})
IsLuminousIntensity    = _make_is_dim_pred("IsLuminousIntensity",     {Candela: 1})
IsIlluminance          = _make_is_dim_pred("IsIlluminance",           {Candela: 1, Metre: -2})


def _is_dimensionless_impl(d, trail):
    """IsDimensionless: succeed for Dimensioned with no dims, or plain numbers."""
    dv = deref(d)
    if isinstance(dv, Dimensioned) and not dv.dims:
        yield None
    elif isinstance(dv, (int, float)) and not isinstance(dv, bool):
        yield None


def _is_dimensioned_impl(d, trail):
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
SI_Area         = Metre(1)**2
SI_Volume       = Metre(1)**3
SI_Velocity     = Metre(1) / Second(1)
SI_Acceleration = Metre(1) / Second(1)**2


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

    Works for ground Dimensioned values and for uninstantiated AttVars that
    carry a dimensional constraint.
    """
    from clausal.terms import DictTerm
    from clausal.logic.units_constraint import UNITS_KEY
    dv = deref(d)
    if isinstance(dv, Dimensioned):
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
    """StripDimensions(Dimensioned, Value): unify Value with the numeric component."""
    dv = deref(d)
    if not isinstance(dv, Dimensioned):
        return
    if unify(deref(value_out), dv.value, trail):
        yield None


def _make_dimensioned_impl(value, dims_in, d_out, trail):
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

StripDimensions = _UnitsPredicate("StripDimensions")
StripDimensions._register(2, _simple_to_trampoline(_strip_dimensions_impl))

MakeDimensioned = _UnitsPredicate("MakeDimensioned")
MakeDimensioned._register(3, _simple_to_trampoline(_make_dimensioned_impl))

# Register the "units" attribute hook for AttVar-based dimensional variables.
import clausal.logic.units_constraint as _units_constraint  # noqa: F401
