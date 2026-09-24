# An imported predicate called at ANOTHER arity resolves in the OWNER -- and the eras agree only if the flip binds the owner handle

**Filed:** 2026-09-24, by the name+arity-ruling lane (review round on
fix/name-arity-ruling-remaining-refusals-2026-09-24).  Design question,
parked for a ruling -- not fixed.

## What happens today

`alim` does `-import_from(alow, [alias(numlist, nl)])`; `alow` defines
`numlist/1`.  In `alim`, `nl(3, L)` (arity 2):

| binding reaching `_dispatch_at(_, 2)` | answer |
|---|---|
| the CLASS `alim` binds today | builtin `numlist/2` -> `L = [1,2,3]` (resolved in `alow`, under `numlist`) |
| owner handle `alow:numlist` | same |
| importer handle `alim:nl` | `PredicateArityMismatchError` (`alim` has no `nl/2`, no builtin `nl`) |

Both `solve.call("nl", 3, L, module=alim)` and a compiled body `nl(3, L)`
in `alim` answer, via the class-arm fallback added for the ruling (on
main before the ruling both refused).  Pinned by
`tests/test_f7_dispatch_at_arity_refusal.py::test_an_aliased_import_resolves_the_other_arity_in_the_OWNER_under_the_OWNER_name`.

## The question

Under name + ARITY, importing `numlist/1` as `nl` does not import any
`nl/2`, so arguably `nl(3, L)` in `alim` should refuse (nothing answers in
the CALLING module).  A class held DIRECTLY (a module-qualified `alow.numlist`
reference) is a different case: there `alow:numlist/2` is the right answer,
and F7's reversed pin requires it.  `_dispatch_at` cannot tell the two apart
for a class; after the flip it can, if an import binds the IMPORTER handle.

Options: (a) the flip binds the importer handle and the class era is left
as is until retirement; (b) the flip binds the owner handle and the leak is
the rule; (c) `solve.call`'s last resort and `globals_env`'s keep-binding
branch refuse without resolving a binding owned by another module (the
keep-binding key also serves term construction, so (c) is not a one-line
change there).
