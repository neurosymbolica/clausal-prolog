"""The Holzbaur port against its own recorded answers AND decisions.

What this guards.  The fuzzers (tests/clpq_port/fuzz/) accept any CORRECT
answer, but CLP(Q) answers are not unique: which optimal vertex bb_inf
picks among ties, which optimal face maximize leaves free, the form and
order of residual constraints, which variables a projection eliminates and
in what order (DEVIATIONS.md D4, D11), which goals stay delayed.  A change
to the port's data structures that alters the pivot order passes every
fuzzer and can still answer differently from 1.3.3.  This test runs a
seeded corpus of workloads (_workloads.py: 2 to 200 variables; chains,
dense and banded rows, tied optima, equations, strict and non-strict
bounds, disequations, var-var and var-number bindings, bb_inf/5, sup, inf,
maximize, minimize, entailed, dump/3 onto subsets, non-linear constraints
that wait and wake, marks and undos) and compares, per workload, with the
golden files recorded from the port (_golden.py):

* the OBSERVATION: each step's success, failure or error term, every
  optimum, vertex and binding as an exact typed number, the residual and
  delayed goals exactly as dump/3 prints them, order included;
* the ALGORITHM TRACE: every pivot (leaving and entering variable,
  coefficient, component), bound swap, solved-for variable and its
  preference category, Fourier-Motzkin elimination, bb_inf branch and
  incumbent, through the port's TRACE hooks (None when no harness runs).

Variables are named canonically (Xi, then _Tk by first appearance), never
by id(), so a run is reproducible across processes.

A GOLDEN CHANGE IS A POTENTIAL DEVIATION FROM 1.3.3.  An observation
change is a changed answer; a trace change with the same observations is
a changed algorithm that the corpus did not catch in an answer, which is
the case a complexity change must show it does not have.  Before
regenerating (``python -m tests.clpq_port.differential.regenerate``, with
--full for the large corpus), either show the new records are what
1.3.3's algorithm gives (and that the old ones were a port bug), with a
DEVIATIONS.md entry for the change, or prove the difference is not
observable and say why in the commit.  "It is still correct" is not
enough: the fuzzers already check that.

The default corpus runs in seconds; ``CLPQ_DIFFERENTIAL=full`` runs the
full one (minutes).  A failure names EVERY differing workload, then shows
the observation diff of the first few.
"""
import os
import re

from tests.clpq_port.differential import _golden
from tests.clpq_port.differential._workloads import corpus

FULL = os.environ.get("CLPQ_DIFFERENTIAL") == "full"

#: A product of two variables in a dumped goal: a delayed non-linear goal.
_PRODUCT = re.compile(r"(X|_T|_Q)\d+\s*\*\s*(X|_T|_Q)\d+")


def test_every_workload_answers_and_decides_as_recorded():
    index, observations = _golden.load()
    workloads = corpus(full=FULL)
    problems, details = _golden.compare(workloads, index, observations)
    message = "\n".join(
        [f"{len(problems)} of {len(workloads)} workloads differ from the "
         f"golden records (a potential deviation from 1.3.3: see this "
         f"module's docstring):"] + problems + details)
    assert not problems, message


def test_the_corpus_is_deterministic_and_reaches_every_step_kind():
    # The corpus covers what the docstring promises, and every workload id
    # is unique.
    workloads = corpus(full=False)
    assert len({w["id"] for w in workloads}) == len(workloads)
    kinds = {step[0] for w in workloads for step in w["steps"]}
    assert kinds == {"post", "nonlinear", "bind", "alias", "mark", "undo",
                     "sup", "inf", "maximize", "minimize", "bb_inf",
                     "entailed", "dump"}
    assert max(w["variables"] for w in workloads) >= 100
    assert corpus(full=False) == workloads


def test_the_golden_records_hold_answers_of_every_kind():
    # A corpus whose steps all failed would compare nothing: the recorded
    # observations hold successes, failures, optima, vertices, bindings,
    # residuals and delayed goals.
    _, observations = _golden.load()
    default = {w["id"] for w in corpus(full=False)}
    seen = {"true": 0, "false": 0, "value": 0, "vertex": 0, "residual": 0,
            "delayed": 0, "binding": 0}
    for name in default:
        observation = observations[name]
        for result in observation["steps"]:
            if result is True:
                seen["true"] += 1
            elif result is False:
                seen["false"] += 1
            elif type(result) is list and result[0] is True:
                data = result[1]
                if type(data) is list and len(data) == 2 \
                        and type(data[1]) is list:
                    seen["vertex"] += 1
                elif type(data) is list:
                    seen["residual"] += 1
                    if any(_PRODUCT.search(c) for c in data):
                        seen["delayed"] += 1
                else:
                    seen["value"] += 1
        seen["binding"] += sum(1 for v in observation["final"]
                               if not (type(v) is str and v.startswith(("X", "_"))))
    assert all(seen.values()), seen
