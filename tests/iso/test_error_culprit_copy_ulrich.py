"""Regression: an ISO builtin error must COPY its culprit (and context) at
raise time.

Found by a diagnostic sweep of Ulrich Neumerkel's ``variable_names/1``
conformity page
(https://www.complang.tuwien.ac.at/ulrich/iso-prolog/variable_names):
``clausal/logic/exceptions.py``'s ``_error()`` used to embed the culprit
(and context) term the builtin handed it BY REFERENCE.  When a builtin
raises mid-conjunction -- e.g. ``N = 'X', write_term(T,
[variable_names([N=T])])`` after ``N`` was already bound earlier in the
same clause -- the raised term held the caller's live ``Var`` object, not
a snapshot.

That matters in two separate ways (both are ISO 7.8.9/7.8.10 requirements,
both pinned below):

1. An UNCAUGHT exception (no ``catch/3``, or one that does not match)
   propagates by unwinding ``solve()``'s generator chain -- a clause body
   is nested sub-generators, one per conjunct -- and each suspended
   frame's cleanup undoes the trail back to its own mark on the way out,
   unbinding whatever it bound -- including ``N`` -- before the exception
   ever reaches the code that reads ``.term``.  So the printed top-level
   error showed ``variable_names([_=_])`` with everything unbound, instead
   of ``variable_names(['X'=_])``.  A ``catch/3`` that MATCHES is a
   different path for THIS symptom: its handler is an inline
   ``try/except`` wrapped directly around the goal, so it reads ``.term``
   before anything unwinds -- see ``_compile_catch_impl`` in
   ``clausal/logic/compiler/control_constructs.py``.  This file drives the
   write_term/atom_length rows UNCAUGHT, straight out of ``solve()``, to
   exercise exactly that path.

2. Independently of (1) -- and this DOES affect a matching ``catch/3``,
   contrary to an earlier draft of this fix's commit message -- a
   culprit's genuinely-still-unbound variables must come back as FRESH,
   independent variables (``copy_term/2`` semantics, what ``throw/1``
   already does via ``globals_env._throw_ball``), not the caller's own Var
   objects shared by reference.  Before the fix, binding the COPY's
   variable under a catch/3 handler could retroactively affect the
   caller's own variable (and vice versa) because they were the same
   Python object; Scryer never shares them.  c1/c2/c3 below pin this
   directly, under a MATCHING catch/3, where (1) was never the problem.

See ``clausal.logic.exceptions._copy_at_raise_time`` for the fix and the
cyclic-culprit (``RecursionError``) fallback it needed (row_cyclic_*
below).

Most of this file tests an internal identity/timing bug in Clausal's own
exception construction (whether a term comes back by reference or as a
snapshot), not an ISO ANSWER Clausal and Scryer might disagree on, so it
needs no running Scryer oracle to drive it.  c1-c3 are the exception:
they pin a specific ISO ANSWER (copy_term/2 semantics under a matching
catch/3), and are Scryer-verified by hand (see the review that found
F1-F7, 2026-10-15).
"""

from __future__ import annotations

import sys
import textwrap

import pytest

import clausal.import_hook  # noqa: F401 -- installs the meta-path finder
from clausal.import_hook import _load_prolog_module
from clausal.logic.exceptions import LogicException, render_error_term
from clausal.logic.solve import solve
from clausal.logic.variables import Trail, Var, deref, is_var, unify
from clausal.terms import term_writeq


def _raise_text(mod, goal_name: str) -> str:
    """Drive ``goal_name(R)`` to its first answer and return the writeq
    text of the LogicException it raises, uncaught, straight out of
    ``solve()`` -- the path point (1) in the module docstring describes.
    Fails the test outright if the goal does not raise.

    The exception is caught and ``.term`` read in the SAME except clause,
    immediately -- nothing else runs between the raise and the read that
    could backtrack further (the correctness trap the task names: this is
    not the "deref after generator exhaustion" bug, which is about reading
    a SUCCESSFUL answer after searching past it)."""
    r = Var()
    try:
        next(iter(solve((goal_name, r), mod)))
    except LogicException as exc:
        return render_error_term(exc.term)
    pytest.fail(f"{goal_name}(R) did not raise")


def _answer_text(mod, goal_name: str) -> str:
    """Drive ``goal_name(R)`` to its first answer and return R's writeq
    text.  Fails the test if the goal raises, or has no answer at all."""
    r = Var()
    try:
        next(iter(solve((goal_name, r), mod)))
    except LogicException as exc:
        pytest.fail(f"{goal_name}(R) raised unexpectedly: "
                    f"{render_error_term(exc.term)}")
    else:
        return term_writeq(deref(r), local_vars=True)
    pytest.fail(f"{goal_name}(R) had no answer")


# ── The program ────────────────────────────────────────────────────────────

_PROGRAM = textwrap.dedent(r"""
    % -- control: a bound variable embedded in a RAW (non-indicator) culprit,
    % the general-purpose case any ISO type_error can hit. ``N = foo(Y), Y =
    % bar`` binds Y, nested inside the compound N is already bound to; by the
    % time atom_length/2 raises type_error(atom, N-as-deref'd), Y reads
    % 'bar' -- unless the culprit is a live reference, in which case the
    % unwind back out of this clause's frame (no catch/3 here) unbinds it
    % again before the Python caller reads exc.term.
    row_nested_bound(R) :-
        N = foo(Y),
        Y = bar,
        atom_length(N, R).

    % -- the mirror case: Y is genuinely never bound.  The copy must leave
    % it a free variable, not spuriously ground it to something left over
    % from the copy machinery.
    row_nested_unbound(R) :-
        N = foo(_Y),
        atom_length(N, R).

    % -- Ulrich's variable_names page, row 1: an atom bound earlier, nested
    % inside the option term write_term/2 rejects as unsupported. The
    % domain_error is CORRECT (write_term/2 does not implement
    % variable_names/1 yet -- a separate, bigger fix); only the culprit's
    % N=X pair is under test here.
    row_ulrich_atom(R) :-
        N = 'X',
        write_term(T, [variable_names([N=T])]),
        R = T.

    % -- Ulrich's page, row 2: same shape, N bound to an integer, plus a
    % second, unrelated option ahead of it in the list (quoted(true)) to
    % confirm the copy walks the WHOLE formal term, not just its first
    % element.
    row_ulrich_int(R) :-
        N = 7,
        write_term(T, [quoted(true), variable_names([N=T])]),
        R = T.

    % -- instantiation_error's culprit-free shape must still work (no
    % culprit at all to copy -- the formal term is the bare atom
    % 'instantiation_error').
    row_instantiation(R) :-
        atom_length(_, R).

    % -- c1/c2/c3 (review F3): a MATCHING catch/3, where point (1) in the
    % module docstring was never the problem -- the handler always read
    % the culprit before any unwind, caught or not.  What was wrong is
    % point (2): the culprit's still-unbound Y shared identity with the
    % caller's own Y.  Scryer-verified: c1 distinct, c2 f(_), c3 _.

    c1(R) :-
        X = f(Y),
        catch(atom_length(X, _), error(type_error(_, C), _), true),
        C = f(Z),
        c1_result(Z, Y, R).

    c1_result(Z, Y, shared) :- Z == Y.
    c1_result(Z, Y, distinct) :- Z \== Y.

    c2(R) :-
        X = f(Y),
        catch(atom_length(X, _), error(type_error(_, C), _), true),
        Y = 1,
        R = C.

    c3(R) :-
        X = f(Y),
        catch(atom_length(X, _), error(type_error(_, C), _), true),
        C = f(2),
        R = Y.

    % -- F1: a CYCLIC culprit (no occurs check) must still raise the ISO
    % error, not a RecursionError escaping from inside _error() itself.
    row_cyclic_caught(R) :-
        X = f(X),
        catch(atom_length(X, _), error(_, _), R = err).

    row_cyclic_uncaught(R) :-
        X = f(X),
        atom_length(X, R).
""")


@pytest.fixture(scope="module")
def mod(tmp_path_factory):
    d = tmp_path_factory.mktemp("errcopy_ulrich")
    path = d / "_errcopy_ulrich.pl"
    path.write_text(_PROGRAM)
    sys.path.insert(0, str(d))
    try:
        return _load_prolog_module("_errcopy_ulrich", str(path))
    finally:
        sys.path.remove(str(d))


def test_bound_value_nested_in_a_raw_culprit_survives_the_raise(mod):
    """type_error(atom, foo(Y)) with Y bound to bar at raise time must
    print foo(bar), not foo(_) -- the direct reproduction of the bug
    outside write_term/2, with no catch/3 anywhere in the clause."""
    assert _raise_text(mod, "row_nested_bound") == (
        "error(type_error(atom,foo(bar)),atom_length/2)")


def test_genuinely_unbound_value_stays_a_free_variable(mod):
    """The mirror case: Y is never bound, so the copy must leave it free --
    not spuriously grounded to whatever the copy machinery touched last."""
    assert _raise_text(mod, "row_nested_unbound") == (
        "error(type_error(atom,foo(_)),atom_length/2)")


def test_ulrich_row_atom_culprit_shows_the_bound_pair(mod):
    """N = 'X' bound before write_term/2 raises; domain_error(write_option,
    variable_names(['X'=_])) must show 'X', not variable_names([_=_])."""
    text = _raise_text(mod, "row_ulrich_atom")
    assert "variable_names(['X'=_])" in text, text
    assert "domain_error(write_option," in text, text


def test_ulrich_row_integer_culprit_shows_the_bound_pair(mod):
    text = _raise_text(mod, "row_ulrich_int")
    assert "variable_names([7=_])" in text, text
    assert "domain_error(write_option," in text, text


def test_instantiation_error_has_no_culprit_to_copy(mod):
    """A culprit-free formal term (the bare atom instantiation_error) must
    pass through the fix untouched -- no culprit, nothing to snapshot."""
    assert _raise_text(mod, "row_instantiation") == (
        "error(instantiation_error,atom_length/2)")


# ── Direct structural check: the unbound slot really is a FREE variable ──
#
# The writeq-text assertions above already distinguish "_" from "bar"/"'X'"
# /"7", but this additionally proves the free slot is not merely rendered
# as "_" by accident (e.g. a value that happens to str() that way) -- it is
# read back into Python and checked with is_var/deref, then unified with an
# arbitrary term to confirm nothing upstream already bound it.


def test_unbound_slot_is_a_real_unbound_var_not_a_lookalike(mod):
    r = Var()
    try:
        next(iter(solve(("row_nested_unbound", r), mod)))
        pytest.fail("row_nested_unbound(R) did not raise")
    except LogicException as exc:
        formal = exc.term[1]       # (type_error, atom, foo(Y))
        culprit = deref(formal[2])  # foo(Y)
        y = deref(culprit[1])       # Y, as copied
        assert is_var(y), y
        trail = Trail()
        assert unify(y, "probe", trail)
        assert deref(y) == "probe"


# ── c1-c3 (F3): the fresh-variable half of the fix, under a MATCHING
# catch/3 -- confirms the culprit's unbound variable is no longer the
# SAME object as the caller's, in both directions (binding either one
# must not affect the other).  A mutant that only derefs (no actual
# fresh-var copying) passes every test above but fails all three of
# these.


def test_c1_copied_variable_is_distinct_from_the_callers(mod):
    assert _answer_text(mod, "c1") == "distinct"


def test_c2_binding_the_callers_variable_does_not_touch_the_copy(mod):
    assert _answer_text(mod, "c2") == "f(_)"


def test_c3_binding_the_copy_does_not_touch_the_callers_variable(mod):
    assert _answer_text(mod, "c3") == "_"


# ── F1: a cyclic culprit must still raise the ISO error ──────────────────


def test_cyclic_culprit_still_raises_the_iso_error_not_recursion_error(mod):
    """X = f(X), atom_length(X, R): the UNCAUGHT path.  Before the fix,
    _copy_at_raise_time's _deref_walk recursed without bound on the cycle
    and a bare RecursionError escaped from inside _error() -- before any
    LogicException existed, so no catch/3 pattern naming error(...) could
    ever have matched it."""
    r = Var()
    with pytest.raises(LogicException) as caught:
        next(iter(solve(("row_cyclic_uncaught", r), mod)))
    # Not asserting the exact culprit shape: a cyclic term's content is
    # exactly what the fallback (return the UNCOPIED term) leaves
    # unresolved -- that is the documented trade-off, not a new promise.
    assert caught.value.term[1][0] == "type_error"


def test_cyclic_culprit_is_still_catchable_by_a_structural_pattern(mod):
    """X = f(X), catch(atom_length(X, _), error(_, _), R = err): a
    catch/3 catcher naming error(_, _) must still match -- it could not,
    if what actually came out of _error() were a raw RecursionError
    instead of the ISO term."""
    assert _answer_text(mod, "row_cyclic_caught") == "err"
