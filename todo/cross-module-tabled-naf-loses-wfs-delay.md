# Cross-module tabled NAF never fires WFS delay semantics

Split out of `todo/done/tabling-lifecycle-gaps-rewrap-and-cross-module-table.md`
(finding 3, P3) when findings 1 and 2 were fixed on
`fix/tabling-wrapper-survives-recompile`. UNTRIAGED — the parent todo recorded
it by reading the code, not by reproducing it.

`_is_tabled_naf` (`logic/compiler/tabled_naf.py:22-32`) asks the *caller's*
per-module db whether the callee is tabled, under the dotted name. An imported
callee is tabled in its own module's db and not in the caller's, so
`not Imported(...)` compiles as plain NAF rather than the WFS-sound
`$naf_tabled` form.

Sound for completed evaluations — the callee's own dispatch is still the tabling
wrapper, so answer dedup and termination are intact. What does not propagate is
the delay/conditional-answer machinery: a cycle through negation that crosses a
module boundary cannot produce `undefined`, where the same cycle inside one
module can.

Note the fix for finding 2 narrowed the workaround space rather than widening
it: `-table` in the *importing* module is now a load error, so an author cannot
mark the callee locally to get the tabled-NAF lowering. Whatever the fix is, it
has to read tabledness from the module that owns the predicate.

Open, in rough order of appetite:

1. Have `_is_tabled_naf` resolve the callee's own module and ask *its* db. Needs
   a caller → callee-module lookup at compile time that does not exist yet; the
   `PredicateMeta` is in `module_dict`, so `__module__` plus
   `sys.modules[...].__clausal_module__.db` is probably enough.
2. Record tabledness on the `PredicateMeta` itself at load, so it travels with
   the class across modules and neither db needs consulting. Cheapest to read,
   and one more piece of state to keep in step with `Database._tabled`.
3. Leave it, and document that WFS `undefined` is a within-module guarantee.

First step is a reproduction: a two-module even/odd cycle through negation whose
single-module twin yields `undefined`, and a check of what the cross-module one
yields. Until that exists the severity is a guess.
