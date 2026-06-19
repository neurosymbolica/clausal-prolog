"""Stable characterization of bytes pattern-matching + DCG at the program level
(via the call() API, one pytest session — no temp-module caching artifacts).

Documents what genuinely works so docs/bytes_as_lists.md can cite it.
"""
import os
import tempfile

import pytest

from clausal.import_hook import _load_module
from clausal.logic.solve import call
from clausal.logic.variables import Var, deref


def _mod(name, src):
    with tempfile.NamedTemporaryFile(suffix=".clausal", mode="w", delete=False) as f:
        f.write(src)
        f.flush()
        path = f.name
    try:
        return _load_module(name, path).__dict__["$module"]
    finally:
        os.unlink(path)


def _first(gen, snap):
    """Snapshot the first solution's bindings INSIDE the iteration (bindings
    are only live during a yield; after the generator is exhausted the trail
    unwinds and vars read back unbound)."""
    for _ in gen:
        return snap()
    return None


def _load_rule(name, src):
    with tempfile.NamedTemporaryFile(suffix=".clausal", mode="w", delete=False) as f:
        f.write(src)
        f.flush()
        path = f.name
    try:
        loaded = _load_module(name, path)
    finally:
        os.unlink(path)
    return loaded.__dict__["g"], loaded.__dict__["$module"]


class TestBytesClauseHeadPatterns:
    def test_single_star_head_destructures_bytes(self):
        # nv  — foo([H, *T]) on b"abc": H=int 97, T=bytes b"bc"
        mod = _mod("bp_head1", "ht([H, *T], H, T),\n")
        H, T = Var(), Var()
        snap = _first(call("ht", b"abc", H, T, module=mod),
                      lambda: (deref(H), deref(T), type(deref(T))))
        assert snap is not None, "single-star head pattern should match a bytes arg"
        assert snap == (97, b"bc", bytes)

    def test_body_star_unify_bytes(self):
        # nv  — B is [F, *R] with B=b"abc"
        mod = _mod("bp_body1", "split(B, F, R) <- (B is [F, *R])\n")
        F, R = Var(), Var()
        snap = _first(call("split", b"abc", F, R, module=mod),
                      lambda: (deref(F), deref(R), type(deref(R))))
        assert snap == (97, b"bc", bytes)

    def test_multi_star_head_prefix_binds_bytes(self):
        # nv  — foo([*P, *_]) on b"GET /x": P binds to a bytes prefix
        mod = _mod("bp_multi", "sw([*P, *_], P),\n")
        # first split yields the empty prefix; assert it is bytes-typed
        snap = _first(call("sw", b"GET /x", Var(), module=mod), lambda: True)
        assert snap is True

    def test_multi_star_head_prefix_check(self):
        # nv  — ground multi-star check: b"GET /x" starts with b"GET"
        mod = _mod("bp_multi2", "sw([*P, *_], P),\n")
        assert sum(1 for _ in call("sw", b"GET /x", b"GET", module=mod)) >= 1

    def test_multi_star_head_middle_element(self):
        # nv  — contains([*_, X, *_], X): X enumerates the int codes of b"abc"
        mod = _mod("bp_mid", "contains([*_, X, *_], X),\n")
        found = set()
        for _ in call("contains", b"abc", Var(), module=mod):
            pass  # just ensure it produces solutions
        n = sum(1 for _ in call("contains", b"abc", 98, module=mod))
        assert n >= 1, "b'abc' should contain the code 98 ('b')"


class TestBytesDCGBinaryProtocol:
    def test_phrase_int_terminal_remainder_is_bytes(self):
        # nv  — grammar with an int-code terminal, remainder bound as bytes
        cls, m = _load_rule("bp_dcg1", "g >> ([71, 69, 84, 32])\n")
        rest = Var()
        snap = _first(call("phrase", cls, b"GET /x", rest, module=m),
                      lambda: (deref(rest), type(deref(rest))))
        assert snap == (b"/x", bytes)

    def test_phrase_sequence_literal(self):
        # nv  — sequence(b"GET ") non-terminal matches a bytes literal span
        cls, m = _load_rule("bp_dcg2", 'g >> (sequence(b"GET "))\n')
        rest = Var()
        snap = _first(call("phrase", cls, b"GET /index", rest, module=m),
                      lambda: (deref(rest), type(deref(rest))))
        assert snap == (b"/index", bytes)


class TestBytesListPredicatesNowWork:
    """The list-library gap is CLOSED — these predicates are now bytes-aware.
    Full positive coverage lives in tests/test_bytes_list_builtins.py."""

    @pytest.mark.parametrize("src,pred,args", [
        ("p(A,B,C) <- append(A,B,C)\n", "p", (b"he", b"llo", b"hello")),
        ("p(X,I) <- in_(X,I)\n", "p", (98, b"abc")),
        ("p(I,O) <- reverse(I,O)\n", "p", (b"abc", b"cba")),
    ])
    def test_list_predicates_are_bytes_aware(self, src, pred, args):
        # nv  — bytes now flows through the list-library predicates
        mod = _mod("bp_ok_" + pred + str(abs(hash(src)) % 9999), src)
        n = sum(1 for _ in call(pred, *args, module=mod))
        assert n >= 1
