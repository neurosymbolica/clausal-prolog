# Phase 8 — Shape Extras

Additional shape operations beyond Phase 1: tile, flip, roll, repeat,
pad, the bidirectional `partition` that subsumes `split` + (part of)
`concatenate`, and the bidirectional `stacked` that subsumes Phase 1's
`stack` plus a backward direction via `jnp.unstack`.

**Files to modify:** `clausal/modules/py/jax.py`,
`clausal/modules/py/_helpers.py` (to make `_bidir_2` / `_bidir_3_mid`
see into list/tuple arguments).

**Depends on:** Phase 1.

---

## Predicates

| Name | Arity | Modes | Description |
|---|---|---|---|
| `partition` | `/3, /4` | `(+A, +N_OR_IDX, -LIST)`, `(-A, +N_OR_IDX, +LIST)`, `/4` adds `AXIS` | Bidirectional — forward `jnp.split`, backward `jnp.concatenate` |
| `array_split` | `/3, /4` | `(+A, +N_OR_IDX, -LIST)`, `(+A, +N_OR_IDX, +AXIS, -LIST)` | `jnp.array_split` (uneven OK) — forward-only |
| `hsplit` | `/3` | `(+A, +N, -LIST)` | |
| `vsplit` | `/3` | | |
| `dsplit` | `/3` | | |
| `tile` | `/3` | `(+A, +REPS, -R)` | |
| `repeat` | `/4` | `(+A, +REPS, +AXIS, -R)` | |
| `roll` | `/3, /4` | `(+A, +SHIFTS, -R)`, `(+A, +SHIFTS, +AXIS, -R)` | |
| `stacked` | `/3` | `(+LS, +AXIS, -A)`, `(-LS, +AXIS, +A)` | Bidirectional — subsumes Phase 1's `stack` and the planned `unstack`. Backward uses `jnp.unstack` |
| `flip` | `/2, /3` | `(+A, -R)`, `(+A, +AXIS, -R)`, both bidirectional | Self-inverse; `/2` reverses all axes |
| `pad` | `/3, /4` | `(+A, +PAD_WIDTH, -R)`, `(+A, +PAD_WIDTH, +MODE, -R)` | |

---

## Context

All `_pure()`:

```python
split = _pred("split",
    (3, _pure(lambda a, n: list(_jnp_mod().split(a, n)))),
    (4, _pure(lambda a, n, axis: list(_jnp_mod().split(a, n, axis=int(axis))))),
)
```

Note `list(...)` — `jnp.split` returns a tuple of arrays; we want a
list for Clausal `findall`/pattern-match.

`split` + `concatenate` **are** collapsed into the bidirectional noun
`partition/3,/4`. The earlier plan rejected this on the grounds that
"split criteria aren't inferable from the concatenated result" — but
N_OR_IDX is always provided as an input argument, so the bijection
is well-defined even though N_OR_IDX is only used directly in the
forward direction. `concatenate/3` stays as a separate forward-only
predicate for joining arbitrary-sized pieces (partition's backward
direction only covers the case where LS is a valid split of A).

`stack` + `unstack` are collapsed the same way into the bidirectional
noun `stacked/3`:

```python
stacked = _pred("stacked",
    (3, _bidir_3_mid(
        lambda ls, axis: _jnp_mod().stack(ls, axis=int(axis)),
        lambda a, axis: list(_jnp_mod().unstack(a, axis=int(axis))),
    )),
)
```

This replaces Phase 1's forward-only `stack/3`. `flip` is likewise
made self-inverse by wrapping with `_bidir_2` and `_bidir_3_mid` —
`jnp.flip` is its own inverse, so the same function appears on both
sides.

---

## Example Usage

```clausal
-import_from(py.jax, [array, arange, shape, array_list,
                      partition, tile, flip, roll, repeat, stacked,
                      concatenate])

Test("partition forward") <- (
    arange(0, 6, A),
    partition(A, 3, LS),
    length(LS, 3)
)

Test("partition roundtrip — forward then backward") <- (
    arange(0, 6, A),
    partition(A, 3, LS),
    partition(A2, 3, LS),
    array_list(A, L),
    array_list(A2, L)
)

Test("tile") <- (
    array([1, 2], A),
    tile(A, [3], R),
    array_list(R, [1, 2, 1, 2, 1, 2])
)

Test("flip along axis") <- (
    array([[1, 2], [3, 4]], A),
    flip(A, 0, R),
    array_list(R, [[3, 4], [1, 2]])
)

Test("roll by 1") <- (
    array([1, 2, 3, 4], A),
    roll(A, 1, R),
    array_list(R, [4, 1, 2, 3])
)

Test("stacked backward") <- (
    array([[1, 2], [3, 4], [5, 6]], A),
    stacked(LS, 0, A),
    length(LS, 3)
)
```

---

## Tests

`tests/fixtures/jax_shape_extras_tests.clausal`:
- Every predicate with shape check
- `split` + `concatenate` roundtrip
- Edge cases: split into 1, tile by 1

---

## Docs

Update `docs/jax.md` shape section.

---

## Issues

1. `split` return type: tuple vs list — we convert to list so that
   `length/2` and list-pattern matching
   (`partition(A, 3, [P0, P1, P2])`) work directly. Applies to every
   splitter (`partition`, `array_split`, `hsplit`/`vsplit`/`dsplit`)
   and to `stacked/3`'s backward direction.
2. `pad` mode argument: `"constant"` (default), `"edge"`, `"reflect"`,
   `"symmetric"`, `"wrap"`, etc. Passed as a plain Python string atom.
3. `pad` plan table had `/4, /5` — the actual signatures
   (`(+A, +PAD_WIDTH, -R)` / `(+A, +PAD_WIDTH, +MODE, -R)`) are
   `/3, /4`. Implemented as `/3, /4` to match the rest of the family.
4. `flip` and `roll` accept int, tuple, or (Clausal) list axis
   arguments — `_deep_deref` preserves tuple vs list, and JAX treats
   lists as iterables of axes.
5. `repeat` takes the axis as an int (we call `int(axis)`). Passing
   `None` to flatten-then-repeat would require a `/3` overload; not
   worth the complexity given `reshape` composes cleanly.
6. `stacked/3`'s backward direction requires JAX ≥ 0.4.28 (where
   `jnp.unstack` was added). Forward (`jnp.stack`) works on any
   modern JAX. The wrapper does not pin a minimum JAX version in
   `pyproject.toml`; on older installs, calling `stacked` with a
   bound array fails with `AttributeError`. Documented in `docs/jax.md`.
7. `flip/2` was added on top of the plan's `/3` to match
   `jnp.flip(a)` — reverse every axis — without forcing users to
   construct a tuple of all axes. Both arities are bidirectional
   (self-inverse via `_bidir_2` / `_bidir_3_mid`).
8. Collapsed `stack/3` + `unstack/3` into the bidirectional `stacked/3`
   per the overview's "single noun for bijective pair" rule (same
   precedent as `logarithm`, `fft_transform`, `tree_flatten`). This
   removes Phase 1's `stack/3` export.
9. `_bidir_2` and `_bidir_3_mid` previously used shallow `deref` on
   the X/Y arguments, which left inner `Var`s unresolved when
   `stacked([A, B], 0, C)` was called with A, B bound elsewhere. Fixed
   in `_helpers.py`: both helpers now use `_deep_deref`, and
   "is this side bound?" uses a new `_any_unbound` helper that sees
   into lists/tuples/dicts. Without that, `stacked(LS, 0, A)` in
   backward mode (where `LS = [R0, R1, R2]` is a list of unbound
   Vars) would be mis-classified as "both bound" and fall through to
   check mode.
10. Added `_bidir_4_mid2` helper (`(+X, +M1, +M2, -Y)` forward,
    `(-X, +M1, +M2, +Y)` backward) alongside `_bidir_3_mid`, so that
    `partition/4`'s two middle arguments (N_OR_IDX and AXIS) can both
    be passed through to forward/backward callables. Used only by
    `partition/4` for now.
11. `partition` collapsed the `split` + `concatenate` bijection into a
    single noun predicate per the "noun name" rule. `concatenate/3`
    stays as a separate forward-only predicate for joining
    arbitrary-sized pieces. `split/3,/4` is no longer exported.
    N_OR_IDX is redundant for computing A in `partition`'s backward
    direction but is accepted for signature symmetry; its consistency
    with LS is not explicitly validated.
