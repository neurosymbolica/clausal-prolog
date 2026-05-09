"""Default-pure builtin whitelist.

The bottom-up engine refuses to call predicates from a `-bottom_up` rule body
unless they are pure-monotonic-deterministic. Users mark their own pure
predicates with `pure_/1`. Standard Clausal builtins that satisfy P-M-D are
treated as implicitly pure so users don't have to repeat the obvious.

This list is implementation detail. To make a *user* predicate callable from
a `-bottom_up` body, call `pure_(P/N)` — never mutate this whitelist.
"""

from __future__ import annotations


# (functor_name, arity) pairs. Arity-tolerant entries (no fixed arity, e.g.
# Compare/2 vs Compare/3) appear once per arity, or with arity == -1 to mean
# "all arities are fine".
_DEFAULT_PURE: frozenset[tuple[str, int]] = frozenset({
    # ── Arithmetic & evaluation ──────────────────────────────────────────
    ("is", 2),
    ("succ", 2),
    ("plus", 3),
    ("abs", 2),
    ("sign", 2),
    ("min", 3),
    ("max", 3),
    ("gcd", 3),

    # ── Term-level comparison (structural and arithmetic) ────────────────
    ("==", 2),
    ("!=", 2),
    ("<", 2),
    ("=<", 2),
    ("<=", 2),
    (">", 2),
    (">=", 2),
    ("compare", 3),
    ("structural_eq", 2),
    ("structural_neq", 2),

    # ── Term inspection ──────────────────────────────────────────────────
    ("var", 1),
    ("nonvar", 1),
    ("ground", 1),
    ("atom", 1),
    ("number", 1),
    ("integer", 1),
    ("float", 1),
    ("atomic", 1),
    ("is_list", 1),
    ("functor", 3),
    ("arg", 3),
    ("length", 2),
    ("copy_term", 2),

    # ── Pure list builtins (deterministic modes) ─────────────────────────
    ("member", 2),
    ("memberchk", 2),
    ("append", 3),
    ("nth0", 3),
    ("nth1", 3),
    ("last", 2),
    ("reverse", 2),
    ("msort", 2),
    ("sort", 2),

    # ── Boolean / control flow that's still pure ─────────────────────────
    ("True", 0),
    ("False", 0),
})


def is_default_pure(functor: str, arity: int) -> bool:
    """True if (functor, arity) is in the default-pure whitelist."""
    if (functor, arity) in _DEFAULT_PURE:
        return True
    if (functor, -1) in _DEFAULT_PURE:
        return True
    return False
