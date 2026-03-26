# Control

Control predicates manage execution flow — forcing determinism, measuring
performance, and controlling search.

---

## Determinism

### Once/1

`Once(Goal)` — call `Goal` and commit to the first solution. Prevents
backtracking into the goal.

```clausal
Test("first only") <- (
    Once(In(X, [1, 2, 3])),
    X == 1
)
```

`Once` is useful when you know a predicate has multiple solutions but you only
want the first:

```clausal
any_member(ELEM, LIST) <- Once(In(ELEM, LIST))

Test("any") <- (any_member(X, [10, 20, 30]), X == 10)
```

---

## Timing

### TimeGoal/1

`TimeGoal(Goal)` — execute `Goal` and print wall-clock and CPU time to stderr.
The goal's solutions pass through unchanged.

```clausal
# skip
Test("time") <- TimeGoal(Append([1, 2], [3, 4], _))
```

Output (to stderr):

```
Wall: 0.000123s  CPU: 0.000098s
```

### TimeGoal/2

`TimeGoal(Goal, Elapsed)` — execute `Goal` and unify `Elapsed` with the
wall-clock time in seconds (as a float). Useful for programmatic benchmarking.

```clausal
# skip
Test("measure") <- (
    TimeGoal(Length(LIST, 1000), SECS),
    SECS < 1.0
)
```

---

## Patterns & Recipes

### Benchmark two approaches

```clausal
# skip
compare_approaches(GOAL_A, GOAL_B) <- (
    TimeGoal(GOAL_A, TIME_A),
    TimeGoal(GOAL_B, TIME_B),
    FASTER == (TIME_A < TIME_B),
    Writeln(f"A: {TIME_A}s, B: {TIME_B}s")
)
```

### Guard with Once

Prevent a test predicate from generating multiple successes:

```clausal
Test("exactly one solution") <- Once(
    Permutation([1, 2, 3], [3, 2, 1])
)
```

---

## Gotchas

- **`Once` cuts all choice points** — it does not just skip one alternative, it
  commits fully. Side effects from the first solution will have happened.
- **`TimeGoal/1` prints to stderr** — not stdout. It won't interfere with
  `Write`/`Writeln` output.
- **`TimeGoal/2` measures wall time** — on a loaded system, wall time may be
  higher than CPU time. Use `/1` to see both.

---

*See also: [If-Then-Else](reified_ite.md) — committed choice with `=>`,
[Tabling](tabling.md) — automatic memoization for performance,
[Exception Handling](exceptions.md) — catch/throw for error control flow.*
