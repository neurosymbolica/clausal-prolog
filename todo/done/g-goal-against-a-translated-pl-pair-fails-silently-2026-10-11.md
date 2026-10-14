# A `-g` goal fails silently against a pair in a translated `.pl` module

Found 2026-10-11 while fixing `library(clpq)` on the `.pl` translator.

```prolog
% pair.pl, loaded by the default (translator) .pl front end
p(a-b).
q(X-Y) :- X = 1, Y = 2.
```

    clausal -g "p(X-Y)" pair.pl     ->  false.          (expected X = a, Y = b)
    clausal -g "q(P)"   pair.pl     ->  P = 1-2.
    clausal -g "q(A-B)" pair.pl     ->  false.          (expected A = 1, B = 2)

The translator emits `a - b` as seam source, which compiles to the seam's
arithmetic node `Sub(left=a, right=b)`; the CLI reads the goal with the ISO
reader, so its `X-Y` is the term `'-'(X, Y)`.  The two do not unify.  Inside
one translated file both sides are `Sub` nodes, so the file's own clauses
agree; any caller that builds the term in ISO form (the CLI, `solve` from
Python with a tuple, a `.clausal` caller) gets a silent `false`.

The native `.pl` front end (`CLAUSAL_PL_FRONTEND=native`, always on in the
sandbox) answers correctly, and so does a `.clausal` module.  Flipping the
`.pl` default to native is slice 8 of
`implementation_plans/native-iso-reader-step2-2026-09-29.md`; this is
another reason for it.  Short of that: the CLI could read a goal for a
translator module through the translator.

## Resolved (2026-10-14)

The native ISO front end became the `.pl` default with the D43 flip (76c6c27d). Under native, the `-g` goal answers `X = a, Y = b.`. The translator, which is now opt-back only, still gives `false.`.
