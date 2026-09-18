"""I/O builtins (V2-15 + Phase 2): write/1, writeln/1, writeq/1,
write_canonical/1, write_term/2, write_text/1, writeln_text/1, print_term/1,
nl/0, tab/1, write_to_string/2, write_text_to_string/2, term_to_string/2,
listing/1, portray_clause/1."""

from __future__ import annotations

import sys as _sys

from clausal.logic.atoms import (
    is_atom as _term_is_atom,
    spelling,
)
from clausal.logic.cells import TUPLE_TAG, chars, is_chars, chars_text
from clausal.logic.variables import Var, deref, is_var, unify
from clausal.terms import (
    term_str as _term_str,
    term_canonical as _term_canonical,
    term_pformat as _term_pformat,
    quote_string as _quote_string,
    Compound,
    DictTerm,
    Div,
    KWTerm,
    SegBytes,
    SegList,
    SegString,
    SetTerm,
)
from clausal.logic.runtime._seg_helpers import normalize_seg_input
from clausal.logic.predicate import PredicateMeta, is_term_instance, term_field_names, term_field_names_of_class
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
        # The EMPTY string is the empty list and prints ``[]`` in the display
        # family too (spec §6.7's ``""``/``[]`` row; Scryer) -- ``term_str``
        # already answers so for both families, and ``write("")`` printing
        # NOTHING while ``write([])`` printed ``[]`` was the last place the
        # ``str`` representation of one term leaked into an answer.
        if val == "":
            return "[]"
        return val
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


def _as_name_arity_indicator(val):
    """Recognize *val* as a ``Name/Arity`` predicate indicator, in any of
    three representations:

    - the CELL shape ``('/', 'foo', 2)`` (see ``clausal/logic/cells.py``) —
      reachable from Python/engine callers that build the indicator as
      plain data directly (e.g. a caller that already has the name and
      arity in hand and constructs the tuple itself); NOT what a
      user-written ``foo/2`` compiles to in ``.clausal`` source today (see
      the ``Div`` case below) — corrected in P3-3 Task 8 fix round 1 (F1)
      after the earlier docs claimed otherwise;
    - the engine-internal ``Compound("/", (functor, arity))`` shape other
      builtins in this package (``database_ops.py``) build and consume;
    - a runtime ``Div`` node (``clausal.pythonic_ast.nodes.Div``, re-exported
      from ``clausal.terms``) — what a user-written ``Fib/2`` ACTUALLY
      compiles to in today's surface: ``/`` is the arithmetic operator, so a
      structural (non-``is``) use of it stays reified as ``Div(left=...,
      right=...)`` rather than a cell (operator nodes are structural terms,
      matched/constructed, not evaluated — see ``BinOp.__unify__``'s
      docstring).  Probed directly (P3-3 Task 8 fix round 1, F1):
      ``Fib/2`` compiles to ``Div(left=<the Fib PredicateMeta class>,
      right=2)`` when ``Fib`` is a declared predicate in scope, or
      ``Div(left=("fib",), right=2)`` when the left operand is an atom (a
      bare name, or — in the default ``-double_quotes(atom)`` mode — a
      ``"fib"`` literal); ``3/2`` (no predicate-denoting operand) compiles to
      ``Div(left=3, right=2)`` unchanged, which is exactly the shape this
      function must REJECT — a bare numeric ``/`` is not a predicate
      indicator, and ``left`` failing the ``PredicateMeta``-or-ATOM check
      below is what tells the two apart.  This is a sound discriminator, not
      a guess: it only recognizes the indicator shape when ``left`` denotes
      a NAME (a class or an atom) and ``right`` is a plain int, so it can
      never misread a genuine arithmetic ``Div`` whose left operand is a
      number or a string.  ``.left``/``.right`` are dereffed before the type checks —
      the same access pattern ``arith_to_ast_expr`` uses for a ``Div`` node
      reached through ``is/2`` (``clausal/logic/compiler/terms_to_ast.py``
      ``deref(term.left)`` / ``deref(term.right)``) — since either slot may
      hold a trail-bound Var.

    Returns ``(name, arity, pred_cls)`` — *name* the identifier SPELLING —
    or ``None`` if *val* is not one of those three shapes with a name that is
    an ATOM (or a ``PredicateMeta`` class, reduced to its ``__name__``) and a
    non-bool int arity.  A plain ``str`` name is a STRING and answers
    ``None`` (Task 12).

    *pred_cls* is the class itself when the left operand WAS one, and ``None``
    otherwise (final review M-a).  The name alone is not enough to find the
    predicate: an ``-import_from``'d class lives on the EXPORTER's row, so
    reducing it to ``__name__`` and looking that up in the calling database
    turned ``listing(qq/1)`` into an ``existence_error`` for a predicate the
    caller can see and call.  The class knows its own row; the name does not.
    """
    pred_cls = None
    if type(val) is tuple and len(val) == 3 and val[0] == "/":
        name, arity = deref(val[1]), deref(val[2])
    elif isinstance(val, Compound) and val.functor == "/" and len(val.args) == 2:
        name, arity = deref(val.args[0]), deref(val.args[1])
    elif isinstance(val, Div):
        name, arity = deref(val.left), deref(val.right)
    else:
        return None
    if isinstance(name, PredicateMeta):
        pred_cls = name
        name = name.__name__
    elif _term_is_atom(name):
        # THE FLIP (spec §6.4): the name half of a predicate indicator is an
        # ATOM, so ``r30_foo/1`` written in source arrives as the arity-0
        # cell ``("r30_foo",)``.
        name = spelling(name)
    else:
        # Task 12: the Stage A arm that also read a plain ``str`` as the name
        # is deleted.  A ``str`` here is a STRING, not a name — the caller
        # (``listing/1``) turns this ``None`` into ``type_error(predicate,
        # …)``, the same refusal a bare string argument gets.  The engine's
        # own indicator BUILDERS (``database_ops.py``'s ``Compound("/",
        # (functor, arity))``) hold the spelling, but they build error terms;
        # nothing feeds one back in here.
        return None
    if not isinstance(arity, int) or isinstance(arity, bool):
        return None
    if arity < 0:
        return None
    return name, arity, pred_cls


def _indicator_operands(val):
    """The two operands of an indicator-SHAPED *val*, dereffed, or ``None``.

    Shape only — it says nothing about whether the operands are well formed,
    which is exactly what the instantiation-vs-type distinction needs
    (final review M-a).
    """
    if type(val) is tuple and len(val) == 3 and val[0] == "/":
        return deref(val[1]), deref(val[2])
    if isinstance(val, Compound) and val.functor == "/" and len(val.args) == 2:
        return deref(val.args[0]), deref(val.args[1])
    if isinstance(val, Div):
        return deref(val.left), deref(val.right)
    return None


def _indicator_row(db, name, arity, pred_cls):
    """The row whose clauses ``listing/1`` should print, or ``None``.

    Three lookups, in the order that makes an indicator name the same
    predicate the equivalent GOAL would (final review M-a):

    1. the CLASS's own bound row, when the indicator's left operand was a
       class and its row is a REAL row at the requested arity.  A shared
       ``-import_from``'d class reads the exporter's row, which is the whole
       point: ``listing(qq/1)`` must print what ``listing(qq)`` prints.  A
       DETACHED row is skipped — it is nobody's predicate (same rule
       ``PredicateMeta._bind_row`` applies), so a standalone class of the
       same name must not shadow the caller's real one;
    2. the calling database's own row — the ordinary local predicate;
    3. the calling module's NAMESPACE, resolved exactly as
       ``higher_order._namespace_dispatch`` resolves a named goal
       (``_find_pred_cls`` for the arity-checked class, then ``_home_db``
       for the row it actually reads), so the str spelling
       ``listing("qq"/1)`` finds the same imported predicate the class
       spelling does.
    """
    if pred_cls is not None:
        row = pred_cls._row
        if row is not None and not row.detached and row.key[1] == arity:
            return row
    if db is None:
        return None
    row = db.row(name, arity, create=False)
    if row is not None:
        return row
    from clausal.logic.builtins.database_ops import (  # noqa: PLC0415
        _find_pred_cls, _home_db,
    )
    module_dict = getattr(db, "module_dict", None)
    if module_dict is None:
        return None
    found = _find_pred_cls(name, arity, module_dict)
    if found is None:
        return None
    return _home_db(db, found).row(found.__name__, arity, create=False)


@_db_builtin("listing", 1, fields=("pred",))
def _make_listing__1(db):
    """Factory for ``listing/1`` — captures *db* so a predicate-name ATOM
    or a ``Name/Arity`` indicator can be resolved to a row.

    P3-3 Task 8: migrated off a bare class-only builtin.  The class/instance/
    ``BuiltinPredicate`` argument shapes need no database at all — a
    ``PredicateMeta``'s ``_clauses`` has read through its row since Task 2 —
    so ``db=None`` (the db-less path ``get_builtin_dispatch("listing", 1,
    None)`` and ``tests/test_listing.py`` exercise) keeps working for those
    three exactly as before.  The two NEW shapes below (a name ATOM, a
    ``Name/Arity`` indicator) genuinely need a database to resolve against,
    and raise the pre-existing ``type_error`` when there isn't one.
    """
    def _listing__1(pred, trail, k):
        """listing(Pred) — print all clauses of a predicate to stdout.

        Accepts:
          - a PredicateMeta class or instance (resolves to class)
          - a BuiltinPredicate (prints the "% name/arity — builtin" line)
          - an atom naming a predicate (NEW, P3-3 Task 8) — the arity-0
            cell ``("foo",)`` (the atoms-as-cells design's §6.4; a bare
            ``str`` is a STRING and raises ``type_error(predicate, …)``)
          - a ``Name/Arity`` indicator (NEW, P3-3 Task 8): the cell
            ``('/', name, arity)``, the engine's ``Compound("/", (name,
            arity))``, or -- what a user-written ``Fib/2`` actually
            compiles to in today's surface, since ``/`` is arithmetic and
            a structural (non-``is``) use of it stays a reified operator
            term -- a runtime ``Div`` node whose (dereffed) left operand is
            a ``PredicateMeta`` class or a str and whose right operand is a
            non-bool int.
        """
        val = deref(pred)

        # Recognize a Name/Arity indicator (cell, Compound, or a runtime
        # Div node) BEFORE the generic term-instance resolution below:
        # Compound and Div are both (perhaps surprisingly) @dataclass, so
        # is_term_instance() would otherwise swallow an indicator-shaped
        # value -- whether or not it turns out to be a WELL-FORMED
        # indicator -- and either treat it as a bare class with no fields
        # of its own, or (for an ill-formed Div like 3/2, a genuine
        # arithmetic expression) report the wrong culprit in the resulting
        # type_error (the Div CLASS instead of the actual Div instance).
        # Gating on the TYPE, not on whether _as_name_arity_indicator
        # actually parsed it, keeps the raised error's culprit the real
        # value in both the well-formed and the rejected case.
        is_indicator_shaped = (
            type(val) is tuple and len(val) == 3 and val[0] == "/"
        ) or isinstance(val, (Compound, Div))
        # Spec §6.4: ``listing/1`` accepts an ATOM as the predicate name —
        # the arity-0 cell ``("z0",)`` names z0/0.  A bare ``str`` is a
        # STRING after THE FLIP and is NOT a name: it falls through to the
        # ``type_error(predicate, …)`` at the bottom of this function.
        indicator = None if _term_is_atom(val) else _as_name_arity_indicator(val)

        # Accept an instance → resolve to its class
        if (
            indicator is None
            and not _term_is_atom(val)
            and not is_indicator_shaped
            and is_term_instance(val)
        ):
            val = type(val)

        if isinstance(val, PredicateMeta):
            name = val.__name__
            arity = len(term_field_names_of_class(val))
            clauses = val._clauses
        elif isinstance(val, BuiltinPredicate):
            name = val._functor
            arity = val._arity
            print(f"% {name}/{arity} — builtin")
            yield None
            return
        else:
            pred_cls = None
            if _term_is_atom(val):
                name, arity = spelling(val), 0
            elif indicator is not None:
                name, arity, pred_cls = indicator
            else:
                # An indicator-SHAPED value with an unbound operand is not a
                # malformed indicator, it is an unfinished one (final review
                # M-a): ``listing(X/2)`` gave a type_error naming the whole
                # Div, which reads as "``/`` is the wrong sort of term here"
                # when the term is right and only the variable is missing.
                operands = _indicator_operands(val)
                if operands is not None and any(is_var(o) for o in operands):
                    raise LogicException(instantiation_error(
                        "listing/1: the predicate indicator is not "
                        "sufficiently instantiated — bind Name/Arity before "
                        "listing it",
                    ))
                raise LogicException(type_error("predicate", val, "listing/1"))
            if db is None and pred_cls is None:
                raise LogicException(type_error("predicate", val, "listing/1"))
            row = _indicator_row(db, name, arity, pred_cls)
            if row is None:
                raise LogicException(existence_error(
                    "procedure", Compound("/", (name, arity)), "listing/1",
                ))
            clauses = row.clauses

        if not clauses:
            print(f"% {name}/{arity} — no clauses")
        else:
            print(f"% {name}/{arity} — {len(clauses)} clause(s)")
            for clause in clauses:
                print(_format_clause(clause))
        yield None
    return _listing__1


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
