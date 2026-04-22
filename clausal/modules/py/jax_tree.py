"""clausal.modules.py.jax_tree — JAX pytree predicates for Clausal.

Pytrees are JAX's structural abstraction — any nested container (dict,
list, tuple, namedtuple, dataclass) whose leaves are arrays. This
module wraps ``jax.tree_util`` so pytrees participate naturally in
Clausal's relational and enumerative idioms:

    -import_from(py.jax_tree, [
        leaf, leaf_with_path,
        tree_flatten, tree_structure, tree_leaves_list,
        all_leaves, treedef_is_leaf,
        tree_map, tree_map_n, tree_reduce,
        keystr,
    ])

Phase 9 — Pytrees
-------------------
All predicates are Tier 1 pure.

Enumeration (nondeterministic):
    leaf(TREE, LEAF)                   Each leaf, in traversal order
    leaf_with_path(TREE, PATH, LEAF)   Leaves with their key-path

Bijective flatten/unflatten:
    tree_flatten(TREE, TREEDEF, LEAVES)    Forward: tree -> (td, leaves)
                                           Backward: (td, leaves) -> tree

Structure queries:
    tree_structure(TREE, TREEDEF)          Extract just the PyTreeDef
    tree_leaves_list(TREE, LEAVES)         Deterministic: all leaves in a list
    all_leaves(LEAVES)                     Check: no pytree containers inside
    treedef_is_leaf(TREEDEF)               Check: the treedef is a trivial leaf

Mapping and reducing:
    tree_map(F, TREE, TREE2)               Map F over every leaf
    tree_map_n(F, TREES, TREE2)            Map F over N trees sharing structure
    tree_reduce(F, TREE, INIT, R)          Reduce leaves with F and INIT

Paths:
    keystr(PATH, STR)                      Render a key-path as '[\"a\"][0]'

Path representation
-------------------
`leaf_with_path/3` and `keystr/2` work with paths — tuples of key
entries, one per container level from the root. Each entry is a
2-tuple so Clausal can pattern-match:

    ("index", N)    — SequenceKey (list/tuple index)
    ("key", K)      — DictKey (dict key)
    ("attr", NAME)  — GetAttrKey (dataclass / namedtuple attribute)
    ("flat", N)     — FlattenedIndexKey (rare; registered dataclasses)

Callables passed through ``++()``
---------------------------------
`tree_map`, `tree_map_n`, `tree_reduce` take Python callables. Build
them inline:

    F is ++(lambda x: x * 2),
    tree_map(F, TREE, DOUBLED)

Same idiom as scipy wrappers that take a callback.
"""

from __future__ import annotations

import threading as _threading

from clausal.logic.variables import deref, is_var, unify
from clausal.logic.trampoline import DONE
from clausal.modules.py._helpers import _pred, _pure, _deep_deref, _check_1
from clausal.modules.py.jax import _ensure_jax


# ── Lazy jax.tree_util import ────────────────────────────────────────────

_jtu_mod = None
_jtu_lock = _threading.Lock()


def _jtu():
    global _jtu_mod
    if _jtu_mod is not None:
        return _jtu_mod
    with _jtu_lock:
        if _jtu_mod is not None:
            return _jtu_mod
        _ensure_jax()
        from clausal.modules.py import _import_stdlib
        _jtu_mod = _import_stdlib("jax.tree_util")
    return _jtu_mod


# ── Key-path conversion ─────────────────────────────────────────────────
#
# jtu.tree_leaves_with_path returns paths as tuples of typed key objects
# (SequenceKey, DictKey, GetAttrKey, FlattenedIndexKey). These don't
# unify well — convert each entry to a ("kind", value) tuple so Clausal
# can pattern-match.

def _path_to_clausal(path):
    out = []
    for key in path:
        if hasattr(key, "idx"):
            out.append(("index", int(key.idx)))
        elif hasattr(key, "key"):
            out.append(("key", key.key))
        elif hasattr(key, "name"):
            out.append(("attr", key.name))
        else:
            out.append(("other", repr(key)))
    return tuple(out)


# ═══════════════════════════════════════════════════════════════════════════
# Leaf enumeration — nondeterministic
# ═══════════════════════════════════════════════════════════════════════════


def _leaf_2(this_generator, _proceed, _fail, _catcher, tree_var, leaf_var, trail):
    tree = _deep_deref(tree_var)
    try:
        leaves = _jtu().tree_leaves(tree)
    except Exception:
        yield (_fail, DONE)
        return
    for leaf_val in leaves:
        mark = trail.mark()
        if unify(leaf_var, leaf_val, trail):
            yield (_proceed, None)
        trail.undo(mark)
    yield (_fail, DONE)


leaf = _pred("leaf", (2, _leaf_2))


def _leaf_with_path_3(this_generator, _proceed, _fail, _catcher,
                     tree_var, path_var, leaf_var, trail):
    tree = _deep_deref(tree_var)
    try:
        pairs = _jtu().tree_leaves_with_path(tree)
    except Exception:
        yield (_fail, DONE)
        return
    for raw_path, leaf_val in pairs:
        path = _path_to_clausal(raw_path)
        mark = trail.mark()
        if unify(path_var, path, trail) and unify(leaf_var, leaf_val, trail):
            yield (_proceed, None)
        trail.undo(mark)
    yield (_fail, DONE)


leaf_with_path = _pred("leaf_with_path", (3, _leaf_with_path_3))


# ═══════════════════════════════════════════════════════════════════════════
# Bijective flatten / unflatten
# ═══════════════════════════════════════════════════════════════════════════
#
# tree_flatten(TREE, TREEDEF, LEAVES) is multi-mode:
#   - (+TREE, -TREEDEF, -LEAVES): jtu.tree_flatten(tree)
#   - (-TREE, +TREEDEF, +LEAVES): jtu.tree_unflatten(td, leaves)
#
# TREEDEF is a jaxlib PyTreeDef; it compares by structural equality via
# `==` and is not a Clausal-unifiable structure, so we treat it as an
# opaque token here.


def _tree_flatten_3(this_generator, _proceed, _fail, _catcher,
                    tree_var, treedef_var, leaves_var, trail):
    tree = _deep_deref(tree_var)
    td = deref(treedef_var)
    ls = _deep_deref(leaves_var)
    jtu = _jtu()

    if not is_var(tree):
        # Forward: tree -> (treedef, leaves)
        try:
            leaves, treedef = jtu.tree_flatten(tree)
        except Exception:
            yield (_fail, DONE)
            return
        if unify(treedef_var, treedef, trail) \
                and unify(leaves_var, list(leaves), trail):
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


# ═══════════════════════════════════════════════════════════════════════════
# Structure queries
# ═══════════════════════════════════════════════════════════════════════════

tree_structure = _pred("tree_structure",
    (2, _pure(lambda tree: _jtu().tree_structure(tree))),
)

tree_leaves_list = _pred("tree_leaves_list",
    (2, _pure(lambda tree: list(_jtu().tree_leaves(tree)))),
)

all_leaves = _pred("all_leaves",
    (1, _check_1(lambda leaves: bool(_jtu().all_leaves(leaves)))),
)

treedef_is_leaf = _pred("treedef_is_leaf",
    (1, _check_1(lambda td: bool(_jtu().treedef_is_leaf(td)))),
)


# ═══════════════════════════════════════════════════════════════════════════
# Mapping and reducing
# ═══════════════════════════════════════════════════════════════════════════

tree_map = _pred("tree_map",
    (3, _pure(lambda f, tree: _jtu().tree_map(f, tree))),
)

# tree_map_n: apply F to the matching leaves of N trees (all sharing the
# same pytree structure). Accepts a list of trees.
tree_map_n = _pred("tree_map_n",
    (3, _pure(lambda f, trees: _jtu().tree_map(f, *trees))),
)

tree_reduce = _pred("tree_reduce",
    (4, _pure(lambda f, tree, init:
              _jtu().tree_reduce(f, tree, initializer=init))),
)


# ═══════════════════════════════════════════════════════════════════════════
# Key-path rendering
# ═══════════════════════════════════════════════════════════════════════════
#
# keystr(PATH, STR) works on the Clausal-side path tuples produced by
# leaf_with_path/3. We round-trip through the native JAX key types to
# get the same string format JAX itself produces (['a'][0] etc.).

def _path_from_clausal(path):
    jtu = _jtu()
    out = []
    for kind, value in path:
        if kind == "index":
            out.append(jtu.SequenceKey(idx=int(value)))
        elif kind == "key":
            out.append(jtu.DictKey(key=value))
        elif kind == "attr":
            out.append(jtu.GetAttrKey(name=value))
        elif kind == "flat":
            out.append(jtu.FlattenedIndexKey(key=int(value)))
        else:
            raise ValueError(f"unknown key-path kind: {kind!r}")
    return tuple(out)


keystr = _pred("keystr",
    (2, _pure(lambda path: _jtu().keystr(_path_from_clausal(path)))),
)


# ── Module-level exports ──────────────────────────────────────────────────

__all__ = [
    # Enumeration
    "leaf", "leaf_with_path",
    # Bijective flatten
    "tree_flatten",
    # Structure queries
    "tree_structure", "tree_leaves_list", "all_leaves", "treedef_is_leaf",
    # Mapping and reducing
    "tree_map", "tree_map_n", "tree_reduce",
    # Key paths
    "keystr",
]
