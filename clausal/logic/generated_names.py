"""The ``$``-prefixed spelling of the runtime names generated code reaches.

Ruling (2026-09-09): TitleCase has no role in Clausal code -- a Python class
is reached via ``++ClassName``.  The names generated code needs bound in a
module's namespace (the ``simple_ast`` node classes ``Predicate``/``Call``/
``Add``/..., and the injected runtime types ``Var``/``Compound``/
``Quantity``/``PyThunk``/...) are therefore referenced ``$``-prefixed, the
convention ``$unify``/``$deref``/``$mint`` already follow: ``$`` is not a
legal identifier character, so a user predicate spelled ``Sub`` or ``Var``
can never shadow the class a clause body compiles through.

ONE table.  :func:`with_dollar_twins` is the only place a twin is minted;
every namespace that seeds these names (``INJECTED_RUNTIME_BUILTINS`` in
``clausal/logic/compiler/predicate.py``, ``runtime_builtins`` in
``clausal/import_hook.py``) passes its bare table through it, and the
emitters ask :func:`dollar_ref` for the spelling to emit.

Deprecation window: the BARE aliases stay bound alongside their twins for
now (a bare ``Var()`` in user code still resolves; the TitleCase lint warns
and suggests ``++Var``).  They are removed later -- see
todo/remove-bare-injected-titlecase-globals-after-deprecation-2026-09-09.md.
``Undefined`` is the canonical Kleene value and stays bare by design; it is
the one name that gets no twin.
"""

from __future__ import annotations

from typing import Any

#: Names that stay bare-only: no ``$`` twin is minted for them.
BARE_ONLY: frozenset[str] = frozenset({"Undefined"})

# Every bare name that has been given a twin, with the object it binds --
# the registry :func:`dollar_ref` and :func:`bare_name_of` consult.  Filled
# by :func:`with_dollar_twins`; both seeding namespaces run through it at
# import time, so the registry is complete before any clause compiles.
_TWINNED: dict[str, Any] = {}


def _register(table: dict) -> None:
    for name, value in table.items():
        if not name.startswith("$") and name not in BARE_ONLY:
            _TWINNED[name] = value


# The node classes are known here, up front, so :func:`dollar_ref` answers
# the same spelling whether or not the import hook has been loaded yet (a
# compiler entered directly from Python compiles the same ``$Add``).
from clausal.pythonic_ast import nodes as _simple_ast  # noqa: E402

_register({name: getattr(_simple_ast, name) for name in _simple_ast.__all__})


def dollar_name(name: str) -> str:
    """``Var`` -> ``$Var``.  Idempotent on an already-prefixed name."""
    return name if name.startswith("$") else "$" + name


def with_dollar_twins(table: dict) -> dict:
    """Return *table* with a ``$``-twin entry for every bare key.

    Bare keys stay (the deprecation window); ``$`` keys and
    :data:`BARE_ONLY` names are passed through untouched.  The twin binds
    the IDENTICAL object -- it is an alias, never a copy.  Pure: a test
    may twin its own mock namespace without touching the registry.
    """
    twinned = dict(table)
    for name, value in table.items():
        if name.startswith("$") or name in BARE_ONLY:
            continue
        twinned[dollar_name(name)] = value
    return twinned


def register_generated_names(table: dict) -> dict:
    """Enter *table*'s bare names into the registry :func:`dollar_ref` /
    :func:`bare_name_of` consult, and return the twinned table.  Called by
    the ONE engine table of injected runtime names
    (``INJECTED_RUNTIME_BUILTINS``); the node classes are registered at
    import above."""
    _register(table)
    return with_dollar_twins(table)


def dollar_ref(cls: Any) -> str:
    """The generated-code spelling of a class *cls* an emitter wants to name.

    Its ``$`` twin when *cls* IS the runtime table's binding for its own
    name (a ``simple_ast`` node class, an injected runtime type), otherwise
    its bare ``__name__`` -- a user's own predicate class, bound in the
    module by the user's own clauses, is the user's to reach bare.
    """
    name = cls.__name__
    if _TWINNED.get(name) is cls:
        return dollar_name(name)
    return name


def bare_name_of(name: str) -> str:
    """Undo :func:`dollar_name` for a consumer that reads generated code
    back (the reifier, the call-site index key): ``$Var`` -> ``Var``.  A
    ``$`` name that is not a twin (``$unify``, ``$define_predicate``) is
    returned unchanged."""
    if name.startswith("$") and name[1:] in _TWINNED:
        return name[1:]
    return name


__all__ = [
    "BARE_ONLY", "dollar_name", "with_dollar_twins",
    "register_generated_names", "dollar_ref", "bare_name_of",
]
