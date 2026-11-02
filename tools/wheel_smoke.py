"""Smoke-test an INSTALLED clausal: what a user gets from ``pip install``.

Run against a built wheel (the release workflow's cibuildwheel test step
does this on every platform), from outside the source tree::

    python tools/wheel_smoke.py

It checks what a missing data file or extension would break: the C
extensions import; the ``clausal`` command runs a Clausal Prolog program
(``-g`` with a CLP(Z) goal, ``main/0``, ``--test``); a ``library(...)``
facade loads (``.seam`` files shipped); an ISO ``.pl`` program runs; every
shipped ``.clausal`` example passes its own tests; and every relative link in
a shipped ``.md`` file resolves inside the installed package.
Runs every check, then exits non-zero naming each one that failed.
"""
from __future__ import annotations

import os
import pathlib
import re
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


FAILED: list[str] = []


def report(name: str, problem: str | None) -> None:
    if problem is None:
        print(f"ok   {name}")
    else:
        print(f"FAIL {name}: {problem}")
        FAILED.append(name)


def check(name: str, argv: list[str], cwd: str, want: str) -> None:
    r = subprocess.run([sys.executable, "-m", "clausal", *argv], cwd=cwd,
                       capture_output=True, text=True, timeout=300)
    report(name, None if r.returncode == 0 and want in r.stdout else
           f"exit {r.returncode}\nstdout: {r.stdout}\nstderr: {r.stderr}")


_LINK = re.compile(r"\]\(([^)\s]+)\)")


def dead_links(package: pathlib.Path) -> list[str]:
    """Relative links in the shipped ``.md`` files whose target is not in
    the installed package (a docs page must be linked by URL)."""
    dead = []
    for md in sorted(package.rglob("*.md")):
        for n, line in enumerate(md.read_text(encoding="utf-8").splitlines(), 1):
            for target in _LINK.findall(line):
                if re.match(r"[a-z]+:", target) or target.startswith("#"):
                    continue
                path = (md.parent / target.split("#")[0]).resolve()
                if not (path.is_relative_to(package) and path.exists()):
                    dead.append(f"{md.relative_to(package)}:{n}: {target}")
    return dead


def main() -> None:
    import clausal
    from clausal.logic.variables import _variables  # noqa: F401  C extension
    from clausal.logic.runtime import _trampoline  # noqa: F401   C extension
    package = pathlib.Path(clausal.__file__).resolve().parent
    print(f"ok   import clausal from {package}")
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
    examples = sorted((package / "examples").glob("*.clausal"))
    report("examples shipped", None if examples else
           f"no .clausal example in {package / 'examples'}")
    for example in examples:
        check(f"example {example.name}", ["--test", str(example)],
              str(example.parent), "[PASSED]")
    dead = dead_links(package)
    report("shipped .md links", None if not dead else
           f"{len(dead)} relative links leave the package:\n  " + "\n  ".join(dead))
    if FAILED:
        sys.exit(f"wheel smoke test FAILED {len(FAILED)}: " + ", ".join(FAILED))
    print("wheel smoke test passed")


if __name__ == "__main__":
    main()
