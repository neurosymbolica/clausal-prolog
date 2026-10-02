# One Drive Loop Per Language — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Collapse the six-plus-one trampoline drive-loop copies to one parameterised C core and one pure-Python twin, lock the pair together with a parity corpus, and fix the newly confirmed `catch/3`-inside-ITE-condition routing bug.

**Architecture:** The shared primitive is "advance the chain to the next root yield" (`drive_to_root_yield`): a `static inline` helper in `_trampoline.c` and a private function in a new `clausal/logic/_trampoline_py.py`, each with two boolean policy flags (`intercept_ts`, `stopiteration_is_exhaustion`) that are compile-time constants at every call site. `trampoline` / `solutions` / `_drive_until_yield` become thin stop-condition wrappers. `_tramp_call`, `_naf_has_solution`, and the general-ITE lowering stop owning loops and call `_drive_until_yield` (the C loop in a built tree). A parity test module drives hand-built `StepGenerator` chains against both implementations.

**Tech Stack:** CPython 3.13 C extension (`setup.py build_ext --inplace`), pytest, the clausal `.clausal` import hook for fixtures.

**Spec:** `docs/superpowers/specs/2026-08-26-one-drive-loop-design.md`

## Global Constraints

- Run all tests and benchmarks **from the clone** (`cd /workspace/clausal-bug-fix`) with `/workspace/clausal/venv/bin/python` — cwd wins over site-packages, so this runs the clone's code on the canonical venv.
- The session cgroup has a 4 GiB memory cap: never run the full suite in one process. Run it in ~8 chunks of `tests/test_*.py` and compare failure **sets** (names), never counts, against a baseline captured before your first change. The clone's known baseline is ~1 pre-existing failure.
- Rebuild the C extension after every `.c` edit: `/workspace/clausal/venv/bin/python setup.py build_ext --inplace` (run from the clone; in a worktree, build there before running anything).
- **C is canonical.** When the parity corpus shows the two implementations disagreeing, fix `_trampoline_py.py` (or the corpus expectation, if C's behaviour is what the suite depends on) — never adjust the C side to match Python. Record every divergence found in the commit message.
- Performance is a gate, not an aspiration (spec §Performance): no new per-iteration allocation, indirect call, or runtime flag dispatch in the C steady-state step path; flags must be literal constants at call sites. Task 6 and 7 have explicit benchmark acceptance steps.
- This clone is shared with other Claude instances: **never `git add -A`**. Stage explicit paths only.
- Clausal syntax gotchas (verified 2026-08-26): general if-then-else is `If(COND, THEN, ELSE)` (Python ternaries are a SyntaxError); `is` binds strings (`R is "then"`), `==` is arithmetic/FD equality and raises `type_error` on non-numeric unbound comparisons; end every clause with a trailing comma; undeclared singletons warn unless the variable starts with `_` and the file has `-allow_singletons`.
- Commit trailer for every commit:

  ```
  Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
  Claude-Session: https://claude.ai/code/session_011g1cBsRmJVg7NB3WoPbEUJ
  ```

**Scratch directory** for baselines and chunk lists (referenced by several tasks):
`/tmp/claude-1000/-workspace-clausal-bug-fix/ab837532-1550-4583-b543-4d615aea2a09/scratchpad` — call it `$SCRATCH` below.

---

### Task 1: NAF/ITE benchmark workload + baselines

The spec requires a workload isolating the NAF and general-ITE drive paths (nothing in `benchmarks/` exercises them today), plus a captured performance and test-failure baseline before anything changes.

**Files:**
- Create: `tests/fixtures/bench_naf_ite.seam`
- Modify: `benchmarks/workloads.py` (add `bench_naf_ite`, register in the `__main__` list)

**Interfaces:**
- Produces: `bench_naf_ite(n: int = 300) -> str` in `benchmarks/workloads.py` — later tasks re-run it by exactly that name and compare against the baseline file `$SCRATCH/bench_baseline.txt`. Also produces `$SCRATCH/suite_baseline.txt` (sorted failing-test names).

- [ ] **Step 1: Write the fixture**

Create `tests/fixtures/bench_naf_ite.seam`:

```
# Workload fixture for benchmarks/workloads.py::bench_naf_ite.
#
# Four recursive loops, each stressing one drive-loop consumer shape:
#   NafFactLoop  — `not` over a goal that fails almost immediately
#                  (the helper-call-per-solution overhead shape)
#   NafChainLoop — `not` over a goal that takes many trampoline steps
#                  before failing (the C-stepping win shape)
#   IteDetLoop   — general ITE, single-solution condition
#   IteMultiLoop — general ITE, ten-solution condition (then-branch runs
#                  once per condition solution)
-module(bench_naf_ite, [
    Item(X),
    MultiStep(X, Y),
    NoPair(X),
    NafFactLoop(N),
    NafChainLoop(N),
    IteDetLoop(N),
    IteMultiLoop(N),
])
-allow_singletons

Item(1),
Item(2),
Item(3),
Item(4),
Item(5),

# 10 solutions (pairs with Y > X); a user-predicate condition is not
# reifiable, so If(MultiStep(...), ...) takes the general-ITE arm.
MultiStep(X, Y) <- (Item(X), Item(Y), Y > X),

# Fails only after enumerating all 25 Item pairs — a many-step NAF goal.
NoPair(S) <- (Item(A), Item(B), S == A + B),

NafFactLoop(0),
NafFactLoop(N) <- (N > 0, not Item(0), M == N - 1, NafFactLoop(M)),

NafChainLoop(0),
NafChainLoop(N) <- (N > 0, not NoPair(99), M == N - 1, NafChainLoop(M)),

IteDetLoop(0),
IteDetLoop(N) <- (N > 0, If(Item(1), true, true), M == N - 1, IteDetLoop(M)),

IteMultiLoop(0),
IteMultiLoop(N) <- (N > 0, If(MultiStep(_X, _Y), true, true), M == N - 1, IteMultiLoop(M)),
```

- [ ] **Step 2: Add the workload function**

In `benchmarks/workloads.py`, after `bench_tabling`, add:

```python
def bench_naf_ite(n: int = 300) -> str:
    """NAF + general-ITE drive loops — stresses ``$naf_has_solution`` and the
    ITE condition driver in both the trivial one-step and many-step shapes.

    Each sub-loop recurses *n* times; every iteration drives one NAF or ITE
    mini-trampoline.  See tests/fixtures/bench_naf_ite.seam for the four
    shapes.  Expected wall time: 0.2–1.0 s total (tune *n* to land there).
    """
    from clausal.testing import load_clausal_module

    fixture = os.path.join(_FIXTURES, "bench_naf_ite.seam")
    mod = load_clausal_module(fixture)
    for name in ("NafFactLoop", "NafChainLoop", "IteDetLoop", "IteMultiLoop"):
        pred = getattr(mod, name)
        for _ in pred(n):
            break
        else:
            raise RuntimeError(f"{name}({n}) produced no solutions")
    return "ok"
```

And register it in the `__main__` workload list:

```python
        ("bench_naf_ite",  lambda: bench_naf_ite()),
```

- [ ] **Step 3: Run it; tune n into the 0.2–1.0 s band**

```bash
cd /workspace/clausal-bug-fix && /workspace/clausal/venv/bin/python benchmarks/workloads.py
```

Expected: all six workloads print a result and a time; `bench_naf_ite` prints `result='ok'`. If `bench_naf_ite` is under 0.2 s or over 1.0 s, change the default `n` (and re-run) until it lands in the band; commit whatever `n` you settled on. If any loop raises (e.g. a syntax slip in the fixture), fix the fixture — the Global Constraints syntax notes cover the likely mistakes.

- [ ] **Step 4: Capture the benchmark baseline (medians of 5)**

```bash
cd /workspace/clausal-bug-fix
for i in 1 2 3 4 5; do /workspace/clausal/venv/bin/python benchmarks/workloads.py; done | tee $SCRATCH/bench_baseline_runs.txt
for i in 1 2 3; do /workspace/clausal/venv/bin/python benchmarks/microbench.py; done | tee $SCRATCH/microbench_baseline_runs.txt
```

Write the per-workload **median** times by hand into `$SCRATCH/bench_baseline.txt` (one `name median_seconds` line per workload, plus the microbench trampoline-dispatch and StepGenerator-allocation medians). Later tasks diff against this file.

- [ ] **Step 5: Capture the suite failure-set baseline**

```bash
cd /workspace/clausal-bug-fix
ls tests/test_*.py | split -n r/8 - $SCRATCH/chunk_
for f in $SCRATCH/chunk_*; do
  /workspace/clausal/venv/bin/python -m pytest $(tr '\n' ' ' < $f) -q 2>&1 | grep -E "^(FAILED|ERROR)" ;
done | sort -u > $SCRATCH/suite_baseline.txt
wc -l $SCRATCH/suite_baseline.txt
```

Expected: ~1 known pre-existing failure. Whatever the set is, it is now the baseline.

- [ ] **Step 6: Commit**

```bash
cd /workspace/clausal-bug-fix
git add tests/fixtures/bench_naf_ite.seam benchmarks/workloads.py
git commit -m "bench: NAF/ITE drive-loop workload (baseline for the drive-loop refactor)"
```

Quote the baseline medians in the commit body.

---

### Task 2: `catch/3` inside a general-ITE condition — failing test, then fix

The bug is already confirmed live (2026-08-26, scratch probe): `If(cond_that_catches(...), then, else)` in trampoline mode lets the `ValueError` escape past the inner `catch/3`, because the ITE arm in `lower_python_trampoline.py` emits its own drive loop with no exception routing. The fix replaces that emitted loop with a call to the runtime's `_drive_until_yield`.

**Files:**
- Modify: `tests/fixtures/catch_trampolined.seam` (new predicates + module exports)
- Modify: `tests/test_catch_trampolined.py` (four new tests)
- Modify: `clausal/logic/compiler/lower_python_trampoline.py:99-181` (the `Branch(reified_test=None)` arm's `true_block`)
- Modify: `clausal/logic/compiler/predicate.py` (import + two `$drive_until_yield` injections, next to the existing `$naf_has_solution` entries at ~line 769 and ~line 1515)

**Interfaces:**
- Consumes: `_drive_until_yield(sg) -> True | None` from `clausal.logic.trampoline` (exists today; C-backed in a built tree).
- Produces: the emitted name `$drive_until_yield` in compiled-predicate globals — Task 8's follow-up todo and the spec reference it by that exact name.

- [ ] **Step 1: Add fixture predicates**

In `tests/fixtures/catch_trampolined.seam`, append to the `-module(...)` export list:

```
    cond_absorbs(R),
    ite_cond_catch(R),
    cond_declines(R),
    ite_cond_decline(R),
    ite_cond_raw(R),
    ite_multi(N),
```

and append at the end of the file:

```
# ── the SEVENTH copy: the general-ITE condition driver ──────────────────────
# If/3 with a non-reifiable (user-predicate) condition compiles to a
# mini-trampoline that drives the condition sub-generator.  Emitted inline it
# had no exception routing at all, so a catch/3 inside the CONDITION was
# inert — the ValueError walked out of the whole construct (confirmed
# 2026-08-26).  These pin the routed behaviour plus the two controls that
# must not change: a declining/absent handler still lets the error escape,
# and the then-branch still runs once per condition solution.
cond_absorbs(R) <- (catch(raise_value_error(_X), _E, R is "absorbed")),
ite_cond_catch(R) <- (If(cond_absorbs(_C), R is "then", R is "else")),

cond_declines(R) <- (catch(raise_value_error(_X), "no_such_error", R is "nope")),
ite_cond_decline(R) <- (If(cond_declines(_C), R is "then", R is "else")),

ite_cond_raw(R) <- (If(raise_value_error(_X), R is "then", R is "else")),

ite_multi(N) <- (If(counted(N), true, N == 0)),
```

- [ ] **Step 2: Add the tests**

In `tests/test_catch_trampolined.py`, after `test_catch_inside_a_goal_lambda_absorbs_the_exception`, add:

```python
# ── the general-ITE condition driver (the seventh loop copy) ─────────────────


def test_catch_inside_an_ite_condition_absorbs_the_exception(mod):
    """A catch/3 inside a general-ITE *condition* absorbs; then-branch runs.

    The condition sub-generator is driven by the ITE's own mini-trampoline,
    which — emitted inline — had no exception routing, so the ValueError
    escaped the whole construct instead of reaching the handler.
    """
    assert _answers(mod.ite_cond_catch) == [("then",)]


def test_declining_catch_in_an_ite_condition_still_lets_the_error_escape(mod):
    """Control: routing must be invisible when no handler absorbs."""
    with pytest.raises(ValueError) as exc_info:
        _answers(mod.ite_cond_decline)
    assert str(exc_info.value) == _INT_NOPE


def test_uncaught_error_in_an_ite_condition_still_escapes(mod):
    """Control: no handler at all — the original exception surfaces."""
    with pytest.raises(ValueError) as exc_info:
        _answers(mod.ite_cond_raw)
    assert str(exc_info.value) == _INT_NOPE


def test_ite_then_branch_runs_once_per_condition_solution(mod):
    """Control: the general ITE enumerates ALL condition solutions."""
    assert _answers(mod.ite_multi) == [(1,), (2,), (3,)]
```

- [ ] **Step 3: Run — expect exactly one failure**

```bash
cd /workspace/clausal-bug-fix && /workspace/clausal/venv/bin/python -m pytest tests/test_catch_trampolined.py -q
```

Expected: `test_catch_inside_an_ite_condition_absorbs_the_exception` FAILS with the raw `ValueError: invalid literal for int() with base 10: 'nope'` escaping; the three controls and all pre-existing tests PASS. If the module fails to *load*, fix the fixture syntax first (trailing commas, export list).

- [ ] **Step 4: Inject `$drive_until_yield` into compiled globals**

In `clausal/logic/compiler/predicate.py`: find the existing import (near line 61):

```python
from clausal.logic.runtime.tramp_call import (  # noqa: F401
    _tramp_call, _naf_has_solution,
)
```

Below it add:

```python
from clausal.logic.trampoline import _drive_until_yield
```

(If `predicate.py` already has a `from clausal.logic.trampoline import ...` line, extend that line instead.) Then, in **both** globals dicts — next to `"$naf_has_solution": _naf_has_solution,` at ~line 769 and again at ~line 1515 — add:

```python
        "$drive_until_yield": _drive_until_yield,
```

- [ ] **Step 5: Replace the emitted ITE loop**

In `clausal/logic/compiler/lower_python_trampoline.py`, inside the `case Branch(... reified_test=None, ...)` arm: delete the `g_name` and `v_name` `ctx.fresh` allocations and the `first_send`, `continue_send`, `step_send_normal`, `step_send_done`, `step_send`, and `true_loop_body` constructs (lines ~100–169), and replace the `true_block` assignment with:

```python
            # Drive the condition through the shared runtime loop.  Emitted
            # inline this was a seventh copy of the drive loop and the only
            # one with no exception routing, so a catch/3 inside the
            # condition never saw its exception (confirmed 2026-08-26); it
            # also treated a root-level _TABLING_SUSPEND as a solution
            # (A04-F008 shape).  $drive_until_yield is the C loop in a
            # built tree.
            true_block = [
                _assign(found_flag, ast.Constant(value=False)),
                _assign_mark(true_mark, trail_name),
                sg_create,
                ast.While(
                    test=_call(_name("$drive_until_yield"), _name(sg_name)),
                    body=[_assign(found_flag, ast.Constant(value=True))]
                    + then_stmts,
                    orelse=[],
                ),
                _undo_stmt(true_mark, trail_name),
            ]
```

Loop equivalence, for the reviewer: the old loop did `sg.send(None)`, ran `then_stmts` per root yield that wasn't `DONE`, re-pulled with `sg.send(None)`, and intercepted mid-chain `_TABLING_SUSPEND`; `_drive_until_yield(sg)` does exactly that per call (returns `True` per solution, `None` on `DONE`/root-`_TABLING_SUSPEND`/exhaustion), and the `while` re-tests after `then_stmts`, which is the same re-pull. What changes is exactly the two fixed behaviours. Also update the stale part of the module docstring (the "byte-for-byte identical / D4 harness" paragraph — that harness retired in D7c-α per `goal_shallow._compile_body_impl`'s docstring; say the `Negate` and `Branch` mini-loops now delegate to runtime helpers).

- [ ] **Step 6: Run the tests — all pass**

```bash
cd /workspace/clausal-bug-fix && /workspace/clausal/venv/bin/python -m pytest tests/test_catch_trampolined.py tests/test_reified_ite.py -q
```

Expected: PASS (including all pre-existing tests in both files).

- [ ] **Step 7: Suite chunks + failure-set diff**

Re-run the 8-chunk sweep from Task 1 Step 5 into `$SCRATCH/suite_after_task2.txt` and `diff $SCRATCH/suite_baseline.txt $SCRATCH/suite_after_task2.txt`. Expected: empty diff. Investigate any new name before proceeding.

- [ ] **Step 8: Benchmark comparison**

Run `benchmarks/workloads.py` 5× as in Task 1 Step 4; compare `bench_naf_ite` (and the other workloads) medians against `$SCRATCH/bench_baseline.txt`. Expected: `IteDetLoop`/`IteMultiLoop` shapes at least as fast (condition stepping now runs in C); everything else within noise. A regression beyond noise on any workload blocks the commit — investigate first.

- [ ] **Step 9: Commit**

```bash
cd /workspace/clausal-bug-fix
git add tests/fixtures/catch_trampolined.seam tests/test_catch_trampolined.py \
        clausal/logic/compiler/lower_python_trampoline.py clausal/logic/compiler/predicate.py
git commit -m "ite: route exceptions in the general-ITE condition driver

The trampoline Branch lowering emitted its own drive loop as generated
AST — the seventh copy, and the only unrouted one: a catch/3 inside the
condition never saw its exception, and a root-level _TABLING_SUSPEND
counted as a solution.  The condition is now driven by
\$drive_until_yield (the C loop in a built tree), like \$naf_has_solution
before it."
```

Quote the benchmark medians in the commit body.

---

### Task 3: Extract the pure-Python twin into `_trampoline_py.py`

Mechanical move, no logic change: the fallback implementations become directly importable so the parity corpus (Task 4) can address them without `sys.modules` games.

**Files:**
- Create: `clausal/logic/_trampoline_py.py`
- Modify: `clausal/logic/trampoline.py`

**Interfaces:**
- Produces: module `clausal.logic._trampoline_py` exporting `DONE`, `FINAL`, `StepGenerator`, `trampoline`, `solutions`, `_drive_until_yield`, `_is_routable`, `_unwind_to_catcher` — Tasks 4 and 5 import it by exactly this path. `clausal.logic.trampoline`'s public surface is unchanged (same names, C-preferred).

- [ ] **Step 1: Create `clausal/logic/_trampoline_py.py`**

Move, verbatim (cut from `trampoline.py`, paste here — do not retype):

- the `_is_routable` function and the routing-policy comment block above it (lines ~49–100),
- `_unwind_to_catcher` (lines ~103–125),
- everything currently inside the `except ImportError:` block, **dedented one level**: the `DONE`/`FINAL` sentinels with their comment, `class StepGenerator`, `trampoline`, `solutions`, `_drive_until_yield` (drop the now-meaningless `# type: ignore[no-redef]` comments).

Give the module this docstring:

```python
"""Pure-Python twin of the C drive loops in ``runtime/_trampoline.c``.

Always importable; in a built tree ``logic/trampoline.py`` re-exports the
C implementations and this module is reached only by
``tests/test_trampoline_parity.py``, which runs the same behavioural
corpus against both.  The C side is canonical: fix divergences HERE.

``_is_routable`` / ``_unwind_to_catcher`` also serve the always-Python
drive-loop consumers (``runtime/tramp_call.py``) regardless of which
implementation is active.
"""

from __future__ import annotations
from typing import Any, Callable, Generator
```

- [ ] **Step 2: Rewrite the seam in `trampoline.py`**

Replace everything from the `# ── Which exceptions the drive loops route…` comment block down to the end of the `except ImportError:` block (keep the module docstring, the imports it still needs, and the `Step` dataclass; keep the factorial demo and `__main__` block at the bottom) with:

```python
# ── Routing policy + pure-Python twin ────────────────────────────────────────
# The policy functions live with the pure-Python twin and are shared by the
# always-Python drive-loop consumers (runtime/tramp_call.py).
from clausal.logic._trampoline_py import (  # noqa: F401
    _is_routable, _unwind_to_catcher,
)

# ── C extension fast path ────────────────────────────────────────────────────
# _trampoline is a C extension providing optimised DONE, StepGenerator,
# trampoline, solutions and _drive_until_yield.  The pure-Python twin in
# _trampoline_py is the no-build fallback; tests/test_trampoline_parity.py
# runs both against one corpus.
try:
    from clausal.logic.runtime._trampoline import (  # type: ignore[import-untyped]
        DONE, FINAL, StepGenerator, trampoline, solutions, _drive_until_yield,
    )
except ImportError:
    from clausal.logic._trampoline_py import (  # noqa: F401
        DONE, FINAL, StepGenerator, trampoline, solutions, _drive_until_yield,
    )
```

Trim the now-unneeded `dataclass`-era imports if anything became unused (keep `dataclass` for `Step`).

- [ ] **Step 3: Verify — imports, demo, both modules**

```bash
cd /workspace/clausal-bug-fix
/workspace/clausal/venv/bin/python -m clausal.logic.trampoline
/workspace/clausal/venv/bin/python -c "
import clausal.logic._trampoline_py as p
import clausal.logic.trampoline as t
from clausal.logic.runtime._trampoline import StepGenerator as CSG
assert t.StepGenerator is CSG, 'built tree must prefer C'
assert p.StepGenerator is not CSG
print('seam OK')"
```

Expected: the factorial demo prints `All tests passed.`, then `seam OK`.

- [ ] **Step 4: Suite chunks + failure-set diff** (as Task 2 Step 7, into `suite_after_task3.txt`). Expected: empty diff.

- [ ] **Step 5: Commit**

```bash
cd /workspace/clausal-bug-fix
git add clausal/logic/_trampoline_py.py clausal/logic/trampoline.py
git commit -m "trampoline: extract the pure-Python twin into _trampoline_py

Mechanical move of the ImportError-fallback implementations into their
own always-importable module so a parity corpus can drive both
implementations in one session."
```

---

### Task 4: Parity corpus over both implementations

Hand-built `StepGenerator` chains, one corpus, both implementations. This task is *expected* to surface at least one real divergence (pre-analysed below); C is canonical.

**Files:**
- Create: `tests/test_trampoline_parity.py`
- Modify (expected, for the known divergence): `clausal/logic/_trampoline_py.py` (`StepGenerator.send`)

**Interfaces:**
- Consumes: `clausal.logic._trampoline_py` (Task 3) and `clausal.logic.runtime._trampoline`; `_TABLING_SUSPEND` from `clausal.logic.tabling` (one shared sentinel, both impls).
- Produces: the corpus module later tasks keep green; no new runtime names.

**Known divergence (analysed from source, 2026-08-26; the corpus must confirm):** when a `StepGenerator`'s inner generator *returns* instead of final-yielding, C's `StepGen_send` converts it (via `PYGEN_RETURN`) into a `RuntimeError` marked `__clausal_engine_protocol__`, which every C loop refuses to route and propagates. The Python twin's `send` lets the bare `StopIteration` escape instead — which `_drive_until_yield` then swallows as exhaustion. Same program, C: loud protocol error; Python: silent zero-solutions. Fix the twin (Step 4).

- [ ] **Step 1: Write the corpus**

Create `tests/test_trampoline_parity.py`:

```python
"""One behavioural corpus, both trampoline implementations.

Drives hand-built StepGenerator chains — never compiled predicates — so the
corpus is independent of the compiled-globals capture
(compiler/predicate.py binds StepGenerator at compile time) and can reach
protocol corners no .clausal fixture reaches.

Every helper takes ``impl`` and builds chains from ``impl.StepGenerator``
with ``impl.DONE`` / ``impl.FINAL``; the two implementations' sentinels are
distinct objects.  ``_TABLING_SUSPEND`` is one shared sentinel from
clausal.logic.tabling.

C is canonical: on divergence, fix _trampoline_py, never the C side.
Acceptance (todo/c-and-python-trampoline-twins-have-no-parity-test.md):
deleting a routing branch from EITHER implementation reds this module.
"""

from __future__ import annotations

import traceback

import pytest

import clausal.logic._trampoline_py as py_impl
from clausal.logic.tabling import _TABLING_SUSPEND

c_impl = pytest.importorskip(
    "clausal.logic.runtime._trampoline",
    reason="C extension not built — the parity corpus needs BOTH implementations",
)


@pytest.fixture(params=["c", "py"], ids=["C", "python"])
def impl(request):
    return c_impl if request.param == "c" else py_impl


# ── chain builders ───────────────────────────────────────────────────────────
# Frame signature: fn(this_generator, proceed, fail, catcher, *args).
# A ROOT frame is built with proceed=fail=catcher=None, so its
# ``yield (proceed, v)`` is a root yield (target None = deliver v) and
# ``yield (fail, DONE)`` is root-level exhaustion.


def root(impl, fn, *args):
    return impl.StepGenerator(fn, None, None, None, *args)


def enum_fn(values, done):
    """Root frame yielding each value as a solution, then exhaustion."""
    def fn(this, proceed, fail, catcher):
        for v in values:
            yield (proceed, v)
        yield (fail, done)
    return fn


def raiser_fn(exc):
    """Leaf frame that raises before its first yield."""
    def fn(this, proceed, fail, catcher):
        raise exc
        yield  # pragma: no cover — makes fn a generator function
    return fn


# ── solutions / trampoline / _drive_until_yield: plain enumeration ───────────


def test_solutions_collects_until_done(impl):
    r = root(impl, enum_fn([1, 2, 3], impl.DONE))
    assert impl.solutions(r) == [1, 2, 3]


def test_solutions_snapshot_runs_while_bindings_live(impl):
    cell = []

    def fn(this, proceed, fail, catcher):
        for v in (1, 2):
            cell.append(v)          # "bind"
            yield (proceed, None)
            cell.pop()              # resumed = backtracked: "undo"
        yield (fail, impl.DONE)

    assert impl.solutions(root(impl, fn), snapshot=lambda: cell[0]) == [1, 2]
    assert cell == []


def test_solutions_final_retires_the_root(impl):
    pulls = []

    def fn(this, proceed, fail, catcher):
        pulls.append("first")
        yield (proceed, 1)
        pulls.append("second")
        yield (proceed, impl.FINAL)
        pulls.append("MUST NOT HAPPEN")  # FINAL means: do not pull again
        yield (fail, impl.DONE)

    got = impl.solutions(root(impl, fn), snapshot=lambda: "snap")
    assert got == ["snap", "snap"]  # solution 1, then FINAL's snapshot
    assert pulls == ["first", "second"]


def test_trampoline_returns_the_final_value_through_a_child(impl):
    def child(this, proceed, fail, catcher, n):
        yield (proceed, n + 1)

    def fn(this, proceed, fail, catcher):
        v = yield (impl.StepGenerator(child, this, this, this, 41), None)
        yield (proceed, v)  # proceed is None at the root → final answer

    assert impl.trampoline(root(impl, fn)) == 42


def test_drive_until_yield_steps_solutions_then_exhausts(impl):
    sg = root(impl, enum_fn(["a", "b"], impl.DONE))
    assert impl._drive_until_yield(sg) is True
    assert impl._drive_until_yield(sg) is True
    assert impl._drive_until_yield(sg) is None


# ── _TABLING_SUSPEND, at the root and mid-chain ──────────────────────────────


def test_root_suspend_is_exhaustion_not_a_solution(impl):
    fn = enum_fn([_TABLING_SUSPEND], impl.DONE)
    assert impl._drive_until_yield(root(impl, fn)) is None      # A04-F008
    assert impl.solutions(root(impl, fn)) == []


def suspend_chain(impl, log):
    """Parent whose child yields (parent, _TABLING_SUSPEND) mid-chain."""
    def child(this, proceed, fail, catcher):
        yield (proceed, _TABLING_SUSPEND)

    def fn(this, proceed, fail, catcher):
        got = yield (impl.StepGenerator(child, this, this, this), None)
        log.append(got)
        yield (None, "intercepted" if got is impl.DONE else "leaked")

    return root(impl, fn)


def test_mid_chain_suspend_is_intercepted_by_drive_until_yield(impl):
    log = []
    assert impl._drive_until_yield(suspend_chain(impl, log)) is True
    assert log == [impl.DONE]  # driver converted the suspend to DONE


def test_mid_chain_suspend_is_NOT_intercepted_by_trampoline(impl):
    # Pins today's per-entry-point flag difference (spec: preserved, not
    # converged).  trampoline() hands the sentinel through untouched.
    log = []
    assert impl.trampoline(suspend_chain(impl, log)) == "leaked"
    assert log == [_TABLING_SUSPEND]


# ── exception routing through the catcher chain ──────────────────────────────


def handler_fn(impl, inner_fn, done, *, decline=False):
    """Frame that spawns inner_fn as a child and handles ValueError."""
    def fn(this, proceed, fail, catcher):
        child = impl.StepGenerator(inner_fn, this, this, this)
        try:
            yield (child, None)
        except ValueError as exc:
            if decline:
                raise
            yield (proceed, f"caught:{exc}")
        yield (fail, done)
    return fn


def test_routable_exception_reaches_the_enclosing_handler(impl):
    fn = handler_fn(impl, raiser_fn(ValueError("boom")), impl.DONE)
    assert impl.solutions(root(impl, fn)) == ["caught:boom"]
    assert impl._drive_until_yield(root(impl, fn)) is True


def test_declining_handler_hands_it_to_the_next_catcher_up(impl):
    inner = handler_fn(impl, raiser_fn(ValueError("boom")), impl.DONE,
                       decline=True)

    def outer(this, proceed, fail, catcher):
        child = impl.StepGenerator(inner, this, this, this)
        try:
            yield (child, None)
        except ValueError as exc:
            yield (proceed, f"outer caught:{exc}")
        yield (fail, impl.DONE)

    assert impl.solutions(root(impl, outer)) == ["outer caught:boom"]


def test_unhandled_exception_propagates_unchanged_with_its_traceback(impl):
    boom = ValueError("boom")

    def parent(this, proceed, fail, catcher):
        # catcher=None: nobody to route to.
        child = impl.StepGenerator(raiser_fn(boom), this, this, None)
        yield (child, None)
        yield (fail, impl.DONE)

    with pytest.raises(ValueError) as ei:
        impl.solutions(root(impl, parent))
    assert ei.value is boom  # identity: routing must be invisible
    frames = [f.name for f in traceback.extract_tb(ei.value.__traceback__)]
    assert "fn" in frames    # raiser_fn's frame survives on the traceback


@pytest.mark.parametrize("exc_type", [GeneratorExit, KeyboardInterrupt,
                                      SystemExit])
def test_control_signals_are_never_routed(impl, exc_type):
    # The enclosing handler catches BaseException on purpose: if the driver
    # wrongly routed the signal, the handler would absorb it and the test
    # would see "stolen" instead of the propagating signal.
    def greedy(this, proceed, fail, catcher):
        child = impl.StepGenerator(raiser_fn(exc_type()), this, this, this)
        try:
            yield (child, None)
        except BaseException:
            yield (proceed, "stolen")
        yield (fail, impl.DONE)

    with pytest.raises(exc_type):
        impl.solutions(root(impl, greedy))


def test_pep479_wrapper_is_exhaustion_for_duy_and_propagates_elsewhere(impl):
    # StopIteration raised inside a generator surfaces as the PEP-479
    # RuntimeError wrapper at the frame boundary.
    def stop_raiser(this, proceed, fail, catcher):
        raise StopIteration()
        yield  # pragma: no cover

    def greedy(this, proceed, fail, catcher):
        child = impl.StepGenerator(stop_raiser, this, this, this)
        try:
            yield (child, None)
        except Exception:
            yield (proceed, "stolen")
        yield (fail, impl.DONE)

    assert impl._drive_until_yield(root(impl, greedy)) is None  # A04-F009
    with pytest.raises(RuntimeError):
        impl.solutions(root(impl, greedy))


def test_generator_that_returns_is_a_protocol_error_not_a_catchable(impl):
    # Inner generator RETURNS instead of final-yielding: an engine anomaly.
    # Canonical (C) behaviour: a RuntimeError marked
    # __clausal_engine_protocol__, refused by routing, propagated by every
    # entry point — never swallowed as exhaustion, never offered to a
    # handler.
    def returns_early(this, proceed, fail, catcher):
        if False:
            yield  # pragma: no cover
        return

    def greedy(this, proceed, fail, catcher):
        child = impl.StepGenerator(returns_early, this, this, this)
        try:
            yield (child, None)
        except Exception:
            yield (proceed, "stolen")
        yield (fail, impl.DONE)

    with pytest.raises(RuntimeError) as ei:
        impl.solutions(root(impl, greedy))
    assert getattr(ei.value, "__clausal_engine_protocol__", False)
    with pytest.raises(RuntimeError):
        impl._drive_until_yield(root(impl, greedy))
```

- [ ] **Step 2: Run it — expect the pre-analysed divergence and nothing else**

```bash
cd /workspace/clausal-bug-fix && /workspace/clausal/venv/bin/python -m pytest tests/test_trampoline_parity.py -q
```

Expected: all `[C]` cases PASS; `test_generator_that_returns_is_a_protocol_error_not_a_catchable[python]` FAILS (bare `StopIteration` / silent exhaustion instead of the marked `RuntimeError`). Any OTHER failure is either a corpus bug or an unknown divergence — for a corpus bug fix the test; for a divergence apply the C-is-canonical rule and record it. Do not proceed with unexplained failures.

- [ ] **Step 3: Fix the twin's `StepGenerator.send`**

In `clausal/logic/_trampoline_py.py`, replace `StepGenerator.send` with:

```python
        def send(self, value: Any) -> tuple:
            try:
                if self._started:
                    return self._gen.send(value)
                self._started = True
                return next(self._gen)
            except StopIteration:
                # C≡Py: StepGen_send converts a returning inner generator
                # (PYGEN_RETURN) into the marked engine-protocol error; a
                # compiled predicate always final-yields (fail, DONE), so a
                # bare return is an engine anomaly, not exhaustion.
                err = RuntimeError(
                    "StepGenerator inner generator returned "
                    "unexpectedly (no final yield)")
                err.__clausal_engine_protocol__ = True
                raise err
```

- [ ] **Step 4: Run the corpus — all green both ways**

Same command as Step 2. Expected: all PASS, both `[C]` and `[python]`.

- [ ] **Step 5: Demonstrate the acceptance mutation (throwaway, not committed)**

Python side: in `_trampoline_py._unwind_to_catcher`, temporarily change `while target is not None:` to `while False:` (routing disabled — every routed exception now surfaces raw); run the corpus and confirm the `[python]` routing cases red; then `git checkout -- clausal/logic/_trampoline_py.py`. C side: in `_trampoline.c::is_routable_exception`, temporarily change the final `return 1;` to `return 0;` (never route), rebuild (`/workspace/clausal/venv/bin/python setup.py build_ext --inplace`), confirm the `[C]` routing cases red, `git checkout -- clausal/logic/runtime/_trampoline.c`, and **rebuild again**. Record "mutation check: both directions red" in the commit message.

- [ ] **Step 6: Suite chunks + failure-set diff** (into `suite_after_task4.txt`; the `send` change is fallback-only so the built-tree suite cannot see it). Expected: empty diff.

- [ ] **Step 7: Commit**

```bash
cd /workspace/clausal-bug-fix
git add tests/test_trampoline_parity.py clausal/logic/_trampoline_py.py
git commit -m "tests: parity corpus over the C and pure-Python trampolines

Hand-built StepGenerator chains, one corpus, both implementations.
Found and fixed the first real divergence: the Python twin let a
returning inner generator surface as bare StopIteration (which
_drive_until_yield swallowed as exhaustion) where C raises the marked
engine-protocol RuntimeError."
```

---

### Task 5: Python twin — one core, three wrappers

**Files:**
- Modify: `clausal/logic/_trampoline_py.py`

**Interfaces:**
- Consumes: nothing new.
- Produces: private `_drive_to_root_yield(root, *, intercept_ts, stopiteration_is_exhaustion) -> tuple[str, Any]` returning `(_YIELDED, value)` or `(_EXHAUSTED, None)`, plus module constants `_YIELDED`, `_EXHAUSTED`. Public surface unchanged. (Task 6's C core mirrors this shape; nothing else imports the private names.)

- [ ] **Step 1: Replace the three loops with core + wrappers**

In `clausal/logic/_trampoline_py.py`, replace the bodies of `trampoline`, `solutions` and `_drive_until_yield` (keeping their docstrings, updated where they described their own inline loops) with:

```python
# ── The drive core ───────────────────────────────────────────────────────────
# "Advance the chain to the next ROOT yield."  The three public entry points
# differ ONLY in their stop condition (what to do with the root-yield value)
# and in two policy flags, passed as literals at each call site:
#
#   intercept_ts                — convert a mid-chain _TABLING_SUSPEND step
#                                 into send(DONE) (solutions, _drive_until_yield)
#   stopiteration_is_exhaustion — treat StopIteration / a PEP-479 wrapper
#                                 from a send as end-of-search
#                                 (_drive_until_yield only; A04-F009)
#
# The entry send (root.send(None)) is never routed to a catcher — all six
# historical loops agreed on that — so only the flags' branches touch it.
# KEEP IN SYNC with drive_to_root_yield in runtime/_trampoline.c (the
# implementation that actually runs); tests/test_trampoline_parity.py
# enforces the agreement.

_YIELDED = "yielded"
_EXHAUSTED = "exhausted"


def _drive_to_root_yield(root, *, intercept_ts, stopiteration_is_exhaustion):
    from clausal.logic.tabling import _TABLING_SUSPEND

    def _is_pep479(exc):
        return (isinstance(exc, RuntimeError)
                and isinstance(exc.__cause__, StopIteration))

    try:
        gen, value = root.send(None)
    except StopIteration:
        if stopiteration_is_exhaustion:
            return (_EXHAUSTED, None)
        raise
    except RuntimeError as exc:
        if stopiteration_is_exhaustion and _is_pep479(exc):
            return (_EXHAUSTED, None)
        raise
    while gen is not None:
        try:
            if intercept_ts and value is _TABLING_SUSPEND:
                gen, value = gen.send(DONE)
            else:
                gen, value = gen.send(value)
        except StopIteration:
            if stopiteration_is_exhaustion:
                return (_EXHAUSTED, None)
            raise
        except Exception as exc:  # noqa: BLE001 — see _is_routable
            if stopiteration_is_exhaustion and _is_pep479(exc):
                # Tested BEFORE routing so a converted exhaustion is never
                # offered to a catch/3 as an error (A04-F009).
                return (_EXHAUSTED, None)
            if not _is_routable(exc):
                raise
            gen, value = _unwind_to_catcher(gen, exc)
    return (_YIELDED, value)
```

and the wrappers:

```python
def trampoline(root: StepGenerator) -> Any:
    _kind, value = _drive_to_root_yield(
        root, intercept_ts=False, stopiteration_is_exhaustion=False)
    return value


def solutions(root: StepGenerator, snapshot: Callable | None = None) -> list:
    from clausal.logic.tabling import _TABLING_SUSPEND

    results: list = []
    while True:
        _kind, value = _drive_to_root_yield(
            root, intercept_ts=True, stopiteration_is_exhaustion=False)
        if value is DONE or value is _TABLING_SUSPEND:  # A04-F008
            return results
        if value is FINAL:
            if snapshot is not None:
                results.append(snapshot())
            return results
        results.append(snapshot() if snapshot is not None else value)


def _drive_until_yield(sg: StepGenerator) -> bool | None:
    from clausal.logic.tabling import _TABLING_SUSPEND

    kind, value = _drive_to_root_yield(
        sg, intercept_ts=True, stopiteration_is_exhaustion=True)
    if kind is _EXHAUSTED:
        return None
    if value is DONE or value is _TABLING_SUSPEND:
        return None
    return True
```

Keep each wrapper's original docstring content (solutions' FINAL comment, duy's A04 notes) attached to the wrapper.

- [ ] **Step 2: Corpus + suite**

```bash
cd /workspace/clausal-bug-fix && /workspace/clausal/venv/bin/python -m pytest tests/test_trampoline_parity.py -q
```

Expected: PASS both ways. Then the 8-chunk sweep + failure-set diff (into `suite_after_task5.txt`). Expected: empty diff.

- [ ] **Step 3: Commit**

```bash
cd /workspace/clausal-bug-fix
git add clausal/logic/_trampoline_py.py
git commit -m "trampoline(py): one drive core, three stop-condition wrappers

trampoline/solutions/_drive_until_yield now share _drive_to_root_yield;
only the stop condition and two literal policy flags differ, matching
the C refactor that follows."
```

---

### Task 6: C core + wrappers

The riskiest task: exception paths and refcounts move. The corpus (both directions), the suite failure-set diff, and the benchmark gate all guard it. Work in small compiles — the file must build after each function is introduced.

**Files:**
- Modify: `clausal/logic/runtime/_trampoline.c`

**Interfaces:**
- Consumes: existing statics `StepGen_send`, `unwind_to_catcher`, `is_routable_exception`, `is_pep479_stopiteration_wrapper`, `get_TABLING_SUSPEND`, `g_DONE`, `g_FINAL`.
- Produces: `static inline drive_result drive_to_root_yield(PyObject *root, int intercept_ts, int stopiteration_is_exhaustion, const char *who, PyObject **out_value)` — internal only; the module's Python-visible API is unchanged.

- [ ] **Step 1: Add the core**

In `_trampoline.c`, after `unwind_to_catcher` and before `trampoline_func`, add:

```c
/* ── The drive core ──────────────────────────────────────────────────────
 *
 * "Advance the chain to the next ROOT yield."  The three entry points
 * (trampoline / solutions / _drive_until_yield) differ ONLY in their stop
 * condition — what they do with the root-yield value — and in two policy
 * flags:
 *
 *   intercept_ts                — convert a mid-chain _TABLING_SUSPEND step
 *                                 into send(DONE)
 *   stopiteration_is_exhaustion — treat StopIteration / a PEP-479 wrapper
 *                                 from a send as end-of-search (A04-F009)
 *
 * Call it with LITERAL flag values only: the function is static inline, so
 * the compiler specialises a copy per call site and the flag branches
 * constant-fold away — one source, the same three loops as before.  ``who``
 * feeds the (cold) protocol-error messages.
 *
 * The entry send (root.send(None)) is never routed to a catcher — all six
 * historical loops agreed on that — only the exhaustion flags touch it.
 *
 * On DRIVE_YIELDED, *out_value holds a NEW reference to the root-yield
 * value.  On DRIVE_ERROR the exception is set.  DRIVE_EXHAUSTED is only
 * possible when stopiteration_is_exhaustion is true.
 *
 * KEEP IN SYNC with _drive_to_root_yield in logic/_trampoline_py.py;
 * tests/test_trampoline_parity.py enforces the agreement.
 */
typedef enum { DRIVE_YIELDED, DRIVE_EXHAUSTED, DRIVE_ERROR } drive_result;

static inline drive_result
drive_to_root_yield(PyObject *root, int intercept_ts,
                    int stopiteration_is_exhaustion,
                    const char *who, PyObject **out_value)
{
    if (intercept_ts)
        /* Resolve the lazy import while no exception is active. */
        (void)get_TABLING_SUSPEND();

    PyObject *step = StepGen_send(StepGen_CAST(root), Py_None);
    if (!step) {
        if (stopiteration_is_exhaustion &&
            (PyErr_ExceptionMatches(PyExc_StopIteration) ||
             (PyErr_ExceptionMatches(PyExc_RuntimeError) &&
              is_pep479_stopiteration_wrapper()))) {
            PyErr_Clear();
            return DRIVE_EXHAUSTED;
        }
        return DRIVE_ERROR;
    }

    while (1) {
        if (!PyTuple_CheckExact(step) || PyTuple_GET_SIZE(step) != 2) {
            PyErr_Format(PyExc_TypeError,
                         "%s: generator must yield 2-tuples", who);
            Py_DECREF(step);
            return DRIVE_ERROR;
        }

        PyObject *gen   = PyTuple_GET_ITEM(step, 0);  /* borrowed */
        PyObject *value = PyTuple_GET_ITEM(step, 1);  /* borrowed */

        if (gen == Py_None) {
            Py_INCREF(value);
            Py_DECREF(step);
            *out_value = value;
            return DRIVE_YIELDED;
        }

        if (!StepGen_Check(gen)) {
            PyErr_Format(PyExc_TypeError,
                         "%s: step target must be StepGenerator or None, "
                         "got %.200s", who, Py_TYPE(gen)->tp_name);
            Py_DECREF(step);
            return DRIVE_ERROR;
        }

        int is_suspend = 0;
        if (intercept_ts) {
            PyObject *ts = get_TABLING_SUSPEND();
            is_suspend = (ts && value == ts);
        }

        /* Keep value alive across the send */
        Py_INCREF(value);
        Py_INCREF(gen);
        Py_DECREF(step);

        step = StepGen_send(StepGen_CAST(gen), is_suspend ? g_DONE : value);
        Py_DECREF(value);

        if (!step) {
            if (stopiteration_is_exhaustion &&
                (PyErr_ExceptionMatches(PyExc_StopIteration) ||
                 (PyErr_ExceptionMatches(PyExc_RuntimeError) &&
                  is_pep479_stopiteration_wrapper()))) {
                /* Tested BEFORE routing so a converted exhaustion is never
                 * offered to a catch/3 as an error (A04-F009). */
                PyErr_Clear();
                Py_DECREF(gen);
                return DRIVE_EXHAUSTED;
            }
            /* Hand it to the enclosing catch/3, if there is one */
            if (is_routable_exception()) {
                PyObject *new_gen, *new_value;
                int r = unwind_to_catcher(gen, &new_gen, &new_value);
                Py_DECREF(gen);
                if (r == 1) {
                    step = PyTuple_Pack(2, new_gen, new_value);
                    Py_DECREF(new_gen);
                    Py_DECREF(new_value);
                    if (!step) return DRIVE_ERROR;
                    continue;
                }
                /* r == 0: uncaught (re-raised), r == -1: different error */
                return DRIVE_ERROR;
            }
            Py_DECREF(gen);
            return DRIVE_ERROR;
        }
        Py_DECREF(gen);
    }
}
```

The forward declarations at the top of the file (`is_pep479_stopiteration_wrapper`, `is_engine_protocol_error`) already exist; `get_TABLING_SUSPEND` and `unwind_to_catcher` are defined above the insertion point — if `StepGen_send` is not, add a forward declaration next to the existing ones.

- [ ] **Step 2: Rewrite the three wrappers**

Replace the bodies of `trampoline_func`, `solutions_func` and `drive_until_yield_func` (keep their argument parsing and type checks verbatim):

```c
static PyObject *
trampoline_func(PyObject *Py_UNUSED(module), PyObject *root)
{
    if (!StepGen_Check(root)) {
        PyErr_SetString(PyExc_TypeError,
                        "trampoline() argument must be a StepGenerator");
        return NULL;
    }
    /* The root protocol ends with yield (None, final_value); no
     * mid-chain suspend interception, no exhaustion conversion —
     * exactly the historical trampoline loop. */
    PyObject *value;
    if (drive_to_root_yield(root, /*intercept_ts=*/0,
                            /*stopiteration_is_exhaustion=*/0,
                            "trampoline", &value) != DRIVE_YIELDED)
        return NULL;   /* DRIVE_EXHAUSTED impossible with the flag off */
    return value;
}
```

```c
static PyObject *
solutions_func(PyObject *Py_UNUSED(module), PyObject *args, PyObject *kwargs)
{
    static char *kwlist[] = {"root", "snapshot", NULL};
    PyObject *root;
    PyObject *snapshot_fn = Py_None;

    if (!PyArg_ParseTupleAndKeywords(args, kwargs, "O|O", kwlist,
                                     &root, &snapshot_fn))
        return NULL;

    if (!StepGen_Check(root)) {
        PyErr_SetString(PyExc_TypeError,
                        "solutions() first argument must be a StepGenerator");
        return NULL;
    }

    PyObject *results = PyList_New(0);
    if (!results) return NULL;

    while (1) {
        PyObject *value;
        if (drive_to_root_yield(root, /*intercept_ts=*/1,
                                /*stopiteration_is_exhaustion=*/0,
                                "solutions", &value) != DRIVE_YIELDED) {
            Py_DECREF(results);
            return NULL;
        }

        if (value == g_DONE) {
            Py_DECREF(value);
            return results;
        }
        {
            /* A04-F008: a root-level suspend is a control sentinel, never
             * a solution. */
            PyObject *ts = get_TABLING_SUSPEND();
            if (ts && value == ts) {
                Py_DECREF(value);
                return results;
            }
        }
        if (value == g_FINAL) {
            /* Producer retiring with its last solution: deliver, do not
             * pull again.  FINAL is a sentinel, not a payload. */
            Py_DECREF(value);
            if (snapshot_fn != Py_None) {
                PyObject *snap = PyObject_CallNoArgs(snapshot_fn);
                if (!snap) { Py_DECREF(results); return NULL; }
                if (PyList_Append(results, snap) < 0) {
                    Py_DECREF(snap);
                    Py_DECREF(results);
                    return NULL;
                }
                Py_DECREF(snap);
            }
            return results;
        }

        PyObject *snap;
        if (snapshot_fn != Py_None) {
            Py_DECREF(value);  /* snapshot_fn doesn't need the raw value */
            snap = PyObject_CallNoArgs(snapshot_fn);
        } else {
            snap = value;      /* already a new reference */
        }
        if (!snap) { Py_DECREF(results); return NULL; }
        if (PyList_Append(results, snap) < 0) {
            Py_DECREF(snap);
            Py_DECREF(results);
            return NULL;
        }
        Py_DECREF(snap);
    }
}
```

```c
static PyObject *
drive_until_yield_func(PyObject *Py_UNUSED(module), PyObject *sg_obj)
{
    if (!StepGen_Check(sg_obj)) {
        PyErr_SetString(PyExc_TypeError,
                        "_drive_until_yield() argument must be a StepGenerator");
        return NULL;
    }

    PyObject *value;
    drive_result r = drive_to_root_yield(sg_obj, /*intercept_ts=*/1,
                                         /*stopiteration_is_exhaustion=*/1,
                                         "_drive_until_yield", &value);
    if (r == DRIVE_EXHAUSTED)
        Py_RETURN_NONE;
    if (r == DRIVE_ERROR)
        return NULL;

    PyObject *ts = get_TABLING_SUSPEND();
    int is_done = (value == g_DONE) || (ts && value == ts);  /* A04-F008 */
    Py_DECREF(value);
    if (is_done)
        Py_RETURN_NONE;   /* search exhausted */
    Py_RETURN_TRUE;       /* solution found — caller should yield */
}
```

Note two deliberate, invisible-to-Python changes to record in the commit: the protocol TypeError text now comes from `who` (identical strings to before), and `trampoline`'s entry-send path no longer differs from its loop path (it never routed either way).

- [ ] **Step 3: Rebuild and run the corpus**

```bash
cd /workspace/clausal-bug-fix
/workspace/clausal/venv/bin/python setup.py build_ext --inplace
/workspace/clausal/venv/bin/python -m pytest tests/test_trampoline_parity.py tests/test_catch_trampolined.py tests/test_source_locations.py -q
```

Expected: PASS. `test_source_locations.py::TestSourceLocationsG6` pins the traceback-preserving throw path that moved with the routing code.

- [ ] **Step 4: Refcount check under a debug-friendly load**

```bash
cd /workspace/clausal-bug-fix
/workspace/clausal/venv/bin/python - <<'EOF'
import clausal.logic.runtime._trampoline as c

def enum_fn(this, proceed, fail, catcher):
    for v in (1, 2, 3):
        yield (proceed, v)
    yield (fail, c.DONE)

def handler(this, proceed, fail, catcher):
    def raiser(this2, p, f, cat):
        raise ValueError("boom")
        yield  # pragma: no cover
    child = c.StepGenerator(raiser, this, this, this)
    try:
        yield (child, None)
    except ValueError:
        yield (proceed, "caught")
    yield (fail, c.DONE)

for _ in range(20000):   # happy path + unwind path, every iteration
    assert c.solutions(c.StepGenerator(enum_fn, None, None, None)) == [1, 2, 3]
    assert c.solutions(c.StepGenerator(handler, None, None, None)) == ["caught"]
print("refcount smoke OK")
EOF
```

Expected: prints `refcount smoke OK`, no crash, stable RSS (watch `ps -o rss` on the pid if in doubt). A segfault or steadily growing RSS means a refcount slip in the core — re-read Step 1's INCREF/DECREF pairs against the originals before anything else.

- [ ] **Step 5: Suite chunks + failure-set diff** (into `suite_after_task6.txt`). Expected: empty diff.

- [ ] **Step 6: Benchmark gate**

Run `benchmarks/microbench.py` 3× and `benchmarks/workloads.py` 5×; compare medians against `$SCRATCH/bench_baseline.txt`. Acceptance (spec): trampoline-dispatch microbench and every macro workload within run-to-run noise. If dispatch regressed beyond noise: check the compiler actually specialised (e.g. `objdump -d build/**/_trampoline*.o | grep -c drive_to_root_yield` — more than one copy or none inlined is fine as long as timings hold; timings are the gate). If it genuinely regressed, convert the core to a macro expanded per wrapper (spec's sanctioned fallback) and re-measure before committing.

- [ ] **Step 7: Commit**

```bash
cd /workspace/clausal-bug-fix
git add clausal/logic/runtime/_trampoline.c
git commit -m "trampoline(c): one drive core, three stop-condition wrappers

trampoline_func/solutions_func/drive_until_yield_func now share the
static inline drive_to_root_yield; flags are literals at each call site
so the branches constant-fold.  Behaviour preserved exactly (parity
corpus + suite failure-set + benchmark medians all unchanged)."
```

Quote the benchmark medians in the commit body.

---

### Task 7: Re-base `_tramp_call` / `_naf_has_solution` on `_drive_until_yield`

**Files:**
- Modify: `clausal/logic/runtime/tramp_call.py`

**Interfaces:**
- Consumes: `_drive_until_yield`, `StepGenerator` from `clausal.logic.trampoline` (C-backed in a built tree).
- Produces: unchanged signatures — `_tramp_call(dispatch_fn, args, trail)` (generator yielding `None` per solution) and `_naf_has_solution(sg) -> bool`; `compiler/predicate.py` keeps importing both by name.

- [ ] **Step 1: Rewrite the module**

Replace the body of `clausal/logic/runtime/tramp_call.py` below its module docstring (keep and lightly update the docstring: the mini-trampoline is now `_drive_until_yield`, i.e. the C loop in a built tree) with:

```python
from __future__ import annotations

from clausal.logic.trampoline import StepGenerator, _drive_until_yield


def _tramp_call(dispatch_fn, args, trail):
    """Call a trampoline-mode dispatch fn from simple-mode context.

    Yields ``None`` once per solution for the enclosing ``for`` loop.  Used
    by simple-mode code paths (lambda bodies, NAF, once) whose inner goal
    resolved to a trampoline-mode dispatch.

    Stepping and exception routing live in ``_drive_until_yield`` — the
    same driver (and, in a built tree, the same C loop) as the main query
    path, so a ``catch/3`` inside ``dispatch_fn`` sees exactly what it
    would see there: routable exceptions thrown back into the ``catcher``
    chain, mid-chain ``_TABLING_SUSPEND`` intercepted, exhaustion treated
    as exhaustion.  Anything unabsorbed propagates to the shallow caller,
    whose own ``try`` covers this loop.
    """
    sg = StepGenerator(dispatch_fn, None, None, None, *args, trail)
    while _drive_until_yield(sg):
        yield None


def _naf_has_solution(sg) -> bool:
    """True if the trampolined goal *sg* yields at least one solution.

    The ``not`` lowering used to emit this loop inline as generated AST —
    a drive-loop copy with no exception routing, so a ``catch/3`` inside a
    negated goal was inert (review finding, 2026-08-25).  Since then the
    loop lives at runtime; it is now ``_drive_until_yield`` itself, which
    stops at the first solution — negation needs existence, not
    enumeration.
    """
    return _drive_until_yield(sg) is True
```

(`_drive_until_yield` returns `True` or `None`, so the bare `while` is exact. The two accepted behaviour changes from the spec — gaining `_TABLING_SUSPEND` interception and exhaustion-on-StopIteration — are inherited from `_drive_until_yield`; they align these bridges with the main query path in `solve._drive_trampoline`.)

- [ ] **Step 2: Targeted tests**

```bash
cd /workspace/clausal-bug-fix && /workspace/clausal/venv/bin/python -m pytest \
  tests/test_catch_trampolined.py tests/test_trampoline_parity.py -q
```

Expected: PASS — `test_catch_trampolined.py` pins the once/findall/`not`/lambda routing these bridges own.

- [ ] **Step 3: Suite chunks + failure-set diff** (into `suite_after_task7.txt`). Expected: empty diff — any new failing name is a real behavioural delta beyond the two accepted ones; investigate, don't rationalise.

- [ ] **Step 4: Benchmark gate**

Workloads 5×, compare medians: `NafFactLoop` (trivial one-step shape) must be within noise of baseline — this is the helper-call-overhead check; `NafChainLoop` at least as fast (stepping moved to C). Other workloads within noise.

- [ ] **Step 5: Commit**

```bash
cd /workspace/clausal-bug-fix
git add clausal/logic/runtime/tramp_call.py
git commit -m "tramp_call: re-base the simple-mode bridges on _drive_until_yield

_tramp_call and _naf_has_solution stop owning drive loops; they drive
through the same (C, in a built tree) loop as the main query path, and
inherit its _TABLING_SUSPEND interception and exhaustion policy."
```

Quote the NAF benchmark medians in the commit body.

---

### Task 8: Bookkeeping — audit record, todos, follow-up

**Files:**
- Modify: `docs/superpowers/specs/2026-08-26-one-drive-loop-design.md` (audit addendum)
- Move: `todo/one-drive-loop-not-six.md` → `todo/done/`, `todo/c-and-python-trampoline-twins-have-no-parity-test.md` → `todo/done/`
- Create: `todo/drive-loop-policy-convergence.md`

**Interfaces:** none — documentation only.

- [ ] **Step 1: Close out the two todos**

At the top of each todo file, change the `**Status: OPEN …**` line to `**Status: DONE 2026-08-26** — see docs/superpowers/specs/2026-08-26-one-drive-loop-design.md and the commits it names.` and add a three-to-five-line closing note stating what landed (per todo: the acceptance criteria and where each is now enforced — the parity module for the twins todo; the core+wrappers and `$drive_until_yield` emission for the six-copies todo, plus the seventh ITE copy found and fixed). Then:

```bash
cd /workspace/clausal-bug-fix
git mv todo/one-drive-loop-not-six.md todo/done/
git mv todo/c-and-python-trampoline-twins-have-no-parity-test.md todo/done/
```

- [ ] **Step 2: File the parked convergence todo**

Create `todo/drive-loop-policy-convergence.md`:

```markdown
# The drive-loop policy flags preserve historical differences — converge or bless them

**Filed:** 2026-08-26, from the one-drive-loop refactor
(docs/superpowers/specs/2026-08-26-one-drive-loop-design.md).
**Status: OPEN — design question, deliberately parked.**

The refactor collapsed the drive loops to one core per language with two
flags whose values PRESERVE how each entry point historically behaved:

| entry point         | intercept_ts | stopiteration_is_exhaustion |
|---------------------|--------------|------------------------------|
| trampoline          | no           | no                           |
| solutions           | yes          | no                           |
| _drive_until_yield  | yes          | yes                          |

`tests/test_trampoline_parity.py::test_mid_chain_suspend_is_NOT_intercepted_by_trampoline`
pins the first difference on purpose.

Open questions, each a deliberate decision rather than a refactor
side-effect:

1. Should `trampoline()` intercept mid-chain `_TABLING_SUSPEND`?  Today a
   suspend reaching a `trampoline()`-driven chain passes through as a
   value.  Is any `trampoline()` call site reachable from tabled code?
2. Should `solutions()` treat StopIteration/PEP-479 from a send as
   exhaustion the way `_drive_until_yield` does, instead of raising?
3. `FINAL` is only interpreted by `solutions`; when producers start
   emitting it (CONTINUATION_TCO_PLAN Phase 4b+), `_drive_until_yield`
   will deliver it as a truthy solution and then re-pull a retired root —
   decide its semantics there BEFORE any producer emits it.

Converging any of these is a behaviour change: decide, test, then flip
the flag in BOTH cores (the parity corpus keeps them agreeing).
```

- [ ] **Step 3: Spec audit addendum**

In the spec's "Audit record" section, append:

```markdown
Addendum (post-implementation): a repo-wide search for AST-emitted
protocol stepping (`attr="send"` over `clausal/logic/compiler/`,
including `optimisations/`) confirmed the general-ITE arm held the only
emitted drive loop; it now emits `$drive_until_yield`.  The parity
corpus found one pre-existing C/Python divergence on landing (a
returning inner generator: C raised the marked engine-protocol
RuntimeError, the Python twin surfaced bare StopIteration which
`_drive_until_yield` swallowed as silent exhaustion) — fixed in the
twin, pinned by
`test_generator_that_returns_is_a_protocol_error_not_a_catchable`.
```

(Adjust the divergence sentence to match what Task 4 actually found, if it differed.)

- [ ] **Step 4: Commit**

```bash
cd /workspace/clausal-bug-fix
git add todo/done/one-drive-loop-not-six.md \
        todo/done/c-and-python-trampoline-twins-have-no-parity-test.md \
        todo/drive-loop-policy-convergence.md \
        docs/superpowers/specs/2026-08-26-one-drive-loop-design.md
git commit -m "todo: close the drive-loop todos, park policy convergence

Both acceptance lists are met: one core per language, no emitted drive
loops, parity corpus reds on either side's deleted routing branch, ITE
routing fixed.  The preserved per-entry-point policy differences are
now a filed design question, not an accident."
```
