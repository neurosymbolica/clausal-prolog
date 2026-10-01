"""clausal.testing — test runner for .clausal predicate modules.

Discovers test/1 clauses in .clausal files (and their ``.seam`` alias), and
in Prolog ``.pl`` files loaded through the experimental Prolog importer, and
runs them. Each test clause is a rule of the form:

    test("description") <- goal1, goal2, ...        % .clausal / .seam
    test('description') :- Goal1, Goal2, ...        % .pl

A test passes if its body succeeds (produces at least one solution).

A NEGATIVE test is plunit's ``test/2`` with the option ``fail``:

    test("description", fail) <- goal1, goal2, ...  % .clausal / .seam
    test('description', fail) :- Goal1, Goal2, ...  % .pl

It passes iff its body has NO solution; a solution fails it, and an
exception is an error as for ``test/1``.  Any other option is a collection
error (:class:`TestCollectionError`) naming it.

Standalone usage
----------------
    python -m clausal.testing clausal/examples/
    python -m clausal.testing clausal/examples/fibonacci.clausal
    python -m clausal.testing path/to/rules.pl

Exit codes: 0 all tests passed; 1 a test failed or a file failed to load
(or, for a ``.pl`` file, to translate); 2 a usage error (missing path, a file
of an unsupported type); 5 no tests were collected.  Pass ``--allow-empty``
to turn "no tests collected" into exit 0.

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

from clausal._suffixes import (
    CLAUSAL_SUFFIXES,
    SOURCE_SUFFIXES,
    is_prolog_source,
    strip_clausal_suffix,
)

#: File extensions the runner collects test/1 clauses from: the Clausal
#: source spellings plus Prolog ``.pl`` (translated on load).
TEST_SUFFIXES: tuple[str, ...] = SOURCE_SUFFIXES

#: Exit codes of ``python -m clausal.testing`` (``main``).
EXIT_OK = 0
EXIT_TESTS_FAILED = 1
EXIT_USAGE = 2
#: Nothing was collected: every root was empty, held no test files, or held
#: only files without test/1 clauses.  Same number as pytest's "no tests
#: collected".  ``--allow-empty`` maps it to ``EXIT_OK``.
EXIT_NO_TESTS = 5


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
    #: A ``test(Name, fail)`` clause: it passes iff its goal has no solution.
    negative: bool = False


@dataclass
class FileResults:
    path: str
    results: list[TestResult] = field(default_factory=list)


def load_clausal_module(path: str | Path) -> object:
    """Load a .clausal (or .seam, or Prolog .pl) file as a module and return it.

    A ``.pl`` file goes through the experimental Prolog importer — the same
    ``PrologLoader`` a ``-import_from`` of a ``.pl`` file uses — so a file the
    translator rejects raises ``SyntaxError`` carrying the translator error.

    Every call compiles the file **afresh**, under a private
    ``_clausal_test_<basename>`` name, so each test gets an independent
    database.  That independence extends to declared terms: the compounds this
    module exports are distinct classes from the ones a plain
    ``import``/``-import_from`` of the same file produces, so a term built here
    will not unify with a pattern built there — it simply yields no solution,
    and the two terms render identically.  Callers that need one term universe
    across both routes should reach the file through ``importlib`` (dotted
    imports of one file are deduplicated by source path; see
    ``import_hook._MODULES_BY_PATH``) rather than mixing the two.
    """
    # Ensure import hook is installed.
    import clausal.import_hook  # noqa: F401

    from clausal.import_hook import _load_module, _load_prolog_module

    path = str(path)
    base = os.path.basename(path)
    is_prolog = is_prolog_source(base)
    if is_prolog:
        base = os.path.splitext(base)[0]
    mod_name = f"_clausal_test_{strip_clausal_suffix(base)}"

    # _load_module handles sys.modules eviction internally.
    old = sys.modules.get(mod_name)
    try:
        mod = (_load_prolog_module if is_prolog else _load_module)(mod_name, path)
    finally:
        # Avoid polluting sys.modules across test runs.
        if old is None:
            sys.modules.pop(mod_name, None)
        else:
            sys.modules[mod_name] = old
    # Out of sys.modules, but still a loaded program: the reflection
    # builtins that enumerate loaded modules (constant_value/2 and kin)
    # must see it, or its own constants answer nothing.
    from clausal.logic.constants import register_detached_module
    register_detached_module(mod)
    return mod


#: The test-clause predicate and its deprecated spelling.  Predicates are
#: lowercase, so it is ``test/1``; ``Test/1`` clauses are still collected and
#: run (a file may hold both while it is being renamed) and the loader warns
#: once per file — see ``term_rewriting._warn_deprecated_test_spelling``.
#: ``test/2`` is plunit's ``test(Name, Options)``; the one option supported
#: is ``fail`` (ruling 2026-09-29), a NEGATIVE test.
TEST_NAME = "test"
TEST_DEPRECATED_NAME = "Test"

#: The ``test/2`` options the runner understands.
TEST_OPTION_FAIL = "fail"

#: plunit's other ``test/2`` options, named in the error for one of them so
#: the author sees it was read and refused, not mistyped.
PLUNIT_UNSUPPORTED_OPTIONS = (
    "true(Cond)", "all(Template Cmp Values)", "set(Template Cmp Values)",
    "throws(Error)", "error(Error)", "false", "nondet", "blocked(Reason)",
    "fixme(Reason)", "setup(Goal)", "cleanup(Goal)", "forall(Generator)",
    "condition(Goal)", "occurs_check(Mode)", "timeout(Seconds)",
)


class TestCollectionError(ValueError):
    """A test clause the runner cannot collect: an unsupported ``test/2``
    option.  A load-time-like error for the whole file (the CLI and the
    pytest plugin report it as ``<collect>``), never a silently skipped
    test."""

    __test__ = False                    # not a pytest test class


def _test_clauses(logic_module) -> list[tuple[str, object]]:
    """``(functor, clause)`` for every ``test/1``, ``Test/1`` and ``test/2``
    clause.

    Order is the order a reader sees: each predicate's clauses in the order
    they were asserted (source order for a loaded file), and the predicates
    merged by source line so a mixed file runs top to bottom.  The merge
    never reorders WITHIN a predicate: it only chooses which predicate's
    next clause comes first (a clause without a source position, e.g. from
    ``assertz``, is taken as if it came last).  A single-predicate file —
    the common case — is exactly the ``clauses_for`` order.  A ``test/2``
    clause is told apart by its head's arity (:func:`_is_negative`).
    """
    db = logic_module.db
    groups = [g for g in (
        [(TEST_NAME, c) for c in db.clauses_for(TEST_NAME, 1)],
        [(TEST_DEPRECATED_NAME, c)
         for c in db.clauses_for(TEST_DEPRECATED_NAME, 1)],
        [(TEST_NAME, c) for c in db.clauses_for(TEST_NAME, 2)],
    ) if g]
    if len(groups) <= 1:
        return groups[0] if groups else []

    def line(entry):
        position = entry[1].position
        return position[0] if position else float("inf")

    merged: list[tuple[str, object]] = []
    heads = [0] * len(groups)
    while True:
        best = None
        for gi, group in enumerate(groups):
            if heads[gi] < len(group) and (
                    best is None
                    or line(group[heads[gi]]) < line(groups[best][heads[best]])):
                best = gi
        if best is None:
            return merged
        merged.append(groups[best][heads[best]])
        heads[best] += 1


def _head_args(head) -> tuple:
    """The argument tuple of a ``test`` clause head."""
    if hasattr(head, "args"):
        return tuple(head.args)
    from clausal.logic.cells import _cell_shape, cell_args  # noqa: PLC0415
    if _cell_shape(head)[0]:
        return tuple(cell_args(head))
    from clausal.logic.predicate import term_field_names  # noqa: PLC0415
    return tuple(getattr(head, n) for n in term_field_names(head))


def _clause_args(clause, db=None) -> tuple:
    """The argument tuple of a ``test`` clause as its SOURCE wrote it.

    A fact -- and a clause whose body is exactly ``true``, which is stored
    the same way -- keeps no ground argument in its head, and no clause
    keeps a compound one: each becomes a fresh variable plus a leading
    ``Unify(V, value)`` body goal (see ``Clause.hoisted``), so the head
    alone would name the test ``_0`` and run it as ``test(_)``.  Each such
    variable is read back from its goal: plain data is itself, a bare name
    (``LoadName``) the atom it spells.  Any other goal (a compound written
    in the seam, a ``Call`` node) is built as ``clause/2`` builds a head,
    when *db* (the clause's module database) is given; a position that
    cannot be built stays the variable, for :func:`_test_option` to
    render."""
    from clausal.logic.builtins.clause_ops import _plain  # noqa: PLC0415
    args = list(_head_args(clause.head))
    lead = list(clause.body or ())[:getattr(clause, "hoisted", 0)]
    if not lead:
        return tuple(args)
    from clausal.logic.variables import Var  # noqa: PLC0415
    unresolved = []
    for i, arg in enumerate(args):
        if not isinstance(arg, Var):
            continue
        for goal in lead:
            if type(goal).__name__ == "Unify" and goal.left is arg:
                right = goal.right
                if type(right).__name__ == "LoadName":
                    args[i] = right.name
                elif _plain(right):
                    args[i] = right
                else:
                    unresolved.append(i)
                break
    if unresolved and db is not None:
        built = _built_head_args(clause, db)
        if built is not None:
            for i in unresolved:
                args[i] = built[i]
    return tuple(args)


def _built_head_args(clause, db) -> "tuple | None":
    """*clause*'s head arguments with its hoisted goals run, as a fresh
    copy -- the head ``clause/2`` answers -- or ``None`` when they cannot
    be built."""
    from clausal.logic.builtins.clause_ops import (  # noqa: PLC0415
        _BuildFailed, _as_cell, _head_built, _on_private_trail)
    from clausal.logic.builtins.inspection import _copy_term  # noqa: PLC0415
    head = _as_cell(clause.head)
    built = _head_built(clause, db)
    if built.why is not None:
        return None
    try:
        term = _on_private_trail(built, lambda _tmp: _copy_term(head, {}))
    except _BuildFailed:
        return None
    return tuple(term[1:]) if type(term) is tuple else None


def _is_negative(clause) -> bool:
    """True for a ``test(Name, fail)`` clause (a ``test/2`` head)."""
    return len(_head_args(clause.head)) == 2


def _test_option(clause) -> tuple[object, str]:
    """``(value, source text)`` of a ``test/2`` clause's option argument.

    A head argument the compiler hoisted (``fail`` in a seam head becomes a
    fresh variable plus a leading ``Unify(V, fail)`` body goal, see
    ``Clause.hoisted``) is read back by :func:`_clause_args`: a bare name
    is the atom it spells, anything else is only rendered for the error."""
    from clausal.logic.variables import Var, deref  # noqa: PLC0415
    from clausal.terms import term_str  # noqa: PLC0415
    opt = deref(_clause_args(clause)[1])
    if isinstance(opt, Var):
        # Not plain data and not a bare name: only rendered for the error.
        for goal in list(clause.body or ())[:getattr(clause, "hoisted", 0)]:
            if type(goal).__name__ == "Unify" and goal.left is opt:
                return None, _render_node(goal.right)
        return None, "a variable"
    from clausal.logic.atoms import is_atom, spelling  # noqa: PLC0415
    if is_atom(opt):
        return spelling(opt), spelling(opt)
    try:
        return None, term_str(opt)
    except Exception:  # noqa: BLE001 - only rendered for the error
        return None, repr(opt)


def _render_node(node) -> str:
    """Source-like text of a hoisted head argument (for an error only)."""
    kind = type(node).__name__
    if isinstance(node, list):
        return "[" + ", ".join(_render_node(e) for e in node) + "]"
    if kind == "LoadName":
        return node.name
    if kind in ("ListLiteral", "TupleLiteral"):
        inner = ", ".join(_render_node(e) for e in node.elements)
        return f"[{inner}]" if kind == "ListLiteral" else f"({inner})"
    if kind == "Call":
        args = ", ".join(_render_node(a) for a in node.args)
        return f"{_render_node(node.func)}({args})"
    if kind == "Constant" or not hasattr(node, "__dataclass_fields__"):
        value = getattr(node, "value", node)
        return repr(value)
    return str(node)


def _check_test_option(mod, clause, name: str) -> None:
    """Raise :class:`TestCollectionError` unless the option is ``fail``."""
    value, text = _test_option(clause)
    if value == TEST_OPTION_FAIL:
        return
    where = getattr(mod, "__file__", None) or getattr(mod, "__name__", "<module>")
    if clause.position and not is_prolog_source(where):
        # A .pl file's positions are lines of its translation (no source map).
        where = f"{where}: line {clause.position[0]}"
    raise TestCollectionError(
        f"{where}: test({name!r}, {text}): unknown test option `{text}`; "
        f"only `{TEST_OPTION_FAIL}` is supported (test(Name, fail) passes "
        "iff Name's goal has no solution). plunit's other options are not: "
        + ", ".join(PLUNIT_UNSUPPORTED_OPTIONS))


def _test_description_term(clause, db=None):
    """The description ARGUMENT of a ``test/1`` or ``test/2`` clause, as
    written (:func:`_clause_args`; *db* is the clause's module database)."""
    args = _clause_args(clause, db)
    return args[0] if args else clause.head


def _test_description_name(desc) -> str:
    """The display NAME of a test description term.

    A description is human text, so the name is that text: the SPELLING of
    an atom (an unquoted ``test("...")`` literal compiles to an atom under
    ``-double_quotes(atom)``) or the string itself under
    ``-double_quotes(chars)``, the default since 2026-09-26.  Both spellings of
    one description therefore name the same test, which is what a reader,
    a report and a ``-k`` selector all expect.

    THE FLIP (2026-09-06-atoms-as-cells-strings) is why this is a function:
    ``str(desc)`` used to be the text because an atom WAS its spelling; on
    a cell it is the tuple repr ``("in: found",)``.  A compound description
    is named by its term text, as ``writeq/1`` writes it (``case(2)``, not
    the tuple repr ``('case', 2)``).  Any other ground value still names
    itself through ``str``.
    """
    from clausal.logic.atoms import is_atom as _term_is_atom, spelling
    if _term_is_atom(desc):
        return spelling(desc)
    from clausal.logic.cells import is_chars, chars_text  # noqa: PLC0415
    if is_chars(desc):
        desc = chars_text(desc)          # stage 1: a test NAME written "..." is the chars carrier
    if isinstance(desc, str):
        return desc
    from clausal.logic.builtins._helpers import _is_compound  # noqa: PLC0415
    if _is_compound(desc):
        from clausal.terms import term_str  # noqa: PLC0415
        return term_str(desc)
    return str(desc)


def collect_tests(mod: object) -> list[str]:
    """Return the test descriptions (``test/1``, ``Test/1`` and
    ``test(Name, fail)`` clauses) from a loaded module.

    Raises :class:`TestCollectionError` for a ``test/2`` clause whose option
    is not ``fail``."""
    logic_module = mod.__dict__.get("$module")
    if logic_module is None:
        return []
    entries = _test_clauses(logic_module)
    names = [_test_description_name(
                 _test_description_term(clause, logic_module.db))
             for _functor, clause in entries]
    for (_functor, clause), name in zip(entries, names):
        if _is_negative(clause):
            _check_test_option(mod, clause, name)
    _warn_description_under_both_spellings(mod, entries, names)
    return names


def _warn_description_under_both_spellings(mod, entries, names) -> None:
    """Warn when one description is a ``test/1`` AND a ``Test/1`` clause.

    Both names are collected, but a name resolves to its FIRST clause, so
    the second clause is reported under a result it never produced.  That
    is invisible from the report, so say so once per collection, naming
    the file and the descriptions, so the author renames one of them.
    """
    spelled: dict[str, set[str]] = {}
    for (functor, clause), name in zip(entries, names):
        spelled.setdefault(name, set()).add(
            f"{functor}/{len(_head_args(clause.head))}")
    doubled = [name for name, functors in spelled.items() if len(functors) > 1]
    if not doubled:
        return
    import warnings  # noqa: PLC0415
    where = getattr(mod, "__file__", None) or getattr(mod, "__name__", "<module>")
    listed = ", ".join(repr(name) for name in doubled)
    warnings.warn(
        f"{where}: test description(s) {listed} defined under more than "
        f"one of {TEST_NAME}/1, {TEST_DEPRECATED_NAME}/1 and "
        f"{TEST_NAME}(Name, fail); each name runs its "
        f"first clause only, so rename the {TEST_DEPRECATED_NAME}/1 clause "
        f"to {TEST_NAME}/1 or give each clause its own description",
        stacklevel=3,
    )


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
        # *description* is the display NAME (what ``collect_tests`` returns);
        # the goal is called with the clause's own description TERM, which is
        # an ATOM for an ordinary ``test("...")`` clause and a string under
        # ``-double_quotes(chars)``.  Calling with the name would pass a
        # ``str`` — a different term from the atom, matching nothing.  The
        # functor is the clause's own: ``test`` or the deprecated ``Test``.
        functor, goal_desc, negative = _test_goal_for_name(
            logic_module, description)
        if negative:
            # test(Name, fail): passes iff the goal has NO solution.  One
            # solution decides it; the rest are never searched for.  An
            # embedder calling run_test without collect_tests still gets
            # an unsupported option refused, never run as a `fail` test.
            _check_test_option(mod, _test_entry(logic_module, description)[1],
                               description)
            gen = call(functor, goal_desc, TEST_OPTION_FAIL, module=logic_module)
            try:
                passed = next(gen, None) is None
            finally:
                gen.close()
        else:
            solutions = list(call(functor, goal_desc, module=logic_module))
            passed = len(solutions) > 0
        result = TestResult(name=description, passed=passed,
                            duration=time.perf_counter() - t0,
                            negative=negative)
    except Exception as e:
        result = TestResult(name=description, passed=False, error=e,
                            duration=time.perf_counter() - t0,
                            negative=_names_negative(logic_module, description))

    # Observation only, and only on failure.  ``passed`` is already decided.
    # A ``fail`` test whose goal SUCCEEDED has no failing conjunct to find:
    # the conjunct walk would only report that every goal solved.
    if (diagnose and not result.passed
            and not (result.negative and result.error is None)):
        result.diagnostic = diagnose_failure(mod, description, path=path,
                                             error=result.error)
        result.line = result.diagnostic.line
        if path is not None and is_prolog_source(path):
            # The translator keeps no source map: positions are lines of the
            # generated Clausal text, not of the .pl file.  Reporting one as
            # ``file.pl:N`` would point at the wrong clause.
            result.line = None
            result.diagnostic.notes.append(
                "a .pl file is translated before it runs: goals above are "
                "shown in their Clausal translation, and any line numbers "
                "are lines of that translation, not of the .pl source")
    return result


def run_file(path: str | Path) -> FileResults:
    """Load a .clausal/.seam/.pl file and run all its test/1 clauses.

    A load (or ``.pl`` translation) failure is one failing ``<load>`` result,
    never an empty result list."""
    path = str(path)
    results = FileResults(path=path)
    try:
        mod = load_clausal_module(path)
    except Exception as e:
        results.results.append(TestResult(name="<load>", passed=False, error=e))
        return results
    try:
        descs = collect_tests(mod)
    except TestCollectionError as e:
        results.results.append(
            TestResult(name="<collect>", passed=False, error=e))
        return results
    try:
        for desc in descs:
            results.results.append(
                run_test(mod, desc, path=path, diagnose=True))
    finally:
        from clausal.logic.constants import unregister_detached_module
        unregister_detached_module(mod)
    return results


# ── Failure diagnostics ───────────────────────────────────────────────────────


def diagnose_failure(
    mod: object,
    description: str,
    path: str | Path | None = None,
    error: BaseException | None = None,
) -> GoalDiagnostic:
    """Explain *why* a already-failed ``test(description)`` clause failed.

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
        diag.notes.append("could not locate the test/1 clause to analyse")
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
                named = _collect_named(
                    prefix, reified and reified[:failing - 1])
                _report_bindings(diag, prefix, named, failing, path)
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


def _test_entry(logic_module, description):
    """The ``(functor, clause)`` whose description names *description*."""
    for functor, clause in _test_clauses(logic_module):
        desc = _test_description_term(clause, logic_module.db)
        if _test_description_name(desc) == description:
            return functor, clause
    return None


def _test_clause(logic_module, description):
    entry = _test_entry(logic_module, description)
    return None if entry is None else entry[1]


def _test_goal_for_name(logic_module, description):
    """The ``(functor, description TERM)`` whose display name is *description*.

    Falls back to *description* itself when no clause matches, so an
    embedder calling ``run_test`` with a term it built rather than with a
    collected name still reaches its own clause — under ``test/1``, or under
    ``Test/1`` when that is the only spelling the module defines.
    """
    entry = _test_entry(logic_module, description)
    if entry is None:
        db = logic_module.db
        if (db.is_defined(TEST_DEPRECATED_NAME, 1)
                and not db.is_defined(TEST_NAME, 1)):
            return TEST_DEPRECATED_NAME, description, False
        return TEST_NAME, description, False
    functor, clause = entry
    return (functor, _test_description_term(clause, logic_module.db),
            _is_negative(clause))


def _names_negative(logic_module, description) -> bool:
    """True when *description* names a ``test(Name, fail)`` clause."""
    try:
        entry = _test_entry(logic_module, description)
    except Exception:  # noqa: BLE001 - only labels an already-failed result
        return False
    return entry is not None and _is_negative(entry[1])


#: Reifying a file is the same work for every failing test in it, so cache —
#: but a whole-tree run must not accumulate every source file it touched.
_REIFY_CACHE: dict[str, object] = {}
_REIFY_CACHE_MAX = 16


def _reified_clause(path, clause):
    """The reified ``Clause(head, goals, position)`` matching *clause*'s
    position, or ``None``.  Cache shared with :func:`_reified_goals`."""
    if path is None or not clause.position:
        return None
    if is_prolog_source(path):
        # A .pl file is Prolog: reifying it as Clausal source can only fail
        # (re-read and re-parsed per failing test) or, worse, succeed on the
        # wrong language.  Its clause positions are lines of the translation.
        return None
    try:
        from clausal.reflection import Clause as ReifiedClause, reify_file, is_v, vfield

        key = str(path)
        items = _REIFY_CACHE.get(key)
        if items is None:
            items = list(reify_file(key))
            if len(_REIFY_CACHE) >= _REIFY_CACHE_MAX:
                _REIFY_CACHE.pop(next(iter(_REIFY_CACHE)), None)
            _REIFY_CACHE[key] = items
        want = tuple(clause.position)
        for item in items:
            if not is_v(item, ReifiedClause):
                continue
            # vfield with an explicit default, not getattr: a cell has no
            # `.position` attribute, so the getattr default answered None for
            # EVERY item and the position match never fired -- which is how
            # the descent diagnostics lost their source text and printed
            # `(_ > 100)` for `(N > 100)`.
            pos = vfield(item, "position", None)
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
    from clausal.reflection import vfield  # noqa: PLC0415
    item = _reified_clause(path, clause)
    if item is None:
        return None
    try:
        goals = list(vfield(item, "goals") or ())
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
                from clausal.reflection import render_source, is_v, vfield

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


def _report_bindings(diag, prefix, named, failing, path=None) -> None:
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
        diag.bindings.append((name, _render_value(value, path)))
    if not diag.bindings:
        span = "goal 1" if failing == 2 else f"goals 1..{failing - 1}"
        diag.bindings_note = f"(none from {span})"


def _pair_vars(runtime, reified, out) -> bool:
    """Walk a runtime goal term and its reified twin in lockstep.

    Collects ``(source name, runtime Var)`` pairs.  Returns False the moment
    the two shapes disagree — an unnamed binding is worse than none.
    """
    from clausal.logic.predicate import term_field_names
    from clausal.logic.variables import Var
    from clausal.reflection import Atom, Goal, Variable, is_v, vfield
    from clausal.terms import Call, LoadName

    if is_v(reified, Variable):
        # ``isinstance``, not ``is_var``: the latter derefs, so a Var already
        # bound by the prefix would read as "not a variable" and abort the walk.
        if isinstance(runtime, Var):
            out.append((str(vfield(reified, "name")), runtime))
            return True
        return False
    if is_v(reified, Goal):
        if not isinstance(runtime, Call):
            return False
        func = runtime.func
        if isinstance(func, LoadName) and str(func.name) != str(vfield(reified, "name")):
            return False
        args = list(runtime.args or ())
        rargs = list(vfield(reified, "args") or ())
        if len(args) != len(rargs):
            return False
        if not all(_pair_vars(a, r, out) for a, r in zip(args, rargs)):
            return False
        kws = list(runtime.kwargs or ())
        rkws = list(vfield(reified, "kwargs") or ())
        if len(kws) != len(rkws):
            return False
        return all(_pair_vars(k.value, r[1], out) for k, r in zip(kws, rkws))
    if is_v(reified, Atom):
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
            for f in term_field_names(reified)
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
    from clausal.reflection import Goal, Variable, is_v, vfield

    if not is_v(reified_goal, Goal) or str(vfield(reified_goal, "name")) != "forall":
        return None
    rargs = list(vfield(reified_goal, "args") or ())
    if not rargs or not isinstance(rargs[0], in_):
        return None
    left = rargs[0].left
    return str(vfield(left, "name")) if is_v(left, Variable) else None


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
        diag.nearest = _render_nearest(
            goal, reified_goal, kind, i, value, path)
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
            rendered = _render_probe_solution(
                goal, reified_goal, holes, kw_holes, path)
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
    from clausal.logic.predicate import term_field_names
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
        for f in term_field_names(term):
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


def _render_probe_solution(goal, reified_goal, holes, kw_holes,
                            path=None) -> str:
    """One all-holes solution as surface text, holes replaced by their values."""
    from clausal.logic.solve import _deref_walk_py
    from clausal.reflection import Goal, render_source, is_v, vfield

    values = [_deref_walk_py(h) for h in holes]
    kw_values = [(str(k.name), _deref_walk_py(k.value)) for k in kw_holes]
    if is_v(reified_goal, Goal):
        try:
            return render_source(Goal(
                name=vfield(reified_goal, "name"),
                args=[_reify_value(v, path=path) for v in values],
                kwargs=[[n, _reify_value(v, path=path)]
                        for n, v in kw_values],
            ))
        except Exception:  # noqa: BLE001
            pass
    func = getattr(goal, "func", None)
    name = str(func.name) if hasattr(func, "name") else "the predicate"
    parts = [_render_value(v, path) for v in values]
    parts += [f"{n}={_render_value(v, path)}" for n, v in kw_values]
    return f"{name}({', '.join(parts)})"


def _render_nearest(goal, reified_goal, kind, index, value,
                     path=None) -> str:
    """The failing goal with the differing argument replaced by what was computed.

    Preferred form splices the computed value into the *reified* goal and hands
    the result to ``clausal.reflection.render_source``, so the output is real
    ``.clausal`` surface syntax.  Without a reified twin we fall back to naming
    the argument and its value.
    """
    from clausal.reflection import Goal, render_source, is_v, vfield

    if is_v(reified_goal, Goal):
        try:
            reified_value = _reify_value(value, path=path)
            # Show the goal's *other* variables at the values the prefix gave
            # them, so the printed near-miss is a concrete term the reader can
            # diff against the assertion rather than a half-open pattern.
            bound = _bound_reified(goal, reified_goal, path)
            args = [_substitute_bound(a, bound)
                    for a in (vfield(reified_goal, "args") or ())]
            kwargs = [[k[0], _substitute_bound(k[1], bound)]
                      for k in (vfield(reified_goal, "kwargs") or ())]
            if kind == "arg" and index < len(args):
                args[index] = reified_value
            elif kind == "kw" and index < len(kwargs):
                kwargs[index][1] = reified_value
            else:
                raise _Unrenderable("argument index out of range")
            return render_source(Goal(name=vfield(reified_goal, "name"), args=args,
                                      kwargs=kwargs))
        except Exception:  # noqa: BLE001
            pass
    label = f"argument {index + 1}" if kind == "arg" else "keyword argument"
    return f"({label} was actually: {_render_value(value, path)})"


def _bound_reified(goal, reified_goal, path=None) -> dict[str, object]:
    """Source-variable name → reified form of its current binding."""
    from clausal.logic.variables import deref, is_var

    named = _collect_named([goal], [reified_goal])
    bound: dict[str, object] = {}
    for name, var in named or ():
        value = deref(var)
        if is_var(value):
            continue
        try:
            bound[name] = _reify_value(value, path=path)
        except Exception:  # noqa: BLE001
            pass
    return bound


def _substitute_bound(reified, bound):
    """Replace ``Variable(name)`` by ``bound[name]`` throughout a reified term."""
    from clausal.reflection import Goal, Variable, is_v, vfield

    if not bound:
        return reified
    if is_v(reified, Variable):
        return bound.get(str(vfield(reified, "name")), reified)
    if is_v(reified, Goal):
        return Goal(
            name=vfield(reified, "name"),
            args=[_substitute_bound(a, bound) for a in (vfield(reified, "args") or ())],
            kwargs=[[k[0], _substitute_bound(k[1], bound)]
                    for k in (vfield(reified, "kwargs") or ())],
        )
    if isinstance(reified, list):
        return [_substitute_bound(v, bound) for v in reified]
    return reified


# ── Atom-aware near-miss rendering ────────────────────────────────────────
#
# THE FLIP (2026-09-06-atoms-as-cells-strings §6.7) closed this problem
# rather than solving it.  Between the P3-1 atom pivot and the flip an atom
# WAS a ``str``, so a reified term could not tell a former bare atom from a
# genuine quoted string of the same spelling, and this module had to consult
# the source file's own ``-module``/``-private`` directives to guess (a
# lexical-shape guess is wrong for ``gpair("a", 1)``; the process-global
# ``predicate_builtins`` pool is wrong because any earlier-loaded module's
# declaration pollutes it).  An atom is now the arity-0 CELL and a ``str`` is
# a STRING: the SHAPE answers, the guess and its file-scanning helper are
# retired, and ``_atomize_declared_atoms`` keeps only the walk that wraps an
# atom as ``Atom`` (which the renderer prints bare, demangling a ``-hide``
# spelling) and leaves a string to be quoted.
#
# *path* stays in these signatures: it identifies the source file for the
# rest of the diagnostic pipeline that threads it, and nothing here needs to
# churn those call sites to drop an argument.

def _atomize_declared_atoms(reified, path):
    """Recursively rewrap ATOM leaves into ``Atom`` so
    :func:`clausal.reflection.render_source` prints them unquoted — the same
    treatment it already gives a reified ``Atom``.  Applied to reified terms
    that came straight from :func:`clausal.reflection.reify_file` (clause
    heads / leaf goals), which never pass through :func:`_reify_value`.  A
    ``str`` leaf is a STRING and is left to be quoted.  *path* is carried for
    the pipeline's benefit, not read here.  See the module-level note above."""
    from clausal.logic.atoms import is_atom as _term_is_atom, spelling
    from clausal.reflection import Atom, Goal, is_v, vfield

    if _term_is_atom(reified):
        # THE FLIP (2026-09-06-atoms-as-cells-strings §6.7): an atom is the
        # arity-0 CELL, so there is nothing left to guess — the shape says
        # it.  The declared-atom heuristic this branch used to run
        # (which strs did this file declare as atoms?) is retired with the
        # representation that forced it; a plain ``str`` is a STRING and is
        # returned unchanged below, quoted by the renderer.  A hidden
        # (``-hide``) atom needs no separate test either: its MANGLED
        # spelling is in slot 0, and ``_ClauseRenderer``'s Atom branch
        # renders the human ``module.name`` form for it.
        return Atom(name=spelling(reified))
    from clausal.logic.cells import is_chars, chars_text  # noqa: PLC0415
    if is_chars(reified):
        return chars_text(reified)     # STAGE 2: the carrier is the string; a str above is the atom
    if is_v(reified, Goal):
        return Goal(
            name=vfield(reified, "name"),
            args=[_atomize_declared_atoms(a, path)
                  for a in (vfield(reified, "args") or ())],
            kwargs=[[k[0], _atomize_declared_atoms(k[1], path)]
                    for k in (vfield(reified, "kwargs") or ())],
        )
    if isinstance(reified, list):
        return [_atomize_declared_atoms(v, path) for v in reified]
    from clausal.logic.cells import compound_cell_shape  # noqa: PLC0415
    from clausal.reflection import _VOCAB_FIELDS  # noqa: PLC0415
    _is_cell, _functor = compound_cell_shape(reified)
    if _is_cell and _functor in _VOCAB_FIELDS:
        # A reified-vocabulary term is returned UNCHANGED, which is exactly
        # what it got pre-P2: these were INSTANCES then, this function has no
        # dataclass branch, and they fell through to the `return reified` at
        # the bottom.  As CELLS they are tuples, so the generic tuple branch
        # below would walk them -- and every slot of a Variable or an Atom is
        # a bare str, which IS an atom (stage 2), so each one would be rewrapped
        # into a fresh vocabulary `Atom`: ("Variable", "N") became
        # (("Atom", "Variable"), ("Atom", "N")), and the renderer refuses it
        # with "cannot render non-string variable name".  Goal is the one that
        # must be walked, and its branch above does that already.
        return reified
    if isinstance(reified, tuple):
        return tuple(_atomize_declared_atoms(v, path) for v in reified)
    if isinstance(reified, dict):
        return {_atomize_declared_atoms(k, path): _atomize_declared_atoms(v, path)
                for k, v in reified.items()}
    return reified


def _render_value(value, path=None) -> str:
    """A computed runtime value as ``.clausal`` surface text."""
    try:
        from clausal.reflection import render_source, is_v, vfield

        return render_source(_reify_value(value, path=path))
    except Exception:  # noqa: BLE001
        from clausal.terms import term_str

        try:
            return term_str(value)
        except Exception:  # noqa: BLE001
            return repr(value)


def _reify_value(value, depth: int = 0, path=None):
    """Runtime term → reified vocabulary, so ``render_source`` can print it.

    ``reify_*`` maps *source* to reified terms; a value computed at run time
    has no source, so this is the missing edge.  Anything outside the closed
    vocabulary raises rather than emitting something that does not mean what
    it says.
    """
    from clausal.logic.predicate import (
        is_term_instance, term_field_names, field_names_for,
    )
    from clausal.logic.variables import deref, is_var
    from clausal.reflection import Atom, Goal, Variable, is_v, vfield

    if depth > DIAG_MAX_DEPTH:
        raise _Unrenderable("term too deep to render")
    value = deref(value)
    if is_var(value):
        return Variable(name="_")
    if type(value) is str:
        return Atom(name=value)        # STAGE 2: a str is the ATOM
    from clausal.logic.cells import is_chars, chars_text  # noqa: PLC0415
    if is_chars(value):
        return chars_text(value)       # the carrier is the STRING; the renderer quotes a str
    if value is None or isinstance(value, (bool, int, float, complex, bytes)):
        return value
    if isinstance(value, list):
        return [_reify_value(v, depth + 1, path) for v in value]
    from clausal.logic.cells import TUPLE_TAG  # noqa: PLC0415
    if type(value) is tuple and value and type(value[0]) is str and value[0] != TUPLE_TAG:
        # A CELL -- ``("cite", art52)``.  P3-2 Task 2 (THE FLIP): this is how
        # a compound term is represented, so it reifies as a ``Goal`` and
        # prints as ``cite(art52)``.  Rendering it as a bare Python tuple
        # would show the reader a representation detail instead of the term
        # they wrote.  (A tuple whose slot 0 is not a str -- ordinary tuple
        # data, or the ``(tuple, ...)`` data tag -- keeps the tuple form.)
        return Goal(name=value[0],
                    args=[_reify_value(v, depth + 1, path)
                          for v in value[1:]],
                    kwargs=[])
    if isinstance(value, tuple):
        return tuple(_reify_value(v, depth + 1, path) for v in value)
    if field_names_for(value) is not None:
        return Atom(name=value.__name__)
    if is_term_instance(value):
        return Goal(name=type(value).__name__,
                    args=[_reify_value(getattr(value, f), depth + 1, path)
                          for f in term_field_names(value)],
                    kwargs=[])
    if isinstance(value, dict):
        return {k: _reify_value(v, depth + 1, path)
                for k, v in value.items()}
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
        lines.append(
            f"  {_descent_leaf_line(leaf, reified_leaf, _NO_CLAUSE, path)}")
        for name, value in _leaf_bindings(leaf, reified_leaf, path):
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
        from clausal.reflection import Clause as ReifiedClause, Goal, reify_file, is_v, vfield

        key = str(path)
        items = _REIFY_CACHE.get(key)
        if items is None:
            items = list(reify_file(key))
            if len(_REIFY_CACHE) >= _REIFY_CACHE_MAX:
                _REIFY_CACHE.pop(next(iter(_REIFY_CACHE)), None)
            _REIFY_CACHE[key] = items

        def find(node):
            from clausal.reflection import is_v  # noqa: PLC0415
            if (is_v(node, Goal) and str(vfield(node, "name")) == "findall"
                    and len(vfield(node, "args") or ()) == 3):
                inner = vfield(node, "args")[1]
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
            if not is_v(item, ReifiedClause):
                continue
            # vfield, not getattr-with-a-default: a reified Clause is a CELL
            # and has no `.position` attribute, so the default answered for
            # EVERY item, `owner` stayed None, and this fell back to the
            # whole-file walk -- which returns whichever findall the FILE
            # opens with rather than the one in the owning clause.  That is
            # precisely the misattribution the owner search exists to prevent.
            cpos = vfield(item, "position", None)
            if (isinstance(cpos, (tuple, list)) and cpos
                    and cpos[0] <= goal_line
                    and (owner is None
                         or cpos[0] > vfield(owner, "position")[0])):
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
    from clausal.reflection import _VOCAB_FIELDS  # noqa: PLC0415
    from clausal.logic.cells import compound_cell_shape  # noqa: PLC0415

    _is_cell, _functor = compound_cell_shape(node)
    if _is_cell and _functor in _VOCAB_FIELDS:
        # P2: a reified vocabulary term IS a tuple now, so the conjunction
        # branch below would flatten a Goal's own SLOTS into separate
        # "leaves" and `flat[index]` would pick one out -- which is how a
        # collapse leaf came to render as the bare functor (`between`) where
        # the whole goal (`usable(L)`) belongs.  A vocabulary cell is ONE
        # leaf; only a genuine comma-conjunction tuple is flattened.
        out.append(node)
    elif isinstance(node, tuple):
        for e in node:
            _flatten_reified(e, out)
    else:
        out.append(node)


def _is_vocabulary_cell(node) -> bool:
    """Is *node* one of clausal.reflection's nine reified-vocabulary cells?

    P2 made every one of them a tuple, so the generic "is this a tuple?"
    branches that predate the flip now catch them and walk their slots as if
    they were data. Three walkers in this file needed this test."""
    from clausal.reflection import _VOCAB_FIELDS  # noqa: PLC0415
    from clausal.logic.cells import compound_cell_shape  # noqa: PLC0415

    is_cell, functor = compound_cell_shape(node)
    return is_cell and functor in _VOCAB_FIELDS


def _reified_children(node):
    """Immediate reified sub-nodes worth recursing into for the findall search."""
    from clausal.reflection import Clause, Goal, is_v, vfield

    if is_v(node, Clause):
        yield from (vfield(node, "goals") or ())
    elif is_v(node, Goal):
        yield from (vfield(node, "args") or ())
        for kw in (vfield(node, "kwargs") or ()):
            yield kw[1]
    elif _is_vocabulary_cell(node):
        # P2: the other seven vocabulary terms ARE tuples, so the generic
        # branch below would yield their own SLOTS as candidate goal nodes --
        # a Variable's name, an Atom's spelling.  They carry no goal children;
        # Clause and Goal, which do, are handled above.
        return
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


def _goal_arity(goal) -> "int | None":
    """How many arguments *goal* passes, or ``None`` when a ``*args`` /
    ``**kwargs`` splat makes that unknowable before the call runs."""
    from clausal.pythonic_ast.nodes import StarUnpack  # noqa: PLC0415

    args = list(getattr(goal, "args", None) or ())
    kwargs = list(getattr(goal, "kwargs", None) or ())
    if any(isinstance(a, StarUnpack) for a in args):
        return None
    if any(getattr(kw, "name", None) is None for kw in kwargs):
        return None
    return len(args) + len(kwargs)


def _resolve_predicate(goal, logic_module, caller_path):
    """``goal.func``'s name → ``(PredRow, defining module, source path)``.

    Resolved to the ROW, at the goal's own arity, so nothing here depends on
    what a module-dict binding looks like (F1 row 4: it used to read a
    ``PredicateMeta`` class's ``_row``/``__module__``, which after the
    retirement flip would resolve nothing and silently drop the descent
    section from every failing ``.clausal`` test).

    Resolution order: the caller's own database under the exact (possibly
    dotted) name -- local predicates and ``-import_from`` adopted rows both
    answer there; then, for a dotted name, the prefix module's database under
    the last segment; then the caller's database under the bare last segment.
    Each candidate is taken only if it has clauses.  A clause body's own
    names resolve in the module that DEFINED the clause, so the defining
    module is returned alongside -- read off ``row.db``, never
    ``sys.modules``: ``load_clausal_module`` pops the test module from
    ``sys.modules`` after loading, so that route was a dead end for every
    predicate a test module defines.
    """
    from clausal.terms import LoadName

    func = getattr(goal, "func", None)
    if not isinstance(func, LoadName):
        return None
    arity = _goal_arity(goal)
    if arity is None:
        return None
    name = str(func.name)
    db = getattr(logic_module, "db", None)
    candidates = []
    if db is not None:
        candidates.append(db.row(name, arity))
    if "." in name:
        prefix, last = name.rsplit(".", 1)
        # The prefix module as the CALLER bound it (``-import_module`` puts
        # the module object in its dict) before ``sys.modules``, which the
        # runner empties of what it loads.
        md = getattr(logic_module, "module_dict", None) or {}
        prefix_mod = md.get(prefix)
        if not hasattr(prefix_mod, "__dict__"):
            prefix_mod = sys.modules.get(prefix)
        prefix_lm = getattr(prefix_mod, "__dict__", {}).get("$module") if prefix_mod else None
        prefix_db = getattr(prefix_lm, "db", None)
        if prefix_db is not None:
            candidates.append(prefix_db.row(last, arity))
        if db is not None:
            # The bare last segment in the caller's database -- an
            # ``-import_from`` of the prefix module lands there -- but ONLY
            # as the prefix module's own row: a local predicate that merely
            # shares the bare name is a different predicate.
            bare = db.row(last, arity)
            if bare is not None and (bare.db is prefix_db
                                     or bare.db.module_name() == prefix):
                candidates.append(bare)
    for row in candidates:
        if row is None or row.detached or not row.clauses:
            continue
        if db is not None and row.db is db:
            return row, logic_module, caller_path
        owner_md = row.db.module_dict if isinstance(row.db.module_dict, dict) else {}
        def_lm = owner_md.get("$module")
        return row, (def_lm or logic_module), owner_md.get("__file__")
    return None


def _head_prefix(head, goal):
    """``Unify(head_arg, goal_arg)`` goals matching *goal* onto *head*, or
    ``None`` when the shapes cannot correspond (arity or keyword mismatch)."""
    from clausal.logic.predicate import term_field_names
    from clausal.pythonic_ast.nodes import Unify

    args = list(goal.args or ())
    kwargs = list(goal.kwargs or ())
    from clausal.logic.cells import _cell_shape, cell_args  # noqa: PLC0415
    if hasattr(head, "args"):
        hargs, names = list(head.args), None
    elif _cell_shape(head)[0]:                      # P2: a head is a cell
        hargs, names = list(cell_args(head)), None
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
    row, sub_lm, sub_path = resolved
    # The row's IDENTITY, not a module-name spelling: two live databases can
    # carry the same module name (a test module reloaded under its name), and
    # a row is keyed per database.  ``seen`` lives for one descent, so the
    # ``id`` cannot be recycled under it.
    key = (id(row.db), row.key)
    if key in seen:
        return [], "none"
    seen = seen | {key}
    clauses = list(row.clauses)          # non-empty: filtered on it above
    total = len(clauses)
    if total > DIAG_MAX_DESCENT_CLAUSES:
        notes.append(
            f"descent walked only the first {DIAG_MAX_DESCENT_CLAUSES} of "
            f"{total} clauses of {row.key[0]}"
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
        return _head_listing(row, clauses, path=sub_path), "head_listing"
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
    from clausal.reflection import vfield  # noqa: PLC0415
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
    rgoals = list(vfield(reified, "goals") or ()) if reified is not None else None
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
                for name, value in _leaf_bindings(leaf, reified_leaf, path):
                    lines.append(f"    {name} = {value}")
                lines.append("    no clause head unifies with these arguments; "
                             "the heads are:")
                lines.extend(f"      {line}" for line in deeper)
                return [lines], "leaves"
            # "none" falls through to render this conjunct as the leaf.
        lines = [_descent_leaf_line(leaf, reified_leaf, clause, path)]
        for name, value in _leaf_bindings(leaf, reified_leaf, path):
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


def _head_listing(row, clauses, path) -> list[str]:
    """One ``file:line  <head source>`` line per clause, source-faithful."""
    lines = []
    label = os.path.basename(str(path)) if path else row.db.module_name()
    for clause in clauses:
        text = None
        reified = _reified_clause(path, clause)
        if reified is not None:
            try:
                from clausal.reflection import render_source, is_v, vfield

                text = render_source(_atomize_declared_atoms(vfield(reified, "head"), path))
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
            from clausal.reflection import render_source, is_v, vfield

            text = render_source(_atomize_declared_atoms(reified_leaf, path))
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


def _leaf_bindings(leaf, reified_leaf, path=None) -> list[tuple[str, str]]:
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
            out.append((name, _render_value(value, path)))
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


#: How a ``test(Name, fail)`` clause whose goal had a solution is reported.
NEGATIVE_SUCCEEDED = ("test(..., fail) succeeded: its goal has a solution, "
                      "and a `fail` test passes only when it has none")


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
    elif result.negative:
        header = lines[0] = f"{header} — {NEGATIVE_SUCCEEDED}"
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


#: Why a scan passed over a file (``main`` reports each one).
SKIP_UNSUPPORTED = "unsupported suffix"
SKIP_NO_TESTS = "no test/1 clauses"
SKIP_NO_COLLECT = "no-collect marker"
SKIP_CONFTEST_IGNORE = "ignored by conftest.py"

#: A test-file-typed file that is DATA, not tests (a fixture meant to fail at
#: load, a grammar spec), opts out of collection by carrying this line within
#: its first 30 lines.  A .pl file spells it with Prolog's comment character.
#: Both runners honour it: the CLI (``discover_clausal_files``) and the
#: pytest plugin (the root ``conftest.py``).
NO_COLLECT_MARKER = "# clausal: no-collect"
NO_COLLECT_MARKER_PL = "% clausal: no-collect"


def opts_out_of_collection(path: str | Path) -> bool:
    """True if a test file carries the no-collect marker in its first 30
    lines (``# clausal: no-collect``; ``% clausal: no-collect`` in .pl)."""
    path = Path(path)
    marker = (NO_COLLECT_MARKER_PL if is_prolog_source(path)
              else NO_COLLECT_MARKER)
    try:
        with path.open(encoding="utf-8") as fh:
            for _, line in zip(range(30), fh):
                if line.strip() == marker:
                    return True
    except (OSError, UnicodeDecodeError):
        # Unreadable or not UTF-8: let the loader report it as a <load>
        # failure rather than skipping the file silently.
        return False
    return False
#: A skipped-file list at most this long is printed in full without ``-v``;
#: a longer one is a single count line unless ``-v`` is given.
SKIPPED_LIST_INLINE_MAX = 5


def _is_scan_noise(path: Path, root: Path) -> bool:
    """True for files under a hidden directory or ``__pycache__`` (or hidden
    files): never test files a reader would expect a report about."""
    try:
        parts = path.relative_to(root).parts
    except ValueError:  # pragma: no cover — rglob yields paths under root
        return False
    return any(part.startswith(".") or part == "__pycache__" for part in parts)


def _conftest_ignores(directory: Path) -> tuple[list[Path], list[str]]:
    """The ``collect_ignore`` paths and ``collect_ignore_glob`` patterns a
    ``conftest.py`` in *directory* gives the pytest plugin, anchored at
    *directory* the way pytest anchors them.

    Read, never executed: only a top-level ``x = [...]``, ``x: T = [...]``
    or ``x += [...]`` with a LITERAL list (or tuple) is understood, via
    ``ast.literal_eval``.  Running a conftest to
    compute its lists would import pytest and whatever else it imports into a
    CLI run that does not use pytest; every in-repo conftest that sets these
    names sets them to literals.  A computed value is not read (that
    conftest's exclusions then apply under pytest only).
    """
    conftest = directory / "conftest.py"
    if not conftest.is_file():
        return [], []
    import ast  # noqa: PLC0415 -- only a directory scan with a conftest needs it
    try:
        tree = ast.parse(conftest.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, SyntaxError, ValueError):
        return [], []
    lists: dict[str, list[str]] = {"collect_ignore": [],
                                   "collect_ignore_glob": []}
    for node in tree.body:
        # ``x = [...]``, ``x: list[str] = [...]`` and ``x += [...]``, at top
        # level; anything else (a conditional append, a computed value) is
        # not read.
        if isinstance(node, ast.Assign) and len(node.targets) == 1:
            target, extend = node.targets[0], False
        elif isinstance(node, ast.AnnAssign) and node.value is not None:
            target, extend = node.target, False
        elif isinstance(node, ast.AugAssign) and isinstance(node.op, ast.Add):
            target, extend = node.target, True
        else:
            continue
        if not (isinstance(target, ast.Name) and target.id in lists):
            continue
        try:
            value = ast.literal_eval(node.value)
        except (ValueError, TypeError, SyntaxError, MemoryError,
                RecursionError):
            continue
        if not isinstance(value, (list, tuple)):
            continue
        entries = [v for v in value if isinstance(v, str)]
        if extend:
            lists[target.id].extend(entries)
        else:
            lists[target.id] = entries
    return ([directory / e for e in lists["collect_ignore"]],
            [str(directory / e) for e in lists["collect_ignore_glob"]])


def _ignored_by_conftests(path: Path, root: Path,
                          cache: dict | None = None) -> bool:
    """True when a ``conftest.py`` at or below *root*, in *path*'s directory
    or one of its ancestors, excludes *path* from pytest collection.

    Pytest's rules: a ``collect_ignore`` entry names a file or directory
    relative to its conftest (a directory excludes everything under it); a
    ``collect_ignore_glob`` pattern is joined to the conftest's directory and
    matched with ``fnmatch`` against the full path (so ``*`` crosses ``/``),
    and a match on a directory excludes everything under it too.

    *cache* (directory -> parsed lists) spares re-reading one conftest per
    file of a scan.
    """
    import fnmatch  # noqa: PLC0415

    if cache is None:
        cache = {}

    directory = path.parent
    candidates = [path]
    while True:
        if directory not in cache:
            cache[directory] = _conftest_ignores(directory)
        paths, globs = cache[directory]
        for candidate in candidates:
            if any(candidate == ignored for ignored in paths):
                return True
            text = str(candidate)
            if any(fnmatch.fnmatch(text, pattern) for pattern in globs):
                return True
        if directory == root or directory.parent == directory:
            return False
        candidates.append(directory)
        directory = directory.parent


def discover_clausal_files(
    roots: list[str | Path],
    skipped: list[tuple[Path, str]] | None = None,
) -> Iterator[Path]:
    """Yield all test files (.clausal, .seam and .pl) under the given roots.

    All extensions are walked as one population, in path order, so a
    directory holding files under several spellings reports them interleaved
    rather than one extension after the other.

    A test-typed file carrying the no-collect marker
    (:func:`opts_out_of_collection`) is not yielded.  Nor, in a DIRECTORY
    scan, is a file a ``conftest.py`` at or below that directory excludes
    through ``collect_ignore``/``collect_ignore_glob``
    (:func:`_ignored_by_conftests`), so the CLI and the pytest plugin skip
    the same files.  As in pytest, a file named explicitly as a root is
    not subject to the conftest lists.

    When *skipped* is a list, every other file the scan passes over is
    appended to it as ``(path, reason)`` — except files under a hidden
    directory or ``__pycache__``, which are noise, not candidates.
    """
    conftest_cache: dict = {}

    def classify(p: Path, scan_root: Path | None = None) -> str | None:
        if p.suffix not in TEST_SUFFIXES:
            return SKIP_UNSUPPORTED
        if (scan_root is not None
                and _ignored_by_conftests(p, scan_root, conftest_cache)):
            return SKIP_CONFTEST_IGNORE
        if opts_out_of_collection(p):
            return SKIP_NO_COLLECT
        return None

    for root in roots:
        root = Path(root)
        if root.is_file():
            reason = classify(root)
            if reason is None:
                yield root
            elif skipped is not None:
                skipped.append((root, reason))
        elif root.is_dir():
            files = sorted(p for p in root.rglob("*") if p.is_file())
            for p in files:
                reason = classify(p, root)
                if reason is None:
                    yield p
                elif skipped is not None and not _is_scan_noise(p, root):
                    skipped.append((p, reason))


def _skipped_lines(skipped: list[tuple[Path, str]], verbose: bool) -> list[str]:
    """The report block naming files a run collected nothing from."""
    if not skipped:
        return []
    counts: dict[str, int] = {}
    for _path, reason in skipped:
        counts[reason] = counts.get(reason, 0) + 1
    breakdown = ", ".join(f"{reason}: {n}" for reason, n in counts.items())
    head = f"{len(skipped)} file(s) skipped ({breakdown})"
    if not verbose and len(skipped) > SKIPPED_LIST_INLINE_MAX:
        return [f"{head}; -v lists them"]
    return [f"{head}:"] + [
        f"  {os.path.relpath(path)}  ({reason})"
        for path, reason in sorted(skipped, key=lambda e: str(e[0]))
    ]


# ── CLI ───────────────────────────────────────────────────────────────────────


def main(args: list[str] | None = None) -> int:
    """Run .clausal/.seam/.pl tests from the command line. Returns exit code.

    Exit codes: ``EXIT_OK`` (0) every collected test passed;
    ``EXIT_TESTS_FAILED`` (1) a test failed or a file failed to load or
    translate; ``EXIT_USAGE`` (2) a path does not exist or names a file of an
    unsupported type; ``EXIT_NO_TESTS`` (5) no test/1 clause was collected —
    an empty scan is an error by default, because a mistyped root or a
    renamed extension otherwise reads as a green run.  ``--allow-empty`` maps
    5 to 0 for callers that genuinely expect an empty directory.
    """
    import argparse

    parser = argparse.ArgumentParser(
        description="Run test/1 clauses in .clausal (or .seam) files and in "
                    "Prolog .pl files",
        epilog="exit status: 0 passed, 1 a test failed or a file failed to "
               "load, 2 usage error, 5 no tests collected (see --allow-empty)",
    )
    parser.add_argument("paths", nargs="+",
                        help=".clausal, .seam or .pl files, or directories")
    parser.add_argument("-v", "--verbose", action="store_true",
                        help="Show individual test results and every "
                             "skipped file")
    empty = parser.add_mutually_exclusive_group()
    empty.add_argument("--allow-empty", action="store_true",
                       help="Exit 0 instead of 5 when no test/1 clauses are "
                            "collected")
    empty.add_argument("--strict", "--fail-on-empty", dest="strict",
                       action="store_true",
                       help="Exit non-zero (5) when no test/1 clauses are "
                            "collected; this is now the default, the flag is "
                            "kept for compatibility")
    parsed = parser.parse_args(args)

    # Validate paths up front so a mistyped path or wrong cwd is an error, not a
    # silently-green run.  A non-existent path, or a file that exists but is not
    # a test file type, is reported and forces a non-zero exit.
    bad_paths: list[str] = []
    for path in parsed.paths:
        p = Path(path)
        if not p.exists():
            bad_paths.append(f"no such file or directory: {path}")
        elif p.is_file() and p.suffix not in TEST_SUFFIXES:
            bad_paths.append(f"not a .clausal, .seam or .pl file: {path}")
    if bad_paths:
        for msg in bad_paths:
            print(f"error: {msg}", file=sys.stderr)
        return EXIT_USAGE

    total_passed = 0
    total_failed = 0
    files_seen = 0
    failures: list[tuple[str, TestResult]] = []
    skipped: list[tuple[Path, str]] = []

    for path in discover_clausal_files(parsed.paths, skipped=skipped):
        files_seen += 1
        file_results = run_file(path)
        rel = os.path.relpath(file_results.path)
        if not file_results.results:
            # Loaded cleanly but holds no test/1 clause (a load failure is a
            # ``<load>`` result, never an empty list).
            skipped.append((path, SKIP_NO_TESTS))

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

    for line in _skipped_lines(skipped, parsed.verbose):
        print(line)

    total = total_passed + total_failed

    # Distinguish "nothing to run" from "everything passed": files that exist but
    # contain no test/1 clauses (or roots with no test files at all) would
    # otherwise print a misleading [PASSED] — and exit 0 in a gate.
    if total == 0:
        if files_seen == 0:
            print("no test files (.clausal, .seam or .pl) found")
        else:
            print(f"{files_seen} file(s) collected, but no test/1 clauses found")
        if parsed.allow_empty:
            print("0 tests [NO TESTS] (allowed by --allow-empty)")
            return EXIT_OK
        print(f"0 tests [NO TESTS] (exit {EXIT_NO_TESTS}; "
              "pass --allow-empty to accept an empty run)")
        return EXIT_NO_TESTS

    status = "PASSED" if total_failed == 0 else "FAILED"
    print(f"{total} tests: {total_passed} passed, {total_failed} failed [{status}]")
    return EXIT_OK if total_failed == 0 else EXIT_TESTS_FAILED


if __name__ == "__main__":
    sys.exit(main())
