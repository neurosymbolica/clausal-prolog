"""clausal.modules.py.hash — Cryptographic hashing predicates for Clausal.

Provides relational predicates for computing cryptographic hashes.
Import via::

    -import_from(py.hash, [hash, hash_bytes])

Or via module import::

    -import_module(py.hash)

Wraps Python's ``hashlib`` module. Supported algorithms include
``sha256``, ``sha512``, ``md5``, ``sha1``, ``sha384``, ``sha3_256``,
``sha3_512``, ``blake2b``, ``blake2s``.
"""

from __future__ import annotations

from clausal.modules.py import _import_stdlib, ModulePredicate, simple_to_trampoline, to_bytes
_hashlib = _import_stdlib("hashlib")

from clausal.logic.variables import deref, is_var, unify


# ── Predicate implementations ────────────────────────────────────────────


def _hash_3(algorithm, data, hex_out, trail, k):
    """hash/3: hash(Algorithm, Data, Hex) — compute hex digest."""
    algo = deref(algorithm)
    data_d = deref(data)
    if is_var(algo) or not isinstance(algo, str):
        return
    if is_var(data_d):
        return
    data_bytes = to_bytes(data_d)
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
    """hash_bytes/3: hash_bytes(Algorithm, Data, Bytes) — compute raw digest bytes."""
    algo = deref(algorithm)
    data_d = deref(data)
    if is_var(algo) or not isinstance(algo, str):
        return
    if is_var(data_d):
        return
    data_bytes = to_bytes(data_d)
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

hash = ModulePredicate("hash")
hash._register(3, simple_to_trampoline(_hash_3))

hash_bytes = ModulePredicate("hash_bytes")
hash_bytes._register(3, simple_to_trampoline(_hash_bytes_3))
