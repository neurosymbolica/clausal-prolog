"""Rules asserted at run time by a ``.pl`` module (ISO 8.9.1, operator
ruling 2026-11-03), from the engine's side: the clause is the one the native
front end gives the same clause written in the file (``database_ops.
_rule_clause``), recompiled lazily like any dynamic predicate, under the
file's directive state even on a bytecode-cache hit; and where a rule may
NOT be asserted -- by a Clausal Prolog module, into a Clausal Prolog
module's procedure -- the refusal is kept.  The ISO answers themselves (and
their Scryer oracle) are ``tests/iso/test_assert_rules*_iso.py``."""
from __future__ import annotations

import importlib
import sys

from clausal.logic.solve import call


def _counting(monkeypatch):
    import clausal.logic.compiler.predicate as cp
    real = cp._compile_predicate_trampoline_impl
    calls = []

    def counting(functor, arity, *a, **kw):
        calls.append((functor, arity))
        return real(functor, arity, *a, **kw)

    monkeypatch.setattr(cp, "_compile_predicate_trampoline_impl", counting)
    return calls


FILL = """\
:- module(arf, [fill/1, count/1, firsts/1]).
:- dynamic(p/1).
fill(N) :- ( between(1, N, I), assertz((p(X) :- X = I, true)), fail ; true ).
count(C) :- findall(X, p(X), L), length(L, C).
firsts(L) :- findall(X, (p(X), X < 3), L).
"""


def test_an_assertz_fill_of_rules_compiles_once_at_the_next_call(
        native, ans, monkeypatch):
    mod = native.load("arf", FILL)
    calls = _counting(monkeypatch)
    assert list(call("fill", 60, module=mod))
    # the first assert compiles (p/1 had no dispatch), the other 59 do not
    assert calls.count(("p", 1)) == 1, calls
    assert ans(mod, "count") == [60]
    assert calls.count(("p", 1)) == 2, calls
    assert ans(mod, "firsts") == [[1, 2]]


CUTS = """\
:- module(arc, [add/0, all/1]).
:- dynamic(c/1).
add :- assertz((c(X) :- member(X, [1, 2, 3]), X > 1, !)), assertz(c(9)).
all(L) :- findall(X, c(X), L).
"""


def test_a_cut_rule_asserted_after_a_bytecode_cache_hit(native, ans):
    """The lowering context the rule is compiled under (D59's surface: may
    it cut) is re-read on the cache-hit path too."""
    native.load("arc", CUTS)                      # writes the bytecode
    sys.modules.pop("arc", None)
    importlib.invalidate_caches()
    mod = importlib.import_module("arc")          # a cache hit
    assert list(call("add", module=mod))
    assert ans(mod, "all") == [[2]]


REIF = """\
:- module(arr, [t/1]).
:- use_module(library(reif)).
:- dynamic(r/2).
t(L) :- assertz((r(X, Y) :- if_(X = a, Y = yes, Y = no))),
        findall(X-Y, (member(X, [a, b]), r(X, Y)), L).
"""


def test_an_asserted_rule_is_lowered_under_the_files_libraries(native, ans):
    """``if_/3`` is library(reif)'s in the file that imports it: an asserted
    rule's body is lowered as the same clause written there."""
    mod = native.load("arr", REIF)
    assert ans(mod, "t") == [[("-", "a", "yes"), ("-", "b", "no")]]


SOFT = """\
:- module(ars, [t/1]).
t(E) :- catch(assertz((s :- '*->'(true, true) ; true)), error(E, _), true).
"""


def test_soft_cut_in_an_asserted_body_is_refused_as_call_refuses_it(native,
                                                                     ans):
    """``*->`` is refused on every surface; at assert time with the error
    call/1 gives it (Scryer has no ``*->`` either: it is no operator there)."""
    mod = native.load("ars", SOFT)
    (e,) = ans(mod, "t")
    assert e[:2] == ("existence_error", "procedure"), e
    assert e[2] == ("/", "*->", 2), e


# ── Clausal Prolog modules ──────────────────────────────────────────────────

CLAUSAL_SIDE = """\
:- module(arcl, [collect/2, try_assert/1, hook/1, hooks/1]).
:- dynamic(hook/1).
collect(G, L) :- findall(X, call(G, X), L).
try_assert(R) :- catch(assertz(arpl:(q(X) :- X = 1)), error(R, _), true).
hooks(L) :- findall(X, hook(X), L).
:- end_module(arcl).
"""

PL_SIDE = """\
:- module(arpl, [dyn_call/1, consulted_call/1, clausal_asserts/1,
                 into_clausal/1, into_clausal_qualified/1, fact_into_clausal/1,
                 own_call/1]).
:- use_module(arcl).
cons(X) :- member(X, [1, 2, 3]), X > 1, !.
add :- assertz((dyn(X) :- member(X, [1, 2, 3]), X > 1, !)).
own_call(L) :- add, findall(X, call(dyn, X), L).
dyn_call(R) :- add, catch(collect(arpl:dyn, R), error(R, _), true).
consulted_call(R) :- catch(collect(arpl:cons, R), error(R, _), true).
clausal_asserts(R) :- try_assert(R).
into_clausal(R) :- catch(assertz((hook(X) :- X = 1)), error(R, _), true).
into_clausal_qualified(R) :-
    catch(assertz(arcl:(hook(X) :- X = 1)), error(R, _), true).
fact_into_clausal(L) :- assertz(hook(5)), hooks(L).
"""


def _pair(native):
    native.load("arcl", CLAUSAL_SIDE, suffix=".clausal")
    return native.load("arpl", PL_SIDE)


def test_a_clausal_module_calling_an_asserted_rule_meets_the_dialect_edge(
        native, ans):
    """A Clausal Prolog module may never call a ``.pl`` module, closures
    included (operator ruling 2026-10-01): its call/N of an asserted rule is
    refused exactly as its call of a consulted rule of the same module is.
    The ``.pl`` module's own call/N runs the rule, its cut local to it."""
    mod = _pair(native)
    edge = ("permission_error", "access", "prolog_module", "arpl")
    assert ans(mod, "consulted_call") == [edge]
    assert ans(mod, "dyn_call") == [edge]
    assert ans(mod, "own_call") == [[2]]


def test_a_clausal_module_still_refuses_to_assert_a_rule(native, ans):
    """Its qualified ``assertz(arpl:(q(X) :- ...))`` reaches the ``.pl``
    module, which the dialect edge refuses before the rule is considered."""
    mod = _pair(native)
    assert ans(mod, "clausal_asserts") == [
        ("permission_error", "access", "prolog_module", "arpl")]


def test_a_rule_is_not_asserted_into_a_clausal_modules_procedure(native, ans):
    """The clause would be compiled in the Clausal Prolog module, which is
    cut-free: refused, imported or qualified, as permission_error(assert,
    rule, Head).  A fact goes in as before."""
    mod = _pair(native)
    for goal in ("into_clausal", "into_clausal_qualified"):
        (e,) = ans(mod, goal)
        assert e[:3] == ("permission_error", "assert", "rule"), (goal, e)
        assert e[3][0] == "hook", (goal, e)
    assert ans(mod, "fact_into_clausal") == [[5]]
