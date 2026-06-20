# DCG Audit & Improvement Scope

**Repo:** this clone, `clausal-dcg_audit`, at `910c1e7f` (string-audit + bytes parity merged).
**Audience:** a fresh instance tasked with fixing/extending Clausal's DCG support.
**Status:** audit complete; 4 required changes + a coverage/test program highlighted below.

> Why this exists: a structured-message NL renderer (Thai visa domain) wanted DCG surface
> realization. Probing the engine found DCGs *mostly* work but have concrete, untested gaps that
> block real use. This document is the empirical map + the fix scope, so the work isn't
> re-discovered from scratch.

---

## 0. How to reproduce (do this first)

```sh
cd /workspace/clausal-dcg_audit
python3 setup.py build_ext --inplace            # build C extensions (~aarch64)
python3 -m pytest tests/test_dcg.py -q           # baseline: 57 passed
PYTHONPATH=$PWD python3 implementation_plans/dcg_audit/probe_isolated.py   # the findings
```

The probe scripts (`probe_features.py`, `probe_isolated.py`, `probe_if_then_else.py`) are the
executable evidence for every claim here. Run them, don't trust prose.

The DCG implementation lives in two places:
- **Translation** (`>>` rule → ordinary clause): `clausal/templating/term_rewriting.py`
  — `_rewrite_dcg_body` / `_rewrite_dcg_sequence` (~L1525-1695), the `RShift` case in
  `visit_Expr` (~L2383-2452), and `_finalize_dcg_rule` (~L3348) which builds the head.
- **Runtime builtins** (`phrase/2`, `phrase/3`, `sequence//1`): `clausal/logic/builtins/dcg.py`.

---

## 1. Status matrix (verified on this engine)

| Feature | Status | Evidence |
|---|---|---|
| Terminals `>> (["a","b"])`, epsilon `[]` | ✅ works | probe_features #1 |
| Non-terminals, chaining, args | ✅ works | #2, #3 |
| **Atom-valued head args** `r(foo) >> ...` | ❌ **BROKEN** — compiled as a variable, matches anything | #4, probe_isolated B/C |
| Compound head args `r(ve(V)) >> ...` (1- & 2-arg) | ✅ works (was broken on older checkout — see §4) | #5, #6 |
| Body `is`-destructure `{M is ve(V)}` (1- & 2-arg) | ✅ works | #7, #8 |
| Single-element / unparenthesized body `>> ["a"]`, `>> p` | ✅ works (the clause-body paren trap does **not** apply to DCG bodies) | #9, #10 |
| Inline goals `{Goal}` | ✅ works | #11 |
| Disjunction `[..] or [..]` | ✅ works | #12 |
| **If-then-else with terminal/list branches** `If([x],[y],[z])` | ❌ **BROKEN** — `AttributeError: 'ListPatternUnify' object has no attribute 'l'` | probe_if_then_else |
| If-then-else with **nonterminal** branches `If(a,b,c)` | ✅ works | test_dcg `test_if_then_else_nonterminals` |
| Negation-as-failure `not [..]` | ✅ works | #14 |
| Pushback / look-ahead `(h,[pb]) >> (body)` | ✅ works | test_dcg `test_look_ahead`; (an early probe "failure" was a test-author bug: str `"a"` vs atom `a`) |
| `sequence//1` splice | ✅ works | #16 |
| List-pattern head `r([H,*T]) >> ...` | ✅ works | #17 |
| `phrase/2`, `phrase/3` residue, multi-solution backtracking | ✅ works | probe_isolated E, J |
| String **input** to `phrase` (strings-as-lists) | ✅ works | test_dcg `TestDCGStringInput` |
| **String terminals in a rule** `>> ("hello")` | ❌ **UNSUPPORTED** — `SyntaxError: Unsupported DCG body element: Constant` | probe_isolated F |
| **`call//1`** / variable nonterminal `r(_g) >> (_g)` | ❌ **UNSUPPORTED** — `NotImplementedError: goal shape not yet supported` | probe_isolated H |

---

## 2. Required changes (prioritized)

### R1 — Atom-valued head arguments match anything  *(HIGH — correctness; REGRESSION)*

> **CORRECTION (verified during fix).** The original root-cause pointer below was wrong on two
> counts, both confirmed empirically:
> 1. It is **not** a DCG-finalize/atoms-set bug, and the DCG head is **not** compiled as a
>    variable. Dumping the stored clauses shows the head correctly holds the atom
>    (`r(T=foo)`, `r(T=bar)`). The defect is downstream, in **runtime dispatch**.
> 2. **Plain `<-` clauses do NOT dispatch atoms correctly either** — `r(foo) <- ...` /
>    `r(bar) <- ...` (rule form) breaks identically. The probe's "baseline correct" (case A)
>    only held for the **fact** form (`r(foo, "F"),`), which works for an unrelated reason:
>    facts push the atom into a *body* `Unify` goal, so the head is a capturing variable and the
>    body unification does the discrimination.
>
> **Actual root cause.** `head_to_match_pattern` (`clausal/logic/compiler/head_match.py`) turns a
> clause head into a Python `match` pattern. An atom is a zero-arity `PredicateMeta` **class**
> (since the string→class atom migration). It matches none of the branches (Var, scalar, str,
> bytes, list, Compound, `Call(LoadName)`, `is_term_instance` — the last is False for a *class*),
> so it fell through to the `# Fallback: wildcard (accept anything)` arm → matched any argument.
> Integers worked because they hit the `MatchValue` branch.
>
> **Regression provenance.** Introduced by commit **`92ce2636`** ("refactor: declared atoms as
> zero-field PredicateMeta classes", 2026-03-26). Before it, atoms were plain **strings** and were
> value-matched via the `str` branch. That commit updated `term_to_ast_expr` and the index
> `head_key` for the new class representation but **missed `head_to_match_pattern`** and the arg
> indexer. This is exactly the §4 "cross-engine divergence": `thai_imm_rules` was pre-refactor
> (atoms = strings → worked); this checkout is post-refactor (broken). Scope is **all predicates**
> with atom head args (top-level *and* nested in a compound), not just DCG.
>
> **Fix applied.** Added a `PredicateMeta`-atom branch to `head_to_match_pattern` (wildcard
> capture + `unify(cap, atom, trail)` guard, mirroring the str/bytes guards) and emitted the guard
> in `compile_head_to_match_case`. Also restored atom indexability in `arg_index.py`
> (`_arg_to_index_key` / `_runtime_arg_key` key an atom as `(name, 0)`), which the same migration
> had dropped (forcing a linear scan). Pinned by `TestAtomHeadDispatch` (5 tests, incl. nested-
> compound and a ≥4-clause indexed case) in `tests/test_dcg.py`.

**Symptom.** Two DCG clauses `r(foo) >> (["F"])` and `r(bar) >> (["B"])` both fire for *either*
input — the head atom matches anything. A `r(foo)` clause also matches a compound input
`r(ve(foo))`. So any grammar that dispatches on an atom argument silently returns wrong solutions.

**Repro.** `probe_isolated.py` cases B/C (and case A *rule* form, not the fact form).

---

### R2 — If-then-else with terminal/list branches crashes  *(MEDIUM-HIGH)*

**Symptom.** `g >> (If([done], [done], [empty]))` raises
`AttributeError: 'ListPatternUnify' object has no attribute 'l'` at load. `If(a, b, c)` with
**nonterminal** branches works; the breakage is specific to **terminal (list) branches**.

**Repro.** `probe_if_then_else.py` (nonterminal → OK; terminal → ERR).

**Root-cause pointer.** `_rewrite_dcg_body`, the `If` case (term_rewriting.py ~L1571): it
recursively rewrites cond/then/else, and a list branch `[done]` becomes a terminal unification
`s_in is [done, *mid]`. The resulting `ListPatternUnify` node is then mishandled downstream
(something accesses `.l` on it). Either the terminal-in-If rewrite produces a malformed node, or
the If lowering doesn't expect a `ListPatternUnify` child.

**Fix direction.** Make the If-branch rewrite handle terminal branches identically to how a
top-level terminal is handled (it works there). Add a regression test mirroring the existing
nonterminal If test but with list branches.

---

### R3 — String terminals in rule bodies unsupported  *(MEDIUM)*

**Symptom.** `hi >> ("hello")` → `SyntaxError: Unsupported DCG body element: Constant(value='hello')`.
Only the list form `>> (["h","i"])` is accepted. This is inconsistent with the engine's
"strings-as-lists" rule (string *input* to `phrase` works; string *terminals* in rules don't).

**Repro.** `probe_isolated.py` case F.

**Root-cause pointer.** `_rewrite_dcg_body` matches `List(...)` terminals but has no case for a
`Constant(str)` (or `bytes`) terminal, so it falls through to the `raise SyntaxError`. Standard
Prolog treats `"abc"` as a terminal sequence; given strings-as-lists, a `str`/`bytes` constant
terminal should expand to `s_in is <string> ++ s_out` (reuse the `sequence//1` / SegString
machinery already in `dcg.py`).

**Fix direction.** Add a `Constant(value=str|bytes)` case to `_rewrite_dcg_body` that threads the
string/bytes as a terminal sequence (mirror the `List` arm, but splice a str/bytes rather than
list elements). Tests: `>> ("hi")` parses both string and list inputs.

---

### R4 — `call//1` / variable nonterminal body unsupported  *(MEDIUM)*

**Symptom.** `run(_g) >> (_g)` (a body that is a bare variable, i.e. the standard `call//1`
meta-nonterminal) → `NotImplementedError: terms_to_goalop: goal shape not yet supported (Call)`.
This is the DCG analogue of "a bare variable cannot be a clause body" (syntax trap #6) — the
feature you flagged as related to the predicate-clause-body restriction. It blocks
higher-order grammars (passing a nonterminal as an argument and invoking it).

**Repro.** `probe_isolated.py` case H.

**Root-cause pointer.** `_rewrite_dcg_body` has no case for a bare `Name` bound to a variable used
as a body (it treats `Name` as a 0-arg nonterminal *call* `name(s_in, s_out)`; when `name` is a
logic variable that lowers to calling an AttVar). Standard DCG defines `call(G, S0, S)` /
`phrase(G, S0, S)` for this. 

**Fix direction.** When a DCG body element is a variable, emit `phrase(Var, s_in, s_out)` (or a
`call//1` builtin) rather than a direct call. Decide whether to expose `call//1` as a builtin in
`dcg.py` and route variable bodies through it. Tests: `run(_g) >> (_g)` then
`phrase(run(some_nonterminal), Input)`.

---

## 3. Gaps vs standard DCG (consider, lower priority)

- **`call//N`** (N>1) — invoke a closure with extra args. R4 covers `call//1`.
- **`\+//1` as an operator** — NAF works via `not`; confirm parity with a `\+` form if desired.
- **Module-qualified nonterminals** in bodies (`mod:nt`) — untested here.
- **Char-type / pushback of computed tokens** — pushback works; computed pushback untested.
- **Error quality** — `SyntaxError: Unsupported DCG body element: <dump>` is opaque; improve to
  name the construct and point at the source line.

---

## 4. Cross-engine divergence (motivates a shared regression suite)

The **same DCG grammar behaves differently across Clausal checkouts**:
- On `clausal-thai_imm_rules` (older): compound head args were **broken** (trap #10), atom heads
  worked.
- On this checkout (`910c1e7f`): compound head args **work**, atom heads are **broken** (R1).

So head-matching semantics in the DCG path have changed under feature branches with **no test
pinning either behavior** (the 57 DCG tests cover neither atom-head dispatch nor compound-head
dispatch directly). **Recommend:** land the R1-R4 regression tests as the canonical DCG dispatch
contract so this can't silently invert again. This is as important as the fixes themselves.

---

## 5. Suggested work plan

1. **Lock the contract first.** Add failing tests for R1-R4 (atom-head dispatch, terminal-branch
   If, string terminals, `call//1`) — they encode the intended semantics. (Red.)
2. **R1 (atom-head).** Highest value, smallest blast radius if it's an atoms-set bug. Fixing it
   likely also clarifies the head-transform path for R2-R4.
3. **R2 (If terminal branches)** — contained rewrite fix.
4. **R3 (string terminals)** — additive `_rewrite_dcg_body` case, reuse SegString.
5. **R4 (call//1)** — variable-body lowering; may touch `dcg.py` (new builtin).
6. **Regression-pin** all of the above; re-run `tests/test_dcg.py` (57) green throughout.

Each step: write the test, make it pass, keep the existing 57 green. The probe scripts in this
directory are the scratch harness; promote their cases into `tests/test_dcg.py`.

---

## 6. Out of scope / non-issues (verified, don't re-investigate)

- Compound head matching — **works here** (don't "fix" it; pin it with a test).
- Body `is`-destructure (any arity) — works.
- Single-element / unparenthesized DCG bodies — work (the `<-` clause-body paren trap does not
  apply to `>>` bodies).
- Pushback / look-ahead — works (early probe "failure" was a str-vs-atom test bug;
  `probe_isolated.py` case I still shows `no-parse` for that reason — not a real defect).
- `phrase/2`, `phrase/3`, string input, state threading, recursion — all covered & green.

---

## 7. Resolution (implemented)

All four required changes are fixed, TDD'd, and regression-pinned. Full main suite: **6369
passed, 0 failed** (run in chunks; the whole suite at once OOMs the sandbox).

| # | Fix | File(s) touched | Tests |
|---|---|---|---|
| **R1** | Atom (`PredicateMeta`) head args were wildcard-matched (regression from `92ce2636`) — added an atom capture+unify guard; restored atom indexing | `compiler/head_match.py`, `compiler/arg_index.py` | `TestAtomHeadDispatch` (5) |
| **R2** | Star-list unify If-condition converts to `ListPatternUnify` but was tagged `reified_test="unify"`, crashing the reified lowering — gate reifiability so it uses the general ITE path | `compiler/terms_to_goalop.py` | `TestIfThenElse::test_if_then_else_terminal_*` (2) |
| **R3** | `str`/`bytes` constant terminals in a DCG body were unsupported — added a `Constant(str\|bytes)` case routed through the `sequence//1` builtin | `templating/term_rewriting.py` | `TestStringTerminals` (4) |
| **R4** | A bare logic-variable body (`call//1`) lowered to a Call on a Var — route variable bodies through `phrase/3` | `templating/term_rewriting.py` | `TestCallNonterminal` (1) |

Total: 12 new tests; `tests/test_dcg.py` now **69 passed** (was 57). R1 is the headline finding —
it is a **core dispatch regression affecting every predicate with an atom head argument**, far
wider than DCG, and the audit's original root-cause pointer was incorrect (see §2 R1 correction).
