"""Tests for bytes support in DCG / phrase — Task 12.

Verifies that ``sequence//1`` handles ``bytes`` subjects in all modes
(A: s0 bound; B: s bound; C: both unbound) and that ``phrase//2,3``
correctly threads a ``bytes`` input through a DCG grammar that matches
integer-code terminals.

Grammar syntax note: this project uses ``>>`` (not ``-->``) for DCG rules.
Byte values are represented as their integer codes in terminal lists
(e.g., ``[71, 69, 84, 32]`` for ``b"GET "``). The assertions on bytes
*preservation* (remainder bound as ``bytes``, ``type(...) is bytes``) are
the real contract; the grammar uses int-code terminals.

Adapted from tests/audit_2026_05_25/test_class_C10_dcg_phrase.py (the
F070 sequence-mode tests) and tests/test_dcg.py (the phrase/3 tests).
"""

from __future__ import annotations

import os
import tempfile

import pytest

from clausal.import_hook import _load_module
from clausal.logic.solve import call
from clausal.logic.variables import Var, deref
from clausal.terms import SegBytes


# ── helpers ────────────────────────────────────────────────────────────────────


def _load_inline(name: str, source: str):
    """Write *source* to a temp .clausal file and load it; return module obj."""
    with tempfile.NamedTemporaryFile(suffix=".clausal", mode="w", delete=False) as f:
        f.write(source)
        f.flush()
        path = f.name
    try:
        return _load_module(name, path)
    finally:
        os.unlink(path)


def _mod(name: str, source: str = ""):
    """Return the ``$module`` from an inline source."""
    return _load_inline(name, source).__dict__["$module"]


# ── sequence//1 — bytes Modes A, B, C ─────────────────────────────────────────


class TestSequenceBytesMode:
    """``sequence(Lst, S0, S)`` with a ``bytes`` Lst value.

    Mirrors test_F070_sequence_mode_{a,b,c}_preserves_str from C10 but for bytes.
    """

    def test_mode_a_bytes_binds_remainder_as_bytes(self):
        # nv — Mode A: S0=bytes, S=unbound → S should be a bytes slice
        mod = _mod("seq_bytes_a")
        s0_val = b"abXY"
        s = Var()
        found = False
        for _ in call("sequence", b"ab", s0_val, s, module=mod):
            sv = deref(s)
            assert type(sv) is bytes, (
                f"sequence(b'ab', b'abXY', S): expected S as bytes, got {type(sv).__name__}: {sv!r}"
            )
            assert sv == b"XY", (
                f"sequence(b'ab', b'abXY', S): expected S=b'XY', got {sv!r}"
            )
            found = True
            break
        assert found, "sequence/3 Mode A with bytes: expected at least one solution"

    def test_mode_b_bytes_builds_s0_as_bytes(self):
        # nv — Mode B: S0=unbound, S=bytes → S0 should be bytes concatenation
        mod = _mod("seq_bytes_b")
        s0 = Var()
        s_val = b"XY"
        found = False
        for _ in call("sequence", b"ab", s0, s_val, module=mod):
            s0v = deref(s0)
            assert type(s0v) is bytes, (
                f"sequence(b'ab', S0, b'XY'): expected S0 as bytes, got {type(s0v).__name__}: {s0v!r}"
            )
            assert s0v == b"abXY", (
                f"sequence(b'ab', S0, b'XY'): expected S0=b'abXY', got {s0v!r}"
            )
            found = True
            break
        assert found, "sequence/3 Mode B with bytes: expected at least one solution"

    def test_mode_c_bytes_builds_segbytes(self):
        # nv — Mode C: S0=unbound, S=unbound, lst=bytes → S0 should be SegBytes
        mod = _mod("seq_bytes_c")
        s0 = Var()
        s = Var()
        found = False
        for _ in call("sequence", b"ab", s0, s, module=mod):
            s0v = deref(s0)
            assert isinstance(s0v, SegBytes), (
                f"sequence(b'ab', S0, S): expected SegBytes, got {type(s0v).__name__}: {s0v!r}"
            )
            found = True
            break
        assert found, "sequence/3 Mode C with bytes: expected at least one solution"

    def test_mode_a_bytes_no_match_fails(self):
        # nv — Mode A: prefix mismatch should fail
        mod = _mod("seq_bytes_a_fail")
        s0_val = b"xyXY"
        s = Var()
        sols = list(call("sequence", b"ab", s0_val, s, module=mod))
        assert len(sols) == 0, (
            f"sequence(b'ab', b'xyXY', S): expected 0 solutions (prefix mismatch), got {len(sols)}"
        )

    def test_mode_a_bytes_too_short_fails(self):
        # nv — Mode A: S0 shorter than lst should fail
        mod = _mod("seq_bytes_a_short")
        s = Var()
        sols = list(call("sequence", b"abc", b"ab", s, module=mod))
        assert len(sols) == 0, (
            f"sequence(b'abc', b'ab', S): expected 0 solutions (too short), got {len(sols)}"
        )

    def test_mode_b_bytes_list_s_fallback(self):
        # nv — Mode B: lst=bytes, s=list → S0 should be list (cross-type, no bytes)
        mod = _mod("seq_bytes_b_list")
        s0 = Var()
        # bytes + list: expected is list of int codes + list elements
        s_val = [88, 89]  # list, not bytes
        found = False
        for _ in call("sequence", b"ab", s0, s_val, module=mod):
            s0v = deref(s0)
            # cross-type → list (int codes from bytes + list ints)
            assert isinstance(s0v, list), (
                f"sequence(b'ab', S0, [88,89]): expected list fallback, got {type(s0v).__name__}: {s0v!r}"
            )
            assert s0v == [97, 98, 88, 89], (
                f"sequence(b'ab', S0, [88,89]): expected [97,98,88,89], got {s0v!r}"
            )
            found = True
            break
        assert found, "sequence/3 Mode B bytes+list: expected at least one solution"

    def test_str_input_unchanged(self):
        # nv — regression: str Lst still works after bytes extension
        mod = _mod("seq_str_reg")
        s = Var()
        found = False
        for _ in call("sequence", "ab", "abXY", s, module=mod):
            sv = deref(s)
            assert type(sv) is str and sv == "XY", (
                f"sequence('ab', 'abXY', S): regression — expected S='XY' (str), got {sv!r}"
            )
            found = True
            break
        assert found, "sequence/3 str regression: expected at least one solution"


# ── phrase//2,3 over bytes subjects ───────────────────────────────────────────


class TestPhraseBytesGrammar:
    """phrase over a bytes subject, using a DCG rule with int-code terminals.

    Grammar syntax: the project uses ``>>`` (not ``-->``). Byte values in
    terminals are written as their int codes: ``[71, 69, 84, 32]`` = b"GET ".
    """

    def test_phrase3_bytes_binds_remainder_as_bytes(self):
        # nv — phrase(g, b"GET /x", Rest) → Rest = b"/x" (bytes)
        # Grammar: match b"GET " via sequence non-terminal
        src = "g >> (sequence(b\"GET \"))\n"
        loaded = _load_inline("phrase_bytes_seq_a", src)
        mod = loaded.__dict__["$module"]
        cls = loaded.__dict__["g"]

        rest = Var()
        results = []
        for _ in call("phrase", cls, b"GET /x", rest, module=mod):
            results.append(deref(rest))
        assert len(results) >= 1, (
            "phrase(g, b'GET /x', Rest): expected >=1 solutions"
        )
        rv = results[0]
        assert rv == b"/x", (
            f"phrase(g, b'GET /x', Rest): expected Rest=b'/x', got {rv!r}"
        )
        assert type(rv) is bytes, (
            f"phrase(g, b'GET /x', Rest): expected Rest as bytes, got {type(rv).__name__}"
        )

    def test_phrase3_bytes_via_int_terminals(self):
        # nv — phrase(g, b"GET /x", Rest) with int-code terminal list
        # g >> ([71, 69, 84, 32])  matches b"GET "
        src = "g >> ([71, 69, 84, 32])\n"
        loaded = _load_inline("phrase_bytes_int_tok", src)
        mod = loaded.__dict__["$module"]
        cls = loaded.__dict__["g"]

        rest = Var()
        results = []
        for _ in call("phrase", cls, b"GET /x", rest, module=mod):
            results.append(deref(rest))
        assert len(results) >= 1, (
            "phrase(g, b'GET /x', Rest) with int terminals: expected >=1 solutions"
        )
        rv = results[0]
        assert rv == b"/x", (
            f"Expected Rest=b'/x', got {rv!r}"
        )
        assert type(rv) is bytes, (
            f"Expected bytes remainder, got {type(rv).__name__}"
        )

    def test_phrase2_bytes_parses_full_match(self):
        # nv — phrase(g, b"GET ") succeeds (full consumption)
        src = "g >> ([71, 69, 84, 32])\n"
        loaded = _load_inline("phrase_bytes_full", src)
        mod = loaded.__dict__["$module"]
        cls = loaded.__dict__["g"]

        count = sum(1 for _ in call("phrase", cls, b"GET ", module=mod))
        assert count >= 1, (
            "phrase(g, b'GET '): expected success (full consumption)"
        )

    def test_phrase2_bytes_fails_on_mismatch(self):
        # nv — phrase(g, b"POST ") fails when grammar expects b"GET "
        src = "g >> ([71, 69, 84, 32])\n"
        loaded = _load_inline("phrase_bytes_fail", src)
        mod = loaded.__dict__["$module"]
        cls = loaded.__dict__["g"]

        count = sum(1 for _ in call("phrase", cls, b"POST ", module=mod))
        assert count == 0, (
            f"phrase(g, b'POST '): expected failure (mismatch), got {count} solutions"
        )

    def test_phrase3_bytes_empty_remainder(self):
        # nv — phrase(g, b"GET ", Rest) → Rest = b""
        src = "g >> ([71, 69, 84, 32])\n"
        loaded = _load_inline("phrase_bytes_empty_rest", src)
        mod = loaded.__dict__["$module"]
        cls = loaded.__dict__["g"]

        rest = Var()
        results = []
        for _ in call("phrase", cls, b"GET ", rest, module=mod):
            results.append(deref(rest))
        assert len(results) >= 1, (
            "phrase(g, b'GET ', Rest): expected >=1 solutions"
        )
        rv = results[0]
        assert rv == b"", (
            f"phrase(g, b'GET ', Rest): expected Rest=b'', got {rv!r}"
        )
        assert type(rv) is bytes, (
            f"Expected bytes remainder, got {type(rv).__name__}"
        )

    def test_phrase3_bytes_type_preserved(self):
        # nv — core contract: remainder is bytes when input is bytes
        src = "g >> ([71, 69, 84, 32])\n"
        loaded = _load_inline("phrase_bytes_type_check", src)
        mod = loaded.__dict__["$module"]
        cls = loaded.__dict__["g"]

        rest = Var()
        results = []
        for _ in call("phrase", cls, b"GET /path/to/resource", rest, module=mod):
            results.append(deref(rest))
        assert results, "phrase/3 over bytes: expected at least one solution"
        rv = results[0]
        assert type(rv) is bytes, (
            f"phrase/3 over bytes: remainder type must be bytes, got {type(rv).__name__!r}: {rv!r}"
        )
        assert rv == b"/path/to/resource"


# ── realistic binary-protocol grammar (added in the docs pass) ────────────────


class TestBytesBinaryProtocolGrammar:
    """A small request-line grammar over a bytes stream, exercising a
    multi-rule DCG with int-code terminals, alternation, sequencing, and a
    preserved bytes remainder. Demonstrates the documented binary-protocol
    use case end to end."""

    _SRC = (
        "method >> ([71, 69, 84])\n"        # b"GET"  (alternation, no args)
        "method >> ([80, 85, 84])\n"        # b"PUT"
        "request >> (method, [32])\n"       # a method then a space b" "
    )

    def test_sequencing_and_remainder(self):
        # nv — composition (non-terminal then terminal); remainder stays bytes.
        loaded = _load_inline("bin_proto_a", self._SRC)
        req = loaded.__dict__["request"]
        m = loaded.__dict__["$module"]
        rest = Var()
        got = None
        for _ in call("phrase", req, b"GET /index", rest, module=m):
            got = (deref(rest), type(deref(rest)))
            break
        assert got == (b"/index", bytes)

    def test_alternation_matches_either_token(self):
        # nv — both GET and PUT alternatives parse to full consumption.
        loaded = _load_inline("bin_proto_b", self._SRC)
        req = loaded.__dict__["request"]
        m = loaded.__dict__["$module"]
        assert sum(1 for _ in call("phrase", req, b"GET ", b"", module=m)) >= 1
        assert sum(1 for _ in call("phrase", req, b"PUT ", b"", module=m)) >= 1

    def test_unknown_method_yields_no_parse(self):
        # nv — a token the grammar doesn't define produces zero solutions.
        loaded = _load_inline("bin_proto_c", self._SRC)
        req = loaded.__dict__["request"]
        m = loaded.__dict__["$module"]
        assert sum(1 for _ in call("phrase", req, b"DEL ", b"", module=m)) == 0
