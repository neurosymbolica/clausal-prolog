# Dicts and Sets

Clausal has first-class support for dictionaries and sets as logic terms. Unlike plain Python `dict` and `set`, `DictTerm` and `SetTerm` participate in unification — dict values can contain logic variables that bind during search, and sets unify by element equality.

---

## DictTerm

`DictTerm` is a unification-aware dictionary. Keys must be ground (strings, ints, or other hashable atoms). Values may be logic variables.

### Syntax

In `.clausal` files, Python dict literals `{k: v, ...}` are automatically wrapped as `DictTerm`:

```python
# Fact with a ground dict
point_type({"x": 0, "y": 0}, "origin"),

# Clause head with variable values — X and Y bind on unification
get_x({"x": X, "y": Y_}, X),

# Dict construction in body
make_point(X, Y, P) <- (P is {"x": X, "y": Y})
```

### Unification semantics

Two `DictTerm`s unify iff:

1. They have the **same set of keys**
2. Values for each key unify pairwise

```python
# Succeeds: same keys, values unify
{"a": 1, "b": 2} is {"a": X, "b": Y}   # X=1, Y=2

# Fails: different key sets
not ({"a": 1} is {"b": 1})

# Fails: value mismatch
not ({"a": 1} is {"a": 2})
```

A `DictTerm` does **not** unify with a plain Python `dict` — they are distinct types.

A logic variable unifies with a `DictTerm` by binding to it:

```python
X is {"key": "val"}   # X binds to DictTerm({"key": "val"})
```

### Nested dicts

Dicts can be nested, and unification recurses into nested values:

```python
get_city({"address": {"city": CITY}}, CITY),

# Query:
get_city({"address": {"city": "London"}}, C)   # C = "London"
```

### Head pattern matching

When a `DictTerm` appears in a clause head, the compiler generates a wildcard capture plus a unification guard. The guard:

1. Pre-allocates `Var()` objects for variable positions in the dict values
2. Constructs the expected `DictTerm` with those variables
3. Calls `unify(captured_arg, expected_dict, trail)`

This means dict patterns in heads work bidirectionally — they match incoming `DictTerm` arguments and also bind when the argument is an unbound variable.

### Body construction

Dict literals in clause bodies construct `DictTerm` objects at runtime. Logic variables in values are dereferenced at construction time if bound, or remain as `Var` objects if unbound.

### Backtracking

`DictTerm` unification is fully backtrackable. If a pairwise value unification fails partway through, all bindings made so far are undone via the trail.

---

## SetTerm

`SetTerm` is a unification-aware set. Elements must be ground (hashable). Backed by `frozenset` for immutability.

### Syntax

In `.clausal` files, Python set literals `{a, b, c}` produce `SetTerm` objects when the elements are ground constants:

```python
colors({1, 2, 3}),
primary({"red", "green", "blue"}),
```

### Unification semantics

Two `SetTerm`s unify iff they contain the **same elements** (order irrelevant, since they are sets):

```python
# Succeeds: same elements regardless of order
{1, 2, 3} is {3, 1, 2}

# Fails: different elements
not ({1, 2} is {1, 2, 3})
```

A logic variable unifies with a `SetTerm` by binding to it.

### Variables in sets

**Not supported.** Set elements must be ground because `frozenset` requires hashable elements. A set containing an unbound logic variable would break hashing. For patterns with variable elements, use lists with `In/2` or `gen_set/2` (planned builtins).

---

## The `__unify__` protocol

DictTerm and SetTerm unification is powered by a generic extension point in the C unifier. Any Python object can define a `__unify__(self, other, trail)` method:

- Return `True` — unification succeeded (bindings made on `trail`)
- Return `False` — unification failed
- Return `NotImplemented` — fall through to the default `==` comparison

The C extension calls `__unify__` after checking tuples and lists, before the `==` fallback. Two companion protocols are also supported:

- `__walk__(self)` — called by `walk()` to substitute bound variables inside the term
- `__occurs_check__(self, var)` — called by occurs-check to detect circular references

These protocols allow custom term types to participate in unification without modifying the C extension.

---

## Python API

```python
from clausal.terms import DictTerm, SetTerm

# Construction
d = DictTerm({"x": 1, "y": 2})
s = SetTerm([1, 2, 3])

# Access
d["x"]          # 1
d.keys()        # dict_keys(["x", "y"])
d.values()      # dict_values([1, 2])
d.items()       # dict_items([("x", 1), ("y", 2)])
len(d)          # 2
"x" in d        # True

len(s)          # 3
1 in s          # True
list(s)         # [1, 2, 3] (iteration order unspecified)

# Unification (C-level)
from clausal.logic.variables import Var, Trail, unify, deref

t = Trail()
x = Var()
unify(DictTerm({"a": x, "b": 2}), DictTerm({"a": 42, "b": 2}), t)
deref(x)  # 42
```

---

## Current status

| Feature | Status |
|---|---|
| `DictTerm`/`SetTerm` classes, `__walk__`/`__occurs_check__` hooks, `structural_unify` support | Done |
| `__unify__` protocol in C, AST transform (`visit_Dict` → `DictTerm`), compiler head/body support | Done |
| Dict builtins: `dict_pairs`, `dict_get`, `dict_put`, `dict_merge`, `gen_dict`, `<<` partial matching | Planned |
| Set builtins: `set_union`, `set_intersection`, `set_subtract`, `gen_set`, `is_set` | Planned |
| Mutable variants (`MutableDict`/`MutableSet`) with trail-backed undo | Planned |

---

## Limitations

- **No `**splat` in DictTerm**: `{**old, key: new_val}` (dict unpacking) is not yet supported in term context. This is planned as syntactic sugar for `dict_put`/`dict_merge`.
- **No variable keys**: Dict keys must be ground. `{X: 1}` where `X` is an unbound variable is not supported.
- **No variable set elements**: Set elements must be ground/hashable.
- **No partial dict matching yet**: SWI-style `Select :< From` (sub-dict matching) is not yet implemented.
- **No dict/set builtins yet**: Operations like `dict_get`, `set_union` are not yet implemented.
