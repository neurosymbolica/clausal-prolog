# Cross-cutting design decisions — 2026-07-05 audit

Append `resolved-by-user` and `open` design questions here as sessions
resolve them, so later sessions check here BEFORE asking the user again.

## Triage order (A12 roll-up, 2026-07-06)

All open questions below, grouped into decision clusters and ordered by
unblocking power (earlier decisions gate later ones). One user sitting per
cluster should close every member question.

1. **Cross-type term identity (numeric/bool conflation)** — the root
   decision the most other questions inherit: `A01-D001` (in
   `investigate-A01-parked-design-decisions.md`), then members A02-D002
   (index keys), A05-D001 (dif/reify truth), A06-D005 + A07-D002 (bools in
   CLP domains), A09-F015/F022 acceptance matrices, A04-F006 tabling
   variant keys.
2. **Error protocol** — one decision closes the largest confirmed-bug
   family: A09-D002 (typed LogicException + narrow the trampoline's
   RuntimeError catch) + A11-D001 (module/wrapper predicates convert at
   the boundary), with A06-D002's silent-no-op principle and A12-F002's
   acceptance folded in. Affects ~14 queued fix todos across
   A06/A09/A10/A11/A12.
3. **Attr-hook & solver-store contract** — A04-D001 (semidet boolean hook
   protocol), A05-D002 (reserved attr keys), A07-D003 (PySAT bridge
   depth), A08-D002 (Z3/ortools/LP hook registration), A12-D001
   (constraints in tabled answers). These must be decided together: the
   hook contract determines what tabling and the backends can preserve.
4. **Tabling soundness semantics** — A04-D004 (NAF-on-tabled spawn vs
   scan), A04-D002 (invalidation granularity); joint with the A04-F001
   SLG completion re-architecture and cluster 3's A12-D001.
5. **Compound ↔ declared-functor-instance identity** — A01-D004 +
   A03-D001 (catch/3 catchers) + A10-D004 (TermExpansion patterns).
6. **Arithmetic `//`/`%` + optimization contracts across backends** —
   A08-D001 (Python semantics everywhere; also fixes the A11 Prolog
   translator's mod/floordiv exports), A08-D005 (optimize result
   contracts), A08-D003/A08-D004 (CLP(Q) float rejection + strict
   inequalities), A07-D001 (taut/sat_count store-awareness).
7. **findall/copy semantics** — A03-D002 (template copy vs sharing) +
   `investigate-A09-copy-term-attrs.md` (copy_term and attributes).
8. **Namespace & import policy** — A10-D002 (stdlib shadowing), A10-D003
   (imported-head clobber), A10-D001 (ALLCAPS names in embedded Python),
   A12-D002 (engine-name leak), plus A10-F013's fix.
9. **Higher-order commit semantics** — A09-D001 (maplist/foldl
   backtracking), A11-D002 (wrapper argument coercion policy).

## Resolved by user — 2026-07-07 (A09 fix session)

The user resolved the following, all per the audit recommendation. Later
sessions/instances: treat these as settled — do not re-ask.

- **A09-D002 (error convention) → (a) typed exceptions.** Raise a typed
  `LogicException` for all type/domain/permission errors; bare failure only
  for legitimate out-of-domain relations; NEVER signal via `RuntimeError`,
  and narrow the trampoline drive-loop's `RuntimeError` catch to
  `StopIteration` + the exact PEP-479 / "already executing" RuntimeErrors
  (not subclasses like `RecursionError`). Gates A09-F006/F011/F012/F018/
  F027/F028 and the A10/A11/A12 error-family items.
- **A01-D001 (cross-type identity) → (c) split.** Stop conflating `bool`
  with `int` (reject `True` as a length/index/arithmetic operand) but keep
  `1 == 1.0` numeric-value equality as Python-native. Gates A09-F015 and the
  A06-D005/A07-D002 bool-in-domain items.
- **A09-D003 (retract bindings) → (a) bind on the real trail.** `retract/1`
  keeps its head-unification bindings (ISO/SWI + output-mode contract);
  re-satisfiability can follow later. Gates A09-F008.
- **A09-F005 (assertz of a rule) → (b) reject cleanly.** Reject asserted
  rules at assert time with a typed error (matches current docs), validating
  before mutating the clause list. A09-F026 doc then cites the clean error.
- **A10-D001 (embedded-Python var names) → (a), strengthened.** Unescaped
  ALLCAPS / `_leading` names in outer Python code are ordinary Python names
  (constants, `JSON`, `UUID`, a local `_tmp`) — NOT logic variables.
  EmbedTransformer.visit_Name no longer unboxes them at all (previously
  `X → X.value` in every context, breaking `MAX = 5` and `return _tmp`). A
  logic variable's value is reached inside embedded Python via the `++`
  escape (PyThunk machinery), not by unboxing a bare Name. Gates A10-F002.
- **A10-D002 (stdlib shadowing) → (a) warn + defer + docs.** A `.clausal`/`.pl`
  file named after a `sys.stdlib_module_names` module is almost always an
  accident. The extension finder emits a `ClausalLintWarning` and defers to
  the standard library (returns None → PathFinder loads the real module)
  rather than silently shadowing it. import.md corrected. Gates A10-F010.
- **A12-D002 (engine-namespace leak) → (a) unleak, partial.** The engine
  helper *functions* `walk`/`deref`/`unify` are injected into module
  namespaces under the reserved `$`-prefix only (generated bodies reference
  `$deref`/`$unify`), freeing the public names so a user predicate
  `walk/2`/`deref/2`/`unify/2` loads and runs. The user-facing *types*
  `Var`/`Trail`/`Compound` (and `PredicateMeta`/`DictTerm`/`SetTerm`/`PyThunk`/
  `Quantity`) remain injected for embedded Python and are documented reserved.
  Mirror of the A10-F013 `clausal.call` fix. Gates A12-F004.
- **A10-D004 (TermExpansion patterns) → (a) match item.head + docs.** A
  non-Predicate TermExpansion pattern (`q(fact(X))`) matches the fact item's
  HEAD; the expansion terms are then wrapped back into fact Predicates. Also
  pre-mint term classes for functors referenced in expansion patterns (a new
  `logged_fact` introduced by an expansion). Doc snippets get their missing
  trailing commas. Full reflection-vocabulary reification (c) is still
  deferred (needs A01-D004/A03-D001). Gates A10-F008.

| ID | Status | Title | Decision + rationale | Raised by | Affects |
|----|--------|-------|----------------------|-----------|---------|
| A01-D001 | resolved-by-user 2026-07-07 | Cross-type numeric/bool unification (1 ≡ True ≡ 1.0 via Python ==) | (c) split — reject bool/int conflation, keep 1==1.0. `investigate-A01-parked-design-decisions.md` | A01 | A01 unify; A02/A04 keys; A05/A06/A07 constraint layers; A09-F015/F022 |
| A09-D003 | resolved-by-user 2026-07-07 | retract/1 binding semantics vs ISO | (a) bind on the real trail (keep bindings). `fix-A09-retract-bindings.md` | A09 | A09 database_ops; docs/database_ops.md |
| A02-D001 | resolved-from-docs | Indexed dispatch must be semantics-preserving for every caller shape (uncomputable non-var key ⇒ all-clauses fallback, never the default bucket) | F095 fix history restored unify parity at the dispatch layer; indexing is threshold-triggered (≥4 clauses) so solution sets must not depend on clause count. See A02 design-questions.md | A02 | A02 arg_index/list_dispatch; A03 predicate.py always-fail defaults |
| A02-D002 | open — parked by user preference | Cross-type numeric index keys (Decimal/Fraction/complex ↔ int buckets) — blocked on A01-D001 (cross-type unification) | Recommendation: fallback-scan now (falls out of the A02-F001 fix); key-by-`numbers.Number` only if A01-D001 endorses Python `==` semantics. `todo/audit-2026-07-05/investigate-A02-parked-design-decisions.md` | A02 | A02 dispatch keys; A04 tabling keys; A01-D001 |
| A03-D001 | open — parked by user preference | Exception-term identity: should `unify(Compound(f, args), f_instance)` succeed, or should catch-catcher lowering resolve declared functor classes? | Recommendation: fix locally in `_catcher_to_structural` (resolve term class from module env, Compound only as fallback) — no unification change; global Compound↔instance unification belongs to A01-D004. `todo/audit-2026-07-05/investigate-A03-parked-design-decisions.md` | A03 | A03 catch/3 (F004); A01 unify/term identity; A02 index keys; A04 tabling keys |
| A03-D002 | open — parked by user preference | findall/bagof/setof template copy semantics: ISO fresh-variable copies vs Clausal structure sharing (retroactive mutation of collected results, A03-F006) | Recommendation: ISO copy (rename vars unbound at collection time); sharing contradicts cheat-sheet §8 "describe output as terms" and is undocumented | A03 | A03 find_all_core; A09 builtins using findall internally; any corpus code collecting templates with free vars |
| A04-D001 | open — parked by user preference | freeze/2 frozen-goal nondeterminism: the attr-hook protocol is boolean, so frozen goals are semidet (first solution only, A04-F011) — document as intended, or redesign the hook contract to yield choice points? | Recommendation: document + lint now; hook-contract redesign only jointly with A05–A07 (dif/CLP hooks share the protocol). `todo/audit-2026-07-05/investigate-A04-parked-design-decisions.md` | A04 | A04 coroutining; A05 dif hooks; A06/A07 CLP propagator hooks |
| A04-D002 | open — parked by user preference | Tabling invalidation granularity: tables over `-dynamic` non-tabled dependencies go silently stale on assertz to the dependency (per-predicate invalidation only — doc-consistent but a footgun) | Recommendation: document loudly now; dependency-graph invalidation folded into the A04-F001 completion re-architecture. `todo/audit-2026-07-05/investigate-A04-parked-design-decisions.md` | A04 | A04 tabling; A09/A11 database ops; corpus rulebases mixing `-dynamic` + `-table` |
| A04-D004 | open — parked by user preference | NAF-on-tabled semantics: should `not p(...)` spawn evaluation of a never-called tabled subgoal (standard SLG), or is "tables reflect only what was queried" intended? Current no-entry→succeed is unsound and query-order-dependent (A04-F002/F003) | Recommendation: spawn (needs compiler seam — `_naf_tabled` is emitted by A03's tabled_naf.py); stopgap = subsuming-variant scan + delay-instead-of-succeed. `todo/audit-2026-07-05/fix-A04-naf-tabled-no-entry.md`, `investigate-A04-wfs-variant-resolution.md` | A04 | A04 tabling/WFS; A03 tabled_naf codegen; docs/wfs.md contract |
| A05-D001 | open — parked by user preference | Cross-type truth in the constraint layer: dif/reify_eq/eq-truth-vars inherit Python `==` unification (`dif(1,1.0)` False, `eq(1,1,1)` succeeds, `structural_eq(1,1.0)` True vs docs' "Prolog ==/2") | Recommendation: keep dif/reify_eq strictly unify-consistent (anything else is unsound vs the engine); the real decision is A01-D001's, which this layer must inherit verbatim; independently fix the structural_eq doc claim. `todo/audit-2026-07-05/investigate-A05-parked-design-decisions.md` | A05 | A01 unify semantics; A05 dif/reif/structural_eq; A03 setof keys; docs/constraints.md |
| A05-D002 | open — parked by user preference | Engine-reserved attr keys ("dif"/"fd"/"clpb"/"real"/"units") are user-writable via put_attr/3 with arbitrary values that reach solver hooks — direct trigger of the A05-F002 segfault and a silent-corruption channel | Recommendation: defensive validation in every hook + document keys as reserved (rejecting writes breaks legitimate hand-posting; namespacing is a breaking rename). `todo/audit-2026-07-05/investigate-A05-parked-design-decisions.md` | A05 | A05 dif hook; A06/A07 FD/B/R hooks; A09 attributes builtins |
| A06-D002 | open — parked by user preference | Constraint-builtin op-string vocabulary: sum_/scalar_product accept only Prolog spellings (#=, =<, \=); the language's own ==/<=/!= silently post nothing (A06-F011) | Recommendation: accept both spellings + raise ValueError on unknown op (silent no-op is indistinguishable from "no solution" in a cut-free language). `todo/audit-2026-07-05/fix-A06-sum-op-strings.md` | A06 | any builtin taking a comparison-op atom; docs/constraints.md; Prolog import mapping |
| A06-D005 | open — parked by user preference | Booleans in CLP(Z): docs say rejected, C hook accepts True via .denominator sniff (binds FD var to True), ground paths treat True==1, Python hook rejects (C/Python divergence, A06-F009) | Recommendation: reject bool at every fd_* entry + hook, sequenced AFTER A01-D001 (bool/int conflation) — the unifier's policy must lead, CLP(Z) follows. `todo/audit-2026-07-05/investigate-A06-parked-design-decisions.md` | A06 | A01 unify (D001); A06 hooks/ground paths; A07 CLP(Q)/CLP(R) reject booleans already |
| A07-D001 | open — parked by user preference | `taut/2`/`sat_count/2`: standalone-formula vs store-aware (Triska) semantics — code ignores the store while the docstring claims Triska's design (A07-F003/F004) | Recommendation: adopt Triska store-aware semantics (cheap once A07-F001 is fixed); stopgap = document standalone semantics explicitly. `todo/audit-2026-07-05/investigate-A07-parked-design-decisions.md` | A07 | A07 clpb; docs/clpb.md; any rulebase using taut/sat_count with a store |
| A07-D002 | open — parked by user preference | Python `True`/`False` in the CLP(B) 0/1 domain (A07-F010) — joint with A01-D001 bool/int conflation | Recommendation: reject bools in `_bool_hook` (consistency with CLP(ℤ)/CLP(ℝ) explicit rejection), unless A01-D001 endorses bool==int, then normalize to int. `todo/audit-2026-07-05/investigate-A07-parked-design-decisions.md` | A07 | A01 unify layer; A07 hook; A02/A04 key conflation |
| A07-D003 | open — parked by user preference | PySAT bridge integration depth: bindings invisible to solver (A07-F005) — assumption bridge vs full SAT_KEY attr hook vs documented detachment | Recommendation: assumption bridge now (±sat_var assumptions for bound registered vars at check/label time; ~5 lines, fixes soundness); full hook only jointly with the A04 hook-contract discussion | A07 | A07 clpsat; A04 hook protocol; A09 pysat.* builtins |
| A08-D001 | open — parked by user preference | `//` and `%` semantics in backend adapters (Z3 emits SMT Euclidean div/mod; CP-SAT emits truncated div / numerator-sign mod; Real-sort FloorDiv becomes true division) — same Clausal expression answers differently per backend | Recommendation: translate faithfully to Python floor-div/mod (language contract is Python arithmetic). `todo/audit-2026-07-05/investigate-A08-parked-design-decisions.md` | A08 | A08 clpz3/clportools; A06/A07 CLP(Z) `//`,`%` semantics parity; cheat-sheet arithmetic contract |
| A08-D002 | open — parked by user preference | Solver-store sync contract: Z3_KEY/OR_KEY/LP_KEY register no attr hooks, so Clausal bindings are invisible to the backend (out-of-domain bindings succeed; labeling returns answers inconsistent with the substitution — A08-F013/F016) | Recommendation: register hooks posting `const == value` on unification, mirroring CLP(FD); interacts with the A04 hook protocol (semidet) | A08 | A08 adapters; A04/A05 attr-hook protocol; docs claiming "same semantics as native CLP" |
| A08-D003 | open — parked by user preference | Float literals reaching CLP(Q): docs promise TypeError, code silently converts to binary-exact Fraction (0.1 → 3602…/36028…); `in_q` after `in_real` succeeds | Recommendation: raise TypeError at clpq entry points (docs-conformant; exactness is CLP(Q)'s purpose). Note the guard currently lives only in clpfd dispatch (A06/A07 seam) | A08 | A08 clpq; A06/A07 dispatch; docs/clpq.md |
| A08-D004 | open — parked by user preference | CLP(Q) strict inequalities: passive diseq is unsound (A08-F004) vs Holzbaur ε-augmented rationals; docs claim Holzbaur fidelity | Recommendation: ε-rationals staged with the F002 bound-enforcement rework; interim aliasing fixes first. `todo/audit-2026-07-05/investigate-A08-clpq-strict-inequalities.md` | A08 | A08 clpq Tableau; entailed semantics; docs/clpq.md comparison table |
| A08-D005 | open — parked by user preference | Optimization result contracts across backends (FEASIBLE-as-optimal, non-attained suprema, var binding, persistent objective on shared CpModel) | Recommendation: unify mirror-named predicates on clpq.maximize's contract (bind vars, proven optimum only) | A08 | A08 clpz3/clportools optimize; docs parity |
| A11-D001 | open — parked by user preference | Error protocol for py.* module predicates: exceptions from wrapper/module predicates BYPASS catch/3 while ++-thunk Python errors are caught (executed differential, A11-F004/F014); the wrapper slice is internally inconsistent (json/csv/files fail clean; url/http/hash/re/datetime-between leak raw — A11-F016–F019) | Recommendation: convert Python exceptions to catchable logic exceptions at the ModulePredicate/trampoline boundary (one fix for every wrapper — same conversion ++ escapes get), then document a bad-data-fails / bad-usage-throws policy. Family of A09-F012. `todo/audit-2026-07-05/investigate-A11-parked-design-decisions.md` | A11 | all modules/py wrappers; A09 builtins (F012 raw escapes); docs/exceptions.md |
| A11-D002 | open — parked by user preference | Wrapper argument coercion vs type guards: regex predicates `str()`-coerce subjects (an unbound Var matches its own repr; char-lists violate the strings-as-lists Liskov contract — A11-F002); datetime ctors `int()`-truncate float components (A11-F015) | Recommendation: Liskov char-list→str join + instantiation/type errors for regex (chars.py house style); reject fractional floats in datetime ctors. `str(term)`/`int(term)` of arbitrary terms is never what a logic program means. `todo/audit-2026-07-05/investigate-A11-parked-design-decisions.md` | A11 | modules/py/* argument handling; A01 strings-as-lists contract; docs/regex.md, date_time.md |
| A10-D001 | open — parked by user preference | Are logic-var-shaped names (ALLCAPS/_leading) reserved in embedded Python code? Store/Del-context names currently break module load with a cryptic ValueError (A10-F002) | Recommendation: unbox `.value` in Load context only (skip Store/Del) — unbreaks ordinary Python (`MAX = 5`, `_tmp`) while preserving documented Load-unboxing. `todo/audit-2026-07-05/fix-A10-embed-visitname-store-context.md` | A10 | A10 EmbedTransformer; any .clausal file mixing Python code; docs/syntax.md conventions |
| A10-D002 | open — parked by user preference | Stdlib shadowing: PredicateFinder/PrologFinder precede PathFinder, so `wave.clausal`/`colorsys.pl` on sys.path shadow not-yet-imported stdlib modules; import.md claims the opposite (A10-F010) | Recommendation: warn on `sys.stdlib_module_names` hits + fix the doc claim now; outright refusal needs a user call. `todo/audit-2026-07-05/fix-A10-stdlib-shadowing-docs-guard.md` | A10 | A10 import hook; A11 module resolution; docs/import.md |
| A10-D003 | open — parked by user preference | Clause head naming an `-import_from`-ed predicate: currently silently REPLACES the source module's predicate process-wide (A10-F004) — extend, error, or local shadow? | Recommendation: load-time error (implicit cross-module mutation must not be a side effect of a clause definition; explicit assertz remains). Joint with A11 module semantics + A03 compile_module class sync. `todo/audit-2026-07-05/investigate-A10-imported-head-clobber.md` | A10 | A10 head handling/_import_remap; A03 compile_module; A11 module semantics; docs/import.md assertz contract |
| A10-D004 | open — parked by user preference | TermExpansion pattern vocabulary: docs match items with bare `q(head)` patterns, engine matches whole Predicate nodes — q() examples never fire (A10-F008) | Recommendation: match non-Predicate patterns against `item.head` for fact items + fix docs now; reflection-vocabulary reification is the principled fix but blocked on A01-D004/A03-D001 (Compound↔instance unification). `todo/audit-2026-07-05/fix-A10-term-expansion-doc-examples.md` | A10 | clausal/logic/term_expansion.py engine (A03 seam); docs/term_expansion.md; A01-D004/A03-D001 |
| A09-D001 | open — parked by user preference | Committed choice in higher-order builtins: maplist/2,3 + foldl/4 take first-solution-per-element, silently losing answers (A09-F004); docs document commit only for include/exclude | Recommendation: restore backtracking in maplist/foldl (implicit commit is a hidden cut, contradicting the cut-free contract; once/1 is the sanctioned *explicit* escape); include/exclude stay committed as documented. `todo/audit-2026-07-05/investigate-A09-ho-committed-choice.md` | A09 | A09 higher_order; corpus rulebases using maplist with nondeterministic goals; docs/higher_order.md |
| A12-D001 | open — parked by user preference | Constraints attached to tabled answers: tables store the answer skeleton and DROP dif/FD attrs on replay — second identical query is unsound (A12-F001) | Recommendation: refuse-to-table-constrained-answers error as stopgap; SLG(C)-style residue storage folded into the A04-F001 completion re-architecture. `todo/audit-2026-07-05/investigate-A12-tabling-answer-constraints.md` | A12 | A04 tabling answer representation (F001/F005); A05/A06/A07 hook families; A04-D001 protocol |
| A12-D002 | open — parked by user preference | Reserved names in .clausal module namespaces: engine helpers (walk/deref/unify/Var/Trail/Compound) leak in and break same-named user predicates with a cryptic TypeError (A12-F004); `solve` is not leaked, so the reserved set is accidental | Recommendation: underscore-prefix the injected engine bindings (no public name reserved); interim clear load error on collision; document. Sequence with A10-F013 (same seam, opposite direction). `todo/audit-2026-07-05/fix-A12-engine-namespace-leak.md` | A12 | A10 import hook module-dict; A01/A04 helper exports; docs/syntax.md |
| A09-D002 | resolved-by-user 2026-07-07 → (a) typed exceptions + narrow the trampoline RuntimeError catch | Builtin error-signaling convention: silent fail vs LogicException vs raw Python exceptions vs RuntimeError-that-the-engine-EATS — _trampoline.c treats any RuntimeError (incl. subclass RecursionError) as generator exhaustion, so locked-assertz permission errors and cyclic-input RecursionErrors become silent "no" (A09-F006/F007/F011/F012) | Recommendation: typed LogicException for type/domain/permission errors; never signal via RuntimeError; narrow the drive-loop catch to StopIteration + the PEP-479/"already executing" RuntimeErrors only (exact-type match, not subclasses). Extends A06-D002 (silent no-op indistinguishable in a cut-free language). `todo/audit-2026-07-05/investigate-A09-runtimeerror-swallow.md` | A09 | A03/A04 runtime/_trampoline.c drive loops; every builtin's error paths; docs/database_ops.md; docs/exceptions.md |
