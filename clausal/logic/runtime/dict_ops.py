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
      * unbound *obj*         → ``instantiation_error`` (an under-instantiated
        read, not a wrong-typed one — an unbound variable is not "not a dict",
        it is a dict not yet known);
      * non-ground *key*      → ``instantiation_error`` (Python hashable-key
        rule / prover ground-key constraint);
      * *obj* not a dict      → ``type_error(dict, obj)``;
      * *key* absent          → ``existence_error(dict_key, key)`` (the Python
        ``KeyError`` analogue — a strict read throws, it does not fail);
      * unhashable *key*      → ``type_error(dict_key, key)``.
    """
    obj = deref(obj)
    key = deref(key)
    if is_var(obj):
        raise LogicException(instantiation_error(_SUBSCRIPT_CTX))
    if is_var(key):
        raise LogicException(instantiation_error(_SUBSCRIPT_CTX))
    # ``mapping_of`` normalises a PLAIN dict's own nil keys (fix round 4,
    # item 1).  Taking ``obj`` raw folded only the LOOKUP key, so on
    # ``{"": 1}`` -- a dict a Python caller built, never through
    # ``DictTerm.__init__`` -- the folded ``()`` missed the stored ``""`` and
    # ``D[""]`` raised ``existence_error(dict_key, [])`` while the same read
    # on the ``DictTerm`` hit.  It is the CALLER's mapping when there is
    # nothing to fold, so it is read, never mutated.
    data = DictTerm.mapping_of(obj)
    if data is None:
        raise LogicException(type_error("dict", obj, _SUBSCRIPT_CTX))
    # Read the mapping only with a NORMALISED key (fix round 3, item 1):
    # every spelling of nil is one key, and ``[]`` -- the spelling
    # ``mint("[]")`` answers -- is unhashable, so ``D.'[]'`` used to raise
    # ``type_error(dict_key, [])`` out of the ``except TypeError`` arm below
    # while ``D.()`` hit.
    key = DictTerm.normalised_key(key)
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


_DICT_KEY_CTX = "{key}/1"


def _dict_key(key: Any) -> Any:
    """Dereference a computed dict-literal key.

    A key written as a logic variable (``{K: V}`` or ``{**OLD, K: V}`` with
    ``K`` bound in the SAME clause frame as the literal) reaches dict
    construction as the Var/AttVar object, not its value — so the built dict
    is keyed by the variable and every later ``get(D, <value>, _)`` misses.
    Dereferencing here makes the key its bound value. An unbound key is an
    instantiation error (mirrors ``_splat_data`` on an unbound source).
    """
    key = deref(key)
    if is_var(key):
        raise LogicException(instantiation_error(_DICT_KEY_CTX))
    # A computed key that derefs to the nil atom must take its canonical
    # KEY form (fix round 3, item 1): ``mint("[]")`` is the empty LIST,
    # which is unhashable, so ``{K: V}`` with ``K = []`` built nothing but a
    # raw ``TypeError``.
    return DictTerm.normalised_key(key)
