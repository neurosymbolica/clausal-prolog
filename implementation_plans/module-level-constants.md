# Module-level constants: `_PI_` — declared, ground, folded at compile time

**Status:** IMPLEMENTED (2026-08-25, branch `feat/constants-and-singleton-lint`). The seven
open questions were resolved 2026-08-24 (record:
`todo/done/module-level-constants-open-questions.md`); decisions are folded into the text
below. See [Deviations from this plan](#deviations-from-this-plan-as-shipped) for the points
where the shipped behavior differs from the design text.

**Goal:** `area == _PI_ * R**2` instead of `(is_pi(PI), area == PI * R**2)` or
`R is ++math.pi`. Constants must be usable as ordinary term arguments (`foo(_MAX_RETRIES_, X)`),
not only inside arithmetic; definable locally to a module; and importable.

---

## The decision in one paragraph

A **new lexical class** carries constant-hood: exactly one leading underscore, exactly one
trailing underscore, at least one character between, interior starting with a non-digit
(`_PI_`, `_MAX_RETRIES_`, `_円周率_`; `_1_` is rejected — a constant named `1` invites
confusion with the literal). A constant whose interior ends in `_UNUSED` (`_X_UNUSED_`) is
legal but earns a lint — it collides visually with the unused-marker suffix.
Constants are **declared** in a module-level directive (working syntax: `-constants(_PI_ =
3.14159, _MAX_RETRIES_ = 3)`), their definitions must be **fully ground at compile time**
(compiler-enforced), and every reference is **folded to the ground value during AST
transformation** — generalizing the existing truth-value alias fold
(`clausal/templating/term_rewriting.py:350-410`), which already does exactly this for
`true`/`false`/`undefined`, reserved names and all. An undeclared `_X_`-shaped reference is a
compile-time error (mirroring strict atoms). Export by listing in `-module`, import via
`-import_from` / qualified `mod._PI_` — which work **unchanged**, because after the re-carve a
constant name is not a logic-variable name, so A10-F017
(`clausal/templating/term_rewriting.py:4260`), the direct-form import check
(`term_rewriting.py:4233`), and the dotted-chain rule (`docs/import.md:159`) all pass it by
construction. No prior namespace-hygiene decision is reversed.

## Why fold instead of bind

"Constants are pre-bound module-scoped Variables" is the right mental model and the wrong
implementation: a shared bound Variable needs exemptions from standardization-apart, the trail,
`copy_term`, and serialization — all to be observationally equivalent to substitution, since the
definition is ground at compile time anyway. Folding gets clause indexing on the literal value,
zero runtime deref cost, and no shared-mutable-term hazard. Cost (accepted): runtime
introspection, traces, and Prolog translation see `3.14159`, not `_PI_` — the C-macro debugging
complaint. Source-level tools (fmt is AST-based) keep the name.

## Rejected alternatives, and why

| Spelling | Killed by |
| --- | --- |
| **ALL_CAPS variables** (`PI`) — original proposal | Import/declaration **captures** existing clause variables, silently re-grounding joins (`foo(N), bar(N)` + constant `N`). Needs capture diagnostics plus reversal of *two* standing walls: A10-F017 rejects var-shaped import aliases, `docs/import.md:159` rejects var-shaped dotted-chain segments — the codebase independently walled off the variable namespace twice. Spends clause-local variable scope (a bare `MAX` in a body carries no syntactic evidence of binding vs. matching; logic programming has no assignment to disambiguate, unlike Python locals). And caseless scripts cannot write ALL_CAPS at all. |
| **`_lowercase` variables** (`_pi`) | Already a first-class variable style (`docs/syntax.md:45`), and the **only** variable spelling available to caseless scripts (`_is_logic_var_name` uses `str.isupper()`, which is `False` for caseless identifiers — so `_名前` is how Japanese variables must be written). Three readings for one spelling. |
| **TitleCase atoms** (`Pi`) | Capture-free and rides strict-atoms rails, but caseless scripts cannot write TitleCase either, and the name reads as an atom, not a value-holder. |
| **Qualified-only** (`mod.PI`) | No local constants; invites "why not a bare word?". (Qualified access is still *supported* — `mod._PI_` — just not the only form.) |
| **`++(constant)`** | Ties the surface language to the Python seam; `++` is meant as a hidden escape hatch; and gives modules no way to *define* constants, only reference Python ones. |
| **term_expansion** | Still needs an answer to "how is the term to be expanded spelled?" — the problem doesn't go away, and the mechanism is heavyweight for the job. |

Case conventions turned out to be Latin-script parochial: the declaration must carry the
semantics, so the spelling only needs to be *distinct*, not *cased*. `_X_` is the only candidate
that is case-free, bare-word, local-capable, greppable, and accepted by the existing import
machinery without new rules.

## Costs (surveyed 2026-08-24, worst first)

1. **The lexical re-carve touches five duplicated classifiers.** `_is_logic_var_name` copies:
   `templating/term_rewriting.py:417`, `templating/desugar.py:57`, `logic/goal_expansion.py:203`,
   `tools/clausal_to_prolog.py:311`, `logic/predicate.py:67` (the last explicitly "kept local so
   this module stays free of a templating import"). Any out-of-tree front end that mirrors the
   classifier must re-carve in lockstep. Miss one and tools disagree about lexical class (e.g.
   `clausal_to_prolog` emits `_PI_` as a Prolog variable while the engine folded a constant).
   **Ship with a conformance test** running a spelling corpus through all five copies and
   asserting identical answers.
2. **Typo softness.** Dropping one underscore (`_PI`, `PI_`) yields a *legal fresh variable* —
   the classic Prolog misspelling bug at exactly the use sites constants serve. Interior typos
   (`_Pl_`) stay in the constant class and hard-error as undeclared. The dropped-underscore forms
   are singletons, so the **singleton-warning lint is a load-bearing companion feature, not a
   nice-to-have — ship them together** (see below).
3. **Underscore overload.** Five readings: `_` anonymous, `_x` variable, `_x_UNUSED` suppressed
   singleton, `_X_` constant, `__x` excluded. Each decidable by a crisp rule; both Prolog and
   Python have precedent for heavier overloading; still the densest part of the design.
4. **Corpus breakage: 3 fixture files** (census over the 370 `.clausal` files outside worktree copies):
   `tests/fixtures/edcg_counter.clausal` (`_edcg_items_in_` etc. — hand-written EDCG hidden
   accumulators) and `_JOINT_COVERAGE_` in `tests/fixtures/callsite_joint_lib.clausal` +
   `tests/fixtures/secondary_dispatch_tro.clausal`. All breaks are loud (undeclared-constant
   error) and are simple renames. Compiler-minted implicit variables (`_read_0` —
   `term_rewriting.py:565`) do not collide.
5. **Prolog ingestion asymmetry.** In Prolog `_PI_` *is* a variable; `prolog_to_clausal` must
   rename `_X_`-shaped inbound variables or it mints accidental constant references. Outbound
   inlines ground values (Prolog has no constants).

## Companion feature: singleton warnings with `_UNUSED` suffix exemption

Warn on any named variable that occurs exactly once in a clause, **in both variable styles**,
unless the name carries the `_UNUSED` suffix (`_reason_UNUSED`, `REASON_UNUSED`); bare `_` stays
the zero-ceremony anonymous form. `_UNUSED` is the **single canonical spelling** — `_unused` is
not an exemption (one grep target, one rule; the mixed-case jar of `_reason_UNUSED` is accepted
as a feature on a deliberately-dead name). Inverse lint (as SWI does for `_X`): a
`_UNUSED`-marked variable occurring more than once warns "marked unused but used".

**Rollout (decided 2026-08-24): default-on** with a per-file opt-out directive, matching the
strict-atoms precedent of defaulting to the strict behavior. Corpus census at decision time:
439 singleton occurrences in 310 clauses across 102 of 370 `.clausal` files (314 ALL_CAPS
style, 125 underscore style), with the largest cluster in generated `clausal-scipy` bidir
fixtures (unused outputs of `svd(M, U, S, VH)`-style calls; the fixtures turned out to be
hand-written, not generated). The same series mechanically cleans the corpus with a
script-assisted per-occurrence rename (`_` or `_UNUSED`); warnings don't fail the suite, so
partial cleanup doesn't block landing.

**Implementation survey addendum (2026-08-24, pre-implementation):** the compiler itself mints
constant-shaped hidden variables — DCG `_dcg{N}_` (`term_rewriting.py:2370,2410`) and EDCG
`_edcg_{acc}_in_`/`_out_`/`_edcg_{pass}_` (`term_rewriting.py:2500-2507`); the
`edcg_counter.clausal` fixture hand-writes that minted convention. These mints lose the trailing
underscore before the re-carve lands. Full task breakdown:
`docs/superpowers/plans/2026-08-24-module-level-constants.md`.

Why a suffix, not the Prolog leading-underscore convention: (a) caseless scripts are *forced*
into leading-underscore variables by `isupper()`, so a case-based exemption is blind exactly for
those users (the Triska gotcha, structurally guaranteed here); (b) `_x` is a first-class style in
Clausal and deserves linting; (c) historically, Edinburgh `_foo` was a pure lexical class — the
"suppresses singleton warnings" reading is a later accretion, not something Clausal must import;
(d) the suffix says what it means in words, on the assumption (already made by predicate names)
that programmers read some English.

## Implementation sketch

- Re-carve the five classifier copies + conformance test; rename the three fixtures.
- Declaration parsing: `-constants(...)` directive alongside the atom-identity directives
  (`term_rewriting.py` directive handling, near `-import_from` at `:4199`). RHS grammar: ground
  literals, previously declared constants, arithmetic over them, and compile-time `++(expr)` —
  **evaluated** during directive processing (not lowered to a goal; cf. the `++escape`-as-a-goal
  always-succeeds trap), then groundness-checked. Decided 2026-08-24: `++` is allowed, with the
  reproducibility caveat documented rather than guaranteed — `_N_ = ++os.cpu_count()` is legal
  and machine-dependent. Groundness violation is a compile error.
- Folding: extend the single bare-`Name` resolution point where `_TRUTH_ALIASES` folds
  (`term_rewriting.py:360` comment names it), consulting the declared-constants table before
  variable minting. Reservation/collision behavior follows `_RESERVED_TRUTH_DECL_NAMES`
  (`term_rewriting.py:403`) and the `-overwrites` shadowing-warning machinery
  (`logic/compiler_v2.py:61`).
- Heads: constants fold uniformly everywhere, heads included — `area(_PI_, R)` matches only when
  the first argument equals the value, exactly as `area(3.14159, R)` would. No binding ambiguity
  exists in this design, so uniform substitution is the simple and correct rule. Decided
  2026-08-24: **no lint** on head occurrences — dispatch-on-named-value is a legitimate idiom,
  and the literal spelling warrants nothing today.
- Export/import: list in `-module` to export; `-import_from(m, [_PI_])` and qualified `m._PI_`
  pass existing checks unchanged. Import folds the *owner's* value at the importer's compile
  time.
- Prolog translators: outbound inline; inbound rename rule for `_X_`-shaped Prolog variables.
- Singleton lint ships in the same release (cost #2).

## Deviations from this plan, as shipped

The implementation (Tasks 1–8, `docs/superpowers/plans/2026-08-24-module-level-constants.md`)
matches this design in its lexical rule, folding mechanism, groundness gate, and default-on
singleton lint. A handful of points came out differently from the text above, all narrowing
rather than reversing a decision:

- **RHS grammar was v1 scalar-only; lifted 2026-08-25.** v1 shipped scalar literals,
  previously-declared constants, declared atoms, unary/binary arithmetic over those, and a
  `++(expr)` escape (evaluated at load time — `-constants(_N_ = ++os.cpu_count())` is legal and
  machine-dependent, exactly as the reproducibility caveat above anticipated). Structured
  literals (list/dict/set/tuple RHS, and functor calls) raised `SyntaxError` rather than being
  supported. This is now lifted: a structured RHS — nested arbitrarily, mixing any of the above
  at any depth — builds a real Clausal term, the same construction the identical literal would
  build in a clause body (`clausal/templating/term_rewriting.py`'s
  `EmbedTransformer._transform_constant_rhs`, extended rather than routed through the generic
  `TermTransformer`/`_make_term_transformer` — see that method's docstring for why: the generic
  term transformer is built for clause bodies, where a functor call or a set/tuple literal
  lowers to an *uninstantiated* `pythonic_ast` node that only becomes a real term when
  `compiler_v2` later compiles the STATIC clause tree into a predicate's bytecode; a
  `-constants` assignment has no such second pass — it runs once, directly, as an ordinary
  module-level statement — so the extension emits AST that constructs the real term on that one
  pass instead). A functor call requires the functor already declared *above* the `-constants`
  directive (`-module`/`-private`/`-dynamic`/an earlier clause, or an import) — a located
  `SyntaxError` otherwise. Structured values are recursively **frozen** at the groundness gate
  (`clausal.logic.constants.check_constant_ground` → `_freeze`): type-preserving frozen
  subclasses (`_FrozenList`/`_FrozenDict`/`_FrozenSet`) so `isinstance` checks and the C unify
  extension see no difference from a literal, only mutation is blocked (`TypeError`); a
  functor constant's own field values are the one deliberate exception, left unfrozen and
  shared. Discovered and fixed along the way, in `clausal/logic/compiler/terms_to_ast.py`
  (`term_to_ast_expr`, the pre-existing value→AST codegen a *compiled* clause body already used
  for any bound module global, not new to this feature): the `SetTerm` branch embedded every
  element as a bare `ast.Constant`, which `compile()` rejects for a non-literal element (an atom
  instance) — fixed to recurse per element, mirroring the `SetLiteral` branch beside it; and
  there was no branch at all for an already-materialized Python `tuple` (only for the
  uninstantiated `TupleLiteral` node) — added, mirroring the `TupleLiteral` branch. Both gaps
  were latent until a structured constant's value flowed through this codegen for the first
  time. See `docs/syntax.md`'s [Structured constants](../docs/syntax.md#structured-constants)
  section for the full reference, including the identity caveat: a constant's value is one
  frozen object as far as its own module-global storage and `module_constant/3` registration go
  (verified/pinned), but a *compiled clause body's* reference to it is constant-propagated at
  predicate-compile time into fresh construction code — so cross-invocation object identity
  (two different clauses' solutions holding the literal same object) does **not** hold; this is
  pre-existing `terms_to_ast` behavior for any known-bound global, not something `-constants`
  controls, and freezing makes it moot for correctness (every reconstruction is equally
  immutable).
- **`module_constant/3` reflection, added 2026-08-25.** The `-constants` lowering also registers
  each `(name, value)` pair on the declaring module (`clausal.logic.database.Module.constants`,
  populated via a second injected helper, `clausal.logic.constants.register_module_constant`,
  mirroring `$check_constant_ground`'s injection sites in `clausal/import_hook.py`). Only a
  module's own declarations are recorded — an imported constant is not re-registered on the
  importer, so `module_constant/3` never finds it there; query the declaring module instead (see
  `docs/import.md`). See `docs/builtins.md`'s `module_constant/3` entry for the full mode
  breakdown.
- **`-module`/`-private` reject constant names outright**, rather than "list in `-module` to
  export" (line 140 above). Constants are process-wide module globals as soon as they're
  declared with `-constants` — there is nothing an export listing could add — so
  `-module(m, [_PI_])` and `-private([_PI_])` are both a load-time `SyntaxError` pointing at
  `-constants` + `-import_from` instead. This is a correction of the plan text, caught during
  implementation, not an open design question.
- **Qualified bare-term access works, better than the plan's contingency.** The plan (Task 6)
  anticipated that `m._PI_` in term position (no `++`) might need a new `visit_Attribute` case,
  with a fallback of rejecting it with a `SyntaxError` pointing at `-import_from`/`++(mod._X_)`
  if that turned out to be contortive. In fact the existing `LoadAttr` lowering — the same
  mechanism that already supports qualified atom references like `currency.euro` in value
  position — covers constants for free. Both `m._PI_` as a bare term and `++(m._PI_)` work,
  test-pinned (`test_qualified_constant_access`).
- **Prolog translators refuse rather than inline.** `clausal_to_prolog` raises
  `NotImplementedError` on any file carrying `-constants`, rather than emitting the folded
  literal values (line 85, 143 above: "outbound inlines ground values"). In practice this
  distinction rarely bites: constant *references* inside ordinary clauses are already folded to
  literals by the time the translator sees them (folding happens in `EmbedTransformer`, before
  the Prolog-emission pass runs) — the only thing that cannot round-trip is the `-constants`
  directive statement itself, which has no Prolog equivalent to emit. `prolog_var_to_clausal`
  (inbound direction) does implement the rename rule as planned: a Prolog variable spelled
  `_PI_` stays a variable — trailing underscores are stripped — so it can never collide with the
  constant class.
- **Escape-validation scoping.** The load-time `SyntaxError` for an undeclared constant-shaped
  reference (line 25 above) also had to be taught, inside `++()`/f-string escapes, to skip a
  comprehension's or a walrus expression's own *Store*-context target — `sum(_ITEM_ for _ITEM_
  in range(N))` must not be misread as a free reference to an undeclared `_ITEM_` constant. This
  is a bug-fix refinement of "every reference is folded," not a new design point (cost #1's
  conformance-test spirit, applied to the new escape-validation code path).
- **Lambda-parameter counting, for the singleton lint's companion feature.** The singleton lint
  (cost #2) initially undercounted arrow-lambda parameters (`(X <- (X > 0))`-shaped code) because
  the shared occurrence-`Counter` never recorded the parameter's own binding site, only body
  uses — a parameter used exactly once in its body was indistinguishable from one used zero
  times. Fixed to count the binding site, which also closes a related blind spot noted at design
  time: a bound-but-never-used lambda parameter now correctly warns.
- **Census guard made repo-relative.** The five-classifier conformance guard (cost #1) needed a
  path-membership fix — the verbatim design used `.claude in p.parts` to skip non-repo
  directories, which is vacuous when the checkout itself lives under `.claude/worktrees/…` (as
  this one does); fixed to test membership relative to the repo root instead.
- **Survey addendum gains one more mint, and one inert case.** The "implementation survey
  addendum" above (compiler-minted constant-shaped hidden variables) missed `_dcg_pb_`
  (pushback-list state, alongside the `_dcg{N}_` and `_edcg_*_` mints already listed) — found and
  renamed during Task 1. Separately, `_clausal_star_query_` (the REPL's `*(goal)` sentinel name)
  is constant-shaped by the lexical rule but provably inert to the classifier: it is matched
  literally, as a string, at statement dispatch in `term_rewriting.py` *before* any name reaches
  `_is_constant_name` — so it never needed a rename and never collides with a real constant
  declaration of the same spelling.
