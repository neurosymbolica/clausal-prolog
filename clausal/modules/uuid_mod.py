"""clausal.modules.uuid_mod — UUID predicates for Clausal.

Provides relational predicates for generating, converting, and inspecting
UUIDs.  Import via::

    -import_from(uuid, [UUIDv4, UUIDStr, UUIDVersion, IsUUID])

Or via module import::

    -import_module(uuid)
    # then use uuid.UUIDv4(U_), uuid.UUIDStr(U_, S_), etc.

Python interop
--------------
All predicates produce and consume **real Python uuid.UUID objects**.
Any ``uuid.UUID`` method can be called via ``++()`` interop on the
resulting values.

The module file is named ``uuid_mod.py`` to avoid shadowing Python's
``uuid`` stdlib module.  The ``ModulesFinder`` alias maps the bare
name ``uuid`` to ``uuid_mod``.
"""

from __future__ import annotations

import uuid as _uuid
from typing import Any, Callable

from clausal.logic.variables import Var, deref, is_var, unify
from clausal.logic.trampoline import DONE


# ── Dispatch adapter (same pattern as date_time.py) ───────────────────────


class _UuidPredicate:
    """Adapter with ``_get_dispatch()`` for a uuid predicate."""

    __slots__ = ("_name", "_dispatch_fns")

    def __init__(self, name: str) -> None:
        self._name = name
        self._dispatch_fns: dict[int, Callable] = {}

    def _register(self, arity: int, fn: Callable) -> None:
        self._dispatch_fns[arity] = fn

    def _get_dispatch(self) -> Callable:
        if len(self._dispatch_fns) == 1:
            return next(iter(self._dispatch_fns.values()))
        return self._multi_dispatch

    def _multi_dispatch(self, this_generator, parent, *args):
        arity = len(args) - 1  # exclude trail
        fn = self._dispatch_fns.get(arity)
        if fn is None:
            yield (parent, DONE)
            return
        yield from fn(this_generator, parent, *args)

    def __repr__(self) -> str:
        arities = sorted(self._dispatch_fns)
        return f"uuid.{self._name}/{arities}"


# ── Simple-mode wrapper ──────────────────────────────────────────────────


def _simple_to_trampoline(simple_fn):
    """Wrap a simple-mode fn(*args, trail, k) → trampoline protocol."""
    def trampoline_fn(this_generator, parent, *args):
        for _ in simple_fn(*args, None):
            yield (parent, None)
        yield (parent, DONE)
    return trampoline_fn


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
    if isinstance(ns, str):
        return _NAMESPACE_ALIASES.get(ns.lower())
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
        return
    if is_var(name):
        return
    try:
        result = _uuid.uuid3(namespace, str(name))
    except (TypeError, ValueError):
        return
    if unify(u, result, trail):
        yield None


def _uuid5_3(ns, name, u, trail, k):
    """Uuid5/3: Uuid5(Namespace, Name, UUID) — SHA-1 namespace UUID."""
    ns, name = deref(ns), deref(name)
    namespace = _resolve_namespace(ns)
    if namespace is None:
        return
    if is_var(name):
        return
    try:
        result = _uuid.uuid5(namespace, str(name))
    except (TypeError, ValueError):
        return
    if unify(u, result, trail):
        yield None


# ── Bidirectional conversion predicates ──────────────────────────────────


def _uuid_str_2(u, s, trail, k):
    """UUIDStr/2: bidirectional — UUID ↔ hyphenated string.

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
        except (ValueError, AttributeError):
            return
        if unify(u, val, trail):
            yield None


def _uuid_hex_2(u, h, trail, k):
    """UUIDHex/2: bidirectional — UUID ↔ 32-char hex string.

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
        except (ValueError, AttributeError):
            return
        if unify(u, val, trail):
            yield None


def _uuid_urn_2(u, urn, trail, k):
    """UUIDUrn/2: bidirectional — UUID ↔ URN string.

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
        except (ValueError, AttributeError):
            return
        if unify(u, val, trail):
            yield None


def _uuid_bytes_2(u, b, trail, k):
    """UUIDBytes/2: bidirectional — UUID ↔ 16-byte bytes.

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
        except (ValueError, AttributeError):
            return
        if unify(u, val, trail):
            yield None


def _uuid_int_2(u, n, trail, k):
    """UUIDInt/2: bidirectional — UUID ↔ 128-bit integer.

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
        except (ValueError, OverflowError):
            return
        if unify(u, val, trail):
            yield None


# ── Inspection predicates ────────────────────────────────────────────────


def _uuid_version_2(u, v, trail, k):
    """UUIDVersion/2: UUIDVersion(UUID, Version) — extract version number."""
    u = deref(u)
    if not isinstance(u, _uuid.UUID):
        return
    if unify(v, u.version, trail):
        yield None


def _uuid_fields_7(u, tl, tm, th, csh, csl, node, trail, k):
    """UUIDFields/7: decompose UUID into 6 integer fields.

    UUIDFields(UUID, TimeLow, TimeMid, TimeHiVersion, ClkSeqHi, ClkSeqLo, Node).
    """
    u = deref(u)
    if not isinstance(u, _uuid.UUID):
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
    """IsUUID/1: type test — succeeds if U is a uuid.UUID."""
    u = deref(u)
    if isinstance(u, _uuid.UUID):
        yield None


# ── Build and export predicate objects ───────────────────────────────────

UUIDv4 = _UuidPredicate("UUIDv4")
UUIDv4._register(1, _simple_to_trampoline(_uuid4_1))

UUIDv1 = _UuidPredicate("UUIDv1")
UUIDv1._register(1, _simple_to_trampoline(_uuid1_1))

UUIDv3 = _UuidPredicate("UUIDv3")
UUIDv3._register(3, _simple_to_trampoline(_uuid3_3))

UUIDv5 = _UuidPredicate("UUIDv5")
UUIDv5._register(3, _simple_to_trampoline(_uuid5_3))

UUIDStr = _UuidPredicate("UUIDStr")
UUIDStr._register(2, _simple_to_trampoline(_uuid_str_2))

UUIDHex = _UuidPredicate("UUIDHex")
UUIDHex._register(2, _simple_to_trampoline(_uuid_hex_2))

UUIDUrn = _UuidPredicate("UUIDUrn")
UUIDUrn._register(2, _simple_to_trampoline(_uuid_urn_2))

UUIDBytes = _UuidPredicate("UUIDBytes")
UUIDBytes._register(2, _simple_to_trampoline(_uuid_bytes_2))

UUIDInt = _UuidPredicate("UUIDInt")
UUIDInt._register(2, _simple_to_trampoline(_uuid_int_2))

UUIDVersion = _UuidPredicate("UUIDVersion")
UUIDVersion._register(2, _simple_to_trampoline(_uuid_version_2))

UUIDFields = _UuidPredicate("UUIDFields")
UUIDFields._register(7, _simple_to_trampoline(_uuid_fields_7))

IsUUID = _UuidPredicate("IsUUID")
IsUUID._register(1, _simple_to_trampoline(_is_uuid_1))
