# W4 cannot be sized until the ALIAS sweep is in — the names, and the shapes

Filed 2026-09-22 by engine-lane after W3 landed (main c5d62557). Three
censuses today each turned out to be a FLOOR because they were keyed on the
name `PredicateMeta`: a vocabulary class reached through an alias
(`reflection.Clause`), a cell's FIELD read (`item.goals`), and the class
name compared as a STRING (`type(t).__name__ == "PredicateMeta"`) are all
invisible to that grep. W4 (the class itself goes) is sized off this sweep,
not off W1b's 31.

## The names to sweep, from the engine (exported cell constructors that
## WERE classes)

    clausal.reflection      Atom, Clause, Escape, FormatString, Goal,
                            IfThenElse, ModuleDirective, PythonCode, Variable
    clausal.logic.clpb      BoolEq, BoolImpl
    clausal.logic.term_expansion   `term_expansion` (a real predicate class,
                            minted by make_predicate; stays a class until W4)

Plus every class `make_predicate` still mints in the engine: the builtin
registry's, `-specialize` aliases (specialization.py x3), `-rename`d
declarations (compiler_v2.py:1229), and `term_expansion` — these are the
predicate classes a downstream body can HOLD as a value.

## The shapes to count (each is a separate number; none subsumes another)

1. `isinstance(x, <Name>)` and `isinstance(x, (<Name>, ...))`, through any
   alias (`reflection.Clause`, `from clausal.reflection import Clause as C`).
2. `type(x) is <Name>`, `type(x) == <Name>`, `type(x).__name__ == "<Name>"`,
   and the quoted strings `"PredicateMeta"` / `'PredicateMeta'`.
3. Attribute reads of a CELL FIELD on a value one of those builds: `.name`,
   `.args`, `.kwargs`, `.position`, `.goals`, `.head`, `.term`, `.value`,
   `.keys`, `.values`, `.expansion`, `.module_before`, `.module_after`, and
   `._fields` / `.__match_args__` on the value or its type.
4. A predicate class held as a VALUE and called later (W1b's shape).
5. `.__name__` / `.__module__` read off a predicate class.

In-tree (tests/, packages/): shape 1 = 0 after W2; shapes 2–5 not yet counted.
Downstream: requested from the three lanes 2026-09-22, by this list.

Replacements that already exist: `reflection.is_v(x, Name)` for shape 1,
`reflection.vfield(x, "field")` for shape 3 on reflection cells; the atom /
`(functor, arity)` key for shapes 4–5 is W4's design, not yet written.

## Downstream result 1 of 3 (the downstream lane, 2026-09-22)

Population: the downstream roster bodies, all parsed. Alias resolution
covers `import X as Y`, `from clausal import reflection`, and
`import clausal.reflection as r`; a planted positive fires on every
detectable shape before each sweep.

    shape 1  isinstance against a vocabulary class            0
    shape 2  type(x) is/== / __name__ == / "PredicateMeta"    0
    shape 3  cell-field read on a PROVABLE vocabulary value   0
             (unrestricted `.value/.args/.name/.head` on anything: 328,
              an UPPER BOUND — `X.value` on a Var is the commonest idiom;
              a true figure inside it needs dataflow, not a name match)
    shape 4  a predicate class held as a VALUE, called later  31 in 5 bodies
             (UNCHANGED from W1b under the widened net)
    shape 5  __name__/__module__ off a predicate class         0

So the sealed side's whole W4 cliff is the 31 hold-and-call sites, and the
alias blind spot did not hide anything there; it was real only in the
corpus tooling (13 isinstance + 31 field reads, already migrated).
