# Control

Control predicates manage execution flow — forcing determinism, measuring
performance, limiting time, and controlling search. For delayed execution, see
[Coroutining](coroutining.md).

Examples on this page are [Clausal Prolog](clausal_prolog.md)
(`.clausal`): ISO Prolog syntax, without cut. (The [seam](syntax.md),
Clausal's Python-syntax surface, spells the same goals in Python syntax.)

---

## Determinism

### once/1

`once(Goal)` — call `Goal` and commit to the first solution. Prevents
backtracking into the goal.

!!! warning "Supported but discouraged"

    `once/1` is a **transition construct**, like `\+` and `forall/2`: it works
    and will keep working while it is phased out, but it commits to a first
    solution, which gives up monotonicity (adding a constraint can lose the
    answer you wanted). Prefer a predicate that is deterministic by
    construction, or [`if_/3`](reified_ite.md) with a reifiable condition.
    Both are shown below.

```clausal
test("first only") :-
    once(in_(X, [1, 2, 3])),
    X == 1.
```

`once` is what you reach for when you know a predicate has multiple solutions
but you only want the first:

```clausal
any_member(ELEM, LIST) :-
    once(in_(ELEM, LIST)).

test("any") :-
    any_member(X, [10, 20, 30]),
    X == 10.
```

The cut-free alternative is to write the predicate so it has only the one
solution you want:

```clausal
first_member(X, [X|_]).

test("first") :-
    first_member(X, [10, 20, 30]),
    X == 10.
```

and, where `once` stood in for a condition (`( Cond -> Then ; Else )`),
`if_/3` with a reified condition such as `memberd_t`:

```clausal
:- use_module(library(reif)).

listed(X, XS, R) :-
    if_(memberd_t(X, XS), R = yes, R = no).

test("listed") :-
    listed(2, [1, 2, 3], yes),
    listed(9, [1, 2, 3], no).
```

---

## Timing

### time_goal/1

`time_goal(Goal)` — execute `Goal` and print the solution count, wall-clock
and CPU time to stderr. The goal's solutions pass through unchanged; the line
is printed once `Goal` is **exhausted**, so a caller that stops at the first
solution (`once`, or an `if --` goal in a seam file) prints nothing.

```clausal
--8<-- "tests/fixtures/docs/control_sigs.txt:time_goal_1"
```

Output (to stderr):

```
# 1 solution(s), 0.000123s wall, 0.000098s CPU
```

### time_goal/2

`time_goal(Goal, Elapsed)` — execute `Goal` and unify `Elapsed` with the
wall-clock time in seconds (as a float). Useful for programmatic benchmarking.

```clausal
--8<-- "tests/fixtures/docs/control_sigs.txt:time_goal_2"
```

### call_with_time_limit/2

`call_with_time_limit(Time, Goal)` — run `Goal` as [`once/1`](#once1) does
(its first answer; its choice points are discarded), but if it has not
answered after `Time` seconds of wall-clock time, throw the ball
`time_limit_exceeded`. This is SWI-Prolog's `call_with_time_limit/2`
(library(time)), with SWI's ball: the one existing Prolog code catches.
A timeout is never a failure.

```clausal
spin(N) :- N1 is N + 1, spin(N1).

test("first answer only") :-
    findall(X, call_with_time_limit(1, member(X, [a, b, c])), XS),
    XS == [a].

test("a goal that runs out throws the ball") :-
    catch(call_with_time_limit(0.2, spin(0)), BALL, true),
    BALL == time_limit_exceeded.
```

- **`Time`** is a number of seconds, an integer or a float, greater than 0.
  Unbound: `instantiation_error`. Not a number:
  `type_error(number, Time)`. Zero or less:
  `domain_error(positive_number, Time)`.
- **`Goal`** is run as `call/1` runs it, with call/1's errors.
- **Nesting.** An inner limit never extends an outer one: the earlier
  deadline wins. When the OUTER deadline passes while an inner call runs,
  the outer call throws, and no `catch/3` on the way takes the alarm — not
  one around the inner call, not a catch-all inside the goal. Only the
  call whose deadline passed throws `time_limit_exceeded`; from there on it
  is an ordinary ball. (SWI-Prolog throws the same ball from wherever the
  alarm lands, so a catch-all inside the goal can take it there.)
- **What a timeout undoes** is what any ball undoes, at the `catch/3` that
  takes it: bindings and constraints made since are undone; `assertz` and
  `retract` are not (ISO). A tabled evaluation cut short leaves no table
  that a later call reads as complete.
- **Cleanup runs to its end.** Once the alarm is on its way out, it is
  not raised again: a `setup_call_cleanup/3` cleanup, a `finally` in Python
  code and a tabled evaluation's close run to completion, as for any other
  ball (SWI-Prolog does the same).
- **A swallowed alarm.** If Python code inside the goal catches the alarm
  and drops it (a library's `except Exception`), it strikes again 50 ms
  later: inside a Python predicate in a form `except Exception` does not
  catch, elsewhere as the ordinary alarm, so either way it reaches its call
  and every `catch/3` around that call can take the ball. If Python code
  turns the alarm into another error (`except Exception: raise
  ValueError(...)`), the timeout is the outcome where that error is
  converted or caught. The call throws the ball whatever the goal then
  answered: a result produced after the alarm struck is not trusted.
  (Python code that catches the alarm and keeps a reference to it, in a
  list say, is taken to be still unwinding; the goal then runs on until it
  returns, and its call throws the ball.)
- **A huge `Time`** (`1.0e300`, `10**400`) is capped at 10^9 seconds
  (about 31 years), which is no limit in practice.
- **Main thread only.** The limit is enforced with `SIGALRM`, which only
  the main thread receives. In another thread, or on a platform without
  `SIGALRM`, the call is refused with
  `error(system_error(time_limit_not_main_thread), call_with_time_limit/2)`
  (`time_limit_no_alarm` without `SIGALRM`); it never runs unlimited.
- **Alarms already set** (the quad runner's, the test runner's,
  pytest-timeout's) keep working: while a limit is active the earliest of
  all deadlines is armed, an outer timer's handler runs at its own time,
  and the handler and the time left are restored when the last limit ends.
- **Granularity.** The alarm lands between Python bytecodes: a long call
  into C (a huge integer multiplication, a regular expression) finishes
  before the ball is thrown.

The [sandbox](sandbox.md#vetted-package-adapters) uses the same mechanism,
and the same ball, for the per-call budget of a vetted package adapter.

---

## Patterns & Recipes

### Benchmark two approaches

```clausal
--8<-- "tests/fixtures/docs/control_sigs.txt:benchmark_recipe"
```

### Guard a test

A test passes when its body has a solution, so there is nothing to guard:
call the predicate with its inputs and its expected output, and no `once` is
needed.

```clausal
test("a permutation") :-
    permutation([1, 2, 3], [3, 2, 1]).
```

---

## Gotchas

- **`once` commits to the first solution** — it discards every remaining
  alternative of `Goal`, not just the next one. Side effects from the first
  solution will have happened. Clausal Prolog has no cut, and `once/1` is a
  supported but discouraged transition construct (it is ISO's committing
  construct, and is being phased out here); see the alternatives above.
- **`time_goal/1` prints to stderr** — not stdout. It won't interfere with
  [write/writeln](io.md) output.
- **`time_goal/2` measures wall time** — on a loaded system, wall time may be
  higher than CPU time. Use `/1` to see both.

---

*See also: [If-Then-Else](reified_ite.md) — `if_/3` and the reified conditionals,
[Tabling](tabling.md) — automatic memoization for performance,
[Exception Handling](exceptions.md) — catch/throw for error control flow.*
