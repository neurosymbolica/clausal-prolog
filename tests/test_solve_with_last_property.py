"""Property: a solution reported LAST is the last one -- over a broad set of
goals, the test programs in ``tests/fixtures`` and ``clausal/examples``.

For every predicate of every program that loads, the most general goal
``p(_, ..., _)`` (and ``test(_)``, which runs a program's whole test suite
as one goal) is run twice:

- with FINAL enabled, recording each answer and its ``last`` flag
  (``solve_with_last``);
- with FINAL disabled in the drive core (``set_final_enabled(False)``: every
  FINAL is read as a plain answer, so nothing retires and every search runs
  to its exhaustion the old way), recording each answer.

The answers must be the same, and only the last one may carry
``last=True``: a FINAL that came too early would have stopped the first run
short.  A goal whose answers differ between two runs with FINAL disabled
(it reads or writes global state) is skipped, as is one that errors, runs
out of time or recursion depth.  Infinite enumerations are cut at LIMIT
answers on both sides.
"""

from __future__ import annotations

import contextlib
import io
import itertools
import signal
import time
from pathlib import Path

import pytest

import clausal.import_hook  # noqa: F401 -- installs the meta-path finder
from clausal.import_hook import _load_module
from clausal.logic.solve import solve_with_last, module_signatures
from clausal.logic.trampoline import set_final_enabled
from clausal.logic.variables import Var, deref
from clausal.terms import term_writeq
from clausal._suffixes import SOURCE_SUFFIXES

_ROOT = Path(__file__).resolve().parent.parent
LIMIT = 25
TIMEOUT = 0.5
BUDGET = 15.0          # seconds per program


class _Timeout(BaseException):  # not routable: no catch/3 can swallow it
    pass


def _alarm(_signum, _frame):
    raise _Timeout


def _programs():
    files = []
    for d in (_ROOT / "tests" / "fixtures", _ROOT / "clausal" / "examples"):
        for p in sorted(d.iterdir()):
            if p.suffix in SOURCE_SUFFIXES and p.is_file():
                head = p.read_text(errors="replace").splitlines()[:30]
                if any("clausal: no-collect" in line for line in head):
                    continue
                files.append(p)
    return files


def _answers(module, name, arity):
    """``[(answer, last)]`` of ``name(_, ..., _)``, at most LIMIT."""
    vs = [Var() for _ in range(arity)]
    goal = (name, *vs) if vs else name
    out = []
    for _t, last in itertools.islice(solve_with_last(goal, module), LIMIT):
        out.append((tuple(term_writeq(deref(v), local_vars=True)
                          for v in vs), last))
    return out


def _run(module, name, arity, enabled):
    set_final_enabled(enabled)
    old = signal.signal(signal.SIGALRM, _alarm)
    signal.setitimer(signal.ITIMER_REAL, TIMEOUT)
    try:
        with contextlib.redirect_stdout(io.StringIO()), \
                contextlib.redirect_stderr(io.StringIO()):
            return _answers(module, name, arity)
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, old)
        set_final_enabled(True)


def _check_program(path):
    """``(goals checked, goals with a last answer, failures)``."""
    try:
        with contextlib.redirect_stdout(io.StringIO()), \
                contextlib.redirect_stderr(io.StringIO()):
            module = _load_module(f"_lastprop_{path.stem}_{abs(hash(path))}",
                                  str(path))
        sigs = module_signatures(module)
    except BaseException as exc:  # noqa: BLE001 -- a program that will not load
        if isinstance(exc, KeyboardInterrupt):
            raise
        return 0, 0, []
    checked = with_last = 0
    failures = []
    start = time.monotonic()
    for name, arities in sigs.items():
        for arity in sorted(arities):
            if time.monotonic() - start > BUDGET:
                return checked, with_last, failures
            try:
                plain = _run(module, name, arity, False)
                marked = _run(module, name, arity, True)
                again = _run(module, name, arity, False)
            except KeyboardInterrupt:
                raise
            except BaseException:  # noqa: BLE001 -- errors, time, depth
                continue
            if plain != again:
                continue                    # global state: not comparable
            checked += 1
            got = [a for a, _last in marked]
            want = [a for a, _last in plain]
            lasts = [last for _a, last in marked]
            if any(lasts):
                with_last += 1
            if got != want or any(lasts[:-1]):
                failures.append(
                    f"{path.name}: {name}/{arity}: answers {got} "
                    f"last {lasts}, without FINAL {want}")
    return checked, with_last, failures


_TOTALS = {"checked": 0, "last": 0}

# Each program runs in a child process: a most general goal can loop in C
# (out of reach of SIGALRM) or eat memory, and a program's global state
# must not leak into the next one.
_CHILD = """
import json, resource, sys
resource.setrlimit(resource.RLIMIT_AS, (3 << 30, 3 << 30))
sys.setrecursionlimit(20000)
from pathlib import Path
from tests.test_solve_with_last_property import _check_program
checked, with_last, failures = _check_program(Path(sys.argv[1]))
print("RESULT " + json.dumps([checked, with_last, failures]))
"""


@pytest.mark.parametrize("path", _programs(), ids=lambda p: p.name)
def test_a_last_answer_is_the_last(path):
    import json
    import subprocess
    import sys
    try:
        proc = subprocess.run(
            [sys.executable, "-c", _CHILD, str(path)], cwd=_ROOT,
            capture_output=True, text=True, timeout=120)
    except subprocess.TimeoutExpired:
        pytest.skip("the program's goals did not finish in time")
    lines = [ln for ln in proc.stdout.splitlines() if ln.startswith("RESULT ")]
    if not lines:
        pytest.skip(f"the child did not report (exit {proc.returncode})")
    checked, with_last, failures = json.loads(lines[-1][len("RESULT "):])
    _TOTALS["checked"] += checked
    _TOTALS["last"] += with_last
    assert not failures, "\n".join(failures)


def test_the_property_was_not_vacuous():
    """Runs after the programs (file order): hundreds of goals ran, and many
    reported a last answer."""
    if _TOTALS["checked"] == 0:
        pytest.skip("run with the per-program cases")
    print(f"goals checked: {_TOTALS['checked']}, "
          f"with a last answer: {_TOTALS['last']}")
    assert _TOTALS["checked"] > 300, _TOTALS
    assert _TOTALS["last"] > 100, _TOTALS
