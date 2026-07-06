Read `docs/superpowers/audits/2026-07-05-fable-partition/prompts/required_reading.md`
before any code or tool use — it defines your role, reading order, standing
contracts, method, and rules.

## Deliverables (write these paths)

- `docs/superpowers/audits/2026-07-05-fable-partition/11-modules-interop/findings.md`
  (from `_templates/findings.md`; IDs `A11-F001…`).
- `docs/superpowers/audits/2026-07-05-fable-partition/11-modules-interop/design-questions.md`
  (from `_templates/design-questions.md`; IDs `A11-D001…`).
- `tests/audit_2026_07_05/test_11_modules_interop.py` — adversarial tests. Suspected-bug tests
  use `@pytest.mark.xfail(strict=False)`; confirmed-correct behavior is a plain
  regression guard. The file must be **green** on a per-file run.
- Todos under `todo/audit-2026-07-05/`: `fix-A11-<slug>.md` (clear remediation)
  or `investigate-A11-<slug>.md` (Opus). Every confirmed finding needing a fix
  has exactly one; its ledger "Todo ref" points to it.
- Update this audit's row in
  `docs/superpowers/audits/2026-07-05-fable-partition/README.md` on completion.

---
## Subsystem A11 — Modules, interop & Prolog tools

**Files (stay within):** `clausal/modules/graphs.py`, `clausal/modules/imperial.py`,
`clausal/modules/units.py`, `clausal/modules/reflection.py`,
`clausal/modules/prolog.py`, `clausal/modules/py/` (all wrappers),
`clausal/regex.py`, `clausal/reflection.py`, `clausal/tools/prolog_ast.py`,
`clausal/tools/prolog_parser.py`, `clausal/tools/prolog_tokenizer.py`,
`clausal/tools/prolog_operators.py`, `clausal/tools/prolog_dialect.py`,
`clausal/tools/prolog_to_clausal.py`, `clausal/tools/clausal_to_prolog.py`.

**Hotspots:**
- `modules/py/*` wrappers (`csv`, `json`, `datetime`, `hash`, `hmac`, `http`,
  `os`, `process`, `random`, `re`, `sqlite`, `tcp`, `url`, `uuid`, `files`,
  `logging`, `pbkdf2`): faithful pass-through of Python stdlib semantics and
  error propagation; snake_case API fidelity (recent datetime rename).
- `regex.py` / `reflection.py`: multi-arity dispatch, auto-binding, reify_source
  static-eval correctness.
- Prolog tools: tokenizer/parser/operator-table round-trip
  (`prolog_to_clausal` → `clausal_to_prolog`) fidelity across ISO/SWI/Scryer.

**Oracle (strong here):** each `modules/py/*` wrapper's oracle is the **Python
stdlib module it wraps** — call both, diff results and error behavior.
Prolog round-trip is its own differential (parse→emit→parse must be stable).

**Seam notes for A12:** modules load via the A10 import hook; reflection reads
the A01 term layer.
