# CLP constraints should carry units via a side channel

**Filed 2026-09-12. Operator's design; earmarked for a fable agent.**
Measured on `3b0e3547` — re-derive, do not quote.

## The problem

`Quantity` values cannot take part in CLP arithmetic. A comparison works, an
arithmetic constraint does not:

    X == Q - Y   with Q a Quantity  ->  type_error(integer, Quantity(...)), '(==)/2'
    `is`                            ->  does not evaluate; builds an unevaluated Div

So a rulebase can DECIDE with united money and cannot COMPUTE with it. Any value
used both ways must be written twice — once united for the comparison, once as a
bare integer for the arithmetic — which defeats the purpose of declaring a unit.

## The design

CLP solvers may be implemented in other languages — `_clpfd_core`,
`_clpfd_propagate`, `_clpb_core` and `_clpr_core` are C extensions — so quantities
cannot be passed in, in general. **They do not need to be.**

A CLP constraint is a comparison with a left- and a right-hand expression, and
those expressions may contain quantities. Therefore:

1. **Extract the units** from both expression trees.
2. **Do the unit arithmetic / dimensional analysis in a SIDE CHANNEL**: add,
   subtract and compare require the same units; multiply adds dimensions; divide
   subtracts them; and so on.
3. **Hand the solver the BARE NUMBERS.** It never sees a unit.
4. **Reattach the computed units** to the appropriate variables afterwards.

Each CLP relation must know its own dimensional rule.

**THE ORIGINAL DESIGN SAID THAT RULE COULD BE EXTRACTED AUTOMATICALLY FROM A PROLOG
DEFINITION OF THE RELATION. IN THIS REPO THERE IS NOTHING TO EXTRACT FROM — checked
before this todo was filed, so that nobody's first finding is the absence of their
input.**

    13 tracked .pl files: 2 tokenizer specs, 11 golden fixtures
    files mentioning `#<` / `#=<` / `#>=` / `#\=` in ANY position: 0

The comparators exist as Python implementations plus operator-table entries in
`tools/prolog_operators.py`, which carry priority and associativity — not
semantics. There is a genuine `library(clpfd)` definition on this machine at
`/workspace/sicstus/lib/sicstus-4.10.1/library/clpfd.pl` (24KB, Mats Carlsson),
and it rescues nothing, for two reasons that are worth stating before anyone plans
around it:

* **It defines SICStus's semantics, not this engine's.** SICStus clpfd is
  finite-domain only; the three-solver dispatch by numeric type here is ours. An
  extracted rule would need validating against our behaviour anyway — which is most
  of the work the extraction was meant to avoid.
* **It is commercially licensed third-party source.** Deriving engine code from it
  is a licensing question before it is a technical one, and not one to settle
  mid-task.

**So the job is: write the dimensional rule by hand.** One rule applied six times
for the comparator set, and per-relation for the expression operators. That is a
different and larger shape than "derive it", and it should be costed as such.

## Four measured facts the implementer would otherwise find the hard way

### 1. The existing guard is CORRECT. Do not simply widen it.

`_reject_nonnumeric_eq` (`clausal/logic/clpfd.py:1793`), with its ordering sibling
`_reject_nonnumeric_order`, is what currently refuses a quantity. Its own docstring
(A12-F002) records why refusing is right: posting the constraint instead produced a
**broken FD var** whose unification hook accepted integers only, so it rejected even
a later binding to the operand it had been equated with. Widening the allowlist
reintroduces exactly that defect.

It is nonetheless the right place to strip and reattach: it already runs BEFORE the
CLP(Q)/CLP(R) dispatch in both the Python `fd_eq` and the C-accelerated wrapper, so
no operand can get past it.

### 2. There are THREE solvers and dispatch is BY NUMERIC TYPE

    int  -> CLP(FD)        float -> CLP(R)        Fraction -> CLP(Q)

with the ground side required to be `numbers.Real`.

### 3. Stripping the unit is NOT sufficient — there are two layers

    isinstance(Decimal('1.00'), numbers.Real)  ->  False

A currency `Quantity` holds a **Decimal**, so removing the unit yields a value the
solvers still reject. The side channel must handle the dimension AND the numeric
type.

### 4. The exact route for money is Decimal -> Fraction -> CLP(Q)

`Fraction(Decimal)` is exact at every scale:

    Decimal('1550.00')            -> Fraction(1550)
    Decimal('0.01')               -> Fraction(1/100)
    Decimal('123456789012345.67') -> Fraction(12345678901234567/100)

and `Fraction` IS `numbers.Real`, so CLP(Q) accepts it. **This gives money an exact
CLP route with no float anywhere** — which matters, because the currency design
exists to keep money out of binary floating point. Do NOT route money through
CLP(R).

## Scope

The comparator set is small and bounded:

    #<   #=   #=<   #>   #>=   #\=     plus the `==` / `!=` arithmetic aliases

All comparisons share one dimensional rule — operands must agree — so the
comparator half is one rule applied six times. The **expression** operators
(`+ - * /`, and `Pow`/`Negate` on the ground-tree path) are where per-relation
rules genuinely differ, and where automatic extraction earns its keep.

## Acceptance

* A money comparison AND a money subtraction both work inside a CLP constraint,
  with the result carrying the right unit.
* Mixing currencies inside one constraint RAISES rather than computing. That
  property is the reason for the exercise.
* No float on any money path; `Decimal -> Fraction` exactness pinned by a test.
* A18-F002's property still holds: a Var compared against a genuinely non-numeric
  ground operand still raises, and no broken FD var is ever posted. Keep the
  guard's existing tests green rather than relaxing them.
* A downstream acceptance case exists and is recorded on the consuming side; ask
  the operator for it rather than inventing one, since it carries a reference
  output that must stay byte-identical.

**Footer:** finishing this todo includes `git mv`-ing it to `todo/done/`.
