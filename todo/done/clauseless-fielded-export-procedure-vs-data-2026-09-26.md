# A clause-less FIELDED export stays DATA (R6/R6b stands, ruled 2026-09-26)

## The ruling

`-module(m, [edge(A, B)])` with no clauses declares a DATA functor, as
ruling R6/R6b (P3-2 Task 2, `term_rewriting._predicate_export_spec`) says:
the binding is the atom of its spelling, references compile to cells, and
`db.declared_kind` answers `"data"`. The ISO spelling `edge/2` is how a
module exports a PROCEDURE with no clauses, and it already stays one (the
module's handle). ISO 13211-1 module exports are predicate indicators only,
so the field-carrying spelling is a Clausal extension that ISO does not
constrain.

The ISO-visible answers were already right for both spellings and did not
change. What changed is the call's message, which now names the DATA
declaration by its source (this file's -module or -private entry, or the
owner module's export entry for an import) and the `name/arity` spelling
that declares a procedure instead.

## Rejected: make a clause-less fielded export a procedure

Asked first (2026-09-26): rebind a clause-less fielded `-module` export to
the module's handle, "if it agrees with ISO". Rejected by the ruling above:
it contradicts R6/R6b, ISO does not decide it, and it would turn the in-repo
DATA exports (measured below) into procedures.

## Measured (0427c5e3)

The ISO-visible answers are the same for both spellings and are pinned in
`tests/test_clauseless_export.py`:

| | `edge(A, B)` (fielded) | `edge/2` (ISO) |
|---|---|---|
| module binding | atom `'edge'` (data) | handle `m\x1fedge` |
| call `edge(1, X)` | `existence_error(procedure, edge/2)` | same |
| through an importer | same | same |
| with `-dynamic(edge/2)` | fails | fails |
| `clause(edge(A, B), Body)` | fails | fails |
| `listing(edge/2)` | fails, prints nothing | same |
| `current_predicate/1` | not a Clausal builtin | not a Clausal builtin |

In-repo census (`-module` lists in .clausal/.seam files, regex-level, may
over-count DCG heads): 41 clause-less, non-dynamic, field-carrying exports
in 151 module files. 23 are referenced as data in their own file; the other
18 are exported for importers (tagged-term shapes, constant functors, the
provenance fixtures' `edge`). Reclassifying them as procedures would change
those files, and downstream code has not been measured.

## What landed

- The call's MESSAGE says `edge/2 is declared as DATA` and names the
  declaration by its source: this file's -module export entry, its -private
  entry, or (for an import, aliased or not) the OWNER module and the owner's
  spelling. It names the `name/arity` spelling that declares a procedure.
  The ISO term is unchanged, and the ISO `edge/2` spelling never gets it.
- The import diagnostic lists `edge/2` exports (it used to report the ISO
  spelling as an EMPTY export list); -private `name/arity` entries are not
  listed as exports.
- `tests/test_clauseless_export.py` pins the DATA binding (the two strict
  xfails written before the ruling became positive pins).

## Options considered (the ruling chose 1)

1. Keep R6/R6b: the fielded entry is data, `edge/2` exports a procedure.
   Nothing more to do; drop the two xfails.
2. Adopt the ruling for `-module` fielded entries: every clause-less
   fielded export becomes a procedure. Breaks the data idiom above unless
   those files move to another way of declaring data.
3. Split by use: a clause-less fielded export that no file references as
   data becomes a procedure. Not decidable per module (an importer may be
   the one constructing it).

## RESOLVED 2026-09-26: R6/R6b stands

Operator ruling: keep R6/R6b. The ISO spelling `edge/2` is the procedure
export and already stays a procedure with no clauses; the field-carrying
spelling is a Clausal extension that ISO does not constrain, and stays a DATA
functor. The strict xfails became positive pins of the DATA binding
(`test_a_clauseless_fielded_export_is_declared_data`,
`test_an_importer_of_a_clauseless_fielded_export_gets_the_atom`).
