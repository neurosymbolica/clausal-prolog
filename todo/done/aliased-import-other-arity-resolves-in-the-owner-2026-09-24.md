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

## Ruling (operator, 2026-09-24): CLOSE THE LEAK

An other-arity call resolves in the namespace the caller NAMED, under the
name the caller USED.  Unqualified `nl(3, L)` in `alim`: the calling module
only (its own rows at that arity, its imports bound under that name at that
arity, builtins under THAT name) -- `nl/2` exists nowhere, so it refuses.
Importing `numlist/1` as `nl` grants no other arity and no other name.
Qualified `alow.numlist(3, L)` / `alow:numlist`: the qualifier's module under
that name -- the builtin `numlist/2` answers (F7's reversed pin stands).
Consistent with D1 (imports bind the OWNER's handle): the handle says where
the predicate lives, not which other arities it grants.

## Resolved (2026-09-24, same branch)

`_dispatch_at`'s class/handle fallback is unchanged -- it serves the
direct/qualified case.  The decision moved to the two places that know the
name was unqualified:

- `compiler_v2._route_other_arity_imported_calls_to_local` (step 3b-quater):
  the import remap spells `nl(3, L)` as `LoadName("alow.numlist")`; a body
  call in that shape at an arity the imported binding is NOT a predicate at
  is re-pointed to the local name `nl`.  A qualified `alow.numlist(3, L)` the
  author wrote does not compile to that shape and keeps the dotted route.
- `globals_env`: an unqualified call site at another arity than its
  predicate binding, with nothing answering, gets its own `$disp_name_N`
  entry (`_unqualified_other_arity_dispatch`), which re-resolves in the
  compiling module under that name and otherwise raises through
  `predicate._refuse_unqualified_other_arity` -- never the owner.
- `solve.call` Phase 5's last resort is `_refuse_unqualified_other_arity`
  instead of `_dispatch_at`.

Unaliased `-import_from(alow, [numlist])` then `numlist(3, L)` resolves
under `numlist` in the calling module: the builtin `numlist/2` answers.
Pinned both eras (the handle era emulated by binding imports to the owner
handle) in `tests/test_f7_dispatch_at_arity_refusal.py`.
