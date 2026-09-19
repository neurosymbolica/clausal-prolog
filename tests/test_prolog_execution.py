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
from clausal.logic.atoms import mint
from clausal.logic.cells import chars
from clausal.logic.exceptions import LogicException
from clausal.logic.variables import Var, deref
from clausal.tools.clausal_to_prolog import clausal_source_to_prolog
from clausal.modules.py.datetime import _dt_to_term as _T
from clausal.modules.py.datetime import _term_to_dt as _P  # py datetime -> its TERM

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

#: A Scryer toplevel answer that is a residual CONSTRAINT rather than
#: `true.`/`false.`/`error(...)`. Matched on the `<module>:` qualifier Scryer
#: prints for an attributed-variable residual (`clpz:(_A in inf..sup).`).
_RESIDUAL_GOAL = re.compile(r"^[a-z][A-Za-z0-9_]*:")

#: A Scryer toplevel answer that is a variable BINDING (`After = 1000000.`)
#: rather than a bare `true.`.
_BINDING_ANSWER = re.compile(r"^[A-Z_][A-Za-z0-9_]* = .*\.$", re.DOTALL)


def _classify_scryer(proc, query: str):
    """Scryer's toplevel answer -> ("succeeds"|"fails"|"raises", detail).

    ONE classifier, called by both runners below. They each carried their own
    copy, so teaching one of them about residual constraints would have left
    the other raising AssertionError on the same answer -- the same defect
    over a second call site.
    """
    line = proc.stdout.strip()
    if line == "true.":
        return ("succeeds", None)
    if line == "false.":
        return ("fails", None)
    if line.startswith("error("):
        return ("raises", line)
    # A CLP query that succeeds with an UNRESOLVED constraint prints the
    # residual goal instead of `true.` -- `clpz:(_A in inf..sup).` for
    # `#=(A, B)` on two fresh variables. That is a SUCCESS carrying a
    # residual, not an unparsed answer. Before the 2026-09-18 ruling nothing
    # this harness emitted could post a constraint, so neither classifier had
    # ever met one.
    if line.endswith(".") and _RESIDUAL_GOAL.search(line):
        return ("succeeds", line)
    # A query whose variables get BOUND prints the bindings, not `true.` --
    # `After = 1000000.`. Also new after the ruling: `=:=` could only TEST, so
    # a query with an unbound output raised instantiation_error and this
    # branch was unreachable. `#=` computes, so the answer is a binding.
    if line.endswith(".") and _BINDING_ANSWER.match(line):
        return ("succeeds", line)
    raise AssertionError(
        f"unparsed Scryer output for query {query!r}: "
        f"stdout={proc.stdout!r} stderr={proc.stderr!r} returncode={proc.returncode}"
    )



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
    return _classify_scryer(proc, query)


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

_EQ_SOURCE = "eq(A, B) <- (A == B)\n"
_EQ_PL = _translate(_EQ_SOURCE)
# PIN the shape this matrix depends on. Ruling 2026-09-18: an unquoted `==` is
# the CLP arithmetic constraint and emits `#=`, WITH its own import -- so this
# matrix needs no clpz-awareness of its own, the emitted text is self-sufficient.
#: The RESPELLED form. `'=='(A, B)` reaches the quoted-functor path and stays
#: ISO `==`, which is what the arithmetic rows above are contrasted against.
_IDENT_SOURCE = "ident(A, B) <- ('=='(A, B))\n"
_IDENT_PL = _translate(_IDENT_SOURCE)
assert _IDENT_PL.strip() == "ident(A, B) :-\n    A == B.", _IDENT_PL

assert _EQ_PL.strip() == (
    ":- use_module(library(clpz), [(#=)/2]).\n\neq(A, B) :-\n    #=(A, B)."), _EQ_PL


class TestEqArithmeticLoweringAgrees:
    """The rows the 2026-09-18 ruling FIXED. Each was a known divergence.

    `#=` binds and propagates, so the three mode rows that `==`/`=:=` could not
    serve -- unbound on either side, and two fresh variables -- now agree with
    the Clausal engine. These assertions replace `assert_known_divergence`
    calls, which is what this file's docstring says to do when the lowering is
    genuinely fixed rather than silenced.
    """

    def test_unbound_left_ground_numeric_right(self, tmp_path):
        # Was §1.2/§1.3's divergence: Clausal BINDS, ISO `==` could not and
        # said false. `#=` binds, so Scryer now answers `_A = 1257000`.
        mod = _load_clausal(tmp_path, "eq4", _EQ_SOURCE)
        v = Var()
        clausal = _run_clausal(lambda: mod.eq(v, 1257000), v)
        scryer = _run_scryer(tmp_path, _EQ_PL, "eq(_, 1257000).")
        assert clausal == ("succeeds", (1257000,))  # the bound value itself, per §1.2
        assert_agreement(clausal, scryer, case="eq(V, 1257000)")

    def test_ground_numeric_left_unbound_right(self, tmp_path):
        # Symmetric to the row above; was equally divergent.
        mod = _load_clausal(tmp_path, "eq6", _EQ_SOURCE)
        v = Var()
        clausal = _run_clausal(lambda: mod.eq(1257000, v), v)
        scryer = _run_scryer(tmp_path, _EQ_PL, "eq(1257000, _).")
        assert clausal == ("succeeds", (1257000,))
        assert_agreement(clausal, scryer, case="eq(1257000, V)")

    def test_unbound_unbound_posts_a_constraint(self, tmp_path):
        # Both engines now POST rather than decide. Scryer reports the residual
        # `clpz:(_A in inf..sup).` -- a success carrying a constraint, which is
        # an answer shape this harness could not produce before the ruling.
        mod = _load_clausal(tmp_path, "eq7", _EQ_SOURCE)
        clausal = _run_clausal(lambda: mod.eq(Var(), Var()))
        scryer = _run_scryer(tmp_path, _EQ_PL, "eq(_, _).")
        assert_agreement(clausal, scryer, case="eq(V, W)")
        assert scryer[1] is not None and "clpz" in scryer[1], scryer

    def test_unbound_left_ground_atom_right(self, tmp_path):
        # Both RAISE: Clausal's type_error(evaluable, foo) against clpz's
        # domain_error(clpz_expression, foo). Agreement is on the outcome KIND.
        mod = _load_clausal(tmp_path, "eq5", _EQ_SOURCE)
        v = Var()
        clausal = _run_clausal(lambda: mod.eq(v, "foo"), v)
        scryer = _run_scryer(tmp_path, _EQ_PL, "eq(_, foo).")
        assert clausal[0] == "raises"
        assert_agreement(clausal, scryer, case="eq(V, foo)")


class TestEqNonIntegerOperandStillDiverges:
    """`#=` is CLP over the INTEGERS, so a non-integer operand diverges.

    Measured 2026-09-19 and ruled the same day: the CLP(Z) solvers raise
    `domain_error(clpz_expression, X)` for any operand that is not an integer,
    where the Clausal engine's `==` falls back to a ground structural test and
    decides. Every row here is the SAME defect -- a non-integer handed to an
    arithmetic site -- and the remedy is not a change to the lowering but a
    respell of the SOURCE, which :class:`TestIdentStructuralLoweringAgrees`
    below shows agreeing on exactly these operands.

    These are pinned as divergences rather than deleted because the limit is
    real, undocumented before this, and invisible to every suite that runs the
    Clausal engine alone.
    """

    def test_float_operand(self, tmp_path):
        # 2500 == 2500.0: Clausal succeeds. `=:=` succeeded here BEFORE the
        # ruling, so this row is a regression the ruling knowingly accepted.
        mod = _load_clausal(tmp_path, "eqf", _EQ_SOURCE)
        clausal = _run_clausal(lambda: mod.eq(2500, 2500.0))
        scryer = _run_scryer(tmp_path, _EQ_PL, "eq(2500, 2500.0).")
        assert "domain_error(clpz_expression" in scryer[1], scryer
        assert_known_divergence(clausal, scryer, case="eq(2500, 2500.0)",
                                spec_section="§1.2/§1.3 + the 2026-09-19 integer limit")

    def test_ground_atoms_equal(self, tmp_path):
        mod = _load_clausal(tmp_path, "eq2", _EQ_SOURCE)
        clausal = _run_clausal(lambda: mod.eq(chars("foo"), chars("foo")))
        scryer = _run_scryer(tmp_path, _EQ_PL, "eq(foo, foo).")
        assert_known_divergence(clausal, scryer, case="eq(foo, foo)",
                                spec_section="the 2026-09-19 integer limit")

    def test_ground_atoms_unequal(self, tmp_path):
        mod = _load_clausal(tmp_path, "eq3", _EQ_SOURCE)
        clausal = _run_clausal(lambda: mod.eq(chars("foo"), chars("bar")))
        scryer = _run_scryer(tmp_path, _EQ_PL, "eq(foo, bar).")
        assert_known_divergence(clausal, scryer, case="eq(foo, bar)",
                                spec_section="the 2026-09-19 integer limit")


class TestIdentStructuralLoweringAgrees:
    """The OTHER witness: `'=='(A, B)` is ISO term identity and agrees on 5/5.

    This class is what makes the divergences above a statement about the
    SPELLING rather than about the translator. The same operands that diverge
    through the arithmetic spelling agree through this one, including the float
    and the two-fresh-variable rows.
    """

    def test_ground_atoms_equal(self, tmp_path):
        mod = _load_clausal(tmp_path, "id1", _IDENT_SOURCE)
        clausal = _run_clausal(lambda: mod.ident(chars("foo"), chars("foo")))
        scryer = _run_scryer(tmp_path, _IDENT_PL, "ident(foo, foo).")
        assert_agreement(clausal, scryer, case="ident(foo, foo)")

    def test_ground_atoms_unequal(self, tmp_path):
        mod = _load_clausal(tmp_path, "id2", _IDENT_SOURCE)
        clausal = _run_clausal(lambda: mod.ident(chars("foo"), chars("bar")))
        scryer = _run_scryer(tmp_path, _IDENT_PL, "ident(foo, bar).")
        assert_agreement(clausal, scryer, case="ident(foo, bar)")

    def test_float_operand(self, tmp_path):
        # The row the arithmetic spelling cannot serve: both say false, because
        # 2500 and 2500.0 are different TERMS.
        mod = _load_clausal(tmp_path, "id3", _IDENT_SOURCE)
        clausal = _run_clausal(lambda: mod.ident(2500, 2500.0))
        scryer = _run_scryer(tmp_path, _IDENT_PL, "ident(2500, 2500.0).")
        assert_agreement(clausal, scryer, case="ident(2500, 2500.0)")
        assert clausal[0] == "fails", clausal

    def test_unbound_left_ground_numeric_right(self, tmp_path):
        mod = _load_clausal(tmp_path, "id4", _IDENT_SOURCE)
        v = Var()
        clausal = _run_clausal(lambda: mod.ident(v, 1257000), v)
        scryer = _run_scryer(tmp_path, _IDENT_PL, "ident(_, 1257000).")
        assert_agreement(clausal, scryer, case="ident(V, 1257000)")

    def test_unbound_unbound(self, tmp_path):
        # Two DISTINCT fresh variables are not identical, in either engine --
        # and this is the row the arithmetic spelling answers by POSTING.
        mod = _load_clausal(tmp_path, "id5", _IDENT_SOURCE)
        clausal = _run_clausal(lambda: mod.ident(Var(), Var()))
        scryer = _run_scryer(tmp_path, _IDENT_PL, "ident(_, _).")
        assert_agreement(clausal, scryer, case="ident(V, W)")
        assert clausal[0] == "fails", clausal


# ── §1.4 / §1.5 -- the `uk/tax` witness, minimised ───────────────────────────────
#
# `Taxable` mirrors liability.clausal:169's shape (RHS is a BinOp -> emits `=:=`);
# `Allow` mirrors liability.clausal:133's shape (RHS is a bare Name -> emits `==`);
# `Chk` is §1.5's bound-operand witness, showing the defect is not only about mode.

_WITNESS_SOURCE = (
    "taxable(TOTAL, ALLOW, AFTER) <- (AFTER == TOTAL - ALLOW)\n"
    "allow(A, F) <- (A == F)\n"
    "chk(X) <- (X == 2500)\n"
)
_WITNESS_PL = _translate(_WITNESS_SOURCE)


class TestTaxWitnessWorkedExample:
    """§1.4's minimised `eq_witness.pl` pair, plus §1.5's bound-operand chk/1."""

    def test_taxable_unbound_output_agrees(self, tmp_path):
        """THE HEADLINE ROW OF THE 2026-09-18 RULING, and it now agrees.

        Clausal COMPUTES After = 1000000. The emitted `=:=` needed both sides
        ground and raised instantiation_error on the unbound output, which is
        what §1.4 pinned. `#=` computes, so Scryer answers `After = 1000000`
        -- the same number, from the exported program.
        """
        mod = _load_clausal(tmp_path, "witness1", _WITNESS_SOURCE)
        after = Var()
        clausal = _run_clausal(lambda: mod.taxable(1257000, 257000, after), after)
        scryer = _run_scryer(tmp_path, _WITNESS_PL, "taxable(1257000, 257000, After).")
        assert clausal == ("succeeds", (1000000,))
        assert_agreement(clausal, scryer,
                         case="taxable(1257000, 257000, After) [unbound]")
        # Not just the same outcome KIND: the same VALUE. Without this the row
        # would stay green if Scryer succeeded with any binding at all.
        assert scryer[1] is not None and "1000000" in scryer[1], scryer

    def test_taxable_bound_output_agrees(self, tmp_path):
        # Hand the emitted `=:=` the answer Clausal would have computed, and it
        # happily checks it -- this is the row that hides the defect from any
        # gate that only ever calls with all outputs pre-filled.
        mod = _load_clausal(tmp_path, "witness2", _WITNESS_SOURCE)
        clausal = _run_clausal(lambda: mod.taxable(1257000, 257000, 1000000))
        scryer = _run_scryer(tmp_path, _WITNESS_PL, "taxable(1257000, 257000, 1000000).")
        assert_agreement(clausal, scryer, case="taxable(1257000, 257000, 1000000) [bound]")

    def test_allow_agrees(self, tmp_path):
        """liability.clausal:133's own shape, also fixed.

        Clausal BINDS A. ISO structural `==` could not bind and failed, which
        is what §1.4 pinned; `#=` binds, so both reach 1257000.
        """
        mod = _load_clausal(tmp_path, "witness3", _WITNESS_SOURCE)
        a = Var()
        clausal = _run_clausal(lambda: mod.allow(a, 1257000), a)
        scryer = _run_scryer(tmp_path, _WITNESS_PL, "allow(A, 1257000).")
        assert clausal == ("succeeds", (1257000,))
        assert_agreement(clausal, scryer, case="allow(A, 1257000)")
        assert scryer[1] is not None and "1257000" in scryer[1], scryer

    def test_chk_bound_float_diverges(self, tmp_path):
        """§1.5's row still diverges, but for a DIFFERENT reason than it did.

        It was type-sensitivity in ISO `==`: Clausal's arithmetic equality
        succeeded, `==` said false. It is now the 2026-09-19 integer limit:
        `#=` raises `domain_error(clpz_expression, 2500.0)`. The outcome kinds
        still differ, so the assertion is unchanged -- but the REASON moved,
        and a row whose reason moved silently is the kind this file exists to
        prevent, so the new reason is asserted explicitly.
        """
        mod = _load_clausal(tmp_path, "witness4", _WITNESS_SOURCE)
        clausal = _run_clausal(lambda: mod.chk(2500.0))
        scryer = _run_scryer(tmp_path, _WITNESS_PL, "chk(2500.0).")
        assert scryer[0] == "raises", scryer
        assert "domain_error(clpz_expression" in scryer[1], scryer
        assert_known_divergence(clausal, scryer, case="chk(2500.0)",
                                spec_section="§1.5 + the 2026-09-19 integer limit")

    def test_chk_bound_int_agrees(self, tmp_path):
        mod = _load_clausal(tmp_path, "witness5", _WITNESS_SOURCE)
        clausal = _run_clausal(lambda: mod.chk(2500))
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
        # THE FLIP (spec §11): text crossing in from Python is a STRING; the
        # clause head carries the ATOM the atom-mode literal denotes, so the
        # Python caller must pass the atom (`mint`), not a str.
        clausal = _run_clausal(
            lambda: mod.service_in_force(mint("virtual_asset"),
                                         _T(_P(datetime).date(2026, 9, 2)))
        )
        scryer = _run_scryer(
            tmp_path,
            _DATE_PL,
            # The category literal migrated with the emission: a Clausal str
            # literal denotes an ATOM, so the head this query must match is
            # `status_commencement(virtual_asset, ...)`, not a char list. With
            # the old spelling the query fails at the HEAD and never reaches
            # the `=<` whose divergence this test exists to pin.
            'service_in_force(virtual_asset, date(2026,9,2)).',
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

_SAME_SOURCE = "same(X, Y) <- (X is Y)\n"
_SAME_PL = _translate(_SAME_SOURCE)


class TestKnownCorrectLoweringControl:
    def test_same_agrees_when_equal(self, tmp_path):
        mod = _load_clausal(tmp_path, "same1", _SAME_SOURCE)
        clausal = _run_clausal(lambda: mod.same(5, 5))
        scryer = _run_scryer(tmp_path, _SAME_PL, "same(5, 5).")
        assert_agreement(clausal, scryer, case="same(5, 5)")

    def test_same_agrees_when_unequal(self, tmp_path):
        mod = _load_clausal(tmp_path, "same2", _SAME_SOURCE)
        clausal = _run_clausal(lambda: mod.same(5, 6))
        scryer = _run_scryer(tmp_path, _SAME_PL, "same(5, 6).")
        assert_agreement(clausal, scryer, case="same(5, 6)")


# ── THE MONEY PIN: a str literal must unify with a same-spelling atom ──────────
#
# AUTHORITY (user-ratified, R2 family; see the block comment in
# tests/test_prolog_emit.py for the full citation): under the current Python
# surface a Clausal ``str`` literal DENOTES AN ATOM. Verified against the live
# engine before this pin was written -- an atom imported from another module
# derefs to a plain ``str``, and ``atom == "spelling"`` is True.
#
# This is the ai_act ``what_if`` shape: a profile KEY is written as a bare atom
# in the module that declares the key surface, and reached as a str literal by
# the module that asks the hypothetical. On the Clausal engine that unifies --
# they are the same value. Before the literal migration the translator lowered
# the str to a Prolog double-quoted char list, so the emitted program FAILED
# where the engine SUCCEEDED: a silent wrong answer, not a loud error.
#
# RED before the migration (re-derived this session against real Scryer and the
# real engine):  Clausal = ('succeeds', ('exception_f',))  /  Scryer = 'fails'.

_KEYS_CLAUSAL = """-module(keys, [profile_key(K), exception_f, harm])
profile_key(exception_f),
profile_key(harm),
"""

_ASKER_CLAUSAL = """-import_from(keys, [profile_key])
hit(K) <- (K is "exception_f", profile_key(K))
"""


def _run_scryer_multifile(tmp_path, files: dict, query: str):
    """Consult a MULTI-MODULE emitted program in real Scryer.

    ``files`` maps file name -> Prolog text; ``harness.pl`` is the entry point
    Scryer is pointed at, and the others sit beside it so its ``use_module``
    directives resolve by relative path -- exactly how the exporter stages a
    domain on disk. same output classification as :func:`_run_scryer`.
    """
    for name, text in files.items():
        (tmp_path / name).write_text(text)
    proc = subprocess.run(
        [SCRYER, "harness.pl"],
        cwd=tmp_path, input=query + "\n",
        capture_output=True, text=True, timeout=15,
    )
    return _classify_scryer(proc, query)


class TestStrLiteralUnifiesWithImportedAtom:
    """The cross-module literal/atom identity pin."""

    def test_str_literal_reaches_an_imported_atom(self, tmp_path):
        from clausal.tools.clausal_to_prolog import (
            clausal_source_to_prolog_ast, module_export_signature,
        )

        # --- Clausal engine: the ground truth -------------------------------
        (tmp_path / "keys.clausal").write_text(_KEYS_CLAUSAL)
        import sys
        sys.path.insert(0, str(tmp_path))
        try:
            asker = _load_clausal(tmp_path, "asker", _ASKER_CLAUSAL)
            var = Var()
            clausal = _run_clausal(lambda: asker.hit(var), var)
        finally:
            sys.path.remove(str(tmp_path))

        # The engine must actually REACH the fact -- a pin whose ground truth
        # is "fails" would go green on a translator that emits nothing.
        # The binding comes back as the engine's atom cell (THE FLIP, §11:
        # an atom is the 1-tuple `("exception_f",)`), i.e. `mint(...)`.
        assert clausal == ("succeeds", (mint("exception_f"),)), clausal

        # --- The emitted program, in real Scryer ----------------------------
        # Signatures are supplied because that is how the real exporter runs:
        # without them an import list carries no arity and Scryer rejects the
        # module declaration before reaching the predicate under test.
        sigs = {"keys": module_export_signature(
            clausal_source_to_prolog_ast(_KEYS_CLAUSAL))}
        scryer = _run_scryer_multifile(tmp_path, {
            "keys.pl": _translate(_KEYS_CLAUSAL),
            "harness.pl": clausal_source_to_prolog(
                _ASKER_CLAUSAL, module_path="asker", module_signatures=sigs),
        }, "hit(_).")

        assert_agreement(clausal, scryer, case='hit(K), K is "exception_f"')


# ── Class G: a str literal containing newlines must still consult ─────────────
#
# 16 corpus domains failed G2 on error(syntax_error(missing_quote)) -- e.g.
# us/tax/irc_s1_income_tax_brackets/parameters.pl, whose `verbatim` parameter is
# a multi-KB statutory table carrying real newlines. The root cause is the
# EMITTER: `emit_term`'s PString branch escaped only backslash and `"`, so an
# embedded newline was written raw and the double-quoted string ran off the end
# of its line. The literal migration routes those values through `_quote_atom`,
# which escapes newlines (and every other control char) per ISO 6.4.2.

_VERBATIM_PROSE = (
    "TABLE 1 - Section 1(j)(2)(A) –Married Individuals Filing Joint Returns\n"
    "If Taxable Income Is: The Tax Is:\n"
    "Not over $23,850 10% of the taxable income\n"
    "Over $23,850 but $2,385 plus 12% of\n"
    "not over $96,950 the excess over $23,850\n"
) * 40  # ~9 KB, the multi-KB scale the citations/verbatim parameters really hit


class TestNewlineBearingLiteralConsults:

    def test_multiline_verbatim_literal_consults_in_scryer(self, tmp_path):
        source = "verbatim(%r),\n" % _VERBATIM_PROSE
        pl = _translate(source)
        assert len(_VERBATIM_PROSE) > 8000, "witness must be multi-KB"
        # The emitted clause is ONE line: no raw newline escaped from the atom.
        assert "\n" not in pl.strip().rstrip("."), pl[:200]
        outcome = _run_scryer_multifile(
            tmp_path, {"harness.pl": pl}, "verbatim(_).")
        assert outcome == ("succeeds", None), outcome


# ── `"[]"`: the collapse onto ISO's one `[]` is FAITHFUL under the flip ────────
#
# ISO has exactly one `[]` and it is an atom (6.3.5; Scryer: `atom([])` and
# `[] == '[]'` are both true). f47e1a8e pinned a DIVERGENCE here: the
# pre-flip engine distinguished the atom `"[]"` from the empty list, so
# `K is "[]", empty_list(K)` failed on the engine while the emitted
# `K = [], empty_list(K)` succeeded -- a false positive in the export.
#
# THE FLIP (2026-09-06-atoms-as-cells-strings §11) made the engine agree
# with ISO: the atom `[]` IS the empty list (`atom([])` true, written `[]`).
# Under atom mode `"[]"` denotes that atom, so the engine now SUCCEEDS
# exactly as the emitted program does, and the translator's warning for
# this literal is gone (item J, 2026-09-07). This pin records the
# agreement and goes RED the day the two sides part again.

_NIL_SOURCE = """empty_list([]),
hit(K) <- (K is "[]", empty_list(K))
"""


class TestBracketAtomLiteralAgrees:

    def test_bracket_atom_literal_agrees(self, tmp_path):
        mod = _load_clausal(tmp_path, "nil1", _NIL_SOURCE)
        var = Var()
        clausal = _run_clausal(lambda: mod.hit(var), var)
        # The engine's own answer: the atom `[]` is the empty list.
        assert clausal == ("succeeds", ([],)), clausal

        scryer = _run_scryer_multifile(
            tmp_path, {"harness.pl": _translate(_NIL_SOURCE)}, "hit(_).")
        assert scryer == ("succeeds", None), scryer

        assert_agreement(clausal, scryer, case='hit(K), K is "[]", empty_list(K)')


# ── chars mode: a string IS its char list, on both sides ─────────────────────
#
# Requested by the engine lane on landing e686ef5c ("a string is its char
# list in =="): the corpus suites' answer idiom is `X == "..."`, and under
# -double_quotes(chars) the ISO side reads "ab" as [a,b] by definition (Scryer:
# `"ab" == [a,b]` is true). Before e686ef5c the engine unified the two but `==`
# said no (measured on 9246f385) -- an answer-level disagreement the export
# would have silently inherited. This pin keeps both sides agreeing.

#: STRUCTURAL, so the comparison is spelled `'=='`. Ruling 2026-09-18: an
#: unquoted `==` here would be the CLP arithmetic constraint and a char list is
#: not an integer, so it would raise `domain_error(clpz_expression, ...)` --
#: which says nothing about whether a string IS its char list.
_STRING_EQ_SOURCE = """-double_quotes(chars)
-private([a, b])
hit(X) <- (X is "ab", '=='(X, [a, b]))
hit2(X) <- (X is [a, b], '=='(X, "ab"))
"""


class TestStringIsItsCharListInEquality:

    def test_string_equals_its_char_list_both_directions(self, tmp_path):
        mod = _load_clausal(tmp_path, "streq1", _STRING_EQ_SOURCE)
        for pred, case in ((mod.hit, 'hit(X), X is "ab", X == [a, b]'),
                           (mod.hit2, 'hit2(X), X is [a, b], X == "ab"')):
            var = Var()
            clausal = _run_clausal(lambda: pred(var), var)
            assert clausal[0] == "succeeds", (case, clausal)

        pl = _translate(_STRING_EQ_SOURCE)
        assert ":- set_prolog_flag(double_quotes, chars)." in pl
        for query, case in (("hit(_).", 'hit(X), X is "ab", X == [a, b]'),
                            ("hit2(_).", 'hit2(X), X is [a, b], X == "ab"')):
            scryer = _run_scryer_multifile(tmp_path, {"harness.pl": pl}, query)
            assert scryer == ("succeeds", None), (case, scryer)
