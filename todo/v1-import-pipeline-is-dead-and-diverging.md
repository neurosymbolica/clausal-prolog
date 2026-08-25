# The v1 import pipeline is unreachable, and now knowingly wrong

**Filed:** 2026-08-26, from the imported-functor review (`adf95a31`).
**Status: OPEN — small, and cheap to get wrong later.**

## The situation

`import_hook.py` picks a pipeline on `_USE_V2_PIPELINE`, hardcoded `True` since
the v2 split. `_exec_module_v1` is therefore dead code — but it is not inert
dead code:

- its deferred paths (`_define_predicate_deferred`, `_assert_fact_deferred`)
  were given the ownership bookkeeping (`record_clause_source`) when the
  clause-clobber refusal landed, because they assign `_clauses` wholesale;
- but the refusal itself is `compiler_v2` step 3c, which v1 never runs.

So v1 records ownership it never consults, and still silently destroys an
imported predicate's clauses. That is documented in place rather than fixed —
the honest state, but it means the flag is now a trap: flipping it back
reinstates a known silent-wrong-answer bug.

## The choice

**Delete it.** Nothing has selected v1 in months; the flag has no runtime
setter, no test flips it. Deleting removes the trap and one of the two
divergent copies of clause-definition bookkeeping.

**Or port the refusal into it** and keep the flag as a real fallback — only
worth it if someone still wants v1 as an escape hatch, which nothing suggests.

Deletion is the recommendation. It should be its own commit, since it touches
the import path and wants an unambiguous bisect point.

## Acceptance

- `_USE_V2_PIPELINE` and `_exec_module_v1` gone, or v1 carries step 3c.
- Suite failure SET unchanged — diff the set, never the count; this tree has
  ~89 environmental failures that a count comparison hides changes behind.
