# Module-qualified atoms (module.atom) don't resolve as VALUES, only as calls

**Found:** 2026-07-03, designing module-prefixed value atoms (`currency.euro`,
`vat_category.standard`) for the EU corpus — the namespacing scheme in the corpus authoring
plan. Exported atoms + `-import_module` are NOT enough: the dotted form works only in CALL
position.

**FIXED:** 2026-07-03 (branch `fix/qualified-atoms-term-position`). See "Resolution" below.

## Repro
```clausal
# currency.clausal
-module(currency, [euro, us_dollar])
```
```clausal
# consumer.clausal
-module(consumer, [is_euro(P)])
-import_from(vocab_lib, [profile_get, profile_has, attr])
-import_module(currency)
-strict_atoms
-private([currency_key])
is_euro(P) <- (profile_get(P, currency_key, currency.euro))   # currency.euro in TERM position
```
Loads OK, but at solve time the qualified atom did not resolve to the module's exported atom.

## Root cause (CORRECTED after investigation)
The original hypothesis ("lowered to bare `euro`, undeclared") was **not** what happens in the
value path. The real cause: `term_to_ast_expr`
(`clausal/logic/compiler/terms_to_ast.py`) had a case for a bare `LoadName` (line ~126, emits a
`Name` resolved via the compiled function's globals) but **no case for a bare (non-`Call`)
`LoadAttr`**. So a `module.atom` reference used as a VALUE fell through to the generic
term-instance constructor and was re-emitted as a runtime `LoadAttr(object=<module>, attr='euro')`
*reflection node* — which of course never unifies with the actual atom.

Minimal proof: `A is currency.euro` bound `A` to `LoadAttr(object=<module currency>, attr='euro')`,
with `A is cur.euro → False`. Both fact-arg (value) and fact-head positions were affected.

The qualified CALL path already worked because `term_to_ast_expr`'s `Call`+`LoadAttr` branch used
`_dotted_name_from_loadattr`; only the value path was missing.

## Resolution
Added a bare-`LoadAttr` case to `term_to_ast_expr`, right after the `LoadName` case, that lowers
`module.atom` to the equivalent Python attribute-access expression (`currency.euro`) via
`_dotted_name_from_loadattr` — mirroring the qualified-call branch. At runtime the
`-import_module`'d module object (already in the compiled function's globals) yields its exported
atom, so the qualified form is now identity-equal to the imported-bare atom.

Verified: `currency.euro` in term position `is cur.euro → True`. Tests added in
`tests/test_module_imports.py::TestQualifiedValueAtoms` (body-position unify + head-position
construction), fixtures `qualified_atom_vocab.clausal` / `qualified_atom_consumer.clausal`.
Full suite: 8255 passed, 0 failures.

## Contrast — these already worked (and still do)
- `currency.euro` in CALL position (like `clpq.rational(...)`) — `-import_module` for qualified calls.
- Imported bare: `-import_from(currency, [euro])` then reference `euro` — shared identity.
- From Python, `currency_mod.euro` yields the atom.

## Separate issue discovered AND fixed (same session)
Building a QUERY *in Python* from a foreign atom — e.g. `solve(consumer.p(currency_mod.euro))` —
raised `NameError: name 'euro' is not defined`. Different code path: the query template lowered a
zero-arity `PredicateMeta` atom via `term_to_ast_expr`'s `PredicateMeta and not _fields` case → a
bare `Name(atom.__name__)`, which fails when the atom is foreign (its bare name isn't in that
function's globals — e.g. `-import_module` only, no `-import_from`).

**Root cause:** `_templatize_query_goal._ground_value` (`clausal/logic/solve.py`) parameterized only
scalar literals `(int, float, complex, bool, str, bytes)`, so an atom arg stayed baked into the
compiled query as a bare name instead of being passed as a bound parameter.

**Fix:** extended `_ground_value` to also parameterize zero-arity atoms (`is_atom(dv)`). The atom
*object* is now passed in as a bound arg (identity preserved; runtime first-arg indexing still keys
off the bound value), so no bare name is emitted. Test:
`test_query_from_python_with_cross_module_atom` + fixture
`qualified_atom_import_module_only.clausal`. Full suite: 8256 passed, 0 failures.

## Why it mattered
The corpus wants language-neutral, namespaced VALUE atoms (`currency.euro`, `country.uk`,
`vat_category.standard`) — brevity, one definition per value, typo-safety under `-strict_atoms`,
and a clean translation key. The `-import_from` workaround is no longer required for the value use
site.
