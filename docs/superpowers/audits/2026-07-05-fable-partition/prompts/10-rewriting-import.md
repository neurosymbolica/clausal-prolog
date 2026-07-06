Read `docs/superpowers/audits/2026-07-05-fable-partition/prompts/required_reading.md`
before any code or tool use — it defines your role, reading order, standing
contracts, method, and rules.

## Deliverables (write these paths)

- `docs/superpowers/audits/2026-07-05-fable-partition/10-rewriting-import/findings.md`
  (from `_templates/findings.md`; IDs `A10-F001…`).
- `docs/superpowers/audits/2026-07-05-fable-partition/10-rewriting-import/design-questions.md`
  (from `_templates/design-questions.md`; IDs `A10-D001…`).
- `tests/audit_2026_07_05/test_10_rewriting_import.py` — adversarial tests. Suspected-bug tests
  use `@pytest.mark.xfail(strict=False)`; confirmed-correct behavior is a plain
  regression guard. The file must be **green** on a per-file run.
- Todos under `todo/audit-2026-07-05/`: `fix-A10-<slug>.md` (clear remediation)
  or `investigate-A10-<slug>.md` (Opus). Every confirmed finding needing a fix
  has exactly one; its ledger "Todo ref" points to it.
- Update this audit's row in
  `docs/superpowers/audits/2026-07-05-fable-partition/README.md` on completion.

---
## Subsystem A10 — Term rewriting, templating & import

**Files (stay within):** `clausal/templating/term_rewriting.py`,
`clausal/templating/compiler.py`, `clausal/templating/parser.py`,
`clausal/import_hook.py`, `clausal/_lazy_hook.py`, `clausal/codegen.py`,
`clausal/logic/goal_expansion.py`, `clausal/pythonic_ast/node_class.py`,
`clausal/pythonic_ast/nodes.py`, `clausal/pythonic_ast/transform.py`,
`clausal/pythonic_ast/conversion_from_python_ast.py`.

**Hotspots (largest file in the codebase — `term_rewriting.py`, ~3600 lines —
coverage-map discipline matters most here):**
- `TermTransformer` / `EmbedTransformer` / `_make_functor_class_ast`: every
  Python-AST node kind → term mapping (operator nodes, list/dict/tuple, unary
  escapes `++()`, f-strings).
- Import hook: transitive py-backed module import, source-vs-installed path
  resolution (`todo/fix-audit-2026-06-24.md` documents a known band-aid — cite,
  don't re-report; probe for *sibling* cases).
- Goal expansion (`goal_expansion.py`): ALLCAPS/trailing_ auto-binding, arrow-
  pattern sugar, recursion into multi-goal bodies.

**Oracle:** `clausal/tools/dump_transformed.py` / repo-root `show_generated.py` to compare
intended vs produced AST; round-trip `.clausal` example files through the hook.

**Seam notes for A12:** produces the Predicate/term AST the compiler (A02/A03)
consumes; import hook feeds the runtime (A04).
