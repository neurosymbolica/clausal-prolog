# `get/3` (soft read, fails) + `get/4` (defaulted) over DictTerm

**Part of:** [dict-native-profile-api.md](dict-native-profile-api.md) · **Order:** 3

## STATUS: DONE 2026-07-14
`get/3` (soft, fails on absent) + `get/4` (defaulted) added to `clausal/logic/builtins/dict_set.py`
(`_get__3`, `_get__4`; auto-merged to a multi-arity `get` builtin). DICT-first arg order per the pinned
API; implemented directly against `DictTerm.__contains__`/`__getitem__` — no routing through the throwing
subscript. Distinct from the older KEY-first `dict_get/3`. Non-ground key / non-dict → soft fail (never
throws). Tests: `get present/absent-fails/value-var/get4-present/get4-default` in the fixture +
`test_dict_set_compiler.py`.

## Goal
The non-throwing reads, mirroring Python `dict.get`:
- `get(P, KEY, VALUE)` — bind `VALUE` if `KEY` present; **fail** the clause if absent
  (Python `d.get(k)` returns `None`; failing is the logic analogue — never bind a sentinel).
- `get(P, KEY, VALUE, DEFAULT)` — bind `VALUE` to the stored value if present, else to `DEFAULT`
  (always succeeds). Arg order is `(DICT, KEY, VALUE, DEFAULT)` per the pinned API.

Ground `KEY`. `P` is a `DictTerm`.

## Where
- New builtins alongside the dict ops (co-locate with the subscript/membership work, e.g. a
  `clausal/logic/builtins/` dict module, or extend the existing attributes/list builtins module).
- `get/3` is exactly `KEY in P` guard + `VALUE is P[KEY]` but must be a single semidet predicate (no throw)
  — implement directly against `DictTerm.__contains__`/`__getitem__`, do not route through the throwing
  subscript.
- Naming decision (see umbrella): overloaded `get`, **not** `get_or_default`.

## Acceptance
- `get({a:1}, a, V)` ⇒ `V=1`; `get({a:1}, z, V)` **fails** (no throw, no binding).
- `get({a:1}, a, V, 9)` ⇒ `V=1`; `get({a:1}, z, V, 9)` ⇒ `V=9`.
- value-var unification: `get({a:V}, a, 7)` unifies `V=7`.
- Prover: `get/3`,`get/4` join the `has_k`/`val_k` name-table recognition — the prover's own downstream todo.
