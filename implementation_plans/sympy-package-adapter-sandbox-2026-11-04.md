# Admitting one vetted package adapter to the sandbox (clausal-sympy)

2026-11-04. Status: **design, for review. Not implemented.** The operator has not yet ruled
on whether the sandbox should admit a package adapter at all.

## Problem

A rulebase run under the sandbox (`CLAUSAL_SANDBOX=1`) wants to solve physics relations
(heat duty, LMTD/UA with `log`, pressure-drop ratios) with `clausal-sympy`. Forward queries
then become deterministic, and inverse queries return every root. Today the sandbox refuses
it twice:

1. When the importing `.seam` is loaded. `-import_from(py.sympy, [...])` classifies the
   target as the route `py_adapter` (`clausal/python_bridges.py:505`, `_classify`). The loader
   admits a route only as a bridge, which must be in `enable(allow_bridges=...)` **and** in
   `APPROVED_BRIDGES` (`clausal/sandbox.py:1028`, `_bridge_admitted`). Otherwise
   `_sandboxed_code` (`sandbox.py:1121`) refuses the file.
2. When a predicate runs. `_multi_dispatch` (`clausal/modules/py/__init__.py:91`) calls
   `check_adapter` (`sandbox.py:1386`), which admits only objects whose `id` is in
   `_STATE.allowed_ids`. Those come only from the engine's `ADAPTERS` table (`sandbox.py:122`,
   collected by `_collect_allowed` at `:392`). Package adapters are outside it by design:
   `is_engine_shipped` (`python_bridges.py:1437`) decides by file.

Outside the sandbox, a project's `[tool.clausal] python_bridges` list gates the import
(`bridge_refusal`, `python_bridges.py:1635`).

## Why not make it a bridge

An admitted bridge is trusted wholesale. `_walk` (`python_bridges.py:1668`) treats a bridge's
own imports as its business, and a bridge is exempt from the dialect gate that keeps Clausal
code Python-free. Listing sympy's `.seam` as a bridge would admit any Python that `.seam`
hosts, and anything the wrapper imports. The bridge mechanism cannot express "these named
predicates of this one adapter, and nothing else".

## Precondition: the wrapper must not evaluate input

Until 2026-11-04 the wrapper's converter fell through to `sympy.sympify` for any term it had no
case for, and `sympify` parses the strings inside a list, tuple or dict with `eval`. So
`sym_str(["__import__('os')..."], R)` ran Python. That fallthrough is now a `TypeError`, pinned by
`TestNoEvalFallback` in `packages/clausal-sympy/tests/test_sympy_module.py` (branch
`t4-sympy-safety`). No admission is safe without that fix, and the review below re-checks it.

## Proposed rule: a new trust kind, "vetted package adapter"

**The allowlist.** A `PACKAGE_ADAPTERS` table in the engine's `clausal/sandbox.py`. It is never
in a project's `pyproject.toml`, so a project cannot vouch for itself. Rows are added only by
engine code review, each with a CHANGELOG entry and an operator ruling. Each row pins:

| Field | Example |
|---|---|
| module | `clausal.modules.py.sympy` |
| distribution | `clausal-sympy==<version>` |
| sha256 of the adapter `.py` | of `packages/clausal-sympy/clausal/modules/py/sympy.py` at that version |
| third-party pins | `sympy==1.14.*`, `mpmath==<version>` |
| predicates | an explicit allowlist (`simplify`, `expand`, `factor`, `solve`, `solve_all`, `diff`, `subs`, `sym_equal`, `sym_str`, `sympy_term`, ...) |
| constructors | none: the raw values `pi`, `e`, `inf`, `sin`, ... stay refused. ISO cells such as `log(X)` already convert. |
| importers (optional) | sha256-pinned `.seam` files that may import it, which is the narrowest reading of "imported from package code" |

**Activation.** Opt-in through `enable(allow_package_adapters=["sympy"])` (or an environment
variable the sandbox child sets). It is off by default, and a second `enable()` may only narrow
it.

**Verification at `enable()`, before anything is imported, failing closed:**
1. Resolve the adapter file with `python_bridges._find` and compare its sha256 with the pin.
2. Check the distribution versions with `importlib.metadata`, and that the sympy dist-info
   belongs to the `sympy` package actually on the path. Verifying the RECORD hashes too is
   optional and costs about a second.
3. Refuse if `sys.modules` already holds the module, loaded from a different file.
4. Import it, then add the ids of exactly the listed predicate objects to `allowed_ids`.

**Load time.** In the sandbox checker and `_classify`, a vetted row's origin counts as clean
only for `-import_from` of its listed names. `-import_module(py.sympy)`, a dotted
`py.sympy.x`, and any unlisted name stay routes and are refused. The importing `.seam` must
itself still be Python-free: no `++`, `--`, or Python f-strings. It is never admitted as a
bridge.

**Run time.** `check_adapter` needs no change once the ids are in `allowed_ids`. Do not widen
`permits_python_target` or `walkable` (`sandbox.py:1280/1297`), so dotted access stays refused.

**Not bounded.** SymPy has no in-process CPU or memory limit. `solve`, `integrate` and `limit`
can run without bound, and `sym_equal` may try up to 120 `simplify` calls. The only bound is
the sandbox child's own timeout. Callers must keep one.

## Cost

| Piece | Size |
|---|---|
| `sandbox.py`: the row type, verification, checker branch and `enable` parameter | ~120-150 lines |
| `python_bridges._classify`: the vetted-origin hook | ~10 lines |
| the wrapper: the `sympify` removal | done (`t4-sympy-safety`) |
| tests | ~250 lines |

## What the review must check

- No `sympify`, `parse_expr` or `S()` on any value derived from a term, including string
  fallbacks inside SymPy's own converters that the wrapper reaches.
- No raw Python objects exported; no `SymExpr` method or `__eq__` reachable from a goal.
- The wrapper's imports stay `clausal.*` plus `sympy`. SymPy is trusted by version pin only.
- `sys.modules` pre-seeded before `enable()` (an impostor module).
- The dotted and `-import_module` routes stay refused.
- `++`, `--` and f-strings in the importing `.seam` still go through `python_routes`.
- A second `enable()` only narrows.
- Objects compiled before a narrowing are still checked at run time; mirror `check_constructor`
  (`sandbox.py:789`).

## Test plan

- The eval payload is refused both inside and outside the sandbox (in place, from
  `t4-sympy-safety`).
- The importing `.seam` loads under the sandbox only with matching pins. A wrong sha, a wrong
  sympy version, an impostor in `sys.modules`, or an unlisted importer each refuse it, with
  named errors.
- `-import_from` of an unlisted name (`sym`, `inf`) refuses.
- `py.sympy.simplify` dotted, and `-import_module(py.sympy)`, refuse.
- A `.seam` that imports sympy and also uses `++` refuses.
- Other package adapters (`scipy_*`, ...) still refuse.
- An inverse `solve/3` returns several roots under the sandbox.
- `check_term` still refuses a `SymExpr` passed in through `solve()`.

## Open for the operator

1. Whether the sandbox may admit a package adapter at all, in this form.
2. For a plain cyclic term (`X = f(X)`): the branch makes it a conversion failure
   (`type_error(sympy_expression, _)` from `sympy_term/2`, failure elsewhere), where it used to
   throw `resource_error(stack)`.
