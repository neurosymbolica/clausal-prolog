# Scryer cell-interchange codec: tagged cells <-> scryer lib_machine Term enum

Parked 2026-09-03 during the Phase 2 bridge. Finding (verified against /workspace/scryer-prolog):
Scryer's embedding API enum (`src/machine/lib_machine/mod.rs::Term`) is nearly isomorphic to the
bridge's tagged cells — `Compound(String, Vec<Term>)` == `("name", args...)`, `Atom(String)` ==
rev-3 string atoms, `List` == Python list, `String` == char-list (both engines chose
host-string-as-char-list, so the cons rule has a direct partner), arbitrary-precision ints both
sides. Scryer's INTERNAL WAM heap (`src/types.rs::HeapCellValueTag`) is unrelated — the codec
targets the API boundary only.

Build (~30-line recursive codec + tests):
- OUT of Scryer: `Term` -> cell (mechanical; `Var(String)` needs a naming/identity scheme).
- INTO Scryer: cells -> canonical term text via the reified renderer (queries enter Scryer as
  text; `Term` is answer-shaped, #[non_exhaustive]) — aligns with canonical's translator work
  (real-Scryer-transcript design specs).
- Decide once, both directions: encoding for `(tuple, ...)` data cells (ISO has no tuples —
  e.g. `tuple/N` functor), and for the higher-order slot-0-Var cell (no ISO counterpart —
  encode as call/N or refuse).
- Out of scope: attributed vars (don't surface through Scryer's API enum).

Depends on: Phase 2 bridge merged (cells.py). Eases: Scryer-based differential testing of the
translators, cross-engine test oracles.
