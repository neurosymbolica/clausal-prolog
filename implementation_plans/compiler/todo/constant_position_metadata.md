# Re-wrap scalar constants so they can carry source positions

**Status:** attempted 2026-04-15, **dropped** until a redesign lands.
Phases 1–3 of `implementation_plans/LITERAL_WRAPPERS.md` (RationalLiteral
class + `literal_value()` helper + threaded through the five documented
compiler consumer sites) were committed at 1513de3 as no-op groundwork.
Phase 4 (flipping `visit_Constant`) was abandoned — see "2026-04-15
findings" below.

## 2026-04-15 findings — why Phase 4 doesn't work as planned

The plan's central assumption — "wrappers live only in the compile-time
AST, unwrap at five compiler sites, runtime never sees them" — turned
out to be wrong. Two attempts:

**Attempt 1** (per-site `literal_value()` unwrap as planned): ~2000
test failures. The plan's five sites only covered `clausal/logic/
compiler/`. At least 15+ more compile-time sites do
`isinstance(term, (int, float, str, bytes, ...))` on the term tree:
- `clausal/logic/specialization.py:747`
- `clausal/logic/builtins/inspection.py:32, 61`
- `clausal/logic/builtins/_helpers.py:30, 47, 98`
- `clausal/logic/solve.py:57`
- `clausal/logic/constraints.py:54`
- `clausal/logic/clpr.py:782, 798, 814, 830`
- `clausal/logic/clportools.py:365`
- `clausal/logic/compiler/arg_index.py` (`_arg_to_index_key`,
  `_runtime_arg_key`, `_static_call_key`)

**Attempt 2** (Attempt 1 + container-constructor unwrap in
`DictTerm`/`SetTerm`/`KWTerm` + visit_Dict raw-key emission): ~3000
test failures. Patching the 15 sites just exposed the deeper issue —
wrappers leak into term-tree **storage**, not just compile-time
analysis.

### Root cause

A clause `Test("foo") <- (1 + 2 == 3)` is stored at runtime as a
PredicateMeta dataclass instance:
```
Test(DESC=StringLiteral(value='foo'))
```
The wrapper is **inside the dataclass field**, not in an AST `Call`
node. Same happens for:
- `Compound.args` tuples
- Python `list` elements (`[1, 2, 3]` becomes
  `[IntLiteral(1), IntLiteral(2), IntLiteral(3)]`)
- PredicateMeta dataclass fields
- KWTerm field values
- DictTerm keys/values
- SetTerm elements

C-level unification (`_variables.c`) compares `IntLiteral(1)` vs `1`
by object identity / structural equality and they don't match — so
**any clause with a constant in head or body silently fails to
unify**. That accounts for all observed failures.

Defensive `literal_value()` unwrap at static Python sites cannot reach
this. Fixing it with that approach would require recursive unwrap
inside every Compound/list/PredicateMeta/KWTerm/DictTerm/SetTerm
constructor (touching how every term tree is built) plus teaching the
C extension about wrappers. That is not "fix N sites"; it's a
runtime-wide refactor.

### Two viable paths forward

**Path A — Design B (subclass natives).** Make `IntLiteral(int)`,
`FloatLiteral(float)`, `StringLiteral(str)`, `BytesLiteral(bytes)`,
`ComplexLiteral(complex)` actual subclasses of their native types.
Then `isinstance(IntLiteral(1), int)` is `True`, `IntLiteral(1) == 1`
is `True`, `hash(IntLiteral(1)) == hash(1)`, and C-level unification
works transparently with zero changes anywhere else. The plan's
"Alt 3 / Design B" rejected this as a "kludge"; in light of these
findings it is the only practical path. Caveats:
- `bool`/`None`/`Ellipsis` can't be subclassed → keep wrapper-style.
  Phase 3's `literal_value()` already handles these three.
- `IntLiteral(1) + IntLiteral(2) → int(3)` (loses position). Fine —
  the result is a fresh value with no source position anyway.
- The `position` field has to be storable on the subclass. For `int`
  subclasses this works via `__slots__` or an instance dict; needs
  verification per-type.

**Path B — drop the slice (chosen, 2026-04-15).** Keep the bare-
True/False Slice G workaround in `terms_to_goalop._extend` /
`_convert`. Constants don't get positions. The motivating use cases
(future dimensional analysis, type inference with provenance,
self-hosted compiler diagnostics, `term_position/2` on constant
goals) wait until Path A is undertaken.

### What stays committed (1513de3)

- `RationalLiteral` class (latent, no caller yet)
- `literal_value(x)` helper in `clausal/pythonic_ast/nodes.py`
- `literal_value()` calls threaded through five compiler sites
  (`head_match.py`, `terms_to_ast.py` ×2, `_vars.py`,
  `terms_to_goalop.py` ×2)

These are no-ops while `visit_Constant` returns native scalars, but
they're useful defensive layers and the right shape for any future
attempt.



**Context:** `clausal/templating/term_rewriting.py:628` has

```python
def visit_Constant(transformer, constant):
    # Python built-in literals are terms directly — return the constant as-is.
    # The evaluator sees the native Python value (int, float, str, bool, None, …).
    return constant
```

This was a deliberate simplification: bypass the `IntLiteral` /
`BoolLiteral` / `StringLiteral` / `NoneLiteral` / `EllipsisLiteral` /
`FloatLiteral` / `BytesLiteral` wrappers (in `pythonic_ast.nodes`) so
the runtime sees native Python scalars directly.  Faster dispatch, no
per-constant allocation, no unwrap needed in `deref` / arith eval.

**The cost:** native Python scalars carry no metadata.  In particular
they have no `position` attribute, so Slice G cannot stamp source
positions onto body goals that are bare constants:

- `P <- True`                — always-succeed goal, position lost
- `P <- False`               — `Fail` IR op, position lost
- `P(X) <- X := 42`          — rhs is native int, position lost
- `P(X) <- X in [1, 2, 3]`   — list elements lose positions

Slice G's `terms_to_goalop._extend` currently papers over this: for
`True` / `False` it synthesises a `Sequence([])` / `Fail()` with
`position=None`, and the G3 scope wrap on the enclosing op covers the
traceback case.  But any user-facing predicate that introspects source
positions of a term (`term_position/2`, self-hosted compiler, error
messages that quote source location for a bad literal) can't recover
positions for bare constants.

## The fix

Revert `visit_Constant` to wrap:

```python
def visit_Constant(transformer, constant):
    v = constant.value
    if v is None:
        return node_ast("NoneLiteral", constant)
    if v is ...:
        return node_ast("EllipsisLiteral", constant)
    if isinstance(v, bool):
        return node_ast("BoolLiteral", constant, value=constant)
    # int / float / str / bytes → matching *Literal
    ...
```

This is the shape `convert_constant` in
`pythonic_ast/conversion_from_python_ast.py:28` already uses — the
templater just stopped mirroring it at some earlier simplification.

## What this breaks — and what has to move

Every runtime site that treats a Python scalar as a terminal term
must learn to unwrap a `*Literal`:

- `deref` — currently a no-op for `int`/`str`/…; needs to unwrap
  `BoolLiteral(value=v)` → `v` (or return the literal and teach every
  consumer).
- Arith eval — `1 + IntLiteral(2)` has to Just Work.
- Unification — `unify(IntLiteral(3), 3)` should succeed.
- `in_iter` — lists of wrapped literals vs native lists.
- Pattern match in `head_to_match_pattern` — literal patterns vs
  native-value patterns.
- Every `isinstance(x, (int, str, bool, …))` check in the compiler.
- Every `if x is True` / `if x is False` fast path.
- Pickling / serialization of clauses to disk (cache invalidation).

Scope: this is a cross-cutting change that touches the runtime, the
lowerer, the head-match generator, and the cache format.  Not small.

## Alternatives considered

### Alt 1 — keep native scalars, add a side table
Maintain a `WeakKeyDictionary` mapping `id(constant_occurrence) →
SourcePos`.  Can't use `id` of the value because `True` / `42` are
interned.  Have to key on the *occurrence* (enclosing term + index).
Fiddly, breaks when the term is rebuilt/cloned.  Rejected.

### Alt 2 — wrap only when position is asked for
Lazy wrap via a `LocatedConst(value, position)` sentinel the user
introspection APIs return.  Still needs to be constructed at parse
time (from the AST node that had the position) and stored somewhere.
Effectively Alt 1 with a nicer interface.  Rejected for the same
reason.

### Alt 3 — wrap only the cases that matter (bool, None)
`True` / `False` are the only scalars that appear *as body goals*
today (meaning `always-succeed` / `always-fail`).  Wrapping just
those avoids the runtime impact of wrapping int/float/str/bytes
while preserving the Slice G case.  But it leaves users without
positions for `X := 42`.  Partial fix; worth considering if the
full revert is too costly.

## Priority

Not blocking for Slice G's traceback target — the G3 scope wrap
handles the common cases without per-constant metadata.  This is
blocking for:

- `term_position/2` returning meaningful results on constant goals
- Any future self-hosted compiler that does source-level error
  reporting on literal mismatches
- Slice G4's strict walker finding `ast.Constant(value=True)` nodes
  emitted from the body without positions and not knowing whether
  to blame the lowerer (fix plumbing) or the constant (fundamental —
  wrap was never there to copy from).

File under "nice-to-have for self-hosting" unless/until a user-visible
need forces it.
