# Control

Control predicates manage execution flow — forcing determinism, measuring
performance, and controlling search. For delayed execution, see
[Coroutining](coroutining.md).

---

## Determinism

### once/1

`once(Goal)` — call `Goal` and commit to the first solution. Prevents
backtracking into the goal.

```seam
test("first only") <- (
    once(in_(X, [1, 2, 3])),
    X == 1
)
```

`once` is useful when you know a predicate has multiple solutions but you only
want the first:

```seam
any_member(ELEM, LIST) <- once(in_(ELEM, LIST))

test("any") <- (any_member(X, [10, 20, 30]), X == 10)
```

---

## Timing

### time_goal/1

`time_goal(Goal)` — execute `Goal` and print the solution count, wall-clock
and CPU time to stderr. The goal's solutions pass through unchanged; the line
is printed once `Goal` is **exhausted**, so a caller that stops at the first
solution (`once`, an `if --` seam) prints nothing.

```seam
--8<-- "tests/fixtures/docs/control_sigs.txt:time_goal_1"
```

Output (to stderr):

```
# 1 solution(s), 0.000123s wall, 0.000098s CPU
```

### time_goal/2

`time_goal(Goal, Elapsed)` — execute `Goal` and unify `Elapsed` with the
wall-clock time in seconds (as a float). Useful for programmatic benchmarking.

```seam
--8<-- "tests/fixtures/docs/control_sigs.txt:time_goal_2"
```

---

## Patterns & Recipes

### Benchmark two approaches

```seam
--8<-- "tests/fixtures/docs/control_sigs.txt:benchmark_recipe"
```

### Guard with once

Prevent a test predicate from generating multiple successes:

```seam
test("exactly one solution") <- once(
    permutation([1, 2, 3], [3, 2, 1])
)
```

---

## Gotchas

- **`once` commits to the first solution** — it discards every remaining
  alternative of `Goal`, not just the next one. Side effects from the first
  solution will have happened. (Clausal has no cut; `once/1` is the ISO
  construct for committing.)
- **`time_goal/1` prints to stderr** — not stdout. It won't interfere with
  [write/writeln](io.md) output.
- **`time_goal/2` measures wall time** — on a loaded system, wall time may be
  higher than CPU time. Use `/1` to see both.

---

*See also: [If-Then-Else](reified_ite.md) — `if_/3` and the reified conditionals,
[Tabling](tabling.md) — automatic memoization for performance,
[Exception Handling](exceptions.md) — catch/throw for error control flow.*
