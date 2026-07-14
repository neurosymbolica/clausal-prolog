# `delete(P, KEY, P2)` — functional key removal

**Part of:** [dict-native-profile-api.md](dict-native-profile-api.md) · **Order:** 5 · **YAGNI-gated**

## Goal
`delete(P, KEY, P2)` binds `P2` to a new `DictTerm` equal to `P` with `KEY` removed.
(`del` is a Python keyword, so the predicate is `delete/3`.) Ground `KEY`.

**Decide the absent-key policy** (pick one, test it, document in the umbrella):
- lenient: `KEY` absent → `P2 == P` (idempotent; matches "functional, always succeeds"); OR
- strict: `KEY` absent → throw (Python `del d[missing]` raises KeyError).
Recommendation: **lenient** (functional-update ops in this API "always succeed"; strictness belongs to the
throwing *read* `P[k]`), but confirm during implementation.

## Status
**No current consumer** — profiles are built-once/read-many; only the planner mutates, and it uses `set`,
not `delete`. Implement when the corpus migration first needs it (it is small + self-contained, hence
listed so it is not forgotten). Do not block the read surface / `set` on this.

## Where
- Co-locate with the other dict builtins. Build a new `DictTerm` minus the key (the type is immutable —
  construct fresh, do not mutate `_data`).

## Acceptance
- `delete({a:1, b:2}, a, P2)` ⇒ `P2 == {b:2}`.
- absent key follows the chosen policy (test it).
- original `P` unchanged (immutability).
