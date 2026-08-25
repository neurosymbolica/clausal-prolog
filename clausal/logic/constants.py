"""Load-time support for -constants declarations.

A constant is a module global bound to a ground value before any clause
statement executes; clause construction embeds the value, so downstream
(indexing, solve, translation) never sees a name. This module supplies the
groundness gate the lowered assignment routes through — extended (2026-08-25)
to also FREEZE the value it gates: "constant" means constant, so a structured
constant (list/dict/set) must not be mutable from the Python side (most
commonly reached through a ``++`` escape holding a reference to the shared
term). See ``_freeze`` below and the Constants section of docs/syntax.md.
"""
from clausal.logic.variables import Var
from clausal.logic.predicate import is_term_instance
from clausal.terms import DictTerm, SetTerm


class ConstantNotGroundError(ValueError):
    """A -constants RHS produced a value containing an unbound variable."""


# ── Frozen structural subclasses ──────────────────────────────────────────────
#
# Type-PRESERVING freezing, not type-swapping: a frozen list is still a
# ``list`` (``isinstance(x, list)`` stays True), so unification, clause-head
# indexing, and the C unify extension (which tests structural class via
# ``PyList_Check``/``PyDict_Check``/``PyAnySet_Check`` — subclass-inclusive,
# not ``*_CheckExact`` — verified against clausal/logic/variables/_variables.c)
# all see no difference from a literal. Only the mutating methods are
# disabled, each raising ``TypeError`` naming the constant-immutability rule.


def _frozen_constant_mutation(self, *_args, **_kwargs):
    raise TypeError(
        "-constants: this value is a frozen constant (structured -constants "
        "values are immutable); mutation is not permitted — build a fresh, "
        "non-constant value instead of mutating the shared one")


class _FrozenList(list):
    """A -constants list value, frozen after the load-time groundness gate."""


class _FrozenDict(dict):
    """A -constants dict value, frozen after the load-time groundness gate."""


class _FrozenSet(set):
    """A -constants set value, frozen after the load-time groundness gate.

    (Set-shaped ``++`` escape results only — a source-level ``{...}`` set
    literal in a -constants RHS lowers to ``SetTerm``, which is already
    immutable by construction; see ``_freeze``.)
    """


for _cls, _mutators in (
    (_FrozenList, ("append", "extend", "insert", "__setitem__",
                   "__delitem__", "pop", "remove", "clear", "sort",
                   "reverse", "__iadd__", "__imul__")),
    (_FrozenDict, ("__setitem__", "__delitem__", "pop", "popitem",
                   "clear", "update", "setdefault")),
    (_FrozenSet, ("add", "discard", "remove", "pop", "clear", "update",
                  "intersection_update", "difference_update",
                  "symmetric_difference_update", "__ior__", "__iand__",
                  "__ixor__", "__isub__")),
):
    for _mutator in _mutators:
        setattr(_cls, _mutator, _frozen_constant_mutation)
del _cls, _mutators, _mutator


def _freeze(value):
    """Recursively freeze *value* into its immutable -constants form.

    Mirrors exactly the structural type a clause-body literal of the same
    source shape builds (list, ``DictTerm``, ``SetTerm``, tuple, functor
    instance) — freezing never changes *which* type a value is, only
    whether it can be mutated.

    ``DictTerm``'s ``.data`` is the one case where freezing can't happen
    through the public constructor: ``DictTerm.__init__`` takes a defensive
    ``dict(data)`` copy, so passing a ``_FrozenDict`` in gets silently
    downgraded back to a plain ``dict``. Freezing it is still possible —
    just not through ``__init__`` — by patching the ``_data`` slot directly
    after construction (``DictTerm`` has no custom ``__setattr__``, so this
    is an ordinary, unresisted slot assignment).

    ``SetTerm`` needs no freezing at all: it is backed by a ``frozenset``
    with no public mutator, immutable by construction.

    Compound-term (functor / ``PredicateMeta``) instances are the one
    deliberate exception to recursion: their field interiors are left
    shared, unfrozen — see the Constants section of docs/syntax.md for the
    documented boundary (a functor constant's *fields* can still be mutated
    if a field itself holds a mutable value, e.g. ``Container([1, 2, 3])``).
    """
    if isinstance(value, (_FrozenList, _FrozenDict, _FrozenSet)):
        return value  # already frozen
    if isinstance(value, DictTerm):
        if not isinstance(value.data, _FrozenDict):
            frozen_data = _FrozenDict(
                (_freeze(k), _freeze(v)) for k, v in value.data.items())
            value._data = frozen_data  # bypass __init__'s defensive copy
        return value
    if isinstance(value, SetTerm):
        return value  # frozenset-backed already; no public mutator
    if is_term_instance(value):
        return value  # functor instance: field interiors stay shared
    if isinstance(value, tuple):
        return tuple(_freeze(v) for v in value)
    if isinstance(value, list):
        return _FrozenList(_freeze(v) for v in value)
    if isinstance(value, dict):
        return _FrozenDict((_freeze(k), _freeze(v)) for k, v in value.items())
    if isinstance(value, (set, frozenset)):
        return _FrozenSet(_freeze(v) for v in value)
    if isinstance(value, bytearray):
        return bytes(value)
    return value


def _contains_var(value) -> bool:
    if isinstance(value, Var):
        return True
    if isinstance(value, (list, tuple, set, frozenset)):
        return any(_contains_var(v) for v in value)
    if isinstance(value, dict):
        return any(_contains_var(k) or _contains_var(v)
                   for k, v in value.items())
    # Term objects (Compound, KWTerm, compile-time PredicateMeta instances,
    # Seg* containers): delegate to the canonical recursive ground check
    # instead of duck-typing an ``.args`` tuple — compile-time predicate
    # classes hold fields by name (``_fields``/``__slots__``), not a generic
    # ``.args``, so ``getattr(value, "args", None)`` silently missed them.
    # ``Compound.is_ground`` (terms.py:587) does the same delegation, lazily,
    # to dodge the circular import (this module is imported very early, from
    # import_hook.py, before clausal.logic.builtins exists).
    from clausal.logic.builtins._helpers import _is_ground  # noqa: PLC0415
    return not _is_ground(value)


def check_constant_ground(name: str, value):
    """Gate a -constants binding: check-and-freeze.

    Returns *value* recursively frozen (see ``_freeze``) iff it is ground;
    raises ``ConstantNotGroundError`` otherwise. The module global and the
    ``module_constant/3`` reflection registry both end up holding this same
    frozen value — see ``register_module_constant`` below.
    """
    if _contains_var(value):
        raise ConstantNotGroundError(
            f"-constants: `{name}` must be fully ground at load time; "
            f"got a value containing an unbound variable: {value!r}")
    return _freeze(value)


def register_module_constant(module, name: str, value) -> None:
    """Record a declared ``-constants`` ``(name, value)`` pair on *module*.

    Backs ``module_constant/3`` reflection (docs/builtins.md). Called from
    generated code immediately after ``$check_constant_ground``, so *value*
    is already gated (ground) and frozen — the registry and the module
    global end up holding the identical object.

    Only a module's OWN ``-constants`` declarations are recorded here — an
    imported constant is not re-registered on the importer; it stays
    reachable through its owning module's ``module_constant/3`` instead
    (see docs/import.md). This function is only ever called from the
    lowering of a ``-constants`` directive itself (never from
    ``-import_from``/``-import_module`` handling), so that choice falls out
    of the call sites rather than needing a check here.
    """
    module.constants[name] = value
