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

---

## STATUS 2026-09-02 — gap 2 FIXED (now pinned); gap 1 re-scoped with findings

**Gap 2 is fixed on current main.** The exact repro above now works: the
matched `KEY` flows into the quoted output and registers as real facts
(`marker/1` yields stays/income). It had no regression pin, so one is added:
`TestNestedVarSubstitution` in tests/test_term_expansion.py +
`tests/fixtures/expansion_nested_var.clausal`. (Side note: the SOURCE
predicate `key/1` is left with zero clauses after full consumption and
raises "no compiled dispatch" if called — arguably correct, noted here.)

**Gap 1 findings (probed 2026-09-02):**
- `global_atom/2` now exists and interns a string to a real atom — the
  ATOM half of the ask is available.
- `functor/3`/`unpack/2` with a string name still build a generic
  `Compound` with a string functor that registers nothing — and a
  Compound-headed generated clause would land squarely in the
  generic-Compound-vs-declared-term identity trap
  (todo/done/a-generic-compound-renders-identically-to-a-declared-term.md)
  and the shared-predicate mutation-gate questions
  ([[a-shared-predicate-has-no-single-mutation-gate]]).
- A further blocker hit while probing the acceptance scenario: a
  TermExpansion BODY's call to `unpack/2` resolved to an (empty) module
  predicate, not the builtin — TE bodies run pre-compile with different
  name resolution, which any computed-name design must also address.

So the remaining work is exactly ONE design decision plus plumbing: what it
means to mint a predicate identity from a computed string at expansion time
(intern-into-what-namespace, visibility, collision-with-declared rules) —
the same identity questions the two linked todos already track. Not decided
unilaterally here.
