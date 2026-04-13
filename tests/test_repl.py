"""Tests for clausal.repl.Solutions interactive solution iterator."""

import pytest
from clausal.repl import Solutions, _format_bindings


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
    assert lines == ["X is 1", "or", "X is 2", "or", "X is 3", "No more solutions."]


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
