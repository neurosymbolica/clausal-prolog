# fix(A11-F010): keyword-form heads reify positionally in written order, names dropped

`clausal/reflection.py:267-280` reifies head ctor kwargs as positional args in
WRITTEN order; the runtime canonicalizes by field name. `kp(y=20, x=10),`
reifies `args=[20,10]` while the runtime enumerates `(10, 20)` — a positional
matcher sees swapped values. Body goals, by contrast, preserve kwargs as
`[name, value]` pairs.

**Fix** (A11-D005): reify keyword heads as kwargs pairs like body goals —
`Goal(name, [], [[name, value], ...])`; field order is a load-time artifact
not available statically.

**Test**: test_F010_keyword_head_reify_matches_runtime_order (xfail).
