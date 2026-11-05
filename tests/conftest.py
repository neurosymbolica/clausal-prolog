"""Fixtures shared by test files under ``tests/`` that opt in to them."""
from __future__ import annotations

import os
import sys

import pytest

#: CPython's default recursion limit, which the depth-sensitive tests are
#: written against.
DEFAULT_RECURSION_LIMIT = 1000


@pytest.fixture
def default_recursion_limit():
    """Run the test at CPython's default recursion limit, then put back
    whatever limit was in force.

    Importing IPython (or jedi) raises the limit to 3000 for the rest of the
    process.  The whole suite runs in one process, so a test that sizes its
    input against the default (a body deep enough to be refused, not one
    that merely loads) would otherwise pass or fail by the order the files
    run in.  A file opts in with
    ``pytestmark = pytest.mark.usefixtures("default_recursion_limit")``."""
    before = sys.getrecursionlimit()
    sys.setrecursionlimit(DEFAULT_RECURSION_LIMIT)
    try:
        yield
    finally:
        sys.setrecursionlimit(before)


# The predicate compiler's whole-function invariant walks are off by default
# (they cost a pass over every compiled function); the suite runs them, here
# and in the processes it starts.
os.environ.setdefault("CLAUSAL_CHECK_COMPILED_FUNCTIONS", "1")
from clausal.logic.compiler import invariants as _compiler_invariants  # noqa: E402

_compiler_invariants.CHECK_COMPILED_FUNCTIONS = (
    os.environ["CLAUSAL_CHECK_COMPILED_FUNCTIONS"] not in ("", "0"))


# ── the SIGALRM tripwire ────────────────────────────────────────────────────
#
# An ITIMER_REAL left armed while SIGALRM's handler is SIG_DFL ends the whole
# pytest process at its expiry, silently ("Alarm clock": no traceback, no
# summary), wherever the run has got to.  This checks after EVERY test that
# no timer is armed without a Python handler, and that no time limit
# (clausal.logic.time_limit) is left live while the handler is not its own,
# and fails the test that left it -- named -- after disarming, so the run
# goes on.  Two system calls per test.

import signal as _signal  # noqa: E402


def _alarm_hazard():
    tl = sys.modules.get("clausal.logic.time_limit")
    if tl is not None:
        return tl.alarm_hazard()
    if not hasattr(_signal, "SIGALRM"):
        return None
    value, interval = _signal.getitimer(_signal.ITIMER_REAL)
    handler = _signal.getsignal(_signal.SIGALRM)
    if (value or interval) and not callable(handler):
        return (f"ITIMER_REAL is armed ({value:.3f} s, interval "
                f"{interval:.3f} s) while the SIGALRM handler is {handler!r}")
    return None


@pytest.fixture(autouse=True)
def _sigalrm_tripwire(request):
    yield
    hazard = _alarm_hazard()
    if hazard is None:
        return
    _signal.setitimer(_signal.ITIMER_REAL, 0)
    tl = sys.modules.get("clausal.logic.time_limit")
    if tl is not None:
        tl._drop_orphans()
    pytest.fail(f"{request.node.nodeid} left a SIGALRM hazard: {hazard}",
                pytrace=False)
