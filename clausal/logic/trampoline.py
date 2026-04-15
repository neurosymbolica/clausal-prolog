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
    from clausal.logic.runtime._trampoline import DONE, _COMMIT, StepGenerator, trampoline, solutions, _drive_until_yield  # type: ignore[import-untyped]
except ImportError:
    # ── DONE / _COMMIT sentinels ─────────────────────────────────────────
    # _COMMIT is the third yield-action sentinel (alongside ``None`` for
    # solution and ``DONE`` for exhaustion).  A producer yielding
    # ``(_proceed, _COMMIT)`` means "here's a solution AND I'm retiring —
    # don't pull again".  See ``implementation_plans/CONTINUATION_TCO_PLAN.md``
    # §4.1 / Phase 4.  Phase 4a (this commit) lands the sentinel and
    # root-driver handling only; no producer emits ``_COMMIT`` yet, so
    # the new branches are cold and existing call sites pay zero overhead.
    DONE: object = object()
    _COMMIT: object = object()

    # ── StepGenerator ─────────────────────────────────────────────────────

    class StepGenerator:  # type: ignore[no-redef]
        """Wraps a generator function, providing ``this_generator`` automatically.

        Usage::

            sg = StepGenerator(pred_fn, proceed, fail, catcher, arg0, arg1, trail)

        The three continuation slots steer three independent dataflows:

        - ``proceed`` — where yielded solutions go (consumer frame).
        - ``fail``    — where to resume on child exhaustion (completion).
        - ``catcher`` — where thrown exceptions propagate (handler chain).

        For normal (non-TCO) call sites the caller passes the same frame for
        all three; continuation-level TCO later sets ``proceed`` to the
        caller's own ``proceed`` while keeping ``fail`` / ``catcher`` pointed
        at the caller.  See ``implementation_plans/CONTINUATION_TCO_PLAN.md``.

        The generator body receives the three continuation slots as its
        first three parameters after ``this_generator``:
        ``pred_fn(sg, proceed, fail, catcher, *args)``.

        ``send(value)`` handles first-call bootstrapping transparently: the
        first call does ``next(inner_gen)``; subsequent calls delegate to
        ``inner_gen.send(value)``.
        """
        __slots__ = ('_gen', '_started', 'proceed', 'fail', 'catcher')

        def __init__(
            self,
            func: Callable,
            proceed: Any,
            fail: Any,
            catcher: Any,
            *args: Any,
        ) -> None:
            self.proceed = proceed
            self.fail = fail
            self.catcher = catcher
            # Forward all three continuation slots to the generator body.
            # Compiled-predicate signature is
            # (this_generator, _proceed, _fail, _catcher, *args, trail).
            self._gen: Generator = func(self, proceed, fail, catcher, *args)
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
        We unwind through the ``catcher`` chain using .throw() until a
        catch/3 handler catches it.
        """
        from clausal.logic.exceptions import LogicException

        gen, value = root.send(None)
        while gen is not None:
            try:
                gen, value = gen.send(value)
            except LogicException as exc:
                target = gen.catcher if hasattr(gen, 'catcher') else None
                while target is not None:
                    try:
                        gen, value = target.throw(exc)
                        break  # handler caught it — resume normal trampoline
                    except LogicException:
                        target = target.catcher if hasattr(target, 'catcher') else None
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

        LogicException routing: same as trampoline() — unwind through the
        ``catcher`` chain via .throw() until caught or surface to Python.
        """
        from clausal.logic.tabling import _TABLING_SUSPEND
        from clausal.logic.exceptions import LogicException

        results: list = []
        gen, value = root.send(None)
        while True:
            if gen is None:
                if value is DONE:
                    return results
                if value is _COMMIT:
                    # Producer committed: deliver this final solution and
                    # stop — no further pull from the (now-retired) root.
                    # ``_COMMIT`` is a sentinel, not a payload, so when
                    # *snapshot* is None there's no raw value to record.
                    if snapshot is not None:
                        results.append(snapshot())
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
                    target = gen.catcher if hasattr(gen, 'catcher') else None
                    while target is not None:
                        try:
                            gen, value = target.throw(type(exc), exc)
                            break
                        except LogicException:
                            target = target.catcher if hasattr(target, 'catcher') else None
                    else:
                        raise exc

    def _drive_until_yield(sg: StepGenerator) -> bool | None:  # type: ignore[no-redef]
        """Pure-Python fallback for C _drive_until_yield.

        Calls sg.send(None) and loops through the trampoline chain until a
        solution is found (returns True) or the search is exhausted (returns
        None).
        """
        from clausal.logic.tabling import _TABLING_SUSPEND
        from clausal.logic.exceptions import LogicException

        try:
            gen, value = sg.send(None)
        except StopIteration:
            return None
        while True:
            if gen is None:
                if value is DONE:
                    return None
                return True
            try:
                if value is _TABLING_SUSPEND:
                    gen, value = gen.send(DONE)
                else:
                    gen, value = gen.send(value)
            except StopIteration:
                return None
            except LogicException as exc:
                target = gen.catcher if hasattr(gen, 'catcher') else None
                while target is not None:
                    try:
                        gen, value = target.throw(type(exc), exc)
                        break
                    except LogicException:
                        target = target.catcher if hasattr(target, 'catcher') else None
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
