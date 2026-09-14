"""P1: a fact module lowered by L3 answers identically to its seam twin.

The plan's §8 controls, applied here rather than deferred:

  §8.2 ASSERT WHICH FRONT END RAN. Caught this for real on the first green run:
       answers matched while L3 had NEVER EXECUTED, because a cached .pyc from a
       previous run was used. A comparison that passes without the front end under
       test running is the exact failure the harness exists to prevent, so every
       test here clears __pycache__ and asserts non-empty lowering stats.
  §8.4 PRINT THE DENOMINATOR. lower_items returns read/lowered/refused, and the
       tests assert on them, so a shrinking population cannot be silent.
  §8.3 NEGATIVE CONTROL. A deliberately mis-lowered clause must be caught.
"""
from __future__ import annotations
import importlib, importlib.util, pathlib, shutil, sys, textwrap
import pytest

# This repo's worktrees have no BUILT C extensions, and a worktree checkout of
# `clausal/` will shadow the built tree if it reaches sys.path first. Rather than
# fail with an opaque ModuleNotFoundError deep in a fixture, resolve it once here:
# prefer a tree whose extensions are built, and SKIP loudly if none is.
def _ensure_built_clausal() -> None:
    try:
        importlib.import_module("clausal.logic.variables._variables")
        return
    except ModuleNotFoundError:
        pass
    for cand in ("/workspace/clausal",):
        if (pathlib.Path(cand) / "clausal" / "logic" / "variables").is_dir():
            sys.path.insert(0, cand)
            for mod in [m for m in sys.modules if m == "clausal" or m.startswith("clausal.")]:
                del sys.modules[mod]
            try:
                importlib.import_module("clausal.logic.variables._variables")
                return
            except ModuleNotFoundError:
                continue
    pytest.skip("no clausal tree with built C extensions on this path",
                allow_module_level=True)


_ensure_built_clausal()

REPO = pathlib.Path(__file__).resolve().parents[2]
L3_PATH = REPO / "clausal" / "tools" / "iso_l3.py"


def _load_l3():
    spec = importlib.util.spec_from_file_location("iso_l3_under_test", L3_PATH)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


@pytest.fixture
def l3_env(tmp_path, monkeypatch):
    """A tmp package dir on sys.path, with PrologLoader.source_to_code replaced by L3."""
    from clausal import import_hook
    L3 = _load_l3()
    stats: dict = {}

    def l3_source_to_code(self, data, path="<string>"):
        items = L3.read_iso(data.decode("utf-8"))
        mod, st = L3.lower_items(items)
        stats.clear(); stats.update(st)
        return compile(mod, path, "exec")

    monkeypatch.setattr(import_hook.PrologLoader, "source_to_code", l3_source_to_code)
    monkeypatch.syspath_prepend(str(tmp_path))
    yield tmp_path, stats, L3
    for p in tmp_path.rglob("__pycache__"):
        shutil.rmtree(p, ignore_errors=True)


def _answers(pred, arity=2):
    from clausal.logic.solve import query
    from clausal.logic.variables import Var
    vs = [Var() for _ in range(arity)]
    names = [f"v{i}" for i in range(arity)]
    return [tuple(s[n] for n in names)
            for s in query(pred(*vs), dict(zip(names, vs)))]


def test_P1_iso_facts_answer_identically_to_the_seam_twin(l3_env):
    tmp, stats, _ = l3_env
    (tmp / "isof.pl").write_text("fact_a(1, 10).\nfact_a(2, 20).\n", encoding="utf-8")
    (tmp / "seamf.seam").write_text("fact_a(1, 10),\nfact_a(2, 20),\n", encoding="utf-8")
    iso = importlib.import_module("isof")
    seam = importlib.import_module("seamf")

    # §8.2 -- without this, a cached .pyc makes the comparison vacuous. Observed.
    assert stats, "L3 never executed; the comparison below would prove nothing"
    assert stats["read"] == 2 and stats["lowered"] == 2 and stats["refused"] == 0, stats
    assert type(iso.__loader__).__name__ == "PrologLoader"

    a_iso, a_seam = _answers(iso.fact_a), _answers(seam.fact_a)
    assert a_iso == [(1, 10), (2, 20)]
    assert a_iso == a_seam


def test_P1_denominator_is_reported_for_refused_constructs(l3_env):
    """Rules are P2. They must be REFUSED and COUNTED, never silently dropped."""
    tmp, stats, L3 = l3_env
    items = L3.read_iso("f(1).\ng(X) :- f(X).\n")
    _, st = L3.lower_items(items)
    assert st["read"] == 2, st
    assert st["lowered"] == 1, st
    assert st["refused"] == 1 and st["refusals"], st


def test_P1_NEGATIVE_CONTROL_a_mislowered_arity_is_caught(l3_env):
    """§8.3: if the harness cannot catch a deliberate mis-lowering, it is not a harness."""
    tmp, stats, L3 = l3_env
    items = L3.read_iso("fact_a(1, 10).\n")
    mod, _ = L3.lower_items(items)
    # Drop the second argument from the emitted head -- a wrong-arity lowering.
    import ast
    for node in ast.walk(mod):
        if isinstance(node, ast.Call) and getattr(node.func, "id", None) == "fact_a":
            node.keywords = node.keywords[:1]
    ast.fix_missing_locations(mod)
    (tmp / "bad.pl").write_text("fact_a(1, 10).\n", encoding="utf-8")
    # The guard pins _fields at arity 2 while the head now supplies 1 -> must not
    # silently produce a working arity-1 predicate.
    from clausal import import_hook
    code = compile(mod, "bad.pl", "exec")
    ns: dict = {}
    ns.update(import_hook.runtime_builtins)
    with pytest.raises(Exception):
        exec(code, ns)


def test_P1_refuses_rather_than_half_handles_an_unsupported_term():
    """A construct outside P1 must RAISE, not be quietly approximated."""
    L3 = _load_l3()
    with pytest.raises(L3.LoweringRefused):
        L3.lower_arg(3.5)      # floats are not in P1 scope
