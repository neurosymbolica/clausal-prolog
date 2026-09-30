"""assertz/asserta recompile lazily: an assert appends and invalidates, and
the next CALL recompiles the predicate once (as retract/1 does).  Each
assert used to recompile the whole predicate (O(n^2): ~90 s for a
250-clause fill).  The first assert of a brand-new predicate still compiles
once, which is what registers the lazy recompile the later ones use."""
from __future__ import annotations

SRC = """\
:- module(alr, [fill/1, fill_new/1, fill_a/1, inter/2, count/1, count_new/1,
               count_a/1, snap/1, first/1]).
:- dynamic(p/1).
:- dynamic(pa/1).
:- dynamic(t/1).
fill(N) :- ( between(1, N, I), assertz(p(I)), fail ; true ).
fill_new(N) :- ( between(1, N, I), assertz(q(I)), fail ; true ).
fill_a(N) :- ( between(1, N, I), asserta(pa(I)), fail ; true ).
count(C) :- findall(X, p(X), L), length(L, C).
count_new(C) :- findall(X, q(X), L), length(L, C).
count_a(L) :- findall(X, pa(X), L).
first(X) :- pa(X).
% a call between asserts sees every clause asserted before it
inter(N, L) :- findall(I-C, (between(1, N, I), assertz(t(I)),
                             findall(x, t(_), Xs), length(Xs, C)), L).
% the logical update view: a running call iterates its snapshot
snap(L) :- findall(X, (p(X), Y is X + 1000, assertz(p(Y))), L).
"""


def _counting(monkeypatch):
    import clausal.logic.compiler.predicate as cp
    real = cp._compile_predicate_trampoline_impl
    calls = []

    def counting(functor, arity, *a, **kw):
        calls.append((functor, arity))
        return real(functor, arity, *a, **kw)

    monkeypatch.setattr(cp, "_compile_predicate_trampoline_impl", counting)
    return calls


def test_an_assertz_fill_compiles_once_at_the_next_call(native, ans,
                                                        monkeypatch):
    mod = native.load("alr_fill", SRC.replace("alr", "alr_fill"))
    calls = _counting(monkeypatch)
    from clausal.logic.solve import call
    assert list(call("fill", 80, module=mod))
    # p/1 is declared with no clauses, so it has no dispatch yet: the FIRST
    # assert compiles (registering the lazy recompile), the other 79 do not
    assert calls.count(("p", 1)) == 1, calls
    assert ans(mod, "count") == [80]
    assert calls.count(("p", 1)) == 2, calls
    del calls[:]
    assert list(call("fill", 40, module=mod))
    assert calls.count(("p", 1)) == 0, calls
    assert ans(mod, "count") == [120]
    assert calls.count(("p", 1)) == 1, calls


def test_a_brand_new_predicate_compiles_at_its_first_assert_only(
        native, ans, monkeypatch):
    mod = native.load("alr_new", SRC.replace("alr", "alr_new"))
    calls = _counting(monkeypatch)
    from clausal.logic.solve import call
    assert list(call("fill_new", 80, module=mod))
    assert calls.count(("q", 1)) == 1, calls
    assert ans(mod, "count_new") == [80]
    assert calls.count(("q", 1)) == 2, calls


def test_asserta_order_is_kept(native, ans):
    mod = native.load("alr_a", SRC.replace("alr", "alr_a"))
    from clausal.logic.solve import call
    assert list(call("fill_a", 5, module=mod))
    assert ans(mod, "count_a") == [[5, 4, 3, 2, 1]]
    assert ans(mod, "first") == [5, 4, 3, 2, 1]


def test_a_call_between_asserts_sees_every_earlier_clause(native, ans):
    mod = native.load("alr_i", SRC.replace("alr", "alr_i"))
    assert ans(mod, "inter", 2, 5) == [[("-", i, i) for i in range(1, 6)]]


def test_a_running_call_iterates_its_snapshot(native, ans):
    """ISO 7.5.4: the clauses asserted while p/1 is being iterated are not
    seen by that iteration (Scryer: L = [1, 2, 3])."""
    mod = native.load("alr_s", SRC.replace("alr", "alr_s"))
    from clausal.logic.solve import call
    assert list(call("fill", 3, module=mod))
    assert ans(mod, "snap") == [[1, 2, 3]]
    assert ans(mod, "count") == [6]


def test_an_assert_into_a_tabled_predicate_abolishes_its_table(native, ans):
    """Scryer: e(1) tabled, assertz(e(2)) -> findall answers [1, 2].  (A
    table over ANOTHER predicate stays stale in Scryer, which has no
    incremental tabling; so does ours.)"""
    mod = native.load("alr_tab", """\
:- module(alr_tab, [add/1, e/1]).
:- dynamic(e/1).
:- table(e/1).
e(1).
add(X) :- assertz(e(X)).
""")
    from clausal.logic.solve import call
    assert ans(mod, "e") == [1]
    assert list(call("add", 2, module=mod))
    assert list(call("add", 3, module=mod))
    assert sorted(ans(mod, "e")) == [1, 2, 3]


def test_a_shallow_dynamic_predicate_filled_by_asserts(native, ans,
                                                      monkeypatch):
    """-shallow keeps its per-assert recompile, onto the TRAMPOLINE compiler
    as before (its registered lazy recompile is the shallow compiler)."""
    mod = native.load("alr_sh", """\
-module(alr_sh, [fill/1, count/1])
-dynamic(nx/2)
-shallow(nx/2)
fill(N) <- findall(I, (between(1, N, I), J is I + 1, assertz(nx(I, J))), _)
count(C) <- (findall(X, nx(X, _), L), length(L, C))
""", suffix=".seam")
    calls = _counting(monkeypatch)
    from clausal.logic.solve import call
    assert list(call("fill", 10, module=mod))
    assert calls.count(("nx", 2)) == 10, calls
    assert ans(mod, "count") == [10]
