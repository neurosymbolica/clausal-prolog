"""clausal.modules.py.torch_data — Dataset predicates for Clausal.

Wraps ``torch.utils.data`` — dataset definition and item access::

    -import_from(py.torch_data, [tensor_dataset, dataset_length,
                                  dataset_item, dataset_element])

Construction
------------
tensor_dataset(TENSORS, DS)          Create TensorDataset from list of tensors.

Properties
----------
dataset_length(DS, N)                Number of items in dataset.

Item Access
-----------
dataset_item(DS, INDEX, ITEM)        Get item by index (tuple of tensors).

Enumeration (nondeterministic)
------------------------------
dataset_element(DS, ITEM)            Enumerate items via backtracking.
dataset_element(DS, INDEX, ITEM)     Enumerate (index, item) pairs.
"""

from __future__ import annotations

from clausal.logic.variables import deref, is_var, unify
from clausal.logic.trampoline import DONE
from clausal.modules.py._helpers import _pred, _deep_deref, _pure
from clausal.modules.py.torch import _ensure_torch, _th


# ── Helpers ──────────────────────────────────────────────────────────────

def _property_2(getter):
    """Property predicate: (+obj, -value) or (+obj, +value) check."""
    def dispatch(this_generator, parent, obj_var, value_var, trail):
        obj = deref(obj_var)
        v = deref(value_var)
        try:
            actual = getter(obj)
        except Exception:
            yield (parent, DONE)
            return
        if is_var(v):
            if unify(value_var, actual, trail):
                yield (parent, None)
        else:
            if actual == v:
                yield (parent, None)
        yield (parent, DONE)
    return dispatch


def _enumerate_items_2(this_generator, parent, ds_var, item_var, trail):
    """Nondeterministic: enumerate dataset items."""
    ds = deref(ds_var)
    try:
        n = len(ds)
    except Exception:
        yield (parent, DONE)
        return
    for i in range(n):
        mark = trail.mark()
        try:
            item = ds[i]
        except Exception:
            trail.undo(mark)
            continue
        if unify(item_var, item, trail):
            yield (parent, None)
        trail.undo(mark)
    yield (parent, DONE)


def _enumerate_items_3(this_generator, parent, ds_var, idx_var, item_var, trail):
    """Nondeterministic: enumerate (index, item) pairs."""
    ds = deref(ds_var)
    try:
        n = len(ds)
    except Exception:
        yield (parent, DONE)
        return
    for i in range(n):
        mark = trail.mark()
        try:
            item = ds[i]
        except Exception:
            trail.undo(mark)
            continue
        if unify(idx_var, i, trail) and unify(item_var, item, trail):
            yield (parent, None)
        trail.undo(mark)
    yield (parent, DONE)


# ═══════════════════════════════════════════════════════════════════════════
# Predicates
# ═══════════════════════════════════════════════════════════════════════════

def _make_tensor_dataset(tensors):
    _ensure_torch()
    td = _th().utils.data.TensorDataset
    return td(*tensors)


tensor_dataset = _pred("tensor_dataset",
    (2, _pure(_make_tensor_dataset)),
)

dataset_length = _pred("dataset_length",
    (2, _property_2(lambda ds: len(ds))),
)

dataset_item = _pred("dataset_item",
    (3, _pure(lambda ds, idx: ds[int(idx)])),
)

dataset_element = _pred("dataset_element",
    (2, _enumerate_items_2),
    (3, _enumerate_items_3),
)


# ── Module-level exports ─────────────────────────────────────────────────

__all__ = [
    "tensor_dataset", "dataset_length",
    "dataset_item", "dataset_element",
]
