Read `docs/superpowers/audits/2026-07-05-fable-partition/prompts/required_reading.md`
before any code or tool use — it defines your role, reading order, standing
contracts, method, and rules.

## Deliverables (write these paths)

- `docs/superpowers/audits/2026-07-05-fable-partition/02-compiler-heads/findings.md`
  (from `_templates/findings.md`; IDs `A02-F001…`).
- `docs/superpowers/audits/2026-07-05-fable-partition/02-compiler-heads/design-questions.md`
  (from `_templates/design-questions.md`; IDs `A02-D001…`).
- `tests/audit_2026_07_05/test_02_compiler_heads.py` — adversarial tests. Suspected-bug tests
  use `@pytest.mark.xfail(strict=False)`; confirmed-correct behavior is a plain
  regression guard. The file must be **green** on a per-file run.
- Todos under `todo/audit-2026-07-05/`: `fix-A02-<slug>.md` (clear remediation)
  or `investigate-A02-<slug>.md` (Opus). Every confirmed finding needing a fix
  has exactly one; its ledger "Todo ref" points to it.
- Update this audit's row in
  `docs/superpowers/audits/2026-07-05-fable-partition/README.md` on completion.

---
## Subsystem A02 — Compiler: heads & indexing

**Files (stay within):** `clausal/logic/compiler/head_match.py`,
`clausal/logic/compiler/arg_index.py`, `clausal/logic/compiler/terms_to_ast.py`,
`clausal/logic/compiler/terms_to_goalop.py`, `clausal/logic/compiler/ir.py`,
`clausal/logic/compiler/list_dispatch.py`.

**Hotspots:**
- `head_to_match_pattern`, multi-star guard AST, str/SegList normalization gates.
- First-argument indexing: numeric/bool/None head literals in **output mode**
  (the 8085-test blind spot — `todo/audit-tests-input-output-mode-coverage.md`).
- Groundness-keyed dispatch selection; index correctness for partial terms.
- `terms_to_ast` / `terms_to_goalop` lowering fidelity vs `terms.py` shapes.

**Oracle:** none external; use `clausal/tools/visualize.py` (`predicate_to_source`)
to inspect generated code and diff intended vs emitted match arms.

**Seam notes for A12:** the IR/goalop contract consumed by A03; head patterns
depending on `terms.py` dunders (A01).
