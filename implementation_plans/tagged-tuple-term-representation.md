# Tagged-tuple term representation ("s-expressions in a Python tuple")

**Status:** PARKED (2026-09-03, same day). Decision by the author after sleeping on it:
the refactoring is very high-risk — it changes the Python seam, requires massive compiler
rewriting, and changes multiple language properties at once. Parked on risk/time cost, not on
lack of merit. Phase 0 (construction fast path, no repr change) remains independently viable.
No engine change made.
Rev 2: tuple-data tag changed from `()` to the `tuple` type object.
Rev 3: tag domain opened (OWA); atoms become global interned strings (standard-Prolog
semantics) with a Ciao-style `-hide` directive for opt-in module-local symbols. This SUPERSEDES
the per-module class-identity atom design shipped 2026-07-29 (strict-atoms release) — the
*checking* survives, the *identity mechanism* is replaced. See §1a.
**Motivation (recorded 2026-09-03):** the driver behind this exploration is making Clausal
**ISO Prolog compatible**. A founding Clausal design point — Python classes/objects being the
same shape as Clausal terms — pulls in the opposite direction, and its actual usage frequency
has never been measured (open question 7).
**Origin:** design discussion 2026-09-03; resolves (rather than works around) both phenomena in
`implementation_plans/dict-atom-keys-vs-predicates.md` — see §3a.

---

## 1. The design

Replace the runtime representation of compound terms — instances of per-functor classes minted
by `PredicateMeta` — with plain Python tuples under a **uniform tagged-cell discipline**:

- **Compound term** `foo(x, y)` → `("foo", x, y)`: slot 0 is the functor, an **interned str**.
- **Tuple data** `(x, y)` → `(tuple, x, y)`: slot 0 is the builtin `tuple` type object
  (identity is a language-level guarantee, one type object per interpreter; in C the tag check
  is `slot0 == (PyObject *)&PyTuple_Type`, a static pointer).
- **The discipline, not the domain, is what resolves ambiguity.** Every tuple inside the
  runtime has a tag in slot 0; no untagged tuple exists. Given that closure property the tag
  domain is **open** (OWA): a str functor, the `tuple` type, an unbound `Var` (higher-order
  terms — `(F, X)` unifies with `("foo", 1)` binding `F = "foo"`, which the class
  representation cannot express), or any object (thunks, partial applications). Only `tuple`
  itself is reserved (it marks tuple data).
- **Zero-arg atom** is the bare interned str; the empty user tuple is `(tuple,)`; a tuple
  containing an empty tuple is `(tuple, (tuple,))`. All mutually unambiguous — but note the
  atom/string collapse, §5.
- **Keyword arguments are a compile-time affair.** The compiler already resolves keyword goals
  against registered signatures and reorders positionally
  (`clausal/logic/compiler/terms_to_goalop.py:398-423`, fed by the `-module` functor lists
  parsed at `clausal/templating/term_rewriting.py:4508`). Construction takes the same path:
  named/positional only, placed by the signature; `**kwargs` stays unsupported (nothing lost).
  Partial terms (`point(x=10)` → `Var()` backfill) are compiler-emitted when the signature is
  known; impossible (compile error) for OWA-unknown functors.
- **Open-world construction is a per-module toggle**: signatures from `-module` are advisory
  when on (any arity/functor constructs a cell), checked when off. All checking is compiler-side.

## 1a. Atoms: global strings + `-hide`, replacing per-module class identity

Standard-Prolog / Ciao model: **predicate names are module-local; atom/functor names in data
are shared globally** (Ciao module-system docs, Cabeza & Hermenegildo 1999/2000). Atoms lower
to interned Python strings. Module-local symbols become **opt-in** via a Ciao-style `-hide`
directive: the compiler automatically renames hidden symbols (mangling, e.g. `"m1$foo"`, or an
unforgeable non-str object — open question §8), which is Ciao's mechanism for true abstract
data types and is also what its later work exploits for static analysis and cheap run-time
checking ("Exploiting Term Hiding...", Hermenegildo et al. 2018).

What this replaces vs. preserves from the strict-atoms design (shipped 2026-07-29):
- **Preserved:** "undeclared bare atom is a compile-time error." It becomes a pure compiler
  lint against the declared vocabulary — it no longer rides on Python name resolution at all.
  `-implicit_atoms` remains the escape hatch.
- **Replaced:** runtime per-module atom identity (`m1.foo is not m2.foo`, non-unifying).
  Default becomes global (`"foo" == "foo"` everywhere); locality is what `-hide` is for.
  The known footguns of the identity design go away with it: the "`-private` in two files
  silently breaks atom identity" trap, `register_atom_identity`/`atom_by_id`
  (`predicate.py:1178-1211`), `CLAUSAL_WARN_ATOM_IDENTITY`, and the import-the-atom-everywhere
  convention.
- **New capability:** terms become picklable/serializable/process-portable for free — class
  terms never were (they need the minting module imported on the other side). The
  second-package-copy hazard (`predicate.py:1138`) vanishes for term data (str and `tuple`
  are copy-proof); it remains only for the machinery types (Var, DictTerm, ...).

## 1b. Phase 3 rulings: functor domain + atom scope (recorded 2026-09-03, pre-Phase-3)

Settled in design discussion after the Phase 2 bridge merged; these bind the Phase 3 plan.

**Functor domain contracts to `{str}`.** Clausal functors were always atoms; with atoms as
strs, the cell functor domain is exactly interned `str`. The slot-0 *tag* domain is
`{str} ∪ {the tuple type object}` — the type object is the reserved, unforgeable data-tag,
not a functor. Consequences: the bridge's slot-0-Var (higher-order functor) support is
DEPRECATED — it caused the bridge's one Critical (cells invisible after the functor Var
bound), imposes a permanent deref on every recognition, and permits category instability
(`(F, 1)` flipping from compound to tuple-data if F binds to the tuple type). Higher-order
metaprogramming routes through `functor/3` / `=..` / `call/N` over cells (ISO's own
trade-off). Phase 3 removes the slot-0 deref from `is_cell` and the funnel — a restriction
that pays immediately. Literals/compounds as functors: no cases (ISO agrees:
`functor(T, 3, 1)` is a type_error). Closes §8 Q5-extension: the tag domain contracts, never
extends. OWA (advisory arity signatures) is orthogonal and unaffected.

**Atom scope: global by spelling; `-hide` mangles with a READER-UNWRITABLE separator.**
- Hidden atoms look like bare identifiers in the owning file; the compiler renames them to
  `module⟨SEP⟩name` where ⟨SEP⟩ is a character the Clausal reader refuses inside any atom
  token, QUOTED OR NOT (e.g. NUL or a private-use codepoint). A dotted prefix
  (`'m.my_atom'`) is rejected: it is forgeable from any module via a quoted atom and
  collides with innocent dotted atoms.
- **The guarantee is uniqueness + analysis soundness, not runtime security** — the
  Ciao/Python stance (Ciao's `:- hide` renaming backs static analysis that may assume no
  foreign module constructs the hidden functor; Python documents `__name` mangling as
  collision avoidance, with `getattr` forging allowed). Runtime construction via
  `atom_chars/2` etc. CAN forge the mangled name; documented out-of-warranty, optionally
  linted, not blocked.
- **Serialization** (the motive for embedding the module path): in-band within Clausal —
  the mangled str marshals/pickles as-is and self-locates with no registry; STRUCTURAL at
  foreign-engine boundaries (the Scryer codec ships hidden atoms as a `(module, name)`
  pair — a NUL inside an atom does not travel politely).
- Printing: the writer renders the human form (`m.my_atom`); the runtime str keeps ⟨SEP⟩.

**Double-quoted strings lower to char LISTS (ISO `double_quotes=chars`, Scryer-compatible),
and the C cons rule retires.** With runtime `str` = atom, the existing str~char-list
unification rule in `_variables.c` (which exists because str used to BE the string type)
would make `'abc'` unify with `"abc"` — ISO forbids it. Phase 3 gates/removes the rule:
str unifies with str by equality, lists with lists; SegString remains the char-list
optimisation. This RESOLVES the deferred cons-rule decision (§8 Q2) — the source-level
discrimination (bare/quoted = atom, double-quoted = chars) forces the runtime answer.

**Coordination note:** the surface parser for this syntax (quoted atoms, double-quoted char
lists, `-hide`) is being built by the author separately, on the Pratt parser already present
in the translation machinery — Phase 3's compiler work should consume its output rather than
grow a second reader.

## 2. Measured numbers (CPython 3.13, /workspace/clausal/venv, 2026-09-03)

| Operation | Class repr today | Tagged tuple |
|---|---|---|
| Construct arity-3 term via `PredicateMeta.__call__` | ~857 ns | — |
| Construct via plain `__init__` (no metaclass `__call__`) | ~86 ns | — |
| Construct tuple literal | — | ~18–25 ns |
| Field access | ~13 ns (`getattr`, slots) | ~15 ns (subscript) — a wash |
| Head dispatch, first-arm hit | ~114 ns (MATCH_CLASS) | ~48 ns (value/literal-pattern seq match) |
| Head dispatch, second-arm hit | ~178 ns | ~85–102 ns |
| Tag dispatch, tuple-data arm | — | ~66 ns |

Str-literal tags in match arms are *literal patterns* (`case ("foo", a, b)` — no dotted-name
issue at all, unlike class tags); `==` on interned strs is pointer-check-first.
`benchmarks/bench_f046_head_dispatch.py` already measures exactly str-literal head dispatch —
it is the stated yardstick for "what native match dispatch costs here."

**Rev-3.1 correction — indexing caveat on the dispatch rows.** The head-dispatch numbers
above apply to (a) predicates below the indexing threshold and (b) the per-clause destructure
step *inside* an index bucket — not to arm selection in indexed predicates. First-arg/joint
indexing kicks in at >=4 clauses when `_analyze_index_positions` finds an indexable position
(`_INDEX_THRESHOLD = 4`, `arg_index.py`); the runtime key is pulled off the instance as
`(type(a).__name__, len(term_field_names(a)))` (`_runtime_arg_key`, `arg_index.py:146` — the
class NAME, not the class object: buckets are spelling-keyed over-approximations, exactness
restored by the in-bucket match) and selects a bucket function by dict lookup. Each bucket body
is compiled by the same `_build_predicate_trampoline_funcdef`, and Phase 8 lifting deliberately
makes `head_to_match_pattern` emit MatchValue/MatchClass inside the bucket
(`compiler/predicate.py:910`), so MATCH_CLASS survives as the post-hash destructure/verify
step (also in the defaults bucket and `__all` fallback). Net effect on the analysis: for
indexed predicates both representations converge to key-extraction -> dict hit -> one
destructure, so the tuple win there is one arm's destructure (~114 -> ~48 ns), not an arm
scan; the sequential-MATCH_CLASS comparison stands only for the un-indexed (<4-clause)
majority. Key extraction itself would get cheaper under tuples (`cell[0]` vs the isinstance
chain + `term_field_names()` + tuple build + hash).

Context that bounds the win:
- **Goal calls never construct terms** (args flattened/positionally,
  `goal_trampoline.py:390`); construction wins apply to structure-heavy programs.
- **Most of the 857 ns is `PredicateMeta.__call__`** overhead; a generated-code fast path
  recovers ~10× with no repr change — **Phase 0**, worth doing regardless.
- **The C unifier win is the big one**: `do_unify` unifies tuples element-wise in C
  (`_variables.c:1114`), never consulting Python `__unify__` on them — compound unification
  stays entirely in C with zero `do_unify` changes. Slot-0 recursion handles every tag kind:
  str vs str (rich-compare, interned fast path), `tuple` vs `tuple`, Var (binds — the
  higher-order case), mismatches fail. One caveat: the cons rule, §5.

## 3. What the tag fixes (the five collision subsystems)

1. **First-arg indexing**: `_runtime_arg_key` (`arg_index.py:157-165`) currently drops tuples;
   slot 0 becomes the index key. Str functor keys are ideal dict keys. Unbound-Var/exotic tags
   index as `_INDEX_VAR` (correct fallback).
2. **Tabling keys**: `_normalize_for_key`'s `("__tuple__", ...)`/`(functor-name, ...)` scheme
   (`tabling.py:396-438` + C twin) — the representation is now *already* that key, str functor
   included. Non-hashable exotic tags need the existing unhashable fallback.
3. **Standard order**: one branch on slot 0 (`_helpers.py:349-401`) — but see §5, atom
   ordering changes observably.
4. **Structural inspection**: `functor/3`, `arg/3`, `=..`, `compound/1` uniform.
5. **Unification**: no C change; tags differ → same-length data tuple never captures a term.

## 3a. Phenomena A and B die outright

From `implementation_plans/dict-atom-keys-vs-predicates.md`:
- **Phenomenon A** (imported atom shadows same-named exported predicate → construction
  `TypeError`): atoms are no longer Python names in module namespaces; a bare atom is a string
  constant and cannot shadow anything. The un-export workaround convention retires.
- **Phenomenon B** (Python-built `DictTerm` atom keys embed as bare `Name`s in query
  templates → `NameError` in unrelated modules): that document already records "string keys
  compile as `Constant` nodes and are therefore always safe." All atom keys become that safe
  case. The import-into-every-queried-module convention retires.

## 3b. In-tree precedent: `Compound` IS this design, second-class

`Compound` (`clausal/terms.py:89` — a plain dataclass of `functor: str` + `args: tuple`) is
structurally the rev-3 cell `("foo", args...)` in a box, with rev-3 semantics on every axis:
string functor (global, spelling-keyed identity), open arity, no signature required (the OWA
construction path already exists). The engine already treats it as a parallel term
representation everywhere terms are consumed: `_arg_to_index_key` gives it the same
`(functor, arity)` bucket key as class instances, tabling's `_normalize_for_key` maps it to
`(functor,) + args` — literally this design's cell as its canonical key — standard order has
a branch for it, `head_match.py:579` emits a match pattern for it, and the ~114
`isinstance(..., Compound)` sites counted in §7 are a pre-existing dual-representation
funnel. What it lacks is exactly what this design is about: speed (dataclass construction is
in the ~86–100 ns class band, not ~20 ns) and first-class citizenship — verified 2026-09-03
that `Compound("foo", (1,))` does NOT unify with `foo(1)`, so it lives as a segregated world
(clause-head container, reflection/assertz currency). That segregation is a working miniature
of Phase 2's two-representations risk.

**Cheap experimental wedge (viable while the full plan stays parked):** reimplement
`Compound` itself as the tagged tuple (or a `tuple` subclass) behind its existing 114-site
funnel and let the C unifier's structural tuple branch handle it. Contained blast radius, no
language-property changes, real measurements — correspondingly limited payoff, since
`Compound` is not the hot representation. Worth doing before any un-parking decision: it
exercises the seam conversion, the C tuple path, and the funnel discipline on a small target.

## 3c. Optimisations the representation would unlock (recorded 2026-09-03)

Beyond the direct wins in §2, the tuple representation's immutability/hashability enables a
class of optimisations structurally unavailable to class terms (which are mutable — slot
assignment works today — and deliberately unhashable):

1. **Hash-consing / ground-term interning**: structurally-equal ground terms become
   pointer-equal → O(1) deep equality; the C unifier's existing identity-first check
   short-circuits deep unification; tabled answers dedup structurally. Converts the per-node
   memory disadvantage (48B tuple vs 32B slots instance) into a net win via sharing. Apply
   selectively (tabling/answer boundaries), not universally.
2. **Maximal structural sharing in copy_term/answer copying**: immutable ground subtrees are
   returned by pointer; only Var-containing paths rebuild — asymptotic (O(var-paths)) not
   constant-factor. Targets exactly the walker loops where Phase 0 measured 1.4–3.2×.
3. **Self-keying tabling**: the deref-walked answer IS its variant key; variant/subsumption
   checks accelerate via pointer equality.
4. **Cheap deep indexing**: `PyTuple_GET_ITEM` array reads make multi-level/joint index keys
   (`arg[0][0]`, `(a[0], b[0])`) practical in C.
5. **Columnar fact stores + zero-conversion JAX/torch seam**: tuples decompose into parallel
   columns for bulk joins; `("foo", x, y)` is already a JAX pytree — clausal_jax/clausal_torch
   would consume terms without conversion or registration.
6. **Marshal-grade serialization**: multiprocessing workers, on-disk answer caches, persistent
   fact stores — no custom reducers, no module-import requirement on the receiving side
   (dissolves the second-package-copy hazard for term data).
7. **Specialization without runtime class minting** (removes the class-identity-churn hazards
   in index bucketing).
8. **A C standard-order comparator** (today the one funnel accessor with no C twin, because
   getattr-chains in C are impractical; tuple recursion is straightforward).

**Keystone macro number (2026-09-03, Stage A of Phase 2 prep — recorded here because the
measurement reports live in gitignored SDD workspaces):** with the walker-heavy
`bench_struct_tabling` (compound cons-chain tabled answers; walker share 56% of profile),
Phase 0's fast path measures **B/A = 0.6509 (~1.54× end-to-end)**, adversarially confirmed by
a single-build gate-defeat experiment (classmethod→staticmethod on `cons._clausal_new`:
1.552×), mechanism ratio ≈2.0× after cProfile-inflation correction, load/compile 1.2% of the
timed window, `bench_fib` control at noise. Stage A also fixed two real bugs en route
(clpfd `_narrow` bignum saturation — direction-aware, soundness-reviewed; bench_tabling
redrive) and filed three engine todos (tabled-redo-resumes-generator, `_on_leader_stack`
linear scan, clpfd↔clpr float-boundary soundness).

Prerequisite for 1–3: the `Var.__hash__ = None` decision (§5-Hashability). Consequence for
Phase 2: the bridge should measure a tabling-heavy workload WITH selective interning enabled,
not just representation parity — that is where this class of wins concentrates. (Blocking
prerequisite from measurement work: the repo currently has NO working walker-heavy macro
workload — bench_tabling is broken two ways; see todo/bench-tabling-overflow-on-display-2026-09-03.md.)

## 4. Codegen notes

- Str-functor arms are plain literal patterns: `case ("point", a, b)` — no trap.
- The `tuple` tag must be a **dotted value pattern**: `case (builtins.tuple, a, b)` after
  `import builtins`. Never `__builtins__.tuple` (`__builtins__` is the module only in
  `__main__`; in imported modules it is a dict — verified). Never bare `tuple` (capture
  pattern). Rev-1 note: the earlier `()` tag had the worse trap that literal `()` is an
  empty-sequence pattern matching `[]` too.
- Hidden (`-hide`) symbols: the compiler substitutes the mangled/unforgeable form at every
  literal occurrence in the owning module; other modules cannot spell it.

## 5. Semantic changes to decide consciously (new in rev 3, mostly from str atoms)

- **Atom/string collapse.** `red` IS `"red"`: `atom/1` vs `string/1` merge (or `atom/1`
  becomes a lint-level notion), `{foo: 1}` and `{"foo": 1}` become the same dict, and the
  clausify-domains string→atom profile-key migration (R8 allowlist etc.) becomes semantically
  moot. Standard order changes observably (atoms currently sort via the compound branch;
  they'd sort as strings) — affects `sort/2`, `setof`, existing golden outputs.
- **The cons rule leaks into atoms** (verified, `_variables.c` "String ↔ List unification",
  ~:1166–1284): a str unifies element-wise with a same-length list of single-char strings, so
  `red` would unify with `['r','e','d']` under `unify()` — class atoms never did. Match
  literal patterns and `==` are unaffected (`"red" == ['r','e','d']` is False); the exposure
  is head-args compiled to wildcard+unify-guard and explicit `=`. Options: accept (document),
  or gate the cons rule to SegString/DCG contexts. Must be decided before Phase 2.
- **Predicate state relocation is now forced** (was an open question in rev 2): `_clauses`,
  `_dispatch_fn`, `_signature`, `_locked`, tabling homes move off the functor class into the
  `Database`, keyed `(module, name, arity)` — predicates stay module-local (Prolog/Ciao model)
  even though atoms go global.
- **Module inference for term-as-goal is lost.** Today `solve()`/`_term_to_goal`/goal
  iteration infer the owning module from the class's `__module__`. A str functor carries none:
  data terms used as goals need explicit module context — a module-qualified goal form (the
  `m:foo(X)` analog) or a resolution rule. Affects `call/N`, `solve(m.pred(...))` surfaces.
- **Hashability**: ground cells are hashable (str functors even more usefully so — compound
  dict keys). Class terms were deliberately unhashable (`predicate.py:622`). Leaning feature.
- **Diagnostics under OWA**: wrong-arity construction stops raising at build time; per-module
  flag, default checked, as before.
- **Embedding idioms** `for trail in term:` and `term.FieldName` (docs) exist only on class
  instances: seam-reconstruct vs deprecate — still open, §8.

## 5a. Seam design: TermProxy (resolves open question 1)

Instead of eagerly converting answer terms back to Python objects at the seam, hand back a
**lazy proxy over a snapshot**. Prototyped and verified 2026-09-03
(`implementation_plans/proto_termproxy.py`, runnable); every load-bearing mechanism demonstrated.

- **Snapshot at yield.** The engine deref-walks the answer (existing C `do_walk`) into a
  frozen tagged-tuple tree; the proxy wraps that. The one walk — needed for binding
  correctness anyway — is the only eager cost. This also fixes a *current* pain
  independently of the redesign: today callers must copy bindings out before resuming
  iteration because backtracking unbinds them; the snapshot is immune by construction, and
  the proxy is `__slots__`-frozen (mutation raises).
- **Existing consumer code works unchanged.** `PredicateMeta.__instancecheck__` accepts a
  proxy whose functor matches, so `isinstance(answer, m.booking)` is True — and since
  MATCH_CLASS is `isinstance()` + attribute reads, **`match`/`case` class patterns run
  unmodified over proxies** (demonstrated: `case booking(who=w, when=d)` matched and
  destructured a proxy). Keyword patterns never consult `__match_args__` on the subject;
  positional patterns read it from the pattern class, which still carries it. `.Field`
  access survives via `__getattr__` resolving field→position through the registered
  signature — nested compounds wrap on demand, scalars come back raw. So the documented
  attribute idiom needs NO class reconstruction at the seam.
- **Materialization is explicit** (`.construct()` / `.to_python()`): the only place
  Python-side validation can raise (e.g. an invalid date). The known risk — errors far from
  their Clausal cause — is mitigated three ways:
  1. **Provenance threading** (demonstrated): the proxy carries its origin (query goal,
     module); `repr` renders Clausal syntax via the reified renderer; `.construct()` raises
     `ClausalMaterializationError` naming the term, chained `from` the underlying error
     (`while materializing date(2026, 2, 31) … caused by ValueError('day is out of range
     for month')`). Origin must thread through nested `construct()` recursion (one-line fix
     over the prototype).
  2. **Eager mode as a debugging dial**: `solve(..., materialize='eager')` per call or per
     module turns far errors back into near ones.
  3. **The principled upstream fix is Ciao-style assertions** — an invalid date is
     constructible in Clausal at all only because OWA construction validates nothing;
     `:- pred`-style assertions checked under a `-check` mode catch it at the Clausal
     construction site, demoting the proxy's chained error to a shipping-mode backstop.
     Natural companion borrow to `-hide` (§1a).
- **Equality/hash**: structural over the snapshot (ground snapshots hash cleanly, consistent
  with the `Var.__hash__ = None` rule in §5-Hashability).
- **Boundaries**: the inner `_get_dispatch` protocol stays raw (frozen ~20-implementor
  contract untouched); proxies are the outer `solve()`/embedding surface only. Term-as-goal
  iteration moves to an explicit `proxy.solve()` or the module-qualified goal form (open
  question 4).

## 6. Hazards

1. **The seam widens**: tagging is mandatory both directions for tuple data; `_get_dispatch`
   implementors (frozen single-arg protocol, ~20 out-of-tree) see new shapes for compounds and
   tuples; `clausal-provenance/engine.py` (getattr + `cls(**{...})`, ~10 sites) is heaviest.
2. **Dict/set pairs** are plain 2-tuples today (`dict_set.py:69-80`) → become `(tuple, k, v)`.
   Migrate, don't exempt. 19 `.clausal` stdlib/corpus files to audit for destructuring.
3. **Off-by-one + C-twin lock-step**: `do_walk` rebuild (`_variables.c:1747`,
   `PyObject_Call(cls, kwargs)` → `PyTuple_New`), `_tabling_core.c`, `_constraints_dif.c`
   (17 term-aware sites), `_clpfd_core.c` (5). Drift is silent corruption, not errors.
4. **Source-level `(a, b)` overload** in `.clausal` (goal position = conjunction, arg position
   = data): compile-time only; emitter tags exactly the data occurrences.
5. **Atom-identity migration**: every test/golden output that relies on `m1.foo ≠ m2.foo`, on
   atom-vs-string dict-key distinctness (`docs/dicts_sets.md:154`), or on atom ordering flips
   behaviour. This is the migration with user-visible semantics, not just representation.

## 7. Refactoring effort — inventory and sizing

Site counts (grep, 2026-09-03, `clausal/` excl. tests unless noted):

| Coupled surface | Count |
|---|---|
| `is_term_instance` | 141 sites / 35 files |
| `term_field_names` | 142 sites / 32 files |
| `isinstance(..., Compound)` | 114 sites / 30 files |
| `PredicateMeta` references | 367 sites / 47 files |
| `type(...).__name__` (functor-by-classname) | 114 sites / 43 files |
| `_fields` | 279 sites / 32 files |
| Term-aware C | `_variables.c` (105), `_tabling_core.c` (17), `_constraints_dif.c` (17), `_clpfd_core.c` (5) |
| Tests touching these internals | 273 sites / 56 files (suite: 245 test files) |
| Out-of-tree `packages/` | 5 files (provenance ≫ scipy, sklearn, torch, sympy-tests) |
| Docs | `python_integration.md`, `keyword_preds.md`, `dicts_sets.md`, strict-atoms migration doc, dot-attribute design doc |

### Phases

- **Phase 0 — construction fast path: DONE 2026-09-03**, merged to clone main at 64bed74c
  (`_clausal_new` classmethod, saturated-emission gate, `_static_call_key` fix, interleaved
  benchmark): measured ~7.3× at arity 3 (~960→~130 ns), suite failure set unchanged; the
  benchmark's repo-root sys.path insert is flagged for canonical sync. Original scope:
  bypass `PredicateMeta.__call__` in
  generated code; add the missing term-construction benchmark. ~857→~90 ns. **1–2 days.**
  Sets the baseline that decides whether Phases 2+ pay.
  **Rebuilder adoption (feat/phase0-adoption, 2026-09-03):** all five term
  walkers now use the `_clausal_new` fast-path gate (`solve.py`
  `_deref_walk_py`, `inspection.py` `_copy_term_py`, and their three C twins —
  `_variables.c` `do_walk`/`c_copy_term`, `_tabling_core.c` `do_deref_walk`).
  Macro A/B on fib/nqueens/qsort/graph/naf_ite showed NO movement (B/A
  0.989–1.024, within noise) — a statement about that workload mix (term
  rebuilding isn't their bottleneck), not about the patch. Walker-level
  in-build A/B measured real speedups where rebuilding dominates:
  1.41×–3.19× (`c_copy_term` 3.19×, `_tabling_core` `do_deref_walk` 2.19×,
  the two Python walkers ~1.4–1.5×). Adoption caveats: `vary/3` must NEVER
  adopt the fast path — its unknown-key `TypeError` on the slow kwargs
  constructor is load-bearing for goal failure; `solve.py:323` is a
  legitimate future adoption candidate, not yet done.
- **Phase 1 — funnel refactor: DONE 2026-09-03**, merged to clone main at 909e9929
  (accessor gap-fill: `is_atom` adoption, `functor_arity`, `term_field_names_of_class`,
  `term_field_values`, `term_field_dict`; ~17 sites migrated across builtins/compiler/
  reflection/repl incl. a sanctioned repl.py dataclass-crash fix; funnel-bypass lint with
  path-verified allowlist; perf gate passed, no metric >3%). Three sites deliberately stay
  hand-rolled with proven cause: inspection.py functor/3, testing.py:2091, io.py listing/1
  head-format — each is a place `functor_arity`'s term-instance contract diverges (KWTerm/
  Compound shapes). CAVEAT for future callers: `Compound` IS a dataclass, so any
  `is_term_instance` guard admits it and `functor_arity` answers for the Compound, not the
  class — this trap produced the one Critical caught at final review. Original scope: route all representation probes
  through the `_helpers.py` accessors + `is_term_instance`/`term_field_names`; kill the direct
  `getattr`/`type().__name__` long tail. ~40 files. **1–2 weeks.**
- **Phase 2 — dual-representation bridge: DONE 2026-09-03**, merged to clone main at 88b53dff
  as an EXPERIMENT behind the `-tagged_terms` module flag (not a shippable feature): cell
  primitives (`clausal/logic/cells.py`, slot-0 deref'd, higher-order Var functors), funnel
  awareness, dual-site cell emission + sequence-pattern head dispatch (flag-off byte-identity
  golden-proven; cells ride the EXISTING C tuple branches — zero C changes needed, exactly as
  §2 predicted), 3-fixture parity corpus (answer-identical), ground-cell interning hook
  (default OFF).
  **RESULTS: cells beat even the fast-pathed class representation — B/A = 0.561 (~1.8×) on the
  walker-heavy macro (controller-reproduced 0.5375; ~2.7× composed vs pre-Phase-0). Interning
  as-implemented: negative on this fixture (0% hits — shape-driven: all-unique answers;
  O(depth³) cost — implementation-driven, NOT fundamental: a same-constraint id-consing
  prototype ran ~7× faster, one complexity order lower, unmeasured at the benchmark — the
  concrete starting point for any interning follow-up).**
  Known bridge limits (all documented+pinned): cell dispatch unindexed; flagged modules' own
  class constructors silently match nothing; cross-module compound exchange out of scope;
  cons-rule deferred to Phase 3 behind a guard test. Original estimate: ~1 week.
- **Phase 3 — compiler flip + atom pivot**: `terms_to_ast` emits cells; `head_match` emits
  literal/value-pattern dispatch; kwarg placement + partial backfill; per-module OWA flag;
  atoms lower to interned strs; `-hide` mangling; predicate state relocates to `Database`;
  specialization stops minting classes; delete `register_atom_identity` machinery;
  module-qualified goal form for term-as-goal. **2–3 weeks** (grew from rev 2: state
  relocation + atom lowering + goal-module surface are new here).
- **Phase 4 — pair migration + semantic audit**: `dict_set` pairs; tabling/order/indexing
  collapse onto slot 0; atom/string-collapse audit across tests, golden outputs, domains
  corpus (dict keys, sort order). **1–2 weeks** (grew: the audit is user-visible semantics).
- **Phase 5 — seam + ecosystem**: bidirectional converter; embedding-idiom decision shipped;
  5 `packages/` files; docs incl. strict-atoms migration note. **~1 week.**

**Total: ~6–9 engineer-weeks** (rev 2 said 5–8; the atom pivot forces predicate-state
relocation and a user-visible semantics audit, partially offset by deleting the atom-identity
machinery). Calibration unchanged: WFS work (far narrower) took 2 review rounds / 13 defects.
Risk concentrates in C-twin lock-step, the atom/string semantic collapse, and out-of-tree
frozen-protocol consumers. Phases 0–1 are safe standalone merges; **Phase 2's A/B bridge is
the go/no-go gate** — if end-to-end corpus numbers don't justify Phases 3–5, stop after
Phase 1 and keep the fast path.

## 8. Open design questions (park, don't block)

1. ~~`for trail in term:` / `term.FieldName` embedding idioms: seam-reconstruct vs
   deprecate?~~ **Resolved by §5a (TermProxy):** `.FieldName` survives unchanged via the
   proxy; term-as-goal iteration becomes `proxy.solve()` / qualified-goal form (Q4).
2. ~~Cons rule (`str` ~ char-list) applying to atoms~~ **RESOLVED (§1b): retired in Phase 3** — double-quotes lower to char lists; str=atom unifies by equality only.
3. ~~`-hide` renaming scheme~~ **RESOLVED (§1b):** mangled str with a reader-unwritable
   separator; uniqueness/analysis guarantee, not runtime security; structural at foreign
   boundaries.
4. Module-qualified goal syntax for data-terms-as-goals (the `m:foo(X)` analog): spelling and
   default-resolution rule when unqualified?
5. Does anything genuinely need per-module atom *identity* (not just hiding) that `-hide`
   cannot express? Scan the corpus before Phase 3 commits to global-by-default.
6. **Monotonicity vs Python objects as terms.** Python objects admitted as terms are mutable
   and dynamic — an object's observable value can change after it has been unified against,
   asserted, tabled, or indexed, which distorts the monotonicity/purity properties an ISO
   direction wants (the engine already half-acknowledges this: terms are deliberately
   unhashable because "mutable terms shouldn't be hashable", `predicate.py:622`; tabling and
   indexing keys assume value stability). Decide where the line goes: immutable term core
   (ISO-shaped) with Python objects quarantined at the seam as opaque leaves, vs today's
   "classes/objects are terms" stance.
7. **Measure the founding design point before deciding 6.** How often is the
   Python-class-shape-as-term surface actually used (constructing terms from Python, `.Field`
   attribute reads, term-as-goal iteration, isinstance-on-term-classes in user code)? Survey
   `packages/`, tests, the domains corpus. Known so far: `clausal-provenance` reconstructs
   via class+kwargs (~10 sites); `clausal-jax`/`clausal-torch` never touch term instances;
   scipy/sklearn consume deref'd scalars. No in-tree numbers for user-facing usage.
