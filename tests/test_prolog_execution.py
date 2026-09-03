"""Stage-0 execution harness for the `==`/mode-lowering design.

Authority: ``implementation_plans/prolog-eq-mode-lowering.md`` (read it before
touching this file; this docstring restates its stage-0 ask, not the whole design).

Today NOTHING in the test suite executes translator output. Every prior Prolog test
(``tests/test_prolog_emit.py`` etc.) asserts *emitted text shape* -- it loads, runs and
queries nothing. The design's §4 recommendation, point 1, says plainly: "Nothing can
be recommended for adoption until a test exists that would have caught this... The
first commit under this design must therefore be the *harness*: a test that translates
a Clausal predicate, runs the emitted ``.pl`` in Scryer, and compares answers against
the same predicate run on the Clausal engine." This file is that harness. It makes no
translator changes -- it only pins what the translator does *today*, so a future
lowering change has something real to turn red or green.

Two documented defects are pinned here, both re-derived and re-run in this session
against the current ``clausal_to_prolog`` output (matches the design doc's transcripts
exactly, verified before writing any test):

  * §1-§3 -- ``==``/``!=`` lowered by operand *shape* (does the RHS look like a
    ``BinOp``?) rather than by operand *mode* (bound vs unbound) or *type* (number vs
    non-number). Clausal ``==`` is a CLP(FD) arithmetic-equality constraint: it can
    bind an unbound side, degrade to a ground structural test, or raise
    ``type_error(evaluable, ...)``. Neither ISO ``==`` nor ISO ``=:=`` reproduces that
    7-row behaviour (§1.2/§1.3's matrix).
  * §6 -- date-term ordering (``<``/``=<``/``>``/``>=``) emitted unconditionally, with
    no operand-type check. ISO's arithmetic evaluator has never heard of ``date/3``,
    so a ``date(...) =< date(...)`` comparison that succeeds on the real engine raises
    ``type_error(evaluable, date/3)`` in the emitted program (§6.2's witness).

CRITICAL HONESTY CONSTRAINT (project standard; this file's whole job is not to violate
it): every comparison below is either

  * an AGREEMENT, via ``assert_agreement`` -- a plain assertion that the Clausal
    engine and the Scryer-run emitted program reach the same outcome kind (succeeds /
    fails / raises); or
  * a KNOWN DIVERGENCE, via ``assert_known_divergence`` -- an assertion that they
    currently *disagree*, decorated with the spec section that documents the defect.
    This assertion is written to go RED, not stay green, the day the lowering it
    names is fixed to actually agree: it asserts the outcome kinds differ, so once a
    future fix makes them equal the assertion itself fails. It is the opposite of
    ``test_F032_arith_eq_roundtrip`` (``tests/audit_2026_07_05/test_11_modules_interop.py:595-599``),
    which the design's §5 calls out by name for asserting ``"=:=" in back or " is "
    in back`` -- deliberately disjunctive, so it "stays green under either lowering
    and pins nothing." Nothing in this file blesses a documented divergence as green.

A known-green control (``TestKnownCorrectLoweringControl``) is included alongside the
two defects: ``is`` (Clausal unify) correctly lowers to ISO ``=/2``
(``clausal_to_prolog.py:1179-1187``, cited in the design's §1.1), so that construct
should AGREE on every row. Without a control like it, a harness that always reports
"diverges" cannot be told apart from a harness that is wired wrong.
"""

from __future__ import annotations

import os
import re
import subprocess

import pytest

import clausal.import_hook  # noqa: F401  -- installs the .clausal finder/loader
from clausal import solve
from clausal.import_hook import _load_module
from clausal.logic.exceptions import LogicException
from clausal.logic.variables import Var, deref
from clausal.tools.clausal_to_prolog import clausal_source_to_prolog

SCRYER = "/workspace/scryer-prolog/target/release/scryer-prolog"
SPEC = "implementation_plans/prolog-eq-mode-lowering.md"

pytestmark = pytest.mark.skipif(
    not os.path.exists(SCRYER),
    reason=f"Scryer binary not found at {SCRYER} -- execution harness needs a real engine",
)


# ── Translation + subprocess plumbing ───────────────────────────────────────────


def _translate(source: str) -> str:
    """Translate Clausal source to Prolog text -- the harness's own front half."""
    return clausal_source_to_prolog(source)


def _load_clausal(tmp_path, name: str, source: str):
    """Load *source* as a live Clausal module (the harness's own ground truth)."""
    path = tmp_path / f"{name}.clausal"
    path.write_text(source)
    return _load_module(f"exec_harness_{name}", str(path))


def _run_clausal(goal_factory, *watch_vars):
    """Run one Clausal goal to its first solution.

    Returns ``("succeeds", (deref'd watch_vars...))``, ``("fails", ())``, or
    ``("raises", str(exc))``.

    *watch_vars* MUST be read from inside the ``solve()`` loop, before the generator
    is allowed to advance again: draining ``solve()`` to exhaustion first (e.g. via
    ``list(...)``) and deref'ing afterward undoes the trail on backtrack-out, turning
    a bound ``1257000`` back into a bare unbound ``AttVar`` (verified this session
    while re-deriving §1.2's matrix -- the spec's own driver reads bindings the same
    way). Returning from inside the loop reads them while they are still live.
    """
    try:
        for _ in solve(goal_factory()):
            return ("succeeds", tuple(deref(v) for v in watch_vars))
    except LogicException as exc:
        return ("raises", str(exc))
    return ("fails", ())


_USE_MODULE_DIRECTIVE = re.compile(r"^:-\s*use_module\([^\n]*\)\.\n\n?", re.MULTILINE)


def _run_scryer(tmp_path, pl_source: str, query: str, *, strip_companion_import: bool = False):
    """Consult *pl_source* in real Scryer and run one *query*.

    Returns ``("succeeds", None)``, ``("fails", None)``, or ``("raises", <error term
    text>)``, classified from Scryer's own top-level answer -- ``   true.`` /
    ``   false.`` / ``   error(...).`` -- exactly the transcript shape
    ``implementation_plans/prolog-eq-mode-lowering.md`` shows for every Scryer block.

    *strip_companion_import*: stage-0 has no companion library staged (the date-type
    fix, §6.4 D1, is a *future*, cross-repo change that would add exports to
    ``clausal_dates.pl`` -- out of scope for this harness, which pins today's
    behaviour). The one witness here that needs a module import (``date_time``, for
    the ``date/3`` constructor) would otherwise fail at ``existence_error`` before
    Scryer ever reaches the predicate under test, which pins nothing about the actual
    defect. ``date(Y, M, D)`` itself needs no import in ISO -- it is a plain compound
    term -- so dropping the directive changes nothing about what is being measured.
    """
    if strip_companion_import:
        pl_source = _USE_MODULE_DIRECTIVE.sub("", pl_source, count=1)
    pl_file = tmp_path / "harness.pl"
    pl_file.write_text(pl_source)
    proc = subprocess.run(
        [SCRYER, "harness.pl"],
        cwd=tmp_path,
        input=query + "\n",
        capture_output=True,
        text=True,
        timeout=8,
    )
    line = proc.stdout.strip()
    if line == "true.":
        return ("succeeds", None)
    if line == "false.":
        return ("fails", None)
    if line.startswith("error("):
        return ("raises", line)
    raise AssertionError(
        f"unparsed Scryer output for query {query!r}: "
        f"stdout={proc.stdout!r} stderr={proc.stderr!r} returncode={proc.returncode}"
    )


# ── Assertion helpers (the honesty-constraint mechanism) ────────────────────────


def assert_agreement(clausal_outcome, scryer_outcome, *, case: str) -> None:
    """Plain green: the Clausal engine and the Scryer-run emitted text AGREE."""
    c_kind, _ = clausal_outcome
    s_kind, _ = scryer_outcome
    assert c_kind == s_kind, (
        f"{case}: expected the Clausal engine and the Scryer-run emitted program to "
        f"AGREE, but they diverged -- Clausal={clausal_outcome!r} "
        f"Scryer={scryer_outcome!r}"
    )


def assert_known_divergence(clausal_outcome, scryer_outcome, *, case: str, spec_section: str) -> None:
    """Pin a documented divergence. Goes RED the day the lowering agrees again.

    Never a plain green assertion of the (wrong) emitted behaviour -- it asserts the
    outcome KINDS differ, which is only true while the defect is live.
    """
    c_kind, _ = clausal_outcome
    s_kind, _ = scryer_outcome
    assert c_kind != s_kind, (
        f"{case}: {SPEC} {spec_section} documents this as a KNOWN DIVERGENCE "
        f"(Clausal engine and Scryer-run emitted text were expected to disagree) but "
        f"they now AGREE -- Clausal={clausal_outcome!r} Scryer={scryer_outcome!r}. "
        f"If the lowering described in {spec_section} has genuinely been fixed to "
        f"match, replace this assert_known_divergence with assert_agreement -- do "
        f"not silence this failure."
    )


# ── §1.2 / §1.3 -- the `==` structural-shape matrix ──────────────────────────────
#
# Predicate `Eq(A, B) <- (A == B)`: neither operand is a BinOp, so
# `_convert_compare`'s `_is_arith_operand` guard is false on both sides and the
# translator emits structural `==`, not `=:=` -- confirmed by inspection of the
# emitted text below. This is verbatim the §1.2/§1.3 witness, re-run against the
# current translator and the real engines in this session.

_EQ_SOURCE = "Eq(A, B) <- (A == B)\n"
_EQ_PL = _translate(_EQ_SOURCE)
assert _EQ_PL.strip() == "eq(A, B) :-\n    A == B."  # pin the shape this matrix depends on


class TestEqStructuralShapeMatrix:
    """§1.2 (Clausal, Python-driver transcript) vs §1.3 (Scryer transcript)."""

    def test_ground_ground_numeric_different_type(self, tmp_path):
        # 2500 == 2500.0: Clausal's arithmetic equality succeeds; ISO structural
        # `==` is type-sensitive and says false.
        mod = _load_clausal(tmp_path, "eq1", _EQ_SOURCE)
        clausal = _run_clausal(lambda: mod.Eq(2500, 2500.0))
        scryer = _run_scryer(tmp_path, _EQ_PL, "eq(2500, 2500.0).")
        assert_known_divergence(clausal, scryer, case="eq(2500, 2500.0)", spec_section="§1.2/§1.3")

    def test_ground_ground_atom_equal(self, tmp_path):
        mod = _load_clausal(tmp_path, "eq2", _EQ_SOURCE)
        clausal = _run_clausal(lambda: mod.Eq("foo", "foo"))
        scryer = _run_scryer(tmp_path, _EQ_PL, "eq(foo, foo).")
        assert_agreement(clausal, scryer, case="eq(foo, foo)")

    def test_ground_ground_atom_unequal(self, tmp_path):
        mod = _load_clausal(tmp_path, "eq3", _EQ_SOURCE)
        clausal = _run_clausal(lambda: mod.Eq("foo", "bar"))
        scryer = _run_scryer(tmp_path, _EQ_PL, "eq(foo, bar).")
        assert_agreement(clausal, scryer, case="eq(foo, bar)")

    def test_unbound_left_ground_numeric_right(self, tmp_path):
        # eq(V, 1257000): Clausal BINDS V; ISO `==` cannot bind and says false.
        mod = _load_clausal(tmp_path, "eq4", _EQ_SOURCE)
        v = Var()
        clausal = _run_clausal(lambda: mod.Eq(v, 1257000), v)
        scryer = _run_scryer(tmp_path, _EQ_PL, "eq(_, 1257000).")
        assert clausal == ("succeeds", (1257000,))  # the bound value itself, per §1.2
        assert_known_divergence(clausal, scryer, case="eq(V, 1257000)", spec_section="§1.2/§1.3")

    def test_unbound_left_ground_atom_right(self, tmp_path):
        # eq(V, foo): Clausal RAISES type_error(evaluable, foo); ISO `==` says false.
        mod = _load_clausal(tmp_path, "eq5", _EQ_SOURCE)
        v = Var()
        clausal = _run_clausal(lambda: mod.Eq(v, "foo"), v)
        scryer = _run_scryer(tmp_path, _EQ_PL, "eq(_, foo).")
        assert clausal[0] == "raises"
        assert_known_divergence(clausal, scryer, case="eq(V, foo)", spec_section="§1.2/§1.3")

    def test_ground_numeric_left_unbound_right(self, tmp_path):
        # eq(1257000, V): symmetric to the V-first row; Clausal binds, ISO says false.
        mod = _load_clausal(tmp_path, "eq6", _EQ_SOURCE)
        v = Var()
        clausal = _run_clausal(lambda: mod.Eq(1257000, v), v)
        scryer = _run_scryer(tmp_path, _EQ_PL, "eq(1257000, _).")
        assert clausal == ("succeeds", (1257000,))
        assert_known_divergence(clausal, scryer, case="eq(1257000, V)", spec_section="§1.2/§1.3")

    def test_unbound_unbound(self, tmp_path):
        mod = _load_clausal(tmp_path, "eq7", _EQ_SOURCE)
        clausal = _run_clausal(lambda: mod.Eq(Var(), Var()))
        scryer = _run_scryer(tmp_path, _EQ_PL, "eq(_, _).")
        assert_known_divergence(clausal, scryer, case="eq(V, W)", spec_section="§1.2/§1.3")


# ── §1.4 / §1.5 -- the `uk/tax` witness, minimised ───────────────────────────────
#
# `Taxable` mirrors liability.clausal:169's shape (RHS is a BinOp -> emits `=:=`);
# `Allow` mirrors liability.clausal:133's shape (RHS is a bare Name -> emits `==`);
# `Chk` is §1.5's bound-operand witness, showing the defect is not only about mode.

_WITNESS_SOURCE = (
    "Taxable(TOTAL, ALLOW, AFTER) <- (AFTER == TOTAL - ALLOW)\n"
    "Allow(A, F) <- (A == F)\n"
    "Chk(X) <- (X == 2500)\n"
)
_WITNESS_PL = _translate(_WITNESS_SOURCE)


class TestTaxWitnessWorkedExample:
    """§1.4's minimised `eq_witness.pl` pair, plus §1.5's bound-operand chk/1."""

    def test_taxable_unbound_output_diverges(self, tmp_path):
        # Clausal COMPUTES After = 1000000; the emitted `=:=` needs both sides
        # ground and raises instantiation_error on the unbound output arg.
        mod = _load_clausal(tmp_path, "witness1", _WITNESS_SOURCE)
        after = Var()
        clausal = _run_clausal(lambda: mod.Taxable(1257000, 257000, after), after)
        scryer = _run_scryer(tmp_path, _WITNESS_PL, "taxable(1257000, 257000, After).")
        assert clausal == ("succeeds", (1000000,))
        assert_known_divergence(
            clausal, scryer, case="taxable(1257000, 257000, After) [unbound]", spec_section="§1.4"
        )

    def test_taxable_bound_output_agrees(self, tmp_path):
        # Hand the emitted `=:=` the answer Clausal would have computed, and it
        # happily checks it -- this is the row that hides the defect from any
        # gate that only ever calls with all outputs pre-filled.
        mod = _load_clausal(tmp_path, "witness2", _WITNESS_SOURCE)
        clausal = _run_clausal(lambda: mod.Taxable(1257000, 257000, 1000000))
        scryer = _run_scryer(tmp_path, _WITNESS_PL, "taxable(1257000, 257000, 1000000).")
        assert_agreement(clausal, scryer, case="taxable(1257000, 257000, 1000000) [bound]")

    def test_allow_diverges(self, tmp_path):
        # liability.clausal:133's own shape: Clausal BINDS A; ISO structural `==`
        # cannot bind and fails.
        mod = _load_clausal(tmp_path, "witness3", _WITNESS_SOURCE)
        a = Var()
        clausal = _run_clausal(lambda: mod.Allow(a, 1257000), a)
        scryer = _run_scryer(tmp_path, _WITNESS_PL, "allow(A, 1257000).")
        assert clausal == ("succeeds", (1257000,))
        assert_known_divergence(clausal, scryer, case="allow(A, 1257000)", spec_section="§1.4")

    def test_chk_bound_float_diverges(self, tmp_path):
        # §1.5: even with BOTH operands bound, int-vs-float flips the verdict --
        # Clausal succeeds (arithmetic equality); ISO `==` is type-sensitive.
        mod = _load_clausal(tmp_path, "witness4", _WITNESS_SOURCE)
        clausal = _run_clausal(lambda: mod.Chk(2500.0))
        scryer = _run_scryer(tmp_path, _WITNESS_PL, "chk(2500.0).")
        assert_known_divergence(clausal, scryer, case="chk(2500.0)", spec_section="§1.5")

    def test_chk_bound_int_agrees(self, tmp_path):
        mod = _load_clausal(tmp_path, "witness5", _WITNESS_SOURCE)
        clausal = _run_clausal(lambda: mod.Chk(2500))
        scryer = _run_scryer(tmp_path, _WITNESS_PL, "chk(2500).")
        assert_agreement(clausal, scryer, case="chk(2500)")


# ── §6.2 -- date-ordering witness (au/aml_ctf, re-derived) ───────────────────────

_DATE_SOURCE = (
    "-import_from(date_time, [\n"
    "    date])\n"
    "\n"
    'status_commencement("virtual_asset", date(2018, 4, 3)),\n'
    "service_in_force(CATEGORY, QUERY_DATE) <- (\n"
    "    status_commencement(CATEGORY, COMMENCEMENT_DATE),\n"
    "    COMMENCEMENT_DATE <= QUERY_DATE\n"
    ")\n"
)
_DATE_PL = _translate(_DATE_SOURCE)


class TestDateOrderingWitness:
    """§6.2's `au/aml_ctf/reporting_entity_obligations.clausal:257-259` witness."""

    def test_service_in_force_diverges(self, tmp_path):
        # Real dates, correctly orderable per clausal/modules/py/datetime.py's own
        # contract: Clausal succeeds. The emitted `=<` asks ISO's arithmetic
        # evaluator to evaluate a `date/3` compound and it raises.
        import datetime

        mod = _load_clausal(tmp_path, "date1", _DATE_SOURCE)
        clausal = _run_clausal(
            lambda: mod.service_in_force("virtual_asset", datetime.date(2026, 9, 2))
        )
        scryer = _run_scryer(
            tmp_path,
            _DATE_PL,
            'service_in_force("virtual_asset", date(2026,9,2)).',
            strip_companion_import=True,
        )
        assert clausal == ("succeeds", ())
        assert scryer[0] == "raises"
        assert_known_divergence(
            clausal, scryer, case="service_in_force(virtual_asset, 2026-09-02)", spec_section="§6.2"
        )


# ── Known-green control ──────────────────────────────────────────────────────────
#
# `is` (Clausal unify) is NOT one of this design's defects -- §1.1 confirms the
# translator correctly lowers it to ISO `=/2`. Included so a harness that always
# reports "diverges" cannot masquerade as one that correctly distinguishes agreement
# from divergence (see docs memory: "Always include a known-green control").

_SAME_SOURCE = "Same(X, Y) <- (X is Y)\n"
_SAME_PL = _translate(_SAME_SOURCE)


class TestKnownCorrectLoweringControl:
    def test_same_agrees_when_equal(self, tmp_path):
        mod = _load_clausal(tmp_path, "same1", _SAME_SOURCE)
        clausal = _run_clausal(lambda: mod.Same(5, 5))
        scryer = _run_scryer(tmp_path, _SAME_PL, "same(5, 5).")
        assert_agreement(clausal, scryer, case="same(5, 5)")

    def test_same_agrees_when_unequal(self, tmp_path):
        mod = _load_clausal(tmp_path, "same2", _SAME_SOURCE)
        clausal = _run_clausal(lambda: mod.Same(5, 6))
        scryer = _run_scryer(tmp_path, _SAME_PL, "same(5, 6).")
        assert_agreement(clausal, scryer, case="same(5, 6)")
