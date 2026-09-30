"""clause/2, retract/1, retractall/1 and assert: defects from the database
review of 2026-09-30.  Every expected answer is Scryer's for the same
program (2026-09-30), except where a test says otherwise.

1. A ``freeze/2`` goal woken by the head PROBE bound on the engine trail
   while the probe ran on a private one, so its bindings outlived the probe:
   clause/2 and retract/1 lost every answer after the first.
2. ``M:Clause`` was not unwrapped: assertz stored a (:)/2 fact nobody could
   reach, retract/retractall were silent no-ops.
3. ``retract(1)`` and friends failed silently (ISO: type_error(callable, _));
   a control construct is permission_error(modify, static_procedure, _).
4. ``retract((r(_) :- 1))`` raised; ISO 8.9.3 and Scryer simply fail.
5. retract/1 recompiled the whole remaining predicate on every removal.
"""
from __future__ import annotations

FREEZE_SRC = """\
:- use_module(library(freeze)).
:- dynamic(p/1).
p(1). p(2). p(3).
c(X-Y) :- freeze(Y, Y = X), clause(p(Y), true).
r(X-Y) :- freeze(Y, Y = X), retract(p(Y)).
ra(X-L) :- freeze(Y, Y = X), retractall(p(Y)), findall(Z, p(Z), L).
"""


def test_clause_with_a_frozen_variable_answers_every_clause(native, ans):
    mod = native.load("dbr_freeze_c", FREEZE_SRC)
    assert ans(mod, "c") == [("-", 1, 1), ("-", 2, 2), ("-", 3, 3)]


def test_retract_with_a_frozen_variable_removes_every_clause(native, ans):
    """Scryer answers [1-1, 1-1, 1-1] here, which no reading of ISO 8.9.3
    gives (the second answer removes p(2)); ISO's is the one pinned."""
    mod = native.load("dbr_freeze_r", FREEZE_SRC)
    assert ans(mod, "r") == [("-", 1, 1), ("-", 2, 2), ("-", 3, 3)]


def test_retractall_with_a_frozen_variable_removes_every_clause(native, ans):
    """ISO 8.9.5: retractall(H) is ``retract((H :- _)), fail ; true``, so
    every clause goes and X is left unbound.  (Scryer answers [2, 3]: the
    same attributed-variable divergence as above.)"""
    from clausal.logic.variables import is_var
    mod = native.load("dbr_freeze_ra", FREEZE_SRC)
    [(x, rest)] = [row[1:] for row in ans(mod, "ra")]
    assert is_var(x) and rest == []


OWNER_SRC = """\
:- module(dbr_owner, [mp/1]).
:- dynamic(mp/1).
mp(1). mp(2). mp(3).
"""

USER_SRC = """\
:- use_module(dbr_owner).
q1(L) :- assertz(dbr_owner:mp(9)), findall(X, dbr_owner:mp(X), L).
q2(L) :- asserta(dbr_owner:mp(0)), findall(X, dbr_owner:mp(X), L).
q3(L) :- assertz(dbr_owner:(mp(9) :- true)), findall(X, dbr_owner:mp(X), L).
q4(L) :- findall(X, retract(dbr_owner:mp(X)), L).
q5(L) :- retract(dbr_owner:mp(2)), findall(X, dbr_owner:mp(X), L).
q6(L) :- findall(X, retract(dbr_owner:(mp(X) :- true)), L).
q7(L) :- retractall(dbr_owner:mp(_)), findall(X, dbr_owner:mp(X), L).
q8(L) :- findall(X, retract((dbr_owner:mp(X) :- true)), L).
q9(R) :- catch((retract(dbr_owner:1), R = ok), E, R = E).
q10(R) :- catch((retract(dbr_owner:_), R = ok), E, R = E).
q11(R) :- catch((retract(_:mp(1)), R = ok), E, R = E).
"""


def test_module_qualified_assert_and_retract(native, ans):
    for name, want in (
            ("q1", [[1, 2, 3, 9]]), ("q2", [[0, 1, 2, 3]]),
            ("q3", [[1, 2, 3, 9]]), ("q4", [[1, 2, 3]]),
            ("q5", [[1, 3]]), ("q6", [[1, 2, 3]]), ("q7", [[]]),
            # the HEAD alone qualified is a clause for (:)/2 (Scryer)
            ("q8", [[]]),
            ("q9", [("error", ("type_error", "callable", 1),
                     ("/", "retract", 1))]),
            ("q10", [("error", "instantiation_error", ("/", "retract", 1))]),
            # Scryer fails here; an unbound module is an instantiation error
            # (ISO/IEC 13211-2), not existence_error(module, <a Var repr>)
            ("q11", [("error", "instantiation_error", ("/", "retract", 1))]),
    ):
        native.load("dbr_owner", OWNER_SRC)
        mod = native.load(f"dbr_user_{name}", USER_SRC)
        assert ans(mod, name) == want, name


ERR_SRC = """\
:- dynamic(p/1).
p(1).
e(G, R) :- catch((G, R = ok), E, R = E).
"""


def _err(kind, *args):
    return ("error", (kind, *args), ("/", "retract", 1))


def test_retract_refuses_what_iso_refuses(native, ans):
    mod = native.load("dbr_errors", ERR_SRC)
    cases = {
        "retract(1)": _err("type_error", "callable", 1),
        "retract(3.5)": _err("type_error", "callable", 3.5),
        "retract([a])": _err("type_error", "callable", ["a"]),
        "retract((a, b))": _err("permission_error", "modify",
                                "static_procedure", ("/", ",", 2)),
        "retract((a ; b))": _err("permission_error", "modify",
                                 "static_procedure", ("/", ";", 2)),
        "retract((a -> b))": _err("permission_error", "modify",
                                  "static_procedure", ("/", "->", 2)),
        "retract(\\+ a)": _err("permission_error", "modify",
                               "static_procedure", ("/", "\\+", 1)),
        # D47: the truth atom true crosses to Python as True
        "retract(true)": _err("permission_error", "modify",
                              "static_procedure", ("/", True, 0)),
        "retract(((a, b) :- true))": _err("permission_error", "modify",
                                          "static_procedure", ("/", ",", 2)),
        "retractall((a, b))": _err("permission_error", "modify",
                                   "static_procedure", ("/", ",", 2)),
        # D47: the truth atom true crosses to Python as True
        "retractall(true)": _err("permission_error", "modify",
                                 "static_procedure", ("/", True, 0)),
    }
    for i, (goal, want) in enumerate(cases.items()):
        mod = native.load(f"dbr_errors_{i}",
                          ERR_SRC + f"t(R) :- e({goal}, R).\n")
        got = ans(mod, "t")
        assert got == [want], goal
    # a string is not callable either (Scryer: type_error(callable, "ab"))
    mod = native.load("dbr_errors_s", ERR_SRC + 't(R) :- e(retract("ab"), R).\n')
    [got] = ans(mod, "t")
    assert got[0] == "error" and got[1][:2] == ("type_error", "callable"), got
    # nothing above removed p(1)
    mod = native.load("dbr_errors_left",
                      ERR_SRC + "t(L) :- findall(X, p(X), L).\n")
    assert ans(mod, "t") == [[1]]


def test_retract_of_a_non_callable_body_fails(native, ans):
    """ISO 8.9.3 / Scryer: ``retract((p(_) :- 1))`` fails -- no clause has
    that body, and 8.9.3.3 has no error for it.  It raised
    type_error(callable, 1)."""
    mod = native.load("dbr_body_1", ERR_SRC + "t(R) :- e(retract((p(_) :- 1)), R).\n"
                      "u(L) :- findall(X, p(X), L).\n")
    assert ans(mod, "t") == []
    assert ans(mod, "u") == [[1]]


def test_retract_drain_does_not_recompile_per_removal(native, ans,
                                                      monkeypatch):
    """A drain of n clauses used to recompile the remaining predicate n-1
    times (O(n^2): ~55 s for 250 clauses).  Now the removals only
    invalidate, and the next call recompiles once."""
    import clausal.logic.compiler.predicate as cp
    n = 60
    src = (":- dynamic(p/1).\n" + "".join(f"p({i}).\n" for i in range(n))
           + "drain :- retract(p(_)), fail.\ndrain.\n"
           + "half :- between(0, 59, I), 0 =:= I mod 2, retract(p(I)), fail.\n"
           + "half.\n"
           + "count(C) :- findall(X, p(X), L), length(L, C).\n")
    mod = native.load("dbr_drain", src)
    real = cp._compile_predicate_trampoline_impl
    calls = []

    def counting(functor, arity, *a, **kw):
        calls.append((functor, arity))
        return real(functor, arity, *a, **kw)

    monkeypatch.setattr(cp, "_compile_predicate_trampoline_impl", counting)
    from clausal.logic.solve import call
    assert list(call("half", module=mod))
    assert ans(mod, "count") == [n // 2]
    # exactly one: the removals compiled nothing, the call recompiled once
    assert calls.count(("p", 1)) == 1, calls
    del calls[:]
    assert list(call("drain", module=mod))
    assert ans(mod, "count") == [0]
    assert calls.count(("p", 1)) <= 1, calls
