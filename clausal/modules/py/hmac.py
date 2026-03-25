"""clausal.modules.py.hmac — HMAC message authentication predicates for Clausal.

Provides relational predicates for HMAC signing and verification.
Import via::

    -import_from(py.hmac, [Sign, Verify])

Wraps Python's ``hmac`` and ``hashlib`` modules. Default algorithm is SHA-256.
"""

from __future__ import annotations

from clausal.modules.py import _import_stdlib
_hmac = _import_stdlib("hmac")
_hashlib = _import_stdlib("hashlib")

from typing import Callable

from clausal.logic.variables import deref, is_var, unify
from clausal.logic.trampoline import DONE


# ── Dispatch adapter ──────────────────────────────────────────────────────


class _HmacPredicate:
    """Adapter with ``_get_dispatch()`` for an HMAC predicate."""

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
        return f"hmac.{self._name}/{arities}"


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


def _resolve_algo(algo_str):
    """Resolve algorithm string to hashlib constructor or None."""
    try:
        return getattr(_hashlib, algo_str, None) or algo_str
    except (TypeError, AttributeError):
        return None


# ── Predicate implementations ────────────────────────────────────────────


def _sign_4(algorithm, key, data, hex_out, trail, k):
    """Sign/4: Sign(Algorithm, Key, Data, Hex) — HMAC with specified algorithm."""
    algo = deref(algorithm)
    key_d = deref(key)
    data_d = deref(data)
    if is_var(algo) or not isinstance(algo, str):
        return
    if is_var(key_d) or is_var(data_d):
        return
    key_b = _to_bytes(key_d)
    data_b = _to_bytes(data_d)
    if key_b is None or data_b is None:
        return
    digest_mod = _resolve_algo(algo)
    if digest_mod is None:
        return
    try:
        h = _hmac.new(key_b, data_b, digest_mod)
    except (ValueError, AttributeError):
        return
    if unify(hex_out, h.hexdigest(), trail):
        yield None


def _sign_3(key, data, hex_out, trail, k):
    """Sign/3: HMAC-SHA256 (default algorithm)."""
    yield from _sign_4("sha256", key, data, hex_out, trail, k)


def _verify_4(algorithm, key, data, hex_in, trail, k):
    """Verify/4: Verify(Algorithm, Key, Data, Hex) — verify HMAC."""
    algo = deref(algorithm)
    key_d = deref(key)
    data_d = deref(data)
    hex_d = deref(hex_in)
    if any(is_var(x) for x in (algo, key_d, data_d, hex_d)):
        return
    if not isinstance(algo, str) or not isinstance(hex_d, str):
        return
    key_b = _to_bytes(key_d)
    data_b = _to_bytes(data_d)
    if key_b is None or data_b is None:
        return
    digest_mod = _resolve_algo(algo)
    if digest_mod is None:
        return
    try:
        h = _hmac.new(key_b, data_b, digest_mod)
    except (ValueError, AttributeError):
        return
    if _hmac.compare_digest(h.hexdigest(), hex_d):
        yield None


def _verify_3(key, data, hex_in, trail, k):
    """Verify/3: verify HMAC-SHA256."""
    yield from _verify_4("sha256", key, data, hex_in, trail, k)


# ── Build and export predicate objects ───────────────────────────────────

Sign = _HmacPredicate("Sign")
Sign._register(3, _simple_to_trampoline(_sign_3))
Sign._register(4, _simple_to_trampoline(_sign_4))

Verify = _HmacPredicate("Verify")
Verify._register(3, _simple_to_trampoline(_verify_3))
Verify._register(4, _simple_to_trampoline(_verify_4))
