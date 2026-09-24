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
