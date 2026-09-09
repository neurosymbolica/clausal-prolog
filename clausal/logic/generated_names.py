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

#: The bare TitleCase keys of ``INJECTED_RUNTIME_BUILTINS`` -- owned HERE,
#: statically, so a process that never imports the compiler (the reifier
#: reading ``$Var()``/``$PyThunk(...)`` back, a standalone formatter) still
#: knows every twin by name.  :func:`register_generated_names` asserts the
#: runtime table matches this list, so drift between the two is loud.
INJECTED_TITLECASE_NAMES: frozenset[str] = frozenset({
    "PredicateMeta", "Var", "Compound", "DictTerm", "SetTerm", "KWTerm",
    "Trail", "PyThunk", "FStringThunk", "Quantity", "BoolEq", "BoolImpl",
})

from clausal.pythonic_ast import nodes as _simple_ast  # noqa: E402

#: Every bare name that HAS a twin -- complete at import, no compiler needed.
#: This is what :func:`bare_name_of` (the readers) consults.
_TWIN_NAMES: frozenset[str] = (
    frozenset(_simple_ast.__all__) | INJECTED_TITLECASE_NAMES
) - BARE_ONLY

# The OBJECT each twinned name binds -- what :func:`dollar_ref` (the
# emitters) consults to decide whether a class IS the runtime binding for
# its own name.  The node classes are entered here, up front; the injected
# runtime types are entered by :func:`register_generated_names` when the
# compiler's table is built (the emitters live in the compiler, so they
# never run before that).
_TWIN_OBJECTS: dict[str, Any] = {
    name: getattr(_simple_ast, name) for name in _simple_ast.__all__
    if name not in BARE_ONLY
}


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
        twin = dollar_name(name)
        if twin in table and table[twin] is not value:
            raise ValueError(
                f"{twin} is already bound to a different object than {name}; "
                f"a twin is an alias of its bare name, never a second binding"
            )
        twinned[twin] = value
    return twinned


def register_generated_names(table: dict) -> dict:
    """Enter the injected runtime types' OBJECTS into the registry
    :func:`dollar_ref` consults, and return *table* twinned.

    Called by the ONE engine table of injected runtime names
    (``INJECTED_RUNTIME_BUILTINS``).  Its bare TitleCase keys must be
    exactly :data:`INJECTED_TITLECASE_NAMES` -- the static list the readers
    already trust -- so an addition to one without the other fails HERE, at
    import, naming the drift, rather than as a reifier that silently stops
    recognising a new ``$Name(...)``.
    """
    bare = {
        name for name in table
        if not name.startswith("$") and name not in BARE_ONLY
    }
    if bare != INJECTED_TITLECASE_NAMES:
        raise RuntimeError(
            "INJECTED_RUNTIME_BUILTINS drifted from "
            "generated_names.INJECTED_TITLECASE_NAMES: "
            f"unexpected {sorted(bare - INJECTED_TITLECASE_NAMES)}, "
            f"missing {sorted(INJECTED_TITLECASE_NAMES - bare)}"
        )
    for name in bare:
        _TWIN_OBJECTS[name] = table[name]
    return with_dollar_twins(table)


def dollar_ref(cls: Any) -> str:
    """The generated-code spelling of a class *cls* an emitter wants to name.

    Its ``$`` twin when *cls* IS the runtime table's binding for its own
    name (a ``simple_ast`` node class, an injected runtime type), otherwise
    its bare ``__name__`` -- a user's own predicate class, bound in the
    module by the user's own clauses, is the user's to reach bare.
    """
    name = cls.__name__
    if _TWIN_OBJECTS.get(name) is cls:
        return dollar_name(name)
    return name


def bare_name_of(name: str) -> str:
    """Undo :func:`dollar_name` for a consumer that reads generated code
    back (the reifier, the call-site index key): ``$Var`` -> ``Var``.  A
    ``$`` name that is not a twin (``$unify``, ``$define_predicate``) is
    returned unchanged."""
    if name.startswith("$") and name[1:] in _TWIN_NAMES:
        return name[1:]
    return name


__all__ = [
    "BARE_ONLY", "INJECTED_TITLECASE_NAMES", "dollar_name",
    "with_dollar_twins", "register_generated_names", "dollar_ref",
    "bare_name_of",
]
