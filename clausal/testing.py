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
    diag = GoalDiagnostic()
    logic_module = mod.__dict__.get("$module") if hasattr(mod, "__dict__") else None
    before = _clause_count(logic_module)
    budget = _diag_budget()
    try:
        with _watchdog(budget):
            sink = io.StringIO()
            with contextlib.redirect_stdout(sink), contextlib.redirect_stderr(sink):
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
    failing = None
    for k in range(1, len(walked) + 1):
        if time.monotonic() > deadline:
            raise _DiagBudgetExceeded()
        trail = Trail()
        try:
            ok = _has_solution(_conjunction(walked[:k]), logic_module, trail)
        except (_DiagBudgetExceeded, RecursionError, *_FATAL):
            raise
        except BaseException as exc:  # noqa: BLE001
            diag.index, diag.raised = k, f"{type(exc).__name__}: {exc}"
            diag.source = sources[k - 1]
            return
        finally:
            _undo(trail)
        if not ok:
            failing = k
            break

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
                _report_nearest(diag, goal, reified_goal, logic_module, deadline)
            finally:
                gen.close()
        else:
            diag.bindings_note = "(none — goal 1 is the first goal)"
            _report_nearest(diag, goal, reified_goal, logic_module, deadline)
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


def _reified_goals(path, clause, arity):
    """The reified (source-faithful) conjuncts of *clause*, or ``None``.

    Matching is by source position, so a mis-association is impossible; a
    conjunct-count mismatch (a body shape whose runtime form does not
    correspond 1:1 with its source conjuncts) declines rather than guesses.
    """
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
                goals = list(item.goals or ())
                return goals if len(goals) == arity else None
    except Exception:  # noqa: BLE001 - source text is a nicety, never fatal
        return None
    return None


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


def _report_nearest(diag, goal, reified_goal, logic_module, deadline) -> None:
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

    args = list(goal.args or ())
    kwargs = list(goal.kwargs or ())
    if not args and not kwargs:
        diag.nearest_note = "the predicate has no solution (it takes no arguments)"
        return

    slots: list[tuple[str, int]] = (
        [("arg", i) for i in range(len(args))]
        + [("kw", i) for i in range(len(kwargs))]
    )

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
        label = (
            f"argument {i + 1}" if kind == "arg"
            else f"keyword argument {kwargs[i].name!r}"
        )
        diag.nearest_note = (
            f"the predicate DID have a solution, which did not unify "
            f"({label} differs):"
        )
        diag.nearest = _render_nearest(goal, reified_goal, kind, i, value)
        wanted = args[i] if kind == "arg" else kwargs[i].value
        note = _arith_vs_number_note(label, wanted, value)
        if note:
            diag.notes.append(note)
        return

    # No single argument explains it — is the predicate satisfiable at all?
    holes = [Var() for _ in args]
    kw_holes = [Keyword(name=k.name, value=Var()) for k in kwargs]
    probe = Call(func=goal.func, args=holes, kwargs=kw_holes)
    trail = Trail()
    try:
        satisfiable = _has_solution(probe, logic_module, trail)
    except (_DiagBudgetExceeded, RecursionError, *_FATAL):
        raise
    except BaseException:  # noqa: BLE001
        satisfiable = False
    finally:
        _undo(trail)
    if satisfiable:
        diag.nearest_note = (
            "the predicate has solutions, but none within one argument of "
            "this goal — two or more arguments differ"
        )
    else:
        diag.nearest_note = (
            "the predicate has no solution for ANY arguments at this point "
            "(check the goals that produced its inputs, or its own clauses)"
        )


_NO_SOLUTION = object()


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
