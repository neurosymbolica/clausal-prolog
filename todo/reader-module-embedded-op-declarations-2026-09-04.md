# prolog_reader: op/3 declarations embedded in a module/2 export list are inert

**Status:** design question, parked during Task 6 (corpus integration) of the
prolog-reader L1/L2 plan. Not a defect — the reader's contract treats parser
output as pure data (`clausal/tools/prolog_reader.py`'s module docstring:
"never on the engine ... this module only depends on dataclasses"), and this
is exactly the kind of module-system semantics the Task 6 brief flagged as an
expected dialect gap going in ("module-system ops... become SyntaxIssues").
Recording the shape of the gap here in case a future task wants to close it.

## What's missing

SWI/Scryer allow `op(Priority, Type, Name)` terms as members of a
`:- module(Name, [...]).` export list, applied as a side effect of loading
the module — before the rest of the file is read. Real corpus examples:

```prolog
:- module(xpath, [ xpath/3, xpath_chk/3,
                    op(400, fx, //), op(400, fx, /), op(200, fy, @) ]).
...
in_dom(//Spec, DOM, Value) :- ...   % needs // as prefix NOW
```

```prolog
:- module(atts, [op(1199, fx, attribute), term_attributed_variables/2]).
...
Term0 = (:- attribute Atts),        % needs `attribute` as prefix NOW, same file
```

`PrologReader` only interprets `op/3` when it's the WHOLE body of a top-level
`:- op(...).` directive item (`prolog_reader.py`'s `PrologReader` docstring:
"`op/3` directives parsed by one `read_term()` call apply to the SAME table
used by later calls"). An `op(...)` term nested inside a `module(...)`
directive's export-list argument is just data to the transformer — never fed
back into `self._op_table`. So even reading ONE such file in isolation (no
cross-file dependency involved) mis-parses its own later use of the operator
it just declared.

Corpus files hitting this (all in `/workspace/scryer-prolog/src/lib`, all as
the sole or dominant cause of their `SyntaxIssue`s): `xpath.pl`, `atts.pl`,
`debug.pl` (`op(900, fx, $)`, `op(900, fx, $-)`), `clpb.pl` (`op(300, fy, ~)`,
`op(500, yfx, #)`). Plus a second-order effect: `atts.pl`'s `attribute` op
never reaching the shared table (even were cross-file persistence added, see
below) is why `clpb.pl`, `clpz.pl`, `dif.pl`, `freeze.pl`, `simplex.pl`,
`when.pl`, and all six `tabling/*.pl` files show one `:- attribute ...`
`SyntaxIssue` each.

## A related, separate gap: no cross-file op persistence in the corpus test

Independently of the above, real Scryer loads library files in dependency
order, so `ops_and_meta_predicates.pl`'s `:- op(700, fx,
non_counted_backtracking).` is in scope by the time `builtins.pl` and
`iso_ext.pl` are compiled, and `clpz.pl`'s `:- op(700, xfx, #>=).` etc. are in
scope by the time `crypto.pl` is compiled. The Task 6 corpus test reads each
file standalone with a fresh `PrologReader`/op table, which cannot see this —
that's a test-harness modeling choice (matching how the brief scoped the
task: one file at a time), not a defect either. Solving it for real would mean
a corpus-level test that reads files in the library's actual load order,
threading one `OperatorTable` through all of them — a bigger, separate piece
of work than Task 6's per-file gate.

## Options if this is ever picked up

1. **Do nothing** (status quo): keep treating `module(...)`'s argument list
   as pure data; these become `SyntaxIssue`s with correct resync, which is
   what the whole reader design already guarantees. Cheapest, keeps the
   "parser output is pure data" boundary intact.
2. **Special-case `:- module(_, [...])`**: scan the export list for bare
   `op(P, T, N)` terms and apply them to the live `_op_table` before
   continuing to read the rest of the file, mirroring what a real loader
   does. Narrow, but it's the reader's first exception to "never interpret
   directive semantics" — needs an explicit decision, not a quiet addition.
3. **Cross-file op persistence for a corpus-level test**: read the whole
   `src/lib` tree in dependency order with one shared `PrologReader`,
   closer to what a real system does, and would silently subsume most of
   option 2's benefit for THIS corpus without touching `prolog_reader.py`.

No recommendation recorded — flagging for the user to weigh against the
"parser output is pure data" design point before any of this is implemented.
