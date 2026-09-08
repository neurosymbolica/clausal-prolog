# Clausal's `is` and `==` carry each other's ISO meanings

Raised by the operator 2026-09-09 while reviewing the `==` split, and MEASURED
rather than inferred:

    X is  3 + 4   ->  Add(left=3, right=4)   unification with the unevaluated TREE
    X ==  3 + 4   ->  7                      evaluates and binds

ISO says the opposite of both: `X is 3+4` is 7 (evaluate and bind), `X = 3+4`
binds the term. So this is not a naming collision — the two spellings are
SWAPPED. `==` is carrying ISO's `is/2`; `is` is carrying ISO's `=`.

## Why the canonical form makes it acute

`docs/superpowers/specs/2026-09-08-iso-canonical-form-operators-design.md` §3.1
registers `'is'(R, E)` as ISO `is/2`. Once that lands, ONE identifier means two
opposite things in the same file depending only on spelling:

    X is 3 + 4        -> the term Add(3, 4)     (infix, Clausal)
    'is'(X, 3 + 4)    -> 7                      (canonical, ISO)

The spec records the fact (§2: "Clausal `is` is unification (nodes.Unify, ISO
`=`)") but does not treat the collision as a problem to resolve. It should say
which way it resolves, even if the answer is "not yet".

## Operator's position (2026-09-09)

Infix `is` "could stay for the time being", but if the spelled-out `'is'(L, R)`
exists it "might need to be moved to the Prolog meaning". So the direction is
toward ISO; the sequencing is open.

## What makes this harder than the `==` split

The `==` migration has an instrument: `==` dispatches four ways at run time and
`clausal/tools/eq_analysis/instrument.py` measures which each site takes. `is`
has no such ambiguity to measure — it is unification at every site, always. So
the migration is not "discover what each site means", it is a genuine SEMANTIC
CHANGE at every `is` site: today's `X is 3 + 4` would stop yielding a term and
start yielding 7. Every site that relies on getting the unevaluated tree breaks
silently, and the ones that wanted the number were already writing `==`.

That argues for sequencing it AFTER the `==` split rather than with it: once
arithmetic sites are respelled `'is'` / `'=:='` / `'#='`, what remains on `==`
and on infix `is` is a much smaller and better-understood set.

## Related

- `docs/superpowers/specs/2026-09-08-iso-canonical-form-operators-design.md`
- `clausal/tools/eq_analysis/instrument.py`, and iso-export-lane's static
  analyser + merge on trunk (`tools/eq_analysis/`)
- `clausal/pythonic_ast/nodes.py::ArithEq` (what `==` compiles to),
  `::Unify` (what `is` compiles to)
