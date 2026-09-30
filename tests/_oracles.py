"""Where the external Prolog oracles live, and how Scryer is run -- the ONE
definition.

Every test that runs a real Prolog system imports its path from here, so the
reference binary is chosen in one place and can be overridden per run:

    CLAUSAL_SCRYER=/path/to/scryer-prolog  CLAUSAL_TREALLA=/path/to/tpl

The Scryer default is the clean build (upstream master plus library(clpq)),
NOT /workspace/scryer-prolog, whose binary is built from uncommitted clpz
work-in-progress that drops constraints and prints trace lines.
tests/test_oracle_paths.py fails if a test hardcodes that path again.

Each caller keeps its own policy for a missing binary (skip, fail, or the
CLAUSAL_ISO_ALLOW_NO_SCRYER opt-out); this module only names the path and,
through :func:`run_scryer`, the one way to put a query to Scryer.
"""
import os
import pathlib
import subprocess

SCRYER = os.environ.get(
    "CLAUSAL_SCRYER", "/workspace/scryer-prolog-clpq/target/release/scryer-prolog")
TREALLA = os.environ.get("CLAUSAL_TREALLA", "/workspace/trealla-prolog/tpl")

#: Answers one query with Scryer's own toplevel printers; see its header.
SCRYER_TOPLEVEL = str(pathlib.Path(__file__).resolve().with_name("_scryer_toplevel.pl"))


def _quoted_atom(text: str) -> str:
    return "'" + (text.replace("\\", "\\\\").replace("'", "\\'")
                  .replace("\n", "\\n").replace("\t", "\\t")) + "'"


def scryer_argv(program=None, goals=(), *, binary=None) -> list:
    """The command line :func:`run_scryer` runs (exposed for its own tests)."""
    if isinstance(goals, str):
        goals = [goals]
    if program is None:
        programs = []
    elif isinstance(program, (str, os.PathLike)):
        programs = [os.fspath(program)]
    else:
        programs = [os.fspath(p) for p in program]
    argv = [binary or SCRYER, *programs]
    if goals:
        argv.append(SCRYER_TOPLEVEL)
    for goal in goals:
        goal = goal.strip()
        if not goal.endswith("."):
            goal += " ."
        argv += ["-g", f"'$clausal_oracle':query({_quoted_atom(goal)})"]
    # A SEPARATE trailing `-g halt`: Scryer runs every -g, and one that raises
    # does not stop the next, so the process exits whatever the queries did.
    # (Scryer-only: Trealla keeps just the LAST -g.)
    argv += ["-g", "halt"]
    return argv


def run_scryer(program=None, goals=(), *, timeout=60, cwd=None, binary=None):
    """Consult *program* in Scryer and put each of *goals* to it as a toplevel query.

    *program* is a path, a list of paths, or None; *goals* is one query or a
    list of them, each run on its own (``"p(X)."``, the dot optional). Every
    answer is printed exactly as Scryer's interactive toplevel prints it
    (``   X = 1.``, ``   false.``, ``   error(...).``), so output that used to be
    parsed from the stdin toplevel parses the same way. With no goals the
    program just loads (e.g. under ``:- initialization(main).``) and halts.

    stdin is always /dev/null: the clean Scryer build hangs when its toplevel
    is driven from a pipe, /dev/null or a pty, so nothing here ever reaches
    that toplevel. Returns the CompletedProcess (``stdout``/``stderr``/
    ``returncode``); TimeoutExpired propagates.
    """
    return subprocess.run(
        scryer_argv(program, goals, binary=binary), cwd=cwd,
        stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=timeout)
