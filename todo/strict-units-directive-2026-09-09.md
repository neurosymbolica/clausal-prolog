# `strict_units`: require every number to carry units

Operator request 2026-09-08/09. Out of scope for now — captured with the
measurements that were taken while discussing it, so nobody re-derives them.

## The ask

A directive under which every number in a module must carry units, with
dimensionless values written explicitly:

```seam
-strict_units
price(5000(euro)),
count(3 ())            % dimensionless, said out loud
```

## Measured, 2026-09-08 (on b2b2911d)

**The surface already parses.** Both `5000()` and `5000 ()` load today, so the
spelling needs no reader work. (Only that they LOAD was checked — not what
they currently denote.)

**The runtime already enforces the interesting half**, so `()` should mean a
dimensionless `Quantity(n, {})` rather than a lint marker — the semantic
reading gets real enforcement from machinery that already exists:

```
Quantity(3,m) + 5               -> UnitsMismatch      bare scalar refused
Quantity(3,m) * 5               -> Quantity(15,m)     scalar scaling allowed
Quantity(3,m) + Quantity(5,{})  -> UnitsMismatch      dimensionless is a DISTINCT
                                                      dimension, not a wildcard
Quantity(5,{}) + 5              -> Quantity(10,{})    dimensionless DOES absorb a
                                                      bare scalar
```

That last line is the boundary case: inside a strict module no bare number
exists, but one can still arrive from a non-strict module or a `++` escape.

## Two designs, and they are complementary

**(a) The directive (syntactic, compile-time).** Gives COVERAGE — every
literal in the file is accounted for. Its cost is that "every number" collides
with numbers that are structurally dimensionless, so it needs an ENUMERATED
exemption list, not a discovered one:
  - arities and priorities — `-table(foo/1)`, `op(700, xfx, ...)`; nobody wants
    to write `700 ()`
  - exponents in unit expressions — the `2` in `10(m**2)`
  - list indices — `nth0(3, L, X)`
Suggested scope: numeric literals in term/argument position within clause heads
and bodies; exempt directive arguments, functor-indicator arities, and
unit-expression exponents. **Operator ruling needed on the exemption list.**

**(b) `StrictQuantity(Quantity)` (value-level, runtime).** Operator's
suggestion 2026-09-09: a subclass that RAISES when it interacts with a value
carrying no units — a bare int in `+`, `*`, etc. Gives PROPAGATION: the
strictness rides on the value through every computation, including into and out
of Python, with no compile-time scope rule at all.

Note (b) sidesteps (a)'s whole blast-radius problem: at runtime an arity or an
operator priority never arrives as a quantity in the first place, so there is
nothing to exempt. What it does NOT give is coverage — a bare `5 + 3` elsewhere
in the module is untouched, because no StrictQuantity is involved. So the two
compose rather than compete: the directive says "every literal is accounted
for", the subclass says "and nothing dimensionless leaks into a dimensioned
computation".

`__pow__` is exempt, per the operator. Be precise about what that means: the
EXPONENT operand is legitimately dimensionless (`q ** 2`), so strictness must
not demand units of it. It does not mean disabling the existing check — today
`Quantity.__pow__` already raises `UnitsMismatch` if the exponent is
non-integer or itself has dimensions, which is correct and should stay.

## Payoff worth noting

A `strict_units` module is MORE confidently exportable to ISO: every number's
dimension is explicit, so `clausal_to_prolog`'s mixed-unit guard could be exact
for such files instead of the syntactic approximation it is today (see
`_check_unit_mixing`'s known limit, pinned in
tests/test_prolog_quantity_units.py).

## Related

- `clausal/terms.py::Quantity` (`__slots__`, `__unify__`, dimensional arithmetic)
- `clausal/logic/units_constraint.py` (the AttVar/UnitState half, for unbound
  dimensioned slots)
- Design conclusion from the same conversation: units belong IN THE VALUE.
  An int subclass carrying units was measured and rejected — `int` subclasses
  cannot have `__slots__` (364 bytes/instance vs `Quantity`'s 48), every
  operator decays to plain `int`, and the value compares and hashes EQUAL to a
  bare number, so `f(5cm)` and `f(5)` collapse to one tabled answer.
- Open and unsettled: currency is NOT dimensionally like SI. Metre<->foot is a
  constant; EUR<->USD is time-varying. Currencies want to be incommensurable
  dimensions that NEVER auto-convert, which is the opposite of what the SI
  normalisation does.
