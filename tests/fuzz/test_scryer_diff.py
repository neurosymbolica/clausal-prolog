"""The differential fuzzer against Scryer (``tests/fuzz/scryer_diff.py``).

By default a fixed small seed set runs (a few hundred cases, a few
minutes): every case must agree with Scryer or be one of the known,
documented differences (``scryer_diff.NORMALISERS`` / ``TESTS``).  A larger
run::

    CLAUSAL_FUZZ_SEEDS=200 python -m pytest tests/fuzz/test_scryer_diff.py

runs seeds 0..199 (60 cases each).  The comparer's own pieces are tested
below without Scryer.
"""

from __future__ import annotations

import os

import pytest

from tests import _oracles
from tests.fuzz import scryer_diff as F

DEFAULT_SEEDS = [0, 1, 2, 3]
DEFAULT_CASES = 40


def _seeds():
    n = os.environ.get("CLAUSAL_FUZZ_SEEDS")
    if n:
        return list(range(int(n))), 60
    return DEFAULT_SEEDS, DEFAULT_CASES


def _need_scryer():
    if not os.path.exists(_oracles.SCRYER):
        if os.environ.get("CLAUSAL_ISO_ALLOW_NO_SCRYER"):
            pytest.skip(f"scryer not built at {_oracles.SCRYER}")
        pytest.fail(f"the Scryer oracle is not built at {_oracles.SCRYER}")


@pytest.mark.parametrize("python_twin", [False, True],
                         ids=["c_trampoline", "python_trampoline"])
def test_agrees_with_scryer_or_a_known_difference(tmp_path, python_twin):
    _need_scryer()
    seeds, count = _seeds()
    if python_twin and not os.environ.get("CLAUSAL_FUZZ_SEEDS"):
        seeds = seeds[:2]
    jobs = max(1, min(4, (os.cpu_count() or 2) // 2))
    total, report = F.fuzz(seeds, count, workdir=tmp_path,
                           python_twin=python_twin, jobs=jobs,
                           log=lambda *_: None)
    assert total == len(seeds) * count
    unexplained = [(full.case.label, small.case.goal_text(), small.clausal,
                    small.scryer)
                   for full, small, known in report if known is None]
    assert not unexplained, unexplained


# ── the comparer, without Scryer ─────────────────────────────────────────────

def test_the_generator_is_seeded():
    a = [c.goal_text() for c in F.generate(5, 20)]
    b = [c.goal_text() for c in F.generate(5, 20)]
    assert a == b
    assert a != [c.goal_text() for c in F.generate(6, 20)]
    # every goal kind the brief names turns up in a modest sample
    text = " ".join(c.goal_text() for s in range(10)
                    for c in F.generate(s, 60))
    for kind in ("dif(", "freeze(", "when(", "\\+ ", " ; ", "==", "compare(",
                 "copy_term(", "term_variables(", "findall(", "w(", "var(",
                 "nonvar(", "ground(", "?=(", "f(A,", "= [", "= f("):
        assert kind in text, kind


def test_queries_are_balanced_and_name_their_variables():
    for case in F.generate(1, 50):
        assert all(F._balanced(g) for g in case.goals), case.goals
        q = case.query(7)
        assert q.endswith("fz_end(7)")
        for v in case.variables:
            assert v in case.goal_text()


def test_split_conjuncts_and_residuals():
    assert F.split_conjuncts("X = f(a,b), dif(X,'a,b'), Y = [1,2]") == [
        "X = f(a,b)", "dif(X,'a,b')", "Y = [1,2]"]
    # bindings go; an alias renames to the least name; qualifiers go
    line = "X = Y, B = f(_A), dif:dif(Y,_A), freeze:freeze(Y,user:g(_B))."
    assert F.residuals(line, ["X", "Y", "B"]) == [
        "dif(X,_1)", "freeze(X,g(_1))"]
    assert F.residuals("true.", []) == []


def test_canon_fresh_renames_in_order_outside_quotes():
    assert F.canon_fresh("f(_G12,_A,_G12,'_X')") == "f(_1,_2,_1,'_X')"


def test_split_cases_survives_a_crash():
    out = "a\nfz_end(0)\ntrue.\nb\nfz_end(1)\ntrue.\nc\n"
    got = F.split_cases(out)
    assert got[0] == ["a"] and got[1] == ["b"] and got[("partial",)] == ["c"]


def _result(goal, clausal, scryer):
    goals = F.split_conjuncts(goal)
    case = F.Case(goals, F._shown(goals, list(F.BASE_VARS)))
    return F.Result(case, clausal, scryer, clausal, scryer)


def test_classify_known_differences():
    # residual order, and Scryer's dif printing a frozen goal's output
    r = _result("freeze(B,w(t1)), dif(A,g(B))",
                ['fz_ans(_1,_2)', 'res["dif(A,g(B))", "freeze(B,w(t1))"]'],
                ['out:t1', 'fz_ans(_1,_2)',
                 'res["freeze(B,w(t1))", "dif(A,g(B))"]'])
    name, kind, _where = F.classify(r)
    assert name == "residual-order+scryer-dif-wakes-frozen-goal", name
    assert kind == "ruling"
    # two variables decide compare/3
    r = _result("compare(E1,f(B,B),f(C,f(B,A)))",
                ["fz_ans(_1,_2,_3,>)"], ["fz_ans(_1,_2,_3,<)"])
    assert F.classify(r)[0] == "variable-order"
    # ... but not a difference past them
    assert not F._decided_by_two_variables(F._read_term("f(B,a)"),
                                           F._read_term("f(B,b)"))
    assert F._decided_by_two_variables(F._read_term("[B|a]"),
                                       F._read_term("[C|b]"))


def test_an_answer_difference_is_unexplained():
    r = _result("compare(E1,[B|A],[1|A])",
                ["fz_ans(_1,_2,>)"], ["fz_ans(_1,_2,<)"])
    if os.path.exists(_oracles.TREALLA):
        # Trealla says < as Scryer does: not Scryer's list order
        assert F.classify(r) is None
    r = _result("A = 1", ["fz_ans(1)", "res[]"], ["fz_ans(2)", "res[]"])
    assert F.classify(r) is None
