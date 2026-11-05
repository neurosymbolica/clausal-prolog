"""call_with_time_limit/2 (operator ruling 2026-11-04, "1+2 option"):
SWI-Prolog's library(time) predicate.

SWI documents it at
https://www.swi-prolog.org/pldoc/doc_for?object=call_with_time_limit/2 :
"Goal is called as in once/1.  If this limit is exceeded, the exception
time_limit_exceeded is raised."  The type and domain errors for Time, the
nesting rule and the main-thread rule are this engine's (the ruling), and
are pinned here.
"""
from __future__ import annotations

import signal
import textwrap
import threading
import time

import pytest

from clausal import Var, call, deref, solve
from clausal.logic import time_limit
from clausal.logic.exceptions import LogicException
from clausal.logic.variables import walk
from clausal.testing import load_clausal_module

BALL = "time_limit_exceeded"
PI = ("/", "call_with_time_limit", 2)

PROGRAM = """
:- module(tl, [spin/0, answers/2, first/2, nested/1, inner_caught/1,
               inner_own/1, catch_all/1, err/3, kept/2, attrs/2, db/1,
               t/1, all_t/1, limited_t/1, fails/1, throws/1, retimed/1,
               tiny/1, cleaned/2, plain_cleaned/2, done_list/1, huge/1]).
:- dynamic(fact/1).
:- dynamic(done/1).
:- table(t/1).
spin :- spin(0).
spin(N) :- N1 is N + 1, spin(N1).
busy(0).
busy(N) :- N > 0, N1 is N - 1, busy(N1).
answers(G, L) :- findall(G, call_with_time_limit(5, G), L).
first(X, L) :- findall(X, call_with_time_limit(5, member(X, [a, b, c])), L).
nested(R) :- catch(call_with_time_limit(0.3, call_with_time_limit(30, spin)),
                   E, R = E).
inner_caught(R) :-
    catch(call_with_time_limit(0.3,
              (catch(call_with_time_limit(30, spin), time_limit_exceeded,
                     R = inner),
               true)),
          time_limit_exceeded, R = outer).
inner_own(R) :-
    call_with_time_limit(30,
        catch(call_with_time_limit(0.2, spin), time_limit_exceeded,
              R = inner)).
catch_all(R) :-
    catch(call_with_time_limit(0.3, catch(spin, _, true)),
          time_limit_exceeded, R = outer).
err(T, G, E) :- catch(call_with_time_limit(T, G), error(E, _), true).
kept(X, R) :- catch((X = 1, call_with_time_limit(0.2, spin)), B, R = B).
attrs(X, R) :- catch((dif(X, a), freeze(X, true),
                      call_with_time_limit(0.2, spin)), B, R = B).
db(R) :- catch((assertz(fact(1)), call_with_time_limit(0.2,
                    (assertz(fact(2)), spin))), B, R = B).
t(X) :- member(X, [1, 2, 3]), busy(200000).
all_t(L) :- findall(X, t(X), L).
limited_t(R) :- catch(call_with_time_limit(0.15, all_t(_)), B, R = B).
fails(L) :- findall(x, call_with_time_limit(1, fail), L).
throws(R) :- catch(call_with_time_limit(1, throw(mine)), B, R = B).
tiny(R) :- catch(call_with_time_limit(1.0e-9, spin), B, R = B).
% The cleanup of setup_call_cleanup/3 runs while the ball unwinds: it
% must run to its end, as it does for an ordinary ball.
cleaned(N, R) :- retractall(done(_)),
    catch(call_with_time_limit(0.05,
              setup_call_cleanup(true, spin, (busy(N), assertz(done(N))))),
          B, R = B).
plain_cleaned(N, R) :- retractall(done(_)),
    catch(setup_call_cleanup(true, throw(x), (busy(N), assertz(done(N)))),
          B, R = B).
done_list(L) :- findall(N, done(N), L).
huge(R) :- catch(call_with_time_limit(1.0e300, true), B, R = B), (var(R), R = ok ; nonvar(R)).
retimed(R) :- catch(call_with_time_limit(0.2, spin), B, true),
              call_with_time_limit(1, R = B).
:- end_module(tl).
"""


@pytest.fixture(scope="module")
def tl(tmp_path_factory):
    d = tmp_path_factory.mktemp("cwtl")
    p = d / "tl.clausal"
    p.write_text(textwrap.dedent(PROGRAM))
    return load_clausal_module(str(p))


def first_answer(goal, var, module):
    for _ in solve(goal, module=module):
        return walk(deref(var))
    return "no"


def clean_alarm():
    assert time_limit.live() == ()
    assert signal.getitimer(signal.ITIMER_REAL) == (0.0, 0.0)
    assert signal.getsignal(signal.SIGALRM) in (signal.SIG_DFL, None)


# ── the argument errors (ISO style) ─────────────────────────────────────────


@pytest.mark.parametrize("time_arg,error", [
    (None, "instantiation_error"),
    ("foo", ("type_error", "number", "foo")),
    (("f", 1), ("type_error", "number", ("f", 1))),
    (0, ("domain_error", "positive_number", 0)),
    (-1, ("domain_error", "positive_number", -1)),
    (0.0, ("domain_error", "positive_number", 0.0)),
    (-0.5, ("domain_error", "positive_number", -0.5)),
])
def test_time_must_be_a_positive_number(tl, time_arg, error):
    E = Var()
    t = Var() if time_arg is None else time_arg
    assert first_answer(("err", t, "true", E), E, tl) == error
    clean_alarm()


def test_an_enormous_time_is_no_limit_in_practice(tl):
    """setitimer cannot take 1e300 s or 10**400 s: such a limit is capped
    (at about 31 years), never an OverflowError."""
    R = Var()
    assert first_answer(("huge", R), R, tl) == "ok"
    assert list(solve(("call_with_time_limit", 10 ** 400, "true"),
                      module=tl))
    clean_alarm()


@pytest.mark.parametrize("seconds", [1, 0.5, 2.25])
def test_an_int_or_float_time_runs_the_goal(tl, seconds):
    E = Var()
    assert first_answer(("err", seconds, "true", E), E, tl) != "no"
    clean_alarm()


def test_an_unbound_goal_is_an_instantiation_error(tl):
    E = Var()
    assert first_answer(("err", 1, Var(), E), E, tl) == "instantiation_error"


def test_a_non_callable_goal_is_a_type_error(tl):
    E = Var()
    assert first_answer(("err", 1, 3, E), E, tl) == ("type_error", "callable",
                                                     3)


def test_the_error_context_is_the_predicate_indicator(tl):
    try:
        list(solve(("call_with_time_limit", "x", "true"), module=tl))
    except LogicException as e:
        assert e.term == ("error", ("type_error", "number", "x"), PI)
    else:
        pytest.fail("no error")


# ── once/1 semantics (SWI: "Goal is called as in once/1") ──────────────────


def test_only_the_first_answer(tl):
    L = Var()
    assert first_answer(("first", Var(), L), L, tl) == ["a"]


def test_failure_is_failure(tl):
    L = Var()
    assert first_answer(("fails", L), L, tl) == []
    clean_alarm()


def test_a_ball_of_the_goal_passes_through(tl):
    R = Var()
    assert first_answer(("throws", R), R, tl) == "mine"
    clean_alarm()


# ── the timeout ─────────────────────────────────────────────────────────────


def test_a_timeout_throws_the_bare_ball(tl):
    t0 = time.monotonic()
    with pytest.raises(LogicException) as info:
        list(solve(("call_with_time_limit", 0.2, "spin"), module=tl))
    assert info.value.term == BALL
    assert time.monotonic() - t0 < 0.2 + 0.5
    clean_alarm()


def test_the_ball_is_caught_by_catch_3(tl):
    R = Var()
    assert first_answer(("retimed", R), R, tl) == BALL
    clean_alarm()


@pytest.mark.parametrize("repeat", range(20))
def test_a_limit_due_at_once_is_still_its_own_ball(tl, repeat):
    """An alarm that lands the moment the limit is armed is still owned by
    the call (and so catchable), never an alarm in flight to nobody."""
    R = Var()
    assert first_answer(("tiny", R), R, tl) == BALL
    clean_alarm()


def test_an_outer_deadline_fires_inside_an_inner_call(tl):
    R = Var()
    t0 = time.monotonic()
    assert first_answer(("nested", R), R, tl) == BALL
    assert time.monotonic() - t0 < 0.3 + 0.5
    clean_alarm()


def test_a_catch_around_the_inner_call_does_not_swallow_the_outer(tl):
    R = Var()
    assert first_answer(("inner_caught", R), R, tl) == "outer"
    clean_alarm()


def test_a_catch_all_inside_does_not_swallow_its_own_limit(tl):
    """The alarm is in flight to its owner: no catch/3 between takes it."""
    R = Var()
    assert first_answer(("catch_all", R), R, tl) == "outer"
    clean_alarm()


def test_an_inner_limit_is_its_own_to_catch(tl):
    R = Var()
    t0 = time.monotonic()
    assert first_answer(("inner_own", R), R, tl) == "inner"
    assert time.monotonic() - t0 < 0.2 + 0.5
    clean_alarm()


# ── cleanup while the ball unwinds ──────────────────────────────────────────


@pytest.mark.parametrize("n", [20000, 200000])
def test_cleanup_runs_to_its_end_while_the_ball_unwinds(tl, n):
    """Once the alarm has been raised into the goal (and not swallowed), it
    does not strike again: setup_call_cleanup/3's cleanup completes, as for
    an ordinary ball."""
    R, L = Var(), Var()
    assert first_answer(("plain_cleaned", n, R), R, tl) == "x"
    assert first_answer(("done_list", L), L, tl) == [n]
    R, L = Var(), Var()
    assert first_answer(("cleaned", n, R), R, tl) == BALL
    assert first_answer(("done_list", L), L, tl) == [n]
    clean_alarm()


def test_a_tabled_evaluation_is_closed_cleanly_when_it_times_out(tmp_path):
    """The tabled wrapper's finally (closing its open-table record) runs to
    its end: no "Exception ignored" report, and the tables answer in full."""
    import subprocess
    import sys
    from tests.test_sandbox import ENGINE_ROOT
    (tmp_path / "tab.clausal").write_text(textwrap.dedent("""
        :- module(tab, [lim/2, n/1]).
        :- table(path/2).
        edge(X, Y) :- between(1, 120, X), Y is X + 1.
        edge(120, 1).
        path(X, Y) :- edge(X, Y).
        path(X, Y) :- path(X, Z), edge(Z, Y).
        n(N) :- findall(X-Y, path(X, Y), L), length(L, N).
        lim(T, R) :- catch(call_with_time_limit(T, n(_)), B, R = B).
        :- end_module(tab).
    """))
    (tmp_path / "run.py").write_text(textwrap.dedent("""
        import random
        from clausal import Var, deref, solve
        from clausal.logic.variables import walk
        from clausal.testing import load_clausal_module
        m = load_clausal_module("tab.clausal")
        random.seed(7)
        bad = 0
        for i in range(40):
            R = Var()
            for _ in solve(("lim", random.uniform(0.001, 0.08), R), module=m):
                break
            N = Var()
            got = [walk(deref(N)) for _ in solve(("n", N), module=m)]
            if got != [14520]:   # 120 nodes reach all 121
                bad += 1
                print("GOT", got)
        print("BAD", bad)
    """))
    r = subprocess.run([sys.executable, "run.py"], cwd=tmp_path,
                       env={**__import__("os").environ,
                            "PYTHONPATH": ENGINE_ROOT},
                       capture_output=True, text=True, timeout=300)
    assert "BAD 0" in r.stdout, (r.stdout, r.stderr[-2000:])
    assert "Exception ignored" not in r.stderr, r.stderr[-3000:]


def test_a_swallowed_alarm_still_ends_the_goal(tl):
    """Python code that swallows every exception (a library's ``except
    Exception``) keeps the goal running after the alarm: the alarm strikes
    again until it gets out, and the call throws the ball."""
    from clausal.modules.py import ModulePredicate, simple_to_trampoline
    from clausal.logic.trampoline import DONE  # noqa: F401

    def _stubborn(trail, k):
        while True:
            try:
                sum(range(1000))
            except Exception:  # noqa: BLE001 -- the point of the test
                pass
        yield None
    p = ModulePredicate("stubborn")
    p._register(0, simple_to_trampoline(_stubborn))
    t0 = time.monotonic()
    with pytest.raises(LogicException) as info:
        list(call("call_with_time_limit", 0.2, p, module=tl))
    assert info.value.term == BALL
    assert time.monotonic() - t0 < 0.2 + 1.0
    clean_alarm()


# ── what a timeout undoes: exactly what any ball undoes ────────────────────


def test_bindings_before_the_timeout_are_undone(tl):
    X, R = Var(), Var()
    for _ in solve(("kept", X, R), module=tl):
        assert walk(deref(R)) == BALL
        assert isinstance(deref(X), Var)
        break


def test_attributes_before_the_timeout_are_undone(tl):
    X, R = Var(), Var()
    for _ in solve(("attrs", X, R), module=tl):
        assert walk(deref(R)) == BALL
        # dif(X, a) is gone: X = a succeeds.
        assert list(solve(("=", X, "a"), module=tl))
        break


def test_the_database_is_kept_as_for_any_ball(tl):
    """ISO: assert/retract are not undone by a ball (or backtracking)."""
    R, F = Var(), Var()
    assert first_answer(("db", R), R, tl) == BALL
    got = [walk(deref(F)) for _ in solve(("fact", F), module=tl)]
    assert got == [1, 2]


# ── tabling ─────────────────────────────────────────────────────────────────


def test_a_timeout_mid_tabled_evaluation_leaves_no_complete_partial_table(tl):
    R, L = Var(), Var()
    assert first_answer(("limited_t", R), R, tl) == BALL
    assert first_answer(("all_t", L), L, tl) == [1, 2, 3]
    clean_alarm()


# ── where a limit cannot be enforced ────────────────────────────────────────


def test_off_the_main_thread_it_is_refused(tl):
    out = {}

    def run():
        try:
            out["v"] = list(solve(("call_with_time_limit", 1, "true"),
                                  module=tl))
        except LogicException as e:
            out["e"] = e.term
    th = threading.Thread(target=run)
    th.start()
    th.join()
    assert out["e"] == ("error", ("system_error",
                                  "time_limit_not_main_thread"), PI)


# ── the alarm it found is kept: outer timers and handlers ──────────────────


class _Outer(BaseException):
    pass


def test_an_outer_python_alarm_still_fires_and_is_restored(tl):
    """A SIGALRM timer armed before (the quad runner's, pytest-timeout's):
    its handler runs at its own time, through a longer inner limit."""
    def fire(signum, frame):
        raise _Outer()
    old = signal.signal(signal.SIGALRM, fire)
    try:
        signal.setitimer(signal.ITIMER_REAL, 0.3)
        t0 = time.monotonic()
        with pytest.raises(_Outer):
            list(solve(("call_with_time_limit", 30, "spin"), module=tl))
        assert time.monotonic() - t0 < 0.3 + 0.5
        assert time_limit.live() == ()
        assert signal.getsignal(signal.SIGALRM) is fire
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, old)


def test_an_outer_timer_keeps_its_remaining_time(tl):
    fired = []

    def fire(signum, frame):
        fired.append(time.monotonic())
    old = signal.signal(signal.SIGALRM, fire)
    try:
        signal.setitimer(signal.ITIMER_REAL, 0.6)
        t0 = time.monotonic()
        assert list(solve(("call_with_time_limit", 5, "true"), module=tl))
        assert signal.getsignal(signal.SIGALRM) is fire
        remaining, _ = signal.getitimer(signal.ITIMER_REAL)
        assert 0.3 < remaining <= 0.6
        while not fired and time.monotonic() - t0 < 2:
            time.sleep(0.01)
        assert fired and 0.5 < fired[0] - t0 < 1.0
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, old)


def test_the_quad_runner_keeps_working(tmp_path):
    from clausal import cli
    from clausal.quad_runner import run_quads
    src = textwrap.dedent("""
        spin(N) :- N1 is N + 1, spin(N1).
        ?- call_with_time_limit(1, member(X, [a, b])).
           X = a.
        ?- catch(call_with_time_limit(0.2, spin(0)), B, true).
           B = time_limit_exceeded.
        ?- call_with_time_limit(30, spin(0)).
           false.
    """)
    (tmp_path / "q.pl").write_text(src)
    module = load_clausal_module(str(tmp_path / "q.pl"))
    import io
    out = io.StringIO()
    summary = run_quads(module, src, cli._goal_reader_ops(src), "q.pl",
                        out=out, timeout=0.6)
    text = out.getvalue()
    assert summary.count("passed") == 2, text
    assert summary.count("failed") == 1 and "no answer within 0.6" in text
    clean_alarm()


def test_the_test_runner_keeps_working(tmp_path):
    """A .clausal file's test/1 clauses that use the limit, run by
    ``clausal --test`` (the test runner's own SIGALRM watchdog included)."""
    import os
    import subprocess
    import sys
    from tests.test_sandbox import ENGINE_ROOT
    (tmp_path / "w.clausal").write_text(textwrap.dedent("""
        :- module(w, []).
        spin(N) :- N1 is N + 1, spin(N1).
        test(first) :- call_with_time_limit(1, member(X, [a, b])), X == a.
        test(timeout) :- catch(call_with_time_limit(0.2, spin(0)), B, true),
                         B == time_limit_exceeded.
        test(wrong) :- call_with_time_limit(1, member(X, [a, b])), X == b.
        :- end_module(w).
    """))
    env = dict(os.environ, PYTHONPATH=ENGINE_ROOT)
    r = subprocess.run([sys.executable, "-m", "clausal", "w.clausal",
                        "--test"], cwd=tmp_path, env=env,
                       capture_output=True, text=True, timeout=120)
    out = r.stdout + r.stderr
    assert "2 passed" in out and "1 failed" in out, out


# ── the seam surface ────────────────────────────────────────────────────────


SEAM_SURFACE_RUNNER = """
import faulthandler, importlib, resource, sys, time
from clausal import Var, deref, solve
from clausal.logic.variables import walk
faulthandler.dump_traceback_later(60, exit=True)   # where a runaway spins
sys.path.insert(0, ".")
m = importlib.import_module("tls")
X = Var()
print("ONE", [walk(deref(X)) for _ in solve(("one", X), module=m)])
B = Var(); t0 = time.monotonic()
for _ in solve(("timed", B), module=m):
    print("TIMED", walk(deref(B)), round(time.monotonic() - t0, 2))
    break
"""


def test_the_seam_surface(tmp_path):
    """In a child capped at 4 GB: the seam's spin/1 builds an ever-deeper
    term (the seam's ``is`` unifies), about 45 MB/s, so a limit that failed
    to stop it would take the whole pytest process to the OOM killer
    (SIGKILL, no report) -- as a full-suite gate once died here.  In a child
    it is a named failure with a traceback instead."""
    import os
    import resource
    import subprocess
    import sys
    from tests.test_sandbox import ENGINE_ROOT
    (tmp_path / "tls.seam").write_text(textwrap.dedent("""
        -module(tls, [one/1, timed/1])
        -private([a, b])
        spin(N) <- (N1 is N + 1, spin(N1))
        one(X) <- call_with_time_limit(1, member(X, [a, b]))
        timed(B) <- catch(call_with_time_limit(0.2, spin(0)), B, True)
    """))
    (tmp_path / "run.py").write_text(textwrap.dedent(SEAM_SURFACE_RUNNER))

    def cap():
        resource.setrlimit(resource.RLIMIT_AS, (4 << 30, 4 << 30))
    r = subprocess.run([sys.executable, "run.py"], cwd=tmp_path,
                       capture_output=True, text=True, timeout=120,
                       preexec_fn=cap,
                       env={**os.environ, "PYTHONPATH": ENGINE_ROOT})
    assert r.returncode == 0, (r.returncode, r.stdout, r.stderr[-4000:])
    assert "ONE ['a']" in r.stdout, r.stdout
    assert f"TIMED {BALL}" in r.stdout, r.stdout

# ── the per-call budget's delegation (time_limit.budgeted) ─────────────────


def test_every_throw_into_a_budgeted_generator_reaches_it():
    """budgeted() is ``yield from`` with a clock: a ball thrown into it a
    second time is handed to the generator too, not raised past it."""
    seen = []

    def gen():
        i = 0
        while i < 4:
            try:
                yield ("step", i)
            except ValueError as e:
                seen.append(str(e))
                continue
            i += 1
    g = time_limit.budgeted(gen(), 10.0, "g/0")
    assert next(g) == ("step", 0)
    assert g.throw(ValueError("one")) == ("step", 0)
    assert g.throw(ValueError("two")) == ("step", 0)
    assert seen == ["one", "two"]
    assert g.send(None) == ("step", 1)
    g.close()
    clean_alarm()


# ── the escalation path (review of the swallowed-alarm handling) ────────────

ESC_PROGRAM = """
:- module(esc, [a/2, c/2, c2/2]).
spin :- spin(0).
spin(N) :- N1 is N + 1, spin(N1).
a(P, R) :- catch(call_with_time_limit(0.1, (call(P), spin)), B, R = caught(B)).
c(P, R) :- catch(call_with_time_limit(0.1, catch(call(P), _, spin)), B,
                 R = caught(B)).
c2(P, R) :- catch(call_with_time_limit(0.1, (catch(call(P), E, true), spin)),
                  B, R = caught(B-E)).
:- end_module(esc).
"""

ESC_RUNNER = """
import sys, time
from clausal import Var, deref, call
from clausal.logic.variables import walk
from clausal.modules.py import ModulePredicate, simple_to_trampoline
from clausal.testing import load_clausal_module
m = load_clausal_module("esc.clausal")

def swallow(trail, k):      # the alarm at 0.1 s lands here, is dropped
    t0 = time.monotonic()
    while time.monotonic() - t0 < 0.13:
        try:
            sum(range(200))
        except Exception:
            pass
    yield None

def convert(trail, k):      # the alarm becomes a ValueError (its __context__)
    try:
        t0 = time.monotonic()
        while time.monotonic() - t0 < 0.13:
            sum(range(200))
    except Exception:
        raise ValueError("converted")
    yield None

preds = {}
for n, f in (("swallow", swallow), ("convert", convert)):
    p = ModulePredicate(n); p._register(0, simple_to_trampoline(f)); preds[n] = p
def norm(t):
    if isinstance(t, (tuple, list)):
        return type(t)(norm(a) for a in t)
    return "_" if type(t).__name__.endswith("Var") else t

goal, pred = sys.argv[1], sys.argv[2]
for i in range(int(sys.argv[3])):
    R = Var(); t0 = time.monotonic()
    try:
        got = [norm(walk(deref(R)))
               for _ in call(goal, preds[pred], R, module=m)]
    except BaseException as e:
        got = "UNCAUGHT " + type(e).__name__ + " " + str(e)[:60]
    print("RESULT", repr(got), round(time.monotonic() - t0, 2), flush=True)
"""


def _esc(tmp_path, goal, pred, runs=5):
    import os
    import subprocess
    import sys
    from tests.test_sandbox import ENGINE_ROOT
    (tmp_path / "esc.clausal").write_text(textwrap.dedent(ESC_PROGRAM))
    (tmp_path / "run.py").write_text(textwrap.dedent(ESC_RUNNER))
    try:
        r = subprocess.run([sys.executable, "run.py", goal, pred, str(runs)],
                           cwd=tmp_path, capture_output=True, text=True,
                           env={**os.environ, "PYTHONPATH": ENGINE_ROOT},
                           timeout=60)
    except subprocess.TimeoutExpired as e:
        pytest.fail(f"hung: the limit was defeated ({e.stdout!r})")
    lines = [ln.split(" ", 1)[1] for ln in r.stdout.splitlines()
             if ln.startswith("RESULT ")]
    assert len(lines) == runs, (r.stdout, r.stderr[-2000:])
    assert "Exception ignored" not in r.stderr, r.stderr[-2000:]
    return [(eval(ln.rsplit(" ", 1)[0]), float(ln.rsplit(" ", 1)[1]))
            for ln in lines]


def test_after_a_swallowed_alarm_catch_3_still_catches_the_ball(tmp_path):
    """A Python predicate drops the first alarm and returns; the second
    strikes in plain engine code (spin), where it must still be routed to
    its call and so to the user's catch/3."""
    for got, secs in _esc(tmp_path, "a", "swallow"):
        assert got == [("caught", BALL)]
        assert secs < 0.13 + 1.0


@pytest.mark.parametrize("goal,want", [
    ("c", [("caught", BALL)]),
    ("c2", "c2"),
])
def test_an_alarm_turned_into_another_exception_is_still_the_timeout(
        tmp_path, goal, want):
    """Python code turns the alarm into a ValueError (whose __context__ is
    the alarm): the timeout is the outcome, not the ValueError, and the
    goal does not run on unlimited."""
    for got, secs in _esc(tmp_path, goal, "convert", runs=3):
        if want == "c2":
            # catch(call(P), E, true) does not take the timeout either: E
            # is left unbound, and the outer catch gets the ball.
            assert got == [("caught", ("-", BALL, "_"))], got
        else:
            assert got == want
        assert secs < 0.13 + 1.0


# ── the alarm invariant: never an armed timer without a Python handler ─────

ORPHAN_RUNNER = """
import signal, sys, time
from clausal import solve
from clausal.logic import time_limit
from clausal.testing import load_clausal_module
m = load_clausal_module("tl.clausal")
# A limit whose frame an unrouted exception skipped is left on the stack ...
d1 = time_limit.push(30.0, "orphan")
# ... and the code that owned SIGALRM before takes it back, as the quad
# runner's or the test runner's watchdog's disarm does.
signal.setitimer(signal.ITIMER_REAL, 0)
signal.signal(signal.SIGALRM, signal.SIG_DFL)
# The next limit must still be enforced by a Python handler.
try:
    list(solve(("call_with_time_limit", 0.1, "spin"), module=m))
    print("NO BALL")
except Exception as e:
    print("BALL", getattr(e, "term", e))
print("TIMER", signal.getitimer(signal.ITIMER_REAL),
      "HANDLER", signal.getsignal(signal.SIGALRM), flush=True)
time.sleep(0.3)        # an armed timer with SIG_DFL would kill us here
time_limit.pop(d1)     # the orphan's late pop changes nothing
print("TIMER2", signal.getitimer(signal.ITIMER_REAL),
      "HANDLER2", signal.getsignal(signal.SIGALRM), flush=True)
time.sleep(0.2)
print("ALIVE", flush=True)
"""


def test_an_orphaned_limit_never_leaves_a_default_handler_armed(tmp_path):
    """A limit left on the stack after another component took SIGALRM back
    (a skipped frame) must not make the next limit arm the timer under
    SIG_DFL: SIGALRM's default action ends the process, silently ("Alarm
    clock"), as a full-suite run once ended."""
    import os
    import subprocess
    import sys
    from tests.test_sandbox import ENGINE_ROOT
    (tmp_path / "tl.clausal").write_text(textwrap.dedent(PROGRAM))
    (tmp_path / "run.py").write_text(textwrap.dedent(ORPHAN_RUNNER))
    r = subprocess.run([sys.executable, "run.py"], cwd=tmp_path,
                       capture_output=True, text=True, timeout=60,
                       env={**os.environ, "PYTHONPATH": ENGINE_ROOT})
    assert r.returncode == 0, (r.returncode, r.stdout, r.stderr[-1500:])
    assert f"BALL {BALL}" in r.stdout, r.stdout
    assert "TIMER (0.0, 0.0) HANDLER 0" in r.stdout, r.stdout
    assert "TIMER2 (0.0, 0.0) HANDLER2 0" in r.stdout
    assert "ALIVE" in r.stdout


def test_the_suite_s_tripwire_names_a_leaked_alarm(tmp_path):
    """tests/conftest.py's tripwire fails the test that leaves ITIMER_REAL
    armed under SIG_DFL (and disarms it), instead of the run dying."""
    import os
    import subprocess
    import sys
    conftest = os.path.join(os.path.dirname(__file__), "conftest.py")
    with open(conftest, encoding="utf-8") as f:
        text = f.read()
    tripwire = text[text.index("# ── the SIGALRM tripwire"):]
    (tmp_path / "conftest.py").write_text("import sys\nimport pytest\n"
                                          + tripwire)
    (tmp_path / "test_leak.py").write_text(textwrap.dedent("""
        import signal
        def test_leaks():
            signal.signal(signal.SIGALRM, signal.SIG_DFL)
            signal.setitimer(signal.ITIMER_REAL, 0.5)
        def test_after():
            import time
            time.sleep(1.0)          # the leaked timer would have killed us
            assert signal.getitimer(signal.ITIMER_REAL) == (0.0, 0.0)
    """))
    r = subprocess.run([sys.executable, "-m", "pytest", "-q",
                        "-p", "no:cacheprovider", "--rootdir", str(tmp_path),
                        str(tmp_path)], cwd=tmp_path, capture_output=True,
                       text=True, timeout=120)
    out = r.stdout + r.stderr
    assert r.returncode == 1, (r.returncode, out[-2000:])
    assert "test_leaks left a SIGALRM hazard" in out, out[-2000:]
    assert "2 passed, 1 error" in out, out[-2000:]
