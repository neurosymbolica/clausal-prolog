# docs/dicts_sets.md:154 says an atom key and the same-spelled string key are distinct — false since P3-1

**Filed:** 2026-09-06 at P3-3 Task 10 close-out (implementer concern; doc under docs/ was out of that task's scope).

`docs/dicts_sets.md:154–156`: "Keys may be strings, ints, or atoms — an atom key and the
same-spelled string key are **distinct** (atoms do not unify with strings), exactly as in
head-position dict patterns above."

Since the P3-1 atom pivot an atom IS a plain `str`, so `{'foo': 1}` keyed by the atom `foo`
and by the string `"foo"` are the same key. The sentence (and the "head-position dict
patterns above" it cross-references) teaches the pre-pivot model. The related design note
`implementation_plans/dict-atom-keys-vs-predicates.md` and Phase 4's atom/string audit
(`implementation_plans/p34-dict-set-tagging-handoff.md`) own the semantic question of
whether dict keys should carry a tag; this todo is only the doc being wrong TODAY.

**To close.** Either fix the paragraph now to state the current behaviour (same-spelled
atom and string keys coincide) and re-check the head-position passage it points at, or
fold into Phase 4's audit if the semantics are about to change. docs/ is snippet-tested —
run the doc-snippet suites after editing.
