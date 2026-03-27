# Coroutining & Resource Control

Clausal provides coroutining primitives for delayed goal execution and deterministic resource management. These predicates enable:

- **Delayed goals** — postpone execution until a variable is bound (`Freeze/2`, `When/2`)
- **Resource cleanup** — guarantee cleanup runs regardless of success, failure, or exceptions (`SetupCallCleanup/3`, `CallCleanup/2`)
- **Solution control** — skip to the Nth solution or count solutions efficiently (`CallNth/2`, `CountAll/2`)

All predicates in this module are **compiler special forms** — they are compiled inline at compile time (like `Once/1`, `FindAll/3`, and `catch/3`), and can be freely nested inside any other meta-predicate.

---

## Freeze/2

```clausal
# skip
Freeze(X, Goal)
```

Delay `Goal` until variable `X` is bound.

- If `X` is already bound at the time `Freeze` is executed, `Goal` runs **immediately**.
- If `X` is unbound, `Goal` is stored as an attributed variable attribute. When `X` is later unified with a value, the frozen goal fires **synchronously** — if the goal succeeds, the unification succeeds; if the goal fails, the unification **fails** (is rejected).

Multiple freezes on the same variable accumulate. All fire when the variable is bound. Backtracking undoes the attribute (the freeze is removed if the trail is unwound).

```clausal
# skip
# Guard: X must be positive when bound
Guarded(X) <- (
    Freeze(X, X > 0),
    X is 5
)
# succeeds — 5 > 0

Rejected(X) <- (
    Freeze(X, X > 0),
    X is -1
)
# fails — the unification X = -1 is rejected because -1 > 0 fails
```

```clausal
# skip
# Deferred binding
Deferred(Y) <- (
    Freeze(X, Y is X),
    X is "hello"
)
# Y = "hello" — the frozen goal Y is X fires when X is bound

# Multiple freezes on the same variable
Multi(Y, Z) <- (
    Freeze(X, Y is X),
    Freeze(X, Z is X),
    X is 42
)
# Y = 42, Z = 42
```

??? info "Implementation"
    Freeze uses the attributed variable hook infrastructure (the same mechanism used by [`dif/2`](constraints.md), [CLP(ℤ)](constraints.md), and [CLP(B)](clpb.md)). The frozen goal is compiled as a closure (zero-arg generator factory) and stored under the `"freeze"` attribute key. The hook drives the generator synchronously — no wakeup queue is needed.

    **Implementation:** `clausal/logic/compiler.py` (`_compile_freeze`), `clausal/logic/coroutining.py` (`_freeze_hook`)

---

## When/2

```clausal
# skip
When(Condition, Goal)
```

Generalized coroutining: delay `Goal` until `Condition` is satisfied.

### Supported conditions

| Condition | Meaning |
|---|---|
| `IsBound(X)` | X is bound (equivalent to `Freeze(X, Goal)`) |
| `IsGround(X)` | X is fully ground (no unbound variables anywhere in X) |
| `(C1, C2)` | Conjunction: both C1 and C2 must be satisfied |
| `(C1 ; C2)` | Disjunction: either C1 or C2 suffices |

```clausal
# skip
# Equivalent to Freeze(X, Goal)
Test("when isbound") <- (
    When(IsBound(X), Y is X),
    X is 42,
    Y is 42
)

# Conjunction: fire when both X and Y are bound
Test("when conjunction") <- (
    When((IsBound(X), IsBound(Y)), R is "done"),
    X is 1,
    Y is 2,
    R is "done"
)

# IsGround: fire when term is fully ground
Test("when ground") <- (
    When(IsGround([X, Y]), R is "all ground"),
    X is 1,
    Y is 2,
    R is "all ground"
)
```

### How conditions decompose

- `When(IsBound(X), Goal)` compiles directly as `Freeze(X, Goal)` — zero overhead.
- `When((C1, C2), Goal)` decomposes to `When(C1, When(C2, Goal))` — the inner When is installed when C1 is satisfied.
- `When(IsGround(X), Goal)` freezes on every unbound variable in X. When any is bound, groundness is re-checked. The goal fires when X is fully ground.
- `When((C1 ; C2), Goal)` attaches to variables in both conditions. Whichever fires first runs the goal (at most once).

??? info "Implementation"
    Compile-time dispatch handles `IsBound` and conjunction. Runtime helpers in `clausal/logic/coroutining.py` handle `IsGround` and disjunction.

    **Implementation:** `clausal/logic/compiler.py` (`_compile_when`), `clausal/logic/coroutining.py` (`_install_when_ground`, `_install_when_disjunction`, `_install_when_condition`)

---

## SetupCallCleanup/3

```clausal
# skip
SetupCallCleanup(Setup, Call, Cleanup)
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
ProcessFile(PATH, RESULT) <- SetupCallCleanup(
    HANDLE is ++open(PATH),
    (DATA is ++HANDLE.read(), RESULT is DATA),
    ++HANDLE.close()
)

# Call fails — Cleanup still runs, overall fails
Test("scc call fails") <- (
    not SetupCallCleanup(
        S is 1,
        In(X, []),
        C is 3
    )
)
```

---

## CallCleanup/2

```clausal
# skip
CallCleanup(Call, Cleanup)
```

Sugar for `SetupCallCleanup(true, Call, Cleanup)` — no setup step, just guaranteed cleanup.

```clausal
# skip
SafeQuery(GOAL) <- CallCleanup(
    CallGoal(GOAL),
    Writeln("query finished")
)
```

---

## CallNth/2

```clausal
# skip
CallNth(+Goal, +N)
```

Call `Goal` and succeed only on the **Nth solution**. The first N-1 solutions are skipped.

- `N` must be a positive integer (>= 1). Raises `type_error(positive_integer, N, "call_nth/2")` otherwise.
- If Goal has fewer than N solutions, `CallNth` fails.
- Only the Nth solution's bindings are visible to the continuation.

```clausal
# skip
# Get the 3rd member
Test("third") <- (
    CallNth(In(X, [10, 20, 30, 40, 50]), 3),
    X is 30
)

# N exceeds available solutions — fails
Test("too few") <- (
    not CallNth(In(X, [1, 2]), 5)
)
```

---

## CountAll/2

```clausal
# skip
CountAll(+Goal, -Count)
```

Count the number of solutions of `Goal` without collecting them. Unifies `Count` with the integer result.

Unlike [FindAll](meta_predicates.md) + `Length`, `CountAll` does not build a list — it just counts. Bindings from the inner goal are **not** visible after counting (the trail is unwound).

```clausal
# skip
# Count members
Test("count") <- (
    CountAll(In(X, ["a", "b", "c", "d"]), N),
    N is 4
)

# No solutions — 0
Test("empty") <- (
    CountAll(In(X, []), N),
    N is 0
)

# With filter
Test("filtered") <- (
    CountAll((In(X, [1, 2, 3, 4, 5]), X > 3), N),
    N is 2
)
```

---

## Nesting inside meta-predicates

All Phase 1 predicates are compiler special forms that compile their goal arguments inline. They nest freely inside other meta-predicates — [FindAll](meta_predicates.md), [Once](control.md), [catch](exceptions.md), [ForAll](meta_predicates.md), and each other:

```clausal
# skip
# FindAll wrapping CallNth
Test("findall+callnth") <- (
    FindAll(X, CallNth(In(X, [10, 20, 30]), 2), BAG),
    BAG is [20]
)

# catch wrapping CallNth with bad N
Test("catch+callnth") <- (
    catch(
        CallNth(In(X, [1, 2, 3]), 0),
        _,
        R is "caught"
    ),
    R is "caught"
)

# Freeze inside FindAll
Test("findall+freeze") <- (
    FindAll(
        Y,
        (Freeze(X, Y is X), X is 99),
        BAG
    ),
    BAG is [99]
)

# CountAll inside FindAll
Test("findall+countall") <- (
    FindAll(
        N,
        CountAll(In(X, ["a", "b", "c"]), N),
        BAG
    ),
    BAG is [3]
)
```

---

??? info "Test coverage"

    Tests are in `tests/test_coroutining.py` (51 tests) and
    `tests/fixtures/coroutining.clausal` (20 tests).

    - **CallNth**: basic, first/last, too few solutions, N as variable, zero/negative/non-integer raises, fail goal, single solution
    - **CountAll**: basic, empty, large range, already-bound correct/wrong, with filter, no side effects
    - **SetupCallCleanup**: basic, call succeeds, call fails (cleanup runs), call throws (cleanup runs, re-raised), setup fails (no cleanup)
    - **CallCleanup**: basic, call fails, call throws, with solutions
    - **Freeze**: already bound, deferred, goal success/failure, multiple on same var, backtracking removes attr
    - **When**: IsBound already/deferred, conjunction full/partial, IsGround already/deferred/nested, goal failure
    - **Meta-predicate nesting**: FindAll+CallNth, FindAll+CountAll, Once+CallNth, Once+CountAll, catch+CallNth, CallNth inside Freeze, SCC inside FindAll, Freeze inside FindAll, CountAll inside CountAll, CallCleanup inside Once

---

*See also: [Builtins](builtins.md) — for the complete predicate index, [Exceptions](exceptions.md) — for throw/catch, [Constraints](constraints.md) — dif/2 and CLP(ℤ) use the same attributed variable mechanism.*
