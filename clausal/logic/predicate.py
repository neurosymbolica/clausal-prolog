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

from clausal.logic.cells import is_chars, chars_text  # stage 1: the chars carrier
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


def record_clause_source(row, module_name: str, module_dict: dict) -> None:
    """Note whose load wrote *row*'s clause list.

    Called at the one site that assigns the clause list wholesale
    (``compiler_v2`` step 4; the two deferred paths in
    ``clausal.import_hook`` this used to name went with the v1 pipeline).
    The mutation gate's ownership policy reads it back — it is what tells a
    module reloading its own clauses from a module about to destroy
    another's, and it is keyed on the source PATH for that reason.

    Takes the ROW (W4b-2d, F1 row 24), not the class: step 4 used to stamp
    ``pred_cls._state_row()`` and only when the name was bound to a class, so
    once a predicate's binding is a mangled atom nothing would be stamped,
    every row would read as unowned, and the gate's clause-clobber refusal
    would pass every load.  Measured 2026-09-24: in all 16,123 class arrivals
    over the house suite the class's row after the bind IS
    ``db.row(functor, arity)``, so stamping the row directly writes the same
    field.
    """
    row.source = (module_name, module_source_path(module_dict))


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
    return term_construction_error_for(
        cls.__name__, tuple(cls._fields), getattr(cls, "_registered_at", None),
        kwargs, constructed_at)


def term_construction_error_for(
    functor: str, registered: tuple[str, ...], registered_at: Any,
    kwargs: dict, constructed_at: tuple[str, int] | None,
) -> ClausalTermConstructionError:
    """The attributable field-name-mismatch error, from plain data -- for a
    builder that has a functor and its fields but no class (the
    specializer's ``_SpecTarget``, F1 row 35)."""
    supplied = tuple(kwargs)
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
    fields = field_names_for(head)
    if fields is not None:
        return len(fields)
    from clausal.logic.cells import _cell_shape  # noqa: PLC0415
    if _cell_shape(head)[0]:                        # P2: a head is a cell
        return len(head) - 1
    try:
        args = getattr(head, "args", None)
        if args is not None:
            return len(args)
        return len(term_field_names(head))
    except Exception:  # noqa: BLE001 - see docstring
        return None


#: The predicate-state facades W2 retired, and where their state lives now.
#: A RAISING TOMBSTONE rather than a plain deletion, because deleting a
#: property's SETTER is SILENT: `cls._clauses_source = x` would go on
#: succeeding as an ordinary class-attribute write while the row never saw it
#: (measured -- the assignment returned cleanly and `row.source` stayed None).
#: A caller that has not been migrated must fail, not be quietly ignored.
#: These go with the class at P4.
#:
#: The state is the ROW's.  A caller holding the Database reads
#: ``db.row(functor, arity).<field>``; a caller holding only the class reads
#: ``cls._state_row().<field>`` -- the Database's row once the class is bound
#: into a module, the class's private detached row otherwise (minted on first
#: use, which is the compatibility mode for a class minted outside a load).
#: A READ that must not mint anything spells the unbound case out:
#: ``cls._row.clauses if cls._row is not None else []``.
_RETIRED_STATE_NAMES = {
    "_dynamic_arities":
        "the Database's -dynamic marks; read them with "
        "`PredicateMeta._declared_arity`, or `db.is_dynamic(functor, arity)`",
    "_clauses_source":
        "the row's `source` field: `cls._state_row().source`",
    "_signature":
        "the row's `signature` field, or `db.row(f, n).signature`",
    "_clauses":
        "the row's `clauses`: `cls._state_row().clauses`, or "
        "`db.row(f, n).clauses`",
    "_dispatch_fn":
        "the row's `dispatch_fn`: `cls._state_row().dispatch_fn`, or "
        "`db.row(f, n).dispatch_fn` (installs need an open `Database.mutate`)",
    "_lazy_recompile":
        "the row's `lazy_recompile`: `cls._state_row().lazy_recompile`",
    "_locked":
        "the row's `locked`: `cls._state_row().locked`, or "
        "`db.row(f, n).locked`",
    "_index_plans":
        "the row's `index_plans`: `cls._state_row().index_plans`",
    "_index_plans_joint":
        "the row's `index_plans_joint`: `cls._state_row().index_plans_joint`",
    "_index_plans_hierarchical":
        "the row's `index_plans_hierarchical`: "
        "`cls._state_row().index_plans_hierarchical`",
    "_clausal_instances":
        "nothing -- the P2 instance bridge is gone (W4a); a class builds "
        "cells",
}

#: The wave a retired name goes with, where it is not W2's (the default the
#: tombstone factory carries).  A reader who hits the refusal is told which
#: landing took the door away, so the spec is findable.
_DEFAULT_RETIRED_WAVE = "W2 of the PredicateMeta retirement, 2026-09-22"

_RETIRED_STATE_WAVES = {
    "_clausal_instances": "W4a of the PredicateMeta retirement, 2026-09-22",
}

#: W4b-0 (2026-09-23) DECISION, recorded rather than actioned: a class body
#: CAN still write a namespace key matching one of ``_RETIRED_STATE_NAMES``
#: (e.g. ``_clausal_instances = True``) and it will sit there inertly.  The
#: tombstone above is a DATA DESCRIPTOR on the metaclass, and per
#: ``type.__getattribute__`` a metaclass data descriptor is consulted
#: WITHOUT EVEN LOOKING at the class's own ``__dict__`` -- so ordinary
#: attribute access (``cls._clausal_instances``, ``getattr``, ``setattr``)
#: still hits the tombstone and raises exactly as tested in
#: test_predrow.py, regardless of what the namespace holds.  Only a raw
#: ``__dict__``/``vars()`` read (which nothing in the tree does for these
#: names any more) would ever see the inert value.  Deliberately NOT adding
#: a refusal in ``__new__`` for this: the one failure mode it would catch
#: (a class body assigning a retired name, expecting it to do the old
#: thing) is already caught the moment anything reads it back through the
#: normal attribute path, so the residual case is inert clutter, not a
#: silent wrong answer -- and W2 already declined to build this same check
#: for the other six retired names.  Revisit only if a concrete instance of
#: the inert-clutter case actually causes confusion.


class RetiredStateError(Exception):
    """What a retired facade's tombstone raises, on read and on write.

    Deliberately NOT an ``AttributeError``.  ``getattr(cls, "_dispatch_fn",
    None)`` and ``hasattr(cls, "_clauses")`` swallow that class, and a probe
    that quietly answered ``None`` would be the silent failure the tombstone
    exists to prevent -- the engine's own goal resolver probed exactly that way
    before W2 migrated it.  Not a ``RuntimeError`` either: the drive loop reads
    a ``RuntimeError`` out of a generator as exhaustion.

    Collateral, measured: none for the ordinary introspection of a predicate
    CLASS.  The tombstones live on the metaclass, and ``dir(cls)`` does not
    list metaclass attributes, so ``inspect.getmembers(cls)``, ``help(cls)``
    and ``vars(cls)`` never touch them.  A walker that fetches one of the
    retired NAMES from a list of its own sees the error, which is the point.
    """


def _make_retired_tombstone(name: str, where: str,
                            wave: str = _DEFAULT_RETIRED_WAVE) -> property:
    """A property that RAISES on read and on write, naming the replacement."""
    def _fail(*_args):
        raise RetiredStateError(
            f"{name!r} was retired ({wave}). Its state lives in {where}.")
    return property(_fail, _fail, doc=f"RETIRED -- see {where}.")


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
    ``_state_row`` created for it.  Binding that class to a real row used
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

    It also carries the predicate dispatch machinery — but none of the
    predicate STATE.  That is one :class:`~clausal.logic.database.PredRow`
    held in ``cls._row`` (P3-3 Task 2): the Database's row for this predicate
    once the class is bound into a module, a private detached row otherwise.
    ``cls._state_row()`` answers it either way; the per-attribute facades
    (``_clauses``, ``_dispatch_fn``, ``_locked``, ...) that used to read
    through to it are retired (W2, 2026-09-22) and raise
    :class:`RetiredStateError`.
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

        # No INSTANCE face for the predicate state any more (W2, 2026-09-22).
        # P3-3 Task 2 injected a read-only property per relocated name here so
        # ``instance._locked`` kept answering the class's row; the facades it
        # delegated to are retired, and an instance has no ``__dict__``
        # (``__slots__`` above), so that read now raises a plain
        # ``AttributeError`` — loud, never silent.

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
        # The clause list, dispatch, lazy recompile, signature, lock and index
        # plans all live on ONE ``PredRow`` — the Database's per-``(functor,
        # arity)`` row.  ``_row`` is the single slot that used to be seven,
        # so a bound class and its Database can no longer disagree.  The
        # per-attribute read-through facades that Task 2 put on this metaclass
        # are retired (W2): callers read the row, ``cls._state_row()``.
        #
        # ``None`` until first use.  A class the compiler binds into a module
        # gets the owning Database's row (``_bind_row``); a class minted with
        # no Database anywhere — bare ``make_predicate`` from Python, the
        # out-of-tree pattern, ``clausal.reflection``, ``clpb``, the builtin
        # registry — lazily gets a PRIVATE DETACHED row over a private
        # Database of its own (``_state_row``).  That is the compatibility
        # mode: the duck type (``_assertz``, ``_get_dispatch()``, ``_lock``)
        # behaves exactly as before with no Database in sight.
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

    # ── Predicate state: the Database row ─────────────────────────────────
    #
    # P3-3 Task 2 moved the state onto ``cls._row``; W2 (2026-09-22) retired
    # the per-attribute properties that read through to it.  ``_state_row``
    # is the one accessor left: the row itself, whichever kind it is.

    def _state_row(cls):
        """The row this class's predicate state lives on.

        The Database's row for ``(functor, arity)`` once the class is bound
        into a module (``_bind_row``).  Otherwise — a ``PredicateMeta`` minted
        outside a ``.clausal`` load, which has no Database to be a row OF and
        must still behave like a predicate — a PRIVATE DETACHED row, minted
        here on first use over a single-predicate ``Database`` nobody else can
        reach, and cached in ``cls._row``.  That is the compatibility mode;
        ``_bind_row`` later replaces the private row if the class is compiled
        into a module.  Goes with ``make_predicate`` at P4.

        Lazy (not minted in ``__init__``) for two reasons: ``database.py``
        imports ``predicate.py``, so eager construction would need a
        module-level cycle; and a class whose predicate state is never touched
        — a pure term/data class — never pays for one.  A READ that must not
        mint tests ``cls._row is None`` itself instead of calling this.
        """
        row = cls._row
        if row is not None:
            return row
        from clausal.logic.database import Database  # noqa: PLC0415
        # ``getattr``, not ``cls._fields``: a bare
        # ``class X(metaclass=PredicateMeta): pass`` declares none, and
        # reading its state used to be a plain attribute read that could not
        # fail.  The key is private to this row's private Database,
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
        dispatch installed).  After it, ``cls._state_row().clauses`` IS
        ``db._clauses[(functor, arity)]``, so ``db.assertz`` needs no mirror.

        *functor* is passed rather than read off ``cls.__name__`` because an
        aliased ``-import_from`` binds a class under a name that is not its
        own, and the clauses live under the name the CLAUSE HEADS use.

        Re-binding a class that already has a row is legitimate and expected:
        a file re-compiled in one process, a name defined at two arities.
        What it NEVER does is move a class off ANOTHER Database's real row --
        that is how a shared predicate got STOLEN (the clause-free
        "vocabulary-implements" idiom, dropped 2026-09-24).  An unauthorized
        caller (a recompile, a dispatch install) is left where it is,
        silently, as before.  An *authorized* caller -- each runs inside a
        write the mutation gate has just cleared: ``compiler_v2`` step 4's
        clause install, step 4a, and ``specialization._install_specialized``
        (P3-3 Task 7) -- gets a ``RuntimeError``: the loads that used to
        reach the move are refused before any write, so reaching it is a
        broken invariant, not a request.  See the body.
        A REAL old row keeps its own contents (it is the Database's, not the
        class's); the pieces of state that were per-CLASS rather than
        per-key before this task travel with the class so the move stays
        lossless — ``locked`` (or-ed: locking was one-way on the class, never
        undone by a later module), and ``source`` (only when the target has
        none; step 4 re-stamps it immediately after binding anyway).
        ``dynamic_arities`` used to be carried here too, unioned; it is
        derived from the Database now (option D, 2026-09-22) so there is
        nothing to carry.

        A DETACHED old row holding clauses is the exception, and it is the one
        case where the clauses travel too (final review I-1): a detached row
        is nobody's Database — once the class stops pointing at it nothing can
        reach it again — so leaving clauses behind there is not "the
        Database's contents", it is silent loss, and since Task 2 the row is
        the ONLY store, so there is no second copy to recover from.  See
        ``_migrate_detached_clauses``.

        The three INDEX PLAN dicts travel on exactly that same condition, only
        onto EMPTY targets, and only when the two rows name the SAME
        ``(functor, arity)`` (roborev M1, ruled 2026-09-17; the same-key guard
        added by the re-review).  They became
        row-local state in P1 Task 1, which put them in reach of this hazard:
        ``compile_predicate_trampoline`` writes the plans and its ``_install``
        binds afterwards, so a class compiled while DETACHED had its plans
        written onto a row that this bind then abandons — a lost optimisation
        (never a wrong answer) for any caller that compiles that way, which no
        in-tree caller does.  Scoped deliberately: from a REAL old row nothing
        moves, because those plans are that Database's, not the class's; and a
        target that already holds plans keeps them, because the compiler
        rewrites them on every recompile and the fresher set is the target's;
        and a bind that RENAMES the predicate carries nothing, because a
        bucket function is keyed on the arguments of the predicate it was
        compiled for.
        """
        new_row = db.row(functor, arity, create=True)
        old_row = cls._row
        if old_row is new_row:
            return
        if (
            old_row is not None
            and not old_row.detached
            and old_row.db is not db
        ):
            if authorized:
                # NO STEAL, EVER (2026-09-24, the vocabulary-implements drop).
                # An authorized caller used to MOVE the class here -- the
                # clause-free vocabulary idiom's mechanism -- and where the
                # owner's row held runtime clauses they vanished from every
                # caller through the class.  Every load write through an
                # ``-import_from`` is now refused before step 4 (step 3d,
                # ``compiler_v2._implements_an_imported_declaration``), so an
                # authorized caller reaching this is a broken invariant: say
                # so rather than move another Database's predicate silently.
                raise RuntimeError(
                    f"internal: binding {cls.__name__} to "
                    f"{db.module_name()}'s row {functor}/{arity} would move it "
                    f"off {old_row.db.module_name()}'s row "
                    f"{old_row.key[0]}/{old_row.key[1]}; a predicate never "
                    f"changes its defining module (the load should have been "
                    f"refused before any write)")
            # POLICED (P3-3 Task 3 fix round 1).  Re-binding is a write that
            # MOVES predicate identity: the class is what a goal resolves
            # through, so re-pointing an ``-import_from``'d class at the
            # importer's row hands the importer's clause list to the OWNER's
            # own queries -- silently, and with the owner's row left holding
            # the clauses nobody can reach any more.  A recompile or a
            # dispatch install has no authorship to make that decision with
            # (its ``recompile`` kind is never refused, precisely because it
            # is meant to change nothing), so it does not get to -- and an
            # authorized caller (above) raises instead of moving it.
            #
            # A class on its private DETACHED row is unbound, not bound
            # elsewhere, so its first real bind is always fine.
            return
        if old_row is not None:
            if old_row.detached and old_row.clauses:
                _migrate_detached_clauses(old_row, new_row)
            if old_row.detached and old_row.key == new_row.key:
                # The plans compiled onto the private row travel with the
                # class; an already-populated target is left alone.
                #
                # SAME KEY ONLY (re-review of the fix wave).  A detached row
                # names the CLASS's own key, and ``_bind_row`` takes *functor*
                # precisely because a class can be bound under a name that is
                # not its own (an aliased ``-import_from``).  Without this
                # guard, compiling ``shade/2`` detached and then binding the
                # class as ``tint/2`` handed tint's row bucket functions keyed
                # on SHADE's arguments -- and ``locked`` travels three lines
                # below, so ``hint_row`` would go on to emit them.
                for _plans in ("index_plans", "index_plans_joint",
                               "index_plans_hierarchical"):
                    carried = getattr(old_row, _plans)
                    if carried and not getattr(new_row, _plans):
                        setattr(new_row, _plans, carried)
            if old_row.locked:
                new_row.locked = True
            if new_row.source is None:
                new_row.source = old_row.source
        cls._row = new_row

    def _ensure_clauses(cls) -> list:
        """Mint this class's clause list in its row's Database and return it.

        The class-side spelling of ``PredRow.ensure_clauses`` — called by the
        mutators below before they append/insert, because a plain ``clauses``
        READ off the row deliberately mints nothing (P3-3 Task 2 fix round 1;
        see ``PredRow.clauses``).
        """
        return cls._state_row().ensure_clauses()

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

        # P2 Task 3 (2026-09-19): a class applied to arguments builds the CELL
        # -- the functor-first tuple the engine unifies in C -- never an
        # instance.  Every Python-side producer (reflection's vocabulary,
        # clpb, term expansion, the packages) goes through here, so this one
        # site is the constructor flip; the class stays as the predicate
        # handle until P4 deletes it.  Unknown keywords still raise.
        unknown = [k for k in kwargs if k not in fields]
        if unknown:
            raise _term_construction_error(cls, kwargs, _source_site(1))
        from clausal.logic.variables import Var  # noqa: PLC0415
        return (cls.__name__, *(kwargs[f] if f in kwargs else Var() for f in fields))

    def _clausal_head(cls, *args: Any, **kwargs: Any) -> Any:
        """RETIRED (W4a, 2026-09-22): the clause-HEAD instance constructor.
        A head is a CELL; ``cls(...)`` builds it.  Raises, never builds."""
        raise RetiredStateError(
            f"{cls.__name__}._clausal_head was retired (W4a, 2026-09-22): a "
            f"clause head is a cell; call {cls.__name__}(...) for the cell")

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
        return cls._state_row().mutate(author, kind, detail, through=cls)

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

    def _instance_head_clause(cls, clause: Any) -> Any:
        """The clause-store door on the CLASS side.

        P2 Task 3 turned a cell head back into an instance here, because the
        store kept heads as instances.  The head flip (2026-09-19) made the
        cell the stored shape, so there is nothing to convert and this is the
        identity -- kept as the named door so the class-side and
        ``Database``-side paths stay visibly symmetrical until P4 deletes
        both.
        """
        return clause

    def _assertz(cls, clause: Any) -> None:
        """append clause at end; the gate invalidates the compiled dispatch."""
        clause = cls._instance_head_clause(clause)
        with cls._gated("assert", "_assertz") as row:
            row.ensure_clauses().append(clause)

    def _asserta(cls, clause: Any) -> None:
        """Prepend clause at front; the gate invalidates the compiled dispatch."""
        clause = cls._instance_head_clause(clause)
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
        # backing dicts DIRECTLY rather than through the row's properties —
        # this is the once-per-goal-invocation path, and three property calls
        # where there used to be two plain attribute lookups is exactly the
        # overhead the phase must not add.
        # The logic below is the same three-step it always was: use the
        # installed dispatch; else recompile through the lazy callback and
        # prefer whatever ``_install`` stored over what the callback returned;
        # else refuse.
        row = cls._state_row()
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
        row = cls._row
        clauses = row.clauses if row is not None else ()
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
        - nothing was declared (the derived set is EMPTY for every name the
          Database holds no ``-dynamic`` mark for — vocabulary atoms, forward
          declarations, plain predicates — so all of those decline exactly
          as before, where the old class-stamped set answered ``None``);
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
        # THE ROW RAW, and the OWNER's Database (option D, 2026-09-22).  Both
        # reads here used to go through facades -- `_clauses` and
        # `_dynamic_arities` -- which for a class with no row MINT a private
        # throwaway one.  `cls._row` is a plain attribute, so this mints
        # nothing, and no row means nothing was declared and no clauses exist,
        # which is `None` either way.
        #
        # IMPORT SEMANTICS ARE PRESERVED BY CONSTRUCTION: for an
        # `-import_from` the shared class's `_row` IS the exporter's row, so
        # `row._db` is the OWNER's Database -- the same place the old
        # class-stamped set lived.  Deriving from the COMPILING module's db
        # would have read the importer's and silently lost the owner's
        # declarations.
        row = cls._row
        if row is None:
            return None
        if row.clauses:
            return None
        declared = {a for (f, a) in row._db._dynamic if f == cls.__name__}
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
        cls._state_row().locked = True

    def _unlock(cls) -> None:
        """Unlock the predicate, allowing runtime assertz/retract."""
        cls._state_row().locked = False

    def __repr__(cls) -> str:
        if not cls._fields:
            return cls.__name__
        # A repr must not mint a row: an unbound class reports the defaults.
        row = cls._row
        compiled = ("compiled" if row is not None and row.dispatch_fn is not None
                    else "uncompiled")
        n = len(row.clauses) if row is not None else 0
        locked = ", locked" if row is not None and row.locked else ""
        return (
            f"<Predicate {cls.__name__}/{cls._arity}, "
            f"{n} clause(s), {compiled}{locked}>"
        )


# ── Arity-aware dispatch resolution ──────────────────────────────────────────


def _refuse_if_known_at_another_arity(db: "Database", functor: str, arity: int) -> None:  # noqa: F821
    """Raise ``PredicateArityMismatchError`` if *db* knows *functor* as a
    predicate at some arity OTHER than *arity* -- the handle-dispatch twin
    of ``PredicateMeta._refuse_call_at``.  F7 (2026-09-24) first called it
    BEFORE ``Database.get_dispatch``'s builtin-registry fallback; the name +
    ARITY ruling (operator, 2026-09-24) moved it AFTER: a same-named builtin
    at the call arity is the normal answer, and this refusal is for the case
    where nothing answers (see the call site in ``_dispatch_at``).

    ``db.is_predicate_name(functor)`` -- not ``db.arities_for`` -- is the
    "known at some arity" test: ``arities_for`` scans only ``_signatures``/
    ``_dynamic``/``_clauses``/``_dispatch``/``_lazy_recompile``/``_rows``
    and is measurably lossy for a bare ``name/arity`` ``-module``/``-private``
    export entry (``mark_predicate_export``, no row minted) and for a row
    this database only ADOPTED via ``-import_from`` -- both of which
    ``is_predicate_name`` counts (it draws from the same union
    ``declared_kind`` does).  Using ``arities_for`` here would silently miss
    exactly the shapes an ``-import_from``'d or ``-module``-exported
    predicate takes before it has any clauses, and let a wrong-arity call on
    one of those fall through to the builtin fallback uncaught.

    Declines (returns, no raise) when:

    - *functor* is a known predicate AT ``arity`` itself
      (``declared_kind(functor, arity) == "predicate"``) -- not a mismatch,
      whatever ``get_dispatch`` goes on to do (a ``-dynamic`` predicate with
      no clauses yet compiled is this database's own business, not F7's);
    - *functor* is not a known predicate at ANY arity in *db* -- a plain
      builtin call, or a genuinely unknown name, both legitimate to resolve
      (or fail to resolve) the ordinary way.

    The reported "defined arity" is best-effort: ``arities_for`` (lossy, but
    fine for a MESSAGE rather than a decision) is asked for the OTHER
    arities; with exactly one candidate it is named, otherwise the
    diagnostic degrades to "does not accept N arguments" rather than
    guessing among several.
    """
    if db.declared_kind(functor, arity) == "predicate":
        return
    if not db.is_predicate_name(functor):
        return
    from clausal.predicate_diagnostics import predicate_arity_mismatch  # noqa: PLC0415
    others = sorted(a for a in db.arities_for(functor) if a != arity)
    defined = others[0] if len(others) == 1 else None
    raise predicate_arity_mismatch(functor, arity, defined)


def _resolve_other_arity_of_class(cls: "PredicateMeta", arity: int) -> Callable | None:
    """The dispatch a call of *arity* arguments reaches when the class *cls*
    (declared at ANOTHER arity) is not its target, or ``None``.

    Name + ARITY ruling (operator, 2026-09-24).  Resolved in the class's own
    module -- ``cls._row._db``, the Database a module-qualified handle for
    this class names -- through ``Database.get_dispatch``: that module's own
    row at *arity*, else the builtin registry.  Exactly what the handle arm
    of ``_dispatch_at`` consults at the same arity, so the two eras agree.
    ``None`` (the caller keeps its refusal) for an unbound class.
    """
    row = cls._row
    if row is None or row._db is None:
        return None
    functor = row._key[0]
    return row._db.get_dispatch(functor, arity)


def _binding_owner_db(binding: Any):
    """The Database that OWNS a predicate *binding* (class or handle), or
    ``None`` -- a class's row db, a handle's module db."""
    if isinstance(binding, PredicateMeta):
        row = binding._row
        return row._db if row is not None else None
    if type(binding) is str:
        from clausal.logic.atoms import is_mangled, demangle  # noqa: PLC0415
        if is_mangled(binding):
            return _db_for_module_name(demangle(binding)[0])
    return None


def binding_grants_arity(binding: Any, arity: int, db: Any, name: str) -> bool:
    """True when the predicate *binding* -- reached through the UNQUALIFIED
    name *name* in the module whose Database is *db* -- is that name's
    predicate at *arity*.  Era-agnostic.

    Operator rulings 2026-09-24 (name + ARITY; the aliased-import leak): a
    binding is the target only at an arity it is a predicate at
    (``is_declared_predicate``) AND, when it is IMPORTED (owned by another
    Database), only at an arity it was imported at: ``-import_from`` plants
    the exporter's rows under the local name (``compiler_v2.
    _plant_imported_rows``), so ``db.row(name, arity)`` answers exactly that.
    The owner's OTHER arities -- a later ``assertz`` there included -- are not
    imported.  Without this the handle era (whose ``is_declared_predicate``
    asks the owner's ``declared_kind``) would grant arities the class era
    (``len(_fields)``) does not.

    The import record is the importing db's ADOPTED rows under *name*
    (``Database.adopt_row``); a name with none -- a binding placed by hand
    (a hand-built globals dict, a held handle assigned in Python) rather
    than by ``-import_from`` -- has no import record to consult and is
    trusted at every arity it is a predicate at, as before.
    """
    if not is_declared_predicate(binding, arity=arity, db=db):
        return False
    owner = _binding_owner_db(binding)
    if owner is None or db is None or owner is db:
        return True
    adopted = db.adopted_arities(name)      # O(1) per-name index
    return not adopted or arity in adopted


def _refuse_unqualified_other_arity(binding: Any, name: str, arity: int,
                                    db: Any = None) -> Callable:
    """The last resort of an UNQUALIFIED call ``name(...)`` at *arity* whose
    name is bound to a predicate (class or handle) that is not its target at
    *arity*, after the calling module's own row and the builtins under
    *name* have both declined.  Raises ``PredicateArityMismatchError`` naming
    *name* -- the name the caller USED, which for an aliased import is not
    the owner's.

    Operator ruling 2026-09-24 (closing the aliased-import leak,
    ``todo/done/aliased-import-other-arity-resolves-in-the-owner-2026-09-24.md``):
    an unqualified call resolves in the CALLING module only; a binding
    grants the one arity it was imported at, never another arity in its
    owner.  So unlike ``_dispatch_at`` -- which serves a binding reached
    DIRECTLY or by a qualified/dotted reference and resolves the other arity
    in the binding's own module -- this never looks the name up in the
    owner.  Callers: ``solve.call`` Phase 5, ``globals_env``'s keep-binding
    branch, and ``_UnqualifiedName`` (the meta-call arm).

    One exception, and only for a class LOCAL to the calling module (its row
    is in *db*): a class whose ``_fields`` are stale while its clause heads
    ARE at *arity* (``PredicateMeta._clause_arity``) is this call's target
    after all, and its dispatch is returned.  An imported class never takes
    this exception -- its row is the owner's.
    """
    from clausal.predicate_diagnostics import (  # noqa: PLC0415
        PredicateArityMismatchError, predicate_arity_mismatch,
    )
    if isinstance(binding, PredicateMeta):
        row = binding._row
        clauses = row.clauses if row is not None else ()
        if (clauses and db is not None and row._db is db
                and all(_head_arity(c.head) == arity for c in clauses)):
            return binding._get_dispatch()        # stale _fields: the target
        try:
            defined = binding._clause_arity()
            if defined is None:
                defined = binding._declared_arity(arity)
        except Exception:  # noqa: BLE001 - a message, not a decision
            defined = None
        if defined is None:
            defined = len(getattr(binding, "_fields", ()))
        site = (getattr(binding, "_registered_at", None)
                if name == binding.__name__ else None)
        try:
            err = predicate_arity_mismatch(name, arity, defined, site=site)
        except Exception:  # noqa: BLE001 - the fault is still real; state it
            err = PredicateArityMismatchError(
                f"{name} takes {defined} arguments, "
                f"but this call passes {arity}")
        raise err
    defined = None
    from clausal.logic.cells import qualify_mangled_goal  # noqa: PLC0415
    _q = qualify_mangled_goal(binding) if type(binding) is str else binding
    if _q is not binding:
        owner = _db_for_module_name(_q[1])
        if owner is not None:
            others = sorted(a for a in owner.arities_for(_q[2]) if a != arity)
            defined = others[0] if len(others) == 1 else None
    raise predicate_arity_mismatch(name, arity, defined)


class _UnqualifiedName:
    """A meta-call goal that ARRIVED as an unqualified name of the calling
    module bound to an IMPORTED predicate (class or handle) -- the adapter
    ``localize_goal`` hands a meta-predicate (``call/N``, ``maplist`` & co.,
    ``phrase``, ``time_goal``) in place of the bare binding.

    Operator ruling 2026-09-24 (the aliased-import leak): ``maplist(nl, ...)``
    in ``alim`` must resolve under ``nl`` in ``alim``, exactly as a direct
    ``nl(...)`` body call does.  The bare binding cannot say that: it is the
    OWNER's class or handle, and ``_dispatch_at`` on it answers the owner's
    other arities (right for a qualified / directly held reference, wrong
    here).  ``_dispatch_at`` recognises this type and asks ``dispatch_at``.
    """
    __slots__ = ("db", "name", "binding")

    def __init__(self, db: Any, name: str, binding: Any) -> None:
        self.db = db
        self.name = name
        self.binding = binding

    def dispatch_at(self, arity: int) -> Callable:
        if binding_grants_arity(self.binding, arity, self.db, self.name):
            return _dispatch_at(self.binding, arity)
        fn = self.db.get_dispatch(self.name, arity)
        if fn is not None:
            return fn
        return _refuse_unqualified_other_arity(
            self.binding, self.name, arity, self.db)

    def _get_dispatch(self):
        # The frozen arity-free protocol: only a class knows its own arity.
        if isinstance(self.binding, PredicateMeta):
            return self.binding._get_dispatch()
        raise TypeError(
            f"{self.name!r}: a predicate handle needs the call arity")

    def __repr__(self) -> str:
        return f"_UnqualifiedName({self.name!r} -> {self.binding!r})"


def _binding_key(binding: Any) -> Any:
    """A dict key for a predicate binding: a handle by value, a class by id
    (the index entry holds the class itself, so the id cannot be reused)."""
    return binding if type(binding) is str else id(binding)


def _binding_own_name(binding: Any) -> str:
    """The OWNER's name of a predicate binding -- the functor a term built
    through it carries, whatever local spelling bound it."""
    if isinstance(binding, PredicateMeta):
        row = binding._row
        return row._key[0] if row is not None else binding.__name__
    from clausal.logic.atoms import demangle  # noqa: PLC0415
    return demangle(binding)[1]


def _import_index(db: Any, md: dict, force: bool = False):
    """The calling module's index of FOREIGN predicate bindings under plain
    names: ``(snapshot, by_binding, by_owner_name, adapters)``.

    Review rounds 4-5 (hot path): ``localize_goal`` and
    ``localize_owner_functor`` would otherwise scan the whole module dict on
    every meta-call.  Rebuilt when the dict's ``(id, len)`` snapshot changes
    (a name added or removed) or on demand (*force*) when a hit fails its
    verification against the live dict (a same-size rebinding).  Every
    POSITIVE answer is verified against the live dict before use; a NEGATIVE
    answer is trusted for as long as the snapshot holds -- the cheap version
    check -- so a same-size rebinding that newly binds an import under a
    plain name is picked up at the next size change.
    """
    snap = (id(md), len(md))
    idx = db.__dict__.get("_import_index")
    if idx is not None and idx[0] == snap and not force:
        return idx
    by_binding: dict = {}
    by_owner: dict = {}
    for k, v in md.items():
        if type(k) is not str or "." in k:
            continue
        if not (isinstance(v, PredicateMeta)
                or (type(v) is str and _is_mangled_fast(v))):
            continue
        if not is_declared_predicate_name(v):
            continue
        owner = _binding_owner_db(v)
        if owner is None or owner is db:
            continue
        by_binding.setdefault(_binding_key(v), []).append((k, v))
        by_owner.setdefault(_binding_own_name(v), []).append((k, v))
    idx = (snap, by_binding, by_owner, {})
    db.__dict__["_import_index"] = idx
    return idx


def _is_mangled_fast(s: str) -> bool:
    from clausal.logic.atoms import is_mangled  # noqa: PLC0415
    return is_mangled(s)


def _live_entries(md: dict, entries) -> list:
    return [(n, b) for (n, b) in entries
            if (md.get(n) is b) or (type(b) is str and md.get(n) == b)]


def localize_goal(db: Any, goal_val: Any) -> Any:
    """*goal_val* as a meta-call in the module whose Database is *db*.

    When *goal_val* is a predicate binding (class or handle) that *db* did not
    define itself but binds under an unqualified name -- an ``-import_from``,
    aliased or not -- return an ``_UnqualifiedName`` so the call resolves under
    that name in *db* (operator ruling 2026-09-24).  Anything else --
    including a binding *db* owns, which resolves in *db* either way, and a
    binding *db* does not bind by any plain name (a qualified reference) --
    comes back unchanged.

    The one ambiguity is inherent: a handle string built by a QUALIFIED
    reference is equal to the owner handle an import binds, so in a module
    that also imports that predicate it is read as the import.  A qualified
    meta-call is spelled ``M:G`` and resolved by ``_resolve_named_goal``'s
    qualified arm, which this does not touch.

    Several plain names for one binding: the owner's own name wins when it is
    one of them, else the alphabetically first -- deterministic.  Indexed:
    see ``_import_index`` (positive and negative answers, verified / version
    checked).
    """
    if db is None:
        return goal_val
    if not (isinstance(goal_val, PredicateMeta)
            or (type(goal_val) is str and _is_mangled_fast(goal_val))):
        return goal_val
    md = getattr(db, "module_dict", None)
    if not isinstance(md, dict):
        return goal_val
    key = _binding_key(goal_val)
    for force in (False, True):
        idx = _import_index(db, md, force)
        # fast path: the adapter chosen last time, verified (one dict lookup)
        chosen = idx[3].get(key)
        if chosen is not None:
            bound = md.get(chosen.name)
            if bound is goal_val or (type(bound) is str and bound == goal_val):
                return chosen
        entries = idx[1].get(key)
        if not entries:
            return goal_val               # negative: trusted while snapshot holds
        live = _live_entries(md, entries)
        if live:
            names = [n for n, _ in live]
            own = _binding_own_name(goal_val)
            name = own if own in names else sorted(names)[0]
            adapter = idx[3][key] = _UnqualifiedName(db, name, goal_val)
            return adapter
    return goal_val


def localize_owner_functor(db: Any, functor: str, arity: int):
    """For a named goal (cell or atom) ``functor/arity`` whose functor is NOT
    bound in the calling module but IS the owner's name of a predicate the
    module imported under an ALIAS **at this very arity**: the
    ``_UnqualifiedName`` for that alias, else ``None`` (the normal lookup).

    A term built through an imported binding keeps the OWNER's functor
    (``dd(N, M)`` with ``alias(dec, dd)`` is ``("dec", N, M)``) -- an alias is
    a local spelling of ONE predicate, and its terms must unify with the
    owner's.  The calling module does not bind ``dec``, so without this a
    goal it built through its own import would fail at the IMPORTED arity.

    Controller decision (round 6, reviewer's option 2, reported to the
    operator): remap ONLY at the arities the alias imported
    (``binding_grants_arity``).  At every other arity the goal is just a goal
    named by the owner's functor, whoever built it -- ``numlist(1, 5, L)``
    from univ or from another module must reach the builtin ``numlist/3``,
    as it did before -- so it takes the calling module's normal lookup.
    Documented consequence: ``call(nl(3), L)`` builds ``("numlist", 3)`` and
    at arity 2 resolves as ``numlist/2`` in the caller (the builtin answers)
    -- partial application through an alias behaves like writing the owner's
    name, because the term IS the owner's term.
    """
    if db is None:
        return None
    md = getattr(db, "module_dict", None)
    if not isinstance(md, dict) or functor in md:
        return None
    for force in (False, True):
        idx = _import_index(db, md, force)
        entries = idx[2].get(functor)
        if not entries:
            return None
        live = [(n, bd) for (n, bd) in _live_entries(md, entries)
                if binding_grants_arity(bd, arity, db, n)]
        if live:
            name, binding = sorted(live, key=lambda e: e[0])[0]
            key = ("$functor", functor, arity)
            adapter = idx[3].get(key)
            if adapter is None or adapter.name != name or adapter.binding is not binding:
                adapter = idx[3][key] = _UnqualifiedName(db, name, binding)
            return adapter
        if _live_entries(md, entries):
            return None                  # imported, but not at this arity
    return None


def _dispatch_at(obj: Any, arity: int, db: Any = None) -> Callable:
    """Resolve *obj*'s dispatch function for a call of *arity* arguments.

    *db*, when given, is the CALLER's database -- the ruling-Q0 hint: a
    predicate HANDLE naming the caller's own module resolves there even when
    the ``.clausal`` runner has popped that module from ``sys.modules``
    (``_owner_db_for_module_name``).  Every other shape ignores it.

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
    if type(obj) is _UnqualifiedName:
        # Operator ruling 2026-09-24: a meta-call goal that arrived as an
        # unqualified name resolves under THAT name in the calling module.
        return obj.dispatch_at(arity)
    if isinstance(obj, PredicateMeta):
        # F7 (ruled 2026-09-24): the ARITY-TAKING OVERLOAD of ``_get_dispatch``
        # is retired from this call site -- measured (full suite, before vs.
        # after deleting this branch outright) that a bare ``getattr(obj,
        # "_get_dispatch", None)()`` fallback for a raw ``PredicateMeta``
        # class is NOT a safe replacement today: ``solve.call``'s "Phase 5"
        # fast path (``pred_cls = module.module_dict.get(functor); dispatch_fn
        # = _dispatch_at(pred_cls, arity)``) passes a raw class through here
        # *by design*, with its own comment stating the point is exactly the
        # clean ``PredicateArityMismatchError`` this refusal gives instead of
        # a raw ``TypeError`` from a mismatched positional-argument call.
        # Deleting this branch outright measured 38 new failures, entirely in
        # ``test_predicate_arity_mismatch_diagnostic.py`` (higher-order
        # families, ``call/N``, ``findall``, ``phrase``, imported/declared
        # arity messages) -- so the refusal moves OUT of ``_get_dispatch``'s
        # arity parameter and INTO this funnel directly: ``_refuse_call_at``
        # is a plain ``PredicateMeta`` method, not part of the frozen
        # duck-typed protocol, so this is not "another `_get_dispatch` with an
        # arity parameter" -- it is calling the SAME diagnostic
        # ``_get_dispatch(arity)`` used to reach, from the one place still
        # holding a raw class rather than a handle.  ``_get_dispatch()``
        # itself is called bare here, same as every other implementor.
        #
        # Name + ARITY ruling (operator, 2026-09-24): a predicate name is
        # name+arity, so a class whose clauses say it is ``p/1`` is simply
        # not the target of a ``p/2`` call.  Before refusing, ``p/2`` is
        # resolved the way the handle arm below resolves it -- in the
        # class's OWN module (``row._db``, the module a handle for this class
        # would name): that module's row at the call arity, else the builtin
        # registry (``Database.get_dispatch`` asks both).  The refusal stays
        # only when nothing answers there, so the class era and the handle
        # era agree (the class-era refusal ahead of a live answer was an
        # artefact of the predicate being a class).
        try:
            obj._refuse_call_at(arity)
        except TypeError as refusal:
            # imported only on the refusal path: this arm is hot (review
            # round 4 measured the per-call import statement)
            from clausal.predicate_diagnostics import (  # noqa: PLC0415
                PredicateArityMismatchError,
            )
            if not isinstance(refusal, PredicateArityMismatchError):
                raise
            fn = _resolve_other_arity_of_class(obj, arity)
            if fn is not None:
                return fn
            raise
        return obj._get_dispatch()
    if is_chars(obj):
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
        raise LogicException(string_goal_error(chars_text(obj), arity, "call/N"))
    if type(obj) is str:   # STAGE 2: the atom (was the arity-0 cell)
        from clausal.logic.cells import qualify_mangled_goal  # noqa: PLC0415
        _q = qualify_mangled_goal(obj, db=db)
        if _q is not obj:
            # W4 (ruled 2026-09-22): a MANGLED atom naming a LOADED module is
            # a module-qualified predicate HANDLE -- the value a held
            # ``m.pred`` becomes once the class goes -- and a compiled body
            # calling a name bound to one arrives here.  Resolve it in ITS
            # module: the row first (W4-proof), then the module's namespace,
            # which is where an ``-import_from``'d predicate is reachable --
            # it lives on the EXPORTER's row, and following the binding is
            # what ``call/N`` does too, so the two paths agree.
            from clausal.logic.solve import resolve_module  # noqa: PLC0415
            _mod_name, _name = _q[1], _q[2]
            _hint = _hint_db(db)
            if _hint is not None and _mod_name == _hint.module_name():
                # Q0: the caller's own module, answered from the caller's db
                # -- resolve_module would look in sys.modules and miss it.
                _hdb, _hmd = _hint, _hint.module_dict
            else:
                _module = resolve_module(_mod_name, None, "call/N")
                _hdb, _hmd = _module.db, _module.module_dict
            # F7 (ruled 2026-09-24): the arity check runs BEFORE
            # ``Database.get_dispatch``'s builtin-registry fallback.
            # ``get_dispatch`` falls back to a same-named builtin keyed
            # ``(functor, arity)`` when the handle's own module has no
            # dispatch entry at THIS arity -- and a user predicate wrong-
            # arity call is exactly that shape (no entry at the call arity,
            # an entry at its own).  Without this check first, deleting the
            # old arity-aware ``PredicateMeta._get_dispatch(arity)`` arm (the
            # one place that used to refuse before looking anything up)
            # would let a wrong-arity call on ``foo/2`` SILENTLY resolve to
            # a builtin ``foo/3`` instead of refusing (measured:
            # ``numlist/1`` in a module that also has a 2-clause local
            # definition, called at arity 2, used to silently hand back the
            # ``numlist/2`` builtin -- see shadow_census.py).
            #
            # REVERSED by the name + ARITY ruling (operator, 2026-09-24): a
            # predicate name is name+arity, so ``numlist/1`` is not the
            # target of a ``numlist/2`` call and the builtin ``numlist/2``
            # answering it is the NORMAL resolution, not a silent shadow
            # (the class-era refusal was an artefact of the predicate being
            # a class).  ``get_dispatch`` -- this module's row at the call
            # arity, else the builtin registry -- is therefore asked FIRST;
            # the refusal stays, after it, for the case where nothing
            # answers.
            _fn = _hdb.get_dispatch(_name, arity)
            if _fn is not None:
                return _fn
            _refuse_if_known_at_another_arity(_hdb, _name, arity)
            _bound = (_hmd or {}).get(_name)
            if _bound is not None and _bound is not obj:
                return _dispatch_at(_bound, arity, _hdb)
            from clausal.logic.exceptions import (  # noqa: PLC0415
                LogicException, existence_error,
                dangling_handle_indicator_and_why,
            )
            # Ruling 2026-09-24 (todo/mangled-goal-culprit-terms-are-
            # malformed-2026-09-23.md): the culprit is the bare Name/Arity
            # indicator -- never a module-qualified compound -- with the
            # module named in the message only, matching the other two
            # entry points (solve's normalisation, call/N) so a ``catch/3``
            # pattern against a dangling handle is the same shape wherever
            # it is written.
            indicator, why = dangling_handle_indicator_and_why(
                _mod_name, _name, arity, loaded=True,
            )
            raise LogicException(existence_error(
                "procedure", indicator,
                f"{why} (reached through a module-qualified handle)"))
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
            dangling_handle_indicator_and_why,
        )
        from clausal.logic.atoms import is_mangled, demangle  # noqa: PLC0415
        from clausal.terms import Compound  # noqa: PLC0415
        if is_mangled(obj):
            # *obj* IS a predicate handle (``qualify_mangled_goal`` above
            # left it untouched only because its module half is not a
            # loaded Clausal module) -- a dangling handle, not the ordinary
            # "atom resolved via a data reference" case below, and it must
            # never carry the raw ``\x1f`` spelling into a catchable term
            # (ruling 2026-09-24, todo/mangled-goal-culprit-terms-are-
            # malformed-2026-09-23.md).
            _mod_name, _name = demangle(obj)
            indicator, why = dangling_handle_indicator_and_why(
                _mod_name, _name, arity, loaded=False,
            )
            raise LogicException(existence_error("procedure", indicator, why))
        name = obj
        indicator = Compound("/", (name, arity))
        raise LogicException(
            existence_error(
                "procedure", indicator,
                f"atom {name!r} is not callable at arity {arity} "
                f"(resolved via a data reference; define or import the "
                f"predicate, or call it by its local name)",
            )
        )
    getter = getattr(obj, "_get_dispatch", None)
    if getter is None:
        # W3 (ruled 2026-09-22): the callee is not a predicate of any kind --
        # a MODULE when a dotted name landed on a package, or any other Python
        # value.  A NAMED LogicException rather than CPython's AttributeError:
        # downstream gates classify this failure by its rendered text, and the
        # class name is the token they may key on, so it is put in the message
        # itself.  See ``exceptions.DispatchTargetError``.
        import types as _types  # noqa: PLC0415
        from clausal.logic.exceptions import (  # noqa: PLC0415
            DispatchTargetError, type_error,
        )
        if isinstance(obj, _types.ModuleType):
            culprit = obj.__name__
            what = f"module {obj.__name__!r}"
        else:
            # The CULPRIT is the offending value itself, as an ISO
            # type_error's is (roborev on e7ac22ad); the human context carries
            # a BOUNDED repr that cannot itself raise -- building an exception
            # must never be the thing that fails.
            import reprlib as _reprlib  # noqa: PLC0415
            try:
                repr(obj)
                culprit = obj
            except Exception:  # noqa: BLE001 - a repr that raises loses nothing
                # ``LogicException`` renders its term with ``repr`` when it
                # is built, so a value whose repr raises cannot be the
                # culprit without the diagnostic itself failing; its TYPE
                # stands in.  (``reprlib.repr`` alone cannot decide this: it
                # swallows the failure and returns a placeholder.)
                culprit = type(obj).__name__
            what = f"a {type(obj).__name__} value {_reprlib.repr(obj)}"
        raise DispatchTargetError(type_error(
            "callable", culprit,
            f"DispatchTargetError: the goal at arity {arity} resolved to "
            f"{what}, not a predicate; a dotted target must name a predicate "
            f"inside the module (or import it), and a Python value is not "
            f"callable as a goal"))
    return getter()


# ── Python reference implementations (kept as fallbacks) ─────────────────────


def _is_term_instance_py(obj: Any) -> bool:
    """True if obj is a term instance with named fields (not a type/class).

    A ``@dataclass`` instance, and only that: W4a (2026-09-22) retired the
    predicate-INSTANCE path, so a predicate class builds a CELL and there is
    no second shape left for this to answer about.  A cell is a tuple and is
    NOT a term instance -- callers discriminate the two, they do not conflate
    them.
    """
    if isinstance(obj, type):
        return False
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
    """Return field name strings for a term instance (a ``@dataclass`` one).

    W4a: the predicate-instance arm went with the instance path.  The CLASS
    twin, ``term_field_names_of_class``, still answers for a predicate class
    -- that is a different question and it stays until W4b.
    """
    if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        return tuple(f.name for f in dataclasses.fields(obj))
    raise TypeError(f"Not a term instance: {obj!r}")


def _db_for_module_name(module_name: str):
    """The Database of a LOADED module, by name, or None.

    Split out so the mangled-name arm can be tested without a real module
    load, and so the lookup has one home when W4b-2 adds callers.

    A loaded ``.clausal`` module has no ``db`` attribute of its own -- its
    Database lives at ``mod.__dict__["$module"].db`` (the same idiom used
    by ``testing.py``'s ``db = getattr(namespace.get("$module"), "db",
    None)`` and ``compiler_v2.py``'s ``getattr(exporter, "db", None)``
    reads).  Measured: 0 of 251 loaded modules carry a bare ``.db``, so a
    ``getattr(mod, "db", None)`` fallback would be dead code, not a real
    module kind -- it is deliberately not restored here.
    """
    import sys  # noqa: PLC0415
    mod = sys.modules.get(module_name)
    if mod is None:
        return None
    return namespace_db(mod.__dict__)


def namespace_db(namespace) -> "Database | None":
    """The Database a module NAMESPACE carries (``namespace["$module"].db``),
    or ``None`` -- the one home for reading a ruling-Q0 ``db=`` hint off a
    namespace, and for ``_db_for_module_name``'s ``sys.modules`` read.

    PLACEHOLDER TRAP (measured 2026-09-24; CLOSED for compile_module by
    ``compiler_v2._install_real_module``): while ``import_hook`` execs a
    module BODY, ``namespace["$module"]`` is the hook's PLACEHOLDER
    ``LogicModule``.  Its Database shares the module dict, so
    ``module_name()`` is the real module's: it captures every local handle
    and answers from an empty store.  ``compile_module`` now installs the
    real module as ``$module`` (and ``__clausal_module__``) before its first
    step, so from there on this answers the db being filled.  Only the body
    exec still sees the placeholder, and there the real db does not exist
    yet, so there is nothing a handle could answer from.
    """
    if not namespace:
        return None
    try:
        return getattr(namespace.get("$module"), "db", None)
    except AttributeError:          # not a mapping
        return None


def _hint_db(db):
    """*db* as a ruling-Q0 hint, or ``None`` when it cannot be one.

    Only a database backed by a real module dict names a module: a db-like
    shim with no ``module_dict`` (``globals_env._GlobalsDb``) or a
    ``Database("x")`` built on a bare string is treated as NO hint rather
    than crashing or capturing handles meant for a loaded module called
    ``"x"``.  Callers therefore pass whatever db they hold, unguarded.
    """
    if db is None or not isinstance(getattr(db, "module_dict", None), dict):
        return None
    return db


def _owner_db_for_module_name(module_name: str, db=None):
    """The Database that owns *module_name*'s predicates: the caller's own
    *db* when it IS that module (ruling Q0 -- the ``.clausal`` runner pops
    loaded modules from ``sys.modules``), else the loaded module's, else
    ``None``.  One home for the local-first rule, shared by the resolvers,
    ``cells.qualify_mangled_goal`` and ``_dispatch_at``'s handle arm."""
    hint = _hint_db(db)
    if hint is not None and module_name == hint.module_name():
        return hint
    return _db_for_module_name(module_name)


def _resolve_mangled_owner(binding, db=None):
    """``(db, functor)`` for a mangled *binding* whose owner module is a
    LOADED Clausal module, or ``None``.

    *db*, when given, is the CALLER's own database, and it is asked first
    (ruling Q0, 2026-09-24): if the handle's module half is ``db``'s own
    module name the handle is local and resolves there, without touching
    ``sys.modules`` -- which the ``.clausal`` test runner empties of every
    module it loads (measured: the owner was absent from ``sys.modules`` in
    43 of 46 descents, all of them local).  A handle naming another module
    still resolves through ``sys.modules``; a registry for a popped
    cross-module owner is deferred until a case needs it.

    The hint is ADDITIVE and, when this landed, passed by no production
    caller: before the flip no predicate binding is a handle, so nothing
    needs it yet.  Each consumer passes its db as it migrates (F1 rows
    58/59/60, then the flip) -- tracked in
    ``todo/q0-db-hint-must-be-wired-at-each-consumer-2026-09-24.md``.

    Shared plumbing for ``resolve_predicate_row``/``is_declared_predicate``'s
    mangled-atom arm: demangle, then require a real ``Database`` at the
    owner.  ``_db_for_module_name(...) is not None`` is the test -- NEVER
    ``module_name in sys.modules`` alone (``todo/qualify-mangled-goal-
    tests-only-sys-modules-2026-09-23.md`` records the live bug that check
    causes: a mangled handle whose module half collides with an unrelated
    loaded Python module, e.g. ``json``, would otherwise read as resolved).

    Takes no ``arity`` (review round, 2026-09-23): this lookup answers
    "which db and functor", never consults an arity to do it, and both
    callers already have their own copy for the read that follows -- an
    unused parameter here was speculative generality on a private
    two-caller helper, not a real shared need.
    """
    from clausal.logic.atoms import demangle  # noqa: PLC0415
    module_name, functor = demangle(binding)
    # Local first (``_owner_db_for_module_name``); a hint that is not a real
    # module database (``_hint_db``) is no hint.
    owner = _owner_db_for_module_name(module_name, db)
    if owner is None:
        return None
    return owner, functor


def mint_predicate_handle(db, functor: str) -> str:
    """The module-qualified handle for *functor* as a predicate of *db*
    (ruling X3, 2026-09-24): ``mangle(db.module_name(), functor)``.

    Minted from the DATABASE, never from a class's ``__module__``: a
    ``make_predicate`` class carries the MINTER's module
    (``clausal.logic.predicate`` for 14 of 15 measured ``-specialize``
    targets), and a handle naming a module with no Database resolves to
    nothing, silently.  A database with no module name cannot own a handle,
    so it is refused rather than minted into one nothing will resolve.
    """
    from clausal.logic.atoms import mangle  # noqa: PLC0415
    module_name = db.module_name()
    if module_name in ("<anonymous>", "<detached>"):
        raise ValueError(
            f"cannot mint a predicate handle for {functor!r}: its database "
            f"belongs to no module ({module_name})")
    return mangle(module_name, functor)


def is_bound_predicate_at(binding, arity: int, db=None) -> bool:
    """Is *binding* a predicate at *arity*, reading the arity from where the
    predicate LIVES?

    A ``PredicateMeta`` class bound to a real row answers with that row's
    arity (``row.key[1]``): a class can be bound at an arity its ``_fields``
    do not spell (a name re-bound within its database), and the row is what
    a write or a call reaches.  Everything else -- an unbound class, a
    detached one, a mangled handle -- is ``is_declared_predicate``.  The
    ONE arity source for the load channel's "is this the imported
    predicate?" questions (``compiler_v2._implements_an_imported_declaration``
    and :func:`is_foreign_class_at_other_arity`), so the two cannot disagree
    about a class whose fields and row differ (round-7 review).
    """
    if isinstance(binding, PredicateMeta):
        row = binding._row
        if row is not None and not row.detached:
            return row.key[1] == arity
    return is_declared_predicate(binding, arity=arity, db=db)


def is_foreign_class_at_other_arity(binding, db, arity: int) -> bool:
    """True when *binding* is a ``PredicateMeta`` class already reading
    ANOTHER Database's real row, at an arity other than *arity*.

    That is an ``-import_from``'d predicate whose name this module ALSO uses
    at another arity for a predicate of its own (``-import_from(a, [p])``
    binds a's ``p/1`` class; this file defines ``p/2``).  The ``p/2`` head is
    this module's own predicate -- its row is this module's, exactly as the
    handle era resolves it -- so the class must be neither bound to it
    (``_bind_row`` would move a's predicate) nor handed the ``p/2`` dispatch
    or index plans (they would land on a's ``p/1`` row), nor put a's row in
    the write's blast radius (operator ruling 2026-09-24: a local ``p/2``
    beside an imported ``p/1`` LOADS -- name and arity make a different
    predicate).  Class era only: a mangled handle has no class to mis-bind,
    and ``through=`` resolves it at the written arity.

    The arity is the BOUND ROW's (``row.key[1]``), not ``len(_fields)``: a
    class can be bound at an arity its field names do not spell (a name
    defined at two arities re-binds it within its database).
    """
    if not isinstance(binding, PredicateMeta):
        return False
    row = binding._row
    if row is None or row.detached or db is None or row.db is db:
        return False
    return not is_bound_predicate_at(binding, arity)


def resolve_predicate_row(binding, *, arity: int,
                          db=None) -> "PredRow | None":
    """F1: the live ``PredRow`` for a module-dict *binding*, era-agnostic.

    Answers correctly whether *binding* is still a ``PredicateMeta`` CLASS
    (today) or already a module-qualified MANGLED ATOM (post W4b-2d) --
    the shape the 23 F1-family call sites need (``._row``, ``.clauses``,
    ``.dispatch_fn``, ``.locked``, ``_lock()``, or a value handed to
    ``_install``/``analyze_mi``/a mutation gate's ``through=``), per
    ``implementation_plans/w4b2-open-questions-2026-09-23.md`` Q2.

    *arity* is REQUIRED and keyword-only.  For the class arm it is not
    consulted (a ``PredicateMeta`` class already carries its own row, at
    whatever arity that row was bound at -- matching today's bare
    ``isinstance`` sites, none of which cross-check arity either); for the
    mangled-atom arm it is the ONLY source of arity -- never guessed via
    ``Database.arities_for`` or any other search.  A data atom misused in
    goal position arrives at a different arity than it was declared at, and
    the caller's own call site (a clause head, a goal, a directive target)
    already knows the arity it means, in both eras alike -- see hazard 3 in
    the W4b-2b brief.

    Three cases:

    1. ``binding`` is a ``PredicateMeta`` class -> ``binding._row`` (may be
       ``None`` -- unbound; deliberately NOT ``binding._state_row()``,
       which would MINT a fresh private detached row on the read and make
       every F1 site that tests ``cls._row is not None`` as a bailout start
       seeing a row that was never really there).
    2. ``binding`` is a mangled atom naming a loaded Clausal module's row at
       exactly *arity* -> that ``PredRow``.
    3. Anything else -- a ``@dataclass`` class, a plain non-mangled string
       (even one that happens to spell something -- hazard 1), a mangled
       atom whose module half is not a loaded Clausal module (unloaded, or
       a real Python module with no Clausal ``Database``, e.g. ``json``),
       ``None``, or an arbitrary object -> ``None``.  This function never
       widens past what W4b-1's own hazard already burned: "could a
       ``@dataclass`` class ever reach this, and would the True branch be
       wrong" is answered ``wrong`` for every one of these shapes.
    """
    if isinstance(binding, PredicateMeta):
        return binding._row
    from clausal.logic.atoms import is_mangled  # noqa: PLC0415
    if is_mangled(binding):
        resolved = _resolve_mangled_owner(binding, db)
        if resolved is None:
            return None
        db, functor = resolved
        return db.row(functor, arity)
    return None


def is_declared_predicate(binding, *, arity: int, db=None) -> bool:
    """F2: True iff *binding* denotes a declared PREDICATE (never data), at
    exactly *arity*, era-agnostic.

    The predicate-name-as-atom coercion (a bare predicate reference in term
    position denotes the atom of its own name; a same-shaped data functor
    must NOT) plus the ``-table``/``-discontiguous``/``-shallow`` directive-
    target typo guards -- the 15 F2-family rows, per
    ``implementation_plans/w4b2-open-questions-2026-09-23.md`` Q2.  Same
    *arity* contract as ``resolve_predicate_row``: required, keyword-only,
    never guessed.

    Three cases:

    1. ``binding`` is a ``PredicateMeta`` class -> ``len(binding._fields) ==
       arity`` (``getattr``-guarded: a bare ``class X(metaclass=
       PredicateMeta): pass`` with no ``_fields`` of its own answers
       ``False`` rather than raising).  ARITY-STRICT (review round,
       2026-09-23; ruled, not merely tightened) -- the first cut answered
       ``True`` unconditionally here, mirroring today's bare
       ``isinstance(x, PredicateMeta)`` sites, which do not check arity
       either.  That is exactly the trap: those 15 sites would have
       migrated arity-blind and then silently flipped to arity-STRICT the
       moment a binding became a mangled atom (arm 2 already requires an
       exact match) -- a behaviour change landing at the one moment no gate
       covers it, the same shape this campaign has already been bitten by
       twice.  F2's own stated question is "is this a predicate AT THIS
       EXACT ARITY" -- strict is the intent in both eras, not a new
       restriction, so any site that turns out to depend on arity-blindness
       needs to surface as a suite failure now, under the full gate, not at
       the flip.  See
       ``test_kind_predicate_class_is_arity_strict_in_both_eras``.
    2. ``binding`` is a mangled atom naming a loaded Clausal module ->
       ``db.declared_kind(functor, arity) == "predicate"`` at the owner's
       db.  Exact arity, exact string match against ``declared_kind``'s
       three answers (``"predicate"``, ``"data"``, ``None``) -- NOT
       ``!= "data"`` (which the open-questions doc's Q1.2 chose for a
       DIFFERENT question, "is this a callable handle at all," where an
       unknown name must still qualify; F2 asks the narrower "is this
       AFFIRMATIVELY a predicate," where an unknown name must answer
       ``False``, not fall through as if it might be one).
    3. Anything else (the same six hazard-1 shapes ``resolve_predicate_row``
       refuses) -> ``False``.
    """
    if isinstance(binding, PredicateMeta):
        return len(getattr(binding, "_fields", ())) == arity
    from clausal.logic.atoms import is_mangled  # noqa: PLC0415
    if is_mangled(binding):
        resolved = _resolve_mangled_owner(binding, db)
        if resolved is None:
            return False
        db, functor = resolved
        return db.declared_kind(functor, arity) == "predicate"
    return False


def predicate_binding_name(binding, *, db=None) -> "str | None":
    """F1 rows 27/29: the predicate's OWN name for a module-dict *binding*,
    era-agnostic -- or ``None`` when *binding* is not a declared predicate.

    An aliased ``-import_from(m, [alias(f, G)])`` binds the exporter's
    predicate under ``G``; clause heads compile to ``f``, so the load channel
    needs ``f`` back from the binding.  Today that is the class's
    ``__name__``; after the flip it is the atom half of the mangled spelling,
    which ``demangle`` reads directly -- no class needed.

    Gated on :func:`is_declared_predicate_name`, so a mangled DATA atom, a
    plain string and a mangled atom naming an unloaded module all answer
    ``None`` rather than a name.
    """
    if not is_declared_predicate_name(binding, db=db):
        return None
    if isinstance(binding, PredicateMeta):
        return binding.__name__
    from clausal.logic.atoms import demangle  # noqa: PLC0415
    return demangle(binding)[1]


def is_declared_predicate_name(binding, *, db=None) -> bool:
    """F2b: True iff *binding* denotes a declared PREDICATE, AT ANY ARITY,
    era-agnostic.

    The predicate-name-as-atom coercion population -- 12 of F2's original 15
    F2-family rows (row 20 excluded: it reads ``type()`` of a live term
    INSTANCE, not a namespace binding, and has no mangled arm to give --
    see ``implementation_plans/w4b2-f2b-and-hard-families-2026-09-23.md``
    Q5; rows 30/31 excluded: F1-shaped, they read ``cls._row`` directly and
    had already migrated to ``resolve_predicate_row`` before F2b started).
    A bare reference to a predicate in term position denotes the ATOM of its
    own name -- a bare ``p/3`` denotes the atom ``p`` exactly as a bare
    ``p/0`` would -- so unlike :func:`is_declared_predicate`, this accessor
    is deliberately ARITY-BLIND: none of its 12 call sites read or compare
    an arity on the ``PredicateMeta`` arm today (bare
    ``isinstance(x, PredicateMeta)``), and forcing an ``arity`` keyword
    through here would mean either fabricating one (wrong for a predicate
    declared at an arity other than the guess) or loosening
    ``is_declared_predicate`` itself back to arity-blind (reopening the
    typo-masking hole rows 30/31 exist to close).  One function cannot hold
    both an arity-required-and-EXACT contract and an arity-IRRELEVANT one;
    this is ``is_declared_predicate``'s own hazard, mirrored -- confirmation
    it is a second function, not an optional keyword on the first.

    Two cases:

    1. ``binding`` is a ``PredicateMeta`` class -> ``True``, unconditionally
       (no arity read, matching every one of the 12 sites' bare
       ``isinstance`` today).
    2. ``binding`` is a mangled atom naming a loaded Clausal module ->
       ``db.is_predicate_name(functor)`` at the owner's db -- the
       arity-free existence scan (Q2: NEVER ``db.arities_for(functor)``,
       which silently misses a ``mark_predicate_export``-only or
       ``adopt_row``-only declared predicate; verified by probe, see the
       method's own docstring).
    3. Anything else -- the same six hazard-1 shapes
       ``resolve_predicate_row``/``is_declared_predicate`` refuse (a
       ``@dataclass`` class, a plain non-mangled string even one that
       happens to spell something, a mangled atom whose module half is not
       a loaded Clausal module, ``None``, an arbitrary object) -> ``False``.
       A bare ``@dataclass`` class never satisfies case 1 (it is not a
       ``PredicateMeta`` instance) and never satisfies case 2 (it is not a
       ``str``, so ``is_mangled`` is ``False``) -- there is no established
       rule that a bare dataclass CLASS reference means the atom of its
       name, and this accessor never invents one.  That is also why rows
       43/44's ISO 8.5.1.3(e) atomicity gates
       (``isinstance(name_val, (PredicateMeta, int, float, bool, bytes))``)
       are safe to migrate here even though the SHAPE accessor
       (``field_names_for``) is not: this function is IDENTITY-shaped like
       the ``isinstance`` it replaces, never SHAPE-shaped like
       ``field_names_for`` -- it does not widen to accept a dataclass, so
       ``functor(T, SomeDataclass, 0)`` keeps raising
       ``type_error(atomic, ...)`` exactly as before.
    """
    if isinstance(binding, PredicateMeta):
        return True
    from clausal.logic.atoms import is_mangled  # noqa: PLC0415
    if is_mangled(binding):
        resolved = _resolve_mangled_owner(binding, db)
        if resolved is None:
            return False
        db, functor = resolved
        return db.is_predicate_name(functor)
    return False


def predicate_owner_module(binding) -> "str | None":
    """F4: the name of the module that OWNS the predicate *binding* denotes,
    era-agnostic, or ``None``.

    A ``PredicateMeta`` class answers its ``__module__``; a mangled atom
    answers its module half (after the flip a module attribute for a
    predicate is a mangled atom, and a ``str`` has no ``__module__`` -- a
    filter keyed on ``getattr(value, "__module__")`` then selects NOTHING).
    Anything else -> ``None``.  Does not require the owner to be loaded.
    """
    if isinstance(binding, PredicateMeta):
        owner = getattr(binding, "__module__", None)
        return owner if isinstance(owner, str) else None
    from clausal.logic.atoms import demangle, is_mangled  # noqa: PLC0415
    if is_mangled(binding):
        return demangle(binding)[0]
    return None


def predicate_arities_for(binding, *, cache: "dict | None" = None,
                          db=None) -> "set[int]":
    """F4 (ruling 3): the SET of arities *binding* is a DEFINED predicate
    at, era-agnostic; the EMPTY set means "not a predicate" -- the role
    ``None`` played for the single-arity reader this replaces
    (``predicate_diagnostics._arity_of``, whose ``if arity:`` guards dropped
    every ``p/0``).  Several arities are several answers, not ambiguity.

    "Defined" is the owner db's HOME keys (``Database.arity_maps()[0]``,
    exactly ``owned_keys``), never the declared-only extras: an arity known
    only from a bare ``name/arity`` export entry or an adopted row is not
    one a call reaches -- with ``p/1`` clauses and a bare-exported ``p/2``,
    calling ``p/2`` raises an arity mismatch, so ``p/2`` is not a thing to
    suggest (roborev on F4).

    1. a ``PredicateMeta`` class -> ``{len(cls._fields)}`` (the arity the
       name is bound at -- the old reader's answer, kept so nothing it
       answered is lost: a module not in ``sys.modules``, a partial load,
       ``term_expansion/4``, which no db records) UNION the owner db's
       defined arities for ``cls.__name__`` (a ``-dynamic(p/1, p/2)`` name
       binds one class but is defined at both).
    2. a mangled atom whose module half is a loaded Clausal module -> the
       owner db's defined arities; if there are NONE, its declared arities
       instead.  The fallback is the mangled twin of arm 1's ``_fields``: a
       name that exists here only as a declaration (a bare-exported
       ``p/1`` with no clauses, an adopted row) is bound as a class at that
       arity today, so the class era answers it, and the mangled era must
       too.  It never ADDS a declared arity beside a defined one.
    3. anything else (a ``@dataclass`` class, a plain string, ``None``, an
       unloaded owner, an arbitrary object) -> ``set()``.

    *cache*, when given, is a dict owned by the caller and kept for one
    batch of questions (one diagnostic): it memoises each db's
    ``arity_maps()`` so a namespace sweep is O(bindings + keys), not
    O(bindings x keys).  Do not keep it across database mutations.
    """
    if isinstance(binding, PredicateMeta):
        found: set[int] = set()
        fields = getattr(binding, "_fields", None)
        if fields is not None:
            found.add(len(fields))
        owner = predicate_owner_module(binding)
        # The caller's db first (Q0), exactly as the mangled arm does, so the
        # two eras agree under the same hint when the owner was popped.
        owner_db = _owner_db_for_module_name(owner, db) if owner else None
        if owner_db is not None:
            defined, _declared = _arity_maps(owner_db, cache)
            found |= defined.get(binding.__name__, set())
        return found
    from clausal.logic.atoms import is_mangled  # noqa: PLC0415
    if is_mangled(binding):
        resolved = _resolve_mangled_owner(binding, db)
        if resolved is None:
            return set()
        db, functor = resolved
        defined, declared = _arity_maps(db, cache)
        return set(defined.get(functor) or declared.get(functor) or ())
    return set()


def _arity_maps(db, cache):
    if cache is None:
        return db.arity_maps()
    key = id(db)
    hit = cache.get(key)
    if hit is None or hit[0] is not db:
        hit = cache[key] = (db, db.arity_maps())
    return hit[1]


def field_names_for(value, *, arity=None, db=None, namespace=None):
    """Field names for a declared functor, or None.

    A FIELD-NAMES reader, not a declaredness one (revised 2026-09-23,
    todo/dynamic-declarations-are-invisible-to-arm-3-2026-09-22.md -- the
    previous wording here claimed the opposite and was wrong for an
    arity-only declaration; see below).  ``None`` means no field names are
    known for *value* -- either because nothing is declared, OR because it
    IS declared but at an arity with no names anywhere (``-dynamic(f/2)``,
    or a bare ``f/2`` entry in a ``-module``/``-private`` export list: both
    register an arity and never field names, on the class's own
    ``PredicateMeta._fields`` -- synthesized placeholders -- and nowhere
    else).  ``()`` means declared with ZERO fields (the 0-arity predicate
    written ``p()``), and ``len()`` is the arity for anything longer.  For
    "is this declared" -- a question this accessor deliberately does NOT
    answer, because for an arity-only declaration it has no way to -- ask
    ``db.declared_kind(functor, arity)`` instead; it already answers
    ``"predicate"`` for both spellings above (``Database.mark_dynamic`` /
    ``mark_predicate_export``), independent of whether any field names are
    known.  The compiler's dominant use of the signature registry is the
    presence test ("a declared functor, or an atom being applied as one?"),
    which never reads a name -- see the spec's premise check.

    Four arms, in order:

    1. a ``@dataclass`` class -> its declared field names.  Permanent.
    2. a ``PredicateMeta`` class -> ``cls._fields``.  DELETED AT W4b-3; it is
       the legacy answer and the census in ``tools/w4b1_census`` measures
       whether arm 3 agrees with it everywhere.
    3. a NAME (``str``, plain or mangled) -> the registry chain below.
       Permanent, and the point of the change: at W4b-2 a module attribute
       for a predicate becomes a mangled atom, and this arm already answers.
       NO builtin-registry fallback (removed W4b-1 fix round 1): a bare
       string that spells a registered builtin name is an ordinary ATOM,
       not a declared functor, and answers ``None`` here.
    4. anything else -> ``None``.
    """
    if isinstance(value, str):
        return _field_names_for_name(value, arity, db, namespace)
    if not isinstance(value, type):
        return None
    if isinstance(value, PredicateMeta):
        return value._fields
    if dataclasses.is_dataclass(value):
        return tuple(f.name for f in dataclasses.fields(value))
    return None


def _field_names_for_name(name, arity, db, namespace):
    """Arm 3.  Demangle -> exact db read -> by-name db read -> the
    namespace's exec-time carrier -> None.

    A MANGLED name is module-qualified by construction, so it is handled
    entirely by the branch below and returns from it -- it never reaches
    the shared tail.  ``namespace`` is a bare-name carrier: letting it
    answer for a mangled name would silently un-qualify the handle, so
    once a name demangles, the OWNER's db is the sole authority for it.
    If the owner module isn't loaded, or is loaded but doesn't know the
    name, the answer is None -- never a fallthrough to the caller's
    namespace.

    NO builtin-registry fallback (removed W4b-1 fix round 1): a bare name
    that happens to spell a registered builtin -- ``'when'``, ``'freeze'``,
    ``'call_nth'`` -- is an ordinary ATOM, not a declared functor, and must
    answer ``None`` here.  See the comment at the tail of this function for
    the full defect this caused before the fallback was removed."""
    from clausal.logic.atoms import demangle, is_mangled  # noqa: PLC0415
    if is_mangled(name):
        # A handle carries its module: resolve against the OWNER's db,
        # never the caller's -- a name declared in both answers for the
        # wrong one -- and never fall through past this branch either.
        module_name, bare_name = demangle(name)
        owner_db = _db_for_module_name(module_name)
        if owner_db is None:
            return None
        if arity is not None:
            return owner_db.signature_for(bare_name, arity)
        return owner_db.declared_fields_by_name(bare_name)
    if db is not None:
        if arity is not None:
            found = db.signature_for(name, arity)
            if found is not None:
                return found
        else:
            # ``signature_for`` needs an arity; the by-name read is the only
            # thing that can answer without one, and it resolves a two-arity
            # name to the LAST declaration (database.py:1010).
            found = db.declared_fields_by_name(name)
            if found is not None:
                return found
    if namespace is not None:
        from clausal.logic.cells import FUNCTOR_SIGNATURES_KEY  # noqa: PLC0415
        found = (namespace.get(FUNCTOR_SIGNATURES_KEY) or {}).get(name)
        if found is not None:
            return tuple(found)
    # NO ``_BUILTIN_FIELDS`` FALLBACK (removed W4b-1 fix round 1, review
    # finding): a bare string that happens to spell a registered builtin
    # name -- ``'when'``, ``'freeze'``, ``'call_nth'`` -- is an ordinary
    # ATOM everywhere outside the registry, not a declared functor, and
    # post atoms-as-str a bare string reaches this accessor constantly.
    # Answering builtin fields for it here made an atom look declared,
    # which crashed or silently mis-shaped five independent call sites the
    # moment they were migrated onto this accessor (``functor(T, when,
    # 2)`` raised ``TypeError: 'str' object is not callable`` building
    # ``when(...)``; ``_is_const_element('when')`` flipped to ``False``;
    # ``_cell_slot_names('when', 2, ns)`` answered ``('condition',
    # 'goal')`` instead of ``()``) -- five sites tripping on the same
    # fallback is the accessor's defect, not five call-site bugs. This
    # fallback had zero production callers: builtins are minted detached
    # on purpose, with no db/namespace entry to be found here by design. A
    # caller that specifically wants a builtin's field names should ask
    # the builtin registry directly (``clausal.logic.builtins.
    # _BUILTIN_FIELDS``), not this accessor -- do not re-add this branch.
    return None


def term_field_names_of_class(cls: Any) -> tuple[str, ...] | None:
    """Field names for a term CLASS, or None.

    RETAINED ALIAS (W4b-1): ``field_names_for`` is the accessor now.  This
    name is in ``__all__`` and out-of-tree callers use it, so it survives
    until W4b-3 retires it with the class.  A ``str`` reaching here would
    take arm 3 with no db and no namespace, which is the same ``None`` the
    old class-only implementation gave -- no caller changes behaviour.
    """
    return field_names_for(cls)


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
    """True iff *obj* is an atom VALUE — STAGE 2 of the atoms-as-str flip: an
    atom IS the Python ``str`` (``clausal.logic.atoms.is_atom``), the chars
    carrier is a STRING and no class is an atom (spec §4).

    This helper used to WIDEN the term test with the zero-field
    ``PredicateMeta`` class (the declared-atom form of the cell era); that
    widening is retired, and the two are one question now.  It stays as the
    name the runtime readers (``atom/1``, ``functor_arity``) call, so a future
    widening has one place to land.  ``predicate.is_zero_field_class`` above
    remains the separate CLASS question the compiler keys on.
    """
    from clausal.logic.atoms import is_atom as _term_is_atom
    return _term_is_atom(obj)          # STAGE 2 (spec §4): no class is an atom


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


# Install the raising tombstones for the facades W2 retired.  On the
# METACLASS, so `cls._clauses_source` -- where *cls* is a predicate class,
# i.e. an INSTANCE of this metaclass -- resolves to them.
for _retired_name, _retired_where in _RETIRED_STATE_NAMES.items():
    setattr(PredicateMeta, _retired_name,
            _make_retired_tombstone(
                _retired_name, _retired_where,
                wave=_RETIRED_STATE_WAVES.get(_retired_name,
                                              _DEFAULT_RETIRED_WAVE)))
del _retired_name, _retired_where


def make_predicate(name: str, fields: list[str], *,
                   instances: Any = _MISSING) -> "PredicateMeta":
    """Dynamically create a PredicateMeta class.

    Useful in tests and runtime code that needs a predicate without a
    module-level class definition::

        foo = make_predicate("foo", ["a", "b"])
        foo._assertz(Clause(head=foo(a=Var(), b=Var()), body=[...]))
        compile_predicate("foo", 2, foo._state_row().clauses, pred_cls=foo)
        fn = foo._get_dispatch()
    """
    if instances is not _MISSING:
        raise TypeError(
            "make_predicate() got `instances=`: that bridge was retired "
            "(W4a, 2026-09-22); a predicate class builds cells.  (The "
            "parameter is still declared so passing it says THIS, rather "
            "than the bare 'unexpected keyword argument' every other typo "
            "should get.)")
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


__all__ = ["PredicateMeta", "RetiredStateError", "_MISSING", "is_term_instance",
           "is_zero_field_class",
           # ``is_atom`` is the DEPRECATED alias of ``is_zero_field_class``
           # (Task 12); exported for one release so out-of-tree importers do
           # not break in the same commit that renames it.
           "is_atom",
           "is_atom_value",
           "term_field_names", "term_field_names_of_class", "field_names_for",
           "term_field_values", "term_field_dict",
           "make_predicate", "make_atom",
           "resolve_predicate_row", "is_declared_predicate",
           "is_declared_predicate_name", "predicate_arities_for",
           "mint_predicate_handle", "namespace_db",
           "predicate_owner_module"]
