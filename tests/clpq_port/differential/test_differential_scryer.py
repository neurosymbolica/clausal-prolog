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
from tests.clpq_port.differential._scryer_batch import (
    multibind_queries, queries, scryer_batch)
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


#: Why a multi-binding query differs.  Scryer fails the unification, and
#: succeeds when the same bindings are made one at a time (checked for
#: every entry, 2026-11-03); the port answers both ways.  In these queries
#: one binding implies the value of a variable bound later in the same
#: unification (bv.pl's export_binding/1 binds it inside the earlier
#: variable's verify_attributes/3), and Scryer's driver then fails the
#: later binding (DEVIATIONS.md D3: "Scryer's clpq fails
#: {X + Y = 3}, f(X, Y) = f(1, 2); the port answers it").
_SCRYER_FAILS = ("Scryer fails the one unification and succeeds with the "
                 "same bindings made one at a time; the port answers")
#: Not about bindings: the posts alone already dump in another order.
#: The smallest case found, {X1 = X0 + 2}, {X1 =< X2}, {X0 >= -2}: the
#: port dumps [X1-X2=<0, X1>=0, X0=-2+X1], Scryer [X1-X2=<0, X0=-2+X1,
#: X1>=0].  Not investigated; no DEVIATIONS.md entry covers it ("open").
_POSTED = ("the residual of the posts alone is in another order "
           "(X0=-2+X1 and X1>=0 swapped); not investigated")

#: Multi-binding queries (_scryer_batch.multibind_query: several variables
#: of one store bound in ONE unification) that differ from Scryer, query id
#: -> (DEVIATIONS.md entry or "open", class, why), default and full sets.
#: Every difference is listed, and a listed query that now answers as
#: Scryer does fails the test too, so the list stays exact.  The baseline
#: of 2026-11-03, before the bound variables' work was done in binding
#: order (D3, ruling 2026-11-03), also held scryer-multibind-40-98 (text:
#: the member list's order, newest first, selected another basis); it
#: answers as Scryer does since.
_MULTIBIND_BASELINE = {
    "scryer-multibind-3-0": ("D3", "answers", _SCRYER_FAILS),
    "scryer-multibind-3-45": ("D3", "answers", _SCRYER_FAILS),
    "scryer-multibind-3-99": ("D3", "answers", _SCRYER_FAILS),
    "scryer-multibind-3-171": ("D3", "answers", _SCRYER_FAILS),
    "scryer-multibind-3-207": ("D3", "answers", _SCRYER_FAILS),
    "scryer-multibind-3-243": ("D3", "answers", _SCRYER_FAILS),
    "scryer-multibind-3-261": ("D3", "answers", _SCRYER_FAILS),
    "scryer-multibind-4-100": ("D3", "answers", _SCRYER_FAILS),
    "scryer-multibind-4-136": ("D3", "answers", _SCRYER_FAILS),
    "scryer-multibind-4-154": ("D3", "answers", _SCRYER_FAILS),
    "scryer-multibind-4-244": ("D3", "answers", _SCRYER_FAILS),
    "scryer-multibind-4-253": ("D3", "answers", _SCRYER_FAILS),
    "scryer-multibind-6-11": ("D3", "answers", _SCRYER_FAILS),
    "scryer-multibind-6-92": ("D3", "answers", _SCRYER_FAILS),
    "scryer-multibind-6-254": ("D3", "answers", _SCRYER_FAILS),
    "scryer-multibind-8-84": ("D3", "answers", _SCRYER_FAILS),
    "scryer-multibind-8-183": ("D3", "answers", _SCRYER_FAILS),
    "scryer-multibind-10-4": ("D3", "answers", _SCRYER_FAILS),
    "scryer-multibind-10-18": ("D3", "answers", _SCRYER_FAILS),
    "scryer-multibind-10-22": ("D3", "answers", _SCRYER_FAILS),
    "scryer-multibind-10-130": ("D3", "answers", _SCRYER_FAILS),
    "scryer-multibind-10-211": ("D3", "answers", _SCRYER_FAILS),
    "scryer-multibind-10-247": ("D3", "answers", _SCRYER_FAILS),
    "scryer-multibind-15-86": ("D3", "answers", _SCRYER_FAILS),
    "scryer-multibind-15-140": ("D3", "answers", _SCRYER_FAILS),
    "scryer-multibind-15-221": ("D3", "answers", _SCRYER_FAILS),
    "scryer-multibind-20-6": ("D3", "answers", _SCRYER_FAILS),
    "scryer-multibind-20-42": ("D3", "answers", _SCRYER_FAILS),
    "scryer-multibind-20-51": ("D3", "answers", _SCRYER_FAILS),
    "scryer-multibind-20-78": ("D3", "answers", _SCRYER_FAILS),
    "scryer-multibind-20-105": ("D3", "answers", _SCRYER_FAILS),
    "scryer-multibind-20-168": ("D3", "answers", _SCRYER_FAILS),
    "scryer-multibind-20-240": ("D3", "answers", _SCRYER_FAILS),
    "scryer-multibind-20-285": ("D3", "answers", _SCRYER_FAILS),
    "scryer-multibind-20-294": ("D3", "answers", _SCRYER_FAILS),
    "scryer-multibind-30-70": ("D3", "answers", _SCRYER_FAILS),
    "scryer-multibind-30-79": ("D3", "answers", _SCRYER_FAILS),
    "scryer-multibind-30-178": ("D3", "answers", _SCRYER_FAILS),
    "scryer-multibind-30-187": ("D3", "answers", _SCRYER_FAILS),
    "scryer-multibind-30-223": ("D3", "answers", _SCRYER_FAILS),
    "scryer-multibind-30-286": ("D3", "answers", _SCRYER_FAILS),
    "scryer-multibind-40-125": ("D3", "answers", _SCRYER_FAILS),
    "scryer-multibind-40-197": ("D3", "answers", _SCRYER_FAILS),
    "scryer-multibind-40-215": ("open", "text", _POSTED),
    "scryer-multibind-40-260": ("D3", "answers", _SCRYER_FAILS),
}


def compare_with_scryer(cases, known_differences=None):
    """Every case of *cases* on both systems: (new, known), lists of
    compiler-style lines."""
    if known_differences is None:
        known_differences = _KNOWN_DIFFERENCES
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
            (known if name in known_differences else new).append(line)
    return new, known


@pytest.mark.skipif(not pathlib.Path(SCRYER).exists(),
                    reason=f"needs the Scryer CLP(Q) build at {SCRYER}")
def test_generated_queries_answer_exactly_as_scryer():
    cases = queries(full=FULL)
    new, _ = compare_with_scryer(cases)
    assert not new, (f"{len(new)} of {len(cases)} queries differ from "
                     f"Scryer's dump/3 and are not known differences:\n"
                     + "\n".join(new))


@pytest.mark.skipif(not pathlib.Path(SCRYER).exists(),
                    reason=f"needs the Scryer CLP(Q) build at {SCRYER}")
def test_multi_binding_queries_answer_as_scryer_or_as_the_baseline():
    # Several variables of one store bound in one unification: every
    # difference from Scryer is in the baseline, and every baseline entry
    # of the set that ran still differs.
    cases = multibind_queries(full=FULL)
    new, known = compare_with_scryer(cases, _MULTIBIND_BASELINE)
    ran = {name for name, _, _ in cases}
    differing = {line.split(":", 1)[0] for line in known}
    agreeing = sorted(name for name in _MULTIBIND_BASELINE
                      if name in ran and name not in differing)
    problems = [f"{len(new)} of {len(cases)} multi-binding queries differ "
                f"from Scryer and are not in the baseline:"] + new
    problems += [f"{name}: in the baseline but now answers as Scryer does "
                 f"(remove it)" for name in agreeing]
    assert not new and not agreeing, "\n".join(problems)


def test_the_known_differences_name_a_deviation():
    for name, (entry, reason) in _KNOWN_DIFFERENCES.items():
        assert entry.startswith("D") and reason, name
    for name, (entry, kind, reason) in _MULTIBIND_BASELINE.items():
        assert (entry.startswith("D") or entry == "open") and kind \
            and reason, name
