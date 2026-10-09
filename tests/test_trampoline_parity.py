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


def test_solutions_final_without_snapshot_appends_no_sentinel(impl):
    # Review Minor-1: FINAL is a sentinel, not a payload — without a
    # snapshot callback there is nothing to record for it. A regression
    # that appended the raw FINAL value would leak the sentinel object
    # into caller-visible results.
    pulls = []

    def fn(this, proceed, fail, catcher):
        pulls.append("first")
        yield (proceed, 1)
        pulls.append("second")
        yield (proceed, impl.FINAL)
        pulls.append("MUST NOT HAPPEN")  # FINAL means: do not pull again
        yield (fail, impl.DONE)

    got = impl.solutions(root(impl, fn))
    assert got == [1]  # solution 1 only; FINAL contributes nothing
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


def test_root_suspend_is_a_protocol_error_for_trampoline(impl):
    # Review follow-up to Q1 (2026-08-27): the pull-drivers can answer a
    # root-level suspend with "no solution" (A04-F008); trampoline()'s
    # contract — return the root-yield value — cannot, and returning the
    # raw sentinel fabricated success at its only runtime call site
    # (clpz3 discards the value).  A loud, unroutable engine-protocol
    # error is the only honest answer.
    fn = enum_fn([_TABLING_SUSPEND], impl.DONE)
    with pytest.raises(RuntimeError) as ei:
        impl.trampoline(root(impl, fn))
    assert getattr(ei.value, "__clausal_engine_protocol__", False)


def suspend_chain(impl, log):
    """Parent whose child yields (parent, _TABLING_SUSPEND) mid-chain.

    Terminates with an explicit ``(None, DONE)`` root yield after the
    intercepted/leaked yield so a caller that keeps pulling (``solutions``)
    can exit cleanly instead of resuming an exhausted generator.  The
    single-pull tests (``_drive_until_yield``, ``trampoline``) never reach
    it.
    """
    def child(this, proceed, fail, catcher):
        yield (proceed, _TABLING_SUSPEND)

    def fn(this, proceed, fail, catcher):
        got = yield (impl.StepGenerator(child, this, this, this), None)
        log.append(got)
        yield (None, "intercepted" if got is impl.DONE else "leaked")
        yield (None, impl.DONE)

    return root(impl, fn)


def test_mid_chain_suspend_is_intercepted_by_drive_until_yield(impl):
    log = []
    assert impl._drive_until_yield(suspend_chain(impl, log)) is True
    assert log == [impl.DONE]  # driver converted the suspend to DONE


def test_mid_chain_suspend_is_intercepted_by_trampoline_too(impl):
    # Policy convergence (todo/drive-loop-policy-convergence.md, Q1,
    # 2026-08-26): all three entry points intercept a mid-chain suspend.
    # trampoline()'s only runtime call site is the Z3 propagator embedding
    # (clpz3._run_goal), which discards the value — a leaked sentinel there
    # fabricated success; interception (suspend → DONE for the parent) is
    # what the other two entry points always did.
    log = []
    assert impl.trampoline(suspend_chain(impl, log)) == "intercepted"
    assert log == [impl.DONE]


def test_solutions_intercepts_mid_chain_suspend(impl):
    # Review Minor-1: solutions() shares _drive_until_yield's intercept_ts
    # policy but had no direct pin — flipping solutions' intercept_ts to
    # False (either core) would turn this "intercepted" into "leaked" and
    # escape the whole corpus.
    log = []
    assert impl.solutions(suspend_chain(impl, log)) == ["intercepted"]
    assert log == [impl.DONE]


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


def test_pep479_wrapper_is_exhaustion_for_duy_and_solutions(impl):
    # StopIteration raised inside a generator surfaces as the PEP-479
    # RuntimeError wrapper at the frame boundary.  Policy convergence
    # (todo/drive-loop-policy-convergence.md, Q2, 2026-08-26): solutions
    # agrees with _drive_until_yield that the wrapper is a converted
    # exhaustion (A04-F009) — the exhaustion test runs BEFORE routing, so
    # the enclosing handler must not steal it either.  trampoline() keeps
    # raising: its contract (return the root-yield value) has no way to
    # represent exhaustion, a blessed difference, not an accident.
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
    assert impl.solutions(root(impl, greedy)) == []
    with pytest.raises(RuntimeError):
        impl.trampoline(root(impl, greedy))


def test_entry_send_pep479_wrapper_exhausts_duy_and_solutions(impl):
    # Review Minor-1: the PEP-479 wrapper case above is hit mid-chain (in
    # the while loop); the ROOT's very first send() has its own try/except
    # in _drive_to_root_yield that no existing test reached. A root frame
    # that raises StopIteration before its first yield surfaces the
    # wrapper on that entry send instead.
    assert impl._drive_until_yield(
        root(impl, raiser_fn(StopIteration()))) is None
    assert impl.solutions(root(impl, raiser_fn(StopIteration()))) == []
    with pytest.raises(RuntimeError):
        impl.trampoline(root(impl, raiser_fn(StopIteration())))


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


# ── FINAL at the root retires the StepGenerator for every pull-driver ────────
# Policy decision (todo/drive-loop-policy-convergence.md, Q3, 2026-08-26),
# made BEFORE any producer emits FINAL (CONTINUATION_TCO_PLAN Phase 4b+):
# a root-level FINAL is "here is a solution AND I am retiring".
# _drive_until_yield delivers the solution (True) and marks the root
# retired; every later pull answers None WITHOUT resuming the retired
# generator.  solutions already stopped pulling; it now also marks the
# root so a later _drive_until_yield on the same root agrees.


def final_then_explode_fn(impl, pulls):
    """Root frame: one solution, then FINAL.  Resuming after FINAL is a
    protocol violation, made loud."""
    def fn(this, proceed, fail, catcher):
        pulls.append("first")
        yield (proceed, "sol")
        pulls.append("final")
        yield (proceed, impl.FINAL)
        pulls.append("MUST NOT HAPPEN")
        raise AssertionError("resumed a retired root")
        yield  # pragma: no cover
    return fn


def test_final_at_root_is_a_solution_then_retirement_for_duy(impl):
    pulls = []
    sg = root(impl, final_then_explode_fn(impl, pulls))
    assert impl._drive_until_yield(sg) is True   # "sol"
    assert impl._drive_until_yield(sg) is True   # FINAL delivers its solution
    assert impl._drive_until_yield(sg) is None   # retired: no further pull
    assert impl._drive_until_yield(sg) is None   # stays retired
    assert pulls == ["first", "final"]


def test_solutions_retirement_is_visible_to_a_later_duy_pull(impl):
    pulls = []
    sg = root(impl, final_then_explode_fn(impl, pulls))
    assert impl.solutions(sg) == ["sol"]         # FINAL itself: no payload
    assert impl._drive_until_yield(sg) is None   # solutions marked it retired
    assert pulls == ["first", "final"]


def test_duy_retirement_is_visible_to_a_later_solutions_call(impl):
    pulls = []
    sg = root(impl, final_then_explode_fn(impl, pulls))
    assert impl._drive_until_yield(sg) is True
    assert impl._drive_until_yield(sg) is True
    assert impl.solutions(sg) == []              # retired root: nothing more
    assert pulls == ["first", "final"]


def test_trampoline_final_passthrough_marks_retired(impl):
    # Review follow-up to Q3 (2026-08-27): trampoline() is inside the
    # retirement protocol too.  A root FINAL is returned as-is (it IS the
    # answer for a value-returning driver) but the root is marked, so a
    # later pull-driver does not re-pull the retired producer.
    def fn(this, proceed, fail, catcher):
        yield (proceed, impl.FINAL)
        raise AssertionError("resumed a retired root")
        yield  # pragma: no cover

    sg = root(impl, fn)
    assert impl.trampoline(sg) is impl.FINAL
    assert impl._drive_until_yield(sg) is None   # retired, not re-pulled


def test_trampoline_on_a_retired_root_is_a_protocol_error(impl):
    # The pull-drivers answer a retired root with benign exhaustion;
    # trampoline() cannot represent exhaustion, so pulling a retired
    # root through it is a loud, unroutable engine anomaly.
    pulls = []
    sg = root(impl, final_then_explode_fn(impl, pulls))
    assert impl.solutions(sg) == ["sol"]
    with pytest.raises(RuntimeError) as ei:
        impl.trampoline(sg)
    assert getattr(ei.value, "__clausal_engine_protocol__", False)
    assert pulls == ["first", "final"]


def test_retired_is_a_visible_writable_attribute_on_both_cores(impl):
    # Review follow-up (2026-08-27): the twin exposes .retired as a
    # public slot; the C StepGenerator must expose the same surface.
    sg = root(impl, enum_fn([1], impl.DONE))
    assert not sg.retired
    sg.retired = True
    assert sg.retired
    assert impl._drive_until_yield(sg) is None   # honoured by the driver


# ── malformed steps are TypeErrors from the driver, never routed ─────────────
# Policy decision (todo/drive-loop-policy-convergence.md, Q4, 2026-08-26):
# the C core's shape checks are canonical — a step that is not a 2-tuple,
# or whose target is neither StepGenerator nor None, is a protocol
# violation (a compiler bug or a hand-built chain gone wrong).  The
# driver raises TypeError directly, OUTSIDE exception routing: no
# enclosing catch/3 may absorb it.  The Python twin used to route the
# unpack TypeError; it now performs the same explicit checks.


def bad_step_chain(impl, bad_step):
    """Child hands the driver *bad_step*; the enclosing handler must not
    steal the resulting TypeError."""
    def bad(this, proceed, fail, catcher):
        yield bad_step

    def greedy(this, proceed, fail, catcher):
        child = impl.StepGenerator(bad, this, this, this)
        try:
            yield (child, None)
        except Exception:
            yield (proceed, "stolen")
        yield (fail, impl.DONE)

    return root(impl, greedy)


@pytest.mark.parametrize("bad_step, match", [
    ("not-a-tuple", "must yield 2-tuples"),
    ((1, 2, 3), "must yield 2-tuples"),
    ((42, None), "must be StepGenerator or None, got int"),
], ids=["non-tuple", "3-tuple", "bad-target"])
def test_malformed_step_is_a_typeerror_never_routed(impl, bad_step, match):
    # The match strings include the entry-point prefix: the TypeError must
    # name the driver that was actually running (review follow-up
    # 2026-08-27 — the C catcher-resume path used to hardcode
    # "trampoline:").
    with pytest.raises(TypeError, match=f"trampoline: .*{match}"):
        impl.trampoline(bad_step_chain(impl, bad_step))
    with pytest.raises(TypeError, match=f"solutions: .*{match}"):
        impl.solutions(bad_step_chain(impl, bad_step))
    with pytest.raises(TypeError, match=f"_drive_until_yield: .*{match}"):
        impl._drive_until_yield(bad_step_chain(impl, bad_step))


def test_bad_target_message_spells_a_dotted_type_the_same_way(impl):
    # C prints the type via tp_name (dotted for many types), the twin via
    # __name__: both must agree on the LAST component so the two cores
    # raise the same message (review follow-up 2026-08-27).
    from collections import OrderedDict

    with pytest.raises(TypeError,
                       match="must be StepGenerator or None, got OrderedDict"):
        impl._drive_until_yield(bad_step_chain(impl, (OrderedDict(), None)))


def test_malformed_first_step_at_entry_is_a_typeerror(impl):
    def fn(this, proceed, fail, catcher):
        yield "junk"

    with pytest.raises(TypeError, match="must yield 2-tuples"):
        impl.trampoline(root(impl, fn))
    with pytest.raises(TypeError, match="must yield 2-tuples"):
        impl._drive_until_yield(root(impl, fn))


def test_malformed_step_after_catcher_resume_names_the_entry_point(impl):
    # A handler absorbs an exception and resumes with a malformed step:
    # the shape check must run in the driver's main loop with the real
    # entry-point name, not in the unwind helper with a hardcoded one.
    def bad_handler(this, proceed, fail, catcher):
        child = impl.StepGenerator(raiser_fn(ValueError("boom")),
                                   this, this, this)
        try:
            yield (child, None)
        except ValueError:
            yield "junk"          # malformed resume step
        yield (fail, impl.DONE)

    with pytest.raises(TypeError,
                       match="solutions: generator must yield 2-tuples"):
        impl.solutions(root(impl, bad_handler))
    with pytest.raises(
            TypeError,
            match="_drive_until_yield: generator must yield 2-tuples"):
        impl._drive_until_yield(root(impl, bad_handler))


# ── pending goals on a solution step ─────────────────────────────────────────
#
# A frame whose last argument is a Trail answers a solution step -- a yield
# of (proceed, None) -- once per answer of the goals queued on the trail,
# and skips it when they have none (clausal/logic/pending.py).

def _queued(trail, *goals):
    for g in goals:
        trail.push_pending(g)


def _answers(n, log):
    def goal():
        for i in range(n):
            log.append(i)
            yield None
    return goal


def _steps(impl, k, goals):
    from clausal.logic.variables import Trail
    trail = Trail()
    marker = object()
    done = impl.DONE

    def fn(this, proceed, fail, catcher, trail):
        for i in range(k):
            _queued(trail, goals[i])
            yield (proceed, None)
        yield (fail, done)
    sg = impl.StepGenerator(fn, marker, marker, marker, trail)
    out = []
    while True:
        step = sg.send(None)
        out.append("sol" if step[1] is None else "done")
        if step[1] is done:
            return out, trail


def test_a_solution_step_is_answered_once_per_answer_of_its_goals(impl):
    log = []
    out, trail = _steps(impl, 2, [_answers(2, log), _answers(3, log)])
    assert out == ["sol"] * 5 + ["done"]
    assert trail.pending is None


def test_a_solution_step_whose_goals_fail_is_skipped(impl):
    log = []
    out, _ = _steps(impl, 3, [_answers(1, log), _answers(0, log), _answers(1, log)])
    assert out == ["sol", "sol", "done"]


def test_an_error_in_a_queued_goal_propagates(impl):
    from clausal.logic.variables import Trail

    def bad():
        raise ValueError("boom")
        yield None
    trail = Trail()
    marker = object()

    def fn(this, proceed, fail, catcher, trail):
        trail.push_pending(bad)
        yield (proceed, None)
        yield (fail, impl.DONE)
    sg = impl.StepGenerator(fn, marker, marker, marker, trail)
    with pytest.raises(ValueError, match="boom"):
        sg.send(None)


@pytest.mark.parametrize("act", ["send", "close", "throw", "init"])
def test_re_entering_a_generator_while_it_runs_its_goals_is_an_error(impl, act):
    """Review H1: a queued goal that sends to, closes or throws into the
    generator whose solution step is running it got a clean error in
    neither twin (C freed the running drain: a segfault)."""
    from clausal.logic.variables import Trail
    trail = Trail()
    marker = object()
    box, seen = {}, []

    def goal():
        sg = box["sg"]
        try:
            if act == "send":
                sg.send(None)
            elif act == "close":
                sg.close()
            elif act == "init":
                sg.__init__(fn, object(), object(), object(), trail)
            else:
                sg.throw(ValueError("x"))
        except RuntimeError as e:
            # an engine-protocol error: never handed to catch/3
            assert getattr(e, "__clausal_engine_protocol__", False)
            seen.append(str(e))
        yield None
        yield None

    def fn(this, proceed, fail, catcher, trail):
        trail.push_pending(goal)
        yield (proceed, None)
        yield (fail, impl.DONE)
    sg = box["sg"] = impl.StepGenerator(fn, marker, marker, marker, trail)
    assert sg.send(None) == (marker, None)
    assert sg.send(None) == (marker, None)          # the goal's second answer
    assert sg.send(None)[1] is impl.DONE
    assert seen and "re-entered while running its pending goals" in seen[0]


def test_a_driver_defers_woken_goals_only_while_it_runs(impl):
    """Review M2: the flag used to stay set after a trail was driven once, so a
    later bare unify queued a woken goal nothing would run."""
    from clausal.logic.variables import Trail
    trail = Trail()
    during = []

    def fn(this, proceed, fail, catcher, trail):
        during.append(trail.defer)
        yield (proceed, 1)
        yield (fail, impl.DONE)
    assert impl.solutions(impl.StepGenerator(fn, None, None, None, trail)) == [1]
    assert during == [True] and trail.defer is False
