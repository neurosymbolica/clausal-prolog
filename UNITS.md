# Dimensional Analysis for Clausal

Physical-unit tracking via `Dimensioned(value, dims)` terms with full arithmetic
support and a library of named-unit predicates.

## Core term: `Dimensioned`

```python
from clausal import Dimensioned, UnitsMismatch

velocity = Dimensioned(10.0, {"m": 1, "s": -1})   # 10 m/s
mass     = Dimensioned(2.0,  {"kg": 1})             # 2 kg
```

`dims` is a `dict[str, int]` mapping SI base dimension keys to integer exponents.
Zero exponents are always removed. The empty dict `{}` means dimensionless.

### SI base dimension keys

| Key   | Quantity               |
|-------|------------------------|
| `m`   | length (metre)         |
| `kg`  | mass (kilogram)        |
| `s`   | time (second)          |
| `A`   | electric current       |
| `K`   | temperature (Kelvin)   |
| `mol` | amount of substance    |
| `cd`  | luminous intensity     |

All values are stored in these base units internally. Named-unit predicates
(e.g. `Kilometer`, `Hour`) scale on input and output — they do **not** add
new dimension keys.

### Arithmetic

| Operation | Behaviour |
|-----------|-----------|
| `a + b`   | Requires identical dims; raises `UnitsMismatch` otherwise |
| `a - b`   | Same as addition |
| `a * b`   | Merges dims by addition (exponents add) |
| `a / b`   | Merges dims by subtraction (exponents subtract) |
| `a ** n`  | Multiplies all exponents by integer `n`; raises `UnitsMismatch` for non-integer `n` |
| `-a`      | Negates value; preserves dims |
| `abs(a)`  | Absolute value; preserves dims |
| `a * scalar` | Scales value; preserves dims |
| `scalar / a` | Inverts dims and scales |

Mixed Dimensioned + plain-number arithmetic is allowed for dimensionless
quantities (`dims == {}`).

### Comparisons

`<`, `<=`, `>`, `>=` require identical dims; raise `UnitsMismatch` otherwise.

### Clausal unification

`Dimensioned` participates in Clausal's unification protocol:

- `__unify__`: dims must match exactly; values are unified recursively.
- `__walk__`: walks the value (follows Var bindings), preserves dims.
- `__occurs_check__`: checks for a Var in the value.

This means you can write:

```clausal
foo(Dimensioned(X, {'m': 1})) <- ...   % X is a free variable in the value slot
```

and unification will bind `X` to the numeric component.

## Module: `clausal.modules.py.units`

Import in `.clausal` files:

```clausal
-import_from(py.units, [Meter, Newton, Watt, IsForce, IsEnergy, ValueOf]).
```

Or from Python:

```python
from clausal.modules.py.units import Meter, Newton, IsForce
from clausal.logic.solve import _drive_trampoline
from clausal.logic.variables import Trail, Var, deref

trail = Trail()
d_var = Var()
for _ in _drive_trampoline(Newton._get_dispatch(), trail, 9.8, d_var):
    print(deref(d_var))   # Dimensioned(9.8, {'kg': 1, 'm': 1, 's': -2})
```

### Named-unit predicates (arity 2)

`UnitName(Number, Dimensioned)` — bidirectional:
- **Forward**: given `Number`, unify `Dimensioned` with `Dimensioned(Number * scale, dims)`.
- **Reverse**: given `Dimensioned` with matching dims, unify `Number` with `value / scale`.

#### SI base units

| Predicate   | Dims                    | Scale |
|-------------|-------------------------|-------|
| `Meter`     | `{m: 1}`                | 1     |
| `Kilogram`  | `{kg: 1}`               | 1     |
| `Second`    | `{s: 1}`                | 1     |
| `Ampere`    | `{A: 1}`                | 1     |
| `Kelvin`    | `{K: 1}`                | 1     |
| `Mole`      | `{mol: 1}`              | 1     |
| `Candela`   | `{cd: 1}`               | 1     |

#### Scaled length (all store as metres)

`Kilometer`, `Centimeter`, `Millimeter`, `Micrometer`, `Nanometer`,
`Inch`, `Foot`, `Yard`, `Mile`, `NauticalMile`, `LightYear`, `AstronomicalUnit`

#### Scaled mass (all store as kilograms)

`Gram`, `Milligram`, `Microgram`, `Tonne`, `Pound`, `Ounce`

#### Scaled time (all store as seconds)

`Millisecond`, `Microsecond`, `Nanosecond`, `Minute`, `Hour`, `Day`, `Week`, `JulianYear`

#### Named derived SI units

| Predicate     | Quantity              | Dims (SI base)                           |
|---------------|-----------------------|------------------------------------------|
| `Newton`      | force                 | `{kg:1, m:1, s:-2}`                     |
| `Joule`       | energy                | `{kg:1, m:2, s:-2}`                     |
| `Watt`        | power                 | `{kg:1, m:2, s:-3}`                     |
| `Pascal`      | pressure              | `{kg:1, m:-1, s:-2}`                    |
| `Hertz`       | frequency             | `{s:-1}`                                 |
| `Volt`        | voltage               | `{kg:1, m:2, s:-3, A:-1}`               |
| `Coulomb`     | charge                | `{A:1, s:1}`                             |
| `Farad`       | capacitance           | `{kg:-1, m:-2, s:4, A:2}`               |
| `Ohm`         | resistance            | `{kg:1, m:2, s:-3, A:-2}`               |
| `Siemens`     | conductance           | `{kg:-1, m:-2, s:3, A:2}`               |
| `Weber`       | magnetic flux         | `{kg:1, m:2, s:-2, A:-1}`               |
| `Tesla`       | magnetic flux density | `{kg:1, s:-2, A:-1}`                    |
| `Henry`       | inductance            | `{kg:1, m:2, s:-2, A:-2}`               |
| `Lumen`       | luminous flux         | `{cd:1}`                                 |
| `Lux`         | illuminance           | `{cd:1, m:-2}`                           |
| `Katal`       | catalytic activity    | `{mol:1, s:-1}`                          |
| `Gray`        | absorbed dose         | `{m:2, s:-2}`                            |
| `Sievert`     | dose equivalent       | `{m:2, s:-2}`                            |

Scaled variants: `Bar`, `Millibar`, `Atmosphere`, `PoundsPerSquareInch`,
`Electronvolt`, `Calorie`, `Kilocalorie`, `KilowattHour`,
`Kilowatt`, `Horsepower`,
`KilometerPerHour`, `MilePerHour`, `Knot`

### Dimension-check predicates (arity 1)

`IsXxx(Dimensioned)` — succeed iff the argument is a `Dimensioned` with the
exact expected dimension dict.

`IsLength`, `IsArea`, `IsVolume`, `IsMass`, `IsTime`, `IsFrequency`,
`IsVelocity`, `IsAcceleration`, `IsForce`, `IsEnergy`, `IsPower`, `IsPressure`,
`IsElectricCurrent`, `IsVoltage`, `IsCharge`, `IsResistance`, `IsCapacitance`,
`IsInductance`, `IsMagneticFlux`, `IsMagneticFluxDensity`, `IsTemperature`,
`IsAmountOfSubstance`, `IsLuminousIntensity`, `IsIlluminance`,
`IsDimensionless`, `IsDimensioned`

`IsDimensionless` also succeeds for plain Python ints/floats.

### Utility predicates

| Predicate                       | Description |
|---------------------------------|-------------|
| `DimensionOf(D, Dims)`          | Unify `Dims` with a `DictTerm` of the dimension dict |
| `ValueOf(D, V)`                 | Unify `V` with the numeric component |
| `StripDimensions(D, V)`         | Alias for `ValueOf` |
| `MakeDimensioned(V, Dims, D)`   | Construct `Dimensioned` from value `V` and `DictTerm` dims |

## Design constraints

- **Dumb implementation**: `Celsius`/`Fahrenheit` are deliberately unsupported —
  they are offset (non-ratio) scales. Only ratio-scale units work correctly.
- **No Kelvin ↔ Celsius conversion**: `Kelvin` stores temperature as-is in `K`.
- **Integer-only exponents in `Pow`**: `area ** 0.5` raises `UnitsMismatch`.
  `(area ** 0.5).dims` is undefined because the exponents would be fractional.
- **Dimension keys are arbitrary atoms**: any hashable Python value works as a key,
  not just the 7 SI base dimensions. Custom domain dimensions (e.g. `"pixel"`,
  `"dollar"`) are fully supported.
- **CLP(FD) compatibility**: `Dimensioned` wraps its value, so a `Dimensioned`
  with an `FDVar` value participates in CLP(FD) through Python's arithmetic
  protocol. Full constraint propagation across the dims boundary requires
  further work.
