"""Smoke-test an INSTALLED clausal: what a user gets from ``pip install``.

Run against a built wheel (the release workflow's cibuildwheel test step
does this on every platform), from outside the source tree::

    python tools/wheel_smoke.py

It checks what a missing data file or extension would break: the C
extensions import; the ``clausal`` command runs a Clausal Prolog program
(``-g`` with a CLP(Z) goal, ``main/0``, ``--test``); a ``library(...)``
facade loads (``.seam`` files shipped); and an ISO ``.pl`` program runs.
Exits non-zero, naming the check, on the first failure.
"""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import textwrap

PROGRAM = textwrap.dedent("""\
    :- module(smoke, [fib/2]).
    :- use_module(library(clpz)).
    :- use_module(library(datetime), [date_add/3, timedelta/3]).

    fib(0, 0).
    fib(1, 1).
    fib(N, F) :-
        N #> 1,
        N1 #= N - 1, N2 #= N - 2,
        F #= F1 + F2,
        fib(N1, F1), fib(N2, F2).

    due(D) :- timedelta(30, 0, TD), date_add(date(2026, 1, 15), TD, D).

    main :- fib(10, F), write(F), nl.

    test("fib(10) = 55") :- fib(10, 55).

    :- end_module(smoke).
""")

ISO = "len([], 0).\nlen([_|T], N) :- len(T, M), N is M + 1.\n"


def check(name: str, argv: list[str], cwd: str, want: str) -> None:
    r = subprocess.run([sys.executable, "-m", "clausal", *argv], cwd=cwd,
                       capture_output=True, text=True, timeout=300)
    if r.returncode != 0 or want not in r.stdout:
        sys.exit(f"FAIL {name}: exit {r.returncode}\nstdout: {r.stdout}\n"
                 f"stderr: {r.stderr}")
    print(f"ok   {name}")


def main() -> None:
    import clausal
    from clausal.logic.variables import _variables  # noqa: F401  C extension
    from clausal.logic.runtime import _trampoline  # noqa: F401   C extension
    print(f"ok   import clausal from {os.path.dirname(clausal.__file__)}")
    with tempfile.TemporaryDirectory() as d:
        with open(os.path.join(d, "smoke.clausal"), "w") as f:
            f.write(PROGRAM)
        with open(os.path.join(d, "count.pl"), "w") as f:
            f.write(ISO)
        check("main/0", ["smoke.clausal"], d, "55\n")
        check("-g with CLP(Z)", ["-g", "X #= 6 * 7", "smoke.clausal"], d,
              "X = 42.")
        check("library(datetime) facade", ["-g", "due(D)", "smoke.clausal"],
              d, "D = date(2026,2,14).")
        check("--test", ["--test", "smoke.clausal"], d, "1 passed")
        check("ISO .pl program", ["-g", "len([a, b], N)", "count.pl"], d,
              "N = 2.")
    print("wheel smoke test passed")


if __name__ == "__main__":
    main()
