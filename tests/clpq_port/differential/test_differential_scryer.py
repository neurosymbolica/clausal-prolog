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
import re

import pytest

import clausal.logic.clpq as clpq
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
    for known in (_ENGINE_KNOWN, _BARE_KNOWN):
        for name, (entry, reason) in known.items():
            assert (entry.startswith("D") or entry == "scryer") and reason, name
    for name, (entry, kind, reason) in _MULTIBIND_BASELINE.items():
        assert (entry.startswith("D") or entry == "open") and kind \
            and reason, name


# ------------------------------------------------- engine workloads (F2)

#: A delayed non-linear goal in the port's residual: Scryer's dump/3 drops
#: them (ruling R8, test_against_oracle.py), so they are left out here.
_DELAYED_GOAL = re.compile(r"\^|abs\(|min\(|max\(|[A-Z_]\w*\s*\*\s*[A-Z_]|/\s*[A-Z_(]")


def linear_only(answers):
    from tests.clpq_oracle import Answer
    return [Answer(a.bindings, [c for c in a.residual
                                if not _DELAYED_GOAL.search(c)])
            for a in answers]


#: Engine workloads (_engine.py) whose answers differ from Scryer's, the
#: program as it is and with its multi-variable unifications made one at
#: a time: id -> (DEVIATIONS.md entry or "scryer", why).  Full set only;
#: the default set answers as Scryer does (2026-11-04).
_ENGINE_KNOWN = {
    # X0 is a CLP(FD) variable; promoted to CLP(Q) it brings its domain's
    # bounds (D20), which Scryer's clpq, knowing nothing of clpz, lacks
    **{f"engine-fd-12-2-{s}": ("D20", "the FD variable's bounds are in "
                               "the residual") for s in ("pl", "clausal")},
    # Scryer raises uninstantiation_error in get_atts/2 while waking
    # abs(X1 - X1) and max(X1, X1); the port's answer X0 = 2, X1 = 3,
    # X2 = 2, S = 2 satisfies every constraint (checked by hand)
    **{f"engine-nonlinear-3-1-{s}": ("scryer", "Scryer raises "
                                     "uninstantiation_error(2) in get_atts/2")
       for s in ("pl", "clausal")},
}


def engine_difference(workload):
    """None, or (kind, text) of how the port's answers to *workload*
    differ from Scryer's: as the program is, then with its
    multi-variable unifications split (D3), which is no difference."""
    from tests.clpq_oracle import oracle_answers
    from tests.clpq_port.differential import _engine
    from tests.clpq_port.differential._scryer_batch import split_unifications
    goal = f"q({', '.join(workload['shown'])})"
    program = workload.get("oracle_program", workload["program"])
    try:
        got = linear_only(_engine.scryer_comparable(workload))
    except Exception as error:              # reported, never hidden
        return "port-error", f"{type(error).__name__}: {error}"
    found = None
    for text in (program, split_unifications(program)):
        try:
            found = difference(got, oracle_answers(text, goal, workload["shown"]))
        except RuntimeError as error:
            found = ("scryer-error", str(error)[:300])
        if found is None:
            return None
    return found


@pytest.mark.skipif(not pathlib.Path(SCRYER).exists(),
                    reason=f"needs the Scryer CLP(Q) build at {SCRYER}")
@pytest.mark.skipif(clpq.SOLVER != "holzbaur",
                    reason="the engine reaches the port with CLAUSAL_CLPQ=holzbaur")
def test_engine_workloads_answer_as_scryer():
    # Every engine workload's answers: the same number, the same bindings,
    # the same residual text and order as Scryer's dump/3 (copy_term/2
    # workloads against the program without the copy: Scryer copies the
    # attributes, todo/copy-term-attributes-...).  Every difference is in
    # _ENGINE_KNOWN, and every entry of the set that ran still differs.
    from tests.clpq_port.differential import _engine
    workloads = _engine.corpus(full=FULL)
    new, agreeing = [], []
    for workload in workloads:
        found = engine_difference(workload)
        name = workload["id"]
        if found is None:
            if name in _ENGINE_KNOWN:
                agreeing.append(f"{name}: known, but answers as Scryer does")
        elif name not in _ENGINE_KNOWN:
            new.append(f"{name}: {found[0]}: {found[1]}")
    assert not new and not agreeing, "\n".join(
        [f"{len(new)} of {len(workloads)} engine workloads differ from "
         f"Scryer:"] + new + agreeing)


# ------------------------------- the new bare families, result by result

def _renamed(strings, pattern=r"_[TQI]\d+"):
    table = {}
    return [re.sub(pattern, lambda m: table.setdefault(
        m.group(0), f"_V{len(table) + 1}"), text) for text in strings]


def _same_dump(recorded, residual):
    """A recorded dump against a replay's residual, as text, internal
    variables named by first appearance; aliased variables may be named
    by another member of their class on each side (the dump names a
    target, the replay its first shown name), so failing the first test
    every variable is named by first appearance."""
    from tests.clpq_oracle import Answer
    rest = [c for c in residual if not re.fullmatch(r"X\d+=X\d+", c)]
    for pattern in (r"_[TQI]\d+", r"\bX\d+\b|_[TQI]\d+"):
        if residual_text([Answer({}, _renamed(recorded, pattern))]) \
                == residual_text([Answer({}, _renamed(rest, pattern))]):
            return True
    return False


def _number(spelt):
    from fractions import Fraction
    return Fraction(spelt) if isinstance(spelt, (int, str)) else spelt


def replay_problem(kind, data, got, shown):
    """None where the port, replaying a recorded result's conjunction on
    a fresh trail (port_answers), agrees with the recording, else why."""
    if type(got) is tuple:
        return None if kind == "fails" and type(data) is list else str(got)
    if kind == "fails":
        return None if not got else f"{len(got)} answers"
    if kind == "optimum":
        if data is None:
            return None if not got else "an optimum where none was recorded"
        if len(got) == 1 and got[0].bindings.get("S") == _number(data):
            return None
        return f"optimum {[a.bindings for a in got]}"
    if len(got) != 1:
        return f"{len(got)} answers"
    if kind == "dump":
        return None if _same_dump(data or [], got[0].residual) else "residual"
    final = data["final"]
    for name, value in zip(shown, final):
        if not (isinstance(value, str) and value[:1] in "X_") \
                and got[0].bindings.get(name) != _number(value):
            return f"{name}: {got[0].bindings.get(name)} recorded {value}"
    if not _same_dump(data.get("residual", []), got[0].residual):
        return "residual"
    return None


#: Results of the base_skeletons and long_row_tails workloads of the
#: default corpus that differ from Scryer: query id -> (entry, why).  The
#: full corpus (1,405 base_skeletons and 394 long_row_tails results, run
#: once on 2026-11-04, not by this test) differs in these classes too and,
#: besides, where Scryer is wrong or raises: Scryer raises in get_atts/2
#: (uninstantiation_error) or nf/2 (type_error) waking a skeleton; its
#: optimum or bound is a float-rounded rational (N rdiv 2^k); it fails or
#: gives an optimum the linear constraints alone exclude (checked with z3)
#: where the port answers correctly.
_ORDER = ("z3 finds the residuals equivalent; the constraints are in "
          "another order, or a row is solved for another variable (D4: "
          "creation order, where Scryer orders as 1.3.3 does)")
_BARE_KNOWN = {
    "base_skeletons-5-0@15": ("D4", _ORDER),
    "base_skeletons-8-1@27": ("D4", _ORDER),
    "long_row_tails-16-0@end": ("D4", _ORDER),
    "long_row_tails-24-1@end": ("D4", _ORDER),
}


@pytest.mark.skipif(not pathlib.Path(SCRYER).exists(),
                    reason=f"needs the Scryer CLP(Q) build at {SCRYER}")
@pytest.mark.skipif(not FULL, reason="CLPQ_DIFFERENTIAL=full (minutes)")
def test_the_skeleton_and_long_row_results_answer_as_scryer():
    # Every result the golden records of the default corpus's
    # base_skeletons and long_row_tails workloads hold (each dump, optimum,
    # failed step and the final store) as one conjunction of the store
    # steps in force (_scryer_batch.workload_queries): the port replaying
    # it on a fresh trail must give the recorded result, and Scryer the
    # same answers (delayed non-linear goals left out: Scryer's dump/3
    # drops them), or Scryer the same with the unifications split (D3).
    from tests.clpq_port.differential import _golden
    from tests.clpq_port.differential._scryer_batch import (
        split_unifications, workload_queries)
    from tests.clpq_port.differential._workloads import corpus
    _, observations = _golden.load()
    cases = []
    for workload in corpus(full=False):
        if workload["id"].rsplit("-", 2)[0] in ("base_skeletons",
                                                "long_row_tails"):
            cases += workload_queries(workload, observations[workload["id"]])
    replays, new, agreeing = [], [], []
    for start in range(0, len(cases), _BATCH):
        batch = cases[start:start + _BATCH]
        plain = scryer_batch([(n, t, s) for n, t, s, _ in batch])
        split = scryer_batch([(n, split_unifications(t), s)
                              for n, t, s, _ in batch])
        for name, text, shown, (kind, data) in batch:
            try:
                got = port_answers(text, shown, bounds=False)
            except Exception as error:      # reported, never hidden
                got = ("raised", f"{type(error).__name__}: {error}")
            problem = replay_problem(kind, data, got, shown)
            if problem:
                replays.append(f"{name}: the replay differs: {problem}\n"
                               f"    query: {text}")
            found = ("port-error", got[1]) if type(got) is tuple else None
            for want in (plain[name], split[name]):
                if type(got) is tuple:
                    break
                if type(want) is tuple:
                    found = ("scryer-error", want[1][:200])
                    continue
                try:
                    found = difference(linear_only(got), want)
                except ValueError as error:
                    found = ("unparsed", str(error))
                if found is None:
                    break
            if found is None:
                if name in _BARE_KNOWN:
                    agreeing.append(f"{name}: known, but answers as Scryer")
            elif name not in _BARE_KNOWN:
                new.append(f"{name}: {found[0]}: {found[1][:400]}\n"
                           f"    query: {text}")
    assert not replays and not new and not agreeing, "\n".join(
        [f"{len(replays)} replays and {len(new)} of {len(cases)} results "
         f"differ:"] + replays + new + agreeing)
