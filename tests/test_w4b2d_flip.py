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


# ── A predicate no Clausal Database owns stays bound as it is (roborev) ──

_PY_EXPORTER = '''
from clausal.logic.predicate import PredicateMeta, make_predicate
from clausal.logic.compiler import compile_predicate_trampoline
from clausal.logic.database import Clause


class pycls(metaclass=PredicateMeta):     # a class statement in Python
    _fields = ("x",)


pymk = make_predicate("pymk", ["x"])      # make_predicate, compiled db=None

for _p, _vals in ((pycls, (1, 2)), (pymk, (7, 8))):
    compile_predicate_trampoline(
        _p.__name__, 1,
        [Clause(head=(_p.__name__, v), body=[]) for v in _vals],
        None, pred_cls=_p)
'''

_PY_IMPORTER = '''
-import_from(flip_pyexp, [pycls, pymk])
via_cls(X) <- pycls(X),
via_mk(X) <- pymk(X),
'''

_PY_PROBE = '''
import sys
sys.path.insert(0, sys.argv[1])
import clausal.import_hook, importlib, json
from clausal.logic.solve import call
from clausal.logic.variables import Var, deref
from clausal.logic.predicate import PredicateMeta
m = importlib.import_module("flip_pyuse")
lm = m.__dict__["$module"]
out = {}
for goal in ("via_cls", "via_mk", "pycls", "pymk"):
    X = Var()
    try:
        out[goal] = sorted(deref(X) for _ in call(goal, X, module=lm))
    except Exception as e:
        out[goal] = type(e).__name__
out["classes"] = sorted(k for k in ("pycls", "pymk")
                        if isinstance(m.__dict__[k], PredicateMeta))
print(json.dumps(out))
'''


def test_a_python_exported_predicate_answers_as_it_does_without_the_flip(
        tmp_path):
    """``-import_from(py_mod, [p])`` of a class a plain PYTHON module
    defines, or a ``make_predicate`` class compiled with ``db=None``: no
    Clausal Database owns it, so a handle minted from the importer would
    name a predicate the importer does not have (``PredicateNotFoundError``
    on every call).  Its own ``_get_dispatch()`` answers, flip or no flip
    -- called from a body AND by name -- and the binding stays the class."""
    (tmp_path / "flip_pyexp.py").write_text(_PY_EXPORTER)
    (tmp_path / "flip_pyuse.clausal").write_text(
        textwrap.dedent(_PY_IMPORTER).lstrip())
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    results = {}
    for era, extra in (("flip", {}), ("class", {"CLAUSAL_NO_FLIP": "1"})):
        env = {k: v for k, v in os.environ.items() if k != "CLAUSAL_NO_FLIP"}
        env.update(extra)
        env["PYTHONPATH"] = os.pathsep.join(
            [root] + [p for p in env.get("PYTHONPATH", "").split(os.pathsep)
                      if p])
        proc = subprocess.run(
            [sys.executable, "-c", _PY_PROBE, str(tmp_path)], cwd=root,
            env=env, capture_output=True, text=True, timeout=300)
        assert proc.returncode == 0, proc.stderr[-2000:]
        results[era] = proc.stdout.strip().splitlines()[-1]
    import json
    flip = json.loads(results["flip"])
    assert flip == {"via_cls": [1, 2], "via_mk": [7, 8], "pycls": [1, 2],
                    "pymk": [7, 8], "classes": ["pycls", "pymk"]}, flip
    assert results["flip"] == results["class"]


def _outcome(fn):
    try:
        return ("ok", fn())
    except Exception as e:  # noqa: BLE001 -- the TYPE is what is compared
        return ("raised", type(e).__name__)


def test_the_hinted_fast_path_answers_what_the_handle_arm_answers(tmp_path):
    """``$dispatch_at``'s fast path for a handle naming the compiling module
    gives the general handle arm's answer.  Pinned for the shape roborev
    doubted: a mangled str of that module with no row, spelled like the
    builtin ``atom_length/2``.  ``Database.get_dispatch`` falls back to the
    builtin -- and so does the general arm, which resolves the owner to the
    hint and asks ``get_dispatch`` first; the two must not diverge."""
    from clausal.logic.compiler.predicate import _dispatch_at_for
    from clausal.logic.predicate import _dispatch_at
    mod = _load(tmp_path, "flip_fast", """
        -private([a])
        own(a),
    """)
    db = mod.__dict__["$module"].db
    hinted = _dispatch_at_for(db)
    # POSITIVE CONTROL: the local predicate IS answered by the fast path,
    # with the very function the general arm returns.
    assert hinted(mod.own, 1) is _dispatch_at(mod.own, 1, db)
    stray = mangle(db.module_name(), "atom_length")
    assert db.row("atom_length", 2) is None
    assert _outcome(lambda: hinted(stray, 2)) == \
        _outcome(lambda: _dispatch_at(stray, 2, db))


def test_a_new_arity_local_predicate_keeps_head_order_across_heads(tmp_path,
                                                                   monkeypatch):
    """The ``"local"`` head (a local ``kp/2`` beside an imported ``kp/1``)
    is built in written order.  The rewriter's keywords are derived per
    head (``first=FIRST``, ``other=OTHER``) and emitted in head order, so
    differently-named heads build the same positional cell; a keyword head
    the USER writes is refused before the body runs."""
    monkeypatch.syspath_prepend(str(tmp_path))
    _load(tmp_path, "flip_kw_owner", """
        -module(flip_kw_owner, [kp(X)])
        kp(1),
    """)
    use = _load(tmp_path, "flip_kw_user", """
        -module(flip_kw_user, [go(A, B)])
        -import_from(flip_kw_owner, [kp])
        kp(FIRST, SECOND) <- (FIRST is 5, SECOND is 6),
        kp(OTHER, NAME) <- (OTHER is 7, NAME is 8),
        go(A, B) <- kp(A, B),
    """)
    A, B = Var(), Var()
    assert [(deref(A), deref(B)) for _ in call(
        "go", A, B, module=use.__dict__["$module"])] == [(5, 6), (7, 8)]
    with pytest.raises(SyntaxError, match="keyword arguments"):
        _load(tmp_path, "flip_kw_user2", """
            -module(flip_kw_user2, [])
            -import_from(flip_kw_owner, [kp])
            kp(b=1, a=2),
        """)
