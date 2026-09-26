# A clause-less FIELDED export: procedure (ruling 2026-09-26) or data (R6/R6b)?

## The question

The 2026-09-26 operator ruling: a predicate exported by `-module(m, [edge(A, B)])`
with no clauses stays a PROCEDURE, "if it agrees with ISO", and does not
become data: the module binding should be the module's handle, not the atom.

That contradicts ruling R6/R6b (P3-2 Task 2,
`term_rewriting._predicate_export_spec`): a field-carrying export entry
declares a DATA functor (it binds the atom of its spelling, references
compile to cells, `db.declared_kind` says `"data"`). R6b made the ISO
spelling `edge/2` the way to export a procedure with no clauses.

ISO 13211-1 module exports are predicate indicators; a field-carrying entry
is not an ISO spelling, so "if it agrees with ISO" does not decide it.

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
those files, and the corpus has not been measured.

## Landed instead (behaviour-preserving)

- The call's MESSAGE says `edge/2 is declared as DATA` and names the ISO
  spelling (`write edge/2 in the export list`); the ISO term is unchanged.
- The import diagnostic lists `edge/2` exports (it used to report the ISO
  spelling as an EMPTY export list).
- Two `xfail(strict=True)` tests in `tests/test_clauseless_export.py` pin
  the ruling's binding; they flip when this is decided.

## Options

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
