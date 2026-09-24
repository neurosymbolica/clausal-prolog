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
"""
from __future__ import annotations

import sys
import textwrap

import pytest

from clausal.logic.atoms import HIDDEN_SEP, mangle
from clausal.logic.exceptions import LogicException
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
            -module({LIB}, [pred(A), flag])
            pred(1),
            pred(2),
            flag,
        """).lstrip())
        _load_module(LIB, str(d / f"{LIB}.clausal"))
        (d / f"{HOST}.clausal").write_text(textwrap.dedent(f"""
            -module({HOST}, [])
            use1(H, X) <- call(H, X)
            use0(H) <- call(H)
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
    assert term.functor == "error"
    inner = term.args[0]
    assert inner.functor == "existence_error"
    assert inner.args[0] == "procedure"
    culprit = inner.args[1]
    assert culprit.functor == "/" and tuple(culprit.args) == (name, arity)
    assert HIDDEN_SEP not in term.args[1], "never the raw mangled spelling"


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
    assert call_term.args[0] == solve_term.args[0]
    # The context differs only in naming the entry point.
    assert (_split_context(call_term.args[1], "call/2")
            == _split_context(solve_term.args[1], "solve/1"))


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
    assert term.args[1].startswith("call/1: ")


# ── controls: what must NOT change ────────────────────────────────────────────

def test_a_resolvable_handle_with_no_matching_clause_still_just_fails(host):
    from clausal.logic.solve import call
    assert _answers(call("use1", mangle(LIB, "pred"), 99, module=host)) == []


def test_a_resolvable_handle_still_answers(host):
    from clausal.logic.solve import call
    assert len(_answers(call("use1", mangle(LIB, "pred"), Var(), module=host))) == 2
    assert len(_answers(call("use0", mangle(LIB, "flag"), module=host))) == 1


def test_an_unmangled_unknown_name_still_fails_silently(host):
    """The translator's pinned §4.2 contract, untouched by ruling 2."""
    from clausal.logic.solve import call
    assert _answers(call("use1", "calln_nosuch_plain", Var(), module=host)) == []
    assert _answers(call("use0", "calln_nosuch_plain", module=host)) == []
