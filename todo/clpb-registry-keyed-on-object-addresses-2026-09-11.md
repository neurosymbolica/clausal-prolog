# CLP(B) keys module-global registries on `id(Var)` — silent wrong-answer hazard

**Filed 2026-09-11.** This file previously claimed this design caused a SIGSEGV. **It did not**
— that crash was `Trail_dealloc` clearing weakrefs while still GC-tracked, fixed the same day
(`todo/done/trail-dealloc-clears-weakrefs-while-still-gc-tracked-2026-09-11.md`). CLP(B) was
implicated only because it is the one place in the engine that puts a `weakref.finalize` on a
Trail, so it was the only code that could trigger the real bug.

What remains is a genuine design hazard with no known reproduction. It is written down because
it is easy to re-derive as a crisis and then dismiss along with the crash it was wrongly
attached to.

## The shape

`clausal/logic/clpb.py`:

    _var_to_id      dict  id(Var) -> ordering index     # keyed on a raw ADDRESS
    _id_to_var      dict  index   -> Var                # the ONLY strong ref to the Var
    _unique_tables  dict  id(Var) -> {(id(hi), id(lo)) -> BDDNode}

`_cleanup_trail_allocs`, driven by `weakref.finalize(trail, ...)`, pops all three when the last
registered Trail dies. Popping `_id_to_var[idx]` releases the only strong reference, so the Var
can be freed — and **a freed object's address is immediately reusable**. A new `Var` allocated
at that address would find the old variable's entry in `_var_to_id`, or its hash-consing table
in `_unique_tables`, and inherit BDD nodes built for a different variable.

`Var` (the C type `AttVar`) is not weakref-able, which is why the code took this route in the
first place — the comment says so.

## Why it has not bitten

The pops are consistent: all three entries for a `(vid, idx)` go together, so a recycled address
finds no stale `_var_to_id` entry and gets a fresh ordinal. The window needs a partial state —
an address recycled while some but not all of its entries survive, or a Var freed while a live
BDD still carries its ordinal. The refcounting is per `(vid, idx)` across TRAILS, and a live BDD
is not a trail, so that second shape is reachable in principle.

**No reproduction is known.** Do not treat this as a live bug; treat it as a design that cannot
be shown correct.

## The relevant precedent

The code already documents fixing one soundness hole here: "Pruning on the first trail's death
was a soundness hole: a second live trail's BDDs still used those ordinals, so after pruning
`_get_var_for_id` returned None and propagation silently skipped the level, leaving the
constraint inert." Refcounting trails fixed that instance. It did not establish that trails are
the right thing to count.

## Directions, in increasing cost

1. **Key on something that is not an address.** Give each registered Var a monotonic token at
   registration and key on that. An address is not an identity for an object that can die.
2. **Count what actually holds the ordinal.** A BDD node carries `var_id`; the registry entry
   for that ordinal should outlive every node carrying it. Counting nodes rather than trails
   makes the invariant true by construction.
3. **Make `Var` weakref-able** and hang the cleanup off the Var itself. This is the clean
   answer and the code says why it was not taken. It costs a pointer per `Var`, which is the
   engine's most-allocated object — a real performance decision, not a free fix.

Whichever is chosen, prefer draining pruning at a safe point (the start of a solve) over doing
it from a finalizer. A finalizer runs inside someone else's allocation; that is what made the
unrelated crash so hard to attribute, and it is a bad place to mutate shared state regardless.

## Verifying any fix

There is no failing test to go green. A fix should come with an instrument that shows address
reuse being handled: register a Var, drop it, force allocation until a new `Var` lands on the
same address, and assert the new one gets its own ordinal and its own table. Confirm the
instrument can FAIL — the earlier attempt at exactly this reported zero reuse events and was
never shown able to report a non-zero one.
