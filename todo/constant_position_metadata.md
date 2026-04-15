# Re-wrap scalar constants so they can carry source positions

**Status:** not started.

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
