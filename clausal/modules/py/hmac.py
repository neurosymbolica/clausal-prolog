"""clausal.modules.py.hmac — HMAC message authentication predicates for Clausal.

Provides relational predicates for HMAC signing and verification.
Import via::

    -import_from(py.hmac, [sign, verify])

Wraps Python's ``hmac`` and ``hashlib`` modules. Default algorithm is SHA-256.
"""

from __future__ import annotations

from clausal.modules.py import (
    text_result,   # stage 1: a str result is the chars carrier
    ModulePredicate,
    _import_stdlib,
    expect_type,
    raise_domain_error,
    require_text,
    simple_to_trampoline,
    to_bytes,
)
_hmac = _import_stdlib("hmac")
_hashlib = _import_stdlib("hashlib")

from clausal.logic.variables import deref, is_var, unify


def _resolve_algo(algo_str):
    """Resolve algorithm string for hmac.new(digestmod=...)."""
    # hmac.new() accepts both a string name and a hashlib constructor.
    # Just pass the string through — hmac handles the lookup internally.
    return algo_str


# ── Predicate implementations ────────────────────────────────────────────


def _sign_4(algorithm, key, data, hex_out, trail, k):
    """sign/4: sign(Algorithm, Key, Data, Hex) — HMAC with specified algorithm."""
    algo_term = deref(algorithm)
    algo = require_text(algo_term, "sign/4", 1)
    key_d = deref(key)
    data_d = deref(data)
    key_b = to_bytes(key_d)
    if key_b is None:
        expect_type(key_d, (str, bytes), "sign/4", arg=2)   # raises
    data_b = to_bytes(data_d)
    if data_b is None:
        expect_type(data_d, (str, bytes), "sign/4", arg=3)   # raises
    digest_mod = _resolve_algo(algo)
    if digest_mod is None:
        return
    try:
        h = _hmac.new(key_b, data_b, digest_mod)
    except ValueError:
        # An unsupported hash name (and shake_*, which needs a length).
        raise_domain_error("hash_algorithm", algo_term, "sign/4", arg=1)
    if unify(hex_out, text_result(h.hexdigest()), trail):
        yield None


def _sign_3(key, data, hex_out, trail, k):
    """sign/3: HMAC-SHA256 (default algorithm)."""
    yield from _sign_4(text_result("sha256"), key, data, hex_out, trail, k)   # stage 1: a module default is text


def _verify_4(algorithm, key, data, hex_in, trail, k):
    """verify/4: verify(Algorithm, Key, Data, Hex) — verify HMAC."""
    algo = deref(algorithm)
    key_d = deref(key)
    data_d = deref(data)
    hex_d = deref(hex_in)
    algo_term = algo
    algo = require_text(algo, "verify/4", 1)
    key_b = to_bytes(key_d)
    if key_b is None:
        expect_type(key_d, (str, bytes), "verify/4", arg=2)   # raises
    data_b = to_bytes(data_d)
    if data_b is None:
        expect_type(data_d, (str, bytes), "verify/4", arg=3)   # raises
    hex_d = require_text(hex_d, "verify/4", 4)
    digest_mod = _resolve_algo(algo)
    if digest_mod is None:
        return
    try:
        h = _hmac.new(key_b, data_b, digest_mod)
    except ValueError:
        # An unsupported hash name (and shake_*, which needs a length).
        raise_domain_error("hash_algorithm", algo_term, "verify/4", arg=1)
    if _hmac.compare_digest(h.hexdigest(), hex_d):
        yield None


def _verify_3(key, data, hex_in, trail, k):
    """verify/3: verify HMAC-SHA256."""
    yield from _verify_4(text_result("sha256"), key, data, hex_in, trail, k)


# ── Build and export predicate objects ───────────────────────────────────

sign = ModulePredicate("sign")
sign._register(3, simple_to_trampoline(_sign_3))
sign._register(4, simple_to_trampoline(_sign_4))

verify = ModulePredicate("verify")
verify._register(3, simple_to_trampoline(_verify_3))
verify._register(4, simple_to_trampoline(_verify_4))
