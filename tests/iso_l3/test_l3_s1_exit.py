"""Slice 1's exit test (plan native-iso-reader-step2 §4).

1. ``rulebase_s1.pl`` (47 ``test/1`` cases: recursion, disjunction, negation,
   ``call/N``, arithmetic, ``==`` vs ``=:=``, ``@<`` and ``compare``) passes
   under ``python -m clausal.testing`` with ``CLAUSAL_PL_FRONTEND=native`` --
   and the run is asserted to have used the native front end, over a
   non-zero population.
2. Its hand-written seam twin gives the SAME all-answers, per predicate and
   call pattern, in order.
3. Scryer, the oracle, agrees on the five ISO-vs-seam hazard names (``==``,
   ``is``, ``^``, ``//``, ``max``) and passes the same ``test/1`` population.
4. NEGATIVE CONTROL: flip one lowering (``==`` -> ``$ArithEq``, the seam's
   evaluating ``==``) and the A/B goes red, and so does the runner.
"""
from __future__ import annotations

import os
import pathlib
import shutil
import subprocess
import sys
import textwrap

import pytest

from clausal.tools import iso_l3 as L3
from tests._oracles import SCRYER

HERE = pathlib.Path(__file__).resolve().parent
REPO = HERE.parents[1]
RULEBASE = HERE / "rulebase_s1.pl"
TWIN = HERE / "rulebase_s1_twin.seam"
N_TESTS = 47

V = object()   # a fresh variable in a call pattern

#: (predicate, *arguments): every helper predicate, in the modes used.
CALLS = [
    ("edge", V, V), ("owns", V, V), ("path", V, V), ("path", "a", V),
    ("len", ["x", "y", "z"], V), ("app", V, V, [1, 2]), ("app", [1], [2], V),
    ("nrev", [1, 2, 3], V), ("fact", 5, V), ("fact", 0, V), ("color", V),
    ("sign_of", -3, V), ("sign_of", 0, V), ("sign_of", 2.5, V),
    ("source", V), ("leaf", V), ("memb", V, ["a", "b", "c"]),
    ("not_in", "z", ["a", "b"]), ("not_in", "a", ["a", "b"]),
    ("apply2", ("app", [1]), [2], V), ("twice", ("edge", "a", "b")),
    ("mapl", "succ_of", [1, 2, 3], V), ("succ_of", 4, V),
    ("reach_from", "a", V), ("reach_from", "b", V), ("goal_var", V, V),
    ("all_owned", V), ("arith", V), ("arith_int_div", V), ("arith_pow", V),
    ("arith_max", V), ("arith_mod", V, V),
    ("eq_struct", 1, 1.0, V), ("eq_struct", "a", "a", V),
    ("eq_struct", ("+", 1, 1), 2, V), ("eq_arith", 1, 1.0, V),
    ("eq_arith", ("+", 1, 1), 2, V), ("eq_arith", 1, 2, V),
    ("before", 1, "a"), ("before", 1.0, 1), ("before", "b", "a"),
    ("before", ("f", "b"), ("g", "a")), ("cmp", V, 1, 2),
    ("cmp", V, ("f", "a"), ("f", "a")), ("cmp", V, "b", "a"),
] + [("oracle", k, V) for k in ("eq", "is", "caret", "intdiv", "max_min")]

ORACLE_KEYS = ("eq", "is", "caret", "intdiv", "max_min")


def _all(mod, name, *args):
    from clausal.logic.solve import call
    from clausal.logic.variables import Var, deref, walk
    real = [Var() if a is V else a for a in args]
    return [tuple(walk(deref(a)) for a in real)
            for _ in call(name, *real, module=mod)]


def _strict(t):
    """A comparison key that tells ``1`` from ``1.0`` and ``True`` (Python's
    ``==`` does not, and the whole point here is ``==`` vs ``=:=``)."""
    if isinstance(t, (list, tuple)):
        return (type(t).__name__, tuple(_strict(x) for x in t))
    return (type(t).__name__, t)


def _ab(native_mod, twin_mod):
    """-> (mismatches, patterns compared, answers compared)."""
    bad, n_answers = [], 0
    for name, *args in CALLS:
        a, b = _all(native_mod, name, *args), _all(twin_mod, name, *args)
        n_answers += len(a)
        if _strict(a) != _strict(b):
            bad.append((name, args, a, b))
    return bad, len(CALLS), n_answers


def _load_pair(native):
    nat = native.load("rb_s1_native", RULEBASE.read_text(encoding="utf-8"))
    twin = native.load("rb_s1_twin", TWIN.read_text(encoding="utf-8"),
                       suffix=".seam")
    st = nat.__loader__.l3_stats
    assert st["read"] == st["lowered"] and st["read"] > 90, st
    return nat, twin


# ── 1. the runner ──


def _clear_rulebase_pyc():
    for p in (HERE / "__pycache__").glob("rulebase_s1*"):
        p.unlink()


def _env(frontend="native"):
    env = dict(os.environ)
    env["CLAUSAL_PL_FRONTEND"] = frontend
    env["PYTHONPATH"] = str(REPO) + os.pathsep + env.get("PYTHONPATH", "")
    return env


def test_the_rulebase_passes_under_python_m_clausal_testing_natively():
    _clear_rulebase_pyc()
    proc = subprocess.run(
        [sys.executable, "-m", "clausal.testing", str(RULEBASE)],
        cwd=REPO, env=_env(), capture_output=True, text=True, timeout=600)
    out = proc.stdout + proc.stderr
    assert proc.returncode == 0, out
    assert f"{N_TESTS} tests: {N_TESTS} passed, 0 failed" in out, out


def test_the_runner_used_the_native_front_end_over_every_clause():
    """The same run, with the loader recorded: WHICH front end ran, and its
    read/lowered/refused counts (a pass that never ran L3 proves nothing)."""
    _clear_rulebase_pyc()
    probe = textwrap.dedent(f"""
        import sys, clausal
        assert clausal.__file__.startswith({str(REPO)!r}), clausal.__file__
        import clausal.testing as T
        seen = []
        orig = T.load_clausal_module
        def rec(p):
            m = orig(p)
            seen.append((type(m.__loader__).__name__,
                         dict(getattr(m.__loader__, "l3_stats", None) or {{}})))
            return m
        T.load_clausal_module = rec
        rc = T.main([{str(RULEBASE)!r}])
        print("SEEN", seen)
        sys.exit(rc)
    """)
    proc = subprocess.run([sys.executable, "-c", probe], cwd=REPO, env=_env(),
                          capture_output=True, text=True, timeout=600)
    out = proc.stdout + proc.stderr
    assert proc.returncode == 0, out
    seen_line = next(ln for ln in out.splitlines() if ln.startswith("SEEN"))
    seen = eval(seen_line[len("SEEN"):])          # a repr we printed
    assert len(seen) == 1, seen
    loader, stats = seen[0]
    assert loader == "NativePrologLoader", seen
    assert stats["read"] == stats["lowered"] > 90 and stats["refused"] == 0


# ── 2. the seam twin ──


def test_the_seam_twin_gives_the_same_answers_per_predicate(native):
    nat, twin = _load_pair(native)
    bad, n_patterns, n_answers = _ab(nat, twin)
    print(f"A/B: {n_patterns} call patterns, {n_answers} answers compared")
    assert n_patterns == len(CALLS) > 40 and n_answers > 60
    assert not bad, "\n".join(map(repr, bad))


# ── 3. the Scryer oracle ──


@pytest.fixture
def scryer():
    if not os.path.exists(SCRYER):
        if os.environ.get("CLAUSAL_ISO_ALLOW_NO_SCRYER"):
            pytest.skip("the Scryer oracle is not built")
        pytest.fail(f"the Scryer oracle is not built at {SCRYER}")

    def run(goal: str):
        proc = subprocess.run(
            [SCRYER, str(RULEBASE)],
            input=f"{goal}, writeq(Out), nl, halt.\n",
            capture_output=True, text=True, timeout=60)
        line = proc.stdout.strip().splitlines()[-1]
        [item] = L3.read_iso(f"answer({line}).\n")
        assert type(item).__name__ == "Clause", (line, item)
        return item.term[1]
    return run


def test_the_strict_key_tells_1_from_1_0():
    assert _strict([1]) != _strict([1.0]) and [1] == [1.0]


@pytest.mark.parametrize("key", ORACLE_KEYS)
def test_scryer_agrees_on_the_hazard_names(native, scryer, key):
    nat = native.load("rb_s1_oracle", RULEBASE.read_text(encoding="utf-8"))
    [(_, native_answer)] = _all(nat, "oracle", key, V)
    assert native_answer, key
    oracle = scryer(f"oracle({key}, Out)")
    assert _strict(native_answer) == _strict(oracle), (key, native_answer,
                                                       oracle)


def test_scryer_passes_the_same_test_population(native, scryer):
    nat = native.load("rb_s1_pop", RULEBASE.read_text(encoding="utf-8"))
    native_names = sorted({n for (n,) in _all(nat, "test", V)})
    assert len(native_names) == N_TESTS
    assert _strict(scryer("findall(N, test(N), Ns), sort(Ns, Out)")) \
        == _strict(native_names)


# ── 4. the negative control ──


def test_NEGATIVE_CONTROL_flipping_one_lowering_turns_the_ab_red(
        native, monkeypatch):
    """``==`` lowered to the seam's ``$ArithEq`` (which evaluates) instead of
    ISO ``==/2``.  The A/B must go red on the == patterns, and the runner must
    fail the == tests.  The flip is counted, so it provably happened."""
    orig = L3._ClauseLowering._call
    flips: list = []

    def flipped(self, name, args, name_pos, pos):
        if name == "==" and len(args) == 2:
            flips.append(pos)
            return L3._node("ArithEq", left=args[0], right=args[1],
                            position=L3._pos_expr(pos))
        return orig(self, name, args, name_pos, pos)

    monkeypatch.setattr(L3._ClauseLowering, "_call", flipped)
    nat, twin = _load_pair(native)
    assert flips, "the negative control never flipped a lowering"
    bad, _, _ = _ab(nat, twin)
    assert bad, "the A/B did not notice == lowered as $ArithEq"
    assert any(name == "eq_struct" for name, *_ in bad), bad

    # The runner, in-process on a COPY (a poisoned .pyc must never land in
    # the repo's __pycache__: the salt does not know about a monkeypatch).
    import clausal.testing as T
    copy = native.tmp / "rb_s1_flipped.pl"
    shutil.copy(RULEBASE, copy)
    monkeypatch.setenv("CLAUSAL_PL_FRONTEND", "native")
    assert T.main([str(copy)]) != 0
