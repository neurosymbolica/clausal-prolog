Read `docs/superpowers/audits/2026-07-05-fable-partition/prompts/required_reading.md`
before any code or tool use — it defines your role, reading order, standing
contracts, method, and rules.

## Deliverables (write these paths)

- `docs/superpowers/audits/2026-07-05-fable-partition/08-clpqr-z3/findings.md`
  (from `_templates/findings.md`; IDs `A08-F001…`).
- `docs/superpowers/audits/2026-07-05-fable-partition/08-clpqr-z3/design-questions.md`
  (from `_templates/design-questions.md`; IDs `A08-D001…`).
- `tests/audit_2026_07_05/test_08_clpqr_z3.py` — adversarial tests. Suspected-bug tests
  use `@pytest.mark.xfail(strict=False)`; confirmed-correct behavior is a plain
  regression guard. The file must be **green** on a per-file run.
- Todos under `todo/audit-2026-07-05/`: `fix-A08-<slug>.md` (clear remediation)
  or `investigate-A08-<slug>.md` (Opus). Every confirmed finding needing a fix
  has exactly one; its ledger "Todo ref" points to it.
- Update this audit's row in
  `docs/superpowers/audits/2026-07-05-fable-partition/README.md` on completion.

---
## Subsystem A08 — CLP(Q/R), Z3 & ortools

**Files (stay within):** `clausal/logic/clpq.py`, `clausal/logic/clpr.py`,
`clausal/logic/clpz3.py`, `clausal/logic/clportools.py`,
`clausal/logic/clportools_lp.py`, `clausal/logic/clportools_graph.py`,
`clausal/logic/clportools_routing.py`, `clausal/logic/_clpr_core.c`,
`clausal/logic/builtins/z3_constraints.py`,
`clausal/logic/builtins/ortools_constraints.py`.

**Known-incorrect warning:** the original CLP(Q) implementation is **known to be
incorrect** — SICStus/Scryer is the canonical reference. Expect real bugs;
prioritize differential testing over reading.

**Hotspots:**
- Rational arithmetic exactness (`clpq.py`); simplex/projection correctness;
  entailment and satisfiability of linear systems.
- `clpr.py` float behavior and its C core.
- Z3/ortools adapters: constraint translation fidelity, result extraction.

**Oracle (strong here):**
- CLP(Z3) → the `z3` package directly: build the same constraints, compare
  sat/model.
- CLP(Q) → SICStus/Scryer via `prolog_backends/{gprolog,scryer}`. **No Prolog
  binary is on PATH** — check availability first; if it can't be built/run, log
  the divergence class you *would* test as an `investigate-*` todo (Opus),
  don't skip silently.
- Cross-check `docs/clpq.md`, `docs/clpr.md` intended vs actual.

**C toolkit:** `refcount_stable` over post/solve loops; audit `_clpr_core.c`.

**Seam notes for A12:** solver vars share the A01/A04 unifier and attribute hooks (A05).
