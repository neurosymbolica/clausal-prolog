# investigate-A06: five parked CLP(FD) design decisions (needs USER, not Opus)

**Parked per standing user mandate** (design questions go to a todo, never
asked interactively). These are policy calls that shape fix todos; do not
implement the affected fixes in a direction-sensitive way before they are
answered. Full context:
`docs/superpowers/audits/2026-07-05-fable-partition/06-clpfd/design-questions.md`.

## 1. A06-D001 — label/1 on unconstrained vars (gates part of the label surface)

`label([X])` with a no-fd-attr X silently yields one "solution" with X left
unbound, while an fd-attr-but-unbounded X raises ValueError
(characterization guard `test_domainless_var_current_behaviour`).
Options: (a) ValueError for any var without a finite domain (SWI-like,
consistent); (b) documented silent-skip; (c) skip+warn.
**Recommendation: (a)** — silently wrong solution counts are the worst
failure mode for an enumeration primitive.

## 2. A06-D002 — sum_/scalar_product op-string vocabulary (gates fix-A06-sum-op-strings)

`_FD_OPS` accepts only Prolog spellings (`#=`, `=<`, `\=`); the language's
own spellings (`==`, `<=`, `!=`) silently post nothing (A06-F011).
Options: (a) accept both + raise on unknown; (b) Python-only (breaking);
(c) status quo documented. **Recommendation: (a).**

## 3. A06-D003 — global_cardinality off-key values (gates part of fix-A06-gcc-var-count)

Values not listed in Pairs are currently unconstrained; SWI restricts Vars
to the pair keys. Options: (a) SWI semantics; (b) permissive documented;
(c) flag. **Recommendation: (a)** if gcc is the library(clpfd) import
target, else (b) with explicit docs. Var-count propagation (A06-F013) is
independent and wanted under either.

## 4. A06-D004 — circuit([]) / circuit([X]) semantics

Both fail today. SWI: `circuit([])` succeeds. Options: (a) full SWI
(`[X]` → X=1); (b) both fail, documented; (c) `[]` succeeds, `[X]` fails.
**Recommendation: (c)** — vacuous truth for `[]`; a 1-node self-loop
contradicts the n≥2 self-loop exclusion.

## 5. A06-D005 — booleans in CLP(Z) (gates fix-A06-bool-hook-divergence; blocked on A01-D001)

Docs say booleans are rejected by CLP(Z); actually `fd_eq(1, True)` → True,
the C hook binds `True` into FD vars (Python hook rejects — C/Python
divergence, A06-F009), `in_domain(X, True, True)` accepted.
Options: (a) reject bool at every fd_* entry + hook; (b) coerce bool→0/1
everywhere; (c) status quo. **Recommendation: (a), sequenced after
A01-D001** — the unifier's bool/int policy must lead and CLP(Z) follow it.
