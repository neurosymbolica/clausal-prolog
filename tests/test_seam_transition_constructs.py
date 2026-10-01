"""D13 on the seam: the transition-construct counter and its ratchet.

The native ``.pl`` front end counts ``\\+``, once/1, forall/2, memberchk/2,
``findall(_, G, [])`` and make_quantity/3 into
``l3_stats["transition_constructs"]`` (tests/iso_l3/test_l3_s4_constructs.py).
The seam loader fills the same key with the same shape; ``if_/3`` (reif's
pure conditional, the replacement target) is NOT counted.  The census
(``clausal.tools.transition_census``) is the "count must not grow" ratchet
over the repository's seam and ``.pl`` files.
"""
from __future__ import annotations

import importlib
import io
import json
import logging
import shutil
import sys
import textwrap

import pytest

from clausal.logic.compiler.terms_to_goalop import TRANSITION_KEYS
from clausal.tools import transition_census as tc

ZERO = dict.fromkeys(TRANSITION_KEYS, 0)


@pytest.fixture
def seam(tmp_path, monkeypatch):
    monkeypatch.syspath_prepend(str(tmp_path))
    names = []

    def load(name, text, *, fresh=True):
        (tmp_path / f"{name}.seam").write_text(textwrap.dedent(text),
                                               encoding="utf-8")
        if fresh:
            for p in tmp_path.rglob("__pycache__"):
                shutil.rmtree(p, ignore_errors=True)
        sys.modules.pop(name, None)
        names.append(name)
        importlib.invalidate_caches()
        return importlib.import_module(name)

    yield load
    for n in names:
        sys.modules.pop(n, None)


def _answers(mod, name, *fixed):
    from clausal.logic.solve import call
    from clausal.logic.variables import Var, deref, walk
    v = Var()
    return [walk(deref(v)) for _ in call(name, *fixed, v, module=mod)]


def _counts(mod):
    return mod.__loader__.l3_stats["transition_constructs"]


def test_keys_are_the_pl_front_ends():
    from clausal.tools.iso_l3_directives import TRANSITION_KEYS as PL_KEYS
    assert TRANSITION_KEYS == PL_KEYS


def test_a_clean_module_counts_zero_every_key_present(seam, caplog):
    caplog.set_level(logging.INFO, logger="clausal.seam_frontend")
    mod = _load_clean(seam)
    assert _counts(mod) == ZERO
    assert not [r for r in caplog.records
                if "transition constructs" in r.getMessage()]


def _load_clean(seam):
    return seam("tc_clean", """\
        p(1),
        p(2),
        q(X) <- p(X)
        """)


EACH = """\
    -private([one])
    p(1),
    p(2),
    a(X) <- (p(X), not p(3))
    b(X) <- once(p(X))
    c() <- forall(p(X), X > 0)
    d(X) <- memberchk(X, [1, 2])
    e(X) <- (p(X), findall(Y, p(Y), []))
    f(X) <- (p(X), findall(Y, p(Y), _))
    g(X) <- (p(X), once((p(Y), not Y == 3)))
    h(X) <- (p(X), not not p(X))
    i(X) <- (p(X), ((not X == 1) or X == 5))
    j(G) <- (G is (not p(1)), call(G))
    """


def test_each_construct_is_counted_at_its_goal_positions(seam, caplog):
    caplog.set_level(logging.INFO, logger="clausal.seam_frontend")
    mod = seam("tc_each", EACH)
    assert _counts(mod) == {
        # a, g (inside once), h (twice), i (an or-arm); j's is DATA
        "\\+/1": 5,
        "once/1": 2, "forall/2": 1, "memberchk/2": 1,
        # e only: f's bag is a variable
        "findall/3_empty": 1, "make_quantity/3": 0}
    lines = [r.getMessage() for r in caplog.records
             if "transition constructs" in r.getMessage()]
    assert len(lines) == 1, lines
    assert "tc_each.seam: transition constructs: 10 sites" in lines[0]
    assert "\\+/1: 5" in lines[0]


def test_forall_counts_once_not_its_lowerings_negations(seam):
    # forall/2 lowers to a double negation; only the source site counts.
    mod = seam("tc_forall", "p(1),\nc() <- forall(p(X), X > 0)\n")
    assert _counts(mod) == {**ZERO, "forall/2": 1}


def test_if_is_not_a_transition_construct(seam):
    mod = seam("tc_if", """\
        -private([y, n])
        r(X, R) <- if_(X is 1, R is y, R is n)
        """)
    assert _counts(mod) == ZERO
    assert _answers(mod, "r", 1) == ["y"]


def test_the_counted_constructs_still_run(seam):
    mod = seam("tc_run", EACH)

    def ans(name):
        return _answers(mod, name)
    assert ans("a") == [1, 2]
    assert ans("b") == [1]
    assert ans("d") == [1]
    assert ans("e") == []
    assert ans("h") == [1, 2]
    assert ans("i") == [2]


def test_a_cache_hit_counts_the_same(seam):
    first = _counts(seam("tc_cache", EACH))
    again = _counts(seam("tc_cache", EACH, fresh=False))
    assert again == first and sum(first.values()) == 10


def test_the_census_reads_a_file_as_the_loader_does(seam, tmp_path):
    mod = seam("tc_twin", EACH)
    counts, skipped = tc.count_seam_file(tmp_path / "tc_twin.seam")
    assert counts == _counts(mod) and skipped == 0


# ── the ratchet ──


def _check(root, baseline, **kw):
    out = io.StringIO()
    rc = tc.check([str(root)], base=root, baseline_path=baseline,
                  out=out, **kw)
    return rc, out.getvalue()


def test_the_ratchet_fails_when_a_construct_is_added(tmp_path):
    root = tmp_path / "src"
    root.mkdir()
    (root / "m.seam").write_text("p(1),\na(X) <- (p(X), not p(2))\n")
    (root / "m.pl").write_text("q(X) :- \\+ X = 1.\n")
    bl = tmp_path / "baseline.json"
    assert _check(root, bl, update=True)[0] == 0
    doc = json.loads(bl.read_text())
    assert doc["files"] == {"m.seam": {"\\+/1": 1}, "m.pl": {"\\+/1": 1}}
    assert _check(root, bl)[0] == 0

    # a new once/1 in the seam file: the gate fails and names it
    (root / "m.seam").write_text(
        "p(1),\na(X) <- (p(X), not p(2))\nb(X) <- once(p(X))\n")
    rc, out = _check(root, bl)
    assert rc == 1, out
    assert "GREW: m.seam: once/1 0 -> 1" in out

    # ... and a new file with a \+ fails too
    (root / "m.seam").write_text("p(1),\na(X) <- (p(X), not p(2))\n")
    (root / "n.pl").write_text("r(X) :- \\+ X = 2.\n")
    rc, out = _check(root, bl)
    assert rc == 1 and "GREW: n.pl: \\+/1 0 -> 1" in out

    # removing a site is reported, not failed
    (root / "n.pl").unlink()
    (root / "m.pl").write_text("q(X) :- X = 1.\n")
    rc, out = _check(root, bl)
    assert rc == 0 and "shrank: m.pl: \\+/1 1 -> 0" in out


def test_if_does_not_trip_the_ratchet(tmp_path):
    root = tmp_path / "src"
    root.mkdir()
    (root / "m.seam").write_text("p(1),\na(X) <- (p(X), not p(2))\n")
    bl = tmp_path / "baseline.json"
    assert _check(root, bl, update=True)[0] == 0
    (root / "m.seam").write_text(
        "p(1),\na(X) <- (p(X), not p(2))\n"
        "b(X, R) <- if_(X is 1, R is 1, R is 2)\n")
    assert _check(root, bl)[0] == 0


def test_an_empty_census_is_an_error(tmp_path):
    root = tmp_path / "src"
    root.mkdir()
    rc, out = _check(root, tmp_path / "b.json", update=True)
    assert rc == 2 and "EMPTY" in out
    (root / "m.seam").write_text("p(1),\n")       # files, but no construct
    rc, out = _check(root, tmp_path / "b.json", update=True)
    assert rc == 2 and "SIZE: 1 files scanned, 0 constructs" in out


def test_the_repository_does_not_grow_its_transition_constructs():
    """THE gate: the repository's seam and ``.pl`` files against the
    committed baseline (clausal/tools/transition_census_baseline.json).  A
    failure names each (file, construct) that grew; rewrite the site with
    if_/3 and reified tests, or -- for a MOVE, not a new site -- re-baseline
    with ``python -m clausal.tools.transition_census --update``."""
    out = io.StringIO()
    rc = tc.check(per_file=False, out=out)
    text = out.getvalue()
    assert rc == 0, text
    # the census saw a real population (fail-closed on an empty walk)
    totals = json.loads(tc.BASELINE.read_text())["totals"]
    assert sum(totals["seam"].values()) > 100, totals
    assert sum(totals["pl"].values()) > 10, totals
