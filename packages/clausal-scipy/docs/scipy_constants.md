# scipy.constants — Physical Constants

The `scipy_constants` module wraps [`scipy.constants`](https://docs.scipy.org/doc/scipy/reference/constants.html) as Clausal predicates. It provides CODATA physical constants, physical constant values by name, and SI prefix multipliers.

---

## Import

```clausal
-import_from(scipy_constants, [value, unit, precision, Lookup, Find, AllNames,
                                SpeedOfLight, PlanckConstant,
                                ReducedPlanckConstant, GravitationalConstant,
                                AvogadroConstant, BoltzmannConstant,
                                ElementaryCharge, ElectronMass, ProtonMass,
                                ElectronVolt, StandardAtmosphere,
                                Kilo, Mega, Giga])
```

Or via the canonical `py.*` path:

```clausal
--8<-- "tests/fixtures/docs/scipy_constants_sigs.txt:import"
```

---

## Tier

All predicates are **Tier 1 — pure**: they perform direct attribute lookups or CODATA database queries, with no stateful objects. There is no handle or result record; the RESULT argument receives a plain Python float or string.

---

## Naming conventions

The `Const` prefix from the spec is dropped since these predicates live in the `scipy_constants` module. Abbreviations that are not the universal name are expanded:

| scipy attribute / function | Clausal predicate |
|---|---|
| `constants.value(name)` | `value` |
| `constants.unit(name)` | `unit` |
| `constants.precision(name)` | `precision` |
| `constants.physical_constants[name]` | `Lookup` |
| `constants.find(sub)` | `Find` |
| `constants.physical_constants.keys()` | `AllNames` |
| `constants.c` | `SpeedOfLight` |
| `constants.h` | `PlanckConstant` |
| `constants.hbar` | `ReducedPlanckConstant` |
| `constants.G` | `GravitationalConstant` |
| `constants.N_A` | `AvogadroConstant` |
| `constants.k` | `BoltzmannConstant` |
| `constants.e` | `ElementaryCharge` |
| `constants.m_e` | `ElectronMass` |
| `constants.m_p` | `ProtonMass` |
| `constants.eV` | `ElectronVolt` |
| `constants.atm` | `StandardAtmosphere` |
| `constants.kilo` | `Kilo` |
| `constants.mega` | `Mega` |
| `constants.giga` | `Giga` |

---

## Predicate catalogue

### CODATA lookup

`scipy.constants.physical_constants` contains all 300+ CODATA recommended values. Every entry has a value (float), a unit string, and an absolute uncertainty. All four predicates below index into this same database.

#### `value(NAME, RESULT)`

Look up a CODATA physical constant value by its full name string.

- `NAME`: CODATA name string, e.g. `'speed of light in vacuum'`, `'Planck constant'`, `'Boltzmann constant'`
- `RESULT`: float value in SI units

```clausal
--8<-- "tests/fixtures/docs/scipy_constants_sigs.txt:codata_lookup"
```

Fails if `NAME` is not a recognised CODATA name.

---

#### `Lookup(NAME, VALUE, UNIT, UNCERTAINTY)`

Access all three CODATA fields for a constant in a single call.

- `VALUE`: float, the physical quantity value in SI units
- `UNIT`: string, the SI unit
- `UNCERTAINTY`: float, absolute uncertainty (not relative — use `precision` for relative)

```clausal
--8<-- "tests/fixtures/docs/scipy_constants_sigs.txt:codata_lookup_ex2"
```

Fails if `NAME` is not recognised, or if any output argument fails to unify.

---

#### `Find(SUBSTRING, NAMES)`

Search the CODATA database by substring; returns all matching constant names.

- `SUBSTRING`: string to search for (case-sensitive, uses `scipy.constants.find`)
- `NAMES`: list of matching name strings; empty list if no match

```clausal
--8<-- "tests/fixtures/docs/scipy_constants_sigs.txt:codata_lookup_ex3"
```

---

#### `AllNames(NAMES)`

Return all CODATA constant names as a list.

- `NAMES`: list of all name strings in `scipy.constants.physical_constants`

```clausal
--8<-- "tests/fixtures/docs/scipy_constants_sigs.txt:codata_lookup_ex4"
```

---

#### `unit(NAME, RESULT)`

Return the SI unit string for a named CODATA constant.

- `RESULT`: a string such as `'m s^-1'` or `'J s'`

```clausal
--8<-- "tests/fixtures/docs/scipy_constants_sigs.txt:codata_lookup_ex5"
```

---

#### `precision(NAME, RESULT)`

Return the relative uncertainty of a named CODATA constant.

- `RESULT`: float, e.g. `0.0` for exact definitions, `2.2e-5` for G

```clausal
--8<-- "tests/fixtures/docs/scipy_constants_sigs.txt:codata_lookup_ex6"
```

---

### Physical constants

All zero-input predicates return a single float in SI units.

#### `SpeedOfLight(RESULT)`

Speed of light in vacuum: c = 299 792 458 m s⁻¹ (exact).

#### `PlanckConstant(RESULT)`

Planck constant: h = 6.626 070 15 × 10⁻³⁴ J s (exact).

#### `ReducedPlanckConstant(RESULT)`

Reduced Planck constant: ℏ = h / (2π) ≈ 1.054 572 × 10⁻³⁴ J s.

#### `GravitationalConstant(RESULT)`

Newtonian constant of gravitation: G = 6.674 3 × 10⁻¹¹ N m² kg⁻².

#### `AvogadroConstant(RESULT)`

Avogadro constant: Nₐ = 6.022 140 76 × 10²³ mol⁻¹ (exact).

#### `BoltzmannConstant(RESULT)`

Boltzmann constant: k = 1.380 649 × 10⁻²³ J K⁻¹ (exact).

#### `ElementaryCharge(RESULT)`

Elementary charge: e = 1.602 176 634 × 10⁻¹⁹ C (exact).

#### `ElectronMass(RESULT)`

Electron rest mass: mₑ = 9.109 383 7139 × 10⁻³¹ kg.

#### `ProtonMass(RESULT)`

Proton rest mass: mₚ = 1.672 621 925 95 × 10⁻²⁷ kg.

---

### unit conversion and SI prefix factors

#### `ElectronVolt(RESULT)`

One electron volt in joules: 1 eV = 1.602 176 634 × 10⁻¹⁹ J (numerically equal to the elementary charge).

#### `StandardAtmosphere(RESULT)`

One standard atmosphere in pascals: 1 atm = 101 325 Pa (exact).

#### `Kilo(RESULT)`

SI kilo prefix: 1 × 10³.

#### `Mega(RESULT)`

SI mega prefix: 1 × 10⁶.

#### `Giga(RESULT)`

SI giga prefix: 1 × 10⁹.

---

## Example

```clausal
--8<-- "tests/fixtures/docs/scipy_constants_sigs.txt:example"
```

---

## Notes

- All values reflect the 2018 CODATA recommended values as shipped with the installed version of SciPy.
- Several fundamental constants (c, h, e, k, Nₐ) became exact definitions under the 2019 SI redefinition; their `precision` is 0.0.
- `value`, `unit`, and `precision` accept the same name strings as `scipy.constants.value()`, `scipy.constants.unit()`, and `scipy.constants.precision()`. Unknown names cause the predicate to fail.

---

*See also: [Python Interop](python_integration.md) — `++()` escape for direct `scipy.constants` access · [Arithmetic](arithmetic.md) — numeric operations in Clausal.*
