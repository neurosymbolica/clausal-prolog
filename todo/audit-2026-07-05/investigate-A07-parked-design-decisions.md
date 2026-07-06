# investigate-A07: three parked CLP(B)/SAT design decisions (needs USER, not Opus)

**Parked by standing user instruction 2026-07-05** (A07 ran non-interactively;
design questions are recorded, never asked). These are policy calls that gate
fix direction; do not implement the affected fixes in a direction-sensitive
way before they are answered. Full context:
`docs/superpowers/audits/2026-07-05-fable-partition/07-clpb-sat/design-questions.md`.

## 1. A07-D001 — taut/2 & sat_count/2: standalone formula vs constraint store
(gates A07-F003, A07-F004)

The module docstring claims "Markus Triska's reference design"; in that design
`taut(Expr, T)` is entailment w.r.t. the posted store and `sat_count` counts
admissible assignments (and posts Expr). Clausal's implementations ignore the
store: after `sat(BoolImpl(X,Y))`, `taut(~X | Y, T)` fails (Triska: T=1);
after `sat(BoolEq(X,Y))`, `sat_count(X | Y, N)` gives 3 (Triska: 1).

Options: (a) adopt Triska store-aware semantics (cheap once A07-F001's
collection fix lands); (b) keep standalone semantics, fix the docstring and
docs/clpb.md to say so explicitly; (c) keep both under separate names.
**Recommendation: (a)** — it is the claimed design and the useful semantics
inside a constraint program; standalone counting stays available via fresh
variables.

## 2. A07-D002 — Python True/False in the CLP(B) domain (gates A07-F010; joint with A01-D001)

`unify(X, True)` on a CLP(B) var succeeds and leaves X bound to `True`
(bool passes the `isinstance(int)` + `in (0,1)` hook checks), while
docs/clpb.md pins the domain to "0/1 (integers), not Python booleans" and
CLP(Z)/CLP(R) explicitly reject bools. `_expr_to_bdd` meanwhile accepts bools
as formula constants by design.

Options: (a) reject bool bindings in `_bool_hook` (consistency with sibling
solvers); (b) accept but normalize the binding to int 0/1; (c) document
acceptance. **Recommendation: (a)**, unless A01-D001 resolves to "bool==int
everywhere", in which case (b). Decide jointly with A01-D001 — the unify
layer is what delivers `True` to the hook.

## 3. A07-D003 — PySAT bridge integration depth (gates the shape of fix-A07-clpsat-bindings-invisible)

Clausal bindings are invisible to the PySAT solver (A07-F005, unsound
models). Options: (a) assumption bridge — at sat_check/label_sat time, add
±sat_var assumptions for every registered var bound to 0/1 (~5 lines, no
hook change, fixes soundness); (b) full SAT_KEY attr hook posting unit
clauses per binding under the current activation scope (eager, bidirectional,
entangled with the A04-D001 hook-contract discussion); (c) document the
backend as fully detached and forbid mixing with unification.
**Recommendation: (a) now**, (b) later if wanted; the soundness fix in
fix-A07-clpsat-bindings-invisible.md is written to be compatible with either.
