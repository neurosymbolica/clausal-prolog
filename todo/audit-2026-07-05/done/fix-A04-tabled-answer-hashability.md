**DONE (with residual) — commit 5f0a5088.** add_answer keys answer_set by the
canonical hashable form (make_subgoal_key); _normalize_for_key (Py+C) gained
tuple/dict/set arms; _deref_walk (Py+C) and walk (C) now rebuild plain dict
values + set elements, so stored/cache answers are correctly frozen. Flips
list + term-instance. **Residual:** the tabling LEADER yields the live body
binding, and a `++`-built dict holds a raw Var, so the FIRST (leader) query
derefs to `{'k': <Var>}` (the cache-hit query is correct — see
`test_dict_answer_cache_hit_is_frozen`). Presenting frozen answers from the
leader is a separate change; `test_dict_answer_leader_query` stays xfail.

---

# fix(A04-F005): tabled answers containing list/dict/set/term instances crash add_answer

**Finding:** `docs/superpowers/audits/2026-07-05-fable-partition/04-runtime-tabling/findings.md` A04-F005
**Tests:** `tests/audit_2026_07_05/test_04_runtime_tabling.py::TestF005UnhashableAnswers` (3 xfail — flip to pass)

## Bug

`TableEntry.add_answer` (`tabling.py:115-122`) does `answer in
self.answer_set`; `freeze_args` (`tabling.py:184-189` → `_deref_walk`)
preserves container types. A frozen answer tuple containing a `list`,
`dict`, `set`, or a declared-functor term instance (dataclass-style, no
`__hash__`) raises `TypeError: unhashable type` on the FIRST answer:

    -table(ts/1)
    ts([1, *T]) <- (T is [2, 3])     # query ts(X) → TypeError: 'list'

Lists are the language's primary data structure — tabling currently works
only for scalar / hashable-Compound answers (all in-tree fixtures are
ints/strings, which is why 97 tabling/WFS tests never hit this).

## Fix direction

Canonicalize answers to a hashable key for `answer_set` membership while
storing the original frozen tuple for unification — reuse
`_normalize_for_key` (already converts lists → tuples, instances →
name+fields tuples): `key = make_subgoal_key(answer, trail)`; keep
`answers` as-is. Watch F006: normalization inherits the cross-type
conflation — acceptable (identical dedup semantics), but keep the two in
one place so a later A01-D001 decision fixes both.

Secondary (same code path): `_deref_walk` (`solve.py:49-68` and the C
mirror `_tabling_core.c:239-369`) does not walk dict/set/DictTerm/Seg*
contents, so "frozen" answers share live inner structure whose Vars
unbind on backtracking — corrupting stored answers once the crash above
is fixed. Extend `_deref_walk` (both impls, keep C≡Py parity — see the
P52 differential in the findings doc) to rebuild dict values, set
elements, and walked Seg* forms.

## Acceptance

- `ts(X)` → `[([1,2,3],)]`, twice (second from cache); dict and
  term-instance fixtures likewise.
- A stored answer containing a dict whose value was body-bound derefs
  identically on the second (cache-hit) query.
- `refcount_stable` loop over the list-answer fixture stays flat.
