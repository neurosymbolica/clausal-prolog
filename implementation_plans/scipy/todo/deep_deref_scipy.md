# ~~Add _deep_deref to scipy wrappers~~ DONE

`_deep_deref()` was introduced in `clausal/modules/py/torch.py` during
Phase 1 to recursively unwrap Var objects inside lists and dicts before
passing them to Python functions. The scipy wrappers (`scipy_spatial.py`,
`scipy_sparse.py`, etc.) have their own `_pure()` helpers that do NOT
call `_deep_deref()`.

This means if a Clausal user passes a list or dict containing bound
variables to a scipy predicate, the underlying scipy function receives
`AttVar` objects instead of plain values — same bug that Phase 1 found
for torch.

## Affected files

Every `_pure()` definition in `clausal/modules/py/`:
- `scipy_spatial.py` (line 225)
- `scipy_sparse.py` (line 256)
- Any other scipy module with its own `_pure()`

## Fix

Either:
1. Add `_deep_deref()` to each file's `_pure()` helper
2. Extract `_pure()` and `_deep_deref()` into a shared utility (see
   `todo/shared_pure_helper.md`)

## Resolution

Fixed by extracting `_pure()` (with `_deep_deref`) into
`clausal/modules/py/_helpers.py`. Both scipy_spatial.py and scipy_sparse.py
now import the shared `_pure` which uses `_deep_deref` automatically.
