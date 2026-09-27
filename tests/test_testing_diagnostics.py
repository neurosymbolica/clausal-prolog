"""Goal-level failure diagnostics for ``python -m clausal.testing``.

A failing test used to report only its name — no goal, no expected, no actual,
no line number.  See ``todo/done/test-failure-goal-level-diagnostics.md``.

The consumer is an automated repair loop, so these assertions are about the
*content* of the failure report, not its cosmetics.
"""

from __future__ import annotations

import textwrap
import time

import pytest

from clausal.testing import main


def write(tmp_path, name, src):
    p = tmp_path / name
    p.write_text(textwrap.dedent(src).lstrip())
    return p


# ── fixtures ─────────────────────────────────────────────────────────────────

BO_SRC = """
-double_quotes(atom)
-private([verdict(A, B, C), cite(D), art52, beneficial_owner, not_beneficial_owner])

chain_subject("parallel_below_threshold"),
chain_subject("simple"),

chain_assess(SUBJ, verdict(beneficial_owner, 2500, [cite(art52)])) <- (
    chain_subject(SUBJ)
),

test("public interface resolves on the parallel_below_threshold fixture") <- (
    chain_subject("parallel_below_threshold"),
    chain_assess("parallel_below_threshold",
        verdict(not_beneficial_owner, _BPS, _CITES))
),
"""

FIRST_GOAL_SRC = """
-double_quotes(atom)
chain_subject("simple"),

test("first conjunct fails") <- (
    chain_subject("absent"),
    chain_subject("simple")
),
"""

BINDINGS_SRC = """
-double_quotes(atom)
prc("alpha", 10),
prc("beta", 20),

test("later goal fails after a binding") <- (
    prc("alpha", NUM),
    prc("gamma", NUM)
),
"""

PASSING_SRC = """
-double_quotes(atom)
prc("alpha", 10),

test("passes") <- (
    prc("alpha", NUM),
    NUM > 5
),
"""

ERROR_SRC = """
-double_quotes(atom)
prc("alpha", 10),

test("raises") <- (
    prc("alpha", NUM),
    atom_length(NUM, LEN),
    LEN > 0
),
"""


# ── stage 1: which goal, its source, the line number ─────────────────────────


def test_later_goal_index_and_source_reported(capsys, tmp_path):
    p = write(tmp_path, "bo.clausal", BO_SRC)
    assert main([str(p)]) == 1
    out = capsys.readouterr().out
    assert "goal 2 of 2 failed" in out
    # the *source text* of the failing goal, not a Python repr
    assert "chain_assess(" in out
    assert "not_beneficial_owner" in out
    assert "_BPS" in out


def test_first_goal_failure_reported(capsys, tmp_path):
    p = write(tmp_path, "first.clausal", FIRST_GOAL_SRC)
    assert main([str(p)]) == 1
    out = capsys.readouterr().out
    assert "goal 1 of 2 failed" in out
    assert "chain_subject(absent)" in out
    # must NOT blame the second (satisfiable) goal
    assert "goal 2 of 2 failed" not in out


def test_line_number_reported(capsys, tmp_path):
    p = write(tmp_path, "bo.clausal", BO_SRC)
    main([str(p)])
    out = capsys.readouterr().out
    lineno = BO_SRC.lstrip().splitlines().index(
        'test("public interface resolves on the parallel_below_threshold fixture") <- ('
    ) + 1
    assert f"bo.clausal:{lineno} :: public interface resolves" in out


# ── stage 2: bindings established before the failing goal ────────────────────


def test_bindings_before_failing_goal_reported(capsys, tmp_path):
    p = write(tmp_path, "bind.clausal", BINDINGS_SRC)
    assert main([str(p)]) == 1
    out = capsys.readouterr().out
    assert "goal 2 of 2 failed" in out
    assert "bindings at failure:" in out
    assert "NUM = 10" in out


def test_no_prior_bindings_is_stated(capsys, tmp_path):
    p = write(tmp_path, "first.clausal", FIRST_GOAL_SRC)
    main([str(p)])
    out = capsys.readouterr().out
    assert "bindings at failure: (none" in out


# ── stage 3: nearest solution ────────────────────────────────────────────────


def test_nearest_solution_reported(capsys, tmp_path):
    p = write(tmp_path, "bo.clausal", BO_SRC)
    main([str(p)])
    out = capsys.readouterr().out
    assert "did not unify" in out
    # the actual computed verdict — the whole point
    assert "beneficial_owner, 2500" in out
    assert "cite(art52)" in out


def test_unsatisfiable_goal_says_so(capsys, tmp_path):
    p = write(tmp_path, "first.clausal", FIRST_GOAL_SRC)
    main([str(p)])
    out = capsys.readouterr().out
    # chain_subject/1 IS satisfiable, just not with "absent"
    assert "did not unify" in out
    assert "chain_subject(simple)" in out


def test_predicate_with_no_solutions_at_all(capsys, tmp_path):
    p = write(tmp_path, "none.clausal", """
        -double_quotes(atom)
        chk(X) <- (X > 0, X < 0),

        test("never") <- (
            chk(5)
        ),
    """)
    main([str(p)])
    out = capsys.readouterr().out
    assert "goal 1 of 1 failed" in out
    assert "no solution" in out


def test_long_goal_is_wrapped_at_argument_boundaries(capsys, tmp_path):
    p = write(tmp_path, "long.clausal", """
        -double_quotes(atom)
        -private([bo_verdict(A, B, C), cite(D), art52_1, beneficial_owner, not_beneficial_owner])

        bo_chain_subject("parallel_below_threshold"),

        bo_chain_assess(SUBJ, bo_verdict(beneficial_owner, 2500, [cite(art52_1)])) <- (
            bo_chain_subject(SUBJ)
        ),

        test("public interface resolves") <- (
            bo_chain_subject("parallel_below_threshold"),
            bo_chain_assess("parallel_below_threshold",
                bo_verdict(not_beneficial_owner, _EFFECTIVE_OWNERSHIP_BPS, _CITATIONS))
        ),
    """)
    main([str(p)])
    out = capsys.readouterr().out
    assert "      bo_chain_assess(parallel_below_threshold," in out
    # continuation aligned under the open paren
    assert "\n" + " " * len("      bo_chain_assess(") + "bo_verdict(" in out


# ── side effects ─────────────────────────────────────────────────────────────


def test_side_effecting_test_is_flagged(capsys, tmp_path):
    """The re-run genuinely re-applies assertz; say so rather than hide it."""
    p = write(tmp_path, "sfx.clausal", """
        -double_quotes(atom)
        -dynamic(seen/1)

        test("side effects") <- (
            assertz(seen(1)),
            1 == 2
        ),
    """)
    assert main([str(p)]) == 1
    out = capsys.readouterr().out
    assert "goal 2 of 2 failed" in out
    assert "this test has side effects" in out


def test_diagnostic_output_is_not_polluted_by_test_writes(capsys, tmp_path):
    p = write(tmp_path, "noisy.clausal", """
        -double_quotes(atom)
        test("noisy") <- (
            writeln("NOISE-FROM-BODY"),
            1 == 2
        ),
    """)
    main([str(p)])
    out = capsys.readouterr().out
    # printed once by the real run, not again by the diagnostic re-run
    assert out.count("NOISE-FROM-BODY") == 1


# ── passing tests and the summary contract ───────────────────────────────────


def test_passing_output_unchanged(capsys, tmp_path):
    p = write(tmp_path, "ok.clausal", PASSING_SRC)
    assert main([str(p)]) == 0
    out = capsys.readouterr().out
    assert "FAILURES" not in out
    assert "goal " not in out
    assert "1 tests: 1 passed, 0 failed [PASSED]" in out


def test_summary_line_and_exit_code_unchanged(capsys, tmp_path):
    p = write(tmp_path, "bo.clausal", BO_SRC)
    assert main([str(p)]) == 1
    out = capsys.readouterr().out
    assert "1 tests: 0 passed, 1 failed [FAILED]" in out
    assert out.startswith("\nFAILURES:")


# ── errors, not failures ─────────────────────────────────────────────────────


def test_erroring_test_keeps_error_and_locates_goal(capsys, tmp_path):
    p = write(tmp_path, "err.clausal", ERROR_SRC)
    assert main([str(p)]) == 1
    out = capsys.readouterr().out
    assert "type_error" in out           # the original message is preserved
    assert "goal 2 of 3 raised" in out   # and the offending conjunct is named
    assert "atom_length" in out


# ── the diagnostic must never change a verdict ───────────────────────────────


def test_diagnostic_crash_degrades_gracefully(capsys, tmp_path, monkeypatch):
    import clausal.testing as t

    def boom(*a, **k):
        raise ValueError("diagnostic exploded")

    monkeypatch.setattr(t, "_diagnose_into", boom)
    p = write(tmp_path, "bo.clausal", BO_SRC)
    assert main([str(p)]) == 1
    out = capsys.readouterr().out
    assert "1 tests: 0 passed, 1 failed [FAILED]" in out
    assert "diagnostic unavailable" in out


def test_diagnostic_does_not_flip_a_pass(capsys, tmp_path, monkeypatch):
    import clausal.testing as t

    def boom(*a, **k):
        raise ValueError("diagnostic exploded")

    monkeypatch.setattr(t, "_diagnose_into", boom)
    p = write(tmp_path, "ok.clausal", PASSING_SRC)
    assert main([str(p)]) == 0
    assert "[PASSED]" in capsys.readouterr().out


def test_runaway_probe_is_bounded(capsys, tmp_path, monkeypatch):
    """A nearest-solution probe can open up a search the real goal never enters.

    ``chk(bravo, okay)`` fails immediately (neither clause head unifies), but
    generalising argument 2 selects the second clause, whose body loops
    forever.  The watchdog must cut that short, keep the partial diagnostic,
    keep the verdict and keep the exit code.
    """
    monkeypatch.setenv("CLAUSAL_TEST_DIAG_BUDGET", "1")
    p = write(tmp_path, "loop.clausal", """
        -double_quotes(atom)
        -private([alfa, bravo, okay, deeper, other])

        chk(alfa, other),
        chk(X, deeper) <- (
            spin(X)
        ),

        spin(X) <- (
            spin(X)
        ),

        test("probe would loop") <- (
            chk(bravo, okay)
        ),
    """)
    started = time.monotonic()
    rc = main([str(p)])
    elapsed = time.monotonic() - started
    out = capsys.readouterr().out
    assert rc == 1
    assert "1 tests: 0 passed, 1 failed [FAILED]" in out
    assert "goal 1 of 1 failed" in out          # partial diagnostic survives
    assert "exceeded its 1s budget" in out
    assert elapsed < 30                          # bounded, not hung


# ── public API ───────────────────────────────────────────────────────────────


def test_run_file_attaches_diagnostic():
    from clausal.testing import run_file
    import tempfile, os

    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "bo.clausal")
        with open(p, "w") as fh:
            fh.write(textwrap.dedent(BO_SRC).lstrip())
        res = run_file(p)
    (r,) = res.results
    assert not r.passed
    assert r.line is not None
    assert r.diagnostic is not None
    assert r.diagnostic.index == 2
    assert r.diagnostic.total == 2


def test_run_test_does_not_diagnose_by_default():
    """conftest's pytest integration calls run_test/2 — it must stay cheap."""
    from clausal.testing import load_clausal_module, run_test
    import tempfile, os

    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "first.clausal")
        with open(p, "w") as fh:
            fh.write(textwrap.dedent(FIRST_GOAL_SRC).lstrip())
        mod = load_clausal_module(p)
        r = run_test(mod, "first conjunct fails")
    assert not r.passed
    assert r.diagnostic is None
