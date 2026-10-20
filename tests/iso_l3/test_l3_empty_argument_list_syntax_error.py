"""``name()`` -- a functor with an empty argument list -- is a syntax error
(ISO 6.3.3: a compound term has at least one argument).

Before the fix the reader built a zero-argument compound: in a ``.clausal``
or ``.pl`` clause body ``nl()`` quietly ran as ``nl``, and a ``-g`` goal
crashed with an internal ``TypeError`` ("the 1-tuple ('nl',) is reserved").
Every path now reports a syntax error with its position.  Scryer reads
``nl().`` as ``syntax_error(incomplete_reduction)``.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

from clausal.tools.prolog_parser import ParseError, parse_term
from clausal.tools.prolog_reader import SyntaxIssue, read_module

REPO_ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize("text, col", [
    ("nl()", 4),
    ("foo(a, g())", 10),
    ("[h()]", 4),
    ("{}()", 4),
])
def test_parser_refuses_an_empty_argument_list(text, col):
    with pytest.raises(ParseError) as info:
        parse_term(text)
    assert "empty argument list" in str(info.value)
    assert (info.value.line, info.value.col) == (1, col)


def test_reader_reports_a_syntax_issue_and_resyncs():
    items = read_module("t :- nl().\nu.\n")
    assert type(items[0]) is SyntaxIssue
    assert "empty argument list" in items[0].message
    assert items[0].message.endswith("at 1:9")
    assert [type(i).__name__ for i in items[1:]] == ["Clause"]


def test_a_quoted_functor_with_arguments_still_reads():
    assert parse_term("'nl'(x)").args[0].name == "x"
    assert parse_term("f(g(x), h)").args[1].name == "h"


def _clausal(cwd, *argv, frontend=None):
    env = dict(os.environ)
    env.pop("CLAUSAL_PL_FRONTEND", None)
    if frontend is not None:
        env["CLAUSAL_PL_FRONTEND"] = frontend
    env["PYTHONPATH"] = str(REPO_ROOT) + os.pathsep + env.get("PYTHONPATH", "")
    return subprocess.run([sys.executable, "-m", "clausal", *argv], cwd=cwd,
                          env=env, capture_output=True, text=True, timeout=120)


@pytest.mark.parametrize("suffix", [".clausal", ".pl"])
def test_a_program_with_an_empty_argument_list_does_not_load(tmp_path,
                                                              suffix):
    prog = tmp_path / f"emptyargs{suffix}"
    prog.write_text("ok.\n\nt :- nl().\n")
    proc = _clausal(tmp_path, prog.name, "-g", "t")
    assert proc.returncode != 0, proc.stdout
    assert "TypeError" not in proc.stderr, proc.stderr
    assert "syntax error" in proc.stderr, proc.stderr
    assert "empty argument list" in proc.stderr, proc.stderr
    assert "line 3" in proc.stderr, proc.stderr


def test_the_pl_translator_front_end_refuses_it_too(tmp_path):
    prog = tmp_path / "emptyargs_translated.pl"
    prog.write_text("ok.\n\nt :- nl().\n")
    proc = _clausal(tmp_path, prog.name, "-g", "t", frontend="translator")
    assert proc.returncode != 0, proc.stdout
    assert "empty argument list" in proc.stderr, proc.stderr
    assert "at 3:9" in proc.stderr, proc.stderr


@pytest.mark.parametrize("goal", ["nl()", "foo(a, g())"])
def test_a_goal_with_an_empty_argument_list_is_a_syntax_error(tmp_path,
                                                               goal):
    prog = tmp_path / "plain.clausal"
    prog.write_text("ok.\n")
    proc = _clausal(tmp_path, prog.name, "-g", goal)
    assert proc.returncode != 0, proc.stdout
    assert "TypeError" not in proc.stderr, proc.stderr
    assert f"-g {goal}: syntax error" in proc.stderr, proc.stderr
    assert "empty argument list" in proc.stderr, proc.stderr
