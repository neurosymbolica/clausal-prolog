"""W4b-2d task 8: THE FLIP -- every predicate binding a load leaves in a
module dict is a mangled HANDLE, not a ``PredicateMeta`` class.

``compiler_v2._flip_bindings`` runs after step 4a and again after step 6b
(``-specialize`` binds a class there).  The owner is the class's ROW's
database (ruling D1: an import binds the OWNER's handle), a row-less class
takes the compiling db (ruling X3).  ``CLAUSAL_NO_FLIP=1`` switches it off.

Also pinned here, one test each, the engine fixes the flip needed:

* ``$dispatch_at`` carries the compiling db as the ruling-Q0 hint, so a
  handle dispatched from a compiled body resolves even when two live
  modules share its module name (the ``.clausal`` runner loads every
  ``t.clausal`` as ``_clausal_test_t``);
* the direct ``specialize_mi`` API binds a handle into its namespace and
  registers the defining db as that handle's owner (a recursive specialized
  predicate calls itself through it);
* a head naming an imported predicate at an arity the OWNER does not know
  builds the importer's own cell (the name + arity ruling) -- the class era
  got there by re-minting a local class, which a handle binding never does.
"""
from __future__ import annotations

import os
import subprocess
import sys
import textwrap

import pytest

import clausal.import_hook  # noqa: F401 -- installs the meta-path finder
from clausal.import_hook import _load_module
from clausal.logic import compiler_v2
from clausal.logic.atoms import mangle
from clausal.logic.predicate import PredicateMeta
from clausal.logic.solve import call
from clausal.logic.variables import Var, deref, walk
from clausal.testing import load_clausal_module

pytestmark = pytest.mark.skipif(
    not compiler_v2._FLIP, reason="CLAUSAL_NO_FLIP=1: the class era")

FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")


def _write(tmp_path, name, src):
    path = tmp_path / name
    path.write_text(textwrap.dedent(src).lstrip())
    return str(path)


def _load(tmp_path, name, src):
    sys.modules.pop(name, None)
    return _load_module(name, _write(tmp_path, f"{name}.clausal", src))


def _classes(module):
    return sorted(k for k, v in vars(module).items()
                  if isinstance(v, PredicateMeta) and not k.startswith("$"))


def test_every_predicate_binding_is_its_owner_s_handle(tmp_path, monkeypatch):
    monkeypatch.syspath_prepend(str(tmp_path))
    owner = _load(tmp_path, "flip_owner", """
        -module(flip_owner, [colour(C), shade(S)])
        -private([red, blue, dark])
        colour(red),
        colour(blue),
        shade(dark),
    """)
    user = _load(tmp_path, "flip_user", """
        -import_from(flip_owner, [colour, alias(shade, tone)])
        own(X) <- colour(X),
        via_alias(X) <- tone(X),
    """)
    # POSITIVE CONTROL first: these names exist and are predicates.
    assert owner.colour == mangle("flip_owner", "colour")
    assert user.own == mangle("flip_user", "own")
    # D1: an import binds the OWNER's handle -- under an alias too, with the
    # owner's functor.
    assert user.colour == mangle("flip_owner", "colour")
    assert user.tone == mangle("flip_owner", "shade")
    # No class is left in either namespace.
    assert _classes(owner) == [] and _classes(user) == []
    lm = user.__dict__["$module"]
    X = Var()
    assert sorted(walk(deref(X)) for _ in call("own", X, module=lm)) == \
        ["blue", "red"]
    assert [walk(deref(X)) for _ in call("via_alias", X, module=lm)] == \
        ["dark"]


def test_a_specialize_target_is_flipped_after_step_6b():
    """``-specialize`` binds its alias to a CLASS at step 6b, after the first
    flip; the second flip (and the install site itself) make it a handle,
    and the load's own test clauses still run through it."""
    name = "tests.fixtures.specialize_natnum"
    sys.modules.pop(name, None)
    mod = _load_module(name, os.path.join(FIXTURES, "specialize_natnum.clausal"))
    assert mod.solve_count_natnum == mangle(name, "solve_count_natnum")
    assert _classes(mod) == []
    lm = mod.__dict__["$module"]
    assert len(list(call("solve_count_natnum", [["natnum", ["s", 0]]], 2,
                         module=lm))) == 1


def test_the_off_switch_keeps_the_class_era():
    """``CLAUSAL_NO_FLIP=1`` (read at import) leaves the class binding --
    the A/B switch, checked in a fresh interpreter."""
    code = textwrap.dedent("""
        import sys, os
        import clausal.import_hook
        from clausal.import_hook import _load_module
        from clausal.logic.predicate import PredicateMeta
        m = _load_module("_flip_off_probe", os.path.join(
            "tests", "fixtures", "specialize_natnum.clausal"))
        print(type(m.natnum_program).__name__,
              isinstance(m.natnum_program, PredicateMeta))
    """)
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    env = dict(os.environ, CLAUSAL_NO_FLIP="1")
    out = subprocess.run([sys.executable, "-c", code], cwd=root, env=env,
                         capture_output=True, text=True, timeout=300)
    assert out.returncode == 0, out.stderr[-2000:]
    assert out.stdout.split()[-1] == "True", out.stdout


def test_a_body_call_resolves_with_two_live_modules_under_one_name(tmp_path):
    """The ``.clausal`` runner loads every ``t.clausal`` as
    ``_clausal_test_t`` and pops it; with the first still alive, the
    second's compiled bodies dispatched their handles by NAME and raised
    ``AmbiguousHandleOwnerError``.  ``$dispatch_at`` now carries the
    compiling db, so each body resolves into its own module."""
    a = tmp_path / "a"
    b = tmp_path / "b"
    a.mkdir()
    b.mkdir()
    first = load_clausal_module(_write(a, "t.clausal", """
        -private([x])
        base(x),
        top(X) <- base(X),
    """))
    second = load_clausal_module(_write(b, "t.clausal", """
        -private([y])
        base(y),
        top(X) <- base(X),
    """))
    assert first.__name__ == second.__name__ == "_clausal_test_t"
    assert first.top == second.top            # one spelling, two databases
    for mod, want in ((second, "y"), (first, "x")):
        X = Var()
        got = [walk(deref(X))
               for _ in call("top", X, module=mod.__dict__["$module"])]
        assert got == [want]


def test_the_direct_specialize_api_binds_a_handle_and_recursion_runs():
    """``specialize_mi(..., module_dict=, db=)`` on a Python-built Module:
    the namespace gets the handle, the defining db is registered as its
    owner, and the specialized ``natnum`` (which calls ITSELF through that
    handle) answers at depth."""
    import clausal.examples.metainterpreters as mi
    from clausal.logic.database import Module
    from clausal.logic.specialization import analyze_mi, specialize_mi
    name = "_flip_spec_direct"
    m = Module(name, module_dict={"__name__": name})
    x = Var()
    program = [[["natnum", 0], []],
               [["natnum", ["s", x]], [["natnum", x]]]]
    returned = specialize_mi(analyze_mi(mi.solve), program, "SolveNat",
                             db=m.db, module_dict=m.module_dict)
    assert isinstance(returned, PredicateMeta)   # the API still returns it
    assert m.module_dict["SolveNat"] == mangle(name, "SolveNat")
    goal = [["natnum", ["s", ["s", ["s", 0]]]]]
    assert len(list(call("SolveNat", goal, module=m))) == 1
    # The handle alone, with no module named: the defining db is its
    # registered owner (this Module is in no ``sys.modules``).
    from clausal.logic.solve import solve
    handle = m.module_dict["SolveNat"]
    assert len(list(solve((handle, goal)))) == 1


def test_a_local_predicate_at_another_arity_than_an_import_loads():
    """``t5b_dual_arity_clash`` imports the owner's ``t5b_kfact/0`` and
    writes its own ``t5b_kfact/2`` (ruled: it LOADS).  Under the flip the
    head saw the owner's handle, whose one signature is /0, and raised a
    construction error at the fact line."""
    for n in ("tests.fixtures.t5b_dual_arity_clash",
              "tests.fixtures.t5b_dual_owner"):
        sys.modules.pop(n, None)
    use = _load_module("tests.fixtures.t5b_dual_arity_clash",
                       os.path.join(FIXTURES, "t5b_dual_arity_clash.clausal"))
    lm = use.__dict__["$module"]
    A, B = Var(), Var()
    assert [(walk(deref(A)), walk(deref(B)))
            for _ in call("t5b_dac_go", A, B, module=lm)] == [(1, 2)]
    owner_db = sys.modules["tests.fixtures.t5b_dual_owner"].__dict__[
        "$module"].db
    assert owner_db.row("t5b_kfact", 2) is None     # the owner is untouched
    assert lm.db.row("t5b_kfact", 2).clauses
