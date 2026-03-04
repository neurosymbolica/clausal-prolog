"""
Generator-based trampoline.

Protocol
--------
Every participating generator must:
  1. Open with ``self = yield``  — receives its own reference at bootstrap time.
  2. Yield Step objects to steer the trampoline.

Step semantics
--------------
  Step(self,   v)  – resume *this* generator with value v
                     (iterative step / tail call — no stack growth)
  Step(child,  v)  – start a fresh nested computation; the child will
                     eventually yield Step(parent, result) to resume self
  Step(parent, v)  – return v to the calling generator
  Step(None,   v)  – the root computation is done; v is the final answer

Self-reference trick
--------------------
A generator cannot normally refer to itself before it is fully constructed.
The solution used here is a two-phase bootstrap performed by the trampoline:

    next(gen)         # advance execution to the ``self = yield`` suspension
    gen.send(gen)     # inject the generator object as ``self``; run to first Step

No wrapper class, no frame inspection — just one spare yield at the top of
every generator.
"""

from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Generator


# ── Step ──────────────────────────────────────────────────────────────────────

@dataclass
class Step:
    """Steering token yielded by every participating generator."""
    gen: Generator | None   # which generator to resume next (None → done)
    value: Any = None       # argument to send into gen


# ── Trampoline ────────────────────────────────────────────────────────────────

def trampoline(initial_gen: Generator) -> Any:
    """
    Drive a chain of Step-yielding generators without growing the call stack.

    The trampoline keeps a set of already-bootstrapped generator ids so it
    knows whether to run the two-phase bootstrap or a plain send.
    """
    started: set[int] = set()

    def resume(gen: Generator, value: Any) -> Step:
        if id(gen) not in started:
            started.add(id(gen))
            next(gen)               # park at ``self = yield``
            return gen.send(gen)    # inject self-reference → first real Step
        return gen.send(value)

    step = resume(initial_gen, None)
    while step.gen is not None:
        step = resume(step.gen, step.value)
    return step.value


# ── Minimal test problem: n! ──────────────────────────────────────────────────
#
# Uses all three Step targets in one small program:
#
#   factorial → validate    Step(child,  …)   new generator (sub-computation)
#   validate  → factorial   Step(parent, n)   return to caller
#   factorial → factorial   Step(self,   n-1) iterative step via trampoline
#   factorial → None        Step(None,   acc) root computation complete
#
# Trace for factorial(None, 4):
#
#   factorial  →  validate     [child]   validate(4) …
#   validate   →  factorial    [parent]  n = 4
#   factorial  →  factorial    [self]    n = 3, acc = 4
#   factorial  →  factorial    [self]    n = 2, acc = 12
#   factorial  →  factorial    [self]    n = 1, acc = 24
#   factorial  →  None         [done]    return 24

def validate(parent: Generator | None, n: int) -> Generator:
    """
    Leaf sub-computation: assert n >= 0, then echo it back to parent.
    Exists solely to demonstrate the 'new generator' (child) Step.
    """
    self = yield                        # bootstrap hook — receives self
    if n < 0:
        raise ValueError(f"n must be >= 0, got {n}")
    yield Step(parent, n)               # ← Step(parent, …)  return to caller


def factorial(parent: Generator | None, n: int) -> Generator:
    """Compute n! while exercising all three Step targets."""
    self = yield                        # bootstrap hook — receives self

    # ① Step(child, …) — delegate to a fresh generator for input validation
    n = yield Step(validate(self, n), None)

    acc = 1
    while n > 1:
        acc *= n
        # ② Step(self, …) — the trampoline drives the loop; no recursion depth
        n = yield Step(self, n - 1)

    # ③ Step(parent, …) — surface the answer to whoever called us
    yield Step(parent, acc)


# ── Tests ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    cases = [(0, 1), (1, 1), (2, 2), (5, 120), (10, 3_628_800)]
    for n, expected in cases:
        got = trampoline(factorial(None, n))
        assert got == expected, f"factorial({n}) → {got}, expected {expected}"
        print(f"factorial({n:>2}) = {got}")

    # Error path through validate
    try:
        trampoline(factorial(None, -1))
        assert False, "should have raised"
    except ValueError as exc:
        print(f"Caught expected error: {exc}")

    print("\nAll tests passed.")
