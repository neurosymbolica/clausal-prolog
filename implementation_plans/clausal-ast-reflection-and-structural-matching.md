# Feature plan: AST reflection → Clausal compound terms + structural matching in Clausal

**Status:** phases 1–3 landed (2026-07-01) — see "Implementation notes" at the end.
Phase 4 (round-trip/expansion) deferred; phase 5 (verifier migration) lives in `clausify`.
**Origin:** surfaced while building the `clausify` adversarial verifier, which needs to
statically analyse `.clausal` rulebases (call-graph, arity, `++`-escape detection). Doing that
with regexes is wrong (Clausal is not a regular language); doing it with Python's `ast` works but
means *analysing Clausal in Python*. The right tool for matching constructions in Clausal code is
**Clausal itself** — this feature makes that possible and is a strong core capability in its own
right (macro-writing, linters, refactoring tools, term-rewriting, teaching).

---

## The idea in one paragraph

`.clausal` source is already parsed by Python's `ast.parse` (Clausal uses Python surface syntax so
that Python can be embedded). Expose a step that **reifies that AST into ordinary Clausal compound
terms** — a homoiconic tree the language can inspect — and then let users **match constructions by
writing the pattern in the head of a predicate (or a DCG rule)** and applying it to the nodes where
the construction can appear. In short: give Clausal the ability to pattern-match Clausal (and the
embedded Python) as data. This is the Lisp/Prolog `read_term`/`=..`/`term_expansion` capability,
specialised to Clausal's Python-AST substrate.

## Why it is a great core feature (not just a verifier need)

- **Metacircular tooling.** Linters, style-checkers, complexity metrics, dead-clause detection,
  call-graph extraction, and refactorings can all be written *in Clausal*, matching goal/head/clause
  patterns declaratively instead of walking a Python AST imperatively.
- **Macros / term-expansion authored in Clausal.** `term_expansion`/`goal_expansion` currently live
  in the Python compiler pipeline (`clausal/logic/term_expansion.py`, `goal_expansion.py`). A
  reified-term interface lets expansions be *expressed and tested* as Clausal rules over reified
  nodes.
- **DCG-based construction matching.** Because a clause body is a sequence of goals, a DCG is a
  natural way to match/parse goal sequences (e.g. "a conjunction containing a `once/1` wrapping a
  membership check"). This is the user's key insight: match at the *right node positions*, not over
  flat text.
- **Teaching / introspection.** `?- clause_ast(deadline/4, AST)` returning a walkable term is a
  strong REPL and docs capability.

## What exists to build on (surveyed 2026-07-01)

- `clausal/import_hook.py::_parse_clausal_source` → `ast.parse(source)` then an `EmbedTransformer`.
  The AST is already in hand at compile time; `_last_transformer` is retained on the loader.
- `clausal/logic/compiler_v2.py::compile_module` turns parsed items into a logic module; it already
  classifies top-level items (`DirectiveItem`, `ImportFromItem`, `ImportModuleItem`, predicate
  clauses).
- `clausal/terms.py::Compound`, `KWTerm`, `Quantity`; `clausal/logic/database.py::{Clause, Module,
  head_key, _flatten_body}` — the target term vocabulary and existing head/body helpers.
- `clausal/tools/prolog_ast.py` + `prolog_parser.py` exist but are the **standard-Prolog** reader
  (capitalised = variable); they do NOT parse `.clausal` surface syntax. This feature targets the
  Python-AST substrate, not the Prolog reader.
- `clausal/pythonic_ast/nodes.py` — the **middle layer** between Python `ast` and the reified
  vocabulary. `EmbedTransformer`/`TermTransformer` lower Python `ast` into these simplified node
  classes (`Add`, `Mult`, `Pow`, `BinOp`, `UnaryOp`, `Call`, `LoadName`, `Unify`, `And`, `Or`,
  `ArithEq`, …). **As of `4944fe5f` (2026-07-01), `BinOp` and `UnaryOp` carry a structural
  `__unify__`** (mirroring `Compound.__unify__`; same operator class required, operands unified
  pairwise, `position` ignored). Because `CmpOp` (`ArithEq`, `Lt`, `Unify`, `In`, …) and `BoolOp`
  (`And`, `Or`) subclass `BinOp`, **every binary/unary operator node — arithmetic, comparison,
  boolean, and unary (incl. the `++` escape's nested `UAdd` and `not`'s `UnaryOp`) — is now a
  first-class unifiable term**. `symbolic_diff.clausal` exercises the end-to-end case this feature
  envisions: `Diff(A + B, X, DA + DB)` matches an operator term in a *head* and unifies it at
  runtime. So the operator/unary subset of "structural matching in Clausal" already works on the raw
  middle-layer nodes — no reification needed for it. (Control-shaped nodes — clause `<-` as
  `Compare(..Lt..)`, goals as `Call`, directives as leading `-` — are still awkward to match raw and
  are what the reified vocabulary below exists to normalize.)

## The AST → Clausal-term mapping (concrete, from real `.clausal`)

Reify each Python AST node as a Clausal compound. Proposed encoding (illustrative functor names):

| `.clausal` construct | Python AST | Reified Clausal term |
|---|---|---|
| clause `H <- (G1, G2)` | `Compare(left=H, ops=[Lt], comparators=[UnaryOp(USub, Tuple([G1,G2]))])` | `clause(HEAD, [GOAL1, GOAL2])` |
| fact `h(1)` | `Call(Name('h'), [Constant(1)])` | `clause(pred(h, [int(1)]), [])` |
| directive `-import_from(m,[A,B])` | `UnaryOp(USub, Call(Name('import_from'), …))` | `directive(import_from, [module(m), [name(a), name(b)]])` |
| goal `deadline(N,P,T,D)` | `Call(Name('deadline'), [Name…])` | `pred(deadline, [var('N'), var('P'), var('T'), var('D')])` |
| negation `not in_(X,L)` | `UnaryOp(Not, Call('in_', …))` | `not(pred(in_, [var('X'), var('L')]))` |
| meta-call `once(G)` | `Call(Name('once'), [G])` | `pred(once, [GOAL])` (arg is itself a reified goal) |
| operator goal `X is 1 + 2` | `Compare(Name('X'), [Is], [BinOp(…)])` | `op(is, [var('X'), add(int(1), int(2))])` |
| escape `++max(L)` | `UnaryOp(UAdd, UnaryOp(UAdd, Call('max', [Name('L')])))` | `escape(pred(max, [var('L')]))` |
| variable `PERIOD_DAYS` / `_X` | `Name(id, ctx=Load)` (ALL_CAPS or leading `_`) | `var('PERIOD_DAYS')` |
| atom / string | `Name`(lowercase) / `Constant(str)` | `atom(a)` / `str("…")` |

Variable vs atom follows Clausal's convention (ALL_CAPS or leading underscore ⇒ variable),
independent of Python's own capitalised-name meaning.

## Public API (proposed)

Python-facing (compile-time reflection):
- `reify_ast(node) -> Compound` — one AST node → a reified Clausal term.
- `reify_source(text) -> list[Compound]` — parse `.clausal` text (no directive execution, no kit
  import) and reify every top-level item. Pure and dependency-light — the property the verifier
  needs (analyse without loading the engine or the kit).

Clausal-facing (the metacircular surface):
- `reified_clause(SOURCE_TERM, CLAUSE)` / `reified_item(SOURCE, ITEM)` — enumerate reified items.
- Builtins to destructure: `clause_head(CLAUSE, HEAD)`, `clause_body(CLAUSE, GOALS)`,
  `goal_functor(GOAL, NAME, ARITY)`, `is_var(NODE)`, `is_escape(NODE, PAYLOAD)`.
- A DCG entry point so users can write grammar rules over a body's goal list.

Then a lint/matcher is just Clausal:
```
# "a called predicate that is neither defined nor imported" — a call-graph lint, in Clausal
undefined_call(SOURCE, NAME, ARITY) <- (
    reified_clause(SOURCE, CLAUSE),
    clause_body(CLAUSE, GOALS),
    member(GOAL, GOALS),
    goal_functor(GOAL, NAME, ARITY),
    not defined_in(SOURCE, NAME, ARITY),
    not imported(SOURCE, NAME, ARITY)
)
```

## Phasing

1. **`reify_ast` / `reify_source` (Python).** The pure AST → `Compound` mapping above + tests over
   real kit files (`kit/*.clausal`). No engine load, no kit import. This alone unblocks the verifier
   (it can call `reify_source` instead of hand-walking `ast`).
2. **Clausal destructuring builtins.** `reified_clause/2`, `clause_head/2`, `clause_body/2`,
   `goal_functor/3`, `is_var/1`, `is_escape/2` — so matchers can be written in Clausal.
   *Scope narrowed by `4944fe5f`:* operator/unary subtrees (`BinOp`/`UnaryOp` — arithmetic,
   comparison, boolean, `++` escape, `not`) are already first-class unifiable terms, so this phase
   need not reify them into a fresh `add/2`-style vocabulary — they can be matched directly, and
   `is_escape/2` can pattern-match the raw nested-`UAdd` `UnaryOp` shape. Concentrate the reification
   effort on the **control shapes** the raw layer can't ergonomically express: clause `<-`
   (`Compare(..Lt..)`) → `clause(HEAD, GOALS)`, goal `Call` → `pred(NAME, ARGS)`, and directive
   leading `-`. Decide explicitly whether the stable Clausal-facing vocabulary should *still* wrap
   operator nodes (for decoupling from internal `pythonic_ast` class names) or expose them raw (less
   code, but couples matchers to `Add`/`Mult`/… names) — a documented trade-off, not an oversight.
3. **DCG support over goal lists.** Grammar rules for matching goal sequences/constructions.
4. **Round-trip / expansion.** `reflect_term(term) -> AST -> code` so term-expansions authored over
   reified terms can be materialised (optional; enables macros-in-Clausal).
5. **Port a real tool.** Re-express the verifier's call-graph / arity / `++`-escape attacks as
   Clausal matchers over reified terms — the dogfood milestone.

## Non-goals

- Not replacing the standard-Prolog reader (`prolog_parser`); this targets the Python-AST substrate.
- Not requiring the engine or the kit to be importable for `reify_source` (phase 1 must stay pure).
- Not a full macro system in phase 1 — reflection first, expansion later.

## Consumer note

`clausify`'s adversarial verifier will ship its Phase-1 static attacks on Python `ast` now, behind a
stable `Attack.run()` interface, and **migrate them to this feature** (phases 1→2→5 above) once it
lands — no change to the verifier's gate, registry, or report. That migration is the first external
validation of this feature.

---

## Implementation notes (phases 1–3, landed 2026-07-01)

- **Approach:** instead of exec'ing the transformed module, `reify_source` statically evaluates the
  `$define_predicate(Predicate(...))` constructor expressions that `EmbedTransformer` emits — a
  closed vocabulary (functor calls with keyword fields, walrus-bound `Var()`s, simple_ast node
  constructors, `PyThunk`/`FStringThunk` lambdas). Pure: no directive execution, no embedded-Python
  or escape evaluation. `EmbedTransformer` stays the single source of truth for surface syntax.
- **Files:** `clausal/reflection.py` (pure layer: `reify_source`/`reify_file`/`reify_ast` +
  vocabulary), `clausal/modules/reflection.py` (Clausal-facing builtins), `docs/reflection.md`,
  `tests/test_reflection.py` (39 tests), `tests/test_reflection_builtins.py` (9 tests, incl. the
  `undefined_call` lint and a DCG construction matcher). `reflection` registered in
  `_IMPORT_ALIASES` (term_rewriting.py).
- **Vocabulary deviations from the sketch above** (documented in `docs/reflection.md`):
  `pred` → `Goal(NAME, ARGS, KWARGS)`; functor/atom names are **strings**, not atoms; Python
  literals stay **raw** (no `int(1)`/`str(...)` wrapping); variables/atoms wrap as
  `Variable('X')`/`Atom('a')`; `clause` → `Clause(HEAD, GOALS, POSITION)` (trailing `position`
  fields wildcard naturally because `__call__` fills missing fields with fresh vars). `Goal`
  carries no position so whole-goal `==`/`SetOf` dedup stays structural.
- **The phase-2 trade-off** (wrap operators vs expose raw) was decided **raw**: operator/unary
  nodes pass through with reified operands, matched via their `__unify__` from `4944fe5f`.
  Control shapes got the normalized vocabulary (`Clause`, `Goal`, `Escape`, `FormatString`,
  `IfThenElse`, `ModuleDirective`, `PythonCode`); conjunctions normalize to Python lists.
- **Phase 3 was free:** bodies are Python lists, so `phrase/2` matches goal sequences with no new
  code — a grammar-rule matcher test passes against reified bodies directly.

### Natural-syntax clause patterns (IMPLEMENTED 2026-07-02 — option 1 below)

Landed as `_expand_arrow_patterns` in `clausal/logic/goal_expansion.py` (13 tests in
`tests/test_reflection_sugar.py`, docs in `docs/reflection.md` §"Arrow Patterns"). As designed:
fires only in reflection-builtin argument positions (identity-checked through the module's own
binding, dotted-remap aware), pattern vars stay clause vars (capture + sharing), `<- True` = fact,
`<- GOALS` captures the body list, goal lists match exactly, operators stay raw both sides.
Variable-headed `HEAD <- GOALS` remains lambda syntax — full destructuring uses `Clause(HEAD,
GOALS)`. Incidental fix: `_expand_goal` now recurses into `TupleLiteral` conjunctions (previously
goal expansion never fired inside multi-goal bodies — latent regex auto-binding gap). Original
design notes kept below for the record.

### Original design notes (2026-07-01)

`(HEAD <- BODY)` **already parses as an expression** in argument position: `TermTransformer`
detects the arrow and builds a runtime `Predicate(head=Call(...), body=TupleLiteral(...))` node
with the surrounding clause's real Vars shared inside (the write-side currency — what `assertz`
consumes). It does NOT unify with the reified vocabulary (different classes at every level:
`Predicate`≠`Clause`, `Call`≠`Goal`, `TupleLiteral`≠list, real Vars≠ground `Variable` terms), so
`ReifiedClause(SRC, MyPred(A, B) <- (Goalx(A), Goaly(B)))` does not match today. Two closures
considered:

1. **Goal-expansion sugar** (preferred): in reflection-builtin argument positions, rewrite the
   `Predicate`-constructor expression into the equivalent vocabulary pattern at compile time
   (precedent: regex auto-binding in `goal_expansion.py`; the AST→vocabulary mapping is
   `reflection._ClauseReifier`). Pattern vars stay the matcher's clause vars → unification against
   ground `Variable(...)` terms gives capture + sharing semantics for free. No new keyword — the
   arrow syntax is already reserved and parsed, so `qc/1` is unnecessary; `qc/n` (named
   substitutions) doubly so.
2. **Unify the currencies**: reify to raw `Predicate`/`Call` nodes and add `__unify__` to them
   (extending `4944fe5f`). More principled (one clause-term shape language-wide) but reworks the
   shipped vocabulary, costs the list-body/DCG property, and touches the assertz write-side shape.

**Deferred** until the clausify verifier migration (phase 5) provides a real matcher corpus — that
usage should decide (a) whether the sugar pays for itself, and (b) whether pattern bodies should
match exactly or as a subsequence.
