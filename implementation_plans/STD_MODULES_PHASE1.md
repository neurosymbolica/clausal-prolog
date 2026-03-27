# Std Modules Phase 1 — Coroutining & Resource Control

**Status: COMPLETE** (commit `659c532`)

**Depends on:** V2-14 (catch/throw), AttVar infrastructure (dif, CLP(FD), CLP(B))

**Goal:** Add the foundational control predicates that Scryer Prolog provides in
`freeze`, `when`, and `iso_ext`. These are prerequisites for writing robust logic
programs — `freeze/2` and `when/2` enable delayed goals (coroutining), while
`setup_call_cleanup/3` provides deterministic resource management.

---

## What was actually built

All 6 predicates were implemented as **compiler special forms** (not runtime
builtins). This matches how once, findall, forall, and catch work — the goal
arguments are compiled inline at compile time via `compile_goal` dispatch.

**Key design decisions that diverged from the original plan below:**

- **call_nth/2 and count_all/2** — the plan proposed runtime meta-predicate
  builtins, but compiler special forms are simpler and more efficient (no
  need to pass goal terms through runtime dispatch).
- **freeze/2** — the plan explored wakeup queues (`trail._wakeups`) and
  compiler-emitted drain loops. The actual implementation uses **synchronous
  hook execution** — the freeze hook drives the frozen goal generator directly
  within the attr hook callback. This is simpler (no C extension changes, no
  wakeup queue, no drain loops) and sufficient for standard freeze semantics
  (frozen goals either succeed or reject the unification).
- **when/2** — compile-time decomposition for `nonvar` (→ freeze) and
  conjunction (→ chained when). Runtime helpers for `ground` (freeze on
  all free vars, re-check on each binding) and disjunction (shared fired flag).
- **No C extension changes** were needed. The existing attr hook protocol
  (`hook(attr_value, bound_to, trail) → bool`) was sufficient.

**Test count:** 71 tests (51 Python in `test_coroutining.py` + 20 `.clausal`
in `fixtures/coroutining.clausal`), including 10 meta-predicate nesting tests
and 8 `.clausal` nesting tests.

**Files created:**
- `clausal/logic/coroutining.py` — freeze hook, when runtime helpers
- `clausal/logic/builtins/control.py` — field registrations for PredicateMeta classes
- `tests/test_coroutining.py` — 51 Python tests
- `tests/fixtures/coroutining.clausal` — 20 `.clausal` integration tests
- `docs/coroutining.md` — full documentation

**Files modified:**
- `clausal/logic/compiler.py` — 6 new special form handlers + dispatch cases
- `clausal/logic/builtins/__init__.py` — register control module
- `docs/builtins.md`, `docs/index.md`, `mkdocs.yml` — documentation updates

---

## Original Plan

*(The rest of this document is the original design exploration, preserved for
reference. The speculative sections about wakeup queues, Option A vs B, etc.
were superseded by the simpler synchronous hook approach described above.)*

---

## Predicates

| Predicate | Arity | Description |
|---|---|---|
| `freeze` | 2 | `freeze(X, Goal)` — delay Goal until X is bound |
| `when` | 2 | `when(Cond, Goal)` — delay Goal until Cond is satisfied |
| `setup_call_cleanup` | 3 | `setup_call_cleanup(Setup, Call, Cleanup)` — deterministic cleanup |
| `call_cleanup` | 2 | `call_cleanup(Call, Cleanup)` — shorthand (setup = true) |
| `call_nth` | 2 | `call_nth(Goal, N)` — succeed on Nth solution only |
| `count_all` | 2 | `count_all(Goal, Count)` — count solutions without collecting |

---

## 1a — freeze/2

**Files:** `clausal/logic/coroutining.py` (new), `clausal/logic/builtins/control.py`,
`clausal/logic/builtins/__init__.py`, `clausal/logic/compiler.py`

### Semantics

`freeze(X, Goal)`: if X is already bound, execute Goal immediately. If X is an
unbound variable, attach Goal as an attribute and delay execution until X is
unified with a value.

when X is later bound via unification, the freeze hook fires and the delayed
goal is executed. Multiple freezes on the same variable accumulate — all delayed
goals fire when the variable is bound.

### Implementation

Create `clausal/logic/coroutining.py`:

```python
FREEZE_KEY = "freeze"

def _freeze_hook(attr_value, bound_to, trail):
    """Fire all frozen goals when a variable is bound."""
    goals = attr_value  # list of (goal_fn, trail) pairs
    for goal_fn in goals:
        # Each goal_fn is a zero-arg callable that runs the goal
        # and returns True on success, False on failure.
        if not goal_fn():
            return False
    return True

register_attr_hook(FREEZE_KEY, _freeze_hook)
```

The key design question is how to represent the delayed goal. Since goals are
compiled to generator functions, we need a callable that can execute the goal
at hook-fire time. Two options:

**Option A — Python callable wrapper (preferred):**
The `freeze` builtin receives the goal as a Python callable (via the meta-predicate
compilation path used by `call/1`). It wraps it into a thunk that, when invoked,
runs the goal generator and checks if it produces at least one solution.

```python
def _freeze_builtin(x, goal_callable, trail, k):
    x = deref(x)
    if not is_var(x):
        # Already bound — run goal immediately
        yield from goal_callable(trail, k)
    else:
        # Attach goal to variable
        existing = get_attr(x, FREEZE_KEY)
        goals = list(existing) if existing else []
        goals.append(goal_callable)
        put_attr(x, FREEZE_KEY, goals, trail)
        yield from k()
```

**Option B — Compiler special form:**
Compile `freeze(X, Goal)` directly in the compiler (like `catch`), capturing the
goal as an AST sub-generator. This gives better performance but more compiler
complexity.

**Decision: Start with Option A** (builtin + meta-predicate call). If performance
is a concern, add compiler special form later. This matches how `call/1` already
works — the goal argument is compiled as a callable by the meta-predicate machinery.

### Hook design

The freeze hook signature must match the C extension's hook protocol:
`hook(attr_value, bound_to, trail) -> bool`. The attr_value is the list of
goal callables. Each callable needs access to the trail.

Problem: the hook receives `trail` but the goal callables were created with a
specific trail reference. Since there's only one trail per search, this is fine —
they'll be the same object.

Bigger problem: goal callables from the meta-predicate path are generator
functions (`def goal(trail, k): ... yield ...`), but the hook must return a
bool synchronously. The hook needs to *drive* the generator to check for at
least one solution.

**Solution:** The hook drives each frozen goal generator, consuming one solution.
If any goal fails (no solutions), the hook returns False (which causes the
unification that triggered it to fail).

```python
def _freeze_hook(goals, bound_to, trail):
    for goal_fn in goals:
        # goal_fn(trail) -> generator yielding None per solution
        found = False
        for _ in goal_fn(trail):
            found = True
            break  # one solution suffices
        if not found:
            return False
    return True
```

Wait — this doesn't handle continuation properly. The frozen goal should
*produce solutions* that feed into the rest of the search, not just check
for existence. This is the fundamental tension between hooks (synchronous
bool return) and goals (generator-based search).

**Revised approach:** freeze hooks that need to run goals should use the
same pattern as CLP(FD) propagation — the hook returns True/False for
immediate pass/fail, and any goal execution is scheduled for later. But
standard `freeze/2` semantics require the goal to run *as part of* the
current unification — if the goal fails, the unification fails.

**Final approach — compiler special form (Option B after all):**

Compile `freeze(X, Goal)` as a compiler special form. The compiler emits:

```python
# Simple mode:
_x = deref(_v_X)
if not is_var(_x):
    # Run goal immediately
    def _freeze_imm_N():
        <compiled Goal with k = [yield None]>
        return; yield
    for _ in _freeze_imm_N():
        <k_stmts>
else:
    # Attach hook: when _x is bound, run goal
    _freeze_mark_N = trail.mark()
    _old_freeze_N = get_attr(_x, "freeze")
    def _freeze_wake_N(attr, bound_to, trail):
        # Re-run all accumulated frozen goals
        ...
    put_attr(_x, "freeze", ..., trail)
    <k_stmts>
```

This is too complex for the hook protocol. Let me reconsider.

**Simplest correct approach — builtin with generator protocol:**

Actually, looking at how Scryer/SWI implement freeze: the frozen goal is
*woken* and added to the goal queue when the variable is bound. The woken
goals are then executed as part of the normal search. in_ Clausal's
generator-based architecture, this means:

1. when `freeze(X, Goal)` is called and X is unbound, store the goal.
2. when X is later bound, the attr hook fires.
3. The hook can't run generators — but it can *schedule* them.
4. The compiler needs a "wakeup queue" check point.

This is the approach used by SWI-Prolog and Scryer: `do_unify_and_wake`
already exists in the C extension. Let me check if it already has a
wake queue mechanism.

Actually, looking at the C extension comment: "structural unification is
complete, then hooks are fired." The hooks are synchronous and return bool.
This is sufficient for constraints (CLP(FD) just narrows domains, dif just
checks disequality), but freeze needs to *run arbitrary goals*.

**Pragmatic approach for Clausal:**

Make `freeze/2` a **compiler special form** (like `catch/3`). The compiler
rewrites `freeze(X, Goal)` into code that:

1. Checks if X is bound → run Goal inline.
2. If X is unbound → store a *thunk* on X, proceed with the continuation.
   when X is later bound (during `unify`), the thunk is placed on a
   **wakeup list** attached to the trail. After each unification in a
   compiled clause body, the compiler emits a wakeup-check loop that
   drains the list and runs each thunk as a sub-generator.

The wakeup list is `trail._wakeups: list[callable]` — a new attribute on
the Trail object. The C extension's `do_unify_and_wake` can append to this
list when a freeze-attributed variable is bound. The compiled code checks
`trail._wakeups` after each goal that might trigger unification.

### Sub-steps for 1a

1. **Add `trail._wakeups` list** to the Trail C extension (or as a Python
   attribute set in `__init__`). Initialize to `[]`.

2. **Create `clausal/logic/coroutining.py`:**
   - `FREEZE_KEY = "freeze"`
   - `_freeze_hook(goals, bound_to, trail)`: appends each goal thunk to
     `trail._wakeups`, returns True (the actual goal execution happens later).
   - `register_attr_hook(FREEZE_KEY, _freeze_hook)`

3. **Compiler integration** (`compiler.py`):
   - Add `freeze` to the special-form dispatch in `compile_goal` and
     `compile_goal_trampoline`.
   - Simple mode: emit inline check + `put_attr` for the delayed case.
   - After every goal call that might trigger unification, emit a wakeup
     drain loop: `while trail._wakeups: _wk = trail._wakeups.pop(0); ...`
   - For the trampoline mode: same pattern but using `StepGenerator`.

4. **Register as builtin** in `builtins/__init__.py` and `builtins/control.py`
   for the dispatch table (even though it's a compiler special form, it needs
   a builtin entry for `call(freeze(X, G))` dynamic invocation).

5. **Tests** in `tests/test_coroutining.py`:
   - `freeze(X, write(X)), X = hello` → prints "hello"
   - `freeze(X, X > 0), X = 5` → succeeds
   - `freeze(X, X > 0), X = -1` → fails
   - Multiple freezes on same variable
   - freeze on already-bound variable → immediate execution
   - freeze + backtracking (trail undo removes the attr)
   - freeze in `.clausal` file integration test

---

## 1b — when/2

**Files:** `clausal/logic/coroutining.py`, `clausal/logic/compiler.py`

**Depends on:** 1a (freeze)

### Semantics

`when(Cond, Goal)`: delay Goal until Cond is satisfied. Conditions:

| Condition | Meaning |
|---|---|
| `nonvar(X)` / `nonvar(X)` | X is bound |
| `ground(X)` / `ground(X)` | X is ground (no unbound vars) |
| `(C1, C2)` | Both C1 and C2 satisfied (conjunction) |
| `(C1 ; C2)` | Either C1 or C2 satisfied (disjunction) |

### Implementation

`when/2` decomposes the condition and attaches freeze-style hooks to the
relevant variables. For conjunction, all sub-conditions must be met. For
disjunction, any sub-condition suffices.

- `when(nonvar(X), Goal)` → equivalent to `freeze(X, Goal)`.
- `when(ground(X), Goal)` → freeze on every unbound var in X; when each is
  bound, re-check groundness; fire Goal when fully ground.
- `when((C1, C2), Goal)` → `when(C1, when(C2, Goal))`.
- `when((C1; C2), Goal)` → attach to vars in C1 *and* C2; when either fires
  and its condition is satisfied, run Goal.

This is a **compiler special form** that recursively decomposes the condition
at compile time (when the condition is statically known) or at runtime (when
the condition is a variable).

### Sub-steps for 1b

1. **Condition parser** in `coroutining.py`: `_decompose_when_condition(cond)`
   returns a structured representation of the condition tree.

2. **Compiler integration**: `when(Cond, Goal)` in `compile_goal` /
   `compile_goal_trampoline`. For the common case `when(nonvar(X), Goal)`,
   emit the same code as freeze. For compound conditions, emit a
   runtime `_when_check` helper call.

3. **Runtime helper** `_install_when(cond, goal_thunk, trail)` in
   `coroutining.py` for dynamically-constructed conditions.

4. **Tests** in `tests/test_coroutining.py`:
   - `when(nonvar(X), write(X)), X = hello` → prints "hello"
   - `when(ground(f(X, Y)), Goal), X = 1, Y = 2` → Goal fires after Y=2
   - `when((nonvar(X), nonvar(Y)), Goal)` → fires when both bound
   - `when((nonvar(X) ; nonvar(Y)), Goal)` → fires when either bound

---

## 1c — setup_call_cleanup/3

**Files:** `clausal/logic/compiler.py`, `clausal/logic/builtins/control.py`

### Semantics

`setup_call_cleanup(Setup, Call, Cleanup)`:

1. Run Setup (must succeed deterministically).
2. Run Call (may succeed, fail, or throw).
3. Regardless of how Call terminates, run Cleanup exactly once.

This is the logic programming equivalent of `try/finally`. The cleanup runs:
- After all solutions of Call have been enumerated (normal termination).
- If Call throws an exception (the exception is re-raised after cleanup).
- If Call fails (cleanup runs, then the whole goal fails).

### Implementation

This is a **compiler special form** similar to `catch/3`. The compiler emits:

```python
# Simple mode:
def _scc_setup_N():
    <compiled Setup with k = [yield None]>
    return; yield
_scc_setup_ok_N = False
for _ in _scc_setup_N():
    _scc_setup_ok_N = True
    break
if not _scc_setup_ok_N:
    pass  # Setup failed — whole goal fails, no cleanup
else:
    _scc_exc_N = None
    _scc_mark_N = trail.mark()
    try:
        def _scc_call_N():
            <compiled Call with k = [yield None]>
            return; yield
        for _ in _scc_call_N():
            <k_stmts>
    except Exception as _e_N:
        _scc_exc_N = _e_N
    finally:
        # Run cleanup once
        def _scc_cleanup_N():
            <compiled Cleanup with k = [yield None]>
            return; yield
        for _ in _scc_cleanup_N():
            break  # one solution suffices
        if _scc_exc_N is not None:
            raise _scc_exc_N
```

### Sub-steps for 1c

1. **Compiler**: Add `setup_call_cleanup` to the special-form dispatch in both
   `compile_goal` and `compile_goal_trampoline`.

2. **`call_cleanup/2`**: Sugar — compile as `setup_call_cleanup(true, Call, Cleanup)`
   where `true` is a goal that always succeeds.

3. **Register** both names in the builtin tables.

4. **Tests** in `tests/test_coroutining.py`:
   - Setup + Call succeeds + Cleanup runs
   - Call fails → Cleanup still runs, overall goal fails
   - Call throws → Cleanup runs, exception re-raised
   - Setup fails → Cleanup does NOT run
   - Cleanup with side effects (write to list, verify order)
   - `.clausal` file integration test

---

## 1d — call_nth/2

**Files:** `clausal/logic/builtins/control.py`

### Semantics

`call_nth(Goal, N)`: call Goal, skip the first N-1 solutions, succeed on the Nth.

### Implementation

This is a **builtin** (not a compiler special form) — it can use the existing
meta-predicate machinery (`call` with a goal argument).

```python
def _call_nth(goal_callable, n, trail, k):
    n_val = deref(n)
    if not isinstance(n_val, int) or n_val < 1:
        raise LogicException(type_error("positive_integer", n_val, "call_nth/2"))
    count = 0
    for _ in goal_callable(trail):
        count += 1
        if count == n_val:
            yield from k()
            return
```

Register as `("call_nth", 2)` in the builtin table with meta-predicate mode
`call_nth(0, +)` (first arg is a goal, second is input).

### Tests

- `call_nth(between(1, 10, X), 5)` → X = 5
- `call_nth(between(1, 3, X), 4)` → fails (only 3 solutions)
- `call_nth(Member(X, [a, b, c]), 1)` → X = a
- N = 0 or negative → error

---

## 1e — count_all/2

**Files:** `clausal/logic/builtins/control.py`

### Semantics

`count_all(Goal, Count)`: count the number of solutions of Goal without
collecting them. Unifies Count with the integer count.

### Implementation

Builtin using meta-predicate call:

```python
def _count_all(goal_callable, count, trail, k):
    n = 0
    for _ in goal_callable(trail):
        n += 1
    mark = trail.mark()
    if unify(count, n, trail):
        yield from k()
    trail.undo(mark)
```

Register as `("count_all", 2)` with meta-predicate mode `count_all(0, -)`.

### Tests

- `count_all(Member(_, [a, b, c]), N)` → N = 3
- `count_all(fail, N)` → N = 0
- `count_all(between(1, 100, _), N)` → N = 100
- Count already bound to correct value → succeeds
- Count already bound to wrong value → fails

---

## File Summary

| File | Action |
|---|---|
| `clausal/logic/coroutining.py` | **New** — freeze hook, when helpers, FREEZE_KEY |
| `clausal/logic/compiler.py` | Add freeze, when, setup_call_cleanup, call_cleanup special forms |
| `clausal/logic/builtins/control.py` | Add call_nth, count_all builtins |
| `clausal/logic/builtins/__init__.py` | Register new builtins |
| `clausal/logic/variables/_variables.c` | Add `trail._wakeups` list (if not using Python-side Trail wrapper) |
| `tests/test_coroutining.py` | **New** — all tests for this phase |
| `tests/fixtures/coroutining.clausal` | **New** — `.clausal` integration fixture |

## Implementation Order

1. **1d (call_nth)** and **1e (count_all)** — standalone builtins, no infrastructure changes. Good warm-up.
2. **1c (setup_call_cleanup)** — compiler special form, modeled on catch/3. No AttVar work.
3. **1a (freeze)** — requires wakeup queue on Trail + compiler integration.
4. **1b (when)** — builds on freeze.

## Test Count Estimate

~45–55 tests across the phase.
