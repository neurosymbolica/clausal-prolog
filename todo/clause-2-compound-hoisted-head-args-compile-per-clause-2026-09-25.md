# clause/2: a compound hoisted head argument compiles one query per clause

Parked 2026-09-25 (feat/clause-2-2026-09-25, roborev LOW).

`clause_ops.head_matches` puts the hoisted head arguments back on a private
trail before it compares the query head.  A hoisted `Unify(V, data)` whose
argument is PLAIN (atomic values, and lists or tuples of them) is bound
directly (`_split_lead` / `_plain`).  A COMPOUND argument is stored as a
`Call(LoadName('k'), [150])` node, and it goes through the query compiler:

```
r(k(150), Y) <- q(Y)        # stored: r(_V, Y) <- (_V = k(150), q(Y)), hoisted 1
```

So the first scan of a 300-clause table compiles 300 head-only queries.
The result is cached per clause after that, and each compile also churns the
FIFO `_query_cache`.  `test_only_the_selected_rule_is_built` pins the count
(`counts["compile"] == 301`).

The cheap fix is to build the cell directly for a ground `Call(LoadName(n),
args)` with plain args.  It was not done because the functor the compiler
emits is not always `n`:
- an `-import_from` alias builds the OWNER's functor;
- a declared signature places keyword args and backfills missing slots with
  fresh Vars;
- `-implicit_functors` changes the rules;
- a name bound to a predicate keeps class emission.

A direct builder has to reproduce `term_to_ast_expr`'s `Call` arm
(`cell_signature_for_name`, `_place_signature_slots`, the OWA branch),
otherwise the head filter and the full construction disagree about the same
clause.  Do it by factoring that arm into a callable
`build_cell(fname, args, namespace)` both paths use.
