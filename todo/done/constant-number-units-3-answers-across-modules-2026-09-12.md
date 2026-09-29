# `constant_number_units/3` answers for OTHER modules' constants

Found 2026-09-12 while building the decimal-string form. **Pre-existing and independent of that
work** — it surfaced as a test in one file colliding with a constant of the same name in another,
and reproduces with a clean two-module probe.

    # xa.clausal
    -module(xa, [fee_x])
    -constant_number_units(fee_x, 11.00, usd)

    # xb.clausal
    -module(xb, [look/2, fee_x])
    -constant_number_units(fee_x, 22.00, usd)
    look(N, U) <- constant_number_units(fee_x, N, U)

    xb asks for fee_x and gets:   Decimal('11.0')   <- xa's
                                  Decimal('22.0')   <- its own

`register_constant_units` **takes a module argument** and records it, so the registration side is
module-aware. The `/3` relation does not filter on it at query time, so every loaded module's
declaration of that name is an answer.

## Why it matters more than a duplicate row

The whole point of the `/3` channel is **fidelity to what this declaration said** — it exists so a
gate can check that a parameter's unit matches the unit its NAME claims. An answer from another
module is not merely extra: a rulebase checking its own declaration can be handed a different
module's magnitude and unit, and `once/1` or a first-solution consumer would take whichever
loaded first. Load ORDER decides. That is the same shape as the `-import_from` module/profile-key
shadow (BUG #2, closed 2026-09-12): silent, order-dependent, and invisible until two things share
a name.

## What it is not

Not a regression from the decimal-string work — the probe above uses plain float literals and
reproduces on any tree carrying the `/3` channel. Not a duplicate-declaration error either:
declaring the same constant name in two modules is legal and normal.

## The decision this needs

Whether `/3` should filter by the querying module, or answer for all and let the caller
disambiguate with a module argument (`constant_number_units/4`?). Filtering is the behaviour the
name implies and the one the gate use-case wants. Answering across modules has no use case anyone
has written down, which is itself evidence.

**Check before fixing**: whether any corpus rulebase relies on reading another module's declared
pair. A census of `constant_number_units/3` call sites, not a name census — see the repeated
lesson that a census of NAMES is never evidence about BINDINGS.

## Closed 2026-09-30 (stale)

No longer reproduces on f01790d2: the two-module probe answers only xb's own
`(22.0, usd)`. Fixed by a92a3e74 (compile-time module insertion:
`constant_number_units(fee_x, ...)` lowers to `module_constant_units($module, ...)`).
