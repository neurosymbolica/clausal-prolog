"""I/O builtins (V2-15 + Phase 2): write/1, writeln/1, print_term/1, nl/0,
tab/1, write_to_string/2, term_to_string/2, listing/1, portray_clause/1."""

from __future__ import annotations

import sys as _sys

from clausal.logic.atoms import demangle_for_display, is_mangled
from clausal.logic.cells import TUPLE_TAG
from clausal.logic.variables import Var, deref, is_var, unify
from clausal.terms import term_str as _term_str, term_pformat as _term_pformat, Compound, Div
from clausal.logic.predicate import PredicateMeta, is_term_instance, term_field_names, term_field_names_of_class
from clausal.logic.exceptions import (
    LogicException, type_error, existence_error, instantiation_error,
)

from clausal.logic.builtins._registry import _builtin, _db_builtin, _DB_BUILTINS, BuiltinPredicate


def _format_term_for_io(val):
    """Format a dereffed value for I/O output.

    Strings pass through as-is (supports f-strings naturally) -- except a
    mangled (-hide) atom, which substitutes its human ``module.name`` form
    (P3-1 Task 6, design doc section 1b: "the writer renders the human
    form"; NOT a round-trip -- the human form re-reads as a different,
    unmangled term -- display only).  The raw runtime str is untouched;
    only what reaches write/1, writeln/1, write_to_string/2 changes.
    Other values use str() which auto-derefs Vars via __str__.
    """
    if isinstance(val, str):
        return demangle_for_display(val) if is_mangled(val) else val
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
        return _term_str(val)
    return str(val)


@_builtin("write", 1)
def _write__1(term, trail, k):
    """write(Term) — print dereffed term to stdout (no newline).

    Strings are printed without quotes.  Vars are auto-dereffed.
    Works naturally with f-strings: write(f"X is {X_}").
    """
    val = deref(term)
    _sys.stdout.write(_format_term_for_io(val))
    _sys.stdout.flush()
    yield None


@_builtin("writeln", 1)
def _writeln__1(term, trail, k):
    """writeln(Term) — print dereffed term to stdout with newline.

    Strings are printed without quotes.  Vars are auto-dereffed.
    Works naturally with f-strings: writeln(f"X is {X_}").
    """
    val = deref(term)
    print(_format_term_for_io(val))
    yield None


@_builtin("print_term", 1)
def _print_term__1(term, trail, k):
    """print_term(Term) — print structured term representation with newline.

    Uses term_str() for Prolog-style output showing term structure
    (e.g., functors, lists, operators).  Vars show as Var(_N).
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
    """write_to_string(Term, Result) — unify Result with the string representation of Term.

    Vars are auto-dereffed.  Strings pass through as-is.
    """
    val = deref(term)
    s = _format_term_for_io(val)
    mark = trail.mark()
    if unify(result, s, trail):
        yield None
    trail.undo(mark)


@_builtin("term_to_string", 2)
def _term_to_string__2(term, result, trail, k):
    """term_to_string(Term, Result) — unify Result with structured term_str representation."""
    from clausal.logic.solve import _deref_walk
    val = _deref_walk(term)
    s = _term_str(val)
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
    if isinstance(val, str):
        # P3-1 Task 6: listing/1's own argument formatting does not route
        # through term_str -- apply the same mangled-atom display
        # substitution directly (see term_str's str branch for the full
        # rationale; same display-only, no-round-trip guarantee).
        display = demangle_for_display(val) if is_mangled(val) else val
        return repr(display)
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
      ``Div(left='some_str', right=2)`` when the left operand is a string
      literal; ``3/2`` (no predicate-denoting operand) compiles to
      ``Div(left=3, right=2)`` unchanged, which is exactly the shape this
      function must REJECT — a bare numeric ``/`` is not a predicate
      indicator, and ``left`` failing the ``PredicateMeta``-or-``str`` check
      below is what tells the two apart.  This is a sound discriminator, not
      a guess: it only recognizes the indicator shape when ``left`` denotes
      a NAME (a class or a string) and ``right`` is a plain int, so it can
      never misread a genuine arithmetic ``Div`` whose left operand is a
      number.  ``.left``/``.right`` are dereffed before the type checks —
      the same access pattern ``arith_to_ast_expr`` uses for a ``Div`` node
      reached through ``is/2`` (``clausal/logic/compiler/terms_to_ast.py``
      ``deref(term.left)`` / ``deref(term.right)``) — since either slot may
      hold a trail-bound Var.

    Returns ``(name, arity, pred_cls)`` or ``None`` if *val* is not one of
    those three shapes with a name that is a str (or a ``PredicateMeta``
    class, reduced to its ``__name__``) and a non-bool int arity.

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
    if not isinstance(name, str) or not isinstance(arity, int) or isinstance(arity, bool):
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
    """Factory for ``listing/1`` — captures *db* so a bare predicate-name str
    or a ``Name/Arity`` indicator can be resolved to a row.

    P3-3 Task 8: migrated off a bare class-only builtin.  The class/instance/
    ``BuiltinPredicate`` argument shapes need no database at all — a
    ``PredicateMeta``'s ``_clauses`` has read through its row since Task 2 —
    so ``db=None`` (the db-less path ``get_builtin_dispatch("listing", 1,
    None)`` and ``tests/test_listing.py`` exercise) keeps working for those
    three exactly as before.  The two NEW shapes below (a bare str atom, a
    ``Name/Arity`` indicator) genuinely need a database to resolve against,
    and raise the pre-existing ``type_error`` when there isn't one.
    """
    def _listing__1(pred, trail, k):
        """listing(Pred) — print all clauses of a predicate to stdout.

        Accepts:
          - a PredicateMeta class or instance (resolves to class)
          - a BuiltinPredicate (prints the "% name/arity — builtin" line)
          - a bare str atom naming a predicate (NEW, P3-3 Task 8)
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
        indicator = None if isinstance(val, str) else _as_name_arity_indicator(val)

        # Accept an instance → resolve to its class
        if (
            indicator is None
            and not isinstance(val, str)
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
            if isinstance(val, str):
                name, arity = val, 0
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
