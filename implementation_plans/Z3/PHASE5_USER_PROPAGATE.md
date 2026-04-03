# Phase 5 — UserPropagateBase Integration

The bidirectional bridge: Z3's CDCL loop calls back into Clausal's trampoline
for custom constraint propagation. This is the most architecturally complex
phase.

**Depends on:** Phase 1 (core infrastructure), Phase 2 or 3 (to have something to propagate)

---

## Files to Modify/Create

| File | Action |
|------|--------|
| `clausal/logic/clpz3.py` | Add `ClausalPropagator`, `z3_propagate`, `z3_table` |
| `clausal/logic/builtins/z3_constraints.py` | Register propagator builtins |
| `tests/test_clpz3_propagate.py` | Propagator tests |

---

## 1. Architecture Recap

```
Clausal generator (outer trampoline) — SUSPENDED during check()
  └─ solver.check()
       └─ Z3 CDCL loop (C++)
            ├─ ClausalPropagator.push()     → trail.mark()
            ├─ ClausalPropagator.on_fixed() → start INNER trampoline
            │    └─ trampoline(StepGenerator(clausal_goal, None, ..., trail))
            │         └─ runs Clausal code, binds vars on same trail
            │    └─ self.propagate() or self.conflict()
            ├─ ClausalPropagator.pop(n)     → trail.undo() × n
            └─ returns sat/unsat
```

Key insight: **the inner trampoline is a fresh, synchronous `while` loop**.
It doesn't interfere with the outer trampoline (which is blocked at `check()`).

---

## 2. `ClausalPropagator` Class

```python
class ClausalPropagator(_z3.UserPropagateBase):
    """Bridge Z3's CDCL solver to Clausal's constraint propagation.

    Registered callbacks:
    - push(): save trail mark (Z3 is making a CDCL decision)
    - pop(n): restore trail to saved marks (Z3 is backtracking)
    - on_fixed(x, v): Z3 assigned variable x to value v
    - on_final(): Z3 found a complete model — verify with Clausal

    The propagator maintains a parallel trail synchronized with Z3's
    internal decision stack.
    """

    def __init__(self, solver_or_none, trail, var_map, rev_map, *,
                 on_fixed_goals=None, on_final_goal=None):
        if solver_or_none is not None:
            super().__init__(solver_or_none)
        else:
            super().__init__(solver_or_none)  # for fresh()
        self.trail = trail
        self.var_map = var_map      # id(Var) → z3 const
        self.rev_map = rev_map      # z3 id → Var
        self.scope_marks = []
        self.on_fixed_goals = on_fixed_goals or []
        self.on_final_goal = on_final_goal

        if solver_or_none is not None:
            self.add_fixed(self._handle_fixed)
            self.add_final(self._handle_final)

    # ── Z3 callbacks ──────────────────────────────────────────────

    def push(self):
        """Z3 is making a CDCL decision. Save trail state."""
        mark = self.trail.mark()
        self.scope_marks.append(mark)

    def pop(self, num_scopes):
        """Z3 is backtracking. Restore trail state."""
        for _ in range(num_scopes):
            mark = self.scope_marks.pop()
            self.trail.undo(mark)

    def fresh(self, new_ctx):
        """Z3 needs a propagator clone for parallel solving.

        Creates a new propagator with a fresh trail. Variable maps
        are shared (read-only during solving).
        """
        new_trail = Trail()
        return ClausalPropagator(
            None, new_trail, self.var_map, self.rev_map,
            on_fixed_goals=self.on_fixed_goals,
            on_final_goal=self.on_final_goal,
        )

    def _handle_fixed(self, z3_var, z3_value):
        """Z3 assigned a variable — run Clausal propagation goals."""
        z3_id = z3_var.get_id()
        clausal_var = self.rev_map.get(z3_id)
        if clausal_var is None:
            return  # Not a Clausal-tracked variable

        value = z3_to_python(z3_value)

        for goal_factory in self.on_fixed_goals:
            try:
                result = self._run_clausal_goal(goal_factory, clausal_var, value)
            except Exception:
                self.conflict([z3_id])
                return

            if result is _FAIL:
                self.conflict([z3_id])
                return

            if result is not None:
                for z3_consequence in result:
                    self.propagate(z3_consequence, [z3_id])

    def _handle_final(self):
        """Z3 has a complete model — optionally verify with Clausal."""
        if self.on_final_goal is None:
            return

        try:
            result = self._run_clausal_goal_simple(self.on_final_goal)
        except Exception:
            self.conflict([])
            return

        if result is _FAIL:
            self.conflict([])

    # ── Inner trampoline ─────────────────────────────────────────

    def _run_clausal_goal(self, goal_factory, var, value):
        """Run a Clausal goal inside a fresh trampoline.

        goal_factory(var, value, trail) → StepGenerator or generator

        Returns:
        - None: goal succeeded with no consequences
        - list of z3.BoolRef: consequences to propagate
        - _FAIL: goal failed (conflict)
        """
        from clausal.logic.trampoline import StepGenerator, trampoline, DONE

        gen_or_sg = goal_factory(var, value, self.trail)
        if isinstance(gen_or_sg, StepGenerator):
            try:
                result = trampoline(gen_or_sg)
                return result
            except Exception:
                return _FAIL
        else:
            # It's a plain generator — drive it
            try:
                for _ in gen_or_sg:
                    pass  # collect side effects (trail bindings)
                return None
            except Exception:
                return _FAIL

    def _run_clausal_goal_simple(self, goal):
        """Run a simple Clausal goal that returns success/failure."""
        from clausal.logic.trampoline import StepGenerator, trampoline

        if callable(goal):
            sg = goal(self.trail)
            if isinstance(sg, StepGenerator):
                try:
                    trampoline(sg)
                    return None
                except Exception:
                    return _FAIL
        return _FAIL


_FAIL = object()  # sentinel
```

### Gotchas

1. **Thread safety in `fresh()`:** `fresh()` is called by Z3 for parallel
   solving. The new propagator gets a **new Trail** (Trails are per-thread).
   The `var_map` / `rev_map` are shared but read-only during solving.

2. **Trail marks vs Z3 decision levels:** Z3 calls `push()` at each CDCL
   decision level (not at each variable assignment). Multiple `on_fixed()`
   calls may happen between `push()` and `pop()`. The trail captures all
   bindings made by inner trampolines; `pop()` undoes them all.

3. **Reentrant inner trampoline:** If the inner trampoline itself calls
   `solver.check()`, we'd have recursive Z3 solving. **Don't do this.**
   The inner trampoline should only do Clausal-side work (unification,
   domain narrowing, database lookups).

4. **Exception handling:** If the inner trampoline raises, we must catch it
   and report a conflict to Z3. Z3 will backtrack. Don't let exceptions
   propagate into Z3's C++ code.

5. **Propagation format:** `self.propagate(consequence, justification_ids)`
   requires Z3 BoolRef expressions. The inner trampoline must translate
   any Clausal-side consequences back to Z3 expressions.

---

## 3. Registering Variables for Tracking

For `on_fixed` to fire, variables must be registered with the propagator:

```python
def z3_register_propagator(vars_list, on_fixed_fn, trail: Trail):
    """Register a UserPropagateBase for the given variables.

    on_fixed_fn(var, value, trail) is called when Z3 assigns a variable.
    It should return None (success, no consequences) or a list of Z3
    BoolRef consequences, or raise an exception (conflict).
    """
    state = get_z3_state(trail)
    vars_list = deref(vars_list)
    if not isinstance(vars_list, list):
        from clausal.terms import cons_to_list
        vars_list = cons_to_list(vars_list)

    prop = ClausalPropagator(
        state.solver, trail, state.var_map, state.rev_map,
        on_fixed_goals=[on_fixed_fn],
    )

    # Register each variable for tracking
    for v in vars_list:
        v = deref(v)
        if is_var(v):
            z3_v = state.var_map.get(id(v))
            if z3_v is not None:
                prop.register(z3_v)

    # Store propagator reference to prevent GC
    if not hasattr(state, '_propagators'):
        state._propagators = []
    state._propagators.append(prop)

    return True
```

---

## 4. Table Constraint (Use Case)

A table (extensional) constraint restricts a tuple of variables to be one of
a listed set of tuples. Z3 doesn't have this natively, but we can implement
it via `UserPropagateBase`:

```python
def z3_table(vars_list, tuples_list, trail: Trail) -> bool:
    """Table constraint: (X1, ..., Xn) must be one of the given tuples.

    Uses a ClausalPropagator that filters valid tuples as variables
    are assigned.
    """
    state = get_z3_state(trail)
    vars_list = deref(vars_list)
    tuples_list = deref(tuples_list)

    if not isinstance(vars_list, list):
        from clausal.terms import cons_to_list
        vars_list = cons_to_list(vars_list)

    z3_vars = [z3_var_for(deref(v), _z3.IntSort(), trail) for v in vars_list
               if is_var(deref(v))]

    # Alternative: encode as disjunction of conjunctions
    # This is simpler than UserPropagateBase for small tables
    clauses = []
    for tup in tuples_list:
        tup = deref(tup)
        if not isinstance(tup, list):
            from clausal.terms import cons_to_list
            tup = cons_to_list(tup)
        conj = _z3.And([z3v == val for z3v, val in zip(z3_vars, tup)])
        clauses.append(conj)

    state.solver.add(_z3.Or(clauses))
    return True
```

**When to use UserPropagateBase instead:** For very large tables (thousands of
tuples), the disjunction encoding is too large. The propagator approach filters
incrementally. Implement this optimization in a later iteration.

---

## 5. Tabling Integration (Use Case)

SLG tabling inside a `UserPropagateBase` callback:

```python
def make_tabled_propagator(tabled_predicate, module, result_var_index):
    """Create a propagator that queries a tabled Clausal predicate.

    When Z3 assigns a variable, the propagator queries the tabled
    predicate to find valid values for dependent variables.
    """
    def on_fixed(var, value, trail):
        from clausal.logic.solve import solve
        from clausal.logic.trampoline import StepGenerator, solutions

        # Build a query goal
        args = [Var() for _ in range(tabled_predicate.arity)]
        args[0] = value  # input: the assigned variable's value

        # Run the tabled query
        result_var = args[result_var_index]
        valid_values = []
        for _ in solve(tabled_predicate(*args), module, trail):
            valid_values.append(deref(result_var))

        if not valid_values:
            return _FAIL

        # Translate to Z3 consequence: output_z3_var ∈ valid_values
        z3_out = get_z3_state(trail).var_map.get(id(result_var))
        if z3_out is not None:
            return [_z3.Or([z3_out == v for v in valid_values])]

        return None

    return on_fixed
```

### Gotcha: Tabling and Trail Interaction

SLG tabling uses the Trail for its own state management (suspension, resumption).
Running a tabled query inside a propagator callback modifies the trail.
When Z3 calls `pop()`, the trail is undone, which also undoes tabling state.

**This is fine** as long as the tabling system doesn't rely on state persisting
across Z3 decision levels. Each `on_fixed` call should be self-contained:
query, collect results, return. Don't leave suspended continuations on the
trail.

---

## 6. Builtin Registration

```python
# Phase 5 additions to z3_constraints.py

@_builtin("z3_table", 2)
def _z3_table__2(vars_list, tuples_list, trail, k):
    """z3_table(Vars, Tuples) — table/extensional constraint via Z3."""
    from clausal.logic.clpz3 import z3_table
    if z3_table(vars_list, tuples_list, trail):
        yield None
```

---

## 7. Tests

### Unit Tests: `tests/test_clpz3_propagate.py`

```python
"""Tests for Z3 UserPropagateBase integration (Phase 5)."""

import pytest
z3 = pytest.importorskip("z3")

from clausal.logic.variables import Var, Trail, deref, unify, is_var
from clausal.logic.clpz3 import (
    in_z3, label_z3, all_different_z3, get_z3_state, z3_var_for,
    ClausalPropagator, z3_table,
)


class TestClausalPropagator:
    def test_push_pop_trail_sync(self):
        """push/pop correctly save and restore trail."""
        trail = Trail()
        state = get_z3_state(trail)
        prop = ClausalPropagator(
            state.solver, trail, state.var_map, state.rev_map
        )

        x = Var()
        prop.push()
        unify(x, 42, trail)
        assert deref(x) == 42

        prop.pop(1)
        assert is_var(deref(x))

    def test_nested_push_pop(self):
        trail = Trail()
        state = get_z3_state(trail)
        prop = ClausalPropagator(
            state.solver, trail, state.var_map, state.rev_map
        )

        x, y = Var(), Var()
        prop.push()
        unify(x, 1, trail)
        prop.push()
        unify(y, 2, trail)

        assert deref(x) == 1
        assert deref(y) == 2

        prop.pop(1)
        assert deref(x) == 1
        assert is_var(deref(y))

        prop.pop(1)
        assert is_var(deref(x))

    def test_pop_multiple(self):
        """pop(2) undoes two levels at once."""
        trail = Trail()
        state = get_z3_state(trail)
        prop = ClausalPropagator(
            state.solver, trail, state.var_map, state.rev_map
        )

        x, y = Var(), Var()
        prop.push()
        unify(x, 1, trail)
        prop.push()
        unify(y, 2, trail)

        prop.pop(2)
        assert is_var(deref(x))
        assert is_var(deref(y))

    def test_fresh(self):
        """fresh() creates a new propagator with a fresh trail."""
        trail = Trail()
        state = get_z3_state(trail)
        prop = ClausalPropagator(
            state.solver, trail, state.var_map, state.rev_map
        )
        fresh_prop = prop.fresh(None)
        assert fresh_prop.trail is not trail
        assert fresh_prop.var_map is state.var_map  # shared


class TestTableConstraint:
    def test_basic_table(self):
        trail = Trail()
        x, y = Var(), Var()
        in_z3([x, y], 1, 5, trail)
        z3_table([x, y], [[1,2], [2,3], [3,4]], trail)
        solutions = []
        for _ in label_z3([x, y], trail):
            solutions.append((deref(x), deref(y)))
        assert sorted(solutions) == [(1,2), (2,3), (3,4)]

    def test_empty_table(self):
        trail = Trail()
        x, y = Var(), Var()
        in_z3([x, y], 1, 5, trail)
        z3_table([x, y], [], trail)
        solutions = list(label_z3([x, y], trail))
        assert solutions == []

    def test_table_with_other_constraints(self):
        trail = Trail()
        x, y = Var(), Var()
        in_z3([x, y], 1, 5, trail)
        z3_table([x, y], [[1,2], [2,3], [3,4]], trail)
        from clausal.logic.clpz3 import z3_gt
        z3_gt(x, 1, trail)  # x > 1
        solutions = []
        for _ in label_z3([x, y], trail):
            solutions.append((deref(x), deref(y)))
        assert sorted(solutions) == [(2,3), (3,4)]

    def test_single_element_table(self):
        trail = Trail()
        x, y = Var(), Var()
        in_z3([x, y], 1, 5, trail)
        z3_table([x, y], [[3, 4]], trail)
        solutions = []
        for _ in label_z3([x, y], trail):
            solutions.append((deref(x), deref(y)))
        assert solutions == [(3, 4)]


class TestInnerTrampoline:
    def test_run_clausal_goal_in_propagator(self):
        """Verify that a full Clausal goal can run inside a propagator."""
        from clausal.logic.trampoline import StepGenerator, trampoline

        trail = Trail()
        result = Var()

        # Simple Clausal goal: unify result with value + 1
        def my_goal(this_sg, parent, var, value, trail):
            if unify(result, value + 1, trail):
                yield (parent, None)

        sg = StepGenerator(my_goal, None, Var(), 5, trail)
        trampoline(sg)
        assert deref(result) == 6

    def test_inner_trampoline_trail_undo(self):
        """Inner trampoline bindings are undone by propagator.pop()."""
        trail = Trail()
        state = get_z3_state(trail)
        prop = ClausalPropagator(
            state.solver, trail, state.var_map, state.rev_map
        )

        result = Var()
        prop.push()

        # Run inner trampoline
        from clausal.logic.trampoline import StepGenerator, trampoline
        def my_goal(this_sg, parent, trail):
            unify(result, 42, trail)
            yield (parent, None)

        sg = StepGenerator(my_goal, None, trail)
        trampoline(sg)
        assert deref(result) == 42

        prop.pop(1)
        assert is_var(deref(result))  # undone!
```

---

## 8. Gotchas & Edge Cases

1. **No yield from callbacks:** Z3 callbacks are synchronous. You cannot
   `yield` from `on_fixed()`. Use a fresh trampoline or plain loop.

2. **Recursive Z3 calls:** Do NOT call `solver.check()` from inside a
   callback. Z3 is already inside `check()`. Recursive calls will deadlock
   or crash.

3. **Exception safety:** Always catch exceptions from inner trampolines.
   Uncaught exceptions in Z3 callbacks cause undefined behavior in C++.

4. **GC of propagator:** The propagator must stay alive for the duration of
   `solver.check()`. Store a reference in `Z3State._propagators`.

5. **Multiple propagators:** You can register multiple `UserPropagateBase`
   instances on the same solver. Each handles different variables/constraints.

6. **Z3's `add_eq` callback:** Fires when Z3 determines two registered terms
   are equal. Could map to Clausal's `unify()`. Defer to a later iteration.

7. **Z3's `add_decide` callback:** Fires before Z3 chooses a branching
   variable. Could implement custom variable ordering. Defer.

8. **Performance:** Each `on_fixed()` callback is a Python call from C++.
   If there are many callbacks per `check()`, the overhead adds up. Keep
   callbacks lightweight. Heavy Clausal goals should be the exception.

---

## Implementation Order

1. `ClausalPropagator` class with push/pop/fresh
2. Unit tests for push/pop/fresh (no Z3 solving, just direct calls)
3. Variable registration (`prop.register(z3_var)`)
4. `on_fixed` callback with inner trampoline
5. `z3_table` via disjunction encoding (simpler, no propagator needed)
6. Tests: table constraint end-to-end
7. `z3_table` via UserPropagateBase (for large tables)
8. Tabling integration (SLG inside callback)
9. `on_final` callback
10. Integration tests
