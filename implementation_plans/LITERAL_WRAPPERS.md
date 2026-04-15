# Literal wrappers — restore `*Literal` nodes for every scalar constant

Revive the `pythonic_ast` literal wrapper classes (`IntLiteral`,
`FloatLiteral`, `ComplexLiteral`, `RationalLiteral`, `StringLiteral`,
`BytesLiteral`, `BoolLiteral`, `NoneLiteral`, `EllipsisLiteral`) in
the templater's output so every scalar constant in Clausal source
becomes a proper `pythonic_ast.Node` with a `position` attribute.
Wrappers live only in the compile-time AST and are unwrapped to
native Python scalars before IR lowering — runtime sees only native
values, unchanged.

**Status:** Phases 1–3 committed (1513de3) as no-op groundwork.
Phase 4 attempted twice on 2026-04-15 and **dropped** — the plan's
"compile-time only" assumption does not hold. See
`todo/constant_position_metadata.md` ("2026-04-15 findings") for the
root cause and the two viable paths forward (Design B subclass-natives,
or stay dropped). Do NOT restart Phases 4–6 from this plan without
reading those findings first.

**Motivation file:** `todo/constant_position_metadata.md` (context,
rejected alternatives).

**Slot in the plan:** follows Slice G's source-location fidelity
work.  Removes four separate "native scalar carve-out" branches from
the compiler that Slice G had to paper over, and unlocks per-constant
`position` for future work (compile-time dimensional analysis,
type inference with source provenance, richer error messages, a
self-hosted compiler's source-level diagnostics).

**Estimated size:** one focused session — ~half a day.  Most
infrastructure already exists; the change is concentrated.

---

## 1. The problem, concretely

`clausal/templating/term_rewriting.py:628` contains the root cause:

```python
def visit_Constant(transformer, constant):
    # Python built-in literals are terms directly — return the constant as-is.
    # The evaluator sees the native Python value (int, float, str, bool, None, …).
    return constant
```

This is a deliberate simplification that bypasses the wrapper
classes defined in `clausal/pythonic_ast/nodes.py:284-322`.
Native Python scalars (`int`, `str`, `bool`, `None`, …) have no
`.position` attribute and no place to hang future metadata (units,
inferred types, dimensional tags).

The consequences, visible today:

- **Slice G position loss on constants.**
  `P <- True` / `P <- False` / `P(X) <- X := 42` lose their source
  positions because the body goal is a native Python value with no
  `position` attribute.  `terms_to_goalop._extend`
  (`clausal/logic/compiler/terms_to_goalop.py:120-124, 182-185`)
  papers over this with four `is True` / `is False` branches that
  synthesize a `Sequence([])` / `Fail()` op with `position=None`.

- **Special-case branches scattered across the compiler.**
  At least five sites do `isinstance(term, (int, float, str, bytes,
  complex))` or `term is True/False/None` because scalars aren't
  Nodes:
  - `clausal/logic/compiler/head_match.py:177-183` — singleton and
    scalar branches for match-pattern emission.
  - `clausal/logic/compiler/terms_to_ast.py:129-133` and `:419-420`
    — two scalar branches emitting `ast.Constant(value=term)`.
  - `clausal/logic/compiler/_vars.py:55` — early return for scalars
    during variable collection.
  - `clausal/logic/compiler/terms_to_goalop.py:120-124, 182-185` —
    the Slice G workaround noted above.

- **Inconsistent AST shape.**
  `pythonic_ast/node_class.py:7-39` defines `_PRIMITIVE_NAMES` and
  the `'plain'` field-kind to cope with scalars mixed into an
  otherwise-uniform Node hierarchy.  Walkers
  (`visit_children`/`transform_children`) carve scalars out via
  `_field_kind`.  This stays necessary for genuine leaf primitives
  (`LoadName.name: str`, arity ints), but today it bleeds into
  user-value positions too.

---

## 2. Design choice — compile-time only (Design A)

Wrappers are introduced at parse/template time and unwrapped back
to native scalars before IR lowering.  Runtime (deref, unify, TRO,
head-match execution, arithmetic) sees only native values —
zero runtime cost, zero C-extension change.

Rejected alternatives (see `todo/constant_position_metadata.md`):

- **Design B (runtime-visible wrappers)** would force every
  `isinstance(x, int)` / `x is True` / `deref` / `unify` site across
  the runtime (including the C extension) to know about wrappers.
  Expensive and unnecessary for the stated goals
  (compile-time analysis, tracebacks, diagnostics).
- **Subclassing native types** (`class IntLiteral(int): ...`) would
  make most code wrapper-oblivious but introduces awkward edge cases
  (interned `True`/`False`, non-subclassable `NoneType`) and a
  subtle leakage where `IntLiteral + IntLiteral = int`.  Rejected as
  a kludge; Design A is cleaner.
- **Partial wrap (bool/None only)** covers the Slice G case but
  forecloses dimensional analysis / type inference use-cases that
  the user has already flagged.

---

## 3. What already exists

The investigation turned up that **the infrastructure is 90%
complete**.  The main missing pieces:

1. `RationalLiteral` class (all others already defined at
   `clausal/pythonic_ast/nodes.py:284-322`).
2. Templater `visit_Constant` reviving wrapper construction.
3. Unwrap-at-boundary discipline at the five consumer sites.

Helpful existing primitives to lean on:

- `clausal/pythonic_ast/conversion_from_python_ast.py:28-40` —
  `convert_constant()` already maps CPython `ast.Constant` →
  `*Literal` for the standard types.  Use as the template for
  `visit_Constant`.
- `clausal/pythonic_ast/nodes.py` — `locate(src, dst)` stamps
  `position` on any Node from a CPython AST node.  Reused below.
- The class set already inherits from `Node` (line 116) and from a
  shared `Literal` base (lines 284-287), so walker infrastructure
  already treats them uniformly.

---

## 4. The unwrap boundary

Two plausible cuts:

**Option 2 — dedicated `strip_literals()` pass** before GoalOp
lowering.  One pass walks the clause body AST, replaces each
`*Literal` node with its `.value`, returns the stripped tree.

**Option 3 — per-site unwrap via a shared `literal_value(x)` helper.**
Each scalar-consumer site unwraps on entry; helper is a no-op for
native values, extracts `.value` for `*Literal`, maps
`NoneLiteral()` / `EllipsisLiteral()` to `None` / `Ellipsis`.

**Chosen: Option 3.**  Reasons:

- The five consumer sites already have `isinstance(term, (int, ...))`
  branches.  Adding `term = literal_value(term)` one line earlier
  is surgical.
- Avoids introducing a new whole-tree pass with its own recursion
  into every nested term shape.
- Keeps wrappers intact for sites that *want* the position
  (e.g. the Slice G traceback threading, future type-inference
  passes).  Option 2 would strip too eagerly.
- The unwrap helper lives in one place
  (`clausal/pythonic_ast/nodes.py` or a new tiny module), so the
  contract is visible and testable.

---

## 5. The plan

### Phase 1 — add the missing class (safe, reversible)

1. Add `RationalLiteral` to `clausal/pythonic_ast/nodes.py` near the
   other literals (~line 298, next to `ComplexLiteral`).  Shape:
   ```python
   @node_class
   class RationalLiteral(Literal):
       value: Fraction = Fraction(0)
   ```
   Import `Fraction` from `fractions` at the top of the module if
   not already present.

2. Add to `__all__` in the same file alongside the other literal
   names.

3. Extend `_CONSTANT_TYPE_MAP` in
   `clausal/pythonic_ast/conversion_from_python_ast.py:28` with
   `Fraction: RationalLiteral` — this makes `simplify(ast_tree)`
   produce `RationalLiteral` nodes when the CPython AST happens to
   carry a `Fraction` (not emitted by the standard Python parser,
   but useful for programmatically-constructed ASTs and for any
   future Clausal source syntax that parses rational literals
   directly).

4. Test: extend `tests/test_simple_ast.py:27-36` with an assertion
   on `RationalLiteral` via a programmatically-constructed
   `ast.Constant(value=Fraction(1,3))` round-tripped through
   `convert_constant`.

**Note:** RationalLiteral is dormant until Clausal source syntax
exposes a rational-literal form.  CLPQ currently promotes to
`Fraction` at runtime.  Adding the class now avoids a gratuitous
second round of plumbing later.

---

### Phase 2 — introduce `literal_value(x)` helper (no-op churn)

1. In `clausal/pythonic_ast/nodes.py`, add:
   ```python
   def literal_value(x):
       """Unwrap a *Literal node to its native Python value.
       Returns x unchanged if not a Literal."""
       if isinstance(x, Literal):
           return x.value
       if isinstance(x, NoneLiteral):
           return None
       if isinstance(x, EllipsisLiteral):
           return ...
       return x
   ```
   (`NoneLiteral`/`EllipsisLiteral` don't inherit from `Literal`
   because they don't need a `.value` field — see lines 317-322.
   Two extra `isinstance` checks cover them.)

2. Add to `__all__` and re-export from `clausal.pythonic_ast`.

3. Test: `tests/test_simple_ast.py` — one test covering all nine
   wrapper types + pass-through for bare native values.

4. Commit.  No behaviour change yet — the helper is defined but
   unused.

---

### Phase 3 — thread `literal_value` through consumer sites (safe, step-wise)

Order intentionally: **update consumers before flipping the
templater**.  Then when Phase 4 flips `visit_Constant`, every
consumer is already ready.  If the order were reversed, Phase 4
would break the test suite and we'd have to bisect which consumer
regressed.

At each site below, add `term = literal_value(term)` (or equivalent)
at the top of the scalar-handling block.  On native scalars the
helper is a no-op, so tests stay green after each individual edit.

Sites in order:

1. **`clausal/logic/compiler/head_match.py:177-183`** — singletons
   + scalar branches.  Apply before the `term is None or term is
   True or term is False` check so `BoolLiteral(True)` → `True`.

2. **`clausal/logic/compiler/terms_to_ast.py:129-133` and
   `:419-420`** — both scalar branches.  Unwrap at entry to each
   branch.

3. **`clausal/logic/compiler/_vars.py:55`** — unwrap before the
   scalar early-return.

4. **`clausal/logic/compiler/terms_to_goalop.py:120-124` and
   `:182-185`** — the Slice G workaround.  Unwrap once at the top
   of `_extend` / `_convert` so the existing `is True` / `is False`
   branches keep working.

5. Run the full test suite after each file edit.  Because the
   templater is unchanged, all tests see native scalars and every
   `literal_value(x)` call is a no-op.  Green at every step.

Commit once after all five sites are updated.

---

### Phase 4 — flip `visit_Constant` to wrap

1. In `clausal/templating/term_rewriting.py`, replace the current
   `visit_Constant` (line 628) with a body mirroring
   `convert_constant` in `pythonic_ast/conversion_from_python_ast.py`
   — but returning a Python AST `Call` that constructs the wrapper
   at runtime, because the templater emits AST that's *compiled*
   (not directly evaluated).  Pattern to follow: look at the
   existing `node_ast("BoolLiteral", ...)` helper used elsewhere in
   term_rewriting.  Dispatch on `constant.value` type:

   ```python
   def visit_Constant(transformer, constant):
       v = constant.value
       if v is None:
           return node_ast("NoneLiteral", constant)
       if v is ...:
           return node_ast("EllipsisLiteral", constant)
       if isinstance(v, bool):
           return node_ast("BoolLiteral", constant, value=constant)
       if isinstance(v, int):
           return node_ast("IntLiteral", constant, value=constant)
       if isinstance(v, float):
           return node_ast("FloatLiteral", constant, value=constant)
       if isinstance(v, complex):
           return node_ast("ComplexLiteral", constant, value=constant)
       if isinstance(v, str):
           return node_ast("StringLiteral", constant, value=constant)
       if isinstance(v, bytes):
           return node_ast("BytesLiteral", constant, value=constant)
       if isinstance(v, Fraction):
           return node_ast("RationalLiteral", constant, value=constant)
       # Unknown constant type — fall back to native passthrough.
       return constant
   ```

   Order matters: `bool` before `int` (bool is an int subclass),
   `Fraction` before `int` is not needed because `Fraction` is
   not an int subclass.  Test this with `isinstance(True, int)
   → True`.

   Ensure `BoolLiteral`, `IntLiteral`, … are exposed in the
   templater's globals so the emitted constructor calls resolve
   at runtime.  Check existing references
   (`clausal/templating/term_rewriting.py` already uses `node_ast`
   for other Node types — find where those names get injected).

2. Run the full test suite.  Expected: green, because Phase 3
   primed every consumer to unwrap.  Any failures point to a
   consumer site we missed.  Fix in place, re-run.

3. Commit.

---

### Phase 5 — simplify Slice G carve-outs

With wrapped literals carrying `position`, the Slice G position-None
fallbacks in `terms_to_goalop.py` for bare True/False bodies
(`_extend:120-124`, `_convert:182-185`) no longer need the "synthesize
a position-less op" code path.  The op built from `BoolLiteral(True)`
gets a real position.

1. Simplify the four `is True` / `is False` branches: keep the
   behavioural short-circuit (`Sequence([])` / `Fail()`) but the
   position is now threaded naturally through the existing
   `getattr(goal, "_position", None)` read a few lines below.

2. If `clausal/logic/compiler/_ast_helpers.py` (Slice G's G4
   strict walker) has a carve-out accepting bare `ast.Constant`
   nodes without positions, tighten it — every emitted node now
   has a position.  (Check
   `_ast_helpers.py` / `goalop_to_python.py` for
   `ast.Constant(value=True)` / `value=False` synthetic emissions;
   Slice G plan §G4 documents these.)

3. Commit.

---

### Phase 6 — tests + documentation

1. Add a dedicated test file
   `tests/test_literal_wrappers.py` covering:
   - Each of the nine `*Literal` classes constructs and carries
     `position`.
   - `visit_Constant` produces the right wrapper for each source
     form: `42`, `3.14`, `1j`, `"hi"`, `b"hi"`, `True`, `False`,
     `None`, `...`.
   - `literal_value()` unwraps each correctly, no-ops on bare
     natives.
   - End-to-end: a `.clausal` predicate with a bare `True` body has
     a non-None position on its `Fail`/`Sequence` IR op
     (regression test for Phase 5's simplification).
   - `RationalLiteral` construction + unwrap (the class is dormant
     until source syntax exposes it; this test documents the
     contract).

2. Update `todo/constant_position_metadata.md` — mark the todo
   resolved, cross-link to this plan doc.

3. Update `implementation_plans/SLICE_G_SOURCE_LOCATIONS.md` — note
   that the bare-constant position-None carve-out is retired.

---

## 6. Risks and open questions

- **The templater's `node_ast` helper.**  Phase 4 assumes
  `node_ast("IntLiteral", ...)` works — i.e., `IntLiteral` is
  resolvable in the runtime scope of the emitted AST.  Verify that
  the templater already injects the pythonic_ast namespace into
  compiled modules; if not, a small import-hook tweak is needed.
  Probe: look at how existing `node_ast("Add", ...)`,
  `node_ast("Lambda", ...)` calls resolve at runtime.

- **`node_class.py`'s `_PRIMITIVE_NAMES`.**  Stays as-is.  Genuine
  primitives remain (identifier `name: str`, arity ints).  But
  audit for any field annotation that currently names e.g.
  `Optional[int]` but means "literal int value" — would want to
  retype to `Optional[IntLiteral]` post-slice.  Probably not
  present; confirm.

- **Clausal source syntax for rationals.**  Out of scope.
  `RationalLiteral` is added as a latent class.  Wiring it to a
  `1/3` source syntax (when it exists) is a separate slice.

- **Tests that inspect native scalars on clause bodies.**  If any
  test does `assert clause.body[0] is True` (identity check on a
  pythonic_ast node after templating), it will fail under Phase 4.
  The `literal_value` sites in Phase 3 prevent this internally;
  user-visible tests might need `isinstance(...,  BoolLiteral)`
  updates.  Grep `tests/` for `is True` / `is False` / `is None`
  against pythonic_ast node accesses before Phase 4.

- **`node_ast("BoolLiteral", ..., value=constant)` with
  `constant.value is True`.**  `ast.Constant(value=True)` is a
  valid CPython AST node; passing the *whole constant* as the
  `value=` keyword means the emitted constructor call carries
  `BoolLiteral(value=ast.Constant(value=True))` at runtime — but
  `node_ast` emits a Python AST `keyword` whose value is an AST
  expression, which then evaluates to `True` at runtime.  Double-
  check this against an existing `node_ast(...)` call that uses
  `value=<constant>` — the existing DictTerm emission pattern at
  `term_rewriting.py:667` is a good reference.

- **Position-repr noise in dumps.**  Node `__repr__` excludes
  `position` via `field(repr=False)` at `nodes.py:116`.  So
  `IntLiteral(value=42)` still prints cleanly.  Verified.

- **Pickling / clause caching.**  Investigation found no compiler
  clause cache.  If one is added later, wrappers are unwrapped
  before IR lowering, so the cache format sees native values — no
  conflict.

---

## 7. Validation checklist

Before declaring the slice done:

- Full test suite green (`python -m pytest tests/
  --ignore=tests/trealla --ignore=tests/test_trealla_backend.py
  --ignore=tests/test_scryer_backend.py -n auto -q`).
- Baseline count recovered: currently 10439 passed / 0 failed
  (see `reference_test_baseline.md`).
- A fresh `python show_generated.py` diff is empty
  (determinism preserved).
- `grep -rn 'isinstance.*int.*float.*str.*bytes' clausal/logic/
  compiler/` returns one less site (one branch collapsed in
  `terms_to_goalop.py`); the others remain as scalar-handling
  branches *after* unwrap but no longer need to exist for
  literal flow.  (Optional cleanup: collapse them after confirming
  no non-literal native-scalar callers remain.)
- `term_position(Term, Pos)` (when added in a future user-facing
  slice) binds `Pos` successfully for constant goals like
  `P <- 42` — this slice makes that possible.

---

## 8. Not in scope

- A user-facing `term_position/2` predicate.  Separate slice.
- Runtime-visible literal wrappers (Design B).  Rejected in §2.
- Clausal source syntax for rational literals.  Separate slice.
- Compile-time dimensional analysis / type inference.  These are
  the *consumers* of the metadata this slice unlocks; each is its
  own research/design effort.
- Touching the C runtime (`_variables.c`, `_tabling_core.c`, etc.).
  Design A is explicit about keeping runtime untouched.
- Renaming `position` → `_position` on `pythonic_ast.Node`.  Kept
  as `position` (internal AST, not Clausal-reachable).  The
  underscore-prefix work done for user-facing terms does not apply
  here.
