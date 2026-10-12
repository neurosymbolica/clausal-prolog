# Coroutining & Resource Control

Clausal Prolog provides coroutining primitives for delayed goal execution and deterministic resource management. These predicates enable:

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
- If `X` is unbound, `Goal` is stored as an attributed variable attribute. When `X` is later unified with a value, the frozen goal is **woken**: it runs right after that unification, before the next goal, with **every** answer. If it fails, execution backtracks as if the unification had failed.

A woken goal backtracks like any other goal, as in Scryer:

```prolog
f(Y) :- freeze(X, member(Y, [1, 2, 3])), X = go.     % Y = 1 ; Y = 2 ; Y = 3
g(Y) :- freeze(X, member(Y, [1, 2, 3])), X = go, Y > 1.   % Y = 2 ; Y = 3
```

Goals woken inside a test run inside it: `X \= go` and `\+ X = go` succeed when the goals `X = go` wakes have no answer, and `memberchk/2` (`once(member(...))`) passes over an element whose woken goals fail and keeps the first answer of the rest.

Multiple freezes on the same variable accumulate. All fire when the variable is bound. Backtracking undoes the attribute (the freeze is removed if the trail is unwound).

```seam
--8<-- "tests/fixtures/docs/coroutining_sigs.txt:freeze_2_ex2"
```

```seam
--8<-- "tests/fixtures/docs/coroutining_sigs.txt:freeze_2_ex3"
```

??? info "Implementation"
    freeze uses the attributed variable hook infrastructure (the same mechanism used by [`dif/2`](constraints.md), [CLP(ℤ)](constraints.md), and [CLP(B)](clpb.md)). The frozen goal is compiled as a closure (zero-arg generator factory) and stored under the `"freeze"` attribute key. When the variable is bound, the hook queues the goal on the trail (`trail.push_pending`); the engine runs the queue at the next goal boundary — after an inline unification or an inline comparison that can bind (`X == 3`, `X <= 3`), at the start of a clause body whose head unified, and at every answer of a called predicate or builtin — once per answer. The queue and every change to it are trailed, so backtracking restores it.

    A bare `unify(...)` called from Python with no driver owning the trail (`trail.defer` false) queues woken goals the same way, and runs the queue itself before it returns: after every hook of the unification has run, to the first answer. If the goals fail, the unification fails and binds nothing. Everything nested in that unification counts as part of it: a partial list or segment string unifying element by element, a hook that unifies, a woken goal that unifies. Those only queue, and the one drain runs their goals. Outside a driver, a `when/2` whose condition already holds runs its goal at once, to its first answer, because no unification would ever run it.

    **Implementation:** `clausal/logic/compiler/control_constructs.py` (`_compile_freeze`), `clausal/logic/coroutining.py` (`_freeze_hook`), `clausal/logic/pending.py` (the queue's drain)

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
- A goal whose condition already holds runs at once, with every answer, like a woken `freeze` goal; if it has none, `when/2` fails.

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

## Inside a hook or at a goal

For constraint-library authors.  An attribute hook runs while the unification that bound its variable is still firing hooks; a goal runs at a goal boundary.  Under a driver `trail.defer` is true in both places, so it cannot tell them apart.  `trail.hooks_running` can:

| Where | `trail.defer` | `trail.hooks_running` |
|---|---|---|
| A goal under a driver (a body goal, a woken goal) | `True` | `0` |
| A woken goal that a bare `unify` runs itself | `True` | `0` |
| Python code outside any driver or unification | `False` | `0` |
| Inside an attribute hook, under a driver or not | `True` | `1` |
| Inside a hook of a unification nested in a hook | `True` | `2`, one more per level |

The contract:

- **Inside a hook** (`hooks_running > 0`) a library must not post a constraint in place, must not run another library's entry point, and must not drive a goal on the trail.  It queues the work as a goal with `trail.push_pending(goal)`, and the goal runs at the next goal boundary, after every hook of the unification has run.  `solve(..., trail=t)` and `call(..., trail=t)` on a trail whose hooks are running raise the ISO-shaped `error(permission_error(call, goal, Goal), Context)`: Context is `solve/2` for `solve`, and `call/N` for `call(F, A1, ..., Ak)`, where N = k + 1 and Goal is `F(A1, ..., Ak)`, or the atom `F` when k = 0 (so `call("p", X, trail=t)` reports `call/2` and the goal `p(X)`, and `call("p", trail=t)` reports `call/1` and the goal `p`).  A driver on a different, fresh trail is allowed, with a caveat: its bindings are on ITS trail, not the outer one.  If it binds a variable of the outer computation and the hook keeps that binding (it takes the first answer and stops), an undo of the outer trail does not undo it: the outer unification is undone and the variable stays bound.  Bind outer variables only through the hook's own trail (by unifying on it), or queue the goal.
- **At a goal** (`hooks_running == 0`) a library may post in place.  A binding it makes wakes goals, which run at the goal boundary that follows, before the next goal and with every answer.  In compiled code that boundary comes after every unification, every inline comparison that can bind (`X == 3`, `X <= 3`, and the posts of a reified test in `if_/3`), and every answer of a call.  A goal that ends in such an op inside a construct with a scope of its own (`catch/3`, `findall/3`, `\+`, `once/1`, `forall/2`, `call_cleanup/2`, `setup_call_cleanup/3`) runs what it woke inside that scope, so `catch/3` catches a ball thrown by a woken goal.

The counter goes up when a unification starts dispatching the hooks of the attributed variables it bound, and back down when that dispatch ends, whether it succeeds, a hook fails, or a hook raises (`KeyboardInterrupt` and `RecursionError` included).  Woken goals that a bare `unify` runs itself (to their first answer) run after its dispatch has ended, so they see `0`.  The counter is read-only.  C extensions read the `hooks_running` field of `TrailObject` from `_variables_capi.h`.

**Implementation:** `clausal/logic/variables/_variables.c` (`fire_wakeups`, `Trail.hooks_running`)

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
