# Fable Partition Audit — Design Spec

> **Audit principle:** log *every* issue you find — correctness, design,
> performance, memory, or doc-drift. Design-level contradictions and
> ambiguities are first-class: they are tracked and *dealt with* (resolved from
> the docs, or by asking the user in-session), not just noted. This round
> produces, per subsystem, a code-findings ledger, a design-questions ledger,
> and an adversarial test suite. It does **not** fix production code; code
> triage and remediation happen after the user reviews the findings.

**Date:** 2026-07-05
**Author:** Michael Amy (with Claude)
**Status:** Draft — pending user review before plan-writing

---

## Goal

Audit the entire `clausal` Python package by partitioning it into 11 disjoint
subsystems and running one **Fable** agent per subsystem, then a final seams &
synthesis session (#12) that covers the interfaces between subsystems and
consolidates the results. Each agent hunts for issues against a shared rubric
plus subsystem-specific hotspots, confirms each correctness finding by running
an adversarial pytest, and writes three artifacts: a code-findings ledger, a
design-questions ledger, and an adversarial test file.

This is an **audit-only** round (findings + tests, no fix commits) with one
exception: design contradictions/ambiguities are resolved in-session with the
user and recorded. The deliverable of the *planning* work is a spec plus 12
ready-to-paste agent prompts; **the user launches each as its own interactive
Fable session** (not this session).

---

## Background

Clausal has an established audit convention from the 2026-05-25 string audit:

- A design spec in `docs/superpowers/specs/`.
- A findings ledger tree under `docs/superpowers/audits/<date>-<topic>/` with
  `README.md`, `findings.md`, and `probes/`.
- An adversarial pytest suite under `tests/audit_<date>/`, organised as
  `test_class_CNN_*.py` files, each pinning a set of findings (`F0NN`).

The prior audit found real bugs (refcount errors, Liskov/type-promotion gaps,
mode-matrix blind spots). The user's working hypothesis is that similar
classes of bug exist across the rest of the codebase, and that unhappy-path /
mode coverage is thin outside the string surface. This round generalises that
methodology to the whole package.

### Authoritative semantics reference: the Clausal cheat-sheet

`/workspace/clausify/docs/clausal-cheatsheet.md` (729 lines) is a dense,
construct-by-construct map of *idiomatic, correct* Clausal, with **runnable**
examples that were executed against the interpreter in `/workspace/clausal`.
It is the closest thing to a ground-truth spec of *intended* behavior and is
the primary reference for rubric class 1 (semantics vs. documentation). Every
agent MUST read it before auditing and treat it as authoritative for the
contracts it covers, including:

- Cut-free by design: **no `!/0`, `(->)/2`, `(*->)/2`** — replaced by disjoint
  guarded clauses, first-arg indexing, reified `If(C,T,E)`, `dif/2`, `once/1`.
- Unification is `is` (not `=`); `==` posts a CLP(ℤ) constraint (multi-mode),
  `:=` is eager Python eval; `!=` is arithmetic disequality; `X is not Y` →
  `dif/2`.
- Bare atoms are **strings**; facts end in a trailing comma, rules use `<-`
  with parenthesized multi-goal bodies; DCG uses `>>`.
- Builtin naming: PascalCase / full words, no abbreviations (`list_item/3` is
  0-based `nth0`; there is no `nth1`; SWI `succ` → `succ/2`).

Caveats: sections marked *(unverified)* are documentation-derived, not
executed — treat as weaker evidence. A live `todo/cheatsheet-remove-python-
escapes.md` indicates the `++()` / `:=` escape guidance is being revised, so
prefer the cheat-sheet's verified relational idioms over escape-based examples
when they conflict. The cheat-sheet lives in the sibling **clausify** repo
(read-only for this audit); do not modify it.

### Other standing constraints (from project memory)

- `==` is **arithmetic** equality (Prolog `=:=`), not structural.
- A string **is** a list of single-character strings (Liskov substitution).
- Clausal is logic programming *in Python* — not a Prolog clone; features
  Python already provides are intentionally omitted.
- The original **CLP(Q)** port is known-incorrect; SICStus/Scryer is the
  canonical reference.
- The full `pytest tests/` run **SIGKILLs (OOM)** on the 3.9 GB box — agents
  MUST run pytest **per-file**, never the whole suite.
- `_query_cache` in `solve.py` keys by arg *types*; back-to-back solves with
  differing non-Var args need a cache clear.

---

## Approach (chosen: A — uniform partition + shared rubric)

Partition the whole package into disjoint subsystems, give every agent the same
rubric plus a prewritten per-subsystem "known contracts & hotspots" block, and
have each write to **disjoint** output paths so the agents can run in parallel
without git-worktree isolation.

Rejected alternatives:
- **B — bespoke per-subsystem specs.** ~11 mini-brainstorms; overkill when the
  deliverable is findings+tests, not remediation.
- **C — risk-prioritized top-N.** Contradicts the "everything, partitioned"
  decision; kept only as a fallback if cost becomes a concern.

---

## Partition (11 subsystems)

C extension cores are folded into their owning subsystem. Sizes are approximate
current line counts.

| # | Audit | Primary files |
|---|-------|---------------|
| 1 | Term layer & C unification | `terms.py`, `pythonic_terms.py`, `variables/_variables.c`, SegList/SegString/VarSeg machinery |
| 2 | Compiler: heads & indexing | `compiler/head_match.py`, `arg_index.py`, `terms_to_ast.py`, `terms_to_goalop.py`, `ir.py`, `list_dispatch.py` |
| 3 | Compiler: goals, control & specialization | `compiler/predicate.py`, `goal_shallow.py`, `goal_trampoline.py`, `control_constructs.py`, `ite_reified.py`, `tabled_naf.py`, `specialization.py`, `optimisations/`, `tro.py`, `destructive_reuse.py` |
| 4 | Runtime, search & tabling | `solve.py`, `trampoline.py` (+`_trampoline.c`), `continuation_search.py`, `coroutining.py`, `tabling.py` (+`_tabling_core.c`), `runtime/*` (+`_list_unify.c`) |
| 5 | Constraints core | `constraints.py` (+`_constraints_dif.c`), `reif.py`, `units_constraint.py`, `builtins/attributes.py` |
| 6 | CLP(FD) | `clpfd.py`, `_clpfd_core.c`, `_clpfd_propagate.c`, FD builtin surface |
| 7 | CLP(B) & SAT | `clpb.py` (+`_clpb_core.c`), `clpsat.py`, `builtins/sat_constraints.py` |
| 8 | CLP(Q/R) & Z3/ortools | `clpq.py`, `clpr.py` (+`_clpr_core.c`), `clpz3.py`, `clportools*`, `builtins/z3_constraints.py`, `builtins/ortools_constraints.py` |
| 9 | Builtins & stdlib predicates | `builtins/*` (lists, higher_order, arithmetic, io, inspection, type_checks, chars +`_chars_core.c`, dict_set, pairs, dcg, database_ops, keyword_ops, control, translations_builtin) |
| 10 | Term rewriting, templating & import | `templating/*` (esp. `term_rewriting.py`), `import_hook.py`, `_lazy_hook.py`, `codegen.py`, `goal_expansion.py`, `pythonic_ast/*` |
| 11 | Modules, interop & Prolog tools | `modules/*` (incl. `py/*`), `regex.py`, `reflection.py`, `tools/prolog_*`, `prolog_backends/` |

Disjointness note: the FD/B/SAT/Q/R/Z3 builtin *adapters* live under
`builtins/` but are audited with their solver (6–8), while the general-purpose
builtins are audit 9. Each agent prompt names its exact file list to prevent
overlap.

---

## Shared rubric (all 11 agents)

Log every issue; write adversarial tests for the correctness ones. Issue
classes:

1. **Semantics vs. documentation** — behavior contradicting docstrings, `docs/`,
   the **Clausal cheat-sheet** (see above), or standing contracts (arithmetic
   `==`, strings-as-lists, comma-not-`and`, cut-free).
2. **Mode / groundness coverage** — input vs output modes, partial terms,
   unbound-var args, the polymorphic mode matrix.
3. **Edge cases** — empty/singleton/cyclic inputs, backtracking & trail
   restoration, deep recursion, re-entrancy.
4. **C-extension safety** (subsystems with `.c`) — refcount / leak / borrowed-ref
   bugs, `Trail_Check` before `Trail_CAST`, error-path cleanup, free-threading
   (FT) safety.
5. **Error handling** — silent failure vs proper `throw/1`, exception term
   shape, resource cleanup on the failure path.
6. **Cross-module interaction & seams** — composition with tabling, dif, CLP,
   DCG, *and the interfaces between subsystems* (compiler-emits ↔
   runtime-consumes, `terms.py` dunders ↔ the C unifier, tabling ↔ dif). Seam
   bugs are the ones a strict partition is most likely to drop: each side
   assumes the other is correct. Each agent declares the upstream contracts it
   *depends on* and the downstream contracts it *provides*, and writes at least
   one test that crosses each boundary it touches. Anything still ambiguous at a
   boundary is handed to the seams & synthesis session (#12).
7. **Design contradictions & ambiguities** — first-class, not a footnote. A
   design issue is any place where the *design itself* is unsound or
   under-specified, independent of whether the code has a bug: two docs (or a
   doc and the cheat-sheet) that specify incompatible behavior; a contract that
   is silent on a case the code must handle (so the implementation picks a
   behavior by accident); an abstraction whose boundary leaks (a "unit" whose
   internals can't change without breaking consumers); an API that is
   internally inconsistent with its siblings; or a semantics that is defensible
   two different ways with no recorded decision. These are tracked and *dealt
   with*, not merely noted (see method + output below).

---

## Per-agent method: deep, run-to-confirm, resolve-design-issues

- **Coverage-map first, then deep (loop-until-dry).** Before probing, the agent
  emits a **coverage map** for its subsystem: the public functions/predicates ×
  the dimensions to exercise (input vs output mode, ground vs partial vs unbound
  args, empty/singleton/cyclic inputs, backtracking, error paths). "Dry" is
  defined *against this map* — the loop repeats until the map is covered AND a
  full pass surfaces nothing new, not merely "found nothing this pass" (which
  quits early on huge files like `term_rewriting.py`). Backstops: stop after 2
  consecutive dry passes or a per-session token budget, whichever first. Cores
  (audits 1–4) warrant the most passes. The mode dimension is not optional — a
  numeric-head-literal bug survived 8085 tests because every test used input
  mode only (`todo/audit-tests-input-output-mode-coverage.md`).
- **Run to confirm:** every correctness finding must be reproduced by an
  executed pytest before it is logged as confirmed. Runs are **per-file**
  (`pytest tests/audit_2026_07_05/test_NN_*.py`) — never the whole suite (OOM).
  Findings that cannot be reproduced are logged as **unconfirmed** with a note.
- **Differential oracles (where one exists).** Reasoning about code is weaker
  than diffing it against an external ground-truth. Where a reference is
  available, the agent generates inputs and compares outputs:
  - `modules/py/*` wrappers → Python's own stdlib (`csv`, `json`, `datetime`,
    `hashlib`, `re`, `sqlite3`, …) is the exact oracle.
  - CLP(Z3)/Z3 constraints → the `z3` package directly.
  - CLP(Q/R) → **known-incorrect**; SICStus/Scryer is canonical. Prolog oracles
    live under `prolog_backends/{gprolog,scryer}` as *sources* — **no binary is
    on PATH**, so the agent checks availability first and, if the backend can't
    be built/run, logs the divergence class it *would* test as an open item
    rather than skipping silently.
  This mirrors clausify's `docs/adversarial-verification/fable-oracle-prompts/`
  differential pattern.
- **C-finding verification toolkit** (audits owning `.c`: 1, 4, 5, 6, 7, 8, 9).
  pytest alone can't confirm a leak or an FT bug. Concrete methods:
  - Refcount/leak: `sys.getrefcount` deltas and `gc.get_objects()` /
    `tracemalloc` snapshots across a stress loop (N×1000 iterations); a stable
    plateau is the pass condition, monotonic growth the finding.
  - Trail/borrowed-ref/error-path: exercise the failure path (pass a non-Trail
    object, force an allocation failure where reachable) — cross-reference the
    already-catalogued patterns in `todo/cross_cutting_issues.md` (Trail_Check,
    unchecked `PyObject_IsInstance` -1 returns) rather than re-discovering them.
  - **Free-threading:** this box runs a **GIL build (3.13)**; FT claims can only
    be *executed* on the `.cpython-314t` free-threaded build. If it isn't
    available in-session, FT findings are reasoned about statically (against
    `_ft_compat.h`) and logged **unconfirmed — needs 3.14t** rather than
    asserted.
- **Resolve design issues interactively.** Each audit runs in its **own
  interactive session**, so the agent is expected to *ask the user* when it hits
  a design-level contradiction or ambiguity it cannot resolve from the docs +
  cheat-sheet. The loop per design issue:
  1. State the issue, the conflicting sources, and 2–3 candidate resolutions
     with trade-offs and a recommendation.
  2. **First check `DESIGN-DECISIONS.md`** — an earlier session may have already
     resolved the same (often cross-cutting) question; if so, cite it and skip
     the ask. Otherwise ask the user (a real question — not a headless subagent).
  3. Record the user's decision, its rationale, and any follow-up work in the
     subsystem's `design-questions.md`, and append cross-cutting decisions to
     `DESIGN-DECISIONS.md` so later sessions see them.
  Design issues the agent *can* resolve unambiguously from the cheat-sheet/docs
  are logged with the resolution and the citation, no question needed. Design
  issues that are out of the agent's scope to decide, or that the user defers,
  are logged as **open** with enough context for later triage. A design finding
  never blocks the correctness pass — log it and continue.

---

## Output layout

```
docs/superpowers/audits/2026-07-05-fable-partition/
  README.md                        # index: partition table, rubric, per-audit status
  DESIGN-DECISIONS.md              # rolled-up log of design issues + user decisions
  01-term-layer/
    findings.md                    # code-level findings ledger
    design-questions.md            # design contradictions/ambiguities: resolved + open
  02-compiler-heads/
    findings.md
    design-questions.md
  ...
  11-modules-interop/
    findings.md
    design-questions.md
  12-seams/                        # session 12: cross-subsystem seam findings
    findings.md
tests/audit_2026_07_05/
  __init__.py
  conftest.py
  test_01_term_layer.py         # one adversarial file per audit
  test_02_compiler_heads.py
  ...
  test_11_modules_interop.py
  test_12_seams.py              # session 12: boundary-crossing tests
```

`findings.md` ledger row format (stable across all audits):

```
| ID | Severity | Title | Location (file:line) | Repro | Expected vs Actual | Test ref |
```

- **ID is namespaced per subsystem** to avoid collisions across the 11 parallel
  sessions: `A<NN>-F<NNN>` (e.g. `A04-F007` = audit 4, finding 7). Design-question
  IDs use `A<NN>-D<NNN>`.
- Severity: `correctness` > `memory` > `design` > `perf` > `doc-drift`.
- Confirmed correctness findings get a test in the subsystem's test file.
- Suspected-but-unreproduced findings are marked `xfail(strict=False)`; findings
  that pin confirmed-correct behavior are plain regression guards.
- The suite must stay **green** on a per-file run after the audit.

`design-questions.md` row format (design contradictions/ambiguities):

```
| ID | Status | Title | Conflicting sources | Options considered | Decision + rationale | Follow-up |
```

- Status: `resolved-from-docs` (cite the doc/cheat-sheet), `resolved-by-user`
  (record the decision), or `open` (needs a decision the user deferred or that
  is out of scope for this round).
- `DESIGN-DECISIONS.md` at the audit root aggregates every `resolved-by-user`
  and `open` row across all 11 subsystems into one triage list, so cross-cutting
  design conflicts (e.g. a contract that two subsystems read differently) are
  visible in one place.

---

## Launch model

- **Each audit runs in its own interactive session**, launched by the user (not
  this session), using **Fable** as the session model. This is deliberate: an
  interactive session lets the agent ask the user to resolve design-level
  contradictions/ambiguities in real time (the design-issues loop above), which
  a headless subagent could not do. The implementation plan provides 11
  ready-to-paste prompt blocks — one per session.
- The prompt opens with required reading, before any code reading:
  1. `/workspace/clausify/docs/clausal-cheatsheet.md` (intended semantics).
  2. The subsystem's own docstrings and `docs/`.
  3. **Prior art for this subsystem** — the relevant slices of
     `todo/cross_cutting_issues.md`, `todo/audit-tests-input-output-mode-
     coverage.md`, `tests/audit_2026_05_25/`, `DUPLICATE_TESTS.md`, and any
     matching `implementation_plans/*/todo/*audit*`. Known issues are **not**
     re-reported; the agent references the existing entry and moves on.
  4. The current `DESIGN-DECISIONS.md` (may be empty for the first sessions).
- Each session writes only to its own disjoint audit + test paths, so multiple
  sessions can run concurrently without conflict. Because each is interactive
  and may block on a user question, run as many in parallel as you can attend
  to — a few at a time is realistic.
- Recommended order: core engine first (1 → 4), then constraints (5 → 8), then
  builtins/rewriting/modules (9 → 11). Cross-cutting design questions surfaced
  by the early core sessions may pre-answer questions in later ones — landing
  their decisions in `DESIGN-DECISIONS.md` first reduces duplicate questions.

### Session 12 — seams & synthesis (runs last)

A final interactive Fable session, launched after 1–11 complete, that does what
no single partition audit can:

- **Seams:** pick up every boundary ambiguity handed off by audits 1–11, and
  probe the interfaces the partition split apart (compiler↔runtime,
  terms↔C-unifier, tabling↔dif↔CLP composition). Writes seam findings and a
  `test_12_seams.py` file.
- **Synthesis:** dedup findings across all 11 ledgers, cull false positives
  (re-run the repro; downgrade what doesn't reproduce), and merge the
  cross-cutting design questions into `DESIGN-DECISIONS.md` with a single
  triage-ready ordering.
- **Memory:** capture confirmed design decisions that are now standing contracts
  into project memory (`/home/node/.claude/projects/-workspace-clausal/memory/`)
  so future work inherits them, per the memory convention.

---

## Scope boundaries

**In:** every `.py` and owning `.c` file listed in the partition table;
findings ledgers; adversarial per-file test suite.

**Out:** production-code fixes (deferred to post-review triage); pure-perf
remediation (log only); benchmarks/`benchmarks/`; docs prose rewrites;
the `packages/` extracted distributions except where they mirror an audited
core file.

---

## Success criteria

- All 11 code-findings ledgers + a session-12 seam ledger written, each with a
  status line in the audit README.
- All 11 design-questions ledgers written; `resolved-by-user` and `open` items
  rolled up (and deduped by session 12) into `DESIGN-DECISIONS.md`.
- One adversarial test file per subsystem plus `test_12_seams.py`; per-file
  `pytest` runs are green.
- Every confirmed correctness finding has a reproducing test reference; C
  findings use the C toolkit (or are flagged `unconfirmed — needs 3.14t` for FT).
- Session 12 has deduped across ledgers, culled false positives, and captured
  standing design decisions into project memory.
- 12 ready-to-paste agent prompts delivered (11 subsystem + 1 seams/synthesis)
  so the user can launch each as its own interactive Fable session.
