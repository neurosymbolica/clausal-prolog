"""The seam's ``if_/3`` requires a REIFIABLE condition (operator ruling
2026-10-01), as Scryer's library(reif) does and as the native ``.pl`` front
end already did:

    if_(If_1, Then_0, Else_0) :- call(If_1, T), (T == true -> Then_0 ; ...)

* a plain goal (``atom(X)``, ``p(X)`` with no ``p/2``, ``not G``, ``X in L``,
  ``once(G)``, ``True``) is refused when the file loads -- it used to run as
  a soft cut (every solution of the goal, the else branch only when there
  were none), which is not monotone;
* a closure condition is called with the truth value appended, and every way
  it answers is a solution -- the seam and the ``.pl`` give the same answers
  (Scryer, measured 2026-10-01: ``[a-yes, b-yes, _-no]`` for the memberd_t
  row, ``[a-b-y, a-_-n, _-_-n]`` for the conjunction row).
"""
from __future__ import annotations

import textwrap

import pytest

from clausal.logic.variables import is_var


def _load(native, name, text, **kw):
    return native.load(name, textwrap.dedent(text), **kw)


def _seam(native, name, text):
    return _load(native, name, text, suffix=".seam", frontend=None)


# ── the refusal ──


@pytest.mark.parametrize("cond", [
    "atom(X)",            # a type test: there is no atom/2
    "p(X)",               # a plain predicate: p/1 exists, p/2 does not
    "not p(X)",
    "X in [1, 2]",
    "once(p(X))",
    "True",
], ids=["type-test", "plain-predicate", "not", "in", "once", "literal"])
def test_a_plain_goal_condition_is_refused_at_load(native, cond):
    from clausal.logic.compiler.terms_to_goalop import (
        NonReifiableConditionError,
    )
    src = f"""\
        -private([yes, no])
        p(1),
        q(X, R) <- if_({cond}, R is yes, R is no)
        """
    with pytest.raises(NonReifiableConditionError) as info:
        _seam(native, "ifr_refused", src)
    err = info.value
    assert isinstance(err, SyntaxError)
    msg = str(err)
    assert "if_/3 requires a reifiable condition in predicate q/2" in msg
    assert "(line 3)" in msg
    assert "soft cut" in msg


def test_the_refusal_names_the_reified_form(native):
    from clausal.logic.compiler.terms_to_goalop import (
        NonReifiableConditionError,
    )
    with pytest.raises(NonReifiableConditionError,
                       match=r"there is no p/2.*p_t/2.*if_\(p_t\("):
        _seam(native, "ifr_hint", "p(1),\nq(X) <- if_(p(X), true, fail)\n")


# ── a closure condition: Scryer's answers, on both front ends ──


def _rows(rows):
    return [tuple("_" if is_var(v) else v for v in r) for r in rows]


def test_a_reified_closure_backtracks_as_on_the_pl(native, ans):
    pl = _load(native, "ifr_memberd_pl", """\
        :- use_module(library(reif)).
        q(X, R) :- if_(memberd_t(X, [a, b]), R = yes, R = no).
        """)
    seam = _seam(native, "ifr_memberd_seam", """\
        -import_from(clausal.stdlib.reif, [memberd_t])
        -private([a, b, yes, no])
        q(X, R) <- if_(memberd_t(X, [a, b]), R is yes, R is no)
        """)
    want = [("a", "yes"), ("b", "yes"), ("_", "no")]     # Scryer
    assert _rows(ans(pl, "q", 2)) == want
    assert _rows(ans(seam, "q", 2)) == want


def test_a_conjunction_of_reified_tests_matches_the_pl(native, ans):
    pl = _load(native, "ifr_conj_pl", """\
        :- use_module(library(reif)).
        q(X, Y, R) :- if_((X = a, Y = b), R = y, R = n).
        """)
    seam = _seam(native, "ifr_conj_seam", """\
        -private([a, b, y, n])
        q(X, Y, R) <- if_((X is a, Y is b), R is y, R is n)
        """)
    want = [("a", "b", "y"), ("a", "_", "n"), ("_", "_", "n")]   # Scryer
    assert _rows(ans(pl, "q", 3)) == want
    assert _rows(ans(seam, "q", 3)) == want


def test_a_user_closure_and_reifs_equals_3(native, ans):
    seam = _seam(native, "ifr_user", """\
        -private([a, yes, no])
        small_t(X, T) <- if_(X < 3, T is True, T is False)
        q(X, R) <- if_(small_t(X), R is yes, R is no)
        e(X, R) <- if_('='(X, a), R is yes, R is no)
        """)
    assert ans(seam, "q", 2, 1) == ["yes"]
    assert ans(seam, "q", 2, 5) == ["no"]
    assert ans(seam, "e", 2, "a") == ["yes"]
    assert _rows(ans(seam, "e", 2)) == [("a", "yes"), ("_", "no")]


def test_a_closure_answering_no_boolean_is_scryers_error(native, ans):
    pl = _load(native, "ifr_err_pl", """\
        :- use_module(library(reif)).
        w(_, maybe).
        e(E) :- catch(if_(w(1), true, true), error(E, _), true).
        """)
    seam = _seam(native, "ifr_err_seam", """\
        -private([maybe])
        w(_, maybe),
        e(E) <- catch(if_(w(1), True, True), error(E, _), True)
        """)
    assert ans(pl, "e") == [("type_error", "boolean", "maybe")]
    assert ans(seam, "e") == ans(pl, "e")


def test_call_of_an_if_term_takes_the_closure_too(native, ans):
    """call/1 of an ``if_`` TERM: the runtime conversion gives the closure
    the same reif meaning as the compiled clause."""
    seam = _seam(native, "ifr_call", """\
        -import_from(clausal.stdlib.reif, [memberd_t])
        -private([a, b, yes, no])
        q(X, R) <- (G is if_(memberd_t(X, [a, b]), R is yes, R is no), call(G))
        """)
    assert _rows(ans(seam, "q", 2)) == [("a", "yes"), ("b", "yes"), ("_", "no")]
