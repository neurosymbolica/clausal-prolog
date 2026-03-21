# Physical Units

Dimensional analysis via `Quantity(value, dims)` terms, with full arithmetic,
named-unit predicates, and syntactic sugar for writing measurements inline.

---

## Quick start

```python
-import_from(py.units, [m, kg, s, Newton, HasUnits, StripUnits])

# Build a dimensioned value with n(Unit) sugar
distance := 100(m)              # Quantity(100, {Metre: 1})
time_    := 9.58(s)             # Quantity(9.58, {Second: 1})
speed    := distance / time_    # Quantity(10.4…, {Metre: 1, Second: -1})

# Check dimension type
HasUnits(speed, m/s)            # succeeds: dims match

# Extract numeric component
StripUnits(9.8(Newton), V)      # V = 9.8

# Constrain an unbound variable to a dimension
HasUnits(F, Newton),            # F must eventually be a Newton quantity
F is 9.8(Newton)                # binds F; hook checks dims match
```

---

## Syntactic sugar

### `n(Unit)` — literal measurement

```python
5(m)          # → Quantity(5,   {Metre: 1})
9.8(Newton)   # → Quantity(9.8, {Kilogram: 1, Metre: 1, Second: -2})
-3(s)         # → Quantity(-3,  {Second: 1})
```

Python parses `5(m)` as a call — the transformer intercepts it and rewrites it
to `++(Quantity(5, m))`. Any numeric literal combined with a unit predicate
works. Compound unit expressions also work:

```python
5(m/s)        # → Quantity(5,   {Metre: 1, Second: -1})
10(m**2)      # → Quantity(10,  {Metre: 2})
```

For unusual constructions, use `++()` directly:

```python
custom := ++(Kilogram(1) * Metre(1) / Second(1)**2 * 9.8)   # same as 9.8(Newton)
```

### `n()` — dimensionless literal

An empty-argument call on any numeric literal produces a dimensionless
`Quantity(n, {})`:

```python
42()      # → Quantity(42,   {})
3.14()    # → Quantity(3.14, {})
0()       # → Quantity(0,    {})
```

This is equivalent to `++(Quantity(n, {}))`. The value participates in unit
arithmetic — dividing two quantities of the same unit to get a ratio is a
common result:

```python
RATIO := 50(m) / 10(m)          # → Quantity(5.0, {})
HasUnits(RATIO, Dimensionless)   # succeeds
RATIO == 5.0()                   # succeeds
```

### `X(Unit)` — construction from a runtime value

When the callee is a logic variable, `MY_VAL(Unit)` desugars to
`++(Quantity(MY_VAL, Unit))`:

```python
N := 9.8
F := N(Newton)          # → ++(Quantity(N, Newton)) = Quantity(9.8, Newton dims)
```

This is the runtime-value counterpart of `9.8(Newton)` — same construction,
variable value. Compound unit expressions work too:

```python
SPEED := 10
V := SPEED(m/s)         # Quantity(10, {Metre: 1, Second: -1})
```

### `HasUnits(X, Unit)` — dimension constraint / check

For dimension checks and constraints (goal position), use `HasUnits` explicitly:

```python
HasUnits(F, Newton)              # check or constrain: F must have Newton dims
```

`HasUnits/2` posts an AttVar constraint on `F` if it is unbound: any subsequent
unification of `F` fires a hook that checks the bound value has matching
dimensions. The constraint backtracks correctly with the trail.

```python
# Constraint posted, then satisfied
HasUnits(F, Newton),
F is 9.8(Newton),       # hook checks dims match → OK
HasUnits(F, Newton)     # ground check: still succeeds

# Constraint posted, then violated → entire conjunction fails
HasUnits(F, Newton),
F is 1(s)               # hook rejects: Newton dims ≠ Second dims
```

Compound unit expressions work directly in `HasUnits` — the transformer
auto-wraps them:

```python
HasUnits(V, m/s)                      # velocity check/constraint
HasUnits(A, m/s**2)                   # acceleration
HasUnits(F, kg*m/s**2)               # force (same dims as Newton)
```

`HasUnits` cannot appear on the RHS of `:=` — that position expects an
expression.

---

## `Quantity` term

```python
from clausal.terms import Quantity, UnitsMismatch

d = Quantity(10.0, {Metre: 1, Second: -1})  # 10 m/s
d.value   # 10.0
d.dims    # MappingProxyType({<Metre>: 1, <Second>: -1})
```

`dims` returns an immutable `MappingProxyType` mapping unit-predicate objects
(not strings) to integer exponents. Zero exponents are removed on construction.
The empty proxy `{}` is dimensionless.

`Quantity` also accepts a unit predicate as its second argument — scale is
applied automatically:

```python
Quantity(5, Kilometre)   # → Quantity(5000.0, {Metre: 1})
Quantity(9.8, Newton)    # → Quantity(9.8, {Kilogram:1, Metre:1, Second:-2})
```

`Quantity` holds a ground numeric value — never a logic variable. An
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
-import_from(py.units, [m, kg, s, Newton, HasUnits, StripUnits])
```

### SI base unit abbreviations

The standard SI abbreviations are provided as importable aliases. Note that
`A` (Ampere) and `K` (Kelvin) are omitted because single uppercase letters are
parsed as logic variables in Clausal — use the full names instead.

| Alias | Full name  | Dims             | SI symbol |
|-------|------------|------------------|-----------|
| `m`   | `Metre`    | `{Metre: 1}`     | m         |
| `kg`  | `Kilogram` | `{Kilogram: 1}`  | kg        |
| `s`   | `Second`   | `{Second: 1}`    | s         |
| `mol` | `Mole`     | `{Mole: 1}`      | mol       |
| `cd`  | `Candela`  | `{Candela: 1}`   | cd        |
| —     | `Ampere`   | `{Ampere: 1}`    | A *(clash)* |
| —     | `Kelvin`   | `{Kelvin: 1}`    | K *(clash)* |

### Named-unit predicates

`Unit(value)` called from Python (via `++` escape or `n(Unit)` sugar) returns
`Quantity(value * scale, dims)` directly.

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

### Utility predicates

| Predicate                  | Description |
|----------------------------|-------------|
| `DimensionOf(D, Dims)`     | Unify `Dims` with a `DictTerm` of the dimension dict |
| `StripUnits(D, V)`         | Unify `V` with the numeric component |
| `MakeQuantity(V, Dims, D)` | Construct `Quantity` from value `V` and `DictTerm` dims |

`DimensionOf` also works on uninstantiated Vars with a dimension constraint —
it unifies `Dims` with the dims from the AttVar's `"units"` attribute.

### `HasUnits/2`

```python
HasUnits(D, UnitPred)
```

Explicit dimension check/constraint predicate. Succeeds if:

- `D` is a ground `Quantity` whose dims match `UnitPred._dims`, or
- `D` is an unbound Var — posts the `"units"` AttVar constraint and succeeds.

Fails if `D` is bound to something else (wrong dims, plain number with
non-empty dims, non-Quantity term).

### Physical constants

| Name                    | Value (SI)                     | Dims |
|-------------------------|--------------------------------|------|
| `SpeedOfLight`          | 2.998 × 10⁸ m/s               | `{m:1, s:-1}` |
| `PlanckConstant`        | 6.626 × 10⁻³⁴ J·s             | `{kg:1, m:2, s:-1}` |
| `BoltzmannConstant`     | 1.381 × 10⁻²³ J/K             | `{kg:1, m:2, s:-2, K:-1}` |
| `StandardGravity`       | 9.80665 m/s²                   | `{m:1, s:-2}` |
| `ElementaryCharge`      | 1.602 × 10⁻¹⁹ C               | `{A:1, s:1}` |
| `GravitationalConstant` | 6.674 × 10⁻¹¹ m³/(kg·s²)     | `{m:3, kg:-1, s:-2}` |

---

## Uninstantiated dimensioned slots (AttVar)

An uninstantiated slot that will eventually hold a measurement uses a plain
Var with a `"units"` AttVar constraint — **not** `Quantity(Var, dims)`.

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

---

## Program verification with `HasUnits`

### Runtime assertions as type checking

`HasUnits` goals are runtime assertions about dimensional types. They can be
thought of exactly like Python's `assert` statement: present during development
and testing, removable for production once correctness is established.

The intended workflow:

1. **Development**: annotate inputs, outputs, and intermediate values with
   `HasUnits` calls. Run tests. Any dimensional error is caught immediately with
   a precise failure point.
2. **Verification**: once the test suite passes with all assertions active, the
   program is known to satisfy its dimensional invariants on those execution
   paths.
3. **Production**: strip `HasUnits` goals from compiled code for zero overhead.

This is more expressive than adding `HasUnits` calls into running code manually;
the key insight is that the test suite *is* the type checker.

### Why this is more powerful than static type systems

Rice's theorem states that no static analysis can decide all semantic properties
of programs. Dimensional correctness is a semantic property — it depends on the
runtime values that flow through a program, not just on the syntactic structure.
A static type system can only approximate this, ruling out some errors but
necessarily rejecting some valid programs or missing some invalid ones.

Runtime assertions with toggleable checking sidestep this limitation:

- The assertions express the *exact* invariants the program must satisfy, with
  no approximation.
- They are checked on real execution paths with real values, including ones
  that arise only from CLP(FD) search, external input, or runtime arithmetic.
- They compose freely with all other Clausal constructs: negation-as-failure,
  `catch/3`, backtracking, constraint solving.

This is the same trade-off as design-by-contract (Eiffel, Python's `assert`,
Racket contracts): richer expressiveness in exchange for runtime rather than
compile-time guarantees.

### Compile-time checking

Runtime verification and static analysis are complementary, not mutually
exclusive. The information encoded in `HasUnits` calls is available at compile
time — the transformer sees the unit expressions as syntax. A future static
pass could:

- Infer `Quantity` types for variables bound by `:=`
- Propagate dimension information through arithmetic expressions
- Report `HasUnits` calls that are provably unreachable or provably always-failing
  before the program runs

Such a pass would catch a class of errors earlier without replacing the runtime
system, which remains the ground truth for correctness.

---

## Design notes

- **No offset scales**: `Celsius`/`Fahrenheit` are unsupported — they are
  offset (non-ratio) scales. Only ratio-scale units work correctly.
- **Integer-only exponents in `Pow`**: `area ** 0.5` raises `UnitsMismatch`.
- **Dimension keys are predicate objects**: the seven SI base unit predicates
  (`Metre`, `Kilogram`, etc.) are the keys in `dims`. Custom dimension keys
  are supported — any hashable Python value works.
- **`A` and `K` aliases omitted**: the standard SI symbols for Ampere and
  Kelvin are single uppercase letters, which Clausal parses as logic variables.
  Use `Ampere` and `Kelvin` (or import the full names).
