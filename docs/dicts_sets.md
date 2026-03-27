# Dicts and Sets

Clausal has first-class support for dictionaries and sets as logic terms. Unlike plain Python `dict` and `set`, `DictTerm` and `SetTerm` participate in unification — dict values can contain logic variables that bind during search, and sets unify by element equality.

---

## DictTerm

`DictTerm` is a unification-aware dictionary. Keys must be ground (strings, ints, or other hashable atoms). Values may be logic variables.

### Syntax

In [`.clausal` files](syntax.md), Python dict literals `{k: v, ...}` are automatically wrapped as `DictTerm`:

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

### Partial dict matching — `SubDict/2`

`SubDict(Pattern, Dict)` succeeds when `Pattern`'s keys are a subset of `Dict`'s keys and the values for those keys unify pairwise. Extra keys in `Dict` are ignored.

```python
# Extract the name field from any dict
get_name(PERSON, NAME) <- SubDict({"name": NAME}, PERSON)

# Check role without caring about other fields
is_admin(PERSON) <- SubDict({"role": "admin"}, PERSON)
```

Compare with full unification:

```python
# Full unification: PERSON must have EXACTLY these two keys
exact(PERSON, NAME) <- (PERSON is {"name": NAME, "role": "admin"})

# Partial match: PERSON may have any other keys
partial(PERSON, NAME) <- SubDict({"name": NAME, "role": "admin"}, PERSON)
```

### Backtracking

`DictTerm` unification is fully backtrackable. If a pairwise value unification fails partway through, all bindings made so far are undone via the trail. See [Lists](lists.md) for the set operations available on plain lists.

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

**Not supported.** Set elements must be ground because `frozenset` requires hashable elements. A set containing an unbound logic variable would break hashing. For patterns with variable elements, use `GenSet/2` to enumerate elements.

---

## Dict builtins

All dict builtins are in `clausal/logic/builtins/dict_set.py`. They use `DictTerm` for all dict arguments — plain Python dicts are not accepted.

### `IsDict/1`
```clausal
# skip
IsDict(+Term)
```
Succeeds if `Term` is a `DictTerm`.

### `DictSize/2`
```clausal
# skip
DictSize(+Dict, -N)
```
`N` is the number of keys in `Dict`.

### `DictKeys/2`
```clausal
# skip
DictKeys(+Dict, -Keys)
```
`Keys` is the sorted list of keys. Keys are sorted by `repr` for determinism across key types.

### `DictValues/2`
```clausal
# skip
DictValues(+Dict, -Values)
```
`Values` is the list of values in key-sorted order (same ordering as `DictKeys`).

### `DictPairs/2`
```clausal
# skip
DictPairs(?Dict, ?Pairs)
```
Bidirectional conversion between a `DictTerm` and a list of `[Key, Value]` 2-element lists.

```python
# Dict → pairs
DictPairs({"a": 1, "b": 2}, PAIRS)
# PAIRS = [["a", 1], ["b", 2]]  (sorted by key)

# Pairs → dict
DictPairs(DICT, [["x", 10], ["y", 20]])
# DICT = DictTerm({"x": 10, "y": 20})
```

### `DictGet/3`
```clausal
# skip
DictGet(+Key, +Dict, ?Value)
```
Semidet: succeeds if `Key` is in `Dict` and `Value` unifies with `Dict[Key]`. Fails if the key is absent or `Key` is unbound.

```python
DictGet("name", {"name": "Alice", "age": 30}, NAME)
# NAME = "Alice"
```

### `DictPut/4`
```clausal
# skip
DictPut(+Key, +Value, +OldDict, -NewDict)
```
`NewDict` is `OldDict` with `Key → Value` inserted or overwritten. Returns a new `DictTerm`; the original is unchanged.

```python
DictPut("b", 99, {"a": 1, "b": 0}, NEW)
# NEW = DictTerm({"a": 1, "b": 99})
```

### `DictPutPairs/3`
```clausal
# skip
DictPutPairs(+Pairs, +OldDict, -NewDict)
```
Bulk update: `Pairs` is a list of `[Key, Value]` 2-element lists. Equivalent to calling `DictPut/4` for each pair in order.

```python
DictPutPairs([["b", 2], ["c", 3]], {"a": 1}, NEW)
# NEW = DictTerm({"a": 1, "b": 2, "c": 3})
```

### `DictRemove/3`
```clausal
# skip
DictRemove(+Key, +OldDict, -NewDict)
```
`NewDict` is `OldDict` without `Key`. Fails if `Key` is not present.

```python
DictRemove("b", {"a": 1, "b": 2, "c": 3}, NEW)
# NEW = DictTerm({"a": 1, "c": 3})
```

### `DictMerge/3`
```clausal
# skip
DictMerge(+D1, +D2, -Merged)
```
`Merged` is the union of `D1` and `D2`. Where keys conflict, `D2`'s value wins.

```python
DictMerge({"a": 1, "b": 0}, {"b": 99, "c": 3}, MERGED)
# MERGED = DictTerm({"a": 1, "b": 99, "c": 3})
```

### `GenDict/3`
```clausal
# skip
GenDict(?Key, +Dict, ?Value)
```
Nondeterministic: on backtracking, enumerates all key-value pairs in `Dict`. Equivalent to SWI's `gen_assoc/3`.

```python
# Enumerate all pairs
GenDict(KEY, {"a": 1, "b": 2}, VALUE)
# → KEY="a", VALUE=1
# → KEY="b", VALUE=2 (on backtrack)

# Filter by key
GenDict("a", {"a": 1, "b": 2}, VALUE)
# → VALUE=1 (only one solution)
```

### `SubDict/2`
```clausal
# skip
SubDict(+Pattern, +Dict)
```
Partial dict matching: succeeds when every key in `Pattern` is also in `Dict`, and the corresponding values unify. Extra keys in `Dict` are ignored.

```python
SubDict({"name": NAME}, {"name": "Alice", "age": 30})
# → NAME = "Alice"

SubDict({"role": "admin"}, {"name": "Bob", "role": "admin", "dept": "eng"})
# → succeeds

SubDict({"role": "admin"}, {"name": "Alice", "role": "user"})
# → fails (value mismatch)

SubDict({"z": 1}, {"x": 1, "y": 2})
# → fails (key absent)
```

---

## Set builtins

### `IsSet/1`
```clausal
# skip
IsSet(+Term)
```
Succeeds if `Term` is a `SetTerm`.

### `SetSize/2`
```clausal
# skip
SetSize(+Set, -N)
```
`N` is the cardinality of `Set`.

### `SetList/2`
```clausal
# skip
SetList(?Set, ?List)
```
Bidirectional conversion between a `SetTerm` and a sorted list.

```python
# Set → list (sorted)
SetList({3, 1, 2}, LIST)  # LIST = [1, 2, 3]

# List → set (duplicates removed)
SetList(SET, [1, 1, 2])   # SET = SetTerm({1, 2})
```

### `SetUnion/3`
```clausal
# skip
SetUnion(+S1, +S2, -Union)
```
`Union` is the set union of `S1` and `S2`.

### `SetIntersection/3`
```clausal
# skip
SetIntersection(+S1, +S2, -Inter)
```
`Inter` is the set intersection of `S1` and `S2`.

### `SetSubtract/3`
```clausal
# skip
SetSubtract(+S1, +S2, -Diff)
```
`Diff` is `S1` minus `S2` (elements in `S1` not in `S2`).

### `SetSymDiff/3`
```clausal
# skip
SetSymDiff(+S1, +S2, -Sym)
```
`Sym` is the symmetric difference of `S1` and `S2` (elements in exactly one of the two sets).

### `SetSubset/2`
```clausal
# skip
SetSubset(+Sub, +Super)
```
Succeeds if every element of `Sub` is also in `Super`. An empty set is a subset of any set.

### `SetDisjoint/2`
```clausal
# skip
SetDisjoint(+S1, +S2)
```
Succeeds if `S1` and `S2` have no elements in common.

### `SetAdd/3`
```clausal
# skip
SetAdd(+Elem, +OldSet, -NewSet)
```
`NewSet` is `OldSet` with `Elem` added. If `Elem` is already present, `NewSet = OldSet`.

### `SetRemove/3`
```clausal
# skip
SetRemove(+Elem, +OldSet, -NewSet)
```
`NewSet` is `OldSet` with `Elem` removed. If `Elem` is absent, `NewSet = OldSet`.

### `GenSet/2`
```clausal
# skip
GenSet(?Elem, +Set)
```
Nondeterministic: on backtracking, enumerates all elements of `Set` in a deterministic order (sorted by `repr`).

```python
GenSet(ELEM, {"a", "b", "c"})
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
| Dict builtins: `IsDict`, `DictSize`, `DictKeys`, `DictValues`, `DictPairs`, `DictGet`, `DictPut`, `DictPutPairs`, `DictRemove`, `DictMerge`, `GenDict`, `SubDict` | Done |
| Set builtins: `IsSet`, `SetSize`, `SetList`, `SetUnion`, `SetIntersection`, `SetSubtract`, `SetSymDiff`, `SetSubset`, `SetDisjoint`, `SetAdd`, `SetRemove`, `GenSet` | Done |
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
