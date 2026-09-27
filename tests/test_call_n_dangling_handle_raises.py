"""Ruling 2 (operator, 2026-09-24): the ``call/N`` BUILTIN raises on an
unresolvable mangled predicate handle, with the same error term ``solve``
raises for that handle -- it no longer fails silently.

Before: ``solve((H, X))`` on a dangling handle ``H`` (module never loaded, or
loaded but the predicate absent) raised
``error(existence_error(procedure, Name/Arity), Context)``, but a clause body
``use(H, X) <- call(H, X)`` handed the same ``H`` returned no answers:
``higher_order._resolve_named_goal`` returned ``None`` (failure) at the end
of the handle's re-entry.

Scope, pinned by the controls below: only a goal whose functor IS a mangled
handle changes.  A handle that resolves and simply has no matching clause
still fails, and an ordinary (un-mangled) unknown name keeps the translator's
pinned §4.2 contract -- ``call(nosuch, X)`` fails rather than raising.

The comparison is of the ERROR TERMS, not "both raise": the formal part
``existence_error(procedure, Name/Arity)`` must be identical, and the context
must be solve's context with only the entry-point prefix (``solve/1`` vs
``call/2``) changed.

Ruling 2 extended (operator, 2026-09-24): ``phrase/2``, ``phrase/3`` and
``time_goal/1`` share ``call/N``'s resolver and RAISE on a dangling handle
exactly like it -- specified behaviour, pinned below.
"""
from __future__ import annotations

import sys
import textwrap

import pytest

from clausal.logic.atoms import HIDDEN_SEP, mangle
from clausal import cell_args, cell_functor
from clausal.logic.exceptions import LogicException, error_context_text
from clausal.logic.variables import Var


LIB = "calln_dangling_lib"
HOST = "calln_dangling_host"
NOT_LOADED = "calln_no_such_module_zz"


@pytest.fixture(scope="module")
def host(tmp_path_factory):
    from clausal.import_hook import _load_module
    d = tmp_path_factory.mktemp("calln_dangling")
    sys.path.insert(0, str(d))
    try:
        (d / f"{LIB}.clausal").write_text(textwrap.dedent(f"""
            -module({LIB}, [pred(A), flag, pair(A, B)])
            pred(1),
            pred(2),
            flag,
            pair(1, 10),
            pair(2, 20),
        """).lstrip())
        _load_module(LIB, str(d / f"{LIB}.clausal"))
        (d / f"{HOST}.clausal").write_text(textwrap.dedent(f"""
            -module({HOST}, [])
            -private([procedure])
            use1(H, X) <- call(H, X)
            use0(H) <- call(H)
            use2(H, A, B) <- call(H, A, B)
            tg(G) <- time_goal(G)
            ph2(R, L) <- phrase(R, L)
            ph3(R, L, S) <- phrase(R, L, S)
            caught(H, I) <- catch(call(H, 1), error(existence_error(procedure, I), _), True)
        """).lstrip())
        mod = _load_module(HOST, str(d / f"{HOST}.clausal"))
        yield mod.__dict__["$module"]
    finally:
        sys.path.remove(str(d))


def _raised(gen):
    with pytest.raises(LogicException) as info:
        list(gen)
    return info.value.term


def _answers(gen):
    return list(gen)


def _split_context(context: str, prefix: str) -> str:
    assert context.startswith(prefix + ": "), (
        f"context should open with the entry point {prefix!r}: {context!r}")
    return context[len(prefix) + 2:]


def _assert_ruled_shape(term, name, arity):
    assert type(term) is tuple and cell_functor(term) == "error"
    inner = cell_args(term)[0]
    assert cell_functor(inner) == "existence_error"
    assert cell_args(inner)[0] == "procedure"
    culprit = cell_args(inner)[1]
    assert culprit == ("/", name, arity)
    assert HIDDEN_SEP not in error_context_text(term), "never the raw mangled spelling"


@pytest.mark.parametrize("module_name, name", [
    (LIB, "nosuchpred"),        # module loaded, predicate absent
    (NOT_LOADED, "whatever"),   # module never loaded
])
def test_call_n_raises_the_same_error_term_solve_raises(host, module_name, name):
    from clausal.logic.solve import call, solve
    handle = mangle(module_name, name)
    solve_term = _raised(solve((handle, Var())))
    call_term = _raised(call("use1", handle, Var(), module=host))
    _assert_ruled_shape(solve_term, name, 1)
    _assert_ruled_shape(call_term, name, 1)
    # The formal part -- what a catch/3 pattern matches -- is IDENTICAL.
    assert cell_args(call_term)[0] == cell_args(solve_term)[0]
    # The context differs only in naming the entry point.
    assert (_split_context(error_context_text(call_term), "call/2")
            == _split_context(error_context_text(solve_term), "solve/1"))


@pytest.mark.parametrize("module_name, name", [
    (LIB, "nosuchpred"),
    (NOT_LOADED, "whatever"),
])
def test_call_1_on_a_bare_dangling_handle_raises(host, module_name, name):
    """Arity 0: ``call(H)``.  (``solve(H)`` on a bare arity-0 handle does not
    yet give the ruled shape -- a separate, pre-existing gap -- so this pins
    the shape rather than comparing with solve.)"""
    from clausal.logic.solve import call
    term = _raised(call("use0", mangle(module_name, name), module=host))
    _assert_ruled_shape(term, name, 0)
    assert error_context_text(term).startswith("call/1: ")


# ── controls: what must NOT change ────────────────────────────────────────────

def test_a_resolvable_handle_with_no_matching_clause_still_just_fails(host):
    from clausal.logic.solve import call
    assert _answers(call("use1", mangle(LIB, "pred"), 99, module=host)) == []


def test_a_resolvable_handle_still_answers(host):
    from clausal.logic.solve import call
    assert len(_answers(call("use1", mangle(LIB, "pred"), Var(), module=host))) == 2
    assert len(_answers(call("use0", mangle(LIB, "flag"), module=host))) == 1


def test_an_unmangled_unknown_name_raises_existence_error(host):
    """FLIPPED 2026-09-25 -- operator ruling 2 ("like Scryer"): a meta-call naming an UNKNOWN procedure raises ISO existence_error(procedure, Name/Arity), catchable; it used to fail silently (the retired §4.2 contract).

    This used to be ``test_an_unmangled_unknown_name_still_fails_silently``
    (the translator's pinned §4.2 contract, untouched by the 2026-09-24
    handle ruling)."""
    from clausal.logic.solve import call
    for gen, arity in ((call("use1", "calln_nosuch_plain", Var(), module=host), 1),
                       (call("use0", "calln_nosuch_plain", module=host), 0)):
        formal = cell_args(_raised(gen))[0]
        assert cell_functor(formal) == "existence_error"
        assert cell_args(formal)[0] == "procedure"
        assert cell_args(formal)[1] == ("/", "calln_nosuch_plain", arity)


# ── call/3+: call/N's extras fold into the handle's goal ─────────────────────

@pytest.mark.parametrize("module_name, name", [
    (LIB, "nosuchpred"),
    (NOT_LOADED, "whatever"),
])
def test_call_3_extras_fold_into_a_dangling_handle(host, module_name, name):
    """``call(H, A, B)`` is the goal ``H(A, B)``: arity 2 in the culprit."""
    from clausal.logic.solve import call, solve
    handle = mangle(module_name, name)
    solve_term = _raised(solve((handle, 1, Var())))
    call_term = _raised(call("use2", handle, 1, Var(), module=host))
    _assert_ruled_shape(call_term, name, 2)
    assert cell_args(call_term)[0] == cell_args(solve_term)[0]
    assert (_split_context(error_context_text(call_term), "call/3")
            == _split_context(error_context_text(solve_term), "solve/1"))


@pytest.mark.parametrize("module_name, name", [
    (LIB, "nosuchpred"),
    (NOT_LOADED, "whatever"),
])
def test_call_2_on_a_handle_cell_folds_its_own_args_first(host, module_name, name):
    """``call(H(1), X)`` is ``H(1, X)``: the cell's argument, then the extra."""
    from clausal.logic.solve import call, solve
    handle = mangle(module_name, name)
    solve_term = _raised(solve((handle, 1, Var())))
    call_term = _raised(call("use1", (handle, 1), Var(), module=host))
    _assert_ruled_shape(call_term, name, 2)
    assert cell_args(call_term)[0] == cell_args(solve_term)[0]


def test_call_3_and_a_handle_cell_still_answer_when_the_handle_resolves(host):
    from clausal.logic.solve import call
    from clausal.logic.variables import deref
    h = mangle(LIB, "pair")
    Y = Var()
    assert [deref(Y) for _ in call("use2", h, 1, Y, module=host)] == [10]
    Z = Var()
    assert [deref(Z) for _ in call("use1", (h, 2), Z, module=host)] == [20]
    assert _answers(call("use2", h, 1, 99, module=host)) == []


# ── ruling 2 extended: phrase/2, phrase/3, time_goal/1 ──────────────────────

@pytest.mark.parametrize("module_name, name", [
    (LIB, "nosuchpred"),
    (NOT_LOADED, "whatever"),
])
def test_time_goal_raises_the_same_error_term_solve_raises(host, module_name, name):
    from clausal.logic.solve import call, solve
    handle = mangle(module_name, name)
    solve_term = _raised(solve((handle, 1)))
    term = _raised(call("tg", (handle, 1), module=host))
    _assert_ruled_shape(term, name, 1)
    assert cell_args(term)[0] == cell_args(solve_term)[0]
    assert (_split_context(error_context_text(term), "time_goal/1")
            == _split_context(error_context_text(solve_term), "solve/1"))


@pytest.mark.parametrize("module_name, name", [
    (LIB, "nosuchpred"),
    (NOT_LOADED, "whatever"),
])
def test_phrase_2_raises_the_same_error_term_solve_raises(host, module_name, name):
    """``phrase(H, L)`` names ``H/2`` -- the goal ``solve((H, L, []))``.
    Ruling C (2026-09-24): the nonterminal term is its WRITTEN arity (the bare
    handle for H//0) and phrase appends S0/S; it used to be a cell padded with
    the pair, which phrase dropped."""
    from clausal.logic.solve import call, solve
    handle = mangle(module_name, name)
    solve_term = _raised(solve((handle, Var(), Var())))
    term = _raised(call("ph2", handle, [], module=host))
    _assert_ruled_shape(term, name, 2)
    assert cell_args(term)[0] == cell_args(solve_term)[0]
    assert (_split_context(error_context_text(term), "phrase/2")
            == _split_context(error_context_text(solve_term), "solve/1"))


@pytest.mark.parametrize("module_name, name", [
    (LIB, "nosuchpred"),
    (NOT_LOADED, "whatever"),
])
def test_phrase_3_raises_the_same_error_term_solve_raises(host, module_name, name):
    """``phrase(H(5), L, R)`` names ``H/3``: the cell's own argument, then
    phrase's S0/S pair."""
    from clausal.logic.solve import call, solve
    handle = mangle(module_name, name)
    solve_term = _raised(solve((handle, 5, Var(), Var())))
    term = _raised(call("ph3", (handle, 5), [], Var(), module=host))   # written arity (ruling C)
    _assert_ruled_shape(term, name, 3)
    assert cell_args(term)[0] == cell_args(solve_term)[0]
    assert (_split_context(error_context_text(term), "phrase/3")
            == _split_context(error_context_text(solve_term), "solve/1"))


def test_time_goal_still_runs_a_resolvable_handle(host):
    from clausal.logic.solve import call
    assert len(_answers(call("tg", (mangle(LIB, "pred"), 1), module=host))) == 1


# ── caught from inside the language ──────────────────────────────────────────

@pytest.mark.parametrize("module_name, name", [
    (LIB, "nosuchpred"),
    (NOT_LOADED, "whatever"),
])
def test_catch_3_in_a_clause_body_catches_it(host, module_name, name):
    """``catch(call(H, 1), error(existence_error(procedure, I), _), true)``
    in a .clausal body.  (The indicator is bound whole: an ``N / A`` pattern
    written in a .clausal body does not unify with the ``'/'(Name, Arity)``
    term -- a separate, pre-existing matter of how that pattern lowers.)"""
    from clausal.logic.solve import call
    from clausal.logic.variables import deref
    I = Var()
    got = [deref(I) for _ in call("caught", mangle(module_name, name), I, module=host)]
    assert got == [("/", name, 1)]


# ── the ``-hide`` spelling rule: raise only AFTER the calling db's lookups ────

def test_a_mangled_spelling_the_calling_db_defines_resolves_and_does_not_raise(host):
    """A ``-hide`` atom carries its BARE declared module name, which need not
    be a loaded module's import name -- so ``qualify_mangled_goal`` leaves it
    alone, and the calling db may define a predicate under exactly that
    spelling.  The language refuses to write one (a ``-hide`` name cannot be a
    functor), so it is installed from Python: declared dynamic, then
    asserted.  ``call/N`` must find it, not raise."""
    from clausal.logic.predicate import _db_for_module_name
    from clausal.logic.solve import call, solve
    from clausal.logic.variables import deref
    decl = "calln_hidden_decl_zz"
    assert _db_for_module_name(decl) is None, "precondition: not a loaded module"
    h = mangle(decl, "secretp")
    host.db.mark_dynamic(h, 1)
    assert len(_answers(solve(("assertz", (h, 7)), module=host))) == 1
    assert host.db.get_dispatch(h, 1) is not None
    X = Var()
    assert [deref(X) for _ in call("use1", h, X, module=host)] == [7]
    # ...and a DIFFERENT name under the same unloaded module half still raises.
    term = _raised(call("use1", mangle(decl, "other"), Var(), module=host))
    _assert_ruled_shape(term, "other", 1)


# ── call/N reached with NO db (the factory's ``_db_optional`` path) ──────────

def test_no_db_a_dangling_unloaded_handle_raises():
    """With no db nothing can answer to a ``-hide`` spelling, so an unloaded-
    module handle is decided at once rather than failed."""
    from clausal.logic.builtins.higher_order import _resolve_named_goal
    with pytest.raises(LogicException) as info:
        _resolve_named_goal(None, mangle(NOT_LOADED, "whatever"), (Var(),), "call/2")
    _assert_ruled_shape(info.value.term, "whatever", 1)
    assert error_context_text(info.value.term).startswith("call/2: module ")


def test_no_db_through_the_call_goal_factory_raises():
    """The same, through the real ``call/2`` dispatch built with ``db=None``."""
    from clausal.logic.builtins._registry import _DB_BUILTINS
    from clausal.logic.solve import _drive_trampoline
    from clausal.logic.variables import Trail
    dispatch = _DB_BUILTINS[("call_goal", 2)](None)
    with pytest.raises(LogicException) as info:
        list(_drive_trampoline(dispatch, Trail(), mangle(NOT_LOADED, "whatever"), Var()))
    _assert_ruled_shape(info.value.term, "whatever", 1)


def test_no_db_an_unmangled_name_still_fails():
    from clausal.logic.builtins.higher_order import _resolve_named_goal
    assert _resolve_named_goal(None, "calln_nosuch_plain", (Var(),), "call/2") is None
