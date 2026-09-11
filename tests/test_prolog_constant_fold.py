"""A declared constant exports as its LITERAL VALUE.

Why folding rather than emitting a name: ISO's evaluable-functor set is fixed and
``++/1`` is not in it, so no conformant system will evaluate ``F > ++max_fine``.
Measured on 2026-09-10 against both reference systems:

    6000 > ++max_fine    Trealla: type_error(evaluable, (++)/1)
                         Scryer:  type_error(evaluable, max_fine/0)

The value is known at export time -- the declaration is in the same file -- so the
exporter substitutes it. A folded file runs anywhere, with no ``op/3`` declaration,
no expansion prelude and no cooperation from the target. That matters because the
prelude route is UNSOLVED in both systems (self-applying ``term_expansion/2`` hangs
Trealla; an included prelude hangs Trealla and Scryer rejects it positionally).

The acceptance test here is deliberately not "it parses": ``test_folded_program_runs``
consults the emitted text in real Scryer and checks the answer. Before this change the
whole file was refused with ``NotImplementedError``, so the 88 corpus parameters that
want to become constants could not have been exported at all.
"""
import os
import re
import subprocess

import pytest

from clausal.tools.clausal_to_prolog import clausal_source_to_prolog

SCRYER = "/workspace/scryer-prolog/target/release/scryer-prolog"

needs_scryer = pytest.mark.skipif(
    not os.path.exists(SCRYER),
    reason=f"Scryer binary not found at {SCRYER}",
)


def _run_scryer(tmp_path, pl_source: str, query: str):
    """Consult *pl_source* in real Scryer and run one *query*."""
    pl_file = tmp_path / "fold.pl"
    pl_file.write_text(pl_source)
    proc = subprocess.run(
        [SCRYER, "fold.pl"], cwd=tmp_path, input=query + "\n",
        capture_output=True, text=True, timeout=15,
    )
    line = proc.stdout.strip()
    if line == "true.":
        return ("succeeds", None)
    if line == "false.":
        return ("fails", None)
    if line.startswith("error("):
        return ("raises", line)
    raise AssertionError(
        f"unparsed Scryer output for {query!r}: stdout={proc.stdout!r} "
        f"stderr={proc.stderr!r} rc={proc.returncode}")


# ── The fold itself ──────────────────────────────────────────────────────────


def test_a_declared_constant_folds_to_its_literal():
    out = clausal_source_to_prolog(
        "-constant_value(max_fine, 5000)\n"
        "\n"
        "applies(X) <- (fine(X, F), F > ++max_fine)\n")
    assert "5000" in out, out
    assert "???" not in out, out
    assert "max_fine" not in out, (
        "the NAME must not survive -- ISO cannot evaluate it", out)


def test_the_declaration_itself_emits_nothing():
    """A constant has no Prolog representation of its own; it exists only at
    the use sites, already substituted."""
    out = clausal_source_to_prolog("-constant_value(max_fine, 5000)\n\np(1),\n")
    assert "constant_value" not in out, out


def test_a_constant_defined_from_earlier_constants_folds_through():
    """``-constant_value(limit, base * 4 + 2)`` must export 42, not an
    expression mentioning ``base`` -- the same reason the name cannot survive."""
    out = clausal_source_to_prolog(
        "-constant_value(base, 10)\n"
        "-constant_value(limit, base * 4 + 2)\n"
        "\n"
        "over(X) <- (X > ++limit)\n")
    assert "42" in out, out
    assert "base" not in out, out


def test_a_structured_constant_folds():
    out = clausal_source_to_prolog(
        "-constant_value(codes, ['au', 'al'])\n"
        "\n"
        "known(C) <- member(C, ++codes)\n")
    assert "au" in out and "al" in out, out
    assert "???" not in out, out


# ── The negative control ─────────────────────────────────────────────────────


def test_a_non_constant_escape_still_refuses():
    """The fold must not swallow the real case. ``++`` over anything that is
    not a declared constant has no value known at export time, so it stays
    untranslatable rather than silently emitting something plausible."""
    out = clausal_source_to_prolog(
        "workers(N) <- (N is ++__import__('os').cpu_count())\n")
    assert "???" in out, out
    assert "untranslatable" in out, out


def test_an_undeclared_name_in_an_escape_is_not_folded():
    """A name that merely LOOKS like a constant is not one."""
    out = clausal_source_to_prolog("over(X) <- (X > ++not_declared_here)\n")
    assert "???" in out, out


# ── Units: lossy, and visibly so ─────────────────────────────────────────────


def test_a_united_constant_exports_its_magnitude_and_says_so():
    """Prolog has no unit system, so the unit cannot cross. The exporter
    already discards units from an inline ``5000(euro)`` literal and records
    it as LOSSY; a united constant follows that precedent rather than
    inventing a policy -- but it must not drop the unit SILENTLY."""
    out = clausal_source_to_prolog(
        "-import_from(european_union, [euro])\n"
        "-constant_number_units(max_fine, 5000, euro)\n"
        "\n"
        "applies(X) <- (fine(X, F), F > ++max_fine)\n")
    assert "5000" in out, out
    assert "???" not in out, out
    assert re.search(r"unit discarded", out), (
        "the dropped unit must be reported, not silent", out)


# ── Acceptance: the emitted program RUNS ─────────────────────────────────────


@needs_scryer
def test_folded_program_runs(tmp_path):
    """The definition of done: not "it parses", but "it answers".

    Before the fold this file was refused outright; with a name emitted
    instead of a value it would consult and then raise
    ``type_error(evaluable, max_fine/0)`` on the comparison.
    """
    pl = clausal_source_to_prolog(
        "-constant_value(max_fine, 5000)\n"
        "\n"
        "applies(X) <- (fine(X, F), F > ++max_fine)\n"
        "fine(acme, 6000),\n"
        "fine(tiny, 10),\n")
    assert _run_scryer(tmp_path, pl, "applies(acme).") == ("succeeds", None)
    assert _run_scryer(tmp_path, pl, "applies(tiny).") == ("fails", None)


@needs_scryer
def test_the_unfolded_form_is_why_this_exists(tmp_path):
    """Positive control on the REASON, not just the result: the same program
    with the name left in place raises in Scryer. If this ever starts
    succeeding, ISO has gained an evaluable ``++``/a constant table and the
    fold could be reconsidered."""
    unfolded = (":- op(200, fy, ++).\n"
                "applies(X) :- fine(X, F), F > ++max_fine.\n"
                "fine(acme, 6000).\n")
    kind, detail = _run_scryer(tmp_path, unfolded, "applies(acme).")
    assert kind == "raises", (kind, detail)
    assert "type_error" in detail and "evaluable" in detail, detail


# ── constant/1, the retrieval form the escape was replaced by ────────────────


def test_constant_1_folds_to_its_literal():
    """`constant(name)` is the blessed retrieval form since 2026-09-11, so the
    exporter must fold it exactly as it folds the escape it replaced."""
    out = clausal_source_to_prolog(
        "-constant_value(max_fine, 5000)\n"
        "\n"
        "applies(X) <- (fine(X, F), F > constant(max_fine))\n")
    assert "5000" in out, out
    assert "???" not in out, out
    assert "constant" not in out, ("the wrapper must not survive either", out)


@needs_scryer
def test_a_constant_1_program_runs(tmp_path):
    pl = clausal_source_to_prolog(
        "-constant_value(max_fine, 5000)\n"
        "\n"
        "applies(X) <- (fine(X, F), F > constant(max_fine))\n"
        "fine(acme, 6000),\n"
        "fine(tiny, 10),\n")
    assert _run_scryer(tmp_path, pl, "applies(acme).") == ("succeeds", None)
    assert _run_scryer(tmp_path, pl, "applies(tiny).") == ("fails", None)
