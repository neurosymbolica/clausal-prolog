# Follow-up issues in _copy_term_impl / _collect_vars_impl (C)

Commit that introduced these: `perf: move _copy_term and _collect_vars hot paths to C extension`

All 6 issues resolved. See commit history for details.

---

## ~~1. KWTerm reconstruction is wrong~~ ✓ DONE

Fixed in: `fix: correct KWTerm reconstruction and items() in c_copy_term; add gap tests`

`c_copy_term` now calls `KWTerm(functor, **fields_dict)` via `PyObject_Call` with
the functor string as the first positional arg and the copied fields as kwargs.
Tests added in `TestCopyTermKWTerm`.

---

## ~~2. `PyMapping_Items` for KWTerm~~ ✓ DONE

Fixed in same commit as #1.

`PyMapping_Items(term)` replaced with `PyObject_CallMethod(term, "items", NULL)`
+ `PyIter_Next` loop, consistent with `c_collect_vars` and `c_is_ground`.

---

## ~~3. DictTerm and SegList with Vars are silently not copied~~ ✓ DONE (gap documented)

Fixed in same commit as #1.

Tests added documenting current fall-through behaviour:
`TestCopyTermDictTerm`, `TestTermVariablesDictTerm`,
`TestCopyTermSegList`, `TestTermVariablesSegList`.

---

## ~~4. No caching of "functor" / "args" interned strings~~ ✓ DONE

Fixed in: `perf: cache str_functor/str_args and use C hash set in _collect_vars; add todo`

`str_functor` and `str_args` added alongside `str_fields`/`str_name`.
11 `PyObject_GetAttrString` call sites replaced with `PyObject_GetAttr`.

---

## ~~5. No inter-extension C code sharing~~ ✓ DONE (written as separate todo)

Documented in: `todo/C_variables_capi_consolidation.md` (same commit as #4)

`_tabling_core.c` replicates `VarObject` struct layout and calls
`c_is_term_instance`/`c_term_field_names` via Python function objects despite
`_variables.c` already exporting them as C function pointers via its capsule.
The fix is tracked in the new todo file.

---

## ~~6. `_collect_vars_impl` allocates a PyLong per variable~~ ✓ DONE

Fixed in same commit as #4.

New `UIntSet` (open-addressing hash set over `uintptr_t` keys) replaces the
Python `set` passed as `seen_ids`. `c_collect_vars` takes `UIntSet *seen`;
`py_collect_vars_impl` manages the set internally. Callers drop the `set()` arg.
