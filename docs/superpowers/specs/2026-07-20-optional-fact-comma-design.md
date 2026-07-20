# Design: optional trailing comma for declared bodyless facts (+ diagnostic)

**Date:** 2026-07-20
**Status:** Approved (design), pending implementation plan
**Source bug:** `BUG-unterminated-fact-clause-misleading-error.md`

## Problem

In a `.clausal` module a **bodyless fact** is written with a trailing comma
(`edge(1, 2),`). The `EmbedTransformer` keys off that comma: with it, Python
parses the statement as a one-element `Tuple` and the transformer rewrites it to
`$define_predicate(...)`; without it, the statement is a bare `Call` (or `Name`)
that falls through to `generic_visit` and is **executed literally** at module
load.

Rules (`head <- (body)`) need no terminator, so facts and rules coexisting in one
module makes the missing fact-comma an easy slip. Dropping it has **two**
distinct failure modes, both present in the live test corpus:

| Case | Example | Today's behavior |
|------|---------|------------------|
| 1. Ground args | `counter(2)`, `GEdge("b","d")` | Bare call constructs and discards a term — fact **silently dropped**, no error. |
| 2. Non-ground args | `p(_, 1)`, `p(X, 1)` | `_`/`X` is unbound at module scope → misleading `name '_' is not defined`. |
| 3. Undeclared functor | `p(_ATOM, 1)` (no `-module`) | Functor `p` unbound → misleading `name 'p' is not defined`. |

Case 1 is worse than the filed bug: **no signal at all**. It was found in ≥9
fixture files (e.g. `tutorial_parallel_clausal_sig_tests.clausal`,
`indexing_sig_tests.clausal`, `thread_safe_predicates.clausal`, and six
`clausal-provenance` fixtures) as the **last fact of a fact block** — the author
comma-separated the block but omitted the final comma, so the last fact never
reached the database. Confirmed empirically: a three-line `counter` block asserts
only two clauses.

## Goals

- A declared predicate's bodyless fact may **omit the trailing comma** (comma
  becomes optional, symmetric with rules). Fixes cases 1 and 2.
- An **undeclared** bare fact that fails to load gets a **terminator-specific
  diagnostic** instead of a misleading `name '...' is not defined`. Fixes case 3.
- No change for legitimate non-fact bare calls (e.g. the load-time macro
  `bottom_up_(Edge)` imported via `-import_from`).

## Non-goals

- Recognizing a bare fact whose predicate is declared only **later** in the file
  (would require a two-pass pre-scan and reintroduces fact/expression ambiguity).
  The comma stays required in that ordering.
- Turning **undeclared** bare calls into facts. An undeclared bare call may be a
  legitimate imported callable; we cannot safely assume it is a fact.

## Design

### Part A — comma optional for declared predicates (transform time)

The disambiguator is `transformer._seen_functors`, already populated before the
fact line is reached by: `-module` export lists, `-dynamic`/`-private`
directives, and any prior clause/fact/rule for the same functor (so the
block-of-facts case is covered — earlier comma'd lines register the functor).

In `EmbedTransformer.visit_Expr`, add two `case`s, placed **after** the existing
`_clausal_star_query_` sentinel case and **before** the final
`return transformer.generic_visit(expr_stmt)`:

1. `case Call(func=Name(id=f), ...)` with `transformer._scope_depth == 0` and
   `f in transformer._seen_functors` → build a fact, identical to the existing
   trailing-comma `Tuple(elts=[single_element])` path.
2. `case Name(id=f)` with `scope_depth == 0`, `f in _seen_functors`, and
   `not _is_logic_var_name(f)` → build a zero-arity fact, identical to the
   existing `Tuple(elts=[Name])` path (A10-F011).

**Refactor to avoid divergence.** The trailing-comma fact-building body
(current lines ~2588–2660: field-name derivation, `_seen_functors` remapping,
`_unseat_directive_minted`, term transformation, head construction, the
`$define_predicate` statement, and first-time `_make_functor_class_ast`) is
extracted into a shared helper, e.g.:

```
transformer._build_fact_statements(func_name, pos_args, kw_args, anchor, src_node, expr_stmt)
    -> list[stmt]     # [functor_class_def?, define_stmt]
```

Both the existing `Tuple` fact cases and the two new bare cases call it. The
`Tuple` cases keep their current guards; only the fact-construction body moves.

The gate matters: `bottom_up_` (imported, not a declared predicate) is absent
from `_seen_functors`, so `bottom_up_(Edge)` stays a plain call. Declared
predicates are never legitimately "called for side effects" at module level, so
converting a bare declared call to a fact is safe.

Directives that register into `_seen_functors` (module exports, dynamic,
private, and prior clauses) enable the optional comma. `-table`,
`-discontiguous`, and `-shallow` do **not** currently populate `_seen_functors`;
a bare fact under one of those without a prior clause keeps requiring the comma.
This is acceptable (rare) and explicitly out of scope; note it in tests.

### Part B — diagnostic for the undeclared case (load time)

After Part A, the only bare `Call`/`Name` statements left unconverted have
**undeclared** functors. Among these, legitimate imported macros (`bottom_up_`)
execute successfully; genuine forgotten-comma facts raise `NameError` (on the
functor, or on an unbound arg like `_`). So catch at the point of failure:

In the loader — `_run_v2_pipeline` (V2) and `_exec_module_v1` (V1) — wrap
`exec(code, module_dict)`:

```
try:
    exec(code, module_dict)
except NameError as e:
    lineno = _last_module_frame_lineno(e.__traceback__, filename)
    line = _read_source_line(filename, lineno)
    if lineno and _looks_like_unterminated_fact(line):
        raise NameError(
            f"{e.args[0]}\n"
            f"  hint: {filename}:{lineno}  {line.strip()!r} looks like a "
            f"bodyless fact missing its trailing ','. Add a comma to make it a "
            f"fact, or declare the predicate (-module/-dynamic)."
        ).with_traceback(e.__traceback__) from e
    raise
```

Helpers (module-private, in `import_hook.py`):
- `_last_module_frame_lineno(tb, filename)` — walk the traceback to the deepest
  frame whose `co_filename == filename`; return its `lineno` (or `None`).
- `_read_source_line(filename, lineno)` — read one line from source; `""` on
  failure.
- `_looks_like_unterminated_fact(line)` — cheap check on the single line: strip
  trailing comment; it is non-empty, does **not** end with `,`, is **not** a
  directive (does not start with `-`), contains no `<-`/`>>`/`:-`, and parses as
  a bare `Call` with a `Name` func or a bare `Name`. A per-line `ast.parse` in a
  `try/except` is sufficient and only runs on the error path.

Properties: additive (original `NameError` message preserved), fires only on an
actual failure (successful macro calls untouched), and works on both the fresh
and `.pyc`-cache load paths because it re-reads source by line number rather
than relying on transformer state.

## Test plan (TDD — tests first, each must fail before the fix)

New fixtures under `tests/fixtures/` + a `tests/test_*` driver:

**Part A (semantics):**
- Declared-via-`-module` bare fact with non-ground arg (`p(_, 1)`) loads and is
  queryable — the canonical repro.
- Block of facts, last one comma-less (`counter(0), counter(1), counter(2)`),
  under `-dynamic` → all three clauses in the DB (regression for the silent drop).
- Bare fact declared by a prior comma'd clause of the same functor → asserted.
- Zero-arity declared bare fact (`flag`) → asserted.
- Ground and non-ground; `_`, `_ATOM`, `True`/`False` in head position (per the
  bug file's "all pass with the comma" table) → identical results with/without
  the comma.
- Negative: `bottom_up_(Edge)` (imported, undeclared) stays a call — the
  provenance fixtures still pass unchanged.
- Negative: a bare fact whose functor is declared only **later** still requires
  the comma (documents the single-pass boundary).

**Part B (diagnostic):**
- Undeclared bare fact (`p(_ATOM, 1)`, no `-module`) → load error message
  contains the terminator hint and the offending line text; still a `NameError`
  subtype/`<load>` failure.
- Legit undeclared call that succeeds is not rewritten and raises nothing.

**Corpus regression:**
- Full suite (`tests/`, `packages/*/tests/`) green. Specifically reconcile any
  test asserting an **exact** solution count against a fact block whose final
  fact was previously silently dropped and now lands. Update those fixtures/tests
  to reflect the (correct) additional fact; call out each change.

## Risks

- **Newly-landing facts shift counts.** The ≥9 fixtures gain their dropped final
  fact. Tests asserting exact counts may need updating — the corpus run surfaces
  them; each change is intentional and noted.
- **Traceback line number accuracy (Part B).** Compiled AST preserves source
  locations; the deepest module-frame lineno is the failing statement. If a line
  cannot be resolved, the diagnostic is skipped and the original error stands
  (never worse than today).
- **Refactor scope (Part A).** Extracting `_build_fact_statements` touches the
  hot trailing-comma path. The existing fact tests must stay green with no
  behavioral change on the comma'd path.

## Files touched

- `clausal/templating/term_rewriting.py` — `visit_Expr`: extract
  `_build_fact_statements`, add the two bare-fact cases.
- `clausal/import_hook.py` — loader `exec` wrapping + three private helpers.
- `tests/fixtures/*.clausal` and `tests/test_*.py` — new coverage; reconcile
  count-sensitive corpus fixtures.
