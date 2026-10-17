# Physical Units

Dimensional analysis via `Quantity(value, dims)` terms, with full arithmetic,
named-unit predicates, SI prefix constants, imperial unit vectors, and, in
the seam, syntactic sugar for writing measurements inline.

!!! note "Clausal Prolog and the seam"

    Examples on this page are [Clausal Prolog](clausal_prolog.md)
    (`.clausal`, ISO Prolog syntax) where it has a spelling, and are marked
    *seam* where only the [seam](syntax.md) does. In Clausal Prolog a
    quantity comes **only** from a units declaration,
    `:- constant_number_units(Name, Number, Unit).`, read in a clause as
    `constant(Name)` (see [Directives](directives.md#-constant_number_units));
    the unit names come from `:- use_module(library(units), [...])` and
    `library(imperial)`. `5 * m` is the ordinary term `'*'(5, m)`. The seam
    also writes a measurement inline, `100(m)`, and computes in `++()`
    escapes; neither exists in Clausal Prolog.

---

## Quick start

```clausal
:- use_module(library(units), [m, s, newton, has_units/2, strip_units/2]).
:- use_module(library(imperial), [foot, inch]).

:- constant_number_units(distance, 100, m).        % 100 (metre)
:- constant_number_units(time, 9.58, s).           % 9.58 (second)
:- constant_number_units(one_newton, 1, newton).
:- constant_number_units(metre_per_second, 1, m/s).
:- constant_number_units(six_feet, 6, foot).
:- constant_number_units(two_inches, 2, inch).

% Arithmetic on quantities: 10.438... (metre / second)
speed(V) :-
    V is constant(distance) / constant(time).

% Scale a unit quantity: 5000 (kilogram * metre / second ** 2)
big_force(F) :-
    F is 5000 * constant(one_newton).

% Imperial: 1.8796... (metre)
height(H) :-
    H is constant(six_feet) + constant(two_inches).

% Check a dimension, against a quantity of that dimension
is_speed(V) :-
    has_units(V, constant(metre_per_second)).

% Extract the numeric component: V = 9.8
force_value(V) :-
    F is 9.8 * constant(one_newton),
    strip_units(F, V).

test("speed") :-
    speed(V),
    is_speed(V),
    strip_units(V, X),
    X > 10.438,
    X < 10.439.

test("big force") :-
    big_force(F),
    strip_units(F, X),
    X == 5000.

test("height") :-
    height(H),
    strip_units(H, X),
    X > 1.8795,
    X < 1.8797.

test("force value") :-
    force_value(V),
    V == 9.8.
```

The seam writes the same program with its inline sugar and `++()` escapes,
and runs it from Python with a goal-position `--` (seam syntax):

```seam
-import_from(py.units,    [m, s, newton, kilo, has_units, strip_units])
-import_from(py.imperial, [foot, inch])

# SI sugar: n(Unit), where Unit is an SI unit predicate
speed(V) <- (
    eval_(100(m), D),          # 100 (metre)
    eval_(9.58(s), T),         # 9.58 (second)
    eval_(D / T, V)            # 10.438... (metre / second)
)

# SI prefix: a plain number, multiplied in a ++ escape
big_force(F) <- (F is ++(5 * kilo * newton(1)))   # 5000 (kilogram * metre / second ** 2)

# Imperial: a unit-vector Quantity, multiplied in a ++ escape
height(H) <- (H is ++(6 * foot + 2 * inch))       # 1.8796... (metre)

# Check a dimension
is_speed(V) <- has_units(V, m/s)

# Extract the numeric component
force_value(V) <- strip_units(9.8(newton), V)     # V = 9.8

def main():
    for V in --speed(V):
        print(V)                           # 10.438413361169102 (metre / second)
    for V in --(speed(V), is_speed(V)):
        print("a speed:", V)
```

`main` runs the queries from Python with a goal-position `--`; call it once the file has
loaded (a query at module top level runs before the predicates are registered).

---

## Naming

Unit names are lowercase identifiers — `metre`, `kilogram`, `newton`,
`kilometre`, `byte` — like the currency names (`euro`) and the symbol forms
(`m`, `kg`, `s`).  Multi-word names use an underscore (`julian_year`), and
the physical constants are snake_case (`speed_of_light`, `planck_constant`).
The length family is spelled like `metre` throughout: `kilometre`,
`centimetre`, `millimetre`, `micrometre`, `nanometre`.  The printed label of
a `Quantity` follows the identifier: `str(5(metre))` is `5 (metre)`, and
`9.8(newton)` prints in base units as `9.8 (kilogram * metre / second ** 2)`
(a scaled unit such as `kilometre` has no label of its own — `5(kilometre)`
prints as `5000 (metre)`).

The spellings these replaced — TitleCase `Metre`, `Second`, `Newton`,
`SpeedOfLight`, … and the American `kilometer`, `centimeter`, … — are
deprecated aliases.  They still resolve — the seam's `-import_from(py.units, [Metre])`
imports `metre` under the old name, and `units.Metre` in Python returns
`units.metre` — but each warns with a `ClausalDeprecatedSpellingWarning`:
once per file from the `-import_from` list (naming every rename in it), once
per process per name from Python attribute access.  Rename `Metre` -> `metre`,
`kilometer` -> `kilometre`, `SpeedOfLight` -> `speed_of_light`; the old
spellings will be removed in a future release.

**Printed labels changed with the rename, and there is no alias for a
label.** A `Quantity` prints its dimension keys by their unit name, so text
that came out of `write/1`, `str()`, a `UnitsMismatch` message or the
predicate `repr` changed spelling in the same release — before:
`9.8 Kilogram·Metre·Second^-2`, `Unit mismatch for add: Metre vs Second`,
`units.Metre/[]`; after (today's format): `9.8 (kilogram * metre / second ** 2)`,
`Unit mismatch for add: metre vs second`, `units.metre/[]`. Anything that
parses or compares those strings must expect the lowercase form; the values,
dimension keys and arithmetic are unchanged.

---

## Writing a measurement

### In Clausal Prolog: a units declaration

A quantity is a units constant: `:- constant_number_units(Name, Number,
Unit).` declares it, and `constant(Name)` stands for it in a clause (it is
replaced at compile time). `Unit` is a unit name or an expression of them
with `*`, `/` and `**` (`m/s`, `m**2`); a scaled unit stores in base units.
A value known only at run time is scaled from a unit quantity, `F is N *
constant(one_newton)`:

```clausal
:- use_module(library(units), [m, s, newton, kilometre, strip_units/2]).

:- constant_number_units(five_m, 5, m).            % 5 (metre)
:- constant_number_units(weight, 9.8, newton).     % 9.8 (kilogram * metre / second ** 2)
:- constant_number_units(back, -3, s).             % -3 (second)
:- constant_number_units(pace, 5, m/s).            % 5 (metre / second)
:- constant_number_units(area, 10, m**2).          % 10 (metre ** 2)
:- constant_number_units(trip, 5, kilometre).      % 5000 (metre)
:- constant_number_units(one_newton, 1, newton).

force_of(N, F) :-
    F is N * constant(one_newton).

test("declared quantities") :-
    X is constant(trip),
    strip_units(X, 5000),
    constant_number_units(trip, 5, U),
    U == kilometre.

test("from a runtime value") :-
    force_of(9.8, F),
    F =:= constant(weight).
```

(`constant_number_units/3` as a goal reads a declaration back: `trip`'s
number and unit as written, `5` and `kilometre`.)

The SI prefix constants (`kilo`, `nano`, …) and IEC binary prefixes
(`kibi`, …) are plain Python numbers, which Clausal Prolog cannot evaluate:
`X is 5 * kilo` raises `type_error(evaluable, kilo/0)`. Use a prefixed unit
(`kilometre`, `gibibyte`, `millisecond`) or write the number.

### Seam sugar: `n(Unit)` — SI predicates only

The rest of this section is seam syntax.

```seam
-import_from(py.units, [m, s, newton])

a(X) <- eval_(5(m), X)          # 5 (metre)
b(X) <- eval_(9.8(newton), X)   # 9.8 (kilogram * metre / second ** 2)
c(X) <- eval_(-3(s), X)         # -3 (second)
d(X) <- eval_(5(m/s), X)        # 5 (metre / second)
e(X) <- eval_(10(m**2), X)      # 10 (metre ** 2)
```

**The argument inside the parentheses must be an SI unit predicate** (or a
compound expression built from SI unit predicates using `*`, `/`, `**`).
Imperial and other scaled-unit **Quantity** values (`inch`, `foot`, `byte`, …)
also work — `5(inch)` is `5 * inch` — because a `Quantity` is callable and
scales itself. SI prefix names (`kilo`, `milli`, …) are plain numbers, not
units; `5(kilo)` raises a `TypeError` ("SI prefixes cannot be used as units").
Multiply a prefix in instead: `++(5 * kilo * m(1))` — call the unit as `m(1)`
to get a multipliable `Quantity`; the bare predicate `m` cannot appear on the
right of `*` (`5 * kilo * m` raises a `TypeError`).

For unusual constructions, use `++()` directly:

```seam
-import_from(py.units, [kilogram, metre, second])

custom(X) <- (X is ++(kilogram(1) * metre(1) / second(1)**2 * 9.8))   # same as 9.8(newton)
```

### Seam: `* unit` style — SI prefixes and imperial

SI prefixes are plain numbers; imperial/non-SI units are `Quantity` unit
vectors.  Both are used via multiplication inside a `++()` escape:

```seam
-import_from(py.units, [kilo, nano, giga, newton, second, hertz])
-import_from(py.imperial, [inch, mph])

force(X) <- (X is ++(5 * kilo * newton(1)))        # 5 kN
tick(X) <- (X is ++(100 * nano * second(1)))       # 100 ns
clock(X) <- (X is ++(2.4 * giga * hertz(1)))       # 2.4 GHz
span(X) <- (X is ++(20 * inch))                    # 20 inches → 0.508 (metre)
pace(X) <- (X is ++(60 * mph))                     # 60 mph → 26.8224 (metre / second)
```

---

## Seam: `n()` — dimensionless literal

An empty-argument call on any numeric literal produces a dimensionless
`Quantity(n, {})`:

```seam
answer(X) <- eval_(42(), X)     # 42 (dimensionless)
pi(X) <- eval_(3.14(), X)       # 3.14 (dimensionless)
```

---

## Seam: `X(Unit)` — construction from a runtime value

(Clausal Prolog scales a unit quantity instead, `F is N *
constant(one_newton)`; see [Writing a measurement](#in-clausal-prolog-a-units-declaration).)
when the callee is a logic variable, `MY_VAL(Unit)` desugars to
`++(Quantity(MY_VAL, Unit))`:

```seam
-import_from(py.units, [newton])

force_of(N, F) <- eval_(N(newton), F)     # force_of(9.8, F): F = 9.8 (kilogram * metre / second ** 2)
```

---

## `has_units(X, Unit)` — dimension constraint / check

In Clausal Prolog the unit argument is a **quantity** of the wanted
dimension, a units constant. (A bare unit name such as `newton` or `m/s` is
the plain atom or term there, and `has_units(F, newton)` fails; the seam's
unit names are the unit predicates themselves.)

```clausal
:- use_module(library(units), [m, s, newton, has_units/2]).

:- constant_number_units(one_newton, 1, newton).
:- constant_number_units(metre_per_second, 1, m/s).
:- constant_number_units(weight, 9.8, newton).
:- constant_number_units(nine_m, 9.8, m).

% check or constrain: F must have newton dims
is_force(F) :-
    has_units(F, constant(one_newton)).

% velocity check/constraint
is_velocity(V) :-
    has_units(V, constant(metre_per_second)).

% an unbound F is constrained first, then checked when it is bound
newton_ok(F) :-
    has_units(F, constant(one_newton)),
    F = constant(weight).

metre_bad(F) :-
    has_units(F, constant(one_newton)),
    F = constant(nine_m).

test("constrain then bind") :-
    newton_ok(_),
    \+ metre_bad(_).

test("check a bound quantity") :-
    V is constant(nine_m) / 2,
    \+ is_velocity(V),
    is_force(constant(weight)).
```

In the seam (seam syntax):

```seam
-import_from(py.units, [m, s, newton, has_units])

is_force(F) <- has_units(F, newton)              # check or constrain: F must have newton dims
is_velocity(V) <- has_units(V, m/s)              # velocity check/constraint
is_acceleration(A) <- has_units(A, m/s**2)       # acceleration

# an unbound F is constrained first, then checked when it is bound
newton_ok(F) <- (has_units(F, newton), eval_(9.8(newton), F))   # succeeds
metre_bad(F) <- (has_units(F, newton), eval_(9.8(m), F))        # fails
```

`has_units/2` posts an AttVar constraint on `F` if it is unbound. In the
seam, compound unit expressions work directly — the transformer auto-wraps
them — and `has_units` cannot appear inside an `eval_/2` expression or on
the RHS of `==`.

---

## `Quantity` term

```python
from clausal.terms import Quantity, UnitsMismatch

d = Quantity(10.0, {metre: 1, second: -1})  # 10 m/s
d.value   # 10.0
d.dims    # MappingProxyType({<metre>: 1, <second>: -1})
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

These are the Python operators on a `Quantity`. In a Clausal Prolog clause,
compute with `is/2` (the seam's [`eval_/2`](arithmetic.md)): `+ - * **`
behave as above, and division is **exact**. Two integer magnitudes divide
to a rational, not a float — with `seven_m` declared as 7 m, `X is
constant(seven_m) / 2` gives `X` the magnitude `7 rdiv 2` — unlike `7 / 2`
between plain numbers, which is 3.5 (see [Operators](operators.md)). A float
magnitude stays a float, a dimension mismatch (`constant(seven_m) + 1`, or
a length plus a force) raises `error(system_error(units_mismatch), (is)/2)`,
and a zero divisor raises `evaluation_error(zero_divisor)` in `is/2` and
fails inside a constraint (`X #= constant(seven_m) / 0`). A
[currency](currency.md) amount is stricter: a float factor beside its exact
`Decimal` magnitude is refused.

```clausal
:- use_module(library(units), [m, newton, strip_units/2]).
:- use_module(library(clpz)).

:- constant_number_units(seven_m, 7, m).
:- constant_number_units(weight, 9.8, newton).

test("exact division") :-
    X is constant(seven_m) / 2,
    strip_units(X, V),
    Half is 7 rdiv 2,
    V == Half,
    \+ float(V).

test("exponents add") :-
    X is constant(seven_m) * constant(seven_m),
    strip_units(X, 49).

test("units that cancel give a plain number") :-
    X is constant(seven_m) / constant(seven_m),
    X == 1.

test("a mismatch is an ISO error") :-
    catch(_ is constant(seven_m) + constant(weight), error(E, _), true),
    E == system_error(units_mismatch).

test("a zero divisor") :-
    catch(_ is constant(seven_m) / 0, error(E, _), true),
    E == evaluation_error(zero_divisor),
    \+ _ #= constant(seven_m) / 0.
```

---

## Modules

### `py.units` — SI units and prefixes

Clausal Prolog imports it through its facade, `library(units)` (the seam
imports `py.units` directly):

```clausal
:- use_module(library(units), [m, kg, s, newton, has_units/2, strip_units/2]).
```

Contains: SI base unit predicates, scaled SI unit predicates, named derived SI
unit predicates, SI prefix constants, IEC binary prefix constants, SI
abbreviations, SI unit vectors, digital information units, physical constants,
and utility predicates (`has_units`, `strip_units`, `dimension_of`, `make_quantity`).

### `py.imperial` — imperial and non-SI unit vectors

```clausal
:- use_module(library(imperial), [inch, foot, yard, mile, pound_mass, mph, lbf]).
```

Contains: imperial and non-SI `Quantity` unit vectors for length, mass, force,
volume, pressure, energy, power, speed, and temperature differences.  All
values are stored in SI base units; `has_units` checks work without changes.

---

### SI base unit predicates

Used in a `constant_number_units` declaration, or with the seam's `n(Unit)` sugar.

| Alias | Full name  | Dims             | SI symbol |
|-------|------------|------------------|-----------|
| `m`   | `metre`    | `{metre: 1}`     | m         |
| `kg`  | `kilogram` | `{kilogram: 1}`  | kg        |
| `s`   | `second`   | `{second: 1}`    | s         |
| `mol` | `mole`     | `{mole: 1}`      | mol       |
| `cd`  | `candela`  | `{candela: 1}`   | cd        |
| —     | `ampere`   | `{ampere: 1}`    | A *(clash)* |
| —     | `kelvin`   | `{kelvin: 1}`    | K *(clash)* |

`A` and `K` are omitted as aliases — single uppercase letters are logic
variables in Clausal Prolog.

**Digital information base unit** (IEC 80000-13):

| Alias | Full name | Dims        | IEC symbol |
|-------|-----------|-------------|------------|
| —     | `bit`     | `{bit: 1}`  | bit        |

`bit` uses itself as the dimension key, exactly like the SI base units.

---

### Scaled SI unit predicates

These scale on the way in and store as SI base units.  Use them like the base units.

#### length (stored as metres)

`kilometre` (`km`), `centimetre` (`cm`), `millimetre` (`mm`),
`micrometre` (`um`), `nanometre` (`nm`)

#### Mass (stored as kilograms)

`gram` (`mg` for milli, `ug` for micro), `milligram`, `microgram`, `tonne`

#### Time (stored as seconds)

`millisecond` (`ms`), `microsecond` (`us`), `nanosecond` (`ns`),
`minute` (`min`), `hour` (`hr`), `day`, `week`, `julian_year`

#### Digital information (stored as bits)

`bit` is the base unit (IEC 80000-13).  All values are normalised to bits.

```clausal
:- use_module(library(units), [gibibyte, megabit, mebibyte, strip_units/2]).

:- constant_number_units(disk, 4, gibibyte).       % 34359738368 (bit)
:- constant_number_units(link, 100, megabit).      % 100000000 (bit)
:- constant_number_units(buffer, 512, mebibyte).   % 4294967296 (bit)

test("digital units store bits") :-
    D is constant(disk),
    strip_units(D, 34359738368),
    L is constant(link),
    strip_units(L, 100000000),
    B is constant(buffer),
    strip_units(B, 4294967296).
```

(The seam can also scale by a binary prefix, `++(512 * mebi * byte(1))`.)

Decimal (SI-prefixed) byte multiples:

| Predicate   | Stored as bits | Alias |
|-------------|----------------|-------|
| `byte`      | 8              | —     |
| `kilobyte`  | 8 × 10³        | —     |
| `megabyte`  | 8 × 10⁶        | —     |
| `gigabyte`  | 8 × 10⁹        | —     |
| `terabyte`  | 8 × 10¹²       | —     |

Decimal bit multiples:

| Predicate   | Stored as bits |
|-------------|----------------|
| `kilobit`   | 10³            |
| `megabit`   | 10⁶            |
| `gigabit`   | 10⁹            |

Binary (IEC-prefixed) byte multiples:

| Predicate   | Stored as bits  |
|-------------|-----------------|
| `kibibyte`  | 8 × 2¹⁰         |
| `mebibyte`  | 8 × 2²⁰         |
| `gibibyte`  | 8 × 2³⁰         |
| `tebibyte`  | 8 × 2⁴⁰         |

Binary bit multiples:

| Predicate   | Stored as bits |
|-------------|----------------|
| `kibibit`   | 2¹⁰            |
| `mebibit`   | 2²⁰            |
| `gibibit`   | 2³⁰            |

#### Named derived SI units

| Predicate | Quantity              | Dims (SI base)                    |
|-----------|-----------------------|-----------------------------------|
| `newton`  | force                 | `{kg:1, m:1, s:-2}`              |
| `joule`   | energy                | `{kg:1, m:2, s:-2}`              |
| `watt`    | power                 | `{kg:1, m:2, s:-3}`              |
| `pascal`  | pressure              | `{kg:1, m:-1, s:-2}`             |
| `hertz`   | frequency             | `{s:-1}`                          |
| `volt`    | voltage               | `{kg:1, m:2, s:-3, A:-1}`        |
| `coulomb` | charge                | `{A:1, s:1}`                      |
| `farad`   | capacitance           | `{kg:-1, m:-2, s:4, A:2}`        |
| `ohm`     | resistance            | `{kg:1, m:2, s:-3, A:-2}`        |
| `siemens` | conductance           | `{kg:-1, m:-2, s:3, A:2}`        |
| `weber`   | magnetic flux         | `{kg:1, m:2, s:-2, A:-1}`        |
| `tesla`   | magnetic flux density | `{kg:1, s:-2, A:-1}`             |
| `henry`   | inductance            | `{kg:1, m:2, s:-2, A:-2}`        |
| `lumen`   | luminous flux         | `{cd:1}`                          |
| `lux`     | illuminance           | `{cd:1, m:-2}`                    |
| `katal`   | catalytic activity    | `{mol:1, s:-1}`                   |
| `gray`    | absorbed dose         | `{m:2, s:-2}`                     |
| `sievert` | dose equivalent       | `{m:2, s:-2}`                     |

Scaled variants: `bar`, `millibar`, `atmosphere`, `electronvolt`, `kilowatt`

---

### SI prefix constants

Plain Python numbers — **not** predicates, and not evaluable from Clausal
Prolog (see [Writing a measurement](#in-clausal-prolog-a-units-declaration)).
The seam uses them inside `++()` by multiplying against a unit vector (seam
syntax):

```seam
-import_from(py.units, [kilo, nano, giga, mega, newton, second, hertz, joule])

prefixed(X) <- (X is ++(5 * kilo * newton(1)))     # 5 kN
prefixed(X) <- (X is ++(100 * nano * second(1)))   # 100 ns
prefixed(X) <- (X is ++(2.4 * giga * hertz(1)))    # 2.4 GHz
prefixed(X) <- (X is ++(1 * mega * joule(1)))      # 1 MJ
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
| `milli` | 1e-3   | m *(clash with metre alias)* | use `milli` |
| `micro` | 1e-6   | μ *(not a valid identifier)* | use `micro` |
| `nano`  | 1e-9   | n → `n`   | |
| `pico`  | 1e-12  | p → `p`   | |
| `femto` | 1e-15  | f → `f`   | |
| `atto`  | 1e-18  | a → `a`   | |
| `zepto` | 1e-21  | z → `z`   | *(rarely needed)* |
| `yocto` | 1e-24  | y → `y`   | *(rarely needed)* |

Single-letter abbreviations (`k`, `h`, `da`, `d`, `c`, `n`, `p`, `f`, `a`)
are available but must be imported explicitly.

`milli` has no safe single-letter alias: `m` is already the metre predicate.
`micro` has no safe alias: `μ` is not a valid Python identifier.  The
per-unit abbreviations `ms`, `mg`, `mm`, `us`, `um` encode both prefix and
unit together.

#### IEC binary prefix constants

Plain Python numbers. The seam uses them inside `++()` by multiplying
against a unit vector (seam syntax); Clausal Prolog writes the prefixed unit
(`gibibyte`, `mebibyte`, `kibibit`):

```seam
-import_from(py.units, [gibi, mebi, kibi, byte, bit])

binary(X) <- (X is ++(4 * gibi * byte(1)))      # 4 GiB → 34359738368 (bit)
binary(X) <- (X is ++(512 * mebi * byte(1)))    # 512 MiB
binary(X) <- (X is ++(100 * kibi * bit(1)))     # 100 Kib
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
letter and are not provided as aliases — in Clausal Prolog an identifier starting with
an uppercase letter is a logic variable.

---

### Imperial and non-SI unit vectors  (`py.imperial`)

Plain `Quantity` values — **not** predicates.  Import them from
`library(imperial)` and declare quantities with them (the seam multiplies a
scalar inside a `++()` escape, `++(20 * inch)`):

```clausal
:- use_module(library(imperial), [inch, pound_mass, mph, kilowatt_hour]).
:- use_module(library(units), [strip_units/2]).

:- constant_number_units(len, 20, inch).            % 0.508 (metre)
:- constant_number_units(mass, 150, pound_mass).    % 68.0388555 (kilogram)
:- constant_number_units(spd, 60, mph).             % 26.8224 (metre / second)
:- constant_number_units(energy, 1, kilowatt_hour). % 3600000.0 (kilogram * metre ** 2 / second ** 2)

test("imperial quantities in SI base units") :-
    L is constant(len),
    strip_units(L, LV),
    abs(LV - 0.508) < 1.0e-9,
    M is constant(mass),
    strip_units(M, MV),
    abs(MV - 68.0388555) < 1.0e-9,
    S is constant(spd),
    strip_units(S, SV),
    abs(SV - 26.8224) < 1.0e-9,
    E is constant(energy),
    strip_units(E, 3600000.0).
```

All values are stored in SI base units; dimensions are the same as their SI
equivalents so `has_units` checks work without any changes:

```clausal
:- use_module(library(imperial), [inch]).
:- use_module(library(units), [metre, has_units/2]).

:- constant_number_units(span, 20, inch).
:- constant_number_units(one_metre, 1, metre).

% succeeds — both have {metre: 1}
is_length :-
    has_units(constant(span), constant(one_metre)).

test("an imperial length is a length") :-
    is_length.
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

#### Temperature differences (stored as kelvin — ratio scale only)

| Name      | Value (K)  |
|-----------|------------|
| `rankine` | 5/9        |

Absolute offset scales (Celsius, Fahrenheit) are unsupported — they are not
ratio scales.

---

### Utility predicates

| Predicate                  | Description |
|----------------------------|-------------|
| `dimension_of(D, Dims)`     | Unify `Dims` with a `DictTerm` of the dimension dict (a bare number is dimensionless: `{}`) |
| `strip_units(D, V)`         | Unify `V` with the numeric component |
| `make_quantity(V, Dims, D)` | Construct `Quantity` from value `V` and `DictTerm` dims |

```clausal
:- use_module(library(units), [newton, dimension_of/2, strip_units/2,
                               make_quantity/3]).

:- constant_number_units(weight, 9.8, newton).

test("dimension_of and make_quantity") :-
    dimension_of(constant(weight), Dims),
    make_quantity(2, Dims, Q),
    strip_units(Q, 2),
    dimension_of(Q, Dims).

test("a bare number is dimensionless") :-
    dimension_of(5, Dims),
    dict_pairs(Dims, []).
```

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
| `speed_of_light`          | 2.998 × 10⁸ m/s               | `{m:1, s:-1}` |
| `planck_constant`        | 6.626 × 10⁻³⁴ J·s             | `{kg:1, m:2, s:-1}` |
| `boltzmann_constant`     | 1.381 × 10⁻²³ J/K             | `{kg:1, m:2, s:-2, K:-1}` |
| `standard_gravity`       | 9.806 65 m/s²                  | `{m:1, s:-2}` |
| `elementary_charge`      | 1.602 × 10⁻¹⁹ C               | `{A:1, s:1}` |
| `gravitational_constant` | 6.674 × 10⁻¹¹ m³/(kg·s²)     | `{m:3, kg:-1, s:-2}` |

---

## Uninstantiated dimensioned slots (AttVar)

An uninstantiated slot that will eventually hold a measurement uses a plain
Var with a `"units"` AttVar constraint — **not** `Quantity(Var, dims)`.

```python
from clausal.logic.variables import Var, Trail
from clausal.logic.units_constraint import constrain_var_dims
from clausal.modules.py.units import newton

trail = Trail()
v = Var()
constrain_var_dims(v, newton._dims, trail)  # post constraint
from clausal.logic.variables import unify
unify(v, newton(9.8), trail)   # fires hook → checks dims → binds v
```

Such a variable, or a ground quantity, may take part in a CLP constraint:
the CLP(FD) comparators and `in_domain/3`, CLP(Q) (`{C}` in a `.pl`
file, `clpq.rational/1`, `in_q/3`, the objectives) and, for physical
quantities only, CLP(R). The solver works on
the exact magnitude in the dimension's base unit and the answer comes back
as a quantity; dimensions that disagree raise
`error(system_error(units_mismatch), Ctx)`. See [clpq.md](clpq.md#units)
and the design in `docs/superpowers/specs/2026-09-12-clp-units-side-channel-design.md`.

---

## Catching unit errors

In Clausal Prolog a dimension mismatch in arithmetic is the ISO error term
`error(system_error(units_mismatch), (is)/2)`, caught with
[`catch/3`](exceptions.md) like any other:

```clausal
:- use_module(library(units), [metre, second]).

:- constant_number_units(three_m, 3, metre).
:- constant_number_units(two_s, 2, second).

mismatch(E) :-
    catch(_ is constant(three_m) + constant(two_s), error(E, _), true).

test("caught") :-
    mismatch(E),
    E == system_error(units_mismatch).
```

In the seam, `UnitsMismatch` is also a Python exception class, so a module
imports it and catches it with a `++` catcher; the instance form binds the
message (seam syntax):

```seam
-import_from(py.units, [metre, second])
-import_from(clausal.terms, [UnitsMismatch])

mismatch_message(MSG) <- catch(
    _ is ++(metre(3) + second(2)),
    ++UnitsMismatch(MSG),
    true
)
# MSG = "Unit mismatch for add: metre vs second"
```

A **comparison** across dimensions (`X > 0` with `X` a length) is not a `UnitsMismatch`
exception but the ISO error term `error(system_error(units_mismatch), Ctx)`;
the seam names `(>)/2` as the context, Clausal Prolog `(is)/2`.

---

## Program verification with `has_units`

`has_units` goals are runtime assertions about dimensional types.  They compose
freely with all Clausal Prolog constructs: [negation-as-failure](control.md), [`catch/3`](exceptions.md),
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

Each SciPy predicate falls into one of four categories (see individual module docs for details: [scipy.linalg](https://github.com/neurosymbolica/clausal-prolog/blob/main/packages/clausal-scipy/docs/scipy_linalg.md), [scipy.special](https://github.com/neurosymbolica/clausal-prolog/blob/main/packages/clausal-scipy/docs/scipy_special.md), [scipy.fft](https://github.com/neurosymbolica/clausal-prolog/blob/main/packages/clausal-scipy/docs/scipy_fft.md), [scipy.differentiate](https://github.com/neurosymbolica/clausal-prolog/blob/main/packages/clausal-scipy/docs/scipy_differentiate.md), [scipy.integrate](https://github.com/neurosymbolica/clausal-prolog/blob/main/packages/clausal-scipy/docs/scipy_integrate.md), [scipy.interpolate](https://github.com/neurosymbolica/clausal-prolog/blob/main/packages/clausal-scipy/docs/scipy_interpolate.md)):

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
- **Integer-only exponents in `Pow`**: `area ** 0.5` raises `UnitsMismatch`
  (in Clausal Prolog, `error(system_error(units_mismatch), (is)/2)`).
- **Dimension keys are predicate objects**: the seven SI base unit predicates
  are the keys in `dims`.
- **`A` and `K` aliases omitted**: single uppercase letters are logic
  variables in Clausal Prolog.
- **SI prefixes are plain numbers**: `kilo = 1e3`, `milli = 1e-3`, etc.
  Clausal Prolog cannot evaluate them; use a prefixed unit (`kilometre`).
  In the seam they cannot appear inside `n(Unit)` parentheses; use
  multiplication in a `++()` escape instead.
- **IEC binary prefixes are plain numbers**: `kibi = 2¹⁰`, `mebi = 2²⁰`, etc.
  Same rules as SI prefixes — in the seam, multiply against a unit vector
  in `++()`.
- **`bit` is the information base unit** (IEC 80000-13): all byte and
  prefixed-bit predicates store internally in bits, so arithmetic between them
  works without conversion.
- **Imperial units are Quantity unit vectors**: `inch`, `foot`, `pound_mass`,
  etc.  Declare a quantity with one (`:- constant_number_units(span, 20,
  inch).`), or in the seam multiply by a scalar in a `++()` escape.  `has_units` checks work
  normally since the dimensions are identical to their SI equivalents.

---

*See also: [Currency](currency.md) — exact-decimal money built on this units machinery · [Arithmetic](arithmetic.md) — numeric operations in Clausal Prolog · [Python Interop](python_integration.md) — the seam's `++()` escape for direct Pint operations.*
