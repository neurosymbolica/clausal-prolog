"""Guard: no test hardcodes the work-in-progress Scryer checkout.

/workspace/scryer-prolog is built from uncommitted clpz work that drops
constraints, so an oracle pointed at it can agree with a wrong answer. The
path is defined once, in tests/_oracles.py (overridable via CLAUSAL_SCRYER).
"""
import pathlib

_TESTS = pathlib.Path(__file__).resolve().parent
_WIP = "/workspace/scryer-prolog" + "/target"   # split so this file does not match itself


def test_no_test_hardcodes_the_wip_scryer_path():
    files = [p for p in _TESTS.rglob("*") if p.is_file() and p.suffix in
             (".py", ".pl", ".seam", ".clausal", ".txt", ".toml", ".cfg", ".ini")]
    assert len(files) > 100, f"guard scanned only {len(files)} files under {_TESTS}"
    hits = [f"{p.relative_to(_TESTS)}:{n}"
            for p in files
            for n, line in enumerate(p.read_text(errors="replace").splitlines(), 1)
            if _WIP in line]
    assert not hits, (
        "hardcoded WIP Scryer path; import SCRYER from tests._oracles instead:\n  "
        + "\n  ".join(hits))


# ── Scryer is never driven through its stdin toplevel ─────────────────────────
#
# The clean build HANGS when its interactive toplevel reads a pipe, /dev/null
# or a pty, and when a -g goal raises with no separate `-g halt` after it.
# tests/_oracles.py:run_scryer puts each query through -g instead, printing the
# answer with the toplevel's own printers.

import ast
import os
import textwrap

import pytest

from tests._oracles import SCRYER, run_scryer, scryer_argv


@pytest.mark.skipif(not os.path.exists(SCRYER), reason=f"Scryer not built at {SCRYER}")
def test_run_scryer_answers_as_the_toplevel_prints(tmp_path):
    (tmp_path / "p.pl").write_text("p(1).\np(2).\nq(a).\n")
    proc = run_scryer("p.pl", ["q(X).", "q(b).", "X is foo+1.", "p(X)", "p(X), X > 1."],
                      cwd=tmp_path, timeout=30)
    # A raising query (the third) does not stop the ones after it, and an
    # answer with choicepoints left is closed as RETURN closes it.
    assert proc.stdout == textwrap.dedent("""\
           X = a.
           false.
           error(type_error(evaluable,foo/0),(is)/2).
           X = 1
        ;  ... .
           X = 2.
        """), (proc.stdout, proc.stderr)
    assert proc.returncode == 0


@pytest.mark.skipif(not os.path.exists(SCRYER), reason=f"Scryer not built at {SCRYER}")
def test_run_scryer_with_no_goals_loads_and_halts(tmp_path):
    (tmp_path / "p.pl").write_text(":- initialization((write(loaded), nl)).\n")
    proc = run_scryer("p.pl", [], cwd=tmp_path, timeout=30)
    assert proc.stdout == "loaded\n", (proc.stdout, proc.stderr)


def test_run_scryer_quotes_the_query_as_one_atom():
    argv = scryer_argv("p.pl", ["X = 'it''s', Y = \"a\\\\b\"", "true."], binary="S")
    assert argv[:2] == ["S", "p.pl"] and argv[2].endswith("_scryer_toplevel.pl")
    assert argv[3:] == [
        "-g", "'$clausal_oracle':query('X = \\'it\\'\\'s\\', Y = \"a\\\\\\\\b\" .')",
        "-g", "'$clausal_oracle':query('true.')",
        "-g", "halt"]


_SCRYER_NAMES = {"SCRYER", "_SCRYER", "scryer", "scryer_bin"}


def test_no_test_feeds_scryer_on_stdin():
    """Every direct subprocess call whose argv starts with a Scryer path passes
    stdin=subprocess.DEVNULL and no input=; anything with queries to ask goes
    through run_scryer."""
    checked, bad = 0, []
    for p in sorted(_TESTS.rglob("*.py")):
        tree = ast.parse(p.read_text(errors="replace"))
        for node in ast.walk(tree):
            if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                    and node.func.attr in ("run", "Popen", "check_output")
                    and node.args and isinstance(node.args[0], ast.List)
                    and node.args[0].elts
                    and isinstance(node.args[0].elts[0], ast.Name)
                    and node.args[0].elts[0].id in _SCRYER_NAMES):
                continue
            checked += 1
            kw = {k.arg: k.value for k in node.keywords}
            if "input" in kw or ast.unparse(kw.get("stdin", ast.Constant(None))) \
                    != "subprocess.DEVNULL":
                bad.append(f"{p.relative_to(_TESTS)}:{node.lineno}")
    assert checked >= 3, f"guard checked only {checked} direct Scryer calls"
    assert not bad, ("Scryer run without stdin=subprocess.DEVNULL (or fed "
                     "input=); use tests._oracles.run_scryer:\n  " + "\n  ".join(bad))
