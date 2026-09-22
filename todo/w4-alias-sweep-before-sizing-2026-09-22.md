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

## Downstream result 2 of 3 (the export lane, 2026-09-22) — and a LIVE break

Planted positive first (it failed on its first run — the sample had two
`.__name__` where one was expected — and was fixed before any number was
printed). Three trees, ~190k lines.

    shape 1  isinstance      9 + 0 + 1  (their first count said 6: the pattern
             admitted only a BARE class name and missed the dotted
             `reflection.Clause` receiver — corrected by them) — and one is a GATE MODULE that
             imports Clause/Goal/ModuleDirective by name and does
             `isinstance` AND `.name` reads together: BROKEN ON MAIN TODAY
             (constructors since W2), silently False on the P2 candidate.
             Told them: migrate to is_v/vfield now with a positive control.
             One more corpus tooling site the earlier 13 missed — told the
             corpus lane.
    shape 2  type-name string: the 1 test already known; bare quoted
             names 23, mostly prose, unsplit
    shape 3  NOT a count: the token census (1623/494/270) is meaningless
             without receivers. The USABLE denominator: only 6 files in
             those trees import reflection or PredicateMeta at all, so a
             cell-field read can only live there. Read the set, not a number.
    shapes 4, 5  NOT answerable statically (receiver typing); the
             instrument would be a runtime hook, as for the division census.
    corpus   clean: 1 tooling isinstance (above), 1 .seam comment.

Their instrument (selftest-refusing) takes `label|root|globs` triples.

**Follow-up (export lane, same day):** two of their three broken files
migrated to `is_v`/`vfield` with a positive control (a domain the gate MUST
flag, before and after, plus a check that `is_v` actually matches). The
third needs a GENERIC walk — "this node's fields without knowing its type"
— which `is_v`/`vfield` cannot give; built as `reflection.vkind` /
`vfields` / `vitems` on feat/reflection-vkind-2026-09-22 (with `is_v` and
`vfield` finally in `__all__`).

## Census CONTRACT (the corpus lane, adopted 2026-09-22) — two numbers, never one

    Q1  BROKEN NOW      sites that fail on main today (W2 made the nine
                        constructors functions)  -> sizes the REPAIR, which
                        happens regardless of W4
    Q2  BLAST RADIUS    sites that WORK today and stop when the class goes
                        (`isinstance(x, PredicateMeta)` at a classification
                        site is the type specimen: verified live, True today,
                        `pred._clauses` raises but the metaclass is intact)
                        -> sizes W4

Today's 8 / 9 / 10 / 13+31 were all correct answers to DIFFERENT unstated
questions (alias-pattern matches; the same with a dotted receiver; sites
broken by W2; isinstance vs field reads). A local `class Atom` in a test
file is OUT (name resolution stated, with an UNRESOLVED bucket rather than a
silent choice); three receiver spellings incl. `reflection as R` ->
`R.Clause`; per-shape denominators (shape 3's = files that can obtain a
cell); a planted positive per shape with its expected count asserted.
Definition: the corpus lane's `_w4-census-definition.md`, under review by the
export lane. **NOT STARTED — waits on the operator's go.** Correction to
result 2 above: the export lane's sweep covered THREE trees, not the corpus
only; the differing counts were definition, not scope.

**Withdrawn (export lane, same day): the "6 files that import reflection"
denominator for shape 3.** A callee that receives a cell as a PARAMETER
reads its fields with no reflection import and no constructor call, so the
importing set is not the set that can hold a cell: measured 7 name
reflection, 224 read a cell-ish field, 6 both, 218 read without naming.
Neither 6 nor 224 is the answer; the record is a LOWER BOUND with its rule
stated and the remainder unexamined. Rule kept: a sweep verifies its own
arithmetic; only a reader verifies its premises.

The generic accessors (`reflection.vkind` / `vfields` / `vitems`) LANDED on
main at 05ebcd91.

## All three broken downstream gates closed (export lane, same day) — and a
## CORRECTION to guidance given here

Migrated with positive controls: the clause-less gate (was deciding
blind), the ledger tool (dotted receivers), the ordered-vocab gate
(scanning nothing; `vitems` was the accessor it needed). Each guarded for
both eras, since pinned study trees have no `vitems`/`vfield`.

**WRONG guidance, measured before it was applied: a BODY GOAL in a reified
term (`Unify`, `And`, ... — `simple_ast` nodes) is still a plain OBJECT,
not a cell.** `vkind(unify)` is None and `cell_functor(unify)` raises. Only
the nine VOCABULARY names moved to cells. So a generic walk is
`vitems(node)` FIRST (None is the dispatch), with the object-era
`__dict__`/`_fields` branches kept beneath it for body goals; a
`type(node).__name__ == "Unify"` test stays correct. Do not tell the next
migrator to swap it for `cell_functor`.

Two remaining failures in that gate's suite are stale TITLECASE heads in
the tests' own inline fixtures (a load-time error since 2d48769f), not W2's.

## Downstream result 3 of 3 (the corpus lane, 2026-09-22) — THE CENSUS IS IN

    ENGINE 4f404716 start = end (a first run VOIDED when main moved mid-census)
    POPULATION 9233 .py scanned / 9233 parsed / 0 unparsed / 0 unresolved

    shape                                     Q1 broken-now       Q2 blast radius
    1 isinstance through an in-scope name     0                   1  (the classification site)
    2 type(x) is Name / literal "Name"        19 SILENTLY WRONG   22 (19 live + 3 tests)
    3 cell-field read (LOWER BOUND)           4                   4
    4 class held as a value, called later     NOT STATICALLY ANSWERABLE
    5 .__name__/.__module__ off a predicate   NOT STATICALLY ANSWERABLE

**A THIRD CATEGORY, neither broken-loud nor fine-until-W4: SILENTLY DEAD
NOW.** One downstream assessment module defines `_kind(term) =
type(term).__name__`; every reified item is a tuple, so all 18 of its
`_kind(x) != "Clause"`-style guards are permanently true and the module
matches nothing, returns nothing, raises nothing. Its importer is the
classification site. `reflection.vkind` (main 05ebcd91) is the drop-in:
`_kind = vkind` moves the contract from "the type's name" to "the
vocabulary's name". Repair is the corpus lane's, awaiting their operator.

Shape 3's lower bound is weaker than it looks: that same module holds 30
field reads and was OUTSIDE the "names reflection" denominator (it imports
`reify_file` by name). Read shape 3 as 4 confirmed + at least 30 in one
known file; the true figure needs the runtime pass shapes 4/5 need.

Two instrument bugs fixed mid-run: an unresolvable binding counted as a
hit; `from clausal import reflection as R` invisible (caught by the
planted positive). Planted positives 3/3, 1/1, 2/2.

**W4 sizing, downstream, from all three results:** the sealed bodies'
31 hold-and-call sites (migrate by wrapping `--handle(X)` once the
boundary pieces land); 1 classification site + 22 type-name sites +
field reads in a handful of tooling files, all migratable to
`is_v`/`vkind`/`vfield`/`vitems` today; and a runtime-hook pass for
shapes 4/5 outside the sealed bodies, not yet built.
