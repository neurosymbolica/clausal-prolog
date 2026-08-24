# Module-level constants: `_PI_` — declared, ground, folded at compile time

**Status:** DESIGN DECIDED (2026-08-24). Not implemented. The seven open questions were
resolved the same day (record: `todo/done/module-level-constants-open-questions.md`);
decisions are folded into the text below.

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
fixtures (unused outputs of `svd(M, U, S, VH)`-style calls). The same series fixes the scipy
fixture *generator* (collapsing that cluster at the source) and mechanically cleans the rest
(`_` or `_UNUSED`); warnings don't fail the suite, so partial cleanup doesn't block landing.

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
