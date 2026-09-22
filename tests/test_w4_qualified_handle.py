"""W4's Python boundary (ruled 2026-09-22): a predicate HANDLE is the
module-qualified atom -- the `-hide` mangling ``module<US>name`` -- and it
resolves with no ``module=`` anywhere a goal is accepted.

Two pieces, both additive (a class-bound name keeps working as before):

1. the ``--`` seam's functor slot accepts a NAME bound to an atom value, so
   ``h = <qualified atom>; --h(X)`` builds ``(<qualified atom>, X)`` and the
   module travels inside the cell;
2. a cell whose functor is mangled is a module-qualified goal at every
   entry point -- ``solve``, ``call/N``, and the runtime funnel
   ``_dispatch_at`` -- normalised to the ``(":", M, G)`` form the engine
   already resolves.
"""
import sys
import textwrap

import pytest

from clausal.logic.atoms import mangle
from clausal.logic.variables import Var, deref


LIB = "w4qlib"


@pytest.fixture
def lib(tmp_path, monkeypatch):
    from clausal.import_hook import _load_module
    monkeypatch.syspath_prepend(str(tmp_path))
    p = tmp_path / f"{LIB}.clausal"
    p.write_text(textwrap.dedent(f"""
        -module({LIB}, [pred(A), flag])
        pred(1),
        pred(2),
        flag,
    """).lstrip())
    mod = _load_module(LIB, str(p))
    assert sys.modules[LIB] is mod
    return mod


def _host(tmp_path, name, body):
    from clausal.import_hook import _load_module
    p = tmp_path / f"{name}.clausal"
    p.write_text(f"-module({name}, [])\n-import_module({LIB})\n" + textwrap.dedent(body))
    return _load_module(name, str(p))


# ── piece 1: the seam's functor slot ────────────────────────────────────────

def test_a_name_bound_to_a_qualified_atom_builds_the_qualified_cell(lib, tmp_path):
    host = _host(tmp_path, "w4host_seam", f"""
        from clausal.logic.atoms import mangle
        h = mangle("{LIB}", "pred")
        def build():
            return --h(X)
    """)
    cell = host.build()
    assert cell[0] == mangle(LIB, "pred"), "the functor is the handle's spelling"
    assert len(cell) == 2


def test_a_name_bound_to_a_class_still_builds_the_bare_cell(lib, tmp_path):
    """The pre-W4 binding: unchanged (this is what the downstream bodies hold
    today, and the migration must work against either binding)."""
    host = _host(tmp_path, "w4host_cls", f"""
        h = {LIB}.pred
        def build():
            return --h(X)
    """)
    assert host.build()[0] == "pred"


def test_a_name_bound_to_a_non_atom_value_is_still_refused(lib, tmp_path):
    host = _host(tmp_path, "w4host_int", """
        h = 42
        def build():
            return --h(X)
    """)
    with pytest.raises((NameError, SyntaxError)):
        host.build()


# ── piece 2: the entry points resolve a mangled functor ─────────────────────

def _answers(trails, var):
    return sorted(deref(var) for _ in trails) if False else None


def test_solve_resolves_a_qualified_cell_with_no_module(lib):
    from clausal.logic.solve import solve
    X = Var()
    got = sorted(deref(X) for _ in solve((mangle(LIB, "pred"), X)))
    assert got == [1, 2]


def test_solve_resolves_a_bare_qualified_atom_as_an_arity_0_goal(lib):
    from clausal.logic.solve import solve
    assert len(list(solve(mangle(LIB, "flag")))) == 1


def test_call_n_resolves_a_qualified_name_with_no_module(lib):
    from clausal.logic.solve import call
    X = Var()
    got = sorted(deref(X) for _ in call(mangle(LIB, "pred"), X))
    assert got == [1, 2]


def test_the_runtime_funnel_resolves_a_qualified_atom(lib):
    from clausal.logic.predicate import _dispatch_at
    fn = _dispatch_at(mangle(LIB, "pred"), 1)
    assert callable(fn)


def test_a_qualified_atom_for_a_missing_predicate_is_an_existence_error(lib):
    from clausal.logic.exceptions import LogicException
    from clausal.logic.predicate import _dispatch_at
    with pytest.raises(LogicException) as info:
        _dispatch_at(mangle(LIB, "nope"), 1)
    assert info.value.term.args[0].functor == "existence_error"


def test_a_compiled_body_calling_a_held_qualified_handle_runs_it(lib, tmp_path):
    """END TO END: a clause body calls a NAME bound to the qualified atom.
    The compiler lowers that to ``$dispatch_at(h, 1)``; the funnel resolves
    the handle in its own module."""
    from clausal.logic.solve import call
    host = _host(tmp_path, "w4host_body", f"""
        from clausal.logic.atoms import mangle
        h = mangle("{LIB}", "pred")
        use(X) <- h(X)
    """)
    X = Var()
    got = sorted(deref(X) for _ in call("use", X, module=host.__dict__["$module"]))
    assert got == [1, 2]
