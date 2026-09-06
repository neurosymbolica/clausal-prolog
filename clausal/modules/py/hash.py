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

from clausal.modules.py import (
    ModulePredicate,
    _import_stdlib,
    expect_type,
    note_rejected_call,
    simple_to_trampoline,
    to_bytes,
    to_text,
)
_hashlib = _import_stdlib("hashlib")

from clausal.logic.variables import deref, is_var, unify


# ── Helper ───────────────────────────────────────────────────────────────


def _algo_text(val, pred):
    """The ``str`` an algorithm NAME denotes, or ``None`` (note recorded).

    Spec §9.1/§9.4: a hash algorithm name is a literal handed to a library,
    which is a text position -- ``hash(sha256, D, H)``, ``hash('sha256', …)``
    and (in the default ``-double_quotes(atom)`` mode) ``hash("sha256", …)``
    all name the same ``hashlib`` constructor.  THE FLIP
    (2026-09-06-atoms-as-cells-strings) made the bare
    ``expect_type(algo, str, …)`` guard reject every source-written name,
    silently.

    A bound value that is not text keeps this module's existing behaviour --
    a recorded type-mismatch note and a clean failure, not a raise.
    """
    text = to_text(val)
    if text is not None:
        return text
    expect_type(val, str, pred, arg=1)   # records the note; always False here
    return None


# ── Predicate implementations ────────────────────────────────────────────


def _hash_3(algorithm, data, hex_out, trail, k):
    """hash/3: hash(Algorithm, Data, Hex) — compute hex digest."""
    algo = _algo_text(deref(algorithm), "hash/3")
    data_d = deref(data)
    if algo is None:
        return
    if is_var(data_d):
        return
    data_bytes = to_bytes(data_d)
    if data_bytes is None:
        expect_type(data_d, (str, bytes), "hash/3", arg=2)
        return
    try:
        h = _hashlib.new(algo)
    except ValueError as exc:  # unknown algorithm
        note_rejected_call("hash/3", exc)
        return
    h.update(data_bytes)
    try:
        digest = h.hexdigest()  # TypeError: shake_* needs a length (F019)
    except TypeError as exc:
        note_rejected_call("hash/3", exc)
        return
    if unify(hex_out, digest, trail):
        yield None


def _hash_bytes_3(algorithm, data, bytes_out, trail, k):
    """hash_bytes/3: hash_bytes(Algorithm, Data, Bytes) — compute raw digest bytes."""
    algo = _algo_text(deref(algorithm), "hash_bytes/3")
    data_d = deref(data)
    if algo is None:
        return
    if is_var(data_d):
        return
    data_bytes = to_bytes(data_d)
    if data_bytes is None:
        expect_type(data_d, (str, bytes), "hash_bytes/3", arg=2)
        return
    try:
        h = _hashlib.new(algo)
    except ValueError as exc:  # unknown algorithm
        note_rejected_call("hash_bytes/3", exc)
        return
    h.update(data_bytes)
    try:
        digest = h.digest()  # TypeError: shake_* needs a length (F019)
    except TypeError as exc:
        note_rejected_call("hash_bytes/3", exc)
        return
    if unify(bytes_out, digest, trail):
        yield None


# ── Build and export predicate objects ───────────────────────────────────

hash = ModulePredicate("hash")
hash._register(3, simple_to_trampoline(_hash_3))

hash_bytes = ModulePredicate("hash_bytes")
hash_bytes._register(3, simple_to_trampoline(_hash_bytes_3))
