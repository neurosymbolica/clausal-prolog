# Constants resolve lexically: declared here, or imported here

**Status**: design, awaiting review. Operator ruled the direction 2026-09-12 (import-only;
module-prefixed access deferred).

## The problem, measured

`constant_number_units/3` is keyed on the constant's ATOM. An atom is global by name, so two
modules declaring `fee_x` register under one key. The result is not merely a leak — it is
backwards:

| you ask about | today |
| --- | --- |
| a constant another module declared, **not** imported | **you get their answer** |
| a constant you **did** import | `[]` — silent |
| an in-scope atom that is no constant | `[]` — silent |
| a name not in scope at all | strict_atoms error ✔ |
| `constant(name)` for an undefined name | **SyntaxError at LOAD** ✔ |

**The relation answers for modules you did not import, and stays silent for the one you did.**
`-import_from(prov, [fee])` carries the VALUE — `++fee` works — but not the declared pair.

Reproduced with a clean two-module probe using plain float literals, so it is independent of
any recent work. Filed as
`todo/constant-number-units-3-answers-across-modules-2026-09-12.md`.

### Why it matters beyond a duplicate row

The `/3` channel exists for **fidelity to what this declaration said** — so a gate can check that
a parameter's unit matches the unit its NAME claims. An answer from another module is not extra
data: `once/1` or any first-solution consumer takes whichever module loaded first, so **load
order decides**. Same family as the `-import_from` module/profile-key shadow closed earlier
today: silent, order-dependent, invisible until two things share a name.

## The rule

**A constant is in scope for `/3` if this module declared it, or imported it.** Nothing else.

This is the rule the language already uses for atoms and predicates, and it needs **no new
syntax**: strict_atoms already refuses a name that was neither declared nor imported, so the
import this rule requires is the import the author is already writing.

Three parts:

1. **`/3` filters by the querying module.** `register_constant_units` already takes and records
   a module; the relation does not consult it at query time. It will.
2. **`-import_from` carries the declared pair**, not just the value. This fixes the half that is
   silent today, and is what makes (1) usable rather than merely stricter.
3. **A BOUND name in scope that is no constant here RAISES.** Operator: referencing a constant
   that was never defined should be an error. `constant(name)` already sets this bar and clears
   it at LOAD time; `/3` should match it, at load where the name is a literal.

### The constraint the measurement forces on (3)

`/3` with an **unbound** first argument legitimately enumerates — measured, 2 rows for a module
with 2 constants. So the raise applies only to the bound case:

    constant_number_units(fee_x, N, U)   fee_x bound, no such constant here  -> RAISE
    constant_number_units(C, N, U)       C unbound                           -> enumerate

Enumeration must also be filtered by (1), or the leak returns through the back door: an unbound
query would otherwise enumerate every module's constants.

## What is NOT in this change

* **Module-prefixed access** (`prov.fee_x`). Deferred by the operator. Dotted constants do not
  resolve at all today (`++prov.fee_p` is a `NameError`), and the design overlaps
  `todo/qualified-unit-declarations-have-no-slash-3-answer-2026-09-11.md`, whose
  `_units_ast_to_term` returns `None` for an `Attribute`. Both dotted questions should be
  settled by one design, later.
* **`-hide`.** It already mangles the atom, so a hidden constant's key is module-unique and
  cannot collide. That makes it the answer for "this constant is mine alone" — the private half,
  not the general rule. Unchanged here.
* **The VALUE side.** `constant(name)` already raises for an undefined name, and does it at
  LOAD: `constant(never_defined)` is a `SyntaxError` saying "nothing declares ...". Untouched,
  and it is the bar `/3` should meet — a compile-time refusal beats a runtime one.

  (Note on spelling, corrected by the operator 2026-09-12: the value of a constant is reached
  with **`constant(name)`**, not `++name`. `++` remains correct for reaching PYTHON objects —
  `++"EUR"`, `++UnitsMismatch(M)`, the `++()` escape — and still happens to resolve a constant,
  but without the load-time check: `++never_defined` loads clean and fails at runtime only if
  the clause executes. corpus-lane's census independently found the corpus uses `constant(name)`
  exclusively.)

## Error shape

The raise should name the constant, the querying module, and the way out — and, where the name
IS declared elsewhere, say so, because "no such constant" is actively misleading when the
constant exists one import away:

    constant_number_units: `fee_x` is not a constant in module `user`.
      It is declared in `prov` — add -import_from(prov, [fee_x]).

Naming the other module is the difference between an error that stops you and an error that
tells you what to type. The information is in the registry already.

## Testing

TDD. The load-bearing cases:

* two modules declaring one name — the querying module gets **its own, once**
* an imported constant answers `/3` (fails today)
* a bound in-scope non-constant raises, and the message names the declaring module when there
  is one
* an **unbound** query still enumerates, and enumerates only this module's
* `-hide`-en constants keep working
* mutation controls: neutering the module filter must fail exactly the leak test; neutering the
  raise must fail exactly the raise tests

## Open input — ANSWERED 2026-09-12 by corpus-lane, and it closes the risk

**Zero `/3` call sites in the corpus**, measured by call site rather than by name across four
surfaces:

    rulebase bodies (.clausal/.seam)          0
    Python / harness (.py, incl. eval)        0
    the kit repo                              0
    -constant_number_currency declarations   18 files -- all DIRECTIVES, none a body goal

They verified that last line specifically, because a grep for the name matches the directive and
the goal identically and 18 declarations must not be reported as 18 call sites.

So (2) cross-module reads and (3) sites relying on `/3` FAILING are both **vacuously zero** —
and (3) was searched for as its own shape (`\+ constant_number_units(...)`,
`not constant_number_units(...)`) rather than left to fall out of the general count.

**With a planted positive control**, because three zeros from one pattern is exactly when to
distrust the pattern: a file containing both shapes was written and the census found both. The
zeros are the absence of call sites, not the absence of a detector.

**Why it is zero, which matters more than the number.** The corpus reaches constants exclusively
through `constant(name)` — the compile-time substitution — and never through the `/3` reflection
channel. 176 declared values across 17 domains, none read back by its declared pair. So `/3`'s
current behaviour **has never been exercised by a rulebase in either direction**: the leak has
never leaked to anyone, and the silence on an imported constant has never silenced anything.

**Consequence for this design: a strict improvement with no migration.** Nothing goes from
answering to raising, nothing from failing to raising, nothing loses an answer. And the channel
is about to become useful — a name-vs-unit gate needs exactly the declared pair — so this is the
cheap moment to make it right, before anything depends on it.

### The original request, kept for the record



corpus-lane is censusing **call sites**, not names:

1. how many `/3` call sites exist, in how many domains
2. any that read a constant the querying module neither declared nor imported — these go from
   answering to raising
3. **any site that relies on `/3` FAILING** — a `\+` or guard expecting no answer. These go from
   failing to raising, a behaviour change even where the leak is absent

(3) is the likeliest to exist and the easiest to miss from the engine side, because "fails
quietly" is something rulebases lean on without saying so. If (2) and (3) are zero the change is
a strict improvement with no migration.

## Blast radius

`/3` is consumed by the corpus and is the mechanism the scale-lint migration is meant to make
checkable, so this is a cross-lane interface change and not an engine-internal one. Three axes
apply: engine suite (failure AND skip name sets), export bytes (iso-export-lane), domain answers
(harness-batch-lane). The domain axis is the one that can see a rulebase that silently depended
on the leak.
