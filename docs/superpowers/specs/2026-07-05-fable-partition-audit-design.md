# Fable Partition Audit — Design Spec

> **Audit principle:** log *every* issue you find — correctness, design,
> performance, memory, or doc-drift. This round produces a findings ledger
> and an adversarial test suite per subsystem. It does **not** fix production
> code; triage and remediation happen after the user reviews the findings.

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

---

## Per-agent method: deep, run-to-confirm

- **Deep (loop-until-dry):** the agent repeats audit passes over its subsystem
  until a full pass surfaces nothing new (suggested cap: stop after 2
  consecutive dry passes, or a per-agent finding/token budget). Cores (audits
  1–4) warrant the most passes.
- **Run to confirm:** every correctness finding must be reproduced by an
  executed pytest before it is logged as confirmed. Runs are **per-file**
  (`pytest tests/audit_2026_07_05/test_NN_*.py`) — never the whole suite (OOM).
  Findings that cannot be reproduced are logged as **unconfirmed** with a note.

---

## Output layout

```
docs/superpowers/audits/2026-07-05-fable-partition/
  README.md                     # index: partition table, rubric, per-audit status
  01-term-layer/findings.md
  02-compiler-heads/findings.md
  ...
  11-modules-interop/findings.md
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

---

## Launch model

- **User launches** the agents (not this session). The implementation plan
  provides 11 ready-to-paste prompt blocks.
- Each agent: `model: "fable"`, `subagent_type: general-purpose` (needs
  Read / Grep / Glob / Bash / Write).
- Every agent prompt opens with required reading:
  `/workspace/clausify/docs/clausal-cheatsheet.md` (intended semantics) plus
  the subsystem's own docstrings/`docs/` — before any code reading.
- Agents write only to disjoint audit + test paths → safe to run in parallel;
  no worktrees. Suggested batch size **4–5** concurrent to bound token burn.
- Recommended order: core engine first (1 → 4), then constraints (5 → 8), then
  builtins/rewriting/modules (9 → 11).

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

- All 11 findings ledgers written, each with a status line in the audit README.
- One adversarial test file per subsystem; per-file `pytest` runs are green.
- Every confirmed correctness finding has a reproducing test reference.
- 11 ready-to-paste agent prompts delivered so the user can launch each audit
  independently.
