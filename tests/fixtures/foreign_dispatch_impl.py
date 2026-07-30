"""An out-of-tree-shaped ``_get_dispatch`` implementor: a plain class.

This is the shape of the ~22 implementors that live in ``packages/`` —
``clausal-scipy``'s ``_LookupPredicate``, ``clausal-spacy``'s
``_SpacyPredicate``, ``clausal-provenance``'s ``_RegistrationGoal``.  None of
them subclass anything from the engine.  Their entire contract with Clausal is

    def _get_dispatch(self): -> dispatch_fn

so widening that protocol to take the call site's arity breaks all of them at
their *correct* arity.  ``foreign_pair`` is deliberately written the long way,
without importing any engine base class, so that this file keeps passing only
as long as the single-argument protocol is honoured.
"""

from clausal.logic.variables import deref, unify
from clausal.logic.trampoline import DONE


def _foreign_pair_dispatch(this_generator, _proceed, _fail, _catcher,
                           key, value_var, trail):
    """foreign_pair(Key, Value) — a two-argument foreign goal."""
    table = {"a": 1, "b": 2}
    val = table.get(deref(key))
    if val is None:
        yield (_fail, DONE)
        return
    if bool(unify(value_var, val, trail)):
        yield (_proceed, None)
    yield (_fail, DONE)


class _ForeignPairPredicate:
    """No base class, no metaclass — exactly like the packages' adapters."""

    def _get_dispatch(self):
        return _foreign_pair_dispatch

    def __repr__(self):
        return "foreign_pair/2"


foreign_pair = _ForeignPairPredicate()
