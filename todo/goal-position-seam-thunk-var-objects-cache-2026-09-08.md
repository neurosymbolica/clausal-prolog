# A `++` over a goal's own variable refuses the query cache

Found in the final fix wave of the goal-position `--` feature
(`feat/goal-position-seam-2026-09-08`), alongside the C1 rename fix that made
such a thunk work at all.

## What happens

`clausal/logic/solve.py::_structural_key`'s `PyThunk` branch raises
`_Uncacheable` for any thunk with a non-empty `var_objects`:

```python
if t.var_objects:
    ...
    raise _Uncacheable()
```

So a goal-position seam whose `++` escape (or f-string) reads a variable the
SAME seam binds —

```clausal
if --(decide(++p, verdict(S, IDS)), N is ++len(IDS)):
```

— is refused the query cache outright and recompiles its query once per
execution. The answers are correct; only the compile is repeated.

## Measured cost (2026-09-08, this branch)

2000 executions of that `if` inside a `for p in profiles:` loop:

| goal | time |
|---|---|
| `--(decide(++p, verdict(S, IDS)), N is ++len(IDS))` (uncached) | 1.615 s |
| the same loop with no var-taking thunk (cached) | 0.160 s |

≈ **10x**, i.e. the whole benefit Task 7 bought for the cacheable shapes.
Pinned as behaviour by
`tests/test_goal_position_seam.py::TestQueryCache::test_a_thunk_over_a_goal_variable_is_correct_but_uncached`,
which asserts the compile count equals the iteration count today.

## Why it was refused rather than keyed

The key and the globals remap have to agree about which `Var`s are rebindable
on a cache hit. `_collect_vars` never reaches a thunk's `var_objects` (it has
no `PyThunk` branch, and `PyThunk` is not a dataclass, so its generic tail
returns nothing), so keying them as `('var', i)` slots would promise a remap
`_compile_as_query` cannot perform — and the count guard, which compares
`len(cached_var_names)` against `len(vars_in_goal)`, could not see the
shortfall either, because the vars were never collected. Keying them by arity
alone goes the other way and CONFLATES goals that lower to different code:
`f(X, X)` and `f(X, Y)` are one arity but two programs.

## The fix, when it is in scope

1. Teach `clausal/logic/solve.py::_collect_vars` to descend into a `PyThunk`'s
   `var_objects` (a `PyThunk` branch; it cannot be reached by the dataclass
   tail). It must NOT descend into `fn` — the closure is a parameter of the
   compiled query, rebound per execution through `_pyt_<id>`, and its
   closed-over Python values are deliberately not part of the key.
2. Restore the `('var', i)` slot keys for `var_objects` in `_structural_key`'s
   thunk branch, using the SAME `var_index` the rest of the walk uses, so a
   variable occurring both in the goal and in the thunk gets one slot and
   `f(X, X)` stays distinguishable from `f(X, Y)`.
3. Confirm `terms_to_ast` lowers a thunk's `var_objects` by the caller's `Var`
   objects (the names `_v<id>` the remap rebinds), not by fresh per-call
   locals — today a `Var` occurring ONLY inside a thunk is lowered to a fresh
   local per call, which is why the latent slot mismatch never bit.
4. Delete the `if t.var_objects: raise _Uncacheable()` refusal. It is one line.
5. Flip the pinning test above to assert a compile count of 1.

## Related

- `clausal/logic/solve.py::_structural_key` — the refusal and its comment
- `clausal/logic/solve.py::_compile_as_query` — the `_pyt_<id>` remap and the
  count guard
- `.superpowers/sdd/2026-09-08-goal-position-seam/task-7-report.md` — the
  cache design this defers
