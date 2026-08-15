# unnecessary_lambda (eta-reduction) — implementation report

Branch `rule/unnecessary-lambda`, based on ad1a9858.

## Spike findings

### (a) Engine equivalence — VERDICT: EQUIVALENT, proceed

A bare predicate reference is accepted wherever a forwarding lambda is, with
identical solutions. Verified by loading `.clausal` modules through
`_load_module` and enumerating `call(...)` solutions for both forms:

| shape | lambda form | bare form | result |
|---|---|---|---|
| maplist/2 | `maplist((X <- positive(X)), L)` | `maplist(positive, L)` | identical |
| maplist/3 | `maplist(((X, Y) <- add_one(X, Y)), L, R)` | `maplist(add_one, L, R)` | identical (`[2,3,4]`) |
| foldl/4 | `foldl(((X, A, O) <- add_step(X, A, O)), L, 0, R)` | `foldl(add_step, L, 0, R)` | identical (`6`) |
| include/3 | `include((X <- big(X)), L, R)` | `include(big, L, R)` | identical |
| user HO via call_goal | `Twice(((A, B) <- add_one(A, B)), 5, Z)` | `Twice(add_one, 5, Z)` | identical (`7`) |
| dotted callee | `maplist(((X, Y) <- etahelper.bump(X, Y)), ...)` | `maplist(etahelper.bump, ...)` | identical |
| zero-arg | `call_goal((() <- pings()))` | `call_goal(pings)` | identical |
| builtin callee | `maplist((X <- ground(X)), L)` | `maplist(ground, L)` | identical |
| param shadowing | `X is 99, maplist((X <- big(X)), L)` | `X is 99, maplist(big, L)` | identical |

Shadowing is documented (docs/lambdas.md "Parameter shadowing") and the engine
agrees: a param named like an enclosing variable shadows it, and the outer
variable is not bound by calling the lambda. The strongest of these are pinned
as tests in `tests/rewrite/test_reflection_contract.py`.

`fold/3` from the task statement is not an engine builtin (`foldl/4` is); the
rule is callee-name-agnostic, so this changes nothing.

### (b) Reified forms

The lambda `((X, Y) <- add_one(X, Y))` as a goal argument reifies as a raw
node (via `reify_ast` with `source=`):

```
Lambda(params=Params(params=[PosOrKwParam(name='X', ...), PosOrKwParam(name='Y', ...)]),
       body=Goal(name='add_one', args=[Atom(name='X'), Atom(name='Y')], kwargs=[]))
```

The bare reference `add_one` in the same position reifies as `Atom('add_one')`
(dotted: `Atom('mod.pred')`). Decisive detail: **param references in the body
reify as `Atom(name)`, captured enclosing variables as `Variable(name)`** —
even in the shadowing collision (reification agrees with the engine). So the
"body args are exactly the params" match is simultaneously the forwarding
check and the closure-capture fence. Further shapes that fall out of the
match for free:

- a call through a variable, `(X <- F(X))`, reifies its body as an `Escape`,
  never a `Goal`;
- a lowercase-headed `(foo <- p(foo))` term reifies as a `Predicate` node,
  never a `Lambda`;
- a multi-goal body reifies as a tuple, an operator body as a raw operator
  node — neither is a `Goal`.

## Design decisions

**Pairing rule (driver).** When the rule output has the SAME goal count as the
input, the correspondence is positional: the i-th output goal is the i-th
input goal, verbatim (node reused, comments untouched — the old path) or
MODIFIED (rendered fresh; `table.move(old, new)` WITHOUT the stale marker).
An equal-count output goal that equals a *different* input goal is a
reordering in disguise — pairing it positionally would hand it another goal's
comments — and is refused. This also handles the duplicate-goal corner (two
identical goals, one modified) that a greedy unmatched-in/unmatched-out
pairing would misclassify as a reorder. Count-changing outputs keep the old
greedy deletion path unchanged; modification combined with a count change
refuses (neither correspondence models it). A modified goal must be a plain
`Goal`: a conjunction group reifies as a bare list, which would render as a
list literal — no faithful node, refused loudly.

**Arrow registration route.** A modified goal is rendered with
`render_source` (text), re-parsed, and `clausal.fmt.comments.arrow_nodes` runs
over the re-parse before splicing. This is mechanically sound because the
renderer's sentinel repair (`_LAMBDA_ARROW_MARKER` → `_tighten_nested_arrows`)
guarantees that in renderer output, `<-` adjacency occurs exactly at rendered
lambda arrows, while a genuine `A < -B` always renders spaced. So the
capture-time detector over rendered text registers every surviving lambda
arrow and nothing else. Proven by tests: a goal holding both a surviving
nested lambda and the eta-reduced argument emits with `<-` intact, and a
genuine `A < -B` inside a modified goal survives as a comparison.

**Argument depth.** The lambda must be a DIRECT positional argument of a
top-level conjunct that is a plain `Goal` — the position higher-order
arguments are actually passed in. Not searched: or-groups, negations, nested
groups, keyword-argument values, arguments-of-arguments, other lambdas'
bodies. Rationale: deeper positions are increasingly likely to be data
(e.g. `bundle(((A, B) <- double(A, B)))` in the closure-arity fixture), and
the corpus census confirmed the depth-1 rule fires exactly on the two genuine
call-position forwarders and nothing else.

**Rule mechanics.** The `Lambda`/`Params` vocabulary is deliberately not
exported to Clausal (`op_node/3` excludes it), so the rule tests the node by
`type(...).__module__`/`__name__` and harvests params through `++` escapes,
then does all matching in Clausal (`Forwards/2`, `Distinct/1`). One argument
of one goal per firing; the driver fixpoints (both-lambdas and
rule-cooperation cases tested). The replacement is `Atom(CALLEE)`.

## Test summary

All with `PYTHONPATH=<worktree>` and the venv interpreter (import location
verified inside the worktree):

- `tests/rewrite/ tests/fmt/ tests/test_reflection.py tests/test_reflection_builtins.py`:
  **1658 passed** (baseline before this work: 1556).
- New: 11 contract-spike tests, 8 driver modified-goal tests, 32 rule tests
  (9 reductions + 16 refusals + 7 through-the-driver, incl. idempotence and
  the mixed surviving/reduced-lambda arrow proof).
- Corpus sweep now runs EVERY shipped rule (was head_fold only); all four
  assertions (conservation, localization, idempotence, arrow safety) hold on
  all 100+ files. Two files legitimately rewrite under the new rule:
  `tests/fixtures/head_list_compound.clausal` (a `call_goal` forwarder) and
  `todo/done/closure-arity-repro.clausal` (a user-HO forwarder); the
  var-bound and compound-nested closures beside the latter correctly refuse.

## Concerns

1. **Term-vs-goal caveat (inherent to eta-reduction).** The lambda and the
   bare reference are equivalent *as a called goal*. A predicate that stores
   its argument and structurally inspects it could distinguish a closure from
   an atom. Statically unknowable; documented in the rule header, same fence
   as head_fold's binding-time caveat (corpus sweep + domain tests).
2. **The two rewritable corpus files are closure fixtures.** They pass the
   sweep's invariants, but their *purpose* is to exercise closures — running
   `clausal-rewrite` over the repo itself would eta-reduce them and weaken
   what they test. Nothing does that automatically today; worth a
   `# lint: do not fold`-style pragma story if that ever changes.
3. **Zero-param lambdas are reduced** (`(() <- pings())` → `pings`).
   Equivalence is engine-verified; flagging because the surface form is rare.
4. **Escape-based type checks in the rule** couple it to
   `clausal.pythonic_ast.nodes` class names (`Lambda`, `PosOrKwParam`). If
   the Lambda vocabulary is ever exported to Clausal properly, the rule
   should switch to structural matching.
5. The worktree needed the compiled `_variables` (and sibling) `.so`
   artifacts copied from the main checkout — they are gitignored build
   products a fresh worktree lacks.
