"""clausal.modules.py.pbkdf2 — PBKDF2 key derivation predicates for Clausal.

Provides relational predicates for PBKDF2-HMAC-SHA256 key derivation.
Import via::

    -import_from(py.pbkdf2, [derive])

Wraps Python's ``hashlib.pbkdf2_hmac``.
"""

from __future__ import annotations

from clausal.modules.py import _import_stdlib, ModulePredicate, simple_to_trampoline, to_bytes
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
        return
    if not isinstance(it, int) or it <= 0:
        return
    if not isinstance(kl, int) or kl <= 0:
        return
    dk = _hashlib.pbkdf2_hmac("sha256", pw_b, sa_b, it, dklen=kl)
    if unify(derived_key, dk.hex(), trail):
        yield None


def _derive_4(password, salt, iterations, derived_key, trail, k):
    """derive/4: default KeyLength=32 bytes."""
    yield from _derive_5(password, salt, iterations, 32, derived_key, trail, k)


# ── Build and export predicate objects ───────────────────────────────────

derive = ModulePredicate("derive")
derive._register(4, simple_to_trampoline(_derive_4))
derive._register(5, simple_to_trampoline(_derive_5))
