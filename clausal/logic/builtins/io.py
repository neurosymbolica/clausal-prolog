"""I/O builtins (V2-15 + Phase 2): write/1, writeln/1, writeq/1,
write_canonical/1, write_term/2, write_text/1, writeln_text/1, print_term/1,
nl/0, tab/1, write_to_string/2, write_text_to_string/2, term_to_string/2,
listing/1, portray_clause/1."""

from __future__ import annotations

import numbers as _numbers
import sys as _sys

from clausal.logic.atoms import (
    demangle,
    is_atom as _term_is_atom,
    is_mangled,
    spelling,
)
from clausal.logic.cells import (
    TUPLE_TAG, chars, is_chars, chars_text,
)
from clausal.logic.variables import Var, deref, is_var, unify
from clausal.terms import (
    term_str as _term_str,
    term_canonical as _term_canonical,
    term_pformat as _term_pformat,
    quote_string as _quote_string,
    Compound,
    DictTerm,
    Div,
    FloorDiv,
    KWTerm,
    SegBytes,
    SegList,
    SegString,
    SetTerm,
)
from clausal.logic.runtime._seg_helpers import normalize_seg_input
from clausal.logic.predicate import (
    PredicateMeta, is_term_instance, term_field_names,
    term_field_names_of_class, resolve_predicate_row,
    is_declared_predicate_name,
)
from clausal.logic.exceptions import (
    LogicException, type_error, domain_error, existence_error,
    instantiation_error,
)

from clausal.logic.builtins._helpers import _is_empty_list
from clausal.logic.builtins._registry import _builtin, _db_builtin, _DB_BUILTINS, BuiltinPredicate


# ── The three writer families (spec §6.7, Task 15 item 4 as amended) ─────────
#
# 1. ISO          write/1, writeq/1, write_canonical/1, write_term/2 --
#                 a string is the LIST of its characters, so ``write("abc")``
#                 prints ``[a,b,c]`` exactly as ISO/Scryer do.  ``writeln/1``
#                 and ``write_to_string/2`` are not ISO NAMES but are
#                 ``write/1``'s semantics (+ a newline / into a string).
# 2. Clausal TEXT write_text/1, writeln_text/1, write_text_to_string/2 --
#                 a string prints as its TEXT and a char list as the text it
#                 spells.  This is the engine's ``~s`` and where f-strings go:
#                 ``writeln_text(f"X is {X}")``.
# 3. Clausal      print_term/1, term_to_string/2 -- the quoted, double-quoted
#    DISPLAY      display form: ``write_term(T, [quoted(true),
#                 double_quotes(true)])``'s SPELLING of a string (the form a
#                 reader recognises as the term they wrote, and the one
#                 Scryer's TOPLEVEL uses) PLUS the display comma spacing.
#
# The ISO family prints NO whitespace after a comma -- ``[a,b,c]``,
# ``f(a,b)``, ``{k:v}`` -- so its output is byte-comparable with Scryer's
# (fix round 1, item 0, operator-ruled 2026-09-07).  The display family
# keeps ``", "``.  Both come out of ``term_str``'s ``sep`` keyword;
# ``write_canonical/1`` has its own renderer and is unaffected.


def _format_term_as_text(val):
    """Format a dereffed value for the Clausal TEXT family.

    A STRING passes through as its text (supports f-strings naturally) --
    the text family is unquoted by definition.  THE FLIP removed the
    mangled-atom substitution from this branch: ``-hide`` mangling lives in
    an ATOM's spelling, and an atom is a cell, so it is the cell branch
    below (through ``term_str``) that demangles.  A ``str`` cannot carry
    ``HIDDEN_SEP`` except by the documented out-of-warranty forgery, and the
    display substitution is not owed to a forgery.
    Other values use str() which auto-derefs Vars via __str__.
    """
    if _is_empty_list(val):
        # Every spelling of the empty list -- ``[]``, ``""``, ``b""``, ``()``
        # -- is the atom ``'[]'`` and prints ``[]`` in EVERY family (fix
        # round 2, item 5).  Decided first: ``()`` is falsy at the cell test
        # below and ``b""`` never reached ``term_str`` at all, so both used
        # to fall to ``str()`` and print ``()`` / ``b''``.
        return "[]"
    if is_chars(val):
        val = chars_text(val)          # stage 1: the carrier is text
    if isinstance(val, str):
        return val                     # STAGE 2: the text, or an atom's spelling ('' prints nothing)
    if isinstance(val, list):
        # A LIST -- routed through ``term_str`` for the same reason the cell
        # branch below is: ``str()`` on a list renders each ELEMENT with
        # ``repr``, so an element that is a cell (``("a",)``, an atom now
        # that atoms are cells) leaked a Python tuple repr into write/1's
        # output.  ``[1, 2]`` is unchanged (spec §6.7's table row).
        return _term_str(val, quoted=False)
    if type(val) is tuple and val and (type(val[0]) is str or val[0] is TUPLE_TAG):
        # A CELL -- ``("pt", 1, 2)`` (or a tuple-DATA cell, ``(tuple, ...)``).
        # P3-2 Task 2 (THE FLIP) makes this how every compound term is
        # represented, and ``str()`` on one is the Python tuple repr, so
        # ``write(pt(1, 2))`` printed ``('pt', 1, 2)``.  ``term_str`` renders
        # it as the term (``clausal/terms.py``'s cell branches); only this
        # shape is routed there, so every other value keeps the exact
        # ``str()`` rendering write/1 has always produced.
        #
        # Slot 0 read RAW -- no deref (P3-2 Task 5/Task 7 review): a
        # slot-0-Var tuple is not a legal cell any more (see
        # ``clausal/logic/cells.py``'s module docstring) and falls through
        # to the ordinary ``str()`` rendering below, same as any other
        # non-str, non-``TUPLE_TAG`` slot 0.
        #
        # ``quoted=False``: the text family is unquoted, so an atom prints its
        # bare spelling (``foo bar``, not ``'foo bar'``) -- exactly what the
        # str branch above already does for the text of a string.
        return _term_str(val, quoted=False)
    return str(val)


#: Term shapes ``term_str`` renders as TERMS rather than falling back to
#: ``repr``.  Everything here goes through the ISO renderer; everything else
#: (``date``, ``Quantity``, a ``PredicateMeta`` class, an opaque Python
#: object, an unbound ``Var``) keeps the exact ``str()`` rendering ``write/1``
#: has always produced -- a ``date`` prints ``2020-01-01``, not its ``repr``,
#: and an unbound ``Var`` prints ``_N`` rather than the style's anonymous
#: placeholder.
_ISO_TERM_TYPES = (str, bytes, list, Compound, KWTerm, DictTerm, SetTerm)


#: What the ISO family puts between a compound's arguments and a list's
#: elements: NOTHING after the comma, so the output is byte-comparable with
#: Scryer (fix round 1, item 0).  ``term_str``'s own default, ``", "``, is
#: the Clausal DISPLAY family's.
ISO_SEP = ","


def _format_term_iso(val, quoted: bool, double_quotes: bool = False) -> str:
    """Format a dereffed value for the ISO family (``write/1``/``writeq/1``/
    ``write_term/2``).

    ``double_quotes(false)`` and ``sep=","``, ISO's own defaults: a string is
    the LIST of its char atoms, so ``write("abc")`` prints ``[a,b,c]`` and
    ``writeq("abc")`` prints the same, byte-comparable with Scryer (fix
    round 1, item 0).  A ``bytes`` is a code list and prints ``[97,98]``
    (item 5).

    Every shape ``term_str`` renders as a term is routed to it (item 1) --
    ``Compound``, ``KWTerm``, ``DictTerm``, ``SetTerm`` and declared term
    instances used to fall to ``str()``, which routes back through
    ``term_str``'s DISPLAY defaults and so printed double-quoted strings and
    Python reprs inside an ISO writer's output.

    *double_quotes* is here only for ``write_term/2``'s option of that name;
    every other caller in the family leaves it False.
    """
    if _is_empty_list(val):
        # ``()`` is nil and is not caught by the cell test below (it is
        # falsy), so it is decided here (fix round 2, item 5).
        return "[]"
    if isinstance(val, _ISO_TERM_TYPES) or is_term_instance(val):
        return _term_str(val, quoted=quoted, double_quotes=double_quotes,
                         sep=ISO_SEP)
    if type(val) is tuple and val and (type(val[0]) is str or val[0] is TUPLE_TAG):
        # A CELL -- ``("pt", 1, 2)`` (or a tuple-DATA cell). Slot 0 read RAW,
        # no deref: a slot-0-Var tuple is not a legal cell (see
        # ``clausal/logic/cells.py``) and falls through to ``str()`` below.
        return _term_str(val, quoted=quoted, double_quotes=double_quotes,
                         sep=ISO_SEP)
    return str(val)


@_builtin("write", 1)
def _write__1(term, trail, k):
    """write(Term) — print dereffed term to stdout (no newline), ISO 8.14.2.

    ``write_term(Term, [numbervars(true)])``: atoms print their bare spelling
    and a STRING prints as the list of characters it is —
    ``write("abc")`` prints ``[a,b,c]``, ``write(['a','b'])`` prints
    ``[a,b]``.  Vars are auto-dereffed.

    For the TEXT rendering — a string as its characters, which is what an
    f-string wants — use ``write_text/1`` / ``writeln_text/1`` (Task 15
    item 4 as amended, 2026-09-07).
    """
    from clausal.logic.solve import _deref_walk
    _sys.stdout.write(_format_term_iso(_deref_walk(term), quoted=False))
    _sys.stdout.flush()
    yield None


@_builtin("writeln", 1)
def _writeln__1(term, trail, k):
    """writeln(Term) — ``write/1`` plus a newline.

    Not an ISO name, but ``write/1``'s semantics: a string prints as its char
    list.  ``writeln_text/1`` is the text form.
    """
    from clausal.logic.solve import _deref_walk
    print(_format_term_iso(_deref_walk(term), quoted=False))
    yield None


@_builtin("write_text", 1)
def _write_text__1(term, trail, k):
    """write_text(Term) — print dereffed term to stdout as TEXT (no newline).

    The Clausal text family (Task 15 item 4 as amended, 2026-09-07): a STRING
    prints as its characters and a char list as the text it spells, an atom
    prints its bare spelling, and every other term prints as ``write/1``
    would.  This is the engine's ``~s``, and it is where f-strings go:
    ``write_text(f"X is {X_}")``.  ``write/1`` is the ISO writer and prints
    a string as ``[a,b,c]``.
    """
    from clausal.logic.solve import _deref_walk
    _sys.stdout.write(_format_term_as_text(_deref_walk(term)))
    _sys.stdout.flush()
    yield None


@_builtin("writeln_text", 1)
def _writeln_text__1(term, trail, k):
    """writeln_text(Term) — ``write_text/1`` plus a newline.

    Works naturally with f-strings: ``writeln_text(f"X is {X_}")``.
    """
    from clausal.logic.solve import _deref_walk
    print(_format_term_as_text(_deref_walk(term)))
    yield None


@_builtin("write_text_to_string", 2)
def _write_text_to_string__2(term, result, trail, k):
    """write_text_to_string(Term, Result) — the ``write_text/1`` rendering of
    Term, as a string.  Prints nothing.
    """
    from clausal.logic.solve import _deref_walk
    s = chars(_format_term_as_text(_deref_walk(term)))   # stage 1: a text RESULT is the carrier
    mark = trail.mark()
    if unify(result, s, trail):
        yield None
    trail.undo(mark)


@_builtin("writeq", 1)
def _writeq__1(term, trail, k):
    """writeq(Term) — write Term quoted so the reader reads it back (ISO 8.14.2).

    The quoted member of the ISO family (spec §6.7): an atom that would not
    re-read as itself is single-quoted (``'foo bar'``); list syntax is
    write/1's, unlike write_canonical/1 below, and so is the ISO comma
    spacing -- there is none (fix round 1, item 0), so ``writeq(f(a, "b"))``
    prints ``f(a,[b])`` byte-for-byte as Scryer does.

    Exactly ``write_term(Term, [quoted(true), numbervars(true)])`` (Task 15
    item 4 as amended, 2026-09-07), so ``double_quotes`` is FALSE and a
    string prints as the char list it is: ``writeq("abc")`` prints
    ``[a,b,c]``.  ``print_term/1`` / ``term_to_string/2`` are the Clausal
    DISPLAY form, which prints ``"abc"`` and keeps ``", "``.
    """
    from clausal.logic.solve import _deref_walk
    _sys.stdout.write(_format_term_iso(_deref_walk(term), quoted=True))
    _sys.stdout.flush()
    yield None


@_builtin("write_canonical", 1)
def _write_canonical__1(term, trail, k):
    """write_canonical(Term) — ISO 8.14.2 canonical form: quoted atoms, no
    operators, no space after a comma, and every list as its ``'.'/2``
    structure (spec §6.7; Scryer prints ``write_canonical("hello")`` as
    ``'.'(h,'.'(e,'.'(l,'.'(l,'.'(o,[])))))``).
    """
    from clausal.logic.solve import _deref_walk
    _sys.stdout.write(_term_canonical(_deref_walk(term)))
    _sys.stdout.flush()
    yield None


# ── write_term/2 (ISO 8.14.2) ────────────────────────────────────────────────
#
# Task 15 item 4 (ISO alignment, 2026-09-07).  The writers of this engine sit
# on ``term_str``'s two switches, and ``write_term/2`` is the predicate that
# exposes them by name:
#
#   write/1, writeln/1, write_to_string/2     quoted(false), double_quotes(false)
#   writeq/1                                  quoted(true),  double_quotes(false)
#   print_term/1, term_to_string/2            quoted(true),  double_quotes(true)
#   write_text/1, writeln_text/1,             the TEXT family (not term_str's
#     write_text_to_string/2                  switches -- ``_format_term_as_text``)
#   write_canonical/1                         its own renderer (term_canonical)
#
# Streams are out of scope, so there is no ``write_term/3``.

#: The write-options this engine knows.  Anything else is a
#: ``domain_error(write_option, Opt)``, as ISO 8.14.2.3 g requires.
#: ``ignore_ops`` and ``numbervars`` are accepted and INERT: this engine
#: never prints operator forms in the write family (so ``ignore_ops(true)``
#: is already what it does), and it has no ``'$VAR'/1`` convention to
#: honour or suppress.
_WRITE_OPTIONS = frozenset({
    "quoted", "double_quotes", "ignore_ops", "numbervars",
})


def _write_option_bool(value, option):
    """Read a write-option's Boolean argument.

    Source ``quoted(true)`` folds ``true``/``false`` to Python ``True``/
    ``False`` (spec §8), but a term built through ``functor/3`` or by a
    Python caller carries the ATOM, so both spellings are read.  Anything
    else is a ``domain_error(write_option, Opt)`` — the option as a whole is
    what ISO reports.
    """
    value = deref(value)
    if value is True or value is False:
        return value
    if _term_is_atom(value):
        name = spelling(value)
        if name == "true":
            return True
        if name == "false":
            return False
    raise LogicException(domain_error("write_option", option, "write_term/2"))


def _write_term_options(options):
    """``(quoted, double_quotes)`` for an ISO write-option list.

    ISO 8.14.2's defaults are ``quoted(false)`` and ``double_quotes(false)``,
    so ``write_term(T, [])`` prints a string as ``[a,b,c]`` — which is
    exactly ``write/1``.  ``ignore_ops(Bool)`` and ``numbervars(Bool)`` are
    accepted and inert (see ``_WRITE_OPTIONS``).

    An unbound ``Options``, and a PARTIAL one (``[quoted(true) | _]``, which
    reaches here as a non-ground ``Seg*``), are both
    ``instantiation_error`` — ISO 8.14.2.3 a/b (fix round 1, item 7).  A
    ground ``Seg*`` walks to the plain list it is and is read normally.
    """
    opts_val = normalize_seg_input(deref(options))
    if is_var(opts_val):
        raise LogicException(instantiation_error("write_term/2"))
    if isinstance(opts_val, (SegList, SegString, SegBytes)):
        # Still a Seg* after the walk: a PARTIAL list, i.e. one whose tail is
        # unbound.  ISO says instantiation_error, not type_error(list, …).
        raise LogicException(instantiation_error("write_term/2"))
    if not isinstance(opts_val, list):
        # A ``str`` lands here too, and gets the same refusal: a string is a
        # list of char ATOMS, never a list of options.
        raise LogicException(type_error("list", opts_val, "write_term/2"))
    quoted = False
    double_quotes = False
    for opt in opts_val:
        opt = deref(opt)
        if is_var(opt):
            raise LogicException(instantiation_error("write_term/2"))
        if not (type(opt) is tuple and len(opt) == 2 and type(opt[0]) is str):
            raise LogicException(
                domain_error("write_option", opt, "write_term/2"))
        name = opt[0]
        if name not in _WRITE_OPTIONS:
            raise LogicException(
                domain_error("write_option", opt, "write_term/2"))
        value = _write_option_bool(opt[1], opt)
        if name == "quoted":
            quoted = value
        elif name == "double_quotes":
            double_quotes = value
    return quoted, double_quotes


@_builtin("write_term", 2)
def _write_term__2(term, options, trail, k):
    """write_term(Term, Options) — ISO 8.14.2's writer with an option list.

    ``quoted(Bool)`` quotes atoms that would not re-read as themselves;
    ``double_quotes(Bool)`` prints a string (and the char list that IS one)
    as ``"abc"`` rather than as ``[a,b,c]``; ``ignore_ops(Bool)`` and
    ``numbervars(Bool)`` are accepted and inert.  Both Boolean options
    default to FALSE, so ``write_term(T, [])`` is exactly ``write/1`` and
    ``write_term(T, [quoted(true)])`` is exactly ``writeq/1``.
    ``write_term(T, [quoted(true), double_quotes(true)])`` is the SPELLING
    ``print_term/1`` / ``term_to_string/2`` give a string (fix round 1,
    item 4) — those two additionally keep the display comma spacing, which
    this writer, being ISO, does not.

    An unrecognised option is ``domain_error(write_option, Opt)``; a
    non-list *Options* is ``type_error(list, Options)``; an unbound or
    partial one is ``instantiation_error``.

    Streams are out of scope, so there is no ``write_term/3``.  Output uses
    the ISO comma spacing — none — so it is byte-comparable with Scryer
    (fix round 1, item 0).
    """
    from clausal.logic.solve import _deref_walk
    quoted, double_quotes = _write_term_options(options)
    _sys.stdout.write(_format_term_iso(_deref_walk(term), quoted=quoted,
                                       double_quotes=double_quotes))
    _sys.stdout.flush()
    yield None


@_builtin("print_term", 1)
def _print_term__1(term, trail, k):
    """print_term(Term) — print structured term representation with newline.

    Uses term_str() for Prolog-style output showing term structure
    (e.g., functors, lists, operators).  Vars show as Var(_N).

    The ``writeq/1`` family (spec §6.7): exactly
    ``write_term(Term, [quoted(true), double_quotes(true)])``, plus the
    newline — Scryer's TOPLEVEL display form.
    """
    from clausal.logic.solve import _deref_walk
    val = _deref_walk(term)
    print(_term_str(val))
    yield None


@_builtin("nl", 0)
def _nl__0(trail, k):
    """nl — print a newline."""
    print()
    yield None


@_builtin("tab", 1)
def _tab__1(n, trail, k):
    """tab(N) — print N spaces."""
    n_val = deref(n)
    if is_var(n_val) or not isinstance(n_val, int):
        return
    _sys.stdout.write(" " * n_val)
    _sys.stdout.flush()
    yield None


@_builtin("write_to_string", 2)
def _write_to_string__2(term, result, trail, k):
    """write_to_string(Term, Result) — unify Result with the ``write/1``
    rendering of Term, as a string.  Prints nothing.

    Not an ISO name, but ``write/1``'s semantics: a string renders as the
    char list it is.  ``write_text_to_string/2`` is the text form.
    """
    from clausal.logic.solve import _deref_walk
    s = chars(_format_term_iso(_deref_walk(term), quoted=False))   # stage 1: a text RESULT is the carrier
    mark = trail.mark()
    if unify(result, s, trail):
        yield None
    trail.undo(mark)


@_builtin("term_to_string", 2)
def _term_to_string__2(term, result, trail, k):
    """term_to_string(Term, Result) — unify Result with structured term_str
    representation.

    The ``writeq/1`` family: exactly the text
    ``write_term(Term, [quoted(true), double_quotes(true)])`` writes.
    """
    from clausal.logic.solve import _deref_walk
    val = _deref_walk(term)
    s = chars(_term_str(val))          # stage 1: a text RESULT is the carrier
    mark = trail.mark()
    if unify(result, s, trail):
        yield None
    trail.undo(mark)


# ── Clause formatting helpers ────────────────────────────────────────────────

def _format_clause_term(val):
    """Format a term value for clause head display."""
    val = deref(val)
    if isinstance(val, Var):
        return str(val)  # _N format for anonymous vars
    if is_chars(val):
        val = chars_text(val)          # stage 1: the carrier is text
    if isinstance(val, str):
        # A STRING (THE FLIP) -- ``listing/1`` is in the quoted family, so it
        # prints as a double-quoted string literal, which is how the module
        # it is listing would have to spell it.  ``repr`` is not that: it
        # picks quotes by content (``"it\'s"``) and would emit a single-
        # quoted literal -- an ATOM -- for the common case.
        return _quote_string(val)
    if isinstance(val, list):
        return "[" + ", ".join(_format_clause_term(e) for e in val) + "]"
    if is_term_instance(val):
        return _format_clause_head(val)
    if type(val) is tuple and val and (type(val[0]) is str or val[0] is TUPLE_TAG):
        # A CELL (or tuple-DATA cell) nested in a clause argument -- ``str()``
        # on a plain tuple is the Python repr, so an argument like
        # ``("pt", 1, 2)`` printed ``('pt', 1, 2)`` in ``listing/1`` output
        # instead of ``pt(1, 2)``.  ``term_str`` renders it as the term
        # (``clausal/terms.py``'s cell branches); Compound already gets this
        # for free via its own ``__str__``, which is why only this shape
        # needs routing here.
        return _term_str(val)
    return str(val)


def _format_clause_head(head):
    """Format a clause head as 'functor(arg1, arg2, ...)'."""
    from clausal.logic.cells import _cell_shape, cell_args, cell_functor  # noqa: PLC0415
    if _cell_shape(head)[0]:                        # P2: a head is a cell
        name, args = cell_functor(head), cell_args(head)
        if not args:
            return name
        return f"{name}({', '.join(_format_clause_term(a) for a in args)})"
    if is_term_instance(head):
        name = type(head).__name__
        fields = term_field_names(head)
        if not fields:
            return name
        args = [_format_clause_term(getattr(head, f)) for f in fields]
        return f"{name}({', '.join(args)})"
    return _term_str(head)


def _format_clause(clause):
    """Format a Clause for listing output."""
    head_str = _format_clause_head(clause.head)
    if clause.is_fact():
        return f"{head_str}."
    body_strs = [str(g) for g in clause.body]
    body = ", ".join(body_strs)
    if len(clause.body) > 1:
        return f"{head_str} <- ({body})."
    return f"{head_str} <- {body}."


# ── listing/1 ────────────────────────────────────────────────────────────────


def _importer_spellings(db, handle) -> list:
    """The names under which the calling module could have adopted *handle*'s
    row: the handle's own atom half, then every other name the module's
    namespace binds to *handle* -- an ``alias(Orig, Local)`` import binds the
    OWNER's handle (ruling D1) under ``Local``, and adopted rows are keyed by
    that importer spelling, which the handle itself does not carry."""
    names = [demangle(handle)[1]]
    module_dict = getattr(db, "module_dict", None) if db is not None else None
    if isinstance(module_dict, dict):
        names += [k for k, v in module_dict.items()
                  if type(v) is str and v == handle and k not in names]
    return names


def _handle_row(db, handle, arity):
    """The row a predicate HANDLE denotes at *arity*, or ``None``: its own
    row, else the row *db* adopted for it under any importer spelling
    (``database_ops._binding_row``, the shared rule)."""
    from clausal.logic.builtins.database_ops import _binding_row  # noqa: PLC0415
    for spelling_ in _importer_spellings(db, handle):
        row = _binding_row(db, handle, spelling_, arity)
        if row is not None:
            return row
    return None


def _is_predicate_handle(name, arity, db) -> bool:
    """True iff *name* is a mangled atom that is a predicate HANDLE -- never
    for a ``-hide`` data atom (``is_mangled`` is not "is a predicate").

    Two ways in: the handle's owner resolves and declares the name as a
    predicate (arity-blind, like the class arm: the arity is checked when the
    row is read); or the owner was popped from ``sys.modules`` and *db*
    adopted a row for exactly this handle at ``-import_from``, under any
    importer spelling (an aliased import included).  *arity* is only
    consulted for the adopted-row key, and a non-int arity (a malformed
    indicator) answers ``False`` so the caller's shape checks still run.
    """
    if not is_mangled(name):
        return False
    if is_declared_predicate_name(name, db=db):
        return True
    if not isinstance(arity, int) or isinstance(arity, bool):
        return False
    return _handle_row(db, name, arity) is not None


def _indicator_row(db, name, arity, pred_cls):
    """The row whose clauses ``listing/1`` should print, or ``None``.

    Three lookups, in the order that makes an indicator name the same
    predicate the equivalent GOAL would (final review M-a):

    1. the BINDING's own row, when the indicator's left operand was a
       predicate binding (*pred_cls*: a class, or after the flip a handle)
       and its row is a REAL row at the requested arity
       (``database_ops._binding_row``, era-agnostic).  A shared
       ``-import_from``'d predicate reads the exporter's row, which is the
       whole point: ``listing(qq/1)`` must print what ``listing(qq)`` prints.
       A DETACHED row is skipped -- it is nobody's predicate (same rule
       ``PredicateMeta._bind_row`` applies), so a standalone class of the
       same name must not shadow the caller's real one.  A HANDLE is
       authoritative (ruling QE): when neither its row nor the row this
       database adopted for it answers at *arity*, the answer is ``None``
       (an ``existence_error``), never a bare-name lookup that could list a
       different local ``name/N``;
    2. the calling module's NAMESPACE, resolved exactly as
       ``higher_order._namespace_dispatch`` resolves a named goal
       (``_find_pred_cls`` for the arity-checked binding, then the row that
       binding reads), so the atom spelling ``listing('qq'/1)`` finds the
       same imported predicate the binding spelling does.  Taken only when
       the binding reads a REAL row (``_binding_row``): a binding that is
       detached or unbound is nobody's predicate, and a standalone class
       whose ``__name__`` differs from the name it is bound under must not
       redirect the lookup to that other name.  F1 row 60 (2026-09-24): this
       leg used to come AFTER the bare ``db.row`` below, and a module that
       imports a predicate and re-declares it ``-dynamic`` holds a LOCAL empty
       twin under the same key, which ``db.row`` prefers -- so listing the
       import printed the twin's "no clauses" in both eras.  A module's OWN
       predicate resolves to its own database here, so it is unaffected;
    3. the calling database's own row -- the ordinary local predicate the
       namespace does not bind at this arity (a name defined at several
       arities binds one of them).
    """
    from clausal.logic.builtins.database_ops import (  # noqa: PLC0415
        _binding_row, _canonical_functor, _find_pred_cls,
    )
    if pred_cls is not None:
        if not isinstance(pred_cls, PredicateMeta):
            return _handle_row(db, pred_cls, arity)
        row = _binding_row(db, pred_cls, name, arity)
        if row is not None and row.key[1] == arity:
            return row
    if db is None:
        return None
    module_dict = getattr(db, "module_dict", None)
    found = (_find_pred_cls(name, arity, module_dict)
             if module_dict is not None else None)
    bound = _binding_row(db, found, name, arity) if found is not None else None
    if bound is not None:
        row = bound.db.row(
            _canonical_functor(db, found, name), arity, create=False)
        if row is not None:
            return row
    return db.row(name, arity, create=False)


def _pi_parts(val):
    """``(separator, name, arity)`` of a ``Name/Arity`` or ``Name//Arity``
    SHAPED *val*, operands dereffed, or ``None`` -- shape only, nothing about
    whether the operands are well formed.

    Four spellings of each: the cell ``('/', n, a)``, the engine's
    ``Compound("/", (n, a))``, and the runtime operator node a user-written
    ``fib/2`` (``Div``) or ``fib//2`` (``FloorDiv``) compiles to.
    """
    if type(val) is tuple and len(val) == 3 and val[0] in ("/", "//"):
        return val[0], deref(val[1]), deref(val[2])
    if (isinstance(val, Compound) and val.functor in ("/", "//")
            and len(val.args) == 2):
        return val.functor, deref(val.args[0]), deref(val.args[1])
    if isinstance(val, Div):
        return "/", deref(val.left), deref(val.right)
    if isinstance(val, FloorDiv):
        return "//", deref(val.left), deref(val.right)
    return None


def _checked_indicator(parts, db):
    """``(name, arity, binding)`` for a well-formed indicator, else the ISO
    error Scryer's ``listing/1`` raises for it (operator ruling 2026-09-25,
    "do what Scryer does").

    Scryer checks the SHAPE itself and hands the operands to ``functor/3``,
    so every operand fault is ``functor/3``'s: an unbound operand is an
    ``instantiation_error``, a non-integer arity ``type_error(integer, A)``, a
    negative one ``domain_error(not_less_than_zero, A)``, a compound name
    (a string is the list it denotes) ``type_error(atomic, N)``, and an
    atomic non-atom name ``type_error(atom, N)`` (``type_error(callable, N)``
    at arity 0, which ``clause/2`` reports for ``functor(H, 3, 0)``).
    ``Name//A`` names ``Name/(A+2)``.  *binding* is the predicate binding
    the name WAS (a ``PredicateMeta`` class, or a predicate HANDLE), else
    ``None``: the name alone is not enough to find an ``-import_from``'d
    predicate, which lives on the EXPORTER's row (final review M-a).  A mangled
    name is a handle only when it denotes a PREDICATE (F1 row 60): a ``-hide``
    DATA atom has the same shape, keeps its mangled spelling, and names no
    predicate.
    """
    sep, name, arity = parts
    if is_var(name) or is_var(arity):
        raise LogicException(instantiation_error(
            "listing/1: the predicate indicator is not sufficiently "
            "instantiated — bind Name/Arity before listing it",
        ))
    if not isinstance(arity, int) or isinstance(arity, bool):
        raise LogicException(type_error("integer", arity, "listing/1"))
    if sep == "//":
        arity += 2
    binding = None
    if isinstance(name, PredicateMeta):
        binding, name = name, name.__name__
    elif _is_predicate_handle(name, arity, db):
        binding, name = name, demangle(name)[1]
    elif _term_is_atom(name):
        name = spelling(name)
    elif isinstance(name, _numbers.Number) and not isinstance(name, bool):
        raise LogicException(type_error(
            "atom" if arity > 0 else "callable", name, "listing/1"))
    else:
        raise LogicException(type_error("atomic", name, "listing/1"))
    if arity < 0:
        raise LogicException(domain_error(
            "not_less_than_zero", arity, "listing/1"))
    return name, arity, binding


@_db_builtin("listing", 1, fields=("pred",))
def _make_listing__1(db):
    """Factory for ``listing/1`` — captures *db* so a ``Name/Arity``
    indicator can be resolved to a row.

    The class/instance/``BuiltinPredicate`` argument shapes are the PYTHON
    API and need no database at all (a ``PredicateMeta``'s clauses are its
    row's), so ``db=None`` (``get_builtin_dispatch("listing", 1, None)``)
    keeps working for those.  An indicator with no database to resolve it
    against names no clauses, and fails.
    """
    def _listing__1(pred, trail, k):
        """listing(PI) — print all clauses of a predicate to stdout.

        Operator ruling 2026-09-25: "do what Scryer does".  Scryer's
        definition (library(format))::

            listing(PI) :-
                    nonvar(PI),
                    (   PI = Name/Arity0 -> Arity = Arity0
                    ;   PI = Name//Arity0 -> Arity is Arity0 + 2
                    ;   type_error(predicate_indicator, PI, listing/1)
                    ),
                    functor(Head, Name, Arity),
                    \\+ \\+ clause(Head, _),
                    ...

        So, for a TERM argument:
          - unbound -> fails;
          - ``Name/Arity`` / ``Name//Arity`` -> lists Name/Arity (resp.
            Name/(Arity+2)); FAILS when that predicate does not exist or has
            no clauses; a malformed operand is ``functor/3``'s ISO error
            (``_checked_indicator``);
          - anything else -- a bare atom, a compound term, a string, a
            number -- is ``type_error(predicate_indicator, PI)``.
        Kept (the Python API, retired at a later flip): a ``PredicateMeta``
        class or instance lists its own clauses, a ``BuiltinPredicate``
        prints its "% name/arity — builtin" line.
        """
        val = deref(pred)
        if is_var(val):
            return                      # Scryer: nonvar(PI), else fail

        # A predicate HANDLE passed DIRECTLY -- the Python API,
        # ``listing(mod.fib)`` once the binding is a handle -- lists its
        # predicate, as the class arm below lists a class (operator ruling
        # 2026-09-25).  A class names one arity; a handle names none, so a
        # name that is a predicate at several arities lists each, in arity
        # order: Scryer refuses a bare name only because it is ambiguous, and
        # listing them all is the Python API's answer.  SOURCE ``listing(fib)``
        # never gets here -- ruling S lowers the bare name to its plain atom,
        # which ``_pi_parts`` does not take, so it stays Scryer's
        # ``type_error(predicate_indicator, fib)``.  A ``-hide`` DATA atom is
        # mangled in the same shape but is no predicate, so it keeps that
        # refusal with its own spelling.
        bare = _bare_handle_listing(val, db)
        if bare is not None:
            for _name, _arity, _clauses in bare:
                if not _clauses:
                    print(f"% {_name}/{_arity} — no clauses")
                else:
                    print(f"% {_name}/{_arity} — {len(_clauses)} clause(s)")
                    for clause in _clauses:
                        print(_format_clause(clause))
            yield None
            return

        parts = _pi_parts(val)
        if parts is not None:
            name, arity, binding = _checked_indicator(parts, db)
            if db is None and binding is None:
                return                  # nothing to resolve it against
            row = _indicator_row(db, name, arity, binding)
            if row is None or not row.clauses:
                return                  # Scryer: \+ \+ clause(Head, _)
            clauses = row.clauses
        else:
            # The Python-object arms.  A term INSTANCE resolves to its class
            # (a cell is a tuple, not an instance, and does not reach here).
            culprit = val               # the refusal names what was PASSED
            if not _term_is_atom(val) and is_term_instance(val):
                val = type(val)
            if isinstance(val, BuiltinPredicate):
                print(f"% {val._functor}/{val._arity} — builtin")
                yield None
                return
            if not isinstance(val, PredicateMeta):
                raise LogicException(type_error(
                    "predicate_indicator", culprit, "listing/1"))
            name = val.__name__
            arity = len(term_field_names_of_class(val))
            # A bare ``make_predicate`` class from user Python may be on NO
            # row, and a listing must not mint one: resolve_predicate_row's
            # class arm is a raw, non-minting ``val._row`` read.
            _row = resolve_predicate_row(val, arity=arity, db=db)
            clauses = _row.clauses if _row is not None else []

        if not clauses:
            print(f"% {name}/{arity} — no clauses")
        else:
            print(f"% {name}/{arity} — {len(clauses)} clause(s)")
            for clause in clauses:
                print(_format_clause(clause))
        yield None
    return _listing__1


def _bare_handle_listing(val, db):
    """``[(name, arity, clauses), ...]`` for a declared predicate HANDLE
    passed directly, one entry per arity its owner DEFINES
    (``predicate_arities_for``) in arity order, each read from the row the
    indicator form ``listing(name/N)`` reads (``_indicator_row``) so the two
    cannot disagree -- else ``None`` (not a handle, a ``-hide`` data atom, or
    a handle naming nothing defined)."""
    if type(val) is not str or not is_mangled(val):
        return None
    if not is_declared_predicate_name(val, db=db):
        return None
    from clausal.logic.predicate import predicate_arities_for  # noqa: PLC0415
    arities = sorted(predicate_arities_for(val, db=db))
    if not arities:
        return None
    name = demangle(val)[1]
    out = []
    for arity in arities:
        row = _indicator_row(db, name, arity, val)
        out.append((name, arity, row.clauses if row is not None else []))
    return out


# ``_db_optional`` is LOAD-BEARING, not a consistency nicety (P3-3 Task 8
# fix round 1, F3): ``_build_all_builtin_classes()`` calls
# ``_stateless_dispatch("listing", 1)`` at import time to populate
# ``_BUILTIN_CLASSES["listing"]``. Without this flag, ``_stateless_dispatch``
# finds the ``listing`` factory in ``_DB_BUILTINS``, sees no ``_db_optional``,
# and returns ``None`` -- leaving ``_BUILTIN_CLASSES["listing"]._dispatch_fn``
# unset (verified: deleting the flag and rebuilding the class table produces
# exactly that ``None``). At BASE ``listing`` lived in ``_BUILTINS``, which
# ``_stateless_dispatch`` answers unconditionally, so this line is what keeps
# that pre-existing, always-worked path working post-migration, not merely a
# nicety for some other caller. Pinned by
# ``TestListingBuiltinClassHasDispatch`` in ``tests/test_listing.py``, so the
# line cannot be deleted silently.
#
# Set on the object ACTUALLY stored in ``_DB_BUILTINS`` — the ``@_db_builtin``
# decorator wraps the factory with ``_simple_to_trampoline``
# (``_wrap_db_factory``) and returns the ORIGINAL, unwrapped function, so an
# attribute set on ``_make_listing__1`` itself would not reach the stored
# callable.
_DB_BUILTINS[("listing", 1)]._db_optional = True


# ── portray_clause/1 ─────────────────────────────────────────────────────────

@_builtin("portray_clause", 1)
def _portray_clause__1(term, trail, k):
    """portray_clause(Term) — pretty-print a term with indentation."""
    from clausal.logic.solve import _deref_walk
    val = _deref_walk(term)
    print(_term_pformat(val))
    yield None
