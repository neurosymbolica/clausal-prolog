# Predicate renames (2026-10-02)

Breaking: these predicate names were TitleCase (Python class-style),
which the engine's TitleCase lint rejects in functor position --
Clausal Prolog code could not call them by name. They are renamed to
lower_snake_case, matching clausal-jax / clausal-torch convention.
Acronyms collapse to one lowercase word (e.g. `FFT` -> `fft`,
`KMeans` -> `k_means`).

| Old (TitleCase) | New (lower_snake_case) |
|---|---|
| `Apart` | `apart` |
| `Binomial` | `binomial` |
| `Cancel` | `cancel` |
| `Coeffs` | `coeffs` |
| `Collect` | `collect` |
| `Degree` | `degree` |
| `Diff` | `diff` |
| `Divisors` | `divisors` |
| `Expand` | `expand` |
| `ExpandTrig` | `expand_trig` |
| `Factor` | `factor` |
| `FactorInt` | `factor_int` |
| `FreeVars` | `free_vars` |
| `Integrate` | `integrate` |
| `IsPrime` | `is_prime` |
| `Latex` | `latex` |
| `Limit` | `limit` |
| `MathML` | `math_ml` |
| `NextPrime` | `next_prime` |
| `Pretty` | `pretty` |
| `Product` | `product` |
| `Roots` | `roots` |
| `Series` | `series` |
| `Simplify` | `simplify` |
| `Solve` | `solve` |
| `SolveAll` | `solve_all` |
| `Subs` | `subs` |
| `Sym` | `sym` |
| `SymEqual` | `sym_equal` |
| `SymStr` | `sym_str` |
| `Together` | `together` |
| `TrigSimp` | `trig_simp` |

## Removed

| Old (TitleCase) | Status |
|---|---|
| `Inf` (arity 1) | removed (2026-10-02 ruling): use the value `inf` (`inf = sympy.oo`, already lowercase and importable) instead of calling `Inf(X)`. |

## Merged

| Old (TitleCase) | Status |
|---|---|
| `ToSympy` (arity 2) | merged into `sympy_term/2` (2026-10-02 ruling): neither old name survives, and there is no alias. `sympy_term(Sympy, Term)` picks the direction by which argument is bound, ISO-`atom_codes/2`-style. See `docs/sympy.md` for the full mode table, the two error cases, and the variable-identity / non-bijection notes. |
| `FromSympy` (arity 2) | merged into `sympy_term/2`, same reason. |
