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
    ("error/2 with a wildcard", "?- atom_length(1, N).\n   error(type_error(atom, 1), _).\n"),
    ("throw/1", "?- throw(oops).\n   throw(oops).\n"),
    ("infinite", "?- length(L, N).\n   L = [], N = 0\n;  L = [_A], N = 1\n;  ..., ad_infinitum.\n"),
    ("a variant with sharing", "?- q(A, B).\n   A = f(_X, B, _X).\n"),
    ("variables of the query", "?- X = Y.\n   X = Y.\n"),
    ("a conjunction in an answer", "?- p(X), p(Y).\n   X = 1, Y = 1\n;  X = 1, Y = 2\n;  X = 2, Y = 1\n;  X = 2, Y = 2.\n"),
    ("approximately", "?- X is 2/3.0.\n   X ~~ '0.6667'.\n"),
    # the bar is an operator once library(dcgs) is loaded, as in Scryer
    ("alternatives", ":- use_module(library(dcgs)).\n?- atom_length(1, N).\n   false | type_error(atom, 1).\n"),
    ("a labelled quad", "ok ?- p(1).\n   true.\n"),
    ("a partial list", "?- append([a], T, L).\n   L = [a|T].\n"),
    ("a partial list with a fresh tail", "?- X = [a|_].\n   X = [a|_A].\n"),
    ("a partial list, two heads", "?- X = [a,b|T].\n   X = [a,b|T].\n"),
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


def test_a_fresh_variable_is_not_the_querys_variable(tmp_path):
    # as in Trealla: T is a variable of the query, so `_A` does not name it
    r = _run(tmp_path, "?- X = [a,b|T].\n   X = [a,b|_A].\n")
    assert r.returncode == 1 and "the bindings differ" in r.stdout


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
                                        "waits", "inputs(foo)"])
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


# ── review fixes (2026-10-24) ──────────────────────────────────────────


def _g(tmp_path, source, *goals, name="g.pl"):
    (tmp_path / name).write_text(source)
    env = dict(os.environ)
    env["PYTHONPATH"] = str(REPO_ROOT) + os.pathsep + env.get("PYTHONPATH", "")
    argv = [sys.executable, "-m", "clausal", name]
    for g in goals:
        argv += ["-g", g]
    return subprocess.run(argv, cwd=tmp_path, env=env, capture_output=True,
                          text=True, timeout=120)


@pytest.mark.parametrize("description", [
    "dif(X, a).", "freeze(X, true).", "X = 1 ; dif(X, a).",
])
def test_a_residual_description_is_not_loaded_as_a_clause(tmp_path, description):
    # dif/2 must stay the library's: the description after the query is
    # skipped, not defined as a fact that would shadow it
    r = _g(tmp_path, "p(1).\n?- dif(X, a).\n   " + description + "\n",
           "dif(1, 1)", "dif(1, 2)")
    assert r.returncode == 1 and r.stdout == "false.\n", (r.stdout, r.stderr)


def test_a_clpz_description_is_not_loaded_as_a_clause(tmp_path):
    src = ("p(1).\n:- use_module(library(clpz)).\n?- X in 4..5.\n"
           "   X in 4..5.\n")
    r = _g(tmp_path, src, "3 in 4..5")
    assert (r.returncode, r.stdout) == (1, "false.\n"), (r.stdout, r.stderr)


def test_the_quad_operators_do_not_leak_into_the_program(tmp_path):
    # the user's own op/3 for ~~ and ?- loads, and in a file with no quad
    # ``a ~~ b`` is a syntax error without that op, as in Scryer
    ok = _g(tmp_path, ":- op(100, xf, ~~).\n:- op(100, xf, ?-).\np(1).\n",
            "p(X)")
    assert (ok.returncode, ok.stdout) == (0, "X = 1.\n"), ok.stderr
    bad = _g(tmp_path, "p(X) :- X = (a ~~ b).\n", "true")
    assert bad.returncode != 0
    bad = _g(tmp_path, "f(x) ?- p(1).\n", "true")
    assert bad.returncode != 0


def test_infix_query_operators_work_after_a_quad(tmp_path):
    r = _g(tmp_path, "p(1).\nlab ?- p(1).\n   true.\n"
                     "?- X is 2/3.0.\n   X ~~ '0.6667'.\n", "p(X)")
    assert (r.returncode, r.stdout) == (0, "X = 1.\n"), r.stderr


def test_a_skipped_directive_lookalike_warns(tmp_path):
    r = _g(tmp_path, "?- dynamic(foo/1).\np(1).\n", "p(X)")
    assert r.returncode == 0
    assert "skipped" in r.stderr and "dynamic" in r.stderr, r.stderr


def test_a_description_shaped_fact_after_a_query_is_skipped(tmp_path):
    # the documented boundary: right after a query, these are descriptions
    r = _g(tmp_path, "p(1).\n?- p(1).\nloops.\nerror(a, b).\nq(2).\n",
           "q(X)", "loops")
    assert r.stdout.startswith("X = 2."), r.stdout
    assert "existence_error" in r.stdout or "false" in r.stdout or r.returncode


def test_a_description_binding_a_variable_not_in_the_query_fails(tmp_path):
    r = _run(tmp_path, "?- true.\n   Y = 1.\n")
    assert r.returncode == 1 and "no variable of the query" in r.stdout


def test_maybe_needs_something_pending(tmp_path):
    r = _run(tmp_path, "?- X = 1.\n   X = 1, maybe.\n")
    assert r.returncode == 1 and "nothing is pending" in r.stdout


def test_all_descriptions_of_a_quad_must_hold(tmp_path):
    ok = _run(tmp_path, "?- p(X).\n   X = 1\n;  X = 2.\n   X = 1\n;  ... .\n")
    assert ok.returncode == 0, ok.stdout
    bad = _run(tmp_path, "?- p(X).\n   X = 1\n;  X = 2.\n   X = 2\n;  ... .\n")
    assert bad.returncode == 1


def test_unexpected_marks_an_answer_that_must_not_occur(tmp_path):
    ok = _run(tmp_path, "?- X = 1.\n   X = 2, unexpected.\n")
    assert ok.returncode == 0, ok.stdout
    bad = _run(tmp_path, "?- X = 1.\n   X = 1, unexpected.\n")
    assert bad.returncode == 1 and "unexpected" in bad.stdout


def test_outputs_matches_what_the_query_wrote(tmp_path):
    ok = _run(tmp_path, '?- write(abc), nl.\n   outputs("abc\\n"), true.\n')
    assert ok.returncode == 0, ok.stdout
    bad = _run(tmp_path, '?- write(abc).\n   outputs("xyz"), true.\n')
    assert bad.returncode == 1 and "wrote" in bad.stdout


def test_dots_in_a_binding_is_any_subterm(tmp_path):
    ok = _run(tmp_path, "?- X = f(1, 2).\n   X = f(..., 2).\n")
    assert ok.returncode == 0, ok.stdout
    bad = _run(tmp_path, "?- X = g(1).\n   X = f(..., 2).\n")
    assert bad.returncode == 1


def test_sto_is_accepted_unchecked(tmp_path):
    r = _run(tmp_path, "?- X = 1.\n   sto, X = 1.\n")
    assert r.returncode == 0, r.stdout


def test_quads_needs_a_file_and_takes_no_toplevel(tmp_path):
    for argv in (["--quads"], ["--quads", "--toplevel", "t.pl"]):
        r = subprocess.run(
            [sys.executable, "-m", "clausal", *argv], cwd=tmp_path,
            env={**os.environ, "PYTHONPATH": str(REPO_ROOT)},
            capture_output=True, text=True, timeout=60, stdin=subprocess.DEVNULL)
        assert r.returncode == 2, (argv, r.stderr)


def test_a_labelled_query_needs_a_description_after_it(tmp_path):
    # `main ?- p.` (for `main :- p.`) is a syntax error, as in Scryer, even
    # in a file that has a quad
    r = _g(tmp_path, "p(1).\n?- p(1).\n   true.\nmain ?- p(1).\nq(2).\n",
           "q(X)")
    assert r.returncode != 0 and "syntax" in (r.stderr + r.stdout).lower()
    ok = _g(tmp_path, "p(1).\nmain ?- p(1).\n   true.\nq(2).\n", "q(X)")
    assert (ok.returncode, ok.stdout) == (0, "X = 2.\n"), ok.stderr


def test_quads_run_off_the_main_thread_without_a_timer(tmp_path):
    import io
    import threading
    from clausal import cli
    from clausal.quad_runner import run_quads
    from clausal.testing import load_clausal_module
    src = PROGRAM + "?- p(X).\n   X = 1\n;  X = 2.\n"
    (tmp_path / "t.pl").write_text(src)
    module = load_clausal_module(str(tmp_path / "t.pl"))
    out, box = io.StringIO(), {}

    def work():
        try:
            box["s"] = run_quads(module, src, cli._goal_reader_ops(src),
                                 "t.pl", out=out)
        except BaseException as exc:    # noqa: BLE001
            box["exc"] = exc

    t = threading.Thread(target=work)
    t.start()
    t.join(60)
    assert "exc" not in box, box.get("exc")
    assert box["s"].count("passed") == 1


@pytest.mark.parametrize("query", ["a(X), !", "(a(X) -> true ; fail)"])
def test_a_clausal_file_quad_with_control_is_refused_clearly(tmp_path, query):
    (tmp_path / "m.clausal").write_text(
        ":- module(m, [a/1]).\na(1).\n\n?- " + query + ".\n   X = 1.\n\n"
        ":- end_module(m).\n")
    env = dict(os.environ)
    env["PYTHONPATH"] = str(REPO_ROOT) + os.pathsep + env.get("PYTHONPATH", "")
    r = subprocess.run([sys.executable, "-m", "clausal", "m.clausal", "--quads"],
                       cwd=tmp_path, env=env, capture_output=True, text=True,
                       timeout=120)
    assert r.returncode == 1
    assert "not Clausal Prolog" in r.stdout and "existence_error" not in r.stdout


def test_the_directive_warning_names_the_file_and_line(tmp_path):
    r = _g(tmp_path, "p(1).\n?- dynamic(foo/1).\n?- initialization(main).\n",
           "p(X)")
    assert r.returncode == 0
    assert "g.pl:2" in r.stderr and "g.pl:3" in r.stderr, r.stderr
    assert "iso_l3.py" not in r.stderr and "warnings.warn" not in r.stderr
    assert "initialization/1 is refused" in r.stderr
    assert "write `:- initialization" not in r.stderr


def test_quads_takes_no_program_args(tmp_path):
    (tmp_path / "t.pl").write_text(PROGRAM)
    r = subprocess.run(
        [sys.executable, "-m", "clausal", "t.pl", "--quads", "--", "a", "b"],
        cwd=tmp_path,
        env={**os.environ, "PYTHONPATH": str(REPO_ROOT)},
        capture_output=True, text=True, timeout=60, stdin=subprocess.DEVNULL)
    assert r.returncode == 2, r.stderr


def test_an_unchecked_alternative_does_not_leak_its_internal_tag(tmp_path):
    r = _run(tmp_path, ":- use_module(library(dcgs)).\n"
                       "?- p(X).\n   X = 5 | loops.\n")
    assert r.returncode == 1, r.stdout
    assert "unsupported:" not in r.stdout
    assert "loops is not checked" in r.stdout


@pytest.mark.parametrize("goal", ["freeze(X, true)", "when(nonvar(X), true)",
                                  "when(ground(f(X, Y)), true)"])
def test_freeze_and_when_leave_something_pending(tmp_path, goal):
    # coroutines are pending goals too: `maybe` (or the goal itself) is needed
    no = _run(tmp_path, f"?- {goal}.\n   true.\n")
    assert no.returncode == 1 and "maybe" in no.stdout, no.stdout
    yes = _run(tmp_path, f"?- {goal}.\n   maybe.\n")
    assert yes.returncode == 0, yes.stdout
    cited = _run(tmp_path, f"?- {goal}.\n   {goal}.\n")
    assert cited.returncode == 0, cited.stdout


def test_g_prints_a_pending_coroutine(tmp_path):
    r = _g(tmp_path, "p(1).\n", "freeze(X, true)", "X = 1, freeze(Y, true)")
    assert r.returncode == 0
    lines = r.stdout.splitlines()
    assert lines[0] == "freeze(X,true).", lines
    assert lines[1] == "X = 1, freeze(Y,true).", lines


@pytest.mark.parametrize("text", [
    # two labelled queries in a row, neither with a description
    "l1 ?- p(1).\nl2 ?- p(2).\nq(3).\n",
    # one, then a description-less one at the end
    "l1 ?- p(1).\nq(3).\nl2 ?- p(2).\n",
    # the first has a description, the second has none
    "l1 ?- p(1).\n   true.\nl2 ?- p(2).\nq(3).\n",
])
def test_labelled_queries_without_a_description_are_refused(tmp_path, text):
    r = _g(tmp_path, "p(1).\n?- p(1).\n   true.\n" + text, "q(X)")
    assert r.returncode != 0 and "syntax" in (r.stderr + r.stdout).lower(), r.stderr


def test_a_labelled_query_after_a_labelled_query_with_a_description(tmp_path):
    r = _g(tmp_path, "p(1).\nl1 ?- p(1).\n   true.\nl2 ?- p(1).\n   true.\n"
                     "q(3).\n", "q(X)")
    assert (r.returncode, r.stdout) == (0, "X = 3.\n"), r.stderr


@pytest.mark.parametrize("text, labels", [
    ("l1 ?- p(1).\nl2 ?- p(2).\nq(3).\n", []),
    ("l1 ?- p(1).\nl2 ?- p(2).\n   true.\nq(3).\n", ["l2"]),
    ("l1 ?- p(1).\n   true.\nl2 ?- p(2).\nq(3).\n", ["l1"]),
    ("l1 ?- p(1).\n   true.\nl2 ?- p(2).\n   true.\n", ["l1", "l2"]),
])
def test_extract_quads_counts_a_labelled_query_only_with_a_description(
        text, labels):
    # the peek that decides on one labelled query must not vouch for the next
    assert [q.label for q in extract_quads("p(1).\n" + text)] == labels
