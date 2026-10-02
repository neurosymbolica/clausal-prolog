"""W4's Python boundary (ruled 2026-09-22): a predicate HANDLE is the
module-qualified atom -- the `-hide` mangling ``module<US>name`` -- and it
resolves with no ``module=`` anywhere a goal is accepted.

Two pieces, both additive (a class-bound name keeps working as before):

1. the ``--`` seam's functor slot accepts a NAME bound to an atom value, so
   ``h = <qualified atom>; --h(X)`` builds a cell.  Since 2026-09-25 (operator
   ruling, option (a)) that cell is the PLAIN ``(pred, X)``: ISO functors are
   never module-qualified, and a goal that must run in the module is written
   ``(":", M, G)``;
2. a cell whose functor is mangled is a module-qualified goal at every
   entry point -- ``solve``, ``call/N``, and the runtime funnel
   ``_dispatch_at`` -- normalised to the ``(":", M, G)`` form the engine
   already resolves.
"""
import sys
import textwrap

import pytest

from clausal import cell_args, cell_functor
from clausal.logic.atoms import mangle
from clausal.logic.variables import Var, deref
from tests._suffix import SEAM


LIB = "w4qlib"


@pytest.fixture
def lib(tmp_path, monkeypatch):
    from clausal.import_hook import _load_module
    monkeypatch.syspath_prepend(str(tmp_path))
    p = tmp_path / f"{LIB}{SEAM}"
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
    p = tmp_path / f"{name}{SEAM}"
    p.write_text(f"-module({name}, [])\n-import_module({LIB})\n" + textwrap.dedent(body))
    return _load_module(name, str(p))


# ── piece 1: the seam's functor slot ────────────────────────────────────────

def test_a_name_bound_to_a_qualified_atom_builds_the_plain_cell(lib, tmp_path):
    """FLIPPED 2026-09-25 -- operator ruling 2026-09-25, option (a).

    This used to be ``test_a_name_bound_to_a_qualified_atom_builds_the_
    qualified_cell``: the cell's functor was the handle's MANGLED spelling,
    so the module travelled in the cell.  ISO: a functor is never
    module-qualified; qualification lives only on a goal (``M:G``).  A cell
    built from a handle is PLAIN, like the one its owner builds, and it runs
    in its module as ``(":", M, cell)`` or ``solve(cell, M)``."""
    from clausal.logic.solve import solve
    host = _host(tmp_path, "w4host_seam", f"""
        from clausal.logic.atoms import mangle
        h = mangle("{LIB}", "pred")
        def build():
            return --h(X)
    """)
    cell = host.build()
    assert cell[0] == "pred", "the functor is the predicate's plain name"
    assert len(cell) == 2
    assert sorted(deref(cell[1]) for _ in solve((":", LIB, cell))) == [1, 2]


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
    assert cell_functor(cell_args(info.value.term)[0]) == "existence_error"


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


# ── review round (roborev on 2dc84e40): the handle's module half, imports, strictness ──

def test_a_name_bound_to_a_plain_string_is_still_refused_in_a_strict_module(lib, tmp_path):
    """Only a MANGLED atom is a handle.  A name bound to a plain string must
    not bypass the declared-functor check a strict module relies on."""
    host = _host(tmp_path, "w4host_plain", """
        h = "undeclared"
        def build():
            return --h(X)
    """)
    with pytest.raises(NameError):
        host.build()


def test_the_handle_module_half_is_the_import_name_of_a_package_nested_module(tmp_path, monkeypatch):
    """A module inside a package registers under its DOTTED import name; the
    handle carries that, and resolves.  (The `-hide` mangling of a data atom
    carries the bare declared name instead; see the next test.)"""
    from clausal.import_hook import _load_module
    from clausal.logic.solve import solve
    monkeypatch.syspath_prepend(str(tmp_path))
    pkg = tmp_path / "w4pkg"; pkg.mkdir()
    (pkg / "__init__.py").write_text("")
    (pkg / f"inner{SEAM}").write_text("-module(inner, [pred(A)])\npred(9),\n")
    _load_module("w4pkg.inner", str(pkg / f"inner{SEAM}"))
    X = Var()
    assert [deref(X) for _ in solve((mangle("w4pkg.inner", "pred"), X))] == [9]


def test_a_mangled_atom_whose_module_is_not_loaded_keeps_the_atom_error(lib):
    """A `-hide` data atom carries its BARE declared module name, which need
    not be an import name.  Reaching the funnel with one is the pre-existing
    'atom is not callable' mistake, not a new 'no such module' one."""
    from clausal.logic.exceptions import LogicException
    from clausal.logic.predicate import _dispatch_at
    with pytest.raises(LogicException) as info:
        _dispatch_at(mangle("no_such_module_anywhere", "secret"), 1)
    inner = cell_args(info.value.term)[0]
    assert cell_functor(inner) == "existence_error" and cell_args(inner)[0] == "procedure"


def test_the_funnel_resolves_a_handle_to_an_imported_predicate(lib, tmp_path):
    """A predicate a module obtained via -import_from lives on the EXPORTER's
    row; the handle names the importer, and the funnel must follow the import
    the way call/N does."""
    from clausal.import_hook import _load_module
    from clausal.logic.predicate import _dispatch_at
    p = tmp_path / f"w4importer{SEAM}"
    p.write_text(f"-module(w4importer, [])\n-import_from({LIB}, [pred])\nuse(X) <- pred(X)\n")
    _load_module("w4importer", str(p))
    assert callable(_dispatch_at(mangle("w4importer", "pred"), 1))


def test_a_mangled_inner_goal_under_an_explicit_qualification_wins(lib, tmp_path):
    """Innermost qualification wins, for the mangled spelling as for `:`."""
    from clausal.import_hook import _load_module
    from clausal.logic.solve import solve
    p = tmp_path / f"w4other{SEAM}"
    p.write_text("-module(w4other, [pred(A)])\npred(77),\n")
    _load_module("w4other", str(p))
    X = Var()
    got = sorted(deref(X) for _ in solve((":", "w4other", (mangle(LIB, "pred"), X))))
    assert got == [1, 2], "the handle names its own module, not the outer one"


def test_an_explicit_module_argument_is_overridden_by_the_handle(lib, tmp_path):
    from clausal.import_hook import _load_module
    from clausal.logic.solve import call, solve
    p = tmp_path / f"w4other2{SEAM}"
    p.write_text("-module(w4other2, [pred(A)])\npred(77),\n")
    other = _load_module("w4other2", str(p))
    X = Var()
    assert sorted(deref(X) for _ in solve((mangle(LIB, "pred"), X), module=other)) == [1, 2]
    Y = Var()
    assert sorted(deref(Y) for _ in call(mangle(LIB, "pred"), Y, module=other)) == [1, 2]


def test_a_missing_predicate_error_names_the_module_in_its_indicator(lib):
    """Ruling 2026-09-24 (todo/mangled-goal-culprit-terms-are-malformed-
    2026-09-23.md) supersedes this test's original shape: the culprit is a
    bare ``Name/Arity`` indicator, never a module-qualified ``':'`` compound
    -- the module the handle named is reported in the MESSAGE instead, so a
    ``catch/3`` pattern against a dangling handle is the same shape whether
    the module never loaded or (this case) loaded but the predicate does
    not exist in it."""
    from clausal.logic.exceptions import LogicException
    from clausal.logic.predicate import _dispatch_at
    with pytest.raises(LogicException) as info:
        _dispatch_at(mangle(LIB, "nope"), 2)
    inner = cell_args(info.value.term)[0]
    assert cell_functor(inner) == "existence_error"
    obj_type, indicator = cell_args(inner)
    assert obj_type == "procedure"
    assert cell_functor(indicator) == "/" and cell_args(indicator) == ("nope", 2)
    assert LIB in info.value.message, "the module is named in the message"
