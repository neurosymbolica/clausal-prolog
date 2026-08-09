# term_expansion: support compile-time predicate synthesis from data

**Found:** 2026-07-03, building the profile-accessor codegen. We wanted one rule to turn a
data decl `profile_key(consent_valid, bool)` into named predicates
`profile_has_consent_valid/1`, `profile_has_consent_valid_t/2`, `profile_get_consent_valid/2`
at load time. `TermExpansion/4` (one-to-many, importable) is the right hook, but two gaps
block computed-name generation. Workaround shipped: a BUILD-TIME codegen script
(a downstream rulebase corpus's own `_tools/gen_profile_accessors.py`) that emits the clauses into a marked
region of the rulebase. This todo is the "nicer" compile-time version.

## Gap 1 — no string -> functor interning
`atom_concat(has_, stays, X)` binds X to the Python `str` "has_stays", not the interned
atom/functor `has_stays` (atoms are PredicateMeta classes). So a name can be COMPUTED as text
but not turned into a callable predicate identity. `unpack(HEAD, ["has_stays", P])` /
`functor(HEAD, "has_stays", 1)` build a term with a string functor that never registers as a
predicate. **Fix:** a primitive to intern a string as a functor — e.g. `atom_string/2`, or make
`functor/3` and `unpack/2` intern a string name into a real functor.

## Gap 2 — variable-bound one-to-many expansion doesn't materialize as clauses
Even fixed-name generation loses the data:
```clausal
-module(gen, [marker(K), TermExpansion(A,B,S,T)])
TermExpansion(q(key(KEY)), [q(marker(KEY))], STATE, STATE) <- True
key(stays),
key(income),
```
After load, `marker/1` EXISTS but `solve(marker(V))` yields NOTHING — the matched `KEY`
(stays/income) did not flow into the quoted output as a registered fact. **Fix:** the expansion
pipeline must substitute the matched variables into the quasi-quoted OUTPUT items and register
the results as real clauses (facts included).

## Acceptance
A single importable `TermExpansion` rule that turns N `profile_key(K, TYPE)` decls into the 3N
accessor clauses (computed names), queryable after load — replacing the build-time script.
