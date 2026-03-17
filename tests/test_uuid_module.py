"""Tests for clausal.modules.uuid_mod — UUID predicates.

All predicates produce and consume real Python uuid.UUID objects.
"""

from __future__ import annotations

import os
import uuid

import pytest

from clausal.logic.variables import Var, Trail, deref, unify
from clausal.modules.uuid_mod import (
    UUIDv4, UUIDv1, UUIDv3, UUIDv5,
    UUIDStr, UUIDHex, UUIDUrn, UUIDBytes, UUIDInt,
    UUIDVersion, UUIDFields, IsUUID,
    _uuid4_1, _uuid1_1, _uuid3_3, _uuid5_3,
    _uuid_str_2, _uuid_hex_2, _uuid_urn_2, _uuid_bytes_2, _uuid_int_2,
    _uuid_version_2, _uuid_fields_7, _is_uuid_1,
)
from clausal.logic.trampoline import DONE
from clausal.logic.solve import call
from clausal.import_hook import _load_module


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
    gen = dispatch(None, None, *args, trail)
    solutions = []
    for parent, value in gen:
        if value is DONE:
            break
        solutions.append(value)
    return solutions, trail


_UUID_IMPORT = '-import_from(uuid, [UUIDv4, UUIDv1, UUIDv3, UUIDv5, UUIDStr, UUIDHex, UUIDUrn, UUIDBytes, UUIDInt, UUIDVersion, UUIDFields, IsUUID])\n'


def _load(name, src_text, tmp_path):
    """Write a .clausal file and load it."""
    p = tmp_path / f"{name}.clausal"
    p.write_text(_UUID_IMPORT + src_text)
    mod = _load_module(name, str(p))
    return mod.__dict__["$module"]


def _succeeds(functor, *args, module):
    for _ in call(functor, *args, module=module):
        return True
    return False


# ── Uuid4 ────────────────────────────────────────────────────────────────


class TestUuid4:
    def test_uuid4_generates(self):
        v = Var()
        results, trail = simple_solutions(_uuid4_1, v)
        assert len(results) == 1
        val = deref(v)
        assert isinstance(val, uuid.UUID)
        assert val.version == 4

    def test_uuid4_unique(self):
        v1, v2 = Var(), Var()
        simple_solutions(_uuid4_1, v1)
        simple_solutions(_uuid4_1, v2)
        assert deref(v1) != deref(v2)

    def test_uuid4_trampoline(self):
        v = Var()
        solutions, trail = trampoline_solutions(UUIDv4, v)
        assert len(solutions) == 1
        assert isinstance(deref(v), uuid.UUID)


# ── Uuid1 ────────────────────────────────────────────────────────────────


class TestUuid1:
    def test_uuid1_generates(self):
        v = Var()
        results, trail = simple_solutions(_uuid1_1, v)
        assert len(results) == 1
        val = deref(v)
        assert isinstance(val, uuid.UUID)
        assert val.version == 1

    def test_uuid1_trampoline(self):
        v = Var()
        solutions, trail = trampoline_solutions(UUIDv1, v)
        assert len(solutions) == 1
        assert isinstance(deref(v), uuid.UUID)


# ── Uuid3 ────────────────────────────────────────────────────────────────


class TestUuid3:
    def test_uuid3_deterministic(self):
        u1, u2 = Var(), Var()
        simple_solutions(_uuid3_3, "dns", "example.com", u1)
        simple_solutions(_uuid3_3, "dns", "example.com", u2)
        assert deref(u1) == deref(u2)

    def test_uuid3_version(self):
        v = Var()
        simple_solutions(_uuid3_3, "dns", "test", v)
        assert deref(v).version == 3

    def test_uuid3_all_namespaces(self):
        for ns in ("dns", "url", "oid", "x500"):
            v = Var()
            results, _ = simple_solutions(_uuid3_3, ns, "test", v)
            assert len(results) == 1, f"namespace {ns} failed"

    def test_uuid3_raw_namespace(self):
        v = Var()
        results, _ = simple_solutions(_uuid3_3, uuid.NAMESPACE_DNS, "test", v)
        assert len(results) == 1

    def test_uuid3_bad_namespace_fails(self):
        v = Var()
        results, _ = simple_solutions(_uuid3_3, "invalid", "test", v)
        assert len(results) == 0

    def test_uuid3_unbound_name_fails(self):
        v, name = Var(), Var()
        results, _ = simple_solutions(_uuid3_3, "dns", name, v)
        assert len(results) == 0

    def test_uuid3_trampoline(self):
        v = Var()
        solutions, _ = trampoline_solutions(UUIDv3, "dns", "example.com", v)
        assert len(solutions) == 1


# ── Uuid5 ────────────────────────────────────────────────────────────────


class TestUuid5:
    def test_uuid5_deterministic(self):
        u1, u2 = Var(), Var()
        simple_solutions(_uuid5_3, "url", "https://example.com", u1)
        simple_solutions(_uuid5_3, "url", "https://example.com", u2)
        assert deref(u1) == deref(u2)

    def test_uuid5_version(self):
        v = Var()
        simple_solutions(_uuid5_3, "dns", "test", v)
        assert deref(v).version == 5

    def test_uuid5_trampoline(self):
        v = Var()
        solutions, _ = trampoline_solutions(UUIDv5, "url", "test", v)
        assert len(solutions) == 1


# ── UUIDStr ──────────────────────────────────────────────────────────────


class TestUUIDStr:
    def test_decompose(self):
        u = uuid.uuid4()
        s = Var()
        results, _ = simple_solutions(_uuid_str_2, u, s)
        assert len(results) == 1
        assert deref(s) == str(u)

    def test_construct(self):
        original = uuid.uuid4()
        s = str(original)
        u = Var()
        results, _ = simple_solutions(_uuid_str_2, u, s)
        assert len(results) == 1
        assert deref(u) == original

    def test_roundtrip(self):
        u_in = uuid.uuid4()
        s, u_out = Var(), Var()
        simple_solutions(_uuid_str_2, u_in, s)
        simple_solutions(_uuid_str_2, u_out, deref(s))
        assert deref(u_out) == u_in

    def test_both_ground_match(self):
        u = uuid.uuid4()
        results, _ = simple_solutions(_uuid_str_2, u, str(u))
        assert len(results) == 1

    def test_both_ground_mismatch(self):
        u = uuid.uuid4()
        results, _ = simple_solutions(_uuid_str_2, u, "not-a-match")
        assert len(results) == 0

    def test_bad_string_fails(self):
        u = Var()
        results, _ = simple_solutions(_uuid_str_2, u, "not-a-uuid")
        assert len(results) == 0


# ── UUIDHex ──────────────────────────────────────────────────────────────


class TestUUIDHex:
    def test_decompose(self):
        u = uuid.uuid4()
        h = Var()
        results, _ = simple_solutions(_uuid_hex_2, u, h)
        assert len(results) == 1
        assert deref(h) == u.hex

    def test_construct(self):
        original = uuid.uuid4()
        u = Var()
        results, _ = simple_solutions(_uuid_hex_2, u, original.hex)
        assert len(results) == 1
        assert deref(u) == original

    def test_roundtrip(self):
        u_in = uuid.uuid4()
        h, u_out = Var(), Var()
        simple_solutions(_uuid_hex_2, u_in, h)
        simple_solutions(_uuid_hex_2, u_out, deref(h))
        assert deref(u_out) == u_in

    def test_bad_hex_fails(self):
        u = Var()
        results, _ = simple_solutions(_uuid_hex_2, u, "zzzz")
        assert len(results) == 0


# ── UUIDUrn ──────────────────────────────────────────────────────────────


class TestUUIDUrn:
    def test_decompose(self):
        u = uuid.uuid4()
        urn = Var()
        results, _ = simple_solutions(_uuid_urn_2, u, urn)
        assert len(results) == 1
        assert deref(urn) == u.urn

    def test_construct(self):
        original = uuid.uuid4()
        u = Var()
        results, _ = simple_solutions(_uuid_urn_2, u, original.urn)
        assert len(results) == 1
        assert deref(u) == original

    def test_roundtrip(self):
        u_in = uuid.uuid4()
        urn, u_out = Var(), Var()
        simple_solutions(_uuid_urn_2, u_in, urn)
        simple_solutions(_uuid_urn_2, u_out, deref(urn))
        assert deref(u_out) == u_in


# ── UUIDBytes ────────────────────────────────────────────────────────────


class TestUUIDBytes:
    def test_decompose(self):
        u = uuid.uuid4()
        b = Var()
        results, _ = simple_solutions(_uuid_bytes_2, u, b)
        assert len(results) == 1
        assert deref(b) == u.bytes

    def test_construct(self):
        original = uuid.uuid4()
        u = Var()
        results, _ = simple_solutions(_uuid_bytes_2, u, original.bytes)
        assert len(results) == 1
        assert deref(u) == original

    def test_roundtrip(self):
        u_in = uuid.uuid4()
        b, u_out = Var(), Var()
        simple_solutions(_uuid_bytes_2, u_in, b)
        simple_solutions(_uuid_bytes_2, u_out, deref(b))
        assert deref(u_out) == u_in

    def test_wrong_length_fails(self):
        u = Var()
        results, _ = simple_solutions(_uuid_bytes_2, u, b"\x00\x01\x02")
        assert len(results) == 0


# ── UUIDInt ──────────────────────────────────────────────────────────────


class TestUUIDInt:
    def test_decompose(self):
        u = uuid.uuid4()
        n = Var()
        results, _ = simple_solutions(_uuid_int_2, u, n)
        assert len(results) == 1
        assert deref(n) == u.int

    def test_construct(self):
        original = uuid.uuid4()
        u = Var()
        results, _ = simple_solutions(_uuid_int_2, u, original.int)
        assert len(results) == 1
        assert deref(u) == original

    def test_roundtrip(self):
        u_in = uuid.uuid4()
        n, u_out = Var(), Var()
        simple_solutions(_uuid_int_2, u_in, n)
        simple_solutions(_uuid_int_2, u_out, deref(n))
        assert deref(u_out) == u_in

    def test_negative_fails(self):
        u = Var()
        results, _ = simple_solutions(_uuid_int_2, u, -1)
        assert len(results) == 0


# ── UUIDVersion ──────────────────────────────────────────────────────────


class TestUUIDVersion:
    def test_version_v4(self):
        u = uuid.uuid4()
        v = Var()
        results, _ = simple_solutions(_uuid_version_2, u, v)
        assert len(results) == 1
        assert deref(v) == 4

    def test_version_v1(self):
        u = uuid.uuid1()
        v = Var()
        results, _ = simple_solutions(_uuid_version_2, u, v)
        assert len(results) == 1
        assert deref(v) == 1

    def test_version_v3(self):
        u = uuid.uuid3(uuid.NAMESPACE_DNS, "test")
        v = Var()
        results, _ = simple_solutions(_uuid_version_2, u, v)
        assert len(results) == 1
        assert deref(v) == 3

    def test_version_v5(self):
        u = uuid.uuid5(uuid.NAMESPACE_DNS, "test")
        v = Var()
        results, _ = simple_solutions(_uuid_version_2, u, v)
        assert len(results) == 1
        assert deref(v) == 5

    def test_non_uuid_fails(self):
        v = Var()
        results, _ = simple_solutions(_uuid_version_2, "not-a-uuid", v)
        assert len(results) == 0


# ── UUIDFields ───────────────────────────────────────────────────────────


class TestUUIDFields:
    def test_decompose(self):
        u = uuid.uuid4()
        tl, tm, th, csh, csl, node = Var(), Var(), Var(), Var(), Var(), Var()
        results, _ = simple_solutions(_uuid_fields_7, u, tl, tm, th, csh, csl, node)
        assert len(results) == 1
        fields = u.fields
        assert deref(tl) == fields[0]
        assert deref(tm) == fields[1]
        assert deref(th) == fields[2]
        assert deref(csh) == fields[3]
        assert deref(csl) == fields[4]
        assert deref(node) == fields[5]

    def test_non_uuid_fails(self):
        tl, tm, th, csh, csl, node = Var(), Var(), Var(), Var(), Var(), Var()
        results, _ = simple_solutions(_uuid_fields_7, 42, tl, tm, th, csh, csl, node)
        assert len(results) == 0


# ── IsUUID ───────────────────────────────────────────────────────────────


class TestIsUUID:
    def test_uuid_passes(self):
        u = uuid.uuid4()
        results, _ = simple_solutions(_is_uuid_1, u)
        assert len(results) == 1

    def test_string_fails(self):
        results, _ = simple_solutions(_is_uuid_1, str(uuid.uuid4()))
        assert len(results) == 0

    def test_int_fails(self):
        results, _ = simple_solutions(_is_uuid_1, 42)
        assert len(results) == 0

    def test_var_fails(self):
        results, _ = simple_solutions(_is_uuid_1, Var())
        assert len(results) == 0


# ── Edge cases ───────────────────────────────────────────────────────────


class TestEdgeCases:
    def test_nil_uuid(self):
        nil = uuid.UUID(int=0)
        s = Var()
        results, _ = simple_solutions(_uuid_str_2, nil, s)
        assert len(results) == 1
        assert deref(s) == "00000000-0000-0000-0000-000000000000"

    def test_max_uuid(self):
        max_u = uuid.UUID(int=(1 << 128) - 1)
        s = Var()
        results, _ = simple_solutions(_uuid_str_2, max_u, s)
        assert len(results) == 1
        assert deref(s) == "ffffffff-ffff-ffff-ffff-ffffffffffff"

    def test_nil_uuid_version(self):
        nil = uuid.UUID(int=0)
        v = Var()
        results, _ = simple_solutions(_uuid_version_2, nil, v)
        assert len(results) == 1

    def test_both_unbound_str_fails(self):
        u, s = Var(), Var()
        results, _ = simple_solutions(_uuid_str_2, u, s)
        assert len(results) == 0

    def test_both_unbound_hex_fails(self):
        u, h = Var(), Var()
        results, _ = simple_solutions(_uuid_hex_2, u, h)
        assert len(results) == 0


# ── Inline .clausal integration ──────────────────────────────────────────


class TestClausalInline:
    def test_uuid4_in_clausal(self, tmp_path):
        mod = _load("ui1", 'Test <- (UUIDv4(U_) and IsUUID(U_))\n', tmp_path)
        assert _succeeds("Test", module=mod)

    def test_uuid_str_roundtrip_clausal(self, tmp_path):
        mod = _load("ui2", 'Test <- (UUIDv4(U_) and UUIDStr(U_, S_) and UUIDStr(U2_, S_) and UUIDStr(U2_, S2_) and S_ == S2_)\n', tmp_path)
        assert _succeeds("Test", module=mod)

    def test_uuid3_clausal(self, tmp_path):
        mod = _load("ui3", 'Test <- (UUIDv3("dns", "example.com", U_) and UUIDVersion(U_, 3))\n', tmp_path)
        assert _succeeds("Test", module=mod)

    def test_uuid5_clausal(self, tmp_path):
        mod = _load("ui4", 'Test <- (UUIDv5("url", "test", U_) and UUIDVersion(U_, 5))\n', tmp_path)
        assert _succeeds("Test", module=mod)

    def test_uuid_int_clausal(self, tmp_path):
        mod = _load("ui5", 'Test <- (UUIDv4(U_) and UUIDInt(U_, N_) and UUIDInt(U2_, N_) and UUIDInt(U2_, N2_) and N_ == N2_)\n', tmp_path)
        assert _succeeds("Test", module=mod)

    def test_uuid_hex_clausal(self, tmp_path):
        mod = _load("ui6", 'Test <- (UUIDv4(U_) and UUIDHex(U_, H_) and UUIDHex(U2_, H_) and UUIDHex(U2_, H2_) and H_ == H2_)\n', tmp_path)
        assert _succeeds("Test", module=mod)


# ── .clausal fixture integration ─────────────────────────────────────────


class TestFixtureIntegration:
    """Load the uuid_basic.clausal fixture and run its Test predicates."""

    @pytest.fixture(autouse=True)
    def _load_fixture(self):
        fixture = os.path.join(
            os.path.dirname(__file__), "fixtures", "uuid_basic.clausal"
        )
        mod = _load_module("uuid_basic", fixture)
        self.module = mod.__dict__["$module"]

    @pytest.mark.parametrize("name", [
        "uuid4 generates",
        "uuid1 generates",
        "uuid3 deterministic",
        "uuid5 deterministic",
        "uuid str roundtrip",
        "uuid hex roundtrip",
        "uuid int roundtrip",
        "uuid4 version is 4",
        "uuid3 version is 3",
        "uuid5 version is 5",
        "uuid fields decompose",
    ])
    def test_fixture(self, name):
        assert _succeeds("Test", name, module=self.module), \
            f"Test({name!r}) failed"
