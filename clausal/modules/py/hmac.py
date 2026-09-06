"""clausal.modules.py.hmac — HMAC message authentication predicates for Clausal.

Provides relational predicates for HMAC signing and verification.
Import via::

    -import_from(py.hmac, [sign, verify])

Wraps Python's ``hmac`` and ``hashlib`` modules. Default algorithm is SHA-256.
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
_hmac = _import_stdlib("hmac")
_hashlib = _import_stdlib("hashlib")

from clausal.logic.variables import deref, is_var, unify


def _resolve_algo(algo_str):
    """Resolve algorithm string for hmac.new(digestmod=...)."""
    # hmac.new() accepts both a string name and a hashlib constructor.
    # Just pass the string through — hmac handles the lookup internally.
    return algo_str


def _require_text(val, pred, arg):
    """The ``str`` an algorithm NAME or a hex DIGEST denotes, or ``None``.

    Spec §9.1/§9.4: a hash algorithm name is a literal handed to a library and
    a hex digest is text a program compares against a literal it wrote -- in
    the default ``-double_quotes(atom)`` mode both of those literals are
    ATOMS, so the bare ``expect_type(x, str, …)`` guards rejected every
    source-written call, silently.

    A bound value that is not text keeps this module's existing behaviour --
    a recorded type-mismatch note and a clean failure, not a raise.
    """
    text = to_text(val)
    if text is not None:
        return text
    expect_type(val, str, pred, arg=arg)   # records the note; always False here
    return None


# ── Predicate implementations ────────────────────────────────────────────


def _sign_4(algorithm, key, data, hex_out, trail, k):
    """sign/4: sign(Algorithm, Key, Data, Hex) — HMAC with specified algorithm."""
    algo = _require_text(deref(algorithm), "sign/4", 1)
    key_d = deref(key)
    data_d = deref(data)
    if algo is None:
        return
    if is_var(key_d) or is_var(data_d):
        return
    key_b = to_bytes(key_d)
    data_b = to_bytes(data_d)
    if key_b is None or data_b is None:
        expect_type(key_d, (str, bytes), "sign/4", arg=2)
        expect_type(data_d, (str, bytes), "sign/4", arg=3)
        return
    digest_mod = _resolve_algo(algo)
    if digest_mod is None:
        return
    try:
        h = _hmac.new(key_b, data_b, digest_mod)
    except (ValueError, AttributeError) as exc:
        # Both are argument-shaped: ValueError for an unsupported hash
        # name, AttributeError for a digestmod without the hash protocol.
        note_rejected_call("sign/4", exc)
        return
    if unify(hex_out, h.hexdigest(), trail):
        yield None


def _sign_3(key, data, hex_out, trail, k):
    """sign/3: HMAC-SHA256 (default algorithm)."""
    yield from _sign_4("sha256", key, data, hex_out, trail, k)


def _verify_4(algorithm, key, data, hex_in, trail, k):
    """verify/4: verify(Algorithm, Key, Data, Hex) — verify HMAC."""
    algo = deref(algorithm)
    key_d = deref(key)
    data_d = deref(data)
    hex_d = deref(hex_in)
    if any(is_var(x) for x in (algo, key_d, data_d, hex_d)):
        return
    algo = _require_text(algo, "verify/4", 1)
    hex_d = _require_text(hex_d, "verify/4", 4)
    if algo is None or hex_d is None:
        return
    key_b = to_bytes(key_d)
    data_b = to_bytes(data_d)
    if key_b is None or data_b is None:
        expect_type(key_d, (str, bytes), "verify/4", arg=2)
        expect_type(data_d, (str, bytes), "verify/4", arg=3)
        return
    digest_mod = _resolve_algo(algo)
    if digest_mod is None:
        return
    try:
        h = _hmac.new(key_b, data_b, digest_mod)
    except (ValueError, AttributeError) as exc:
        # Both are argument-shaped: ValueError for an unsupported hash
        # name, AttributeError for a digestmod without the hash protocol.
        note_rejected_call("verify/4", exc)
        return
    if _hmac.compare_digest(h.hexdigest(), hex_d):
        yield None


def _verify_3(key, data, hex_in, trail, k):
    """verify/3: verify HMAC-SHA256."""
    yield from _verify_4("sha256", key, data, hex_in, trail, k)


# ── Build and export predicate objects ───────────────────────────────────

sign = ModulePredicate("sign")
sign._register(3, simple_to_trampoline(_sign_3))
sign._register(4, simple_to_trampoline(_sign_4))

verify = ModulePredicate("verify")
verify._register(3, simple_to_trampoline(_verify_3))
verify._register(4, simple_to_trampoline(_verify_4))
