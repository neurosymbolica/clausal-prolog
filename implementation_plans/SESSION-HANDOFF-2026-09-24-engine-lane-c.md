# Engine-lane handoff, 2026-09-24 (c) -- late evening

Supersedes the in-flight section of SESSION-HANDOFF-2026-09-24-engine-lane-b.md (read b
first for rulings, landings, working rules). Canonical main: **0c8f5839** (vocabulary
drop landed; before it 37785199 namespace_db-once, f150bff2 Q0 wiring). Box/GitLab NOT
pushed. Gate baseline 146 (+ known F026 timing flake). Operator wants CODE shown when
discussing code issues.

## Branches in flight (each: merge main -> full gate -> roborev until only Lows -> land)
| branch / worktree | state |
|---|---|
| fix/q0-runtime-registry-2026-09-24 /workspace/_q0reg tip 12fd252e (contains main) | gate+review RUNNING at handoff (bg task b9a76loq5 output in session tasks/); agent fixed 7 failures + High/Medium |
| fix/small-todos-batch-2026-09-24 /workspace/_todobatch | rulings 2A, 4C, 1B, 3A done; merged main clean; needs gate+review; LAND ONLY AFTER operator answers Q1-Q3 below |
| fix/real-module-during-compile-2026-09-24 /workspace/_realmod | gate CLEAN; agent fixing roborev Medium (_install_real_module must replace ONLY the import-hook placeholder, never a live module) |
| fix/heads-without-calling-binding-2026-09-24 /workspace/_heads tip 95b2e850 | merge main CONFLICTED (predicate.py, compiler/predicate.py) -> aborted; agent merging + fixing Medium (placeholder arg_N names vs class _fields after a clause exists; prefer row.signature/HeadFieldNames) |
| fix/move-class-only-data-2026-09-24 /workspace/_classdata tip acddc715 | a merge of main is IN PROGRESS in that worktree (abort failed); compiler_v2.py conflicted; agent told to resolve in place and commit |
| spike/w4b2d-flip-dry-run-2026-09-24 /workspace/_flipdry | NOT for landing; report implementation_plans/w4b2d-flip-dry-run-2026-09-24.md |

Note: heads branch makes predicate.build_term_cell the ONE home of term arity checks; the
todo batch's ruling-4C lines must move there after both land (listed in the todo batch
agent's report: predicate.py:1049, terms_to_ast.py:568/431/1112, head_match.py:687).

## OPEN OPERATOR QUESTIONS (asked with code; unanswered at handoff)
Q1 ruling 4C split: data functors raise on too few args; PREDICATE names build at the
   written arity (phrase(count_leaves(T), L) appends S0/S). Is that what 4C meant?
Q2 listing(fib) now means fib/0 (spec 6.4), since a bare name reaches listing as the
   plain atom; listing(fib/2) unchanged. Keep, or list all arities (SWI)?
Q3 call(pk(3), X) against an imported pk/1 now RAISES the arity refusal (was silent
   failure); maplist accepts cell goals (maplist(add(1), [1,2], L) = [2,3]). OK?
Q4 AmbiguousHandleOwnerError (two live modules sharing a name, raised only when RUNNING
   a handle) is a Python LookupError, not catch/3-able. (a) keep (recommended) or
   (b) ISO term system_error(ambiguous_handle_owner(M)).

## After these land (pre-flip remainder, from the dry run)
small fixes (listing(p) bare, analyze_mi(mod.solve), step 4a, tabling guard, cell
spelling) -> the flip (W4b-2d) -> migrate 484 class-pinning tests -> W4b-3 deletion.
Downstream: 259 corpus scorer sites LOUD at the flip; remedy = cells to solve (NOT
--m.pred, ruled all-solve); list at /workspace/_p4-flip-downstream-impact-2026-09-24.md.
