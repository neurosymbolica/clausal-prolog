# `KEY in P` — key membership over DictTerm (Pythonic `has`)

**Part of:** [dict-native-profile-api.md](dict-native-profile-api.md) · **Order:** 2

## Goal
`filing_status in P` succeeds iff `P` (a `DictTerm`) contains that **key** — Python's `k in d` semantics.
This is the profile presence-test (replaces `profile_has/2`). Ground key.

## Where
- Today `in_/2` is a **list-element** membership builtin (`clausal/logic/builtins/` lists; see
  `builtins/__init__.py` "lists — in_/2 …"). It must **dispatch on the right operand's type**: a
  `DictTerm` → key membership (`DictTerm.__contains__`, terms.py:1658); a list → existing element
  membership; a `SetTerm` → element membership. Keep list/set behaviour byte-identical.
- Decide semidet vs. enumerating: for a **ground** key it is semidet (succeed once / fail). An **unbound**
  key over a dict should enumerate the keys (mirrors `X in List`) — nice-to-have; ground-key semidet is the
  required case for profiles. Document whichever you land.

## Acceptance
- `a in {a:1, b:2}` succeeds; `z in {a:1}` fails.
- list/set `in_` regression tests still pass unchanged.
- (if enumeration implemented) `K in {a:1, b:2}` yields `K=a` then `K=b`.
- Prover coordination: the SMT front-end must recognise dict-key `in` as `has_k` — tracked in the
  clausify-side prover todo, not here.
