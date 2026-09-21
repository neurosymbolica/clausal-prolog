# Implementing the `atom` boundary — a scope, measured 2026-09-21

Spec: `docs/superpowers/specs/2026-09-21-python-boundary-atom-and-string-design.md`.
Operator decisions folded in: the class is **`atom`, lower case** (a Python
class, peer of `str`); `sorted()` mixing `atom` and `str` by text is accepted
for now — standard order of terms belongs on the Clausal side, returned as a
list; the downstream dict-key count comes from the corpus lane.

**The headline, and it is not what the design implies: `++` HAS NO CONVERSION
TODAY.** `to_term` exists, has a registry, and is called by NOTHING on the
escape path — verified by spying on it through a live `++` evaluation:

    to_term called during ++ ?  False

So this is not "register two types". It is "wire a conversion into a hot path
that has none", and that is the whole risk.

## The three pieces

### 1. The `atom` class — small, specified, low risk

New, in `clausal/logic/atoms.py` beside `mint`/`is_atom`/`spelling`. The spec
carries the implementation and the acceptance test. Two traps, both measured
and both easy to reintroduce:

* `return str == other` inside `__eq__` recurses forever — compare through
  `str.__eq__`;
* **`__eq__` alone is not enough, and it fails ONE-SIDED**: `str` defines its
  own `__ne__`, the subclass inherits it without overriding, reflected-operand
  priority does not fire, and `'a' != atom('a')` answers False while
  `atom('a') != 'a'` answers True.

### 2. The OUT boundary (`--`) — one function, wide reach

`seam.export()` is the single point where a term becomes a value Python keeps
(`each`/`once_bind` both go through it). It must wrap an atom as `atom(...)`
and render the chars carrier as a plain `str`.

One function is the good news. The reach is the bad news: every seam read in
existence goes through it, and **the engine tree has 0 `--` sites in its own
`.clausal`/`.seam` files** — in-tree coverage is the ~110 tests in
`test_goal_position_seam.py` / `test_seam_operator.py`, which build their
sources inline. So the in-tree gate for this half is thinner than the file
count suggests.

### 3. The IN boundary (`++`) — the real work

No hook exists. Creating one means:

* **reversing a documented decision.** `to_term` currently reads
  `if isinstance(value, _SCALARS): return value`, with `str` in `_SCALARS`,
  commented "a Python str crossing the seam IS the atom" (spec 2026-09-18 §3
  Q1). The new ruling inverts exactly that line.
* **calling a converter on every escape.** Measured blast radius in the engine
  tree alone: **779 `++` sites across 72 files.** `to_term` recurses through
  lists and dicts, so this is a per-escape cost on a path that currently does
  nothing.
* **a migration whose size cannot be measured statically.** Only **7** in-tree
  `++` sites pass a string literal directly. Every other site that hands over a
  value that happens to be a `str` at runtime changes meaning from atom to
  string, and no census can find those — the operand is an arbitrary
  expression.

That last point deserves naming: **implementing this fix has the same
unmeasurable-blast-radius property as the defect it fixes.** The failure mode
is also the same — a goal that silently stops matching, rather than an error.

## The leak rule needs a test, not a comment

`type(term) is str` IS `is_atom`, and it is False for an `atom`. So `++` must
normalise `atom` to a plain `str` on the way in, and no term may hold one. That
wants an assertion over a walked term in the gate, because a leaked `atom` is
invisible to `is_atom` and would be a fourth failure class of the same family.

## Suggested order

1. the `atom` class + its acceptance test — isolated, no behaviour change;
2. the OUT boundary, with the seam tests extended to assert `atom` comes out
   and text comes out as `str` — still no `++` change, so nothing downstream
   moves yet;
3. the leak-rule test, BEFORE the IN boundary, so it is in place when the thing
   it guards starts existing;
4. the IN boundary, behind a directive or flag if one is cheap, so the 779
   sites can be moved in batches rather than at once;
5. the in-tree `++("literal")` migration — 7 known sites;
6. the downstream migration, sized by the corpus lane's dict-key count plus a
   structural census of `++` operands that are `str`-valued at runtime.

## What I would want before starting step 4

The corpus lane's string-as-dict-key count, and an honest answer to whether the
per-escape conversion cost is acceptable on the `++` path. Both are cheap to
get and both can change the design (a narrower hook — convert only at goal
argument positions, say — might be enough and much cheaper).

## Not in scope

Standard order of terms. Ruled: it belongs on the Clausal side and comes back
as a list, so the boundary does not have to make `atom` and `str` sort apart.
