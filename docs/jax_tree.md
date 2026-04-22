# jax_tree — JAX Pytrees

A **pytree** is JAX's structural abstraction: any nested Python
container (dict, list, tuple, namedtuple, dataclass) whose leaves are
arrays (or scalars). JAX's `jax.tree_util` module is the traversal
library — flatten, unflatten, map over leaves, and so on. Pytrees are
the natural data shape for model parameters, optimiser state, and
batched examples.

This module is the relational counterpart. Leaf enumeration via
`findall`, bijective flatten, path-based queries — every Clausal idiom
that reads nicely against a tree of arrays.

All predicates are Tier 1 pure.

## Import

```clausal
-import_from(py.jax_tree, [
    leaf, leaf_with_path,
    tree_flatten, tree_structure, tree_leaves_list,
    all_leaves, treedef_is_leaf,
    tree_map, tree_map_n, tree_reduce,
    keystr
])
```

---

## Leaf enumeration

### `leaf(TREE, LEAF)`

Nondeterministic — each leaf of `TREE`, in JAX's traversal order, is a
solution. Combine with `findall` to collect them:

```clausal
Test("leaf enumerates flat list") <- (
    TREE is ++([1.0, 2.0, 3.0]),
    findall(L, leaf(TREE, L), LS),
    LS == [1.0, 2.0, 3.0]
)
```

Scalars are pytrees of depth zero — they produce a single leaf. Empty
containers produce no leaves:

```clausal
Test("leaf on empty dict") <- (
    TREE is ++({}),
    findall(L, leaf(TREE, L), LS),
    LS == []
)
```

### `leaf_with_path(TREE, PATH, LEAF)`

Each solution binds both the leaf and its **key-path** — a tuple of
(kind, value) 2-tuples describing one container level each:

| Entry | Meaning | Example |
|---|---|---|
| `("index", N)` | list or tuple index | `("index", 0)` |
| `("key", K)` | dict key | `("key", "weight")` |
| `("attr", NAME)` | dataclass / namedtuple attribute | `("attr", "bias")` |
| `("flat", N)` | flattened index (registered dataclasses) | `("flat", 2)` |

Pattern-match the path directly:

```clausal
Test("leaf_with_path exposes dict key") <- (
    TREE is ++({"a": 1.0}),
    leaf_with_path(TREE, (("key", "a"),), 1.0)
)

Test("nested dict + list index") <- (
    TREE is ++({"a": [1.0, 2.0]}),
    leaf_with_path(TREE, (("key", "a"), ("index", 1)), 2.0)
)
```

### `keystr(PATH, STR)`

Render a Clausal-side path tuple as the same string JAX itself produces
(`['a'][0]`, `.bias`, etc.). Useful for error messages and debug logs:

```clausal
Test("keystr dict + index") <- (
    keystr((("key", "a"), ("index", 0)), S),
    S == "['a'][0]"
)
```

---

## Bijective flatten

### `tree_flatten(TREE, TREEDEF, LEAVES)`

**Forward** `(+TREE, -TREEDEF, -LEAVES)` — returns the JAX `PyTreeDef`
token plus a flat list of leaves.

**Backward** `(-TREE, +TREEDEF, +LEAVES)` — rebuilds the tree.

```clausal
Test("tree_flatten roundtrip") <- (
    TREE is ++({"a": [1.0, 2.0], "b": 3.0}),
    tree_flatten(TREE, TREEDEF, LEAVES),
    tree_flatten(REBUILT, TREEDEF, LEAVES),
    REBUILT == TREE
)
```

The `TREEDEF` is an opaque JAX value — store it, pass it, compare it
with `==`. The backward direction is the standard way to rebuild a
pytree with modified leaves:

```clausal
Test("modify leaves via flatten/unflatten") <- (
    TREE is ++({"a": [1.0, 2.0], "b": 3.0}),
    tree_flatten(TREE, TREEDEF, LEAVES),
    MODIFIED is ++([l * 10 for l in LEAVES]),
    tree_flatten(NEW_TREE, TREEDEF, MODIFIED),
    leaf(NEW_TREE, 10.0)        # succeeds — 10.0 is a leaf of NEW_TREE
)
```

### `tree_structure(TREE, TREEDEF)` and `tree_leaves_list(TREE, LEAVES)`

`tree_structure/2` returns just the `PyTreeDef`; `tree_leaves_list/2`
returns just the flat list (deterministic, no backtracking). Useful
when you want one side without the other.

---

## Structural checks

### `all_leaves(LEAVES)`

Succeeds iff `LEAVES` is a flat list — i.e. nothing inside is itself a
pytree container. Fails quietly if any element is a list/dict/tuple:

```clausal
Test("all_leaves rejects nested list") <- (
    not all_leaves([[1.0], 2.0])
)
```

### `treedef_is_leaf(TREEDEF)`

Succeeds iff `TREEDEF` represents a bare leaf (no containers). Useful
for guarding recursive patterns that should terminate at scalars.

---

## Mapping and reducing

### `tree_map(F, TREE, TREE2)`

Apply the Python callable `F` to every leaf. The structure is
preserved:

```clausal
Test("tree_map doubles leaves") <- (
    TREE is ++({"a": 1.0, "b": 2.0}),
    F is ++(lambda x: x * 2),
    tree_map(F, TREE, DOUBLED),
    tree_leaves_list(DOUBLED, LS),
    LS == [2.0, 4.0]
)
```

### `tree_map_n(F, TREES, TREE2)`

`TREES` is a **list** of trees, all sharing the same pytree structure.
`F` is called with one argument per tree:

```clausal
Test("add matching leaves of two trees") <- (
    T1 is ++({"a": 1.0, "b": 2.0}),
    T2 is ++({"a": 10.0, "b": 20.0}),
    F is ++(lambda x, y: x + y),
    tree_map_n(F, [T1, T2], R),
    tree_leaves_list(R, LS),
    LS == [11.0, 22.0]
)
```

### `tree_reduce(F, TREE, INIT, R)`

Left-fold over leaves with accumulator `INIT`:

```clausal
Test("tree_reduce sums leaves") <- (
    TREE is ++({"a": 1.0, "b": 2.0, "c": 3.0}),
    F is ++(lambda acc, x: acc + x),
    tree_reduce(F, TREE, 0.0, TOTAL),
    TOTAL == 6.0
)
```

### `apply_updates(PARAMS, UPDATES, NEW_PARAMS)`

Element-wise add updates to a params pytree, leaf by leaf. Both
`optax.apply_updates` and `eqx.apply_updates` are thin wrappers
around the same `tree_map`, so the canonical predicate lives here —
not behind any optimiser library. `py.jax_optax.apply_updates` is
re-exported for backwards compatibility.

```clausal
Test("apply_updates on a dict pytree") <- (
    PARAMS is ++({"w": jax.numpy.array([1.0, 2.0]), "b": jax.numpy.array(0.5)}),
    UPDATES is ++({"w": jax.numpy.array([-0.1, -0.2]), "b": jax.numpy.array(-0.05)}),
    apply_updates(PARAMS, UPDATES, NEW)
)
```

`None` leaves in `PARAMS` (the optax convention for "no update for
this slot") are passed through unchanged, matching `optax.apply_updates`'s
behaviour.

---

## Idiom — `findall` over pytree leaves

The Clausal sweet spot. Collect the leaves that satisfy a predicate
without having to flatten + filter procedurally:

```clausal
Test("leaves greater than 2") <- (
    TREE is ++({"a": 1.0, "b": [2.0, 3.0, 4.0]}),
    findall(L, (leaf(TREE, L), L > 2.0), BIG),
    length(BIG, 2)
)
```

Combine with `element_count/2` from `py.jax` to filter by size, e.g.
"find every parameter array larger than 1000":

```clausal
-import_from(py.jax, [element_count])

large_params(PARAMS, BIG) <- (
    findall(L, (leaf(PARAMS, L), element_count(L, N), N > 1000), BIG)
)
```

---

## Callables via `++()`

`tree_map`, `tree_map_n`, `tree_reduce` take Python callables — build
them inline with the standard `++()` idiom:

```clausal
Test("callable via ++()") <- (
    TREE is ++({"a": 1.0}),
    F is ++(lambda x: x * 2),
    tree_map(F, TREE, SCALED),
    tree_leaves_list(SCALED, [2.0])
)
```

Same pattern as `scipy` wrappers that take a callback. Clausal doesn't
have first-class lambdas, so we borrow from Python.

---

## Deferred

- **Custom pytree registration.** `jtu.register_pytree_node` and
  `register_dataclass` extend the pytree system to user types. Wrapping
  these is useful but non-trivial — the register call takes Python
  callbacks. Tracked for a later phase cluster.
