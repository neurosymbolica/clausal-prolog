"""Where the clp(q,r) example programs the CLP(Q) port tests read live.

The programs (the 1.3.3 distribution's examples, filled_rectangle.pl, the
SICStus 3.7.1 manual chapter) are outside the licence acceptance that
covers the 1.3.3 sources, so they are never copied into this repository:
the tests read them at test time from ``CLAUSAL_CLPQ_EXAMPLES_DIR``
(default ``/workspace/claude_sicstus_clpq``) and skip where one is absent.

A skip for an absent file is easy to miss, so ``CLAUSAL_REQUIRE_CLPQ_EXAMPLES=1``
turns it into a failure (tests/clpq_port/test_manual_examples.py,
test_a_missing_example_file_fails_when_required).
"""
import os
import pathlib

import pytest

DEFAULT_DIR = "/workspace/claude_sicstus_clpq"


def examples_dir() -> pathlib.Path:
    return pathlib.Path(os.environ.get("CLAUSAL_CLPQ_EXAMPLES_DIR", DEFAULT_DIR))


def example_file(name: str) -> pathlib.Path:
    """The example file *name*, or a skip (a failure when
    CLAUSAL_REQUIRE_CLPQ_EXAMPLES=1) when it is absent."""
    path = examples_dir() / name
    if not path.exists():
        if os.environ.get("CLAUSAL_REQUIRE_CLPQ_EXAMPLES") == "1":
            pytest.fail(f"CLAUSAL_REQUIRE_CLPQ_EXAMPLES=1 and {path} is absent "
                        f"(CLAUSAL_CLPQ_EXAMPLES_DIR names its directory)",
                        pytrace=False)
        pytest.skip(f"needs {path} (set CLAUSAL_CLPQ_EXAMPLES_DIR to its "
                    f"directory; CLAUSAL_REQUIRE_CLPQ_EXAMPLES=1 makes this "
                    f"a failure)")
    return path
