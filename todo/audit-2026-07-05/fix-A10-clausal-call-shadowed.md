# fix(A10-F013, seam A11): `clausal.call` public API shadowed by builtin call/N class

**Problem.** `clausal/__init__.py` imports the documented query API
(`from clausal.logic.solve import call`) and then `_export_builtin_classes()`
overwrites module attributes with every `_BUILTIN_CLASSES` entry — including
`call` → `<BuiltinClass call/[1..8]>`. The cheat-sheet (§6: `call("ParcelLateFee",
10, N := Var(), module=…)`) and docs/import.md document `clausal.call` as the
query function; actually using it raises
`TypeError: __init__() got an unexpected keyword argument 'module'`.
Check `once`, `solve`, `query` for the same collision class (none collide
today, but nothing prevents a future builtin named `once` — `once` IS a
builtin concept; verify).

**Repro/test.** tests/audit_2026_07_05/test_10_rewriting_import.py::test_F013_clausal_call_is_query_api
(xfail).

**Fix.** In `_export_builtin_classes`, skip names already bound in the module
namespace (`if hasattr(mod, name): continue` — with an explicit allowlist if
some overwrites are intended), or re-assert the solve API after the export
loop. Decide which object `from clausal import call` should be — the docs say
the function.

**Ownership.** `clausal/__init__.py` is A11 (modules-interop) territory —
found from A10 probing; dedupe at A12.
