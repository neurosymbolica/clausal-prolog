# investigate(A02, Opus): parked design decision — cross-type numeric index keys

Parked per user preference (2026-07-05: "park it in a todo, I'll get to
it" — precedent `investigate-A01-parked-design-decisions.md`). Recorded as
**A02-D002** in
`docs/superpowers/audits/2026-07-05-fable-partition/02-compiler-heads/design-questions.md`.

## A02-D002 — should Decimal/Fraction/complex callers key into int/float index buckets?

**Context.** `unify(Decimal(1), 1)` succeeds today (Python `==` semantics —
whether that is *intended* is itself parked as **A01-D001**). But
`_INDEXABLE_TYPES` (`arg_index.py:37`) excludes these types, so under
indexing (≥4 clauses) a `Decimal(1)` caller takes the uncomputable-key path
(A02-F001) and today loses solutions; after the F001 fix it will take the
all-clauses fallback (correct but unindexed). Meanwhile `True`/`1.0` callers
DO hit the `1` bucket — not by design, but because Python hashes all
numerics uniformly.

**Options.**
1. **Fallback-scan only** (what the F001 fix gives for free): correct in
   every A01-D001 outcome; exotic numeric callers just don't benefit from
   indexing. *Recommended now.*
2. **Key any `numbers.Number`** in `_runtime_arg_key` (return the value;
   Python's unified numeric hash makes `{1: bucket}.get(Decimal(1))` hit):
   restores O(1) dispatch, but hard-commits the index layer to cross-type
   numeric equality — wrong if A01-D001 resolves to type-strict unification.
3. **Resolve A01-D001 first**, then align both layers in one change
   (strict: also stop `True`/`1.0` from sharing the `1` bucket — today's
   hash-equality behavior would become a bug).

**Recommendation:** (1) now via the F001 fix; revisit (2) vs (3) when
A01-D001 is decided. Whoever resolves A01-D001 must re-check
`test_bool_and_float_callers_share_int_bucket` in
`tests/audit_2026_07_05/test_02_compiler_heads.py` — it pins today's
(hash-equality) behavior as a consistency guard, not as an endorsement.
