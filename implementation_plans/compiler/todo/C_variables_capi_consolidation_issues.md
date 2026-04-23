# C API capsule consolidation — open issues

Post-implementation review of the `_tabling_core.c` capsule migration.

All issues identified have been resolved in this changeset.

---

## 1. ~~Dead code left behind~~ FIXED

`str__fields`, `str___dataclass_fields__`, `str_name`, and `dc_fields_func`
were unreferenced after the migration.  Removed.

---

## 2. ~~No tabling tests for `@dataclass` terms~~ FIXED

Added 14 tests in `TestDataclassTerms` covering `_normalize_for_key`,
`make_subgoal_key`, `freeze_args`, `_deref_walk`, and `_unify_answer`
with `@dataclass` term instances (ground, with Vars, nested).

---

## 3. ~~`Compound` registered via Python-time call~~ FIXED

`_register_compound_type` replaced with `import_compound_type()` at
`PyInit__tabling_core` — imports `clausal.terms.Compound` directly,
eliminating the last registration handshake from `tabling.py`.
