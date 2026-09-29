# The ISO reader refuses `2 ** -1` (a negative literal as the right operand of `**`)

Found 2026-09-29 by slice 1 of the native `.pl` front end
(implementation_plans/native-iso-reader-step2-2026-09-29.md), writing the
Scryer-oracle cases.

```
>>> from clausal.tools.iso_l3 import read_iso
>>> read_iso("a(X) :- X is 2 ** -1.\n")
[SyntaxIssue(..., message="Expected '.', got 'integer' (1) at 1:20", ...)]
>>> read_iso("a(X) :- X is 2 ^ -1.\n")      # xfy 200: reads
>>> read_iso("a(X) :- X is 2 ** (-1).\n")   # parenthesised: reads
```

Scryer reads it (`X is 2 ** -1.` gives `X = 0.5`). ISO 6.3.4.1: a `-` name token
directly followed by a numeric literal is a NEGATIVE NUMERIC LITERAL, a term of
priority 0. The Pratt parser (`clausal/tools/prolog_parser.py`) treats it as
prefix `-` (fy 200), which does not fit `**`'s xfx right argument (max 199).
Any xfx 200 operator is affected; xfy 200 (`^`) hides it.

Not fixed in slice 1: the reader/parser is the surface parser (user-owned, see
memory "Phase 3 parser is user-owned"). The slice-1 rulebase and
its oracle cases avoid the spelling. The translator reads with the same parser.
