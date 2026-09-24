"""ISO ``clause/2`` (13211-1 §8.8.1) -- step 2 of the 2026-09-25 plan.

``clause(H, B)`` is true iff ``H :- B`` unifies with a clause of a DYNAMIC
procedure.  The loader stores a clause with its constant/compound head
arguments hoisted into leading ``Unify`` body goals; ``Clause.hoisted``
counts them and ``clause/2`` puts them back (option B).  The Body is a term
in the form term position builds and ``call/1`` runs (step 1).

Expectations were checked on the box (2026-09-25) against Scryer
(``/workspace/scryer-prolog``) and Trealla (``/workspace/trealla-prolog``) with
this program::

    :- dynamic(d/2).
    d(0, 0).  d(X, X).  d(f(X), [1, X]).  d(X, Y) :- p(X), \\+ s(Y).
    st(1).  st(X) :- st(X), true.  p(1).

    clause(d(A, B), Body)     both: d(0,0)-true, d(_A,_A)-true,
                              d(f(_X),[1,_X])-true, d(_A,_B)-(p(_A),\\+s(_B))
    clause(_, true)           both: instantiation_error
    clause(4, true)           both: type_error(callable, 4)
    clause(d(_,_), 4)         both: type_error(callable, 4)
    clause(st(_), _)          both: permission_error(access,private_procedure,st/1)
    clause(atom_length(_,_),_) both: permission_error(... atom_length/2)
    clause(call(_), _)        both: permission_error(... call/1)
    clause((a,b), _)          both: permission_error(... (',')/2)
    clause(true, _)           both: permission_error(... true/0)
    clause(!, _)              both: permission_error(... !/0)
    clause(nosuch(_), _)      both: fail
    clause(d(_,_), (_;4))     both: fail (only the TOP of Body is checked)
    clause(d(_,_), foo)       both: fail
    clause(d(0,0), true)      both: two answers (d(0,0) and d(X,X))
    assertz(nd(1)), clause(nd(X), B)   both: X = 1, B = true (assertz => dynamic)
    assertz during iteration  both: the new clause is not seen (logical update view)
    clause(user:d(_,_), B)    Trealla: the four clauses; Scryer:
                              existence_error '$clause'/2 (a Scryer bug)
    clause("ab", _)           both: type_error(callable, [a,b])
    clause(d(_,_), [x])       Scryer: type_error(callable, [x]); Trealla: fail

ISO decides the last two against Scryer: a non-empty list IS callable (the
compound '.'/2), so ``clause([a], B)`` names the procedure '.'/2, which is
not defined -- it FAILS -- and a list Body is callable, so ``clause(d(_,_),
[x])`` just fails to match.  (Step 1 made the same ISO-over-Scryer call for
``call([a])``.)
"""
from __future__ import annotations

import os
import sys
import warnings
from pathlib import Path

import pytest

from clausal.logic.exceptions import LogicException
from clausal.logic.variables import Var, deref, is_var
from clausal.pythonic_ast import nodes
from clausal.terms import Compound

FIXTURES = Path(__file__).parent / "fixtures"
NAME = "clause_2_iso"


def _load(name, filename=None):
    from clausal.import_hook import _load_module
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        mod = _load_module(name, str(FIXTURES / f"{filename or name}.clausal"))
    return mod


@pytest.fixture
def mod():
    saved = sys.modules.pop(NAME, None)
    m = _load(NAME)
    yield m
    sys.modules.pop(NAME, None)
    if saved is not None:
        sys.modules[NAME] = saved


@pytest.fixture
def lm(mod):
    return mod.__dict__["$module"]


def _walk(t):
    from clausal.logic.solve import _deref_walk
    return _deref_walk(t)


def _clause(lm, head, body=None):
    """Every ``(Head, Body)`` answer, fully dereferenced."""
    from clausal.logic.solve import call
    B = Var() if body is None else body
    return [(_walk(head), _walk(B)) for _ in call("clause", head, B, module=lm)]


def _error(lm, head, body=None):
    from clausal.logic.solve import call
    with pytest.raises(LogicException) as info:
        list(call("clause", head, Var() if body is None else body, module=lm))
    term = info.value.term
    assert term.functor == "error"
    return term.args[0]


def _pi(formal):
    """``permission_error(access, private_procedure, N/A)`` -> ``(N, A)``."""
    assert formal.functor == "permission_error", formal
    assert formal.args[0] == "access" and formal.args[1] == "private_procedure"
    ind = formal.args[2]
    assert ind.functor == "/"
    return ind.args[0], ind.args[1]


# ── errors (ISO 8.8.1.3) ────────────────────────────────────────────────────


def test_an_unbound_head_is_an_instantiation_error(lm):
    # Scryer + Trealla: clause(_, true) -> instantiation_error
    assert _error(lm, Var(), True) == "instantiation_error"


@pytest.mark.parametrize("head", [4, 2.5, None])
def test_a_non_callable_head_is_a_type_error(lm, head):
    # Scryer + Trealla: clause(4, true) -> type_error(callable, 4)
    formal = _error(lm, head, True)
    assert formal.functor == "type_error"
    assert formal.args[0] == "callable" and formal.args[1] == head


def test_a_non_callable_body_is_a_type_error(lm):
    # Scryer + Trealla: clause(d(_,_), 4) -> type_error(callable, 4)
    formal = _error(lm, ("d", Var(), Var()), 4)
    assert formal.functor == "type_error"
    assert formal.args[0] == "callable" and formal.args[1] == 4


def test_the_head_is_checked_before_the_body(lm):
    formal = _error(lm, 4, 5)
    assert formal.args[1] == 4


def test_only_the_top_of_the_body_is_checked(lm):
    # Scryer + Trealla: clause(d(_,_), (_ ; 4)) fails, no error
    assert _clause(lm, ("d", Var(), Var()), nodes.Or(left=Var(), right=4)) == []
    # clause(d(_,_), foo) fails
    assert _clause(lm, ("d", Var(), Var()), "foo") == []


def test_a_static_procedure_is_a_permission_error(lm):
    # Scryer + Trealla: clause(st(_), _) -> permission_error(access,
    # private_procedure, st/1); p/1 is static too.
    assert _pi(_error(lm, ("st", Var()))) == ("st", 1)
    assert _pi(_error(lm, ("p", 1))) == ("p", 1)


@pytest.mark.parametrize("head, pi", [
    (("atom_length", "abc", Var()), ("atom_length", 2)),   # both: permission
    (("call", Var()), ("call", 1)),                        # both: permission
    (("clause", Var(), Var()), ("clause", 2)),
    (("assertz", Var()), ("assertz", 1)),
])
def test_a_builtin_is_a_permission_error(lm, head, pi):
    assert _pi(_error(lm, head)) == pi


def _control_heads():
    X = Var()
    return [
        ((("p", X), ("s", X)), (",", 2)),       # both: (',')/2
        ((",", ("p", X), ("s", X)), (",", 2)),  # the ISO cell spelling
        ((";", ("p", X), ("s", X)), (";", 2)),
        (("\\+", ("p", X)), ("\\+", 1)),
        (nodes.Not(operand=("p", X)), ("\\+", 1)),
        (nodes.Or(left=("p", X), right=("s", X)), (";", 2)),
        (nodes.IfExpr(test=("p", X), body=True, orelse=True), ("if_", 3)),
        (True, ("true", 0)),                    # both: true/0
        ("true", ("true", 0)),
        ("!", ("!", 0)),                        # both: !/0
        ("fail", ("fail", 0)),
        (("findall", X, ("p", X), Var()), ("findall", 3)),
        (("once", ("p", X)), ("once", 1)),
        (("eval_", 1, X), ("eval_", 2)),
    ]


@pytest.mark.parametrize("head, pi", _control_heads())
def test_a_control_construct_is_a_permission_error(lm, head, pi):
    assert _pi(_error(lm, head)) == pi


def test_an_unknown_procedure_fails(lm):
    # Scryer + Trealla: clause(nosuch(_), _) fails
    assert _clause(lm, ("nosuch", Var())) == []
    assert _clause(lm, "nosuch0") == []
    assert _clause(lm, ("d", 1, 2, 3)) == []     # d/3: another arity


def test_a_dynamic_procedure_with_no_clauses_fails(lm):
    assert lm.db.row("none", 1).dynamic
    assert _clause(lm, ("none", Var())) == []


def test_a_list_or_string_head_fails(lm):
    """ISO: a list is the callable '.'/2 (and ``[]`` the atom '[]'), which
    names no procedure -- clause/2 fails.  Scryer/Trealla give type_error
    for ``clause("ab", _)``; ISO decides, as step 1 did for call/1."""
    from clausal.logic.cells import chars
    assert _clause(lm, [1, 2]) == []
    assert _clause(lm, []) == []
    assert _clause(lm, chars("ab")) == []
    # A list Body is callable too, so it only fails to match
    # (Scryer: type_error(callable, [x]); Trealla: fails).
    assert _clause(lm, ("d", Var(), Var()), ["x"]) == []


# ── heads ───────────────────────────────────────────────────────────────────


def test_fact_heads_come_back_as_written_with_body_true(lm):
    """``fib(0, 0)`` is stored as ``fib(_A, _B) :- _A = 0, _B = 0``; the two
    hoisted goals go back into the head."""
    got = _clause(lm, ("fib", Var(), Var()))
    assert got[0] == (("fib", 0, 0), True)
    assert got[1] == (("fib", 1, 1), True)
    assert len(got) == 3
    row = lm.db.row("fib", 2)
    assert [c.hoisted for c in row.clauses] == [2, 2, 0]


def test_a_bound_head_selects_and_a_bound_body_filters(lm):
    assert _clause(lm, ("fib", 0, Var()))[0] == (("fib", 0, 0), True)
    # clause(fib(0, 0), true): the fact, not the rule (its body is not true)
    assert _clause(lm, ("fib", 0, 0), True) == [(("fib", 0, 0), True)]
    # Scryer + Trealla: clause(d(0, 0), true) has two answers
    assert len(_clause(lm, ("d", 0, 0), True)) == 2


def test_a_repeated_variable_head(lm):
    (h, b), = [a for a in _clause(lm, ("d", Var(), Var()))
               if a[1] is True and is_var(a[0][1])]
    assert h[1] is h[2] and b is True


def test_structured_head_arguments_share_their_variables(lm):
    got = _clause(lm, ("d", Var(), Var()))
    # d(f(X), [1, X])
    h, b = got[2]
    assert h[1][0] == "f" and h[2][0] == 1 and h[1][1] is h[2][1] and b is True
    # d([a, pt(Y, [b])], Y) <- p(Y): nested compound and list, shared with body
    h, b = got[3]
    assert h[1][0] == "a" and h[1][1][0] == "pt" and h[1][1][2] == ["b"]
    y = h[1][1][1]
    assert is_var(y) and h[2] is y and b == ("p", y)
    # d(pt(X, Y), a) <- (p(X), s(Y)): an atom argument stays in the head
    h, b = got[4]
    assert h[2] == "a" and b == (("p", h[1][1]), ("s", h[1][2]))


# ── bodies ──────────────────────────────────────────────────────────────────


def _bodies(lm):
    return [b for _, b in _clause(lm, ("d", Var(), Var()))]


def test_body_shapes(lm):
    b = _bodies(lm)
    X, Y = Var(), Var()
    # (p(X), s(Y)) -- a plain tuple, as term position builds it
    assert type(b[5]) is tuple and b[5][0][0] == "p" and b[5][1][0] == "s"
    # (not p(X), s(Y))
    assert type(b[6][0]) is nodes.Not and b[6][0].operand[0] == "p"
    # if_(p(X), s(Y), Y is 3)
    ite = b[7]
    assert type(ite) is nodes.IfExpr and ite.test[0] == "p"
    assert ite.body[0] == "s" and type(ite.orelse) is nodes.Unify
    assert ite.orelse.right == 3 and ite.orelse.left is ite.body[1]
    # (p(X), Y is X + 1): `is` is Unify; the arithmetic stays a term
    assert type(b[8][1]) is nodes.Unify and type(b[8][1].right) is nodes.Add
    assert type(b[9]) is nodes.Or
    assert type(b[10][1]) is nodes.CompareChain
    assert type(b[11][1]) is nodes.in_ and b[11][1].right == [1, 2]
    assert type(b[12][2]) is nodes.ArithNeq
    assert type(b[13][1]) is nodes.ArithEq and b[13][1].right == 2
    assert type(b[14][1]) is nodes.GtE
    # call(p, Y): term position builds the predicate's binding for `p`
    assert b[15][0] == "call" and b[15][2] is not None
    # (p(X) and s(Y), X < Y): `and` flattens into the conjunction
    assert type(b[16]) is tuple and len(b[16]) == 3
    assert type(b[16][2]) is nodes.Lt


def test_nested_calls_and_arithmetic_in_the_fib_body(lm):
    (h, b), = [a for a in _clause(lm, ("fib", Var(), Var())) if a[1] is not True]
    n, f = h[1], h[2]
    assert type(b[0]) is nodes.Gt and b[0].left is n
    assert b[3][0] == "fib" and b[4][0] == "fib"
    assert b[5][0] == "eval_" and b[5][2] is f


def test_meta_call_special_forms_come_back_as_their_cells(lm):
    """findall/once/eval_ have no term class (todo/control-builtins-cannot-
    be-built-as-terms-2026-09-25.md): they come back as the ISO term the text
    denotes, the cell, with their arguments converted like any other."""
    got = {h[1]: b for h, b in _clause(lm, ("sp", Var(), Var()))}
    f = got[1]
    assert f[0] == "findall" and f[2] == ("p", f[1]) and is_var(f[3])
    assert got[2][0] == "once" and got[2][1][0] == "p"
    assert type(got[3]) is nodes.Not and got[3].operand[0] == "findall"
    assert got[3].operand[2][0] == "once"
    assert got[4][0] == "eval_" and type(got[4][1]) is nodes.Add
    assert got[4][2] == 3


def test_a_body_with_a_variable_reading_python_expression_is_refused(lm):
    """``Y is f"v{Y}"`` is a Python closure over Y, not a term: building it
    would evaluate it with Y unbound (to ``'v_0'``).  The clause is refused
    with the ISO "you may not inspect this" error -- but only when its head
    is the one asked about."""
    (h, b), = _clause(lm, ("fs", 2, Var()))
    assert h[1] == 2 and b == ("p", h[2])
    assert _pi(_error(lm, ("fs", 1, Var()))) == ("fs", 2)
    assert _pi(_error(lm, ("fs", Var(), Var()))) == ("fs", 2)


# ── order, freshness, the logical update view ───────────────────────────────


def test_clauses_come_back_in_clause_order(lm):
    heads = [h for h, _ in _clause(lm, ("lu", Var()))]
    assert heads == [("lu", 1), ("lu", 2)]


def test_each_answer_is_a_fresh_renaming(lm):
    from clausal.logic.solve import call
    H, B = ("d", Var(), Var()), Var()
    first = None
    for _ in call("clause", H, B, module=lm):
        h = _walk(H)
        if is_var(h[1]) and h[1] is h[2]:      # d(X, X)
            first = h[1]
            break
    again = [a for a in _clause(lm, ("d", Var(), Var()))
             if a[1] is True and is_var(a[0][1])]
    assert first is not None and again[0][0][1] is not first
    stored = lm.db.row("d", 2).clauses[1].head
    assert stored[1] is not first


def test_a_nested_clause_call_sees_the_clause_unbound(lm):
    """A meta-interpreter calls clause/2 again while an answer is live: the
    construction must not leave the STORED clause's variables bound."""
    from clausal.logic.solve import call
    H, B = ("fib", Var(), Var()), Var()
    outer = []
    for _ in call("clause", H, B, module=lm):
        outer.append(_walk(H))
        inner = _clause(lm, ("fib", Var(), Var()))
        assert [h for h, _ in inner][:2] == [("fib", 0, 0), ("fib", 1, 1)]
        assert is_var(inner[2][0][1])
    assert outer[:2] == [("fib", 0, 0), ("fib", 1, 1)]


def test_the_logical_update_view(lm):
    """ISO 7.5.4: the clauses are those of the procedure when clause/2 was
    called.  Scryer + Trealla: an assertz during the iteration is not seen."""
    from clausal.logic.solve import call
    X, B = Var(), Var()
    seen = []
    for _ in call("clause", ("lu", X), B, module=lm):
        seen.append(deref(X))
        next(call("assertz", ("lu", 10 + len(seen)), module=lm), None)
    assert seen == [1, 2]
    assert [h[1] for h, _ in _clause(lm, ("lu", Var()))] == [1, 2, 11, 12]
    # A retract during the iteration does not hide the clause either.
    seen = []
    for _ in call("clause", ("lu", X), B, module=lm):
        seen.append(deref(X))
        if len(seen) == 1:
            next(call("retract", ("lu", 2), module=lm), None)
    assert seen == [1, 2, 11, 12]
    assert [h[1] for h, _ in _clause(lm, ("lu", Var()))] == [1, 11, 12]


def test_an_assertz_created_procedure_is_dynamic(lm):
    """Scryer + Trealla: assertz(nd(1)), clause(nd(X), B) -> X = 1, B = true.
    A procedure assertz creates is unlocked, and an unlocked row is one a
    runtime write may change: dynamic in ISO's sense."""
    from clausal.logic.solve import call
    next(call("assertz", Compound("nd_new", (1, Var())), module=lm))
    row = lm.db.row("nd_new", 2)
    assert not row.dynamic and not row.locked
    assert row.clauses[0].hoisted == 1
    (h, b), = _clause(lm, ("nd_new", Var(), Var()))
    assert h[1] == 1 and is_var(h[2]) and b is True


# ── the round trip ──────────────────────────────────────────────────────────


def _sorted_answers(lm, name, x):
    from clausal.logic.solve import call

    def norm(v):
        v = _walk(v)
        return "_" if is_var(v) else repr(v)
    X = Var() if x is None else x
    Y = Var()
    # repr, with every unbound Var's name masked: the two sides allocate
    # different fresh variables.
    import re
    out = []
    for _ in call(name, X, Y, module=lm):
        out.append(re.sub(r"AttVar\(_\d+\)|Var\(_\d+\)", "V", repr((norm(X), norm(Y)))))
    return out


@pytest.mark.parametrize("x", [None, 0, 1, 2, 3, "a", "b"])
def test_call_of_the_body_answers_what_the_head_does(lm, x):
    """``rt(X, Y) <- (clause(d(X, Y), B), call(B))``: for every clause of
    d/2, calling its Body with its Head's bindings answers what calling the
    head does -- in the same order."""
    direct = _sorted_answers(lm, "d", x)
    through = _sorted_answers(lm, "rt", x)
    assert direct, "no answers: the comparison would be vacuous"
    assert through == direct


def test_the_round_trip_covers_every_clause(lm):
    """Positive control for the test above: every clause of d/2 answers for
    some input (none is dead weight that would pass trivially)."""
    assert len(lm.db.row("d", 2).clauses) == 17
    assert len(_clause(lm, ("d", Var(), Var()))) == 17


# ── Clause.hoisted from every normalizer ────────────────────────────────────


def test_hoisted_counts_from_every_normalizer(lm):
    from clausal.logic.builtins.database_ops import _normalize_fact_clause
    counts = [c.hoisted for c in lm.db.row("d", 2).clauses]
    # d(0,0)=2 (fact), d(X,X)=0, d(f(X),[1,X])=1 (a list holding a variable
    # stays in the head), d([a,pt(..)],Y)=1 (rule: the structural list),
    # d(pt(X,Y), a)=1 (a rule's atom stays)
    assert counts[:5] == [2, 0, 1, 1, 1]
    assert all(n == 0 for n in counts[5:14]) and counts[14] == 0
    assert _normalize_fact_clause(Compound("q", (1, Var(), "a"))).hoisted == 2
    assert _normalize_fact_clause(("q", 1)).hoisted == 0   # a cell: untouched


def test_hoisted_is_not_part_of_clause_equality():
    from clausal.logic.database import Clause
    assert Clause(head=("q", 1), body=[], hoisted=1) == Clause(head=("q", 1), body=[])


# ── qualified heads, handles, both eras ─────────────────────────────────────


@pytest.fixture
def other():
    name = "call_body_terms_other"
    saved = sys.modules.pop(name, None)
    m = _load(name)
    yield m.__dict__["$module"]
    sys.modules.pop(name, None)
    if saved is not None:
        sys.modules[name] = saved


def test_a_qualified_head_reads_that_module(lm, other):
    got = _clause(other, (":", NAME, ("lu", Var())))
    assert [h[2][1] for h, _ in got] == [1, 2]
    # ...and the other module's own static p/1 is refused through it.
    assert _pi(_error(lm, (":", "call_body_terms_other", ("p", Var())))) == ("p", 1)
    # M:H with H unbound is an instantiation_error; non-callable a type_error.
    assert _error(lm, (":", NAME, Var())) == "instantiation_error"
    assert _error(lm, (":", NAME, 7)).functor == "type_error"


def test_a_predicate_handle_head_resolves_in_its_module(lm, other):
    from clausal.logic.atoms import mangle
    got = _clause(other, (mangle(NAME, "lu"), Var()))
    assert [h[1] for h, _ in got] == [1, 2]


_OWNER = "tests.fixtures.gate_dyn_owner"
_USER = "_clause2_gate_dyn_user"

_ERAS = [pytest.param(f, p, id=f"{'flipped' if f else 'class'}-"
                              f"{'popped' if p else 'loaded'}")
         for f in (False, True) for p in (False, True)]


@pytest.fixture
def pair():
    """An owner of a -dynamic predicate and an importer that re-declares it
    (so the importer holds an empty local twin) -- see
    tests/test_listing_indicator_both_eras.py."""
    from clausal.import_hook import _load_module
    saved = sys.modules.get(_OWNER)
    sys.modules.pop(_OWNER, None)
    sys.modules.pop(_USER, None)
    owner = _load_module(_OWNER, os.path.join(FIXTURES, "gate_dyn_owner.clausal"))
    user = _load_module(_USER, os.path.join(FIXTURES, "gate_dyn_user.clausal"))
    yield owner, user
    sys.modules.pop(_USER, None)
    if saved is not None:
        sys.modules[_OWNER] = saved
    else:
        sys.modules.pop(_OWNER, None)


@pytest.mark.parametrize("flipped,owner_popped", _ERAS)
def test_an_imported_dynamic_predicate_reads_the_owner_in_both_eras(
        pair, flipped, owner_popped):
    from clausal.logic.atoms import mangle
    from clausal.logic.predicate import PredicateMeta
    from clausal.logic.solve import call
    owner, user = pair
    ulm = user.__dict__["$module"]
    next(call("gd_add", 42, module=ulm), None)
    assert len(owner.__dict__["$module"].db.row("gd_p", 1).clauses) == 2
    assert ulm.db.row("gd_p", 1).clauses == [], "no empty twin: no hazard"
    if flipped:
        assert isinstance(user.__dict__["gd_p"], PredicateMeta)
        user.__dict__["gd_p"] = mangle(_OWNER, "gd_p")
    if owner_popped:
        sys.modules.pop(_OWNER, None)
    got = _clause(ulm, ("gd_p", Var()))
    assert [h[1] for h, _ in got] == [1, 42]
    assert all(b is True for _, b in got)
