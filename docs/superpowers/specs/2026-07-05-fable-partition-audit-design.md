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

Audit the entire `clausal` Python package by partitioning it into ~11 disjoint
subsystems and running one **Fable** agent per subsystem. Each agent hunts for
issues against a shared rubric plus subsystem-specific hotspots, confirms each
correctness finding by running an adversarial pytest, and writes two artifacts:
a findings ledger and an adversarial test file.

This is an **audit-only** round (findings + tests, no fix commits). The
deliverable of the *planning* work is a spec plus 11 ready-to-paste agent
prompts; **the user launches the agents** (not this session).

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
6. **Cross-module interaction** — composition with tabling, dif, CLP, DCG.
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

- **Deep (loop-until-dry):** the agent repeats audit passes over its subsystem
  until a full pass surfaces nothing new (suggested cap: stop after 2
  consecutive dry passes, or a per-agent finding/token budget). Cores (audits
  1–4) warrant the most passes.
- **Run to confirm:** every correctness finding must be reproduced by an
  executed pytest before it is logged as confirmed. Runs are **per-file**
  (`pytest tests/audit_2026_07_05/test_NN_*.py`) — never the whole suite (OOM).
  Findings that cannot be reproduced are logged as **unconfirmed** with a note.
- **Resolve design issues interactively.** Each audit runs in its **own
  interactive session**, so the agent is expected to *ask the user* when it hits
  a design-level contradiction or ambiguity it cannot resolve from the docs +
  cheat-sheet. The loop per design issue:
  1. State the issue, the conflicting sources, and 2–3 candidate resolutions
     with trade-offs and a recommendation.
  2. Ask the user (a real question — this is not a headless subagent).
  3. Record the user's decision, its rationale, and any follow-up work in the
     subsystem's `design-questions.md`.
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
tests/audit_2026_07_05/
  __init__.py
  conftest.py
  test_01_term_layer.py         # one adversarial file per audit
  test_02_compiler_heads.py
  ...
  test_11_modules_interop.py
```

`findings.md` ledger row format (stable across all audits):

```
| ID | Severity | Title | Location (file:line) | Repro | Expected vs Actual | Test ref |
```

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
- The prompt opens with required reading:
  `/workspace/clausify/docs/clausal-cheatsheet.md` (intended semantics) plus
  the subsystem's own docstrings/`docs/` — before any code reading.
- Each session writes only to its own disjoint audit + test paths, so multiple
  sessions can run concurrently without conflict. Because each is interactive
  and may block on a user question, run as many in parallel as you can attend
  to — a few at a time is realistic.
- Recommended order: core engine first (1 → 4), then constraints (5 → 8), then
  builtins/rewriting/modules (9 → 11). Cross-cutting design questions surfaced
  by the early core sessions may pre-answer questions in later ones — landing
  their decisions in `DESIGN-DECISIONS.md` first reduces duplicate questions.

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

- All 11 code-findings ledgers written, each with a status line in the audit
  README.
- All 11 design-questions ledgers written; `resolved-by-user` and `open` items
  rolled up into `DESIGN-DECISIONS.md`.
- One adversarial test file per subsystem; per-file `pytest` runs are green.
- Every confirmed correctness finding has a reproducing test reference.
- 11 ready-to-paste agent prompts delivered so the user can launch each audit
  as its own interactive Fable session.
