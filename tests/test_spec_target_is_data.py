"""F1 row 35, the data half: the specializer's unfolder takes the predicate
AS DATA (``_SpecTarget``: a name, field names, and the cell they build), not
the ``PredicateMeta`` class.

Measured when this landed: all 136 specialized installs across the
specialization suites produced byte-identical clauses (variables renamed
canonically) before and after the change.
"""

from __future__ import annotations

import importlib
import os
import re
import sys

import pytest

from clausal.logic.predicate import make_predicate
from clausal.logic.specialization import (
    _SpecTarget, _specialized_fields, _unfold, analyze_mi,
)
from clausal.logic.variables import Var


def test_the_target_builds_the_cell_a_class_builds():
    """The target (name + fields, no class -- W4b-3 slice 4) builds the
    cell a class with the same fields builds."""
    cls = make_predicate("spt_p", ["a", "b", "c"])
    target = _SpecTarget("spt_p", ("a", "b", "c"))
    assert target(a=1, b=2, c=3) == cls(a=1, b=2, c=3) == ("spt_p", 1, 2, 3)
    # The unfolder's own builder fills a slot it leaves out with a fresh Var
    # (it writes its generated heads by keyword on purpose).
    partial = target(b=2)
    assert partial[0] == "spt_p" and partial[2] == 2
    assert isinstance(partial[1], Var) and isinstance(partial[3], Var)
    from clausal.logic.predicate import ClausalTermConstructionError
    with pytest.raises(ClausalTermConstructionError) as exc:
        target(nope=1)
    assert (exc.value.functor, exc.value.registered_fields) == (
        "spt_p", ("a", "b", "c"))


def _canon(clauses):
    names = {}
    return [re.sub(r"(?:Att)?Var\(_\w+\)",
                   lambda m: names.setdefault(m.group(0), f"V{len(names)}"),
                   repr(c.head) + " :- " + repr(c.body)) for c in clauses]


def _natnum_program():
    return [
        [["natnum", 0], []],
        [["natnum", ["s", "X"]], [["natnum", "X"]]],
    ]


@pytest.mark.parametrize("mi", ["solve", "solve_count", "solve_limit"])
def test_the_unfolder_runs_without_any_class(mi):
    """A target built from a name and fields alone -- the only shape since
    W4b-3 slice 4 -- unfolds to EXACTLY the clauses the class-built target
    unfolded to (recorded on 9fa2cfa0, before the class went:
    ``fixtures/spec_target_unfold_goldens.json``)."""
    import json
    mis = importlib.import_module("clausal.examples.metainterpreters")
    pattern = analyze_mi(getattr(mis, mi))
    fields = tuple(_specialized_fields(pattern))
    classless = _unfold(pattern, _natnum_program(),
                        _SpecTarget("spt_spec", fields))
    with open(os.path.join(_FIXTURES, "spec_target_unfold_goldens.json")) as f:
        golden = json.load(f)[mi]
    assert golden, "empty golden: nothing compared"
    assert _canon(classless) == golden


def test_a_specialize_target_carries_its_directive_site():
    """The ``registered by`` line: the make_predicate class carried
    ``_registered_at``; the target reads its row's ``declared_at``, which
    ``compiler_v2._run_specialization`` stamps with the ``-specialize``
    directive's own line (``_declared_site``)."""
    from clausal.import_hook import _load_module
    from clausal.logic.predicate import ClausalTermConstructionError
    from clausal.logic.specialization import _declared_site
    path = os.path.join(_FIXTURES, "specialize_natnum.clausal")
    name = "_spt_site_natnum"
    sys.modules.pop(name, None)
    try:
        mod = _load_module(name, path)
    finally:
        sys.modules.pop(name, None)
    db = mod.__dict__["$module"].db
    with open(path) as f:
        line = next(i for i, text in enumerate(f, 1)
                    if text.startswith("-specialize(") and
                    "solve_count_natnum" in text)
    site = _declared_site(db, "solve_count_natnum", 2)
    assert site == (os.path.abspath(path), line) or site == (path, line), site
    target = _SpecTarget("solve_count_natnum", ("GOALS", "COUNT"), site)
    with pytest.raises(ClausalTermConstructionError) as exc:
        target(nope=1)
    assert exc.value.registered_at == site


# ── the actual output, against main's (class-built) output ──────────────────

_FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")


def _per_clause(lines):
    """Renumber variables within EACH clause.  The dump named them across the
    whole list, which froze accidental sharing of Var objects between
    separate clauses (the CPD pass does not rename clauses apart); a golden
    should pin structure, not that."""
    out = []
    for line in lines:
        names = {}
        out.append(re.sub(r"\bV\d+\b",
                          lambda m: names.setdefault(m.group(0), f"V{len(names)}"),
                          line))
    return out


def _goldens():
    with open(os.path.join(_FIXTURES, "spec_target_goldens.txt")) as f:
        text = f.read()
    body = "\n".join(l for l in text.splitlines() if not l.startswith("#"))
    out = {}
    for block in re.split(r"(?m)^(?===)", body):
        if block.strip():
            header, *lines = block.strip().splitlines()
            out[header.split()[1]] = lines
    return out


def _installed_by_loading(stem, monkeypatch):
    from clausal.import_hook import _load_module
    from clausal.logic import specialization as sp
    captured = {}
    real = sp._install_specialized

    def spy(new_name, fields, clauses, *a, **k):
        captured[f"{new_name}/{len(fields)}"] = _canon(clauses)
        return real(new_name, fields, clauses, *a, **k)

    monkeypatch.setattr(sp, "_install_specialized", spy)
    name = f"_spt_golden_{stem}"
    sys.modules.pop(name, None)
    try:
        _load_module(name, os.path.join(_FIXTURES, f"{stem}.clausal"))
    finally:
        sys.modules.pop(name, None)
    return captured


@pytest.mark.parametrize("stem,key", [
    ("specialize_deep", "deep_natnum/1"),          # the deep path
    ("specialize_cpd", "cpd_graph/1"),             # the CPD path
    ("specialize_cpd", "cpd_count_natnum/2"),      # the CPD path, 2 fields
    ("specialize_builtins", "solve_factorial/1"),  # a residual clause
])
def test_each_unfolding_path_installs_what_main_installed(
        stem, key, monkeypatch):
    golden = _per_clause(_goldens()[key])
    assert golden, "empty golden: nothing compared"
    assert _per_clause(_installed_by_loading(stem, monkeypatch)[key]) == golden


def test_the_direct_api_installs_what_main_installed(monkeypatch):
    from clausal.logic.specialization import specialize_mi
    from clausal.logic import specialization as sp
    mis = importlib.import_module("clausal.examples.metainterpreters")
    x = Var()
    program = [[["natnum", 0], []], [["natnum", ["s", x]], [["natnum", x]]]]
    got = {}
    real = sp._install_specialized

    def spy(new_name, fields, clauses, *a, **k):
        got["c"] = _canon(clauses)
        return real(new_name, fields, clauses, *a, **k)

    monkeypatch.setattr(sp, "_install_specialized", spy)
    specialize_mi(analyze_mi(mis.solve), program, "SolveNatnum")
    assert "c" in got, "nothing installed"
    assert _per_clause(got["c"]) == _per_clause(_goldens()["SolveNatnum/1"])
