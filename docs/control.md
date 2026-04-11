# Control

Control predicates manage execution flow — forcing determinism, measuring
performance, and controlling search. For delayed execution, see
[Coroutining](coroutining.md).

---

## Determinism

### once/1

`once(Goal)` — call `Goal` and commit to the first solution. Prevents
backtracking into the goal.

```clausal
Test("first only") <- (
    once(in_(X, [1, 2, 3])),
    X == 1
)
```

`once` is useful when you know a predicate has multiple solutions but you only
want the first:

```clausal
any_member(ELEM, LIST) <- once(in_(ELEM, LIST))

Test("any") <- (any_member(X, [10, 20, 30]), X == 10)
```

---

## Timing

### time_goal/1

`time_goal(Goal)` — execute `Goal` and print wall-clock and CPU time to stderr.
The goal's solutions pass through unchanged.

```clausal
--8<-- "tests/fixtures/docs/control_sigs.txt:time_goal_1"
```

Output (to stderr):

```
Wall: 0.000123s  CPU: 0.000098s
```

### time_goal/2

`time_goal(Goal, Elapsed)` — execute `Goal` and unify `Elapsed` with the
wall-clock time in seconds (as a float). Useful for programmatic benchmarking.

```clausal
--8<-- "tests/fixtures/docs/control_sigs.txt:time_goal_2"
```

---

## Patterns & Recipes

### Benchmark two approaches

```clausal
--8<-- "tests/fixtures/docs/control_sigs.txt:benchmark_recipe"
```

### Guard with once

Prevent a test predicate from generating multiple successes:

```clausal
Test("exactly one solution") <- once(
    permutation([1, 2, 3], [3, 2, 1])
)
```

---

## Gotchas

- **`once` cuts all choice points** — it does not just skip one alternative, it
  commits fully. Side effects from the first solution will have happened.
- **`time_goal/1` prints to stderr** — not stdout. It won't interfere with
  [write/writeln](io.md) output.
- **`time_goal/2` measures wall time** — on a loaded system, wall time may be
  higher than CPU time. Use `/1` to see both.

---

*See also: [If-Then-Else](reified_ite.md) — committed choice with `=>`,
[Tabling](tabling.md) — automatic memoization for performance,
[Exception Handling](exceptions.md) — catch/throw for error control flow.*
