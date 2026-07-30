# Slice / `...` / comprehensions in a clause body crash with a raw internal error

STATUS: OPEN (filed 2026-07-29, found while triaging
[[done/render-completeness-comparechain-slice-evaluate]]).

Three surfaces that `EmbedTransformer` happily rewrites are rejected only much
later, by an internal exception with no source line, no caret and no suggestion —
where every other unsupported surface in the language gets a `SyntaxError` from
`term_rewriting.py` naming the construct.

Reproduce by importing a one-clause module (each is its own module; all three
fail at import, i.e. compilation is eager):

| surface | current failure |
|---|---|
| `Take(P, S) <- (S is P[1:3])` | `NotImplementedError: term_to_ast_expr: unsupported term type slice: slice(1, 3, None)` — `clausal/logic/compiler/terms_to_ast.py:588` |
| `Dots(X) <- (X is ...)` | `NotImplementedError: term_to_ast_expr: unsupported term type ellipsis: Ellipsis` — same line |
| `Go(L, M) <- (M is [Y for Y in L])` (also set/dict/generator forms) | `NameError: name 'Y' is not defined` at import — but only because the loop variable is unbound; see below |

The slice case is the most misleading of the three: `EmbedTransformer` builds
`LoadSubscript(object=P, index=<raw ast.Slice>)`, so the *reifier* also refuses it
(`ReifyError: cannot reify: 1:3`) and `simple_ast.Slice` — which exists, with
`lower`/`upper`/`step` and a `__str__` — is never constructed on the `.clausal`
path at all. It is only built by
`clausal/pythonic_ast/conversion_from_python_ast.py:126`, reachable solely through
`nodes.simplify()`, which nothing calls.

The comprehension case fails because the loop variable is emitted as a bare
reference that no walrus binds, so the generated `ListComp(...)` constructor
evaluates a name that does not exist.

That is a fault of the *loop variable*, not of comprehensions, and the
distinction was originally missed here: **declare the name and the comprehension
compiles.**

```clausal
-private([x])

Sq(L, M) <- (M is [x * x for x in L])
```

imports, runs, and yields one solution with `M` bound to the `ListComp` term
itself — a comprehension in a clause body is inert structure, like `await`, not
something that iterates. So `ListComp`/`SetComp`/`DictComp`/`GeneratorExpr`/
`ForClause` are live emission sites, not dead ones, and the reified clause
contains them. The renderer handles all four as of
`fix/renderer-completeness-comparechain-setliteral`
(`TestComprehensions` in `tests/test_reflection_render.py`); only `ForClause`
remains in `RENDER_EXCLUSIONS`, because it is never a term on its own.

What is left open here is the diagnostic: an *undeclared* loop variable gets the
strict-atoms `NameError` (which at least names the atom and how to declare it),
and a **logic variable** — the far likelier thing to write, since `[Y for Y in L]`
is what a Python reader reaches for — gets a bare `NameError: name 'Y' is not
defined` with no line, no caret and no hint that a comprehension is not a
generator here.

## Work
Two independent choices, per surface:

1. **Diagnose, don't crash.** Reject in `term_rewriting.py` at the visit site
   (`visit_Slice`, the `ast.Constant(Ellipsis)` path) with a `SyntaxError`
   carrying the line and a pointer to the working spelling — `nth0/3`/`sublist`
   for slices. This is the cheap half and matches how the method-call form
   `P.foo(A)` and `:=` are already refused. For comprehensions the rejection
   cannot be at the visit site, because the surface is legal (a declared loop
   variable compiles): it has to be a diagnostic on the *loop variable* — a
   logic-variable target is never meaningful, since nothing binds it, so
   `visit_ListComp` and friends can refuse that one target shape by name and
   point at `findall/3`.
2. **Or implement them.** Slices have an obvious meaning on list terms and
   `simple_ast.Slice` is already defined for it, which suggests someone intended
   to. Making a comprehension *iterate* would need the loop variable bound as a
   logic variable, i.e. real work, and `findall/3` already covers the ground.

Recommendation: do (1) for all three now — an internal `NotImplementedError` is
never the right answer to a user's file — and treat slice support as a separate
feature request. If slices are implemented, note that the renderer
(`clausal/reflection.py`, `_RENDER_STRUCTURAL_NODES`) will need a `Slice` branch,
and the completeness sweep in `tests/test_reflection_render.py`
(`test_emittable_node_kinds_are_all_decided`) will fail until it is added, which
is the intended prompt. A tuple comprehension target
(`[x for x, y in L]`) is a fourth instance of the same class of fault, found
while rendering these: `EmbedTransformer` reaches it and dies on
`assert type(tuple_expr.ctx) == Load` in `visit_Tuple`
(`clausal/templating/term_rewriting.py:1457`) — a bare `AssertionError` with no
message at all, at import and under `reify_source` alike.
