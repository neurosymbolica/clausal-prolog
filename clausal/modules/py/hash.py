"""clausal.modules.py.hash — Cryptographic hashing predicates for Clausal.

Provides relational predicates for computing cryptographic hashes.
Import via::

    -import_from(py.hash, [Hash, HashBytes])

Or via module import::

    -import_module(py.hash)

Wraps Python's ``hashlib`` module. Supported algorithms include
``sha256``, ``sha512``, ``md5``, ``sha1``, ``sha384``, ``sha3_256``,
``sha3_512``, ``blake2b``, ``blake2s``.
"""

from __future__ import annotations

from clausal.modules.py import _import_stdlib
_hashlib = _import_stdlib("hashlib")

from typing import Callable

from clausal.logic.variables import deref, is_var, unify
from clausal.logic.trampoline import DONE


# ── Dispatch adapter ──────────────────────────────────────────────────────


class _HashPredicate:
    """Adapter with ``_get_dispatch()`` for a hash predicate."""

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
        return f"hash.{self._name}/{arities}"


# ── Simple-to-trampoline wrapper ─────────────────────────────────────────


def _simple_to_trampoline(simple_fn):
    """Wrap a simple-mode fn(*args, trail, k) → trampoline protocol."""
    def trampoline_fn(this_generator, parent, *args):
        for _ in simple_fn(*args, None):
            yield (parent, None)
        yield (parent, DONE)
    return trampoline_fn


# ── Helpers ───────────────────────────────────────────────────────────────


def _to_bytes(val):
    """Convert string or bytes to bytes, or return None."""
    if isinstance(val, str):
        return val.encode("utf-8")
    if isinstance(val, bytes):
        return val
    return None


# ── Predicate implementations ────────────────────────────────────────────


def _hash_3(algorithm, data, hex_out, trail, k):
    """Hash/3: Hash(Algorithm, Data, Hex) — compute hex digest."""
    algo = deref(algorithm)
    data_d = deref(data)
    if is_var(algo) or not isinstance(algo, str):
        return
    if is_var(data_d):
        return
    data_bytes = _to_bytes(data_d)
    if data_bytes is None:
        return
    try:
        h = _hashlib.new(algo)
    except ValueError:
        return  # unknown algorithm
    h.update(data_bytes)
    if unify(hex_out, h.hexdigest(), trail):
        yield None


def _hash_bytes_3(algorithm, data, bytes_out, trail, k):
    """HashBytes/3: HashBytes(Algorithm, Data, Bytes) — compute raw digest bytes."""
    algo = deref(algorithm)
    data_d = deref(data)
    if is_var(algo) or not isinstance(algo, str):
        return
    if is_var(data_d):
        return
    data_bytes = _to_bytes(data_d)
    if data_bytes is None:
        return
    try:
        h = _hashlib.new(algo)
    except ValueError:
        return
    h.update(data_bytes)
    if unify(bytes_out, h.digest(), trail):
        yield None


# ── Build and export predicate objects ───────────────────────────────────

Hash = _HashPredicate("Hash")
Hash._register(3, _simple_to_trampoline(_hash_3))

HashBytes = _HashPredicate("HashBytes")
HashBytes._register(3, _simple_to_trampoline(_hash_bytes_3))
