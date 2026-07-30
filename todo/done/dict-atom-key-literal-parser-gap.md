# Dict literals with bare-atom keys `{filing_status: V}` fail to load (`unhashable type: 'LoadName'`)

**Part of:** [dict-native-profile-api.md](dict-native-profile-api.md) · **Discovered:** 2026-07-14 while
landing item 1 (subscript read). **Pre-existing** — not introduced by the subscript work.

## STATUS: DONE 2026-07-14
**Design decision (Michael):** atom keys and string keys are **distinct** — atoms don't unify with
strings in Clausal, so `{foo: 1}` and `{"foo": 1}` are different dicts (matches Python dict-key identity).
No canonicalization. Atom keys added *alongside* the existing string-key support (the current corpus is
string-keyed); atom keys are the priority for the profile surface.

**Fix:** `visit_Dict` (`clausal/templating/term_rewriting.py`) now routes each key through
`_visit_dict_key`, which lowers a bare-atom key to `$intern_atom("foo")` — a helper injected into the
module dict (`clausal/import_hook.py`) that does `predicate_builtins.setdefault(name, make_predicate(name, []))`,
yielding the **same** interned `PredicateMeta` the bare-atom mint pass produces. This is needed because dict
literals are constructed **eagerly during exec**, before the mint pass runs, so an atom key can't rely on a
later module-global binding. String/int `Constant` keys, computed-expr keys, and logic-variable keys are
transformed exactly as before. Covered by the `atom key *` tests in `tests/test_dict_set_compiler.py` +
`tests/fixtures/dict_set_patterns.clausal` (subscript/get/in/unify/merge/delete/distinct-from-string, plus
mixed atom+string keys and cross-literal atom identity). Full suite green (9295 passed).

Original symptom + root-cause analysis retained below for reference.

---

## Symptom
A dict literal whose **key** is a bare atom (unquoted identifier) does not load:

```clausal
D is {foo: 1}          # TypeError: unhashable type: 'LoadName' at load
V is {a: 1, b: 2}[a]   # same — this is literally the item-1 acceptance sugar
```

String and integer keys are fine (`{"foo": 1}`, `{1: "one"}`) — the entire existing DictTerm test
corpus uses string keys. Bare atoms work everywhere **except dict-key position**: `X is foo` binds
`X` to the interned atom, and an atom passed as a *runtime* subscript index reads correctly
(`subscript_get(P, K, V)` with an atom-keyed DictTerm built in Python passes — see
`tests/test_dict_set_compiler.py::TestDictSubscriptRead::test_reads_atom_key`).

## Root cause (probed)
`visit_Dict` (clausal/templating/term_rewriting.py:748-763) lowers a non-splat literal to
`DictTerm({k: v, ...})` by transforming each key with `transformer.visit(k)`. A bare atom key
becomes a `LoadName` node (visit_Name), which is unhashable, so building the emitted Python dict
throws at exec time. String keys become `Constant` (hashable) and work. The fix must resolve a
bare-atom key to its interned atom **value** (the same object `X is foo` yields) before it lands in
key position — i.e. treat identifiers in dict-key position as atoms, not variable/name references.

## Why it matters
This blocks the **ergonomic** surface the whole capability is designed around — `P[filing_status]`,
`{filing_status: V}`, `get(P, filing_status, V)` all use bare-atom keys. Every downstream dict op
(items 2–5) inherits the gap. The item-1 **read runtime** is representation-agnostic and already
supports atom keys; only literal *construction* sugar is missing. Land this before (or alongside) the
pilot-domain rewrite, since the corpus is atom-keyed.

## Scope / acceptance
- `{foo: 1}` loads and constructs `DictTerm({<atom foo>: 1})`; `{foo: 1}` unifies with a dict built
  from the same atom key.
- `V is {a: 1, b: 2}[a]` binds `V=1` (closes the item-1 acceptance sugar end-to-end).
- Decide + document the key-collision rule: does bare `foo` (atom) collide with `"foo"` (string) as a
  key? Python dicts treat them as distinct; the prover projects on declared keys, so pin whether the
  surface canonicalizes atom↔string keys or keeps them distinct. (Design question — record the
  decision here rather than guessing.)
- Mixed literals `{a: 1, "b": 2}` behave per that rule.
