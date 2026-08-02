"""clausal.testing — test runner for .clausal predicate modules.

Discovers test/1 clauses in .clausal files and runs them. Each test clause
is a rule of the form:

    test("description") <- goal1, goal2, ...

A test passes if its body succeeds (produces at least one solution).

Standalone usage
----------------
    python -m clausal.testing clausal/examples/
    python -m clausal.testing clausal/examples/fibonacci.clausal

Pytest integration
------------------
The conftest.py plugin (see conftest.py at project root) uses this module
to collect and run .clausal tests as individual pytest items.

Failure diagnostics
-------------------
A bare "test X failed" is close to no signal for an automated repair loop, so
both runners — ``run_file`` for the CLI and the conftest plugin's
``ClausalItem`` for pytest — re-run a *failing* test's clause body in a
diagnostic mode (see :func:`diagnose_failure`) and report which conjunct
failed, its source text, the bindings established before it and — when the
goal is a satisfiable predicate call that merely did not unify — the solution
it *did* have.

Two invariants govern that re-run:

* It is **observation only.**  ``passed`` is decided before diagnostics start
  and is never revised.  Any exception, budget overrun or disagreement
  degrades to a note.
* It is **bounded** (wall-clock budget, conjunct cap, one solution per probe).

Its cost is irrelevant because it runs only on failure — but its *side
effects* are not free: see :func:`diagnose_failure` for the exposure.
"""

from __future__ import annotations

import contextlib
import io
import os
import signal
import sys
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterator


# ── Diagnostic bounds ─────────────────────────────────────────────────────────
# The re-run can hit runaway recursion, an infinite loop or a merely very
# expensive goal.  Three independent bounds; whichever trips first yields a
# partial diagnostic plus a note rather than a hang or a crash.

#: Wall-clock budget for the whole diagnostic pass of ONE failing test.
DIAG_BUDGET_ENV = "CLAUSAL_TEST_DIAG_BUDGET"
DEFAULT_DIAG_BUDGET = 10.0
#: Maximum number of body conjuncts walked.
DIAG_MAX_GOALS = 64
#: Maximum term depth reproduced when rendering a computed value.
DIAG_MAX_DEPTH = 40
#: Rung-3 descent: how many predicate-call levels below the failing goal.
DIAG_MAX_DESCENT_DEPTH = 2
#: Wrong-value/collapse scan: how many SATISFIABLE call levels it may follow.
#: Deliberately deeper than the failing-call descent bound — a wrong value
#: rides a chain of succeeding wrappers (assess → decide → stay_eligibility →
#: the collapsed findall in the measured incident), and the scan only ever
#: recurses into calls that already solved.  When this bound stops the scan it
#: says so in a note (see _note_depth_stop) instead of going silent.
DIAG_MAX_COLLAPSE_DEPTH = 5
#: ...how many clauses per descended predicate.
DIAG_MAX_DESCENT_CLAUSES = 4
#: ...how many leaf findings in total.
DIAG_MAX_DESCENT_LEAVES = 6
#: ...how many bindings per leaf.
DIAG_MAX_DESCENT_BINDINGS = 4


def _diag_budget() -> float:
    try:
        return float(os.environ.get(DIAG_BUDGET_ENV, DEFAULT_DIAG_BUDGET))
    except ValueError:
        return DEFAULT_DIAG_BUDGET


class _DiagBudgetExceeded(BaseException):
    """Raised by the watchdog timer.

    Deliberately a ``BaseException``: the solver's drive loop and plenty of
    library code catch ``Exception`` (and the trampoline narrows a
    ``RuntimeError`` whose ``__cause__`` is ``StopIteration`` into "exhausted"),
    so an ``Exception`` subclass could be swallowed and silently reported as
    "no solutions" — which is exactly the misdiagnosis we must not make.
    """


class _Unrenderable(Exception):
    """A computed value has no faithful ``.clausal`` surface form."""


#: Never absorbed by the diagnostic's catch-alls — the operator asked to stop.
_FATAL = (KeyboardInterrupt, SystemExit)


@contextlib.contextmanager
def _watchdog(seconds: float):
    """Interrupt the body after *seconds* with :class:`_DiagBudgetExceeded`.

    Falls back to a no-op where ``SIGALRM`` is unavailable (Windows) or we are
    not on the main thread (pytest-xdist workers, embedded use); the coarser
    between-steps deadline check still applies there.
    """
    usable = (
        seconds > 0
        and hasattr(signal, "setitimer")
        and hasattr(signal, "SIGALRM")
        and threading.current_thread() is threading.main_thread()
    )
    if not usable:
        yield False
        return

    def _fire(signum, frame):  # pragma: no cover - timing dependent
        raise _DiagBudgetExceeded()

    previous = signal.signal(signal.SIGALRM, _fire)
    signal.setitimer(signal.ITIMER_REAL, seconds)
    try:
        yield True
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous)


@dataclass
class GoalDiagnostic:
    """Why a test failed, at conjunct granularity.

    ``index`` is 1-based over ``total`` body conjuncts and is ``None`` when the
    walk could not attribute the failure at all.
    """

    index: int | None = None
    total: int = 0
    source: str | None = None
    line: int | None = None
    raised: str | None = None
    bindings: list[tuple[str, str]] = field(default_factory=list)
    bindings_note: str | None = None
    nearest: str | None = None
    nearest_note: str | None = None
    nearest_examples: list[str] = field(default_factory=list)
    descent: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def lines(self, indent: str = "    ") -> list[str]:
        """Render as report lines (no trailing newlines)."""
        out: list[str] = []
        if self.index is not None:
            verb = "raised" if self.raised else "failed"
            out.append(f"{indent}goal {self.index} of {self.total} {verb}:")
            if self.source:
                out.extend(_wrap_goal(self.source, indent + "  "))
            if self.raised:
                # An exception message may be several lines — a lookup failure
                # carries its candidate list this way.  Indent the
                # continuations so the block stays visibly attached to the
                # goal it belongs to instead of falling back to column 0.
                first, *rest = self.raised.splitlines() or [""]
                out.append(f"{indent}  {first}")
                out.extend(f"{indent}  {line}" for line in rest)
        if self.bindings:
            rendered = ", ".join(f"{n} = {v}" for n, v in self.bindings)
            out.append(f"{indent}bindings at failure: {rendered}")
        elif self.bindings_note:
            out.append(f"{indent}bindings at failure: {self.bindings_note}")
        if self.nearest_note:
            out.append(f"{indent}{self.nearest_note}")
        if self.nearest:
            out.extend(_wrap_goal(self.nearest, indent + "  "))
        for example in self.nearest_examples:
            out.extend(_wrap_goal(example, indent + "  "))
        for line in self.descent:
            out.append(f"{indent}  {line}")
        for note in self.notes:
            out.append(f"{indent}note: {note}")
        return out


@dataclass
class TestResult:
    name: str
    passed: bool
    error: Exception | None = None
    duration: float = 0.0
    line: int | None = None
    diagnostic: GoalDiagnostic | None = None


@dataclass
class FileResults:
    path: str
    results: list[TestResult] = field(default_factory=list)


def load_clausal_module(path: str | Path) -> object:
    """Load a .clausal file as a Python module and return it."""
    # Ensure import hook is installed.
    import clausal.import_hook  # noqa: F401

    from clausal.import_hook import _load_module

    path = str(path)
    mod_name = f"_clausal_test_{os.path.basename(path).removesuffix('.clausal')}"

    # _load_module handles sys.modules eviction internally.
    old = sys.modules.get(mod_name)
    try:
        mod = _load_module(mod_name, path)
    finally:
        # Avoid polluting sys.modules across test runs.
        if old is None:
            sys.modules.pop(mod_name, None)
        else:
            sys.modules[mod_name] = old
    return mod


def collect_tests(mod: object) -> list[str]:
    """Return the list of test/1 clause descriptions from a loaded module."""
    logic_module = mod.__dict__.get("$module")
    if logic_module is None:
        return []
    clauses = logic_module.db.clauses_for("Test", 1)
    descriptions = []
    for clause in clauses:
        head = clause.head
        # Head is a PredicateMeta instance or Compound with 1 arg (the description).
        if hasattr(head, "args"):
            desc = head.args[0]
        else:
            from clausal.logic.predicate import term_field_names
            names = term_field_names(head)
            desc = getattr(head, names[0]) if names else str(head)
        # Description might be a string or a ground value.
        descriptions.append(str(desc))
    return descriptions


def run_test(
    mod: object,
    description: str,
    *,
    path: str | Path | None = None,
    diagnose: bool = False,
) -> TestResult:
    """Run a single test/1 clause by description. Returns a TestResult.

    ``diagnose`` is opt-in — both runners (``run_file`` and the pytest
    plugin's ``ClausalItem``) enable it, but an embedder calling ``run_test``
    directly gets no diagnostic re-run, which re-executes body goals and any
    side effects they carry, unless it asks for one.
    """
    from clausal.logic.solve import call

    logic_module = mod.__dict__["$module"]
    t0 = time.perf_counter()
    try:
        solutions = list(call("Test", description, module=logic_module))
        passed = len(solutions) > 0
        result = TestResult(name=description, passed=passed,
                            duration=time.perf_counter() - t0)
    except Exception as e:
        result = TestResult(name=description, passed=False, error=e,
                            duration=time.perf_counter() - t0)

    # Observation only, and only on failure.  ``passed`` is already decided.
    if diagnose and not result.passed:
        result.diagnostic = diagnose_failure(mod, description, path=path,
                                             error=result.error)
        result.line = result.diagnostic.line
    return result


def run_file(path: str | Path) -> FileResults:
    """Load a .clausal file and run all its test/1 clauses."""
    path = str(path)
    results = FileResults(path=path)
    try:
        mod = load_clausal_module(path)
    except Exception as e:
        results.results.append(TestResult(name="<load>", passed=False, error=e))
        return results
    for desc in collect_tests(mod):
        results.results.append(run_test(mod, desc, path=path, diagnose=True))
    return results


# ── Failure diagnostics ───────────────────────────────────────────────────────


def diagnose_failure(
    mod: object,
    description: str,
    path: str | Path | None = None,
    error: BaseException | None = None,
) -> GoalDiagnostic:
    """Explain *why* a already-failed ``Test(description)`` clause failed.

    Locates the clause, walks its body conjuncts and re-executes cumulative
    prefixes until one yields no solution (or raises); that conjunct is the
    culprit.  Then reports the bindings live at that point and, for a
    predicate call, the solution the predicate *did* have.

    Never raises, and never reports a verdict — the caller has already decided
    pass/fail.  Every failure mode inside becomes a note on the returned
    diagnostic.

    Side-effect exposure
    --------------------
    The re-run executes real goals, so ``assertz``/``retract``, file and
    network I/O in a test body **run again** — and the cumulative-prefix walk
    executes conjunct *i* once per prefix that contains it, so an ``assertz``
    in goal 1 of an n-conjunct test can be applied up to n extra times.  Two
    partial mitigations are applied here:

    * ``stdout``/``stderr`` are captured and discarded, so ``write/1`` noise
      cannot corrupt the report that a gate parses.
    * the module database's clause count is compared before and after; a
      change is reported as a note rather than silently absorbed.

    There is no transactional rollback for a logic database, so an
    ``assertz``-ing test genuinely does re-apply.  That is the documented
    price of the diagnostic; it is paid only on an already-failing test.
    """
    # Error path only: the py-interop package is heavy to import, and most
    # failing tests never touch it — but its guards are the only place that
    # knows WHY an interop goal failed (int where timedelta is required, …),
    # so collect their rejection notes for the whole re-run.  A failed
    # import degrades to no collection: this function promises never to
    # raise, and the notes are an enrichment, not the diagnosis.
    try:
        from clausal.modules.py import collect_type_mismatch_notes
    except Exception:  # noqa: BLE001 - never-raise contract
        def collect_type_mismatch_notes():
            return contextlib.nullcontext([])

    diag = GoalDiagnostic()
    logic_module = mod.__dict__.get("$module") if hasattr(mod, "__dict__") else None
    before = _clause_count(logic_module)
    budget = _diag_budget()
    type_notes: list[str] = []
    try:
        with _watchdog(budget):
            sink = io.StringIO()
            with contextlib.redirect_stdout(sink), contextlib.redirect_stderr(sink):
                with collect_type_mismatch_notes() as type_notes:
                    _diagnose_into(diag, mod, description, path, error, budget)
    except _DiagBudgetExceeded:
        diag.notes.append(
            f"diagnostic re-run exceeded its {budget:g}s budget — "
            "analysis above may be incomplete "
            f"(raise ${DIAG_BUDGET_ENV} to allow more)"
        )
    except RecursionError:
        diag.notes.append(
            "diagnostic re-run hit the Python recursion limit — "
            "the test body is probably non-terminating"
        )
    except _FATAL:
        raise
    except BaseException as exc:  # noqa: BLE001 - diagnostics must never escape
        diag.notes.append(f"diagnostic unavailable: {type(exc).__name__}: {exc}")

    # Guard rejections recorded during the re-run (deduplicated in order).
    # The list object survives the context manager, and holds whatever was
    # collected even when the re-run died on the budget or an exception.
    diag.notes.extend(type_notes)

    after = _clause_count(logic_module)
    if before is not None and after is not None and after != before:
        diag.notes.append(
            f"the diagnostic re-run changed the database "
            f"({after - before:+d} clause(s)) — this test has side effects"
        )
    return diag


def _clause_count(logic_module) -> int | None:
    try:
        store = logic_module.db._clauses
        return sum(len(v) for v in store.values())
    except Exception:  # noqa: BLE001
        return None


def _diagnose_into(diag, mod, description, path, error, budget) -> None:
    """Fill *diag*.  Split out so tests can force the degradation path."""
    from clausal.logic.variables import Trail

    logic_module = mod.__dict__["$module"]
    clause = _test_clause(logic_module, description)
    if clause is None:
        diag.notes.append("could not locate the Test/1 clause to analyse")
        return
    if clause.position:
        diag.line = clause.position[0]

    body = list(clause.body or ())
    diag.total = len(body)
    if not body:
        diag.notes.append("the test body is empty")
        return
    walked = body
    if len(body) > DIAG_MAX_GOALS:
        walked = body[:DIAG_MAX_GOALS]
        diag.notes.append(
            f"only the first {DIAG_MAX_GOALS} of {len(body)} conjuncts were walked"
        )

    reified = _reified_goals(path, clause, len(body))
    sources = _goal_sources(body, reified)

    deadline = time.monotonic() + budget

    # 1. Which conjunct is the culprit?  Cumulative prefixes, first one that
    #    yields nothing (or raises) is it.
    failing, raised = _first_failing(walked, logic_module, deadline)
    if raised is not None:
        diag.index, diag.raised = failing, raised
        diag.source = sources[failing - 1]
        return

    if failing is None:
        # The re-run disagrees with the verdict.  Report that honestly rather
        # than inventing a culprit — do NOT touch the verdict.
        if error is not None:
            diag.notes.append(
                "the test raised, but the diagnostic re-run of its conjuncts "
                "did not reproduce the error"
            )
        else:
            diag.notes.append(
                "the diagnostic re-run found a solution for every conjunct — "
                "the failure is not attributable to a single goal "
                "(non-determinism, or state changed by the first run)"
            )
        return

    diag.index = failing
    diag.source = sources[failing - 1]

    # 2 & 3.  Re-establish the prefix, then read bindings and probe the goal
    #         with the prefix's bindings live.
    prefix = walked[:failing - 1]
    goal = walked[failing - 1]
    reified_goal = reified[failing - 1] if reified else None
    trail = Trail()
    try:
        if prefix:
            gen = _solutions(_conjunction(prefix), logic_module, trail)
            try:
                if next(gen, None) is None:
                    diag.notes.append(
                        "prefix goals became unsatisfiable on re-run; "
                        "bindings and nearest-solution analysis skipped"
                    )
                    return
                _report_bindings(
                    diag, prefix,
                    _collect_named(prefix, reified and reified[:failing - 1]),
                    failing,
                )
                _report_nearest(diag, goal, reified_goal, logic_module, deadline, path)
                _report_wrong_value(
                    diag, goal, prefix, logic_module, deadline, path)
            finally:
                gen.close()
        else:
            diag.bindings_note = "(none — goal 1 is the first goal)"
            _report_nearest(diag, goal, reified_goal, logic_module, deadline, path)
    finally:
        _undo(trail)


# ── Locating the clause and its source text ──────────────────────────────────


def _test_clause(logic_module, description):
    from clausal.logic.predicate import term_field_names

    for clause in logic_module.db.clauses_for("Test", 1):
        head = clause.head
        if hasattr(head, "args"):
            desc = head.args[0]
        else:
            names = term_field_names(head)
            desc = getattr(head, names[0]) if names else None
        if str(desc) == description:
            return clause
    return None


#: Reifying a file is the same work for every failing test in it, so cache —
#: but a whole-tree run must not accumulate every source file it touched.
_REIFY_CACHE: dict[str, object] = {}
_REIFY_CACHE_MAX = 16


def _reified_clause(path, clause):
    """The reified ``Clause(head, goals, position)`` matching *clause*'s
    position, or ``None``.  Cache shared with :func:`_reified_goals`."""
    if path is None or not clause.position:
        return None
    try:
        from clausal.reflection import Clause as ReifiedClause, reify_file

        key = str(path)
        items = _REIFY_CACHE.get(key)
        if items is None:
            items = list(reify_file(key))
            if len(_REIFY_CACHE) >= _REIFY_CACHE_MAX:
                _REIFY_CACHE.pop(next(iter(_REIFY_CACHE)), None)
            _REIFY_CACHE[key] = items
        want = tuple(clause.position)
        for item in items:
            if not isinstance(item, ReifiedClause):
                continue
            pos = getattr(item, "position", None)
            if pos is not None and tuple(pos) == want:
                return item
    except Exception:  # noqa: BLE001 - source text is a nicety, never fatal
        return None
    return None


def _reified_goals(path, clause, arity):
    """The reified (source-faithful) conjuncts of *clause*, or ``None``.

    Matching is by source position, so a mis-association is impossible; a
    conjunct-count mismatch (a body shape whose runtime form does not
    correspond 1:1 with its source conjuncts) declines rather than guesses.
    """
    item = _reified_clause(path, clause)
    if item is None:
        return None
    try:
        goals = list(item.goals or ())
    except Exception:  # noqa: BLE001
        return None
    return goals if len(goals) == arity else None


def _goal_sources(body, reified) -> list[str]:
    """Source text per conjunct, falling back to the runtime term's own str."""
    from clausal.terms import term_str

    out = []
    for i, goal in enumerate(body):
        text = None
        if reified is not None:
            try:
                from clausal.reflection import render_source

                text = render_source(reified[i])
            except Exception:  # noqa: BLE001
                text = None
        if text is None:
            try:
                text = term_str(goal)
            except Exception:  # noqa: BLE001
                text = str(goal)
        out.append(text)
    return out


# ── Executing conjuncts ──────────────────────────────────────────────────────


def _conjunction(goals):
    from clausal.terms import And

    node = goals[0]
    for extra in goals[1:]:
        node = And(left=node, right=extra)
    return node


def _solutions(goal, logic_module, trail):
    from clausal.logic.solve import solve

    return solve(goal, logic_module, trail=trail)


def _has_solution(goal, logic_module, trail) -> bool:
    gen = _solutions(goal, logic_module, trail)
    try:
        return next(gen, None) is not None
    finally:
        gen.close()


def _first_failing(goals, logic_module, deadline, prefix=()):
    """1-based index of the first conjunct whose cumulative prefix yields no
    solution, paired with ``None`` — or with the rendered exception if that
    prefix raised instead.  ``(None, None)`` when every prefix is satisfiable.

    *prefix* goals are prepended to every probe but never blamed: indices are
    relative to *goals*.
    """
    from clausal.logic.variables import Trail

    pre = list(prefix)
    for k in range(1, len(goals) + 1):
        if time.monotonic() > deadline:
            raise _DiagBudgetExceeded()
        trail = Trail()
        try:
            ok = _has_solution(_conjunction(pre + goals[:k]), logic_module, trail)
        except (_DiagBudgetExceeded, RecursionError, *_FATAL):
            raise
        except BaseException as exc:  # noqa: BLE001
            return k, f"{type(exc).__name__}: {exc}"
        finally:
            _undo(trail)
        if not ok:
            return k, None
    return None, None


def _undo(trail) -> None:
    """Return the shared clause-body Vars to their pre-diagnostic state.

    ``solve`` unwinds its own trail on exhaustion, but a probe abandoned mid
    solution (we only ever take the first) would otherwise leave bindings on
    Var objects that the clause body owns and the next probe reuses.
    """
    try:
        trail.undo(0)
    except Exception:  # noqa: BLE001
        pass


# ── Stage 2: bindings ────────────────────────────────────────────────────────


def _collect_named(goals, reified) -> list[tuple[str, object]] | None:
    """``(source name, runtime Var)`` for every variable in *goals*, or None."""
    if reified is None:
        return None
    named: list[tuple[str, object]] = []
    for goal, twin in zip(goals, reified):
        if not _pair_vars(goal, twin, named):
            return None
    return named


def _report_bindings(diag, prefix, named, failing) -> None:
    from clausal.logic.variables import deref, is_var

    if named is None:
        diag.bindings_note = (
            "(unavailable — could not recover source variable names for "
            f"goals 1..{failing - 1})"
        )
        return
    seen: set[int] = set()
    for name, var in named:
        if id(var) in seen:
            continue
        seen.add(id(var))
        value = deref(var)
        if is_var(value):
            continue
        diag.bindings.append((name, _render_value(value)))
    if not diag.bindings:
        span = "goal 1" if failing == 2 else f"goals 1..{failing - 1}"
        diag.bindings_note = f"(none from {span})"


def _pair_vars(runtime, reified, out) -> bool:
    """Walk a runtime goal term and its reified twin in lockstep.

    Collects ``(source name, runtime Var)`` pairs.  Returns False the moment
    the two shapes disagree — an unnamed binding is worse than none.
    """
    from clausal.logic.variables import Var
    from clausal.reflection import Atom, Goal, Variable
    from clausal.terms import Call, LoadName

    if isinstance(reified, Variable):
        # ``isinstance``, not ``is_var``: the latter derefs, so a Var already
        # bound by the prefix would read as "not a variable" and abort the walk.
        if isinstance(runtime, Var):
            out.append((str(reified.name), runtime))
            return True
        return False
    if isinstance(reified, Goal):
        if not isinstance(runtime, Call):
            return False
        func = runtime.func
        if isinstance(func, LoadName) and str(func.name) != str(reified.name):
            return False
        args = list(runtime.args or ())
        rargs = list(reified.args or ())
        if len(args) != len(rargs):
            return False
        if not all(_pair_vars(a, r, out) for a, r in zip(args, rargs)):
            return False
        kws = list(runtime.kwargs or ())
        rkws = list(reified.kwargs or ())
        if len(kws) != len(rkws):
            return False
        return all(_pair_vars(k.value, r[1], out) for k, r in zip(kws, rkws))
    if isinstance(reified, Atom):
        return True
    if isinstance(reified, list):
        if not isinstance(runtime, list) or len(runtime) != len(reified):
            return False
        return all(_pair_vars(a, r, out) for a, r in zip(runtime, reified))
    if isinstance(reified, (str, bytes, bool, int, float, complex)) or reified is None:
        return True
    # Operator nodes (Gt, Not, Is, …) — same class on both sides, same fields.
    fields = getattr(type(reified), "__dataclass_fields__", None)
    if fields is not None and type(runtime) is type(reified):
        return all(
            _pair_vars(getattr(runtime, f, None), getattr(reified, f, None), out)
            for f in fields
            if f != "position"
        )
    return False


# ── Stage 3: nearest solution ────────────────────────────────────────────────


def _forall_shape(goal):
    """``(loop_var, elements, body)`` if *goal* is ``forall(V in LIST, Body)``.

    Matches the exact runtime shape a ``forall/2`` over a list literal lowers
    to: ``Call(forall, [in_(left=Var, right=[...]), Body])`` where LIST is a
    ground Python list.  Returns ``None`` for any other ``forall`` (a generated
    generator, a non-list right side, a bound loop variable), so those keep the
    generic ladder.
    """
    from clausal.logic.variables import deref, is_var
    from clausal.pythonic_ast.nodes import in_
    from clausal.terms import Call, LoadName

    if not isinstance(goal, Call):
        return None
    func = goal.func
    if not (isinstance(func, LoadName) and str(func.name) == "forall"):
        return None
    args = list(goal.args or ())
    if len(args) != 2 or goal.kwargs:
        return None
    cond, body = args
    if not isinstance(cond, in_):
        return None
    loop_var = cond.left
    if not is_var(loop_var):
        return None
    elements = deref(cond.right)
    if not isinstance(elements, list):
        return None
    return loop_var, elements, body


def _forall_var_name(reified_goal) -> str | None:
    """Source name of the loop variable, from the reified ``forall`` twin."""
    from clausal.pythonic_ast.nodes import in_
    from clausal.reflection import Goal, Variable

    if not isinstance(reified_goal, Goal) or str(reified_goal.name) != "forall":
        return None
    rargs = list(reified_goal.args or ())
    if not rargs or not isinstance(rargs[0], in_):
        return None
    left = rargs[0].left
    return str(left.name) if isinstance(left, Variable) else None


def _report_forall(diag, goal, reified_goal, logic_module, deadline) -> bool:
    """Name the LIST element(s) for which a ``forall`` body has no solution.

    Candidate 1 of ``todo/forall-failure-names-no-failing-binding``: a
    diagnostic-only re-run.  For each element of LIST (bounded the same way the
    descent is — ``DIAG_MAX_DESCENT_LEAVES`` findings, ``$CLAUSAL_TEST_DIAG_BUDGET``
    deadline), bind the loop variable to the element and test whether Body has a
    solution; report the elements for which it does not, by name.  Does not
    touch ``forall``'s semantics or the verdict.  Returns True once it has set a
    report (so the caller stops), False to fall through to the generic ladder.
    """
    from clausal.logic.variables import Trail
    from clausal.pythonic_ast.nodes import Unify

    shape = _forall_shape(goal)
    if shape is None:
        return False
    loop_var, elements, body = shape
    if not elements:
        return False
    name = _forall_var_name(reified_goal) or "the loop variable"

    total = len(elements)
    failing: list[str] = []
    truncated = False
    for element in elements:
        if time.monotonic() > deadline:
            raise _DiagBudgetExceeded()
        if len(failing) >= DIAG_MAX_DESCENT_LEAVES:
            # A later element might also fail; we no longer need its identity,
            # only to know the count is not exhaustive.  Stop probing (each
            # probe re-solves Body) and note the bound.
            truncated = True
            break
        trail = Trail()
        try:
            probe = _conjunction([Unify(left=loop_var, right=element), body])
            has = _has_solution(probe, logic_module, trail)
        except (_DiagBudgetExceeded, RecursionError, *_FATAL):
            raise
        except BaseException:  # noqa: BLE001 - a probe that errors is just no answer
            has = False
        finally:
            _undo(trail)
        if not has:
            failing.append(f"{name} = {_render_value(element)}")

    if not failing:
        # The re-run found a solution for every element — the failure is not
        # attributable to a single element (non-determinism, or a body that
        # couples elements).  Fall through rather than invent a culprit.
        return False

    shown = len(failing)
    if truncated:
        diag.nearest_note = (
            f"failed for at least {shown} of {total} elements "
            f"(first {DIAG_MAX_DESCENT_LEAVES} shown):"
        )
        diag.notes.append(
            f"more than {DIAG_MAX_DESCENT_LEAVES} of the {total} elements "
            "failed; only the first are named"
        )
    else:
        diag.nearest_note = f"failed for {shown} of {total} elements:"
    diag.descent = failing
    return True


def _report_nearest(diag, goal, reified_goal, logic_module, deadline, path) -> None:
    """Show the solution the failing predicate DID have, if it had one.

    Re-runs the goal with one over-constrained argument replaced by a fresh
    variable — the same single-site generalisation ``replace_subterm/4``
    performs on reified terms, applied here at the argument positions of the
    live goal (its arguments are unevaluated ``simple_ast`` nodes, which the
    reified-domain walker treats as leaves).  Generalising a whole argument is
    strictly more general than generalising anything inside it, so if the
    whole-argument probe finds nothing, no deeper probe can.
    """
    from clausal.logic.variables import Trail, Var
    from clausal.pythonic_ast.nodes import Keyword
    from clausal.terms import Call

    if not isinstance(goal, Call):
        diag.nearest_note = (
            "no solution (this conjunct is not a predicate call, so there is "
            "no nearest solution to show)"
        )
        return

    # ``forall(X in LIST, Body)`` reaches here as a Call to a "predicate"
    # named ``forall`` that has no clauses: the generic slot/all-holes/descent
    # ladder below can only report the bare rung-3 non-answer, because it does
    # not know LIST's elements are the thing to blame.  Intercept and name the
    # element(s) for which Body has no solution instead.
    if _report_forall(diag, goal, reified_goal, logic_module, deadline):
        return

    args = list(goal.args or ())
    kwargs = list(goal.kwargs or ())
    if not args and not kwargs:
        diag.nearest_note = "the predicate has no solution (it takes no arguments)"
        return

    slots: list[tuple[str, int]] = (
        [("arg", i) for i in range(len(args))]
        + [("kw", i) for i in range(len(kwargs))]
    )

    def slot_label(kind, i) -> str:
        return (
            f"argument {i + 1}" if kind == "arg"
            else f"keyword argument {kwargs[i].name!r}"
        )

    def render_rung1(kind, i, value) -> str | None:
        """Set the rung-1 note and near-miss; RETURN the arith note unappended.

        The caller appends it only once this rendering is known to be final —
        a degenerate rendering may be replaced by a later concrete slot or by
        descent findings, and the note must not outlive the near-miss it
        describes.
        """
        label = slot_label(kind, i)
        diag.nearest_note = (
            f"the predicate DID have a solution, which did not unify "
            f"({label} differs):"
        )
        diag.nearest = _render_nearest(goal, reified_goal, kind, i, value)
        wanted = args[i] if kind == "arg" else kwargs[i].value
        return _arith_vs_number_note(label, wanted, value)

    degenerate: tuple[str, int, str | None] | None = None
    for kind, i in slots:
        if time.monotonic() > deadline:
            raise _DiagBudgetExceeded()
        hole = Var()
        if kind == "arg":
            probe = Call(func=goal.func,
                         args=args[:i] + [hole] + args[i + 1:],
                         kwargs=kwargs)
        else:
            kw = kwargs[i]
            probe = Call(func=goal.func, args=args,
                         kwargs=kwargs[:i]
                         + [Keyword(name=kw.name, value=hole)]
                         + kwargs[i + 1:])
        value = _first_binding(probe, hole, logic_module)
        if value is _NO_SOLUTION:
            continue
        if not _value_is_concrete(value):
            # The probe only matched a clause-head pattern or a deferred
            # constraint: the freed argument came back with unbound holes in
            # it, so this near-miss says nothing about why the concrete
            # argument was rejected (todo D).  Render it NOW — a budget blow
            # in a later probe or in the descent below must still leave a
            # near-miss in the report — then keep scanning for a slot with a
            # concrete near-miss, which overwrites this rendering.
            if degenerate is None:
                held_note = render_rung1(kind, i, value)
                degenerate = (kind, i, held_note)
            continue
        note = render_rung1(kind, i, value)
        if note:
            diag.notes.append(note)
        return

    if degenerate is not None:
        # Every solvable slot solved only with its hole left (partly) unbound.
        # The weak rung-1 line is already rendered; descent findings replace
        # it, and its held-back arith note only lands if they don't.
        kind, i, held_note = degenerate
        label = slot_label(kind, i)
        if _report_descent(
                diag, goal, logic_module, deadline, path,
                intro=(f"the predicate has solutions with {label} freed, but "
                       f"none binds {label} to a concrete value")):
            diag.nearest = None
        elif held_note:
            diag.notes.append(held_note)
        return

    # No single argument explains it — is the predicate satisfiable at all?
    holes = [Var() for _ in args]
    kw_holes = [Keyword(name=k.name, value=Var()) for k in kwargs]
    probe = Call(func=goal.func, args=holes, kwargs=kw_holes)
    examples: list[str] = []
    any_concrete = False
    trail = Trail()
    gen = None
    try:
        gen = _solutions(probe, logic_module, trail)
        for _ in range(3):
            if next(gen, None) is None:
                break
            if not any_concrete and _value_is_concrete(
                    [*holes, *(k.value for k in kw_holes)]):
                any_concrete = True
            rendered = _render_probe_solution(goal, reified_goal, holes, kw_holes)
            if rendered not in examples:
                examples.append(rendered)
    except (_DiagBudgetExceeded, RecursionError, *_FATAL):
        raise
    except BaseException:  # noqa: BLE001 - a probe that errors is just no answer
        # A raise here keeps whatever solutions were already collected: if some
        # examples exist the predicate demonstrably HAS solutions, so rung-2
        # ("has solutions, but none within one argument") stays the truthful
        # classification; a raise before the first solution leaves examples
        # empty — equivalent to the old satisfiable=False (fall through to the
        # rung-3 descent below).
        pass
    finally:
        if gen is not None:
            gen.close()
        _undo(trail)
    if examples:
        diag.nearest_note = (
            "the predicate has solutions, but none within one argument of "
            "this goal — two or more arguments differ; it does have:"
        )
        diag.nearest_examples = examples
        if not any_concrete:
            # Every example left holes unbound (e.g. a var-coupled fact
            # matching the bare-holes probe) — as anonymised renders they say
            # nothing (todo D).  The weak rendering above survives a budget
            # blow inside the descent; findings replace it.
            if _report_descent(
                    diag, goal, logic_module, deadline, path,
                    intro=("the predicate has solutions, but none binds "
                           "every argument to a concrete value")):
                diag.nearest_examples = []
    else:
        diag.nearest_note = (
            "the predicate has no solution for ANY arguments at this point "
            "(check the goals that produced its inputs, or its own clauses)"
        )
        _report_descent(diag, goal, logic_module, deadline, path)


def _report_wrong_value(diag, goal, prefix, logic_module, deadline, path) -> None:
    """Blame a wrong VALUE feeding a failing comparison/unification conjunct.

    ``_report_nearest`` only descends when the failing conjunct is itself a
    predicate ``Call``.  The measured incident class fails at a downstream
    comparison (``MAX == 90``) whose operand was produced — with the wrong value
    — by an EARLIER prefix conjunct that succeeded.  When that producer is a
    predicate call, descend into it (reusing the ordinary clause-body descent,
    which now includes the findall-collapse sentinel) so the real defect a level
    or two down is named instead of just the top-level mismatch.

    Runs only when ``goal`` is not a ``Call`` and the ordinary descent added
    nothing; on findings it appends to ``diag.descent`` under a headline, leaving
    the already-rendered comparison note in place."""
    from clausal.terms import Call

    if isinstance(goal, Call):
        return
    if diag.descent or diag.nearest_examples:
        return  # ordinary descent already spoke; don't pile on
    producer = _wrong_value_producer(goal, prefix)
    if producer is None:
        return
    notes: list[str] = []
    leaves, kind = _descend(
        producer, logic_module, path, deadline, 1, frozenset(), notes)
    if kind != "leaves" or not leaves:
        # Nothing attributable.  But if the scan was cut short by its depth
        # bound, silence would misread as "nothing deeper to find" — surface
        # the stop note (and only it), mirroring the budget-exceeded note.
        diag.notes.extend(
            n for n in notes
            if n.startswith("the wrong-value descent stopped"))
        return
    leaves = _cap_leaves(leaves, notes)
    name = _goal_name(producer) or "an earlier goal"
    diag.descent = [
        f"the value it compares was produced by {name}, which succeeded with a "
        "wrong value; that producer's failing route:"
    ]
    diag.descent += [line for group in leaves for line in group]
    diag.notes.extend(notes)


def _wrong_value_producer(goal, prefix):
    """The earliest prefix ``Call`` sharing a runtime Var with *goal*, or None.

    The comparison ``MAX == 90`` and the producer ``max_additional_days(MAX)``
    share the SAME runtime ``Var`` object for ``MAX`` (clause-body variables are
    shared), so matching by identity ties the mismatch to the goal that computed
    it — no name reconstruction needed."""
    from clausal.terms import Call

    wanted = set()
    _collect_var_ids(goal, wanted)
    if not wanted:
        return None
    for conjunct in prefix:
        if not isinstance(conjunct, Call):
            continue
        here: set[int] = set()
        _collect_var_ids(conjunct, here)
        if here & wanted:
            return conjunct
    return None


def _collect_var_ids(term, out: set[int]) -> None:
    """``id()`` of every runtime ``Var`` object reachable in *term*.

    Deliberately does NOT deref: by the time the wrong-value bridge runs the
    prefix has been re-established, so the shared clause-body Var may already
    carry the (wrong) value.  Its OBJECT IDENTITY still ties the comparison to
    the producer that computed it — the whole point of the match — so we key on
    the raw ``Var`` instance, bound or not."""
    from clausal.logic.variables import Var

    if isinstance(term, Var):
        out.add(id(term))
        return
    args = getattr(term, "args", None)
    if args:
        for a in args:
            _collect_var_ids(a, out)
    kwargs = getattr(term, "kwargs", None)
    if kwargs:
        for kw in kwargs:
            _collect_var_ids(getattr(kw, "value", kw), out)
    fields = getattr(type(term), "__dataclass_fields__", None)
    if fields is not None and args is None:
        for f in fields:
            if f != "position":
                _collect_var_ids(getattr(term, f, None), out)
    if isinstance(term, (list, tuple)):
        for e in term:
            _collect_var_ids(e, out)


def _goal_name(goal) -> str | None:
    from clausal.terms import LoadName

    func = getattr(goal, "func", None)
    if isinstance(func, LoadName):
        return f"{func.name}(...)"
    return None


def _cap_leaves(leaves, notes):
    """Trim descent finding-GROUPS to ``DIAG_MAX_DESCENT_LEAVES``, noting the cut.

    The cap counts findings (groups) across the whole descent including fan-out,
    so a finding and its binding sub-lines are shown or dropped as a unit — never
    split.  Shared by the rung-3 descent and the wrong-value bridge."""
    if len(leaves) > DIAG_MAX_DESCENT_LEAVES:
        notes.append(
            f"only the first {DIAG_MAX_DESCENT_LEAVES} of {len(leaves)} "
            f"descent findings are shown"
        )
        leaves = leaves[:DIAG_MAX_DESCENT_LEAVES]
    return leaves


_NO_SOLUTION = object()


def _value_is_concrete(value) -> bool:
    """No unbound holes anywhere in *value* — the probe solution carries a value.

    Groundness via the canonical helper; any doubt (an exotic node it cannot
    walk, an error) counts as concrete, keeping the pre-existing rung-1/2
    rendering.
    """
    try:
        from clausal.logic.builtins._helpers import _is_ground

        return bool(_is_ground(value))
    except Exception:  # noqa: BLE001 - doubt → keep today's rendering
        return True


def _arith_vs_number_note(label: str, wanted, actual) -> str | None:
    """The is/== note when this argument pairs an arith term with a number.

    Both sides are already in hand here — *wanted* is the over-constrained
    argument of the live goal, *actual* what the predicate computed for it — so
    the check is two isinstance tests on a path only a failing test reaches.

    Requiring a *number* opposite the operator term is what keeps the note off
    legitimate code: a clause that builds ``DA + DB`` to unify against another
    operator term of the same shape (``BinOp.__unify__`` supports exactly that)
    never has a number on the other side, so it is never named here.  Either
    direction fires: the term may be what the predicate returned, or what the
    caller wrote into the goal.
    """
    from clausal.logic.exceptions import (
        IS_VS_EQ_HINT,
        is_arith_operator_term,
        render_arith_operator_term,
    )
    from clausal.logic.variables import deref

    wanted, actual = deref(wanted), deref(actual)
    for term, number in ((wanted, actual), (actual, wanted)):
        if is_arith_operator_term(term) and _is_number(number):
            return (f"{label} pairs an unevaluated arithmetic term "
                    f"(`{render_arith_operator_term(term)}`) with a number. "
                    f"{IS_VS_EQ_HINT}")
    return None


def _is_number(value) -> bool:
    """A number for is/== purposes.  ``bool`` is excluded: ``True`` is not 1 here."""
    import numbers

    return isinstance(value, numbers.Number) and not isinstance(value, bool)


def _first_binding(probe, hole, logic_module):
    """Value bound to *hole* by the first solution of *probe*, or the sentinel."""
    from clausal.logic.solve import _deref_walk_py
    from clausal.logic.variables import Trail

    trail = Trail()
    gen = _solutions(probe, logic_module, trail)
    try:
        if next(gen, None) is None:
            return _NO_SOLUTION
        return _deref_walk_py(hole)
    except (_DiagBudgetExceeded, RecursionError, *_FATAL):
        raise
    except BaseException:  # noqa: BLE001 - a probe that errors is just no answer
        return _NO_SOLUTION
    finally:
        gen.close()
        _undo(trail)


def _render_probe_solution(goal, reified_goal, holes, kw_holes) -> str:
    """One all-holes solution as surface text, holes replaced by their values."""
    from clausal.logic.solve import _deref_walk_py
    from clausal.reflection import Goal, render_source

    values = [_deref_walk_py(h) for h in holes]
    kw_values = [(str(k.name), _deref_walk_py(k.value)) for k in kw_holes]
    if isinstance(reified_goal, Goal):
        try:
            return render_source(Goal(
                name=reified_goal.name,
                args=[_reify_value(v) for v in values],
                kwargs=[[n, _reify_value(v)] for n, v in kw_values],
            ))
        except Exception:  # noqa: BLE001
            pass
    func = getattr(goal, "func", None)
    name = str(func.name) if hasattr(func, "name") else "the predicate"
    parts = [_render_value(v) for v in values]
    parts += [f"{n}={_render_value(v)}" for n, v in kw_values]
    return f"{name}({', '.join(parts)})"


def _render_nearest(goal, reified_goal, kind, index, value) -> str:
    """The failing goal with the differing argument replaced by what was computed.

    Preferred form splices the computed value into the *reified* goal and hands
    the result to ``clausal.reflection.render_source``, so the output is real
    ``.clausal`` surface syntax.  Without a reified twin we fall back to naming
    the argument and its value.
    """
    from clausal.reflection import Goal, render_source

    if isinstance(reified_goal, Goal):
        try:
            reified_value = _reify_value(value)
            # Show the goal's *other* variables at the values the prefix gave
            # them, so the printed near-miss is a concrete term the reader can
            # diff against the assertion rather than a half-open pattern.
            bound = _bound_reified(goal, reified_goal)
            args = [_substitute_bound(a, bound)
                    for a in (reified_goal.args or ())]
            kwargs = [[k[0], _substitute_bound(k[1], bound)]
                      for k in (reified_goal.kwargs or ())]
            if kind == "arg" and index < len(args):
                args[index] = reified_value
            elif kind == "kw" and index < len(kwargs):
                kwargs[index][1] = reified_value
            else:
                raise _Unrenderable("argument index out of range")
            return render_source(Goal(name=reified_goal.name, args=args,
                                      kwargs=kwargs))
        except Exception:  # noqa: BLE001
            pass
    label = f"argument {index + 1}" if kind == "arg" else "keyword argument"
    return f"({label} was actually: {_render_value(value)})"


def _bound_reified(goal, reified_goal) -> dict[str, object]:
    """Source-variable name → reified form of its current binding."""
    from clausal.logic.variables import deref, is_var

    named = _collect_named([goal], [reified_goal])
    bound: dict[str, object] = {}
    for name, var in named or ():
        value = deref(var)
        if is_var(value):
            continue
        try:
            bound[name] = _reify_value(value)
        except Exception:  # noqa: BLE001
            pass
    return bound


def _substitute_bound(reified, bound):
    """Replace ``Variable(name)`` by ``bound[name]`` throughout a reified term."""
    from clausal.reflection import Goal, Variable

    if not bound:
        return reified
    if isinstance(reified, Variable):
        return bound.get(str(reified.name), reified)
    if isinstance(reified, Goal):
        return Goal(
            name=reified.name,
            args=[_substitute_bound(a, bound) for a in (reified.args or ())],
            kwargs=[[k[0], _substitute_bound(k[1], bound)]
                    for k in (reified.kwargs or ())],
        )
    if isinstance(reified, list):
        return [_substitute_bound(v, bound) for v in reified]
    return reified


def _render_value(value) -> str:
    """A computed runtime value as ``.clausal`` surface text."""
    try:
        from clausal.reflection import render_source

        return render_source(_reify_value(value))
    except Exception:  # noqa: BLE001
        from clausal.terms import term_str

        try:
            return term_str(value)
        except Exception:  # noqa: BLE001
            return repr(value)


def _reify_value(value, depth: int = 0):
    """Runtime term → reified vocabulary, so ``render_source`` can print it.

    ``reify_*`` maps *source* to reified terms; a value computed at run time
    has no source, so this is the missing edge.  Anything outside the closed
    vocabulary raises rather than emitting something that does not mean what
    it says.
    """
    from clausal.logic.predicate import (
        PredicateMeta, is_term_instance, term_field_names,
    )
    from clausal.logic.variables import deref, is_var
    from clausal.reflection import Atom, Goal, Variable
    from clausal.terms import Compound, KWTerm

    if depth > DIAG_MAX_DEPTH:
        raise _Unrenderable("term too deep to render")
    value = deref(value)
    if is_var(value):
        return Variable(name="_")
    if value is None or isinstance(value, (bool, int, float, complex, str, bytes)):
        return value
    if isinstance(value, list):
        return [_reify_value(v, depth + 1) for v in value]
    if isinstance(value, tuple):
        return tuple(_reify_value(v, depth + 1) for v in value)
    if isinstance(value, type) and isinstance(value, PredicateMeta):
        return Atom(name=value.__name__)
    if isinstance(value, Compound):
        return Goal(name=str(value.functor),
                    args=[_reify_value(a, depth + 1) for a in value.args],
                    kwargs=[])
    if isinstance(value, KWTerm):
        return Goal(name=str(value.functor), args=[],
                    kwargs=[[k, _reify_value(v, depth + 1)]
                            for k, v in value.items()])
    if is_term_instance(value):
        return Goal(name=type(value).__name__,
                    args=[_reify_value(getattr(value, f), depth + 1)
                          for f in term_field_names(value)],
                    kwargs=[])
    if isinstance(value, dict):
        return {k: _reify_value(v, depth + 1) for k, v in value.items()}
    raise _Unrenderable(f"no surface form for {type(value).__name__}")


# ── Stage 4: descent into the failing predicate ──────────────────────────────


_DESCENT_DEFAULT_INTRO = (
    "the predicate has no solution for ANY arguments at this point"
)


# ── findall collapse sentinel ────────────────────────────────────────────────
#
# ``findall(Tmpl, Goal, List)`` ALWAYS succeeds: if ``Goal`` has no solution for
# any generated candidate, ``List`` binds to ``[]`` and the conjunct passes.  A
# downstream ``max_list``/``sum``/``==`` then works on the empty (or degenerate)
# list and the whole predicate succeeds with the WRONG value — so the ordinary
# cumulative-prefix walk never blames anything inside the findall.  This sentinel
# runs ``Goal``'s own conjuncts through ``_first_failing`` (the same walker the
# rest of the descent uses); when the body fails for EVERY candidate it names the
# first failing body conjunct, which is the real defect.


def _findall_parts(goal):
    """``(template, body_conjuncts, bag)`` for a runtime ``findall/3`` Call,
    else None.

    ``template`` is the collected-term argument (arg 1); ``body_conjuncts`` is
    the findall's inner Goal flattened to a conjunct list (a
    ``TupleLiteral``/``And`` conjunction splits into its parts; a bare goal is
    a one-element list); ``bag`` is the result-list argument (arg 3)."""
    from clausal.pythonic_ast.nodes import TupleLiteral
    from clausal.terms import And, Call, LoadName

    if not isinstance(goal, Call) or not isinstance(goal.func, LoadName):
        return None
    if str(goal.func.name) != "findall":
        return None
    args = list(goal.args or ())
    if len(args) != 3 or goal.kwargs:
        return None
    template, inner, bag = args

    def flatten(node, out):
        if isinstance(node, TupleLiteral):
            for e in node.elements or ():
                flatten(e, out)
        elif isinstance(node, And):
            flatten(node.left, out)
            flatten(node.right, out)
        else:
            out.append(node)

    conjuncts: list = []
    flatten(inner, conjuncts)
    return (template, conjuncts, bag) if conjuncts else None


def _bag_value(bag):
    """Deref-walked value of a findall's (live-bound) result bag, or None."""
    from clausal.logic.solve import _deref_walk_py

    try:
        return _deref_walk_py(bag)
    except Exception:  # noqa: BLE001
        return None


def _findall_collapsed(bag) -> bool:
    """The findall result *bag* looks like a swallowed failure: ``[]`` or all-0.

    A non-empty list with a non-zero element means the body did produce useful
    solutions — not a collapse — so leave it to the ordinary walk.  Anything we
    cannot deref to a concrete list is treated as NOT collapsed (no false blame).
    """
    value = _bag_value(bag)
    if not isinstance(value, list):
        return False
    if not value:
        return True
    for item in value:
        if item != 0:
            return False
    return True


def _findall_collapse_finding(goal, logic_module, path, deadline,
                              depth, seen, notes, bag_value=None):
    """A descent finding-group naming a collapsed findall's failing body goal.

    Runs the findall body's conjuncts through ``_first_failing`` (with the outer
    bindings live); when the body has no solution the first-failing conjunct is
    the culprit, rendered as one leaf group (source line + up to
    ``DIAG_MAX_DESCENT_BINDINGS`` bindings), prefixed with the findall it hid
    behind.

    A body that DOES have a solution is not automatically healthy: the measured
    ``[0]`` shape collapses to one TRIVIAL solution (the LENGTH=0 probe) while
    every non-trivial candidate fails — ``max_list([0]) = 0`` then flips the
    verdict upstream.  For a non-empty all-zeros bag the walk re-runs with a
    ``template is not 0`` disequality injected just after the conjunct that
    introduces the template variable, so the first NON-trivial failure is the
    one named (see :func:`_trivial_collapse_probe`).

    When the named body conjunct is itself a predicate call, its own failing
    route is followed (bounded by ``DIAG_MAX_COLLAPSE_DEPTH``) and rendered
    indented beneath it — the measured chain continues two levels below the
    findall.  Returns ``None`` when nothing can be honestly attributed.

    *bag_value* is the deref-walked result list observed by the CALLER while
    the findall's bindings were still live — by the time this function runs
    the re-run trail has been undone, so the bag itself no longer carries the
    collapsed value."""
    parts = _findall_parts(goal)
    if parts is None:
        return None
    template, conjuncts, _bag = parts
    failing, raised = _first_failing(conjuncts, logic_module, deadline)
    if raised is not None:
        return None
    headline = ("a findall whose body failed for every candidate — "
                "it silently collapsed to an empty result:")
    probe_goals = conjuncts
    leaf_index = None if failing is None else failing - 1
    if failing is None:
        # Body solved — either genuinely healthy, or the [0]-shape trivial
        # collapse.  Only a non-empty ALL-ZEROS bag re-walks with the
        # disequality; anything else is left alone (no false blame).
        probe = _trivial_collapse_probe(template, conjuncts, bag_value)
        if probe is None:
            return None
        probe_goals, inject_pos, rendered_bag = probe
        failing, raised = _first_failing(probe_goals, logic_module, deadline)
        if raised is not None or failing is None or failing <= inject_pos:
            # Cannot honestly attribute: the body found a non-trivial solution
            # on re-run (non-determinism), or the injected disequality itself
            # is the first failure (the candidate generator only ever produces
            # the trivial value — nothing downstream to blame).
            return None
        headline = ("a findall whose body succeeds only for the trivial "
                    f"value 0 — it silently collapsed to {rendered_bag}; "
                    "the first non-trivial candidate fails at:")
        leaf_index = failing - 2   # probe has one injected goal before it
    leaf = probe_goals[failing - 1]
    reified_leaf = _reified_findall_body_goal(goal, path, leaf_index)

    from clausal.logic.variables import Trail
    from clausal.terms import Call

    trail = Trail()
    gen = None
    lines = [headline]
    try:
        prefix = probe_goals[:failing - 1]
        if prefix:
            gen = _solutions(_conjunction(prefix), logic_module, trail)
            if next(gen, None) is None:
                # Prefix unsatisfiable on the isolated re-run — still name the
                # body goal, just without live bindings.
                reified_leaf = None
        lines.append(f"  {_descent_leaf_line(leaf, reified_leaf, _NO_CLAUSE, path)}")
        for name, value in _leaf_bindings(leaf, reified_leaf):
            lines.append(f"    {name} = {value}")
        # The failing body conjunct may be a call whose own failing route lies
        # deeper (the measured chain: stay_is_valid_for_length → its inner
        # collapsed findall → window_days_used).  Follow it while the depth
        # bound allows; when the bound stops us, say so.
        if isinstance(leaf, Call):
            if depth < DIAG_MAX_COLLAPSE_DEPTH:
                deeper, kind = _descend(
                    leaf, logic_module, path, deadline, depth + 1, seen, notes)
                if kind == "leaves" and deeper:
                    for group in deeper:
                        lines.extend(f"    {line}" for line in group)
            else:
                _note_depth_stop(notes, leaf)
    except (_DiagBudgetExceeded, RecursionError, *_FATAL):
        raise
    except BaseException:  # noqa: BLE001 - a broken probe is not a finding
        return None
    finally:
        if gen is not None:
            gen.close()
        _undo(trail)
    return lines


def _trivial_collapse_probe(template, conjuncts, value):
    """Disequality-injected body walk for the ``[0]``-shape collapse, or None.

    Applies only when *value* (the collapsed bag, deref-walked while its
    bindings were live) is a NON-EMPTY all-zeros list — the measured signature
    of a findall whose body succeeds only via its trivial zero-valued
    candidate.  Returns ``(probe_goals, inject_pos, rendered_bag)`` where
    *probe_goals* is *conjuncts* with ``template is not 0`` inserted right
    after the first conjunct that mentions the template variable (by raw Var
    identity — the generator, e.g. ``between(0, 90, LENGTH)``), and
    *inject_pos* is the 1-based position of the injected goal.  ``None`` when
    the bag is not that shape or the template's variable(s) never appear in
    the body (nothing to constrain)."""
    from clausal.pythonic_ast.nodes import DoesNotUnify

    if not (isinstance(value, list) and value
            and all(item == 0 for item in value)):
        return None
    wanted: set[int] = set()
    _collect_var_ids(template, wanted)
    if not wanted:
        return None
    for j, conjunct in enumerate(conjuncts):
        here: set[int] = set()
        _collect_var_ids(conjunct, here)
        if here & wanted:
            probe = (conjuncts[:j + 1]
                     + [DoesNotUnify(left=template, right=0)]
                     + conjuncts[j + 1:])
            return probe, j + 2, _render_value(value)
    return None


def _note_depth_stop(notes, conjunct) -> None:
    """Record — once — that the collapse scan hit its depth bound.

    Silent exhaustion would imply there is nothing deeper to find; the note
    keeps the ladder honest without unbounding the walk."""
    if any(n.startswith("the wrong-value descent stopped") for n in notes):
        return
    name = _goal_name(conjunct) or "a deeper call"
    notes.append(
        f"the wrong-value descent stopped at its {DIAG_MAX_COLLAPSE_DEPTH}-"
        f"level depth bound (before {name}); paths beyond it were not examined"
    )


def _scan_body_for_findall_collapse(pre, body, goals_list, logic_module, path,
                                    deadline, depth, seen, notes):
    """First collapsed-findall finding reachable from *body*'s conjuncts, or None.

    For each body conjunct, with the goals BEFORE it re-run to establish live
    bindings:

    * a ``findall`` whose result bag looks like a swallowed failure (``[]`` or
      all-zeros) yields the finding-group naming its body's own failing conjunct;
    * any OTHER predicate ``Call`` — the clause is satisfiable, so this conjunct
      succeeded — is recursed into (bounded by ``DIAG_MAX_COLLAPSE_DEPTH``,
      with a note when that bound stops the walk): a wrapper predicate that
      merely forwards to a findall-bearing one is exactly how the collapse
      hides a level deeper.  The recursion's findings are usually a nested
      collapse, but can also be an ordinary failing clause route inside the
      (overall satisfiable) callee — e.g. a non-fallback clause that SHOULD
      have produced the value; either is a truthful "failing route" for the
      wrong value, so leaves are surfaced as-is.  "Re-ran satisfiable" notes
      from the recursion are dropped: satisfiable callees are the EXPECTED
      state on this path, not the anomaly that note reports."""
    from clausal.logic.variables import Trail
    from clausal.terms import Call, LoadName

    for offset, conjunct in enumerate(body):
        if time.monotonic() > deadline:
            raise _DiagBudgetExceeded()
        parts = _findall_parts(conjunct)
        is_plain_call = (
            parts is None
            and isinstance(conjunct, Call)
            and isinstance(getattr(conjunct, "func", None), LoadName)
        )
        if parts is None and not is_plain_call:
            continue
        prefix = goals_list[:len(pre) + offset]
        trail = Trail()
        gen = None
        try:
            if prefix:
                gen = _solutions(_conjunction(prefix), logic_module, trail)
                if next(gen, None) is None:
                    continue
            if parts is not None:
                _template, _conjuncts, bag = parts
                # The findall must actually run to bind its bag; re-run just
                # it.  Read the collapsed value BEFORE the trail is undone —
                # the finding needs it and the bag unbinds with the trail.
                run = Trail()
                run_gen = _solutions(conjunct, logic_module, run)
                try:
                    if next(run_gen, None) is None:
                        continue
                    if not _findall_collapsed(bag):
                        continue
                    bag_value = _bag_value(bag)
                finally:
                    run_gen.close()
                    _undo(run)
                finding = _findall_collapse_finding(
                    conjunct, logic_module, path, deadline, depth, seen, notes,
                    bag_value=bag_value)
                if finding is not None:
                    return finding
            elif depth < DIAG_MAX_COLLAPSE_DEPTH:
                scratch: list[str] = []
                deeper, kind = _descend(
                    conjunct, logic_module, path, deadline,
                    depth + 1, seen, scratch)
                notes.extend(
                    n for n in scratch
                    if "re-ran satisfiable during descent" not in n)
                if kind == "leaves" and deeper:
                    return deeper[0]
            else:
                _note_depth_stop(notes, conjunct)
        except (_DiagBudgetExceeded, RecursionError, *_FATAL):
            raise
        except BaseException:  # noqa: BLE001 - a broken probe is not a finding
            continue
        finally:
            if gen is not None:
                gen.close()
            _undo(trail)
    return None


class _NoClause:
    """Sentinel clause for a findall body leaf (no owning clause position)."""
    position = None


_NO_CLAUSE = _NoClause()


def _reified_findall_body_goal(goal, path, index):
    """The reified body conjunct at *index* of a reified ``findall`` goal, or None.

    Matches by the runtime findall's clause position is unavailable here, so this
    reifies from the goal's own position when present; on any mismatch it
    declines, and the leaf renders from the runtime term (variables as ``_``)."""
    pos = getattr(goal, "position", None)
    if not path or not isinstance(pos, (tuple, list)) or not pos:
        return None
    try:
        from clausal.reflection import Clause as ReifiedClause, Goal, reify_file

        key = str(path)
        items = _REIFY_CACHE.get(key)
        if items is None:
            items = list(reify_file(key))
            if len(_REIFY_CACHE) >= _REIFY_CACHE_MAX:
                _REIFY_CACHE.pop(next(iter(_REIFY_CACHE)), None)
            _REIFY_CACHE[key] = items

        def find(node):
            if (isinstance(node, Goal) and str(node.name) == "findall"
                    and len(node.args or ()) == 3):
                inner = node.args[1]
                flat: list = []
                _flatten_reified(inner, flat)
                if 0 <= index < len(flat):
                    return flat[index]
            for child in _reified_children(node):
                hit = find(child)
                if hit is not None:
                    return hit
            return None

        # Reified Goals carry no position, but their owning Clauses do — and a
        # file can hold several findalls (the measured incident nests one two
        # clauses below another).  Search the clause whose source position most
        # closely precedes the runtime findall's own line FIRST, so the twin
        # comes from the right clause instead of whichever findall the file
        # happens to open with; fall back to the whole-file walk only when no
        # clause can be placed.
        goal_line = pos[0]
        owner = None
        for item in items:
            if not isinstance(item, ReifiedClause):
                continue
            cpos = getattr(item, "position", None)
            if (isinstance(cpos, (tuple, list)) and cpos
                    and cpos[0] <= goal_line
                    and (owner is None or cpos[0] > owner.position[0])):
                owner = item
        if owner is not None:
            hit = find(owner)
            if hit is not None:
                return hit
        for item in items:
            if item is owner:
                continue
            hit = find(item)
            if hit is not None:
                return hit
    except Exception:  # noqa: BLE001 - source text is a nicety, never fatal
        return None
    return None


def _flatten_reified(node, out):
    # A parenthesised findall body reifies its comma-conjunction to a Python
    # tuple (verified against the reflection layer); a single-goal body reifies
    # to a bare Goal.  Anything else is left as one opaque leaf, which degrades
    # to unreified rendering rather than misattributing.
    if isinstance(node, tuple):
        for e in node:
            _flatten_reified(e, out)
    else:
        out.append(node)


def _reified_children(node):
    """Immediate reified sub-nodes worth recursing into for the findall search."""
    from clausal.reflection import Clause, Goal

    if isinstance(node, Clause):
        yield from (node.goals or ())
    elif isinstance(node, Goal):
        yield from (node.args or ())
        for kw in (node.kwargs or ()):
            yield kw[1]
    elif isinstance(node, (list, tuple)):
        yield from node


def _report_descent(diag, goal, logic_module, deadline, path,
                    intro=_DESCENT_DEFAULT_INTRO) -> bool:
    """Walk the failing predicate's own clause bodies against the live goal.

    Called at rung 3 (the all-holes probe proved the predicate unsatisfiable)
    and, since todo D, at rung 1/2 when the probe solutions are degenerate —
    they left the freed argument(s) unbound, so the near-miss carried no
    value.  *intro* is the truthful headline prefix for the calling rung; the
    descent itself only ever states facts about the CONCRETE arguments, which
    hold at every rung.  On findings, sets ``nearest_note``/``descent`` and
    returns True; otherwise leaves the diagnostic untouched and returns False.
    """
    notes: list[str] = []
    leaves, kind = _descend(goal, logic_module, path, deadline, 1, frozenset(), notes)
    if kind == "leaves" and leaves:
        # ``leaves`` is a list of finding-groups (each a list of rendered
        # lines).  The cap counts FINDINGS (groups) across the whole descent
        # including fan-out, so a finding and its binding sub-lines are shown or
        # dropped as a unit — never split — and whole groups are trimmed.
        diag.nearest_note = f"{intro}; no clause body survives:"
        leaves = _cap_leaves(leaves, notes)
        diag.descent = [line for group in leaves for line in group]
        diag.notes.extend(notes)
        return True
    elif kind == "head_listing" and leaves:
        # If the clause cap tripped for this descent, only the first N clause
        # heads were examined, so the headline must not claim ALL heads
        # mismatch — soften it to state the bound.  The cap note carries a
        # distinctive prefix (see _descend); its presence means truncation.
        cap_prefix = (
            f"descent walked only the first {DIAG_MAX_DESCENT_CLAUSES} of "
        )
        truncated = any(n.startswith(cap_prefix) for n in notes)
        if truncated:
            diag.nearest_note = (
                f"{intro}; no clause head among the first "
                f"{DIAG_MAX_DESCENT_CLAUSES} unifies with these arguments "
                "— the heads are:"
            )
        else:
            diag.nearest_note = (
                f"{intro}; no clause head unifies with these arguments — the "
                "heads are:"
            )
        diag.descent = leaves[:DIAG_MAX_DESCENT_LEAVES]
        diag.notes.extend(notes)
        return True
    return False


def _resolve_predicate(goal, logic_module, caller_path):
    """``goal.func``'s name → ``(PredicateMeta, defining module, source path)``.

    Resolution order: the caller's module dict under the exact (possibly
    dotted) name; the attribute on the imported Python module for a dotted
    name; the bare last segment in the caller's module dict (imports land
    there).  A clause body's own names resolve in the module that DEFINED the
    clause, so the defining module — not the caller's — is returned alongside.

    A predicate defined in the caller's own module keeps *caller_path*:
    ``load_clausal_module`` pops the test module from ``sys.modules`` after
    loading, so the ``sys.modules`` route is a dead end exactly there.
    """
    from clausal.logic.predicate import PredicateMeta
    from clausal.terms import LoadName

    func = getattr(goal, "func", None)
    if not isinstance(func, LoadName):
        return None
    name = str(func.name)
    md = getattr(logic_module, "module_dict", None) or {}
    candidates = [md.get(name)]
    if "." in name:
        prefix, last = name.rsplit(".", 1)
        candidates.append(getattr(sys.modules.get(prefix), last, None))
        candidates.append(md.get(last))
    for cls in candidates:
        if isinstance(cls, PredicateMeta) and cls._clauses:
            if cls.__module__ == getattr(logic_module, "name", None):
                return cls, logic_module, caller_path
            defining = sys.modules.get(cls.__module__)
            def_lm = getattr(defining, "__dict__", {}).get("$module") if defining else None
            src = getattr(defining, "__file__", None) if defining else None
            return cls, (def_lm or logic_module), src
    return None


def _head_prefix(head, goal):
    """``Unify(head_arg, goal_arg)`` goals matching *goal* onto *head*, or
    ``None`` when the shapes cannot correspond (arity or keyword mismatch)."""
    from clausal.logic.predicate import term_field_names
    from clausal.pythonic_ast.nodes import Unify

    args = list(goal.args or ())
    kwargs = list(goal.kwargs or ())
    if hasattr(head, "args"):
        hargs, names = list(head.args), None
    else:
        names = list(term_field_names(head))
        hargs = [getattr(head, n) for n in names]
    if len(args) + len(kwargs) != len(hargs):
        return None
    pre = [Unify(left=h, right=g) for h, g in zip(hargs, args)]
    if kwargs:
        if names is None:
            return None
        positional = set(names[:len(args)])
        for kw in kwargs:
            kw_name = str(kw.name)
            if kw_name not in names or kw_name in positional:
                return None
            pre.append(Unify(left=hargs[names.index(kw_name)], right=kw.value))
    return pre


def _descend(goal, logic_module, caller_path, deadline, depth, seen, notes):
    """Descent findings for *goal*'s predicate, with a kind tag.

    Return shape is polymorphic by kind:

    - ``("leaves", groups)`` where ``groups`` is ``list[list[str]]`` — one
      GROUP per finding (a group is a leaf line plus its binding sub-lines).
      A single clause route can fan out into several findings when it recurses
      into a deeper predicate, so the number of groups can exceed the clause
      count; each group is capped/dropped as a unit so a finding is never split
      from its bindings.  (Returned as ``(groups, "leaves")``.)
    - ``(lines, "head_listing")`` where ``lines`` is ``list[str]`` — one line
      per clause head (Task 5), a single finding rendered flat.
    - ``([], "none")`` — could not resolve / nothing to say; caller keeps its
      own rendering.
    """
    resolved = _resolve_predicate(goal, logic_module, caller_path)
    if resolved is None:
        return [], "none"
    cls, sub_lm, sub_path = resolved
    key = (cls.__module__, cls.__name__)
    if key in seen:
        return [], "none"
    seen = seen | {key}
    clauses = list(cls._clauses)
    total = len(clauses)
    if total > DIAG_MAX_DESCENT_CLAUSES:
        notes.append(
            f"descent walked only the first {DIAG_MAX_DESCENT_CLAUSES} of "
            f"{total} clauses of {cls.__name__}"
        )
        clauses = clauses[:DIAG_MAX_DESCENT_CLAUSES]
    # One group per FINDING (a leaf line + its bindings).  A single clause
    # route can fan out into several findings when it recurses into a deeper
    # predicate, so ``_clause_leaves`` returns a LIST of groups and we extend.
    # The DIAG_MAX_DESCENT_LEAVES cap (applied by _report_descent) counts
    # groups, i.e. findings across the whole descent including fan-out — a
    # finding and its binding sub-lines are shown or dropped as a unit, never
    # split apart or miscounted (design §Flat leaves).
    groups: list[list[str]] = []
    mismatches = 0
    for clause in clauses:
        if time.monotonic() > deadline:
            raise _DiagBudgetExceeded()
        try:
            clause_groups, state = _clause_leaves(
                clause, goal, sub_lm, sub_path, deadline, depth, seen, notes)
        except (_DiagBudgetExceeded, RecursionError, *_FATAL):
            raise
        except BaseException:  # noqa: BLE001 - a broken probe is not a finding
            continue
        if state == "head_mismatch":
            mismatches += 1
        elif state == "leaves":
            groups.extend(clause_groups)
    if mismatches == len(clauses) and clauses:
        return _head_listing(cls, clauses, path=sub_path), "head_listing"
    return (groups, "leaves") if groups else ([], "none")


def _clause_leaves(clause, goal, logic_module, path, deadline, depth, seen, notes):
    """Findings for one clause route: ``(groups, state)``.

    ``groups`` is ``list[list[str]]`` — one group per finding (a leaf line plus
    its binding sub-lines).  A route usually yields ONE group, but when it
    recurses into a deeper predicate the deeper findings fan out and this route
    returns several groups (so the total-finding cap sees every fan-out
    finding).  ``state`` is ``"leaves"``, ``"head_mismatch"`` (head or hoisted
    structural arg failed to unify — this clause was never a route) or
    ``"skip"`` (probe artifact or re-run disagreement — say nothing); for the
    non-``"leaves"`` states ``groups`` is empty."""
    from clausal.logic.variables import Trail
    from clausal.pythonic_ast.nodes import Unify

    pre = _head_prefix(clause.head, goal)
    if pre is None:
        return [], "head_mismatch"
    body = list(clause.body or ())[:DIAG_MAX_GOALS]

    # Tail-align source conjuncts: _normalize_structural_head_args PREPENDS
    # Unify goals for structural head args, so the runtime body may be longer
    # than its source.  k is that prepended count.
    reified = _reified_clause(path, clause)
    rgoals = list(reified.goals or ()) if reified is not None else None
    k = 0
    if rgoals is not None:
        k = len(body) - len(rgoals)
        if k < 0 or not all(isinstance(g, Unify) for g in body[:k]):
            rgoals, k = None, 0

    goals_list = pre + body
    failing, raised = _first_failing(goals_list, logic_module, deadline)
    if raised is not None:
        return [], "skip"          # probe artifact, never reported as cause
    if failing is None:
        # The clause re-ran satisfiable — but a ``findall`` that collapsed to []
        # is EXACTLY what makes a wrong-value clause "succeed", so before we
        # write this off as non-determinism, look for a swallowed failure inside
        # any of the clause's findall conjuncts.
        collapse = _scan_body_for_findall_collapse(
            pre, body, goals_list, logic_module, path, deadline,
            depth, seen, notes)
        if collapse is not None:
            return [collapse], "leaves"
        head_name = str(
            getattr(clause.head, "functor", None) or type(clause.head).__name__
        )
        notes.append(
            f"a clause of {head_name} re-ran satisfiable "
            f"during descent — non-determinism, or state changed by the run"
        )
        return [], "skip"
    if failing <= len(pre) + k:
        return [], "head_mismatch"  # failed while matching head arguments

    idx = failing - 1               # into goals_list
    leaf = goals_list[idx]
    src_idx = idx - len(pre) - k    # into rgoals
    reified_leaf = (
        rgoals[src_idx]
        if rgoals is not None and 0 <= src_idx < len(rgoals) else None
    )

    trail = Trail()
    gen = None
    try:
        prefix_goals = goals_list[:idx]
        if prefix_goals:
            gen = _solutions(_conjunction(prefix_goals), logic_module, trail)
            if next(gen, None) is None:
                return [], "skip"
        from clausal.terms import Call

        if depth < DIAG_MAX_DESCENT_DEPTH and isinstance(leaf, Call):
            deeper, deeper_kind = _descend(
                leaf, logic_module, path, deadline, depth + 1, seen, notes)
            if deeper_kind == "leaves" and deeper:
                # deeper is a list of finding-groups; return them AS-IS so each
                # deeper finding stays its own group and is counted by the
                # total-finding cap — never merged into a single parent group.
                return deeper, "leaves"
            if deeper_kind == "head_listing" and deeper:
                # A head listing beneath this parent leaf is ONE finding: the
                # parent conjunct, its bindings, and the heads, all one group.
                lines = [_descent_leaf_line(leaf, reified_leaf, clause, path)]
                for name, value in _leaf_bindings(leaf, reified_leaf):
                    lines.append(f"    {name} = {value}")
                lines.append("    no clause head unifies with these arguments; "
                             "the heads are:")
                lines.extend(f"      {line}" for line in deeper)
                return [lines], "leaves"
            # "none" falls through to render this conjunct as the leaf.
        lines = [_descent_leaf_line(leaf, reified_leaf, clause, path)]
        for name, value in _leaf_bindings(leaf, reified_leaf):
            lines.append(f"    {name} = {value}")
        # A failing leaf that CONSUMES a collapsed findall's bag (`length(
        # VALID_DAYS, LENGTH)` with `VALID_DAYS = []`) is only the symptom;
        # the swallowed failure inside the findall is the cause.  Name it
        # beneath the leaf when the bag demonstrably feeds it.
        feeding = _collapsed_findall_feeding(
            leaf, body[:idx - len(pre)], logic_module, path, deadline,
            depth, seen, notes)
        if feeding:
            lines.extend(f"    {line}" for line in feeding)
        return [lines], "leaves"
    except (_DiagBudgetExceeded, RecursionError, *_FATAL):
        raise
    except BaseException:  # noqa: BLE001
        return [], "skip"
    finally:
        if gen is not None:
            gen.close()
        _undo(trail)


def _collapsed_findall_feeding(leaf, earlier, logic_module, path, deadline,
                               depth, seen, notes):
    """Collapse finding for a findall (before *leaf* in the same body) whose
    result bag the failing *leaf* consumes, or None.

    Runs with the caller's prefix bindings live, so the findall has already
    executed and its bag is bound.  The bag→leaf raw-Var-identity gate keeps
    unrelated (legitimately empty) findalls in the same body unblamed: only a
    bag the failing conjunct actually reads can be the reason it failed."""
    leaf_ids: set[int] = set()
    _collect_var_ids(leaf, leaf_ids)
    if not leaf_ids:
        return None
    for conjunct in earlier:
        if time.monotonic() > deadline:
            raise _DiagBudgetExceeded()
        parts = _findall_parts(conjunct)
        if parts is None:
            continue
        _template, _conjuncts, bag = parts
        bag_ids: set[int] = set()
        _collect_var_ids(bag, bag_ids)
        if not (bag_ids & leaf_ids):
            continue
        if not _findall_collapsed(bag):
            continue
        try:
            finding = _findall_collapse_finding(
                conjunct, logic_module, path, deadline, depth, seen, notes,
                bag_value=_bag_value(bag))
        except (_DiagBudgetExceeded, RecursionError, *_FATAL):
            raise
        except BaseException:  # noqa: BLE001 - a broken probe is not a finding
            continue
        if finding is not None:
            return finding
    return None


def _head_listing(cls, clauses, path) -> list[str]:
    """One ``file:line  <head source>`` line per clause, source-faithful."""
    lines = []
    label = os.path.basename(str(path)) if path else cls.__module__
    for clause in clauses:
        text = None
        reified = _reified_clause(path, clause)
        if reified is not None:
            try:
                from clausal.reflection import render_source

                text = render_source(reified.head)
            except Exception:  # noqa: BLE001
                text = None
        if text is None:
            from clausal.terms import term_str

            try:
                text = term_str(clause.head)
            except Exception:  # noqa: BLE001
                text = repr(clause.head)
        line = clause.position[0] if clause.position else None
        lines.append(f"{label}:{line}  {text}" if line is not None
                     else f"{label}  {text}")
    return lines


def _descent_leaf_line(leaf, reified_leaf, clause, path) -> str:
    """``file:line  <source text>`` for one leaf conjunct."""
    text = None
    if reified_leaf is not None:
        try:
            from clausal.reflection import render_source

            text = render_source(reified_leaf)
        except Exception:  # noqa: BLE001
            text = None
    if text is None:
        from clausal.terms import term_str

        try:
            text = term_str(leaf)
        except Exception:  # noqa: BLE001
            text = repr(leaf)
    line = None
    pos = getattr(leaf, "position", None)
    if isinstance(pos, (tuple, list)) and pos:
        line = pos[0]
    if line is None and clause.position:
        line = clause.position[0]
    label = os.path.basename(str(path)) if path else "?"
    return f"{label}:{line}  {text}" if line is not None else f"{label}  {text}"


def _leaf_bindings(leaf, reified_leaf) -> list[tuple[str, str]]:
    """Up to DIAG_MAX_DESCENT_BINDINGS named, bound variables of the leaf."""
    from clausal.logic.variables import deref, is_var

    if reified_leaf is None:
        return []
    named = _collect_named([leaf], [reified_leaf]) or []
    out: list[tuple[str, str]] = []
    seen_ids: set[int] = set()
    for name, var in named:
        if id(var) in seen_ids:
            continue
        seen_ids.add(id(var))
        value = deref(var)
        if is_var(value):
            continue
        try:
            out.append((name, _render_value(value)))
        except Exception:  # noqa: BLE001
            continue
        if len(out) >= DIAG_MAX_DESCENT_BINDINGS:
            break
    return out


# ── Report formatting ────────────────────────────────────────────────────────


def _wrap_goal(text: str, indent: str, width: int = 96) -> list[str]:
    """Print a goal, splitting at top-level argument commas when it is long.

    Continuations align under the opening paren, matching how the goal reads
    in source.
    """
    text = text.strip()
    if len(indent) + len(text) <= width or "(" not in text:
        return [indent + text]
    head, _, rest = text.partition("(")
    if not rest.endswith(")"):
        return [indent + text]
    inner = rest[:-1]
    parts, depth, quote, start = [], 0, None, 0
    for i, ch in enumerate(inner):
        if quote:
            if ch == quote and (i == 0 or inner[i - 1] != "\\"):
                quote = None
        elif ch in "'\"":
            quote = ch
        elif ch in "([{":
            depth += 1
        elif ch in ")]}":
            depth -= 1
        elif ch == "," and depth == 0:
            parts.append(inner[start:i])
            start = i + 1
    parts.append(inner[start:])
    parts = [p.strip() for p in parts]
    if len(parts) < 2:
        return [indent + text]
    pad = " " * (len(indent) + len(head) + 1)
    lines = [f"{indent}{head}({parts[0]},"]
    for part in parts[1:-1]:
        lines.append(f"{pad}{part},")
    lines.append(f"{pad}{parts[-1]})")
    return lines


def _failure_lines(rel: str, result: TestResult) -> list[str]:
    location = f"{rel}:{result.line}" if result.line else rel
    header = f"  {location} :: {result.name}"
    lines = [header]
    if result.error is None:
        detail, rest = "", []
    else:
        detail, *rest = str(result.error).splitlines() or [""]
    if result.error is not None:
        header = lines[0] = f"{header} — {detail}"
    # A multi-line message (a lookup failure lists its candidates) belongs in
    # the report exactly once.  The goal block below already reproduces it in
    # full and under the goal it came from, so print the remainder here only
    # when there is no goal block to carry it.
    if rest and not _diagnostic_repeats(result, rest):
        lines.extend(f"    {line}" for line in rest)
    if result.diagnostic is not None:
        lines.extend(result.diagnostic.lines())
    return lines


def _diagnostic_repeats(result: TestResult, rest: list[str]) -> bool:
    """True when the goal diagnostic already prints these message lines."""
    raised = getattr(result.diagnostic, "raised", None)
    if not raised:
        return False
    raised_lines = raised.splitlines()
    return rest and rest[-1] in raised_lines


def discover_clausal_files(roots: list[str | Path]) -> Iterator[Path]:
    """Yield all .clausal files under the given roots."""
    for root in roots:
        root = Path(root)
        if root.is_file() and root.suffix == ".clausal":
            yield root
        elif root.is_dir():
            yield from sorted(root.rglob("*.clausal"))


# ── CLI ───────────────────────────────────────────────────────────────────────


def main(args: list[str] | None = None) -> int:
    """Run .clausal tests from the command line. Returns exit code."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Run test/1 clauses in .clausal files",
    )
    parser.add_argument("paths", nargs="+", help=".clausal files or directories")
    parser.add_argument("-v", "--verbose", action="store_true",
                        help="Show individual test results")
    parser.add_argument("--strict", "--fail-on-empty", dest="strict",
                        action="store_true",
                        help="Exit non-zero when no Test(...) clauses are collected")
    parsed = parser.parse_args(args)

    # Validate paths up front so a mistyped path or wrong cwd is an error, not a
    # silently-green run.  A non-existent path, or a file that exists but is not a
    # .clausal/.pl file, is reported and forces a non-zero exit.
    bad_paths: list[str] = []
    for path in parsed.paths:
        p = Path(path)
        if not p.exists():
            bad_paths.append(f"no such file or directory: {path}")
        elif p.is_file() and p.suffix != ".clausal":
            bad_paths.append(f"not a .clausal file: {path}")
    if bad_paths:
        for msg in bad_paths:
            print(f"error: {msg}", file=sys.stderr)
        return 2

    total_passed = 0
    total_failed = 0
    files_seen = 0
    failures: list[tuple[str, TestResult]] = []

    for path in discover_clausal_files(parsed.paths):
        files_seen += 1
        file_results = run_file(path)
        rel = os.path.relpath(file_results.path)

        for r in file_results.results:
            if r.passed:
                total_passed += 1
                if parsed.verbose:
                    print(f"  PASS  {rel}::{r.name}")
            else:
                total_failed += 1
                failures.append((rel, r))
                if parsed.verbose:
                    msg = f"  FAIL  {rel}::{r.name}"
                    if r.error:
                        msg += f"  ({r.error})"
                    print(msg)

    # Summary
    print()
    if failures:
        print("FAILURES:")
        for rel, r in failures:
            for line in _failure_lines(rel, r):
                print(line)
        print()

    total = total_passed + total_failed

    # Distinguish "nothing to run" from "everything passed": files that exist but
    # contain no Test(...) clauses (or roots with no .clausal files at all) would
    # otherwise print a misleading [PASSED].
    if total == 0:
        if files_seen == 0:
            print("no .clausal files found")
        else:
            print(f"{files_seen} file(s) collected, but no Test(...) clauses found")
        if parsed.strict:
            print("0 tests [NO TESTS]")
            return 1
        print("0 tests [NO TESTS] (use --strict to fail)")
        return 0

    status = "PASSED" if total_failed == 0 else "FAILED"
    print(f"{total} tests: {total_passed} passed, {total_failed} failed [{status}]")
    return 0 if total_failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
