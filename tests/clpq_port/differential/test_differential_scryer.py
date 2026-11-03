"""The port against Scryer's library(clpq), EXACTLY, on generated queries.

tests/clpq_port/test_against_oracle.py compares hand-picked queries, and
the residuals of most of them by z3 equivalence.  Here seeded queries of
10 to 40 variables (_scryer_batch.query: boxes, band or random sparse
rows, equations, disequations, strict bounds, var-number and var-var
bindings between the posts, sup/inf into S, bb_inf/5 with its vertex,
projections onto subsets) go to both, and the answers must be IDENTICAL:
the same number of answers, every shown binding the same exact number,
and the residual dump/3 prints the same constraints as text in the same
order.  Where they are not, the difference is classified: equivalent
residuals (z3, tests/clpq_oracle.py same_solution_sets) in another form
or order, or different answers.

A difference listed in _KNOWN_DIFFERENCES (with its DEVIATIONS.md entry
and reason) is expected; any other fails the test, and the failure names
every one.  Scryer's copy of 1.3.3 is the oracle, not 1.3.3 itself
(DEVIATIONS.md D4: SICStus's order of variables can differ again).

Default: 40 queries, about ten seconds; CLPQ_DIFFERENTIAL=full: 300.
Skipped without the Scryer build (tests/_oracles.py).
"""
import os
import pathlib

import pytest

from tests._oracles import SCRYER
from tests.clpq_oracle import same_solution_sets
from tests.clpq_port.differential._scryer_batch import queries, scryer_batch
from tests.clpq_port.test_against_oracle import port_answers, residual_text

FULL = os.environ.get("CLPQ_DIFFERENTIAL") == "full"

#: query id -> (DEVIATIONS.md entry, why the port differs).  The run of
#: 2026-11-03: the 40 default queries and 299 of the 300 full ones answer
#: exactly as Scryer does, bindings, residual text and order included.
_KNOWN_DIFFERENCES = {
    # full set only: 40 variables, random sparse rows; dump/3 of all 40
    # raises resource_error(clpq_projection) past the 4,000,000 work cap,
    # where Scryer (no cap) answers.
    "scryer-40-62": ("D24", "dump/3's projection passes the "
                     "clpq_projection cap; 1.3.3 has no cap"),
}

_BATCH = 25


def difference(got, want):
    """None where the answers are identical, else a one-line description
    and its class: "bindings", "text" (equivalent residuals, different
    text or order) or "answers" (z3 finds them different)."""
    if len(got) != len(want):
        return "answers", f"{len(got)} answers against Scryer's {len(want)}"
    if [a.bindings for a in got] == [a.bindings for a in want] \
            and residual_text(got) == residual_text(want):
        return None
    equivalent, why = same_solution_sets(got, want)
    if [a.bindings for a in got] != [a.bindings for a in want]:
        kind = "bindings" if equivalent else "answers"
    else:
        kind = "text" if equivalent else "answers"
    return kind, (f"{why or 'equivalent'}; port {residual_text(got)} "
                  f"{[a.bindings for a in got]}; Scryer {residual_text(want)} "
                  f"{[a.bindings for a in want]}")


def compare_with_scryer(cases):
    """Every case of *cases* on both systems: (new, known), lists of
    compiler-style lines."""
    new, known = [], []
    for start in range(0, len(cases), _BATCH):
        batch = cases[start:start + _BATCH]
        wanted = scryer_batch(batch)
        for name, text, shown in batch:
            want = wanted[name]
            if type(want) is tuple:
                found = ("scryer-error", want[1][:300])
            else:
                try:
                    got = port_answers(text, shown, bounds=False)
                except Exception as error:      # reported, never hidden
                    found = ("port-error", f"{type(error).__name__}: {error}")
                else:
                    found = difference(got, want)
            if found is None:
                continue
            line = f"{name}: {found[0]}: {found[1]}\n    query: {text}"
            (known if name in _KNOWN_DIFFERENCES else new).append(line)
    return new, known


@pytest.mark.skipif(not pathlib.Path(SCRYER).exists(),
                    reason=f"needs the Scryer CLP(Q) build at {SCRYER}")
def test_generated_queries_answer_exactly_as_scryer():
    cases = queries(full=FULL)
    new, _ = compare_with_scryer(cases)
    assert not new, (f"{len(new)} of {len(cases)} queries differ from "
                     f"Scryer's dump/3 and are not known differences:\n"
                     + "\n".join(new))


def test_the_known_differences_name_a_deviation():
    for name, (entry, reason) in _KNOWN_DIFFERENCES.items():
        assert entry.startswith("D") and reason, name
