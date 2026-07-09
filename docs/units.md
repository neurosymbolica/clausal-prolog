# Physical Units

Dimensional analysis via `Quantity(value, dims)` terms, with full arithmetic,
named-unit predicates, SI prefix constants, imperial unit vectors, and
syntactic sugar for writing measurements inline.

---

## Quick start

```python
-import_from(py.units,    [m, kg, s, Newton, kilo, has_units, strip_units])
-import_from(py.imperial, [foot, inch, pound_mass, mph])

# SI sugar: n(Unit) — Unit must be an SI predicate
distance := 100(m)              # Quantity(100, {Metre: 1})
_time    := 9.58(s)             # Quantity(9.58, {Second: 1})
speed    := distance / _time    # Quantity(10.4…, {Metre: 1, Second: -1})

# SI prefix: plain number, multiply in ++ escape
big_force := ++(5 * kilo * Newton(1))   # 5 kN → Quantity(5000, {kg:1, m:1, s:-2})

# Imperial: unit-vector Quantity, multiply in ++ escape
height := ++(6 * foot + 2 * inch)       # Quantity(1.879…, {Metre: 1})

# Check dimension type
has_units(speed, m/s)            # succeeds: dims match

# Extract numeric component
strip_units(9.8(Newton), V)      # V = 9.8
```

---

## Two syntactic styles

### `n(Unit)` sugar — SI predicates only

```python
5(m)          # → Quantity(5,   {Metre: 1})
9.8(Newton)   # → Quantity(9.8, {Kilogram: 1, Metre: 1, Second: -2})
-3(s)         # → Quantity(-3,  {Second: 1})
5(m/s)        # → Quantity(5,   {Metre: 1, Second: -1})
10(m**2)      # → Quantity(10,  {Metre: 2})
```

**The argument inside the parentheses must be an SI unit predicate** (or a
compound expression built from SI unit predicates using `*`, `/`, `**`).
Imperial and other scaled-unit **Quantity** values (`inch`, `foot`, `Byte`, …)
also work — `5(inch)` is `5 * inch` — because a `Quantity` is callable and
scales itself. SI prefix names (`kilo`, `milli`, …) are plain numbers, not
units; `5(kilo)` raises a `TypeError` ("SI prefixes cannot be used as units").
Multiply a prefix in instead: `++(5 * kilo * m(1))` — call the unit as `m(1)`
to get a multipliable `Quantity`; the bare predicate `m` cannot appear on the
right of `*` (`5 * kilo * m` raises a `TypeError`).

For unusual constructions, use `++()` directly:

```python
custom := ++(Kilogram(1) * Metre(1) / Second(1)**2 * 9.8)   # same as 9.8(Newton)
```

### `* unit` style — SI prefixes and imperial

SI prefixes are plain numbers; imperial/non-SI units are `Quantity` unit
vectors.  Both are used via multiplication inside a `++()` escape:

```python
F   := ++(5 * kilo * Newton(1))        # 5 kN
t   := ++(100 * nano * Second(1))      # 100 ns
f   := ++(2.4 * mega * Hertz(1))       # 2.4 GHz
len := ++(20 * inch)                   # 20 inches → 0.508 m
spd := ++(60 * mph)                    # 60 mph → 26.82 m/s
```

---

## `n()` — dimensionless literal

An empty-argument call on any numeric literal produces a dimensionless
`Quantity(n, {})`:

```python
42()      # → Quantity(42,   {})
3.14()    # → Quantity(3.14, {})
```

---

## `X(Unit)` — construction from a runtime value

when the callee is a logic variable, `MY_VAL(Unit)` desugars to
`++(Quantity(MY_VAL, Unit))`:

```python
N == 9.8
F := N(Newton)          # → Quantity(9.8, Newton dims)
```

---

## `has_units(X, Unit)` — dimension constraint / check

```python
has_units(F, Newton)              # check or constrain: F must have Newton dims
has_units(V, m/s)                 # velocity check/constraint
has_units(A, m/s**2)              # acceleration
```

`has_units/2` posts an AttVar constraint on `F` if it is unbound. Compound unit
expressions work directly — the transformer auto-wraps them.

`has_units` cannot appear on the RHS of `:=` or `==`.

---

## `Quantity` term

```python
from clausal.terms import Quantity, UnitsMismatch

d = Quantity(10.0, {Metre: 1, Second: -1})  # 10 m/s
d.value   # 10.0
d.dims    # MappingProxyType({<Metre>: 1, <Second>: -1})
```

### Arithmetic

| Operation  | Behaviour |
|------------|-----------|
| `a + b`    | Requires identical dims; raises `UnitsMismatch` otherwise |
| `a - b`    | Same as addition |
| `a * b`    | Merges dims by addition (exponents add) |
| `a / b`    | Merges dims by subtraction (exponents subtract) |
| `a ** n`   | Multiplies all exponents by integer `n` |
| `-a`       | Negates value; preserves dims |
| `abs(a)`   | Absolute value; preserves dims |
| `a * k`    | Scales value by plain number; preserves dims |
| `k / a`    | Inverts dims and scales |

---

## Modules

### `py.units` — SI units and prefixes

```python
-import_from(py.units, [m, kg, s, Newton, kilo, has_units, strip_units])
```

Contains: SI base unit predicates, scaled SI unit predicates, named derived SI
unit predicates, SI prefix constants, IEC binary prefix constants, SI
abbreviations, SI unit vectors, digital information units, physical constants,
and utility predicates (`has_units`, `strip_units`, `dimension_of`, `make_quantity`).

### `py.imperial` — imperial and non-SI unit vectors

```python
-import_from(py.imperial, [inch, foot, yard, mile, pound_mass, mph, lbf])
```

Contains: imperial and non-SI `Quantity` unit vectors for length, mass, force,
volume, pressure, energy, power, speed, and temperature differences.  All
values are stored in SI base units; `has_units` checks work without changes.

---

### SI base unit predicates

Used with `n(Unit)` sugar.

| Alias | Full name  | Dims             | SI symbol |
|-------|------------|------------------|-----------|
| `m`   | `Metre`    | `{Metre: 1}`     | m         |
| `kg`  | `Kilogram` | `{Kilogram: 1}`  | kg        |
| `s`   | `Second`   | `{Second: 1}`    | s         |
| `mol` | `Mole`     | `{Mole: 1}`      | mol       |
| `cd`  | `Candela`  | `{Candela: 1}`   | cd        |
| —     | `Ampere`   | `{Ampere: 1}`    | A *(clash)* |
| —     | `Kelvin`   | `{Kelvin: 1}`    | K *(clash)* |

`A` and `K` are omitted as aliases — single uppercase letters are logic
variables in Clausal.

**Digital information base unit** (IEC 80000-13):

| Alias | Full name | Dims        | IEC symbol |
|-------|-----------|-------------|------------|
| —     | `Bit`     | `{Bit: 1}`  | bit        |

`Bit` uses itself as the dimension key, exactly like the SI base units.

---

### Scaled SI unit predicates

These scale on the way in and store as SI base units.  Use with `n(Unit)` sugar.

#### length (stored as metres)

`Kilometer` (`km`), `Centimeter` (`cm`), `Millimeter` (`mm`),
`Micrometer` (`um`), `Nanometer` (`nm`)

#### Mass (stored as kilograms)

`Gram` (`mg` for milli, `ug` for micro), `Milligram`, `Microgram`, `Tonne`

#### Time (stored as seconds)

`Millisecond` (`ms`), `Microsecond` (`us`), `Nanosecond` (`ns`),
`Minute` (`min`), `Hour` (`hr`), `Day`, `Week`, `JulianYear`

#### Digital information (stored as bits)

`Bit` is the base unit (IEC 80000-13).  All values are normalised to bits.

```python
-import_from(py.units, [Bit, Byte, Kilobyte, Gigabyte, Kibibyte, Gibibyte,
                        Kilobit, Megabit, kibi, mebi, gibi, tebi])

size   := 4(Gibibyte)                    # Quantity(34_359_738_368, {Bit: 1})
rate   := 100(Megabit)                   # Quantity(100_000_000,    {Bit: 1})
custom := ++(512 * mebi * Byte(1))       # 512 MiB via binary prefix
```

Decimal (SI-prefixed) byte multiples:

| Predicate   | Stored as bits | Alias |
|-------------|----------------|-------|
| `Byte`      | 8              | —     |
| `Kilobyte`  | 8 × 10³        | —     |
| `Megabyte`  | 8 × 10⁶        | —     |
| `Gigabyte`  | 8 × 10⁹        | —     |
| `Terabyte`  | 8 × 10¹²       | —     |

Decimal bit multiples:

| Predicate   | Stored as bits |
|-------------|----------------|
| `Kilobit`   | 10³            |
| `Megabit`   | 10⁶            |
| `Gigabit`   | 10⁹            |

Binary (IEC-prefixed) byte multiples:

| Predicate   | Stored as bits  |
|-------------|-----------------|
| `Kibibyte`  | 8 × 2¹⁰         |
| `Mebibyte`  | 8 × 2²⁰         |
| `Gibibyte`  | 8 × 2³⁰         |
| `Tebibyte`  | 8 × 2⁴⁰         |

Binary bit multiples:

| Predicate   | Stored as bits |
|-------------|----------------|
| `Kibibit`   | 2¹⁰            |
| `Mebibit`   | 2²⁰            |
| `Gibibit`   | 2³⁰            |

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

Scaled variants: `Bar`, `Millibar`, `Atmosphere`, `Electronvolt`, `Kilowatt`

---

### SI prefix constants

Plain Python numbers — **not** predicates.  Use inside `++()` by multiplying
against a unit vector:

```python
++(5 * kilo * Newton(1))      # 5 kN
++(100 * nano * Second(1))    # 100 ns
++(2.4 * giga * Hertz(1))     # 2.4 GHz
++(1 * mega * Joule(1))       # 1 MJ
```

| Name    | Value  | SI symbol | Note |
|---------|--------|-----------|------|
| `yotta` | 1e24   | Y *(clash)* | uppercase = logic var |
| `zetta` | 1e21   | Z *(clash)* | |
| `exa`   | 1e18   | E *(clash)* | |
| `peta`  | 1e15   | P *(clash)* | |
| `tera`  | 1e12   | T *(clash)* | |
| `giga`  | 1e9    | G *(clash)* | |
| `mega`  | 1e6    | M *(clash)* | |
| `kilo`  | 1e3    | k → `k`   | |
| `hecto` | 1e2    | h → `h`   | |
| `deca`  | 1e1    | da → `da` | |
| `deci`  | 1e-1   | d → `d`   | |
| `centi` | 1e-2   | c → `c`   | |
| `milli` | 1e-3   | m *(clash with Metre alias)* | use `milli` |
| `micro` | 1e-6   | μ *(not a valid identifier)* | use `micro` |
| `nano`  | 1e-9   | n → `n`   | |
| `pico`  | 1e-12  | p → `p`   | |
| `femto` | 1e-15  | f → `f`   | |
| `atto`  | 1e-18  | a → `a`   | |
| `zepto` | 1e-21  | z → `z`   | *(rarely needed)* |
| `yocto` | 1e-24  | y → `y`   | *(rarely needed)* |

Single-letter abbreviations (`k`, `h`, `da`, `d`, `c`, `n`, `p`, `f`, `a`)
are available but must be imported explicitly.

`milli` has no safe single-letter alias: `m` is already the Metre predicate.
`micro` has no safe alias: `μ` is not a valid Python identifier.  The
per-unit abbreviations `ms`, `mg`, `mm`, `us`, `um` encode both prefix and
unit together.

#### IEC binary prefix constants

Plain Python numbers — use inside `++()` by multiplying against a unit vector:

```python
++(4   * gibi * Byte(1))    # 4 GiB  →  Quantity(4 × 2³⁰ × 8, {Bit: 1})
++(512 * mebi * Byte(1))    # 512 MiB
++(100 * kibi * Bit(1))     # 100 Kib
```

| Name   | Value  | IEC symbol |
|--------|--------|------------|
| `kibi` | 2¹⁰    | Ki         |
| `mebi` | 2²⁰    | Mi         |
| `gibi` | 2³⁰    | Gi         |
| `tebi` | 2⁴⁰    | Ti         |
| `pebi` | 2⁵⁰    | Pi         |
| `exbi` | 2⁶⁰    | Ei         |

The IEC symbol abbreviations (`Ki`, `Mi`, `Gi`, …) start with an uppercase
letter and are not provided as aliases — in Clausal an identifier starting with
an uppercase letter is a logic variable.

---

### Imperial and non-SI unit vectors  (`py.imperial`)

Plain `Quantity` values — **not** predicates.  Import from `py.imperial` and
use by multiplying a scalar inside a `++()` escape:

```python
-import_from(py.imperial, [inch, foot, pound_mass, mph, kilowatt_hour])

LEN  := ++(20 * inch)           # Quantity(0.508,   {Metre: 1})
MASS := ++(150 * pound_mass)    # Quantity(68.04,   {Kilogram: 1})
SPD  := ++(60 * mph)            # Quantity(26.82,   {Metre:1, Second:-1})
E    := ++(1 * kilowatt_hour)   # Quantity(3.6e6,   {kg:1, m:2, s:-2})
```

All values are stored in SI base units; dimensions are the same as their SI
equivalents so `has_units` checks work without any changes:

```python
has_units(++(20 * inch), Metre)     # succeeds — both have {Metre: 1}
```

#### length (stored as metres)

| Name               | Value (m)       | Abbrev |
|--------------------|-----------------|--------|
| `inch`             | 0.0254          | —      |
| `foot`             | 0.3048          | `ft`   |
| `yard`             | 0.9144          | `yd`   |
| `mile`             | 1 609.344       | `mi`   |
| `nautical_mile`    | 1 852.0         | `nmi`  |
| `light_year`       | 9.461 × 10¹⁵   | `ly`   |
| `astronomical_unit`| 1.496 × 10¹¹   | `au`   |

#### Mass (stored as kilograms)

| Name          | Value (kg)      | Abbrev |
|---------------|-----------------|--------|
| `pound_mass`  | 0.453 592 37    | `lb`, `lbm` |
| `ounce_mass`  | 0.028 349 52    | `oz`   |
| `stone`       | 6.350 293 18    | —      |
| `short_ton`   | 907.184 74      | —      |
| `long_ton`    | 1 016.046 909   | —      |

#### Force (stored as Newtons = kg·m/s²)

| Name          | Value (N)       | Abbrev |
|---------------|-----------------|--------|
| `pound_force` | 4.448 221 615   | `lbf`  |

#### Volume (stored as cubic metres)

| Name             | Value (m³)      | Abbrev |
|------------------|-----------------|--------|
| `litre`          | 1 × 10⁻³        | `l`    |
| `millilitre`     | 1 × 10⁻⁶        | `ml`   |
| `gallon_us`      | 3.785 × 10⁻³    | —      |
| `quart_us`       | 9.464 × 10⁻⁴    | —      |
| `pint_us`        | 4.732 × 10⁻⁴    | —      |
| `fluid_ounce_us` | 2.957 × 10⁻⁵    | —      |
| `gallon_uk`      | 4.546 × 10⁻³    | —      |
| `pint_uk`        | 5.683 × 10⁻⁴    | —      |
| `fluid_ounce_uk` | 2.841 × 10⁻⁵    | —      |

#### Pressure (stored as Pascals = kg/(m·s²))

| Name  | Value (Pa)  | Abbrev |
|-------|-------------|--------|
| `psi` | 6 894.757   | —      |

#### Energy (stored as Joules = kg·m²/s²)

| Name           | Value (J)       | Abbrev |
|----------------|-----------------|--------|
| `calorie`      | 4.184           | —      |
| `kilocalorie`  | 4 184.0         | —      |
| `btu`          | 1 055.056       | —      |
| `kilowatt_hour`| 3 600 000.0     | —      |

#### Power (stored as Watts = kg·m²/s³)

| Name         | Value (W)  | Abbrev |
|--------------|------------|--------|
| `horsepower` | 745.699 87 | —      |

#### Speed (stored as m/s)

| Name    | Value (m/s)          | Abbrev |
|---------|----------------------|--------|
| `mph`   | 0.447 04             | —      |
| `kph`   | 0.277 7̄              | —      |
| `knot`  | 0.514 4̄              | —      |

#### Temperature differences (stored as Kelvin — ratio scale only)

| Name      | Value (K)  |
|-----------|------------|
| `rankine` | 5/9        |

Absolute offset scales (Celsius, Fahrenheit) are unsupported — they are not
ratio scales.

---

### Utility predicates

| Predicate                  | Description |
|----------------------------|-------------|
| `dimension_of(D, Dims)`     | Unify `Dims` with a `DictTerm` of the dimension dict |
| `strip_units(D, V)`         | Unify `V` with the numeric component |
| `make_quantity(V, Dims, D)` | Construct `Quantity` from value `V` and `DictTerm` dims |

### `has_units/2`

```python
has_units(D, UnitPred)
```

Explicit dimension check/constraint predicate. Succeeds if `D` is a ground
`Quantity` whose dims match `UnitPred._dims`, or if `D` is an unbound Var
(posts an AttVar constraint).

### Physical constants

| Name                    | Value (SI)                     | Dims |
|-------------------------|--------------------------------|------|
| `SpeedOfLight`          | 2.998 × 10⁸ m/s               | `{m:1, s:-1}` |
| `PlanckConstant`        | 6.626 × 10⁻³⁴ J·s             | `{kg:1, m:2, s:-1}` |
| `BoltzmannConstant`     | 1.381 × 10⁻²³ J/K             | `{kg:1, m:2, s:-2, K:-1}` |
| `StandardGravity`       | 9.806 65 m/s²                  | `{m:1, s:-2}` |
| `ElementaryCharge`      | 1.602 × 10⁻¹⁹ C               | `{A:1, s:1}` |
| `GravitationalConstant` | 6.674 × 10⁻¹¹ m³/(kg·s²)     | `{m:3, kg:-1, s:-2}` |

---

## Uninstantiated dimensioned slots (AttVar)

An uninstantiated slot that will eventually hold a measurement uses a plain
Var with a `"units"` AttVar constraint — **not** `Quantity(Var, dims)`.

```python
from clausal.logic.variables import Var, Trail
from clausal.logic.units_constraint import constrain_var_dims
from clausal.modules.py.units import Newton

trail = Trail()
v = Var()
constrain_var_dims(v, Newton._dims, trail)  # post constraint
from clausal.logic.variables import unify
unify(v, Newton(9.8), trail)   # fires hook → checks dims → binds v
```

---

## Catching unit errors

`UnitsMismatch` is catchable via [`catch/3`](exceptions.md) using the `ClassName(Message)` form:

```python
catch(
    ++(Metre(3) + Second(2)),
    UnitsMismatch(MSG),
    1 == 1
)
```

---

## Program verification with `has_units`

`has_units` goals are runtime assertions about dimensional types.  They compose
freely with all Clausal constructs: [negation-as-failure](control.md), [`catch/3`](exceptions.md),
backtracking, [constraint solving](constraints.md).

The intended workflow:

1. **Development**: annotate inputs and outputs with `has_units` calls.
2. **Verification**: once tests pass with assertions active, dimensional
   invariants are confirmed on those paths.
3. **Production**: strip `has_units` goals for zero overhead.

---

## Dimensional analysis with SciPy predicates

SciPy wrapper predicates are quantity-aware: when `Quantity` inputs are
passed, units are stripped before calling SciPy, and the result is re-wrapped
with correctly propagated dimensions.  when plain inputs are passed, SciPy is
called directly with zero overhead.

Each SciPy predicate falls into one of four categories (see individual module docs for details: [scipy.linalg](scipy_linalg.md), [scipy.special](scipy_special.md), [scipy.fft](scipy_fft.md), [scipy.differentiate](scipy_differentiate.md), [scipy.integrate](scipy_integrate.md), [scipy.interpolate](scipy_interpolate.md)):

| Category | Behaviour | Examples |
|---|---|---|
| **Require dimensionless** | Raises `UnitsMismatch` if any input has non-empty dims | `scipy_special` (Gamma, Erf, Bessel, ...) |
| **Pass-through** | Output dims = input dims | `scipy_fft` (FFT, IFFT, ...) |
| **Algebraic propagation** | Output dims computed from input dims by a fixed rule | `scipy_linalg` (Solve, Norm, Det, ...), `scipy_differentiate` (Derivative, Jacobian, Hessian) |
| **Intrinsically dimensionless** | Inputs stripped, output is always plain | `scipy_stats` test statistics, `scipy_cluster` labels |

### Modules with quantity support

| Module | Status | Notes |
|---|---|---|
| `scipy_linalg` | Supported | Full algebraic propagation for all predicates |
| `scipy_special` | Supported | Requires dimensionless inputs |
| `scipy_fft` | Supported | Pass-through (output dims = input dims) |
| `scipy_differentiate` | Supported | `df` dims = `f_dims - x_dims`; callable probing detects `f` output dims |
| `scipy_integrate` | Supported | Array quadrature: `y_dims + x_dims`; callable quadrature: probes `f`, `f_dims + x_dims` |
| `scipy_interpolate` | Supported | Dims stored in handle; eval/integral/derivative propagate algebraically |

See each module's documentation for details.

---

## Design notes

- **No offset scales**: `Celsius`/`Fahrenheit` are unsupported.
- **Integer-only exponents in `Pow`**: `area ** 0.5` raises `UnitsMismatch`.
- **Dimension keys are predicate objects**: the seven SI base unit predicates
  are the keys in `dims`.
- **`A` and `K` aliases omitted**: single uppercase letters are logic
  variables in Clausal.
- **SI prefixes are plain numbers**: `kilo = 1e3`, `milli = 1e-3`, etc.
  They cannot appear inside `n(Unit)` parentheses; use multiplication in
  a `++()` escape instead.
- **IEC binary prefixes are plain numbers**: `kibi = 2¹⁰`, `mebi = 2²⁰`, etc.
  Same rules as SI prefixes — multiply against a unit vector in `++()`.
- **`Bit` is the information base unit** (IEC 80000-13): all byte and
  prefixed-bit predicates store internally in bits, so arithmetic between them
  works without conversion.
- **Imperial units are Quantity unit vectors**: `inch`, `foot`, `pound_mass`,
  etc.  Multiply by a scalar in a `++()` escape.  `has_units` checks work
  normally since the dimensions are identical to their SI equivalents.

---

*See also: [Arithmetic](arithmetic.md) — numeric operations in Clausal · [Python Interop](python_integration.md) — `++()` escape for direct Pint operations.*
