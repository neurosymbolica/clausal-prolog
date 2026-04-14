# Slice G — Source-location fidelity

Replace `ast.fix_missing_locations` in the compiler with a strict
assertion walker, backed by per-node position threading from
`.clausal` / `.pl` source through `GoalOp` IR and into every emitted
`ast.*` node.

**Status:** not started.

**Preconditions:** Slice D complete (IR is source of truth; every
emitted node passes through `terms_to_goalop` → `lower_python_*`).

**Slot in the plan:** `COMPILER_MIGRATION_PLAN.md` §9 (Slice G).
This file is the design detail behind that entry.

**Estimated size:** 1.5–2 weeks of focused time. The plan doc's
original ~1-week estimate understates the per-node "what position
does this emit with?" decisions G4 forces.

---

## 1. The problem, concretely

`ast.fix_missing_locations(func_def)` is a bulk-zeroing silencer:
any AST node without `lineno` / `col_offset` inherits its parent's
values — ultimately the outer `FunctionDef`, which the compiler
builds with `lineno=0, col_offset=0` (see `_ast_helpers._EXTRA_FUNCDEF`).

In practice **every** emitted node ends up labelled line 0, column 0.
When a compiled predicate raises, the traceback's topmost frame is
inside the generated function but points at a meaningless line.

We want: emitted nodes carry the `lineno`/`col_offset` of the
originating `.clausal` source term, so Python's traceback machinery
surfaces the real source location when things go wrong.

---

## 2. Why this slice is not mechanical

The user's framing: *"each one has to be thought about."*

`fix_missing_locations` is appealing because it makes the uncomfortable
question go away — *what position should this scaffolding node carry?*
Replacing it with an assertion-walker doesn't eliminate that question;
it forces every case to be answered.

Categories of emitted nodes, each needing an explicit decision:

| Kind | Natural position | Notes |
|---|---|---|
| Direct goal lowerings (`Unify`, `Evaluate`, `Call`, `in_`, `Lt`, …) | Originating goal's `.position` | Clean 1:1. |
| Structural children of a goal (mark/undo, `ast.Name`, wrappers) | The goal's position | "Exception raised inside here blames that goal." |
| Reified / general ITE scaffolding | `IfExpr.position` | Whole three-way branch attributed to the `IfExpr`. |
| NAF sub-gen `FunctionDef` wrapper | `Not.position` | The inner goal's own emissions use the inner's position. |
| `once` / `findall` / `catch` sub-gen wrappers | The meta-call term's position | Wrapper blames the call site. |
| Goal-lambda `FunctionDef` | `Lambda.position` | Body goals bring their own positions. |
| Head-match `ast.Match` + case patterns | Clause-head position | Requires `terms.Compound.position` (see §5 Gap #1). |
| Predicate top-level `FunctionDef` | First clause's head position, or a `SYNTHETIC` sentinel | See §5 Gap #2. |
| Arg-index / dispatch scaffolding (bucket selectors, `_get_dispatch` fallback) | Predicate position | Synthesised; no finer origin. |
| Trail `_assign_mark` / `_undo_stmt` from `Alternate` / `Branch` | The parent `Or` / `IfExpr` position | Implicit from the scope stack (§3). |

The assertion walker in G4 is where each undiagnosed "what position?"
surfaces as a loud failure — at which point we either (a) plumb a real
position or (b) mark the node as legitimately synthetic with a
one-line comment.

---

## 3. Design — a position scope on `CompilationContext`

The lifting primitive:

```python
class CompilationContext:
    _position_stack: list[tuple[int, int, int, int]] = field(default_factory=list)

    @contextmanager
    def at_position(self, pos):
        self._position_stack.append(pos)
        try:
            yield
        finally:
            self._position_stack.pop()

    @property
    def current_position(self) -> tuple[int, int, int, int] | None:
        return self._position_stack[-1] if self._position_stack else None
```

Leaf AST builders in `_ast_helpers.py` (`_name`, `_call`, `_if`,
`_assign`, `_assign_mark`, `_undo_stmt`, `_attr`, …) read
`ctx.current_position` and stamp `lineno` / `col_offset` on the node
they build. The call site's sole responsibility is to enter the scope
with the right term's position before emitting.

The scope stack **is** the thoughtful model: every node emitted
inside `with ctx.at_position(goal.position):` is attributed to that
goal. No silent parent-inheritance.

Tradeoffs considered and rejected:

- **Explicit `lineno=`/`col_offset=` kwargs on every helper call.**
  Too verbose; the compiler would drown in boilerplate.
- **`ast.copy_location(new, src_goal_as_ast)`.** The source "AST" node
  is a `pythonic_ast.nodes.Node`, not an `ast.AST`, so `copy_location`
  won't find the fields. Would require an adapter.
- **Thread `position` as a function parameter everywhere.** Would
  rewrite every signature in `control_constructs.py` etc.  The
  context-stack threads through `ctx` which is already plumbed.

---

## 4. Sub-slices

### G0 — Infrastructure (no behaviour change)

- Audit `.clausal` parser: does it set `position` on body terms today?
  (Body terms are `pythonic_ast.nodes` subclasses — positions are
  inherited from `Node`. Confirm parser calls `locate()` on every
  constructed body-goal term.)
- Audit `.pl` importer (`clausal/tools/prolog_import.py` etc.): set
  position on imported terms.
- Add `position` to `clausal.terms.Compound` / `PyThunk` / `KWTerm` /
  `DictTerm` / `SetTerm` (default `None`, `compare=False`, `repr=False`
  — mirror the `nodes.Node` pattern).
- Add `CompilationContext._position_stack` + `at_position()` context
  manager + `current_position` property.
- Update `_ast_helpers` leaf builders to accept an optional `ctx=None`
  kwarg; when supplied, stamp `lineno` / `col_offset` from
  `ctx.current_position`.  No call-site changes yet — the kwarg
  is optional so existing emitters keep compiling.

**Validation:** suite still green; no AST shape change.

### G1 — Regression test (RED)

Write `tests/test_source_locations.py`:

```python
def test_div_by_zero_traceback_points_at_source_line():
    # compile a predicate whose body has "X is Y / 0" at a known line
    # run it; catch the ZeroDivisionError
    # assert the innermost tb frame inside the compiled fn has lineno == that line
```

This **must fail today** — the traceback's innermost frame reports
line 0. The failing test is the regression target G2–G6 fix.

### G2 — Thread positions into `GoalOp`

- Add `position: tuple[int,int,int,int] | None = None` to `GoalOp`
  base dataclass (`ir.py`).
- `terms_to_goalop._convert` / `_extend` read the body term's
  `position` and stamp it on every produced `GoalOp`.
- Edge cases:
  - Flattened `Sequence` from an `And(And(a, b), c)` chain: use the
    outermost `And`'s position.
  - `Fail` / `Sequence(ops=[])` from `False` / `True`: use the
    originating boolean's position (parsers should set it — confirm
    in G0).
  - `MetaCall`: position of the outer `Call` term, not the inner
    (the inner brings its own position via its raw term).

**Validation:** unit test walks a parsed corpus; every op has a
position (or a principled `None` for synthesised-from-nothing cases
— document those cases in `ir.py`).

### G3 — Wire lowering to enter scopes

- Every match arm in `lower_shared`, `lower_python_shallow`,
  `lower_python_trampoline`, and `_lower_meta_call` opens
  `with ctx.at_position(ir.position):` before emitting AST.
- `control_constructs._lower_inner` / `_lower_inner_trampoline` are
  the IR-pipeline entry points from meta-helpers — each outer helper
  (`_compile_once`, `_compile_catch`, …) enters a scope on its
  meta-call's position around the scaffolding it wraps the inner
  lowering with.
- Still using `fix_missing_locations` as the closer — this slice
  populates positions but enforces nothing yet.

**Validation:** G1 test should now pass (traceback line correct).
Suite green.

### G4 — Strict walker, replace `fix_missing_locations`

- New `_ast_helpers.assert_all_nodes_located(funcdef, *, allow_synthetic)`:
  traverse; raise `InvariantError` listing every unlocated node with
  its `ast.dump` snippet and path from the outer `FunctionDef`.
- Replace the 4 `fix_missing_locations` call sites:
  `predicate.py:298`, `predicate.py:511`, `predicate.py:1147`,
  `control_constructs.py:857`.
- **Expected:** loud failures on first landing.  Each is a
  "needs thought" moment:
  - Is there a real source position we should be using? Plumb it.
  - Is it genuinely synthesised scaffolding? Add to `allow_synthetic`
    with a one-line rationale comment.
- Iterate until suite green.

**Risk mitigation:** land G4 behind `CLAUSAL_ASSERT_LOCATIONS=1` env
flag first.  Run CI under the flag; fix everything it catches;
flip the default to on only once clean.

### G5 — Predicate- and clause-level scaffolding

- Head-match patterns: `head_to_match_pattern` / `compile_head_to_match_case`
  scope on clause-head position (depends on G0's `Compound.position`).
- Top-level `FunctionDef`: scope on first clause's head position.
  Synthesised predicates (`_dr_*`, etc.) use a `SYNTHETIC_POSITION`
  sentinel the walker accepts.
- Dispatch scaffolding (bucket selectors, `_get_dispatch` fallback
  in `goal_shallow._dispatch_call_iter` /
  `goal_trampoline._dispatch_call_trampoline`): scope on predicate
  position.  "Error in the dispatcher blames the predicate, not
  line 0."

### G6 — Expand regression coverage

One case per shape, each inducing a known-line runtime failure and
verifying `tb.tb_lineno`:

- Unify body (occurs-check or arity mismatch)
- Evaluate body (divide by zero, type error)
- `Call` to a missing predicate (runtime resolution failure)
- Reified ITE (test raises in then branch)
- General ITE (raise in cond sub-gen)
- `catch` (raise in goal, raise again in recovery)
- `findall` (raise in inner goal)
- List-pattern unify (length mismatch)
- Goal lambda (body raises)
- Tabled NAF (raise in tabled predicate)
- Trampoline sub-predicate call (raise deep in callee)

### G7 — Cleanup

- Delete `fix_missing_locations` imports from `predicate.py`
  and `control_constructs.py`.
- Update `README.md` §8 (pipeline) and §10 (invariants) with
  the position invariant and scope-stack pattern.
- Delete `todo/ast_source_locations.md`.
- Update `COMPILER_MIGRATION_PLAN.md` §9 Slice G row to ✅.

---

## 5. Gaps that must close before G1 is even viable

### Gap #1: `clausal.terms` types don't carry `position`

`Compound`, `PyThunk`, `KWTerm`, `DictTerm`, `SetTerm` have no
`position` field.  Bodies mostly use `pythonic_ast.nodes.*` (which
DO carry position), so body compilation is workable, but:

- Head-match (`head_to_match_pattern`) walks `Compound` — needs
  a position to scope on.
- `_catcher_to_structural` (in `control_constructs.py`) converts
  body `Call` to `Compound` — would drop the position if `Compound`
  can't carry it.
- Nested `Compound` inside `List` / arg positions — same issue.

**Resolution:** add `position` to all terms.py classes listed above
(default `None`, `compare=False`, `repr=False`).  Audit `__eq__` /
`__hash__` where hand-written (`KWTerm` has a non-trivial `__eq__`
for order-insensitive kwargs — don't let position break identity).

### Gap #2: predicate-level position is not single-valued

`compile_predicate(...)` takes `clauses: list[Clause]` and produces
one `FunctionDef`.  Natural position of the top-level `FunctionDef`:

- Options: first clause's head; clauses' enclosing module; predicate
  registration site in Python source.
- Some predicates are compiler-synthesised (`_dr_append__3`, bucket
  functions).  They legitimately have no source position.

**Resolution:** top-level `FunctionDef` uses first clause's head
position.  Synthesised predicates use a `SYNTHETIC_POSITION`
sentinel (probably `(0, 0, 0, 0)` with a module-level constant and
an allow-list in the walker).

### Gap #3: parser coverage unknown

Does the `.clausal` parser call `nodes.locate()` on every constructed
body term?  Does the `.pl` importer set positions?  If not, G2
silently produces `None`-position ops and G1 fails for reasons
unrelated to the compiler.

**Resolution:** add a G0 pre-check — parse a few known-shape test
fixtures, dump `position` on every body term, confirm non-`None`.
Fix parser gaps before G2.

---

## 6. What this slice deliberately does NOT tackle

- `clausal/templating/*` `fix_missing_locations` calls — transform
  layer, not compile layer.  Separate slice if anyone cares.
- `clausal/import_hook.py`, `clausal/codegen.py`, `python_repl.py`,
  `clausal/tools/dump_transformed.py` — each has its own contract
  and is outside `clausal/logic/compiler/`.
- End-column fidelity — we carry the full tuple
  `(start_line, start_col, end_line, end_col)` but Python's traceback
  machinery only surfaces `lineno` / `col_offset`.  `end_lineno` /
  `end_col_offset` are nice-to-have for future tooling; walker
  asserts them too but they're not tested for user-visible effect.
- Performance.  Position-stamping is a few extra ints per node;
  generated-AST size grows by a constant factor.  Negligible.

---

## 7. Validation strategy

- **G1 + G6 regression tests** — hard traceback-line assertions.
  These are the user-visible truth.
- **`assert_all_nodes_located`** under `CLAUSAL_ASSERT_LOCATIONS=1`
  in CI — catches any compiler path emitting un-positioned nodes.
  Land as a permanent assertion once G4 is clean.
- **Position-round-trip** unit test — for a parsed corpus,
  `terms_to_goalop(body)` should produce ops whose positions match
  the input body terms.
- **Suite stays green** throughout — 10482 passed, 90 skipped.

---

## 8. Risks

- **G4 cascade.**  The first strict-walker run surfaces dozens of
  unlocated nodes.  If any land in hot dispatch paths that
  `fix_missing_locations` currently hides, compilation might break
  broadly until fixed.  *Mitigation:* feature flag + staged
  rollout.
- **`terms.Compound` identity.**  Adding `position` mustn't break
  `__eq__` / `__hash__` in user-visible ways (clauses unify on
  structural equality; position is cosmetic).  *Mitigation:*
  `compare=False` on the dataclass field, plus targeted tests.
- **Parser gaps in G0.**  If the `.pl` importer doesn't set
  positions, G2 silently no-ops.  *Mitigation:* G0 pre-check dumps
  positions on test fixtures; fix parser before building on top.
- **Generated-code churn.**  Existing `show_generated.py` / tests
  that snapshot AST output may need regeneration (AST nodes now
  carry non-zero positions).  *Mitigation:* the determinism check
  (`show_generated.py | diff`) still holds — positions are
  deterministic — but golden-file tests may need updating.

---

## 9. First concrete step

**Write G1 — the failing test.**  It locks in the regression target
and, during its setup, exposes any parser-side position gaps before
we touch compiler internals.  If G0's parser audit reveals that body
terms aren't being located at parse time, that's fixed first.
