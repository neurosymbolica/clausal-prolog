"""An exception raised asynchronously during a search reaches the caller.

A signal handler runs at the next bytecode boundary, wherever that is.  If
that boundary is inside code whose exceptions CPython cannot hand back to
anyone -- a ``gc.callbacks`` callback, a ``__del__``, a weakref callback --
the exception is reported as "unraisable" and dropped, and the one signal
delivery is lost: a single Ctrl-C or SIGALRM timeout leaves the search
running until memory runs out.

``clausal.aio`` used to register a Python function in ``gc.callbacks``,
called at the start and end of EVERY collection; an allocating search
collects thousands of times a second, so a fair share of alarms landed in
it.  The callback is now a C function (no bytecode, so no handler runs in
it).  Separately, ``is/2`` turned ANY Python exception out of evaluation into
``type_error(evaluable, F/N)``, so an alarm landing in the evaluator came
back as a type error, and running out of memory did too.

The search tests run in a child process: so the trampoline can be chosen
(C, or the pure-Python twin), so memory is capped, and so a lost signal
costs a bounded wait instead of the run.
"""

from __future__ import annotations

import gc
import json
import os
import subprocess
import sys
import textwrap
import types
from pathlib import Path

import pytest

from clausal.logic.exceptions import LogicException

_ROOT = Path(__file__).resolve().parent.parent
_FACADES = _ROOT / "tests" / "iso_l3" / "test_l3_library_facades.py"

_CHILD = textwrap.dedent(r'''
    import json, os, random, resource, signal, sys, threading, time
    mode, kind, preload, trials, spin_dir = sys.argv[1:6]
    trials = int(trials)
    # A lost signal must not take the box down: cap the address space.
    resource.setrlimit(resource.RLIMIT_AS, (3 * 1024 ** 3, 3 * 1024 ** 3))
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    if mode == "py":
        sys.modules["clausal.logic.runtime._trampoline"] = None
    if preload == "facades":
        import pytest
        rc = pytest.main(["-q", "-p", "no:cacheprovider", "-p", "no:randomly",
                          sys.argv[6]])
        assert rc == 0, rc
    elif preload == "aio":
        import clausal.aio  # noqa: F401
    import clausal.logic.trampoline as tr
    from clausal import solve
    sys.path.insert(0, spin_dir)
    import importlib
    spin = importlib.import_module("spin")

    class Alarm(Exception): pass
    class BaseAlarm(BaseException): pass
    class Backstop(BaseException): pass
    expected = {"exception": Alarm, "base": BaseAlarm,
                "keyboard": KeyboardInterrupt}[kind]
    unraisable = []
    sys.unraisablehook = lambda u: unraisable.append(
        f"{type(u.exc_value).__name__} in {u.object!r}"[:120])

    results = {}
    rng = random.Random(1234)
    for _ in range(trials):
        state = {"fired": 0}
        def on_alarm(sig, frame):
            state["fired"] += 1
            if state["fired"] == 1 and kind != "keyboard":
                signal.setitimer(signal.ITIMER_REAL, 1.5)   # the backstop
                raise expected()
            signal.setitimer(signal.ITIMER_REAL, 0)
            raise Backstop()
        signal.signal(signal.SIGALRM, on_alarm)
        delay = rng.uniform(0.005, 0.15)
        timer = None
        if kind == "keyboard":
            # Ctrl-C's own handler, Python's default_int_handler, on the
            # interval timer (SIGINT from another process or thread arrives
            # at times this test does not control); the backstop is a
            # second, Python-level, alarm.
            signal.signal(signal.SIGALRM, signal.default_int_handler)
            signal.signal(signal.SIGUSR1, on_alarm)
            state["fired"] = 1
            timer = threading.Timer(delay + 1.5, os.kill,
                                    (os.getpid(), signal.SIGUSR1))
            timer.start()
            signal.setitimer(signal.ITIMER_REAL, delay)
        else:
            signal.setitimer(signal.ITIMER_REAL, delay)
        try:
            for _ in solve(("spin", 0), module=spin):
                pass
            outcome = "exhausted"
        except Backstop:
            outcome = "lost"
        except BaseException as e:
            outcome = ("delivered" if type(e) is expected
                       else f"converted to {type(e).__name__}: {e}"[:160])
        finally:
            signal.setitimer(signal.ITIMER_REAL, 0)
            if timer is not None:
                timer.cancel()
        results[outcome] = results.get(outcome, 0) + 1
    print("RESULT", json.dumps({"trampoline": tr.trampoline.__module__,
                                "results": results,
                                "unraisable": unraisable[:5]}))
''')


def _spin(tmp_path, mode, kind, preload, trials=15):
    (tmp_path / "spin.pl").write_text("spin(N) :- N1 is N+1, spin(N1).\n")
    script = tmp_path / "child.py"
    script.write_text(_CHILD)
    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join(
        [str(_ROOT)] + ([env["PYTHONPATH"]] if env.get("PYTHONPATH") else []))
    proc = subprocess.run(
        [sys.executable, str(script), mode, kind, preload, str(trials),
         str(tmp_path), str(_FACADES)],
        cwd=_ROOT, env=env, capture_output=True, text=True, timeout=300)
    lines = [l for l in proc.stdout.splitlines() if l.startswith("RESULT ")]
    assert proc.returncode == 0 and lines, (proc.stdout[-3000:], proc.stderr[-3000:])
    report = json.loads(lines[-1][len("RESULT "):])
    if mode == "py":
        assert report["trampoline"] == "clausal.logic._trampoline_py", report
    else:
        assert report["trampoline"] == "clausal.logic.runtime._trampoline", report
    return report


_MODES = [pytest.param("c", id="c_trampoline"),
          pytest.param("py", id="python_trampoline")]


@pytest.mark.parametrize("mode", _MODES)
@pytest.mark.parametrize("kind", ["exception", "base", "keyboard"])
def test_an_alarm_during_a_search_reaches_the_caller(tmp_path, mode, kind):
    report = _spin(tmp_path, mode, kind, "aio")
    assert report["results"] == {"delivered": 15}, report
    assert report["unraisable"] == [], report


@pytest.mark.parametrize("mode", _MODES)
def test_an_alarm_reaches_the_caller_after_the_library_facades_ran(tmp_path, mode):
    # The ordering that first showed it: the facades test file imports
    # clausal.aio, and from then on alarms were lost.
    report = _spin(tmp_path, mode, "exception", "facades", trials=10)
    assert report["results"] == {"delivered": 10}, report
    assert report["unraisable"] == [], report


def test_no_engine_gc_callback_runs_bytecode():
    """A gc callback that is a Python function is a place a signal handler
    can run and have its exception dropped as unraisable."""
    import clausal.aio  # noqa: F401  (registers its callback)
    offenders = [cb for cb in gc.callbacks
                 if isinstance(cb, types.FunctionType)
                 and (getattr(cb, "__module__", "") or "").startswith("clausal")]
    assert offenders == []


def test_await_only_still_knows_when_the_collector_is_running():
    from clausal import aio
    seen = []

    def probe(phase, info):
        seen.append((phase, aio._gc_collecting()))
    gc.callbacks.append(probe)          # after the engine's own callback
    try:
        gc.collect()
    finally:
        gc.callbacks.remove(probe)
    assert seen == [("start", True), ("stop", False)]
    assert aio._gc_collecting() is False


# ── is/2: a foreign exception out of evaluation is not a type error ──────

class _Foreign(Exception):
    pass


def _raise_in_evaluate(monkeypatch, exc):
    import clausal.logic.exact_arith as ea

    def evaluate(*_a, **_k):
        raise exc
    monkeypatch.setattr(ea, "evaluate", evaluate)


def _run_is():
    from clausal.logic.builtins.iso_compare import _iso_eval
    return _iso_eval(("+", 1, 2), "is/2")


def test_a_foreign_exception_in_is_propagates_unchanged(monkeypatch):
    exc = _Foreign("from a signal handler")
    _raise_in_evaluate(monkeypatch, exc)
    with pytest.raises(_Foreign) as info:
        _run_is()
    assert info.value is exc


@pytest.mark.parametrize("exc_type", [KeyboardInterrupt, SystemExit])
def test_a_control_exception_in_is_propagates_unchanged(monkeypatch, exc_type):
    _raise_in_evaluate(monkeypatch, exc_type())
    with pytest.raises(exc_type):
        _run_is()


def test_memory_exhaustion_in_is_is_resource_error_memory(monkeypatch):
    # ISO 13211-1 7.12.2 h: resource_error(memory), not type_error(evaluable).
    _raise_in_evaluate(monkeypatch, MemoryError())
    with pytest.raises(LogicException) as info:
        _run_is()
    assert info.value.term[0] == "error"
    assert info.value.term[1] == ("resource_error", "memory")


def test_a_non_evaluable_python_value_is_still_type_error_evaluable():
    from clausal.logic.builtins.iso_compare import _iso_eval
    with pytest.raises(LogicException) as info:
        _iso_eval(("+", 1, object()), "is/2")
    assert info.value.term[1][0] == "type_error"
    assert info.value.term[1][1] == "evaluable"


def test_a_foreign_exception_in_a_clpz_bound_fold_propagates(monkeypatch):
    # The same catch-all, in CLP(Z)'s domain of a ground expression node:
    # an exception that was not evaluation's own came back as the default
    # domain, silently.
    import clausal.logic.clpfd as clpfd
    from clausal import terms
    from clausal.logic.variables import Trail
    node = terms.FloorDiv(left=7, right=2)
    assert clpfd._expr_domain(node, Trail()) == ((3, 3),)
    exc = _Foreign("from a signal handler")

    def boom(_expr):
        raise exc
    monkeypatch.setattr(clpfd, "_eval_ground", boom)
    with pytest.raises(_Foreign):
        clpfd._expr_domain(node, Trail())


def test_memory_error_caught_by_catch_is_resource_error_memory():
    # ISO 7.12.2 h, as RecursionError is resource_error(stack).
    from clausal.logic.exceptions import python_error_term
    term = python_error_term(MemoryError())
    assert term[0] == "error" and term[1] == ("resource_error", "memory")
