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
controller required (2026-09-05, A-3), and each is a reduction of a real kit host
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
    META_CALLER_SIGNATURES,
    clausal_source_to_prolog,
    clausal_source_to_prolog_ast,
    collect_local_meta_modes,
)

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
# The translator therefore emits exactly two spellings: an integer for a meta position
# and `?` for every other position. `:` is honoured but unneeded; `*` is a load error.

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
    assert META_CALLER_SIGNATURES[("include", 3)] == (0, 1)


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
