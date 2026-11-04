"""The workload families reach the code they were added for.

A review of the differential harness found three gaps, each closed by
workloads whose golden records test_differential_golden.py compares:

* F1: no workload compared non-linear bases, so compare_power_products
  never handed a pair of bases to the standard order of terms
  (normal_form._standard_order).  The ``base_skeletons`` family posts
  abs/min/max/product/quotient bases and wakes them.
* F2: every workload ran on a bare trail (``defer`` False).  The engine
  workloads (_engine.py) run programs through the engine, .pl and
  .clausal.
* F3: a shared row tail (linear_forms._SharedTail) was kept unread only
  inside chain_bind's multi-variable unifications, and never read or
  shared again after an undo.  The ``long_row_tails`` family keeps shared
  rows in the store across marks and undos.

These tests count what the default corpus's workloads of each family run,
so a generator change that stops reaching the code fails here, not
silently.
"""
import collections

import pytest

from clausal.logic.clpq import SOLVER, linear_forms, normal_form
from tests.clpq_port.differential import _engine, _golden, _observe
from tests.clpq_port.differential._workloads import corpus


def _family(workload):
    return workload["id"].rsplit("-", 2)[0]


@pytest.fixture
def counters(monkeypatch):
    """Counts of what the port does while workloads run under
    :func:`run`: standard-order comparisons by kind and by the classes of
    the bases compared; shared tails made, read and shared again, and
    whether an undo of the workload came between a tail's making and its
    reading or sharing again."""
    counts = collections.Counter()
    state = {"step": None, "undos": [], "born": {}}

    standard_order = normal_form._standard_order

    def counting_standard_order(kind, first, second):
        counts[f"standard_order:{kind}"] += 1
        if kind == normal_form._BASES:
            for base in (first, second):
                counts[f"base:{type(normal_form.deref(base)).__name__}"] += 1
        return standard_order(kind, first, second)
    monkeypatch.setattr(normal_form, "_standard_order", counting_standard_order)

    def after_an_undo(form):
        born = state["born"].get(id(form))
        if born is None or born[1] is not form or born[0] is None:
            return False
        return any(born[0] < undo < state["step"] for undo in state["undos"])

    shared = linear_forms._SharedTail
    make = shared.__init__

    def counting_make(self, *arguments):
        make(self, *arguments)
        counts["shared:made"] += 1
        state["born"][id(self)] = (state["step"], self)
    monkeypatch.setattr(shared, "__init__", counting_make)

    read = shared.terms

    def counting_read(self):
        if self.base is not None:
            counts["shared:read"] += 1
            if after_an_undo(self):
                counts["shared:read after an undo"] += 1
        return read.fget(self)
    monkeypatch.setattr(shared, "terms", property(counting_read))

    from_tail = linear_forms._delete_factor_from_tail

    def counting_from_tail(variable, form, base, start):
        counts["shared:shared again"] += 1
        if after_an_undo(form):
            counts["shared:shared again after an undo"] += 1
        return from_tail(variable, form, base, start)
    monkeypatch.setattr(linear_forms, "_delete_factor_from_tail",
                        counting_from_tail)

    step = _observe._Run.step

    def numbered_step(self, current):
        state["step"] = next(i for i, s in enumerate(self.workload["steps"])
                             if s is current)
        return step(self, current)
    monkeypatch.setattr(_observe._Run, "step", numbered_step)

    def run(workloads):
        counts.clear()
        for workload in workloads:
            state["undos"] = [i for i, s in enumerate(workload["steps"])
                              if s[0] == "undo"]
            state["born"] = {}
            state["step"] = None
            _observe.observe(workload)
        return counts
    return run


def test_the_skeleton_family_compares_bases_by_the_standard_order(counters):
    # F1.  The families that were there before never reach it (0 in the
    # default corpus, 2026-11-04); the skeleton family compares skeletons
    # with skeletons and with variables.
    counts = counters([w for w in corpus() if _family(w) == "base_skeletons"])
    assert counts[f"standard_order:{normal_form._BASES}"] > 0, counts
    assert counts["base:NonlinearBase"] > 0, counts
    assert counts["base:Var"] + counts["base:AttVar"] > 0, counts
    others = counters([w for w in corpus() if _family(w) == "mixed"])
    assert others[f"standard_order:{normal_form._BASES}"] == 0, others


def test_the_long_row_family_keeps_shared_tails_across_undos(counters):
    # F3: tails made, shared again, and read or shared again after an
    # undo put them back.
    counts = counters([w for w in corpus() if _family(w) == "long_row_tails"])
    assert counts["shared:made"] > 0, counts
    assert counts["shared:shared again"] > 0, counts
    assert counts["shared:read after an undo"] > 0, counts
    assert counts["shared:shared again after an undo"] > 0, counts


def test_every_engine_template_runs_on_both_surfaces_alike():
    # F2.  A program that runs as .pl and as .clausal answers and decides
    # the same on both: the golden records of the two are equal.
    index, observations = _golden.load()
    workloads = _engine.corpus(full=False)
    assert {w["id"].split("-")[1] for w in workloads} == set(_engine.TEMPLATES)
    problems = []
    for workload in workloads:
        if workload["surface"] != ".clausal":
            continue
        twin = workload["id"][:-len("clausal")] + "pl"
        for key in ("observation", "trace"):
            if index[workload["id"]][key] != index[twin][key]:
                problems.append(f"{workload['id']}: {key} differs from {twin}")
    assert not problems, "\n".join(problems)


@pytest.mark.skipif(SOLVER != "holzbaur", reason="needs CLAUSAL_CLPQ=holzbaur")
def test_the_engine_workloads_answer_and_pivot_through_the_port():
    # The engine workloads exercise the port (CLAUSAL_CLPQ=holzbaur), not
    # legacy: their recorded traces hold pivots, and their answers hold
    # optima, bindings and residuals.
    index, observations = _golden.load()
    workloads = _engine.corpus(full=False)
    assert sum(index[w["id"]]["pivots"] for w in workloads) > 0
    answers = [a for w in workloads for a in observations[w["id"]]["answers"]]
    assert any(a["residual"] for a in answers)
    assert all(observations[w["id"]]["answers"] for w in workloads
               if w["id"].startswith(("engine-freeze", "engine-dif")))


def test_no_record_of_the_new_families_depends_on_a_work_cap():
    # Where a resource_error of a clpq cap (DEVIATIONS.md D24) is raised
    # depends on the work count, which an implementation-only change may
    # alter without changing the algorithm: the generators keep the new
    # families' projections below the caps (as dense and banded do).
    import json
    index, observations = _golden.load()
    full = corpus(full=True) + _engine.corpus(full=True)
    capped = [w["id"] for w in full
              if _family(w) in ("base_skeletons", "long_row_tails")
              or w.get("driver") == "engine"
              if "resource_error" in json.dumps(observations[w["id"]])]
    assert not capped, capped
