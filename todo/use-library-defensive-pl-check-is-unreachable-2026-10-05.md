# `_use_library`'s defensive `.pl` check is unreachable

**Filed** 2026-10-05, carried over from the extension-flip checklist (its "Open Low
(review)" note on route 1) when that checklist was retired. Severity: Low. Not a bug.

## What

`clausal/tools/iso_l3_directives._use_library`, under the Clausal Prolog surface, looks up
the source of every mapped library module (`_module_source(mod)`) and refuses it if it is
ISO Prolog (`.pl`):

```python
if names and ctx.surface == _SURFACE_CLAUSAL_PROLOG:
    # A mapped library is engine code today (Python or seam); were
    # one ever a .pl module, Clausal Prolog may not import it.
    found = _module_source(mod)
    if _is_iso_prolog_source(found):
        raise _refused(...)
```

- It is **unreachable today**: every module in `_LIBRARY_MODULES` / `_LIBRARY_OVERRIDES`
  is `.py` or `.seam`.
- It **costs a `find_spec`** per mapped-library import in every `.clausal` file.
- It has **no twin** in the translator's mapped-library branch
  (`clausal/tools/prolog_to_clausal.py`), so the two `.pl` front ends do not agree on it
  if it ever fires.

## Suggested fix

Replace the run-time check with a static test over `_LIBRARY_MODULES` and
`_LIBRARY_OVERRIDES` asserting that no mapped module resolves to a `.pl` file. That keeps
route 1 (Clausal Prolog may not import ISO Prolog) guarded for the library table at no
per-import cost, and covers both front ends at once.
