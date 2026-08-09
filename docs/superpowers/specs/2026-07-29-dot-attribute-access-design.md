# `PROFILE.key` — dict attribute-access sugar, and the dict-type-module convention

**Date:** 2026-07-29
**Status:** design approved (brainstormed with Michael); not yet implemented.

## Summary

Two coupled changes.

1. **Language.** Allow `BASE.key` where `BASE` is a logic variable: pure source-level sugar for a
   read of `BASE[key]` into an implicit variable. Same atom resolution, same errors, same runtime.
   There is no `./2` term. `.` reads `DictTerm`s only; arbitrary Python objects stay behind
   `++(...)`.
2. **Convention.** A dict "type" gets a module that owns its key atoms (`-private` by default) and
   exports *semantic* predicates rather than per-key getters. Tell-don't-ask instead of
   `get(PROFILE, key, VALUE), <inline test>` repeated at every call site.

The language change is small and rides on tested machinery. The convention is where the value is.

## Motivation

Across a large external corpus, `get()` calls of this shape number in the high hundreds, spread
over most of the corpus's files: `get(PROFILE, key, PROFILE_KEY), use(PROFILE_KEY)` — a whole goal
and a named variable spent on fetching one value. `PROFILE.key` is the same character count as the
variable name alone and removes the goal.

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

### `P.key` is not a term

This must be stated first because the syntax invites the wrong reading. `X is P.key` looks like
`X is '.'(P, key)` — a `./2` compound. **It is not.** There is no `./2` term, no `.` functor, and
nothing a program can inspect, unify against, or construct with `=..`. The construct exists only in
source; it is gone before any term is built.

`.` therefore lives *outside* the regular term language, and the documentation must lead with that
rather than treating it as an operator.

### Lowering

The meaning of `P.key` is: **read once into an implicit variable, then substitute**. For a clause
body containing one or more occurrences of `P.key`, the compiler:

1. mints a fresh implicit variable (conceptually `IMPLICIT_P_KEY`);
2. inserts a hard-failing read — the `get/3` shape, but throwing rather than failing, i.e. exactly
   `P[key]`'s semantics — as a **goal**, at the position of the first occurrence;
3. substitutes that variable at every remaining occurrence of `P.key` in the same scope.

```clausal
foo(P) <- ( bar(P.k), baz(P.k, 1) )

# means exactly
foo(P) <- ( <read P[k] into V, throwing if absent>, bar(V), baz(V, 1) )
```

Placing the read as a **goal at the first-occurrence position** — rather than caching it in a
compiled-in Python local — is what makes this sound under backtracking. In
`member(P, [D1, D2]), foo(P.k)` the read sits after `member/2`, so redo re-executes it against the
new binding of `P`. A cache hoisted to clause entry would go stale; this cannot.

**The same lowering applies to `P[key]`**, so the two spellings remain exactly equivalent and `[]`
gains the same single-evaluation guarantee. This is a change to existing `[]` behaviour (today each
occurrence inlines its own `$subscript` call) and needs its own regression pass.

### Scoping the read to its control construct

The read is inserted **immediately before the goal that uses it, inside the innermost enclosing
control construct** — never lifted out of a disjunction arm, `not`, or if-then-else branch:

```clausal
( a(P) or b(P.k) )

# means
( a(P) or ( <read P[k] into P_K>, b(P_K) ) )
```

Lifting the read ahead of the disjunction would make it throw on a missing key even when `a(P)`
succeeds — turning a successful determination into an error. Scoping it per arm avoids that.

The consequence is deliberate and accepted: **sharing does not cross an arm boundary.** A later
`P.k` outside the disjunction reads again. Re-reading is cheap (measured noise), and the alternative
— reasoning about which arm bound the implicit variable — is not worth it.

In `clausal/templating/term_rewriting.py`, `visit_Attribute` currently raises when the base of a
dotted name is a logic variable. That rejection becomes the rewrite above, for:

```
BASE.key     # atom key
BASE.KEY     # variable key
BASE.a.b     # chained
```

Non-variable bases (`mod.pred`, `currency.euro`) keep today's `LoadAttr` behaviour untouched.

### Semantics — inherited from `P[key]`

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
- **No Python-level caching.** Sharing happens through the implicit *variable* described above,
  which backtracking unwinds correctly. Caching the value in a compiled-in local would be unsound
  under `member(P, [D1, D2]), foo(P.k)`. Measured cost is noise anyway (0.421s vs 0.448s / 20k
  solves), so the read-once lowering is for clarity and single-evaluation semantics, not speed.
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

Predicates are `snake_case` per the standing convention
(`todo/done/module-predicates-snake-case-rename.md`): un-enforced, chosen because the local student
models generate it far more reliably than TitleCase, and because it matches Python's stdlib and
SWI-Prolog.

```clausal
# profile.clausal — owns the keys
-module(profile, [ make(Fields, P), valid(P), is_foreign_person(P), acquisition_value_cents(P, C) ])
-private([ foreign_person, investor_type, acquisition_value_cents, query_date ])

make(Fields, P) <- ( ... )    # constructor
valid(P)        <- ( ... )    # validator for dicts arriving from Python/JSON

# semantic method: encodes the legal test, so the definition of foreign-ness
# lives here once instead of being re-derived inline at each call site
is_foreign_person(P) <- ( P.foreign_person is True )
is_foreign_person(P) <- ( P.investor_type is "foreign_government_investor" )
```

Callers import *methods*, not keys.

### snake_case is why Phenomenon A exists

**Phenomenon A** (`implementation_plans/dict-atom-keys-vs-predicates.md`): when a module imports a
0-arity atom whose name matches a predicate that same module *exports*, the atom shadows the
predicate. Every call `key(A, B)` then mis-resolves to constructing the 0-arity atom with keyword
arguments and fails with `TypeError: __init__() got an unexpected keyword argument '<VarName>'`. The
collision is tied to the **export**, not to mere coexistence — an unexported predicate and an
imported same-named atom get along fine, which is what at least one downstream domain relies on.

The reason this bites at all is that snake_case predicates and snake_case key atoms occupy the same
namespace shape. `query_date` the key and `query_date/2` the predicate are spelled identically
because *both* conventions point at the same domain noun. Under TitleCase predicates the collision
could not arise; it is the price of the snake_case convention, and worth paying, but it means
Phenomenon A is structural rather than incidental — it will recur for every domain whose key names
its own test.

Keeping keys `-private` to the type module removes the import that triggers it.

### A predicate name is *not* usable as a key (verified)

A key atom must be declared; the same-named predicate will not serve. In a module that defines
`query_date/2`, a bare `query_date` in key position binds to the **predicate class**, and the
compiler dies:

```
NotImplementedError: term_to_ast_expr: unsupported term type PredicateMeta:
  <Predicate query_date/2, 1 clause(s), compiled>
```

This is loud and at load time, so it is a diagnostics problem rather than a correctness one — but it
should be a named Clausal error suggesting the qualified form or an import.

The correctness problem is next door, and it is severe. See
`todo/query-template-rebinds-atom-dict-keys.md`: when such a dict crosses the Python→`solve()`
boundary into a module where the key name is bound to *anything else*, the query template silently
rebinds the key to that other object. Verified end to end — a profile with `query_date: 5` returns
**zero** solutions from a rule that should succeed, with no error, even though the rule reads the key
in fully qualified form. Strict reads surface it as a bogus `existence_error`; `get/3` fails
silently; `get/4` silently returns the default.

This is the strongest argument for the convention. Keys that never leave their type module, read by
methods defined in that module, cannot hit either failure — the name is bound to the atom exactly
where it is used. It is also an argument for fixing the underlying compiler behaviour (option 2 of
`dict-atom-keys-vs-predicates.md`: compile atom keys by identity, not by name), since the convention
protects only its adopters.

### Why this is the right shape

Requiring a key to be *declared* buys typo protection on the name but says nothing about whether an
arbitrary profile dict actually carries it. Python resolves this the same way: objects know their
attributes because a class defines them; dicts do not care. Defining that schema *is* defining the
class — so the schema belongs in a module alongside a constructor/validator and the predicates that
use the keys.

Three concrete payoffs:

1. **It dissolves Phenomenon A** (defined above). One downstream domain's `profile_keys.yaml`
   documents the workaround in a comment:
   *"query_date INCLUDED: its `query_date/2` predicate is NOT exported from computation, so the
   imported `query_date` atom and the predicate coexist."* That un-export dance exists only because
   key atoms must travel to their readers. Under the convention they do not travel.
2. **It moves an existing schema into the language.** Most domains in that corpus already carry
   a `profile_keys.yaml` with types (`foreign_person: bool`, `interest_percent: value`), self-described
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
  name. The test for a method is whether it encodes a domain test (`is_foreign_person(P)`,
  `threshold_applies(P, T)`), not whether it wraps a key.

### Polymorphism — a real constraint

The engine has `-discontiguous` (intra-module, non-adjacent clauses) but **no `-multifile`**. A
method predicate therefore cannot be extended from another module. Polymorphism must be tag-dispatch
*within* the type module or one designated dispatch module, discriminating on a `kind`/`type` key.
That is closed-world dispatch, not open extension. The convention must not promise more.

## Ecosystem impact

- **SMT prover** (an external prover's own front end): profile reads are projected onto `has_k`/`val_k`
  Z3 consts only for *recognized* read forms. A new form the projection does not know degrades
  provability silently rather than erroring. **Resolved 2026-07-29** by a shared desugaring seam
  rather than a second implementation — see "The shared desugar seam" below.
- **Reifier / renderer / auditor**: see the round-trip decision above.
- **Corpus lint** (the downstream corpus's own convention checker, rule R8 + its string-key
  allowlist): needs rules for the new convention, and R8 should be re-examined once keys stop
  crossing modules.
- **Docs**: `docs/dicts_sets.md`, `docs/directives.md`, an external cheat-sheet and scaffolding
  skeletons. Item 1 of `todo/dict-native-profile-api.md` ("Core promotion — remaining") is the
  natural home.
- **Downstream helper-library wrappers** (`check_gte`, `check_tri`, …) take the key as a
  *parameter*, so they need the dynamic `P[KEY]` form and are unaffected.
- **Back-compat**: none at risk. `X.attr` is currently a `SyntaxError`, so no existing code relies on
  any behaviour here.

## The shared desugar seam

`clausal/templating/desugar.py` holds `desugar_surface(tree) -> tree`, the ONE implementation of
`P.key → P[key]`. Both front ends run it: `TermTransformer.visit_Attribute` calls it, and the
prover — an independent SMT-based checker maintained by a downstream consumer — calls it
immediately after its own `ast.parse`. A future sugar is added there once, and both sides learn
it together.

The boundary is deliberate and narrow — **syntax only**:

- The pass is pure `ast → ast`, imports nothing but `ast`, preserves source positions, and returns
  anything it does not recognise untouched (so an unmodelled shape still reaches each consumer's
  own "unsupported" path — the prover degrades, it never invents a proof).
- Semantics are **not** shared. The prover re-implements engine behaviour on purpose so it is an
  independent cross-check; if it consumed the engine's Terms IR or analysis, an engine bug would
  become invisible to it. Sugar carries no semantics, so sharing it costs nothing.
- The read-once hoisting pass (`_lower_dict_reads`) stays engine-only. Minting implicit variables
  and reordering goals is an evaluation strategy, not a spelling; the prover models the inline
  `P[key]` read directly and wants neither.
- Two shapes are explicitly NOT rewritten: a dotted module path (`mod.pred`) and the reserved
  method-call form `P.foo(A)` — the latter would otherwise change shape under the engine's
  `SyntaxError` and the prover's `Unsupported`. The `++(...)` Python escape is not descended into
  at all: its payload is real Python, where `D.value` is genuine attribute access.

## Migration

Strictly additive and opt-in. `get/3` is not deprecated — it remains correct for optional keys, and
the majority of the 909 sites may well stay as they are. Sequence:

1. Land the language change plus the `instantiation_error` fix.
2. Document `.` and the convention.
3. Teach the SMT projection the new form.
4. Pilot the convention on **one** domain (the domain that carries the Phenomenon A workaround in
   its own YAML comment is the natural choice) and confirm decision-preservation and
   `G3 PROVED ≥ baseline` before any corpus-wide pass.

## Testing

- Parser/compiler: `P.k` ≡ `P[k]` for atom keys, variable keys, chains; `mod.pred` unaffected;
  `X.foo(A)` still rejected; undeclared key still a load-time `NameError`; no `./2` term is
  observable (`=..`, `functor/3`, unification against `'.'(_, _)` all see through the sugar).
- Lowering: repeated `P.k` in one body reads once; likewise repeated `P[k]`; the read re-executes on
  redo under `member(P, [D1, D2]), foo(P.k)`; the read stays inside each disjunction arm, `not`, and
  if-then-else arm — one test per construct, including the `( a(P) or b(P.k) )` case where a missing
  key must **not** prevent `a(P)` from succeeding.
- Key/predicate collision: a bare key naming a locally-defined predicate is a named Clausal error,
  not `NotImplementedError: unsupported term type PredicateMeta`.
- Runtime: missing key throws `existence_error`; non-dict throws `type_error`; unbound base throws
  `instantiation_error` (new); `Var`-valued key aliases; correct behaviour in argument position,
  comparisons, and under `not`.
- Convention: a fixture type-module with private keys, a constructor, a validator, and a semantic
  method; a caller that imports only methods; a tag-dispatch polymorphism case.
- Regression: the full suite, plus one pilot domain re-proved.

## Open questions

1. Renderer round-trip: preserve `.` or flatten to `[k]`?
   **Answered in implementation:** flattens to `[k]`. Clauses that needed read-once lowering also
   render their extracted `_read_N` goals. Accepted trade; it does change audit/reified output.
2. ~~Does the SMT projection see source or post-lowering IR?~~ **Answered 2026-07-29 — SOURCE.**
   The prover has its own front end: it does `ast.parse(text)` on the `.clausal` source, entirely
   independent of the engine's pipeline. Two consequences, both the opposite of what was assumed:
   - **`.` is invisible to the prover and MUST be taught before any domain adopts it.** The prover
     never sees the engine's `P.k → P[k]` rewrite; it sees an `ast.Attribute` node it does not
     handle. Migration step 3 is therefore a **hard blocker** on the pilot, not a nice-to-have.
     (Its node-walking helper for the arrow-adjacency check already visits `ast.Attribute`, but
     that is not a read projection.)
   - **The read-once lowering does not affect the prover at all**, since the prover never sees
     lowered goals. The feared `_read_0 is P[k]` shape never reaches it.
   Note the target form already exists: the prover's translation layer already projects
   `V is P[key]` (a `bind_is` goal with a `Subscript` RHS) via its own subscript-read axiom.
   Teaching the prover `.` is plausibly just normalizing `Attribute` → `Subscript` in its front end
   before that check.
   **Done 2026-07-29** — and done *once*, as a shared syntax-only pass rather than a second copy of
   the rule. See "The shared desugar seam" above.
3. Should Phenomenon A get its own engine fix (arity-aware call resolution — option 3 in
   `implementation_plans/dict-atom-keys-vs-predicates.md`), independent of this convention? It would
   fix `get/3` and `[]` sites too, not only those adopting the new shape. Given that snake_case makes
   the collision structural, this looks more like a standing debt than a corner case.

## Dependency

`todo/query-template-rebinds-atom-dict-keys.md` is not caused by this design, but it silently
corrupts atom dict keys crossing the Python boundary and this feature inherits it unchanged. The
pilot domain should not be read as evidence for the convention until that is fixed or the domain is
confirmed unaffected.
