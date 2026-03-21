# scipy.constants — Physical Constants

The `scipy_constants` module wraps [`scipy.constants`](https://docs.scipy.org/doc/scipy/reference/constants.html) as Clausal predicates. It provides CODATA physical constants, physical constant values by name, and SI prefix multipliers.

---

## Import

```clausal
-import_from(scipy_constants, [Value, Unit, Precision, Lookup, Find, AllNames,
                                SpeedOfLight, PlanckConstant,
                                ReducedPlanckConstant, GravitationalConstant,
                                AvogadroConstant, BoltzmannConstant,
                                ElementaryCharge, ElectronMass, ProtonMass,
                                ElectronVolt, StandardAtmosphere,
                                Kilo, Mega, Giga])
```

Or via the canonical `py.*` path:

```clausal
-import_from(py.scipy_constants, [Value, Unit, ...])
```

---

## Tier

All predicates are **Tier 1 — pure**: they perform direct attribute lookups or CODATA database queries, with no stateful objects. There is no handle or result record; the RESULT argument receives a plain Python float or string.

---

## Naming conventions

The `Const` prefix from the spec is dropped since these predicates live in the `scipy_constants` module. Abbreviations that are not the universal name are expanded:

| scipy attribute / function | Clausal predicate |
|---|---|
| `constants.value(name)` | `Value` |
| `constants.unit(name)` | `Unit` |
| `constants.precision(name)` | `Precision` |
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

#### `Value(NAME, RESULT)`

Look up a CODATA physical constant value by its full name string.

- `NAME`: CODATA name string, e.g. `'speed of light in vacuum'`, `'Planck constant'`, `'Boltzmann constant'`
- `RESULT`: float value in SI units

```clausal
Value('speed of light in vacuum', C),   % C = 299792458.0 m/s
Value('Planck constant', H),            % H = 6.626070e-34 J·s
Value('elementary charge', E)           % E = 1.602177e-19 C
```

Fails if `NAME` is not a recognised CODATA name.

---

#### `Lookup(NAME, VALUE, UNIT, UNCERTAINTY)`

Access all three CODATA fields for a constant in a single call.

- `VALUE`: float, the physical quantity value in SI units
- `UNIT`: string, the SI unit
- `UNCERTAINTY`: float, absolute uncertainty (not relative — use `Precision` for relative)

```clausal
Lookup('electron mass', V, U, ERR)
% V = 9.109384e-31, U = 'kg', ERR = 2.8e-40
```

Fails if `NAME` is not recognised, or if any output argument fails to unify.

---

#### `Find(SUBSTRING, NAMES)`

Search the CODATA database by substring; returns all matching constant names.

- `SUBSTRING`: string to search for (case-sensitive, uses `scipy.constants.find`)
- `NAMES`: list of matching name strings; empty list if no match

```clausal
Find('electron mass', NAMES)
% NAMES = ['alpha particle-electron mass ratio',
%           'deuteron-electron mass ratio', 'electron mass', ...]

Find('zzznomatch', NAMES)
% NAMES = []
```

---

#### `AllNames(NAMES)`

Return all CODATA constant names as a list.

- `NAMES`: list of all name strings in `scipy.constants.physical_constants`

```clausal
AllNames(NAMES),
++(len(NAMES))   % 300+ depending on scipy version
```

---

#### `Unit(NAME, RESULT)`

Return the SI unit string for a named CODATA constant.

- `RESULT`: a string such as `'m s^-1'` or `'J s'`

```clausal
Unit('speed of light in vacuum', U)  % U = 'm s^-1'
```

---

#### `Precision(NAME, RESULT)`

Return the relative uncertainty of a named CODATA constant.

- `RESULT`: float, e.g. `0.0` for exact definitions, `2.2e-5` for G

```clausal
Precision('Newtonian constant of gravitation', P)  % P > 0 (G has uncertainty)
Precision('speed of light in vacuum', P)           % P = 0.0 (exact since 2019)
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

### Unit conversion and SI prefix factors

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
-import_from(scipy_constants, [SpeedOfLight, BoltzmannConstant,
                                AvogadroConstant, Value, Unit])

% Thermal energy at room temperature (kT at 300 K)
ThermalEnergy(KT) <-
    BoltzmannConstant(K),
    KT is K * 300.

% Check that c agrees with CODATA lookup
CheckC <-
    SpeedOfLight(C_DIRECT),
    Value('speed of light in vacuum', C_LOOKUP),
    C_DIRECT == C_LOOKUP.

% Print the unit of Planck's constant
PlanckUnit <-
    Unit('Planck constant', U),
    Writeln(U).
```

---

## Notes

- All values reflect the 2018 CODATA recommended values as shipped with the installed version of SciPy.
- Several fundamental constants (c, h, e, k, Nₐ) became exact definitions under the 2019 SI redefinition; their `Precision` is 0.0.
- `Value`, `Unit`, and `Precision` accept the same name strings as `scipy.constants.value()`, `scipy.constants.unit()`, and `scipy.constants.precision()`. Unknown names cause the predicate to fail.
