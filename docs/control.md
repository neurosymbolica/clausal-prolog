# Control

Control predicates manage execution flow — forcing determinism, measuring
performance, and controlling search. For delayed execution, see
[Coroutining](coroutining.md).

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

```seam
test("first only") <- (
    once(in_(X, [1, 2, 3])),
    X == 1
)
```

`once` is what you reach for when you know a predicate has multiple solutions
but you only want the first:

```seam
any_member(ELEM, LIST) <- once(in_(ELEM, LIST))

test("any") <- (any_member(X, [10, 20, 30]), X == 10)
```

The cut-free alternative is to write the predicate so it has only the one
solution you want:

```seam
first_member(X, [X, *_]),

test("first") <- (first_member(X, [10, 20, 30]), X == 10)
```

and, where `once` stood in for a condition (`( Cond -> Then ; Else )`),
`if_/3` with a reified condition such as `memberd_t`:

```seam
-import_from(clausal.stdlib.reif, [memberd_t])
-private([yes, no])
listed(X, XS, R) <- if_(memberd_t(X, XS), R is yes, R is no)

test("listed") <- (listed(2, [1, 2, 3], yes), listed(9, [1, 2, 3], no))
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

### Guard a test

A test passes when its body has a solution, so there is nothing to guard:
call the predicate with its inputs and its expected output, and no `once` is
needed.

```seam
test("a permutation") <- permutation([1, 2, 3], [3, 2, 1])
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
