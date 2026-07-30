# Renderer completeness gaps: CompareChain / Slice / Evaluate / SetLiteral

STATUS: DONE (2026-07-29). Filed 2026-07-20 from the Fable review of the
reified-term renderer.

## FIXED — 2026-07-29

The renderer is now complete over the *reachable* node set, and the reachable set
is pinned by a mechanical sweep instead of a hand-list.

### Triage: the todo named four, two of which are not renderer gaps

Verified one at a time by reifying a clause containing each node, rendering it,
and (for the ones that reify) importing the same surface as a real `.clausal`
module to see whether the language accepts it at all.

| node | claim | verdict |
|---|---|---|
| `CompareChain` | unhandled | **true** — reaches the renderer, compiles, runs. Fixed. |
| `SetLiteral` | unhandled | **true** — same. Fixed. |
| `Slice` | unhandled | **not a renderer gap** — a slice never reaches the renderer. |
| `Evaluate` | unhandled | **not a renderer gap** — the node is unreachable from source. |

`Slice`: `Take(P, S) <- (S is P[1:3])` does not reify (`ReifyError: cannot reify:
1:3`) and does not *compile*: `EmbedTransformer` leaves the raw Python slice
inside `LoadSubscript.index`, and importing the module dies in
`clausal/logic/compiler/terms_to_ast.py:588` with `NotImplementedError:
term_to_ast_expr: unsupported term type slice`. `simple_ast.Slice` is only ever
built by `clausal/pythonic_ast/conversion_from_python_ast.py`, which nothing on
the `.clausal` path calls. There is no legal surface to render, so a rendering
would have been invented, not recovered. Filed the upstream half separately:
[[slice-and-ellipsis-in-clause-body-crash-with-notimplementederror]].

`Evaluate`: `:=` was removed by the walrus redesign — `X := E` now raises
`ReifyError: ':=' is not a Clausal operator`, the front end has no `Evaluate`
emission site, and the surviving surface is the builtin `eval_(E, X)`, which
reifies to a plain `Goal` and already round-tripped. `nodes.Evaluate` lives on
only as a downstream compiler/specialization pattern.

### The systematic sweep the todo asked for, and what it found

The reachable set is closed and enumerable: `EmbedTransformer` builds every
clause body out of `node_ast("<ClassName>", …)` calls, with the name either a
literal or an entry in one of its `BINOP_CLS` / `UNARYOP_CLS` / `BOOLOP_CLS` /
`CMPOP_CLS` tables. That is 50 node classes — not the 159 in
`simple_ast.__all__`, most of which are statement forms a clause body cannot
hold. Sweeping those 50 against the renderer found **nine** unhandled, of which
the todo named two:

| node | disposition |
|---|---|
| `CompareChain` | fixed (in todo) |
| `SetLiteral` | fixed (in todo) |
| `Await` | fixed — todo missed it |
| `Yield`, `YieldFrom` | fixed — todo missed them |
| `ListComp`, `SetComp`, `DictComp`, `GeneratorExpr` | first excluded, wrongly — see the correction below; rendered in a follow-up |
| `ForClause` | excluded: rendered by its owning comprehension, never a term on its own |

`await`/`yield` in a clause body are *not* coroutine surface — they compile to
inert term structures (`Go(L, M) <- (M is await L)` binds `M` to
`Await(value=[1, 2])`), so they are reachable and now render.

**Correction (follow-up commit).** The four comprehension kinds were excluded on
the claim that "every form fails at import with `NameError: name 'Y' is not
defined`", the loop variable being a bare reference nothing binds — and so, like
`Slice`, having no legal surface to render. That was wrong. The `NameError` is
what an *unbound* loop variable gets; declare the name and the comprehension is
ordinary legal surface:

```clausal
-private([x])

Sq(L, M) <- (M is [x * x for x in L])
```

imports, runs, and yields one solution with `M` bound to the `ListComp` term —
the same "inert term structure, not control flow" reading that `await`/`yield`
got two paragraphs up, missed here because the probe used `Y` (a logic variable)
rather than a declared atom. All four now render and round-trip; only `ForClause`
stays excluded, since it is never a term on its own.

Beyond the node classes, `_ClauseRenderer.term` was missing three of the seven
payload types `ast.Constant` can carry, all of which the reifier yields as
themselves: **`None`** (`X is None` — compiles and runs), **`bytes`** (`X is
b'ab'` — compiles and runs) and **`Ellipsis`** (reifies, but like `Slice` does
not compile; rendered anyway, since render inverts reify). `term` is now total
over constants. The todo missed all three; the 4171-clause corpus sweep had not
reached them either.

Nothing was rendered *wrongly*: every gap was a loud `RenderError`, so the
"raise loudly, never corrupt" contract held throughout. There were no silent
lies to find.

### Changes

`clausal/reflection.py`
- `_RENDER_STRUCTURAL_NODES`: new name→method dispatch table for the node kinds
  that are not plain operators, replacing the `if name == …` chain at the tail of
  `_operator_ast`. The four pre-existing branches (`StarUnpack`,
  `LoadSubscript`, `Lambda`, `DictLiteral`) moved into it unchanged.
- `RENDER_NODE_CLASS_NAMES` = `RENDER_OP_CLASS_NAMES | _RENDER_STRUCTURAL_NODES`,
  derived not hand-listed, so the completeness sweep cannot go stale.
  `RENDER_OP_CLASS_NAMES` is untouched — `op_node/3` stays bijective with the
  operator tables specifically.
- `_compare_chain_ast`, `_set_literal_ast`, `_await_ast`, `_yield_ast`,
  `_yield_from_ast`; `None`/`bytes`/`Ellipsis` in `term`.

`tests/test_reflection_render.py`
- `TestCompareChain`, `TestSetLiteral`, `TestPlainConstants`,
  `TestInertPythonExprNodes` — round-trip via the existing `assert_round_trips`
  (`reify(render_source(c)) == c`), plus two hand-written surface assertions
  (`Range(X) <- (0 < X < 10)`, `HasInts(S) <- (S is {1, 2})`) so a chain cannot
  quietly become a conjunction and a set cannot become `set([…])`.
- `test_emittable_node_kinds_are_all_decided` /
  `test_render_exclusions_are_not_stale`: re-derive the 50 emittable names from
  `term_rewriting.py` and require each to be either in
  `RENDER_NODE_CLASS_NAMES` or in a `RENDER_EXCLUSIONS` dict that states why.
  A newly emittable node kind now fails the suite until someone records a
  decision, and an exclusion that stops being true also fails.

### Refusals, i.e. where a faithful rendering does not exist

Each keeps the contract rather than invent text:

- **A `CompareChain` whose adjacent links disagree on their shared operand.**
  `0 < X < 10` reifies to *pairwise* links that share the middle operand
  (`Lt(0, X)`, `Lt(X, 10)`) because the chain evaluates it once; Python's chain
  surface writes it once. A mutated `Lt(0, X), Lt(Y, 10)` has no chain surface —
  `0 < X < 10` would silently drop `Y`. Checked on the *rendered* surface of the
  join (re-reification is textual, the same criterion the duplicate-dict-key
  guard uses) and refused on mismatch.
- **A one-link `CompareChain`, and an empty `SetLiteral`.** `0 < X` re-reifies to
  a bare `Lt`, not a chain; `{}` is the dict surface and `ast.unparse` spells an
  empty `ast.Set` as `{*()}`, which re-reifies as a one-element set holding a
  splatted empty tuple. Neither is constructible by the front end; both are
  reachable by mutation, so both raise.
- **A comprehension with no for-clause, and a tuple comprehension target**
  (follow-up). `[E]` with an empty `clauses` list is the list-literal surface,
  which re-reifies as a list; a tuple target unparses bare (`for x, y in L`),
  which `EmbedTransformer` refuses in turn, so writing it would emit text that
  cannot be read back. Neither is constructible by the front end either.

### Verification

Red-green: the 36 new tests were run before the change (30 failed — the six
`*_raises` guards passed already, on the *generic* `cannot render operator node`
message, and now pass on the specific one) and after (all pass). Full suite:
`1 failed, 10556 passed, 136 skipped, 44 xfailed` — the one failure is the
expected `test_doc_snippet_coverage.py::test_no_raw_untested_blocks`; baseline
was `1 failed, 10520 passed`.

## Open design questions

**Should the renderer accept the runtime's `SetTerm`?** A reified `{a, b}` is
`SetLiteral(elements=[…])` — an ordered list, so the written order round-trips
exactly. But the *runtime* value is `terms.SetTerm`, backed by a `frozenset`,
where order is arbitrary. Nothing produces a `SetTerm` inside a reified term
today (reify is textual and never evaluates), so the renderer refuses it via the
catch-all. Options: (a) leave it refused — an auditor works on reified terms, and
a `SetTerm` in one means something evaluated where it should not have;
(b) render it with elements in `sorted(…, key=repr)` order, accepting that the
surface is a normalisation rather than a recovery; (c) render it only when it has
0 or 1 elements, where order cannot differ. **Recommendation: (a)**, and revisit
only if the auditor is ever fed engine-side terms. Silently normalising set order
is exactly the "plausible but incorrect text" failure this todo exists to avoid.

**Should the exclusion list live in the test or in `reflection.py`?** It is in
the test today, because it records *why the language cannot reach a node*, which
is a fact about the compiler rather than about the renderer. If a second consumer
(the auditor, deciding which clauses it can mutate) needs the same list, promote
it to `reflection.py` next to `RENDER_NODE_CLASS_NAMES`.
