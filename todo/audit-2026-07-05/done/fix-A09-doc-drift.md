# fix(A09-F023/F024/F025/F026): builtins doc drift (union dups, transpose example, append "all directions", database_ops page)

**Finding:** docs/superpowers/audits/2026-07-05-fable-partition/09-builtins/findings.md A09-F023, F024, F025, F026

## Items

1. **F023** — `union/3` docstring (lists.py:562-564) and docs/lists.md:258
   say "no duplicates"; actual (SWI-consistent): S1's internal dups survive
   (`union([1,1],[],U)`=[1,1]). Fix the wording ("no element of S2 already in
   S1 is added").
2. **F024** — transpose/2 F055 docstring (lists.py:914-941) claims
   `transpose("ab")` → `[['a'],['b']]`; actual and Liskov-correct:
   `[['a','b']]` ("ab" is a 2-row column of 1-char rows). Also the
   `items=[r]` fallback branch it references is dead for str rows — delete or
   re-justify.
3. **F025** — docs/lists.md:73-75 "append/3 … Works in all directions":
   append(+,−,−) fails (no partial-list mode). Either implement partial-list
   modes (bigger job — SegList tail) or scope the claim to the three
   supported modes (docstring lists them correctly). Same doc-note for open
   modes of maplist(−,+), zip_(−,−,+), same_length(−,−), length(−,−).
4. **F026** — docs/database_ops.md:121-127: "assertz adds facts, not rules"
   (rules are half-supported and poisonous — A09-F005) and "will raise a
   permission error" (actually silent failure — A09-F006). Update once those
   fixes land; if F005 lands as (b) reject-rules, the doc stays but should
   cite the clean error.

## Acceptance

- Docs/docstrings match executed behaviour; probe commands from the findings
  ledger reproduce what the docs now say.
