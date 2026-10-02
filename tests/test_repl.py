"""Tests for clausal.repl.Solutions interactive solution iterator."""

import pytest
from clausal.repl import Solutions, _format_bindings
from tests._suffix import SEAM


# ── Helpers ───────────────────────────────────────────────────────────────────

def make_keys(*keys):
    """Return a callable that yields scripted keypresses one at a time."""
    it = iter(keys)
    def _read():
        return next(it)
    return _read


def run(iterator, *keys, capsys=None):
    """Run Solutions with scripted keys; return captured stdout."""
    import io, sys
    buf = io.StringIO()
    old = sys.stdout
    sys.stdout = buf
    try:
        s = Solutions(iterator, _read=make_keys(*keys))
        s._run()
    finally:
        sys.stdout = old
    return buf.getvalue()


# ── _format_bindings ──────────────────────────────────────────────────────────

def test_format_bindings_empty():
    # nv
    assert _format_bindings({}) == "true."


def test_format_bindings_single():
    # nv
    assert _format_bindings({"X": 1}) == "X is 1"


def test_format_bindings_multiple():
    # nv
    result = _format_bindings({"X": 1, "Y": 2})
    assert "X is 1" in result
    assert "Y is 2" in result


# ── No solutions ──────────────────────────────────────────────────────────────

def test_no_solutions():
    # nv
    out = run(iter([]))
    assert out.strip() == "false."


# ── Single solution, user stops with ENTER ────────────────────────────────────

def test_one_solution_enter_stops():
    # Only one solution → no prompt needed (exhausted automatically)
    # nv
    out = run(iter([{"X": 42}]))
    assert "X is 42" in out
    assert "No more solutions." in out


# ── Two solutions, user stops after first with ENTER ─────────────────────────

def test_two_solutions_enter_after_first():
    # nv
    out = run(iter([{"X": 1}, {"X": 2}]), '\r')
    assert "X is 1" in out
    assert "." in out
    assert "X is 2" not in out


# ── Two solutions, user stops after first with '.' ───────────────────────────

def test_two_solutions_dot_after_first():
    # nv
    out = run(iter([{"X": 1}, {"X": 2}]), '.')
    assert "X is 1" in out
    assert "X is 2" not in out


# ── Two solutions, user requests next with SPACE ─────────────────────────────

def test_two_solutions_space_advances():
    # nv
    out = run(iter([{"X": 1}, {"X": 2}]), ' ')
    assert "X is 1" in out
    assert "or" in out
    assert "X is 2" in out
    assert "No more solutions." in out


# ── Two solutions, user requests next with 'n' ───────────────────────────────

def test_two_solutions_n_advances():
    # nv
    out = run(iter([{"X": 1}, {"X": 2}]), 'n')
    assert "X is 1" in out
    assert "X is 2" in out


# ── ESC aborts cleanly (no terminal '.') ─────────────────────────────────────

def _content_lines(out):
    """Return non-blank lines with the prompt line stripped out."""
    lines = []
    for l in out.splitlines():
        stripped = l.strip()
        if stripped and "SPACE/n" not in stripped:
            lines.append(stripped)
    return lines


def test_esc_aborts():
    # nv
    out = run(iter([{"X": 1}, {"X": 2}]), '\x1b')
    lines = _content_lines(out)
    assert lines == ["X is 1"]  # only first solution, no '.' terminator


# ── 'q' aborts cleanly ────────────────────────────────────────────────────────

def test_q_aborts():
    # nv
    out = run(iter([{"X": 1}, {"X": 2}]), 'q')
    lines = _content_lines(out)
    assert lines == ["X is 1"]  # only first solution, no '.' terminator


# ── 'a' shows all remaining ───────────────────────────────────────────────────

def test_a_shows_all():
    # nv
    out = run(iter([{"X": 1}, {"X": 2}, {"X": 3}]), 'a')
    lines = _content_lines(out)
    assert lines == ["X is 1", "or", "X is 2", "or", "X is 3", "# No more solutions."]


# ── Three solutions, next then stop ──────────────────────────────────────────

def test_three_solutions_next_then_stop():
    # nv
    out = run(iter([{"X": 1}, {"X": 2}, {"X": 3}]), ' ', '\r')
    assert "X is 1" in out
    assert "X is 2" in out
    assert "X is 3" not in out


# ── or separator appears between solutions ────────────────────────────────────

def test_or_separator_between_solutions():
    # nv
    out = run(iter([{"X": 1}, {"X": 2}, {"X": 3}]), ' ', ' ')
    lines = [l.strip() for l in out.splitlines() if l.strip()]
    or_indices = [i for i, l in enumerate(lines) if l == "or"]
    assert len(or_indices) == 2


# ── A cell GOAL is solved, never iterated (post-flip hazard) ──────────────────
#
# After the PredicateMeta flip, calling a builtin class from Python BUILDS A
# CELL: ``clausal.between(1, 3, X)`` is the tuple ``("between", 1, 3, X)``.
# ``Solutions`` used to hand anything iterable to ``iter()``, so a cell was
# walked element by element -- four "solutions", X never bound: a silently
# wrong answer.  A str (an atom goal or a predicate handle) walked its chars.

def _cell_run(goal, *keys, **kw):
    import io, sys
    buf = io.StringIO()
    old = sys.stdout
    sys.stdout = buf
    try:
        Solutions(goal, _read=make_keys(*keys), **kw)._run()
    finally:
        sys.stdout = old
    return buf.getvalue()


def test_builtin_cell_goal_is_solved_with_module():
    from clausal import Module, Var, between
    X = Var()
    goal = between(1, 3, X)
    assert type(goal) is tuple  # the hazard's premise: a cell, iterable
    sols = list(Solutions(goal, _varnames={"X": X},
                          module=Module("repl_cell_goal"))._iter)
    assert sols == [{"X": 1}, {"X": 2}, {"X": 3}]


def test_builtin_cell_goal_displays_its_solutions():
    from clausal import Module, Var, between
    X = Var()
    out = _cell_run(between(1, 2, X), "a", _varnames={"X": X},
                    module=Module("repl_cell_goal_display"))
    assert "X is 1" in out and "X is 2" in out
    assert "between" not in out  # the functor is not a "solution"


def test_cell_goal_unnamed_vars_are_reported():
    from clausal import Module, Var, between
    X = Var()
    sols = list(Solutions(between(1, 2, X),
                          module=Module("repl_cell_goal_unnamed"))._iter)
    assert [list(s.values()) for s in sols] == [[1], [2]]


def test_unqualified_cell_goal_without_module_is_loud():
    from clausal import Var, between
    from clausal.logic.exceptions import LogicException
    with pytest.raises(LogicException, match="existence_error|module"):
        Solutions(between(1, 3, Var()))  # raises at construction


def test_user_predicate_cell_goal_and_qualified_cell(tmp_path):
    from clausal import Var
    from clausal.import_hook import _load_module
    src = tmp_path / f"repl_cell_goal_user{SEAM}"
    src.write_text("colour(1),\ncolour(2),\nok(),\n")
    mod = _load_module("repl_cell_goal_user", str(src))
    X = Var()
    assert list(Solutions(("colour", X), _varnames={"X": X},
                          module=mod)._iter) == [{"X": 1}, {"X": 2}]
    Y = Var()
    assert list(Solutions((":", mod, ("colour", Y)),
                          _varnames={"Y": Y})._iter) == [{"Y": 1}, {"Y": 2}]
    # A str goal (an atom goal, or a predicate handle such as ``mod.ok``)
    # is solved -- iterating it would walk its characters.
    assert list(Solutions("ok", module=mod)._iter) == [{}]
    assert list(Solutions(mod.ok, module=mod)._iter) == [{}]


# ── query()'s deprecation text names the ruled form ───────────────────────────

def test_query_deprecation_warning_recommends_solve_and_call():
    import warnings
    from clausal import Module, Var, query, between
    X = Var()
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        list(query(between(1, 1, X), {"X": X}, Module("repl_query_warn")))
    msgs = [str(x.message) for x in w
            if issubclass(x.category, DeprecationWarning)]
    assert len(msgs) == 1, msgs
    msg = msgs[0]
    assert 'solve(("pred", X := Var()), module=m)' in msg
    assert 'call("pred", X := Var(), module=m)' in msg
    assert "for trail in pred(X := Var())" not in msg


def test_query_docstring_does_not_recommend_iterating_a_call():
    from clausal.logic.solve import query
    doc = query.__doc__
    assert "for trail in greeting(X := Var())" not in doc
    assert 'solve(("greeting", X := Var()), module=m)' in doc
