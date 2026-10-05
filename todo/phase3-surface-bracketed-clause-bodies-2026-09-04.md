# Phase 3 surface idea: clause bodies inside `(...)` or possibly `[...]`

**From the user, 2026-09-04, while reviewing the toklex formalism design.** Explicitly
a LANGUAGE question, not a formalism question — parked here so it reaches the Phase 3
surface-syntax discussion (which is user-owned parser territory; see
`implementation_plans/prolog-parser-formalism-handoff.md`).

The idea (user's reasoning, paraphrased):

- Clause bodies delimited by `(` ... `)` — or possibly `[` ... `]` — rather than bare
  comma-joined goals up to the terminator.
- Benefits named: (1) easier to *see* what the goals are; (2) easier to **lift a body
  out** and drop it elsewhere — e.g. as a term expression inside another body — without
  commas being an issue or needing additional parentheses (a bare `a, b, c` body is
  precedence-fragile when embedded; a delimited one is a self-contained term).

Notes for when this is taken up:

- Today's seam (`.seam`) surface already has `head <- (...)` shapes (the clausal-fmt work
  established `head <- (...),` is a Tuple statement under the Python-AST reading), so
  `()`-delimited bodies are close to the existing look.
- `[...]` bodies would collide with list syntax unless position disambiguates
  (body-after-neck); that trade-off belongs with the surface ruling.
- Interacts with open question 3 of
  `implementation_plans/toklex-token-formalism-design.md` (dot-terminated vs
  newline-significant items): a delimited body weakens the need for a clause
  terminator, since the item end becomes structurally visible.
- Token-layer impact: none (parens/brackets are already solo/punct tokens); this is
  entirely L1/L2 + language design.
