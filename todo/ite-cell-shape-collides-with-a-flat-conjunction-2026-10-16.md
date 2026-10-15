# `_is_ite_cell` misreads a 3-goal flat conjunction whose first goal is the atom `;` or `->`

**Status: OPEN, low priority** (final review M-3, 2026-10-16; not realistic, noted for the record).

`clausal/logic/builtins/clause_ops.py` `_is_ite_cell(b)` classifies ANY stored 3-tuple body whose slot 0 is `";"` or `"->"` as an if-then(-else) cell. A flat 3-goal conjunction `( ';', b, c )`, where the first goal is the 0-arity atom `;`, has the same shape and would be read as `( b -> c )`/`( b ; c )` by `clause/2`, `retract/1` and `engine_body_pattern`.

Telling them apart needs a distinct representation for one of the two: a marker type for the ITE cell, or a wrapper for the flat conjunction. That is more than a local fix, and the flat-tuple encoding is already the source of the data-destructive retract todo. Fold it into that redesign.
