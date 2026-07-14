"""clausal.logic.runtime.dict_ops — runtime helpers for the dict-native
profile surface (see todo/dict-native-profile-api.md).

Currently implements the strict subscript read ``V is P[K]`` (item 1).
Sibling operations (``get/3``, ``get/4``, key membership, splat/merge,
``delete/3``) will land here as they are implemented.
"""

from __future__ import annotations

from typing import Any

from clausal.logic.variables import deref, is_var
from clausal.terms import DictTerm
from clausal.logic.exceptions import (
    LogicException,
    existence_error,
    instantiation_error,
    type_error,
)

# ISO-style functor/arity tag for the subscript-read context, so a caught
# error(_, Context) carries a recognizable culprit for the operation.
_SUBSCRIPT_CTX = "[]/2"


def _subscript(obj: Any, key: Any) -> Any:
    """Evaluate ``P[K]`` on the right-hand side of ``is/2``.

    Returns the stored value for *key* in *obj*.  The value may itself be a
    ``Var``, so it participates in unification with the ``is/2`` left-hand
    side (``X is {"a": V}["a"]`` aliases ``X`` and ``V``).

    Errors (all raised as catchable ``LogicException``s):
      * non-ground *key*      → ``instantiation_error`` (Python hashable-key
        rule / prover ground-key constraint);
      * *obj* not a dict      → ``type_error(dict, obj)``;
      * *key* absent          → ``existence_error(dict_key, key)`` (the Python
        ``KeyError`` analogue — a strict read throws, it does not fail);
      * unhashable *key*      → ``type_error(dict_key, key)``.
    """
    obj = deref(obj)
    key = deref(key)
    if is_var(key):
        raise LogicException(instantiation_error(_SUBSCRIPT_CTX))
    if isinstance(obj, DictTerm):
        data = obj.data
    elif isinstance(obj, dict):
        data = obj
    else:
        raise LogicException(type_error("dict", obj, _SUBSCRIPT_CTX))
    try:
        return data[key]
    except KeyError:
        raise LogicException(
            existence_error("dict_key", key, _SUBSCRIPT_CTX)
        ) from None
    except TypeError:
        # Unhashable key (e.g. a list/compound reached here despite the
        # is_var guard) — a wrong-typed key, not a missing one.
        raise LogicException(
            type_error("dict_key", key, _SUBSCRIPT_CTX)
        ) from None


_SPLAT_CTX = "{**}/1"


def _splat_data(source: Any) -> dict:
    """Return the underlying dict of a splat source ``{**source, ...}``.

    Guards the merge lowering so an unbound or non-dict splat source raises a
    catchable typed error instead of a raw ``AttributeError`` on ``.data``:
      * unbound source → ``instantiation_error``;
      * non-dict source → ``type_error(dict, source)``.
    A plain Python dict is accepted (library-returned dicts merge without an
    escape), mirroring ``DictTerm.__unify__``.
    """
    source = deref(source)
    if isinstance(source, DictTerm):
        return source.data
    if isinstance(source, dict):
        return source
    if is_var(source):
        raise LogicException(instantiation_error(_SPLAT_CTX))
    raise LogicException(type_error("dict", source, _SPLAT_CTX))
