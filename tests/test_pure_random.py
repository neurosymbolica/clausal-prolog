"""The pure, state-threaded random library ``pure_random`` (operator ruling
2026-10-07), and the deprecation of ``py.random``.

The generator state is the term ``rng(Seed, N)``; every draw is a relation
``S0 -> S``.  These tests pin:

* the GOLDEN VALUES: fixed seeds -> fixed outputs.  A change in the seed
  derivation, in the float -> integer/permutation mappings, or in Python's
  ``random.Random(int).random()`` fails here, loudly;
* determinism across processes (subprocess, different hash seeds) and from
  both surfaces (``.seam`` and ``.clausal``);
* that backtracking restores the state, DCG threading through ``phrase/3``,
  every error case, a deterministic uniformity smoke test, and that a
  permutation is a permutation and a sample has no duplicates;
* that ``py.random`` warns once per process.

All of these fail on the base (no ``clausal.modules.pure_random``, no
deprecation warning) and pass after.
"""
from __future__ import annotations

import hashlib
import json
import os
import random as py_random
import subprocess
import sys
import textwrap

import pytest

import clausal
from clausal import Var, solve
from clausal.import_hook import _load_module
from clausal.logic.cells import chars
from clausal.logic.exceptions import LogicException
from clausal.logic.trampoline import DONE
from clausal.logic.variables import Trail, walk
import clausal.modules.pure_random as R

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(clausal.__file__)))


# ── helpers ──────────────────────────────────────────────────────────────


def run(pred, *args):
    """Drive a predicate's dispatch; the walked args of each solution."""
    trail = Trail()
    out = []
    for _parent, v in pred._get_dispatch()(None, None, None, None, *args,
                                            trail):
        if v is DONE:
            break
        out.append([walk(a) for a in args])
    return out


def error_of(pred, *args):
    """The formal term of the error *pred* raises (``error(F, _)`` -> F)."""
    with pytest.raises(LogicException) as info:
        run(pred, *args)
    term = info.value.term
    assert term[0] == "error"
    return term[1]


def seed(s):
    S = Var()
    assert len(run(R.rng_seed, s, S)) == 1
    return walk(S)


def draws(pred, args_before, n, s, args_after=()):
    """*n* chained calls ``pred(*args_before, X, *args_after, S0, S)``; the
    X values and the final state."""
    xs = []
    for _ in range(n):
        x, s1 = Var(), Var()
        (sol,) = run(pred, *args_before, x, *args_after, s, s1)
        xs.append(walk(x))
        s = walk(s1)
    return xs, s


def _load(tmp_path, monkeypatch, name, src, ext):
    monkeypatch.syspath_prepend(str(tmp_path))
    path = tmp_path / f"{name}.{ext}"
    path.write_text(textwrap.dedent(src))
    sys.modules.pop(name, None)
    return _load_module(name, str(path))


def answers(mod, name, n):
    out = []
    vs = [Var() for _ in range(n)]
    for _ in solve((name, *vs), module=mod):
        out.append([walk(v) for v in vs])
    return out


# ── golden values ────────────────────────────────────────────────────────
#
# Committed outputs for fixed seeds.  If one of these changes, the
# reproducibility guarantee in clausal/modules/pure_random.py has been
# broken -- by an edit to the mapping or by a Python change.  Do not
# "update the goldens" without a ruling.

GOLDEN_FLOATS_42 = [0.13543887981365155, 0.4779424142209394,
                    0.718561210333975, 0.7325657050432315,
                    0.9385043605356724]
GOLDEN_FIRST_FLOAT = {
    "abc": 0.583353109332208,
    -1: 0.646634884878535,
    2 ** 100: 0.8553081077436056,
    0: 0.0544045858010378,
}
GOLDEN_DICE_42 = [6, 5, 6, 5, 1, 3, 6, 5, 2, 4]          # ends at rng(42, 15)
GOLDEN_BIG_0 = 1351729673625841332875365865054383378138465617980119119218178
GOLDEN_MEMBER_1 = "b"                                   # ends at rng(1, 2)
GOLDEN_PERM_1 = [8, 1, 7, 5, 6, 10, 4, 9, 3, 2]          # ends at rng(1, 17)
GOLDEN_SAMPLE_1 = [2, 4, 5, 7]                          # ends at rng(1, 7)


class TestGolden:
    def test_seed_state_is_rng_seed_0(self):
        assert seed(42) == ("rng", 42, 0)
        assert seed("abc") == ("rng", "abc", 0)

    def test_floats(self):
        xs, s = draws(R.random, (), 5, seed(42))
        assert xs == GOLDEN_FLOATS_42
        assert s == ("rng", 42, 5)

    @pytest.mark.parametrize("s", sorted(GOLDEN_FIRST_FLOAT, key=repr))
    def test_first_float(self, s):
        (x,), _ = draws(R.random, (), 1, seed(s))
        assert x == GOLDEN_FIRST_FLOAT[s]

    def test_atom_and_string_seed_are_the_same_seed(self):
        a, _ = draws(R.random, (), 3, seed("abc"))
        b, _ = draws(R.random, (), 3, seed(chars("abc")))
        assert a == b
        # ... but the integer 5 and the atom '5' are not
        c, _ = draws(R.random, (), 1, seed(5))
        d, _ = draws(R.random, (), 1, seed("5"))
        assert c != d

    def test_the_documented_derivation(self):
        """The N-th float IS random.Random(SHA-256 material).random(): the
        module docstring's points 1-2, recomputed here independently."""
        for s, sb in ((42, b"i42"), ("abc", b"tabc"), (-1, b"i-1")):
            xs, _ = draws(R.random, (), 3, seed(s))
            for n, x in enumerate(xs):
                material = hashlib.sha256(
                    b"clausal.pure_random.v1\0" + sb + b"\0"
                    + str(n).encode()).digest()
                assert x == py_random.Random(
                    int.from_bytes(material, "big")).random()

    def test_between(self):
        xs, s = draws(R.random_between, (1, 6), 10, seed(42))
        assert xs == GOLDEN_DICE_42
        assert s == ("rng", 42, 15)

    def test_between_wide_range(self):
        (x,), s = draws(R.random_between, (0, 2 ** 200), 1, seed(0))
        assert x == GOLDEN_BIG_0
        assert s == ("rng", 0, 4)            # 200 bits = four 53-bit draws

    def test_between_single_value_still_draws(self):
        (x,), s = draws(R.random_between, (-5, -5), 1, seed(0))
        assert (x, s) == (-5, ("rng", 0, 1))

    def test_member(self):
        (x,), s = draws(R.random_member, (), 1, seed(1),
                        (["a", "b", "c", "d", "e"],))
        assert (x, s) == (GOLDEN_MEMBER_1, ("rng", 1, 2))

    def test_permutation(self):
        p, s1 = Var(), Var()
        run(R.random_permutation, list(range(1, 11)), p, seed(1), s1)
        assert walk(p) == GOLDEN_PERM_1
        assert walk(s1) == ("rng", 1, 17)

    def test_sample(self):
        p, s1 = Var(), Var()
        run(R.random_sample, list(range(1, 11)), 4, p, seed(1), s1)
        assert walk(p) == GOLDEN_SAMPLE_1
        assert walk(s1) == ("rng", 1, 7)


# ── determinism across processes ─────────────────────────────────────────

_CHILD = """
import json, clausal
from clausal.logic.variables import Var, Trail, walk
from clausal.logic.trampoline import DONE
import clausal.modules.pure_random as R
def run(pred, *args):
    t = Trail()
    for _p, v in pred._get_dispatch()(None, None, None, None, *args, t):
        if v is DONE: break
        return [walk(a) for a in args]
s = run(R.rng_seed, "abc", Var())[1]
xs = []
for _ in range(5):
    x, s1 = Var(), Var(); run(R.random_between, 1, 1000, x, s, s1)
    xs.append(walk(x)); s = walk(s1)
f = run(R.random, Var(), run(R.rng_seed, 42, Var())[1], Var())[0]
print(json.dumps([clausal.__file__, xs, f]))
"""


def test_same_answers_in_another_process():
    here, _ = draws(R.random_between, (1, 1000), 5, seed("abc"))
    outs = []
    for hashseed in ("0", "12345"):          # str hashing differs per process
        env = dict(os.environ, PYTHONPATH=ROOT, CLAUSAL_ROOT=ROOT,
                   PYTHONHASHSEED=hashseed)
        res = subprocess.run([sys.executable, "-c", _CHILD], env=env,
                             capture_output=True, text=True, timeout=120,
                             cwd=ROOT)
        assert res.returncode == 0, res.stderr
        outs.append(json.loads(res.stdout.strip().splitlines()[-1]))
    for loaded_from, xs, f in outs:
        assert os.path.dirname(os.path.dirname(loaded_from)) == ROOT
        assert xs == here
        assert f == GOLDEN_FLOATS_42[0]


# ── both surfaces ────────────────────────────────────────────────────────

SEAM_SRC = """
    -import_from(pure_random, [rng_seed, random, random_between,
                               random_member, random_permutation,
                               random_sample])
    -private([a, b, c, d, e])

    dice([X, Y]) >> (random_between(1, 6, X), random_between(1, 6, Y))

    floats([F1, F2, F3], S) <- (
        rng_seed(42, S0), random(F1, S0, S1), random(F2, S1, S2),
        random(F3, S2, S)
    )
    dice10(Xs, S) <- (rng_seed(42, S0), roll(10, Xs, S0, S))
    roll(0, [], S, S),
    roll(N, [X, *Xs], S0, S) <- (
        N > 0, random_between(1, 6, X, S0, S1), N1 == N - 1,
        roll(N1, Xs, S1, S)
    )
    dcg(L, S) <- (rng_seed(1, S0), phrase(dice(L), S0, S))
    bt(A, B) <- (
        rng_seed(7, S0),
        findall(X, (random_between(1, 1000000, X, S0, _)
                    or random_between(1, 1000000, X, S0, _)), [A, B])
    )
    misc(M, P, Q) <- (
        rng_seed(1, S0),
        random_member(M, [a, b, c, d, e], S0, _),
        random_permutation([1, 2, 3, 4, 5, 6, 7, 8, 9, 10], P, S0, _),
        random_sample([1, 2, 3, 4, 5, 6, 7, 8, 9, 10], 4, Q, S0, _)
    )
"""

CLAUSAL_SRC = """
    :- module({name}, [floats/2, dice10/2, dcg/2, bt/2, misc/3]).
    :- use_module(library(pure_random),
                  [rng_seed/2, random/3, random_between/5, random_member/4,
                   random_permutation/4, random_sample/5]).

    dice([X, Y]) --> random_between(1, 6, X), random_between(1, 6, Y).

    floats([F1, F2, F3], S) :-
        rng_seed(42, S0), random(F1, S0, S1), random(F2, S1, S2),
        random(F3, S2, S).
    dice10(Xs, S) :- rng_seed(42, S0), roll(10, Xs, S0, S).
    roll(0, [], S, S).
    roll(N, [X|Xs], S0, S) :-
        N > 0, random_between(1, 6, X, S0, S1), N1 is N - 1,
        roll(N1, Xs, S1, S).
    dcg(L, S) :- rng_seed(1, S0), phrase(dice(L), S0, S).
    bt(A, B) :-
        rng_seed(7, S0),
        findall(X, (random_between(1, 1000000, X, S0, _)
                   ; random_between(1, 1000000, X, S0, _)), [A, B]).
    misc(M, P, Q) :-
        rng_seed(1, S0),
        random_member(M, [a, b, c, d, e], S0, _),
        random_permutation([1, 2, 3, 4, 5, 6, 7, 8, 9, 10], P, S0, _),
        random_sample([1, 2, 3, 4, 5, 6, 7, 8, 9, 10], 4, Q, S0, _).

    :- end_module({name}).
"""


@pytest.fixture(params=["seam", "clausal"])
def program(request, tmp_path, monkeypatch):
    ext = request.param
    name = f"pure_random_prog_{ext}"
    src = (SEAM_SRC if ext == "seam"
           else CLAUSAL_SRC.replace("{name}", name))
    return _load(tmp_path, monkeypatch, name, src, ext)


class TestFromSource:
    def test_floats(self, program):
        assert answers(program, "floats", 2) == [
            [GOLDEN_FLOATS_42[:3], ("rng", 42, 3)]]

    def test_dice(self, program):
        assert answers(program, "dice10", 2) == [
            [GOLDEN_DICE_42, ("rng", 42, 15)]]

    def test_backtracking_restores_the_state(self, program):
        [[a, b]] = answers(program, "bt", 2)
        assert a == b

    def test_dcg_threads_the_state_through_phrase_3(self, program):
        [[xs, s]] = answers(program, "dcg", 2)
        # the same two draws, chained by hand
        ys, s2 = draws(R.random_between, (1, 6), 2, seed(1))
        assert (xs, s) == (ys, s2)

    def test_member_permutation_sample(self, program):
        assert answers(program, "misc", 3) == [
            [GOLDEN_MEMBER_1, GOLDEN_PERM_1, GOLDEN_SAMPLE_1]]


def test_scryer_style_random_1_import_is_an_error(tmp_path, monkeypatch):
    """Scryer's library(random) exports random/1; ours has random/3.  An
    import of random/1 is refused by name, never bound to something else."""
    src = """
        :- module(pr_scryer_style, [go/1]).
        :- use_module(library(pure_random), [random/1]).
        go(X) :- random(X).
        :- end_module(pr_scryer_style).
    """
    with pytest.raises(ImportError) as info:
        _load(tmp_path, monkeypatch, "pr_scryer_style", src, "clausal")
    msg = str(info.value)
    assert "random/1" in msg and "random/3" in msg


# ── errors: never a silent failure ───────────────────────────────────────


def _formal(term):
    """``domain_error(D, C)`` etc. as a plain tuple; atoms as str."""
    return walk(term)


class TestErrors:
    @pytest.mark.parametrize("pred,pre,post", [
        (R.random, (), ()),
        (R.random_between, (1, 6), ()),
        (R.random_member, (), ([1, 2],)),
    ])
    def test_unbound_state(self, pred, pre, post):
        assert error_of(pred, *pre, Var(), *post, Var(), Var()) == \
            "instantiation_error"

    def test_unbound_state_permutation_and_sample(self):
        assert error_of(R.random_permutation, [1], Var(), Var(), Var()) == \
            "instantiation_error"
        assert error_of(R.random_sample, [1], 1, Var(), Var(), Var()) == \
            "instantiation_error"

    def test_state_with_an_unbound_component(self):
        assert error_of(R.random, Var(), ("rng", Var(), 0), Var()) == \
            "instantiation_error"
        assert error_of(R.random, Var(), ("rng", 1, Var()), Var()) == \
            "instantiation_error"

    @pytest.mark.parametrize("bad", [
        "rng", 42, ("rng", 42), ("rng", 42, 0, 1), ("gen", 42, 0),
        ("rng", 42, -1), ("rng", 42, 1.0), ("rng", 1.5, 0),
        ("rng", ("f", 1), 0), ("rng", 42, True), ("rng", [1], 0),
    ])
    def test_malformed_state(self, bad):
        f = error_of(R.random, Var(), bad, Var())
        assert f[:2] == ("type_error", "rng_state")
        assert walk(f[2]) == bad

    def test_seed_errors(self):
        assert error_of(R.rng_seed, Var(), Var()) == "instantiation_error"
        for bad in (1.5, ("f", 1), [1, 2], True):
            assert error_of(R.rng_seed, bad, Var()) == \
                ("type_error", "rng_seed", bad)

    def test_between_errors(self):
        s = seed(1)
        assert error_of(R.random_between, Var(), 6, Var(), s, Var()) == \
            "instantiation_error"
        assert error_of(R.random_between, 1, 6.0, Var(), s, Var()) == \
            ("type_error", "integer", 6.0)
        assert error_of(R.random_between, 7, 6, Var(), s, Var()) == \
            ("domain_error", ("not_less_than", 7), 6)

    def test_member_errors(self):
        s = seed(1)
        assert error_of(R.random_member, Var(), [], s, Var()) == \
            ("domain_error", "non_empty_list", [])
        assert error_of(R.random_member, Var(), Var(), s, Var()) == \
            "instantiation_error"
        assert error_of(R.random_member, Var(), "foo", s, Var()) == \
            ("type_error", "list", "foo")

    def test_sample_errors(self):
        s = seed(1)
        assert error_of(R.random_sample, [1, 2], -1, Var(), s, Var()) == \
            ("domain_error", "not_less_than_zero", -1)
        assert error_of(R.random_sample, [1, 2], 3, Var(), s, Var()) == \
            ("domain_error", ("not_greater_than", 2), 3)
        assert error_of(R.random_sample, [1, 2], "x", Var(), s, Var()) == \
            ("type_error", "integer", "x")

    def test_errors_are_catchable_from_source(self, tmp_path, monkeypatch):
        src = """
            :- module(pr_catch, [e/1]).
            :- use_module(library(pure_random), [random/3]).
            e(E) :- catch(random(_, nope, _), error(E, _), true).
            :- end_module(pr_catch).
        """
        mod = _load(tmp_path, monkeypatch, "pr_catch", src, "clausal")
        assert answers(mod, "e", 1) == [[("type_error", "rng_state",
                                          "nope")]]


# ── properties ───────────────────────────────────────────────────────────


def test_permutation_is_a_permutation():
    s = seed("perm")
    for n in range(0, 30):
        p, s1 = Var(), Var()
        run(R.random_permutation, list(range(n)), p, s, s1)
        assert sorted(walk(p)) == list(range(n))
        s = walk(s1)


def test_permutation_of_terms_with_variables_keeps_them():
    v = Var()
    p, s1 = Var(), Var()
    run(R.random_permutation, [v, "a"], p, seed(3), s1)
    got = walk(p)
    assert len(got) == 2 and "a" in got and any(x is v for x in got)


def test_sample_has_no_duplicates():
    s = seed("sample")
    items = list(range(20))
    for k in range(0, 21):
        p, s1 = Var(), Var()
        run(R.random_sample, items, k, p, s, s1)
        got = walk(p)
        assert len(got) == k and len(set(got)) == k
        assert set(got) <= set(items)
        s = walk(s1)


def test_floats_are_in_the_unit_interval():
    xs, _ = draws(R.random, (), 2000, seed("unit"))
    assert all(type(x) is float and 0.0 <= x < 1.0 for x in xs)


def test_uniformity_smoke():
    """Deterministic chi-square bounds: 6000 die rolls (5 df) and 5000
    floats in 10 bins (9 df), each below the 0.1% critical value."""
    xs, _ = draws(R.random_between, (1, 6), 6000, seed(2026))
    counts = [xs.count(i) for i in range(1, 7)]
    chi = sum((c - 1000) ** 2 / 1000 for c in counts)
    assert chi < 20.52, counts
    fs, _ = draws(R.random, (), 5000, seed(2026))
    bins = [0] * 10
    for f in fs:
        bins[int(f * 10)] += 1
    chi = sum((c - 500) ** 2 / 500 for c in bins)
    assert chi < 27.88, bins


# ── py.random is deprecated ──────────────────────────────────────────────


def test_py_random_warns_once_per_process():
    """In a fresh process: the first py.random call warns, naming the pure
    library; later calls (any predicate) do not; the answers still come."""
    child = textwrap.dedent("""
        import warnings, json
        warnings.simplefilter("always")
        from clausal.logic.variables import Var, Trail, walk
        from clausal.logic.trampoline import DONE
        import clausal.modules.py.random as PR
        from clausal.lint_warnings import ClausalPyRandomDeprecationWarning
        def run(pred, *args):
            for _p, v in pred._get_dispatch()(None, None, None, None,
                                              *args, Trail()):
                if v is DONE: return None
                return [walk(a) for a in args]
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            a = run(PR.float_0_to_1, Var())
            b = run(PR.integer_between, 1, 6, Var())
            c = run(PR.float_0_to_1, Var())
        hits = [str(x.message) for x in w
                if issubclass(x.category, ClausalPyRandomDeprecationWarning)]
        print(json.dumps([len(hits), hits[0] if hits else "",
                          a is not None and b is not None and c is not None]))
    """)
    env = dict(os.environ, PYTHONPATH=ROOT, CLAUSAL_ROOT=ROOT)
    res = subprocess.run([sys.executable, "-c", child], env=env,
                         capture_output=True, text=True, timeout=120,
                         cwd=ROOT)
    assert res.returncode == 0, res.stderr
    n, msg, answered = json.loads(res.stdout.strip().splitlines()[-1])
    assert n == 1
    assert "deprecated" in msg and "pure_random" in msg
    assert answered


def test_py_random_warning_is_visible_by_default():
    from clausal.lint_warnings import (
        ClausalLintWarning, ClausalPyRandomDeprecationWarning)
    assert issubclass(ClausalPyRandomDeprecationWarning, ClausalLintWarning)
    assert issubclass(ClausalPyRandomDeprecationWarning, UserWarning)
