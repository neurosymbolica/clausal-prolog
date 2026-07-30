# formalize_lib helpers → spelled-out snake_case

**Requested:** originally alongside the date-API rename; parked 2026-07-05 after the in-repo module
snake_case migration finished. **Why:** same rationale as the whole snake_case push
([[module-predicates-snake-case-rename]] / the closed `date-api-snake-case-rename`) — the local
student models generate spelled-out `snake_case` far more reliably than terse/abbreviated names, and
it's closer to Python/SWI-Prolog. `formalize_lib` is the helper library the clausify rulebases lean
on most, so the payoff is high.

## Scope — SEPARATE REPO
`formalize_lib` lives in the **clausify kit**, not this repo — around
`/workspace/clausify/kit` (per the test-running notes: kit repros run from there so `formalize_lib`
resolves). This todo is a pointer; the actual edits + rulebase sweep happen in that repo, coordinated
like the other external sweep.

## Rename (spell out + snake_case)
| current | proposed | note |
|---|---|---|
| `prof_get` | `profile_get` | spell out "profile" |
| `prof_has` | `profile_has` | |
| `attr` | `attribute` | spell out |

Audit the rest of `formalize_lib`'s surface for other abbreviations while there (same "spell out,
keep only universal abbreviations" philosophy documented in `docs/for_prolog_programmers.md`).

## Rollout (flag-day, matching the datetime + module precedent)
1. Rename the helpers in `formalize_lib` (no deprecated aliases).
2. Sweep the `clausify-domains` rulebases + `kit/scaffolding/*` call-sites in lockstep.
3. Re-run the kit conformance / oracle scores to confirm unchanged.

## Related
- [[module-predicates-snake-case-rename]] — the in-repo counterpart (done); its "external sweep"
  follow-up (clausify-domains rulebases) should be coordinated with this one — same repo, same PR.
