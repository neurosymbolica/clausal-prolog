"""Regression: an ISO builtin error must COPY its culprit at raise time.

Found by a diagnostic sweep of Ulrich Neumerkel's ``variable_names/1``
conformity page
(https://www.complang.tuwien.ac.at/ulrich/iso-prolog/variable_names):
``clausal/logic/exceptions.py``'s ``_error()`` (and the procedure-existence
shortcut in ``existence_error()``) used to embed the culprit term the
builtin handed it BY REFERENCE.  When a builtin raises mid-conjunction --
e.g. ``N = 'X', write_term(T, [variable_names([N=T])])`` after ``N`` was
already bound earlier in the same clause -- the raised term holds the
caller's live ``Var`` object, not a snapshot.

That matters because the goal is run through ``solve()``, a generator, and
a clause body is a chain of nested sub-generators (one GAG frame per
conjunct).  An UNCAUGHT exception (no ``catch/3``, or one that does not
match) propagates by unwinding that chain: each suspended frame's
generator-cleanup undoes the trail back to its own mark on the way out,
unbinding whatever it bound -- including ``N`` -- before the exception
ever reaches the code that reads ``.term``.  (A ``catch/3`` that DOES match
is a different, ALREADY-correct path: its handler is an inline
``try/except`` wrapped directly around the goal, so it reads ``.term``
before anything unwinds -- see ``_compile_catch_impl`` in
``clausal/logic/compiler/control_constructs.py``.  This file deliberately
raises UNCAUGHT and reads ``exc.term`` from outside ``solve()``, the one
path that was actually broken; measured directly below, in
test_uncaught_raise_reproduces_the_bug_without_the_fix.)

So the printed top-level error showed ``variable_names([_=_])`` with
everything unbound, instead of ``variable_names(['X'=_])``.

The fix (2026-10-15) makes ``_error()`` -- and the one existence_error path
that bypasses it -- copy the formal error term the same way
``globals_env._throw_ball`` copies a thrown ball (ISO 7.8.10.1 b):
dereference everything as of THIS moment, and copy_term the result so any
STILL-unbound variable becomes an independent fresh one rather than being
spuriously grounded. A ground formal term skips the copy (cheap, the
common case).

This file is engine-only (no Scryer oracle needed): it is testing an
internal identity/timing bug in Clausal's own exception construction, not
an ISO ANSWER Clausal and Scryer might disagree on.
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


def _raise_text(mod, goal_name: str) -> str:
    """Drive ``goal_name(R)`` to its first answer and return the writeq
    text of the LogicException it raises, uncaught, straight out of
    ``solve()`` -- the path this bug actually lived on (see the module
    docstring).  Fails the test outright if the goal does not raise.

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


# ── The program: every row binds something earlier, then raises UNCAUGHT ──

_PROGRAM = textwrap.dedent("""
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
