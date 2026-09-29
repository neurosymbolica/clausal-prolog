# Retire `_CONSTANT_` and give constants an ISO-safe surface

**Raised by the operator 2026-09-10**, on advice from Markus Triska: avoid the leading
underscore. **Sequenced AFTER** `feat/titlecase-is-a-variable-2026-09-10` — see Sequencing.

## Why the spelling is wrong

A constant is spelled `_PI_`, `_MAX_RETRIES_` — one leading and one trailing underscore. To
any Prolog reader a leading underscore is a VARIABLE, and in ISO it specifically marks the
don't-care/singleton convention. So the spelling reads as the one thing a constant is not.

It is also propped up by a special case. `_is_constant_name` is carved OUT of
`_is_logic_var_name` in **all five copies** of that classifier, pinned by
`test_var_classifier_conformance`:

    if _is_constant_name(identifier):
        return False
    if identifier.startswith("_"):
        return True

Retiring the spelling deletes that carve-out from all five, which leaves the variable rule as
one sentence with no exceptions: underscore-led or capital-initial is a variable.

## The cost of retiring: measured, and it is nearly nil

    -constants directive, tracked .clausal        engine: 1 fixture
    module_constant/3, tracked .clausal           engine: 0
    -constants / module_constant/3 downstream     0 files in all four sibling repos

So this is a deletion plus one fixture, not a migration. Re-measure before acting — that is a
fact with a shelf life — but the shape is: nothing real depends on it.

## The operator's proposed replacement

A directive `-constant_value(name, value)` that inserts `value` into the underlying Python module's
globals under the key `name`; `++name` then retrieves it in place. Lowercase `name`, so it
lives in the atom/predicate namespace and cannot collide with the variable rule at all. It
reuses the `++` escape rather than adding a mechanism, and `++name` already works for a bare
name — `docs/exceptions.md:94` uses `++ValueError` bare as a catch/3 catcher.

## Two design questions the proposal has to answer

Neither is an objection; both are things the current mechanism does that the new one must
either keep or knowingly drop.

**1. Freezing.** Today a structured constant (list/dict/set) is FROZEN on declaration,
type-preservingly, and `clausal/logic/constants.py` says why: "constant means constant, so a
structured constant must not be mutable from the Python side — most commonly reached through
a `++` escape holding a reference to the shared term". The proposal's retrieval path IS that
`++` escape, so the hazard is not incidental to it, it is the design. Keep freezing at
insertion, or state that a constant is now mutable through the escape.

**2. Fold vs lookup.** Today the value is embedded at clause construction, so "downstream
(indexing, solve, translation) never sees a name". `++name` is a runtime lookup in module
globals. That is a real semantic change: it costs the constant-folding property that indexing
and the translator currently rely on, and it makes a constant late-bound (rebind the global
and clauses already built change meaning). Decide whether `-constant` should still fold at
construction and merely ALSO expose the global, which would keep both properties.

Also settle: what happens on redeclaration, and whether the groundness gate
(`ConstantNotGroundError`) survives.

## Sequencing — why this is not being done now

`feat/titlecase-is-a-variable-2026-09-10` is in flight and is editing `_is_logic_var_name`,
its five copies, and `test_var_classifier_conformance` — exactly the files this touches. Two
agents in the same predicate at once is the "two moving inputs" failure that has cost this
project repeatedly today. Land that branch first, then do this against a still tree.

It is also strictly easier afterwards: once TitleCase is a variable, the only remaining
exception in the classifier is this one, so the change is visible as a deletion rather than
tangled with a widening.

## Definition of done

- `-constant_value(name, value)` implemented, with the two questions above answered in the commit.
- `-constants(_N_ = ...)`, `_is_constant_name`, and the carve-out gone from all five
  classifier copies; `test_var_classifier_conformance` updated to pin the simpler rule.
- The engine fixture migrated; a test asserting the retired spelling fails loudly.
- Re-measure downstream first and say the number in the commit.


---

# Extension: `-constant_value_units(id, value, units)`, and the `N (unit)` sugar

> **Read the scope correction at the end of this file first.** The sugar is NOT removed
> in this work — usages are converted to named constants and the machinery stays. This
> section explains why removing it is the eventual goal, not what this task does.

**Operator, 2026-09-10.** A three-argument form keeps the unit out of the value, and could let
the `N (unit)` sugar be retired entirely.

## Why this is the strongest argument for the whole direction

The sugar is what makes FUNCTOR POSITION ambiguous. A variable applied to something is read as
a unit annotation — `run(G, X) <- (G(X))` does not call G, it tries to build a quantity and
fails at RUNTIME with "cannot build a Quantity from AttVar: SI prefixes cannot be used as
units". That ambiguity is the ONLY reason the TitleCase rule needs an asymmetry: on 2026-09-10
the operator accepted that `FOO(3)` is legal while `Foo(3)` is refused, purely so a bare Python
class in a body could not silently become a units expression.

**Retire the sugar and that cost disappears.** Functor position becomes unambiguous, and the
variable rule can be uniform in both positions. Combined with retiring `_CONSTANT_` above, the
name rules collapse to: lowercase is an atom or predicate, capital-initial or underscore-led is
a variable, and there are no exceptions anywhere.

## Feasibility: measured, and it is small

Inline unit literals in real code — `<number>(<unit>)` — with comments AND string bodies
stripped:

    engine            128 in 7 files    (the units library's own fixtures/examples)
    domains            ~30 in a few files, dominated by currency in planning-action costs,
                       e.g. cost(days(90), 0(euro), hassle(high)) and MONEY == 1270(euro)
    two sibling trees  5 each, all one currency

**Two earlier counts of mine were WRONG and the record should say so.** A first pass reported
767 and a second 592 for the domains: both were counting legal citations inside string
literals — `"21 U.S.C. 812(b)(2)(B)"`, `"Article 465(1)"` — because I stripped `#` comments
but not string bodies. Downstream code is a text corpus with code in it; that floor is written down
in this project's own notes and I walked into it twice. Anyone re-measuring must strip string
bodies, and should check a known-prose line does NOT match before believing a number.

## The gap the proposal has to close

`-constant_value_units(id, value, units)` gives NAMED quantities. It does not by itself give an INLINE one,
and the real sites are inline: `cost(days(90), 0(euro), hassle(high))`. Retiring the sugar with
no replacement makes a literal quantity inexpressible in an argument. So decide one of:

- **name every literal** — feasible at this scale (a few dozen), and arguably better: `0(euro)`
  becomes something like `no_cost`, which reads;
- **or provide an ordinary term form** for inline quantities, e.g. `quantity(0, euro)`, which
  needs no sugar and no special parse.

Note that `days(90)` and `hassle(high)` in that same expression are ORDINARY functors. The
parser cannot distinguish them from `0(euro)` structurally — which is precisely the ambiguity.
After retirement `0(euro)` is a plain syntax error and `days(90)` still works.

## This reverses a standing ruling — deliberately

`SESSION-HANDOFF-2026-09-10-engine-lane.md` §2 records "Units `N (unit)` stay" as a ruling. The
operator may of course change his own ruling, but it should be recorded as a reversal rather
than drift, and the lanes told, because at least one downstream tree writes currency costs this
way.

## Sequencing

Still after `feat/titlecase-is-a-variable-2026-09-10`. If the sugar is retired, the asymmetry
that branch encodes can be REMOVED in the same change that removes the sugar — so the order is:
land step 3 as ruled, then this. **Superseded in part — see the scope correction at the end of this file: the sugar is NOT removed yet, so the functor rule cannot be simplified in this piece of work.**


---

# RULED 2026-09-10 — and the one consequence that needs building

**Operator's rulings, both direct:**

1. **Retrieval is `++name`**, the explicit escape. A constant is a Python global and `++`
   reaches it, so the spelling never lies and a bare lowercase name stays an atom. Accepted
   cost: a `++` at every use site, which is exactly where constants are meant to be common.
2. **Runtime lookup, not folding at clause construction.** Constants become late-bound.
3. **Do it regardless of instance count.** The rationale is maintainability and it is the right
   one: a threshold, fine or quantity used in more than one place must be updatable in ONE
   place, or some sites get missed. That argument does not depend on how many sites exist
   today — it is about the sites that will exist.

The two are consistent by construction: `++expr` is a `PyThunk` evaluated at run time, so
choosing the escape essentially entails the lookup.

## The consequence: exported domains break unless the EXPORTER folds

Measured on this tree, not predicted:

    applies(X) <- (fine(X, F), F > ++max_fine)

      exports as:  /* WARNING: untranslatable clausal construct: ++(max_fine)
                      Replace with Prolog equivalent manually. */
                   applies(X) :- fine(X, F), F > ??? .

    applies(X) <- (fine(X, F), F > 5000)      exports as:  F > 5000.   (fine)

So under these rulings, **any exported domain that uses a constant emits broken Prolog**. That
lands on the publishable domains, which are a real deliverable, and it is not hypothetical: the
DRY argument says constants will be used for exactly the thresholds and fines those domains are
made of.

**Requirement, not a reversal.** The exporter must resolve a DECLARED constant to its literal
value when emitting `.pl`. The value is known at export time — the declaration is in the same
file — so this is fold-at-export with lookup-at-runtime, which keeps both rulings intact. Any
`++` over something that is NOT a declared constant must keep today's loud untranslatable
warning.

Add to the definition of done:

- `-constant_value`/`-constant_value_units` declared names export as their literal value, with a test
  asserting the exported `.pl` for a rule that uses one, and a test that a non-constant `++`
  still warns.
- Tell a downstream exporter before it lands; they hold a byte-identical baseline across the roster
  and will want to re-run it, since "every file differs" is the diff that hides a regression.


---

# SCOPE CORRECTION 2026-09-10 — keep the units machinery, convert usages only

**Operator:** do not remove the units machinery yet. Only convert USAGES to named constants.

This is deprecation in the right order — empty the room before demolishing it — and it changes
three things above.

**1. `N (unit)` keeps working.** `_is_unit_expr`, the annotation sugar and their tests stay
exactly as they are. Nothing about the sugar is deleted in this piece of work.

**2. The TitleCase asymmetry CANNOT be dropped yet, and the earlier note saying "then simplify
the functor rule" is wrong until the sugar actually goes.** The asymmetry exists because a
variable in functor position is a unit annotation; while that remains true, `Foo(3)` must keep
being refused. So the ordering is now:

    step 3 (in flight)  ->  -constant/3 + retire _CONSTANT_  ->  convert usages
                        ->  [later, separate] retire the sugar  ->  drop the asymmetry

**3. Retiring the sugar gets an exit criterion instead of a date.** It becomes eligible when a
census of real usages returns zero. Re-measure with string bodies AND comments stripped — see
the census section above for why, and check a known-prose line does not match before believing
the number.

## What "usages" means here

Convert real uses: the domain planning-action costs (`cost(days(90), 0(euro), …)`), the
currency comparisons, and the handful in the two sibling trees.

**Do NOT convert the units library's own fixtures and examples** — the engine's ~128 sites in 7
files. Those exist to TEST the sugar, and while the sugar is supported its tests must keep
testing it. Converting them would delete the subject of the test rather than migrate a usage.
If that reading is wrong, it is the one assumption in this file worth correcting before the
work starts.

## Consequence for the conversion

Because the sugar stays, the conversion has a working fallback the whole time: any site that
turns out awkward to name can simply be left as `0(euro)` and revisited. The conversion cannot
break anything by being incomplete, which is the point of doing it in this order.


---

# `++` IS translatable — operator's correction, and what two real Prologs say

**Operator, 2026-09-10:** translate `++` as a prefix operator `++/1`. In Syntax 1 Clausal it
looks up the constant; it just happens to be done in Python.

He is right, and my earlier "untranslatable" framing was wrong — that `???` is a deficiency in
the EXPORTER, not a property of the construct. Measured rather than argued, on the box, against
both reference systems with `:- op(200, fy, ++).` in the file:

    X = ++max_fine        Trealla: term_ok(++max_fine)     Scryer: term_ok(++max_fine)
    6000 > ++max_fine     Trealla: type_error(evaluable,(++)/1)
                          Scryer:  type_error(evaluable,max_fine/0)

Also confirmed on the import side: with the `op/3` declaration present, this project's own
reader PARSES `++max_fine` correctly; only the translator refuses it, with "Prolog functor
'++' cannot be translated to a Clausal predicate name". So the round trip is a small mapping
job, not a redesign.

## The split, and why it means BOTH things are needed

**As a TERM** — unification, argument position — `++name` exports, parses and round-trips
cleanly in both systems. Nothing more is required.

**In ARITHMETIC** — `>`, `is`, any comparison — both systems raise `type_error(evaluable, …)`.
ISO's evaluable-functor set is fixed and `++/1` is not in it, so no conformant system will
evaluate it. And arithmetic is exactly where the DRY case lives: a threshold or fine is used as
`F > max_fine`.

So exporting `++` as an operator and folding constants are **not alternatives**. The rule:

- `++` over a **declared constant** → emit the LITERAL VALUE. Runs anywhere, any position,
  needs no `op/3` and no cooperation from the target.
- `++` over **anything else** → emit `++(...)` as a prefix operator, with the `:- op(200, fy,
  ++).` declaration in the output, instead of today's `???` and "untranslatable" warning.
  Well-formed, honest, round-trippable, and the target decides what it means.

That is strictly better than today in both directions, and it keeps the operator's reading of
`++/1` as a real operator whose meaning travels with the language rather than the file.

## Definition of done, revised

- Declared constants export as literals; a test asserts the exported `.pl` for `F > max_fine`
  RUNS in a reference system rather than merely parsing.
- Non-constant `++` exports as the prefix operator with its `op/3` declaration; a test asserts
  it parses in a reference system. The `???` output goes.
- The importer maps `++(X)` back to the Clausal escape rather than refusing it as a predicate
  name, closing the round trip.
- Reference systems are on the box: `/workspace/scryer-prolog/target/release/scryer-prolog` and
  `/workspace/trealla-prolog/tpl` (neither is on PATH).


---

# Term rewriting makes `++constant` portable — the idea holds, the PACKAGING does not yet

**Operator, 2026-09-10:** in Scryer, `++constant` could be implemented with term rewriting, so
this is actually portable. Instruction: add the expansion prelude to the translation support
libs **once it is seen to work**.

**It is not yet seen to work, so nothing has been added.** What is proven and what is not,
measured on the box against both reference systems:

## PROVEN — the rewriting itself is sound

    expand_consts((6000 > ++max_fine), G)  ->  expanded(6000>5000)   then  runs

So a load-time rewrite genuinely turns the non-evaluable operator form into ordinary
arithmetic that any conformant system executes. The operator's reasoning is right: this does
not need an evaluable-functor extension, and it is portable in principle.

Also proven, each in isolation in Scryer: the `fy 200` operator itself (`op_ok(++foo)`), a
clause term as an argument (`clause_arg_ok((a:-b))`), both together
(`both_ok((a:-1> ++f))`), a VARIABLE operand in a clause head (`var_operand_ok(foo)`), and a
space before the operand (`spaced_ok(++n)`). None of the obvious suspects is the blocker.

## NOT PROVEN — delivering it as a prelude fails in both, differently

    same file defining term_expansion/2   Trealla: hangs (rc=124)   — self-application loops
    prelude via :- include(...)           Trealla: hangs (rc=124)
                                          Scryer:  syntax_error(incomplete_reduction) at the
                                                   prelude's own clauses, and the error line
                                                   MOVES with the file, so it is positional

Two systems, two unrelated failures, and every construct passing alone. That is a packaging
problem worth solving properly rather than guessing at: candidate directions are a real module
(`:- module/2` + `use_module`) instead of textual `include`, guarding `term_expansion/2` so it
cannot rewrite its own predicates' clauses, and checking whether each system applies a
`term_expansion/2` defined in an imported module to the IMPORTING file at all — behaviour
differs and is not ISO.

## What to do

Solve the packaging, prove it by RUNNING an exported domain in both reference systems, and only
then add the prelude to the translation support libraries. The acceptance test is not "it
parses" — it is `applies(a)` answering correctly through the rewrite, in both systems.

Reference binaries (neither on PATH):
`/workspace/scryer-prolog/target/release/scryer-prolog`, `/workspace/trealla-prolog/tpl`.

Note this does NOT remove the need to fold declared constants at export: folding produces a file
that runs with no prelude, no `op/3` and no cooperation from the target. The prelude is what
makes a NON-constant `++` portable, and it is the better story for round-tripping. Both remain
worth having, for different reasons.


---

# UPSTREAM: the predicate is `constant_value/2` — Markus Triska, 2026-09-10

The operator put this convention to Markus Triska, who advises both Scryer and Trealla. His
answer: it should be doable, and **the predicate should be called `constant_value/2`.**

That changes the status of the name. It is no longer ours: it is a proposed cross-
implementation convention with the upstream advisor's blessing, so the exported `.pl`, the
expansion prelude and any Clausal-side reflective builtin must use that exact spelling and
arity. Earlier drafts in this file say `clausal_const/2` — those are superseded.

If the two systems eventually implement `constant_value/2` natively, the prelude becomes
unnecessary there and the exported file gets simpler rather than more complex. That is a much
better end state than a Clausal-specific mechanism, and it is worth the naming discipline now.

## The arity raises a real question the 3-argument directive was meant to answer

`constant_value(Name, Value)` has **two** arguments. The Clausal directive the operator
proposed is `-constant_value_units(id, value, units)` with **three**, specifically so the unit is kept out
of the value. Those are different layers and not a contradiction, but they meet at the export
and something has to give:

    -constant_value_units(max_fine, 5000, euro)      what does this export as?

      (a) constant_value(max_fine, 5000)            unit LOST
      (b) constant_value(max_fine, q(5000, euro))   unit inside the value — the thing the
                                                     3-arity form exists to avoid
      (c) constant_value(max_fine, 5000) plus a separate unit fact

Not a decision to take silently. (b) is probably right for an exported file — the receiving
system has no unit system, so a quantity has to be a term — but it means the Clausal-side
separation is a Clausal-side property that does not survive export, and that should be stated
rather than discovered. Worth putting back to Markus if the convention is meant to carry
united quantities at all, since that is a question about the convention and not about Clausal.

## Naming on the Clausal side

`module_constant/3` (`inspection.py:747`) is today's reflective predicate:
`module_constant(Module, Name, Value)`, where `Name` is the atom of the full declaration
spelling including the underscores. When `_CONSTANT_` is retired the underscores go, and this
is the natural moment to align the name with the upstream one. Decide whether Clausal exposes
`constant_value/2` (module-implicit) alongside or instead of `module_constant/3`.

The name is FREE — checked rather than assumed. The single `constant_value` occurrence in the
tree is `tests/test_constants.py:445`, the test function name
`test_true_false_undefined_as_constant_values`. No predicate, builtin or directive uses it.


---

# `constant_value_units/3` — the operator's sibling, and the evidence for it

**Operator, 2026-09-10:** propose a sibling `constant_value_units/3` alongside Markus's
`constant_value/2`, described as a way to INDICATE units so they are available to static or
runtime dimensional analysers. Clausal already has the runtime analyser, in `Quantity`.

**This answers the arity question above, and better than the options I listed.** The value in
`constant_value/2` stays a plain number, so arithmetic works in any system with no cooperation
at all; the units travel separately as metadata for whoever can use them. Nothing is lost and
nothing is smuggled into the value.

    -constant_value_units(max_fine, 5000, euro)

      exports as:  constant_value(max_fine, 5000).
                   constant_value_units(max_fine, 5000, euro).

Emit BOTH rather than deriving one from the other. Each then stands alone: a system that knows
only `/2` gets working arithmetic; an analyser reads `/3`. The redundancy of the value is worth
it for that, and since the file is generated the two cannot drift — a consistency check in the
exporter is cheap insurance if wanted.

Note the consequence plainly: an exported program is DIMENSIONLESS at run time unless the
target implements dimensional analysis. That is not a regression — no ISO system has one — and
it is precisely what the `/3` fact exists to enable.

## The evidence for the upstream proposal, measured

The claim that Clausal already has a runtime dimensional analyser is true and worth being able
to demonstrate, since it is the argument for the convention being useful rather than
speculative:

    eval_(3 (metre) + 4 (metre), S)     ->  S = 7 metre
    eval_(3 (metre) + 4 (second), S)    ->  UnitsMismatch: Unit mismatch for add: metre vs second
    eval_(12 (metre) / 4 (second), S)   ->  S = 3.0 metre·second^-1

So it adds like units, REFUSES unlike ones with a named error rather than silently coercing,
and derives compound dimensions. That is a real analyser, not a units label.

(Method note for whoever re-runs these: `is` in Clausal is UNIFICATION, so `S is 3 (metre) +
4 (metre)` binds the unevaluated TERM and proves nothing about dimensions. Use `eval_/2`. A
first pass of mine used `is` and produced three unevaluated expressions that could easily have
been read as "no dimensional checking".)

## Open, for upstream rather than for us

Whether `constant_value_units/3` should carry the VALUE at all, or be
`constant_value_units(Name, Units)` keyed to the `/2` fact. Carrying it makes each fact
self-contained; omitting it removes the redundancy. That is a question about the convention,
so it belongs with Markus rather than being settled here.


---

# THE SPELLING, settled 2026-09-10 — one name in all three places

**Operator's clarification:** the DIRECTIVES are `constant_value/2` and
`constant_value_units/3` — in Clausal and in the translation support libraries.

So the name does not change shape as it crosses. The directive, the exported fact and the
support-library predicate are the same term:

    Clausal source     -constant_value(max_fine, 5000)
                       -constant_value_units(max_fine, 5000, euro)

    exported .pl       constant_value(max_fine, 5000).
                       constant_value_units(max_fine, 5000, euro).

    support lib        constant_value/2, constant_value_units/3

Export becomes near-identity: strip the leading `-`, add the full stop. Nothing to translate,
nothing to keep in sync, and no second vocabulary for a reader to learn. Every earlier
`-constant(...)` spelling in this file has been corrected in place rather than left to
contradict this section — the whole point of today's work was documents that state the rule
they replaced.

**Consequence worth noting:** a `-constant_value` directive and a `constant_value/2` fact in an
imported `.pl` are now the same thing said in two syntaxes, so the IMPORT direction has an
obvious reading too — a `.pl` carrying `constant_value(max_fine, 5000).` can be understood as a
constant declaration rather than an ordinary fact. Whether the importer should do that
automatically, or only under a flag, is a real question and is NOT settled here: silently
reinterpreting a plain fact as a declaration would be exactly the kind of implicit behaviour
this project keeps removing.

**Also still open, and now sharper:** if `constant_value_units/3` carries the value, then
`-constant_value_units(max_fine, 5000, euro)` alone is enough to declare the constant, and
`-constant_value` is only needed for a dimensionless one. Decide whether the `/3` form implies
the `/2` fact on export (emit both, as recorded above) or whether an author must write both
directives. Emitting both from the `/3` directive is the better default: one declaration, two
facts, no redundancy in the SOURCE.


---

# SCOPE, settled 2026-09-10 — two syntaxes, and the directive belongs to only one

**Operator's terminology, adopt it:** Clausal has **ISO syntax** (what was called "syntax 1")
and **seam syntax**. They are different surfaces with different needs.

**The constants directive is for the ISO syntax.** In seam syntax there is much less need for
it: Python is right there. A constant is a Python module global, and `++name` reaches it. No
directive, no new mechanism, no registry — the language already has the answer.

That splits this file's work into three pieces with very different readiness, and the earlier
sections should be read against this split rather than as one job:

## (a) NOW — retire `_CONSTANT_` from seam syntax

Independent of everything else and immediately valuable. `-constants(_N_ = ...)` and
`_is_constant_name` go; the replacement in seam syntax is a plain Python module global reached
with `++name`. This deletes the carve-out from all five `_is_logic_var_name` copies and leaves
the variable rule with no exceptions. Measured cost: 1 engine fixture, 0 downstream. Sequenced
after the TitleCase branches, which edit the same predicate.

## (b) LATER — the directives, in ISO syntax

`-constant_value/2` and `-constant_value_units/3` are ISO-syntax directives. That surface is
gated on the reader-fed compiler, which does not exist yet (see
`implementation_plans/iso-conformance-gap-survey-2026-09-09.md`, item 4 — the reader emits
`ReaderItem`s and nothing consumes them). So the directives cannot be built now, and this file
should not pretend otherwise.

## (c) WITH (b) — the export side and the support libs

`constant_value/2` / `constant_value_units/3` facts in the exported `.pl`, plus the expansion
prelude. Only needed once a program can DECLARE a constant in ISO syntax, so it rides with (b).
The prelude packaging is separately unsolved — see the section above.

**Re-reading note:** sections earlier in this file that describe "the constants work" as one
task predate this split. The naming, the `++` retrieval ruling, the runtime-lookup ruling, the
export requirement and the measured evidence all still hold; only the SEQUENCING changes.

---

# UPSTREAM STATUS — presenting at the Scryer meetup, October 2026

Markus Triska thinks the convention looks generally useful and has asked the operator to
present it at the next Scryer Prolog meetup in October and gather feedback.

So this stops being an internal design and becomes a proposal to a community. Two consequences:

- **The open questions in this file are the agenda**, not loose ends: whether
  `constant_value_units/3` carries the value or is keyed to the `/2` fact; whether both facts
  are emitted or one derived; whether an importer may reinterpret a `constant_value/2` fact as
  a declaration or must be told to. Each is a question about the CONVENTION and is better
  answered by that room than by us.
- **The evidence should travel with it.** The dimensional-analysis measurements above are the
  argument that this is useful rather than speculative: like units add, unlike units raise a
  named error, compound dimensions derive. Worth having runnable rather than quoted.

Nothing in this file should be implemented in a way that presumes the convention's final shape
before that feedback, EXCEPT (a), which does not depend on it at all.


---

# UNITS PARSING: opt-in, not removed — operator's ruling, 2026-09-10

Supersedes the earlier "retire the sugar" framing AND refines the "keep the machinery"
correction. The end state is neither deletion nor status quo:

**Units parsing is DISABLED BY DEFAULT, with a directive to enable it.** The machinery stays
and stays supported; a file that wants `N (unit)` says so.

## Preconditions, in order

1. The constants directives land (ISO syntax — so this waits on the reader-fed compiler).
2. Every number-with-units is converted to a named constant.
3. Then flip the default to off, and add the enabling directive.

Nobody loses the feature at any point, and no file breaks at the moment of the flip, because
step 2 has already emptied the room.

## Why this is the right shape, and what it buys

`FOO(3)` — a variable in functor position — is a unit annotation today. ISO refuses that
outright: verified in Trealla as `syntax_error(variable_cannot_be_functor)`. So the sugar is
the ONE remaining reason Clausal accepts a variable as a functor.

With units parsing off by default, the default surface refuses a variable in functor position
for BOTH spellings, uniformly, which is exactly ISO. **The TitleCase functor-position asymmetry
the operator accepted on 2026-09-10 can then be lifted for the default surface** — the reason
for it was precisely that `Foo(3)` had to be refused so a bare Python class could not silently
become a units expression, and with no units expression to become, the exception has no job.

Inside a file that enables units parsing the asymmetry returns, scoped and explicit. That is
acceptable in a way the global default was not: it is a property of a file that asked for it.

## Note for whoever writes the flip

State in the directive's docs that enabling units parsing makes the file non-ISO in one
specific, nameable way — a variable may appear in functor position — rather than describing it
as a feature switch with no cost. A reader choosing it should know what they are trading.


---

# 2026-09-11 — RULED AND MOSTLY BUILT, on `feat/lowercase-constants-2026-09-11`

Everything above this line is superseded where it conflicts. The rulings below are the
operator's, all direct, all on 2026-09-11.

## The surface, as ruled

| written | means | mechanism |
| --- | --- | --- |
| `pi` | the ATOM `("pi",)` — always, never the value | compiled to a cell literal |
| `++pi` | the constant's VALUE | Python module-global lookup (seam); term expansion (ISO) |
| `'pi'` | the same atom | quoted form |

**A name can be a constant AND an atom, and that is the ordinary case, not an edge one.** The
operator corrected me on this twice: my first implementation made a bare name yield the VALUE,
and my second refused the combination outright. Both were wrong. One name carries both
readings, and `constant_value(pi, 3.14159)` alongside `-module(m, [pi])` is how it is written.

**Declaring a constant does NOT declare the atom** — a conservative reading I chose and flagged
rather than one he ruled. A bare `pi` still needs its atom listing, and the diagnostic is the
ordinary strict-atoms one. Starting strict leaves the relaxation available; starting permissive
could not be tightened later without breaking files. **Worth putting back to him.**

## The directive is a FAMILY, positional, one per line

    -constant_value(pi, 3.14159)
    -constant_value_units(max_fine, 5000, euro)

`-constants(a = 1, b = 2)` is retired and raises a message naming the replacement. His reasons,
both recorded because they generalise: the keyword form **could not have a family** (there is
nowhere to put a third argument on one pair), and **one line per constant reads better in a
diff**.

The units form binds `name = Quantity(value, units)` — the identical object the `5000 (euro)`
annotation sugar builds — so the unit is kept out of the value.

## The reflective predicate is `constant_value(atom, ground_term)`

Markus Triska's name, so the spelling and arity are not ours to vary. `Name` is an ATOM, not a
string. `module_constant/3` stays for the case where the module matters.

**One compromise, and it needs his word.** The module-implicit reading would need the CALLING
module, which a builtin does not get — the registry hands dispatch functions their arguments
and a trail and nothing else. So `constant_value/2` enumerates every loaded Clausal module's
own declarations, exactly as `module_constant(-Module, +Name, ?Value)` does. Two modules
declaring the same name both answer. That matches a Prolog system's one flat program, but it is
not what "module-implicit" would mean here.

## A security requirement he raised, and it is built

**A constant declaration must not overwrite an existing binding.** It lowers to a module-level
assignment, so left unchecked it silently replaces an import, a helper `def`, a functor class or
an imported predicate — the value would be right and every other use of the name would quietly
become the constant. Refused at load time, checked once the whole module has been walked (a
`def` BELOW the declaration overwrites it just as surely as one above), with an ATOM of the same
spelling whitelisted because that is the intended pairing.

The snapshot of the file's own bindings is taken BEFORE the walk. Read afterwards it includes
generated code — the `-module` rewrite emits an assignment for every declared atom — so `pi`
looked like a hosted binding and the constant/atom pair this design exists for was refused.

## Two defects found by building it, both fixed

- **A structured constant did not unify with its own literal.** `-constant_value(origin,
  point(0, 0))` stored a functor INSTANCE, because the RHS runs before
  `_process_declarations` has unbound the functor class, while a clause literal `point(0, 0)`
  builds the cell `("point", 0, 0)`. Measured: 0 answers both ways. Invisible while a bare
  reference folded through the clause builder (which converted on the way in), and exposed the
  moment `++name` — which hands the stored object straight to the goal — became the only way to
  read a constant. Fixed in `_freeze`, which now converts an instance to its cell.
- **Order dependence.** `-constant_value` before `-module` gave the atom where the value was
  wanted: the `-module` rewrite also emits a guarded atom assignment at its OWN position, which
  ran after the constant's. Both emission sites now skip a name already declared as a constant.

## WHERE IT STANDS — and the blocker

Committed, gated, on the branch: the lowercase spelling, the classifier carve-out deletion (all
five copies), the import changes, and the test/doc migration. That part gated CLEAN — 144
failures, name set identical to the baseline.

**Everything in this section is UNCOMMITTED and the full suite SEGFAULTS with it** (exit 139,
inside `tests/test_clpb.py`, ~37% in). Established, not guessed:

- The baseline runs the identical 87-file prefix clean; the branch does not. So it is mine.
- It is CUMULATIVE, not a bad pair: the minimal pair that the bisect pointed at passes alone,
  and 120 tests pass together.
- It is deterministic under `-q` (three runs) and ABSENT under `-v` — the same tests, the same
  order. That points at allocation pattern rather than logic.
- Reverting `clausal/templating/term_rewriting.py` to the last commit makes it go away;
  reverting `constants.py`, `compiler_v2.py` or `inspection.py` individually does not.
- Inside `term_rewriting.py` it is NOT the `visit_Name` change and NOT the overwrite guard —
  both were disabled separately and it still crashed. That leaves the directive-family handler,
  the dispatch change, and the two atom-assign skips.
- The faulthandler stack shows NO test-function frame under `pytest_pyfunc_call`, which is what
  a crash inside a C call — or inside GC triggered at that allocation — looks like.

The working copy of the four changed engine files is preserved at
`/home/node/.claude/jobs/af5b4bbe/tmp/wip/`. **Do not land this half until the segfault is
understood.** A latent refcount bug in a C extension that a Python-side allocation change merely
perturbs is a live possibility and would be worth finding on its own account.

## The segfault is GC-VISIBLE — narrowed further, 2026-09-11 (late)

Two more measurements, both controls rather than inferences:

- **Disabling the garbage collector makes it disappear.** The same 87-file prefix, same order,
  with `gc.disable()` in a `pytest_configure` hook: exit 1 and the two standing failures, no
  crash. So the fault is something the collector traverses — a freed object still reachable
  from a container, or a missing incref, in one of the C extensions. Python-side changes only
  move WHEN a collection happens.
- **The crashing test is
  `tests/test_clpb.py::TestBoolHook::test_bind_to_invalid_int`**, not the `test_clpb.py` file
  label the `-q` progress dots suggested — those lag the file heading, and reading them cost
  two wrong bisects. It passes alone (115 tests in that file pass alone) and needs the long
  prefix.
- **The baseline does NOT crash even under aggressive GC** (`gc.set_threshold(1, 1, 1)`, same
  87 files): exit 1. So "latent bug my change merely perturbs" is a HYPOTHESIS, not something
  measured — the honest statement is that the branch triggers it and the baseline does not.

Next step for whoever picks this up: build the extensions with assertions
(`Py_DEBUG`/`--with-pydebug` or at least `PYTHONMALLOC=debug`) and run the prefix, which turns
a use-after-free into a diagnosed abort at the point of misuse rather than a segfault later.
`PYTHONMALLOC=debug` alone is one command and worth trying first.

## It is not attributable to any single change — 2026-09-11, final narrowing

Every sub-change in `term_rewriting.py` was disabled INDIVIDUALLY, each edit asserted to have
actually applied (one earlier round used `str.replace` with no assert and proved nothing —
that is the fail-open shape again, in the bisect instrument itself):

| disabled | result |
| --- | --- |
| the `visit_Name` constants branch (restored to the old behaviour) | still crashes |
| the no-overwrite guard AND its pre-walk snapshot | still crashes |
| both `-module`/`-private` atom-assign skips | still crashes |
| the directive handler made UNREACHABLE at dispatch | still crashes |
| the whole file reverted to the last commit | **clean** |

So no single edit causes it, and the whole set does. With `gc.disable()` the same set is clean.
The conclusion the measurements support is that this is a **latent GC-visible fault that a
large enough perturbation of the transformer exposes**, not a defect in any one line — the
changes shift allocation and collection timing, and something in a C extension is reachable by
the collector after it should not be.

`PYTHONMALLOC=debug` does NOT catch it before the segfault, which argues against a plain
use-after-free of a Python-allocated block and for a raw `PyObject*` held in a C struct without
a reference, dereferenced after collection.

What that means for landing: **the committed half of this branch is unaffected and gated clean**
(failure name set identical to the 144-name baseline). Only the uncommitted half is blocked, and
it is blocked on a C-level defect that is worth finding on its own account, whoever it belongs
to. A gdb backtrace on the crashing run, or a `--with-pydebug` interpreter, is the next step;
guessing at more Python-side rearrangements is not.
