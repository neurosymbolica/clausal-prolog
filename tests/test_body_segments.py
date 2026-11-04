"""A long conjunction compiles as a chain of segment functions.

``clausal.logic.compiler.body_segments`` cuts a conjunction that nests
deeper than CPython allows into module-level segment generators run as
trampoline frames (todo/done/
pl-readers-recursion-limit-on-long-clause-bodies-2026-10-02.md, operator
ruling 2026-11-03).  The segmented code must give the inline code's
answers, in its order, with its exceptions, and keep cut, if-then-else,
catch/3, negation and findall/3 semantics across segment boundaries.

Each program below is run twice: with ``CLAUSAL_BODY_SEGMENT_HEIGHT=2``
(every conjunction of two goals or more is cut, so most goals sit in a
segment of their own and every construct straddles a boundary) and with
segmentation off; the two must agree, and the segmented run must really
have hoisted segments.
"""
from __future__ import annotations

import ast
import itertools
import textwrap
import warnings

import pytest

import clausal.codegen as codegen
import clausal.import_hook  # noqa: F401 -- installs the meta-path finder
from clausal.import_hook import _load_module
from clausal.logic.compiler import body_segments
from clausal.logic.exceptions import LogicException
from clausal.logic.solve import call as pcall, call_with_last
from clausal.logic.variables import Var, deref, walk

_names = itertools.count()

PROGRAM = """
q(X, Y) :- Y is X + 1.
r(1).
r(2).
r(3).

% a cut in the third of five segments: A..E commit to their first answers,
% the later goals still backtrack, the second clause is cut away.
cut5(L) :- r(A), r(B), r(C), r(D), r(E), !, r(F), r(G), r(H), r(I),
           L = [A, B, C, D, E, F, G, H, I].
cut5(none).

% a cut inside an if-then-else branch and inside a disjunction: both cut the clause.
cut_ite(X, L) :- r(A), r(B), ( X > 1 -> r(C), !, r(D) ; r(C), r(D) ), r(E),
                 L = [A, B, C, D, E].
cut_ite(_, none).
cut_or(L) :- r(A), r(B), ( r(C), C >= 2, ! ; r(C) ), r(D), r(E), L = [A, B, C, D, E].
cut_or(none).

% an if-then-else whose condition and branches are long conjunctions.
ite(X, L) :- r(A), r(B),
             ( r(P), q(P, P1), q(P1, P2), P2 =:= X + 2 -> r(C), r(D), q(C, E), q(E, F)
             ; r(C), D = 0, E = 0, F = 0 ),
             r(G), L = [A, B, C, D, E, F, G].

% catch/3 around a long goal that throws part way; the continuation after
% the catch throws too, and that must NOT be caught by the catch.
thrower(B, C, X) :- ( B + C =:= X -> throw(found(B, C)) ; true ).
catch_span(X, L) :- r(A),
                    catch((r(B), r(C), thrower(B, C, X), r(D), q(D, E)),
                          found(P, Q), (D = P, E = Q)),
                    r(F), ( F =:= 3, A =:= 2 -> throw(after(A, B)) ; true ),
                    L = [A, B, C, D, E, F].
catch_outer(X, L) :- catch(catch_span(X, L), after(P, Q), L = after(P, Q)).

% \\+ of a long conjunction, true for some A and false for others.
naf(L) :- r(A), r(Z), \\+ (r(B), r(C), r(D), q(B, B1), B1 + C + D =:= A + 3 * Z),
          r(F), L = [A, Z, F].

% findall/3 of a long goal, inside a long body.
fa(L) :- r(A), r(B), findall(X-Y, (r(X), r(Y), q(X, X1), X1 + Y =:= A + B), S),
         r(C), length(S, N), L = [A, B, C, N, S].

% an uncaught error deep in the body, after some answers.
err(L) :- r(A), r(B), r(C), r(D), ( A + B + C + D > 9 -> atom_length(_, _) ; true ),
          r(E), L = [A, B, C, D, E].

% constraints posted early, woken by later segments.
coroutines(L) :- dif(A, B), freeze(C, C > 1), r(A), r(B), r(C), r(D),
                 q(D, E), L = [A, B, C, D, E].

% a deterministic long body: its only answer is the last one.
det(L) :- q(0, A), q(A, B), q(B, C), q(C, D), q(D, E), q(E, F), q(F, G),
          L = [A, B, C, D, E, F, G].

% an if-then-else early in a long body: the rest of the body is the
% continuation both branches share (a later pass copies it apart).
ite_long(X, L) :- r(A), ( A > X -> B = big ; B = small ), q(A, V1), LONG_TAIL,
                  L = [A, B, V60].

% a long recursive body.
cnt(N, N, A, A).
cnt(I, N, A0, A) :- I < N, I >= 0, A0 >= 0, succ(I, I1), q(A0, A1), q(A1, A2),
                    A3 is A2 - 1, cnt(I1, N, A3, A).
""".replace("LONG_TAIL", ", ".join(f"q(V{i}, V{i + 1})" for i in range(1, 60)))

QUERIES = [
    ("cut5", 1), ("cut_ite", 2, "x1"), ("cut_ite", 2, "x2"), ("cut_or", 1),
    ("ite", 2, "x1"), ("ite", 2, "x9"),
    ("catch_span", 2, "x4"), ("catch_outer", 2, "x4"), ("catch_outer", 2, "x9"),
    ("naf", 1), ("fa", 1), ("err", 1), ("coroutines", 1), ("det", 1),
    ("cnt", 4, "cnt"), ("ite_long", 2, "x1"),
]


def _load(tmp_path, src):
    name = f"bodyseg{next(_names)}"
    path = tmp_path / f"{name}.pl"
    path.write_text(textwrap.dedent(src).lstrip())
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")      # singleton-variable lint
        return _load_module(name, str(path)).__dict__["$module"]


def _run(m, query):
    name, arity = query[0], query[1]
    tag = query[2] if len(query) > 2 else None
    out = Var()
    if tag == "cnt":
        args = (0, 30, 0, out)
    elif tag and tag.startswith("x"):
        args = (int(tag[1:]), out)
    else:
        args = (out,)
    answers = []
    try:
        for _ in pcall(name, *args, module=m):
            answers.append(walk(deref(out)))
    except LogicException as exc:
        answers.append(("raised", walk(deref(exc.term))))
    return _fresh_vars_numbered(answers)


def _fresh_vars_numbered(value):
    """Unbound variables in an answer by first appearance, not identity."""
    seen: dict = {}

    def go(x):
        if isinstance(x, Var):
            return seen.setdefault(id(x), f"_G{len(seen)}")
        if isinstance(x, list):
            return [go(y) for y in x]
        if isinstance(x, tuple):
            return tuple(go(y) for y in x)
        return x
    return go(value)


def _both(tmp_path, monkeypatch, src, queries):
    hoisted, refused = [], []
    real_hoist = body_segments.hoist_segments

    def spy(func_def, segments):
        try:
            funcs = real_hoist(func_def, segments)
        except body_segments.SegmentRefused as exc:
            refused.append((func_def.name, str(exc)))
            raise
        hoisted.extend(funcs)
        return funcs

    monkeypatch.setattr(body_segments, "hoist_segments", spy)
    monkeypatch.setenv(body_segments.ENV_VAR, "2")
    m = _load(tmp_path, src)
    split = {q: _run(m, q) for q in queries}
    assert hoisted, "nothing was cut into segments"
    assert not refused, refused
    monkeypatch.delenv(body_segments.ENV_VAR)
    monkeypatch.setattr(body_segments, "SPLIT_ABOVE", 10 ** 9)
    count = len(hoisted)
    m = _load(tmp_path, src)
    plain = {q: _run(m, q) for q in queries}
    assert len(hoisted) == count, "the plain run cut segments"
    return split, plain


def test_segmented_answers_equal_inline_answers(tmp_path, monkeypatch):
    split, plain = _both(tmp_path, monkeypatch, PROGRAM, QUERIES)
    bad = [q for q in QUERIES if split[q] != plain[q]]
    assert not bad, {q: (split[q], plain[q]) for q in bad}


def test_the_expected_answers(tmp_path, monkeypatch):
    # Pin the semantics too, not only the agreement.
    split, _ = _both(tmp_path, monkeypatch, PROGRAM, QUERIES)
    cut5 = split[("cut5", 1)]
    assert len(cut5) == 81 and cut5[0] == [1] * 9 and "none" not in cut5
    assert split[("cut_ite", 2, "x2")] == [[1, 1, 1, d, e] for d in (1, 2, 3)
                                           for e in (1, 2, 3)]
    assert split[("cut_or", 1)] == [[1, 1, 2, d, e] for d in (1, 2, 3)
                                    for e in (1, 2, 3)]
    # The continuation's throw is not the inner catch's: it ends the search.
    span = split[("catch_span", 2, "x4")]
    assert span[-1] == ("raised", ("after", 2, 1))
    assert split[("catch_outer", 2, "x4")][-1] == ("after", 2, 1)
    err = split[("err", 1)]
    assert err[-1][0] == "raised" and err[-1][1][0] == "error"
    assert split[("det", 1)] == [[1, 2, 3, 4, 5, 6, 7]]
    assert split[("cnt", 4, "cnt")] == [30]


def test_the_last_answer_is_still_known(tmp_path, monkeypatch):
    # FINAL: a deterministic long body's answer is reported as the last.
    monkeypatch.setenv(body_segments.ENV_VAR, "2")
    m = _load(tmp_path, PROGRAM)
    L = Var()
    lasts = [last for _, last in call_with_last("det", L, module=m)]
    assert lasts == [True]
    lasts = [last for _, last in call_with_last("cut5", L, module=m)]
    assert lasts[:-1] == [False] * 80


def test_a_long_body_needs_no_outliner(tmp_path, monkeypatch):
    # At the default thresholds a 3000-goal body compiles as segments:
    # CPython never refuses it, so the old outliner is never asked.
    def no_outliner(node, force=False):
        raise AssertionError("the outliner ran")

    monkeypatch.delenv(body_segments.ENV_VAR, raising=False)
    monkeypatch.setattr(codegen, "split_deep_nesting", no_outliner)
    n = 3000
    goals = ", ".join(f"q({'X' if i == 1 else f'V{i - 1}'}, V{i})"
                      for i in range(1, n + 1))
    m = _load(tmp_path, f"""
        q(X, Y) :- Y is X + 1.
        r(1).
        r(2).
        p(X, Y, Z) :- {goals}, r(Z), Y = V{n}.
        """)
    Y, Z = Var(), Var()
    assert [(walk(deref(Y)), walk(deref(Z)))
            for _ in pcall("p", 0, Y, Z, module=m)] == [(n, 1), (n, 2)]


def _canonical(text):
    """Variable names carry process-wide numbers: number them by first use."""
    import re
    seen: dict = {}
    return re.sub(r"_v\d+", lambda mo: seen.setdefault(mo.group(), f"_v#{len(seen)}"),
                  text)


def test_a_body_under_the_limit_compiles_as_before(tmp_path, monkeypatch):
    # 12 goals nest ~14 deep: under the limit, so the code is exactly what
    # it is with segmentation off.
    dumps = []
    real = codegen.functiondef_to_function

    def spy(node, globals_=None, filename="<template>"):
        if node.name.startswith("p__"):
            dumps.append((_canonical(ast.dump(node)),
                          getattr(node, "_clausal_segments", None)))
        return real(node, globals_, filename)

    monkeypatch.setattr("clausal.logic.compiler.predicate.functiondef_to_function", spy)
    monkeypatch.delenv(body_segments.ENV_VAR, raising=False)
    src = """
        q(X, Y) :- Y is X + 1.
        p(X, Y) :- q(X, A), q(A, B), q(B, C), q(C, D), q(D, E), q(E, F),
                   q(F, G), q(G, H), q(H, I), q(I, J), q(J, K), q(K, Y).
        """
    _load(tmp_path, src)
    monkeypatch.setattr(body_segments, "SPLIT_ABOVE", 10 ** 9)
    _load(tmp_path, src)
    assert len(dumps) == 2
    assert dumps[0][1] is None and dumps[1][1] is None
    assert dumps[0][0] == dumps[1][0]


def test_a_refused_segment_rebuilds_without_segments(tmp_path, monkeypatch):
    # Any refusal falls back to the inline body (and the old outliner).
    def refuse(func_def, segments):
        raise body_segments.SegmentRefused("test")

    monkeypatch.setattr(body_segments, "hoist_segments", refuse)
    monkeypatch.setenv(body_segments.ENV_VAR, "2")
    m = _load(tmp_path, PROGRAM)
    assert len(_run(m, ("cut5", 1))) == 81


def test_a_cached_query_runs_its_segments_on_the_new_variables(tmp_path, monkeypatch):
    # A query compiled once is reused for the next query of the same shape
    # with the new variables rebound in a copy of its globals: its segment
    # functions must read the copy too.
    import clausal
    monkeypatch.setenv(body_segments.ENV_VAR, "2")
    m = _load(tmp_path, PROGRAM)
    got = []
    for start in (0, 10):
        A, B, C = Var(), Var(), Var()
        goal = (",", ("q", start, A), (",", ("r", B), (",", ("q", A, C), ("r", B))))
        got.append([(walk(deref(A)), walk(deref(B)), walk(deref(C)))
                    for _ in clausal.solve(goal, m)])
    assert got == [[(1, b, 2) for b in (1, 2, 3)], [(11, b, 12) for b in (1, 2, 3)]]


def _nested_long_negations(depth, width=20):
    """``\\+ \\+ (g, ..., g, \\+ \\+ (g, ..., g, ...))``: *depth* levels, each
    a conjunction of *width* + 1 goals, so every level is long enough to be
    cut on its own."""
    goal = "r(1)"
    for _ in range(depth):
        goal = "\\+ \\+ (" + ", ".join(["r(1)"] * width) + f", {goal})"
    return goal


def test_nested_long_conjunctions_are_lowered_a_bounded_number_of_times(
        tmp_path, monkeypatch):
    # A long conjunction is folded once plain, and folded again in segments
    # only if it nests too deep.  The refold lowered its goals again, so a
    # long conjunction inside a long conjunction inside ... was lowered
    # 2**depth times: depth 10 took 7 s to load
    # (todo/done/load-time-doubles-per-nested-negation-mark-undo-invariant-2026-10-16.md).
    # Each sequence is now folded at most twice: a nested one its own fold
    # cut is not lowered again by the refold (it calls the same chain).
    monkeypatch.delenv(body_segments.ENV_VAR, raising=False)
    depth = 14
    calls = 0
    real = body_segments.fold_sequence
    # Two predicates, each with depth + 1 sequences (the clause body too).
    bound = 2 * 2 * (depth + 1)

    def counting(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls > bound:
            raise AssertionError(f"fold_sequence called over {bound} times")
        return real(*args, **kwargs)

    monkeypatch.setattr(body_segments, "fold_sequence", counting)
    m = _load(tmp_path, f"""
        r(1).
        p(yes) :- {_nested_long_negations(depth)}.
        q(yes) :- {_nested_long_negations(depth)}, r(2).
        """)
    assert _run(m, ("p", 1)) == ["yes"]
    assert _run(m, ("q", 1)) == []


def test_a_long_conjunction_in_a_refolded_one_is_cut_too(
        tmp_path, monkeypatch):
    # A long conjunction nested in one that is refolded in segments left
    # the inner fold's segments unreached, so the predicate was refused and
    # rebuilt without segments (by the outliner, which dies on a long
    # enough body).  The refold now calls the inner fold's chain.
    monkeypatch.delenv(body_segments.ENV_VAR, raising=False)
    refused = _record_refusals(monkeypatch)
    src = f"""
        r(1).
        p(yes) :- {_nested_long_negations(3)}.
        q(yes) :- {_nested_long_negations(3)}, r(2).
        """
    hoisted = _record_hoisted(monkeypatch)
    m = _load(tmp_path, src)
    assert not refused, refused
    assert len(hoisted) >= 4
    assert _run(m, ("p", 1)) == ["yes"]
    assert _run(m, ("q", 1)) == []


def _record_refusals(monkeypatch):
    """Every ``SegmentRefused`` raised, wherever it is caught."""
    refused: list = []
    real = body_segments.SegmentRefused.__init__

    def init(self, *args):
        refused.append(args)
        real(self, *args)

    monkeypatch.setattr(body_segments.SegmentRefused, "__init__", init)
    return refused


def _record_hoisted(monkeypatch):
    hoisted: list = []
    real = body_segments.hoist_segments

    def spy(func_def, segments):
        funcs = real(func_def, segments)
        hoisted.extend(funcs)
        return funcs

    monkeypatch.setattr(body_segments, "hoist_segments", spy)
    return hoisted


# ── the production path: plain fold first, refold when too deep ────────────
#
# ``CLAUSAL_BODY_SEGMENT_HEIGHT`` cuts every sequence without folding it
# plain first.  The default thresholds fold plain, then refold a sequence
# that turns out too deep; these tests lower the thresholds so that path
# runs over short programs, with long conjunctions nested in catch/3,
# if-then-else, \\+, disjunction and findall/3 inside long ones.

_CHAIN = ", ".join(f"q(W{i}, W{i + 1})" for i in range(8))

NESTED = f"""
q(X, Y) :- Y is X + 1.
r(1).
r(2).

n_catch(L) :- r(A), q(A, B), q(B, C),
              catch((W0 = C, {_CHAIN}), _, true), r(Z), L = [A, C, W8, Z].
n_catch_throw(L) :- r(A), q(A, B),
              catch((W0 = B, {_CHAIN}, W8 > 9, throw(big(W8))), big(E), W8 = E),
              r(Z), L = [A, W8, Z].
n_ite(L) :- r(A), q(A, B), q(B, C),
            ( r(Z) -> W0 = C, {_CHAIN} ; W8 = none, Z = none ), r(D), L = [A, W8, Z, D].
n_ite_else(L) :- r(A), q(A, B), q(B, C),
            ( A > 5 -> W8 = none ; W0 = C, {_CHAIN} ), r(D), L = [A, W8, D].
n_naf(L) :- r(A), q(A, B), q(B, C),
            \\+ (W0 = C, {_CHAIN}, W8 < A), r(Z), L = [A, C, Z].
n_or(L) :- r(A), q(A, B), q(B, C),
           ( W0 = C, {_CHAIN}, r(W9) ; W8 = A, W9 = 0 ), r(Z), L = [A, W8, W9, Z].
n_findall(L) :- r(A), q(A, B), q(B, C),
           findall(W8, (r(W0), {_CHAIN}), S), r(Z), L = [A, S, Z].
n_deep(L) :- r(A), q(A, B), q(B, C),
             catch(( r(Z) -> W0 = C, {_CHAIN},
                     \\+ (q(W8, X0), {_CHAIN.replace("W", "X")}, X8 < 0) ; Z = 0 ),
                   _, true),
             r(D), L = [A, W8, Z, D].
n_cut_cond(L) :- r(A), r(B), ( r(C), C > A, !, r(D), D > B -> r(E), E > C ; E = 0, C = 0, D = 0 ),
                 r(F), L = [A, B, C, D, E, F].
"""

NESTED_QUERIES = [(n, 1) for n in (
    "n_catch", "n_catch_throw", "n_ite", "n_ite_else", "n_naf", "n_or",
    "n_findall", "n_deep", "n_cut_cond")]


def _production(monkeypatch, split_above):
    monkeypatch.delenv(body_segments.ENV_VAR, raising=False)
    monkeypatch.setattr(body_segments, "SPLIT_ABOVE", split_above)
    monkeypatch.setattr(body_segments, "MIN_OPS", 2)
    monkeypatch.setattr(body_segments, "SEGMENT_HEIGHT", 2)


@pytest.mark.parametrize("split_above", [1, 3, 6])
def test_nested_long_goals_on_the_production_path(tmp_path, monkeypatch, split_above):
    refused = _record_refusals(monkeypatch)
    hoisted = _record_hoisted(monkeypatch)
    _production(monkeypatch, split_above)
    m = _load(tmp_path, NESTED)
    split = {q: _run(m, q) for q in NESTED_QUERIES}
    assert hoisted, "nothing was cut into segments"
    assert not refused, refused
    monkeypatch.setattr(body_segments, "SPLIT_ABOVE", 10 ** 9)
    count = len(hoisted)
    m = _load(tmp_path, NESTED)
    plain = {q: _run(m, q) for q in NESTED_QUERIES}
    assert len(hoisted) == count, "the plain run cut segments"
    bad = [q for q in NESTED_QUERIES if split[q] != plain[q]]
    assert not bad, {q: (split[q], plain[q]) for q in bad}
    assert plain[("n_catch", 1)] == [[a, a + 2, a + 10, z]
                                     for a in (1, 2) for z in (1, 2)]


def test_a_nested_catch_in_a_body_too_long_for_the_outliner(tmp_path, monkeypatch):
    # 12000 goals with a 30-goal catch/3 near the end: the catch is cut
    # while folding the body plain, the body is refolded.  It was refused
    # and rebuilt by the outliner, which died (``GeneratedCodeError``:
    # maximum recursion depth exceeded).  A 12000-goal body takes about
    # 15 s to load with or without the catch.
    def no_outliner(node, force=False):
        raise AssertionError("the outliner ran")

    monkeypatch.delenv(body_segments.ENV_VAR, raising=False)
    monkeypatch.setattr(codegen, "split_deep_nesting", no_outliner)
    refused = _record_refusals(monkeypatch)
    n = 12000
    chain = ", ".join(f"q(V{i}, V{i + 1})" for i in range(n))
    inner = ", ".join(f"q(W{i}, W{i + 1})" for i in range(30))
    m = _load(tmp_path, f"""
        q(X, Y) :- Y is X + 1.
        r(1).
        r(2).
        p(L) :- V0 = 0, {chain}, catch((W0 = V{n}, {inner}), _, true), r(Z), L = [W30, Z].
        """)
    assert not refused, refused
    assert _run(m, ("p", 1)) == [[n + 30, 1], [n + 30, 2]]
