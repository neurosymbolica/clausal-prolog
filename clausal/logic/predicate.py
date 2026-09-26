"""clausal.logic.predicate — predicates as Database rows named by handles.

A predicate is a row in its module's ``Database`` (``clausal.logic.database``);
a module binds the predicate's name to its HANDLE, the module-qualified
mangled atom ``mint_predicate_handle`` spells.  This module holds what the
rest of the engine asks about predicate bindings and terms: term construction
against a registered signature (``build_term_cell``, ``head_cell`` for a
module body's clause heads), the era-agnostic resolvers (``resolve_predicate_row``,
``is_declared_predicate``, ``is_declared_predicate_name``,
``predicate_arities_for``, ``field_names_for``), handle ownership
(``register_handle_owner``, ``namespace_db``) and ``_dispatch_at``.

The ``PredicateMeta`` metaclass that made a predicate a Python CLASS was
deleted at W4b-3 slice 7 (2026-09-26); ``make_predicate`` stays as a stub
that raises ``MakePredicateRetiredError``.
"""

from __future__ import annotations

import dataclasses
import os
import re
import sys
import textwrap
from typing import Any, Callable, NoReturn

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


class AmbiguousArityConstructionError(ClausalTermConstructionError):
    """A term was built against a name registered at SEVERAL arities, and
    the arguments fit none of them, or more than one.

    ``arity`` and ``registered_fields`` are ``None`` -- there is no single
    registration to report, and ``()`` would read as a 0-field one.  The
    candidates are in ``signatures``, ``{arity: field names}``.
    """

    def __init__(
        self,
        message: str,
        *,
        functor: str,
        signatures: "dict[int, tuple[str, ...]]",
        supplied_fields: tuple[str, ...],
        constructed_at: tuple[str, int] | None,
    ) -> None:
        super().__init__(
            message, functor=functor, arity=None,
            supplied_fields=supplied_fields, registered_fields=None,
            registered_at=None, constructed_at=constructed_at)
        self.signatures = dict(signatures)


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


def term_arity_error_for(
    functor: str, registered: tuple[str, ...], registered_at: Any,
    n_args: int, kwargs: dict, constructed_at: tuple[str, int] | None,
) -> ClausalTermConstructionError:
    """The attributable positional-overflow error, from plain data -- the
    arity half of :func:`build_term_cell`, for a builder that has a functor
    and its registered fields but no class (a predicate HANDLE's head).

    ``PredicateMeta.__call__`` used to *drop* positional arguments past
    ``len(_fields)``, so ``some_atom(A, B)`` on a zero-arity class returned a
    silently wrong term.  That is worse than the keyword path's bare
    ``TypeError``: there is no exception at all to repair against.
    """
    registered = tuple(registered)
    supplied = _overflow_supplied_fields(registered, n_args) + tuple(
        k for k in kwargs if k not in registered[:n_args]
    )
    named = [k for k in kwargs if k in registered]
    message = (
        f"functor {functor}/{len(registered)} was constructed with {n_args} "
        f"positional argument(s)"
        + (f" and field names {_format_fields(tuple(named))}" if named else "")
        + "\n"
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


def construction_arity_fault(fields: tuple[str, ...], n_positional: int,
                             keyword_names) -> "str | None":
    """THE too-few/too-many decision for a construction against a registered
    signature (ruling C, 2026-09-24; operator Q1 2026-09-25: "refuse too
    few").  Answers ``"too_many"``, ``"too_few"`` or ``None``.

    * more positional arguments than *fields* -> ``"too_many"``;
    * some slot past the positional arguments that no name in
      *keyword_names* fills -> ``"too_few"``: no silent fresh-Var padding.
      That includes KEYWORD-ONLY construction that names only some slots,
      and a construction with no arguments at all against a signature that
      has fields (operator ruling 2026-09-25, "let's not auto-correct
      arity"; it used to pad every unnamed slot with a fresh ``Var``);
    * otherwise ``None``.

    Pure data in, nothing raised, so every site shares the DECISION and keeps
    its own error: :func:`build_term_cell` (runtime: the class call, and a
    handle's head through :func:`head_cell`) raises
    :func:`term_arity_error_for`; the compiler's ``_place_signature_slots``
    (compile time, placing AST nodes) raises a ``SyntaxError``; and the
    compiler's written-arity re-ask (``construction_signature_for_name``)
    reads ``"too_few"`` as "a predicate NAME written at a shorter arity".
    """
    n_fields = len(fields)
    if n_positional > n_fields:
        return "too_many"
    if n_positional < n_fields and not all(
            f in keyword_names for f in fields[n_positional:]):
        return "too_few"
    return None


def build_term_cell(functor: str, fields: tuple[str, ...], args: tuple,
                    kwargs: dict, *, origin: Any = None,
                    site: Any = None) -> tuple:
    """THE one home of term construction against a registered signature:
    place *args* and *kwargs* into *fields* and build the cell
    ``(functor, slot, ...)``, with the head/term ARITY check.

    Era-agnostic by construction: ``PredicateMeta.__call__`` (a class
    binding, today) and :func:`head_cell` (a predicate HANDLE, after the
    flip) both come here, so the two eras answer the same cell and raise the
    same error for the same (functor, fields, args, kwargs).

    * more positional arguments than fields, or FEWER with the rest not all
      named by keyword (ruling C, 2026-09-24: no silent padding) ->
      :func:`term_arity_error_for` -- the decision is
      :func:`construction_arity_fault`, the one the compiler asks too;
    * a keyword naming no field -> :func:`term_construction_error_for`;
    * a slot neither fills -- keyword-only construction naming only some
      slots, or no arguments at all -- is the too-few refusal as well
      (operator ruling 2026-09-25); nothing is padded with a fresh ``Var``.

    *origin* is the class being called, if any: its ``_registered_at``
    (the declaration site) is read only when an error is raised, keeping it
    off the construction hot path.  A HANDLE has no origin; its caller passes
    the owner row's ``declared_at`` as *site* instead.

    *kwargs* is consumed (positional fills are written into it, which is
    what the construction error reports as the supplied fields).  The
    "constructed at" site search starts at the CALLER'S caller (frame 2),
    exactly where ``PredicateMeta.__call__``'s own search started.
    """
    # Positional overflow used to be DROPPED (``if i < len(fields)``), so a
    # call with too many arguments returned a wrong term instead of raising.
    # Ruling C (2026-09-24) refuses too FEW the same way: a registered
    # signature is ONE arity; the compound at another arity is built by name
    # (``(name, *args)``), not against it.  Asked for EVERY construction, not
    # only one with positional arguments (operator ruling 2026-09-25): a
    # keyword-only construction naming some slots, and one with no arguments
    # at all, are refused too -- they used to be padded with fresh Vars.  The
    # decision is :func:`construction_arity_fault`, shared with the compiler.
    # A keyword naming no field at all is that error first when there are no
    # positional arguments (its message names the stray field), exactly as it
    # was before keyword-only construction was checked for arity.
    if not args and any(k not in fields for k in kwargs):
        raise term_construction_error_for(
            functor, tuple(fields), getattr(origin, "_registered_at", site),
            kwargs, _source_site(2))
    if construction_arity_fault(fields, len(args), kwargs):
        raise term_arity_error_for(
            functor, fields, getattr(origin, "_registered_at", site),
            len(args), kwargs, _source_site(2))
    if args:
        # A keyword naming a slot a POSITIONAL argument already fills used
        # to be overwritten by it here -- the keyword's value dropped
        # silently, and the slot the arguments were meant to reach left
        # unfilled and padded with a fresh ``Var`` (W4b-3, the no-padding
        # audit, 2026-09-25).  Python's own "multiple values" refusal.
        doubled = [fields[i] for i in range(len(args)) if fields[i] in kwargs]
        if doubled:
            registered_at = getattr(origin, "_registered_at", site)
            constructed_at = _source_site(2)
            raise ClausalTermConstructionError(
                f"functor {functor}/{len(fields)} was constructed with "
                f"field(s) {_format_fields(tuple(doubled))} given both "
                f"positionally and by name\n"
                f"  registered by: {_format_site(registered_at)}\n"
                f"  constructed at: {_format_site(constructed_at)}",
                functor=functor, arity=len(fields),
                supplied_fields=tuple(kwargs), registered_fields=tuple(fields),
                registered_at=registered_at, constructed_at=constructed_at)
        for i, val in enumerate(args):
            kwargs[fields[i]] = val
    unknown = [k for k in kwargs if k not in fields]
    if unknown:
        raise term_construction_error_for(
            functor, tuple(fields), getattr(origin, "_registered_at", site),
            kwargs, _source_site(2))
    from clausal.logic.variables import Var  # noqa: PLC0415
    return (functor, *(kwargs[f] if f in kwargs else Var() for f in fields))


def _head_arity(head: Any) -> int | None:
    """How many arguments the clause head *head* has, or ``None`` if unreadable.

    The head shapes that reach here:

    - an atom (a ``str``), which is how a 0-arity fact (``myflag,``) stores
      its head -- name/0;
    - a cell ``(functor, *args)``;
    - a ``Compound``-style head with an ``args`` sequence;
    - a term instance, whose arity is its field count.

    (A zero-field ``PredicateMeta`` class was a fourth, answered from its
    ``_fields``, until W4b-3 slice 7 deleted the class.)

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
    if type(head) is str:
        # STAGE 2: an atom head is name/0 (``database.head_key`` agrees).
        # Since W4b-3 slice 5 this is how a module's own 0-arity fact
        # (``myflag,``) stores its head -- the atom, where it used to be the
        # rewriter's zero-field class (answered from its ``_fields`` until
        # W4b-3 slice 7 deleted the class).
        return 0
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


class RetiredStateError(Exception):
    """What a retired facade's tombstone raised, on read and on write.

    The tombstones lived on the ``PredicateMeta`` metaclass and went with it
    (W4b-3 slice 7); the exception class stays because it is public (in
    ``__all__``) and a caller may still ``except`` it.  Its history:

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
    raise predicate_arity_mismatch(functor, arity, defined,
                                   site=_row_declared_at(db, functor, defined))


def _row_declared_at(db, functor: str, arity) -> "tuple[str, int] | None":
    """The declaration site recorded on *db*'s row for ``functor/arity``
    (``PredRow.declared_at``), or ``None`` -- for a diagnostic's "defined
    at" line when the binding is a handle and there is no class to ask
    (W4b-2d R6).  Never raises: it only feeds a message."""
    if db is None or not isinstance(arity, int):
        return None
    try:
        row = db.row(functor, arity)
    except Exception:  # noqa: BLE001 - a message, not a decision
        return None
    return row.declared_at if row is not None else None


def _binding_owner_db(binding: Any, db: Any = None):
    """The Database that OWNS a predicate *binding* (class or handle), or
    ``None`` -- a class's row db, a handle's module db.  *db* is the caller's
    (ruling Q0): it resolves a handle to a popped owner, locally or by
    identity through the caller's imports.  A question, not a dispatch, so
    an ambiguous owner answers ``None`` (``_owner_db_or_none``)."""
    if type(binding) is str:
        from clausal.logic.atoms import is_mangled, demangle  # noqa: PLC0415
        if is_mangled(binding):
            # A handle: resolved as a handle (registry included), never as
            # a user-written module name.
            return _owner_db_or_none(demangle(binding)[0], db)
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
    owner = _binding_owner_db(binding, db)
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

    (A class-era exception -- a LOCAL class with stale ``_fields`` whose
    clause heads were at *arity* -- went with the class at W4b-3 slice 7.)
    """
    from clausal.predicate_diagnostics import (  # noqa: PLC0415
        PredicateArityMismatchError, predicate_arity_mismatch,
    )
    defined = None
    site = None
    # A diagnostic: the handle's owner (with the caller's db as the Q0
    # hint) only sharpens the message, so an ambiguous owner is "unknown".
    from clausal.logic.atoms import demangle, is_mangled  # noqa: PLC0415
    if type(binding) is str and is_mangled(binding):
        _mod_name, _bare = demangle(binding)
        owner = _owner_db_or_none(_mod_name, db)
        if owner is not None:
            others = sorted(a for a in owner.arities_for(_bare) if a != arity)
            defined = others[0] if len(others) == 1 else None
            # The class arm's "defined at" line, from the ROW (W4b-2d R6):
            # only under the owner's own name, as there.
            if name == _bare:
                site = _row_declared_at(owner, _bare, defined)
    raise predicate_arity_mismatch(name, arity, defined, site=site)


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
            # Q0 (round-3 review): the calling db is the hint here too --
            # the same one ``binding_grants_arity`` was just given.
            return _dispatch_at(self.binding, arity, db=self.db)
        fn = self.db.get_dispatch(self.name, arity)
        if fn is not None:
            return fn
        return _refuse_unqualified_other_arity(
            self.binding, self.name, arity, self.db)

    def _get_dispatch(self):
        # The frozen arity-free protocol: a handle needs the call arity (only
        # a class knew its own, and the class is gone -- W4b-3 slice 7).
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
    through it carries, whatever local spelling bound it.  Only ever a
    HANDLE: ``_import_index`` indexes handles only (W4b-3 slice 2), and its
    entries are the only way here."""
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
        # HANDLES only.  A ``PredicateMeta`` class arm stood here; after the
        # flip no load leaves a class bound in a module dict (every one is
        # flipped, or refused at load since W4b-3 slice 1), and the census
        # measured it never true (0 of 65,787).  Deleted W4b-3 slice 2.
        if not (type(v) is str and _is_mangled_fast(v)):
            continue
        if not is_declared_predicate_name(v, db=db):
            continue
        owner = _binding_owner_db(v, db)
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
    if not (type(goal_val) is str and _is_mangled_fast(goal_val)):
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


def _atom_goal_message(name: str, arity: int, db: Any) -> str:
    """The message for an ATOM called as a goal at *arity*.

    The ISO term is ``existence_error(procedure, name/arity)`` whatever this
    says; this is only its message.  When *name*/*arity* is declared as DATA
    (ruling R6/R6b: a field-carrying entry declares a term constructor) the
    message names the declaration by its SOURCE -- this file's -module or
    -private entry, or the OWNER module's export entry for an import (under
    the owner's spelling: an aliased import calls the owner's atom) -- and
    the ``name/arity`` spelling that declares a procedure instead.  *db* may
    be a name-only shim or ``None``; anything that cannot answer gets the
    general message."""
    origins_of = getattr(db, "declaration_origins", None)
    origins = origins_of(name, arity) if origins_of is not None else []
    pi = f"{name}/{arity}"

    def _entry(spelling, fields):
        return f"{spelling}({', '.join(str(f) for f in fields)})"

    if len(origins) == 1:
        kind, module, spelling, fields = origins[0]
        entry = _entry(spelling, fields)
        where = f" in {module}" if module else ""
        if kind == "module":
            return (
                f"{pi} is declared as DATA, not as a procedure: the -module "
                f"export entry {entry}{where} declares a term constructor, "
                f"and it has no clauses to call.  To export a procedure with "
                f"no clauses, write {pi} in that export list instead; to "
                f"call it here, define its clauses")
        if kind == "private":
            return (
                f"{pi} is declared as DATA, not as a procedure: the -private "
                f"entry {entry}{where} declares a term constructor, and it "
                f"has no clauses to call.  To declare a procedure, write "
                f"{pi} in that -private list instead; to call it here, "
                f"define its clauses")
        return (
            f"{pi} is declared as DATA, not as a procedure: it is imported "
            f"from {module}, whose export entry {entry} declares a term "
            f"constructor, and it has no clauses to call.  For {module} to "
            f"export a procedure, its export list writes "
            f"{spelling}/{arity} instead, and its clauses are defined there "
            f"or asserted with -dynamic")
    if origins:
        owners = "; ".join(f"{module} (export entry {_entry(spelling, fields)})"
                           for _k, module, spelling, fields in origins)
        return (
            f"{pi} is declared as DATA, not as a procedure: it is imported, "
            f"under aliases of the same spelling, from {owners}, and a call "
            f"through any of them reaches {pi}, which has no clauses.  For an "
            f"owner to export a procedure, its export list writes {pi} "
            f"instead")
    declared_kind = getattr(db, "declared_kind", None)
    if declared_kind is not None and declared_kind(name, arity) == "data":
        return (f"{pi} is declared as DATA (a term constructor), not as a "
                f"procedure, and it has no clauses to call")
    return (f"atom {name!r} is not callable at arity {arity} "
            f"(resolved via a data reference; define or import the "
            f"predicate, or call it by its local name)")


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

    So the arity stops here.  A Clausal predicate is a HANDLE (a mangled
    ``str``), resolved at the call arity against its owner's rows below; a
    foreign implementor is called the way it was always called.  (The one
    arity-aware implementor, the ``PredicateMeta`` class, went at W4b-3
    slice 7.)  Do not add an ``arity`` parameter to another
    ``_get_dispatch``; add the case here.

    Off the hot path by construction: locked predicates (the default) have their
    dispatch function pre-cached in ``base_globals`` under ``$disp_<name>_<n>``
    and the goal emitters reference that name directly, so only unlocked
    (``-dynamic``) callees and the runtime meta-call funnels arrive here.
    """
    if type(obj) is _UnqualifiedName:
        # Operator ruling 2026-09-24: a meta-call goal that arrived as an
        # unqualified name resolves under THAT name in the calling module.
        return obj.dispatch_at(arity)
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
            #
            # Ruling Q0 (final): the OWNER is found by the handle-only rule
            # (``_owner_db_for_module_name``: the caller's db, then by
            # identity, then ``sys.modules``, then the handle-owner
            # registry) -- never by ``resolve_module``, which answers a name
            # a user WROTE and so must miss an owner the ``.clausal`` runner
            # popped from ``sys.modules``.
            from clausal.logic.atoms import demangle  # noqa: PLC0415
            _mod_name, _name = demangle(obj)
            _hdb = _owner_db_for_module_name(_mod_name, db)
            _hmd = _hdb.module_dict if isinstance(
                getattr(_hdb, "module_dict", None), dict) else None
            # F7 (ruled 2026-09-24): the arity check runs BEFORE
            # ``Database.get_dispatch``'s builtin-registry fallback.
            # ``get_dispatch`` falls back to a same-named builtin keyed
            # ``(functor, arity)`` when the handle's own module has no
            # dispatch entry at THIS arity -- and a user predicate wrong-
            # arity call is exactly that shape (no entry at the call arity,
            # an entry at its own).  Without this check first, deleting the
            # old arity-aware ``_get_dispatch(arity)`` class arm (the
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
                dangling_handle_indicator_and_why,
            )
            from clausal.predicate_diagnostics import (  # noqa: PLC0415
                PredicateNotFoundError,
            )
            # Ruling 2026-09-24 (todo/mangled-goal-culprit-terms-are-
            # malformed-2026-09-23.md): the culprit is the bare Name/Arity
            # indicator -- never a module-qualified compound -- with the
            # module named in the message only, matching the other two
            # entry points (solve's normalisation, call/N) so a ``catch/3``
            # pattern against a dangling handle is the same shape wherever
            # it is written.
            #
            # Ruling 2026-09-25: raised as ``PredicateNotFoundError`` -- the
            # SAME ISO term, now also the ``KeyError`` an unqualified unknown
            # call raises, so one condition has one Python type.
            _indicator, why = dangling_handle_indicator_and_why(
                _mod_name, _name, arity, loaded=True,
            )
            raise PredicateNotFoundError(
                f"{why} (reached through a module-qualified handle)",
                _name, arity)
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
            # Raised as ``PredicateNotFoundError`` (ruling 2026-09-25): the
            # same ISO term, and the unqualified unknown call's Python type.
            from clausal.predicate_diagnostics import (  # noqa: PLC0415
                PredicateNotFoundError,
            )
            _mod_name, _name = demangle(obj)
            _indicator, why = dangling_handle_indicator_and_why(
                _mod_name, _name, arity, loaded=False,
            )
            raise PredicateNotFoundError(why, _name, arity)
        name = obj
        indicator = Compound("/", (name, arity))
        raise LogicException(
            existence_error(
                "procedure", indicator,
                _atom_goal_message(name, arity, db),
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
    """True if obj is a zero-arity ``PredicateMeta`` CLASS -- always False
    since W4b-3 slice 7 deleted the class.  The name stays (it is public, and
    documented) so an out-of-tree caller's question still has an answer; no
    object is such a class any more.  ``clausal.logic.atoms.is_atom`` is the
    ATOM test."""
    return False


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


def _owner_db_for_module_name(module_name: str, db=None, *,
                              question: bool = False):
    """The Database that owns the predicates a HANDLE whose module half is
    *module_name* names, or ``None``.  HANDLE RESOLUTION ONLY -- never call
    this for a module name a user WROTE (``M:G``, an import): those go
    through ``solve.resolve_module``, which is lookup-only in
    ``sys.modules`` and must stay so (``test_resolution_never_imports``).

    Ruling Q0 (operator, final, 2026-09-24), in order:

    1. the caller's own *db* when it IS that module -- the ``.clausal``
       runner pops loaded modules from ``sys.modules``;
    2. BY IDENTITY, the owner database the caller ADOPTED a row from under
       that module name at ``-import_from`` (``Database.adopted_owner_dbs``)
       -- the one database this caller actually imported, even when the name
       has since been reused;
    3. the module ``sys.modules`` holds under that name (today's rule);
    4. only then the handle-owner REGISTRY (``_registered_handle_owner``):
       the cross-module remainder, an owner popped from ``sys.modules``.

    Raises ``AmbiguousHandleOwnerError`` when step 2 or step 4 finds more
    than one live database under the name -- a handle's spelling cannot say
    which one it meant, and answering with either would be silently wrong.
    Only a DISPATCH calls this directly; a question (resolver, predicate
    test, diagnostic) calls ``_owner_db_or_none``, where ambiguity is
    "unknown" (*question* -- see ``_registered_handle_owner``).

    One home for the rule, shared by the resolvers,
    ``cells.qualify_mangled_goal`` and ``_dispatch_at``'s handle arm."""
    hint = _hint_db(db)
    if hint is not None:
        if module_name == hint.module_name():
            return hint
        adopted_owner_dbs = getattr(hint, "adopted_owner_dbs", None)
        adopted = adopted_owner_dbs(module_name) if adopted_owner_dbs else ()
        if len(adopted) == 1:
            return adopted[0]
        if len(adopted) > 1:
            raise AmbiguousHandleOwnerError(module_name, len(adopted),
                                            "imported by the calling module")
    found = _db_for_module_name(module_name)
    if found is not None:
        return found
    return _registered_handle_owner(module_name, question=question)


def _owner_db_or_none(module_name: str, db=None):
    """``_owner_db_for_module_name`` for a QUESTION (a predicate test, a
    resolver, a diagnostic): an ambiguous owner is "unknown" -- ``None`` --
    instead of a raise.  Policy: only an actual DISPATCH of a handle
    (``cells.qualify_mangled_goal``, ``_dispatch_at``'s handle arm) raises
    ``AmbiguousHandleOwnerError``; a question about a handle never does."""
    try:
        return _owner_db_for_module_name(module_name, db, question=True)
    except AmbiguousHandleOwnerError:
        return None


class AmbiguousHandleOwnerError(LookupError):
    """A predicate handle's module half names more than one LIVE database
    and nothing about the call site says which (ruling Q0, the name-reuse
    case: measured 24 of 579 ``load_clausal_module`` calls reused a module
    name while an earlier module under it was still alive).  Raised rather
    than answering with either one: a handle resolved into the wrong
    module's database runs the wrong clauses and says nothing."""

    def __init__(self, module_name: str, count: int, where: str):
        self.module_name = module_name
        self.count = count
        super().__init__(
            f"predicate handle names module {module_name!r}, which {count} "
            f"live databases answer to ({where}); a handle cannot say which "
            f"one it means, so it is refused rather than resolved into "
            f"either")


# The handle-owner REGISTRY (ruling Q0, the cross-module remainder):
# module name -> weak references to the Databases LOADED under that name.
# Consulted by ``_owner_db_for_module_name`` ONLY, after the caller's db and
# ``sys.modules`` -- never by ``solve.resolve_module`` (a user-written
# ``M:G``) or by import-by-name, so a popped module never becomes reachable
# by a name a user writes.  Filled by ``compile_module`` at the end of every
# load (``register_handle_owner``).  Weak: a dropped module leaves no entry
# (the reference callback prunes it, and an emptied name is deleted).
_HANDLE_OWNERS: "dict[str, list]" = {}

# module name -> the registry weakrefs (the ref OBJECTS, compared by
# identity) that were ALL still live right after ``_registered_handle_owner``
# ran the collector for that name.  A QUESTION about the same set skips the
# collection: a program that keeps asking about a truly ambiguous name pays
# one collection, not one per lookup.  A DISPATCH never consults it -- it
# is about to raise, the exceptional case, so it always collects first and
# its answer never depends on when the collector last ran.  Holding the
# ref objects (never the databases) keeps their identities from being
# reused; any change to the name's registrations -- a new load, or a reap,
# which also drops this entry -- gives a different set, and the next
# question collects again.  At most one entry per registered name.
_AMBIGUOUS_AFTER_COLLECT: "dict[str, tuple]" = {}


def _reap_handle_owner(module_name: str, ref) -> None:
    _AMBIGUOUS_AFTER_COLLECT.pop(module_name, None)
    refs = _HANDLE_OWNERS.get(module_name)
    if refs is None:
        return
    try:
        refs.remove(ref)
    except ValueError:
        pass
    if not refs:
        _HANDLE_OWNERS.pop(module_name, None)


def register_handle_owner(db) -> None:
    """Record *db* as a live owner for handles naming its module.  A db that
    names no module (``_hint_db`` refuses it, or ``<anonymous>``/
    ``<detached>``) owns no handle and is not recorded.  Idempotent."""
    import weakref  # noqa: PLC0415
    if _hint_db(db) is None:
        return
    module_name = db.module_name()
    if module_name in ("<anonymous>", "<detached>"):
        return
    refs = _HANDLE_OWNERS.setdefault(module_name, [])
    if any(r() is db for r in refs):
        return
    refs.append(weakref.ref(
        db, lambda ref, _n=module_name: _reap_handle_owner(_n, ref)))


def _live_handle_owners(module_name: str) -> list:
    # A SNAPSHOT: a collection during the walk runs ``_reap_handle_owner``,
    # which removes from the live list -- iterating it directly could skip a
    # live entry and report a truly ambiguous name as having one owner.
    return [d for d in (r() for r in tuple(_HANDLE_OWNERS.get(module_name, ())))
            if d is not None]


def _same_refs(remembered, refs) -> bool:
    return (remembered is not None and refs is not None
            and len(remembered) == len(refs)
            and all(a is b for a, b in zip(remembered, refs)))


def _registered_handle_owner(module_name: str, *, question: bool = False):
    """The ONE live database registered under *module_name*, ``None`` when
    there is none, ``AmbiguousHandleOwnerError`` when more than one is live.

    A module dropped by the runner is often still reachable only through a
    reference CYCLE (module dict -> ``$module`` -> db -> module dict), so a
    weak reference to it outlives the module until the cycle collector runs.
    Before calling a name ambiguous the collector is run once: only an owner
    something still REALLY holds counts.  Off the hot path -- reached only
    for a handle whose owner is neither the caller nor in ``sys.modules``,
    and the collection only when two candidates are left.  A *question*
    (answered ``None`` on ambiguity) collects at most once per candidate set
    (``_AMBIGUOUS_AFTER_COLLECT``), so an owner dropped into a cycle after
    its set was found ambiguous is seen by questions at the next natural
    collection (or dispatch); a DISPATCH collects every time before it
    raises, so it resolves to a survivor regardless of collector timing."""
    live = _live_handle_owners(module_name)
    if len(live) > 1 and not (question and _same_refs(
            _AMBIGUOUS_AFTER_COLLECT.get(module_name),
            _HANDLE_OWNERS.get(module_name))):
        import gc  # noqa: PLC0415
        del live
        gc.collect()
        live = _live_handle_owners(module_name)
        if len(live) > 1:
            _AMBIGUOUS_AFTER_COLLECT[module_name] = tuple(
                _HANDLE_OWNERS.get(module_name, ()))
    if not live:
        return None
    if len(live) == 1:
        return live[0]
    raise AmbiguousHandleOwnerError(
        module_name, len(live),
        "loaded under that name, none of them in sys.modules")


def handle_designator(module_name: str, owner):
    """The module designator a qualified goal built from a handle carries:
    the dotted NAME when ``sys.modules`` resolves it to *owner* (the pure-
    data spelling ``resolve_module`` looks up), else the owner's Module
    OBJECT -- so a handle whose owner was found by the caller's db, by
    identity or by the registry reaches ``resolve_module``'s object arm and
    never asks it to resolve a popped name (which it must not)."""
    if _db_for_module_name(module_name) is owner:
        return module_name
    md = owner.module_dict
    logic_module = md.get("$module") if isinstance(md, dict) else None
    if logic_module is not None and getattr(logic_module, "db", None) is owner:
        return logic_module
    # No real ``$module`` for this db: synthesise ONE Module per owner and
    # keep it on the db, so the designator is stable -- the query cache keys
    # on ``id(module)``, and a fresh wrapper per call would miss every time
    # and could reuse a freed wrapper's id for a different db.
    cached = owner.__dict__.get("_handle_module")
    if cached is None or cached.db is not owner:
        from clausal.logic.database import Module  # noqa: PLC0415
        cached = Module(module_name, db=owner, module_dict=md)
        owner.__dict__["_handle_module"] = cached
    return cached


def _resolve_mangled_owner(binding, db=None):
    """``(db, functor)`` for a mangled *binding* whose owner module is a
    LOADED Clausal module, or ``None``.

    *db*, when given, is the CALLER's own database, and it is asked first
    (ruling Q0, 2026-09-24): if the handle's module half is ``db``'s own
    module name the handle is local and resolves there, without touching
    ``sys.modules`` -- which the ``.clausal`` test runner empties of every
    module it loads (measured: the owner was absent from ``sys.modules`` in
    43 of 46 descents, all of them local).  A handle naming another module
    resolves by identity through the caller's imports, then
    ``sys.modules``, then the handle-owner registry (the popped
    cross-module remainder) -- see ``_owner_db_for_module_name``.

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
    # The resolvers built on this answer QUESTIONS (is it declared, which
    # row, which arities) -- an ambiguous owner is "unknown" there, never a
    # raise; only an actual dispatch raises (``qualify_mangled_goal``,
    # ``_dispatch_at``).
    owner = _owner_db_or_none(module_name, db)
    if owner is None:
        return None
    return owner, functor


def mint_predicate_handle(db, functor: str) -> str:
    """The module-qualified handle for *functor* as a predicate of *db*
    (ruling X3, 2026-09-24): ``mangle(db.module_name(), functor)``.

    Minted from the DATABASE, never from a class's ``__module__``: a
    ``make_predicate`` class carried the MINTER's module
    (``clausal.logic.predicate`` for 14 of 15 measured ``-specialize``
    targets, before W4b-3 retired both), and a handle naming a module with
    no Database resolves to nothing, silently.  A database with no module name cannot own a handle,
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
    """Is *binding* a predicate at *arity*?  :func:`is_declared_predicate`.

    It read the arity off a bound ``PredicateMeta`` class's row first (a
    class could be bound at an arity its ``_fields`` did not spell); the
    class went at W4b-3 slice 7, and a handle's arity IS its owner's row
    key, which ``is_declared_predicate`` reads.  Kept as the one arity
    source for the load channel's "is this the imported predicate?"
    question (``compiler_v2._implements_an_imported_declaration``)."""
    return is_declared_predicate(binding, arity=arity, db=db)


def resolve_predicate_row(binding, *, arity: int,
                          db=None) -> "PredRow | None":
    """F1: the live ``PredRow`` for a module-dict *binding* -- a predicate
    HANDLE, the module-qualified MANGLED ATOM a module binds (the
    ``PredicateMeta`` CLASS arm went at W4b-3 slice 7) -- the shape the 23
    F1-family call sites need (``._row``, ``.clauses``, ``.dispatch_fn``, ``.locked``, ``_lock()``, or a value handed to
    ``_install``/``analyze_mi``/a mutation gate's ``through=``), per
    ``implementation_plans/w4b2-open-questions-2026-09-23.md`` Q2.

    *arity* is REQUIRED and keyword-only: it is the ONLY source of arity -- never guessed via
    ``Database.arities_for`` or any other search.  A data atom misused in
    goal position arrives at a different arity than it was declared at, and
    the caller's own call site (a clause head, a goal, a directive target)
    already knows the arity it means, in both eras alike -- see hazard 3 in
    the W4b-2b brief.

    Two cases:

    1. ``binding`` is a mangled atom naming a loaded Clausal module's row at
       exactly *arity* -> that ``PredRow``.
    2. Anything else -- a ``@dataclass`` class, a plain non-mangled string
       (even one that happens to spell something -- hazard 1), a mangled
       atom whose module half is not a loaded Clausal module (unloaded, or
       a real Python module with no Clausal ``Database``, e.g. ``json``),
       ``None``, or an arbitrary object -> ``None``.  This function never
       widens past what W4b-1's own hazard already burned: "could a
       ``@dataclass`` class ever reach this, and would the True branch be
       wrong" is answered ``wrong`` for every one of these shapes.
    """
    from clausal.logic.atoms import is_mangled  # noqa: PLC0415
    if is_mangled(binding):
        resolved = _resolve_mangled_owner(binding, db)
        if resolved is None:
            return None
        db, functor = resolved
        return db.row(functor, arity)
    return None


def tabled_home_of(binding, *, arity: int, db) -> "tuple | None":
    """``(home_db, canonical_functor)`` when *binding* -- a module-dict
    binding in the module whose Database is *db* -- names a predicate that
    is tabled at *arity* in ANOTHER module's database; ``None`` otherwise.

    The cross-module tabled-NAF seam (``tabled_naf._resolve_tabled_call`` at
    compile time, ``tabling._naf_tabled`` at run time) asks this for an
    ``-import_from``'d callee: tabledness is recorded in the OWNING module's
    db, and an importer's own db knows nothing about it
    (todo/cross-module-tabled-naf-loses-wfs-delay.md).  It used to be
    answered by a ``_tabled_home_db`` stamp that ``Database.mark_tabled``
    put on the CLASS -- state that lived nowhere but the class, so once a
    binding is a mangled handle the seam went silently wrong: ``[]`` where
    WFS says ``Undefined``, and ``[True]`` when only the compile-time half
    was moved (the W4b-2d dry run, R6).  Both halves call this one function
    so they cannot disagree.

    The home is the database of the binding's ROW (``resolve_predicate_row``
    -- a class's ``_row``, a handle's owner row at *arity*): an importer
    reaches the owner's row by adoption, never a copy, so ``row.db`` IS the
    module that declared ``-table``.  The canonical spelling is the row's
    own functor, which is what the home db keys its tables, dispatch and
    signatures by (the compiled seam may hand in a dotted import spelling).
    Which arities are tabled stays the home db's answer (``is_tabled``).
    """
    row = resolve_predicate_row(binding, arity=arity, db=db)
    if row is None:
        return None
    home = row.db
    if home is db:
        return None
    canonical = row.key[0]
    if home.is_tabled(canonical, arity):
        return home, canonical
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

    Cases (a ``PredicateMeta`` CLASS arm -- ``len(_fields) == arity`` --
    stood first until W4b-3 slice 7 deleted the class; its history:
    ``len(binding._fields) ==
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
    loading = loading_head_fields(binding)
    if loading is not None:
        # A handle its LOADING module declared: answered as the rewriter's
        # class answered, from its field names (W4b-3 slice 5).
        return len(loading) == arity
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
    needs ``f`` back from the binding: the atom half of the handle's mangled
    spelling, which ``demangle`` reads directly (it was the class's
    ``__name__`` until the flip).

    Gated on :func:`is_declared_predicate_name`, so a mangled DATA atom, a
    plain string and a mangled atom naming an unloaded module all answer
    ``None`` rather than a name.
    """
    if not is_declared_predicate_name(binding, db=db):
        return None
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

    Cases (a ``PredicateMeta`` CLASS answered ``True`` unconditionally
    until W4b-3 slice 7 deleted the class):

    1. ``binding`` is a handle its LOADING module declared (W4b-3 slice 5)
       -> ``True``.
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
    if loading_head_fields(binding) is not None:
        return True      # declared by its LOADING module (W4b-3 slice 5)
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

    A mangled atom (a handle) answers its module half (after the flip a module attribute for a
    predicate is a mangled atom, and a ``str`` has no ``__module__`` -- a
    filter keyed on ``getattr(value, "__module__")`` then selects NOTHING).
    Anything else -> ``None``.  Does not require the owner to be loaded.
    """
    from clausal.logic.atoms import demangle, is_mangled  # noqa: PLC0415
    if is_mangled(binding):
        return demangle(binding)[0]
    return None


# ── W4b-3 slice 5: a predicate NAME is declared, not a class minted ────────

#: The module-namespace record of every predicate name the running module
#: body has declared (``$declare_head``): ``{functor: (fields, site)}``.
#: ``fields`` is what a head is built against while the body runs -- the
#: role the rewriter's class ``_fields`` played -- and ``site`` the
#: declaration's source position (the class's ``_registered_at``), which
#: ``compiler_v2`` step 4 stamps as ``row.declared_at``.  ``$``-keyed, so
#: no user name can collide with it and the flip's binding scan skips it.
PREDICATE_HEADS_KEY = "$predicate_heads"


def local_predicate_handle(namespace, functor: str) -> "str | None":
    """The handle *namespace*'s own module binds *functor* to: the value
    the module body's ``$declare_head`` binds for a local predicate
    (``mint_predicate_handle`` over the module's Database, whose
    ``module_name()`` is this same ``__name__``).  ``None`` for a namespace
    that names no module."""
    module_name = namespace.get("__name__")
    if not module_name:
        return None
    from clausal.logic.atoms import mangle  # noqa: PLC0415
    return mangle(module_name, functor)


def declared_head(namespace, binding) -> "tuple[str, tuple, Any] | None":
    """``(functor, fields, site)`` when *binding* is a predicate HANDLE the
    module body running in *namespace* declared with ``$declare_head``;
    ``None`` otherwise (an imported handle, an atom, any other value).

    The binding must still BE that module's handle for the name: a later
    ``-import_from`` or a user assignment over the name retires the
    declaration, exactly as rebinding the name retired the class."""
    if type(binding) is not str or not namespace:
        return None
    heads = namespace.get(PREDICATE_HEADS_KEY)
    if not heads:
        return None
    from clausal.logic.atoms import demangle, is_mangled  # noqa: PLC0415
    if not is_mangled(binding):
        return None
    functor = demangle(binding)[1]
    entry = heads.get(functor)
    if entry is None or binding != local_predicate_handle(namespace, functor):
        return None
    return functor, entry[0], entry[1]


def is_local_predicate_binding(namespace, name: str) -> bool:
    """True when *name* in *namespace* is bound to a predicate this module
    declared -- a local handle ``$declare_head`` bound.  The load path's
    "a predicate lives here" test (it was ``isinstance(module_dict.get(name),
    PredicateMeta)`` while a predicate was a class)."""
    return declared_head(namespace, namespace.get(name)) is not None


#: Module name -> namespace, for every module whose body has run under the
#: import hook and whose compile has not yet reached step 4a-bis.  See
#: :func:`loading_head_fields`.
_LOADING_NAMESPACES: dict = {}


def begin_loading_declarations(namespace: dict) -> None:
    """Start *namespace*'s ``$declare_head`` record for a module load (the
    import hook, right before the body runs).  A fresh record every run, so
    a body re-run into a namespace that already finished a load never reads
    the previous run's declarations as its own."""
    namespace[PREDICATE_HEADS_KEY] = {}
    name = namespace.get("__name__")
    if name:
        _LOADING_NAMESPACES[name] = namespace


def end_loading_declarations(namespace: dict) -> None:
    """Retire *namespace*'s ``$declare_head`` record: step 4a-bis of
    ``compiler_v2.compile_module``, from which the Database is the sole
    authority for the handles the load declared (step 4 gave each its row)
    -- and, on a failed load, the import hook's cleanup.  Idempotent."""
    namespace.pop(PREDICATE_HEADS_KEY, None)
    name = namespace.get("__name__")
    if name and _LOADING_NAMESPACES.get(name) is namespace:
        del _LOADING_NAMESPACES[name]


def loading_head_fields(binding) -> "tuple | None":
    """The field names a module that is still LOADING declared for the
    predicate HANDLE *binding* (``$declare_head``), or ``None``.

    The class the rewriter used to mint answered "a predicate at
    ``len(_fields)``, with these field names" from the moment the module
    body ran, before step 4 of ``compiler_v2.compile_module`` gave the
    Database a row to answer from -- goal expansion's auto-binding reads a
    head's names at step 1b, for one.  The declaration record answers the
    same question for the handle until step 4a-bis, where
    ``end_loading_declarations`` retires it and the Database is the sole
    authority.

    O(1) and allocation-free when no load is in progress: the resolvers
    that ask this sit on runtime paths too."""
    if not _LOADING_NAMESPACES or type(binding) is not str:
        return None
    from clausal.logic.atoms import HIDDEN_SEP  # noqa: PLC0415
    module_name, sep, _functor = binding.partition(HIDDEN_SEP)
    if not sep:
        return None
    namespace = _LOADING_NAMESPACES.get(module_name)
    if namespace is None:
        return None
    found = declared_head(namespace, binding)
    return found[1] if found is not None else None


def _declares_over(namespace, functor: str, fields: tuple) -> bool:
    """Whether ``$declare_head(functor, fields)`` (re)binds *functor* -- the
    guard the rewriter's class block spelled in Python, arm for arm:

    * the name is unbound in the MODULE dict (a Python builtin of the same
      spelling -- ``sorted``, ``reversed`` -- is not a user binding);
    * the name is bound to the runtime-table alias its ``$`` twin holds (the
      deprecation-window bare ``Var``, ``Sub``, ...);
    * the name is bound to THIS module's own handle and the recorded fields
      differ (the class era re-minted the class: a ``-dynamic`` placeholder
      unseated by a clause's head names), or none are recorded (a module
      body re-run into a namespace that already finished a load);
    * the name is bound to the pooled ATOM of its own spelling (an earlier
      module declared the atom; the predicate wins in the file that
      declares it -- Phenomenon A);
    * the name is an ALIASED import of a DATA functor (``alias(edge, e)``
      binds ``e`` to the atom ``edge``, and the -import_from put ``e`` in
      the functor-signature carrier).  Building the head from that atom
      raised ``TypeError: 'str' object is not callable``; binding the local
      handle instead lets the load reach ``compiler_v2``'s import/local
      clash check, which refuses it by name (ruling 2026-09-26).

    Anything else -- an imported handle, a user's own value -- is left
    alone, and the head is built from that binding as before."""
    if functor not in namespace:
        return True
    value = namespace[functor]
    from clausal.logic.generated_names import dollar_name, has_twin  # noqa: PLC0415
    if has_twin(functor) and value is namespace.get(dollar_name(functor)):
        return True
    if type(value) is not str:
        return False
    if value == functor:
        return True
    from clausal.logic.atoms import is_mangled  # noqa: PLC0415
    from clausal.logic.cells import FUNCTOR_SIGNATURES_KEY  # noqa: PLC0415
    if not is_mangled(value) and functor in (
            namespace.get(FUNCTOR_SIGNATURES_KEY) or {}):
        return True
    if value == local_predicate_handle(namespace, functor):
        entry = (namespace.get(PREDICATE_HEADS_KEY) or {}).get(functor)
        return entry is None or entry[0] != fields
    return False


def declare_head(functor: str, fields: tuple, /) -> None:
    """``$declare_head``: declare *functor* as a predicate of the module whose
    body is running, with *fields* as its head's field names (W4b-3 slice 5).

    The rewriter emits one statement per predicate name where it used to
    emit a guarded ``class <functor>(metaclass=$PredicateMeta)`` block, at
    the same position.  When :func:`_declares_over` says the name is this
    module's to bind, it binds the module's own predicate HANDLE -- the
    value the flip bound in place of the class at step 4a-bis -- and records
    ``(fields, site)`` under :data:`PREDICATE_HEADS_KEY` for the heads the
    body builds (:func:`head_cell`) and for step 4's ``declared_at`` stamp.
    Otherwise it changes nothing.

    The namespace is the CALLER's globals, read from frame 1 as
    :func:`head_cell` reads its home: only generated module-body code calls
    this."""
    namespace = sys._getframe(1).f_globals
    fields = tuple(fields)
    if not _declares_over(namespace, functor, fields):
        return
    handle = local_predicate_handle(namespace, functor)
    if handle is None:
        # A RUNTIME error: this is raised while a body runs, where a
        # ``SyntaxError`` would carry no filename or line to point at.
        raise RuntimeError(
            f"cannot declare the predicate {functor}: this namespace belongs "
            f"to no module (it has no usable __name__), and a predicate is "
            f"named by its module.  Define {functor} in a .clausal file and "
            f"import it, or run this code with a non-empty module-level "
            f"__name__")
    namespace.setdefault(PREDICATE_HEADS_KEY, {})[functor] = (
        fields, _source_site(1))
    namespace[functor] = handle


def keeps_predicate(name: str, /) -> bool:
    """``$keeps_predicate``: the guard of a ``-module``/``-private`` bare-atom
    line (``term_rewriting._make_atom_str_assign_ast``) -- True when *name*
    is already a predicate this module declared, which the atom must not
    clobber.  It tested ``isinstance(.., $PredicateMeta)`` while a predicate
    was a class."""
    return is_local_predicate_binding(sys._getframe(1).f_globals, name)


def head_cell(binding, /, *args: Any, **kwargs: Any) -> Any:
    """``$head``: build a clause HEAD for the predicate *binding* names,
    without calling the binding (W4b-2d task 5; the flip dry run's R4).

    The rewriter emits every module-level head as ``$head(<binding>, ...)``
    (``term_rewriting._head_ctor_ast``).  While a module body runs, a head
    naming a predicate -- an IMPORTED one included -- used to be built by
    calling the binding, ``binding(*args)``, i.e. ``PredicateMeta.__call__``.
    After the flip the binding is a predicate HANDLE (a mangled ``str``),
    so that call raised ``'str' object is not callable`` and the load died
    before the mutation gate could give its refusal.

    * anything that is not a mangled handle -> called exactly as before (``binding(*args, **kwargs)``): the
      same cell, the same ``ClausalTermConstructionError`` and the same
      message, byte for byte, and the same ``TypeError`` for a non-callable;
    * a predicate HANDLE -> :func:`_handle_head_cell`: the cell is built
      under the handle's PLAIN name (ruling S -- the class built it under
      ``cls.__name__``, the same spelling) from the field names the OWNER's
      Database records (``Database.head_signatures``: the row's signature
      -- after a clause, the head's derived names, the class's ``_fields``
      too -- else an arity-only declaration's ``arg_N`` placeholders, the
      class's ``_fields`` while no clause exists), through
      :func:`build_term_cell`, the helper the class uses -- so the arity
      check answers the same in both eras.

    A HANDLE naming ANOTHER module's predicate (an importer writing a clause
    for an imported name) DEFERS to the load gate (operator ruling
    2026-09-25): see :func:`_handle_head_cell`.  The executing module is
    read from the CALLER'S FRAME: ``$head`` is bound straight to this
    function in ``INJECTED_RUNTIME_BUILTINS`` and is called only by a module
    body's generated code, so frame 1's globals ARE that module's namespace.
    A caller that is not that code -- a wrapper, a ``functools.partial``, an
    eval with its own globals -- finds no ``$module`` there (or its own), so
    the head keeps its construction error: the failure mode is the error the
    head raised before deferral existed, never a silent accept.  Passing the
    namespace explicitly would change the ``$head(<binding>, ...)`` emission,
    which the reifier and the rewriter-output pins read.
    """
    if type(binding) is str:
        from clausal.logic.atoms import is_mangled  # noqa: PLC0415
        if is_mangled(binding):
            home = sys._getframe(1).f_globals
            declared = declared_head(home, binding)
            if declared is not None:
                # This module body's OWN predicate (``$declare_head``, W4b-3
                # slice 5): built against the field names its declaration
                # recorded -- exactly what the rewriter's class did with its
                # ``_fields`` -- and a construction error names the
                # declaration site the class's ``_registered_at`` held.  A
                # 0-arity head is the ATOM of its name, as for any handle.
                functor, fields, site = declared
                if not fields and not args and not kwargs:
                    return functor
                return build_term_cell(functor, fields, args, kwargs,
                                       site=site)
            return _handle_head_cell(binding, args, kwargs, home=home)
    return binding(*args, **kwargs)


def _handle_head_cell(handle: str, args: tuple, kwargs: dict,
                      home: "dict | None" = None) -> Any:
    """The HANDLE arm of :func:`head_cell`.

    *home* is the namespace of the module whose body builds the head.  When
    it is not the handle's owner, the head is an importer's clause for an
    imported predicate, which the load gate refuses ("defines a clause for
    gv_owned/1, which it -import_from's ...").  The rewriter
    spells such a head with field names derived from the IMPORTER's head
    (``gv_owned(teal)`` -> ``arg_0=teal``, ``gv_owned(COLOUR)`` ->
    ``colour=COLOUR``), in head order.  The class era built it against a
    local class re-minted with those names.  So a construction error against
    the OWNER's names does not speak for such a head: it is built at its
    written arity, in written order, and the gate gives the verdict.

    Only at an arity the OWNER knows: that is a clause for the imported
    predicate, which the gate refuses.  A head at another arity is the
    importer's OWN predicate (the name + arity ruling; see
    :func:`_foreign_head_verdict` and
    ``test_an_imported_head_at_a_new_arity_builds_the_importers_own_predicate``).
    A head in the owner's own module, or with no module to tell (*home*
    carries no ``$module``), keeps every construction error.

    INVARIANT: a deferred head never reaches a row.  Its positional build
    ignores the field names, which is right only because the gate refuses
    it.  So the key is recorded in *home*'s ``$deferred_heads``, and
    ``compiler_v2.compile_module`` raises if its step 3d permitted a load
    that would write one (``_refuse_unrefused_deferred_heads``).
    """
    from clausal.logic.atoms import demangle  # noqa: PLC0415
    try:
        return _owner_head_cell(handle, args, dict(kwargs))
    except ClausalTermConstructionError:
        verdict = _foreign_head_verdict(handle, home, len(args) + len(kwargs))
        if verdict is None:
            raise
    functor = demangle(handle)[1]
    written = (*args, *kwargs.values())
    if verdict == "local":
        # The name + ARITY ruling (operator, 2026-09-24): a local ``p/2``
        # beside an imported ``p/1`` LOADS -- a different predicate, this
        # module's own.  The class era got there by the rewriter's guard
        # re-minting a LOCAL class when the imported class's ``_fields`` did
        # not match the head (``_make_functor_class_ast``, retired at W4b-3
        # slice 5); after the flip
        # the binding is the owner's handle, the guard does not fire, and
        # the owner's one signature would refuse the head.  Built at the
        # written arity in written order -- the rewriter's field names for
        # this head, which step 4 stamps on the LOCAL row
        # (``HeadFieldNames``) -- and NOT recorded as deferred: no gate
        # refusal is owed, the row is this module's.
        #
        # "Written order" is safe for keyword arguments too: the only
        # keywords that reach a ``$head`` are the rewriter's own, derived
        # from the head (``arg_0=``, ``colour=COLOUR``) and emitted in HEAD
        # order.  A user-written keyword head (``p(b=1, a=2)``) is refused
        # by the rewriter before the body runs, in both eras
        # (``test_w4b2d_flip``: the keyword head and the differently-named
        # heads cases).
        return (functor, *written) if written else functor
    home.setdefault("$deferred_heads", set()).add((functor, len(written)))
    return (functor, *written) if written else functor


def _foreign_head_verdict(handle: str, home: "dict | None",
                          written: int) -> "str | None":
    """How :func:`_handle_head_cell` treats a head the owner's signature
    refused, from ONE owner resolution:

    * ``"defer"`` -- *home* is not the owner and the head is written at an
      arity the owner knows: an importer's clause for the imported
      predicate, which the load gate refuses;
    * ``"local"`` -- *home* is not the owner and the owner does not know
      the arity: the importer's OWN predicate (the name + arity ruling);
    * ``None`` -- the owner's own module, or no module to tell: keep the
      construction error.

    The owner is compared by DATABASE IDENTITY, with *home*'s db as the
    ruling-Q0 hint: ``_resolve_mangled_owner(handle, db=home_db)`` answers
    *home_db* itself for a handle naming *home*'s own module.  A handle names
    a module, not a load, so a handle minted by an EARLIER load under the same
    module name (the twin-reload case) is, by ruling Q0, this module's own:
    it keeps its construction error, exactly as a local handle does."""
    home_db = namespace_db(home) if home is not None else None
    if home_db is None:
        return None
    resolved = _resolve_mangled_owner(handle, db=home_db)
    if resolved is None or resolved[0] is home_db:
        return None
    if written in resolved[0].head_signatures(resolved[1]):
        return "defer"
    return "local"


def _defers_to_the_gate(handle: str, home: "dict | None", written: int) -> bool:
    """True when :func:`_foreign_head_verdict` answers ``"defer"``."""
    return _foreign_head_verdict(handle, home, written) == "defer"


def _owner_head_cell(handle: str, args: tuple, kwargs: dict) -> Any:
    """A handle's head built against the OWNER's registered field names."""
    from clausal.logic.atoms import demangle  # noqa: PLC0415
    functor = demangle(handle)[1]
    resolved = _resolve_mangled_owner(handle)
    signatures = resolved[0].head_signatures(resolved[1]) if resolved else {}
    if not signatures:
        raise TypeError(
            f"cannot build a clause head for {functor}: the predicate handle "
            f"{handle!r} names nothing its owner module "
            f"{demangle(handle)[0]!r} knows"
            + ("" if resolved else " (the module is not loaded)"))
    fields = _head_signature_for(functor, signatures, args, kwargs)
    if not fields and not args and not kwargs:
        # A 0-arity head is the ATOM of its name -- the class returned
        # ITSELF here (``red() is red``); post-flip the atom IS the str.
        return functor
    # The declaration SITE lives on the owner's row (``PredRow.declared_at``,
    # W4b-2d R6), so a handle's construction error names it the way the
    # class's ``_registered_at`` does.
    site = _row_declared_at(resolved[0], resolved[1], len(fields))
    return build_term_cell(functor, fields, args, kwargs, site=site)


def _head_signature_for(functor: str, signatures: dict, args: tuple,
                        kwargs: dict) -> tuple[str, ...]:
    """Which of the owner's ``{arity: fields}`` a head is built against.

    One known arity -> that one, whatever was written: exactly the class
    era, whose class carries ONE ``_fields`` (so an overflow or a stray
    keyword raises from ``build_term_cell`` with the class's message).
    Several (a name defined at more than one arity, ruling 2026-09-24) ->
    the arity as WRITTEN (positional + keyword count) when the keywords
    fit it; else the one arity the arguments fit; else a
    :class:`AmbiguousArityConstructionError` naming the arities, never a
    guess.
    """
    if len(signatures) == 1:
        return next(iter(signatures.values()))
    written = len(args) + len(kwargs)
    fits = sorted(a for a, names in signatures.items()
                  if len(args) <= a and all(k in names for k in kwargs))
    if written in fits:
        return signatures[written]
    if len(fits) == 1:
        return signatures[fits[0]]
    supplied = _overflow_supplied_fields((), len(args)) + tuple(kwargs)
    constructed_at = _source_site(1)
    known = ", ".join(f"{functor}/{a}" for a in sorted(signatures))
    message = (
        f"functor {functor} was constructed with {len(args)} positional "
        f"argument(s) and field names {_format_fields(tuple(kwargs))}\n"
        f"but it is registered at several arities ({known}), and "
        f"{'none' if not fits else 'more than one'} of them fits\n"
        f"  constructed at: {_format_site(constructed_at)}")
    raise AmbiguousArityConstructionError(
        message, functor=functor, signatures=signatures,
        supplied_fields=supplied, constructed_at=constructed_at)


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

    (A ``PredicateMeta`` CLASS arm -- ``{len(cls._fields)}`` UNION the
    owner's defined arities -- stood first until W4b-3 slice 7.)

    1. a mangled atom whose module half is a loaded Clausal module -> the
       owner db's defined arities; if there are NONE, its declared arities
       instead: a name that exists here only as a declaration (a
       bare-exported ``p/1`` with no clauses, an adopted row) was bound as a
       class at that arity, which answered it.  It never ADDS a declared
       arity beside a defined one.  A handle its LOADING module declared
       answers that declaration's arity too.
    2. anything else (a ``@dataclass`` class, a plain string, ``None``, an
       unloaded owner, an arbitrary object) -> ``set()``.

    *cache*, when given, is a dict owned by the caller and kept for one
    batch of questions (one diagnostic): it memoises each db's
    ``arity_maps()`` so a namespace sweep is O(bindings + keys), not
    O(bindings x keys).  Do not keep it across database mutations.
    """
    from clausal.logic.atoms import is_mangled  # noqa: PLC0415
    if is_mangled(binding):
        # Declared by its LOADING module (W4b-3 slice 5): what the class
        # arm answered -- the declared arity, UNION the defined ones when the owner
        # resolves.  Read FIRST, as ``is_declared_predicate[_name]`` read it,
        # so an owner that does not resolve (yet) cannot make this answer
        # "not a predicate" while they answer "a predicate".
        loading = loading_head_fields(binding)
        resolved = _resolve_mangled_owner(binding, db)
        if resolved is None:
            return {len(loading)} if loading is not None else set()
        db, functor = resolved
        defined, declared = _arity_maps(db, cache)
        if loading is not None:
            return {len(loading)} | set(defined.get(functor, ()))
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
    register an arity and never field names).  EXCEPTION (2026-09-24): a
    MANGLED handle answers what the class it replaces carries --
    ``Database.field_names_at``: the row's registered signature when one is
    recorded (after a clause, the head's derived names), else the
    synthesized ``arg_N`` placeholders of an arity-only declaration
    (``Database.placeholder_fields``); a plain name with a *db* still
    answers ``None`` for the latter, as before.  ``()``
    means declared with ZERO fields (the 0-arity predicate
    written ``p()``), and ``len()`` is the arity for anything longer.  For
    "is this declared" -- a question this accessor deliberately does NOT
    answer, because for an arity-only declaration it has no way to -- ask
    ``db.declared_kind(functor, arity)`` instead; it already answers
    ``"predicate"`` for both spellings above (``Database.mark_dynamic`` /
    ``mark_predicate_export``), independent of whether any field names are
    known.  The compiler's dominant use of the signature registry is the
    presence test ("a declared functor, or an atom being applied as one?"),
    which never reads a name -- see the spec's premise check.

    Three arms, in order (a ``PredicateMeta`` class arm answering
    ``cls._fields`` was deleted with the class at W4b-3 slice 7):

    1. a ``@dataclass`` class -> its declared field names.  Permanent.
    2. a NAME (``str``, plain or mangled) -> the registry chain below.
       Permanent, and the point of the change: at W4b-2 a module attribute
       for a predicate becomes a mangled atom, and this arm already answers.
       NO builtin-registry fallback (removed W4b-1 fix round 1): a bare
       string that spells a registered builtin name is an ordinary ATOM,
       not a declared functor, and answers ``None`` here.
    3. anything else -> ``None``.
    """
    if isinstance(value, str):
        loading = loading_head_fields(value)
        if loading is not None:
            # A handle its LOADING module declared: the rewriter's class
            # answered ``_fields`` here (W4b-3 slice 5).
            return loading
        return _field_names_for_name(value, arity, db, namespace)
    if not isinstance(value, type):
        return None
    if dataclasses.is_dataclass(value):
        return tuple(f.name for f in dataclasses.fields(value))
    return None


def _field_names_for_name(name, arity, db, namespace):
    """Arm 2 (the NAME arm).  Demangle -> exact db read -> by-name db read -> the
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
        # Ruling Q0: honour the caller's *db* (a handle naming the caller's
        # own, possibly popped, module resolves there), then the handle-only
        # owner rule -- the caller's db is the HINT here, never a fallback
        # for a handle naming another module.
        owner_db = _owner_db_or_none(module_name, db)
        if owner_db is None:
            return None
        # A handle replaces the class, so it answers what the class's
        # ``_fields`` would: ``field_names_at`` is the registered signature
        # (after a clause: the head's derived names, stamped at step 4)
        # first, and an arity-only declaration's ``arg_N`` placeholders
        # only when nothing else is recorded.
        if arity is not None:
            return owner_db.field_names_at(bare_name, arity)
        found = owner_db.declared_fields_by_name(bare_name)
        if found is None:
            # By NAME with no fielded declaration: answer only when the name
            # is a predicate at exactly ONE arity (the class carries one
            # ``_fields``); at several, which one is meant is not ours to
            # guess.
            arities = owner_db.predicate_arities(bare_name)
            if len(arities) == 1:
                found = owner_db.field_names_at(bare_name,
                                                next(iter(arities)))
        return found
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
    name is in ``__all__`` and out-of-tree callers use it, so it is kept
    after W4b-3 slice 7 deleted the predicate class it was named for; it
    answers exactly what ``field_names_for(cls)`` answers (a ``@dataclass``
    class's fields; a predicate handle's declared fields; ``None`` for
    anything else, including a ``str`` with no db or namespace).
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

# The C accelerators, with the pure-Python twins above as the fallback.
# (Until W4b-3 slice 8 the extension also needed a ``_register_predicate_meta``
# call here: it held the ``PredicateMeta`` class for its class-as-term arms,
# and the call was where it set up the interned names ``is_term_instance``
# reads.  Slice 7 deleted the class; slice 8 moved that setup into the
# extension's module init and removed the slot, the arms and the call.)
try:
    from clausal.logic.variables._variables import (
        is_term_instance,
        term_field_names,
    )
except ImportError:
    pass


# DEPRECATED alias, kept for ONE release (Task 12, atoms-as-cells/strings).
# ``predicate.is_atom`` is the zero-field-CLASS test and always was -- it
# answers ``False`` for everything since W4b-3 slice 7 deleted the class; the
# TERM test of the same name lives in ``clausal.logic.atoms``.  No in-tree
# caller uses either class-test name; this one survives only because
# out-of-tree code may still import it from here.  Delete it when the
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
    widening has one place to land.  (``predicate.is_zero_field_class`` above
    asked the separate CLASS question; it answers ``False`` for everything
    since W4b-3 slice 7, and nothing in-tree asks it.)
    """
    from clausal.logic.atoms import is_atom as _term_is_atom
    return _term_is_atom(obj)          # STAGE 2 (spec §4): no class is an atom


class MakePredicateRetiredError(TypeError):
    """``make_predicate`` was RETIRED (W4b-3 slice 6, 2026-09-25): a
    predicate is a Database row, named by a handle, and a class created in
    Python has no Database to be a row of.  A ``TypeError`` -- the call
    itself is the mistake, whatever its arguments -- raised at the call, so
    the traceback points at the line to change."""


_MAKE_PREDICATE_RETIRED = (
    "make_predicate({name!r}, {fields!r}) was retired (W4b-3 slice 6): a "
    "predicate is a row in a module's Database, named by a handle, not a "
    "class made in Python.\n"
    "  -> define {name} in a .clausal module and import it (or load the "
    "module and run a goal with solve((\"{name}\", *args), module=m));\n"
    "  -> to supply a predicate from Python, bind a plain object (not a "
    "class) with a _get_dispatch() method returning its dispatch function "
    "into a Python module, and -import_from it;\n"
    "  -> to build a term, write the cell: ({name!r}, arg, ...).")


def make_predicate(name: str, fields: list[str], *,
                   instances: Any = _MISSING) -> NoReturn:
    """RETIRED (W4b-3 slice 6): raises :class:`MakePredicateRetiredError`.

    It created a ``PredicateMeta`` class from Python -- the Python-API arm of
    the class era; the class itself was deleted at W4b-3 slice 7.
    The name stays so a caller gets THIS explanation, pointing at the
    replacements, rather than an ``ImportError``/``AttributeError``."""
    raise MakePredicateRetiredError(
        _MAKE_PREDICATE_RETIRED.format(name=name, fields=list(fields)
                                       if isinstance(fields, (list, tuple))
                                       else fields))


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

    (A zero-arity PREDICATE -- the thing a bare ``p()`` declaration declares,
    which is a procedure and not an atom -- is a row named by its handle;
    ``make_predicate(name, [])`` minted one as a class until W4b-3 slice 6.)

    Delegates to ``clausal.logic.atoms.mint`` (spec §6.1) — the public atom
    API that Plan 0 of the atoms-as-cells/strings plan introduces.
    """
    from clausal.logic.atoms import mint
    return mint(name)


__all__ = ["RetiredStateError", "_MISSING", "is_term_instance",
           "is_zero_field_class",
           # ``is_atom`` is the DEPRECATED alias of ``is_zero_field_class``
           # (Task 12); exported for one release so out-of-tree importers do
           # not break in the same commit that renames it.
           "is_atom",
           "is_atom_value",
           "term_field_names", "term_field_names_of_class", "field_names_for",
           "term_field_values", "term_field_dict",
           "make_predicate", "MakePredicateRetiredError", "make_atom",
           "resolve_predicate_row", "is_declared_predicate",
           "is_declared_predicate_name", "predicate_arities_for",
           "mint_predicate_handle", "namespace_db",
           "predicate_owner_module",
           "head_cell", "build_term_cell", "construction_arity_fault",
           "AmbiguousArityConstructionError"]
