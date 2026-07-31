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


# ── recursion ────────────────────────────────────────────────────────────────

# inner_rule's body must be UNSATISFIABLE with N free, or the outer predicate
# is satisfiable and _report_nearest stops at rung 1 ("argument 1 differs")
# before descent ever runs (see the constraint-solver note on TWO_ROUTES_SRC).
# The contradictory pair `N > 100, N < 0` forces descent; N = 5 still fails at
# the first conjunct, `N > 100`.
NESTED_SRC = """
inner_rule(N) <- (N > 100, N < 0),
outer_rule(N) <- (inner_rule(N)),

Test("nested failure") <- (
    outer_rule(5)
),
"""


def test_descends_through_intermediate_predicate(capsys, tmp_path):
    p = write(tmp_path, "nested.clausal", NESTED_SRC)
    assert main([str(p)]) == 1
    out = capsys.readouterr().out
    assert "N > 100" in out   # the inner predicate's conjunct, not inner_rule(N)
    assert "N = 5" in out


def test_cross_module_descent(capsys, tmp_path, monkeypatch):
    import sys as _sys
    monkeypatch.syspath_prepend(str(tmp_path))
    _sys.modules.pop("descent_lib", None)
    write(tmp_path, "descent_lib.clausal", """
        -module(descent_lib, [lib_check(N)])

        lib_check(N) <- (N > 100, N < 0)
    """)
    p = write(tmp_path, "use.clausal", """
        -import_from(descent_lib, [lib_check])

        Test("cross-module") <- (
            lib_check(5)
        ),
    """)
    try:
        assert main([str(p)]) == 1
        out = capsys.readouterr().out
        assert "no clause body survives" in out
        assert "N > 100" in out
        assert "N = 5" in out
        assert "descent_lib.clausal:" in out   # leaf names the DEFINING file
    finally:
        _sys.modules.pop("descent_lib", None)


# Same unsatisfiability requirement as NESTED_SRC (contradictory `N > 100,
# N < 0`), so the chain lvl1->lvl2->lvl3 reaches descent instead of rung 1.
# Descent caps at depth 2: lvl1's leaf lvl2(N) recurses to lvl2, whose leaf
# lvl3(N) is a Call at depth 2 and is rendered as-is — lvl3's body is never
# entered, so `N > 100` never surfaces.
DEEP_SRC = """
lvl3(N) <- (N > 100, N < 0),
lvl2(N) <- (lvl3(N)),
lvl1(N) <- (lvl2(N)),

Test("three levels") <- (
    lvl1(5)
),
"""


def test_depth_cap_stops_at_two_levels(capsys, tmp_path):
    p = write(tmp_path, "deep.clausal", DEEP_SRC)
    assert main([str(p)]) == 1
    out = capsys.readouterr().out
    assert "lvl3(" in out          # depth-2 leaf is the lvl3 CALL...
    assert "N > 100" not in out    # ...not lvl3's body — depth cap held
