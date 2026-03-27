# Coroutining & Resource Control

Clausal provides coroutining primitives for delayed goal execution and deterministic resource management. These predicates enable:

- **Delayed goals** — postpone execution until a variable is bound (`freeze/2`, `when/2`)
- **Resource cleanup** — guarantee cleanup runs regardless of success, failure, or exceptions (`setup_call_cleanup/3`, `call_cleanup/2`)
- **Solution control** — skip to the Nth solution or count solutions efficiently (`call_nth/2`, `count_all/2`)

All predicates in this module are **compiler special forms** — they are compiled inline at compile time (like `once/1`, `findall/3`, and `catch/3`), and can be freely nested inside any other meta-predicate.

---

## freeze/2

```clausal
# skip
freeze(X, Goal)
```

Delay `Goal` until variable `X` is bound.

- If `X` is already bound at the time `freeze` is executed, `Goal` runs **immediately**.
- If `X` is unbound, `Goal` is stored as an attributed variable attribute. when `X` is later unified with a value, the frozen goal fires **synchronously** — if the goal succeeds, the unification succeeds; if the goal fails, the unification **fails** (is rejected).

Multiple freezes on the same variable accumulate. All fire when the variable is bound. Backtracking undoes the attribute (the freeze is removed if the trail is unwound).

```clausal
# skip
# Guard: X must be positive when bound
Guarded(X) <- (
    freeze(X, X > 0),
    X is 5
)
# succeeds — 5 > 0

Rejected(X) <- (
    freeze(X, X > 0),
    X is -1
)
# fails — the unification X = -1 is rejected because -1 > 0 fails
```

```clausal
# skip
# Deferred binding
Deferred(Y) <- (
    freeze(X, Y is X),
    X is "hello"
)
# Y = "hello" — the frozen goal Y is X fires when X is bound

# Multiple freezes on the same variable
Multi(Y, Z) <- (
    freeze(X, Y is X),
    freeze(X, Z is X),
    X is 42
)
# Y = 42, Z = 42
```

??? info "Implementation"
    freeze uses the attributed variable hook infrastructure (the same mechanism used by [`dif/2`](constraints.md), [CLP(ℤ)](constraints.md), and [CLP(B)](clpb.md)). The frozen goal is compiled as a closure (zero-arg generator factory) and stored under the `"freeze"` attribute key. The hook drives the generator synchronously — no wakeup queue is needed.

    **Implementation:** `clausal/logic/compiler.py` (`_compile_freeze`), `clausal/logic/coroutining.py` (`_freeze_hook`)

---

## when/2

```clausal
# skip
when(Condition, Goal)
```

Generalized coroutining: delay `Goal` until `Condition` is satisfied.

### Supported conditions

| Condition | Meaning |
|---|---|
| `nonvar(X)` | X is bound (equivalent to `freeze(X, Goal)`) |
| `ground(X)` | X is fully ground (no unbound variables anywhere in X) |
| `(C1, C2)` | Conjunction: both C1 and C2 must be satisfied |
| `(C1 ; C2)` | Disjunction: either C1 or C2 suffices |

```clausal
# skip
# equivalent to freeze(X, Goal)
Test("when isbound") <- (
    when(nonvar(X), Y is X),
    X is 42,
    Y is 42
)

# Conjunction: fire when both X and Y are bound
Test("when conjunction") <- (
    when((nonvar(X), nonvar(Y)), R is "done"),
    X is 1,
    Y is 2,
    R is "done"
)

# ground: fire when term is fully ground
Test("when ground") <- (
    when(ground([X, Y]), R is "all ground"),
    X is 1,
    Y is 2,
    R is "all ground"
)
```

### How conditions decompose

- `when(nonvar(X), Goal)` compiles directly as `freeze(X, Goal)` — zero overhead.
- `when((C1, C2), Goal)` decomposes to `when(C1, when(C2, Goal))` — the inner when is installed when C1 is satisfied.
- `when(ground(X), Goal)` freezes on every unbound variable in X. when any is bound, groundness is re-checked. The goal fires when X is fully ground.
- `when((C1 ; C2), Goal)` attaches to variables in both conditions. Whichever fires first runs the goal (at most once).

??? info "Implementation"
    Compile-time dispatch handles `nonvar` and conjunction. Runtime helpers in `clausal/logic/coroutining.py` handle `ground` and disjunction.

    **Implementation:** `clausal/logic/compiler.py` (`_compile_when`), `clausal/logic/coroutining.py` (`_install_when_ground`, `_install_when_disjunction`, `_install_when_condition`)

---

## setup_call_cleanup/3

```clausal
# skip
setup_call_cleanup(Setup, Call, Cleanup)
```

Deterministic resource management — the logic programming equivalent of `try/finally`.

1. **Setup** runs first (must succeed deterministically; only the first solution is taken).
2. **Call** runs normally (may succeed zero or more times, fail, or throw).
3. **Cleanup** runs **exactly once**, regardless of how Call terminates:
   - After all solutions of Call have been enumerated
   - If Call fails (Cleanup runs, then the whole goal fails)
   - If Call throws an exception (Cleanup runs, then the exception is re-raised)

If **Setup fails**, the whole goal fails and Cleanup does **not** run.

```clausal
# skip
# Basic pattern: open/use/close
ProcessFile(PATH, RESULT) <- setup_call_cleanup(
    HANDLE is ++open(PATH),
    (DATA is ++HANDLE.read(), RESULT is DATA),
    ++HANDLE.close()
)

# Call fails — Cleanup still runs, overall fails
Test("scc call fails") <- (
    not setup_call_cleanup(
        S is 1,
        in_(X, []),
        C is 3
    )
)
```

---

## call_cleanup/2

```clausal
# skip
call_cleanup(Call, Cleanup)
```

Sugar for `setup_call_cleanup(true, Call, Cleanup)` — no setup step, just guaranteed cleanup.

```clausal
# skip
SafeQuery(GOAL) <- call_cleanup(
    call_goal(GOAL),
    writeln("query finished")
)
```

---

## call_nth/2

```clausal
# skip
call_nth(+Goal, +N)
```

Call `Goal` and succeed only on the **Nth solution**. The first N-1 solutions are skipped.

- `N` must be a positive integer (>= 1). Raises `type_error(positive_integer, N, "call_nth/2")` otherwise.
- If Goal has fewer than N solutions, `call_nth` fails.
- Only the Nth solution's bindings are visible to the continuation.

```clausal
# skip
# Get the 3rd member
Test("third") <- (
    call_nth(in_(X, [10, 20, 30, 40, 50]), 3),
    X is 30
)

# N exceeds available solutions — fails
Test("too few") <- (
    not call_nth(in_(X, [1, 2]), 5)
)
```

---

## count_all/2

```clausal
# skip
count_all(+Goal, -Count)
```

Count the number of solutions of `Goal` without collecting them. Unifies `Count` with the integer result.

Unlike [findall](meta_predicates.md) + `length`, `count_all` does not build a list — it just counts. Bindings from the inner goal are **not** visible after counting (the trail is unwound).

```clausal
# skip
# Count members
Test("count") <- (
    count_all(in_(X, ["a", "b", "c", "d"]), N),
    N is 4
)

# No solutions — 0
Test("empty") <- (
    count_all(in_(X, []), N),
    N is 0
)

# With filter
Test("filtered") <- (
    count_all((in_(X, [1, 2, 3, 4, 5]), X > 3), N),
    N is 2
)
```

---

## Nesting inside meta-predicates

All Phase 1 predicates are compiler special forms that compile their goal arguments inline. They nest freely inside other meta-predicates — [findall](meta_predicates.md), [once](control.md), [catch](exceptions.md), [forall](meta_predicates.md), and each other:

```clausal
# skip
# findall wrapping call_nth
Test("findall+callnth") <- (
    findall(X, call_nth(in_(X, [10, 20, 30]), 2), BAG),
    BAG is [20]
)

# catch wrapping call_nth with bad N
Test("catch+callnth") <- (
    catch(
        call_nth(in_(X, [1, 2, 3]), 0),
        _,
        R is "caught"
    ),
    R is "caught"
)

# freeze inside findall
Test("findall+freeze") <- (
    findall(
        Y,
        (freeze(X, Y is X), X is 99),
        BAG
    ),
    BAG is [99]
)

# count_all inside findall
Test("findall+countall") <- (
    findall(
        N,
        count_all(in_(X, ["a", "b", "c"]), N),
        BAG
    ),
    BAG is [3]
)
```

---

??? info "Test coverage"

    Tests are in `tests/test_coroutining.py` (51 tests) and
    `tests/fixtures/coroutining.clausal` (20 tests).

    - **call_nth**: basic, first/last, too few solutions, N as variable, zero/negative/non-integer raises, fail goal, single solution
    - **count_all**: basic, empty, large range, already-bound correct/wrong, with filter, no side effects
    - **setup_call_cleanup**: basic, call succeeds, call fails (cleanup runs), call throws (cleanup runs, re-raised), setup fails (no cleanup)
    - **call_cleanup**: basic, call fails, call throws, with solutions
    - **freeze**: already bound, deferred, goal success/failure, multiple on same var, backtracking removes attr
    - **when**: nonvar already/deferred, conjunction full/partial, ground already/deferred/nested, goal failure
    - **Meta-predicate nesting**: findall+call_nth, findall+count_all, once+call_nth, once+count_all, catch+call_nth, call_nth inside freeze, SCC inside findall, freeze inside findall, count_all inside count_all, call_cleanup inside once

---

*See also: [Builtins](builtins.md) — for the complete predicate index, [Exceptions](exceptions.md) — for throw/catch, [Constraints](constraints.md) — dif/2 and CLP(ℤ) use the same attributed variable mechanism.*
