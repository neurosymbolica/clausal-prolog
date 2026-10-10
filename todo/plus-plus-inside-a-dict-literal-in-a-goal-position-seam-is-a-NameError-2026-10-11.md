# `++a` inside a dict literal in a goal-position seam is a NameError

Found 2026-10-11 on main ed531f2a (reproduced).

```seam
-module(iso_s, [p(X), q(X), r(X)])
-private([w(X), k])
p(X) <- (X == 1)
q(w(X)) <- (X == 1)
r({'k': X}) <- (X == 1)
def flat(a):
    if --p(++a):
        return True
    return False
def nested(a):
    if --q(w(++a)):
        return True
    return False
def indict(a):
    if --r({'k': ++a}):
        return True
    return False
```

`flat(1)`/`flat(2)` and `nested(1)`/`nested(2)` give True/False. `indict(1)`
and `indict(2)` raise `NameError: name '_pyt_<id>' is not defined` from the
compiled `_query` (via `solve.py` `_drive_trampoline`).

## Cause (checked)

The compiled code calls each `++` thunk by its `_pyt_<id>` global, and the
collector that injects those globals (`_walk_body` in
`clausal/logic/compiler/globals_env.py`, and the older `_collect_py_thunks`)
descends into lists, term instances and cells only. A `DictTerm` is neither
(`is_term_instance` and `_cell_shape` are both False for it), so a thunk in
a dict value is lowered by `term_to_ast_expr` but never injected.

## Fix direction

Walk `DictTerm` values (and keys) and `SetTerm` elements in both
collectors. Then check the query cache: `_goal_cache_key` fills
`goal_thunks` with its own walk, and the assert after compilation
(`_thunk_names_not_called`) requires it to agree with `term_to_ast_expr`'s
walk, so the cache key must see a thunk inside a dict too, or a second call
with a different `++a` would be served the first call's value. Test with
two calls of different values, as `flat(1)`/`flat(2)` do.
