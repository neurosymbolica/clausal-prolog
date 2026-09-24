# A conjunction that starts with an atom is indistinguishable from a compound

Parked 2026-09-25 (call-runs-body-terms, step 1 of the ISO clause/2 plan).

In term position a conjunction is a plain tuple, and a compound is a cell --
a tuple whose slot 0 is a str functor.  When the first conjunct is an ATOM
the two are the same tuple:

```
g(G) <- (G is (z, w))        % G = ('z', 'w')   -- the cell z(w)
h(G) <- (G is (z, s(X)))     % G = ('z', ('s', X)) -- the cell z(s(X))
k(G) <- (G is (p(X), s(X)))  % G = (('p', X), ('s', X)) -- a conjunction
```

`call(G)` (clausal/logic/builtins/call_body.py `is_conjunction_tuple`) reads
the first two as the CELL, so `call((z, w))` calls z/1, not z/0 then w/0.
ISO's `','(z, w)` has no such ambiguity.  clause/2 returning such a body
hands back a term that no longer means what the clause says.

Options: spell conjunction as the ISO cell `(",", A, B)` in term position
(call/1 already runs it), or give the term-rewriter a distinct conjunction
node.  Needs a representation ruling.
