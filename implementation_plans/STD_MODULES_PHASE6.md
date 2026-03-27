# Std Modules Phase 6 — User-Facing Attributed Variables

**Status: COMPLETE**

**Depends on:** C extension AttVar infrastructure (already complete), CLP(FD)/CLP(B)/dif/units
all use it internally.

**Goal:** Expose the attributed variable API as user-callable builtins so that
users can build custom constraint solvers in `.clausal` files. The internal
infrastructure is mature — CLP(FD), CLP(B), CLP(R), dif/2, and units all use
it. This phase adds the public-facing predicates.

**Non-goal:** Redesigning the attr infrastructure. The existing C extension
`put_attr`/`get_attr`/`del_attr`/`register_attr_hook` is correct and
well-tested. We only add builtin wrappers.

---

## Design Principles

1. **Thin wrappers over the C extension.** Each builtin calls the
   corresponding C function (`put_attr`, `get_attr`, `del_attr`) directly.
   No new data structures, no new trail mechanisms.

2. **String keys.** All attribute keys are strings, matching the existing
   convention (`"fd"`, `"real"`, `"dif"`, `"units"`, `"b"`). Users choose
   their own string keys for custom constraints.

3. **Hook registration stays in Python.** `register_attr_hook(key, fn)` is
   a module-load-time operation — it must happen before any unification
   triggers hooks. Exposing this as a `.clausal` predicate would be fragile
   (timing-dependent). Instead, users write their hook function in Python
   and register it via the import hook or a companion `.py` file. The
   `.clausal` predicates handle get/put/del only.

4. **Clausal naming conventions.** Scryer uses `put_attr/3`, `get_attr/3` —
   we use `put_attr/3`, `get_attr/3`. The overview mentions `PutAtts/2`,
   `GetAtts/2` (plural, Scryer-style multi-attr operations) — we provide
   both the singular (per-key) and plural (all-attrs) variants.

---

## Predicates

### Core (per-key)

| Predicate | Description |
|---|---|
| `put_attr/3` | `put_attr(Var, Key, Value)` — attach attribute Value under string Key to Var. Var must be an unbound variable. Key must be a ground string. Trailed for backtracking. |
| `get_attr/3` | `get_attr(Var, Key, Value)` — retrieve the attribute stored under Key. Fails if Var has no attribute for Key. Unifies Value with the stored attribute. |
| `del_attr/2` | `del_attr(Var, Key)` — remove the attribute under Key from Var. Succeeds even if no attribute existed. Trailed for backtracking. |

### Bulk (all attrs)

| Predicate | Description |
|---|---|
| `get_attrs/2` | `get_attrs(Var, Attrs)` — unify Attrs with a `DictTerm` of all attributes on Var. Empty DictTerm if no attributes. |
| `put_attrs/2` | `put_attrs(Var, Attrs)` — set multiple attributes from a `DictTerm`. Each key-value pair is applied via `put_attr`. |

### Inspection

| Predicate | Description |
|---|---|
| `attvar/1` | `attvar(Var)` — succeeds if Var is an unbound variable with at least one attribute. Fails for bound terms and for bare (non-attributed) variables. |
| `term_attvars/2` | `term_attvars(Term, Vars)` — collect all attributed variables occurring in Term into a list. Traverses compound terms, lists, and PredicateMeta instances recursively. |

---

## Implementation Details

### `put_attr/3`

```python
@_builtin("put_attr", 3)
def _put_attr__3(var, key, value, trail, k):
    var_d = deref(var)
    key_d = deref(key)
    if not is_var(var_d):
        return  # must be unbound
    if is_var(key_d) or not isinstance(key_d, str):
        return  # key must be ground string
    put_attr(var_d, key_d, deref(value), trail)
    yield None
```

### `get_attr/3`

```python
@_builtin("get_attr", 3)
def _get_attr__3(var, key, value, trail, k):
    var_d = deref(var)
    key_d = deref(key)
    if not is_var(var_d):
        return  # must be unbound var
    if is_var(key_d) or not isinstance(key_d, str):
        return
    attr = get_attr(var_d, key_d)
    if attr is None:
        return  # no such attribute → fail
    if unify(value, attr, trail):
        yield None
```

### `del_attr/2`

```python
@_builtin("del_attr", 2)
def _del_attr__2(var, key, trail, k):
    var_d = deref(var)
    key_d = deref(key)
    if not is_var(var_d):
        return
    if is_var(key_d) or not isinstance(key_d, str):
        return
    del_attr(var_d, key_d, trail)
    yield None
```

### `get_attrs/2`

```python
@_builtin("get_attrs", 2)
def _get_attrs__2(var, attrs, trail, k):
    var_d = deref(var)
    if not is_var(var_d):
        return
    # Access the internal attrs dict (C-level)
    raw = var_d.attrs if hasattr(var_d, 'attrs') else {}
    result = DictTerm(dict(raw or {}))
    if unify(attrs, result, trail):
        yield None
```

Note: Accessing `var_d.attrs` requires checking how the C extension exposes
the attrs dict. If not directly accessible, we iterate known keys or add a
`get_all_attrs(var)` C helper.

### `put_attrs/2`

```python
@_builtin("put_attrs", 2)
def _put_attrs__2(var, attrs, trail, k):
    var_d = deref(var)
    attrs_d = deref(attrs)
    if not is_var(var_d):
        return
    if isinstance(attrs_d, DictTerm):
        data = attrs_d.data
    elif isinstance(attrs_d, dict):
        data = attrs_d
    else:
        return
    for key, value in data.items():
        if not isinstance(key, str):
            return
        put_attr(var_d, key, deref(value), trail)
    yield None
```

### `attvar/1`

```python
@_builtin("attvar", 1)
def _is_att_var__1(var, trail, k):
    var_d = deref(var)
    if is_var(var_d):
        raw = var_d.attrs if hasattr(var_d, 'attrs') else None
        if raw:
            yield None
```

### `term_attvars/2`

```python
@_builtin("term_attvars", 2)
def _term_attributed_variables__2(term, vars_list, trail, k):
    seen = set()
    result = []
    _collect_attvars(deref(term), seen, result)
    if unify(vars_list, result, trail):
        yield None

def _collect_attvars(term, seen, result):
    if is_var(term):
        vid = id(term)
        if vid not in seen:
            seen.add(vid)
            raw = term.attrs if hasattr(term, 'attrs') else None
            if raw:
                result.append(term)
        return
    if isinstance(term, list):
        for item in term:
            _collect_attvars(deref(item), seen, result)
    elif is_term_instance(term):
        for f in term_field_names(term):
            _collect_attvars(deref(getattr(term, f)), seen, result)
    elif isinstance(term, Compound):
        for arg in term.args:
            _collect_attvars(deref(arg), seen, result)
```

---

## C Extension Check: `attrs` Accessibility

The C extension stores attributes in `AttVarObject->attrs` (a PyObject dict
pointer). We need to verify whether this is exposed as a Python-level
attribute. Options:

1. **Already exposed**: If `var.attrs` works from Python, `get_attrs` can
   read it directly.
2. **Not exposed**: Add a `get_all_attrs(var) -> dict | None` function to the
   C extension, or expose `attrs` as a read-only property.

Investigation needed at implementation time. Fallback: iterate over known
keys (`"fd"`, `"real"`, `"dif"`, `"units"`, `"b"`, plus any user keys).

`get_attrs` returns a `DictTerm` (not a pair list) — consistent with how
clausal uses DictTerm for JSON objects, CSV records, and ProcessCreate results.
`put_attrs` accepts a `DictTerm` or plain Python dict.

---

## Hook Registration Pattern for User Constraints

Users who want custom constraint propagation write a Python companion module:

```python
# my_constraint.py
from clausal.logic.variables import register_attr_hook, put_attr, get_attr, deref, is_var

MY_KEY = "my_constraint"

def _my_hook(attr_value, bound_to, trail):
    """Called when a variable with my_constraint attr is unified."""
    bound_to = deref(bound_to)
    # ... check constraint, propagate, return True/False
    return True

register_attr_hook(MY_KEY, _my_hook)
```

Then in `.clausal`:

```clausal
-import_from(attributes, [put_attr, get_attr, attvar])

my_constrain(X, BOUND) <- put_attr(X, "my_constraint", BOUND)
```

This pattern matches how CLP(FD), CLP(B), dif, and units work — hook
registration in Python, attr manipulation via predicates.

---

## Test Plan (~30 tests)

### put_attr/3 (~5 tests)
- Put attr on unbound var, then get_attr succeeds.
- Put attr on bound term → fails.
- Key must be ground string (unbound key fails).
- Overwrite existing attr.
- Backtracking undoes put_attr (trail check).

### get_attr/3 (~5 tests)
- Get existing attr → unifies value.
- Get non-existent attr → fails.
- Get from non-var → fails.
- Unification of value (e.g. get_attr(V, "k", 42) checks equality).
- Get after attr deleted → fails.

### del_attr/2 (~3 tests)
- Delete existing attr, then get_attr fails.
- Delete non-existent attr → succeeds (no-op).
- Backtracking undoes del_attr.

### get_attrs/2 (~3 tests)
- Var with two attrs → DictTerm with 2 entries.
- Var with no attrs → empty DictTerm.
- Non-var → fails.

### put_attrs/2 (~3 tests)
- Put multiple attrs via DictTerm, verify each with get_attr.
- Empty DictTerm → succeeds (no-op).
- Non-dict argument → fails.

### attvar/1 (~3 tests)
- Var with attr → succeeds.
- Bare var (no attrs) → fails.
- Bound term → fails.

### term_attvars/2 (~5 tests)
- Simple var with attr → [Var].
- List containing mix of att-vars and plain vars → correct subset.
- Compound term with nested att-vars.
- No att-vars → empty list.
- Same var appearing multiple times → listed once.

### Integration (~5 tests)
- put_attr + CLP(FD) attr coexist on same variable.
- User attr survives through unification (hook not registered → attr stays).
- Custom hook rejects unification (hook returns False).
- Round-trip: put_attr, bind var, hook fires, verify.

---

## File Summary

### New files

| File | Purpose |
|---|---|
| `clausal/logic/builtins/attributes.py` | put_attr, get_attr, del_attr, get_attrs, put_attrs, attvar, term_attvars |
| `tests/test_attributes.py` | Attributed variable builtin tests (~30) |

### Modified files

| File | Change |
|---|---|
| `clausal/logic/builtins/__init__.py` | Add attributes module to docstring |
| `docs/builtins.md` | Add Attributed Variables section |
| `implementation_plans/STD_MODULES_OVERVIEW.md` | Mark Phase 6 complete, link plan |

### Possibly modified

| File | Change |
|---|---|
| `clausal/logic/variables/_variables.c` | May need `get_all_attrs()` or `attrs` property if not already exposed |

---

## Implementation Order

1. **Check C extension `attrs` accessibility** — determine if `var.attrs` is
   readable from Python. If not, add minimal C helper.
2. **Core predicates** — put_attr/3, get_attr/3, del_attr/2 (simplest, no
   traversal).
3. **Bulk predicates** — get_attrs/2, put_attrs/2.
4. **Inspection** — attvar/1, term_attvars/2.
5. **Tests** — all ~30 tests including integration with existing constraints.
6. **Docs** — update builtins.md.

Estimated total: 7 predicates, ~30 tests.
