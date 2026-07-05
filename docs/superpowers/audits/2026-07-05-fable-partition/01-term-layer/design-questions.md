# Design questions — A01 term-layer & C unification

Status: resolved-from-docs (cite) | resolved-by-user (record) | open.

All `open` items below were explicitly **parked by the user on 2026-07-05**
("This is a tricky decision. Park it in a todo, I'll get to it.") — see
`todo/audit-2026-07-05/investigate-A01-parked-design-decisions.md`. Do not
re-ask; pick up from that todo.

| ID | Status | Title | Conflicting sources | Options considered | Decision + rationale | Follow-up |
|----|--------|-------|---------------------|--------------------|----------------------|-----------|
| A01-D001 | open (parked) | Cross-type numeric unification: `unify` falls back to Python `==`, so `1`/`True`/`1.0`/`Decimal(1)`/`Fraction(1,1)` all unify | Prolog structural unification (1 ≠ 1.0) vs Clausal's Python-native stance (`_variables.c:1379` rich-compare fallback, documented "compared with `==`" in the unify docstring); cheat-sheet is silent | (a) keep Python `==` and document; (b) Prolog-style type-distinguishing; (c) split: keep 1==1.0 but stop conflating bool/int | — (recommendation at parking time: (c); bool/int conflation is the likeliest rulebase footgun while 1/1.0 equality is defensible Python-native) | Characterization test `test_d001_...` pins current behaviour; A02/A04 must check dispatch/tabling-key consistency either way |
| A01-D002 | open (parked) | Quantity dimensionless asymmetry: `Quantity(5,{}) <= 5` is True but `== 5` and `unify(q,5)` are False | `terms.py:1656-1696` comparisons accept plain numbers when dimensionless; eq/unify require Quantity | (a) unify/eq dimensionless with plain numbers (Liskov); (b) strict everywhere; (c) status quo, document | — | Characterization test `test_d002_...` |
| A01-D003 | resolved-from-docs | Binding an attributed var with **no registered hook** silently succeeds; on var-var aliasing the newer var's attrs become invisible (no merge) | SWI/SICStus error-or-call semantics vs `_variables.c` header: "Constraint propagation is entirely left to user-supplied hooks" | (a) error like SWI; (b) documented as-is | Documented behaviour — the C module explicitly delegates ALL attr semantics to hooks; in-tree consumers (dif, clpfd) register hooks that handle merging. No change. | Guard `test_hookless_attr_unification_characterization` |
| A01-D004 | open (parked) | Compound Var-functor: supported feature or not? Determines the A01-F003 fix direction | Docstring `terms.py:70-73` advertises `Compound(functor_var, args)`; every code path treats functor as plain-compared str (F003) | (a) full support (deref + bind unbound functor); (b) deref-only, no output mode; (c) reject non-str functor at construction + fix docstring | — (recommendation at parking time: (b) — deref-only fixes the observed silent failures cheaply without committing to functor-var metaprogramming semantics) | `fix-A01-compound-var-functor.md` blocked on this |
