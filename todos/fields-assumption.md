# `._fields` assumption may exist in other call sites

`clausal/logic/compiler.py`, `_arg_to_index_key` and `_runtime_arg_key`

These two functions used `cls._fields` directly on term instances, which only
works for `PredicateMeta` instances. Dataclass-based terms (like `Add`, `Sub`,
etc.) don't have `_fields` — they use `__dataclass_fields__` instead.

The fix uses the existing `term_field_names()` helper from
`clausal.logic.predicate`, which handles both cases. But the fact that two
call sites were using `._fields` directly, while the helper already existed,
suggests the dataclass-as-term path is newer and other call sites may have the
same assumption.

Action: grep the codebase for `\._fields` (excluding `__dataclass_fields__`
and known-safe uses like `ast.FunctionDef._fields` and `PredicateMeta`
definitions) to find any remaining instances.
