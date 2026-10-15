# existence_error("procedure", ...)'s skip of the raise-time copy is a shape test, not a provenance test

Found 2026-10-15 (fix/iso-error-culprit-copy-2026-10-15, re-review round).

`_error()`'s `existence_error("procedure", culprit, ctx)` path skips
`_copy_at_raise_time` whenever `_is_indicator(culprit)` (an `F/A` pair)
and `ctx` is a `str` or `None`. That test is about the *shape* of the
arguments, not about whether they were actually built fresh for this
raise -- it is safe only because every current caller happens to build
`Name/Arity` from a functor string and an int arity, never from a live,
possibly-bound term.

**Why it is safe today** -- every current call site constructs the
indicator from a string functor and an int arity:

- `clausal/logic/predicate_diagnostics.py:95`
- `clausal/logic/compiler/globals_env.py:428`
- `clausal/logic/modules/py/__init__.py:108`
- `clausal/logic/builtins/higher_order.py:404`
- `clausal/logic/predicate.py:1172`
- `clausal/logic/builtins/call_body.py:524` (`folded_existence_error`)
- `clausal/logic/cells.py:1125`
- `string_goal_error`

`M:F/A` (`clausal/logic/cells.py:1119`) is not an indicator at the top
level (it is a module-qualified term wrapping one), so it takes the
general `_error` path instead and is copied normally -- it is not
exempt.

**Risk:** a future `existence_error("procedure", ...)` call site that
builds its `F/A` from a user-supplied, possibly-live, possibly-bound Var
(for `F` or `A`) would silently skip the copy. On an uncaught raise, the
error term would then keep a live engine Var reachable from outside the
raise -- exactly the bug class this whole fix round closed for every
other `_error()` path.

**Options:**
- Copy on this path too, unconditionally. Costs about 1-3 microseconds
  per `existence_error("procedure", ...)` raise, and changes the
  identity-sensitive test
  `test_a_missing_procedure_names_itself_as_scryer_does`
  (`cell_args(term)[1] is pi`) to a structural `==` comparison.
- Or, cheaper: assert `_is_ground(culprit)` on the shortcut in debug or
  test builds, so a future violation fails loudly at the call site
  instead of silently shipping a live var.

**Re-audit trigger:** any new `existence_error("procedure", ...)` call
site added anywhere in the engine -- check whether its indicator is
guaranteed ground-by-construction before assuming the shortcut still
applies.
