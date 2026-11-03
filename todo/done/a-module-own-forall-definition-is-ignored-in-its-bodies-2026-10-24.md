# A module's own definition of `forall/2` is ignored in its own bodies

**Status: FIXED 2026-11-03 (commit COMMIT).** A `.pl` or `.clausal` file's own
definition (clauses or `dynamic/1`) of a special form or goal control that is
no ISO built-in now runs in its own bodies and through `call/N`, its
arguments passed as data: the compiler (`terms_to_goalop`) and call/N ask
`call_body.own_definition_shadows`, and the native front end reads the
file's heads ahead (`iso_l3.prescan_own_special_forms`). Every such name
had the issue: `forall/2`, `call_cleanup/2`, `setup_call_cleanup/3`,
`call_nth/2`, `count_all/2`, `freeze/2`, `when/2`, `findall/4`,
`catch_error/2`, `catch_recover/3`, `eval_/2` (`ignore/1`, `not/1`,
`phrase/2,3` already ran the definition). The ISO ones (`once/1`,
`findall/3`, `catch/3`, `\+`, `call/N` ...) are refused at load, per the
ruling of 2026-10-24, so no further ruling was needed. Scryer refuses
`findall/4` too (its own builtin); the engine keeps ISO's set. The seam
keeps its special forms. Left: `todo/pl-translator-call-n-of-a-defined-not-1-2026-11-03.md`
(translator only). Pinned in tests/iso/test_own_special_form_names_scryer.py
(test_engine, test_oracle, test_dynamic_engine, test_dynamic_oracle,
test_other_module_keeps_the_special_form, test_seam_keeps_the_special_form).

Filed 2026-10-24, split from
[the builtin-redefinition todo](iso-a-file-can-redefine-a-builtin-2026-10-16.md)
when its ISO part was fixed.

`forall/2` is no ISO built-in, so a `.pl` or `.clausal` file may define it
(Scryer loads such a file and runs the definition). In its own clause
bodies the compiler's special form still runs instead:

```
forall(X, _) :- X = mine.
q(L) :- findall(X, forall(X, true), L).
```

| | `q(L)` |
|---|---|
| Clausal (`.pl`) | `error(instantiation_error, call/1)` (the special form) |
| Scryer | `L = [mine]` (the file's definition) |

An IMPORTED definition already runs on every route
(`tests/test_imported_special_form_names.py`). The same may hold for the
other non-ISO special-form names a file may now define (`ignore/1`,
`call_cleanup/2`, `setup_call_cleanup/3`, `call_nth/2`, `phrase/2`);
`logic/special_forms.py` lists them.
