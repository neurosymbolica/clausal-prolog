# `delete/3` — functional key removal (+ reserved `discard/3`, `pop/4`, `pop/5`)

**Part of:** [dict-native-profile-api.md](dict-native-profile-api.md) · **Order:** 5 · **YAGNI-gated**

## STATUS: `delete/3` DONE 2026-07-14; `discard/3`, `pop/4`, `pop/5` still reserved (YAGNI)
`delete(Dict, Key, NewDict)` added to `clausal/logic/builtins/dict_set.py` (`_delete__3`): builds a fresh
residual `DictTerm` (immutable — never mutates `_data`); **throws** `existence_error(dict_key, KEY)` on
absent, `instantiation_error` on non-ground key, `type_error(dict, D)` on non-dict. Distinct from the older
no-throw `dict_remove/3` (KEY-first). Tests: `delete removes key/keeps original/absent throws`. The reserved
siblings below remain unimplemented until a consumer appears (names/signatures fixed here).

## Goal
`delete(P, KEY, P2)` binds `P2` to a new `DictTerm` equal to `P` with `KEY` removed.
(`del` is a Python keyword, so the predicate is `delete/3`.) Ground `KEY`.

**Absent-key policy: THROW** (decided 2026-07-14) — mirrors Python `del d[missing]` raising `KeyError`.
Consistent with the strict read `P[k]`: strict-named ops throw; softly-named ops don't.

## Reserved sibling names (claim now; implement on demand)
Same YAGNI gate — define when a consumer appears, but the names/signatures are fixed here so the vocabulary
stays coherent:
- **`discard(P, KEY, P2)`** — no-throw removal: `KEY` absent ⇒ `P2 == P` (idempotent). Name borrowed from
  Python `set.discard` (remove-if-present, no error). *(Alternative considered: `delete_nothrow`; `discard`
  preferred for Python familiarity + brevity — confirm.)*
- **`pop(P, KEY, VALUE, P2)`** — remove + retrieve, **throws** if absent (Python `d.pop(k)`): binds `VALUE`
  to the removed value and `P2` to the residual dict.
- **`pop(P, KEY, VALUE, P2, DEFAULT)`** — remove + retrieve, no-throw (Python `d.pop(k, default)`):
  `VALUE` = stored value or `DEFAULT`; `P2` = `P` minus `KEY` (or `P` unchanged if absent).

  **Arity note (provisional):** Python's `pop` mutates in place and returns only the value; our immutable
  dicts must ALSO output the residual, so the relational forms are `pop/4` + `pop/5`, not `/2` + `/3`.
  Confirm before implementing.

## Status
**No current consumer** — profiles are built-once/read-many; only the planner mutates, and it uses `set`,
not `delete`/`pop`. Implement each when the corpus migration first needs it (all small + self-contained,
listed so the names are reserved and not forgotten). Do not block the read surface / `set` on these.

## Where
- Co-locate with the other dict builtins. Build a new `DictTerm` for the residual (the type is immutable —
  construct fresh, never mutate `_data`).

## Acceptance
- `delete({a:1, b:2}, a, P2)` ⇒ `P2 == {b:2}`; `delete({a:1}, z, _)` **throws** (catchable via `catch/3`).
- `discard({a:1}, z, P2)` ⇒ `P2 == {a:1}` (no throw).
- `pop({a:1, b:2}, a, V, P2)` ⇒ `V=1, P2 == {b:2}`; `pop({a:1}, z, _, _)` throws;
  `pop({a:1}, z, V, P2, 9)` ⇒ `V=9, P2 == {a:1}`.
- original `P` unchanged in all cases (immutability).
