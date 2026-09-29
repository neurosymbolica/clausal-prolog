"""ISO core builtins that did not exist (existence_error(procedure, ...)):
unify_with_occurs_check/2 (8.2.2), subsumes_term/2 (8.2.4),
acyclic_term/1 (8.3.11), retractall/1 (8.9.5), current_predicate/1 (8.8.2).
Every answer below is Scryer's for the same goal (2026-09-30)."""
import pytest

from clausal.logic.database import Module
from clausal.logic.solve import _deref_walk, solve
from clausal.logic.variables import Var

SRC = """\
-allow_singletons
-dynamic(foo/1)
-dynamic(bar/2)
-private([a, zzz, baz, append, foo, bar, f(_)])
foo(1),
foo(2),
baz(1),
cp1() <- current_predicate(foo/1)
cp2() <- current_predicate(bar/2)
cp3(N) <- current_predicate(baz/N)
cp4() <- current_predicate(zzz/0)
cp5() <- current_predicate(append/3)
cp6(R) <- catch((current_predicate(4), R is 1), E, R is E)
ra1(L) <- (retractall(foo(1)), findall(W, foo(W), L))
ra3(R) <- catch((retractall(baz(_)), R is 1), E, R is E)
ra5(R) <- catch((retractall(3), R is 1), E, R is E)
ac1() <- (V is f(V), acyclic_term(V))
ac2() <- (V is f(W), acyclic_term(V))
ac3() <- (V is W + V, acyclic_term(V))
ra6(L) <- (retractall(foo(_)), findall(W, foo(W), L))
ra7(R) <- catch((retractall(_), R is 1), E, R is E)
cp7(N) <- current_predicate(N/2)
cp8(R) <- catch((current_predicate(foo/a), R is 1), E, R is E)
"""


@pytest.fixture
def mod(tmp_path):
    from clausal.import_hook import _load_module
    p = tmp_path / "isodbt.clausal"
    p.write_text(SRC)
    return _load_module("isodbt", str(p))


def _n(goal, m):
    return len(list(solve(goal, m)))


def _v(m, pred):
    v = Var()
    return [_deref_walk(v) for _ in solve((pred, v), m)]


def test_unify_with_occurs_check():
    m = Module("uwoc")
    X, Y, Z = Var(), Var(), Var()
    assert _n(("unify_with_occurs_check", X, ("f", X)), m) == 0
    assert _n(("unify_with_occurs_check", Y, ("f", "a")), m) == 1
    assert _n(("unify_with_occurs_check", Z, Z), m) == 1


def test_subsumes_term():
    m = Module("subs")
    A, B, C, Z, Q = Var(), Var(), Var(), Var(), Var()
    assert _n(("subsumes_term", ("f", Var()), ("f", "a")), m) == 1
    assert _n(("subsumes_term", ("f", "a"), ("f", Var())), m) == 0
    assert _n(("subsumes_term", ("f", A, A), ("f", B, C)), m) == 0
    assert _n(("subsumes_term", ("f", Var(), Var()), ("f", Z, Z)), m) == 1
    assert _n(("subsumes_term", ("g", Q), ("f", Q)), m) == 0


def test_acyclic_term(mod):
    assert _n("ac1", mod) == 0
    assert _n("ac2", mod) == 1


def test_current_predicate(mod):
    assert _n("cp1", mod) == 1          # dynamic, clauses
    assert _n("cp2", mod) == 1          # dynamic, no clauses
    assert _v(mod, "cp3") == [1]
    assert _n("cp4", mod) == 0
    assert _n("cp5", mod) == 0          # a builtin is not user-defined
    assert _v(mod, "cp6") == [
        ("error", ("type_error", "predicate_indicator", 4),
         ("/", "current_predicate", 1))]


def test_retractall(mod):
    assert _v(mod, "ra1") == [[2]]
    [e] = _v(mod, "ra3")
    assert e[1] == ("permission_error", "modify", "static_procedure",
                    ("/", "baz", 1))
    [e] = _v(mod, "ra5")
    assert e[1] == ("type_error", "callable", 3)


def test_acyclic_term_through_an_operator_node_deep_and_shared(mod):
    assert _n("ac3", mod) == 0        # the cycle closes through an Add node
    # The walker itself (a query of a 5000-deep term trips the query
    # compiler's own recursion first):
    from clausal.logic.builtins.inspection import _is_acyclic
    deep = "z"
    for _ in range(5000):
        deep = ("s", deep)
    assert _is_acyclic(deep)                            # no RecursionError
    shared = "x0"
    for _ in range(60):
        shared = ("f", shared, shared)                  # 2**60 paths
    assert _is_acyclic(shared)


def test_retractall_more(mod):
    assert _v(mod, "ra6") == [[]]
    [e] = _v(mod, "ra7")
    assert e[1] == "instantiation_error"


def test_current_predicate_more(mod):
    assert _v(mod, "cp7") == ["bar"]
    [e] = _v(mod, "cp8")
    assert e[1][0] == "type_error" and e[1][1] == "predicate_indicator"
    P = Var()
    names = {str(_deref_walk(P)[1]) for _ in solve(("current_predicate", P), mod)}
    assert {"foo", "bar", "baz", "cp1"} <= names
    assert not any(n.startswith(("_", "$")) for n in names)
