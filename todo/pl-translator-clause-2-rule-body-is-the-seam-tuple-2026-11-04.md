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
