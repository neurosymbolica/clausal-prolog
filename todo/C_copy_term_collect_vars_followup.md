# Follow-up issues in _copy_term_impl / _collect_vars_impl (C)

Commit: `perf: move _copy_term and _collect_vars hot paths to C extension`

---

## 1. KWTerm reconstruction is wrong (pre-existing Python bug, faithfully reproduced in C)

Both the original Python `_copy_term` and the new C `c_copy_term` reconstruct a
KWTerm incorrectly:

```python
# Python original (inspection.py, before this commit)
return KWTerm({k: _copy_term(v, var_map) for k, v in term.items()})
# ↑ passes dict as positional `functor` arg → _functor = dict, _fields = {}
```

```c
// C (c_copy_term in _variables.c)
PyObject *result = PyObject_CallOneArg(KWTerm_type, new_dict);
// ↑ KWTerm(new_dict) → same: _functor = new_dict, _fields = {}
```

**What both should do:**
```python
KWTerm(term.functor, **{k: _copy_term(v, var_map) for k, v in term.items()})
```

In C, use `PyObject_Call` with the functor string as first positional arg and
the copied fields as `**kwargs`:
```c
PyObject *functor = PyObject_GetAttrString(term, "functor");
PyObject *result  = PyObject_Call(KWTerm_type, PyTuple_Pack(1, functor), kwargs);
```

**Impact:** If a KWTerm ever reaches `copy_term/2`, the copy has the field dict
as its functor and no fields.  Tests all pass today, suggesting this path is never
exercised.  But it is silently wrong.

**Fix:** Correct both the Python fallback and the C path at the same time.  Add a
test: `copy_term(KWTerm('r', a=X), Y), Y == KWTerm('r', a=_)`.

---

## 2. `PyMapping_Items` for KWTerm in c_copy_term — use `items()` call instead

`c_copy_term` uses `PyMapping_Items(term)` to obtain KWTerm items.
`PyMapping_Items` uses C-level mapping protocol (`mp_subscript` + `keys()`).
KWTerm only implements `keys()`, `values()`, `items()` at Python level; it does
**not** implement `tp_as_mapping->mp_subscript` at C level.  `PyMapping_Items`
falls back to calling `.items()` when subscript is missing, so it works today,
but it is fragile.

`c_collect_vars` and `c_is_ground` both correctly use
`PyObject_CallMethod(term, "values", NULL)`.  `c_copy_term` should use
`PyObject_CallMethod(term, "items", NULL)` + iterator for consistency and safety:

```c
PyObject *items_view = PyObject_CallMethod(term, "items", NULL);
PyObject *iter = PyObject_GetIter(items_view);
Py_DECREF(items_view);
PyObject *pair;
while ((pair = PyIter_Next(iter))) {
    PyObject *k = PyTuple_GET_ITEM(pair, 0);
    PyObject *v = PyTuple_GET_ITEM(pair, 1);
    ...
    Py_DECREF(pair);
}
```

---

## 3. DictTerm and SegList with Vars are silently not copied

`DictTerm` (`clausal.terms.DictTerm`) and `SegList` can contain logic variables,
but neither `c_copy_term` nor `c_collect_vars` handle them.  Both fall through to
"return as-is", meaning:

- `copy_term(dict_term_with_var, Y)` → Y shares the **same** Var as the original
  (not a fresh copy).
- `term_variables(dict_term_with_var, Vs)` → Vs = [] (vars not collected).

This is a **pre-existing gap** in the Python implementations too — they have the
same blind spot.  Impact is likely small given current usage, but worth a test.

---

## 4. No caching of "functor" / "args" interned strings in _variables.c

`c_copy_term` (and the existing `py_functor_name`, `py_arity`, `c_is_ground`)
access Compound fields via `PyObject_GetAttrString(term, "functor")` and
`PyObject_GetAttrString(term, "args")`.  `PyObject_GetAttrString` interns its
string argument each call, but that is still slower than using a pre-interned
`PyObject *` stored at module-init time.

`_tabling_core.c` already caches `str_functor` and `str_args`.  `_variables.c`
should do the same (alongside the existing `str_fields`, `str_name`), then use
`PyObject_GetAttr(term, str_functor)` / `PyObject_GetAttr(term, str_args)`
throughout `c_copy_term`, `c_is_ground`, `py_functor_name`, `py_arity`,
`py_nth_arg`, `py_args_list`.

---

## 5. No inter-extension C code sharing — duplicate traversal logic

`_variables.c`, `_tabling_core.c`, and `_clpfd_propagate.c` all implement
essentially the same term-traversal pattern:

```
var_deref → Var check → primitive check → PredicateMeta class check →
list → Compound → KWTerm → term instance
```

Each extension duplicates:
- `var_deref` (struct layout replication in `_tabling_core.c`)
- `c_is_term_instance` (C version in `_variables.c`, Python-callback version
  in `_tabling_core.c`)
- `c_term_field_names`

**Option A:** Export a shared `_term_helpers.h` header from the `variables`
package and `#include` it in sibling extensions (requires `include_dirs` in
`setup.py`).

**Option B:** Use PyCapsule to expose `var_deref`, `c_is_term_instance`,
`c_term_field_names` as C-callable pointers, imported once at module init by
each extension.

Option B is cleaner for a compiled-package distribution.  Option A is simpler
to prototype.

---

## 6. `_collect_vars_impl` allocates a PyLong per variable for set membership

Each unbound Var encountered in `c_collect_vars` allocates a `PyLong` via
`PyLong_FromVoidPtr(term)` to check / insert into the `seen_ids` set.  For
deep terms with many variables this is `O(n)` allocations that are immediately
discarded.

Alternative: use a C-level hash set (e.g. a small open-addressing table on the
stack/heap using raw `uintptr_t` keys) instead of a Python `set`.  This would
avoid all Python object allocation for the dedup bookkeeping.

This is an optimisation, not a correctness issue.  Measure first before
implementing.
