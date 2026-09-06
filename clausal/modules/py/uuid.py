"""clausal.modules.py.uuid — UUID predicates for Clausal.

Provides relational predicates for generating, converting, and inspecting
UUIDs.  Import via::

    -import_from(py.uuid, [uuid_v4, uuid_str, uuid_version, is_uuid])

Or via module import::

    -import_module(py.uuid)
    # then use py.uuid.uuid_v4(U_), py.uuid.uuid_str(U_, S_), etc.

Python interop
--------------
All predicates produce and consume **real Python uuid.UUID objects**.
Any ``uuid.UUID`` method can be called via ``++()`` interop on the
resulting values.
"""

from __future__ import annotations

from clausal.modules.py import (
    ModulePredicate,
    _import_stdlib,
    expect_type,
    note_mismatch,
    note_rejected_call,
    simple_to_trampoline,
    to_text,
)
_uuid = _import_stdlib("uuid")


from typing import Any

from clausal.logic.variables import Var, deref, is_var, unify


def _name_text(val) -> str:
    """The ``str`` a UUID name argument denotes.

    Text is a string or an ATOM, and both convert to the same ``str``
    (spec §9.4).

    THE FLIP (2026-09-06-atoms-as-cells-strings): ``str()`` on the arity-0
    cell ``("bar",)`` is the Python tuple repr ``"('bar',)"``, so every text
    coercion in a wrapper routes through ``to_text`` instead.  A term that is
    not text keeps the old ``str`` fallback -- this position never promised a
    type contract.
    """
    text = to_text(val)
    return text if text is not None else str(val)



# ── Namespace resolver ───────────────────────────────────────────────────

_NAMESPACE_ALIASES = {
    "dns": _uuid.NAMESPACE_DNS,
    "url": _uuid.NAMESPACE_URL,
    "oid": _uuid.NAMESPACE_OID,
    "x500": _uuid.NAMESPACE_X500,
}


def _resolve_namespace(ns):
    """Resolve a namespace argument to a uuid.UUID.

    Accepts string aliases ("dns", "url", "oid", "x500") or a raw
    uuid.UUID instance.  Returns None on failure.
    """
    if isinstance(ns, _uuid.UUID):
        return ns
    # Spec §9.4: the alias is TEXT -- a string or an ATOM (``dns`` written
    # bare, or ``"dns"`` in the default ``-double_quotes(atom)`` mode).
    text = to_text(ns)
    if text is not None:
        return _NAMESPACE_ALIASES.get(text.lower())
    return None


# ── Generation predicates ────────────────────────────────────────────────


def _uuid4_1(u, trail, k):
    """Uuid4/1: bind u to a random v4 UUID."""
    if unify(u, _uuid.uuid4(), trail):
        yield None


def _uuid1_1(u, trail, k):
    """Uuid1/1: bind u to a time-based v1 UUID."""
    if unify(u, _uuid.uuid1(), trail):
        yield None


def _uuid3_3(ns, name, u, trail, k):
    """Uuid3/3: Uuid3(Namespace, Name, UUID) — MD5 namespace UUID."""
    ns, name = deref(ns), deref(name)
    namespace = _resolve_namespace(ns)
    if namespace is None:
        if not is_var(ns):
            note_mismatch(
                "uuid_v3/3",
                f"was called with {ns!r} where a uuid.UUID or a namespace "
                'alias "dns", "url", "oid" or "x500" is required (argument 1)',
            )
        return
    if is_var(name):
        return
    try:
        result = _uuid.uuid3(namespace, _name_text(name))
    except (TypeError, ValueError) as exc:
        note_rejected_call("uuid_v3/3", exc)
        return
    if unify(u, result, trail):
        yield None


def _uuid5_3(ns, name, u, trail, k):
    """Uuid5/3: Uuid5(Namespace, Name, UUID) — SHA-1 namespace UUID."""
    ns, name = deref(ns), deref(name)
    namespace = _resolve_namespace(ns)
    if namespace is None:
        if not is_var(ns):
            note_mismatch(
                "uuid_v5/3",
                f"was called with {ns!r} where a uuid.UUID or a namespace "
                'alias "dns", "url", "oid" or "x500" is required (argument 1)',
            )
        return
    if is_var(name):
        return
    try:
        result = _uuid.uuid5(namespace, _name_text(name))
    except (TypeError, ValueError) as exc:
        note_rejected_call("uuid_v5/3", exc)
        return
    if unify(u, result, trail):
        yield None


# ── Bidirectional conversion predicates ──────────────────────────────────


def _uuid_str_2(u, s, trail, k):
    """uuid_str/2: bidirectional — UUID ↔ hyphenated string.

    If U is ground UUID: decompose → S = str(U).
    If S is ground string: construct → U = uuid.UUID(S).
    """
    u, s = deref(u), deref(s)
    if isinstance(u, _uuid.UUID):
        if unify(s, str(u), trail):
            yield None
    elif isinstance(s, str) and not is_var(s):
        try:
            val = _uuid.UUID(s)
        except (ValueError, AttributeError) as exc:
            note_rejected_call("uuid_str/2", exc)
            return
        if unify(u, val, trail):
            yield None
    elif not is_var(u):
        expect_type(u, _uuid.UUID, "uuid_str/2", arg=1)
    else:
        expect_type(s, str, "uuid_str/2", arg=2)


def _uuid_hex_2(u, h, trail, k):
    """uuid_hex/2: bidirectional — UUID ↔ 32-char hex string.

    If U is ground UUID: decompose → H = U.hex.
    If H is ground string: construct → U = uuid.UUID(hex=H).
    """
    u, h = deref(u), deref(h)
    if isinstance(u, _uuid.UUID):
        if unify(h, u.hex, trail):
            yield None
    elif isinstance(h, str) and not is_var(h):
        try:
            val = _uuid.UUID(hex=h)
        except (ValueError, AttributeError) as exc:
            note_rejected_call("uuid_hex/2", exc)
            return
        if unify(u, val, trail):
            yield None
    elif not is_var(u):
        expect_type(u, _uuid.UUID, "uuid_hex/2", arg=1)
    else:
        expect_type(h, str, "uuid_hex/2", arg=2)


def _uuid_urn_2(u, urn, trail, k):
    """uuid_urn/2: bidirectional — UUID ↔ URN string.

    If U is ground UUID: decompose → Urn = U.urn.
    If Urn is ground string: construct → U from URN.
    """
    u, urn = deref(u), deref(urn)
    if isinstance(u, _uuid.UUID):
        if unify(urn, u.urn, trail):
            yield None
    elif isinstance(urn, str) and not is_var(urn):
        try:
            val = _uuid.UUID(urn)
        except (ValueError, AttributeError) as exc:
            note_rejected_call("uuid_urn/2", exc)
            return
        if unify(u, val, trail):
            yield None
    elif not is_var(u):
        expect_type(u, _uuid.UUID, "uuid_urn/2", arg=1)
    else:
        expect_type(urn, str, "uuid_urn/2", arg=2)


def _uuid_bytes_2(u, b, trail, k):
    """uuid_bytes/2: bidirectional — UUID ↔ 16-byte bytes.

    If U is ground UUID: decompose → B = U.bytes.
    If B is ground bytes: construct → U = uuid.UUID(bytes=B).
    """
    u, b = deref(u), deref(b)
    if isinstance(u, _uuid.UUID):
        if unify(b, u.bytes, trail):
            yield None
    elif isinstance(b, bytes) and not is_var(b):
        try:
            val = _uuid.UUID(bytes=b)
        except (ValueError, AttributeError) as exc:
            note_rejected_call("uuid_bytes/2", exc)
            return
        if unify(u, val, trail):
            yield None
    elif not is_var(u):
        expect_type(u, _uuid.UUID, "uuid_bytes/2", arg=1)
    else:
        expect_type(b, bytes, "uuid_bytes/2", arg=2)


def _uuid_int_2(u, n, trail, k):
    """uuid_int/2: bidirectional — UUID ↔ 128-bit integer.

    If U is ground UUID: decompose → N = U.int.
    If N is ground int: construct → U = uuid.UUID(int=N).
    """
    u, n = deref(u), deref(n)
    if isinstance(u, _uuid.UUID):
        if unify(n, u.int, trail):
            yield None
    elif isinstance(n, int) and not is_var(n):
        try:
            val = _uuid.UUID(int=n)
        except (ValueError, OverflowError) as exc:
            note_rejected_call("uuid_int/2", exc)
            return
        if unify(u, val, trail):
            yield None
    elif not is_var(u):
        expect_type(u, _uuid.UUID, "uuid_int/2", arg=1)
    else:
        expect_type(n, int, "uuid_int/2", arg=2)


# ── Inspection predicates ────────────────────────────────────────────────


def _uuid_version_2(u, v, trail, k):
    """uuid_version/2: uuid_version(UUID, Version) — extract version number."""
    u = deref(u)
    if not expect_type(u, _uuid.UUID, "uuid_version/2", arg=1):
        return
    if unify(v, u.version, trail):
        yield None


def _uuid_fields_7(u, tl, tm, th, csh, csl, node, trail, k):
    """uuid_fields/7: decompose UUID into 6 integer fields.

    uuid_fields(UUID, TimeLow, TimeMid, TimeHiVersion, ClkSeqHi, ClkSeqLo, Node).
    """
    u = deref(u)
    if not expect_type(u, _uuid.UUID, "uuid_fields/7", arg=1):
        return
    fields = u.fields  # (time_low, time_mid, time_hi_version, clock_seq_hi, clock_seq_lo, node)
    mark = trail.mark()
    if (unify(tl, fields[0], trail)
            and unify(tm, fields[1], trail)
            and unify(th, fields[2], trail)
            and unify(csh, fields[3], trail)
            and unify(csl, fields[4], trail)
            and unify(node, fields[5], trail)):
        yield None
    else:
        trail.undo(mark)


def _is_uuid_1(u, trail, k):
    """is_uuid/1: type test — succeeds if U is a uuid.UUID."""
    u = deref(u)
    if isinstance(u, _uuid.UUID):
        yield None


# ── Build and export predicate objects ───────────────────────────────────

uuid_v4 = ModulePredicate("uuid_v4")
uuid_v4._register(1, simple_to_trampoline(_uuid4_1))

uuid_v1 = ModulePredicate("uuid_v1")
uuid_v1._register(1, simple_to_trampoline(_uuid1_1))

uuid_v3 = ModulePredicate("uuid_v3")
uuid_v3._register(3, simple_to_trampoline(_uuid3_3))

uuid_v5 = ModulePredicate("uuid_v5")
uuid_v5._register(3, simple_to_trampoline(_uuid5_3))

uuid_str = ModulePredicate("uuid_str")
uuid_str._register(2, simple_to_trampoline(_uuid_str_2))

uuid_hex = ModulePredicate("uuid_hex")
uuid_hex._register(2, simple_to_trampoline(_uuid_hex_2))

uuid_urn = ModulePredicate("uuid_urn")
uuid_urn._register(2, simple_to_trampoline(_uuid_urn_2))

uuid_bytes = ModulePredicate("uuid_bytes")
uuid_bytes._register(2, simple_to_trampoline(_uuid_bytes_2))

uuid_int = ModulePredicate("uuid_int")
uuid_int._register(2, simple_to_trampoline(_uuid_int_2))

uuid_version = ModulePredicate("uuid_version")
uuid_version._register(2, simple_to_trampoline(_uuid_version_2))

uuid_fields = ModulePredicate("uuid_fields")
uuid_fields._register(7, simple_to_trampoline(_uuid_fields_7))

is_uuid = ModulePredicate("is_uuid")
is_uuid._register(1, simple_to_trampoline(_is_uuid_1))
