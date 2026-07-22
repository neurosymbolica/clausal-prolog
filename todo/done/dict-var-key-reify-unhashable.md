# Reifier crashes on a var-keyed non-splat dict literal — `TypeError: unhashable type: 'Variable'`

**DONE 2026-07-21.** Fixed per the fix direction below: `_is_intern_atom_key` replaced
with a conservative `_is_const_key` whitelist (Constant / negated number / tuple of
those); any dict with a non-constant key now routes to the `DictLiteral`
representation. F013 verified preserved (string/int-only dicts still reify to a raw
dict). New `TestDictLiteral` cases: var-key round-trip, mixed var+string and var+atom
keys, var-key-shares-splat-representation. Red-green verified; full suite 10009
passed, 0 failed. The `if key is not None` splat-marker note below was left as-is:
splat literals provably do not reach the raw-dict branch (splat round-trip tests
pass), so the guard is inert; not worth churning.

**Filed:** 2026-07-21, split out of `dict-nonsplat-var-key-eager-fold.md` while triaging
the orchestrator's `DICT-VAR-KEY-FINDINGS.md` (it asked "check for interaction with
`a1cb0230`" — this is that interaction, verified by probe).

## Symptom
```python
reify_source('f(O) <- (K is "a", O is {K: 20})\n')
# TypeError: unhashable type: 'Variable'
```
Controls (verified 2026-07-21 on `a1cb0230`): splat var key `{**{"n": 1}, K: 20}` round-trips
OK (splat path yields `DictLiteral`), var VALUE `{"a": V}` round-trips OK. Only the
non-splat var-KEY form crashes.

## Root cause
`clausal/reflection.py` `_ClauseReifier.term`, `ast.Dict` branch (~236-254): `a1cb0230`
routes a dict to the list-keyed `simple_ast.DictLiteral` representation only when a key is
an `$intern_atom(...)` call (`_is_intern_atom_key`, ~149). A logic-var key is a bare
`ast.Name` → falls through to the raw-Python-dict comprehension → `self.term(key)` yields a
reflection `Variable`, which is unhashable by policy (predicate.py:203, "mutable terms
shouldn't be hashable") → TypeError. Exactly the atom-key bug `a1cb0230` fixed, for the
Variable-key case it didn't cover.

## Fix direction
Extend the `DictLiteral` fallback condition: route to `DictLiteral` when any key would not
reify to a hashable constant — i.e. bare-atom keys (current check) OR variable keys (any
non-`ast.Constant` key is the simple over-approximation; check whether that regresses the
string/int raw-dict guarantee, F013 — it shouldn't, since `ast.Constant` covers those).
No renderer change expected — `_dict_literal_ast`/`_dict_key_ast` already round-trip
`DictLiteral`. Add cases to `tests/test_reflection_render.py` `TestDictLiteral`: var-key
round-trip, mixed var/string keys.

Note while in there: the raw-dict comprehension's `if key is not None` silently drops
`key=None` entries (Python-AST splat form). Probably unreachable (splats are rewritten
before reification) — confirm, and if unreachable prefer raising over silent drop.

## Impact / priority
MEDIUM: reflection is the auditor-engine substrate (renderer/reifier prereqs landed
2026-07-20). Any corpus/domain clause containing `{K: V}` kills reification of its whole
file with a bare TypeError, like the atom-key bug that gated 22% of corpus — but var-keyed
literals are rare today (they are also runtime-broken, see sibling ticket, so nobody ships
them). Small, self-contained fix with an existing landed pattern to follow; cheap to do
ahead of the deeper compiler fix in `dict-nonsplat-var-key-eager-fold.md`.
