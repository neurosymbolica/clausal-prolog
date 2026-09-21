"""Stage-1 pins for `:- meta_predicate` emission (class-M ladder, step A).

Authority: ``implementation_plans/prolog-lambda-lowering.md`` §3.3 (the mechanism,
verified in Scryer), §4.1 A1 (what to emit), §8 Stage 1 (the ordering), and the
"Stage-1 mechanism (ruled 2026-09-05)" subsection this work added to that note.

THE DEFECT, in one line: Scryer resolves a meta-call in the *callee's* module, so a
bare predicate reference handed to a translated higher-order predicate raises
``existence_error`` -- even when caller and callee are the same module (§3.2). A
``:- meta_predicate`` directive on the consuming predicate makes Scryer qualify the
meta-argument at the *call site*, which reproduces Clausal ``call_goal`` semantics.

WHAT ACCEPTANCE MEANS HERE. "A directive appears in the emitted text" is NOT
acceptance and no test in the end-to-end section settles for it: every case in
``TestScryerCallThrough`` consults real translator output in real Scryer and CALLS
THROUGH a bare reference, asserting the answer. The three shapes are the three the
controller required (2026-09-05, A-3), and each is a reduction of a real vocab host
measured in this session's host scan:

  (i)   a BODY-LOCAL host          -- ``eval_requirements/4`` shape (43 real sites)
  (ii)  a THREADING chain, X-MODULE-- ``find_mus/4`` / ``failing_ids/4`` shape (42 sites)
  (iii) a TWO-META-ARG host        -- ``verified_flips/5`` shape (18 sites), where one
        meta position is body-local (DECIDE) and the other is only reachable through
        a private helper (APPLY). Emitting a directive that covers DECIDE but not
        APPLY is the "present and wrong" hazard; (iii) fails if APPLY is missed.

Cases (ii) and (iii) need modes that a single module's text cannot supply -- they are
what the ``meta_modes`` kwarg exists for, and the exporter's cross-module fixpoint
(trunk ``tools/iso_export/export.py``) is what computes them in production. Here they
are supplied explicitly, so this file pins the *emission* half; the trunk suite pins
the *inference* half.
"""

from __future__ import annotations

import os
import subprocess

import pytest

from clausal.tools.clausal_to_prolog import (
    GOAL_TRANSPARENT,
    META_CALLER_SIGNATURES,
    MODE_MODULE_SENSITIVE,
    _existing_meta_predicate_indicators,
    clausal_source_to_prolog,
    clausal_source_to_prolog_ast,
    collect_local_meta_modes,
    goal_subterms,
)
from clausal.tools.prolog_ast import PAtom, PCompound, PDirective, PNumber

SCRYER = "/workspace/scryer-prolog/target/release/scryer-prolog"

requires_scryer = pytest.mark.skipif(
    not os.path.exists(SCRYER),
    reason=f"Scryer binary not found at {SCRYER} -- call-through acceptance needs a real engine",
)

# The one-clause `call_goal/N` shim over ISO `call/N`, verbatim the shape the design
# note's §1.3 and §3.2 probes use. Scryer has no `call_goal/N` (§5 lists it among the
# absent builtins); without the shim every case below would die at
# `existence_error(call_goal/N)` before reaching the thing under test. Supplying it as
# raw text rather than as Clausal source is deliberate: it keeps the shim out of the
# translator's own detection, so what the directive-emitter sees is only the host.
CALL_GOAL_SHIM = "\ncall_goal(G, A) :- call(G, A).\ncall_goal(G, A, B) :- call(G, A, B).\ncall_goal(G, A, B, C) :- call(G, A, B, C).\n"


def _scryer(tmp_path, files: dict[str, str], entry: str, query: str) -> str:
    """Write *files* into tmp_path, consult *entry* in real Scryer, run one *query*.

    Returns Scryer's first answer line verbatim (e.g. ``R = three.`` or
    ``error(existence_error(...),...).``) so a caller can assert on a real BINDING and
    not merely on success.
    """
    for name, text in files.items():
        (tmp_path / name).write_text(text)
    proc = subprocess.run(
        [SCRYER, entry], cwd=tmp_path, input=query + "\n",
        capture_output=True, text=True, timeout=15,
    )
    out = proc.stdout.strip()
    if not out:
        raise AssertionError(
            f"no answer from Scryer for {query!r}: stdout={proc.stdout!r} "
            f"stderr={proc.stderr!r} rc={proc.returncode}")
    return out.splitlines()[0].strip()


# ── A. The mode vocabulary Scryer actually honours (controller A-2) ──────────────
#
# A-2 asked which mode spellings Scryer honours, and for the MINIMAL honoured set to
# be what the translator emits. Measured in this session and pinned here so a Scryer
# upgrade that changes the answer turns this red rather than silently changing what a
# directive means:
#
#   integer N  -> HONOURED (qualifies; N = arguments call/N appends)
#   0          -> HONOURED (a plain goal)
#   :          -> HONOURED (module-sensitive term)
#   ?, +, -    -> valid syntax, NON-meta: the argument is NOT qualified
#   *          -> syntax_error(invalid_meta_predicate_decl) -- must never be emitted
#
# READ THIS TABLE NARROWLY. Every row below is a host whose argument is called at ONE
# arity, and there it is true that any integer works. It does NOT follow that the
# integer's value is ignored in general -- TestAmbiguousPositionContract measures mode
# `N` resolving the argument against `name/N` in the CALLER's module, which only shows
# up when the same name exists at several arities. Generalising this table beyond
# single-arity hosts is exactly the error that produced the `?, +, -` rows looking like
# limitations rather than the correct non-meta behaviour they are.
#
# The translator emits three spellings: an integer for a position with one call arity,
# `:` for a goal position called at several, and `?` for a non-meta position. `*` is a
# load error and is never emitted.

@requires_scryer
@pytest.mark.parametrize("mode,qualifies", [
    ("3", True), ("0", True), (":", True),
    ("?", False), ("+", False), ("-", False),
])
def test_scryer_mode_vocabulary(tmp_path, mode, qualifies):
    lib = (f":- module(mp_lib, [host/4]).\n"
           f":- meta_predicate(host(?, ?, {mode}, ?)).\n"
           f"host(A, B, G, R) :- call(G, A, B, R).\n")
    user = (":- module(mp_user, [go/1]).\n"
            ":- use_module('mp_lib', [host/4]).\n"
            "local(1, 2, three).\n"
            "go(R) :- host(1, 2, local, R).\n")
    answer = _scryer(tmp_path, {"mp_lib.pl": lib, "mp_user.pl": user}, "mp_user.pl", "go(R).")
    if qualifies:
        assert answer == "R = three.", f"mode {mode!r} was expected to qualify: {answer}"
    else:
        assert "existence_error" in answer, (
            f"mode {mode!r} is a NON-meta annotation and must not qualify: {answer}")


@requires_scryer
def test_scryer_rejects_star_mode(tmp_path):
    """`*` is a load-time syntax error -- pinned so it is never added to the emitter."""
    lib = (":- module(mp_lib, [host/4]).\n"
           ":- meta_predicate(host(?, ?, *, ?)).\n"
           "host(A, B, G, R) :- call(G, A, B, R).\n")
    answer = _scryer(tmp_path, {"mp_lib.pl": lib}, "mp_lib.pl", "true.")
    assert "syntax_error" in answer, answer


# ── B. Body-local detection ─────────────────────────────────────────────────────

_BODY_LOCAL_LIB = """-module(mlib, [
    host(A, B, G, R),
])

host(A, B, G, R) <- call_goal(G, A, B, R)
"""


def test_body_local_detection_finds_the_meta_position():
    pmodule = clausal_source_to_prolog_ast(_BODY_LOCAL_LIB, strict=True)
    assert collect_local_meta_modes(pmodule) == {("host", 4): {2: 3}}


def test_body_local_detection_emits_the_directive():
    out = clausal_source_to_prolog(_BODY_LOCAL_LIB, strict=True)
    assert ":- meta_predicate(host(?, ?, 3, ?))." in out


def test_directive_follows_the_module_directive():
    """Placement: with `discontiguous`, right after `:- module` and before any clause."""
    out = clausal_source_to_prolog(_BODY_LOCAL_LIB, strict=True)
    lines = [ln for ln in out.splitlines() if ln.strip()]
    assert lines[0].startswith(":- module(")
    assert lines[1] == ":- meta_predicate(host(?, ?, 3, ?))."


def test_no_meta_call_emits_no_directive():
    out = clausal_source_to_prolog("plain(A, B) <- (A is B)\n", strict=True)
    assert "meta_predicate" not in out


def test_a_goal_passed_on_but_never_called_is_not_a_meta_position():
    """A threading host has NO body-local evidence -- the exporter's fixpoint owns it.

    This is the 116-site population measured in this session's host scan. The
    translator must not guess a mode for it: an under-annotated position fails
    LOUDLY in Scryer (controller A-2), which is the accepted outcome, whereas a
    guessed mode would qualify a term that may not be a goal at all.
    """
    src = """-module(qc, [thread(A, G, R)])

thread(A, G, R) <- other(A, G, R)
"""
    out = clausal_source_to_prolog(src, strict=True)
    assert "meta_predicate" not in out


def test_call_goal_arities_map_to_appended_argument_counts():
    """`call_goal/N` applies the goal to N-1 arguments, so the mode is N-1."""
    src = """-module(m, [
    one(G),
    two(G),
    three(G),
])

one(G) <- call_goal(G, x)
two(G) <- call_goal(G, x, y)
three(G) <- call_goal(G, x, y, z)
"""
    pmodule = clausal_source_to_prolog_ast(src, strict=True)
    assert collect_local_meta_modes(pmodule) == {
        ("one", 1): {0: 1}, ("two", 1): {0: 2}, ("three", 1): {0: 3},
    }


def test_meta_caller_table_is_keyed_by_functor_and_arity():
    """The base-case table: (functor, arity) -> (goal argument index, appended count)."""
    assert META_CALLER_SIGNATURES[("call_goal", 3)] == (0, 2)
    assert META_CALLER_SIGNATURES[("call", 3)] == (0, 2)


@pytest.mark.parametrize("functor,arity", [
    ("include", 3), ("exclude", 3), ("max_by", 3), ("min_by", 3),
])
def test_the_table_carries_nothing_speculative(functor, arity):
    """No vocab host reaches these, and they are plausible DATA constructors.

    An earlier draft carried them on the reasoning that a host reaching one *would*
    be a meta host. In a legal corpus `include(...)`, `max_by(...)` and friends are
    at least as likely to be ordinary terms, and a wrong annotation on a data
    position corrupts it silently (see TestDataPositionFence). Step B re-adds
    include/3 when the companion exists and something consumes it.
    """
    assert (functor, arity) not in META_CALLER_SIGNATURES


def test_meta_call_under_a_goal_transparent_wrapper_is_found():
    """`once(call_goal(G, ...))` is the real `verified_flips/5` spelling."""
    src = """-module(m, [h(P, G, R)])

h(P, G, R) <- once(call_goal(G, P, R))
"""
    assert collect_local_meta_modes(
        clausal_source_to_prolog_ast(src, strict=True)) == {("h", 3): {1: 2}}


# ── C. The meta_modes kwarg (controller A-1(b)) ─────────────────────────────────

_THREADING_LIB = """-module(qc, [
    failing_like(IDS, P, PRED, OUT),
])
-import_from(flib, [eval_req(IDS, P, PRED, OUT)])

failing_like(IDS, P, PRED, OUT) <- eval_req(IDS, P, PRED, OUT)
"""


def test_meta_modes_supplies_a_mode_local_detection_cannot_see():
    out = clausal_source_to_prolog(
        _THREADING_LIB, strict=True, module_path="qc",
        module_signatures={"flib": {("eval_req", 4)}},
        meta_modes={"qc": {("failing_like", 4): (None, None, 4, None)}})
    assert ":- meta_predicate(failing_like(?, ?, 4, ?))." in out


def test_meta_modes_is_keyed_by_the_module_path_it_was_translated_under():
    """Lookup key is `module_path` exactly as passed (the exporter passes the same string)."""
    out = clausal_source_to_prolog(
        _THREADING_LIB, strict=True, module_path="qc",
        module_signatures={"flib": {("eval_req", 4)}},
        meta_modes={"a.different.module": {("failing_like", 4): (None, None, 4, None)}})
    assert "meta_predicate" not in out


def test_meta_modes_unions_with_local_detection():
    """Two meta positions, one from each source -- the `verified_flips/5` shape."""
    src = """-module(vlib, [
    vflips(P, E, APPLY, DECIDE, OUT),
])

vflips(P, E, APPLY, DECIDE, OUT) <- (
    call_goal(DECIDE, P, BASE),
    apply_one(P, E, APPLY, DECIDE, BASE, OUT)
)
"""
    out = clausal_source_to_prolog(
        src, strict=True, module_path="vlib",
        meta_modes={"vlib": {("vflips", 5): (None, None, 3, None, None)}})
    assert ":- meta_predicate(vflips(?, ?, 3, 2, ?))." in out


def test_meta_modes_never_declares_a_predicate_this_module_does_not_define():
    out = clausal_source_to_prolog(
        _BODY_LOCAL_LIB, strict=True, module_path="mlib",
        meta_modes={"mlib": {("elsewhere", 2): (0, None)}})
    assert "elsewhere" not in out


def test_directives_are_deterministic_across_runs():
    kwargs = dict(strict=True, module_path="vlib",
                  meta_modes={"vlib": {("host", 4): (None, None, 3, None)}})
    src = _BODY_LOCAL_LIB.replace("mlib", "vlib")
    assert clausal_source_to_prolog(src, **kwargs) == clausal_source_to_prolog(src, **kwargs)


# ── D. Scryer call-through acceptance (controller A-3) ───────────────────────────

class TestScryerCallThrough:
    """Consult real translator output and CALL a bare reference through it.

    Each case asserts a real binding. Each is paired with a NO-DIRECTIVE control that
    must raise `existence_error`, because a suite that only ever asserts success
    cannot tell a working directive from a Scryer that resolves bare atoms anyway --
    the control is what makes the green mean something.
    """

    # (i) body-local host -- the eval_requirements/4 shape
    LIB_I = _BODY_LOCAL_LIB
    DQ_I = """-module(dq, [
    go(R),
])
-import_from(mlib, [host(A, B, G, R)])

local(1, 2, three)

go(R) <- host(1, 2, local, R)
"""

    @requires_scryer
    def test_i_body_local_host_calls_through(self, tmp_path):
        lib = clausal_source_to_prolog(self.LIB_I, strict=True) + CALL_GOAL_SHIM
        assert ":- meta_predicate(host(?, ?, 3, ?))." in lib
        dq = clausal_source_to_prolog(self.DQ_I, strict=True)
        answer = _scryer(tmp_path, {"mlib.pl": lib, "dq.pl": dq}, "dq.pl", "go(R).")
        assert answer == "R = three.", answer

    @requires_scryer
    def test_i_control_without_the_directive_raises(self, tmp_path):
        lib = clausal_source_to_prolog(self.LIB_I, strict=True) + CALL_GOAL_SHIM
        stripped = "\n".join(ln for ln in lib.splitlines()
                             if not ln.startswith(":- meta_predicate("))
        dq = clausal_source_to_prolog(self.DQ_I, strict=True)
        answer = _scryer(tmp_path, {"mlib.pl": stripped, "dq.pl": dq}, "dq.pl", "go(R).")
        assert "existence_error" in answer, answer

    # (ii) threading chain, CROSS-MODULE -- the find_mus/4 + failing_ids/4 shape.
    # `qc:failing_like/4` never calls its own argument; the consumer is `flib:eval_req/4`
    # in ANOTHER module. Without a directive on the threading host the bare atom is
    # qualified in `qc` and raises -- measured in this session and the reason the
    # exporter needs a cross-module fixpoint rather than a body-local rule.
    FLIB_II = """-module(flib, [
    eval_req(IDS, P, PRED, OUT),
])

eval_req(ID, P, PRED, OUT) <- call_goal(PRED, ID, P, OUT)
"""
    QC_II = _THREADING_LIB
    DQ_II = """-module(dq2, [
    go(R),
])
-import_from(qc, [failing_like(IDS, P, PRED, OUT)])

local_req(r1, p, met)

go(R) <- failing_like(r1, p, local_req, R)
"""

    def _stage_ii(self):
        flib = clausal_source_to_prolog(self.FLIB_II, strict=True) + CALL_GOAL_SHIM
        qc = clausal_source_to_prolog(
            self.QC_II, strict=True, module_path="qc",
            module_signatures={"flib": {("eval_req", 4)}},
            meta_modes={"qc": {("failing_like", 4): (None, None, 3, None)}})
        dq = clausal_source_to_prolog(
            self.DQ_II, strict=True, module_path="dq2",
            module_signatures={"qc": {("failing_like", 4)}})
        return flib, qc, dq

    @requires_scryer
    def test_ii_threading_chain_calls_through(self, tmp_path):
        flib, qc, dq = self._stage_ii()
        assert ":- meta_predicate(eval_req(?, ?, 3, ?))." in flib
        assert ":- meta_predicate(failing_like(?, ?, 3, ?))." in qc
        answer = _scryer(tmp_path, {"flib.pl": flib, "qc.pl": qc, "dq2.pl": dq},
                         "dq2.pl", "go(R).")
        assert answer == "R = met.", answer

    @requires_scryer
    def test_ii_control_consumer_declared_but_threading_host_not_still_raises(self, tmp_path):
        """The measurement that forced the fixpoint: declaring only the CONSUMER fails."""
        flib, _, dq = self._stage_ii()
        qc_bare = clausal_source_to_prolog(
            self.QC_II, strict=True, module_path="qc",
            module_signatures={"flib": {("eval_req", 4)}})
        assert "meta_predicate" not in qc_bare
        answer = _scryer(tmp_path, {"flib.pl": flib, "qc.pl": qc_bare, "dq2.pl": dq},
                         "dq2.pl", "go(R).")
        assert "existence_error" in answer, answer

    # (iii) TWO meta arguments -- the verified_flips/5 shape. DECIDE is body-local;
    # APPLY is only ever called by the private helper `apply_one/6`. A directive that
    # covers DECIDE alone loads fine, looks emitted, and still raises on APPLY.
    VLIB_III = """-module(vlib, [
    vflips(P, E, APPLY, DECIDE, OUT),
])

vflips(P, E, APPLY, DECIDE, OUT) <- (
    call_goal(DECIDE, P, BASE),
    apply_one(P, E, APPLY, DECIDE, BASE, OUT)
)

apply_one(P, E, APPLY, DECIDE, BASE, result(BASE, NEW)) <- (
    call_goal(APPLY, P, E, P2),
    call_goal(DECIDE, P2, NEW)
)
"""
    DQ_III = """-module(dq3, [
    go(R),
])
-import_from(vlib, [vflips(P, E, APPLY, DECIDE, OUT)])

edit(base, bump, bumped)
verdict(base, low)
verdict(bumped, high)

go(R) <- vflips(base, bump, edit, verdict, R)
"""

    def _stage_iii(self, *, apply_mode):
        modes = {("vflips", 5): (None, None, apply_mode, None, None)}
        vlib = clausal_source_to_prolog(
            self.VLIB_III, strict=True, module_path="vlib",
            meta_modes={"vlib": modes}) + CALL_GOAL_SHIM
        dq = clausal_source_to_prolog(
            self.DQ_III, strict=True, module_path="dq3",
            module_signatures={"vlib": {("vflips", 5)}})
        return vlib, dq

    @requires_scryer
    def test_iii_both_meta_arguments_call_through(self, tmp_path):
        vlib, dq = self._stage_iii(apply_mode=3)
        assert ":- meta_predicate(vflips(?, ?, 3, 2, ?))." in vlib, vlib
        answer = _scryer(tmp_path, {"vlib.pl": vlib, "dq3.pl": dq}, "dq3.pl", "go(R).")
        assert answer == "R = result(low,high).", answer

    @requires_scryer
    def test_iii_control_covering_only_the_body_local_argument_still_raises(self, tmp_path):
        """The 'present and wrong' hazard: DECIDE annotated, APPLY missed."""
        vlib, dq = self._stage_iii(apply_mode=None)
        assert ":- meta_predicate(vflips(?, ?, ?, 2, ?))." in vlib, vlib
        answer = _scryer(tmp_path, {"vlib.pl": vlib, "dq3.pl": dq}, "dq3.pl", "go(R).")
        assert "existence_error" in answer, answer


# ── E. The goal-position fence ──────────────────────────────────────────────────

class TestDataPositionFence:
    """Evidence is read from GOAL positions only -- never from a term that merely
    LOOKS like a meta-call.

    `test_the_hazard_is_real` is the reason this fence exists and is measured, not
    assumed: it hand-writes the annotation the unfenced scan would have produced and
    shows Scryer silently corrupting a data argument. The other cases show the
    translator does not produce it.
    """

    @requires_scryer
    def test_the_hazard_is_real(self, tmp_path):
        """A mode on a DATA position corrupts the term, silently and with no error.

        `keep/2` just unifies its two arguments. Annotate argument 1 as a goal and
        Scryer module-qualifies it at the call site, so a caller that passed `foo`
        gets back `hazard_user:foo` -- and `R == foo` then FAILS with no error
        anywhere. Loud failure is acceptable (controller A-2); this is the quiet kind.
        """
        lib = (":- module(hazard_lib, [keep/2]).\n"
               ":- meta_predicate(keep(1, ?)).\n"
               "keep(D, D).\n")
        user = (":- module(hazard_user, [probe/1, same/0]).\n"
                ":- use_module('hazard_lib', [keep/2]).\n"
                "probe(R) :- keep(foo, R).\n"
                "same :- keep(foo, R), R == foo.\n")
        files = {"hazard_lib.pl": lib, "hazard_user.pl": user}
        assert _scryer(tmp_path, files, "hazard_user.pl", "probe(R).") == \
            "R = hazard_user:foo."
        assert _scryer(tmp_path, files, "hazard_user.pl", "same.") == "false."

    def test_a_term_that_merely_looks_like_a_meta_call_is_not_evidence(self):
        """The `mk` shape: the clause BUILDS `call_goal(D, X)`, it never calls it."""
        src = "mk(D, X, T) <- (T is call_goal(D, X))\n"
        assert collect_local_meta_modes(
            clausal_source_to_prolog_ast(src, strict=True)) == {}
        assert "meta_predicate" not in clausal_source_to_prolog(src, strict=True)

    def test_a_locally_built_closure_does_not_annotate_its_captured_parameter(self):
        """`D` is captured INSIDE the goal term; the goal is not `D` itself."""
        src = "host(D, X, Y) <- call_goal(closure_over(D), X, Y)\n"
        assert collect_local_meta_modes(
            clausal_source_to_prolog_ast(src, strict=True)) == {}
        assert "meta_predicate" not in clausal_source_to_prolog(src, strict=True)

    def test_a_real_meta_call_under_a_data_term_is_still_not_reached(self):
        """Depth does not rescue it: the fence stops at the first non-combinator."""
        src = "mk(D, T) <- (T is wrapper(once(call_goal(D, x))))\n"
        assert collect_local_meta_modes(
            clausal_source_to_prolog_ast(src, strict=True)) == {}

    def test_goal_subterms_descends_combinators_and_stops_at_data(self):
        goal = PCompound(",", (
            PCompound("once", (PCompound("reached", (PAtom("a"),)),)),
            PCompound("=", (PAtom("t"), PCompound("not_reached", (PAtom("b"),)))),
        ))
        functors = {n.functor for n in goal_subterms(goal) if isinstance(n, PCompound)}
        assert "reached" in functors
        assert "not_reached" not in functors

    def test_every_goal_transparent_entry_indexes_a_real_argument(self):
        for (functor, arity), indexes in GOAL_TRANSPARENT.items():
            assert indexes, f"{functor}/{arity} lists no goal argument"
            assert max(indexes) < arity, f"{functor}/{arity} indexes past its arity"


# ── F. The ambiguous-position contract (controller ruling 2026-09-05) ───────────

class TestAmbiguousPositionContract:
    """ONE contract, shared by local detection, the supplied map and the fixpoint:

      * a position with a SINGLE call arity   -> that integer;
      * a position that IS a goal but is called at SEVERAL arities -> `:`;
      * a position with NO goal evidence      -> `?`, never a guess.

    The ruling reached here assumed Scryer ignores the integer's value, which would
    have allowed any candidate (it proposed the maximum). It does not:
    `test_the_mode_integer_pins_the_callers_arity` measures mode `N` resolving the
    argument against `name/N` in the CALLER's module, so the maximum silently drops
    every other chain, and `0` is not a safe stand-in either. `:` is the only
    spelling correct in every row, so it implements the ruling's intent -- "every
    chain then works" -- with the mechanism that actually holds.
    """

    AMBIGUOUS = ("two(PRED, OUT) <- call_goal(PRED, a, OUT)\n"
                 "two(PRED, OUT) <- call_goal(PRED, a, b, OUT)\n")

    @requires_scryer
    @pytest.mark.parametrize("mode,expected", [
        ("2", "L = [short]."),          # pins p/2: the 3-appended clause is lost
        ("3", "L = [long]."),           # pins p/3: the 2-appended clause is lost
        (":", "L = [short,long]."),     # qualifies without pinning: both survive
    ])
    def test_the_mode_integer_pins_the_callers_arity(self, tmp_path, mode, expected):
        """The measurement the contract turns on. A host calling its argument at two
        arities, against a caller that defines the name at both."""
        lib = (f":- module(amb, [two/2]).\n"
               f":- meta_predicate(two({mode}, ?)).\n"
               f"two(Pred, Out) :- call(Pred, a, Out).\n"
               f"two(Pred, Out) :- call(Pred, a, b, Out).\n")
        user = (":- module(ambq, [go/1]).\n"
                ":- use_module('amb', [two/2]).\n"
                "p(a, short).\n"
                "p(a, b, long).\n"
                "go(R) :- two(p, R).\n")
        answer = _scryer(tmp_path, {"amb.pl": lib, "ambq.pl": user}, "ambq.pl",
                         "findall(R, go(R), L).")
        assert answer == expected, answer

    @requires_scryer
    def test_zero_is_not_a_safe_stand_in(self, tmp_path):
        """`0` only looks safe until the caller defines the name at arity 0.

        It then binds the meta-argument to `p/0` and the caller gets back UNBOUND
        variables -- no error, wrong answers. This is why the ambiguous mode is `:`
        and not `0`.
        """
        lib = (":- module(amb, [two/2]).\n"
               ":- meta_predicate(two(0, ?)).\n"
               "two(Pred, Out) :- call(Pred, a, Out).\n"
               "two(Pred, Out) :- call(Pred, a, b, Out).\n")
        user = (":- module(ambq, [go/1]).\n"
                ":- use_module('amb', [two/2]).\n"
                "p.\n"
                "p(a, short).\n"
                "p(a, b, long).\n"
                "go(R) :- two(p, R).\n")
        answer = _scryer(tmp_path, {"amb.pl": lib, "ambq.pl": user}, "ambq.pl",
                         "findall(R, go(R), L).")
        assert "short" not in answer and "long" not in answer, answer

    @requires_scryer
    def test_colon_qualifies_a_bare_reference_for_call_n_consumption(self, tmp_path):
        """`:` is LOAD-BEARING here, so it is pinned directly and not by implication.

        The whole ambiguous-position contract rests on `:` doing the one job the
        directive exists for: making a BARE predicate reference from the caller's
        module resolve when the callee reaches it through `call/N`. Asserted here
        against a real binding, with a `?` control on the identical layout that must
        raise -- so this cannot go green on a Scryer that resolves bare atoms anyway.
        """
        def lib(mode):
            return (f":- module(collib, [host/4]).\n"
                    f":- meta_predicate(host(?, ?, {mode}, ?)).\n"
                    f"host(A, B, G, R) :- call(G, A, B, R).\n")
        user = (":- module(coluser, [go/1]).\n"
                ":- use_module('collib', [host/4]).\n"
                "local(1, 2, three).\n"
                "go(R) :- host(1, 2, local, R).\n")

        answer = _scryer(tmp_path, {"collib.pl": lib(":"), "coluser.pl": user},
                         "coluser.pl", "go(R).")
        assert answer == "R = three.", answer

        control = _scryer(tmp_path, {"collib.pl": lib("?"), "coluser.pl": user},
                          "coluser.pl", "go(R).")
        assert "existence_error" in control, control

    def test_conflicting_local_arities_become_module_sensitive(self):
        assert collect_local_meta_modes(
            clausal_source_to_prolog_ast(self.AMBIGUOUS, strict=True)) == {
            ("two", 2): {0: MODE_MODULE_SENSITIVE}}
        assert ":- meta_predicate(two(:, ?))." in clausal_source_to_prolog(
            self.AMBIGUOUS, strict=True)

    def test_a_single_call_arity_still_emits_the_precise_integer(self):
        assert ":- meta_predicate(host(?, ?, 3, ?))." in clausal_source_to_prolog(
            _BODY_LOCAL_LIB, strict=True)

    def test_local_and_supplied_disagreeing_become_module_sensitive(self):
        """Neither source wins -- the shipped behaviour must equal the documented one."""
        out = clausal_source_to_prolog(
            _BODY_LOCAL_LIB, strict=True, module_path="mlib",
            meta_modes={"mlib": {("host", 4): (None, None, 5, None)}})
        assert ":- meta_predicate(host(?, ?, :, ?))." in out

    def test_local_and_supplied_agreeing_keep_the_integer(self):
        out = clausal_source_to_prolog(
            _BODY_LOCAL_LIB, strict=True, module_path="mlib",
            meta_modes={"mlib": {("host", 4): (None, None, 3, None)}})
        assert ":- meta_predicate(host(?, ?, 3, ?))." in out

    def test_a_supplied_module_sensitive_mode_is_emitted_as_is(self):
        out = clausal_source_to_prolog(
            _THREADING_LIB, strict=True, module_path="qc",
            module_signatures={"flib": {("eval_req", 4)}},
            meta_modes={"qc": {("failing_like", 4): (
                None, None, MODE_MODULE_SENSITIVE, None)}})
        assert ":- meta_predicate(failing_like(?, ?, :, ?))." in out

    @requires_scryer
    def test_the_emitted_module_sensitive_directive_calls_through_at_both_arities(
            self, tmp_path):
        """End to end on translator output: BOTH chains must resolve."""
        lib = clausal_source_to_prolog(
            "-module(amb, [\n    two(PRED, OUT),\n])\n\n" + self.AMBIGUOUS,
            strict=True) + CALL_GOAL_SHIM
        assert ":- meta_predicate(two(:, ?))." in lib
        dq = clausal_source_to_prolog(
            "-module(ambq, [\n    go(R),\n])\n"
            "-import_from(amb, [two(PRED, OUT)])\n\n"
            "p(a, short)\n"
            "p(a, b, long)\n\n"
            "go(R) <- two(p, R)\n", strict=True)
        answer = _scryer(tmp_path, {"amb.pl": lib, "ambq.pl": dq}, "ambq.pl",
                         "findall(R, go(R), L).")
        assert answer == "L = [short,long].", answer


# ── G. Hand-written directives suppress the generated one (controller A-4) ───────

def test_a_hand_written_directive_suppresses_the_generated_one():
    src = "-meta_predicate(host(0))\n\nhost(G) <- call_goal(G)\n"
    out = clausal_source_to_prolog(src, strict=True)
    assert out.count("meta_predicate") == 1
    assert ":- meta_predicate(host(0))." in out


def test_the_conjunction_spelling_suppresses_every_predicate_it_names():
    """ISO allows one directive to carry a comma-separated list of specs."""
    src = ("-meta_predicate((host(0), other(0)))\n\n"
           "host(G) <- call_goal(G)\n"
           "other(G) <- call_goal(G)\n")
    out = clausal_source_to_prolog(src, strict=True)
    assert out.count("meta_predicate") == 1


def test_existing_indicators_read_both_spellings():
    single = PDirective(PCompound("meta_predicate", (
        PCompound("foo", (PNumber(0), PAtom("?"))),)))
    assert _existing_meta_predicate_indicators(single) == {("foo", 2)}

    conjunction = PDirective(PCompound("meta_predicate", (
        PCompound(",", (
            PCompound("foo", (PNumber(0), PAtom("?"))),
            PCompound(",", (
                PCompound("bar", (PAtom("?"),)),
                PCompound("baz", (PNumber(2), PAtom("?"), PAtom("?"))),
            )),
        )),)))
    assert _existing_meta_predicate_indicators(conjunction) == {
        ("foo", 2), ("bar", 1), ("baz", 3)}
