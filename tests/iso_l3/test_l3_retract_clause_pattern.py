"""retract/1 matches the clause pattern ISO 8.9.3 describes.

retract(Head) is retract((Head :- true)): it removes a FACT.  It used to
test the head plus every ``Unify`` in the body, so ``retract(r(_))``
removed the RULE ``r(X) :- X = 1`` (Scryer removes the fact ``r(2)``), and
``retract((r(X) :- X = 1))`` removed nothing.  Every answer below is
Scryer's for the same program (2026-09-30)."""
from __future__ import annotations

import pytest

SRC = """\
:- dynamic(r/1).
r(X) :- X = 1.
r(2).
t1(L) :- retract(r(_)), findall(Y, r(Y), L).
t3(L) :- retract((r(X) :- X = 1)), findall(Y, r(Y), L).
t4(L) :- retract((r(_) :- _)), findall(Y, r(Y), L).
t5(L) :- retract((r(_) :- X = 1)), findall(Y, r(Y), L), L = [_|_], X = X.
"""


def test_retract_pattern(native, ans):
    # t4: retract/1 is re-executable -- its second answer removes r(2)
    for name, want in (("t1", [[1]]), ("t3", [[2]]), ("t4", [[2], []]),
                       ("t5", [[2]])):
        mod = native.load(f"l3_retract_{name}", SRC)
        assert ans(mod, name) == want, name


def test_retract_of_a_rule_body_binds_it(native, ans):
    """Scryer: [_ = 1, true] -- the rule's body, then (re-executed) the
    fact's."""
    mod = native.load("l3_retract_bind",
                      ":- dynamic(r/1).\nr(X) :- X = 1.\nr(2).\n"
                      "t(B) :- retract((r(_) :- B)).\n")
    b1, b2 = ans(mod, "t")
    assert b1[0] == "=" and b1[2] == 1
    assert b2 is True


def test_retractall_matches_the_head_whatever_the_body(tmp_path):
    """retractall(Head) removes every clause whose HEAD unifies (ISO 8.9.5).
    A seam rule's own ``X is 3`` (a unification) used to read as a head
    test, keeping ``h(X) <- (X is 3)`` out of ``retractall(h(5))``.
    Scryer, for ``h(X) :- X = 3. h(7).``: t1 [7], t2 [], t3 []."""
    from clausal.import_hook import _load_module
    from clausal.logic.solve import _deref_walk, solve
    from clausal.logic.variables import Var
    for name, goal, want in (("t1", "5", [7]), ("t2", "7", []),
                             ("t3", "_", [])):
        p = tmp_path / f"_retractall_{name}.clausal"
        p.write_text("-allow_singletons\n-dynamic(h/1)\nh(X) <- (X is 3)\nh(7),\n"
                     f"t(L) <- (retractall(h({goal})), findall(Y, h(Y), L))\n")
        m = _load_module(f"_retractall_{name}", str(p))
        v = Var()
        assert [_deref_walk(v) for _ in solve(("t", v), m)] == [want], name


def test_more_patterns(native, ans):
    """Scryer: a fact with a compound argument retracts by its value;
    a multi-goal rule body matches as a conjunction (the ','/2 cell against
    the engine's flat body tuple); retract(Head) of a predicate with only
    rules fails."""
    src = (":- dynamic(f/1).\n:- dynamic(g/1).\n:- dynamic(q/1).\n"
           "f(p(1, [a])).\nf(p(2, [b])).\n"
           "g(X) :- X = 1, X > 0.\ng(5).\n"
           "q(X) :- X = 1.\n"
           "t1(L) :- retract(f(p(2, _))), findall(Y, f(Y), L).\n"
           "t2(L) :- retract((g(X) :- X = 1, X > 0)), findall(Y, g(Y), L).\n"
           "t3(L) :- findall(x, retract(q(_)), L).\n")
    for name, want in (("t1", [[("p", 1, ["a"])]]), ("t2", [[5]]),
                       ("t3", [[]])):
        mod = native.load(f"l3_retract_more_{name}", src)
        assert ans(mod, name) == want, name


def test_clause_2_with_a_conjunction_body(native, ans):
    """clause(g(X), (X = 1, X > 0)) finds the rule; a disjunction matches
    too; a left-nested pattern does not.  Scryer: c1 [x], c2 [], c3 [x],
    c4 []."""
    mod = native.load("l3_clause_conj",
                      ":- dynamic(g/1).\n"
                      "g(X) :- X = 1, X > 0, X < 5.\n"
                      "g(X) :- (X = 1 ; X = 2).\n"
                      "c1(L) :- findall(x, clause(g(Y), (Y = 1, Y > 0, Y < 5)), L).\n"
                      "c2(L) :- findall(x, clause(g(Y), ((Y = 1, Y > 0), Y < 5)), L).\n"
                      "c3(L) :- findall(x, clause(g(Y), (Y = 1 ; Y = 2)), L).\n"
                      "c4(L) :- findall(x, clause(g(Y), (Y = 1, Y > 0)), L).\n")
    assert ans(mod, "c1") == [["x"]]
    assert ans(mod, "c2") == [[]]
    assert ans(mod, "c3") == [["x"]]
    assert ans(mod, "c4") == [[]]


def test_open_tail_and_negation_patterns(native, ans):
    """(G, Rest) with Rest unbound takes the remaining goals; \\+ G matches
    a negation.  Scryer: c2 [X = 1], c3 [], c4 [x], c5 [x]."""
    src = (":- dynamic(g/1).\n"
           "g(X) :- X = 1, X > 0, X < 5.\n"
           "g(X) :- \\+ X = 2.\n"
           "c1(R) :- clause(g(_), (_, R)).\n"
           "c2(L) :- findall(F, clause(g(_), (F, _, _)), L).\n"
           "c3(L) :- findall(x, clause(g(_), (_, _, _, _)), L).\n"
           "c4(L) :- findall(x, clause(g(Y), \\+ Y = 2), L).\n"
           "c5(L) :- retract((g(_) :- _, _)), findall(x, clause(g(_), _), L).\n")
    for name, check in (
            ("c1", lambda r: len(r) == 1 and [g[0] for g in r[0]] == [">", "<"]),
            ("c2", lambda r: len(r) == 1 and [g[0] for g in r[0]] == ["="]),
            ("c3", lambda r: r == [[]]),
            ("c4", lambda r: r == [["x"]]),
            ("c5", lambda r: r == [["x"]])):
        mod = native.load(f"l3_open_tail_{name}", src)
        got = ans(mod, name)
        assert check(got), (name, got)


def test_a_clause_with_no_term_form(tmp_path):
    """A clause holding a Python expression has no term form: clause/2 and
    retractall/1 refuse it with permission_error when it may match;
    retract(Head) skips it (it is no fact)."""
    from clausal.import_hook import _load_module
    from clausal.logic.exceptions import LogicException, render_error_term
    from clausal.logic.solve import _deref_walk, solve
    from clausal.logic.variables import Var
    p = tmp_path / "_no_term_form.clausal"
    p.write_text("-allow_singletons\n-dynamic(h/1)\n-dynamic(k/2)\n"
                 "h(X) <- (Y is ++(X + 1))\n"
                 "k(A, ++(A + 1)) <- True\n"
                 "t2(R) <- retract(h(_))\n"
                 "t3(R) <- retractall(k(_, _))\n"
                 "t5(R) <- retract(':-'(h(_), _))\n")
    m = _load_module("_no_term_form", str(p))
    v = Var()
    assert [_deref_walk(v) for _ in solve(("t2", v), m)] == []
    for goal in ("t3", "t5"):
        with pytest.raises(LogicException) as ei:
            list(solve((goal, Var()), m))
        assert "permission_error(access,private_procedure" in render_error_term(
            ei.value.term), goal


REEXEC = """\
:- dynamic(s7/1).
:- dynamic(k/1).
s7(a). s7(b). s7(a).
t1(R) :- findall(X, retract(s7(X)), R).
t2(R) :- findall(X, retract(s7(X)), _), findall(Y, s7(Y), R).
t3(R) :- assertz(k(1)), assertz(k(2)), findall(X, (retract(k(X)), assertz(k(9))), R0), findall(Y, k(Y), R1), R = R0-R1.
t4(R) :- once(retract(s7(X))), R = X.
"""


def test_retract_is_re_executable(native, ans):
    """ISO 8.9.3.1: on backtracking retract/1 removes the next match, over
    the clauses as they were at the call (a clause asserted meanwhile is
    not seen).  It committed to the first match.  Scryer's answers."""
    for name, want in (("t1", [["a", "b", "a"]]), ("t2", [[]]),
                       ("t3", [("-", [1, 2], [9, 9])]), ("t4", ["a"])):
        mod = native.load(f"l3_retract_reexec_{name}", REEXEC)
        assert ans(mod, name) == want, name
