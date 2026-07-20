# Reified-term → source renderer (`render_ast` / `render_source`)

Date: 2026-07-20
Todo: `todo/reified-term-to-source-renderer.md`

## Purpose

Build the inverse of `reify_ast`: turn a reified `Clause`/`Goal`/`Variable`/`Atom`/…
term back into Python surface `ast`, so `ast.unparse` renders runnable `.clausal`
source. This is the foundational primitive for the Clausal-AST mutation auditor
(match+replace in Clausal → rewritten term → runnable source to score a mutant).

`reflection.py` today maps source → reified terms one way only. There is no way to
render a *rewritten* reified term back to source. This spec closes that gap.

## Public API (in `clausal/reflection.py`)

- `render_ast(term) -> ast.AST` — the primitive: reified term → Python surface `ast`
  node. This is the always-needed half; both scoring paths (source-round-trip and
  in-process `compile_module`) build on it.
- `render_source(term) -> str` — thin wrapper: `render_ast` → `ast.unparse` + the
  existing `_unparse_clause` top-level `<-` arrow repair.
- `RenderError(Exception)` — raised loudly for any node kind the renderer cannot
  handle. The renderer NEVER emits malformed text (a silently-corrupt mutant would
  falsely "survive" and inflate the auditor's coverage report).

Both added to `__all__`.

## Design: `_ClauseRenderer`

A class mirroring `_ClauseReifier`, dispatching on reified term type. The mapping
inverts the forward reifier and `TermTransformer`'s surface conventions:

| Reified term | Surface `ast` produced | Notes |
|---|---|---|
| `Clause(head, goals, pos)` | fact (goals `[]`) → head expr as `Expr` statement; rule → `Compare(head, [Lt()], [UnaryOp(USub(), body)])` | The `Compare/Lt/USub` shape is exactly what surface `HEAD <- BODY` parses to and what `_unparse_clause` repairs. body = the single goal, or `ast.Tuple` of the goals. |
| `Goal(name, args, kwargs)` | `ast.Call(func=Name or dotted Attribute, args=[…], keywords=[ast.keyword(k, v)…])` | dotted `name` → `Attribute` chain. |
| `Variable(name)` | `ast.Name(name)` | `#anon…` names → `ast.Name("_")` (anonymous). Named vars are ALL-CAPS / `_`-led, so they re-reify as variables. |
| `Atom(name)` | `ast.Name(name)`, or dotted → `ast.Attribute` chain | lowercase names re-reify as atoms by the surface naming convention. |
| raw `simple_ast` operator nodes | dispatch table keyed on class → `BinOp` / `Compare` / `UnaryOp` / `BoolOp` | `Add`→`+`, `Sub`→`-`, `Mult`→`*`, … ; `Lt`→`<`, `GtE`→`>=`, `ArithEq`→`==`, `ArithNeq`→`!=` ; `Unify`→`is`, `DoesNotUnify`→`is not`, `in_`→`in`, `NotIn`→`not in` ; `And`→`and`, `Or`→`or` ; **`BitOr`→`\|`** (this is the list cons-tail — see below) ; `Not`→`not`, `Negate`→ unary `-`, `UnaryPlus`→ unary `+`, `Invert`→`~`. `StarUnpack`→`ast.Starred`. All BinOp/CmpOp use `.left`/`.right`; UnaryOp use `.operand`. |
| `IfThenElse(c, t, e)` / `simple_ast.IfExpr` | `ast.Call(func=Name("If"), args=[cond, then, otherwise])` | Clausal's parser rejects Python ternary syntax (`a if b else c`); the surface form is `If(cond, then, otherwise)` — an `ast.Call` to the `If` name. Using `ast.IfExp` would break the round-trip. |
| `Escape(code, vars, pos)` | `++(<code>)` | `code` is unparsed Python text; parse it back to an expr and wrap so unparse emits a re-parseable adjacent-`++`. |
| `FormatString(code, …)` | the f-string surface | same parse-back-and-wrap approach. |
| plain list `[a, b]` | `ast.List` of rendered elements | — |
| **list with cons tail `[a, b \| T]`** | `ast.List` whose LAST element is `ast.BinOp(left, BitOr(), right)` | The cons tail reifies as a **`BitOr` node** (surface `\|` parses as bitwise-or), NOT `Starred` — verified by probe: `[a, b \| T]` → `[Atom(a), BitOr(left=Atom(b), right=Variable(T))]`. It is handled by the operator dispatch row above (`BitOr`→`\|`); render it back to `\| T`. Rendering it as `*T`/`Starred` re-reifies to a **different** node and BREAKS the round-trip. |
| list literally written with `*tail` | last element → `ast.Starred` | Distinct surface from the cons form; both exist, they are NOT interchangeable. |
| tuple / dict / int / float / str / bool | `ast.Tuple` / `ast.Dict` / `ast.Constant` | negative numbers via `UnaryOp(USub, Constant)`. |
| `ModuleDirective` / `PythonCode` | raise `RenderError` | out of scope: the auditor only rewrites clause bodies. |

Unknown reified node kind → `RenderError`, never silent.

### Implementation notes
- **Recurse on children.** `Goal.args`, `kwargs` values, `BinOp`/`Compare`/`UnaryOp`
  operands, list elements, and `IfThenElse` parts are themselves reified terms —
  render each via `render_ast` (e.g. `ast.keyword(k, render_ast(v))`).
- **Locations.** `render_ast` builds fresh nodes without `lineno`/`col_offset`.
  `ast.unparse` tolerates this for expressions, but call
  `ast.fix_missing_locations` on the tree defensively before unparse.
- **`Escape` `vars`.** The captured-variable list must survive the round-trip —
  render it so re-reification reproduces the same `Escape(code, vars, …)`; cover it
  with a fixture, don't rely on the corpus sweep alone.

## Acceptance — round-trip invariant

The invariant, tested per node kind:

    reify(render_source(clause)) ≡structural≡ clause

`render` then re-`reify` is the identity on reified terms (idempotent; whitespace /
comments need not survive — only structure). Structural comparison uses the reified
terms' own `==`/unification.

### Tests

1. **Checked-in fixture set** (always runs, in-repo, portable): a set of clauses
   covering every node kind — comparisons, arithmetic, `is`, `==`, `not`, plain
   lists, **cons-tail lists `[a, b | T]`** and `*tail` lists (distinct cases),
   dict `get`, `kwargs`, nested compounds, if-then-else, **escapes (with a captured
   `vars` list)**, atoms vs variables, facts vs rules. Each asserts the round-trip
   invariant. This is the portable **smoke test**, not a completeness proof — a
   hand-written fixture set will miss node kinds (the `BitOr` cons tail was missed
   in the first draft of this very spec), so it does NOT by itself certify the
   renderer.
2. **Corpus round-trip — the real completeness gate.** A parametrized test walking
   every `.clausal` file under `/workspace/clausify-domains` (571 files),
   **filtering to `Clause` items only** (`reified_clause`, or
   `type(item).__name__ == "Clause"`) — every file opens with `-module`/
   `-import_from`, which reify to `ModuleDirective`/`PythonCode`, the node kinds the
   renderer deliberately *raises* on; iterating raw `reified_item` would
   `RenderError` on line 1 of every file. The test may skip (with a clear reason)
   when the corpus dir is absent so the engine suite stays portable — **but it MUST
   be RUN, and pass with zero `RenderError`s, before the mutation auditor depends on
   the renderer.** "Green fixtures" ≠ "complete"; this sweep is what closes the gap.
   Any clause the renderer can't handle must raise `RenderError`, never silently
   corrupt (a corrupt mutant would falsely "survive" and inflate the auditor's
   coverage report).

## Out of scope

- The optional Clausal-callable `clause_source(ClauseTerm, Text)` predicate — the
  auditor's driver is Python and calls the API directly. Filed as a follow-on in the
  todo; not built here.
- Rendering `ModuleDirective` / `PythonCode` — raise instead.
- **Non-splat dict literals with bare-atom keys** (`{foo: V}`). These crash the reflection
  *reifier* (`reify_source` → `TypeError: unhashable type: 'Goal'`) before any clause reaches the
  renderer, so they cannot be exercised by the render gate. 126/571 corpus files trip this; the
  corpus test skips exactly them with reason `reifier defect (dict-literal atom key unhashable)`.
  Filed as `todo/reify-source-dict-literal-atom-key-unhashable.md` (a reifier fix, separate from the
  renderer). The splat form `{**B, foo: V}` reifies fine and IS rendered (`DictLiteral` node).

## Method

Strict TDD: write the round-trip test for a node kind, then implement that renderer
branch until green. Reuse `ast.unparse` + `_unparse_clause` rather than hand-emitting
text (far more robust). Keep the renderer next to the reifier so vocabulary changes
keep both halves in sync.
