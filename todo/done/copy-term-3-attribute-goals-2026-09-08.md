# `copy_term/3` — copy a term and hand back its attribute goals as a list

**Status: FIXED 2026-11-04 (commit 720e0e75).** `copy_term/3` is a builtin on every surface; its goals come from `clausal.logic.residuals`, the function the `-g` and `?-` printers use (dif, CLP(Z), freeze, when, CLP(B), CLP(R), CLP(Q)), in Scryer's plain spelling as the printers write it. Pinned in tests/iso/test_copy_term_3_scryer.py (a Scryer execution pin, .pl and .clausal), tests/fixtures/copy_term_3.clausal and tests/fixtures/copy_term_3.seam. The translator's witness suite has no row for it.

ISO-adjacent (SWI, Scryer, SICStus all provide it): `copy_term(Term, Copy,
Goals)` copies `Term` to `Copy` with fresh variables and returns in `Goals` the
list of goals that, when called, reinstate the constraints attached to the
copied variables (clpfd domains, `dif/2`, `freeze/2`, ...).

Why now (2026-09-08): the goal-position `--` seam
(docs/superpowers/specs/2026-09-08-goal-position-seam-design.md §4a) exports
answers to Python as COPIES and refuses to export an unbound variable that
still carries constraints, because the alternative is to strip them silently.
`copy_term/3` is the ISO-shaped way for a caller to ASK for the residue inside
the goal — `--(goal, copy_term(X, X2, GOALS))` — so the seam needs no special
syntax for residual goals; the residue arrives as a plain term. Scryer's
`copy_term/3` is the reference for the goal spelling (`X in 1..3`, `dif(X, Y)`).

Needs: an attribute-goal hook per attributed-variable kind (clpfd, dif, freeze,
clpb/clpq/clpr) — `attribute_goals//1` in SWI/Scryer terms — and the builtin
itself. Pair with a `.seam` and a Scryer execution pin in the translator's witness suite, and a `.clausal` (Clausal Prolog) test: copy_term/3 is missing there too.
