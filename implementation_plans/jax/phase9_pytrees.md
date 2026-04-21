# Phase 9 — Pytrees

Pytrees are JAX's structural abstraction — any nested container
(dict, list, tuple, namedtuple, dataclass) whose leaves are arrays.
`jax.tree_util` provides the traversal primitives. This is the phase
where JAX's relational affordances shine: leaf enumeration via
`findall`, bijective flatten/unflatten, structural queries.

**File to create:** `clausal/modules/py/jax_tree.py`

**Depends on:** Phase 1 — `clausal/modules/py/jax.py` for lazy import
and `_pred`/`_pure`/`_property_2`/`_bidir_3_mid` helpers.

---

## Predicates

### Enumeration (nondeterministic)

| Name | Arity | Modes | Purity | Nondet? | Description |
|---|---|---|---|---|---|
| `leaf` | `/2` | `(+TREE, -LEAF)` | pure | yes | Enumerate leaves in traversal order |
| `leaf_with_path` | `/3` | `(+TREE, -PATH, -LEAF)` | pure | yes | Leaves with their key-path |

### Bijective flatten/unflatten

| Name | Arity | Modes | Purity | Bijective? | Description |
|---|---|---|---|---|---|
| `tree_flatten` | `/3` | `(+TREE, -TREEDEF, -LEAVES)`, `(-TREE, +TREEDEF, +LEAVES)` | pure | yes | Flatten ↔ unflatten |

### Structure queries

| Name | Arity | Modes | Purity | Description |
|---|---|---|---|---|
| `tree_structure` | `/2` | `(+TREE, -TREEDEF)` | pure | Extract the pytree structure |
| `tree_leaves_list` | `/2` | `(+TREE, -LEAVES)` | pure | All leaves as one list (deterministic) |
| `all_leaves` | `/1` | `(+LEAVES)` | pure | Check a list has no pytree containers |
| `treedef_is_leaf` | `/1` | `(+TREEDEF)` | pure | Check treedef is trivial |

### Mapping and reducing

| Name | Arity | Modes | Purity | Description |
|---|---|---|---|---|
| `tree_map` | `/3` | `(+F, +TREE, -TREE2)` | pure | Map Python callable over every leaf |
| `tree_map_n` | `/3` | `(+F, +TREES, -TREE2)` | pure | Map over N trees sharing structure |
| `tree_reduce` | `/4` | `(+F, +TREE, +INIT, -R)` | pure | Reduce over leaves |

### Key paths

| Name | Arity | Modes | Purity | Description |
|---|---|---|---|---|
| `keystr` | `/2` | `(+PATH, -STR)` | pure | Render key-path as a human-readable string |

---

## Context and Reference Patterns

### File structure

Follow `torch_nn.py`. Lazy import JAX and pull `jax.tree_util` as `_jtu`:

```python
from clausal.modules.py.jax import _ensure_jax, _jx

def _jtu():
    _ensure_jax()
    import jax.tree_util as _m
    return _m
```

### Leaf enumeration — nondeterministic

Same pattern as `named_parameter/3` in `torch_nn.py` (lines cited in
Phase 2 of the PyTorch plan):

```python
def _leaf_2(this_generator, _proceed, _fail, _catcher, tree_var, leaf_var, trail):
    tree = _deep_deref(deref(tree_var))
    leaves = _jtu().tree_leaves(tree)
    for leaf in leaves:
        mark = trail.mark()
        if unify(leaf_var, leaf, trail):
            yield (_proceed, None)
        trail.undo(mark)
    yield (_fail, DONE)

leaf = _pred("leaf", (2, _leaf_2))
```

### `leaf_with_path` — path is a tuple of keys

`jtu.tree_leaves_with_path(tree)` returns `[(path, leaf), ...]` where
each path is a tuple of `SequenceKey(idx)` / `DictKey(key)` /
`GetAttrKey(name)` entries. For relational use, convert each path
entry to a Clausal-friendly representation:

```python
def _path_to_clausal(path):
    out = []
    for key in path:
        # SequenceKey(idx=0) -> ("index", 0)
        # DictKey(key="a")    -> ("key", "a")
        # GetAttrKey(name="x") -> ("attr", "x")
        if hasattr(key, "idx"):
            out.append(("index", int(key.idx)))
        elif hasattr(key, "key"):
            out.append(("key", key.key))
        elif hasattr(key, "name"):
            out.append(("attr", key.name))
        else:
            out.append(("other", repr(key)))
    return tuple(out)
```

This gives Clausal users tuples they can pattern-match:

```clausal
leaf_with_path(PARAMS, [("key", "layer1"), ("key", "weight")], W)
```

### Bijective flatten

`tree_flatten` is the centerpiece. Use a three-arg bidirectional helper
because the TREEDEF mediates:

```python
def _tree_flatten_3(this_generator, _proceed, _fail, _catcher,
                   tree_var, treedef_var, leaves_var, trail):
    tree = _deep_deref(deref(tree_var))
    td = deref(treedef_var)
    ls = _deep_deref(deref(leaves_var))
    jtu = _jtu()

    if not is_var(tree):
        # Forward: tree -> (treedef, leaves)
        leaves, treedef = jtu.tree_flatten(tree)
        if unify(treedef_var, treedef, trail) and unify(leaves_var, list(leaves), trail):
            yield (_proceed, None)
    elif not is_var(td) and not is_var(ls):
        # Backward: (treedef, leaves) -> tree
        try:
            rebuilt = jtu.tree_unflatten(td, ls)
        except Exception:
            yield (_fail, DONE)
            return
        if unify(tree_var, rebuilt, trail):
            yield (_proceed, None)
    yield (_fail, DONE)

tree_flatten = _pred("tree_flatten", (3, _tree_flatten_3))
```

### `tree_map` — callable argument

The callable is passed through from Clausal via `++()`:

```python
tree_map = _pred("tree_map",
    (3, _pure(lambda f, tree: _jtu().tree_map(f, tree))),
)
```

Example usage:

```clausal
F is ++(lambda x: x * 2),
tree_map(F, PARAMS, DOUBLED)
```

`tree_map_n` takes a list of trees (all sharing the same structure):

```python
tree_map_n = _pred("tree_map_n",
    (3, _pure(lambda f, trees: _jtu().tree_map(f, *trees))),
)
```

### `tree_reduce`

Standard reduction:

```python
tree_reduce = _pred("tree_reduce",
    (4, _pure(lambda f, tree, init: _jtu().tree_reduce(f, tree, initializer=init))),
)
```

---

## Example Usage

```clausal
-import_from(py.jax, [array, shape, element_count])
-import_from(py.jax_tree, [leaf, leaf_with_path, tree_flatten,
                            tree_structure, tree_map, tree_reduce,
                            all_leaves, keystr])
-import_module(jax)

# Pytree enumeration

Test("leaf enumerates flat list") <- (
    TREE is ++([1.0, 2.0, 3.0]),
    findall(L, leaf(TREE, L), LS),
    LS == [1.0, 2.0, 3.0]
)

Test("leaf enumerates nested dict") <- (
    TREE is ++({"a": [1.0, 2.0], "b": (3.0, 4.0)}),
    findall(L, leaf(TREE, L), LS),
    length(LS, 4)
)

Test("leaf_with_path exposes structure") <- (
    TREE is ++({"a": [1.0, 2.0]}),
    findall(P-L, leaf_with_path(TREE, P, L), PAIRS),
    length(PAIRS, 2)
)

# Bijective flatten

Test("tree_flatten forward") <- (
    TREE is ++({"a": [1.0, 2.0], "b": 3.0}),
    tree_flatten(TREE, TREEDEF, LEAVES),
    length(LEAVES, 3)
)

Test("tree_flatten roundtrip") <- (
    TREE is ++({"a": [1.0, 2.0], "b": 3.0}),
    tree_flatten(TREE, TREEDEF, LEAVES),
    tree_flatten(REBUILT, TREEDEF, LEAVES),
    REBUILT == TREE
)

Test("unflatten with modified leaves") <- (
    TREE is ++({"a": [1.0, 2.0], "b": 3.0}),
    tree_flatten(TREE, TREEDEF, LEAVES),
    MODIFIED is ++([l * 10 for l in LEAVES]),
    tree_flatten(NEW_TREE, TREEDEF, MODIFIED),
    # NEW_TREE should be {"a": [10.0, 20.0], "b": 30.0}
    leaf(NEW_TREE, 10.0)
)

# Mapping

Test("tree_map doubles leaves") <- (
    TREE is ++({"a": 1.0, "b": 2.0}),
    F is ++(lambda x: x * 2),
    tree_map(F, TREE, DOUBLED),
    findall(L, leaf(DOUBLED, L), LS),
    member(2.0, LS),
    member(4.0, LS)
)

Test("tree_reduce sums leaves") <- (
    TREE is ++({"a": 1.0, "b": 2.0, "c": 3.0}),
    F is ++(lambda acc, x: acc + x),
    tree_reduce(F, TREE, 0.0, TOTAL),
    TOTAL == 6.0
)

# Showcase: find all parameter arrays larger than a threshold

large_params(PARAMS, BIG) <- (
    findall(L, (leaf(PARAMS, L), element_count(L, N), N > 1000), BIG)
)
```

---

## Tests

**`.clausal` integration tests** (`tests/fixtures/jax_tree_tests.clausal`):

- `leaf/2` over flat list, nested dict, nested tuple, mixed
- `leaf_with_path/3` produces correctly-shaped paths for each container type
- `tree_flatten/3` forward and backward
- Roundtrip: flatten -> modify leaves -> unflatten
- `tree_map/3` with simple and multi-output functions
- `tree_reduce/4` with sum, max, count
- Empty pytrees (empty list, empty dict)
- `all_leaves/1` for both valid and invalid inputs

---

## Docs

Create `docs/jax_tree.md`:
- What is a pytree; why JAX has them
- Leaf enumeration with `findall` — the Clausal integration sweet spot
- Bijective flatten
- Mapping and reducing
- Path-based queries
- All examples backed by `.clausal` tests

---

## Issues

_To be populated during implementation._

Known items to validate:

1. **`KeyPath` decomposition.** JAX ships `SequenceKey`, `DictKey`,
   `GetAttrKey`, `FlattenedIndexKey`. The `_path_to_clausal` helper
   handles the first three — verify which actually appear in practice.
   If `FlattenedIndexKey` appears (e.g. for registered dataclasses),
   add it to the mapping.

2. **Treedef equality for roundtrip tests.** `PyTreeDef` objects
   compare by structural equality via `==`. Tests can rely on this.

3. **`tree_map` with callables from Clausal.** Clausal lambdas don't
   exist; users pass Python callables via `++()`. This is fine — the
   same pattern as passing callables to `MatrixFunction` in
   `scipy_linalg.py`. Document the `++(lambda x: ...)` idiom.

4. **Path rendering via `keystr`.** `jtu.keystr(path)` produces a
   human-readable string like `['a'][0]`. Useful for error messages and
   debug output.

5. **Custom pytree registration deferred.** `jtu.register_pytree_node`
   and `register_dataclass` extend the pytree system with user types.
   Wrapping these as Clausal predicates is useful but non-trivial
   (callbacks must be Python-callable). Track for a later phase.

6. **Performance of repeated `leaf/2` enumeration.** Each call
   flattens the tree from scratch. For very deep trees this may be
   slow. If it becomes an issue, cache `tree_leaves(tree)` keyed on
   `id(tree)` — but only if profiling shows it matters.
