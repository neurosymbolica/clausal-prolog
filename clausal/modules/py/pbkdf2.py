"""clausal.modules.py.pbkdf2 — PBKDF2 key derivation predicates for Clausal.

Provides relational predicates for PBKDF2-HMAC-SHA256 key derivation.
Import via::

    -import_from(py.pbkdf2, [Derive])

Wraps Python's ``hashlib.pbkdf2_hmac``.
"""

from __future__ import annotations

from clausal.modules.py import _import_stdlib
_hashlib = _import_stdlib("hashlib")

from typing import Callable

from clausal.logic.variables import deref, is_var, unify
from clausal.logic.trampoline import DONE


# ── Dispatch adapter ──────────────────────────────────────────────────────


class _Pbkdf2Predicate:
    """Adapter with ``_get_dispatch()`` for a PBKDF2 predicate."""

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
        return f"pbkdf2.{self._name}/{arities}"


def _simple_to_trampoline(simple_fn):
    def trampoline_fn(this_generator, parent, *args):
        for _ in simple_fn(*args, None):
            yield (parent, None)
        yield (parent, DONE)
    return trampoline_fn


# ── Helpers ───────────────────────────────────────────────────────────────


def _to_bytes(val):
    if isinstance(val, str):
        return val.encode("utf-8")
    if isinstance(val, bytes):
        return val
    return None


# ── Predicate implementations ────────────────────────────────────────────


def _derive_5(password, salt, iterations, key_length, derived_key, trail, k):
    """Derive/5: Derive(Password, Salt, Iterations, KeyLength, DerivedKey)."""
    pw = deref(password)
    sa = deref(salt)
    it = deref(iterations)
    kl = deref(key_length)
    if any(is_var(x) for x in (pw, sa, it, kl)):
        return
    pw_b = _to_bytes(pw)
    sa_b = _to_bytes(sa)
    if pw_b is None or sa_b is None:
        return
    if not isinstance(it, int) or it <= 0:
        return
    if not isinstance(kl, int) or kl <= 0:
        return
    dk = _hashlib.pbkdf2_hmac("sha256", pw_b, sa_b, it, dklen=kl)
    if unify(derived_key, dk.hex(), trail):
        yield None


def _derive_4(password, salt, iterations, derived_key, trail, k):
    """Derive/4: default KeyLength=32 bytes."""
    yield from _derive_5(password, salt, iterations, 32, derived_key, trail, k)


# ── Build and export predicate objects ───────────────────────────────────

Derive = _Pbkdf2Predicate("Derive")
Derive._register(4, _simple_to_trampoline(_derive_4))
Derive._register(5, _simple_to_trampoline(_derive_5))
