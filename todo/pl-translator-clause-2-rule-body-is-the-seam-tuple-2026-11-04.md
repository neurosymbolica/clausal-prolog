# The .pl translator's clause/2 hands a rule's conjunction back as the seam's plain tuple

Found 2026-11-04 while fixing
`todo/done/clause-terms-partial-list-head-is-a-head-pattern-2026-11-04.md`.
Severity: low (the translator is the legacy `.pl` front end; the native front
end, the default, is right).

## What / Repro

```prolog
:- dynamic(q/1).
q(X) :- r(X), w(X).
r(_). w(_).
t :- clause(q(1), B), writeq(B), nl.
```

```
CLAUSAL_PL_FRONTEND=native     clausal t.pl -g t   ->  r(1),w(1)
CLAUSAL_PL_FRONTEND=translator clausal t.pl -g t   ->  (('r', 1), ('w', 1))
Scryer                                             ->  r(1),w(1)
```

The translator lowers `.pl` to seam, so the module's procedures are not on
the ISO surface (`clause_ops.iso_bodies` is False) and `clause_terms` builds
the body the seam way: a conjunction is the plain Python tuple of goals, not
`','/2` cells. `writeq/1` then prints the tuple's repr. A body PATTERN
(`clause(q(L), (r(L2), w(T)))`) still matches, since `engine_body_pattern`
reads the pattern for the same surface; only the term handed back is in the
seam's spelling.

Pinned (as exempt rows on the translator surface) in
`tests/iso/test_clause_partial_list_head_scryer.py`
(`_TRANSLATOR_CONJUNCTION_ROWS`); remove the exemption when this is fixed.

## Investigation 2026-11-04: needs a design choice

Not fixed. Turning the translator's Body into the ISO term is not a local
spelling change: the translator lowers `.pl` text to seam text, and what
clause/2 can rebuild from the lowered goals has lost the ISO body. On
`CLAUSAL_PL_FRONTEND=translator` (Scryer / the native front end in the right
column):

```
r(X), w(X)                    (('r', X), ('w', X))                        r(A),w(A)
\+ r(X), w(X)                 (Not(operand=('r', X)), ('w', X))           \+r(A),w(A)
X = "ab", Y is X + 1          (Unify(..), ('eval_', Add(X, 1), Y))        A=[a,b],B is A+1
X =.. L                       ('unpack', X, L)                            A=..B
X =:= 1, X < 1                ArithEq(X, 1), Lt(X, 1)                     A=:=1,A<1
fail ; false                  or(false, false)                            fail;false
(r(X), w(X)), r(X)            flat: (('r', X), ('w', X), ('r', X))        (r(A),w(A)),r(A)
nl, X = 1                     nl(X is 1)    (a conjunction read as a cell) nl,A=1
X = f(.., [1|T])              [1, *T] inside the Body                     [1|A]
```

Two ways to get the ISO term:

A. The translator records the body AS READ, as the native front end does
   (`Predicate.source_body`): the PrologLoader would have to carry each
   clause's ISO body term, over the clause's own variables, through the
   seam text it generates -- the seam has no syntax for that, so either a
   new seam annotation (a change to the seam surface) or a side channel
   from the translator to the generated Predicate nodes keyed by clause
   position and the translator's variable renaming. Exact, as the native
   front end is.
B. Map the rebuilt seam body back to ISO in `clause_ops` for translator
   modules only (seam goal nodes to their ISO functors, the translator's
   renamed builtins back through `BUILTIN_NAME_MAP`, conjunctions goal by
   goal). Lossy where the lowering already lost the text: grouping
   (`(a,b),c` reads back as `a,(b,c)`), `fail` vs `false`, and a user
   predicate whose name a renamed builtin maps to (`unpack/2` vs `=..`).

Recommendation: neither while the native front end is the default -- keep
the exemption rows (`_TRANSLATOR_CONJUNCTION_ROWS`) and retire the
translator's clause/2 with the translator. If the translator stays, A.
