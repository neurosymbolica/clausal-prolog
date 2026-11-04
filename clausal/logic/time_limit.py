"""Wall-clock time limits: ``call_with_time_limit/2`` and the per-call budget
of a vetted package adapter (operator ruling 2026-11-04, "1+2 option").

One mechanism, one ball.  A limit that runs out throws the bare atom
``time_limit_exceeded``: SWI-Prolog's ball for ``call_with_time_limit/2``
(library(time)), and the one existing Prolog code catches (Scryer's
library(clpz) optimisation code catches exactly it).  A timeout is never a
failure: a goal cut short has not been shown to have no answer.

How it works
------------
``SIGALRM`` and ``signal.setitimer(ITIMER_REAL, ...)``, as the quad runner
and the test runner already use them.  Every live limit is a
:class:`Deadline` on one stack, outermost first.  While the stack is not
empty this module owns the ``SIGALRM`` handler; the handler and timer it
found when the first limit was pushed (the quad runner's, pytest-timeout's,
the test runner's watchdog's) are saved, still honoured -- the timer is set
to the EARLIEST of every deadline and the saved one, and the saved handler
is called when its own time comes -- and restored, with the time it has
left, when the last limit is popped.

Ownership.  When the alarm fires, the handler raises :class:`TimeLimitAlarm`
for the OUTERMOST deadline that has passed (an inner limit never extends an
outer one: both are on the stack, and the earlier wins).  The alarm is in
flight to the call that owns that deadline: ``catch/3`` does not match it
(:func:`clausal.logic.exceptions.catch_match` re-raises it), and a time
limit that does not own it passes it on.  Only the owner turns it into the
ball ``time_limit_exceeded``, which from there on is an ordinary ball.  So a
``catch(..., time_limit_exceeded, ...)`` around an inner limit cannot
swallow the outer limit's timeout.

Lost alarms.  Code that catches every exception (``except Exception`` in a
library, a ``__del__`` the interpreter reports as unraisable) can swallow
the alarm.  So once a deadline has fired, the alarm repeats every
:data:`REPEAT` seconds until its owner has seen it, and the owner answers
the ball on ANY exit after its deadline fired -- an answer, a failure or
another exception -- so a swallowed alarm that made some code give up early
cannot read as that code's answer.

Main thread only.  Python runs signal handlers in the main thread, and only
the main thread may install one.  Elsewhere a limit cannot be enforced, so
it is refused (:func:`unavailable_error`), never silently ignored; so is a
platform without ``SIGALRM``/``setitimer`` (Windows).

The alarm is delivered between Python bytecodes: a long call into C (a big
integer multiplication, a regex) finishes before it lands.
"""
from __future__ import annotations

import os
import signal
import threading
import time

from clausal.logic.exceptions import LogicException

__all__ = ["BALL", "REPEAT", "Deadline", "TimeLimitAlarm", "new", "start",
           "push", "pop", "budgeted", "owned", "live",
           "check_seconds", "ball", "unavailable_error", "available",
           "release_from_depth"]

#: The ball a time limit throws when it runs out (SWI's).
BALL = "time_limit_exceeded"

#: Seconds between repeats of an alarm its owner has not seen yet.
REPEAT = 0.05

#: The shortest interval the timer is set to (setitimer treats 0 as "off").
_TINY = 1e-6


class TimeLimitAlarm(LogicException):
    """The alarm of :attr:`deadline`, in flight to the call that owns it.

    A :class:`~clausal.logic.exceptions.LogicException` (so the engine's
    exception routing carries it up the catcher chain, and the boundaries
    that convert stray Python exceptions leave it alone) whose term is the
    ball; ``catch/3`` never matches it, and the owner replaces it with a
    plain ``LogicException(time_limit_exceeded)``."""

    #: Read by ``catch_match``: never matched by a catch/3 on the way.
    _clausal_in_flight = True

    def __init__(self, deadline: "Deadline") -> None:
        super().__init__(BALL, message="")
        self.deadline = deadline


class Deadline:
    """One live time limit: due at :attr:`at` (``time.monotonic``)."""

    __slots__ = ("at", "fired", "depth", "label", "live")

    def __init__(self, at: float, depth: int, label: str) -> None:
        self.at = at
        self.fired = False      # its alarm has been raised at least once
        self.depth = depth      # the drive-episode depth it was pushed at
        self.label = label
        self.live = True

    def __repr__(self) -> str:
        return (f"<Deadline {self.label} in "
                f"{self.at - time.monotonic():.3f}s"
                f"{' fired' if self.fired else ''}>")


class _Clock:
    """The process's limits (main thread only, so no lock: a signal handler
    cannot wait for one).  ``critical`` defers the handler while the stack
    or the timer is being changed; the deferred alarm is re-armed after."""

    def __init__(self) -> None:
        self.stack: "list[Deadline]" = []
        self.saved_handler = None       # the handler found at the first push
        self.saved_at = None            # when the saved timer is due, or None
        self.saved_interval = 0.0
        self.critical = False
        self.deferred = False


_CLOCK = _Clock()


def available() -> bool:
    """Whether a limit can be enforced here: SIGALRM exists and this is the
    main thread."""
    return (hasattr(signal, "SIGALRM") and hasattr(signal, "setitimer")
            and threading.current_thread() is threading.main_thread())


def unavailable_error(context: str) -> LogicException:
    """``error(system_error(time_limit_not_main_thread), Context)`` off the
    main thread, ``error(system_error(time_limit_no_alarm), Context)`` where
    the platform has no ``SIGALRM``: a time limit that cannot be enforced
    is refused, never quietly dropped."""
    from clausal.logic.exceptions import system_error  # noqa: PLC0415
    if not (hasattr(signal, "SIGALRM") and hasattr(signal, "setitimer")):
        return LogicException(system_error(
            "time_limit_no_alarm", context),
            message=f"{context}: this platform has no SIGALRM, so a time "
                    f"limit cannot be enforced")
    return LogicException(system_error(
        "time_limit_not_main_thread", context),
        message=f"{context}: a time limit is enforced with SIGALRM, which "
                f"only the main thread receives; this is thread "
                f"{threading.current_thread().name!r}")


def ball(context: "str | None" = None) -> LogicException:
    """The plain ball a limit throws when it runs out."""
    text = f"{context}: the time limit ran out" if context else None
    return LogicException(BALL, message=text)


def check_seconds(value, context: str) -> float:
    """The limit *value* (deref'd) as seconds, or the ISO error:
    ``instantiation_error`` unbound, ``type_error(number, V)`` for a
    non-number, ``domain_error(positive_number, V)`` for one that is not
    > 0 (or not finite)."""
    import math  # noqa: PLC0415
    from fractions import Fraction  # noqa: PLC0415
    from decimal import Decimal  # noqa: PLC0415
    from clausal.logic.exceptions import (  # noqa: PLC0415
        domain_error, instantiation_error, type_error)
    from clausal.logic.variables import deref, is_var  # noqa: PLC0415
    v = deref(value)
    if is_var(v):
        raise LogicException(instantiation_error(context))
    if type(v) is bool or not isinstance(v, (int, float, Fraction, Decimal)):
        raise LogicException(type_error("number", v, context))
    seconds = float(v)
    if not (seconds > 0) or math.isinf(seconds):
        raise LogicException(domain_error("positive_number", v, context))
    return seconds


# ── the handler and the timer ───────────────────────────────────────────────


def _rearm(now: float) -> None:
    """Set the timer to the next thing due: a deadline not yet fired, a
    fired one's repeat, or the saved outer timer."""
    nxt = None
    for d in _CLOCK.stack:
        due = (now + REPEAT) if d.fired else d.at
        nxt = due if nxt is None or due < nxt else nxt
    if _CLOCK.saved_at is not None:
        nxt = _CLOCK.saved_at if nxt is None or _CLOCK.saved_at < nxt \
            else nxt
    if nxt is None:
        signal.setitimer(signal.ITIMER_REAL, 0)
    else:
        signal.setitimer(signal.ITIMER_REAL, max(nxt - now, _TINY))


def _fire(signum, frame) -> None:
    if _CLOCK.critical:
        _CLOCK.deferred = True          # re-armed when the change is done
        return
    now = time.monotonic()
    if _CLOCK.saved_at is not None and now >= _CLOCK.saved_at:
        _chain(signum, frame, now)      # the outer timer's time: its turn
        now = time.monotonic()
    for d in _CLOCK.stack:              # outermost first
        if now >= d.at:
            d.fired = True
            _rearm(now)                 # repeat until the owner has it
            raise TimeLimitAlarm(d)
    _rearm(now)


def _chain(signum, frame, now: float) -> None:
    """The saved handler's timer is due: run that handler as the timer would
    have.  It usually raises (and unwinds through every limit); if it
    returns, its timer repeats with its own interval, or is done."""
    handler = _CLOCK.saved_handler
    interval = _CLOCK.saved_interval
    _CLOCK.saved_at = (now + interval) if interval > 0 else None
    if callable(handler):
        try:
            handler(signum, frame)
        finally:
            if _CLOCK.stack:
                _rearm(time.monotonic())
        return
    if handler == signal.SIG_DFL:
        # The default action of SIGALRM ends the process; so it does here.
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, signal.SIG_DFL)
        os.kill(os.getpid(), signal.SIGALRM)
    # SIG_IGN or None (a handler not installed from Python): nothing.


def _begin_critical() -> None:
    _CLOCK.critical = True


def _end_critical() -> None:
    _CLOCK.critical = False
    if _CLOCK.deferred:
        _CLOCK.deferred = False
        if _CLOCK.stack:
            signal.setitimer(signal.ITIMER_REAL, _TINY)


def _drive_depth() -> int:
    from clausal.logic.tabling import _drive_ctx  # noqa: PLC0415
    return len(_drive_ctx.episodes)


def new(seconds: float, label: str = "call_with_time_limit/2") -> Deadline:
    """A limit of *seconds* from now, not yet armed (:func:`start`).  Raises
    :func:`unavailable_error` where it cannot be enforced.  Separate from
    :func:`start` so a caller can arm it INSIDE its ``try``: an alarm that
    lands the moment it is armed is then still the caller's to own."""
    if not available():
        raise unavailable_error(label)
    return Deadline(time.monotonic() + seconds, _drive_depth(), label)


def push(seconds: float, label: str = "call_with_time_limit/2") -> Deadline:
    """:func:`new` and :func:`start`: the caller must :func:`pop` it on
    every exit."""
    d = new(seconds, label)
    start(d)
    return d


def start(d: Deadline) -> None:
    """Arm the limit *d*."""
    now = time.monotonic()
    _begin_critical()
    try:
        if not _CLOCK.stack:
            value, interval = signal.getitimer(signal.ITIMER_REAL)
            _CLOCK.saved_handler = signal.getsignal(signal.SIGALRM)
            _CLOCK.saved_at = (now + value) if value > 0 else None
            _CLOCK.saved_interval = interval
            signal.signal(signal.SIGALRM, _fire)
        _CLOCK.stack.append(d)
        _rearm(now)
    finally:
        _end_critical()


def pop(d: Deadline) -> None:
    """End the limit *d* (idempotent).  The last one restores the handler
    and the timer found by the first, with the time that timer has left (a
    timer already due fires at once)."""
    if not d.live:
        return
    _begin_critical()
    try:
        d.live = False
        try:
            _CLOCK.stack.remove(d)
        except ValueError:
            return
        now = time.monotonic()
        if _CLOCK.stack:
            _rearm(now)
            return
        _CLOCK.deferred = False
        signal.setitimer(signal.ITIMER_REAL, 0)
        handler = _CLOCK.saved_handler
        signal.signal(signal.SIGALRM,
                      handler if handler is not None else signal.SIG_DFL)
        if _CLOCK.saved_at is not None:
            signal.setitimer(signal.ITIMER_REAL,
                             max(_CLOCK.saved_at - now, _TINY),
                             _CLOCK.saved_interval)
        _CLOCK.saved_handler = None
        _CLOCK.saved_at = None
        _CLOCK.saved_interval = 0.0
    finally:
        _CLOCK.critical = False
        _CLOCK.deferred = False


def release_from_depth(depth: int) -> None:
    """Pop every limit pushed at drive-episode depth *depth* or deeper: the
    drive that ran them is closing (``tabling.end_drive_episode``).  A limit
    whose frame an exception skipped (``KeyboardInterrupt``, the quad
    runner's timeout: signals the drive loop does not route through the
    catcher chain) would otherwise keep its alarm armed after the query."""
    if not _CLOCK.stack:
        return
    for d in [d for d in _CLOCK.stack if d.depth >= depth]:
        pop(d)


def live() -> "tuple[Deadline, ...]":
    """The live limits, outermost first (for tests and diagnostics)."""
    return tuple(_CLOCK.stack)


# ── running Python code under a limit ───────────────────────────────────────


def owned(exc: BaseException, d: Deadline) -> bool:
    """Whether *exc* is the alarm of *d*, or anything at all once *d* fired
    (a swallowed alarm makes every outcome after it suspect)."""
    return (isinstance(exc, TimeLimitAlarm) and exc.deadline is d) or d.fired


def budgeted(gen, seconds: float, context: str, on_timeout=None):
    """Delegate to the trampoline-protocol generator *gen* (``yield from``),
    each of its steps under one budget of *seconds* in all: the clock runs
    only while *gen* runs, not while the solutions it yields are consumed.
    Running out throws the ball ``time_limit_exceeded``, after calling
    *on_timeout()* (state repair: a cache the alarm may have left half
    written)."""
    remaining = seconds
    value = None
    started = False
    while True:
        if remaining <= 0:
            gen.close()
            _timed_out(on_timeout)
            raise ball(context)
        d = new(remaining, context)
        t0 = time.monotonic()
        try:
            start(d)
            step = gen.send(value) if started else next(gen)
            started = True
        except StopIteration:
            pop(d)
            if d.fired:
                _timed_out(on_timeout)
                raise ball(context) from None
            return
        except BaseException as e:
            pop(d)
            if owned(e, d):
                gen.close()
                _timed_out(on_timeout)
                raise ball(context) from None
            raise
        pop(d)
        if d.fired:
            gen.close()
            _timed_out(on_timeout)
            raise ball(context)
        remaining -= time.monotonic() - t0
        try:
            value = yield step
        except GeneratorExit:
            gen.close()
            raise
        except BaseException as e:
            # Thrown into us from the catcher chain: hand it to gen.
            try:
                step = gen.throw(e)
            except StopIteration:
                return
            value = yield step


def _timed_out(on_timeout) -> None:
    if on_timeout is not None:
        on_timeout()
