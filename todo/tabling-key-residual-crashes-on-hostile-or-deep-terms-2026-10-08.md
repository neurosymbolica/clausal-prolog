# Tabling key: residual crashes on hostile or very deep terms

Opened 2026-10-08, after the two crash-fix rounds on the variant key (535f9285, d9586317). Every case
below crashes or misbehaves on 83457c29 too: none is a regression, and none is reachable from a
plain `.clausal` program without a Python object that misbehaves on purpose or a partial list nested
tens of thousands deep. They are recorded so the next pass on `do_normalize` starts from them.

## 1. `SegList.__walk__` overflows the C stack on very deep nesting

A partial list nested ~49,000 x 2 deep segfaults inside `SegList.__walk__`, before the key is
reached. `SEG_MAX_DEPTH` stops the key's own recursion; the walk has no bound of its own.
Fix: give the walk an explicit stack (or a depth check that raises `RecursionError`).

## 2. `do_normalize` borrows the dereferenced term

```c
term = VarAPI->deref(term);     /* borrowed */
```

The term is then used across calls back into Python (`__class__`, a dataclass field getter, the
registered `_seg_key`). If that Python code undoes the trail (`trail.undo`), the binding that held
the term goes, the term can be freed, and the next access reads freed memory (SIGSEGV on a tuple).
Fix: `Py_INCREF` the dereferenced term on entry and release it on every exit path.

## 3. Re-entry through a dataclass field getter restarts the depth

The dataclass branch calls `PyObject_GetAttr` for each field. A field getter that itself tables a
call re-enters `make_subgoal_key`, which starts at `seg_depth_base`, not at the depth reached, so
each re-entry gets a fresh `MAX_DEPTH` of C stack and a deep enough chain overflows. The `_seg_key`
branch already carries the depth (`seg_depth_base = depth + SEG_LAYER_COST`); the field-getter
branch should do the same.

## 4. A partial list whose tail is bound to `()` or bytes

`_seg_key` on a partial list whose open tail was later bound to the nil cell `()` or to a `bytes`
value raises `PartialTermError` instead of keying as the closed list. `()` and `b""` are spellings
of `[]` (`atoms.is_nil`), so these should key like `[]`, and a non-empty bytes tail like its codes.

## Tests

Each case needs a subprocess test (a crash must fail the test, not the run), in the style of
`_child(src)` in `tests/test_tabling_char_and_code_list_key.py`.

## Also pre-existing, found reviewing the text fast paths (2026-10-08), both Low

- `_head_list_unify_output` (C) reads `var_vals` / `after_vals` with `PyList_GET_SIZE` and no type
  check: called directly with a tuple it segfaults. Compiled code always passes lists, so it is
  unreachable from a program; a `PyList_Check` at entry would make it a TypeError.
- The C and Python twins of the head-list helpers disagree on str SUBCLASSES: C tests
  `PyUnicode_Check`, Python `type(x) is str`, so `[S("a")|"cd"]` builds a carrier in C and a list in
  Python. Pick one (exact `str`, as `is_char_atom` says) and align the C side.
