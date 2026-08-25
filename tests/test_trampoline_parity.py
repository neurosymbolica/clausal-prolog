"""One behavioural corpus, both trampoline implementations.

Drives hand-built StepGenerator chains — never compiled predicates — so the
corpus is independent of the compiled-globals capture
(compiler/predicate.py binds StepGenerator at compile time) and can reach
protocol corners no .clausal fixture reaches.

Every helper takes ``impl`` and builds chains from ``impl.StepGenerator``
with ``impl.DONE`` / ``impl.FINAL``; the two implementations' sentinels are
distinct objects.  ``_TABLING_SUSPEND`` is one shared sentinel from
clausal.logic.tabling.

C is canonical: on divergence, fix _trampoline_py, never the C side.
Acceptance (todo/c-and-python-trampoline-twins-have-no-parity-test.md):
deleting a routing branch from EITHER implementation reds this module.
"""

from __future__ import annotations

import traceback

import pytest

import clausal.logic._trampoline_py as py_impl
from clausal.logic.tabling import _TABLING_SUSPEND

c_impl = pytest.importorskip(
    "clausal.logic.runtime._trampoline",
    reason="C extension not built — the parity corpus needs BOTH implementations",
)


@pytest.fixture(params=["c", "py"], ids=["C", "python"])
def impl(request):
    return c_impl if request.param == "c" else py_impl


# ── chain builders ───────────────────────────────────────────────────────────
# Frame signature: fn(this_generator, proceed, fail, catcher, *args).
# A ROOT frame is built with proceed=fail=catcher=None, so its
# ``yield (proceed, v)`` is a root yield (target None = deliver v) and
# ``yield (fail, DONE)`` is root-level exhaustion.


def root(impl, fn, *args):
    return impl.StepGenerator(fn, None, None, None, *args)


def enum_fn(values, done):
    """Root frame yielding each value as a solution, then exhaustion."""
    def fn(this, proceed, fail, catcher):
        for v in values:
            yield (proceed, v)
        yield (fail, done)
    return fn


def raiser_fn(exc):
    """Leaf frame that raises before its first yield."""
    def fn(this, proceed, fail, catcher):
        raise exc
        yield  # pragma: no cover — makes fn a generator function
    return fn


# ── solutions / trampoline / _drive_until_yield: plain enumeration ───────────


def test_solutions_collects_until_done(impl):
    r = root(impl, enum_fn([1, 2, 3], impl.DONE))
    assert impl.solutions(r) == [1, 2, 3]


def test_solutions_snapshot_runs_while_bindings_live(impl):
    cell = []

    def fn(this, proceed, fail, catcher):
        for v in (1, 2):
            cell.append(v)          # "bind"
            yield (proceed, None)
            cell.pop()              # resumed = backtracked: "undo"
        yield (fail, impl.DONE)

    assert impl.solutions(root(impl, fn), snapshot=lambda: cell[0]) == [1, 2]
    assert cell == []


def test_solutions_final_retires_the_root(impl):
    pulls = []

    def fn(this, proceed, fail, catcher):
        pulls.append("first")
        yield (proceed, 1)
        pulls.append("second")
        yield (proceed, impl.FINAL)
        pulls.append("MUST NOT HAPPEN")  # FINAL means: do not pull again
        yield (fail, impl.DONE)

    got = impl.solutions(root(impl, fn), snapshot=lambda: "snap")
    assert got == ["snap", "snap"]  # solution 1, then FINAL's snapshot
    assert pulls == ["first", "second"]


def test_trampoline_returns_the_final_value_through_a_child(impl):
    def child(this, proceed, fail, catcher, n):
        yield (proceed, n + 1)

    def fn(this, proceed, fail, catcher):
        v = yield (impl.StepGenerator(child, this, this, this, 41), None)
        yield (proceed, v)  # proceed is None at the root → final answer

    assert impl.trampoline(root(impl, fn)) == 42


def test_drive_until_yield_steps_solutions_then_exhausts(impl):
    sg = root(impl, enum_fn(["a", "b"], impl.DONE))
    assert impl._drive_until_yield(sg) is True
    assert impl._drive_until_yield(sg) is True
    assert impl._drive_until_yield(sg) is None


# ── _TABLING_SUSPEND, at the root and mid-chain ──────────────────────────────


def test_root_suspend_is_exhaustion_not_a_solution(impl):
    fn = enum_fn([_TABLING_SUSPEND], impl.DONE)
    assert impl._drive_until_yield(root(impl, fn)) is None      # A04-F008
    assert impl.solutions(root(impl, fn)) == []


def suspend_chain(impl, log):
    """Parent whose child yields (parent, _TABLING_SUSPEND) mid-chain."""
    def child(this, proceed, fail, catcher):
        yield (proceed, _TABLING_SUSPEND)

    def fn(this, proceed, fail, catcher):
        got = yield (impl.StepGenerator(child, this, this, this), None)
        log.append(got)
        yield (None, "intercepted" if got is impl.DONE else "leaked")

    return root(impl, fn)


def test_mid_chain_suspend_is_intercepted_by_drive_until_yield(impl):
    log = []
    assert impl._drive_until_yield(suspend_chain(impl, log)) is True
    assert log == [impl.DONE]  # driver converted the suspend to DONE


def test_mid_chain_suspend_is_NOT_intercepted_by_trampoline(impl):
    # Pins today's per-entry-point flag difference (spec: preserved, not
    # converged).  trampoline() hands the sentinel through untouched.
    log = []
    assert impl.trampoline(suspend_chain(impl, log)) == "leaked"
    assert log == [_TABLING_SUSPEND]


# ── exception routing through the catcher chain ──────────────────────────────


def handler_fn(impl, inner_fn, done, *, decline=False):
    """Frame that spawns inner_fn as a child and handles ValueError."""
    def fn(this, proceed, fail, catcher):
        child = impl.StepGenerator(inner_fn, this, this, this)
        try:
            yield (child, None)
        except ValueError as exc:
            if decline:
                raise
            yield (proceed, f"caught:{exc}")
        yield (fail, done)
    return fn


def test_routable_exception_reaches_the_enclosing_handler(impl):
    fn = handler_fn(impl, raiser_fn(ValueError("boom")), impl.DONE)
    assert impl.solutions(root(impl, fn)) == ["caught:boom"]
    assert impl._drive_until_yield(root(impl, fn)) is True


def test_declining_handler_hands_it_to_the_next_catcher_up(impl):
    inner = handler_fn(impl, raiser_fn(ValueError("boom")), impl.DONE,
                       decline=True)

    def outer(this, proceed, fail, catcher):
        child = impl.StepGenerator(inner, this, this, this)
        try:
            yield (child, None)
        except ValueError as exc:
            yield (proceed, f"outer caught:{exc}")
        yield (fail, impl.DONE)

    assert impl.solutions(root(impl, outer)) == ["outer caught:boom"]


def test_unhandled_exception_propagates_unchanged_with_its_traceback(impl):
    boom = ValueError("boom")

    def parent(this, proceed, fail, catcher):
        # catcher=None: nobody to route to.
        child = impl.StepGenerator(raiser_fn(boom), this, this, None)
        yield (child, None)
        yield (fail, impl.DONE)

    with pytest.raises(ValueError) as ei:
        impl.solutions(root(impl, parent))
    assert ei.value is boom  # identity: routing must be invisible
    frames = [f.name for f in traceback.extract_tb(ei.value.__traceback__)]
    assert "fn" in frames    # raiser_fn's frame survives on the traceback


@pytest.mark.parametrize("exc_type", [GeneratorExit, KeyboardInterrupt,
                                      SystemExit])
def test_control_signals_are_never_routed(impl, exc_type):
    # The enclosing handler catches BaseException on purpose: if the driver
    # wrongly routed the signal, the handler would absorb it and the test
    # would see "stolen" instead of the propagating signal.
    def greedy(this, proceed, fail, catcher):
        child = impl.StepGenerator(raiser_fn(exc_type()), this, this, this)
        try:
            yield (child, None)
        except BaseException:
            yield (proceed, "stolen")
        yield (fail, impl.DONE)

    with pytest.raises(exc_type):
        impl.solutions(root(impl, greedy))


def test_pep479_wrapper_is_exhaustion_for_duy_and_propagates_elsewhere(impl):
    # StopIteration raised inside a generator surfaces as the PEP-479
    # RuntimeError wrapper at the frame boundary.
    def stop_raiser(this, proceed, fail, catcher):
        raise StopIteration()
        yield  # pragma: no cover

    def greedy(this, proceed, fail, catcher):
        child = impl.StepGenerator(stop_raiser, this, this, this)
        try:
            yield (child, None)
        except Exception:
            yield (proceed, "stolen")
        yield (fail, impl.DONE)

    assert impl._drive_until_yield(root(impl, greedy)) is None  # A04-F009
    with pytest.raises(RuntimeError):
        impl.solutions(root(impl, greedy))


def test_generator_that_returns_is_a_protocol_error_not_a_catchable(impl):
    # Inner generator RETURNS instead of final-yielding: an engine anomaly.
    # Canonical (C) behaviour: a RuntimeError marked
    # __clausal_engine_protocol__, refused by routing, propagated by every
    # entry point — never swallowed as exhaustion, never offered to a
    # handler.
    def returns_early(this, proceed, fail, catcher):
        if False:
            yield  # pragma: no cover
        return

    def greedy(this, proceed, fail, catcher):
        child = impl.StepGenerator(returns_early, this, this, this)
        try:
            yield (child, None)
        except Exception:
            yield (proceed, "stolen")
        yield (fail, impl.DONE)

    with pytest.raises(RuntimeError) as ei:
        impl.solutions(root(impl, greedy))
    assert getattr(ei.value, "__clausal_engine_protocol__", False)
    with pytest.raises(RuntimeError):
        impl._drive_until_yield(root(impl, greedy))
