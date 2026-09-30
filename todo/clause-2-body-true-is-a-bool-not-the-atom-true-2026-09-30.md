# clause/2 hands back the body `true` as Python `True`, so `B == true` fails

**Status: OPEN, needs a ruling. Found 2026-09-30 while checking `H :- true`
clauses on the native `.pl` front end.**

    :- dynamic(g/2).
    :- dynamic(k/1).
    g(b, 2) :- true.
    k(c) :- (true, true).
    run :-
        findall(x, (clause(g(_, _), B), B == true), L1), write(L1), nl,
        clause(k(_), B2), write(B2), nl,
        findall(x, (B2 = (X, Y), X == true, Y == true), L2), write(L2), nl.

| | Scryer | Clausal (native `.pl`) |
|---|---|---|
| `L1` | `[x]` | `[]` |
| `B2` | `true,true` | `(True, True)` |
| `L2` | `[x]` | `[]` |

`clause_ops.py` documents this: a stored body `[True]` comes back as `True`,
and `engine_body_pattern` maps an input pattern `true` to `True` so
`clause(H, true)` still matches. But a body that comes back UNBOUND-then-bound
is the bool, which is not `==` the atom `true`, and `write/1` prints `True`.
`call(B)` still works.

Question: should the Body term be the atom `true` (ISO; Scryer) at the
`clause/2` boundary, with `True` kept only inside the engine? Consumers of
the `True` shape: `clause_terms`, `listing`-style readers, and anything that
compares a body with `True`.
