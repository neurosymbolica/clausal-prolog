"""Quads: queries using answer descriptions (``clausal.tools.quads``,
``clausal.quad_runner``, ``clausal --quads FILE``).

A ``?- Query.`` and the answer descriptions after it are skipped by the
loader, and run as tests by ``--quads``.
"""

from __future__ import annotations

import os
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

from clausal.tools.quads import extract_quads, is_answer_description
from clausal.tools.iso_l3 import read_iso

REPO_ROOT = Path(__file__).resolve().parent.parent

PROGRAM = textwrap.dedent("""\
    p(1). p(2).
    q(f(X, Y, X), Y).

    """)


def _run(tmp_path, body, *argv):
    (tmp_path / "t.pl").write_text(PROGRAM + textwrap.dedent(body))
    env = dict(os.environ)
    env["PYTHONPATH"] = str(REPO_ROOT) + os.pathsep + env.get("PYTHONPATH", "")
    return subprocess.run(
        [sys.executable, "-m", "clausal", "t.pl", "--quads", *argv],
        cwd=tmp_path, env=env, capture_output=True, text=True, timeout=120)


def _terms(text):
    return [it.term for it in read_iso(text)]


@pytest.mark.parametrize("text", [
    "true", "false", "X = 1", "X = 1, Y = f(_A)", "X = 1 ; X = 2",
    "instantiation_error", "type_error(atom, 1)", "error(E, _)",
    "throw(oops)", "...", "..., ad_infinitum", "loops", "maybe",
    "X = 1 ; ...", "outputs(foo)", "domain_error(not_less_than_zero, -1)",
])
def test_answer_description_syntax(text):
    assert all(is_answer_description(t) for t in _terms(text + " .")), text


@pytest.mark.parametrize("text", ["foo.", "p(1).", "1 = X.", "a :- b.", "X."])
def test_not_an_answer_description(text):
    assert not any(is_answer_description(t) for t in _terms(text))


def test_extract_quads_pairs_queries_with_their_descriptions():
    quads = extract_quads("p(1).\n\n?- p(X).\n   X = 1.\n\n?- p(2).\n\n"
                          "lab ?- p(3).\n   false.\n")
    assert [(q.line, q.label, len(q.descriptions)) for q in quads] == [
        (3, None, 1), (6, None, 0), (8, "lab", 1)]


def test_a_description_with_no_query_before_it_is_a_clause():
    quads = extract_quads("X = 1 ; X = 2.\n")
    assert quads == []


def test_loader_ignores_quads(tmp_path):
    # ``X = 1.`` after a query must not define =/2: the file still loads.
    (tmp_path / "ok.pl").write_text(PROGRAM + "?- p(X).\n   X = 1\n;  X = 2.\n")
    env = dict(os.environ)
    env["PYTHONPATH"] = str(REPO_ROOT) + os.pathsep + env.get("PYTHONPATH", "")
    r = subprocess.run([sys.executable, "-m", "clausal", "ok.pl", "-g", "p(X)"],
                       cwd=tmp_path, env=env, capture_output=True, text=True,
                       timeout=120)
    assert (r.returncode, r.stdout) == (0, "X = 1.\nX = 2.\n"), r.stderr


def test_loader_ignores_quads_in_clausal_files(tmp_path):
    (tmp_path / "m.clausal").write_text(
        ":- module(m, [a/1]).\na(1).\n\n?- a(X).\n   X = 1.\n\n"
        ":- end_module(m).\n")
    env = dict(os.environ)
    env["PYTHONPATH"] = str(REPO_ROOT) + os.pathsep + env.get("PYTHONPATH", "")
    r = subprocess.run([sys.executable, "-m", "clausal", "m.clausal", "--quads"],
                       cwd=tmp_path, env=env, capture_output=True, text=True,
                       timeout=120)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "1 passed" in r.stdout


# ── the runner: one passing quad per kind of description ──────────────────

PASSING = [
    ("all answers", "?- p(X).\n   X = 1\n;  X = 2.\n"),
    ("a prefix and ...", "?- p(X).\n   X = 1\n;  ... .\n"),
    ("failure", "?- p(3).\n   false.\n"),
    ("true", "?- p(1).\n   true.\n"),
    ("instantiation_error", "?- between(I, I, 0).\n   instantiation_error.\n"),
    ("type_error", "?- atom_length(1, N).\n   type_error(atom, 1).\n"),
    ("error/2 with a wildcard", "?- atom_length(1, N).\n   error(type_error(_, _), _).\n"),
    ("throw/1", "?- throw(oops).\n   throw(oops).\n"),
    ("infinite", "?- length(L, N).\n   L = [], N = 0\n;  L = [_A], N = 1\n;  ..., ad_infinitum.\n"),
    ("a variant with sharing", "?- q(A, B).\n   A = f(_X, B, _X).\n"),
    ("variables of the query", "?- X = Y.\n   X = Y.\n"),
    ("a conjunction in an answer", "?- p(X), p(Y).\n   X = 1, Y = 1\n;  X = 1, Y = 2\n;  X = 2, Y = 1\n;  X = 2, Y = 2.\n"),
    ("approximately", "?- X is 2/3.0.\n   X ~~ '0.6667'.\n"),
    # the bar is an operator once library(dcgs) is loaded, as in Scryer
    ("alternatives", ":- use_module(library(dcgs)).\n?- atom_length(1, N).\n   false | type_error(atom, 1).\n"),
    ("a labelled quad", "ok ?- p(1).\n   true.\n"),
    ("an answer then an error", "?- p(X), atom_length(X, N).\n   type_error(atom, 1).\n"),
]


@pytest.mark.parametrize("name, body", PASSING, ids=[n for n, _ in PASSING])
def test_passing_quad(tmp_path, name, body):
    r = _run(tmp_path, body)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "1 found, 1 passed, 0 failed, 0 skipped" in r.stdout


FAILING = [
    ("a missing answer", "?- p(X).\n   X = 1.\n", "expected no further answer"),
    ("a wrong value", "?- p(X).\n   X = 3\n;  X = 2.\n", "the bindings differ"),
    ("a wrong variable sharing", "?- q(A, B).\n   A = f(_X, _Y, _Z).\n", "the bindings differ"),
    ("a missing binding", "?- X = 1.\n   true.\n", "the bindings differ"),
    ("false but answers", "?- p(X).\n   false.\n", "expected no answer"),
    ("answers but none", "?- p(3).\n   X = 1.\n", "no more answers"),
    ("the wrong error", "?- atom_length(1, N).\n   instantiation_error.\n", "raised"),
    ("an error not raised", "?- p(1).\n   type_error(atom, 1).\n", "expected an error"),
    ("too few answers", "?- p(X).\n   X = 1\n;  X = 2\n;  X = 3.\n", "an answer"),
    ("outside the approximation", "?- X is 2/3.0.\n   X ~~ '0.8'.\n", "is not ~~"),
]


@pytest.mark.parametrize("name, body, why", FAILING, ids=[n for n, _, _ in FAILING])
def test_failing_quad(tmp_path, name, body, why):
    r = _run(tmp_path, body)
    assert r.returncode == 1, r.stdout + r.stderr
    assert "quad failed" in r.stdout and why in r.stdout, r.stdout
    assert "t.pl:4:" in r.stdout          # the line of the query
    assert "1 found, 0 passed, 1 failed" in r.stdout


def test_a_residual_constraint_needs_maybe(tmp_path):
    body = ":- use_module(library(clpz)).\n?- X #> 3.\n   true.\n"
    r = _run(tmp_path, body)
    assert r.returncode == 1 and "maybe" in r.stdout
    r = _run(tmp_path, ":- use_module(library(clpz)).\n?- X #> 3.\n   maybe.\n")
    assert r.returncode == 0, r.stdout


@pytest.mark.parametrize("annotation", ["loops", "other_answer_sequence",
                                        "outputs(foo)", "unexpected"])
def test_unchecked_annotations_skip(tmp_path, annotation):
    r = _run(tmp_path, f"?- p(X).\n   X = 1, {annotation}.\n")
    assert r.returncode == 0, r.stdout
    assert "0 failed, 1 skipped" in r.stdout


def test_a_query_without_description_is_skipped(tmp_path):
    r = _run(tmp_path, "?- p(X).\n")
    assert r.returncode == 0 and "1 skipped" in r.stdout


def test_a_query_that_never_answers_times_out(tmp_path):
    body = "spin(N) :- N1 is N + 1, spin(N1).\n?- spin(0).\n   false.\n"
    (tmp_path / "t.pl").write_text(PROGRAM + body)
    from clausal.quad_runner import run_quads
    from clausal.testing import load_clausal_module
    from clausal import cli
    module = load_clausal_module(str(tmp_path / "t.pl"))
    import io
    out = io.StringIO()
    src = (tmp_path / "t.pl").read_text()
    summary = run_quads(module, src, cli._goal_reader_ops(src), "t.pl",
                        out=out, timeout=0.5)
    assert summary.count("failed") == 1 and "no answer within" in out.getvalue()


def test_quads_takes_no_goal(tmp_path):
    r = _run(tmp_path, "", "-g", "true")
    assert r.returncode == 2
