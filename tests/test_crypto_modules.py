"""Tests for Phase 7c crypto modules: py.hash, py.hmac, py.pbkdf2."""

from __future__ import annotations

import pytest

from clausal.logic.variables import Var, Trail, deref, unify
from clausal.logic.trampoline import DONE

from clausal.modules.py.hash import (
    hash, hash_bytes, _hash_3, _hash_bytes_3,
)
from clausal.modules.py.hmac import (
    sign, verify, _sign_3, _sign_4, _verify_3, _verify_4,
)
from clausal.modules.py.pbkdf2 import (
    derive, _derive_4, _derive_5,
)


# ── Helpers ──────────────────────────────────────────────────────────────


def simple_solutions(fn, *args):
    """Run a simple-mode builtin and collect solutions."""
    trail = Trail()
    results = list(fn(*args, trail, None))
    return results, trail


def trampoline_solutions(pred, *args):
    """Run a trampoline-protocol predicate and collect solution snapshots."""
    trail = Trail()
    dispatch = pred._get_dispatch()
    gen = dispatch(None, None, None, None, *args, trail)
    solutions = []
    for parent, value in gen:
        if value is DONE:
            break
        solutions.append(value)
    return solutions, trail


# ── hash/3 ───────────────────────────────────────────────────────────────


class TestHash:

    def test_sha256_known_vector(self):
        """hash("sha256", "abc", H) → known hex digest."""
        # nv
        h = Var()
        sols, trail = simple_solutions(_hash_3, "sha256", "abc", h)
        assert len(sols) == 1
        assert deref(h) == "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"

    def test_sha512(self):
        # nv
        h = Var()
        sols, trail = simple_solutions(_hash_3, "sha512", "abc", h)
        assert len(sols) == 1
        assert len(deref(h)) == 128  # SHA-512 hex is 128 chars

    def test_md5(self):
        """MD5 of empty string."""
        # nv
        h = Var()
        sols, trail = simple_solutions(_hash_3, "md5", "", h)
        assert len(sols) == 1
        assert deref(h) == "d41d8cd98f00b204e9800998ecf8427e"

    def test_sha1(self):
        """SHA-1 of "abc"."""
        # nv
        h = Var()
        sols, trail = simple_solutions(_hash_3, "sha1", "abc", h)
        assert len(sols) == 1
        assert deref(h) == "a9993e364706816aba3e25717850c26c9cd0d89d"

    def test_bytes_input(self):
        """hash accepts bytes data."""
        # nv
        h = Var()
        sols, trail = simple_solutions(_hash_3, "sha256", b"abc", h)
        assert len(sols) == 1
        assert deref(h) == "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"

    def test_unknown_algorithm_fails(self):
        # nv
        h = Var()
        sols, _ = simple_solutions(_hash_3, "nonexistent", "abc", h)
        assert len(sols) == 0

    def test_unbound_data_fails(self):
        # nv
        h = Var()
        sols, _ = simple_solutions(_hash_3, "sha256", Var(), h)
        assert len(sols) == 0

    def test_unbound_algorithm_fails(self):
        # nv
        h = Var()
        sols, _ = simple_solutions(_hash_3, Var(), "abc", h)
        assert len(sols) == 0

    def test_trampoline_protocol(self):
        # nv
        h = Var()
        sols, trail = trampoline_solutions(hash, "sha256", "abc", h)
        assert len(sols) == 1
        assert deref(h) == "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"


# ── hash_bytes/3 ──────────────────────────────────────────────────────────


class TestHashBytes:

    def test_returns_bytes(self):
        # nv
        b = Var()
        sols, trail = simple_solutions(_hash_bytes_3, "sha256", "abc", b)
        assert len(sols) == 1
        assert isinstance(deref(b), bytes)

    def test_length_matches_algorithm(self):
        """SHA-256 → 32 bytes, SHA-512 → 64 bytes."""
        # nv
        b256 = Var()
        simple_solutions(_hash_bytes_3, "sha256", "abc", b256)
        assert len(deref(b256)) == 32

        b512 = Var()
        simple_solutions(_hash_bytes_3, "sha512", "abc", b512)
        assert len(deref(b512)) == 64


# ── sign/3,4 ─────────────────────────────────────────────────────────────


class TestHmacSign:

    def test_sha256_known_vector(self):
        """RFC 4231 test case 2: HMAC-SHA256."""
        # nv
        h = Var()
        sols, trail = simple_solutions(
            _sign_4, "sha256", b"\x0b" * 20, b"Hi There", h
        )
        assert len(sols) == 1
        assert deref(h) == "b0344c61d8db38535ca8afceaf0bf12b881dc200c9833da726e9376c2e32cff7"

    def test_default_sha256(self):
        """sign/3 uses SHA-256 by default."""
        # nv
        h3 = Var()
        h4 = Var()
        simple_solutions(_sign_3, "secret", "data", h3)
        simple_solutions(_sign_4, "sha256", "secret", "data", h4)
        assert deref(h3) == deref(h4)

    def test_different_key_different_result(self):
        # nv
        h1 = Var()
        h2 = Var()
        simple_solutions(_sign_3, "key1", "data", h1)
        simple_solutions(_sign_3, "key2", "data", h2)
        assert deref(h1) != deref(h2)

    def test_unbound_key_fails(self):
        # nv
        h = Var()
        sols, _ = simple_solutions(_sign_3, Var(), "data", h)
        assert len(sols) == 0

    def test_custom_algorithm(self):
        """sign("sha512", KEY, DATA, HEX)."""
        # nv
        h = Var()
        sols, trail = simple_solutions(_sign_4, "sha512", "key", "data", h)
        assert len(sols) == 1
        assert len(deref(h)) == 128  # SHA-512 hex

    def test_trampoline_protocol(self):
        # nv
        h = Var()
        sols, trail = trampoline_solutions(sign, "secret", "data", h)
        assert len(sols) == 1


# ── verify/3,4 ───────────────────────────────────────────────────────────


class TestHmacVerify:

    def test_correct_hmac_succeeds(self):
        # nv
        h = Var()
        simple_solutions(_sign_3, "secret", "data", h)
        hex_val = deref(h)
        sols, _ = simple_solutions(_verify_3, "secret", "data", hex_val)
        assert len(sols) == 1

    def test_incorrect_hmac_fails(self):
        # nv
        sols, _ = simple_solutions(_verify_3, "secret", "data", "deadbeef")
        assert len(sols) == 0

    def test_custom_algorithm(self):
        # nv
        h = Var()
        simple_solutions(_sign_4, "sha512", "key", "msg", h)
        hex_val = deref(h)
        sols, _ = simple_solutions(_verify_4, "sha512", "key", "msg", hex_val)
        assert len(sols) == 1


# ── derive/4,5 ───────────────────────────────────────────────────────────


class TestPbkdf2:

    def test_known_derivation(self):
        # nv
        dk = Var()
        sols, trail = simple_solutions(_derive_5, "password", "salt", 1, 32, dk)
        assert len(sols) == 1
        result = deref(dk)
        assert isinstance(result, str)
        assert len(result) == 64  # 32 bytes → 64 hex chars

    def test_different_iterations_different_result(self):
        # nv
        dk1 = Var()
        dk2 = Var()
        simple_solutions(_derive_5, "password", "salt", 1, 32, dk1)
        simple_solutions(_derive_5, "password", "salt", 2, 32, dk2)
        assert deref(dk1) != deref(dk2)

    def test_default_key_length(self):
        """derive/4 uses 32-byte key length."""
        # nv
        dk4 = Var()
        dk5 = Var()
        simple_solutions(_derive_4, "password", "salt", 1, dk4)
        simple_solutions(_derive_5, "password", "salt", 1, 32, dk5)
        assert deref(dk4) == deref(dk5)

    def test_unbound_password_fails(self):
        # nv
        dk = Var()
        sols, _ = simple_solutions(_derive_4, Var(), "salt", 1, dk)
        assert len(sols) == 0

    def test_zero_iterations_fails(self):
        # nv
        dk = Var()
        sols, _ = simple_solutions(_derive_5, "pw", "salt", 0, 32, dk)
        assert len(sols) == 0

    def test_trampoline_protocol(self):
        # nv
        dk = Var()
        sols, trail = trampoline_solutions(derive, "password", "salt", 1, dk)
        assert len(sols) == 1
