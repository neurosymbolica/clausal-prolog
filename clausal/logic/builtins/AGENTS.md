# clausal/logic/builtins/ — registered builtin predicates

The builtin predicates every module can call (`append/3`, `functor/3`,
`assertz/1`, `write/1`, `dif/2`, ...). Each is a Python function registered
by `(name, arity)` in the dicts in `_registry.py`; importing the package
imports every family module, which fills the registry, then
`_build_all_builtin_classes()` builds one `BuiltinTerm` per name (calling it
builds a goal cell). Up: [../AGENTS.md](../AGENTS.md)

Control constructs (`,`, `;`, `not`, `once`, `catch`, `findall`, if-then-else,
...) are mostly compiled inline by `../compiler/control_constructs.py` and
`../compiler/terms_to_goalop.py`, not registered here. `call/1` on a body term
is `call_body.py`.

## Map

| File | Family |
|---|---|
| `__init__.py` | Imports every family module (order irrelevant), then builds classes. A NEW module must be imported here. |
| `_registry.py` | Decorators, `_BUILTINS` / `_DB_BUILTINS` / `_BUILTIN_FIELDS`, `BuiltinPredicate`, `BuiltinTerm`, `get_builtin_dispatch`, `structural_unify`. |
| `_helpers.py` | Shared term-inspection helpers (fast versions are in `../variables/_variables.c`). |
| `type_checks.py` | `var/1`, `nonvar/1`, `integer/1`, `ground/1`, `must_be/2`, ... |
| `arithmetic.py` | `between/3`, `succ/2`, `plus/3`, `gcd/3`, ... (C: `../_arithmetic_core.c`) |
| `iso_compare.py` | ISO comparison/unification/arithmetic under ISO names (`=:=`, `@<`, ...). |
| `inspection.py` | `functor/3`, `arg/3`, `copy_term/2`, `term_variables/2`, `numbervars/3`, ... |
| `lists.py` | `in_/2` (member), `append/3`, `length/2`, `sort/2`, ... (C: `../_lists_core.c`) |
| `pairs.py` | Scryer `library(pairs)`. |
| `chars.py` | `atom_chars/2`, `atom_codes/2`, `sub_atom/5`, `char_code/2`, ... (C: `_chars_core.c`) |
| `dict_set.py` | Dict and set builtins. |
| `higher_order.py` | `call/N`, `maplist`, `foldl`, `include`, `aggregate_all/3`, ... |
| `lambda_lib.py` | `library(lambda)` (`\X^G`, `+\`). |
| `control.py` | `call_nth/2`, `count_all/2`, `setup_call_cleanup/3`, `time_goal`, `statistics/2`. |
| `call_body.py` | `call/1` of a body term (ISO 7.6.2); not decorator-registered. |
| `database_ops.py`, `clause_ops.py` | `assertz`, `asserta`, `retract`, `abolish`, tabling resets; ISO `clause/2`. |
| `io.py` | `write`, `writeq`, `write_term`, `print_term`, `listing`, `portray_clause`, ... |
| `dcg.py` | `phrase/2,3`, `sequence//1`. |
| `flags.py` | `set_prolog_flag/2`, `current_prolog_flag/2`. |
| `attributes.py` | `put_attr/3`, `get_attr/3`, `term_attvars/2`, ... |
| `keyword_ops.py` | `vary/3`, `unbound_keys/2`, `signature/3`. |
| `constraints.py` | `dif/2`, reified `eq/3`, CLP(FD/B/R/Q) entry points; imports `sat_constraints.py` and `ortools_constraints.py` at its end. |
| `clpz_names.py` | `in/2`, `ins/2`, `labeling/2`, `#<==>` etc. (Scryer names, over `../clpz_surface.py`). |
| `z3_constraints.py`, `sat_constraints.py`, `ortools_constraints.py` | `z3.*`, `pysat.*`, `ortools.*` builtins (optional backends). |
| `translations_builtin.py` | `translate/3`. |

`../units_constraint.py` registers `has_units/2` and `../units_clp.py` a
units hook; `__init__.py` imports both before building classes.

## Adding a builtin

Pick the family file, then one of three decorators from `_registry.py`:

- `@_builtin("name", arity)` — simple mode. Signature `fn(arg0, ..., trail, k)`;
  a generator that yields `None` once per solution. Bind with
  `mark = trail.mark(); if unify(x, v, trail): yield None; trail.undo(mark)`.
  Fields (keyword names) come from the parameter names minus the last two.
- `@_trampoline_builtin("name", arity)` — native trampoline protocol, for
  builtins that enumerate lists or call sub-goals. Actual signature (see
  `lists.py`): `fn(this_generator, _proceed, _fail, _catcher, *args, trail)`;
  yield `(_proceed, None)` per solution and `(_fail, DONE)` at the end.
- `@_db_builtin("name", arity, fields=(...))` — needs the caller's database
  (assert, `call/N`); decorates a factory `factory(db) -> simple-mode fn`.

Errors: `raise LogicException(type_error(...))` etc. from `../exceptions.py`
(Scryer `error(Formal, Context)` terms). If the ISO name differs from the seam
name, register both (e.g. `lists.py` registers `memberchk/2` beside
`in_check/2`); the `.pl` <-> seam name maps are in
`clausal/tools/prolog_to_clausal.py` and `clausal/tools/prolog_dialect.py`.
Then document it in [builtins.md](../../../docs/builtins.md) (its signature
companion is `tests/fixtures/docs/builtins_sig_tests.seam`).

## Gotchas

- No default-valued trailing parameters on a simple-mode fn: field
  extraction strips exactly the last two parameters, so extras leak into the
  term's arity (`tests/iso/test_iso_registration.py` pins this).
- Some families write the dicts directly instead of decorating
  (`higher_order.py` `call/N`, `dcg.py` `phrase`, `control.py` `time_goal`,
  `lambda_lib.py`); grep `_DB_BUILTINS[` before assuming a name is unregistered.
- `_db_optional` (on `listing/1` and `call/N`) is load-bearing: it lets the
  db-less class table build these. See `_stateless_dispatch`.
- C fast paths are optional (`try: import` with `_py` fallbacks); keep both
  behaviours in step.
