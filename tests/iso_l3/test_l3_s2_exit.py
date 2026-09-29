"""Slice 2's exit test (plan native-iso-reader-step2 §4 Slice 2).

The rulebase under ``s2/native`` is three modules:

* ``s2main.pl``         -- imports the .seam module (``use_module(s2lib/shapes)``)
                           and the .pl module under BOTH path spellings
                           (``s2lib/facts`` and ``'s2lib/facts'``); a local
                           ``base/1`` beside ``facts:base/1``; its own dynamic,
                           table, discontiguous and meta_predicate procedures;
                           module-exported and imported ops; double_quotes
                           switched chars -> codes -> atom -> chars.
* ``s2lib/facts.pl``    -- a .pl library: dynamic + assertz, and assertz into
                           an undeclared procedure (assert_creates_dynamic).
* ``s2lib/shapes.seam`` -- a .seam library that imports ``facts.pl`` back.

1. Each module gives the SAME all-answers as its hand-written seam twin
   (``s2/twin``), per predicate and call pattern, in order, type-strict.
2. Scryer, the oracle, loads the .pl files (with ``s2/oracle``'s ISO stand-in
   for the .seam module) and answers every main-module pattern the same.
3. NEGATIVE CONTROL: lower ``m:G`` as the unqualified ``G`` and the A/B goes
   red.
Every load clears ``__pycache__``, asserts which loader ran each module, and
asserts non-zero read/lowered counts.
"""
from __future__ import annotations

import importlib
import os
import shutil
import subprocess
import sys

import pytest

from clausal.tools import iso_l3 as L3

HERE = os.path.dirname(os.path.abspath(__file__))
S2 = os.path.join(HERE, "s2")
SCRYER = "/workspace/scryer-prolog/target/release/scryer-prolog"
ENV = "CLAUSAL_PL_FRONTEND"

V = object()   # a fresh variable in a call pattern

#: s2main (native) vs s2twmain (twin): every predicate, in the modes used.
#: The stateful ones (bumped, noted, seen_all) run once, in this order, on
#: both sides.
MAIN_CALLS = [
    ("shape_area", V, V), ("big", V), ("local_base", V), ("their_base", V),
    ("bumped", V), ("noted", V), ("seen_all", V), ("fib", 15, V),
    ("fib", 10, 55), ("kind", V, V), ("kind", "b", V), ("twice", ("kind", "a", "vowel")),
    ("ops", V), ("dq_chars", V), ("dq_codes", V), ("dq_atom", V),
    ("dq_back", V), ("dq_chars", ["a", "b"]),
]
FACTS_CALLS = [
    ("base", V), ("pair", V, V), ("rel", V), ("counter", V), ("notes", V),
]
SHAPES_CALLS = [
    ("area", ("sq", 3), V), ("area", ("rect", 2, 5), V), ("scaled", 2, V),
    ("kinds", V),
]

_OWN = ("s2main", "s2twmain", "s2lib", "s2tw")


def _forget():
    for n in list(sys.modules):
        if n.split(".")[0] in _OWN:
            sys.modules.pop(n, None)


@pytest.fixture
def tree(tmp_path, monkeypatch):
    """Both rulebases copied under tmp (a poisoned .pyc never lands in the
    repo), on sys.path, native front end on, nothing cached."""
    shutil.copytree(os.path.join(S2, "native"), tmp_path / "native")
    shutil.copytree(os.path.join(S2, "twin"), tmp_path / "twin")
    monkeypatch.syspath_prepend(str(tmp_path / "native"))
    monkeypatch.syspath_prepend(str(tmp_path / "twin"))
    monkeypatch.setenv(ENV, "native")
    _forget()
    importlib.invalidate_caches()
    yield tmp_path
    _forget()


def _load(tmp):
    for p in tmp.rglob("__pycache__"):
        shutil.rmtree(p, ignore_errors=True)
    from clausal import import_hook as ih
    nat = importlib.import_module("s2main")
    twin = importlib.import_module("s2twmain")
    mods = {n: importlib.import_module(n) for n in
            ("s2lib.facts", "s2lib.shapes", "s2tw.facts", "s2tw.shapes")}
    for name in ("s2main", "s2lib.facts"):
        m = sys.modules[name]
        assert type(m.__loader__) is ih.NativePrologLoader, name
        st = m.__loader__.l3_stats
        assert st["read"] > 0 and st["read"] == st["lowered"], (name, st)
        assert st["directives"] > 0 and st["refused"] == 0, (name, st)
    assert type(mods["s2lib.shapes"].__loader__).__name__ == "PredicateLoader"
    assert nat.__loader__.l3_stats["directives"] >= 10
    return nat, twin, mods


def _all(mod, name, *args):
    from clausal.logic.solve import call
    from clausal.logic.variables import Var, deref, walk
    real = [Var() if a is V else a for a in args]
    return [tuple(walk(deref(a)) for a in real)
            for _ in call(name, *real, module=mod)]


def _strict(t):
    """Tells 1 from 1.0 and from True, and a list from a tuple."""
    if isinstance(t, (list, tuple)):
        return (type(t).__name__, tuple(_strict(x) for x in t))
    return (type(t).__name__, t)


def _ab(pairs):
    """pairs: [(native_mod, twin_mod, calls)] -> (mismatches, n_patterns,
    n_answers)."""
    bad, n_pat, n_ans = [], 0, 0
    for nat, twin, calls in pairs:
        for name, *args in calls:
            a, b = _all(nat, name, *args), _all(twin, name, *args)
            n_pat += 1
            n_ans += len(a)
            if _strict(a) != _strict(b):
                bad.append((nat.__name__, name, args, a, b))
    return bad, n_pat, n_ans


def _pairs(nat, twin, mods):
    return [(nat, twin, MAIN_CALLS),
            (mods["s2lib.facts"], mods["s2tw.facts"], FACTS_CALLS),
            (mods["s2lib.shapes"], mods["s2tw.shapes"], SHAPES_CALLS)]


# ── 1. the seam twins ──


def test_each_module_answers_as_its_seam_twin(tree):
    nat, twin, mods = _load(tree)
    bad, n_pat, n_ans = _ab(_pairs(nat, twin, mods))
    print(f"A/B: 3 modules, {n_pat} call patterns, {n_ans} answers compared")
    assert n_pat == len(MAIN_CALLS) + len(FACTS_CALLS) + len(SHAPES_CALLS)
    assert n_ans > 40
    assert not bad, "\n".join(map(repr, bad))


def test_the_imported_pl_module_is_one_module_under_both_spellings(tree):
    nat, _twin, mods = _load(tree)
    facts = mods["s2lib.facts"]
    # bump/1 (unquoted spelling) and notes/1 (quoted spelling) both reach
    # the SAME module's state, and so does shapes.seam's import of facts.
    assert _all(nat, "bumped", V) == [([1, 2, 3],)]
    assert _all(facts, "counter", V) == [(3,)]
    assert sys.modules["s2lib.shapes"].__dict__["base"] is not None


# ── 2. the Scryer oracle ──


def _pl(x) -> str:
    """A cell as Prolog text (the call patterns' arguments only)."""
    if isinstance(x, str):
        return x
    if isinstance(x, int):
        return str(x)
    if isinstance(x, list):
        return "[" + ",".join(_pl(e) for e in x) + "]"
    if isinstance(x, tuple):
        return f"{x[0]}(" + ",".join(_pl(e) for e in x[1:]) + ")"
    raise TypeError(x)


def _chars_as_list(t):
    """Scryer prints a chars string as its list; the engine's carrier is
    ('$chars', s), which unifies with that list."""
    if isinstance(t, tuple) and len(t) == 2 and t[0] == "$chars":
        return list(t[1])
    if isinstance(t, (list, tuple)):
        return type(t)(_chars_as_list(e) for e in t)
    return t


@pytest.fixture
def scryer():
    if not os.path.exists(SCRYER):
        if os.environ.get("CLAUSAL_ISO_ALLOW_NO_SCRYER"):
            pytest.skip("the Scryer oracle is not built")
        pytest.fail(f"the Scryer oracle is not built at {SCRYER}")
    return SCRYER


def test_scryer_loads_the_pl_files_and_answers_the_same(tree, scryer):
    # The Scryer tree: the .pl files as they are, the .seam module replaced
    # by its ISO stand-in (Scryer cannot read .seam).
    root = tree / "scryer"
    shutil.copytree(os.path.join(S2, "native"), root)
    (root / "s2lib" / "shapes.seam").unlink()
    (root / "s2lib" / "__init__.py").unlink()
    shutil.copy(os.path.join(S2, "oracle", "s2lib", "shapes.pl"),
                root / "s2lib" / "shapes.pl")
    goals = []
    for k, (name, *args) in enumerate(MAIN_CALLS):
        # Every goal's variables are its own (one conjunction shares them).
        vs = [f"V{k}_{i}" for i, a in enumerate(args) if a is V]
        call_args = ",".join(f"V{k}_{i}" if a is V else _pl(a)
                             for i, a in enumerate(args))
        goals.append(f"findall([{','.join(vs)}], s2main:{name}({call_args}), "
                     f"L{k}), writeq(L{k}), nl")
    program = ", ".join(f"({g})" for g in goals) + ", halt.\n"
    proc = subprocess.run([scryer, "s2main.pl"], input=program, cwd=root,
                          capture_output=True, text=True, timeout=300)
    lines = [ln for ln in proc.stdout.splitlines() if ln.strip()]
    assert len(lines) == len(MAIN_CALLS), proc.stdout + proc.stderr
    ops = L3.reader_op_table()
    ops.define(200, "xfy", "^^")
    ops.define(700, "xfx", "===>")
    nat, _twin, _mods = _load(tree)
    bad, n_answers = [], 0
    for (name, *args), line in zip(MAIN_CALLS, lines):
        [item] = L3.read_iso(f"answer({line}).\n", ops)
        assert type(item).__name__ == "Clause", (line, item)
        oracle = item.term[1]
        free = [i for i, a in enumerate(args) if a is V]
        native = [[row[i] for i in free]
                  for row in _chars_as_list(_all(nat, name, *args))]
        n_answers += len(native)
        if _strict(native) != _strict(oracle):
            bad.append((name, args, native, oracle))
    print(f"Scryer oracle: {len(lines)} call patterns, {n_answers} answers")
    assert n_answers > 20
    assert not bad, "\n".join(map(repr, bad))


# ── 3. the negative control ──


def test_NEGATIVE_CONTROL_an_unqualified_m_G_turns_the_ab_red(tree,
                                                              monkeypatch):
    """``m:G`` lowered as the plain ``G``: facts:base(X) becomes the LOCAL
    base/1.  The A/B must go red on their_base, and the flip is counted."""
    flips: list = []

    def flipped(self, args, spans, sp, pos):
        flips.append(args)
        return self.goal(args[1], spans[1])

    monkeypatch.setattr(L3._ClauseLowering, "_qualified", flipped)
    nat, twin, mods = _load(tree)
    assert flips, "the negative control never flipped a lowering"
    bad, _, _ = _ab(_pairs(nat, twin, mods))
    assert any(name == "their_base" for _m, name, *_ in bad), bad
