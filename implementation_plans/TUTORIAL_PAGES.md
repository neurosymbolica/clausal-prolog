# Tutorial Pages Plan

Create tutorial-quality pages for every Clausal feature. Some pages already exist
and need upgrading; others are new.

**Principle**: each page should teach *one feature area* with motivation, syntax,
worked examples, gotchas, and links. Not a reference dump — a tutorial a reader
can follow top-to-bottom.

**Style rules** (apply to every page):

- `.clausal` code in ` ```clausal ` fences; Python in ` ```python `
- Variables ALLCAPS: `X`, `NAME`, `RESULT`
- Predicate names TitleCase: `append`, `findall`
- Comma-separated goals, multi-goal bodies always parenthesized
- Python only in "query it from Python" boxes (2–4 lines max)
- No internal API (PredicateMeta, Var, deref, Trail, Module) unless the page
  is explicitly about internals
- Each page ends with "See also" cross-links

---

## Page inventory

Status key: **NEW** = create from scratch, **UPGRADE** = existing page needs
tutorial narrative added, **OK** = existing page is already tutorial quality
(light polish only).

### Getting Started

| # | Page | File | Status | Notes |
|---|------|------|--------|-------|
| 1 | Tutorial | `tutorial.md` | OK | Already 377 lines, good narrative. Light polish only. |

### Core Language

| # | Page | File | Status | Notes |
|---|------|------|--------|-------|
| 2 | Predicates & Rules | `predicates.md` | UPGRADE | 227 lines. Add: guards, multi-clause dispatch, `-private`, worked example (family tree → graph reachability). |
| 3 | Syntax Reference | `syntax.md` | OK | 1066 lines, comprehensive. Fix issues per DOCS_IMPROVEMENT_PLAN Phase 1. |
| 4 | If-Then-Else | `reified_ite.md` | OK | 276 lines, thorough. |
| 5 | Lambdas & Closures | `lambdas.md` | OK | 282 lines, well-explained. |
| 6 | DCGs | `dcg.md` | UPGRADE | 238 lines. Add: state threading section (state/1, state/2, counter/accumulator patterns from V2-17b). Reference `dcg_state.clausal` example. |
| 7 | Exception Handling | `exceptions.md` | OK | 254 lines, good coverage. |
| 8 | Directives | `directives.md` | UPGRADE | 185 lines. Add: intro paragraph motivating each directive, one example per directive showing the problem it solves. |
| 9 | Dicts & Sets | `dicts_sets.md` | OK | 472 lines, comprehensive. |

### Builtins

| # | Page | File | Status | Notes |
|---|------|------|--------|-------|
| 10 | Type Checking | — | NEW | `var`, `nonvar`, `is_str`, `number`, `integer`, `float_`, `compound`, `callable_`, `is_list`, `ground`. when to use each, common patterns. |
| 11 | Arithmetic | — | NEW | `between`, `succ`, `plus`, `abs_`, `max_`, `min_`, `sign`, `gcd`, `divmod_`. Also `:=` evaluation, comparison operators. |
| 12 | Lists | — | NEW | All 24 list predicates. Group by: construction, access, search, sorting, set ops, aggregation. Worked examples: flatten a tree, rotate a list, partition. |
| 13 | Pairs | — | NEW | `pairs_keys_values`, `pairs_keys`, `pairs_values`. Short page — show key-value processing patterns. |
| 14 | Higher-Order | — | NEW | `maplist/2,3`, `include`, `exclude`, `foldl`, `take_while`, `drop_while`, `span`, `group_by`, `sort_by`, `max_by`, `min_by`, `filter_map`. Show with lambdas. |
| 15 | Meta-Predicates | `meta_predicates.md` | UPGRADE | 224 lines. Add: `bagof` existential quantification (`X^Goal`), `setof` vs `sort(findall(...))` comparison, `forall` patterns. Ensure `Call/1..8` is covered. |
| 16 | I/O | `io.md` | UPGRADE | 83 lines → expand to ~200. Add: f-string worked examples, print_term vs write vs writeln comparison table, formatting patterns (tables, aligned output). |
| 17 | Term Inspection | — | NEW | `functor`, `arg`, `unpack`, `copy_term`, `term_variables`, `numbervars`. Meta-programming patterns: term rewriting, variable renaming. |
| 18 | Database Ops | — | NEW | `assertz`, `asserta`, `retract`, `abolish_table`, `abolish_all_tables`. Dynamic predicates, `-dynamic` directive, assert/retract patterns (memo, state). |
| 19 | Keyword Predicates | — | NEW | `vary`, `extend`, `unbound_keys`, `signature`. KWTerm, Python keyword syntax `foo(x=1, y=2)`, partial terms. |
| 20 | Control | — | NEW | `time_goal/1,2`, `once/1`. Benchmarking patterns. Short page. |

### Constraints

| # | Page | File | Status | Notes |
|---|------|------|--------|-------|
| 21 | dif & CLP(FD) | `constraints.md` | OK | 594 lines, good. |
| 22 | CLP(B) | `clpb.md` | OK | 221 lines, solid. |
| 23 | CLP(R) | `clpr.md` | OK | 356 lines, good. |

### Advanced Features

| # | Page | File | Status | Notes |
|---|------|------|--------|-------|
| 24 | Module System | `import.md` | OK | 257 lines, comprehensive. |
| 25 | Regex | `regex.md` | UPGRADE | 145 lines → ~250. Add: more auto-binding examples, practical patterns (log parsing, CSV extraction, URL routing), combination with `findall` for iteration. |
| 26 | Term & Goal Expansion | `term_expansion.md` | UPGRADE | 123 lines → ~250. Add: real-world example (auto-logging, clause counting), one-to-many expansion walkthrough, module state example. |
| 27 | Python Interop | `python_integration.md` | UPGRADE | 403 lines. Restructure: lead with `++()` escape and `import`/`query()`, push low-level API (Trail, Var, deref) into collapsible section. |
| 28 | Tabling | `tabling.md` | OK | 370 lines, well-explained. |
| 29 | Well-Founded Semantics | `wfs.md` | UPGRADE | 115 lines → ~200. Add: second worked example (even/odd mutual recursion), explanation of "undefined" in practice, when WFS vs NAF. |

### Internals (light-touch — these are for contributors)

| # | Page | File | Status | Notes |
|---|------|------|--------|-------|
| 30 | Indexing & Dispatch | `indexing.md` | OK | 691 lines, comprehensive deep-dive. |
| 31 | Bytecode Caching | `caching.md` | OK | 129 lines, adequate for internals. |
| 32 | Architecture | `architecture.md` | OK | 206 lines, good overview. |
| 33 | Compiler | `compiler.md` | OK | Internals reference. |
| 34 | Specialization | `specialization.md` | OK | Internals reference. |

### Standard Library (non-scipy)

These already exist and are adequate reference pages. Light polish only.

| # | Page | File | Status |
|---|------|------|--------|
| 35 | Date & Time | `date_time.md` | OK |
| 36 | YAML | `yaml.md` | OK |
| 37 | SQLite | `sqlite.md` | OK |
| 38 | spaCy NLP | `spacy.md` | OK |
| 39 | UUIDs | `uuid.md` | OK |
| 40 | Graphs | `graphs.md` | OK |
| 41 | scikit-learn | `sklearn.md` | OK |
| 42 | SymPy | `sympy.md` | OK |
| 43 | Units | `units.md` | OK |
| 44 | Logging | `logging.md` | OK |

### SciPy Library

These already exist as reference pages. They follow a consistent pattern and are
adequate. No tutorial rewrite planned unless requested.

| # | Page | File | Status |
|---|------|------|--------|
| 45 | scipy.special | `scipy_special.md` | OK |
| 46 | scipy.linalg | `scipy_linalg.md` | OK |
| 47 | scipy.optimize | `scipy_optimize.md` | OK |
| 48 | scipy.stats | `scipy_stats.md` | OK |
| 49 | scipy.integrate | `scipy_integrate.md` | OK |
| 50 | scipy.interpolate | `scipy_interpolate.md` | OK |
| 51 | scipy.fft | `scipy_fft.md` | OK |
| 52 | scipy.ndimage | `scipy_ndimage.md` | OK |
| 53 | scipy.spatial | `scipy_spatial.md` | OK |
| 54 | scipy.constants | `scipy_constants.md` | OK |
| 55 | scipy.differentiate | `scipy_differentiate.md` | OK |
| 56 | scipy.signal | `scipy_signal.md` | OK |
| 57 | scipy.sparse | `scipy_sparse.md` | OK |
| 58 | scipy.cluster | `scipy_cluster.md` | OK |

---

## Work items (priority order)

### Batch 1: New builtin tutorial pages (biggest gap)

These predicates are only documented in `builtins.md` (a 2390-line reference
dump). Each needs its own tutorial page.

1. **Lists** (#12) — largest predicate group (24), most commonly used
2. **Arithmetic** (#11) — foundational, needed early
3. **Higher-Order** (#14) — key differentiator, pairs with lambdas
4. **Type Checking** (#10) — simple, quick to write
5. **Term Inspection** (#17) — meta-programming gateway
6. **Database Ops** (#18) — dynamic predicates, assert/retract
7. **Pairs** (#13) — short page, quick win
8. **Keyword Predicates** (#19) — unique Clausal feature
9. **Control** (#20) — short page (time_goal, once)

### Batch 2: Upgrade existing pages

10. **I/O** (#16) — 83 → ~200 lines
11. **Regex** (#25) — 145 → ~250 lines
12. **Term & Goal Expansion** (#26) — 123 → ~250 lines
13. **WFS** (#29) — 115 → ~200 lines
14. **DCGs** (#6) — add state threading section
15. **Predicates** (#2) — add tutorial narrative
16. **Directives** (#8) — add motivation & examples
17. **Meta-Predicates** (#15) — expand bagof/setof/forall
18. **Python Interop** (#27) — restructure for .clausal-first audience

### Batch 3: mkdocs.yml nav update

After all pages are created/upgraded, update `mkdocs.yml` nav:

```yaml
nav:
  - Home: index.md
  - Getting Started:
    - Project Goals: goals.md
    - Tutorial: tutorial.md
    - Syntax: syntax.md
    - Testing: testing.md
  - Language:
    - Predicates: predicates.md
    - Lambdas: lambdas.md
    - If-Then-Else: reified_ite.md
    - DCGs: dcg.md
    - Dicts and Sets: dicts_sets.md
    - Exceptions: exceptions.md
    - Directives: directives.md
  - Builtins:
    - Predicate Index: builtins.md
    - Type Checking: type_checking.md        # NEW
    - Arithmetic: arithmetic.md              # NEW
    - Lists: lists.md                        # NEW
    - Pairs: pairs.md                        # NEW
    - Higher-Order: higher_order.md          # NEW
    - Meta-Predicates: meta_predicates.md
    - Term Inspection: term_inspection.md    # NEW
    - Database Operations: database_ops.md   # NEW
    - Keyword Predicates: keyword_preds.md   # NEW
    - Control: control.md                    # NEW
    - I/O: io.md
    - Logging: logging.md
  - Constraints:
    - dif & CLP(FD): constraints.md
    - CLP(B): clpb.md
    - CLP(R): clpr.md
  - Standard Library:
    # ... (unchanged)
  - Advanced:
    - Module System: import.md
    - Regex: regex.md
    - Term & Goal Expansion: term_expansion.md
    - Python Interop: python_integration.md
    - Tabling: tabling.md
    - Well-Founded Semantics: wfs.md
  - Internals:
    - Architecture: architecture.md
    - Compiler: compiler.md
    - Indexing: indexing.md
    - Caching: caching.md
    - Specialization: specialization.md
  - Prolog Translation: prolog_translation.md
  - IPython / Jupyter: ipython.md
  - Examples: examples.md
```

---

## Per-page template

Each new tutorial page should follow this structure:

```markdown
# {Feature Name}

One-paragraph intro: what this feature does, when you need it.

---

## Quick Example

One short, self-contained `.clausal` example showing the feature in action.

## {Predicate Group 1}

### PredicateName/Arity

**signature**: `PredicateName(Arg1, Arg2, Result)`

{1–2 sentence description}

```clausal
{example}
```

{Repeat for each predicate in the group}

## {Predicate Group 2}
...

## Patterns & Recipes

2–3 worked examples combining multiple predicates from this page.

## Gotchas

Common mistakes or surprising behavior.

---

*See also: [Related Page](related.md) — brief description.*
```

---

## Estimated scope

- **9 new pages** (Batch 1): ~150–300 lines each → ~1800 lines total
- **9 page upgrades** (Batch 2): ~50–150 lines added each → ~900 lines total
- **1 nav update** (Batch 3): mechanical edit to mkdocs.yml
- **Total**: ~2700 lines of new/revised documentation
