# Assertion Diagnostic Descent Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** When a test's failing goal has *no* solution for any arguments (rung 3), descend into the predicate's own clause bodies and report the first failing conjunct per clause route with its bindings; when it *has* solutions two-plus arguments away (rung 2), print 1–3 of them.

**Architecture:** All changes live in `clausal/testing.py` (the failure-diagnostic engine for `python -m clausal.testing`). A new "Stage 4: descent" section reuses the existing cumulative-prefix walk (extracted as `_first_failing`), the reify cache, and the bindings collector. New tests go in `tests/test_testing_descent.py`; existing `tests/test_testing_diagnostics.py` must stay green untouched.

**Tech Stack:** Pure Python 3.13, pytest. No new dependencies.

**Spec:** `docs/superpowers/specs/2026-07-30-assertion-diagnostic-descent-design.md` — read it first; it has the rationale and the verified repro table.

## Global Constraints

- **Branch:** work on `todo/B-assertion-diagnostic-descent` (already created, spec committed).
- **Python for ALL test runs:** `/home/node/.pyenv/versions/3.13.3/bin/python` with `PYTHONPATH=/workspace/clausal-bug-fix`, run from `/workspace/clausal-bug-fix`. The venv python silently tests the WRONG tree. Verify once per session: `PYTHONPATH=/workspace/clausal-bug-fix /home/node/.pyenv/versions/3.13.3/bin/python -c "import clausal.testing as t; print(t.__file__)"` must print `/workspace/clausal-bug-fix/clausal/testing.py`.
- **NEVER `git add -A` or `git add .`** — this clone is shared with other agent instances; stage explicit paths only.
- **Never raise from diagnostics:** every new code path may raise only `_DiagBudgetExceeded`, `RecursionError`, `KeyboardInterrupt`, `SystemExit`. Everything else is swallowed at the clause level.
- **No new budget knob:** `$CLAUSAL_TEST_DIAG_BUDGET` / the `deadline` parameter is the only time bound.
- **No behavioral change to rung 1** (the "argument N differs" path) or to the pass/fail verdict.
- Pytest command template: `cd /workspace/clausal-bug-fix && PYTHONPATH=/workspace/clausal-bug-fix /home/node/.pyenv/versions/3.13.3/bin/python -m pytest <files> -q -p no:cacheprovider`

---

### Task 1: Extract `_first_failing` (pure refactor)

**Files:**
- Modify: `clausal/testing.py` — `_diagnose_into` (step-1 loop at ~lines 391–410), new helper in the "Executing conjuncts" section (~line 541)
- Test: existing `tests/test_testing_diagnostics.py` (no new tests; behavior must not change)

**Interfaces:**
- Produces: `_first_failing(goals, logic_module, deadline, prefix=()) -> tuple[int | None, str | None]` — 1-based index of the first conjunct whose cumulative prefix (with `prefix` goals prepended to every probe) has no solution, paired with `None`; or `(k, "ExcType: msg")` if that prefix raised; or `(None, None)` if every prefix is satisfiable. Task 3's descent calls this.

- [ ] **Step 1: Add the helper** in the "Executing conjuncts" section of `clausal/testing.py`:

```python
def _first_failing(goals, logic_module, deadline, prefix=()):
    """1-based index of the first conjunct whose cumulative prefix yields no
    solution, paired with ``None`` — or with the rendered exception if that
    prefix raised instead.  ``(None, None)`` when every prefix is satisfiable.

    *prefix* goals are prepended to every probe but never blamed: indices are
    relative to *goals*.
    """
    from clausal.logic.variables import Trail

    pre = list(prefix)
    for k in range(1, len(goals) + 1):
        if time.monotonic() > deadline:
            raise _DiagBudgetExceeded()
        trail = Trail()
        try:
            ok = _has_solution(_conjunction(pre + goals[:k]), logic_module, trail)
        except (_DiagBudgetExceeded, RecursionError, *_FATAL):
            raise
        except BaseException as exc:  # noqa: BLE001
            return k, f"{type(exc).__name__}: {exc}"
        finally:
            _undo(trail)
        if not ok:
            return k, None
    return None, None
```

- [ ] **Step 2: Rewire `_diagnose_into`** — replace its step-1 `for k in range(...)` loop with:

```python
    failing, raised = _first_failing(walked, logic_module, deadline)
    if raised is not None:
        diag.index, diag.raised = failing, raised
        diag.source = sources[failing - 1]
        return
```

The `if failing is None:` re-run-disagrees block and everything after stays exactly as it is.

- [ ] **Step 3: Run the existing diagnostics suite**

Run: `cd /workspace/clausal-bug-fix && PYTHONPATH=/workspace/clausal-bug-fix /home/node/.pyenv/versions/3.13.3/bin/python -m pytest tests/test_testing_diagnostics.py tests/test_testing_cli.py -q -p no:cacheprovider`
Expected: all pass (19 + CLI tests), zero failures.

- [ ] **Step 4: Commit**

```bash
git add clausal/testing.py
git commit -m "refactor(testing): extract _first_failing from _diagnose_into"
```

---

### Task 2: Rung 2 — render the solutions the probe already found

**Files:**
- Modify: `clausal/testing.py` — `GoalDiagnostic` (~line 126), `_report_nearest` all-holes block (~lines 738–760), new helper `_render_probe_solution` near `_render_nearest`
- Create: `tests/test_testing_descent.py`

**Interfaces:**
- Consumes: nothing new.
- Produces: `GoalDiagnostic.nearest_examples: list[str]` (rendered by `lines()`); `_render_probe_solution(goal, reified_goal, holes, kw_holes) -> str`. Task 3 renders `descent` right after `nearest_examples` in `lines()`.

- [ ] **Step 1: Create `tests/test_testing_descent.py` with the failing rung-2 test**

```python
"""Stage-4 descent diagnostics + rung-2 examples for ``python -m clausal.testing``.

Rung 3 ("no solution for ANY arguments") used to carry no value — measured
0/29 recovery in study 13.  See
``docs/superpowers/specs/2026-07-30-assertion-diagnostic-descent-design.md``.
"""

from __future__ import annotations

import textwrap

from clausal.testing import main


def write(tmp_path, name, src):
    p = tmp_path / name
    p.write_text(textwrap.dedent(src).lstrip())
    return p


# ── rung 2: satisfiable, but 2+ arguments differ ─────────────────────────────

PAIR_SRC = """
pairx("a", 1),
pairx("b", 2),

Test("both arguments differ") <- (
    pairx("c", 3)
),
"""


def test_two_plus_args_differ_shows_example_solutions(capsys, tmp_path):
    p = write(tmp_path, "pair.clausal", PAIR_SRC)
    assert main([str(p)]) == 1
    out = capsys.readouterr().out
    assert "two or more arguments differ" in out   # old sentence survives
    assert "it does have:" in out                  # new suffix
    assert "pairx('a', 1)" in out                  # an actual solution, rendered
```

- [ ] **Step 2: Run it to make sure it fails**

Run: `cd /workspace/clausal-bug-fix && PYTHONPATH=/workspace/clausal-bug-fix /home/node/.pyenv/versions/3.13.3/bin/python -m pytest tests/test_testing_descent.py -q -p no:cacheprovider`
Expected: FAIL on `assert "it does have:" in out` (the old message has no examples).

- [ ] **Step 3: Implement.** Three edits to `clausal/testing.py`:

(a) `GoalDiagnostic`: add field `nearest_examples: list[str] = field(default_factory=list)` and, in `lines()` directly after the `if self.nearest:` block:

```python
        for example in self.nearest_examples:
            out.extend(_wrap_goal(example, indent + "  "))
```

(b) New helper next to `_render_nearest`:

```python
def _render_probe_solution(goal, reified_goal, holes, kw_holes) -> str:
    """One all-holes solution as surface text, holes replaced by their values."""
    from clausal.logic.solve import _deref_walk_py
    from clausal.reflection import Goal, render_source

    values = [_deref_walk_py(h) for h in holes]
    kw_values = [(str(k.name), _deref_walk_py(k.value)) for k in kw_holes]
    if isinstance(reified_goal, Goal):
        try:
            return render_source(Goal(
                name=reified_goal.name,
                args=[_reify_value(v) for v in values],
                kwargs=[[n, _reify_value(v)] for n, v in kw_values],
            ))
        except Exception:  # noqa: BLE001
            pass
    func = getattr(goal, "func", None)
    name = str(func.name) if hasattr(func, "name") else "the predicate"
    parts = [_render_value(v) for v in values]
    parts += [f"{n}={_render_value(v)}" for n, v in kw_values]
    return f"{name}({', '.join(parts)})"
```

(c) In `_report_nearest`, replace the block from `trail = Trail()` through the final `if satisfiable: ... else: ...` with a solution iterator. `_report_descent` does not exist until Task 3 — for now the unsatisfiable branch keeps the old sentence verbatim:

```python
    examples: list[str] = []
    trail = Trail()
    gen = None
    try:
        gen = _solutions(probe, logic_module, trail)
        for _ in range(3):
            if next(gen, None) is None:
                break
            rendered = _render_probe_solution(goal, reified_goal, holes, kw_holes)
            if rendered not in examples:
                examples.append(rendered)
    except (_DiagBudgetExceeded, RecursionError, *_FATAL):
        raise
    except BaseException:  # noqa: BLE001 - a probe that errors is just no answer
        pass
    finally:
        if gen is not None:
            gen.close()
        _undo(trail)
    if examples:
        diag.nearest_note = (
            "the predicate has solutions, but none within one argument of "
            "this goal — two or more arguments differ; it does have:"
        )
        diag.nearest_examples = examples
    else:
        diag.nearest_note = (
            "the predicate has no solution for ANY arguments at this point "
            "(check the goals that produced its inputs, or its own clauses)"
        )
```

Note the old `satisfiable` flag is gone: a probe that raises mid-first-solution lands in `examples == []`, exactly as `satisfiable = False` did before.

- [ ] **Step 4: Run the new test and the old suite**

Run: `cd /workspace/clausal-bug-fix && PYTHONPATH=/workspace/clausal-bug-fix /home/node/.pyenv/versions/3.13.3/bin/python -m pytest tests/test_testing_descent.py tests/test_testing_diagnostics.py -q -p no:cacheprovider`
Expected: all pass. (No existing test asserts the exact rung-2 sentence — verified by grep.)

- [ ] **Step 5: Commit**

```bash
git add clausal/testing.py tests/test_testing_descent.py
git commit -m "feat(testing): rung 2 prints the solutions the probe already found"
```

---

### Task 3: Descent core — single level, leaves with bindings

**Files:**
- Modify: `clausal/testing.py` — constants (~line 66), `GoalDiagnostic`, `_reified_goals` (~line 486), `_report_nearest` unsat branch, new "Stage 4: descent" section after Stage 3
- Test: `tests/test_testing_descent.py`

**Interfaces:**
- Consumes: `_first_failing` (Task 1), `nearest_examples` rendering slot (Task 2).
- Produces:
  - `GoalDiagnostic.descent: list[str]` — pre-indented report lines, rendered by `lines()` after `nearest_examples` as `f"{indent}  {line}"`.
  - `_reified_clause(path, clause) -> ReifiedClause | None` — the position-matched reified `Clause(head, goals, position)` item, cached; `_reified_goals` becomes a thin wrapper over it.
  - `_resolve_predicate(goal, logic_module, caller_path) -> tuple[PredicateMeta, logic_module, source_path | None] | None`
  - `_descend(goal, logic_module, caller_path, deadline, depth, seen, notes) -> tuple[list[str], str]` with kind `"leaves" | "head_listing" | "none"` — Task 4 adds the recursive call, Task 5 adds the `"head_listing"` kind; in this task it returns `("leaves"| "none")` only.
  - `_report_descent(diag, goal, logic_module, deadline, path) -> None`
  - `_report_nearest` gains a trailing `path` parameter (the test file's path); both call sites in `_diagnose_into` pass the `path` they already hold.

**Why the path threading is load-bearing:** `load_clausal_module` pops the test module from `sys.modules` after loading (`clausal/testing.py:201-209`), so for a predicate defined in the test file itself, `sys.modules.get(cls.__module__)` is `None` — the descent would have no source path, hence no reified goals, hence leaves rendered by `term_str` as `(_ > 100)` with no variable names and NO bindings. The caller's `path` is the correct source file exactly when `cls.__module__ == logic_module.name`.
  - Constants: `DIAG_MAX_DESCENT_DEPTH = 2`, `DIAG_MAX_DESCENT_CLAUSES = 4`, `DIAG_MAX_DESCENT_LEAVES = 6`, `DIAG_MAX_DESCENT_BINDINGS = 4`.

- [ ] **Step 1: Write the failing tests** (append to `tests/test_testing_descent.py`):

```python
# ── rung 3: descent into the failing predicate ───────────────────────────────

GUARD_SRC = """
chk_range(PCT) <- (
    PCT >= 0,
    PCT > 100,
    PCT <= 100
),

Test("contradictory guards") <- (
    chk_range(50)
),
"""


def test_contradictory_guard_named_with_value(capsys, tmp_path):
    p = write(tmp_path, "guard.clausal", GUARD_SRC)
    assert main([str(p)]) == 1
    out = capsys.readouterr().out
    assert "no clause body survives" in out
    assert "PCT > 100" in out       # the failing conjunct, source-faithful
    assert "PCT = 50" in out        # ...with the head binding that dooms it


TWO_ROUTES_SRC = """
-private([small, big])

classify(X, small) <- (X < 10, X < 0),
classify(X, big) <- (X > 10, X > 100),

Test("two routes both fail") <- (
    classify(5, _KIND)
),
"""


def test_each_clause_route_gets_a_leaf(capsys, tmp_path):
    p = write(tmp_path, "routes.clausal", TWO_ROUTES_SRC)
    assert main([str(p)]) == 1
    out = capsys.readouterr().out
    assert "X < 0" in out    # clause 1's first failing conjunct (5 < 10 passed)
    assert "X > 10" in out   # clause 2's
    assert "X = 5" in out


DYN_SRC = """
-dynamic(dynp(A))

Test("zero-clause predicate") <- (
    dynp(1)
),
"""


def test_zero_clause_predicate_keeps_old_message(capsys, tmp_path):
    p = write(tmp_path, "dyn.clausal", DYN_SRC)
    assert main([str(p)]) == 1
    out = capsys.readouterr().out
    assert "no solution for ANY arguments" in out
    assert "no clause body survives" not in out
```

- [ ] **Step 2: Run to verify they fail**

Run: `cd /workspace/clausal-bug-fix && PYTHONPATH=/workspace/clausal-bug-fix /home/node/.pyenv/versions/3.13.3/bin/python -m pytest tests/test_testing_descent.py -q -p no:cacheprovider`
Expected: the two new descent tests FAIL on `"no clause body survives"`; `test_zero_clause_predicate_keeps_old_message` may already pass (it asserts absence).

- [ ] **Step 3: Implement.**

(a) Constants, after `DIAG_MAX_DEPTH` (~line 66):

```python
#: Rung-3 descent: how many predicate-call levels below the failing goal.
DIAG_MAX_DESCENT_DEPTH = 2
#: ...how many clauses per descended predicate.
DIAG_MAX_DESCENT_CLAUSES = 4
#: ...how many leaf findings in total.
DIAG_MAX_DESCENT_LEAVES = 6
#: ...how many bindings per leaf.
DIAG_MAX_DESCENT_BINDINGS = 4
```

(b) `GoalDiagnostic`: add `descent: list[str] = field(default_factory=list)`; in `lines()`, after the `nearest_examples` loop from Task 2:

```python
        for line in self.descent:
            out.append(f"{indent}  {line}")
```

(c) Split `_reified_goals` so the descent can reach heads and skip the arity gate:

```python
def _reified_clause(path, clause):
    """The reified ``Clause(head, goals, position)`` matching *clause*'s
    position, or ``None``.  Cache shared with :func:`_reified_goals`."""
    if path is None or not clause.position:
        return None
    try:
        from clausal.reflection import Clause as ReifiedClause, reify_file

        key = str(path)
        items = _REIFY_CACHE.get(key)
        if items is None:
            items = list(reify_file(key))
            if len(_REIFY_CACHE) >= _REIFY_CACHE_MAX:
                _REIFY_CACHE.pop(next(iter(_REIFY_CACHE)), None)
            _REIFY_CACHE[key] = items
        want = tuple(clause.position)
        for item in items:
            if not isinstance(item, ReifiedClause):
                continue
            pos = getattr(item, "position", None)
            if pos is not None and tuple(pos) == want:
                return item
    except Exception:  # noqa: BLE001 - source text is a nicety, never fatal
        return None
    return None


def _reified_goals(path, clause, arity):
    """(docstring unchanged from today)"""
    item = _reified_clause(path, clause)
    if item is None:
        return None
    try:
        goals = list(item.goals or ())
    except Exception:  # noqa: BLE001
        return None
    return goals if len(goals) == arity else None
```

(d) New section after Stage 3 (`_reify_value`), before "Report formatting":

```python
# ── Stage 4: descent into the failing predicate ──────────────────────────────


def _report_descent(diag, goal, logic_module, deadline, path) -> None:
    """Rung-3 refinement: walk the failing predicate's own clause bodies.

    Only called after the all-holes probe proved the predicate unsatisfiable.
    On any leaf findings, upgrades ``nearest_note`` and fills ``descent``;
    otherwise leaves the rung-3 sentence exactly as it was.
    """
    notes: list[str] = []
    leaves, kind = _descend(goal, logic_module, path, deadline, 1, frozenset(), notes)
    if kind == "leaves" and leaves:
        diag.nearest_note = (
            "the predicate has no solution for ANY arguments at this point; "
            "no clause body survives:"
        )
        if len(leaves) > DIAG_MAX_DESCENT_LEAVES:
            notes.append(
                f"only the first {DIAG_MAX_DESCENT_LEAVES} of {len(leaves)} "
                f"descent findings are shown"
            )
            leaves = leaves[:DIAG_MAX_DESCENT_LEAVES]
        diag.descent = leaves
        diag.notes.extend(notes)


def _resolve_predicate(goal, logic_module, caller_path):
    """``goal.func``'s name → ``(PredicateMeta, defining module, source path)``.

    Resolution order: the caller's module dict under the exact (possibly
    dotted) name; the attribute on the imported Python module for a dotted
    name; the bare last segment in the caller's module dict (imports land
    there).  A clause body's own names resolve in the module that DEFINED the
    clause, so the defining module — not the caller's — is returned alongside.

    A predicate defined in the caller's own module keeps *caller_path*:
    ``load_clausal_module`` pops the test module from ``sys.modules`` after
    loading, so the ``sys.modules`` route is a dead end exactly there.
    """
    from clausal.logic.predicate import PredicateMeta
    from clausal.terms import LoadName

    func = getattr(goal, "func", None)
    if not isinstance(func, LoadName):
        return None
    name = str(func.name)
    md = getattr(logic_module, "module_dict", None) or {}
    candidates = [md.get(name)]
    if "." in name:
        prefix, last = name.rsplit(".", 1)
        candidates.append(getattr(sys.modules.get(prefix), last, None))
        candidates.append(md.get(last))
    for cls in candidates:
        if isinstance(cls, PredicateMeta) and cls._clauses:
            if cls.__module__ == getattr(logic_module, "name", None):
                return cls, logic_module, caller_path
            defining = sys.modules.get(cls.__module__)
            def_lm = getattr(defining, "__dict__", {}).get("$module") if defining else None
            src = getattr(defining, "__file__", None) if defining else None
            return cls, (def_lm or logic_module), src
    return None


def _head_prefix(head, goal):
    """``Unify(head_arg, goal_arg)`` goals matching *goal* onto *head*, or
    ``None`` when the shapes cannot correspond (arity or keyword mismatch)."""
    from clausal.logic.predicate import term_field_names
    from clausal.pythonic_ast.nodes import Unify

    args = list(goal.args or ())
    kwargs = list(goal.kwargs or ())
    if hasattr(head, "args"):
        hargs, names = list(head.args), None
    else:
        names = list(term_field_names(head))
        hargs = [getattr(head, n) for n in names]
    if len(args) + len(kwargs) != len(hargs):
        return None
    pre = [Unify(left=h, right=g) for h, g in zip(hargs, args)]
    if kwargs:
        if names is None:
            return None
        positional = set(names[:len(args)])
        for kw in kwargs:
            kw_name = str(kw.name)
            if kw_name not in names or kw_name in positional:
                return None
            pre.append(Unify(left=hargs[names.index(kw_name)], right=kw.value))
    return pre


def _descend(goal, logic_module, caller_path, deadline, depth, seen, notes):
    """Leaf report lines for *goal*'s predicate, with a kind tag.

    Returns ``(lines, kind)``; kind is ``"leaves"`` (per-route failing
    conjuncts), ``"head_listing"`` (every clause head failed to unify —
    Task 5), or ``"none"`` (could not resolve / nothing to say, caller keeps
    its own rendering).
    """
    resolved = _resolve_predicate(goal, logic_module, caller_path)
    if resolved is None:
        return [], "none"
    cls, sub_lm, sub_path = resolved
    key = (cls.__module__, cls.__name__)
    if key in seen:
        return [], "none"
    seen = seen | {key}
    clauses = list(cls._clauses)
    total = len(clauses)
    if total > DIAG_MAX_DESCENT_CLAUSES:
        notes.append(
            f"descent walked only the first {DIAG_MAX_DESCENT_CLAUSES} of "
            f"{total} clauses of {cls.__name__}"
        )
        clauses = clauses[:DIAG_MAX_DESCENT_CLAUSES]
    leaves: list[str] = []
    mismatches = 0
    for clause in clauses:
        if time.monotonic() > deadline:
            raise _DiagBudgetExceeded()
        try:
            clause_lines, state = _clause_leaves(
                clause, goal, sub_lm, sub_path, deadline, depth, seen, notes)
        except (_DiagBudgetExceeded, RecursionError, *_FATAL):
            raise
        except BaseException:  # noqa: BLE001 - a broken probe is not a finding
            continue
        if state == "head_mismatch":
            mismatches += 1
        elif state == "leaves":
            leaves.extend(clause_lines)
    if mismatches == len(clauses) and clauses:
        # Task 5 turns this into the head listing; until then, nothing to say.
        return [], "none"
    return (leaves, "leaves") if leaves else ([], "none")


def _clause_leaves(clause, goal, logic_module, path, deadline, depth, seen, notes):
    """Report lines for one clause route: ``(lines, state)`` where state is
    ``"leaves"``, ``"head_mismatch"`` (head or hoisted structural arg failed to
    unify — this clause was never a route) or ``"skip"`` (probe artifact or
    re-run disagreement — say nothing)."""
    from clausal.logic.variables import Trail
    from clausal.pythonic_ast.nodes import Unify

    pre = _head_prefix(clause.head, goal)
    if pre is None:
        return [], "head_mismatch"
    body = list(clause.body or ())[:DIAG_MAX_GOALS]

    # Tail-align source conjuncts: _normalize_structural_head_args PREPENDS
    # Unify goals for structural head args, so the runtime body may be longer
    # than its source.  k is that prepended count.
    reified = _reified_clause(path, clause)
    rgoals = list(reified.goals or ()) if reified is not None else None
    k = 0
    if rgoals is not None:
        k = len(body) - len(rgoals)
        if k < 0 or not all(isinstance(g, Unify) for g in body[:k]):
            rgoals, k = None, 0

    goals_list = pre + body
    failing, raised = _first_failing(goals_list, logic_module, deadline)
    if raised is not None:
        return [], "skip"          # probe artifact, never reported as cause
    if failing is None:
        notes.append(
            f"a clause of {type(clause.head).__name__} re-ran satisfiable "
            f"during descent — non-determinism, or state changed by the run"
        )
        return [], "skip"
    if failing <= len(pre) + k:
        return [], "head_mismatch"  # failed while matching head arguments

    idx = failing - 1               # into goals_list
    leaf = goals_list[idx]
    src_idx = idx - len(pre) - k    # into rgoals
    reified_leaf = (
        rgoals[src_idx]
        if rgoals is not None and 0 <= src_idx < len(rgoals) else None
    )

    trail = Trail()
    gen = None
    try:
        prefix_goals = goals_list[:idx]
        if prefix_goals:
            gen = _solutions(_conjunction(prefix_goals), logic_module, trail)
            if next(gen, None) is None:
                return [], "skip"
        # (Task 4 inserts the recursion here.)
        lines = [_descent_leaf_line(leaf, reified_leaf, clause, path)]
        for name, value in _leaf_bindings(leaf, reified_leaf):
            lines.append(f"    {name} = {value}")
        return lines, "leaves"
    except (_DiagBudgetExceeded, RecursionError, *_FATAL):
        raise
    except BaseException:  # noqa: BLE001
        return [], "skip"
    finally:
        if gen is not None:
            gen.close()
        _undo(trail)


def _descent_leaf_line(leaf, reified_leaf, clause, path) -> str:
    """``file:line  <source text>`` for one leaf conjunct."""
    text = None
    if reified_leaf is not None:
        try:
            from clausal.reflection import render_source

            text = render_source(reified_leaf)
        except Exception:  # noqa: BLE001
            text = None
    if text is None:
        from clausal.terms import term_str

        try:
            text = term_str(leaf)
        except Exception:  # noqa: BLE001
            text = repr(leaf)
    line = None
    pos = getattr(leaf, "position", None)
    if isinstance(pos, (tuple, list)) and pos:
        line = pos[0]
    if line is None and clause.position:
        line = clause.position[0]
    label = os.path.basename(str(path)) if path else "?"
    return f"{label}:{line}  {text}" if line is not None else f"{label}  {text}"


def _leaf_bindings(leaf, reified_leaf) -> list[tuple[str, str]]:
    """Up to DIAG_MAX_DESCENT_BINDINGS named, bound variables of the leaf."""
    from clausal.logic.variables import deref, is_var

    if reified_leaf is None:
        return []
    named = _collect_named([leaf], [reified_leaf]) or []
    out: list[tuple[str, str]] = []
    seen_ids: set[int] = set()
    for name, var in named:
        if id(var) in seen_ids:
            continue
        seen_ids.add(id(var))
        value = deref(var)
        if is_var(value):
            continue
        try:
            out.append((name, _render_value(value)))
        except Exception:  # noqa: BLE001
            continue
        if len(out) >= DIAG_MAX_DESCENT_BINDINGS:
            break
    return out
```

(e) Thread the path and wire in the descent:

- `_report_nearest(diag, goal, reified_goal, logic_module, deadline)` becomes
  `_report_nearest(diag, goal, reified_goal, logic_module, deadline, path)`. Update both
  call sites in `_diagnose_into` (~lines 452 and 457) to append the `path` argument they
  already hold as a parameter.
- The rung-3 `else:` branch written in Task 2 becomes:

```python
    else:
        diag.nearest_note = (
            "the predicate has no solution for ANY arguments at this point "
            "(check the goals that produced its inputs, or its own clauses)"
        )
        _report_descent(diag, goal, logic_module, deadline, path)
```

- [ ] **Step 4: Run the descent tests and both existing suites**

Run: `cd /workspace/clausal-bug-fix && PYTHONPATH=/workspace/clausal-bug-fix /home/node/.pyenv/versions/3.13.3/bin/python -m pytest tests/test_testing_descent.py tests/test_testing_diagnostics.py tests/test_testing_cli.py -q -p no:cacheprovider`
Expected: all pass. Watch `test_predicate_with_no_solutions_at_all` in the old suite — it asserts `"no solution" in out`, which the new sentence still contains; it now also gets a descent block, which it does not forbid.

- [ ] **Step 5: Commit**

```bash
git add clausal/testing.py tests/test_testing_descent.py
git commit -m "feat(testing): rung 3 descends into the failing predicate's clauses"
```

---

### Task 4: Recursion — depth 2, cross-module, depth cap

**Files:**
- Modify: `clausal/testing.py` — the marked spot in `_clause_leaves`
- Test: `tests/test_testing_descent.py`

**Interfaces:**
- Consumes: `_descend(goal, logic_module, deadline, depth, seen, notes)` and the live-prefix scope in `_clause_leaves` (Task 3).
- Produces: recursion behavior only; signatures unchanged.

- [ ] **Step 1: Write the failing tests:**

```python
# ── recursion ────────────────────────────────────────────────────────────────

NESTED_SRC = """
inner_rule(N) <- (N > 100),
outer_rule(N) <- (inner_rule(N)),

Test("nested failure") <- (
    outer_rule(5)
),
"""


def test_descends_through_intermediate_predicate(capsys, tmp_path):
    p = write(tmp_path, "nested.clausal", NESTED_SRC)
    assert main([str(p)]) == 1
    out = capsys.readouterr().out
    assert "N > 100" in out   # the inner predicate's conjunct, not inner_rule(N)
    assert "N = 5" in out


def test_cross_module_descent(capsys, tmp_path, monkeypatch):
    import sys as _sys
    monkeypatch.syspath_prepend(str(tmp_path))
    _sys.modules.pop("descent_lib", None)
    write(tmp_path, "descent_lib.clausal", """
        -module(descent_lib, [lib_check(N)])

        lib_check(N) <- (N > 100, N < 200)
    """)
    p = write(tmp_path, "use.clausal", """
        -import_from(descent_lib, [lib_check])

        Test("cross-module") <- (
            lib_check(5)
        ),
    """)
    try:
        assert main([str(p)]) == 1
        out = capsys.readouterr().out
        assert "no clause body survives" in out
        assert "N > 100" in out
        assert "N = 5" in out
        assert "descent_lib.clausal:" in out   # leaf names the DEFINING file
    finally:
        _sys.modules.pop("descent_lib", None)


DEEP_SRC = """
lvl3(N) <- (N > 100),
lvl2(N) <- (lvl3(N)),
lvl1(N) <- (lvl2(N)),

Test("three levels") <- (
    lvl1(5)
),
"""


def test_depth_cap_stops_at_two_levels(capsys, tmp_path):
    p = write(tmp_path, "deep.clausal", DEEP_SRC)
    assert main([str(p)]) == 1
    out = capsys.readouterr().out
    assert "lvl3(" in out          # depth-2 leaf is the lvl3 CALL...
    assert "N > 100" not in out    # ...not lvl3's body — depth cap held
```

- [ ] **Step 2: Run to verify** — `test_descends_through_intermediate_predicate` FAILS (leaf today is `inner_rule(N)`, so `N > 100` is absent). `test_depth_cap_stops_at_two_levels` may already pass; keep it as the cap's regression guard.

Run: `cd /workspace/clausal-bug-fix && PYTHONPATH=/workspace/clausal-bug-fix /home/node/.pyenv/versions/3.13.3/bin/python -m pytest tests/test_testing_descent.py -q -p no:cacheprovider`

- [ ] **Step 3: Implement** — at the `# (Task 4 inserts the recursion here.)` marker in `_clause_leaves`, with the prefix bindings live (this is why the recursion sits inside the `gen` scope — the inner head prefix must see the concrete argument values):

```python
        from clausal.terms import Call

        if depth < DIAG_MAX_DESCENT_DEPTH and isinstance(leaf, Call):
            deeper, deeper_kind = _descend(
                leaf, logic_module, path, deadline, depth + 1, seen, notes)
            if deeper_kind == "leaves" and deeper:
                return deeper, "leaves"
            # "head_listing" is attached beneath this leaf in Task 5;
            # "none" falls through to render this conjunct as the leaf.
```

- [ ] **Step 4: Run all three test files again** (same command as Task 3 step 4). Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add clausal/testing.py tests/test_testing_descent.py
git commit -m "feat(testing): descent recurses one more level, capped at depth 2"
```

---

### Task 5: No-head-match listing

**Files:**
- Modify: `clausal/testing.py` — `_descend` (mismatch tally branch), `_clause_leaves` (recursion branch), `_report_descent` (new kind), new helper `_head_listing`
- Test: `tests/test_testing_descent.py`

**Interfaces:**
- Consumes: `_reified_clause` (Task 3) for source-faithful heads.
- Produces: `_descend` kind `"head_listing"`; `_head_listing(cls, clauses, path) -> list[str]`.

- [ ] **Step 1: Write the failing tests** (this is the working_time `[H|T]`-as-`BitOr` shape — a cons head written with `|` parses as `BitOr` and can never unify with a list):

```python
# ── no clause head matches ───────────────────────────────────────────────────

CONS_SRC = """
-private([work])

wk_totals([], 0),
wk_totals([MINS, STATUS] | REST, TOTAL) <- (
    wk_totals(REST, SUB),
    TOTAL == SUB + MINS
),

Test("cons head never matches") <- (
    wk_totals([[2880, work]], 2880)
),
"""


def test_all_heads_fail_lists_the_heads(capsys, tmp_path):
    p = write(tmp_path, "cons.clausal", CONS_SRC)
    assert main([str(p)]) == 1
    out = capsys.readouterr().out
    assert "no clause head unifies" in out
    assert "| REST" in out               # the BitOr head, source-faithful
    assert "wk_totals([], 0)" in out     # the base case is listed too


CONS_NESTED_SRC = """
-private([work])

wkn_totals([], 0),
wkn_totals([MINS, STATUS] | REST, TOTAL) <- (
    wkn_totals(REST, SUB),
    TOTAL == SUB + MINS
),

wkn_check(WEEKS) <- (
    wkn_totals(WEEKS, _TOTAL)
),

Test("nested cons head") <- (
    wkn_check([[2880, work]])
),
"""


def test_head_listing_attaches_beneath_parent_leaf(capsys, tmp_path):
    p = write(tmp_path, "consn.clausal", CONS_NESTED_SRC)
    assert main([str(p)]) == 1
    out = capsys.readouterr().out
    assert "wkn_totals(WEEKS, _TOTAL)" in out   # the parent leaf conjunct
    assert "no clause head unifies" in out
    assert "| REST" in out
    assert "WEEKS = [[2880, work]]" in out
```

- [ ] **Step 2: Run to verify both FAIL** on `"no clause head unifies"`.

Run: `cd /workspace/clausal-bug-fix && PYTHONPATH=/workspace/clausal-bug-fix /home/node/.pyenv/versions/3.13.3/bin/python -m pytest tests/test_testing_descent.py -q -p no:cacheprovider`

- [ ] **Step 3: Implement.**

(a) Helper, next to `_descent_leaf_line`:

```python
def _head_listing(cls, clauses, path) -> list[str]:
    """One ``file:line  <head source>`` line per clause, source-faithful."""
    lines = []
    label = os.path.basename(str(path)) if path else cls.__module__
    for clause in clauses:
        text = None
        reified = _reified_clause(path, clause)
        if reified is not None:
            try:
                from clausal.reflection import render_source

                text = render_source(reified.head)
            except Exception:  # noqa: BLE001
                text = None
        if text is None:
            from clausal.terms import term_str

            try:
                text = term_str(clause.head)
            except Exception:  # noqa: BLE001
                text = repr(clause.head)
        line = clause.position[0] if clause.position else None
        lines.append(f"{label}:{line}  {text}" if line is not None
                     else f"{label}  {text}")
    return lines
```

(b) In `_descend`, replace the mismatch-tally return:

```python
    if mismatches == len(clauses) and clauses:
        return _head_listing(cls, clauses, path=sub_path), "head_listing"
```

(c) In `_clause_leaves`' recursion branch (Task 4), handle the new kind — the listing attaches *beneath* this conjunct's leaf line so the reader sees the concrete arguments directly above the heads that reject them:

```python
            if deeper_kind == "head_listing" and deeper:
                lines = [_descent_leaf_line(leaf, reified_leaf, clause, path)]
                for name, value in _leaf_bindings(leaf, reified_leaf):
                    lines.append(f"    {name} = {value}")
                lines.append("    no clause head unifies with these arguments; "
                             "the heads are:")
                lines.extend(f"      {line}" for line in deeper)
                return lines, "leaves"
```

(d) In `_report_descent`, handle a top-level head listing (the test goal itself hits the unmatchable predicate; its source and bindings are already printed above by stages 1–2):

```python
    elif kind == "head_listing" and leaves:
        diag.nearest_note = (
            "the predicate has no solution for ANY arguments at this point; "
            "no clause head unifies with these arguments — the heads are:"
        )
        diag.descent = leaves[:DIAG_MAX_DESCENT_LEAVES]
        diag.notes.extend(notes)
```

- [ ] **Step 4: Run all three test files** (same command as Task 3 step 4). Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add clausal/testing.py tests/test_testing_descent.py
git commit -m "feat(testing): descent reports when no clause head unifies, listing the heads"
```

---

### Task 6: Clause cap note

**Files:**
- Test: `tests/test_testing_descent.py` (implementation already landed in Task 3; this task proves the cap and its note)

**Interfaces:** none new.

- [ ] **Step 1: Write the test:**

```python
# ── caps are noted, never silent ─────────────────────────────────────────────

SIX_SRC = """
-private([r1, r2, r3, r4, r5, r6])

sixway(N, r1) <- (N > 100),
sixway(N, r2) <- (N > 100),
sixway(N, r3) <- (N > 100),
sixway(N, r4) <- (N > 100),
sixway(N, r5) <- (N > 100),
sixway(N, r6) <- (N > 100),

Test("six clauses") <- (
    sixway(5, _R)
),
"""


def test_clause_cap_is_applied_and_noted(capsys, tmp_path):
    p = write(tmp_path, "six.clausal", SIX_SRC)
    assert main([str(p)]) == 1
    out = capsys.readouterr().out
    assert out.count("N > 100") == 4          # DIAG_MAX_DESCENT_CLAUSES leaves
    assert "first 4 of 6 clauses" in out      # the truncation is stated
```

- [ ] **Step 2: Run it.** Expected: PASS if Task 3's cap code is correct; if it fails, fix the cap/note wording in `_descend` to match (`descent walked only the first 4 of 6 clauses of sixway`).

Run: `cd /workspace/clausal-bug-fix && PYTHONPATH=/workspace/clausal-bug-fix /home/node/.pyenv/versions/3.13.3/bin/python -m pytest tests/test_testing_descent.py -q -p no:cacheprovider`

- [ ] **Step 3: Commit**

```bash
git add tests/test_testing_descent.py clausal/testing.py
git commit -m "test(testing): descent clause cap is applied and noted"
```

---

### Task 7: End-to-end verification and close-out

**Files:**
- Modify: `todo/B-assertion-diagnostic-stops-one-level-above-the-cause.md` (move to `todo/done/`)

**Interfaces:** none.

- [ ] **Step 1: schengen** — the wrong-type argument becomes visible:

```bash
S=/workspace/clausify-executor-train/_reruns/study13/study_schengen_max_stay_r1/scratch
cd $S && PYTHONPATH=/workspace/clausal-bug-fix:/workspace/clausify/kit:/workspace/clausify:$S \
  /home/node/.pyenv/versions/3.13.3/bin/python -m clausal.testing \
  eu/schengen_90_180_max_stay/tests/test_public_interface.clausal > /tmp/e2e_schengen.txt 2>&1
grep -c "no clause body survives" /tmp/e2e_schengen.txt          # expect >= 1
grep "window_days_used" /tmp/e2e_schengen.txt                    # the leaf
grep "REFERENCE_DATE_OBJ" /tmp/e2e_schengen.txt                  # its binding
```

Expected: for the `days_used` tests, a leaf naming `window_days_used(HISTORY, REFERENCE_DATE_OBJ, WINDOW_SIZE, DAYS_USED)` with `REFERENCE_DATE_OBJ` and `WINDOW_SIZE = 180` bound. (The recursion into `kit.rolling_window` raises on compiling a live `date` — a probe artifact — so the descent correctly falls back to this conjunct as the leaf.)

- [ ] **Step 2: vat** — the contradictory guard is named:

```bash
S=/workspace/clausify-executor-train/_reruns/study13/study_vat_pro_rata_deduction_r2/scratch
cd $S && PYTHONPATH=/workspace/clausal-bug-fix:/workspace/clausify/kit:/workspace/clausify:$S \
  /home/node/.pyenv/versions/3.13.3/bin/python -m clausal.testing \
  eu/vat/pro_rata_deduction/tests/test_public_interface.clausal > /tmp/e2e_vat.txt 2>&1
grep "RAW_PCT > 100" /tmp/e2e_vat.txt        # the guard, from clause 2
grep "TOTAL_CENTS <= 0" /tmp/e2e_vat.txt     # the route-1 leaf
grep "RAW_PCT = 50" /tmp/e2e_vat.txt         # the value that dooms it
```

- [ ] **Step 3: working_time** — the `|` heads are listed:

```bash
S=/workspace/clausify-executor-train/_reruns/study13/study_working_time_average_r1/scratch
cd $S && PYTHONPATH=/workspace/clausal-bug-fix:/workspace/clausify/kit:/workspace/clausify:$S \
  /home/node/.pyenv/versions/3.13.3/bin/python -m clausal.testing \
  eu/labour/working_time_average/tests/test_public_interface.clausal > /tmp/e2e_wta.txt 2>&1
grep "no clause head unifies" /tmp/e2e_wta.txt
grep -F "| REST_WEEKS" /tmp/e2e_wta.txt      # the BitOr head, source-faithful
grep "wt_compliance(" /tmp/e2e_wta.txt       # facade tests' depth-2 leaf
```

If any of steps 1–3 misses its expected strings, STOP and debug before proceeding — the archived trees are the ground truth this feature exists for.

- [ ] **Step 4: Full-suite regression gate**

```bash
cd /workspace/clausal-bug-fix && PYTHONPATH=/workspace/clausal-bug-fix \
  /home/node/.pyenv/versions/3.13.3/bin/python -m pytest tests/ -q -p no:cacheprovider 2>&1 | tail -5
```

Expected: same failure SET as the 2026-07-30 baseline — exactly one standing failure, `tests/test_doc_snippet_coverage.py::test_no_raw_untested_blocks`. Two tests are load-marginal and must be re-run alone before being read as regressions: `test_F026_multi_star_splits_bounded_for_moderate_input` and `test_06_clpfd.py::TestOracles::test_queens8_count`.

- [ ] **Step 5: Move the todo to done** — append an `## Outcome` section (one paragraph: what landed, the three e2e results, branch name) to `todo/B-assertion-diagnostic-stops-one-level-above-the-cause.md`, then:

```bash
cd /workspace/clausal-bug-fix
mv todo/B-assertion-diagnostic-stops-one-level-above-the-cause.md todo/done/
git add todo/done/B-assertion-diagnostic-stops-one-level-above-the-cause.md
git commit -m "todo(done): assertion diagnostic descends into the failing predicate"
```

(The file is currently untracked, so `mv` + `git add` of the explicit destination path is correct; do not `git add -A`.)

---

## Self-Review Notes

- **Spec coverage:** shared walk → Task 1; rung 2 examples → Task 2; descent core, module switch, tail-alignment, bindings, caps, `GoalDiagnostic` fields → Task 3; recursion/depth/cross-module → Task 4; no-head-match listing (top-level and nested) → Task 5; clause-cap note → Task 6; e2e per-case expectations + regression gate → Task 7. Cycle guard: the `seen` frozenset in Task 3's `_descend`. Leaves cap: enforced + noted in `_report_descent` (no dedicated test — constructing >6 natural leaves needs a contrived deep fan; the cap code is 4 lines and the clause cap test covers the "caps are noted" contract).
- **Disagreement honesty:** a clause that re-runs satisfiable during descent contradicts the all-holes probe; it yields no leaf and appends a note (Task 3, `_clause_leaves` `failing is None` branch).
- **Types:** `_descend` returns `(list[str], str)` everywhere; `_clause_leaves` returns `(list[str], str)` with states `"leaves" | "head_mismatch" | "skip"`; both consistent across Tasks 3–5.
