# A bare arity>=1 predicate name in clause SOURCE is the binding, not the atom

Found 2026-09-24 while implementing the self-denoting-atom ruling
(`todo/done/self-denoting-predicate-atom-spelling-post-flip-mangled-or-plain-2026-09-24.md`,
branch `fix/w4b-self-atom-plain-2026-09-24`). The operator ruling says a
bare predicate reference in DATA position denotes the PLAIN atom of its
name in both eras ("the default in Prolog is global, but be cognizant of
directive hide/1"). The compile-time lowering sites (`term_to_ast_expr`,
`_ground_value`) now honour it. The clause-SOURCE side does not, for
arity >= 1.

## Measurement (clone main cbd7eef2 + the branch above, today's era)

Fixture:

    -module(zq, [z/0, b/1, q/1, r/1])
    z <- True,
    b(1),
    q(z),
    r(b),

`solve((pred, X), m)` then reading X:

| fact | stored value            | query "plain" | query class | query mangled |
|------|-------------------------|---------------|-------------|---------------|
| q(z) | `'z'` (str)             | 1             | 0 (pre-fix) / 1 (post-fix) | 1 |
| r(b) | the `b/1` CLASS object  | 0             | 0           | 0             |

`r(b)` with class query answers 0 because the query side bakes plain `'b'`
while the head holds the class. Also: `q(Y) <- (Y == b)` raises
`type_error(evaluable, <Predicate b/1>)`, so the body's bare `b` is the
class too. Post-flip, the stored value would be the mangled handle
`zq\x1fb` (inferred, not measured -- the flip is unbuilt), still not the
plain atom `b`.

## Question

Should the source compiler lower a bare arity>=1 predicate name in data
position to its plain atom (like z/0 already is), or is the binding
intended there? Under the ruling it should be plain; a `-hide` atom must
keep its mangled spelling. Find where the zero-arity case is lowered to
the str and whether arity>=1 goes through LoadName instead.

## Attempted 2026-09-24 (fix/small-todos-batch-2026-09-24) -- BLOCKED, decision needed

**Where it happens.** Zero-arity `z` is lowered to `'z'` by the rewriter; an
arity>=1 name survives as a `LoadName('b')` node in the stored clause
(`Clause(head=('r', _3), body=[Unify(_3, LoadName(name='b'))])`), and
`term_to_ast_expr`'s LoadName arm emits a runtime `Name` load -- the binding.

**The obvious fix works for data** (6 lines in that arm: resolve the name in
`lowering_globals()`; if `predicate_binding_name(...)` answers, bake
`Constant(mint(name))`): `r(b)` stores `'b'`, a plain `r(b)` query answers 1,
`t(b) <- True` and `l([b, 2])` likewise.

**It breaks every higher-order builtin.** 25 new failures in 8 targeted files
(baseline 425 passed, 0 failed): maplist/include/exclude/partition/foldl/
filter_map/group_by/sort_by/max_by/min_by/tfilter/span/take_while/phrase/
time_goal. They are STATELESS builtins (no db), so they can only run a goal
that is callable; a plain atom is not, and they fail SILENTLY:

```
-module(zq3, [b/1, g/0, g2/0])
b(1),
g  <- maplist(b, [1]),
g2 <- call(b, 1),
```
```
                       today (binding)   with the fix (plain 'b')
g   maplist(b, [1])    1                 0      <- silent
g2  call(b, 1)         1                 1      (call/N is db-receiving:
                                                 _resolve_named_goal)
# the same from Python, today:
call('maplist', m.b, [1])  -> 1
call('maplist', 'b', [1])  -> 0     <- the query side under ruling S already
call('call', 'b', 1)       -> 1        hands maplist a plain atom
solve(('maplist', m.b, [1]), lm) -> 0  <- measured: a CLASS in a query is
                                          lowered to 'b' (_ground_value) and
                                          maplist fails silently TODAY
```

**Question: which order?**

A. Make the higher-order family db-receiving first (resolve a named goal in
   the CALLER's module the way `call/N` does -- `_make_call_goal_factory` /
   `_resolve_named_goal`), then land the 6-line lowering. ~20 builtins in
   `higher_order.py` (currently being edited by another branch). Result:
   `maplist(b, L)` answers from an atom, in both eras, and the ruling holds
   in source and queries alike.

B. Keep the binding in clause source (close this todo as "intended"), and
   accept the asymmetry measured above: `r(b)` stores the class/handle, a
   plain `r(b)` query answers 0.

Recommendation: A -- it also fixes the query side, which under ruling S is
already handing maplist a plain atom and getting a silent 0. Nothing applied;
the lowering diff is above and trivially re-created.
