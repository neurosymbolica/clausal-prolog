# investigate-A01: three parked term-layer design decisions (needs USER, not Opus)

**Parked by the user 2026-07-05** during the A01 audit ("This is a tricky
decision. Park it in a todo, I'll get to it."). These are policy calls that
shape fix todos; do not implement the affected fixes in a direction-sensitive
way before they are answered. Full context:
`docs/superpowers/audits/2026-07-05-fable-partition/01-term-layer/design-questions.md`.

## 1. A01-D001 — cross-type numeric unification

`unify` falls back to Python `==` for atomics, so `1`, `True`, `1.0`,
`Decimal(1)`, `Fraction(1,1)` all unify with each other (probe-confirmed;
`test_d001_cross_type_numeric_unification_characterization` pins it).
Prolog distinguishes 1 from 1.0; Python doesn't.

Options: (a) keep Python `==`, document it; (b) Prolog-style type-sensitive
unification; (c) split — keep numeric-value equality but stop conflating
bool/int. **Recommendation: (c)** — `True`/`1` conflation is the likeliest
rulebase footgun; `1`/`1.0` equality is defensible as Python-native.
Whatever the call: A02 (first-arg indexing) and A04 (tabling keys) must be
checked for consistency with it.

## 2. A01-D002 — Quantity dimensionless asymmetry

`Quantity(5,{}) <= 5` is True, but `Quantity(5,{}) == 5` and
`unify(Quantity(5,{}), 5)` are False. Options: (a) Liskov — dimensionless
quantity behaves as its number everywhere; (b) strict everywhere; (c) status
quo, documented.

## 3. A01-D004 — Compound Var-functor support level (gates fix-A01-compound-var-functor)

The docstring advertises `Compound(functor_var, args)` but every path is
broken for it (A01-F003): unify compares the functor with `!=` (a functor Var
*bound* to `"f"` still fails), copy_term doesn't freshen it, `_is_ground` /
`_collect_vars` / `term_str` ignore it. Options: (a) full support — deref and
bind unbound functor Vars during unification; (b) deref-only — bound functor
Vars work everywhere, unbound ones don't bind (construction-time convenience);
(c) reject non-str functors at construction and fix the docstring.
**Recommendation: (b)** — fixes all observed silent failures without
committing to functor-var metaprogramming semantics.
