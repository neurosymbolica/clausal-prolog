# Dicts and Sets for Clausal

## Context

Clausal uses Python syntax but currently treats `dict` and `set` literals as **atomic** — they pass through unification via `==` with no structural decomposition. Python has great syntax for both (`{k: v}` and `{a, b, c}`), and logic programming has well-established approaches to associative data (SWI dicts, `library(assoc)`, `library(ordsets)`). This plan adds first-class logic-programming support for both.

### Design principle

**Purity comes from the interface, not the implementation.** Python's built-in `dict` is a C-optimized O(1) hash map — reimplementing AVL trees (like `library(assoc)`) in Python would be slower for no logical benefit. We use Python containers internally but expose a pure, functional, unification-aware interface. Impure (mutable) variants are offered separately for performance-critical accumulation.

### Relationship to KWTerm

`KWTerm(functor, **kwargs)` is already close to SWI's tagged dict: keyword-based, order-independent, unification-aware. However, KWTerm requires a functor/tag and uses attribute access (`t.x`), not subscript (`d["x"]`). Dicts are tag-free and key-flexible. We keep both: KWTerm for record-like compound terms, DictTerm for general-purpose associative data.

---

## Part 1: DictTerm — Pure Logic Dict

### 1.1 Term type

New class `DictTerm` in `clausal/terms.py`:

```python
class DictTerm:
    """Unification-aware dictionary term.

    Keys must be ground (str, int, or other hashable atoms).
    Values may be Vars, participating in unification.
    """
    __slots__ = ("_data",)

    def __init__(self, data: dict):
        self._data = dict(data)  # defensive copy

    @property
    def data(self) -> dict:
        return self._data

    def keys(self):   return self._data.keys()
    def values(self): return self._data.values()
    def items(self):  return self._data.items()
    def __len__(self): return len(self._data)
    def __getitem__(self, key): return self._data[key]

    def __eq__(self, other):
        return isinstance(other, DictTerm) and self._data == other._data

    def __hash__(self):
        return hash(frozenset(self._data.items()))

    def __repr__(self):
        inner = ", ".join(f"{k!r}: {v!r}" for k, v in self._data.items())
        return f"DictTerm({{{inner}}})"
```

### 1.2 Unification semantics

Two `DictTerm`s unify iff:
1. They have the **same set of keys**
2. Values for each key unify pairwise

This matches SWI-Prolog's dict unification. A `DictTerm` does **not** unify with a plain `dict` (type mismatch).

**Implementation** — extend `do_unify` in `_variables.c`:

```c
/* After the list check, before the PyObject_RichCompareBool fallback */
if (DictTerm_Check(t1) && DictTerm_Check(t2)) {
    PyObject *d1 = DictTerm_GET_DATA(t1);
    PyObject *d2 = DictTerm_GET_DATA(t2);
    /* Same key sets? */
    PyObject *k1 = PyDict_Keys(d1);
    PyObject *k2 = PyDict_Keys(d2);
    /* ... sort and compare key lists ... */
    /* Pairwise unify values for each shared key */
    for each key in k1:
        r = do_unify(PyDict_GetItem(d1, key),
                     PyDict_GetItem(d2, key),
                     trail, depth + 1, oc);
        if (r != 1) return r;
    return 1;
}
```

Also extend `do_walk` and `do_occurs_check` to recurse into `DictTerm._data` values.

**Alternative — Python-level hook:** If modifying the C extension is too invasive initially, we can add a `__unify__` protocol: `do_unify` checks for a `__unify__` method on non-Var, non-tuple, non-list objects and delegates to it. This makes the C code generic and future-proof for other custom term types. Trade-off: one Python call per dict unification vs. pure C speed.

**Decision needed:** C-native DictTerm support vs. `__unify__` protocol. Recommend starting with `__unify__` protocol for flexibility, optimise to C later if profiling shows it matters.

### 1.3 AST and compiler integration

**Parser/AST layer** (`term_rewriting.py`):
- `visit_Dict` currently emits a `DictLiteral` node that compiles to a plain Python `dict`.
- Change: in term context (clause heads and bodies), emit a `DictTerm(...)` constructor call instead.
- In `++()` Python escapes, keep plain dict semantics.

**Compiler** (`compiler.py`):
- Head patterns: `{x: X, y: Y} <- ...` compiles to a `match` case that:
  1. Checks `isinstance(arg, DictTerm)`
  2. Checks key set equality
  3. Extracts values and unifies with pattern variables
- Body goals: dict literals in body position construct `DictTerm(...)` at runtime.

**Example Clausal syntax:**

```python
# Clause with dict pattern in head
lookup(Key, {Key: Value}, Value),

# Dict construction in body
make_point(X, Y, Point) <- Point = {x: X, y: Y},

# Nested
get_name(Person, Name) <- Person = {name: Name, address: {city: City}},
```

### 1.4 Partial dict matching

SWI has `Select :< From` (sub-dict). We need an equivalent.

**Syntax options:**
- `{x: X} << {x: 1, y: 2, z: 3}` — `<<` as "contained in"
- `{x: X} <= {x: 1, y: 2, z: 3}` — subset-or-equal (conflicts with arithmetic)
- Builtin predicate: `dict_select({x: X}, FullDict)` — verbose but clear

**Recommend `<<`** — it's available, intuitive ("projects from"), and doesn't clash with existing operators.

Semantics of `A << B`:
- A's keys must be a subset of B's keys
- Values for A's keys unify pairwise with corresponding values in B
- B may have extra keys (ignored)

Implementation: a new builtin predicate `DictSelect` that compiles the `<<` operator in goal context.

### 1.5 Dict operations — builtins

```
dict_pairs(Dict, Pairs)           % DictTerm ↔ list of key:value pairs
dict_keys(Dict, Keys)             % extract key list
dict_values(Dict, Values)         % extract value list
dict_get(Key, Dict, Value)        % like get_assoc — semidet
dict_put(Key, Value, Old, New)    % functional update → new DictTerm
dict_put(Pairs, Old, New)         % bulk update from pair list
dict_merge(D1, D2, Merged)        % D2 keys override D1
dict_remove(Key, Old, New)        % remove key → new DictTerm
dict_size(Dict, N)                % number of keys
is_dict(Term)                     % type check
```

**Pythonic sugar** — consider compiling `{**old, k: new_v}` (Python's dict unpacking) to `dict_put` / `dict_merge`. This gives us functional update with native syntax:

```python
update_name(Old, Name, New) <- New = {**Old, name: Name},
```

### 1.6 `gen_dict/3` — nondeterministic enumeration

```python
gen_dict(Key, Dict, Value)   # enumerates all key-value pairs on backtracking
```

Equivalent to `library(assoc)`'s `gen_assoc/3`. Yields one `Key=..., Value=...` binding per solution.

---

## Part 2: SetTerm — Pure Logic Set

### 2.1 Term type

New class `SetTerm` in `clausal/terms.py`:

```python
class SetTerm:
    """Unification-aware set term.

    Elements must be ground (or at least sufficiently instantiated for hashing).
    Backed by frozenset for immutability and hashability.
    """
    __slots__ = ("_elements",)

    def __init__(self, elements):
        self._elements = frozenset(elements)

    @property
    def elements(self) -> frozenset:
        return self._elements

    def __len__(self): return len(self._elements)
    def __contains__(self, item): return item in self._elements
    def __iter__(self): return iter(self._elements)

    def __eq__(self, other):
        return isinstance(other, SetTerm) and self._elements == other._elements

    def __hash__(self):
        return hash(self._elements)
```

### 2.2 Unification semantics

Two `SetTerm`s unify iff they contain the **same elements** (as a set — order irrelevant). Elements are compared by `==`, not unification, since set membership requires ground/hashable elements.

**Variables in sets:** Not supported in the pure version. A set `{X, 1, 2}` where `X` is unbound would break hashing. If we want partial set patterns later, that's a separate feature (constraint-based).

### 2.3 AST and compiler integration

- `visit_Set` currently emits `SetLiteral` → plain Python `set`.
- Change: in term context, emit `SetTerm(...)` constructor call.
- Head patterns: `{1, 2, 3}` in a clause head checks `isinstance(arg, SetTerm)` and tests set equality.

**Example:**

```python
# Set membership via backtracking
member(X, S) <- is_set(S), gen_set(X, S),

# Set operations
colors({red, green, blue}),
has_red(S) <- member(red, S),
```

### 2.4 Set operations — builtins

```
set_list(Set, List)                % SetTerm ↔ sorted list
set_union(S1, S2, Union)           % set union
set_intersection(S1, S2, Inter)    % set intersection
set_subtract(S1, S2, Diff)         % S1 - S2
set_symdiff(S1, S2, Sym)           % symmetric difference
set_subset(Sub, Super)             % subset test
set_disjoint(S1, S2)               % disjoint test
set_add(Elem, Old, New)            % add element → new SetTerm
set_remove(Elem, Old, New)         % remove element → new SetTerm
set_size(Set, N)                   % cardinality
is_set(Term)                       % type check
gen_set(Elem, Set)                 % enumerate elements on backtracking
```

All operations return new `SetTerm`s — no mutation, fully pure.

---

## Part 3: Impure / Mutable Variants

For accumulation patterns (e.g., building up a large dict inside `findall` or a loop), pure functional update creates O(N) copies per step. Offer mutable variants with Trail integration for backtrackable destructive updates.

### 3.1 MutableDict

```python
class MutableDict:
    """Mutable dict with backtrackable updates via Trail."""

    def put(self, key, value, trail):
        # Record old value on trail for undo
        trail.record(self, key, self._data.get(key, _ABSENT))
        self._data[key] = value

    def remove(self, key, trail):
        trail.record(self, key, self._data.pop(key, _ABSENT))
```

Trail integration: extend `Trail.undo()` to recognize `MutableDict` entries (or use a callback-based trail entry).

### 3.2 MutableSet

Same pattern — `frozenset` replaced with `set`, mutations recorded on Trail.

### 3.3 Exposure

These live in `clausal/modules/collections.clausal` or `clausal/terms.py` and are imported explicitly:

```python
-import_from(clausal.modules.collections, [MutableDict, MutableSet])
```

**Not the default.** The pure versions are the default when you write `{}` syntax. Mutable variants are opt-in.

---

## Part 4: The `__unify__` Protocol

Rather than hardcoding every new term type in the C unifier, add a generic extension point:

```c
/* In do_unify, after tuple/list checks, before == fallback: */
PyObject *hook = PyObject_GetAttrString(t1, "__unify__");
if (hook) {
    /* Call t1.__unify__(t2, trail, depth, oc) */
    /* Returns: 1 (success), 0 (fail), -1 (error) */
    result = PyObject_CallFunction(hook, "OOii", t2, trail, depth, oc);
    ...
}
```

This lets `DictTerm`, `SetTerm`, `KWTerm`, and future term types define their own unification without C changes. The protocol:

```python
class DictTerm:
    def __unify__(self, other, trail, depth, oc):
        if not isinstance(other, DictTerm):
            return NotImplemented
        if self._data.keys() != other._data.keys():
            return False
        for key in self._data:
            if not unify(self._data[key], other._data[key], trail):
                return False
        return True
```

Similarly, add `__walk__` and `__occurs_check__` protocols.

**Trade-off:** One Python-to-C boundary crossing per custom-type unification. Acceptable for dicts (usually few, large); might matter for deeply nested terms. Profile later, move hot paths to C if needed.

---

## Implementation Order

### Phase 1: Foundation (do first)
1. **`__unify__` / `__walk__` / `__occurs_check__` protocol** in `_variables.c`
   - Generic hook, unlocks all subsequent work
   - Test with a trivial custom type
2. **`DictTerm` class** in `terms.py` with `__unify__`, `__walk__`, `__occurs_check__`
3. **Unit tests** for DictTerm unification (same keys, different keys, nested vars, occurs check)

### Phase 2: Compiler integration
4. **AST transform** — `visit_Dict` in `term_rewriting.py` emits `DictTerm(...)` in term context
5. **Head pattern compilation** — `compiler.py` handles `DictTerm` in clause heads (match + key extraction + pairwise unification)
6. **Tests** — round-trip: `.clausal` file with dict patterns, queries, backtracking

### Phase 3: Dict builtins
7. **Core builtins**: `dict_pairs`, `dict_get`, `dict_put`, `dict_merge`, `dict_keys`, `dict_values`, `is_dict`, `dict_size`
8. **`gen_dict/3`** — nondeterministic enumeration
9. **Partial matching** — `<<` operator → `DictSelect` builtin
10. **`{**old, k: v}` sugar** — compile dict unpacking to `dict_put` / `dict_merge`

### Phase 4: Sets
11. **`SetTerm` class** with `__unify__`, `__walk__`
12. **AST transform** — `visit_Set` emits `SetTerm(...)` in term context
13. **Set builtins**: `set_union`, `set_intersection`, `set_subtract`, `set_subset`, `set_add`, `gen_set`, `is_set`, `set_list`

### Phase 5: Impure variants (optional, demand-driven)
14. **`MutableDict`** with Trail-backed undo
15. **`MutableSet`** with Trail-backed undo
16. **Trail extension** — callback-based trail entries for custom undo

---

## Open Questions

1. **Plain `dict` interop:** Should `unify(DictTerm({...}), plain_dict, trail)` succeed by auto-wrapping the plain dict? Convenient for Python interop but blurs the type boundary. Recommend: no auto-wrapping; provide `dict_from_py/2` for explicit conversion.

2. **Dict in `walk()`:** `walk()` should reconstruct `DictTerm` with walked values. But since keys must be ground, only values need walking. Confirm: keys are never Vars.

3. **Printing:** `write/1` and `print_term/2` need cases for `DictTerm` and `SetTerm`. Use `{k: v, ...}` and `{a, b, ...}` syntax respectively.

4. **`copy_term/2`:** Must recurse into `DictTerm` values and `SetTerm` elements to copy variables. Extend `_collect_vars` in `compiler.py` (already handles `dict` — just needs the `DictTerm` case).

5. **Indexing:** First-argument indexing in the compiler currently handles atoms, ints, tuples, lists. Add a `DictTerm` case? Probably not worth it — dicts in first-argument position are rare. Revisit if profiling shows dispatch overhead.

6. **`numbervars/3`:** Extend to recurse into DictTerm values.
