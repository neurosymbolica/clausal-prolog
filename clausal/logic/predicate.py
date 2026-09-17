"""clausal.logic.predicate — Predicate-as-Class via PredicateMeta.

PredicateMeta turns a class into a first-class predicate:
  - Class-level clause storage, dispatch, and signature
  - Locking to prevent cross-module mutation
  - __call__ override for partial term creation (missing fields → Var())
  - __init__, __eq__, __repr__, __match_args__ — no @dataclass needed

Usage:
    class fib(metaclass=PredicateMeta):
        _fields = ('n', 'f')

    # fib is a class (not a singleton instance)
    # fib(n=0) creates a term with f=Var()
    # fib._clauses, fib._get_dispatch(), fib._assertz(clause), etc.
"""

from __future__ import annotations

import contextlib
import dataclasses
import os
import re
import sys
import textwrap
from typing import Any, Callable

from clausal._suffixes import CLAUSAL_SUFFIXES


_MISSING = object()  # sentinel for "field not provided"


# ── Attributable term-construction errors ────────────────────────────────────
#
# Constructing a term whose keyword names do not match the bound class's
# ``_fields`` used to surface as a bare, context-free
#
#     TypeError: __init__() got an unexpected keyword argument 'arg_1'
#
# with no functor, no field names and no source location.  See
# ``todo/done/functor-field-name-mismatch-diagnostic.md``.  Two distinct authoring
# mistakes produce that identical message, and the error below names which one
# it is, because that is what lets an author pick a *different* fix instead of
# re-rolling the same one.

# ``arg_0`` .. ``arg_N`` — the placeholder field names a directive-minted class
# carries until a real clause unseats it (see ``_unseat_directive_minted`` in
# clausal/templating/term_rewriting.py).
_PLACEHOLDER_FIELD_RE = re.compile(r"\Aarg_\d+\Z")

# Directory of the ``clausal`` package, used to skip engine frames when
# attributing a source site to user code.
#: The engine package's directory, with a TRAILING SEPARATOR.
#:
#: The separator is the whole point: a bare prefix compare would count a
#: SIBLING whose name merely starts with this one as engine-internal.  That is
#: not hypothetical here — the extension distributions install alongside the
#: package (``…/site-packages/clausal`` and ``…/site-packages/clausal_jax``),
#: so ``clausal_jax/x.py``.startswith(``…/clausal``) is True and a frame from
#: one of them would be SKIPPED while looking for the user's call site, which
#: attributes a diagnostic to whatever lies further up the stack instead.
_CLAUSAL_PKG_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "")

# How far to walk the stack looking for a user frame before giving up.
_SITE_SEARCH_DEPTH = 12


def _is_logic_var_name(name: str) -> bool:
    """True for a Clausal logic-variable spelling (``_x`` or ``ALLCAPS``).

    Mirrors ``clausal.templating.term_rewriting._is_logic_var_name``; kept
    local so this module stays free of a templating import.  Constant-shaped
    names (``_PI_``) are excluded too — pinned by
    test_var_classifier_conformance.
    """
    if name == "_" or name.startswith("__"):
        return False
    if name.startswith("_"):
        return True
    # Capital initial (ISO): ``X``, ``FOO``, ``Foo``.  ``Foo`` joined
    # this class on 2026-09-10 -- see term_rewriting._is_logic_var_name,
    # which is the copy that carries the full rationale.  All five
    # copies move together (test_var_classifier_conformance).
    return name[:1].isupper()


def _all_placeholders(names: tuple[str, ...]) -> bool:
    """True if *names* is non-empty and entirely ``arg_N`` placeholders."""
    return bool(names) and all(_PLACEHOLDER_FIELD_RE.match(n) for n in names)


def module_source_path(module_dict_or_module):
    """Canonical source path of a module (or of its ``__dict__``).

    The identity a clause-ownership check needs.  One ``.clausal`` file
    legitimately compiles under two module *names* in one process — a dotted
    ``-import_from`` uses the dotted name, ``clausal.testing.
    load_clausal_module`` a private ``_clausal_test_*`` one — so keying
    ownership on the name would make a file refuse to load beside itself.  The
    path does not move.
    """
    if isinstance(module_dict_or_module, dict):
        path = module_dict_or_module.get("__file__")
    else:
        path = getattr(module_dict_or_module, "__file__", None)
    if not path:
        return None
    try:
        return os.path.realpath(path)
    except OSError:  # pragma: no cover — defensive
        return path


def record_clause_source(pred_cls, module_name: str, module_dict: dict) -> None:
    """Note whose load wrote ``pred_cls._clauses``.

    Called at the one site that assigns the clause list wholesale
    (``compiler_v2`` step 4; the two deferred paths in
    ``clausal.import_hook`` this used to name went with the v1 pipeline).
    The mutation gate's ownership policy reads it back — it is what tells a
    module reloading its own clauses from a module about to destroy
    another's, and it is keyed on the source PATH for that reason.
    """
    pred_cls._clauses_source = (module_name, module_source_path(module_dict))


def _source_site(depth: int) -> tuple[str, int] | None:
    """Return ``(filename, lineno)`` of the nearest user frame above *depth*.

    A ``.clausal`` frame is preferred; otherwise the first frame outside the
    ``clausal`` package wins, so a term built from Python is attributed to the
    Python caller rather than to engine internals.  Returns ``None`` when the
    stack yields nothing useful.
    """
    try:
        frame = sys._getframe(depth)  # noqa: SLF001
    except ValueError:  # pragma: no cover — stack shallower than expected
        return None
    for _ in range(_SITE_SEARCH_DEPTH):
        if frame is None:
            return None
        filename = frame.f_code.co_filename
        if filename.endswith(CLAUSAL_SUFFIXES) or not filename.startswith(
            _CLAUSAL_PKG_DIR
        ):
            return (filename, frame.f_lineno)
        frame = frame.f_back
    return None


def _format_site(site: tuple[str, int] | None) -> str:
    return f"{site[0]}:{site[1]}" if site else "<unknown>"


def _format_fields(names: tuple[str, ...]) -> str:
    return f"({', '.join(names)})"


def _camel_case(name: str) -> str:
    """``ash_query_key`` → ``AshQueryKey`` — a legal -import_from alias."""
    return "".join(part.title() for part in name.split("_") if part) or "Alias"


class ClausalTermConstructionError(TypeError):
    """A term was built with field names its bound class does not have.

    A ``TypeError`` subclass so existing ``except TypeError`` handlers keep
    working.  Carries the functor, both field-name tuples, and both source
    locations as attributes for programmatic consumers.
    """

    def __init__(
        self,
        message: str,
        *,
        functor: str,
        arity: int,
        supplied_fields: tuple[str, ...],
        registered_fields: tuple[str, ...],
        registered_at: tuple[str, int] | None,
        constructed_at: tuple[str, int] | None,
    ) -> None:
        super().__init__(message)
        self.functor = functor
        self.arity = arity
        self.supplied_fields = supplied_fields
        self.registered_fields = registered_fields
        self.registered_at = registered_at
        self.constructed_at = constructed_at


def _construction_hint(
    functor: str,
    supplied: tuple[str, ...],
    registered: tuple[str, ...],
) -> str:
    """Name the *class* of authoring mistake behind a field-name mismatch."""
    if not registered:
        # The bound class is a 0-arity ATOM but arguments were supplied.  Under
        # the snake_case convention a vocabulary atom and a predicate routinely
        # share a spelling; the import binds last and wins.  See "Phenomenon A"
        # in implementation_plans/dict-atom-keys-vs-predicates.md.
        confidence = (
            "almost certainly"
            if all(_is_logic_var_name(n) for n in supplied)
            else "likely"
        )
        n = len(supplied)
        body = (
            f"{functor} resolved to a 0-arity atom, but it was called with "
            f"{n} argument(s) — {confidence} an imported atom is shadowing a "
            f"same-named predicate. A module that both exports the predicate "
            f"{functor}/{n} and imports the atom {functor} binds the atom "
            f"last, so every call constructs the atom. Fix: un-export "
            f"{functor}/{n}, or import the atom under an alias — "
            f"-import_from(vocab, [alias({functor}, {_camel_case(functor)})]) "
            f"— or keep the key a string."
        )
    elif len(supplied) > len(registered):
        # More arguments than the class has fields.  Arity — unlike field
        # names — is the functor's cross-module contract, so this is never a
        # cosmetic disagreement: some declaration of this name is wrong.
        body = (
            f"{functor} takes {len(registered)} argument(s) but "
            f"{len(supplied)} were supplied. A functor name has exactly one "
            f"arity in Clausal, so a second declaration of {functor} with a "
            f"different arity — or an imported {functor} of another arity "
            f"shadowing this one — cannot be reconciled. Fix: give every "
            f"declaration and clause head of {functor} the same number of "
            f"arguments, or rename one of them."
        )
    elif _all_placeholders(supplied) or _all_placeholders(registered):
        body = (
            "a functor minted by a directive keeps placeholder arg_N names "
            "until a real clause unseats it — -dynamic(f/N) with no clause in "
            "that file leaves the class named (arg_0, ..). Check whether both "
            "modules declare the same functor, and whether an -import_from "
            "rebinds this name after the local declaration: the import wins, "
            "so later constructions use the local field names against the "
            "foreign class. Fix: declare the functor in exactly one module "
            "and import it."
        )
    else:
        body = (
            "the two declarations of this functor disagree on argument names. "
            "Check whether both modules declare it — an -import_from rebinds "
            "the name after a local -module/-private declaration, so later "
            "constructions use the local field names against the foreign "
            "class. Fix: declare the functor in exactly one module and "
            "import it."
        )
    return textwrap.fill(
        f"({body})",
        width=79,
        initial_indent="  ",
        subsequent_indent="   ",
        break_long_words=False,
        break_on_hyphens=False,
    )


def _term_construction_error(
    cls: Any, kwargs: dict, constructed_at: tuple[str, int] | None
) -> ClausalTermConstructionError:
    """Build the attributable error for a field-name mismatch on *cls*."""
    functor = cls.__name__
    registered = tuple(cls._fields)
    supplied = tuple(kwargs)
    registered_at = getattr(cls, "_registered_at", None)
    message = (
        f"functor {functor}/{len(registered)} was constructed with field names "
        f"{_format_fields(supplied)}\n"
        f"but its class was registered with {_format_fields(registered)}\n"
        f"  registered by: {_format_site(registered_at)}\n"
        f"  constructed at: {_format_site(constructed_at)}\n"
        f"{_construction_hint(functor, supplied, registered)}"
    )
    return ClausalTermConstructionError(
        message,
        functor=functor,
        arity=len(registered),
        supplied_fields=supplied,
        registered_fields=registered,
        registered_at=registered_at,
        constructed_at=constructed_at,
    )


def _overflow_supplied_fields(
    registered: tuple[str, ...], n_args: int
) -> tuple[str, ...]:
    """Field names *n_args* positional arguments would have been given.

    The positions that fit take the class's own names; the surplus take the
    ``arg_N`` placeholders the rewriter would have derived for them, so an
    arity overflow reads the same way as the keyword-path mismatch.
    """
    return tuple(registered[:n_args]) + tuple(
        f"arg_{i}" for i in range(len(registered), n_args)
    )


def _term_arity_error(
    cls: Any, n_args: int, kwargs: dict, constructed_at: tuple[str, int] | None
) -> ClausalTermConstructionError:
    """Build the attributable error for positional overflow on *cls*.

    ``PredicateMeta.__call__`` used to *drop* positional arguments past
    ``len(_fields)``, so ``some_atom(A, B)`` on a zero-arity class returned a
    silently wrong term.  That is worse than the keyword path's bare
    ``TypeError``: there is no exception at all to repair against.
    """
    functor = cls.__name__
    registered = tuple(cls._fields)
    supplied = _overflow_supplied_fields(registered, n_args) + tuple(
        k for k in kwargs if k not in registered[:n_args]
    )
    registered_at = getattr(cls, "_registered_at", None)
    message = (
        f"functor {functor}/{len(registered)} was constructed with {n_args} "
        f"positional argument(s)\n"
        f"but its class was registered with {len(registered)} field(s) "
        f"{_format_fields(registered)}\n"
        f"  registered by: {_format_site(registered_at)}\n"
        f"  constructed at: {_format_site(constructed_at)}\n"
        f"{_construction_hint(functor, supplied, registered)}"
    )
    return ClausalTermConstructionError(
        message,
        functor=functor,
        arity=len(registered),
        supplied_fields=supplied,
        registered_fields=registered,
        registered_at=registered_at,
        constructed_at=constructed_at,
    )


_init_cache: dict[tuple[str, ...], Callable] = {}


def _make_init(fields: tuple[str, ...]):
    """Generate an __init__ that accepts fields as keyword args with _MISSING default."""
    cached = _init_cache.get(fields)
    if cached is not None:
        return cached
    if not fields:
        def __init__(self):
            pass
        _init_cache[fields] = __init__
        return __init__
    params = ", ".join(f"{f}=_MISSING" for f in fields)
    assigns = "\n    ".join(f"self.{f} = {f}" for f in fields)
    code = f"def __init__(self, {params}):\n    {assigns}"
    globs = {"_MISSING": _MISSING}
    exec(code, globs)  # noqa: S102
    fn = globs["__init__"]
    _init_cache[fields] = fn
    return fn


_fast_new_cache: dict[tuple[str, ...], Callable] = {}


def _make_fast_new(fields: tuple[str, ...]):
    """Generate a ``_clausal_new`` classmethod: positional, no checks.

    Additive fast path alongside ``_make_init`` / ``PredicateMeta.__call__``.
    Callers must supply every field, in ``_fields`` order — there is no
    missing-field backfill (no ``Var()`` defaults) and no arity checking.
    Parameters are named ``_a0.._aN`` (not the field names) so a field
    literally named e.g. ``x`` can never shadow a parameter.

    This path bypasses ``PredicateMeta.__call__`` entirely, so any future
    construction-time hook (interning, validation, provenance) must be
    added in both places.
    """
    cached = _fast_new_cache.get(fields)
    if cached is not None:
        return cached
    params = ", ".join(f"_a{i}" for i in range(len(fields)))
    assigns = "\n    ".join(
        f"inst.{f} = _a{i}" for i, f in enumerate(fields)
    )
    code = f"def _clausal_new(cls, {params}):\n    inst = cls.__new__(cls)\n    {assigns}\n    return inst"
    globs: dict[str, Any] = {}
    exec(code, globs)  # noqa: S102
    fn = globs["_clausal_new"]
    _fast_new_cache[fields] = fn
    return fn


def _term_iter(self):
    """Iterate solutions for this term as a goal.

    Enables ``for trail in greeting(X := Var()): print(deref(X))``.
    """
    from clausal.logic.solve import solve  # noqa: PLC0415
    return solve(self)


def _make_eq(fields: tuple[str, ...]):
    """Generate an __eq__ that compares field values."""
    def __eq__(self, other):
        if type(self) is not type(other):
            return NotImplemented
        return all(getattr(self, f) == getattr(other, f) for f in fields)
    return __eq__


# ── The class-as-value calling convention ────────────────────────────────────
#
# The C engine reaches every Python term type the same way: a plain
# ``PyObject_GetAttrString(t, "__unify__")`` followed by ``hook(other, trail)``
# (``clausal/logic/variables/_variables.c``).  That lookup means two different
# things depending on what ``t`` is, and PredicateMeta puts *both* kinds of
# ``t`` into terms:
#
#   * ``t`` is an **instance** (``cite(art_6_1)``).  The lookup binds, so the
#     call lines up with the written ``(self, other, trail)``.
#   * ``t`` is the **class itself**.  A bare functor name is a legal term value
#     in Clausal — ``FUNCTOR_NAME is cite`` puts the class on a unification
#     side — and attribute lookup on a class hands back the *unbound* function.
#     The same two-argument call then lands ``other`` in ``self`` and leaves
#     ``trail`` unfilled.
#
# That second case is
# ``todo/done/internal-unify-typeerror-reaches-the-user-as-error-text.md``.  The
# author of a legal-looking goal saw
#
#     TypeError: _make_unify.<locals>.__unify__() missing 1 required
#                positional argument: 'trail'
#
# — a closure inside the engine and a parameter they have never written, in
# place of their goal simply failing.  Measured cost in the formalization
# corpus: 10 repair attempts across two runs, neither recovering, because a
# message about ``trail`` offers nothing to edit.  This is the second time a
# lost ``trail`` argument has escaped as the whole of a user-facing error —
# ``todo/done/arity-mismatch-reports-a-missing-trail-argument.md`` was the
# first, from a different seam — which is a standing hint that any Python
# ``TypeError`` naming ``trail`` is an engine fault wearing a user's clothes.
#
# Arity-0 atoms were always immune, not by luck but by decision: PredicateMeta
# installs no hooks on them at all, because "the class IS the value" and
# identity comparison is the whole of unification for them.  The sentinel
# default below extends that decision to functor classes of every arity.
#
# A descriptor that hands each caller its own signature is the tidier way to
# say this and was written first, then thrown away: it puts a Python frame on
# *every* instance-side hook lookup, which took `t.__unify__` from 35ns to
# 103ns and showed up end-to-end on term head matching — the hottest path
# through the unifier.  An ``is`` against a module-level object costs one
# pointer compare on that path instead.  It is not a heuristic: only a
# two-argument call can leave the default in place, and a two-argument call is
# by construction the class-side one.
_CLASS_CALL = object()


def _make_unify(fields: tuple[str, ...], owner: type):
    """Generate a ``__unify__`` that recursively unifies corresponding fields.

    Called by the C ``do_unify`` when two PredicateMeta instances of the
    same type appear on both sides of a unification.

    *owner* is the class this hook is installed on.  It is required rather than
    defaulted because the class-side branch answers ``self is owner``, and an
    ``owner`` that quietly defaulted to ``None`` would make ``unify(cls, None)``
    say yes.
    """
    def __unify__(self, other, trail=_CLASS_CALL):
        if trail is _CLASS_CALL:
            # Class-side call: ``self``/``other`` are really ``other``/``trail``
            # and the term is *owner* itself.  A bare class carries no
            # arguments, so identity is the only way it can unify; anything
            # else defers with ``NotImplemented`` rather than answering
            # ``False``, leaving the C unifier's own fallback — the symmetric
            # hook, then rich compare — free to decide exactly as it does for
            # an arity-0 atom.  This branch therefore cannot change *whether*
            # any two terms unify, only stop the engine crashing on the ask.
            return True if self is owner else NotImplemented
        if type(self) is not type(other):
            return NotImplemented
        from clausal.logic.variables import unify  # noqa: PLC0415
        for f in fields:
            if not unify(getattr(self, f), getattr(other, f), trail):
                return False
        return True
    return __unify__


def _make_occurs_check(fields: tuple[str, ...]):
    """Generate an ``__occurs_check__`` that recurses into field values.

    Called by the C ``do_occurs_check`` for PredicateMeta instances. Without
    it, occurs-check falls through to ``return 0`` and unify_with_occurs_check
    would build a cyclic term through a predicate term (A01-F001).

    Carries the same class-as-value sentinel as ``_make_unify``: the C side
    calls ``hook(var)`` after a bare ``getattr``, so on a class-valued term it
    loses an argument in exactly the same way.
    """
    def __occurs_check__(self, var=_CLASS_CALL):
        if var is _CLASS_CALL:
            # Class-side call: ``self`` is really the variable, and the term is
            # the bare class, which holds no field values — so nothing can
            # occur in it.  Same reasoning PredicateMeta applies to arity-0
            # atoms, which get no hook at all.
            return False
        from clausal.logic.variables import occurs_check  # noqa: PLC0415
        return any(occurs_check(var, getattr(self, f)) for f in fields)
    return __occurs_check__


def _make_repr(fields: tuple[str, ...]):
    """Generate an instance __repr__: ``fib(n=1, f=2)``."""
    def __repr__(self):
        cls_name = type(self).__name__
        parts = ", ".join(f"{f}={getattr(self, f)!r}" for f in fields)
        return f"{cls_name}({parts})"
    return __repr__


def _head_arity(head: Any) -> int | None:
    """How many arguments the clause head *head* has, or ``None`` if unreadable.

    Three head shapes reach here and the third one used to crash:

    - a ``Compound``-style head with an ``args`` sequence;
    - a term instance, whose arity is its field count;
    - the **class itself**, which is how a 0-arity fact atom (``myflag,``)
      stores its head — ``red() is red``, so the class IS the value.  That one
      reached ``term_field_names`` and raised ``TypeError: must be called with
      a dataclass type or instance``, which is nonsense in the mouth of an
      arity diagnostic.  ``_fields`` answers it directly.

    ``None`` means *unknown*, never *zero*: a head shape nobody anticipated
    must make the predicate's arity unknown — and so unrefusable — rather than
    let a diagnostic replace one failure with a stranger one.

    ``database.head_key`` reads the same shapes and knows two more (``KWTerm``,
    ``Call``), but it is not what this wants: it lives downstream of this module
    so reaching it means a per-call local import, it *raises* on anything else,
    and it rejects ``Compound(functor_var, args)`` — whose functor is unknown but
    whose arity is right there — because it needs a str functor and this needs
    only a count.
    """
    fields = getattr(head, "_fields", None) if isinstance(head, PredicateMeta) else None
    if fields is not None:
        return len(fields)
    try:
        args = getattr(head, "args", None)
        if args is not None:
            return len(args)
        return len(term_field_names(head))
    except Exception:  # noqa: BLE001 - see docstring
        return None


# The seven relocated predicate-state names (P3-3 Task 2).  Defined here
# because two different descriptors have to serve them: the metaclass
# properties on ``PredicateMeta`` (below), which answer ``cls._locked``, and
# the plain class-level properties injected into every predicate class's
# namespace (``_INSTANCE_STATE_PROPERTIES``), which answer
# ``instance._locked``.
_RELOCATED_STATE_NAMES = (
    "_clauses",
    "_clauses_source",
    "_dispatch_fn",
    "_lazy_recompile",
    "_signature",
    "_locked",
    "_dynamic_arities",
)


def _make_instance_state_property(name: str) -> property:
    """A read-only class-level property giving INSTANCES the class's state.

    Before P3-3 Task 2 these seven were plain per-class attributes, so an
    instance resolved them through the ordinary MRO walk —
    ``some_term._locked`` found the class attribute and returned it.  Moving
    them to METACLASS properties would have broken that silently: a metaclass
    descriptor is consulted for ``cls.x``, never for ``instance.x``, and
    ``__slots__`` leaves instances no ``__dict__`` to fall back on, so every
    one of the seven would raise ``AttributeError`` on an instance where it
    used to return a value.  Out-of-tree code reading ``instance._locked`` is
    unguarded against that.

    So each predicate class also carries a plain property of the same name,
    which delegates to the class (and therefore to the row).  The two faces
    coexist: ``type.__getattribute__`` finds the METACLASS property first for
    ``cls.x``, and instance lookup finds THIS one for ``instance.x``.  Reads
    are live — mutate through the class, see it through any instance.

    Read-ONLY on purpose: ``instance._locked = True`` raised ``AttributeError``
    before this task too (the name is not in ``__slots__`` and there is no
    instance ``__dict__``), so a setter here would be a new capability, not a
    restored one.
    """
    def _get(self):
        return getattr(type(self), name)

    _get.__name__ = name
    return property(
        _get,
        doc=f"Live read-through to ``type(self).{name}`` (P3-3 Task 2).",
    )


_INSTANCE_STATE_PROPERTIES = {
    name: _make_instance_state_property(name)
    for name in _RELOCATED_STATE_NAMES
}
"""One shared property object per name — a property takes its instance at call
time, so the same descriptor serves every predicate class and class creation
allocates nothing."""


def _describe_row(row) -> str:
    """``f/N`` plus where the row lives — for the I-1 refusal text."""
    functor, arity = row.key
    if row.detached:
        return f"{functor}/{arity} (the class's private detached row)"
    where = None
    if row.source:
        where = row.source[0]
    else:
        module_dict = getattr(row.db, "module_dict", None) or {}
        where = module_dict.get("__name__")
    return (f"{functor}/{arity} (module {where})" if where
            else f"{functor}/{arity} (a bound Database row)")


def _migrate_detached_clauses(old_row, new_row) -> None:
    """Carry clauses held on a DETACHED row onto the real row being bound.

    Final review I-1.  ``make_predicate`` mints a class with no Database, so
    ``P._assertz(...)`` before any load lands on the private row
    ``_detached_row`` created for it.  Binding that class to a real row used
    to move only ``dynamic_arities``/``locked``/``source``: the clauses stayed
    on a row that nothing could reach again, and since Task 2 made the row the
    single store there is no longer a second copy to recover them from — a
    later ``assertz`` through the class appended to the (empty) real row and
    the earlier clauses were simply gone, with no error, warning or write
    stamp.

    Two outcomes, never a third:

    * the target row has NO clauses — the ordinary standalone-then-loaded
      shape — so the detached clauses and their write stamps MOVE onto it and
      the detached row is emptied.  The bind stays lossless, which is what the
      docstring above claims of every other field it carries;
    * BOTH rows hold clauses — two independent clause sets for one predicate,
      with no rule saying which wins or in what order they would interleave —
      so the bind is REFUSED.  Silently picking one is the outcome I-1 exists
      to forbid.

    No transaction of its own: every in-tree ``_bind_row`` caller that can
    reach here already runs inside the ``Database.mutate`` its clause or
    dispatch install opened (``compiler_v2`` step 4/4a,
    ``compiler.predicate._install``, ``specialization._install_specialized``),
    so this write is inside that authorization and stamped by it.
    """
    if new_row.clauses:
        from clausal.logic.exceptions import (  # noqa: PLC0415
            LogicException, permission_error,
        )
        from clausal.terms import Compound  # noqa: PLC0415
        functor, arity = new_row.key
        raise LogicException(permission_error(
            "modify", "static_procedure", Compound("/", (functor, arity)),
            f"cannot bind {_describe_row(old_row)} onto "
            f"{_describe_row(new_row)}: the detached row holds "
            f"{len(old_row.clauses)} clause(s) and the target row already "
            f"holds {len(new_row.clauses)} — binding would silently discard "
            f"one set (retract or clear one side first)",
        ))
    new_row.ensure_clauses().extend(old_row.clauses)
    if old_row.writes:
        new_row.writes.extend(old_row.writes)
        old_row.writes.clear()
    # Emptied, not left holding a stale duplicate: this is a MOVE, and the
    # detached row can still be reached by a caller that kept a reference.
    old_row.clauses = []


class PredicateMeta(type):
    """Metaclass that turns a class with ``_fields`` into a predicate.

    The class body should define ``_fields`` as a tuple of field name strings.
    PredicateMeta generates ``__init__``, ``__eq__``, ``__repr__``,
    ``__match_args__``, and ``__slots__`` from that tuple — no ``@dataclass``
    needed.

    It also adds predicate dispatch machinery:
      _clauses, _dispatch_fn, _lazy_recompile, _signature, _locked,
      _clauses_source, _dynamic_arities
    all of which are READ-THROUGH PROPERTIES onto one
    :class:`~clausal.logic.database.PredRow` held in ``cls._row`` (P3-3
    Task 2) — the Database's row for this predicate once the class is bound
    into a module, a private detached row otherwise.
    """

    def __new__(
        mcs,
        name: str,
        bases: tuple,
        namespace: dict,
        **kwargs: Any,
    ) -> PredicateMeta:
        fields: tuple[str, ...] = namespace.get("_fields", ())

        # __slots__ for lightweight instances
        namespace["__slots__"] = fields
        namespace["__match_args__"] = fields

        # P3-3 Task 2 fix round 1 — the INSTANCE face of the seven relocated
        # state attributes.  Injected into the namespace (not assigned after
        # class creation) for two reasons: ``cls.__dict__`` is a read-only
        # mappingproxy, and a post-hoc ``setattr`` would be intercepted by the
        # metaclass property of the same name and written to the ROW instead
        # of the class.  A name that is also a FIELD is skipped — ``__slots__``
        # has already claimed that slot descriptor, and declaring both is a
        # ``ValueError`` at class creation (same rule the ``_clausal_new`` and
        # ``_registered_at`` guards below follow).
        for _state_name, _state_prop in _INSTANCE_STATE_PROPERTIES.items():
            if _state_name not in fields:
                namespace[_state_name] = _state_prop

        cls = super().__new__(mcs, name, bases, namespace, **kwargs)

        # Instance protocols — generated from _fields
        cls.__init__ = _make_init(fields)
        cls.__eq__ = _make_eq(fields)
        cls.__repr__ = _make_repr(fields)
        cls.__hash__ = None  # mutable terms shouldn't be hashable
        cls.__iter__ = _term_iter
        if fields:
            cls.__unify__ = _make_unify(fields, cls)
            cls.__occurs_check__ = _make_occurs_check(fields)
            # Additive fast constructor (Phase 0 Task 1): skip when a field
            # is literally named "_clausal_new" -- __slots__ already put a
            # member descriptor at that class attribute, and attaching a
            # classmethod over it would silently shadow the field. Atoms
            # (fields == ()) get nothing; there is no positional payload to
            # accelerate.
            if "_clausal_new" not in fields:
                cls._clausal_new = classmethod(_make_fast_new(fields))
        # For zero-field classes (atoms), skip __unify__/__occurs_check__: the
        # class IS the value, so identity comparison (C line 886: t1 == t2) and
        # the fallback PyObject_RichCompareBool handle unification correctly,
        # and an atom can never contain a Var.  A with-fields class used *as a
        # value* — a bare functor name — reaches the same answer through the
        # ``_CLASS_CALL`` branch of the hooks above rather than by having no
        # hook, since it still needs the instance form for its instances.
        #
        # (P3-1 §1b/R2: atoms are now global-by-spelling interned strs; the
        # per-module atom-identity class machinery that used to live here
        # (CLAUSAL_WARN_ATOM_IDENTITY / _make_atom_identity_unify) is deleted
        # — there is no more "same spelling, different owning module" case for
        # a real atom to warn about. Zero-field PredicateMeta classes are NOT
        # a retireable pre-pivot straggler, per the Task 7 sweep
        # (phase3-decomposition-and-p31-atom-pivot.md): the compiler no
        # longer mints one for a plain atom, but a 0-arity PREDICATE
        # declared with explicit call syntax — ``-module(m, [p()])``, as
        # opposed to the bare-Name atom syntax ``-module(m, [p])`` — still
        # legitimately mints one, and ``make_predicate(n, [])`` remains a
        # general-purpose, still-tested construction API for that shape
        # (``make_atom`` is NOT: P3-3 Task 7 made it return the atom str,
        # since a public factory minting a class atom was the one door left
        # for a class atom to enter a program that has none). This zero-field
        # fast path stays permanently, not just transitionally.)

        # Where this class was registered, for the field-name mismatch
        # diagnostic.  Frame 1 is the .clausal module body running the
        # generated ``class <functor>(metaclass=PredicateMeta)`` block (or the
        # Python caller of ``make_predicate``).  Skipped when a field of that
        # name exists, since __slots__ would have made it a descriptor.
        if "_registered_at" not in fields:
            cls._registered_at = _source_site(1)

        return cls

    def __init__(cls, name: str, bases: tuple, namespace: dict, **kwargs: Any) -> None:
        super().__init__(name, bases, namespace, **kwargs)
        # Predicate machinery — per-class, not inherited.
        #
        # P3-3 Task 2 (THE INVERSION): none of it lives on the class any more.
        # ``_clauses``, ``_clauses_source``, ``_dispatch_fn``,
        # ``_lazy_recompile``, ``_signature``, ``_locked`` and
        # ``_dynamic_arities`` are now read-through PROPERTIES (defined on this
        # metaclass, just below) onto ONE ``PredRow`` — the Database's
        # per-``(functor, arity)`` row.  ``_row`` is the single slot that used
        # to be seven, so every read and write keeps its old
        # last-writer-wins-on-one-class shape; what changes is WHERE the value
        # lands, and that a bound class and its Database can no longer disagree.
        #
        # ``None`` until first use.  A class the compiler binds into a module
        # gets the owning Database's row (``_bind_row``); a class minted with
        # no Database anywhere — bare ``make_predicate`` from Python, the
        # out-of-tree pattern, ``clausal.reflection``, ``clpb``, the builtin
        # registry — lazily gets a PRIVATE DETACHED row over a private
        # Database of its own (``_detached_row``).  That is the compatibility
        # mode: the duck type (``_clauses`` append, ``_get_dispatch()``,
        # ``_locked``) behaves exactly as before with no Database in sight.
        cls._row = None
        # The Database of the module that declared this predicate ``-table``,
        # stamped by ``Database.mark_tabled`` at load.  ``None`` everywhere
        # else.  Tabledness is recorded in the OWNING module's per-module db;
        # an ``-import_from`` shares this class with modules whose own db
        # knows nothing about it, so the stamp is what lets a caller-side
        # seam (``_is_tabled_naf`` at compile time, ``_naf_tabled`` at run
        # time) find the callee's home db — and with it the home table store
        # — instead of silently compiling ``not Imported(...)`` as plain NAF
        # (todo/cross-module-tabled-naf-loses-wfs-delay.md).  Which arities
        # are tabled stays the home db's answer (``is_tabled``); the class
        # carries only the pointer.
        cls._tabled_home_db = None  # Database | None

    # ── Predicate state: read-throughs onto the Database row ──────────────
    #
    # P3-3 Task 2.  Each of these WAS a plain per-class attribute set in
    # ``__init__`` above; each is now a property over ``cls._row``.  The
    # storage moved; the semantics did not — one slot per class, last writer
    # wins, ``None``/``False``/``[]`` defaults unchanged — so every existing
    # reader and writer (``cls._clauses.append(...)``,
    # ``cls._clauses[:] = ...``, ``cls._dispatch_fn = fn``, ``cls._locked``,
    # ``getattr(cls, "_clauses_source", None)``, the tests that reset a class
    # with ``cls._clauses = []``) keeps working verbatim.

    def _detached_row(cls):
        """Mint and cache this class's PRIVATE row — the compatibility mode.

        A ``PredicateMeta`` minted outside a ``.clausal`` load has no Database
        to be a row OF, and must still behave like a predicate: append to
        ``_clauses``, get a ``_dispatch_fn``, answer ``_get_dispatch()``.  It
        gets a ``PredRow`` over a private single-predicate ``Database`` nobody
        else can reach, so all seven attributes keep their old semantics with
        no Database anywhere in the caller's world.  ``_bind_row`` later
        replaces it if the class is compiled into a module.

        Lazy (not minted in ``__init__``) for two reasons: ``database.py``
        imports ``predicate.py``, so eager construction would need a
        module-level cycle; and a class whose predicate state is never touched
        — a pure term/data class — never pays for one.
        """
        row = cls._row
        if row is not None:
            return row
        from clausal.logic.database import Database  # noqa: PLC0415
        # ``getattr``, not ``cls._fields``: a bare
        # ``class X(metaclass=PredicateMeta): pass`` declares none, and
        # reading its ``_clauses`` used to be a plain attribute read that
        # could not fail.  The key is private to this row's private Database,
        # so an arity of 0 there costs nothing.
        fields = getattr(cls, "_fields", ()) or ()
        row = Database().row(cls.__name__, len(fields), create=True)
        # Marked so ``_bind_row`` can tell "not bound to anything" from "bound
        # to another module's predicate": the first is free to move, the
        # second is policed (P3-3 Task 3 fix round 1).
        row.detached = True
        cls._row = row
        return row

    def _bind_row(cls, db, functor: str, arity: int,
                  authorized: bool = False) -> None:
        """Point this class's state at *db*'s row for ``(functor, arity)``.

        Called at the sites that make a class the compiled face of a stored
        predicate: ``compiler_v2`` step 4 (clauses attached), step 4a (a
        clause-less ``-dynamic`` declaration) and ``compiler._install`` (a
        dispatch installed).  After it, ``cls._clauses`` IS
        ``db._clauses[(functor, arity)]``, so ``db.assertz`` needs no mirror.

        *functor* is passed rather than read off ``cls.__name__`` because an
        aliased ``-import_from`` binds a class under a name that is not its
        own, and the clauses live under the name the CLAUSE HEADS use.

        Re-binding a class that already has a row is legitimate and expected:
        a clause-free imported declaration getting its clauses downstream, a
        file re-compiled in one process, a name defined at two arities.  It is
        also how a shared predicate gets STOLEN, so it is policed: a class
        already reading another Database's real row is left where it is unless
        the caller passes *authorized*, which TWO callers do, each from inside
        a write the mutation gate has just cleared: ``compiler_v2`` step 4's
        clause install, and ``specialization._install_specialized`` (P3-3
        Task 7), which makes a ``-specialize`` alias the compiled face of the
        defining module's row.  The specialization one passes
        ``through=pred_cls`` to its ``Database.mutate``, so the class's
        CURRENT row is in that write's blast radius and the policy has already
        refused the case this guard exists for -- an alias name that resolves
        to somebody else's predicate -- before the bind is reached.  See the
        body.
        A REAL old row keeps its own contents (it is the Database's, not the
        class's); three pieces of state that were per-CLASS rather than
        per-key before this task travel with the class so the move stays
        lossless — ``dynamic_arities`` (unioned: it is a set ACROSS arities by
        construction), ``locked`` (or-ed: locking was one-way on the class,
        never undone by a later module), and ``source`` (only when the target
        has none; step 4 re-stamps it immediately after binding anyway).

        A DETACHED old row holding clauses is the exception, and it is the one
        case where the clauses travel too (final review I-1): a detached row
        is nobody's Database — once the class stops pointing at it nothing can
        reach it again — so leaving clauses behind there is not "the
        Database's contents", it is silent loss, and since Task 2 the row is
        the ONLY store, so there is no second copy to recover from.  See
        ``_migrate_detached_clauses``.

        The three INDEX PLAN dicts travel on exactly that same condition, and
        only onto EMPTY targets (roborev M1, ruled 2026-09-17).  They became
        row-local state in P1 Task 1, which put them in reach of this hazard:
        ``compile_predicate_trampoline`` writes the plans and its ``_install``
        binds afterwards, so a class compiled while DETACHED had its plans
        written onto a row that this bind then abandons — a lost optimisation
        (never a wrong answer) for any caller that compiles that way, which no
        in-tree caller does.  Scoped deliberately: from a REAL old row nothing
        moves, because those plans are that Database's, not the class's; and a
        target that already holds plans keeps them, because the compiler
        rewrites them on every recompile and the fresher set is the target's.
        """
        new_row = db.row(functor, arity, create=True)
        old_row = cls._row
        if old_row is new_row:
            return
        if (
            old_row is not None
            and not old_row.detached
            and old_row.db is not db
            and not authorized
        ):
            # POLICED (P3-3 Task 3 fix round 1).  Re-binding is a write that
            # MOVES predicate identity: the class is what a goal resolves
            # through, so re-pointing an ``-import_from``'d class at the
            # importer's row hands the importer's clause list to the OWNER's
            # own queries -- silently, and with the owner's row left holding
            # the clauses nobody can reach any more.  A recompile or a
            # dispatch install has no authorship to make that decision with
            # (its ``recompile`` kind is never refused, precisely because it
            # is meant to change nothing), so it does not get to.  The
            # authorized re-binds are ``compiler_v2`` step 4's clause install
            # -- which is what keeps the clause-free vocabulary idiom working
            # -- and ``specialization._install_specialized``'s alias install
            # (P3-3 Task 7); both run inside a mutation-gate transaction
            # already cleared for their author, and the second additionally
            # names the class in that transaction's ``through=``.
            #
            # A class on its private DETACHED row is unbound, not bound
            # elsewhere, so its first real bind is always fine.
            return
        if old_row is not None:
            if old_row.detached and old_row.clauses:
                _migrate_detached_clauses(old_row, new_row)
            if old_row.detached:
                # The plans compiled onto the private row travel with the
                # class; an already-populated target is left alone.
                for _plans in ("index_plans", "index_plans_joint",
                               "index_plans_hierarchical"):
                    carried = getattr(old_row, _plans)
                    if carried and not getattr(new_row, _plans):
                        setattr(new_row, _plans, carried)
            old_declared = old_row.dynamic_arities
            if old_declared:
                if new_row.dynamic_arities is None:
                    new_row.dynamic_arities = set(old_declared)
                else:
                    new_row.dynamic_arities |= old_declared
            if old_row.locked:
                new_row.locked = True
            if new_row.source is None:
                new_row.source = old_row.source
        cls._row = new_row

    def _ensure_clauses(cls) -> list:
        """Mint this class's clause list in its row's Database and return it.

        The class-side spelling of ``PredRow.ensure_clauses`` — called by the
        mutators below before they append/insert, because a plain ``_clauses``
        READ deliberately mints nothing (P3-3 Task 2 fix round 1; see
        ``PredRow.clauses``).
        """
        return (cls._row or cls._detached_row()).ensure_clauses()

    @property
    def _clauses(cls) -> list:
        return (cls._row or cls._detached_row()).clauses

    @_clauses.setter
    def _clauses(cls, value: list) -> None:
        (cls._row or cls._detached_row()).clauses = value

    @property
    def _clauses_source(cls) -> "tuple[str, str] | None":
        """``(module_name, source_path)`` of the load that last wrote
        ``_clauses``, or ``None`` while the class has none.  An
        ``-import_from`` SHARES this class across modules, so "whose clauses
        are these" is the only thing separating a module reloading its own
        work from a second module quietly overwriting someone else's — see
        ``compiler_v2._reject_redefinition_of_imported_predicates``.  The
        source PATH is the identity that matters, not the module name: one
        file legitimately compiles under two names in one process (a dotted
        import and ``clausal.testing.load_clausal_module``).
        """
        return (cls._row or cls._detached_row()).source

    @_clauses_source.setter
    def _clauses_source(cls, value: "tuple[str, str] | None") -> None:
        (cls._row or cls._detached_row()).source = value

    @property
    def _dispatch_fn(cls) -> "Callable | None":
        return (cls._row or cls._detached_row()).dispatch_fn

    @_dispatch_fn.setter
    def _dispatch_fn(cls, value: "Callable | None") -> None:
        (cls._row or cls._detached_row()).dispatch_fn = value

    @property
    def _lazy_recompile(cls) -> "Callable | None":
        return (cls._row or cls._detached_row()).lazy_recompile

    @_lazy_recompile.setter
    def _lazy_recompile(cls, value: "Callable | None") -> None:
        (cls._row or cls._detached_row()).lazy_recompile = value

    @property
    def _signature(cls) -> "tuple[str, ...] | None":
        return (cls._row or cls._detached_row()).signature

    @_signature.setter
    def _signature(cls, value: "tuple[str, ...] | None") -> None:
        (cls._row or cls._detached_row()).signature = value

    @property
    def _locked(cls) -> bool:
        """Runtime-mutation lock.  Set by ``_lock`` after a module load
        completes; read by ``_assertz``/``_asserta``/``_retract`` and by the
        ``assertz/1``-family builtins before they touch the clause list."""
        return (cls._row or cls._detached_row()).locked

    @_locked.setter
    def _locked(cls, value: bool) -> None:
        (cls._row or cls._detached_row()).locked = value

    @property
    def _dynamic_arities(cls) -> "set[int] | None":
        """Arities this NAME was DECLARED at (``-dynamic(f/N)``), stamped by
        compiler_v2 at load.  ``None`` everywhere else.  A declaration is
        the one arity source that cannot be a stale inference — unlike
        ``_fields`` (stale on the re-minted vocabulary atom) and unlike an
        empty ``_clauses`` (which says nothing) — so ``_refuse_call_at``
        may consult it when, and only when, the clause list is empty.

        Row-LOCAL storage, deliberately NOT derived from ``row.dynamic``
        (P3-3 Task 2): ``dynamic`` is a per-``(f, a)`` boolean and this is a
        per-NAME set whose ``None``-vs-set and size-1-vs-larger distinctions
        both decide behavior in ``_declared_arity``.  Deriving would be lossy.
        """
        return (cls._row or cls._detached_row()).dynamic_arities

    @_dynamic_arities.setter
    def _dynamic_arities(cls, value: "set[int] | None") -> None:
        (cls._row or cls._detached_row()).dynamic_arities = value

    @property
    def _index_plans(cls) -> dict:
        return (cls._row or cls._detached_row()).index_plans

    @_index_plans.setter
    def _index_plans(cls, value: dict) -> None:
        (cls._row or cls._detached_row()).index_plans = value

    @property
    def _index_plans_joint(cls) -> dict:
        return (cls._row or cls._detached_row()).index_plans_joint

    @_index_plans_joint.setter
    def _index_plans_joint(cls, value: dict) -> None:
        (cls._row or cls._detached_row()).index_plans_joint = value

    @property
    def _index_plans_hierarchical(cls) -> dict:
        return (cls._row or cls._detached_row()).index_plans_hierarchical

    @_index_plans_hierarchical.setter
    def _index_plans_hierarchical(cls, value: dict) -> None:
        (cls._row or cls._detached_row()).index_plans_hierarchical = value

    # ── Term construction ─────────────────────────────────────────────────

    def __call__(cls, *args: Any, **kwargs: Any) -> Any:
        """Create a term instance, filling missing fields with fresh Var().

        For zero-arity predicates (atoms), returns the class itself —
        the class IS the atom value.  ``red() is red`` holds.

        - Positional args are mapped to fields in order.
        - Keyword args: any field not provided gets a fresh Var().
        - If no args at all, all fields get Var() (fully unbound term).
        """
        if not cls._fields and not args and not kwargs:
            return cls

        fields = cls._fields

        if args:
            # Positional overflow used to be DROPPED here (``if i <
            # len(fields)``), so a call with too many arguments returned a
            # wrong term instead of raising — strictly worse than the keyword
            # path's TypeError, because there was nothing to repair against.
            # One length check replaces the former per-argument comparison, so
            # the hot path is if anything marginally cheaper.
            if len(args) > len(fields):
                raise _term_arity_error(
                    cls, len(args), kwargs, _source_site(1)
                )
            for i, val in enumerate(args):
                kwargs[fields[i]] = val

        instance = cls.__new__(cls)
        try:
            cls.__init__(instance, **kwargs)
        except TypeError:
            # A bare "unexpected keyword argument" here names neither the
            # functor nor either field-name tuple nor any source location, so
            # nothing in it identifies a target to repair.  Re-raise with all
            # of that attached — but only when the kwargs really are unknown
            # fields; any other TypeError from __init__ is passed through.
            if all(k in fields for k in kwargs):
                raise
            raise _term_construction_error(
                cls, kwargs, _source_site(1)
            ) from None

        # Replace _MISSING with fresh Var()
        from clausal.logic.variables import Var  # noqa: PLC0415
        for f in fields:
            if getattr(instance, f) is _MISSING:
                object.__setattr__(instance, f, Var())

        return instance

    # ── Predicate properties ──────────────────────────────────────────────

    @property
    def _functor(cls) -> str:
        return cls.__name__

    @property
    def _arity(cls) -> int:
        return len(cls._fields)

    # ── Clause management ─────────────────────────────────────────────────

    def _mutate(cls, author: str, kind: str, detail: Any = None):
        """Class-side spelling of the mutation gate (``Database.mutate``).

        The class-side spelling exists because a ``PredicateMeta`` knows which
        row it faces but not which ``(db, functor, arity)`` that is — an alias
        binds a class under a name that is not its own — and because the class
        itself belongs in the write's blast radius: it is passed as *through*,
        so a write made via a SHARED (``-import_from``'d) class is asked about
        the row that class currently reads, not only the one this Database
        holds.
        """
        row = cls._row or cls._detached_row()
        return row.mutate(author, kind, detail, through=cls)

    def _runtime_author(cls) -> str:
        """``runtime-assert:<module>`` — who a runtime assert/retract made
        through this class is.  Per WRITE, not per load: the module that
        asserts a clause is recorded as its author even when another module
        compiled the predicate (the mutation-gate todo's ``assertz``
        attribution defect)."""
        from clausal.logic.database import RUNTIME_AUTHOR_PREFIX  # noqa: PLC0415
        return f"{RUNTIME_AUTHOR_PREFIX}{cls.__module__}"

    @contextlib.contextmanager
    def _gated(cls, kind: str, detail: Any = None):
        """:meth:`_mutate` with the gate's ENTRY refusal translated to
        ``RuntimeError``.

        The exception CLASS is this channel's, pinned by callers since long
        before the gate — the drive loop treats a ``RuntimeError`` from a
        generator as exhaustion, and several tests read it — but the TEXT is
        the gate's, unedited, because the policy that produced it lives in
        exactly one place (P3-3 Task 3).  Only the refusal raised by
        ``__enter__`` is translated; a ``LogicException`` raised by the body
        is the caller's and passes through untouched.
        """
        from clausal.logic.exceptions import LogicException  # noqa: PLC0415
        ctx = cls._mutate(cls._runtime_author(), kind, detail)
        try:
            row = ctx.__enter__()
        except LogicException as exc:
            raise RuntimeError(str(exc.term.args[1])) from None
        try:
            yield row
        except BaseException as exc:  # noqa: BLE001 — re-raised below
            if not ctx.__exit__(type(exc), exc, exc.__traceback__):
                raise
        else:
            ctx.__exit__(None, None, None)

    def _assertz(cls, clause: Any) -> None:
        """append clause at end; the gate invalidates the compiled dispatch."""
        with cls._gated("assert", "_assertz") as row:
            row.ensure_clauses().append(clause)

    def _asserta(cls, clause: Any) -> None:
        """Prepend clause at front; the gate invalidates the compiled dispatch."""
        with cls._gated("assert", "_asserta") as row:
            row.ensure_clauses().insert(0, clause)

    def _retract(cls, head: Any) -> bool:
        """Remove first clause whose head equals head (structural equality).

        Returns True if a clause was removed, False if none matched.
        """
        with cls._gated("retract", "_retract") as row:
            clauses = row.clauses
            for i, clause in enumerate(clauses):
                if clause.head == head:
                    del clauses[i]
                    return True
        return False

    # ── Dispatch ──────────────────────────────────────────────────────────

    def _get_dispatch(cls, arity: int | None = None) -> Callable:
        """Return the compiled dispatch function.

        If dispatch_fn was cleared by assertz/retract and a lazy recompile
        callback is registered, recompiles on demand.

        *arity* is the call site's argument count.  This is the one place where
        a name becomes a dispatch function, so it is the one place that can
        notice the caller and the callee disagree about how many arguments there
        are — see ``_refuse_call_at``.  Omitted (``None``) by callers that
        already know the arity is right, and by the many places that just want
        the function.

        This is the ONLY ``_get_dispatch`` in the system that takes an *arity*,
        and callers that do not know they hold a ``PredicateMeta`` must go
        through ``_dispatch_at`` rather than passing one blind — the protocol at
        large is single-argument and stays that way.  See ``_dispatch_at``.
        """
        # ``len(cls._fields)`` rather than ``cls._arity``: identical by
        # definition, but skips a property descriptor on a path taken once per
        # goal invocation.
        if arity is not None and arity != len(cls._fields):
            cls._refuse_call_at(arity)
        # P3-3 Task 2: the state is the Database row's now.  Read the row's
        # backing dicts DIRECTLY rather than through the ``_dispatch_fn`` /
        # ``_lazy_recompile`` properties — this is the once-per-goal-invocation
        # path, and three property calls where there used to be two plain
        # attribute lookups is exactly the overhead the phase must not add.
        # The logic below is the same three-step it always was: use the
        # installed dispatch; else recompile through the lazy callback and
        # prefer whatever ``_install`` stored over what the callback returned;
        # else refuse.
        row = cls._row
        if row is None:
            row = cls._detached_row()
        db = row._db
        key = row._key
        dispatch = db._dispatch
        fn = dispatch.get(key)
        if fn is None:
            lazy = db._lazy_recompile.get(key)
            if lazy is not None:
                fn = lazy()
                # A recompile installs through ``compiler._install``, which is
                # where a ``-table``d predicate gets its SLG wrapper back and a
                # ``-shallow`` one gets its trampoline adapter.  Whatever
                # ``_install`` put on the row therefore outranks the function
                # the recompile happened to hand back: assigning the return
                # value blind is how an ``assertz`` used to leave a tabled
                # predicate dispatching raw.
                installed = dispatch.get(key)
                if installed is None:
                    # Written to the backing dict rather than through the
                    # gate (P3-3 Task 3): this is the once-per-goal path, and
                    # what it stores is the row's OWN recompiled function —
                    # a ``recompile``, which the policy never refuses.  There
                    # is no authorship question to ask and no budget here to
                    # ask one.
                    dispatch[key] = fn
                else:
                    fn = installed
            else:
                raise NotImplementedError(
                    f"Predicate {cls.__name__}/{cls._arity} has no compiled "
                    "dispatch function. The compiler must be run first."
                )
        return fn

    def _clause_arity(cls, accept: int | None = None) -> int | None:
        """The one arity every clause head of *cls* has, or ``None``.

        ``_arity`` is the cheap answer and is right almost always, but it can
        be stale: a module that imports a 0-arity vocabulary atom and then
        defines a same-named predicate re-mints its clauses onto the imported
        class without moving ``_arity`` (``tests/fixtures/
        impord_atom_then_pred.clausal``).  Clause heads cannot be stale, and
        they are also exactly what a refusal would be claiming — *no clause of
        this predicate can match a call of that shape*.

        ``None`` when there are no clauses (a bare functor, a forward
        declaration, a ``-dynamic`` predicate not yet asserted into), when they
        disagree, or when a head's shape cannot be read: in all of those cases
        nothing is known well enough to refuse.

        *accept* is an arity the caller will not refuse whatever the answer, and
        is what keeps this off the hot path.  If the **first** head already has
        it, there is nothing left to learn — either every head has it, or the
        heads disagree, and both answers decline — so the remaining heads are
        not read and ``None`` comes back after one head.  That matters because
        the stale-``_arity`` predicates above take this path on *every* call
        (``0 != 2`` forever), and a 2000-fact one measured 108 µs per call
        walking heads it could not learn anything from, against 0.10 µs for an
        honest ``_arity``.  It is deliberately a re-derivation rather than a
        memo: ``_clauses`` is mutated in place by ``assertz``/``retract`` and by
        three load-time paths that replace it wholesale
        (``import_hook``, ``compiler_v2``), and a cached arity that outlived one
        of those would either suppress a real refusal or refuse a call that had
        become correct.  Reading one head cannot go stale.
        """
        clauses = cls._clauses
        if not clauses:
            return None
        first = _head_arity(clauses[0].head)
        if first is None or first == accept:
            return None
        for clause in clauses[1:]:
            if _head_arity(clause.head) != first:
                return None
        return first

    def _declared_arity(cls, calling: int) -> int | None:
        """The one arity ``-dynamic`` declared *cls* at, when nothing else answers.

        Consulted by ``_refuse_call_at`` only after ``_clause_arity`` came back
        empty-handed, and answers only for the shape that motivates it: a
        declared-but-clause-free predicate (the ISO declare-then-assertz
        pattern, and its retract-back-to-empty return leg).  ``None`` — refuse
        nothing — whenever:

        - the class has clauses (the heads were the authority and declined;
          a declaration must not outvote them);
        - nothing was declared (``_dynamic_arities`` is ``None`` on every
          class the compiler did not stamp — vocabulary atoms, forward
          declarations, plain predicates — so all of those decline exactly
          as before);
        - more than one arity was declared (one number in the message means
          one declared arity; guessing which to blame would be wrong half
          the time);
        - *calling* IS the declared arity (a declared call is never refused,
          whatever ``_fields`` thinks);
        - the declaration disagrees with the class's own shape.  A
          ``-dynamic(f/3)`` can stamp a same-named class authored at another
          arity (a module that imported a 0-arity vocabulary atom ``f`` and
          also declares ``f/3``), and when two authored sources disagree,
          refusing with either number is confidently wrong half the time.
          ``_fields`` serves only as this VETO — it cancels refusals, it is
          never the arity the refusal reports — so the stale-``_fields``
          hazard the clause walk exists to avoid cannot return through it.
        """
        if cls._clauses:
            return None
        declared = cls._dynamic_arities
        if not declared or len(declared) != 1 or calling in declared:
            return None
        arity = next(iter(declared))
        if arity != len(cls._fields):
            return None
        return arity

    def _refuse_call_at(cls, arity: int) -> None:
        """Raise if no clause of *cls* could match a call of *arity* arguments.

        Only reached when the call site's arity differs from ``_arity``, so the
        clause read here is off the dispatch path for an agreeing call — and is
        one head, not the whole list, whenever the heads say the call is fine
        (see ``_clause_arity``).

        Raises ``PredicateArityMismatchError`` or nothing at all.  A diagnostic
        that can itself fail is worse than no diagnostic: whatever shape the
        clause list or the registration site turns out to be, this either states
        the arity fault or declines quietly.
        """
        try:
            defined = cls._clause_arity(accept=arity)
        except Exception:  # noqa: BLE001 - see docstring
            return
        if defined is None:
            defined = cls._declared_arity(arity)
        if defined is None:
            return
        from clausal.predicate_diagnostics import (  # noqa: PLC0415
            PredicateArityMismatchError,
            predicate_arity_mismatch,
        )
        try:
            err = predicate_arity_mismatch(
                cls.__name__, arity, defined,
                site=getattr(cls, "_registered_at", None),
            )
        except Exception:  # noqa: BLE001 - the fault is still real; state it
            err = PredicateArityMismatchError(
                f"{cls.__name__} takes {defined} arguments, "
                f"but this call passes {arity}"
            )
        raise err

    # ── Locking ───────────────────────────────────────────────────────────

    def _lock(cls) -> None:
        """Lock the predicate, preventing runtime assertz/retract."""
        cls._locked = True

    def _unlock(cls) -> None:
        """Unlock the predicate, allowing runtime assertz/retract."""
        cls._locked = False

    def __repr__(cls) -> str:
        if not cls._fields:
            return cls.__name__
        compiled = "compiled" if cls._dispatch_fn is not None else "uncompiled"
        n = len(cls._clauses)
        locked = ", locked" if cls._locked else ""
        return (
            f"<Predicate {cls.__name__}/{cls._arity}, "
            f"{n} clause(s), {compiled}{locked}>"
        )


# ── Arity-aware dispatch resolution ──────────────────────────────────────────


def _dispatch_at(obj: Any, arity: int) -> Callable:
    """Resolve *obj*'s dispatch function for a call of *arity* arguments.

    ``_get_dispatch()`` is a duck-typed protocol, and it is deliberately and
    permanently **single-argument**.  Roughly two dozen implementors live
    outside this tree — ``packages/clausal-scipy``'s ``_LookupPredicate``,
    ``packages/clausal-spacy``'s ``_SpacyPredicate``,
    ``packages/clausal-provenance``'s ``_RegistrationGoal`` and friends — and
    most of them inherit from nothing at all: they are plain classes whose whole
    contract is ``def _get_dispatch(self)``.  Widening the protocol to take the
    call site's arity broke every one of them at their *correct* arity, which is
    not a trade a diagnostic gets to make.

    So the arity stops here.  Exactly one implementor is arity-aware —
    ``PredicateMeta``, which is where clause heads live and therefore the only
    place that can tell a wrong-arity call from a right one — and predicates are
    *instances* of that metaclass while foreign implementors are instances of
    plain classes, so ``isinstance`` separates them exactly.  Everyone else is
    called the way they were always called.  Do not add an ``arity`` parameter to
    another ``_get_dispatch``; add the case here.

    Off the hot path by construction: locked predicates (the default) have their
    dispatch function pre-cached in ``base_globals`` under ``$disp_<name>_<n>``
    and the goal emitters reference that name directly, so only unlocked
    (``-dynamic``) callees and the runtime meta-call funnels arrive here.
    """
    if isinstance(obj, PredicateMeta):
        return obj._get_dispatch(arity)
    if type(obj) is str:
        # THE FLIP (spec §6.4): a ``str`` is a STRING.  The Stage A arm here
        # also accepted a bare ``str`` and built the indicator out of its
        # spelling, which silently read a string as a predicate NAME; it is
        # deleted, and a string takes the same refusal
        # ``higher_order._resolve_named_goal`` (``call/N``) and
        # ``solve._term_to_goal`` (``solve/1``) give -- Task 15 item 3's
        # ``existence_error(procedure, '.'/N)``: the string IS the compound
        # ``'.'/2`` and so IS callable; the procedure is what does not exist.
        from clausal.logic.exceptions import (  # noqa: PLC0415
            LogicException, string_goal_error,
        )
        raise LogicException(string_goal_error(obj, arity, "call/N"))
    if type(obj) is tuple and len(obj) == 1 and type(obj[0]) is str:
        # P3-1 Task 2 fix round (controller ruling, 2026-09-04), carried
        # through THE FLIP: a bare atom is the arity-0 CELL, reached here
        # whenever a goal resolves to a NAME that turned out to be data, not
        # a predicate (a dotted cross-module reference to an atom, or any
        # other resolution path that used to find a minted 0-arity class).
        # Pre-pivot this quirk of class re-minting sometimes silently reached
        # a DIFFERENT module's re-minted class of the same name (see
        # task-2-report.md's "resolved by fix round 1"); that was never a
        # contract, so the ruling is: calling an atom as a goal, at any
        # arity, through any resolution path, is a genuine error — but a
        # clean, positioned one, never a raw AttributeError.  Do NOT
        # special-case dispatch-to-local-predicate here; that routing is
        # P3-3's qualified-goal design.
        from clausal.logic.exceptions import (  # noqa: PLC0415
            LogicException, existence_error,
        )
        from clausal.terms import Compound  # noqa: PLC0415
        name = obj[0]
        indicator = Compound("/", (name, arity))
        raise LogicException(
            existence_error(
                "procedure", indicator,
                f"atom {name!r} is not callable at arity {arity} "
                f"(resolved via a data reference; define or import the "
                f"predicate, or call it by its local name)",
            )
        )
    return obj._get_dispatch()


# ── Python reference implementations (kept as fallbacks) ─────────────────────


def _is_term_instance_py(obj: Any) -> bool:
    """True if obj is a term instance with named fields (not a type/class).

    Works for both PredicateMeta instances and @dataclass instances.
    """
    if isinstance(obj, type):
        return False
    if isinstance(type(obj), PredicateMeta):
        return True
    return dataclasses.is_dataclass(obj)


def _is_zero_field_class_py(obj: Any) -> bool:
    """True if obj is a zero-arity PredicateMeta CLASS (a declared atom).

    The CLASS test, not the term test: ``clausal.logic.atoms.is_atom`` is the
    term test (the arity-0 cell).  Named for the question it asks since Task
    12 of the atoms-as-cells design — the two used to share the stem
    ``is_atom``, which is why several call sites asked the wrong one.
    """
    return isinstance(obj, PredicateMeta) and not obj._fields


def _term_field_names_py(obj: Any) -> tuple[str, ...]:
    """Return field name strings for a term instance."""
    cls = type(obj)
    if isinstance(cls, PredicateMeta):
        return cls._fields
    if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        return tuple(f.name for f in dataclasses.fields(obj))
    raise TypeError(f"Not a term instance: {obj!r}")


def term_field_names_of_class(cls: Any) -> tuple[str, ...] | None:
    """Return field name strings for a term CLASS (not instance), or None.

    The class-level twin of ``term_field_names``: a ``PredicateMeta`` class
    (including a zero-arity atom class) yields ``cls._fields``; a bare
    ``@dataclass`` class yields its declared field names in declaration
    order — the same set ``term_field_names`` yields for an *instance* of
    it, nothing excluded. Anything else (a non-term class, or a non-class
    value) yields None rather than raising, since callers use this to test
    "is this class term-shaped" rather than asserting it.

    Models ``compiler/head_match.py``'s ``_resolved_field_names`` (read
    that first) but lives here as the canonical version; that function
    delegates its class-cases to this one.
    """
    if not isinstance(cls, type):
        return None
    if isinstance(cls, PredicateMeta):
        return cls._fields
    if dataclasses.is_dataclass(cls):
        return tuple(f.name for f in dataclasses.fields(cls))
    return None


def term_field_values(obj: Any) -> tuple:
    """Return declared-field values for a term instance, in ``term_field_names`` order.

    Term instances only; raises ``TypeError`` otherwise, mirroring
    ``term_field_names``'s own contract (it is what actually raises here).
    """
    return tuple(getattr(obj, name) for name in term_field_names(obj))


def term_field_dict(obj: Any) -> dict[str, Any]:
    """Return a name -> value dict for a term instance's declared fields.

    The reconstruct-pattern helper: callers that build ``dict(zip(term_field_names(x),
    (getattr(x, n) for n in ...)))`` by hand should use this instead. Term
    instances only; raises ``TypeError`` otherwise (via ``term_field_names``).
    """
    return {name: getattr(obj, name) for name in term_field_names(obj)}


# ── C-accelerated versions (with Python fallback) ────────────────────────────

is_term_instance = _is_term_instance_py
is_zero_field_class = _is_zero_field_class_py
term_field_names = _term_field_names_py

# Which ``PredicateMeta`` currently owns the accelerator's registration slot.
#
# ``_register_predicate_meta`` stores its argument in a single C ``static
# PyObject *``, and ``is_term_instance`` answers ``isinstance(type(obj), <that
# class>)``.  The slot is process-global and the extension uses single-phase
# init, so its static state outlives ``del sys.modules["clausal..."]`` — a
# second import of the package builds a second ``PredicateMeta`` and, if it
# re-registers, silently steals the slot.  Terms already minted by the FIRST
# copy then stop being terms: their metaclass is no longer the registered one,
# so ``is_term_instance`` returns False for objects its own Python fallback
# still accepts, and every caller mistakes a live functor instance for a
# non-term.  That surfaced as ``head_key`` refusing a clause head it was
# holding; see ``tests/test_second_package_copy_term_identity.py``.
#
# So the slot is claimed once and never stolen: first copy keeps the fast path,
# later copies use the pure-Python implementations above, which close over
# *their own* ``PredicateMeta`` and are therefore self-consistent.  Both copies
# end up internally correct; only the later ones pay interpreter speed, which is
# the right way round because the first copy is the one already holding live
# terms.
#
# The record lives on ``sys`` because that is the only namespace guaranteed to
# survive the ``sys.modules`` surgery that creates the second copy in the first
# place.  It is not an extra leak: the C slot already holds a strong reference
# to the same class.
_C_SLOT_OWNER_ATTR = "_clausal_c_predicate_meta_owner"

try:
    from clausal.logic.variables._variables import (
        _register_predicate_meta,
        is_term_instance,
        term_field_names,
        # The C extension registers the accelerator under the OLD name; the
        # C symbol is deliberately left alone (Task 12), so the rename to
        # the question it actually asks happens on import.
        is_atom as is_zero_field_class,
    )
except ImportError:
    pass
else:
    if getattr(sys, _C_SLOT_OWNER_ATTR, None) is None:
        _register_predicate_meta(PredicateMeta)
        setattr(sys, _C_SLOT_OWNER_ATTR, PredicateMeta)
    else:
        # Another copy of this package owns the slot. Keep the reference
        # implementations rather than invalidating that copy's live terms.
        is_term_instance = _is_term_instance_py
        is_zero_field_class = _is_zero_field_class_py
        term_field_names = _term_field_names_py


# DEPRECATED alias, kept for ONE release (Task 12, atoms-as-cells/strings).
# ``predicate.is_atom`` is the zero-field-CLASS test and always was; the TERM
# test of the same name lives in ``clausal.logic.atoms``.  Every in-tree
# caller now imports ``is_zero_field_class``; this name survives only because
# the C extension registers its accelerator as ``is_atom`` and out-of-tree
# code may still import it from here.  Delete it, not the C symbol, when the
# release window closes.
is_atom = is_zero_field_class


def is_atom_value(obj: Any) -> bool:
    """True if obj is an atom-shaped VALUE: the arity-0 cell ``("bar",)``, or
    a zero-arity PredicateMeta class (a declared atom).

    Two different questions share the stem ``is_atom`` in this tree, and this
    is the union of them:

    * ``clausal.logic.atoms.is_atom`` is the TERM test — after the flip
      (2026-09-06-atoms-as-cells-strings §6.1) exactly the 1-tuple whose
      slot 0 is a ``str``.  A plain ``str`` is a STRING and fails it.
    * ``predicate.is_zero_field_class`` above is the CLASS test — "a
      zero-field ``PredicateMeta`` class", the declared-atom form.  Several
      COMPILER call sites (``terms_to_ast.py``, ``_lower_goalop_shared.py``)
      key off that one to decide identity-lowering / bare-Name-reference
      behaviour, so it must stay the narrow class question.  Task 12 renamed
      it out of the shared stem; ``is_atom`` now means the term test
      everywhere except the deprecated alias below it.

    Runtime readers (``atom/1``, ``functor_arity``) want either shape and
    call THIS helper, never one of the two halves alone.
    """
    from clausal.logic.atoms import is_atom as _term_is_atom
    return _term_is_atom(obj) or is_zero_field_class(obj)


def _class_origin(cls: type) -> str:
    """Best-effort ``file:line`` for where *cls*'s methods were compiled.

    Deliberately reads ``__code__`` off the class's own methods instead of
    consulting ``sys.modules`` or ``cls.__module__``: the situation this exists
    to describe is one where ``sys.modules`` has had its ``clausal`` entries
    deleted, so the usual introspection resolves to the wrong copy or to nothing
    at all.
    """
    for attr in ("__new__", "__init__"):
        fn = cls.__dict__.get(attr)
        fn = getattr(fn, "__func__", fn)
        code = getattr(fn, "__code__", None)
        if code is not None:
            return f"{code.co_filename}:{code.co_firstlineno}"
    return "<unknown source>"


def describe_term_identity_mismatch(obj: Any) -> str:
    """Explain a *foreign* functor instance, or return ``""``.

    ``is_term_instance`` is nominal: it asks whether ``type(obj)`` is an
    instance of *this* module's ``PredicateMeta``.  When two copies of the
    ``clausal`` package are live in one process there are two unrelated
    ``PredicateMeta`` classes, and a term minted by one copy is simply not a
    term to the other — the object walks and quacks like a functor instance and
    still fails every check.

    Callers that are about to reject a term should append this to their error.
    Without it the message is actively misleading: it says "expected a functor
    dataclass instance" while holding one.  Returns ``""`` when *obj* is not a
    functor instance at all, so the caller's own wording stands unaltered.

    Never raises.  It runs on the way into someone else's ``raise``, where an
    exception of its own would replace a usable error with a confusing one, and
    it introspects objects minted by a *foreign* copy of the package whose
    invariants this one cannot assume.
    """
    try:
        return _describe_term_identity_mismatch(obj)
    except Exception:  # noqa: BLE001 — a diagnostic must not upstage the fault
        return ""


def _describe_term_identity_mismatch(obj: Any) -> str:
    cls = type(obj)
    if isinstance(cls, PredicateMeta):
        return ""  # recognised; nothing to explain
    if not isinstance(getattr(cls, "_fields", None), tuple):
        return ""  # not a functor class at all
    foreign = type(cls)
    # ``_fields`` alone is not enough: a stdlib ``namedtuple`` has one too, and
    # its metaclass is plain ``type``.  Without this the message below would
    # tell someone who passed a namedtuple as a head that two copies of the
    # clausal package are live and that they should fix their import surgery —
    # confident, specific and entirely wrong.  A genuinely foreign functor
    # class is minted by the *other copy's* ``PredicateMeta``, which is the
    # same source file and therefore the same class name; a metaclass that is
    # not one leaves the caller's own wording to stand.
    if foreign is type or foreign.__name__ != PredicateMeta.__name__:
        return ""
    mine = PredicateMeta
    return (
        f"\nThis head IS a functor instance, but of a class this copy of clausal "
        f"does not recognise:\n"
        f"  head class:     {cls.__name__}/{len(cls._fields)} "
        f"declared in module {cls.__module__!r}\n"
        f"  its metaclass:  {foreign.__module__}.{foreign.__qualname__} "
        f"id=0x{id(foreign):x} defined at {_class_origin(foreign)}\n"
        f"  this copy uses: {mine.__module__}.{mine.__qualname__} "
        f"id=0x{id(mine):x} defined at {_class_origin(mine)}\n"
        "Two distinct PredicateMeta class objects means two copies of the clausal "
        "package are live in this process (note the source paths: identical paths "
        "still mean two copies of the same file), and terms cannot cross between "
        "them. The usual cause is deleting 'clausal*' from sys.modules and "
        "re-importing, which leaves already-imported holders bound to the first "
        "copy while new imports build a second. Fix the import surgery, not the "
        "term: one clausal package per process.\n"
    )


def make_predicate(name: str, fields: list[str]) -> "PredicateMeta":
    """Dynamically create a PredicateMeta class.

    Useful in tests and runtime code that needs a predicate without a
    module-level class definition::

        foo = make_predicate("foo", ["a", "b"])
        foo._assertz(Clause(head=foo(a=Var(), b=Var()), body=[...]))
        compile_predicate("foo", 2, foo._clauses, pred_cls=foo)
        fn = foo._get_dispatch()
    """
    return PredicateMeta(name, (), {"_fields": tuple(fields)})


def make_atom(name: str) -> tuple[str]:
    """Return the atom *name* — the arity-0 cell ``(name,)``.

    THE FLIP (2026-09-06-atoms-as-cells-strings §5.1): an atom is a 1-tuple
    whose slot 0 is the interned spelling, and a plain ``str`` is a STRING.
    Two calls with the same spelling give equal atoms; equality, never
    identity, is the semantics (§5.2).

    It kept minting a zero-arity ``PredicateMeta`` until P3-3 Task 7.  That
    made it the one door left in the public API through which a CLASS atom
    could enter a program that has none anywhere else — a live
    mixed-representation path, and the shape every accessor since the pivot
    has had to dual-accept.  The function stays for API continuity (it is
    exported, and out-of-tree callers spell an atom with it); what it returns
    changed.

    A zero-arity PREDICATE class — the thing a bare ``p()`` declaration mints,
    which is a procedure and not an atom — is ``make_predicate(name, [])``.

    Delegates to ``clausal.logic.atoms.mint`` (spec §6.1) — the public atom
    API that Plan 0 of the atoms-as-cells/strings plan introduces.
    """
    from clausal.logic.atoms import mint
    return mint(name)


__all__ = ["PredicateMeta", "_MISSING", "is_term_instance",
           "is_zero_field_class",
           # ``is_atom`` is the DEPRECATED alias of ``is_zero_field_class``
           # (Task 12); exported for one release so out-of-tree importers do
           # not break in the same commit that renames it.
           "is_atom",
           "is_atom_value",
           "term_field_names", "term_field_names_of_class",
           "term_field_values", "term_field_dict",
           "make_predicate", "make_atom"]
