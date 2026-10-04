# scipy.constants — Physical Constants

The `scipy_constants` module wraps [`scipy.constants`](https://docs.scipy.org/doc/scipy/reference/constants.html) as Clausal predicates. It provides CODATA physical constants, physical constant values by name, and SI prefix multipliers.

---

## Import

```clausal
-import_from(scipy_constants, [value, unit, precision, lookup, find, all_names,
                               scipy_speed_of_light, scipy_planck_constant,
                               scipy_reduced_planck_constant,
                               scipy_gravitational_constant,
                               scipy_avogadro_constant, scipy_boltzmann_constant,
                               scipy_elementary_charge, scipy_electron_mass,
                               scipy_proton_mass, scipy_electron_volt,
                               scipy_standard_atmosphere, scipy_pi,
                               scipy_kilo, scipy_mega, scipy_giga])
```

Or via the canonical `py.*` path:

```clausal
--8<-- "tests/fixtures/docs/scipy_constants_sigs.txt:import"
```

---

## Tier

All predicates are **Tier 1 — pure**: they perform direct attribute lookups or CODATA database queries, with no stateful objects. There is no handle or result record; the RESULT argument receives a plain Python float, a unit as a **string** (`"m s^-1"`), or constant names as **atoms**. A constant name is the key every predicate here looks up, so `find/2` and `all_names/1` answer atoms (`'speed of light in vacuum'`); a unit is free-form text, so `unit/2` and `lookup/4` answer a string (ruled 2026-10-04). A `NAME` or `SUBSTRING` argument may be an atom or a string.

---

## Naming conventions

The `Const` prefix from the spec is dropped since these predicates live in the `scipy_constants` module. Abbreviations that are not the universal name are expanded:

| scipy attribute / function | Clausal predicate |
|---|---|
| `constants.value(name)` | `value` |
| `constants.unit(name)` | `unit` |
| `constants.precision(name)` | `precision` |
| `constants.physical_constants[name]` | `lookup` |
| `constants.find(sub)` | `find` |
| `constants.physical_constants.keys()` | `all_names` |
| `constants.c` | `scipy_speed_of_light` |
| `constants.h` | `scipy_planck_constant` |
| `constants.hbar` | `scipy_reduced_planck_constant` |
| `constants.G` | `scipy_gravitational_constant` |
| `constants.N_A` | `scipy_avogadro_constant` |
| `constants.k` | `scipy_boltzmann_constant` |
| `constants.e` | `scipy_elementary_charge` |
| `constants.m_e` | `scipy_electron_mass` |
| `constants.m_p` | `scipy_proton_mass` |
| `constants.eV` | `scipy_electron_volt` |
| `constants.atm` | `scipy_standard_atmosphere` |
| `constants.kilo` | `scipy_kilo` |
| `constants.mega` | `scipy_mega` |
| `constants.giga` | `scipy_giga` |
| `constants.pi` | `scipy_pi` |

The constants are lower_snake_case with a `scipy_` prefix. They were
TitleCase (`SpeedOfLight`, `Kilo`, ...) and were renamed with no aliases
(see [RENAMES.md](RENAMES.md)): TitleCase reads as a logic variable. The
prefix keeps them apart from `py.units`' exact `speed_of_light`, `kilo`, ...
and the arithmetic `pi` -- these are SciPy's float values, and a file may
import both.

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

#### `lookup(NAME, VALUE, UNIT, UNCERTAINTY)`

Access all three CODATA fields for a constant in a single call.

- `VALUE`: float, the physical quantity value in SI units
- `UNIT`: a string, the SI unit (`"kg"`)
- `UNCERTAINTY`: float, absolute uncertainty (not relative — use `precision` for relative)

```clausal
--8<-- "tests/fixtures/docs/scipy_constants_sigs.txt:codata_lookup_ex2"
```

Fails if `NAME` is not recognised, or if any output argument fails to unify.

---

#### `find(SUBSTRING, NAMES)`

Search the CODATA database by substring; returns all matching constant names.

- `SUBSTRING`: string to search for (case-sensitive, uses `scipy.constants.find`)
- `NAMES`: list of matching names, as atoms; empty list if no match

```clausal
--8<-- "tests/fixtures/docs/scipy_constants_sigs.txt:codata_lookup_ex3"
```

---

#### `all_names(NAMES)`

Return all CODATA constant names as a list.

- `NAMES`: list of all names in `scipy.constants.physical_constants`, as atoms

```clausal
--8<-- "tests/fixtures/docs/scipy_constants_sigs.txt:codata_lookup_ex4"
```

---

#### `unit(NAME, RESULT)`

Return the SI unit of a named CODATA constant.

- `RESULT`: a string such as `"m s^-1"` or `"J s"` (not an atom)

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

These are VALUES, not predicates: each is a `Quantity` in SI units (a float
magnitude with its dimensions), and the SI prefixes and `scipy_pi` are plain
floats. Use one where a value goes -- `C is scipy_speed_of_light`,
`has_units(scipy_boltzmann_constant, joule / kelvin)`; calling one
(`scipy_speed_of_light(C)`) is no goal.

| Name | Value |
|---|---|
| `scipy_speed_of_light` | c = 299 792 458 m s⁻¹ (exact) |
| `scipy_planck_constant` | h = 6.626 070 15 × 10⁻³⁴ J s (exact) |
| `scipy_reduced_planck_constant` | ℏ = h / (2π) ≈ 1.054 572 × 10⁻³⁴ J s |
| `scipy_gravitational_constant` | G = 6.674 3 × 10⁻¹¹ N m² kg⁻² |
| `scipy_avogadro_constant` | Nₐ = 6.022 140 76 × 10²³ mol⁻¹ (exact) |
| `scipy_boltzmann_constant` | k = 1.380 649 × 10⁻²³ J K⁻¹ (exact) |
| `scipy_elementary_charge` | e = 1.602 176 634 × 10⁻¹⁹ C (exact) |
| `scipy_electron_mass` | mₑ = 9.109 383 7139 × 10⁻³¹ kg |
| `scipy_proton_mass` | mₚ = 1.672 621 925 95 × 10⁻²⁷ kg |

### Unit conversion and SI prefix factors

| Name | Value |
|---|---|
| `scipy_electron_volt` | 1 eV = 1.602 176 634 × 10⁻¹⁹ J (numerically the elementary charge) |
| `scipy_standard_atmosphere` | 1 atm = 101 325 Pa (exact) |
| `scipy_pi` | π, a float |
| `scipy_kilo` | 1 × 10³, a float |
| `scipy_mega` | 1 × 10⁶, a float |
| `scipy_giga` | 1 × 10⁹, a float |

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
