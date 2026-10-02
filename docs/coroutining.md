# Coroutining & Resource Control

Clausal provides coroutining primitives for delayed goal execution and deterministic resource management. These predicates enable:

- **Delayed goals** — postpone execution until a variable is bound (`freeze/2`, `when/2`)
- **Resource cleanup** — guarantee cleanup runs regardless of success, failure, or exceptions (`setup_call_cleanup/3`, `call_cleanup/2`)
- **Solution control** — skip to the Nth solution or count solutions efficiently (`call_nth/2`, `count_all/2`)

All predicates in this module are **compiler special forms** — they are compiled inline at compile time (like `once/1`, `findall/3`, and `catch/3`), and can be freely nested inside any other meta-predicate.

---

## freeze/2

```seam
--8<-- "tests/fixtures/docs/coroutining_sigs.txt:freeze_2"
```

Delay `Goal` until variable `X` is bound.

- If `X` is already bound at the time `freeze` is executed, `Goal` runs **immediately**.
- If `X` is unbound, `Goal` is stored as an attributed variable attribute. when `X` is later unified with a value, the frozen goal fires **synchronously** — if the goal succeeds, the unification succeeds; if the goal fails, the unification **fails** (is rejected).

Multiple freezes on the same variable accumulate. All fire when the variable is bound. Backtracking undoes the attribute (the freeze is removed if the trail is unwound).

```seam
--8<-- "tests/fixtures/docs/coroutining_sigs.txt:freeze_2_ex2"
```

```seam
--8<-- "tests/fixtures/docs/coroutining_sigs.txt:freeze_2_ex3"
```

??? info "Implementation"
    freeze uses the attributed variable hook infrastructure (the same mechanism used by [`dif/2`](constraints.md), [CLP(ℤ)](constraints.md), and [CLP(B)](clpb.md)). The frozen goal is compiled as a closure (zero-arg generator factory) and stored under the `"freeze"` attribute key. The hook drives the generator synchronously — no wakeup queue is needed.

    **Implementation:** `clausal/logic/compiler.py` (`_compile_freeze`), `clausal/logic/coroutining.py` (`_freeze_hook`)

---

## when/2

```seam
--8<-- "tests/fixtures/docs/coroutining_sigs.txt:when_2"
```

Generalized coroutining: delay `Goal` until `Condition` is satisfied.

### Supported conditions

| Condition | Meaning |
|---|---|
| `nonvar(X)` | X is bound (equivalent to `freeze(X, Goal)`) |
| `ground(X)` | X is fully ground (no unbound variables anywhere in X) |
| `(C1, C2)` | Conjunction: both C1 and C2 must be satisfied |
| `(C1 ; C2)` | Disjunction: either C1 or C2 suffices |

```seam
--8<-- "tests/fixtures/docs/coroutining_examples.seam:supported_conditions"
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

```seam
--8<-- "tests/fixtures/docs/coroutining_sigs.txt:setup_call_cleanup_3"
```

Deterministic resource management — the logic programming equivalent of `try/finally`.

1. **Setup** runs first (must succeed deterministically; only the first solution is taken).
2. **Call** runs normally (may succeed zero or more times, fail, or throw).
3. **Cleanup** runs **exactly once**, regardless of how Call terminates:
   - After all solutions of Call have been enumerated
   - If Call fails (Cleanup runs, then the whole goal fails)
   - If Call throws an exception (Cleanup runs, then the exception is re-raised)

If **Setup fails**, the whole goal fails and Cleanup does **not** run.

```seam
--8<-- "tests/fixtures/docs/coroutining_examples.seam:setup_call_cleanup_3_ex2"
```

---

## call_cleanup/2

```seam
--8<-- "tests/fixtures/docs/coroutining_sigs.txt:call_cleanup_2"
```

Sugar for `setup_call_cleanup(true, Call, Cleanup)` — no setup step, just guaranteed cleanup.

```seam
--8<-- "tests/fixtures/docs/coroutining_sigs.txt:call_cleanup_2_ex2"
```

---

## call_nth/2

```seam
--8<-- "tests/fixtures/docs/coroutining_sigs.txt:call_nth_2"
```

Call `Goal` and succeed only on the **Nth solution**. The first N-1 solutions are skipped.

- `N` must be a positive integer (>= 1). Anything else, an unbound `N` included, raises
  `error(type_error(positive_integer, N), call_nth/2)` (the Scryer error form; see
  [Exceptions](exceptions.md)). `N` does not enumerate.
- If Goal has fewer than N solutions, `call_nth` fails.
- Only the Nth solution's bindings are visible to the continuation.

```seam
--8<-- "tests/fixtures/docs/coroutining_examples.seam:call_nth_2_ex2"
```

---

## count_all/2

```seam
--8<-- "tests/fixtures/docs/coroutining_sigs.txt:count_all_2"
```

Count the number of solutions of `Goal` without collecting them. Unifies `Count` with the integer result.

Unlike [findall](meta_predicates.md) + `length`, `count_all` does not build a list — it just counts. Bindings from the inner goal are **not** visible after counting (the trail is unwound).

```seam
--8<-- "tests/fixtures/docs/coroutining_examples.seam:count_all_2_ex2"
```

---

## Nesting inside meta-predicates

All of these are compiler special forms that compile their goal arguments inline. They nest freely inside other meta-predicates — [findall](meta_predicates.md), [once](control.md), [catch](exceptions.md), [forall](meta_predicates.md), and each other:

```seam
--8<-- "tests/fixtures/docs/coroutining_examples.seam:nesting_inside_meta_predicates"
```

---

??? info "Test coverage"

    Tests are in `tests/test_coroutining.py` (51 tests) and
    `tests/fixtures/coroutining.seam` (20 tests).

    - **call_nth**: basic, first/last, too few solutions, N as variable, zero/negative/non-integer raises, fail goal, single solution
    - **count_all**: basic, empty, large range, already-bound correct/wrong, with filter, no side effects
    - **setup_call_cleanup**: basic, call succeeds, call fails (cleanup runs), call throws (cleanup runs, re-raised), setup fails (no cleanup)
    - **call_cleanup**: basic, call fails, call throws, with solutions
    - **freeze**: already bound, deferred, goal success/failure, multiple on same var, backtracking removes attr
    - **when**: nonvar already/deferred, conjunction full/partial, ground already/deferred/nested, goal failure
    - **Meta-predicate nesting**: findall+call_nth, findall+count_all, once+call_nth, once+count_all, catch+call_nth, call_nth inside freeze, SCC inside findall, freeze inside findall, count_all inside count_all, call_cleanup inside once

---

*See also: [Builtins](builtins.md) — for the complete predicate index, [Exceptions](exceptions.md) — for throw/catch, [Constraints](constraints.md) — dif/2 and CLP(ℤ) use the same attributed variable mechanism.*
