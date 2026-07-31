"""Stage-4 descent diagnostics + rung-2 examples for ``python -m clausal.testing``.

Rung 3 ("no solution for ANY arguments") used to carry no value — measured
0/29 recovery in study 13.  See
``docs/superpowers/specs/2026-07-30-assertion-diagnostic-descent-design.md``.
"""

from __future__ import annotations

import textwrap

from clausal.testing import main


def write(tmp_path, name, src):
    p = tmp_path / name
    p.write_text(textwrap.dedent(src).lstrip())
    return p


# ── rung 2: satisfiable, but 2+ arguments differ ─────────────────────────────

PAIR_SRC = """
pairx("a", 1),
pairx("b", 2),

Test("both arguments differ") <- (
    pairx("c", 3)
),
"""


def test_two_plus_args_differ_shows_example_solutions(capsys, tmp_path):
    p = write(tmp_path, "pair.clausal", PAIR_SRC)
    assert main([str(p)]) == 1
    out = capsys.readouterr().out
    assert "two or more arguments differ" in out   # old sentence survives
    assert "it does have:" in out                  # new suffix
    assert "pairx('a', 1)" in out                  # an actual solution, rendered


# ── rung 3: descent into the failing predicate ───────────────────────────────

GUARD_SRC = """
chk_range(PCT) <- (
    PCT >= 0,
    PCT > 100,
    PCT <= 100
),

Test("contradictory guards") <- (
    chk_range(50)
),
"""


def test_contradictory_guard_named_with_value(capsys, tmp_path):
    p = write(tmp_path, "guard.clausal", GUARD_SRC)
    assert main([str(p)]) == 1
    out = capsys.readouterr().out
    assert "no clause body survives" in out
    assert "PCT > 100" in out       # the failing conjunct, source-faithful
    assert "PCT = 50" in out        # ...with the head binding that dooms it


# Each route's constraints must be UNSATISFIABLE even with the argument free,
# or the whole-argument-hole probe (rung 2) finds a degenerate solution and
# descent never runs: the clausal constraint solver leaves a lone one-sided
# bound (`X < 0`) satisfiable with X unbound, so a contradictory pair
# (`X < 0, X > 100`) is what forces rung 3.  X = 5 still makes each clause fail
# at the asserted conjunct.
TWO_ROUTES_SRC = """
-private([small, big])

classify(X, small) <- (X < 10, X < 0, X > 100),
classify(X, big) <- (X > 10, X < 0),

Test("two routes both fail") <- (
    classify(5, _KIND)
),
"""


def test_each_clause_route_gets_a_leaf(capsys, tmp_path):
    p = write(tmp_path, "routes.clausal", TWO_ROUTES_SRC)
    assert main([str(p)]) == 1
    out = capsys.readouterr().out
    assert "X < 0" in out    # clause 1's first failing conjunct (5 < 10 passed)
    assert "X > 10" in out   # clause 2's
    assert "X = 5" in out


DYN_SRC = """
-dynamic(dynp/1)

Test("zero-clause predicate") <- (
    dynp(1)
),
"""


def test_zero_clause_predicate_keeps_old_message(capsys, tmp_path):
    p = write(tmp_path, "dyn.clausal", DYN_SRC)
    assert main([str(p)]) == 1
    out = capsys.readouterr().out
    assert "no solution for ANY arguments" in out
    assert "no clause body survives" not in out
