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
| `Go(L, M) <- (M is [Y for Y in L])` (also set/dict/generator forms) | `NameError: name 'Y' is not defined` at import |

The slice case is the most misleading of the three: `EmbedTransformer` builds
`LoadSubscript(object=P, index=<raw ast.Slice>)`, so the *reifier* also refuses it
(`ReifyError: cannot reify: 1:3`) and `simple_ast.Slice` — which exists, with
`lower`/`upper`/`step` and a `__str__` — is never constructed on the `.clausal`
path at all. It is only built by
`clausal/pythonic_ast/conversion_from_python_ast.py:126`, reachable solely through
`nodes.simplify()`, which nothing calls.

The comprehension case fails because the loop variable is emitted as a bare
reference that no walrus binds, so the generated `ListComp(...)` constructor
evaluates a name that does not exist. `ForClause`, `ListComp`, `SetComp`,
`DictComp` and `GeneratorExpr` are therefore all dead emission sites today.

## Work
Two independent choices, per surface:

1. **Diagnose, don't crash.** Reject in `term_rewriting.py` at the visit site
   (`visit_Slice`, the `ast.Constant(Ellipsis)` path, `visit_ListComp` and
   friends) with a `SyntaxError` carrying the line and a pointer to the working
   spelling — `nth0/3`/`sublist` for slices, `findall/3` for comprehensions. This
   is the cheap half and matches how the method-call form `P.foo(A)` and `:=` are
   already refused.
2. **Or implement them.** Slices have an obvious meaning on list terms and
   `simple_ast.Slice` is already defined for it, which suggests someone intended
   to. Comprehensions would need the loop variable bound as a logic variable, i.e.
   real work, and `findall/3` already covers the ground.

Recommendation: do (1) for all three now — an internal `NotImplementedError` is
never the right answer to a user's file — and treat slice support as a separate
feature request. If slices are implemented, note that the renderer
(`clausal/reflection.py`, `_RENDER_STRUCTURAL_NODES`) will need a `Slice` branch
and the `RENDER_EXCLUSIONS` list in `tests/test_reflection_render.py` will need
its comprehension entries revisited; the completeness sweep there
(`test_emittable_node_kinds_are_all_decided`) will fail until both are updated,
which is the intended prompt.
