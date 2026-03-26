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
from typing import Any, Callable, Generator

# ── Step (legacy) ─────────────────────────────────────────────────────────────
# Kept for backward compatibility with existing compiled code and tests.
# New code should yield plain tuples (gen, value) instead.

@dataclass
class Step:
    """Steering token yielded by every participating generator (legacy)."""
    gen: Generator | None
    value: Any = None


# ── C extension fast path ────────────────────────────────────────────────────
# _trampoline is a C extension providing optimised DONE, StepGenerator,
# trampoline, and solutions.  Fall back to pure-Python implementations below.

try:
    from clausal.logic._trampoline import DONE, StepGenerator, trampoline, solutions  # type: ignore[import-untyped]
except ImportError:
    # ── DONE sentinel ─────────────────────────────────────────────────────
    DONE: object = object()

    # ── StepGenerator ─────────────────────────────────────────────────────

    class StepGenerator:  # type: ignore[no-redef]
        """Wraps a generator function, providing ``this_generator`` automatically.

        Usage::

            sg = StepGenerator(pred_fn, parent, arg0, arg1, trail)

        This calls ``pred_fn(sg, parent, arg0, arg1, trail)`` internally, so the
        generator body receives ``sg`` as its ``this_generator`` parameter.

        ``send(value)`` handles first-call bootstrapping transparently:
        the first call does ``next(inner_gen)``; subsequent calls delegate to
        ``inner_gen.send(value)``.
        """
        __slots__ = ('_gen', '_started', 'parent')

        def __init__(self, func: Callable, *args: Any) -> None:
            self.parent = args[0] if args else None  # first arg is always parent
            self._gen: Generator = func(self, *args)
            self._started: bool = False

        def send(self, value: Any) -> tuple:
            if self._started:
                return self._gen.send(value)
            self._started = True
            return next(self._gen)

        def throw(self, *args: Any) -> tuple:
            return self._gen.throw(*args)

        def close(self) -> None:
            self._gen.close()

    # ── Trampoline ────────────────────────────────────────────────────────

    def trampoline(root: StepGenerator) -> Any:  # type: ignore[no-redef]
        """
        Drive a chain of tuple-yielding generators without growing the call stack.

        Each generator yields ``(target, value)`` tuples.  The trampoline loop is
        just::

            step = root.send(None)
            while step[0] is not None:
                step = step[0].send(step[1])
            return step[1]

        No ``started`` set, no ``resume`` helper — StepGenerator handles
        bootstrapping internally.

        LogicException routing: when a generator raises LogicException, the
        throwing generator is dead (its try/finally already ran trail.undo).
        We unwind through the parent chain using .throw() until a catch/3
        handler catches it.
        """
        from clausal.logic.exceptions import LogicException

        gen, value = root.send(None)
        while gen is not None:
            try:
                gen, value = gen.send(value)
            except LogicException as exc:
                target = gen.parent if hasattr(gen, 'parent') else None
                while target is not None:
                    try:
                        gen, value = target.throw(exc)
                        break  # parent caught it — resume normal trampoline
                    except LogicException:
                        target = target.parent if hasattr(target, 'parent') else None
                else:
                    raise exc  # uncaught — surface to Python
        return value

    def solutions(root: StepGenerator, snapshot: Callable | None = None) -> list:  # type: ignore[no-redef]
        """Collect all solution values from *root* until DONE.

        If *snapshot* is provided, it is called while bindings are live
        and its return value is collected instead of the raw solution value.

        Handles SLG tabling: ``_TABLING_SUSPEND`` is intercepted and converted
        to DONE so the parent's while-loop exits normally.  The consumer
        generator remains saved in the table entry's suspended list for later
        resumption by the leader's completion phase.

        LogicException routing: same as trampoline() — unwind through parent
        chain via .throw() until caught or surface to Python.
        """
        from clausal.logic.tabling import _TABLING_SUSPEND
        from clausal.logic.exceptions import LogicException

        results: list = []
        gen, value = root.send(None)
        while True:
            if gen is None:
                if value is DONE:
                    return results
                results.append(snapshot() if snapshot is not None else value)
                gen, value = root.send(None)
            else:
                try:
                    # Intercept _TABLING_SUSPEND → send DONE to parent instead
                    if value is _TABLING_SUSPEND:
                        gen, value = gen.send(DONE)
                    else:
                        gen, value = gen.send(value)
                except LogicException as exc:
                    target = gen.parent if hasattr(gen, 'parent') else None
                    while target is not None:
                        try:
                            gen, value = target.throw(type(exc), exc)
                            break
                        except LogicException:
                            target = target.parent if hasattr(target, 'parent') else None
                    else:
                        raise exc


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

def validate(this_generator: StepGenerator, parent: StepGenerator | None, n: int) -> Generator:
    """
    Leaf sub-computation: assert n >= 0, then echo it back to parent.
    Exists solely to demonstrate the 'new generator' (child) target.
    """
    if n < 0:
        raise ValueError(f"n must be >= 0, got {n}")
    yield (parent, n)


def factorial(this_generator: StepGenerator, parent: StepGenerator | None, n: int) -> Generator:
    """Compute n! while exercising all three targets."""

    # ① (child, …) — delegate to a fresh generator for input validation
    n = yield (StepGenerator(validate, this_generator, n), None)

    acc = 1
    while n > 1:
        acc *= n
        # ② (this_generator, …) — the trampoline drives the loop; no recursion depth
        n = yield (this_generator, n - 1)

    # ③ (parent, …) — surface the answer to whoever called us
    yield (parent, acc)


# ── Tests ────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    cases = [(0, 1), (1, 1), (2, 2), (5, 120), (10, 3_628_800)]
    for n, expected in cases:
        got = trampoline(StepGenerator(factorial, None, n))
        assert got == expected, f"factorial({n}) → {got}, expected {expected}"
        print(f"factorial({n:>2}) = {got}")

    # Error path through validate
    try:
        trampoline(StepGenerator(factorial, None, -1))
        assert False, "should have raised"
    except ValueError as exc:
        print(f"Caught expected error: {exc}")

    print("\nAll tests passed.")
