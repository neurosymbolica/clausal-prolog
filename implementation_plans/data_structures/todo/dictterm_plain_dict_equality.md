# DictTerm vs plain Python dict — structural `==` asymmetry

## Problem

Clausal's `DictTerm` (the unification-aware dict behind `{"a": 1}` in
source) doesn't compare equal to a plain Python `dict` with matching
content.

```python
# clausal/terms.py:659
def __eq__(self, other):
    return isinstance(other, DictTerm) and self._data == other._data
```

So in Clausal:

```
X is {"a": 1.0},         # X is DictTerm({"a": 1.0})
Y is ++({"a": 1.0}),     # Y is a Python dict
X == Y                   # FAILS — type-asymmetric equality
```

This leaked out during the JAX `++()` escape audit: `tree_flatten`
roundtrip tests do `tree_flatten(REBUILT, TREEDEF, LEAVES), REBUILT
== TREE`. The bidirectional predicate's backward direction produces
a Python dict, forcing TREE to be constructed via `++({...})` rather
than the native `{...}` literal. Otherwise the compare fails.

Two sites in `tests/fixtures/jax_tree_tests.clausal` (lines ~75, ~82)
retain the `++()` escape for exactly this reason — flagged in
`implementation_plans/jax/todo/jax_fixture_escape_audit.md` under the
ranks 4–7 cleanup but left unfixed pending a decision on DictTerm
equality semantics.

## Why it matters

- **Fixture cognitive load.** Authors writing roundtrip tests against
  bidirectional Python-returning predicates need to remember this
  asymmetry. The native-literal form is the obvious first thing to
  try, and when it "silently" fails the unify (no error, just a
  failed test), debugging is indirect.
- **Parallel to `SEGLIST_STRING_ASYMMETRY.md`.** Same shape of
  problem: two types that logically represent the same value fail a
  compare because of Python-level `isinstance` gating. Fix decided
  there may inform this one.
- **Scope creeps into predicate wrappers.** Every wrapper that takes
  a dict-typed argument has to decide whether to `_deep_deref` (which
  already handles DictTerm → dict conversion) or special-case
  DictTerm in its own `isinstance` check. See
  `scikit_learn/todo/sklearn-deref-params-dictterm.md` for a past
  instance where this was missed.

## Design space

### Option A — Symmetric `__eq__`

Have `DictTerm.__eq__` accept a plain `dict` as equal when contents
match:

```python
def __eq__(self, other):
    if isinstance(other, DictTerm):
        return self._data == other._data
    if isinstance(other, dict):
        return self._data == other
    return NotImplemented
```

And optionally patch `dict` on the Python side via
`__eq__` dispatch — not possible directly, but NotImplemented on
DictTerm's side gives Python a chance to try `dict.__eq__(other,
self)`, which fails because `dict.__eq__` checks
`isinstance(other, dict)` and DictTerm isn't a dict subclass.

**Subtlety.** This makes `==` asymmetric in practice:
`DictTerm({}) == {}` would be True, but `{} == DictTerm({})` remains
False unless Python's coercion rules intervene. Clausal code mostly
uses the DictTerm-on-the-left form (via `TREE` being the Clausal
term), so practically OK — but risks subtle bugs.

### Option B — Subclass `dict`

Make `DictTerm` a `dict` subclass (inheriting `__eq__` from dict).
Override only the methods that need unification semantics.

**Risk.** JAX / Equinox / optax libraries might behave differently
for `isinstance(x, dict)` on a DictTerm subclass. `_deep_deref`
already converts to plain dict on the way in, so this should be
transparent, but any library-level dispatch table keyed on `type(x)
is dict` breaks.

### Option C — Only normalize at equality check sites

Leave DictTerm's `__eq__` alone; add a Clausal-level equality
predicate (`dict_equal/2`?) that normalises both operands. Pushes
the problem to authors: they must remember to use the new predicate
for library-result comparisons.

**Verdict.** Worst ergonomics; probably not worth implementing.

### Option D — Normalize on construction

Have the parser emit plain `dict` rather than `DictTerm` when all
values are ground. Only build DictTerm when the literal contains
Vars. Eliminates the type mismatch for the common "literal fully
ground" case.

**Tradeoff.** Two code paths for dict values; subsequent operations
can't rely on always-DictTerm. May break unification in corner cases
where a value becomes a Var after binding, but the construction
already locked in a plain dict.

## Suggested direction

**Lean toward Option A.** It's the smallest change, preserves the
existing construction semantics, and matches the `SEGLIST` direction
(make the types compare equal when they logically represent the same
value). The asymmetry concern is largely theoretical — Clausal code
naturally puts the DictTerm on the left.

List terms have the same potential issue — Clausal list `[1, 2]`
compared to a library-produced Python `list([1, 2])` — but Clausal
lists are implemented as Python lists (not a wrapper type), so the
compare already works. Only DictTerm is affected because it's a
distinct wrapper class.

## Acceptance criteria

- `{"a": 1.0} == ++({"a": 1.0})` succeeds in Clausal.
- Reverse also succeeds (or is documented as out of scope).
- The two roundtrip tests in `jax_tree_tests.clausal` switch back to
  native dict / list literal construction; the `++()` escapes are
  removed.
- No regression in `tests/test_jax_infra.py` or any other fixture
  that relies on DictTerm semantics.

## Cross-references

- `clausal/terms.py:633` — `DictTerm` class
- `clausal/modules/py/_helpers.py:42` — `_deep_deref` already
  handles DictTerm → dict conversion at the predicate boundary
- `implementation_plans/data_structures/todo/SEGLIST_STRING_ASYMMETRY.md`
  — parallel problem for string-as-list-of-chars
- `implementation_plans/scikit_learn/todo/sklearn-deref-params-dictterm.md`
  — DictTerm leaked past an `isinstance(x, dict)` check, silently
  returning empty params
- `implementation_plans/jax/todo/jax_fixture_escape_audit.md` — where
  the two retained `++()` sites are documented
