"""Ruling R14 (2026-09-29): ``Module.declare_dynamic(name, arity)`` is the
covered Python spelling of ``-dynamic(name/arity)``.

Under declare-first, ``assertz`` adds clauses only to a ``-dynamic``
predicate, so without it a ``Module`` built from Python had no way to
receive an assert.  Errors are ISO ``dynamic/1``'s.
"""
import pytest

import clausal.import_hook  # noqa: F401 -- installs the meta-path finder
from clausal import LogicException, Module, Var, solve
from clausal.import_hook import _load_module
from clausal.logic.solve import _deref_walk


def _answers(goal_fn, m):
    x = Var()
    return [_deref_walk(x) for _ in solve(goal_fn(x), module=m)]


def test_fresh_module_refuses_assert_until_declared():
    m = Module("r14_fresh")
    with pytest.raises(LogicException) as exc:
        list(solve(("assertz", ("p", 1)), module=m))
    assert exc.value.term[1] == (
        "permission_error", "modify", "static_procedure", ("/", "p", 1))
    m.declare_dynamic("p", 1)
    assert _answers(lambda x: ("p", x), m) == []       # declared: fails, no error
    assert len(list(solve(("assertz", ("p", 1)), module=m))) == 1
    assert len(list(solve(("assertz", ("p", 2)), module=m))) == 1
    assert _answers(lambda x: ("p", x), m) == [1, 2]
    assert len(list(solve(("retract", ("p", 1)), module=m))) == 1
    assert _answers(lambda x: ("p", x), m) == [2]


def test_zero_arity():
    m = Module("r14_zero")
    m.declare_dynamic("flag", 0)
    assert list(solve("flag", module=m)) == []
    list(solve(("assertz", "flag"), module=m))
    assert len(list(solve("flag", module=m))) == 1


def test_idempotent():
    m = Module("r14_idem")
    m.declare_dynamic("p", 1)
    list(solve(("assertz", ("p", 1)), module=m))
    m.declare_dynamic("p", 1)          # again, now with a clause: still fine
    assert _answers(lambda x: ("p", x), m) == [1]


def test_only_that_arity():
    m = Module("r14_arity")
    m.declare_dynamic("p", 1)
    with pytest.raises(LogicException):
        list(solve(("assertz", ("p", 1, 2)), module=m))


@pytest.mark.parametrize("name, arity, formal", [
    (Var(), 1, "instantiation_error"),
    ("p", Var(), "instantiation_error"),
    (1, 1, ("type_error", "atom", 1)),
    (("$chars", "p"), 1, ("type_error", "atom", ("$chars", "p"))),
    ("p", "1", ("type_error", "integer", "1")),
    ("p", 1.0, ("type_error", "integer", 1.0)),
    ("p", True, ("type_error", "integer", True)),
    ("p", -1, ("domain_error", "not_less_than_zero", -1)),
])
def test_bad_arguments(name, arity, formal):
    m = Module("r14_bad")
    with pytest.raises(LogicException) as exc:
        m.declare_dynamic(name, arity)
    assert exc.value.term[1] == formal
    assert exc.value.term[2] == ("/", "dynamic", 1)


def test_builtin_is_a_static_procedure():
    m = Module("r14_builtin")
    with pytest.raises(LogicException) as exc:
        m.declare_dynamic("atom_length", 2)
    assert exc.value.term[1] == (
        "permission_error", "modify", "static_procedure",
        ("/", "atom_length", 2))


def test_static_predicate_with_clauses_is_refused(tmp_path):
    src = tmp_path / "r14_static.clausal"
    src.write_text("-dynamic(d/1)\ns(1),\nd(1),\n")
    mod = _load_module("r14_static", str(src))
    m = mod.__clausal_module__
    with pytest.raises(LogicException) as exc:
        m.declare_dynamic("s", 1)
    assert exc.value.term[1] == (
        "permission_error", "modify", "static_procedure", ("/", "s", 1))
    m.declare_dynamic("d", 1)             # already dynamic: a no-op
    m.declare_dynamic("fresh", 2)         # new in a loaded module: fine
    list(solve(("assertz", ("fresh", 1, 2)), module=m))
    x = Var()
    assert [_deref_walk(x) for _ in solve(("fresh", 1, x), module=m)] == [2]
