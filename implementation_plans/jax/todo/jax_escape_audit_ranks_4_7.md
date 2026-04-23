# JAX fixtures — ranks 4–7 of the `++()` escape audit

Follow-up to `jax_fixture_escape_audit.md` (ranks 1–3 applied on
2026-04-23; 104+18 sites rewritten, 251 → 131 `++()` occurrences
remaining across 12 JAX fixtures). This doc captures the next four
proposed fixes with concrete implementation sketches.

Priorities here are **lower-ROI cleanup**, not load-bearing work.
Each is small and self-contained; tackle whichever has a real caller
when the time comes.

---

## Rank 4 — `tree_at_get/3` (mirror of `tree_at_set/4`)

**Problem.** Equinox's `tree_at(where, tree, replace=...)` has a
predicate wrapper (`tree_at_set/4`), but reading a leaf by the same
callable path does not. Users fall back to `++(M.bias)`,
`++(BN.inference)`, etc.

**Sites (~7):**
- `jax_equinox_tests.clausal:195,198` — `NB is ++(NEW_MODEL.bias)`
- `jax_equinox_tests.clausal:205,208` — same pattern in
  `tree_at_apply` test
- `jax_equinox_tests.clausal:323,324,331` —
  `++(BN.inference) == False` (BatchNorm mode probe)

**Proposed predicate.**

```
tree_at_get(+WHERE, +TREE, -VALUE)  /3
```

Where `WHERE` is the same callable used by `tree_at_set/4` —
`++(lambda m: m.bias)`. Implementation is trivial: `VALUE is
WHERE(TREE)`, wrapped as a `_pure` dispatch.

**Implementation sketch.** In `clausal/modules/py/jax_equinox.py`,
right after `tree_at_apply`:

```python
tree_at_get = _pred("tree_at_get",
    (3, _pure(lambda where, tree: where(tree))),
)
```

Add to `__all__`. Export alongside `tree_at_set`, `tree_at_apply`.

**Call-site rewrite.**

```clausal
% Before
NB is ++(NEW_MODEL.bias),

% After
tree_at_get(++(lambda m: m.bias), NEW_MODEL, NB),
```

Not a huge ergonomic win (still a lambda), but it keeps attribute
read relational and composes with `tree_at_set` visually:

```clausal
WHERE is ++(lambda m: m.bias),
tree_at_get(WHERE, MODEL, OLD_BIAS),
tree_at_set(WHERE, MODEL, NEW_BIAS, UPDATED)
```

**Tradeoff.** Pure ergonomic win for the `tree_at` idiom; doesn't
help one-off field reads (`++(BN.inference)`), which would want a
separate `field_value/3` predicate — omitted for the same reason
category C was (too generic, cuts across every wrapped class).

---

## Rank 5 — `complex_split/3` (real/imag bidirectional)

**Problem.** JAX complex arrays need `.real` / `.imag` attribute
access to pull out their components; the wrapper has no predicate
for this, so fixtures escape via `++(V.real)` / `++(V.imag)`.

**Sites (~9):**
- `jax_fft_tests.clausal:23,24` — `V_REAL is ++(V.real)`, `V_IMAG is
  ++(V.imag)` after `fft_transform`
- `jax_fft_tests.clausal:40,41,165,166,181,182,193` — same pattern,
  various FFT result shapes
- `jax_linalg_tests.clausal:350` — `E_REAL is ++(E.real)` after
  `eig/2` (eigenvalues are complex)

**Proposed predicate.**

```
complex_split(+C, -REAL, -IMAG)   /3   forward
complex_split(-C, +REAL, +IMAG)   /3   backward (reconstruct)
```

Backward mode uses `jnp.complex(real, imag)` (well, `real + 1j *
imag` since `jnp.complex` doesn't exist — use `jax.lax.complex`).
Check-mode not offered: equality on complex arrays is elementwise
anyway.

**Implementation sketch.** Lives in `py.jax` alongside other
math predicates (complex arrays come out of `linalg.eig`, `fft.fft`,
etc. — cross-cutting, not fft-specific):

```python
def _complex_split_forward(c):
    # c is a jax.Array with complex dtype
    return c.real, c.imag

def _complex_split_backward(real_imag):
    real, imag = real_imag
    return real + 1j * imag

complex_split = _pred("complex_split", (3, _bidir_3_split))
```

Or since we have two output slots and one input (similar to
`partition/4`), write a dedicated dispatch rather than shoehorn
through `_bidir_3_mid`. The shape is close enough to
`_partition_4_dispatch` in `jax_equinox.py` — same two-output-slot
pattern with a filter-spec-like opt.

**Call-site rewrite.**

```clausal
% Before
V_REAL is ++(V.real),
V_IMAG is ++(V.imag),

% After
complex_split(V, V_REAL, V_IMAG),
```

One predicate replaces two escapes per site — ~4.5 sites effectively
worth of readability win.

**Tradeoff.** Adding a third shape of bidirectional helper (after
`_bidir_2` and `_bidir_3_mid`) should be justified — in this case
the shape is `(+C) ↔ (+REAL, +IMAG)`, which is genuinely new. Worth
the helper rather than a hand-rolled dispatch since a second
caller (e.g. `lstsq` returning residuals) might want the same
pattern.

---

## Rank 6 — `grad_fn/2`, `jit_fn/2` (return-the-function forms)

**Problem.** Phase 12's `grad_value/3` and `jit_compile/2` cover
the one-shot and function-returning cases respectively, but
`jit_compile` has no `grad`-returning analogue, and composing
them (e.g. jit the grad of f) requires the escape.

**Sites (~2):**
- `jax_transforms_tests.clausal:163` — `GRAD is ++(jax.grad(F))`
  (to then pass to `jit_compile`)
- The Phase 17b `++(jax.vmap(BN, axis_name=..., in_axes=(0, None),
  out_axes=(0, None)))` site in `jax_equinox_tests.clausal:304–306`
  is *not* in scope here — see "Non-fixable" below.

**Proposed predicates.**

```
grad_fn(+F, -G)        /2   returns jax.grad(F) as a callable
value_and_grad_fn(+F, -G)  /2   returns jax.value_and_grad(F)
```

Naming: `_fn` suffix distinguishes from the one-shot
`grad_value/3`. Matches Phase 17's `filter_jit_compile/2` precedent
(return-the-function). `jit_compile/2` already exists with the
right shape — no `jit_fn` needed.

**Implementation sketch.** In `clausal/modules/py/jax_transforms.py`:

```python
grad_fn = _pred("grad_fn",
    (2, _pure(lambda f: _jx().grad(f))),
)

value_and_grad_fn = _pred("value_and_grad_fn",
    (2, _pure(lambda f: _jx().value_and_grad(f))),
)
```

Add to `__all__` and the re-export list in the docstring.

**Call-site rewrite.**

```clausal
% Before
GRAD is ++(jax.grad(F)),
jit_compile(GRAD, GRAD_JIT)

% After
grad_fn(F, GRAD),
jit_compile(GRAD, GRAD_JIT)
```

**Tradeoff.** Only 1–2 sites today but the shape is natural — any
Clausal user doing custom transform composition will hit this
immediately. Cheap to add.

---

## Rank 7 — `null` atom for Python `None`

**Problem.** Clausal has no atomic `None`; predicates that accept
or return Python `None` force callers through `++(None)`. Nine
sites today, some testing "is not None" (`STATE != ++(None)`) and
one using `None` as a structural value (`partition_spec(["x",
++(None)], P)` — "this dim is not sharded").

**Sites (~9):**
- `jax_sharding_tests.clausal:123` — `partition_spec(["x", ++(None)],
  P)` (structural: None = not-sharded)
- `jax_sharding_tests.clausal:132,147,155` — `S != ++(None)`
- `jax_optax_tests.clausal:96` — `STATE != ++(None)`
- `jax_nn_tests.clausal:17,163` — `FN != ++(None)`, `F != ++(None)`
- `jax_scipy_tests.clausal:194` — `M != ++(None)`
- `jax_transforms_tests.clausal:176` — `JP != ++(None)`

**Proposed export.** Expose `null` as a module-level re-export, same
mechanism as `NaN`/`Inf` aliases added to `py.jax.__getattr__`:

```python
# In clausal/modules/py/jax.py

_CONST_ALIASES = {"NaN": "nan", "Inf": "inf"}


def __getattr__(name):
    # ... existing handling ...
    if name == "null":
        return None
    # ...
```

Or simpler — as a direct module attribute: `null = None`. No lazy
import needed; `None` is a literal.

**Call-site rewrite.**

```clausal
% Before
partition_spec(["x", ++(None)], P),
S != ++(None)

% After (after adding null to import list)
partition_spec(["x", null], P),
S != null
```

**Tradeoff.** Cheaper than the `NaN` work — `null` is genuinely a
literal, doesn't need a lazy dependency. Name choice: `null`
matches JSON / SQL / JS conventions and doesn't clash with
Clausal's `nil` (list terminator). The existing TODO
`implementation_plans/naming/todo/builtin_numeric_constants.md`
already wants IEEE constants promoted to AST-level builtins; adding
`null` to that list makes sense.

**Caveat on `!= ++(None)`.** Several sites use this just as a
smoke-test that a bound value is non-null. In most cases the
`RESULT is (A, B)` pattern-matching would fail on `None` anyway, so
the check is redundant. Could often be deleted rather than
rewritten.

---

## Bonus — `partition_spec/2` bidirectionality (rank-3 remainder)

Two `++(str(P))` sites in `jax_sharding_tests.clausal:118,124`
survive rank 3 because there's no clean relational way to compare
a `PartitionSpec` against anything. Making `partition_spec/2`
bidirectional — `(-AXES, +P)` recovers the axes tuple — would let
these become:

```clausal
% Before
partition_spec(["x"], P),
S is ++(str(P)),
S == "P('x',)"

% After
partition_spec(["x"], P),
partition_spec(AXES, P),
AXES == ["x"]
```

Which is actually a stronger test — it checks the *structure*, not
the string. Implementation lives in
`clausal/modules/py/jax_sharding.py`; the backward direction is
`list(p)` on a `PartitionSpec`.

**Larger change than ranks 4–7**, so called out separately. Not
blocked on anything; just a slightly more involved refactor.

---

## Non-fixable / escape-is-right

These stay in the fixtures regardless:

- **`++(lambda ...)`** for transform callables — semantically
  required, documented as the escape.
- **`++(jax.vmap(M, axis_name=..., in_axes=(0, None), out_axes=(0,
  None)))`** — the one site (Phase 17b BatchNorm + vmap). Adding a
  `vmap_axis/5` predicate to cover just this shape is overkill
  for a single site. Revisit if a second use case surfaces.
- **`++(equinox.is_array)`**, **`++(equinox.nn.BatchNorm)`** —
  passing Python callables/classes as values, intentional.

---

## Priority summary

| Rank | Change | Sites | Effort | Pattern |
|---|---|---|---|---|
| 4 | `tree_at_get/3` | ~4 | tiny (one predicate) | mirror `tree_at_set` |
| 5 | `complex_split/3` | ~9 | small (bidir dispatch) | new helper shape |
| 6 | `grad_fn/2`, `value_and_grad_fn/2` | ~2 | tiny | alongside `jit_compile` |
| 7 | `null` alias | ~9 | trivial (one line) | module attribute |
| Bonus | `partition_spec/2` bidirectional | 2 | medium | requires reverse direction |

Total ~26 sites fixable for maybe half a day of work. Not urgent —
JAX fixtures are already at 131/251 `++()` occurrences after ranks
1–3; the remaining ones are long-tail.

---

## Cross-references

- `implementation_plans/jax/todo/jax_fixture_escape_audit.md` — the
  parent audit (ranks 1–3)
- `implementation_plans/naming/todo/builtin_numeric_constants.md` —
  where `null` alongside `NaN`/`Inf` eventually belong as builtins
- `implementation_plans/jax/phase17_equinox.md` Issue 5 — why
  `tree_at`'s `where` arg stays a lambda (relevant for rank 4's
  ergonomics)
- `clausal/modules/py/jax_equinox.py` — home for rank 4
  (`tree_at_get`)
- `clausal/modules/py/jax_transforms.py` — home for rank 6
  (`grad_fn`, `value_and_grad_fn`)
- `clausal/modules/py/jax.py` — home for rank 5 (`complex_split`)
  and rank 7 (`null` alias)
- `clausal/modules/py/jax_sharding.py` — home for the bonus
  (`partition_spec/2` bidirectional)
