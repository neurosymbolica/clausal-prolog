# The EDCG body rewriter's if-then-else case is unreachable

**Filed:** 2026-08-26, found while renaming `If/3` → `if_/3`.
**Status: DONE 2026-08-26.**

## What was wrong

`_rewrite_edcg_body` in `clausal/templating/term_rewriting.py` has an
if-then-else case that threads each accumulator through the condition and both
branches. It never ran: the generic
`case Call(func=Name(id=name), args=args, keywords=kwargs)` above it matches
*any* call, so the ITE fell in there first and was rebuilt as an opaque call
whose arguments were never visited. The branches got no accumulator threading
and no DCG state args, and the branch goals reached the compiler as bare terms:

```clausal
pick >> (if_(inc, inc, inc))
# NotImplementedError: terms_to_goalop: goal shape not yet supported
# (LoadName): LoadName(name='inc')
```

Pre-existing, verified against canonical main — not a regression from the
rename.

## What shipped

**1. Ordering.** The ITE case now precedes *both* `Call` cases. That also makes
`if_` a reserved control construct in an EDCG body, which is what it already is
in an ordinary clause body — `TermTransformer.visit_Call` recognises it before
any user predicate of that name.

**2. The case was also wrong once reachable.** It closed each branch to the
accumulator's `out_var` — the *head's* output — and reported `(out, out)`. A
goal after the ITE then had nowhere to push (`out == out + 1`, no solutions).
Branches now meet at a fresh join variable and the case reports
`(join, out_var)`; `_rewrite_edcg_rule`'s existing rule-level closer ties the
last link to `out_var`. Extracted as `_edcg_join_vars` / `_edcg_close_branch`.

**3. The disjunction case had the identical defect** and is fixed the same way
— `(a or b), c` in an EDCG body silently had no solutions. Regression test:
`TestEdcgControlFlow::test_goal_after_disjunction_continues_the_chain`
(confirmed red against the old code by reverting the hunk).

**4. The DCG rewriter was checked** as the todo asked: no bug there. Its ITE
case already precedes its generic `Call` case, and it threads `s_in`/`s_out` by
parameter rather than by returned state, so no join variable is needed.

Tests: `tests/test_edcg.py::TestEdcgIfThenElse` (6 — then/else threading,
condition push reaching the then-branch and *not* the else-branch, a goal after
the ITE, the implicit `dcg` accumulator), the disjunction regression above, and
`tests/test_if_spelling.py::TestIfUnderscore::test_edcg_body` /
`TestLegacyIf::test_edcg_body_warns` restored now that the path works.
Docs: a "Control flow in an EDCG body" section in `docs/syntax.md`.

Related: [[rename-If-3-to-if_-3]].
