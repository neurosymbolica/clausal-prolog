# Docs Improvement Plan

Work through these phases in order. Each phase is independent — commit after each.

---

## Phase 1: Fix cheatsheet errors (syntax.md)

The cheatsheet (lines 929–1051) and related sections have syntax that doesn't exist.

### 1a. Remove `A.goal(B)` infix sugar

- **Lines 421–427**: Remove the "infix and postfix" section entirely (the `A.goal(B)` and `A .goal` forms). `visit_Attribute` in `term_rewriting.py` only handles module-qualified calls like `utils.Helper(X)`, not method-style infix.
- **Line 984**: Remove `A.goal(B),  # infix sugar` from cheatsheet.

### 1b. Remove `module/(Terms)` syntax

- **Lines 440–444**: Replace with the actual module qualification syntax: `mod.Pred(X)` via `-import_module(mod)`. Reference `directives.md` and `import.md`.
- **Line 990**: Fix in cheatsheet to show `utils.Double(X, Y)` instead of `module/(Terms)`.

### 1c. Fix DCG arrow

- **Line 980**: Change `Rule > ListDescription,` to `Rule >> ListDescription,` (double `>`).

### 1d. Remove `(--clpz)` constraint domain syntax

- **Line 998**: Remove. No `clpz` exists in the codebase. CLP(FD) constraints are used directly (`in_domain`, `==`, `!=`, `<`, etc.).

### 1e. Mark EDCG as experimental

- **Lines 1026–1032**: Add a comment `# EXPERIMENTAL — directive parsing only, no end-to-end rewriting yet`.
- **directives.md lines 103–131**: Add an admonition box at the top of the EDCG section:
  ```
  !!! warning "Experimental"
      EDCG directives are parsed but end-to-end rewriting is not yet implemented.
  ```

### 1f. ~~Clean up `equivalent` comment~~ (Done — `equivalent/2` renamed to `structural_eq/2`)

---

## Phase 2: write tutorial.md

Create `docs/tutorial.md` and add it to `mkdocs.yml` nav under "Getting Started" (after `goals.md`, before `syntax.md`).

Target: ~300 lines. Conversational tone. All examples in `.clausal` syntax with ALLCAPS variables. Minimal Python — only the `import` + `clausal.query()` one-liner to run things.

### Structure

```
# Tutorial

## Your first .clausal file
- Create `hello.clausal`
- Define a fact: `greeting("hello"),`
- Query it from Python (3 lines max)

## Facts and rules
- Family tree: parent/2 facts
- grandparent/2 rule with `<-` and `and`
- Multiple solutions / backtracking

## Logic variables
- ALLCAPS convention: X, PARENT, CHILD
- Anonymous variable: _
- How unification works (by example, not theory)

## Lists
- List syntax: [], [1, 2, 3], [HEAD, *TAIL]
- member/2, append/3 by example
- Pattern matching on lists in clause heads

## Arithmetic
- Walrus operator: (N := X + 1)
- Comparison: X > 0, X < 10

## Negation
- `not goal` — negation as failure
- when to use it, when not to

## Testing your code
- test/1 predicates
- Running tests: `python -m pytest`
- Link to testing.md for details

## Where to go next
- Link to syntax.md (full reference)
- Link to constraints.md (CLP(FD), dif/2)
- Link to dcg.md (grammars)
- Link to examples.md (worked examples)
- Link to builtins.md (predicate index)
```

### Style rules for the tutorial
- Every code block uses ` ```clausal ` fencing (not `python`)
- Variables are ALLCAPS: `X`, `HEAD`, `REST`, `PARENT`, `CHILD`, `N`, `F`
- Python appears only in "Query it from Python" boxes — keep to 2–3 lines
- No mention of PredicateMeta, Var(), deref(), Trail, Module(), or any internal API
- No mention of `_x` leading-underscore style — just teach ALLCAPS

---

## Phase 3: Rebalance Python vs .clausal focus

### 3a. Rewrite index.md

The landing page should make `.clausal` the star. Restructure:

1. **Quick taste** — show a `.clausal` file (fibonacci or family tree). Use ` ```clausal ` fence.
2. **Query it** — one Python snippet: `import clausal; from fibonacci import fib` + `clausal.query(fib(10, F))`. max_ 4 lines. Use ` ```python ` fence.
3. **What's inside** — the existing feature table (keep as-is, it's good).

Remove the `Module()` context-manager inline example entirely. That belongs in `python_integration.md`. The landing page should say: "write `.clausal` files, import them, query them."

### 3b. Rewrite examples.md "Running Examples" section (lines 106–132)

Replace the low-level API examples with:

```clausal
# in_ your .clausal file, add test predicates:
test("fib 10") <- fib(10, 55),
```

Then show the simple Python query:

```python
from fibonacci import fib
for s in clausal.query(fib(10, F)):
    print(s[F])  # 55
```

Remove the `call("Fib", 10, F, module=fib.__dict__["$module"])` example and the raw `query()` with `Call(LoadName(...))` term trees.

### 3c. Rewrite predicates.md

Currently 82% Python metaclass internals. Restructure:

1. **Lead with .clausal syntax** — how to define predicates in a `.clausal` file (facts, rules, fields inferred from head). This is what 95% of users need.
2. **Python-side** section (collapsed/admonition) — `PredicateMeta`, `make_predicate()`, `_fields`. label it clearly as "for embedding/advanced use".

### 3d. Add disclaimer to python_integration.md

Add at the top:

> Most clausal programs are written as `.clausal` files and queried with `clausal.query()`. This page covers the lower-level Python API for embedding logic programming in Python applications, testing, and advanced use cases.

Move the Trail/Var/deref/term-tree sections into a "Low-level API" subsection or collapsible admonition.

---

## Phase 4: Convert examples to ALLCAPS variables

Systematic find-and-replace across docs. The rule:

- `X_` → `X`, `Y_` → `Y`, `N_` → `N`, `F_` → `F`, `R_` → `R`, `S_` → `S`, `D_` → `D`
- `head_` → `HEAD`, `tail_` → `TAIL`, `rest_` → `REST`
- `Result_` → `RESULT`, `Acc_` → `ACC`, `Elem_` → `ELEM`
- Predicate names stay TitleCase: `Fib`, `append`, `Member` (no change)
- Atoms stay lowercase or quoted: `"hello"`, `red` (no change)
- `_` (anonymous) stays as-is

### Files to update (by priority — highest occurrence count first)

1. `syntax.md` (60 occurrences) — most visible, do first
2. `constraints.md` (55)
3. `lambdas.md` (34)
4. `clpr.md` (35)
5. `clpb.md` (25)
6. `meta_predicates.md` (21)
7. `reified_ite.md` (21)
8. `scipy_optimize.md` (21)
9. `python_integration.md` (17)
10. `exceptions.md` (16)
11. `scipy_ndimage.md` (15)
12. All remaining files with occurrences

### Watch out for

- Lambda parameter variables (`_x <- ...`) — these become `(X <- ...)` which is fine
- The cheatsheet line 933–934 should flip: show ALLCAPS first, leading-underscore as "also valid" footnote (it already does this — just make sure the rest of the file matches)
- Don't change `_fields`, `_clauses`, or other Python identifiers that happen to have underscores
- Don't change variable names inside ` ```python ` blocks — those are Python code where `_x` may be actual Python identifiers referring to Var objects

---

## Phase 5: Add ```clausal fencing

Every `.clausal` code example should use ` ```clausal ` fencing instead of ` ``` ` (unfenced) or ` ```python `.

### How to distinguish

- If the code block shows `.clausal` file content (facts, rules, directives, queries), fence as ` ```clausal `
- If the code block shows Python code (`import`, `for`, `print`, `clausal.query()`), fence as ` ```python `
- If the code block shows shell commands, fence as ` ```bash `

### Files to update

All 42+ files with unfenced code blocks. The big ones:

1. `builtins.md` — 334 unfenced blocks (biggest job)
2. `syntax.md` — ~57 blocks that are `.clausal` but fenced as `python`
3. `constraints.md` — ~26 unfenced blocks
4. `dcg.md` — ~42 unfenced blocks
5. `meta_predicates.md` — ~34 unfenced blocks
6. `lambdas.md` — ~27 unfenced blocks
7. All remaining files

### Note

mkdocs won't have a `clausal` syntax highlighter built in, but using the correct fence name is still important for semantics. If desired, add a Pygments lexer later or alias `clausal` to `python` in mkdocs.yml:

```yaml
# mkdocs.yml — optional, maps clausal to python highlighting
extra:
  pymdownx.highlight:
    custom_fences:
      - name: clausal
        class: highlight
        format: !!python/name:pymdownx.superfences.fence_code_format
```

Or just alias in the theme config. Either way, get the fence names right now.

---

## Phase 6: Add cross-links

### examples.md → feature pages

Each example section should link to the relevant doc page. E.g.:

- fibonacci.clausal → [Tabling](tabling.md), [Arithmetic builtins](builtins.md#arithmetic)
- nqueens.clausal → [CLP(FD) constraints](constraints.md)
- sudoku.clausal → [CLP(FD)](constraints.md), [Higher-order](meta_predicates.md)
- map_coloring.clausal → [dif/2](constraints.md#dif2)
- dcg_state.clausal → [DCGs](dcg.md)
- lambdas.clausal → [Lambdas](lambdas.md)
- sorting.clausal → [Lists](builtins.md#lists)

### Feature pages → each other

| From | Add link to | Context |
|------|------------|---------|
| `dcg.md` | `directives.md` | `-table` directive often used with DCGs |
| `exceptions.md` | `builtins.md` | Which builtins can throw |
| `testing.md` | `examples.md` | "See examples for real test predicates" |
| `predicates.md` | `architecture.md` | How predicates fit in the big picture |
| `io.md` | `python_integration.md` | `++()` escape for Python calls |
| `index.md` | `testing.md`, `dcg.md`, `exceptions.md`, `clpb.md` | Missing from "What's inside" table |

### scipy cross-links

Add a "See also" line at the bottom of each scipy page linking to related scipy modules. E.g.:

- `scipy_linalg.md` → `scipy_sparse.md` (sparse matrices)
- `scipy_optimize.md` → `scipy_linalg.md` (linear algebra solvers)
- `scipy_stats.md` → `scipy_special.md` (distribution functions)
- `scipy_signal.md` → `scipy_fft.md` (frequency domain)
- `scipy_ndimage.md` → `scipy_interpolate.md` (image resampling)

---

## Phase 7: Minor cleanups

- **mkdocs.yml line 3**: Change `site_url: https://clausal.example.io/` to a real URL or remove.
- **builtins.md**: Add a summary table at the top listing all predicates grouped by category, each linking to its section anchor.
- **syntax.md**: The file is 1051 lines. Consider splitting into subsections or adding a TOC note at the top pointing to key sections.
