"""The `==` mode instrument: does it record what actually executed?

Every classification has a POSITIVE CONTROL here — a program that must produce
it — because an instrument whose failure mode is "records nothing" is
indistinguishable from "the code under analysis has no `==`", and that is the
shape of silent-success failure this repo keeps re-learning.
"""
import json
import os
import tempfile

import pytest

from clausal.import_hook import _load_module
from clausal.logic.solve import solve
from clausal.logic.variables import Trail, Var
from clausal.tools.eq_analysis import instrument


@pytest.fixture
def inst():
    instrument.reset()
    instrument.install()
    yield instrument
    instrument.uninstall()
    instrument.reset()


def _load(src, name):
    d = tempfile.mkdtemp()
    path = os.path.join(d, f"{name}.clausal")
    with open(path, "w") as fh:
        fh.write(src)
    return _load_module(name, path), path


SRC = (
    "-module({n}, [test_ground, binds(X), structural(A), constrains(X, Y), lo])\n"
    "-double_quotes(chars)\n"
    "test_ground <- (1 + 1 == 2)\n"
    "binds(X) <- (X == 3 + 4)\n"
    "structural(A) <- (A == lo)\n"
    "constrains(X, Y) <- (X == Y + 1)\n"
)


def _run(mod, goal):
    list(solve(goal, mod, Trail()))


def test_each_path_is_recorded_with_its_own_classification(inst):
    """One positive control per path. `1 + 1 == 2` is the pin that matters
    most: its left side arrives as an Add TREE, not an int, and a naive
    isinstance check against (int, float) classifies the most basic
    arithmetic site STRUCTURAL — which the first draft of this classifier
    did."""
    mod, path = _load(SRC.format(n="_ei1"), "_ei1")
    _run(mod, ("test_ground",))
    _run(mod, ("binds", Var()))
    _run(mod, ("structural", ("lo",)))
    _run(mod, ("constrains", Var(), Var()))
    by_line = {r["line"]: r["path"] for r in inst.records()}
    assert by_line[3] == instrument.TEST, "1 + 1 == 2 is arithmetic, not structural"
    assert by_line[4] == instrument.BIND
    assert by_line[5] == instrument.STRUCTURAL
    assert by_line[6] == instrument.CONSTRAINT


def test_the_site_is_the_real_clausal_file_not_the_template(inst):
    """The clause code object reports co_filename `<template>`; the real path
    lives on the frame's globals. Pinning it stops a future refactor from
    silently reporting every site against `<template>`."""
    mod, path = _load(SRC.format(n="_ei2"), "_ei2")
    _run(mod, ("test_ground",))
    files = {r["file"] for r in inst.records()}
    assert files == {os.path.abspath(path)}
    assert all(f.endswith(".clausal") for f in files)


def test_one_record_per_execution_duplicates_preserved(inst):
    """The verdict table needs the multiset, not the set: a site is only
    FORCED to `#=` if it took two different paths across executions."""
    mod, _ = _load(SRC.format(n="_ei3"), "_ei3")
    _run(mod, ("test_ground",))
    _run(mod, ("test_ground",))
    _run(mod, ("test_ground",))
    assert len([r for r in inst.records() if r["line"] == 3]) == 3


def test_a_site_taking_two_modes_reports_both(inst):
    """The case with no correct static answer: the SAME site binds on one
    call and tests on another. This is what makes `#=` forced rather than
    chosen, so the instrument has to be able to see it at all."""
    src = (
        "-module(_ei4, [eq(X, Y)])\n"
        "-double_quotes(chars)\n"
        "eq(X, Y) <- (X == Y + 1)\n"
    )
    mod, _ = _load(src, "_ei4")
    _run(mod, ("eq", Var(), 1))          # X unbound, Y ground -> binds
    _run(mod, ("eq", 3, 2))              # both ground        -> tests
    paths = {r["path"] for r in inst.records() if r["line"] == 3}
    assert paths == {instrument.BIND, instrument.TEST}


def test_install_twice_refuses_rather_than_double_counting(inst):
    with pytest.raises(RuntimeError, match="twice"):
        instrument.install()


def test_uninstall_restores_and_stops_recording():
    import clausal.logic.compiler.predicate as predicate
    before = predicate._fd_eq_fn
    instrument.reset()
    instrument.install()
    assert predicate._fd_eq_fn is not before
    instrument.uninstall()
    assert predicate._fd_eq_fn is before
    mod, _ = _load(SRC.format(n="_ei5"), "_ei5")
    _run(mod, ("test_ground",))
    assert instrument.records() == []


def test_an_exception_propagates_and_is_not_recorded_as_a_path(inst):
    """A raising comparison is not a classification. Swallowing it here would
    both corrupt the data and hide a real engine error."""
    src = ("-module(_ei6, [bad(X), lo])\n-double_quotes(chars)\n"
           "bad(X) <- (X == lo)\n")
    mod, _ = _load(src, "_ei6")
    with pytest.raises(Exception):
        _run(mod, ("bad", Var()))
    assert inst.records() == []


def test_write_jsonl_round_trips(inst, tmp_path):
    mod, _ = _load(SRC.format(n="_ei7"), "_ei7")
    _run(mod, ("binds", Var()))
    out = tmp_path / "obs.jsonl"
    n = instrument.write_jsonl(out)
    rows = [json.loads(line) for line in out.read_text().splitlines()]
    assert n == len(rows) == len(inst.records())
    assert set(rows[0]) == {"file", "line", "path"}


def test_a_var_comparison_that_shows_no_mode_is_FAILED_not_TEST(inst):
    """`X == X + 1` is inconsistent: nothing binds, nothing is posted, no
    arithmetic is performed. Recording that as TEST would let the verdict
    table report `'=:='` MEASURED off a run in which the site never did
    arithmetic — a confidence the data did not earn, and baked into the
    RECORDS, where no later fix can recover it: only a full re-run gets it
    back. FAILED is absorbing downstream, so it never decides and never
    forces; it is nearer NOT_EXERCISED than TEST, with the useful difference
    that a test DOES reach the site, so the remedy is a better test."""
    src = ("-module(_ei8, [p(X)])\n-double_quotes(chars)\n"
           "p(X) <- (X == X + 1)\n")
    mod, _ = _load(src, "_ei8")
    _run(mod, ("p", Var()))
    assert [r["path"] for r in inst.records()] == [instrument.FAILED]


def test_FAILED_does_not_displace_a_real_mode_at_the_same_site(inst):
    """Negative control on the classifier, mirroring the absorbing rule on
    the merge side: a site that fails once and BINDS once must report both,
    so the merge can drop FAILED and still see `is`. If FAILED were sticky
    here, a clean binding site would come back with no mode at all."""
    src = ("-module(_ei9, [p(X, Y)])\n-double_quotes(chars)\n"
           "p(X, Y) <- (X == Y)\n")
    mod, _ = _load(src, "_ei9")
    _run(mod, ("p", Var(), 7))              # binds
    _run(mod, ("p", 1, 2))                  # ground, both numeric -> TEST
    paths = [r["path"] for r in inst.records()]
    assert instrument.BIND in paths
    assert instrument.FAILED not in paths
