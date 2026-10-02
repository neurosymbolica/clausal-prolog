"""A long clause body loads and answers, on every front end.

The trampoline compiler opens one loop per backtracking goal around the REST
of the body (``while _st is not DONE: <continuation>``), so a body with ~19
goals nested past CPython's limit of 20 statically nested blocks and the
module failed to load with a bare ``SyntaxError: too many statically nested
blocks`` that named neither the predicate nor the file.
``clausal.codegen.split_deep_nesting`` now outlines the deep tail into
nested helper generators, and a compile failure that still happens names the
clause (``GeneratedCodeError``).

Every test here that loads a 19+ goal body failed on 8288dbea.

Scryer (the reference) loads and answers each of these bodies.
"""
from __future__ import annotations

import ast
import itertools
import textwrap
import warnings

import pytest

import clausal.codegen as codegen
import clausal.import_hook  # noqa: F401 -- installs the meta-path finder
from clausal.codegen import GeneratedCodeError, split_deep_nesting
from clausal.import_hook import _load_module
from clausal.logic.solve import call as pcall
from clausal.logic.variables import Var, deref, walk
from tests._suffix import SEAM

_names = itertools.count()

FRONT_ENDS = ("native", "translator", "seam")


def _load(tmp_path, monkeypatch, front_end, pl_src, seam_src=None):
    name = f"longbody{next(_names)}"
    if front_end == "seam":
        path = tmp_path / f"{name}{SEAM}"
        path.write_text(textwrap.dedent(seam_src).lstrip())
    else:
        monkeypatch.setenv("CLAUSAL_PL_FRONTEND", front_end)
        path = tmp_path / f"{name}.pl"
        path.write_text(textwrap.dedent(pl_src).lstrip())
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")      # singleton-variable lint
        return _load_module(name, str(path)).__dict__["$module"]


def _answers(m, name, *args, outs):
    return [tuple(walk(deref(o)) for o in outs) for _ in pcall(name, *args, module=m)]


def _chain(n, sep=", "):
    """``q(X, V1), q(V1, V2), ..., q(V{n-1}, V{n})``."""
    return sep.join(f"q({'X' if i == 1 else f'V{i - 1}'}, V{i})"
                    for i in range(1, n + 1))


# ── 1. a conjunction of N user calls ────────────────────────────────────────

@pytest.mark.parametrize("n", [19, 50, 200])
@pytest.mark.parametrize("front_end", FRONT_ENDS)
def test_long_conjunction_loads_and_answers(tmp_path, monkeypatch, front_end, n):
    # A 3-way choice point in the MIDDLE of the body: backtracking into it
    # has to re-enter the outlined tail once per answer.
    goals = _chain(n, sep="\0").split("\0")
    body = ", ".join(goals[: n // 2] + ["r(Z)"] + goals[n // 2:])
    m = _load(tmp_path, monkeypatch, front_end,
              f"""
              q(X, Y) :- X < 1000, succ(X, Y).
              r(1).
              r(2).
              r(3).
              p(X, Y, Z) :- {body}, Y = V{n}.
              """,
              f"""
              q(X, Y) <- (X < 1000, succ(X, Y))
              r(1),
              r(2),
              r(3),
              p(X, Y, Z) <- ({body}, Y is V{n})
              """)
    Y, Z = Var(), Var()
    assert _answers(m, "p", 1, Y, Z, outs=(Y, Z)) == [
        (n + 1, 1), (n + 1, 2), (n + 1, 3)]
    # ... and a goal failing deep in the tail fails the whole clause.
    assert _answers(m, "p", 1000 - n + 5, Y, Z, outs=(Y, Z)) == []


@pytest.mark.parametrize("front_end", FRONT_ENDS)
def test_long_conjunction_of_builtins_and_unifications(tmp_path, monkeypatch, front_end):
    n = 60
    body = ", ".join(f"V{i} = X, X >= {-i}" for i in range(1, n + 1))
    m = _load(tmp_path, monkeypatch, front_end,
              f"p(X, Y) :- {body}, succ(X, Y).\n",
              f"p(X, Y) <- ({body.replace(' = ', ' is ')}, succ(X, Y))\n")
    Y = Var()
    assert _answers(m, "p", 7, Y, outs=(Y,)) == [(8,)]
    assert _answers(m, "p", -30, Y, outs=(Y,)) == []


def test_long_body_under_the_shallow_strategy(tmp_path, monkeypatch):
    n = 50
    m = _load(tmp_path, monkeypatch, "seam", None, f"""
        -shallow([p/2, q/2])
        q(X, Y) <- succ(X, Y)
        p(X, Y) <- ({_chain(n)}, Y is V{n})
        """)
    Y = Var()
    assert _answers(m, "p", 0, Y, outs=(Y,)) == [(n,)]


def test_long_tail_recursive_body_keeps_running(tmp_path, monkeypatch):
    # 25 deterministic goals before the self-call: the recursion runs 20000
    # deep, so a lost tail-call rewrite would show up as a blow-up here.
    guards = ", ".join(f"I >= {-j}" for j in range(25))
    m = _load(tmp_path, monkeypatch, "native", f"""
        cnt(N, N, A, A).
        cnt(I, N, A0, A) :- I < N, {guards}, succ(I, I1), A1 is A0 + 2, cnt(I1, N, A1, A).
        """)
    A = Var()
    assert _answers(m, "cnt", 0, 20000, 0, A, outs=(A,)) == [(40000,)]


# ── 2. other constructs that nest ───────────────────────────────────────────

@pytest.mark.parametrize("front_end", ("native", "translator"))
def test_deep_disjunction_of_conjunctions(tmp_path, monkeypatch, front_end):
    depth = 40
    goal = "q(X, Y)"
    for i in range(depth):
        goal = f"(q(X, Z{i}), {goal} ; Y = {i})"
    m = _load(tmp_path, monkeypatch, front_end, f"""
        q(X, Y) :- succ(X, Y).
        p(X, Y) :- {goal}.
        """)
    Y = Var()
    assert _answers(m, "p", 3, Y, outs=(Y,)) == [(4,)] + [(i,) for i in range(depth)]


@pytest.mark.parametrize("front_end", ("native", "translator"))
def test_if_nesting_with_long_branches(tmp_path, monkeypatch, front_end):
    # Each if_/3 level adds no block of its own, but each else-branch runs 6
    # calls before the next level: 4 levels nest 24+ blocks.  (Kept to 4
    # levels: nested if_/3 code grows ~4x per level, a separate matter.)
    depth, calls = 4, 6
    goal = "q(X, Y)"
    for i in range(depth):
        chain = ", ".join(f"q(X, W{i}_{j})" for j in range(calls))
        goal = f"if_(X = {i + 100}, Y = {i}, ({chain}, {goal}))"
    # The native front end imports if_/3 as ISO code must; the translator
    # has it built in and knows no library(reif).
    header = ":- use_module(library(reif))." if front_end == "native" else ""
    m = _load(tmp_path, monkeypatch, front_end, f"""
        {header}
        q(X, Y) :- succ(X, Y).
        p(X, Y) :- {goal}.
        """)
    Y = Var()
    assert _answers(m, "p", 5, Y, outs=(Y,)) == [(6,)]
    assert _answers(m, "p", 102, Y, outs=(Y,)) == [(2,)]


@pytest.mark.parametrize("front_end", ("native", "translator"))
def test_deep_findall_and_negation(tmp_path, monkeypatch, front_end):
    n = 40
    m = _load(tmp_path, monkeypatch, front_end, f"""
        q(X, Y) :- succ(X, Y).
        p(X, L) :- findall(V{n}, ({_chain(n)}), L).
        n(X) :- \\+ ({_chain(n)}, V{n} =:= 0).
        """)
    L = Var()
    assert _answers(m, "p", 1, L, outs=(L,)) == [([n + 1],)]
    assert _answers(m, "n", 1, outs=()) == [()]


@pytest.mark.parametrize("front_end", ("native", "translator"))
def test_dcg_rule_with_many_nonterminals(tmp_path, monkeypatch, front_end):
    n = 60
    m = _load(tmp_path, monkeypatch, front_end, f"""
        a --> [a].
        b --> [b].
        s --> {", ".join("a" for _ in range(n))}, b.
        """)
    ok = ["a"] * n + ["b"]
    assert _answers(m, "phrase", "s", ok, outs=()) == [()]
    assert _answers(m, "phrase", "s", ["a"] * (n - 1) + ["b"], outs=()) == []


# ── 3. the outliner itself ──────────────────────────────────────────────────

def _nested_loops(depth, body, *, generator):
    """``f(xs)``: ``depth`` nested loops, the outer one over ``xs`` and each
    inner one over its parent's single value, around *body*."""
    lines = ["def f(xs):", "    acc = []", "    for v0 in xs:"]
    ind = "        "
    for i in range(1, depth):
        lines.append(f"{ind}for v{i} in (v{i - 1},):")
        ind += "    "
    lines += [ind + line for line in body]
    lines.append("    yield ('end', acc)" if generator else "    return acc")
    node = ast.parse("\n".join(lines)).body[0]
    assert split_deep_nesting(node) is True
    helpers = [n for n in ast.walk(node)
               if isinstance(n, ast.FunctionDef) and n.name.startswith("$nest")]
    assert helpers
    return codegen.functiondef_to_function(node, {})


def test_short_functions_are_left_untouched():
    src = "def f(xs):\n" + "".join(
        "    " * (i + 1) + f"for v{i} in xs:\n" for i in range(5)) + "    " * 6 + "pass\n"
    node = ast.parse(src).body[0]
    before = ast.dump(node, include_attributes=True)
    assert split_deep_nesting(node) is False
    assert ast.dump(node, include_attributes=True) == before


def test_outlined_plain_function_shares_bindings_and_returns():
    f = _nested_loops(30, ["acc.append(v29)", "if v29 == 2:", "    return 'early'"],
                      generator=False)
    assert f([1]) == [1]
    assert f([1, 2, 3]) == "early"


def test_outlined_generator_delegates_sends():
    f = _nested_loops(25, ["got = (yield (v0, v24))", "acc.append(got)"],
                      generator=True)
    g = f([1, 2])
    assert next(g) == (1, 1)
    assert g.send("a") == (2, 2)
    assert g.send("b") == ("end", ["a", "b"])


def test_break_and_continue_stay_with_their_loop():
    f = _nested_loops(30, ["acc.append(v29)", "if v29 == 0:", "    continue",
                           "acc.append(-v29)", "break"], generator=False)
    assert f([0, 3]) == [0, 3, -3]


# ── 4. a compile failure names the clause ───────────────────────────────────

@pytest.mark.parametrize("front_end", FRONT_ENDS)
def test_a_codegen_failure_names_the_predicate_file_and_line(
        tmp_path, monkeypatch, front_end):
    monkeypatch.setattr(codegen, "_MAX_BLOCK_DEPTH", 10 ** 6)   # outliner off
    n = 25
    with pytest.raises(GeneratedCodeError) as ei:
        _load(tmp_path, monkeypatch, front_end,
              f"q(X, Y) :- succ(X, Y).\n\np(X, V{n}) :- {_chain(n)}.\n",
              f"q(X, Y) <- succ(X, Y)\n\np(X, V{n}) <- ({_chain(n)})\n")
    e = ei.value
    assert isinstance(e, SyntaxError)
    assert e.predicate == "p/2"
    assert e.lineno == 3
    assert e.filename.endswith((".pl", SEAM)) and str(tmp_path) in e.filename
    msg = str(e)
    assert "p/2" in msg and f"{e.filename}:3" in msg
    assert "too many statically nested blocks" in msg
