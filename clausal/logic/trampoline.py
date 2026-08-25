"""
Generator-based trampoline.

Protocol
--------
Every participating generator yields **tuples** ``(target, value)`` to steer
the trampoline:

  (this_generator, v)  – resume *this* generator with value v
                         (iterative step / tail call — no stack growth)
  (child,          v)  – start a fresh nested computation; the child will
                         eventually yield (parent, result) to resume self
  (parent,         v)  – return v to the calling generator
  (None,           v)  – the root computation is done; v is the final answer

StepGenerator
-------------
A generator cannot normally refer to itself before it is fully constructed.
``StepGenerator`` solves this by acting as a thin wrapper: it is created
*first*, then calls the generator function passing itself as the
``this_generator`` parameter.  The compiled function signature is::

    def pred__N(this_generator, parent, arg0, …, argN, trail):
        …

No bootstrap ``self = yield`` is needed — ``this_generator`` is just a
regular parameter.

A C extension (_trampoline) provides optimised versions of StepGenerator
and trampoline() for production use.  This module is the pure-Python
reference implementation.
"""

from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Generator

# ── Step (legacy) ─────────────────────────────────────────────────────────────
# Kept for backward compatibility with existing compiled code and tests.
# New code should yield plain tuples (gen, value) instead.

@dataclass
class Step:
    """Steering token yielded by every participating generator (legacy)."""
    gen: Generator | None
    value: Any = None


# ── Routing policy + pure-Python twin ────────────────────────────────────────
# The policy functions live with the pure-Python twin and are shared by the
# always-Python drive-loop consumers (runtime/tramp_call.py).
from clausal.logic._trampoline_py import (  # noqa: F401
    _is_routable, _unwind_to_catcher,
)

# ── C extension fast path ────────────────────────────────────────────────────
# _trampoline is a C extension providing optimised DONE, StepGenerator,
# trampoline, solutions and _drive_until_yield.  The pure-Python twin in
# _trampoline_py is the no-build fallback; tests/test_trampoline_parity.py
# runs both against one corpus.
try:
    from clausal.logic.runtime._trampoline import (  # type: ignore[import-untyped]
        DONE, FINAL, StepGenerator, trampoline, solutions, _drive_until_yield,
    )
except ImportError:
    from clausal.logic._trampoline_py import (  # noqa: F401
        DONE, FINAL, StepGenerator, trampoline, solutions, _drive_until_yield,
    )


# ── Minimal test problem: n! ─────────────────────────────────────────────────
#
# Uses all three targets in one small program:
#
#   factorial → validate    (child,  …)   new generator (sub-computation)
#   validate  → factorial   (parent, n)   return to caller
#   factorial → factorial   (self,   n-1) iterative step via trampoline
#   factorial → None        (None,   acc) root computation complete
#
# Trace for factorial(None, 4):
#
#   factorial  →  validate     [child]   validate(4) …
#   validate   →  factorial    [parent]  n = 4
#   factorial  →  factorial    [self]    n = 3, acc = 4
#   factorial  →  factorial    [self]    n = 2, acc = 12
#   factorial  →  factorial    [self]    n = 1, acc = 24
#   factorial  →  None         [done]    return 24

def validate(
    this_generator: StepGenerator,
    proceed: StepGenerator | None,
    fail: StepGenerator | None,
    catcher: StepGenerator | None,
    n: int,
) -> Generator:
    """
    Leaf sub-computation: assert n >= 0, then echo it back to proceed.
    Exists solely to demonstrate the 'new generator' (child) target.
    """
    if n < 0:
        raise ValueError(f"n must be >= 0, got {n}")
    yield (proceed, n)


def factorial(
    this_generator: StepGenerator,
    proceed: StepGenerator | None,
    fail: StepGenerator | None,
    catcher: StepGenerator | None,
    n: int,
) -> Generator:
    """Compute n! while exercising all three targets."""

    # ① (child, …) — delegate to a fresh generator for input validation
    n = yield (StepGenerator(validate, this_generator, this_generator, this_generator, n), None)

    acc = 1
    while n > 1:
        acc *= n
        # ② (this_generator, …) — the trampoline drives the loop; no recursion depth
        n = yield (this_generator, n - 1)

    # ③ (proceed, …) — surface the answer to whoever called us
    yield (proceed, acc)


# ── Tests ────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    cases = [(0, 1), (1, 1), (2, 2), (5, 120), (10, 3_628_800)]
    for n, expected in cases:
        got = trampoline(StepGenerator(factorial, None, None, None, n))
        assert got == expected, f"factorial({n}) → {got}, expected {expected}"
        print(f"factorial({n:>2}) = {got}")

    # Error path through validate
    try:
        trampoline(StepGenerator(factorial, None, None, None, -1))
        assert False, "should have raised"
    except ValueError as exc:
        print(f"Caught expected error: {exc}")

    print("\nAll tests passed.")
