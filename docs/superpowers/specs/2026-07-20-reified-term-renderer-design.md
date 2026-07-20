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
| raw `simple_ast` operator nodes | dispatch table keyed on class → `BinOp` / `Compare` / `UnaryOp` / `BoolOp` | `Add`→`+`, `Sub`→`-`, `Mult`→`*`, … ; `Lt`→`<`, `GtE`→`>=`, `ArithEq`→`==`, `ArithNeq`→`!=` ; `Unify`→`is`, `DoesNotUnify`→`is not`, `in_`→`in`, `NotIn`→`not in` ; `And`→`and`, `Or`→`or` ; `Not`→`not`, `Negate`→ unary `-`, `UnaryPlus`→ unary `+`, `Invert`→`~`. `StarUnpack`→`ast.Starred`. All BinOp/CmpOp use `.left`/`.right`; UnaryOp use `.operand`. |
| `IfThenElse(c, t, e)` / `simple_ast.IfExpr` | `ast.IfExp(test, body, orelse)` | |
| `Escape(code, vars, pos)` | `++(<code>)` | `code` is unparsed Python text; parse it back to an expr and wrap so unparse emits a re-parseable adjacent-`++`. |
| `FormatString(code, …)` | the f-string surface | same parse-back-and-wrap approach. |
| list, with optional trailing `*tail` | `ast.List`; tail element → `ast.Starred` | inverts `[a, b | T]` → `[a, b, *T]`. |
| tuple / dict / int / float / str / bool | `ast.Tuple` / `ast.Dict` / `ast.Constant` | negative numbers via `UnaryOp(USub, Constant)`. |
| `ModuleDirective` / `PythonCode` | raise `RenderError` | out of scope: the auditor only rewrites clause bodies. |

Unknown reified node kind → `RenderError`, never silent.

## Acceptance — round-trip invariant

The invariant, tested per node kind:

    reify(render_source(clause)) ≡structural≡ clause

`render` then re-`reify` is the identity on reified terms (idempotent; whitespace /
comments need not survive — only structure). Structural comparison uses the reified
terms' own `==`/unification.

### Tests

1. **Checked-in fixture set** (always runs, in-repo, portable): a set of clauses
   covering every node kind — comparisons, arithmetic, `is`, `==`, `not`, lists with
   a tail, dict `get`, `kwargs`, nested compounds, if-then-else, escapes, atoms vs
   variables, facts vs rules. Each asserts the round-trip invariant.
2. **Corpus round-trip** (opt-in, skips if absent): a parametrized test walking
   every `.clausal` file under `/workspace/clausify-domains` (569 files). Skipped
   with a clear reason when the corpus directory is missing, so the suite stays
   self-contained and portable. Any clause the renderer can't handle must raise
   `RenderError`, not silently corrupt.

## Out of scope

- The optional Clausal-callable `clause_source(ClauseTerm, Text)` predicate — the
  auditor's driver is Python and calls the API directly. Filed as a follow-on in the
  todo; not built here.
- Rendering `ModuleDirective` / `PythonCode` — raise instead.

## Method

Strict TDD: write the round-trip test for a node kind, then implement that renderer
branch until green. Reuse `ast.unparse` + `_unparse_clause` rather than hand-emitting
text (far more robust). Keep the renderer next to the reifier so vocabulary changes
keep both halves in sync.
