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
| `++name` for an undefined name | `NameError` ✔ |

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
   that was never defined should be an error.

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
* **The VALUE side.** `++name` already raises for an undefined name. Untouched.

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

## Open input, requested before building

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
