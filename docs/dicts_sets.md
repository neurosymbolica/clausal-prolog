# Dicts and Sets

Clausal has first-class support for dictionaries and sets as logic terms. Unlike plain Python `dict` and `set`, `DictTerm` and `SetTerm` participate in unification — dict values can contain logic variables that bind during search, and sets unify by element equality.

---

## DictTerm

`DictTerm` is a unification-aware dictionary. Keys must be ground (strings, ints, or other hashable atoms). Values may be logic variables.

### Syntax

in_ [`.clausal` files](syntax.md), Python dict literals `{k: v, ...}` are automatically wrapped as `DictTerm`:

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

when a `DictTerm` appears in a clause head, the compiler generates a wildcard capture plus a unification guard. The guard:

1. Pre-allocates `Var()` objects for variable positions in the dict values
2. Constructs the expected `DictTerm` with those variables
3. Calls `unify(captured_arg, expected_dict, trail)`

This means dict patterns in heads work bidirectionally — they match incoming `DictTerm` arguments and also bind when the argument is an unbound variable.

### Body construction

Dict literals in clause bodies construct `DictTerm` objects at runtime. Logic variables in values are dereferenced at construction time if bound, or remain as `Var` objects if unbound.

### Splat sugar

Python's dict unpacking syntax `{**old, "k": v}` is supported in clause bodies. It constructs a new `DictTerm` by merging:

```python
# Add or overwrite a key
update_name(OLD, NAME, NEW) <- (NEW is {**OLD, "name": NAME})

# Merge two dicts (right side wins on conflict)
merge_defaults(DEFAULTS, OVERRIDES, RESULT) <-
    (RESULT is {**DEFAULTS, **OVERRIDES})
```

This compiles to `DictTerm({**deref(OLD).data, "name": NAME})` at runtime. The splat argument must be a bound `DictTerm` at call time.

### Partial dict matching — `sub_dict/2`

`sub_dict(Pattern, Dict)` succeeds when `Pattern`'s keys are a subset of `Dict`'s keys and the values for those keys unify pairwise. Extra keys in `Dict` are ignored.

```python
# Extract the name field from any dict
get_name(PERSON, NAME) <- sub_dict({"name": NAME}, PERSON)

# Check role without caring about other fields
is_admin(PERSON) <- sub_dict({"role": "admin"}, PERSON)
```

Compare with full unification:

```python
# Full unification: PERSON must have EXACTLY these two keys
exact(PERSON, NAME) <- (PERSON is {"name": NAME, "role": "admin"})

# Partial match: PERSON may have any other keys
partial(PERSON, NAME) <- sub_dict({"name": NAME, "role": "admin"}, PERSON)
```

### Backtracking

`DictTerm` unification is fully backtrackable. If a pairwise value unification fails partway through, all bindings made so far are undone via the trail. See [Lists](lists.md) for the set operations available on plain lists.

---

## SetTerm

`SetTerm` is a unification-aware set. Elements must be ground (hashable). Backed by `frozenset` for immutability.

### Syntax

in_ `.clausal` files, Python set literals `{a, b, c}` produce `SetTerm` objects when the elements are ground constants:

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

**Not supported.** Set elements must be ground because `frozenset` requires hashable elements. A set containing an unbound logic variable would break hashing. For patterns with variable elements, use `gen_set/2` to enumerate elements.

---

## Dict builtins

All dict builtins are in `clausal/logic/builtins/dict_set.py`. They use `DictTerm` for all dict arguments — plain Python dicts are not accepted.

### `is_dict/1`
```clausal
# skip
is_dict(+Term)
```
Succeeds if `Term` is a `DictTerm`.

### `dict_size/2`
```clausal
# skip
dict_size(+Dict, -N)
```
`N` is the number of keys in `Dict`.

### `dict_keys/2`
```clausal
# skip
dict_keys(+Dict, -Keys)
```
`Keys` is the sorted list of keys. Keys are sorted by `repr` for determinism across key types.

### `dict_values/2`
```clausal
# skip
dict_values(+Dict, -Values)
```
`Values` is the list of values in key-sorted order (same ordering as `dict_keys`).

### `dict_pairs/2`
```clausal
# skip
dict_pairs(?Dict, ?Pairs)
```
Bidirectional conversion between a `DictTerm` and a list of `[Key, Value]` 2-element lists.

```python
# Dict → pairs
dict_pairs({"a": 1, "b": 2}, PAIRS)
# PAIRS = [["a", 1], ["b", 2]]  (sorted by key)

# Pairs → dict
dict_pairs(DICT, [["x", 10], ["y", 20]])
# DICT = DictTerm({"x": 10, "y": 20})
```

### `dict_get/3`
```clausal
# skip
dict_get(+Key, +Dict, ?Value)
```
Semidet: succeeds if `Key` is in `Dict` and `Value` unifies with `Dict[Key]`. Fails if the key is absent or `Key` is unbound.

```python
dict_get("name", {"name": "Alice", "age": 30}, NAME)
# NAME = "Alice"
```

### `dict_put/4`
```clausal
# skip
dict_put(+Key, +Value, +OldDict, -NewDict)
```
`NewDict` is `OldDict` with `Key → Value` inserted or overwritten. Returns a new `DictTerm`; the original is unchanged.

```python
dict_put("b", 99, {"a": 1, "b": 0}, NEW)
# NEW = DictTerm({"a": 1, "b": 99})
```

### `dict_put_pairs/3`
```clausal
# skip
dict_put_pairs(+Pairs, +OldDict, -NewDict)
```
Bulk update: `Pairs` is a list of `[Key, Value]` 2-element lists. equivalent to calling `dict_put/4` for each pair in order.

```python
dict_put_pairs([["b", 2], ["c", 3]], {"a": 1}, NEW)
# NEW = DictTerm({"a": 1, "b": 2, "c": 3})
```

### `dict_remove/3`
```clausal
# skip
dict_remove(+Key, +OldDict, -NewDict)
```
`NewDict` is `OldDict` without `Key`. Fails if `Key` is not present.

```python
dict_remove("b", {"a": 1, "b": 2, "c": 3}, NEW)
# NEW = DictTerm({"a": 1, "c": 3})
```

### `dict_merge/3`
```clausal
# skip
dict_merge(+D1, +D2, -Merged)
```
`Merged` is the union of `D1` and `D2`. Where keys conflict, `D2`'s value wins.

```python
dict_merge({"a": 1, "b": 0}, {"b": 99, "c": 3}, MERGED)
# MERGED = DictTerm({"a": 1, "b": 99, "c": 3})
```

### `gen_dict/3`
```clausal
# skip
gen_dict(?Key, +Dict, ?Value)
```
Nondeterministic: on backtracking, enumerates all key-value pairs in `Dict`. equivalent to SWI's `gen_assoc/3`.

```python
# Enumerate all pairs
gen_dict(KEY, {"a": 1, "b": 2}, VALUE)
# → KEY="a", VALUE=1
# → KEY="b", VALUE=2 (on backtrack)

# include by key
gen_dict("a", {"a": 1, "b": 2}, VALUE)
# → VALUE=1 (only one solution)
```

### `sub_dict/2`
```clausal
# skip
sub_dict(+Pattern, +Dict)
```
Partial dict matching: succeeds when every key in `Pattern` is also in `Dict`, and the corresponding values unify. Extra keys in `Dict` are ignored.

```python
sub_dict({"name": NAME}, {"name": "Alice", "age": 30})
# → NAME = "Alice"

sub_dict({"role": "admin"}, {"name": "Bob", "role": "admin", "dept": "eng"})
# → succeeds

sub_dict({"role": "admin"}, {"name": "Alice", "role": "user"})
# → fails (value mismatch)

sub_dict({"z": 1}, {"x": 1, "y": 2})
# → fails (key absent)
```

---

## Set builtins

### `is_set/1`
```clausal
# skip
is_set(+Term)
```
Succeeds if `Term` is a `SetTerm`.

### `set_size/2`
```clausal
# skip
set_size(+Set, -N)
```
`N` is the cardinality of `Set`.

### `set_list/2`
```clausal
# skip
set_list(?Set, ?List)
```
Bidirectional conversion between a `SetTerm` and a sorted list.

```python
# Set → list (sorted)
set_list({3, 1, 2}, LIST)  # LIST = [1, 2, 3]

# List → set (duplicates removed)
set_list(SET, [1, 1, 2])   # SET = SetTerm({1, 2})
```

### `set_union/3`
```clausal
# skip
set_union(+S1, +S2, -union)
```
`union` is the set union of `S1` and `S2`.

### `set_intersection/3`
```clausal
# skip
set_intersection(+S1, +S2, -Inter)
```
`Inter` is the set intersection of `S1` and `S2`.

### `set_subtract/3`
```clausal
# skip
set_subtract(+S1, +S2, -Diff)
```
`Diff` is `S1` minus `S2` (elements in `S1` not in `S2`).

### `set_sym_diff/3`
```clausal
# skip
set_sym_diff(+S1, +S2, -Sym)
```
`Sym` is the symmetric difference of `S1` and `S2` (elements in exactly one of the two sets).

### `set_subset/2`
```clausal
# skip
set_subset(+Sub, +Super)
```
Succeeds if every element of `Sub` is also in `Super`. An empty set is a subset of any set.

### `set_disjoint/2`
```clausal
# skip
set_disjoint(+S1, +S2)
```
Succeeds if `S1` and `S2` have no elements in common.

### `set_add/3`
```clausal
# skip
set_add(+Elem, +OldSet, -NewSet)
```
`NewSet` is `OldSet` with `Elem` added. If `Elem` is already present, `NewSet = OldSet`.

### `set_remove/3`
```clausal
# skip
set_remove(+Elem, +OldSet, -NewSet)
```
`NewSet` is `OldSet` with `Elem` removed. If `Elem` is absent, `NewSet = OldSet`.

### `gen_set/2`
```clausal
# skip
gen_set(?Elem, +Set)
```
Nondeterministic: on backtracking, enumerates all elements of `Set` in a deterministic order (sorted by `repr`).

```python
gen_set(ELEM, {"a", "b", "c"})
# → ELEM="a", ELEM="b", ELEM="c" (on backtrack)
```

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

# DictTerm access
d["x"]          # 1
d.keys()        # dict_keys(["x", "y"])
d.values()      # dict_values([1, 2])
d.items()       # dict_items([("x", 1), ("y", 2)])
len(d)          # 2
"x" in d        # True

# SetTerm access
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
| Dict builtins: `is_dict`, `dict_size`, `dict_keys`, `dict_values`, `dict_pairs`, `dict_get`, `dict_put`, `dict_put_pairs`, `dict_remove`, `dict_merge`, `gen_dict`, `sub_dict` | Done |
| Set builtins: `is_set`, `set_size`, `set_list`, `set_union`, `set_intersection`, `set_subtract`, `set_sym_diff`, `set_subset`, `set_disjoint`, `set_add`, `set_remove`, `gen_set` | Done |
| Splat sugar: `{**old, "k": v}` in clause bodies | Done |
| `trail.record(callable)` — generic callback hook for backtrackable mutable state | Done |

---

## Limitations

- **No variable keys**: Dict keys must be ground. `{X: 1}` where `X` is an unbound variable is not supported.
- **No variable set elements**: Set elements must be ground/hashable.
- **Splat requires bound DictTerm**: `{**OLD, "k": v}` requires `OLD` to be a bound `DictTerm` at runtime. Unbound `OLD` raises `AttributeError` on `.data` access.
- **No mutable variants**: Mutable dict/set types were considered and rejected — the [`++()` Python escape](python_integration.md) covers accumulation patterns with idiomatic, explicit syntax. Use `trail.record()` directly if you need backtrackable undo of custom mutable state.

---

*See also: [Python Interop](python_integration.md) — `++()` escape for dict/set mutation patterns · [Builtins](builtins.md) — full predicate index including dict and set predicates.*
