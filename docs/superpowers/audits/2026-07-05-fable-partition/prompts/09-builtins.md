Read `docs/superpowers/audits/2026-07-05-fable-partition/prompts/required_reading.md`
before any code or tool use — it defines your role, reading order, standing
contracts, method, and rules.

## Deliverables (write these paths)

- `docs/superpowers/audits/2026-07-05-fable-partition/09-builtins/findings.md`
  (from `_templates/findings.md`; IDs `A09-F001…`).
- `docs/superpowers/audits/2026-07-05-fable-partition/09-builtins/design-questions.md`
  (from `_templates/design-questions.md`; IDs `A09-D001…`).
- `tests/audit_2026_07_05/test_09_builtins.py` — adversarial tests. Suspected-bug tests
  use `@pytest.mark.xfail(strict=False)`; confirmed-correct behavior is a plain
  regression guard. The file must be **green** on a per-file run.
- Todos under `todo/audit-2026-07-05/`: `fix-A09-<slug>.md` (clear remediation)
  or `investigate-A09-<slug>.md` (Opus). Every confirmed finding needing a fix
  has exactly one; its ledger "Todo ref" points to it.
- Update this audit's row in
  `docs/superpowers/audits/2026-07-05-fable-partition/README.md` on completion.

---
## Subsystem A09 — Builtins & stdlib predicates

**Files (stay within):** `clausal/logic/builtins/lists.py`,
`clausal/logic/builtins/higher_order.py`, `clausal/logic/builtins/arithmetic.py`,
`clausal/logic/builtins/io.py`, `clausal/logic/builtins/inspection.py`,
`clausal/logic/builtins/type_checks.py`, `clausal/logic/builtins/chars.py`,
`clausal/logic/builtins/dict_set.py`, `clausal/logic/builtins/pairs.py`,
`clausal/logic/builtins/dcg.py`, `clausal/logic/builtins/database_ops.py`,
`clausal/logic/builtins/keyword_ops.py`, `clausal/logic/builtins/control.py`,
`clausal/logic/builtins/translations_builtin.py`,
`clausal/logic/builtins/_chars_core.c`, `clausal/logic/_lists_core.c`.

(Solver-specific builtin adapters — z3/ortools/sat — belong to A07/A08, not here.)

**Hotspots:**
- List builtins under the strings-as-lists rule: every `isinstance(_, str)` site,
  `append`/`length`/`member`/`reverse`/`nth`(`list_item`)/`msort`/`last` in
  **both** input and output modes; result-type promotion.
- Higher-order (`MapList`/`Filter`/`Exclude`/`FoldLeft`) with partial/unbound args.
- `type_checks`, `inspection` (`CopyTerm`/`TermVariables`/`NumberVars`),
  `dict_set`, `pairs`, `control` (once/timeouts), `database_ops` (assertz/retract
  clause sync).
- `chars` C core (`_chars_core.c`).

**C toolkit:** `refcount_stable` over char/list-builtin loops; audit
`_chars_core.c`, `clausal/logic/_lists_core.c` against `todo/cross_cutting_issues.md`.

**Oracle:** Python's own list/string semantics for the pure list ops; DCG example
`clausal/examples/dcg_state.clausal`.

**Seam notes for A12:** builtins lean on A01 term shapes and A04 unify helpers.
