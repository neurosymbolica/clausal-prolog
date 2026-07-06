Read `docs/superpowers/audits/2026-07-05-fable-partition/prompts/required_reading.md`
before any code or tool use — it defines your role, reading order, standing
contracts, method, and rules.

## Deliverables (write these paths)

- `docs/superpowers/audits/2026-07-05-fable-partition/01-term-layer/findings.md`
  (from `_templates/findings.md`; IDs `A01-F001…`).
- `docs/superpowers/audits/2026-07-05-fable-partition/01-term-layer/design-questions.md`
  (from `_templates/design-questions.md`; IDs `A01-D001…`).
- `tests/audit_2026_07_05/test_01_term_layer.py` — adversarial tests. Suspected-bug tests
  use `@pytest.mark.xfail(strict=False)`; confirmed-correct behavior is a plain
  regression guard. The file must be **green** on a per-file run.
- Todos under `todo/audit-2026-07-05/`: `fix-A01-<slug>.md` (clear remediation)
  or `investigate-A01-<slug>.md` (Opus). Every confirmed finding needing a fix
  has exactly one; its ledger "Todo ref" points to it.
- Update this audit's row in
  `docs/superpowers/audits/2026-07-05-fable-partition/README.md` on completion.

---
## Subsystem A01 — Term layer & C unification

**Files (stay within):** `clausal/terms.py`, `clausal/pythonic_terms.py`,
`clausal/logic/variables/_variables.c`, `clausal/logic/variables/__init__.py`.

**Hotspots:**
- `SegList` / `SegString` / `VarSeg` / `ConcreteSeg` dunders: `__walk__`,
  `__unify__`, `__eq__`/`__hash__` (asymmetries), `__occurs_check__`,
  `__contains__`, `__add__`/`__radd__`. The strings-as-lists Liskov rule:
  promote a walked all-1-char-str list to `str`; keep list shape otherwise.
- The C `do_unify` `str ↔ list` branches and the `__unify__` protocol-hook
  ordering in `_variables.c`.
- Var deref, trail record/undo, occurs-check on cyclic terms.

**C toolkit:** use `refcount_stable` on unify/backtrack loops; check `_variables.c`
against `todo/cross_cutting_issues.md` (Trail_Check before cast; `PyObject_IsInstance`
-1 handling). FT: `_ft_compat.h` — log `unconfirmed — needs 3.14t` unless run there.

**Oracle:** none external; the cheat-sheet's strings-as-lists section + the prior
string audit (`tests/audit_2026_05_25/`) are the reference — extend, don't repeat.

**Seam notes for A12:** how `terms.py` dunders are invoked by the C unifier, and
by the compiler's head matcher (A02).
