"""Fixtures shared by test files under ``tests/`` that opt in to them."""
from __future__ import annotations

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
