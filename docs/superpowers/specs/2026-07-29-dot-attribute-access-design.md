# `PROFILE.key` — dict attribute-access sugar, and the dict-type-module convention

**Date:** 2026-07-29
**Status:** design approved (brainstormed with Michael); not yet implemented.

## Summary

Two coupled changes.

1. **Language.** Allow `BASE.key` where `BASE` is a logic variable, as exact syntactic sugar for
   `BASE[key]`. Same atom resolution, same errors, same runtime. `.` reads `DictTerm`s only;
   arbitrary Python objects stay behind `++(...)`.
2. **Convention.** A dict "type" gets a module that owns its key atoms (`-private` by default) and
   exports *semantic* predicates rather than per-key getters. Tell-don't-ask instead of
   `get(PROFILE, key, VALUE), <inline test>` repeated at every call site.

The language change is small and rides on tested machinery. The convention is where the value is.

## Motivation

Across `clausify` / `clausify-domains` there are **909 `get()` calls in 90 files**. Almost all are
the shape `get(PROFILE, key, PROFILE_KEY), use(PROFILE_KEY)` — a whole goal and a named variable
spent on fetching one value. `PROFILE.key` is the same character count as the variable name alone
and removes the goal.

More importantly, the current corpus is *asking*, not *telling*. The determination of, say,
foreign-ness is an inline sequence of goals duplicated at each site. Under the convention it becomes
`foreign_person(P)` everywhere, with a single point of update.

## What was verified (probes, 2026-07-29)

Against `/workspace/clausal-bug-fix` @ `79294be4`, pyenv 3.13.3 + `PYTHONPATH` per
`running-tests-in-bug-fix-clone`.

| Claim | Result |
|---|---|
| `.clausal` is parsed as Python syntax, so `X.attr` already parses | ✅ rejected deliberately at `term_rewriting.py:1022`/`:1035`, not a grammar gap |
| `P[K]` works in *arbitrary* term position | ✅ argument position, comparison, chained `P[a][b]`, repeated, under `not` |
| `P[k]` value that is an unbound `Var` aliases correctly | ✅ |
| `get/3` on a missing key **fails**; `P[k]` on a missing key **throws** | ✅ 0 solutions vs `existence_error(dict_key, k)` |
| Unbound base | ⚠️ gives `type_error(dict, _)`; should be `instantiation_error` |
| Atoms are per-module objects but compare/hash by name | ✅ `m1.foo is m2.foo` → `False`, yet cross-module dict read works |
| Strict atoms (default) rejects an undeclared bare key | ✅ `NameError: strict_atoms: undeclared atom …` |
| Functor instances expose fields as **uppercase** attributes | ✅ `Pair(A=1,B=2).A == 1`, `.a` raises |
| Perf: `get/3` vs `P[k]`, 20k solves | 0.448s vs 0.421s — no caching justified |
| Engine has `-discontiguous` but **no `-multifile`** | ✅ grep clean; polymorphism is intra-module only |
| `-private` atoms reachable from Python via `getattr` | ✅ |
| `-private` atoms reachable from another *Clausal* module when **qualified** | ⚠️ yes — `P[tmod.priv_key]` works; privacy is advisory |
| Phenomenon B (`dict-atom-keys-vs-predicates.md`) still live | ✅ reproduced: a Python/other-module-built `DictTerm` passed to `solve()` raises `NameError: name '<key>' is not defined` in the callee's namespace |

## Part 1 — the language change

### Specification

In `clausal/templating/term_rewriting.py`, `visit_Attribute` currently raises when the base of a
dotted name is a logic variable. Change it so that when `_is_logic_var_name(base)` holds, the node is
rewritten to the existing subscript form:

```
BASE.key   ⇒   BASE[key]        # key resolved exactly as a bare atom is today
BASE.KEY   ⇒   BASE[KEY]        # variable key; already supported by LoadSubscript
BASE.a.b   ⇒   BASE[a][b]
```

Non-variable bases (`mod.pred`, `currency.euro`) keep today's `LoadAttr` behaviour untouched.

### Semantics — all inherited, none new

- **Missing key throws** (`existence_error(dict_key, K)`), because `P[k]` throws. `.` is *not* a
  drop-in for `get/3`; it replaces the sites where the key is schema-guaranteed. Where absence is
  expected and should mean "this rule does not fire", authors keep `get/3` (soft-fail), `get/4`
  (defaulted), or `tri_get/3` (Kleene).
- **Non-dict base** → `type_error(dict, _)`. `.` therefore stays inert on Python objects; `++(...)`
  remains the only seam for `getattr`. This is deliberate: `getattr` can run arbitrary code via
  `@property`, is not guaranteed pure or deterministic, and would break assumptions relied on by
  tabling and by the SMT projection. Implicit arbitrary-code execution inside term construction is
  not worth the ergonomics.
- **Key resolution is unchanged**, including the strict-atoms declaration requirement. `P.status`
  loads iff `P[status]` loads. This preserves the sugar invariant and keeps load-time typo detection
  (`P.filing_sttus` is a `NameError` at load, not an `existence_error` on some untested case).
- **Qualified keys use the long form**: `P[profile.query_date]`. `.` is the short form, valid
  wherever a *bare* atom would already resolve — inside the owning module, or in a module that
  imports the key.
- **No caching.** Measured difference is noise, and cross-goal CSE would be unsound under
  `member(P, [D1, D2]), Foo(P.k)` where the base is rebound on redo.
- **No mutation, ever.** Reads only. Functional update stays `{**P, k: V}`; removal stays
  `delete/3`.

### Deliberate non-goals

- No functor-field access. `T.A` is not read from a compound. This keeps `BASE.KEY` unambiguously a
  variable *key* rather than colliding with uppercase functor field names.
- No method-call form. `X.foo(A)` stays a `SyntaxError`; reserved.
- No change to the ISO Prolog reader (`tools/prolog_tokenizer.py`), whose dot rule is
  whitespace-terminated. This is a Clausal-syntax feature only.

### Fixes riding along

- Unbound base should raise `instantiation_error`, not `type_error(dict, _)`
  (`clausal/logic/runtime/dict_ops.py`, `_subscript`).
- Decide whether the reified-term renderer round-trips `.` as `.` or flattens to `[k]`. Flattening is
  acceptable and cheaper; it costs source fidelity in audit output.

## Part 2 — the dict-type-module convention

### Shape

```clausal
# profile.clausal — owns the keys
-module(profile, [ Mk(Fields, P), Valid(P), ForeignPerson(P), AcquisitionValueCents(P, C), ... ])
-private([ foreign_person, investor_type, acquisition_value_cents, query_date, ... ])

Mk(Fields, P)  <- ( ... )     # constructor
Valid(P)       <- ( ... )     # validator for dicts arriving from Python/JSON

# semantic method: encodes the legal test, so the definition of foreign-ness
# lives here once instead of being re-derived inline at each call site
ForeignPerson(P) <- ( P.foreign_person is True )
ForeignPerson(P) <- ( P.investor_type is "foreign_government_investor" )
```

Callers import *methods*, not keys.

### Why this is the right shape

Requiring a key to be *declared* buys typo protection on the name but says nothing about whether an
arbitrary profile dict actually carries it. Python resolves this the same way: objects know their
attributes because a class defines them; dicts do not care. Defining that schema *is* defining the
class — so the schema belongs in a module alongside a constructor/validator and the predicates that
use the keys.

Three concrete payoffs:

1. **It dissolves Phenomenon A.** `au/firb/profile_keys.yaml` documents the workaround in a comment:
   *"query_date INCLUDED: its `query_date/2` predicate is NOT exported from computation, so the
   imported `query_date` atom and the predicate coexist."* That un-export dance exists only because
   key atoms must travel to their readers. Under the convention they do not travel.
2. **It moves an existing schema into the language.** 40 of 54 domains already carry
   `profile_keys.yaml` with types (`foreign_person: bool`, `interest_percent: value`), self-described
   as "single source of truth … so the interface catalog can machine-derive the profile schema
   (IC-13) and the SMT proof can range over a symbolic profile." It is a sidecar that nothing
   enforces at load time. The type module is that file, where the compiler and strict-atoms checker
   can see it.
3. **It narrows Phenomenon B.** A Python-built `DictTerm` passed to `solve()` inlines its atom keys
   as bare `Name`s resolved in the *callee's* namespace. If the entry-point predicate lives in the
   key-owning module, the keys are in scope and the failure cannot arise.

### It is a convention, not a mechanism

Python-spirited flexibility is intended:

- Keys are private **by default**, with deliberate export for the few genuinely read raw elsewhere.
  External code then gets `P[profile.key]` or an import plus `P.key`, at the cost of its own
  fragility when the schema changes. That is the author's trade to make.
- **Privacy is advisory, not enforced.** Verified: `-private` does not block qualified access —
  `P[tmod.priv_key]` reads fine from another module. This matches Python's `_private` and should be
  documented as such rather than presented as a guarantee.
- **Exported methods must be semantic.** `dict-native-profile-api.md` deleted the
  `profile_find_<key>/2` accessor families across 31 rulebases as "codegen boilerplate, ~100
  lines/domain". A type module exporting one getter per key is that boilerplate returning under a new
  name. The test for a method is whether it encodes a domain test (`ForeignPerson(P)`,
  `ThresholdApplies(P, T)`), not whether it wraps a key.

### Polymorphism — a real constraint

The engine has `-discontiguous` (intra-module, non-adjacent clauses) but **no `-multifile`**. A
method predicate therefore cannot be extended from another module. Polymorphism must be tag-dispatch
*within* the type module or one designated dispatch module, discriminating on a `kind`/`type` key.
That is closed-world dispatch, not open extension. The convention must not promise more.

## Ecosystem impact

- **SMT prover** (`clausify` `auto/formal`): profile reads are projected onto `has_k`/`val_k` Z3
  consts only for *recognized* read forms. A new form the projection does not know degrades
  provability silently rather than erroring. The projection must learn `.` — or, if `.` is flattened
  to `[k]` before the prover sees it, confirm that flattening happens upstream of projection.
- **Reifier / renderer / auditor**: see the round-trip decision above.
- **Corpus lint** (`clausify-domains/_tools/check_corpus_conventions.py`, R8 + `R8_STRINGKEY_ALLOWLIST`):
  needs rules for the new convention, and R8 should be re-examined once keys stop crossing modules.
- **Docs**: `docs/dicts_sets.md`, `docs/directives.md`, the clausify cheat-sheet and scaffolding
  skeletons. Item 1 of `todo/dict-native-profile-api.md` ("Core promotion — remaining") is the
  natural home.
- **`formalize_lib` wrappers** (`check_gte`, `check_tri`, …) take the key as a *parameter*, so they
  need the dynamic `P[KEY]` form and are unaffected.
- **Back-compat**: none at risk. `X.attr` is currently a `SyntaxError`, so no existing code relies on
  any behaviour here.

## Migration

Strictly additive and opt-in. `get/3` is not deprecated — it remains correct for optional keys, and
the majority of the 909 sites may well stay as they are. Sequence:

1. Land the language change plus the `instantiation_error` fix.
2. Document `.` and the convention.
3. Teach the SMT projection the new form.
4. Pilot the convention on **one** domain (`au/firb` is the natural choice — it carries the
   Phenomenon A workaround in its own YAML comment) and confirm decision-preservation and
   `G3 PROVED ≥ baseline` before any corpus-wide pass.

## Testing

- Parser/compiler: `P.k` ≡ `P[k]` for atom keys, variable keys, chains; `mod.pred` unaffected;
  `X.foo(A)` still rejected; undeclared key still a load-time `NameError`.
- Runtime: missing key throws `existence_error`; non-dict throws `type_error`; unbound base throws
  `instantiation_error` (new); `Var`-valued key aliases; correct behaviour in argument position,
  comparisons, and under `not`.
- Convention: a fixture type-module with private keys, a constructor, a validator, and a semantic
  method; a caller that imports only methods; a tag-dispatch polymorphism case.
- Regression: the full suite, plus one pilot domain re-proved.

## Open questions

1. Renderer round-trip: preserve `.` or flatten to `[k]`?
2. Does the SMT projection see source or post-flattening IR?
3. Should Phenomenon A get its own engine fix (arity-aware call resolution — option 3 in
   `implementation_plans/dict-atom-keys-vs-predicates.md`), independent of this convention? It would
   fix `get/3` and `[]` sites too, not only those adopting the new shape.
