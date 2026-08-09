# Reified-term → AST/source renderer (the inverse of `reify_ast`)

STATUS: DONE (2026-07-20).
RESULT: `render_ast`/`render_source` landed in `clausal/reflection.py`; corpus round-trip gate green over 571 files / 4171 reifiable clauses; 126 files deferred to pre-existing reifier bug (`todo/reify-source-dict-literal-atom-key-unhashable.md`).

**Critical prerequisite** for the Clausal-AST
mutation auditor (design in a downstream consumer's own docs — Approach B:
match+replace in Clausal, then the rewritten term must be turned back into
something runnable so a generated mutant can be scored).

## The core deliverable is `reified term → Python ast` (`render_ast`)
This is the foundational, always-needed inverse of `reify_ast`. BOTH candidate
scoring paths need it:
- **source-round-trip path** (v1): `render_ast` → `ast.unparse` (+ the `<-` arrow
  repair in `_unparse_clause`) → text spliced into the sibling and scored in a
  fresh subprocess. Provide `render_source(term) -> str` as this thin unparse
  wrapper.
- **direct / in-process path** (possible v2): `render_ast` → `compile_module(...)`
  (`clausal/logic/compiler_v2.py:92`) → a live predicate scored in-process, no
  text and no file. (`assertz` is NOT a shortcut here — it operates on *runtime*
  terms, and there is no reified→runtime de-reifier; `render_ast` + `compile_module`
  is the clean direct route.)

So: **`render_ast` is the primitive; `render_source` is a one-line unparse wrapper
over it.** Building `render_ast` unblocks either scoring strategy.

## What exists today (and the gap)
`clausal/reflection.py` reifies source → ground terms **one way only**:
- `reify_source(text)` / `reify_file(path)` / `reify_ast(node)` — forward
  (Python `ast` → reified `Clause`/`Goal`/… terms), lines 456-569.
- `_unparse_clause(node)` (line 529) unparses a **Python `ast` node** back to
  `.clausal` text via `ast.unparse` + a top-level `<-`-arrow repair.

There is **no inverse of `reify_ast`**: nothing maps a reified `Clause`/`Goal`
term back to a Python `ast` node (or to source text). Confirmed: reified terms
have no renderer — `str(Clause(...))` yields a Python repr, and the reflection
module exposes only `_unparse_clause` (ast-node input) and `reify_source`.

## Deliverable
A public function in `clausal/reflection.py`, e.g.
`render_source(term) -> str` (and/or `render_ast(term) -> ast.AST`), the inverse
of `reify_ast`. Recommended implementation: **reified term → Python `ast` node →
`ast.unparse` + the existing `_unparse_clause` arrow repair** (reuse unparse
rather than hand-emit text — far more robust).

The mapping mirrors the forward reifier (`_ClauseReifier` at reflection.py:136 and
`clausal/templating/term_rewriting.py`'s `TermTransformer`). The closed reified
vocabulary to cover (reflection.py:82-90):
- `Clause(head, goals, position)` → `HEAD <- (G1, G2, ...)` (single-goal fact =
  head only, no arrow — match `reify_source`'s own round-trip).
- `Goal(name, args, kwargs)` → `ast.Call` (or the operator/`is`/`==`/comparison/
  arithmetic form the forward reifier produced — invert whatever `TermTransformer`
  maps operators *to*; check how e.g. `BS >= THRESHOLD` reifies and mirror it).
- `Variable(name)` → `ast.Name`; `Atom(name)` → the atom's surface form.
- `Escape(code, vars, position)`, `FormatString(...)`, `IfThenElse(cond, then,
  otherwise)` → their surface syntax.
- arg value kinds: nested `Goal`s, lists, numbers, strings, dict literals, and
  `kwargs` → `ast.keyword`s.
- `ModuleDirective` / `PythonCode` — out of scope for the mutation use case
  (auditor only rewrites clause bodies), but render or explicitly raise.

## Acceptance — the corpus round-trip invariant (make this the test)
For **every clause in every `.clausal` file across a downstream rulebase corpus**
(~30 domains) the following must hold:

    reify(render_source(clause)) ≡structural≡ clause

i.e. `render` then re-`reify` is the identity on reified terms (idempotent;
whitespace/comments need not survive — only structure). A node kind the renderer
misses must **raise loudly**, never emit malformed text (a silently corrupt
mutant would falsely "survive" and inflate the coverage report). Add this as a
parametrized test that walks the corpus (or a checked-in fixture set of clauses
covering every node kind: comparisons, arithmetic, `is`, `==`, `not`, lists,
dict `get`, `kwargs`, nested compounds, if-then-else).

Probe already run (2026-07-20): `reify_file` → `_unparse_clause` →
`reify_source` round-trips 31/31 items on a client-categorisation domain's `computation.clausal`, so the
`ast.unparse` path is viable; this task adds the **reified-term → ast** half so
the round-trip works on *rewritten* terms, not just re-parsed source.

## Reuse note
This is not mutation-only: it is the general "Clausal-driven codegen / refactor /
lint-autofix" primitive (emit rewritten source from a program that manipulated
reified terms). Belongs in the engine next to the reifier so vocabulary changes
keep both halves in sync.

## Optional follow-on (not required for the auditor)
A Clausal-callable wrapper predicate `clause_source(ClauseTerm, Text)` in
`clausal/modules/reflection.py` so a `.clausal` program (not just the Python
driver) can render. The mutation auditor's driver is Python, so it can call the
Python API directly; the predicate is a nicety for pure-Clausal clients.
