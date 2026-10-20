# fix(A11-F011): anonymous-var reification numbering collides with user variable _1

`_anonymous_var` (reflection.py:153-155) names anonymous `_` as `_1`, `_2`, …
Leading-underscore names are legal user logic vars, so `Foo(_1, _, X)` reifies
with head args `[Variable('_1'), Variable('_1'), ...]` — asserting a sharing
that does not exist at runtime (docs/reflection.md: sharing is meaningful).

**Fix** (A11-D006): use non-identifier names no user var can collide with
(e.g. `Variable('#anon1')` — the name needn't be a legal identifier), or scan
the clause's user names and skip collisions.

**Test**: test_F011_anon_var_does_not_alias_user_underscore_one (xfail).
