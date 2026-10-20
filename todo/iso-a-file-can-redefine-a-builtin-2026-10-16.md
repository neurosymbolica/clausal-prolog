# A `.pl` or `.clausal` file can define a clause for an ISO builtin

Filed 2026-10-16 by iso-export-lane, found while re-measuring the
[ISO compatibility report](../docs/iso_prolog_compatibility_report.md)
(it is listed there under "Known gaps"). OPEN.

## The divergence

A Prolog text that contains a clause for a built-in predicate loads, and
inside its own module that clause replaces the builtin. In ISO a built-in
predicate is a static procedure, and Scryer refuses such a file.

Measured on main 885938f9, CLI `-g`, both surfaces. The oracle is
`/workspace/scryer-prolog-clpq/target/release/scryer-prolog`
(v0.10.0-137-g9acba77a).

| file contains | goal | `.pl` | `.clausal` | Scryer |
|---|---|---|---|---|
| `atom_length(_, 5).` | `atom_length(abc, L)` | `L = 5`, loads | `L = 5`, loads | `permission_error(modify,static_procedure,atom_length/2)` from `load/1` |
| `X is _ :- X = 99.` | `R is 1 + 1` | `R = 99`, loads | loads | (not run) |
| `write(_) :- true.` | | loads | loads | |
| `atom(_).` | | loads | loads | |
| `call(_).` | | refused: `cannot define the control construct call/1 (ISO permission_error(modify, static_procedure, call/1))` | refused, same | `permission_error(modify,static_procedure,call/1)` |
| `true :- fail.` | | refused, same | refused, same | |

At run time the refusal already exists: `assertz(atom_length(x, 1))` gives
`permission_error(modify, static_procedure, atom_length/2)`.

The override is module-local. Module `rd` defines `atom_length(_, 5)` and
exports `t(L) :- atom_length(abc, L)`. An importer's `u(A, B) :- t(A),
atom_length(abc, B)` gives `A = 5, B = 3`, so other modules still see the
real builtin. The defining module's own calls do not, and that includes
`is/2`.

## Where the two checks live

- The loader's guard, `clausal/tools/iso_l3.py:920`
  (`_lower_clause`/`LoweringRefused`), refuses only a fixed list of control
  constructs: `, ; -> *-> ! \+ :- call`, and `true`/`fail`/`false` at
  arity 0.
- assert/retract's guard, `clausal/logic/builtins/database_ops.py:390`,
  asks `(functor, arity) in _BUILTINS or (functor, arity) in _DB_BUILTINS`,
  so it already knows every builtin.

The likely fix is for the loader to consult the same registry for every
clause head and raise the same `permission_error(modify, static_procedure,
F/N)`, for both surfaces. Whether the translator front end needs its own
guard is not yet checked.

## Before fixing, check

- **Library and corpus code that relies on shadowing.** A census of clause
  heads whose name/arity is in `_BUILTINS` is needed: the engine's own
  `.pl`/`.clausal` library files, the `iso_diff` and other test fixtures,
  and the downstream rule bases. A deliberate override (a library that
  re-implements a builtin in Prolog) would need an allowlist or a
  `redefine`-style declaration.
- **Non-ISO and library names.** Scryer protects only ISO's built-ins: a
  file defining `append/3`, `length/2` or `writeln/1` loads there (checked
  2026-10-16). Clausal ships all three. Refusing a user's own definition of
  them would be stricter than ISO and Scryer, so the refusal should probably
  cover ISO 13211-1's built-ins only (a set that is not yet written down
  separately from the registry).
- **The `.seam` surface** is out of scope (Python syntax, not ISO).

## A clause for a special form's name (measured 2026-10-20)

The override above is not uniform. A `.pl` file with a clause for the name
and `q(L) :- findall(X, <goal>, L).`:

| clause in the file | `q(L)` | Scryer |
|---|---|---|
| `atom_length(X, _) :- X = mine.` | `[mine]` (the clause) | refused at load |
| `once(X) :- X = mine.` | `instantiation_error` (the special form; the clause is ignored) | refused |
| `findall(X, _, _) :- X = mine.` | the special form | refused |
| `throw(X) :- X = mine.` | the special form | refused |
| `forall(X, _) :- X = mine.` | the special form | loads, `[mine]` (forall/2 is no ISO builtin) |
| `write(X) :- X = mine.` | fails | refused |

`call/N` of the cell agrees with the body for a module's own definition
(`_import_shadows_special_form` answers False for it). An IMPORTED
definition is what runs, on every route
(`tests/test_imported_special_form_names.py`). Scryer refuses defining
`once/1`, `findall/3`, `catch/3`, `bagof/3`, `throw/1`, `keysort/2`,
`term_variables/2`. It loads a definition of `forall/2`, `ignore/1`,
`call_cleanup/2`, `setup_call_cleanup/3`, `freeze/2`, `call_nth/2`,
`length/2`, `msort/2`, `between/3`, `succ/2` and `phrase/2`, and then uses it.
So a refusal limited to ISO's builtins still leaves a module's own
`forall/2` ignored in its bodies, where Scryer runs it.
