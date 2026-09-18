"""clausal.modules.py.pbkdf2 — PBKDF2 key derivation predicates for Clausal.

Provides relational predicates for PBKDF2-HMAC-SHA256 key derivation.
Import via::

    -import_from(py.pbkdf2, [derive])

Wraps Python's ``hashlib.pbkdf2_hmac``.
"""

from __future__ import annotations

from clausal.modules.py import (
    text_result,   # stage 1: a str result is the chars carrier
    ModulePredicate,
    _import_stdlib,
    expect_type,
    note_mismatch,
    simple_to_trampoline,
    to_bytes,
)
_hashlib = _import_stdlib("hashlib")

from clausal.logic.variables import deref, is_var, unify


# ── Predicate implementations ────────────────────────────────────────────


def _derive_5(password, salt, iterations, key_length, derived_key, trail, k):
    """derive/5: derive(Password, Salt, Iterations, KeyLength, DerivedKey)."""
    pw = deref(password)
    sa = deref(salt)
    it = deref(iterations)
    kl = deref(key_length)
    if any(is_var(x) for x in (pw, sa, it, kl)):
        return
    pw_b = to_bytes(pw)
    sa_b = to_bytes(sa)
    if pw_b is None or sa_b is None:
        expect_type(pw, (str, bytes), "derive/5", arg=1)
        expect_type(sa, (str, bytes), "derive/5", arg=2)
        return
    if not expect_type(it, int, "derive/5", arg=3):
        return
    if it <= 0:
        note_mismatch("derive/5", "was called with iterations <= 0 (argument 3)")
        return
    if not expect_type(kl, int, "derive/5", arg=4):
        return
    if kl <= 0:
        note_mismatch("derive/5", "was called with key length <= 0 (argument 4)")
        return
    dk = _hashlib.pbkdf2_hmac("sha256", pw_b, sa_b, it, dklen=kl)
    if unify(derived_key, text_result(dk.hex()), trail):
        yield None


def _derive_4(password, salt, iterations, derived_key, trail, k):
    """derive/4: default KeyLength=32 bytes."""
    yield from _derive_5(password, salt, iterations, 32, derived_key, trail, k)


# ── Build and export predicate objects ───────────────────────────────────

derive = ModulePredicate("derive")
derive._register(4, simple_to_trampoline(_derive_4))
derive._register(5, simple_to_trampoline(_derive_5))
