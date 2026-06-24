# BUG: a .clausal module that imports a Python-backed module can't be transitively imported

> **RESOLVED 2026-06-24** — fix in `clausal/import_hook.py` (`_ensure_source_modules_on_path`),
> regression test `tests/test_transitive_py_module_import.py`. Root cause below.
>
> ## Root cause (the "transitive" framing was incidental)
>
> The distinguishing variable is **not** transitivity — it is whether the clausal **source** tree is on
> `sys.path`. `clausal_torch` / `clausal_jax` are installed *non-editably* and drop bare `.py` files into
> `site-packages/clausal/modules/` with **no `__init__.py`**, making that directory a PEP 420 namespace
> portion. When a process runs from a cwd that does not put the source tree on `sys.path` (the normal
> rulebase + separate-test-harness shape), the stdlib `PathFinder` resolves `clausal.modules` to that
> site-packages portion **before** the editable finder is consulted — and that portion lacks the
> source-only `py/` subpackage. So `from clausal.modules.py.datetime import …` fails with
> `No module named 'clausal.modules.py'`. (`clausal.testing`/`clausal.import_hook` still resolve to source
> because they don't exist in site-packages, so `PathFinder` falls through to the editable finder; but
> `clausal.modules` *does* exist there, so it wins. That asymmetry is the bug.) `clausal.modules.py` was a
> **correct** name all along — the reporter's "literal `.py` appended" guess was wrong.
>
> Both *direct* and *transitive* py-backed imports fail under the affected resolution; the original repro
> happened to compare plain-vs-py-backed (both 2-level), not direct-vs-transitive.
>
> ## Fix
>
> `clausal/import_hook.py` now splices the canonical source `clausal/modules` directory onto
> `clausal.modules.__path__` at hook-install time (the hook itself always loads from source, so it can
> locate the directory relative to `__file__`). This makes the `py/` subpackage — and the bare source
> modules `graphs`/`imperial`/`prolog`/`units` — discoverable regardless of cwd, for **all** Python-backed
> wrappers (date_time, regex, json, os, …), confirmed for date_time and regex.
>
> ---
>
> *Original report follows.*

**Reported 2026-06-24** (found while formalizing the SARA IRC tax domain for the Clausify project; the
rulebase had to avoid `-import_from(date_time, ...)` and use `++` over `datetime` instead so it stayed
importable by its test harness).

## Symptom

If module **A** (`a.clausal`) does `-import_from(date_time, [...])` (or any Python-backed
`clausal.modules.*` module), and module **B** (`b.clausal`) then does `-import_from(a, [...])`, loading **B**
fails at load time with:

```
<load> — No module named 'clausal.modules.py'
```

The bogus name `clausal.modules.py` (a literal `.py` appended to a dotted module path) points at a
path/name-construction bug in the import hook when it follows a transitive import whose target re-exports
from a Python-backed module under `clausal/modules/`.

Direct use is fine — a file that imports `date_time` and uses it **itself** works (verified elsewhere). The
failure is specifically the **transitive** case (B imports A imports date_time).

## Minimal repro

`todo/transitive-import-repro/` (run from that dir, `source /workspace/clausal/venv/bin/activate`):

- **Control — PASSES.** `use_plain.clausal` imports `mod_plain.clausal` (no Python-backed import):
  ```
  python -m clausal.testing use_plain.clausal   →  1 passed
  ```
- **Trigger — FAILS.** `use_dt.clausal` imports `mod_dt.clausal`, which does `-import_from(date_time, [Date, DateDiff])`:
  ```
  python -m clausal.testing use_dt.clausal      →  <load> — No module named 'clausal.modules.py'
  ```

`mod_dt.clausal`:
```clausal
-import_from(date_time, [Date, DateDiff])
days_between(Y1,M1,D1, Y2,M2,D2, N) <- (
    Date(Y1,M1,D1, S), Date(Y2,M2,D2, E), DateDiff(E, S, TD), N is ++TD.days)
```
`use_dt.clausal`:
```clausal
-import_from(mod_dt, [days_between])
Test("transitive import of a date_time module") <- (days_between(2026,1,1, 2026,4,1, N), N == 90)
```

## Scope

- Confirmed with `date_time`. The error string (`clausal.modules.py`) suggests it is **not** specific to
  `date_time` but affects **any Python-backed `clausal.modules.*` module** re-exported across a `.clausal`
  module boundary (regex, json, os, …) — please confirm. Plain `.clausal`→`.clausal` transitive imports are
  unaffected (control passes).

## Impact

- Forces multi-file rulebases that need stdlib-backed features (dates, regex, json, …) to either inline the
  Python via `++(...)` or collapse to a single file. For the SARA formalization the workaround was native
  `++` over `datetime.date`, which is equivalent — but the limitation is a sharp edge for any modular
  rulebase + separate test-harness layout, which is the normal shape.

## Workaround

Use `++(...)` over the underlying Python object instead of `-import_from(date_time, ...)`, OR keep the
Python-backed import in the same file that is loaded directly (don't put it behind a transitive import).
