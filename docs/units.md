# Physical Units

Dimensional analysis via `Dimensioned(value, dims)` terms, with full arithmetic,
named-unit predicates, and syntactic sugar for writing measurements inline.

---

## Quick start

```python
-import_from(py.units, [Metre, Kilogram, Second, Newton, IsForce, StripDimensions])

# Build a dimensioned value with n(Unit) sugar
distance := 100(Metre)          # Dimensioned(100, {Metre: 1})
time_    := 9.58(Second)        # Dimensioned(9.58, {Second: 1})
speed    := distance / time_    # Dimensioned(10.4…, {Metre: 1, Second: -1})

# Check dimension type
IsForce(9.8(Newton))

# Extract numeric component
StripDimensions(9.8(Newton), V),        # V = 9.8

# Constrain an unbound variable to a dimension
F(Newton),                      # F must eventually be bound to a Newton value
F is 9.8(Newton)                # binds F, hook checks dims match
```

---

## Syntactic sugar

### `n(Unit)` — literal measurement

```python
5(Metre)          # → Dimensioned(5,   {Metre: 1})
9.8(Newton)       # → Dimensioned(9.8, {Kilogram: 1, Metre: 1, Second: -2})
-3(Second)        # → Dimensioned(-3,  {Second: 1})
```

Python parses `5(Metre)` as a call — the transformer intercepts it and rewrites
it to `++(Metre(5))`. Any numeric literal (int or float) combined with a
single named unit predicate works. For compound or unusual units, use
`++()` directly:

```python
custom := ++(Kilogram(1) * Metre(1) / Second(1)**2 * 9.8)   # same as 9.8(Newton)
```

### `n()` — dimensionless literal

An empty-argument call on any numeric literal produces a dimensionless
`Dimensioned(n, {})`:

```python
42()      # → Dimensioned(42,   {})
3.14()    # → Dimensioned(3.14, {})
0()       # → Dimensioned(0,    {})
```

This is equivalent to `++(Dimensioned(n, {}))` or calling the `Dimensionless`
predicate. The value participates in unit arithmetic — dividing two compatible
quantities to get a ratio is a common result:

```python
RATIO := 50(Metre) / 10(Metre)   # → Dimensioned(5.0, {})
IsDimensionless(RATIO)            # succeeds
RATIO == 5.0()                    # succeeds
```

`IsDimensionless` also succeeds for plain Python ints/floats.

### `X(Unit)` — dimension constraint on a variable

When the callee is a logic variable, `X(Unit)` desugars to `HasUnits(X, Unit)`:

```python
F(Newton)              # → HasUnits(F, Newton)
```

`HasUnits/2` posts an AttVar constraint on `F`: any subsequent unification
of `F` fires a hook that checks the bound value has matching dimensions.
The constraint backtracks correctly with the trail.

```python
# Constraint posted, then satisfied
F(Newton),
F is 9.8(Newton),      # hook checks {Newton dims} == {Newton dims} → OK
IsForce(F)             # succeeds

# Constraint posted, then violated → entire conjunction fails
F(Newton),
F is 1(Second)         # hook rejects: Newton dims ≠ Second dims
```

`X(Unit)` produces a **goal**, not a value. It cannot appear on the RHS of
`:=` — that position expects an expression.

---

## `Dimensioned` term

```python
from clausal.terms import Dimensioned, UnitsMismatch

d = Dimensioned(10.0, {Metre: 1, Second: -1})  # 10 m/s
d.value   # 10.0
d.dims    # MappingProxyType({<Metre>: 1, <Second>: -1})
```

`dims` returns an immutable `MappingProxyType` mapping unit-predicate objects
(not strings) to integer exponents. Zero exponents are removed on construction.
The empty proxy `{}` is dimensionless.

`Dimensioned` holds a ground numeric value — never a logic variable. An
uninstantiated dimensioned slot is a plain Var with a `"units"` AttVar
constraint (see below).

### Arithmetic

| Operation  | Behaviour |
|------------|-----------|
| `a + b`    | Requires identical dims; raises `UnitsMismatch` otherwise |
| `a - b`    | Same as addition |
| `a * b`    | Merges dims by addition (exponents add) |
| `a / b`    | Merges dims by subtraction (exponents subtract) |
| `a ** n`   | Multiplies all exponents by integer `n`; raises `UnitsMismatch` for non-integer |
| `-a`       | Negates value; preserves dims |
| `abs(a)`   | Absolute value; preserves dims |
| `a * k`    | Scales value by plain number; preserves dims |
| `k / a`    | Inverts dims and scales |

Dimensionless values (`dims == {}`) interoperate freely with plain numbers.

### Comparisons

`<`, `<=`, `>`, `>=` require identical dims; raise `UnitsMismatch` otherwise.

---

## Module: `clausal.modules.py.units`

Import in `.clausal` files:

```python
-import_from(py.units, [Metre, Newton, IsForce, StripDimensions])
```

### Named-unit predicates — `Unit(Number, Dimensioned)`

Bidirectional, arity 2:

- **Forward** (`Number` given): unify `Dimensioned` with `Dimensioned(Number * scale, dims)`.
- **Reverse** (`Dimensioned` given): unify `Number` with `value / scale`.

The `n(Unit)` sugar (`5(Metre)`) calls `Unit(n)` as a plain Python call
(arity 1), returning `Dimensioned` directly. The two-argument predicate
form is still useful for reverse mode and for pattern matching in clause heads.

#### SI base units

| Predicate  | Dims          | Scale |
|------------|---------------|-------|
| `Metre`    | `{Metre: 1}`  | 1     |
| `Kilogram` | `{Kilogram: 1}` | 1   |
| `Second`   | `{Second: 1}` | 1     |
| `Ampere`   | `{Ampere: 1}` | 1     |
| `Kelvin`   | `{Kelvin: 1}` | 1     |
| `Mole`     | `{Mole: 1}`   | 1     |
| `Candela`  | `{Candela: 1}` | 1    |

#### Scaled length (store as metres)

`Kilometer`, `Centimeter`, `Millimeter`, `Micrometer`, `Nanometer`,
`Inch`, `Foot`, `Yard`, `Mile`, `NauticalMile`, `LightYear`, `AstronomicalUnit`

#### Scaled mass (store as kilograms)

`Gram`, `Milligram`, `Microgram`, `Tonne`, `Pound`, `Ounce`

#### Scaled time (store as seconds)

`Millisecond`, `Microsecond`, `Nanosecond`, `Minute`, `Hour`, `Day`, `Week`, `JulianYear`

#### Named derived SI units

| Predicate | Quantity              | Dims (SI base)                    |
|-----------|-----------------------|-----------------------------------|
| `Newton`  | force                 | `{kg:1, m:1, s:-2}`              |
| `Joule`   | energy                | `{kg:1, m:2, s:-2}`              |
| `Watt`    | power                 | `{kg:1, m:2, s:-3}`              |
| `Pascal`  | pressure              | `{kg:1, m:-1, s:-2}`             |
| `Hertz`   | frequency             | `{s:-1}`                          |
| `Volt`    | voltage               | `{kg:1, m:2, s:-3, A:-1}`        |
| `Coulomb` | charge                | `{A:1, s:1}`                      |
| `Farad`   | capacitance           | `{kg:-1, m:-2, s:4, A:2}`        |
| `Ohm`     | resistance            | `{kg:1, m:2, s:-3, A:-2}`        |
| `Siemens` | conductance           | `{kg:-1, m:-2, s:3, A:2}`        |
| `Weber`   | magnetic flux         | `{kg:1, m:2, s:-2, A:-1}`        |
| `Tesla`   | magnetic flux density | `{kg:1, s:-2, A:-1}`             |
| `Henry`   | inductance            | `{kg:1, m:2, s:-2, A:-2}`        |
| `Lumen`   | luminous flux         | `{cd:1}`                          |
| `Lux`     | illuminance           | `{cd:1, m:-2}`                    |
| `Katal`   | catalytic activity    | `{mol:1, s:-1}`                   |
| `Gray`    | absorbed dose         | `{m:2, s:-2}`                     |
| `Sievert` | dose equivalent       | `{m:2, s:-2}`                     |

Scaled variants: `Bar`, `Millibar`, `Atmosphere`, `PoundsPerSquareInch`,
`Electronvolt`, `Calorie`, `Kilocalorie`, `KilowattHour`, `Kilowatt`,
`Horsepower`, `KilometerPerHour`, `MilePerHour`, `Knot`

### Dimension-check predicates — `IsXxx(Dimensioned)`

Succeed iff the argument is a `Dimensioned` with the expected dimension dict.

`IsLength`, `IsArea`, `IsVolume`, `IsMass`, `IsTime`, `IsFrequency`,
`IsVelocity`, `IsAcceleration`, `IsForce`, `IsEnergy`, `IsPower`, `IsPressure`,
`IsElectricCurrent`, `IsVoltage`, `IsCharge`, `IsResistance`, `IsCapacitance`,
`IsInductance`, `IsMagneticFlux`, `IsMagneticFluxDensity`, `IsTemperature`,
`IsAmountOfSubstance`, `IsLuminousIntensity`, `IsIlluminance`,
`IsDimensionless`, `IsDimensioned`

`IsDimensionless` also succeeds for plain Python ints/floats.

### Utility predicates

| Predicate                     | Description |
|-------------------------------|-------------|
| `DimensionOf(D, Dims)`        | Unify `Dims` with a `DictTerm` of the dimension dict |
| `StripDimensions(D, V)`       | Unify `V` with the numeric component |
| `MakeDimensioned(V, Dims, D)` | Construct `Dimensioned` from value `V` and `DictTerm` dims |

`DimensionOf` also works on uninstantiated Vars with a dimension constraint —
it unifies `Dims` with the dims from the AttVar's `"units"` attribute.

### `HasUnits/2`

```python
HasUnits(D, UnitPred)
```

The builtin underlying `X(Unit)` sugar. Succeeds if:

- `D` is a ground `Dimensioned` whose dims match `UnitPred._dims`, or
- `D` is an unbound Var — posts the `"units"` AttVar constraint and succeeds.

Fails if `D` is bound to something else (wrong dims, plain number with
non-empty dims, non-Dimensioned term).

### Physical constants

| Name                 | Value (SI)                           | Dims |
|----------------------|--------------------------------------|------|
| `SpeedOfLight`       | 2.998 × 10⁸ m/s                     | `{m:1, s:-1}` |
| `PlanckConstant`     | 6.626 × 10⁻³⁴ J·s                  | `{kg:1, m:2, s:-1}` |
| `BoltzmannConstant`  | 1.381 × 10⁻²³ J/K                  | `{kg:1, m:2, s:-2, K:-1}` |
| `StandardGravity`    | 9.80665 m/s²                        | `{m:1, s:-2}` |
| `ElementaryCharge`   | 1.602 × 10⁻¹⁹ C                    | `{A:1, s:1}` |
| `GravitationalConstant` | 6.674 × 10⁻¹¹ m³/(kg·s²)       | `{m:3, kg:-1, s:-2}` |

---

## Uninstantiated dimensioned slots (AttVar)

An uninstantiated slot that will eventually hold a measurement uses a plain
Var with a `"units"` AttVar constraint — **not** `Dimensioned(Var, dims)`.

```python
from clausal.logic.variables import Var, Trail
from clausal.logic.units_constraint import constrain_var_dims, UNITS_KEY
from clausal.modules.py.units import Newton

trail = Trail()
v = Var()
constrain_var_dims(v, Newton._dims, trail)  # post constraint

from clausal.logic.variables import unify
unify(v, Newton(9.8), trail)   # fires hook → checks dims → binds v
```

The hook fires on unification, checks dims match, and rejects if they don't.
The constraint is undone if the trail is rewound past the mark where it was posted.

---

## Catching unit errors

`UnitsMismatch` is a plain Python exception raised when incompatible units are
combined inside `++()` escapes. It is catchable via `catch/3` using the
`python_error(ClassName, Message)` pattern:

```python
catch(
    ++(Metre(3) + Second(2)),           # raises UnitsMismatch
    python_error("UnitsMismatch", MSG), # MSG bound to the error string
    1 == 1                              # recovery goal
)
```

The `python_error/2` term is the general form for any Python exception that
escapes through a `++()` escape — see [Exception Handling](exceptions.md) for
the full treatment.

If the catcher pattern does not match the raised exception, the exception is
re-raised and continues to propagate.

---

## Design notes

- **No offset scales**: `Celsius`/`Fahrenheit` are unsupported — they are
  offset (non-ratio) scales. Only ratio-scale units work correctly.
- **Integer-only exponents in `Pow`**: `area ** 0.5` raises `UnitsMismatch`.
- **Dimension keys are predicate objects**: the seven SI base unit predicates
  (`Metre`, `Kilogram`, etc.) are the keys in `dims`. Custom dimension keys
  are supported — any hashable Python value works.
- **`n(Unit)` limitation**: the unit argument must be a bare name — a named
  unit predicate visible in scope. Compound unit expressions
  (`Kilogram * Metre / Second**2`) cannot appear as the arg; use `++()` or
  a named predicate (`Newton`).
