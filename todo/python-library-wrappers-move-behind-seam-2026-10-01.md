# Python-library wrappers move behind `.seam`: Clausal Prolog never calls Python directly

**Filed:** 2026-10-01. **Ruled (operator, 2026-10-01):** `.seam` is THE Python-interop boundary.
Clausal Prolog (`.clausal`, the cut-free dialect) reaches Python only through `.seam` wrapper
modules, whose correctness is the wrapper author's responsibility. The engine-provided
`py/<lib>` bridges are NOT an exception: `:- use_module(py/datetime, [date_add/3, ...])` from
Clausal code becomes an import of a `.seam` wrapper.

Companion rulings, same day:
- `.pl` may call `.clausal`; `.clausal` may NEVER call `.pl` (arbitrary Prolog is assumed to
  use cut). There is no opt-in flag: vendored Prolog is converted to `.clausal` and validated.
- So the Clausal dialect's guarantees hold TRANSITIVELY: its only exits are other `.clausal`
  modules and `.seam` wrappers.

## Status (2026-10-01, branch feat/py-adapters-behind-seam-facades-2026-10-01)

- Done for core: every Python module under `clausal/modules` (py/, the
  domain modules, countries/) has a generated `.seam` facade imported as
  `library(<path>)` (ruled spelling); `clausal/_py_facades.py` lists them.
- Done: the load-time refusal under the `clausal_prolog` surface (both
  `.pl` front ends), inert until the extension flip; alias module names
  (`european_union`, `units`) import their facade.
- Open: extension distributions -- `todo/package-adapters-need-library-facades-2026-10-01.md`;
  Do item 2's other routes and item 3's downstream migration census.

## Population (measured 2026-10-01)

- Core wrappers, `clausal/modules/py/*.py`: 20 modules (csv, datetime, files, hash, hmac,
  http, imperial, json, logging, os, pbkdf2, process, random, re, sqlite, tcp, units, url, uuid,
  plus `_helpers`). They are Python modules today; there is no `.seam` wrapper for any of them.
- Extension distributions, `packages/clausal-*/.../clausal/modules/py/*.py`: about 45 more
  (jax*, opencv*, scipy_*, sklearn, spacy, sympy, torch*, yaml), contributed via PEP 420.
- Regenerate rather than trust these counts: `ls clausal/modules/py/*.py` and
  `find packages -path '*clausal/modules/py/*.py'`.

## Do

1. Decide the wrapper form. Either:
   - each `py/<lib>` becomes a `.seam` module exposing the same predicates, or
   - a `.seam` facade per library re-exports the existing Python implementation.
   Either way, the `.seam` file is the only thing a `.clausal` module may import. Keep the
   predicate names and arities, so call sites change only their import line.
2. Enforcement, by construction: a `.clausal` module importing `py/<lib>` directly, or any
   non-`.seam` Python module, is a load-time error, alongside the `.clausal` → `.pl` refusal.
   Name every other route Python could be reached from Clausal code (e.g. a goal built at
   runtime, Python-side `solve` with a Clausal module) and close or document each one.
3. Transition: today's Clausal code imports `py/datetime` widely, and the `.pl` loader is the
   interim carrier for Clausal Prolog. Sequence this with the "`.clausal` parses as Clausal
   Prolog" flip, so no consumer is left with neither path. Size the import-line migration by
   census.
4. Extension distributions: the same treatment, one todo per distribution if it can't be
   done in one pass.
5. Tests: a YES test (a `.clausal` module using a `.seam` wrapper loads and works) and a NO
   test (a direct `py/<lib>` import from `.clausal` is refused), for at least `datetime` and
   one extension wrapper.
