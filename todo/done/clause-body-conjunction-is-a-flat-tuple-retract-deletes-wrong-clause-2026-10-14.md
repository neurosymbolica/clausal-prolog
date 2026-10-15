# DATA-DESTRUCTIVE: a conjunction body is a flat tuple, so retract deletes the wrong clause

**Found:** 2026-10-14. **On main since 9282e665.** Nothing to do with cut.

The engine stores a clause body as a FLAT goal list, and `clause/2` (and the
matcher `retract/1` shares with it, `clause_ops.clause_terms` /
`engine_body_pattern` / `unify_body`) handed a conjunction back as the flat
tuple `(G1, ..., Gn)`. In a `.pl` / `.clausal` module that tuple is not a
conjunction: a tuple whose first element is an atom is a CELL. So, for

    :- dynamic(d/1).
    d(X) :- X = 1.
    d(X) :- nl, X = 1.

- `retract((d(_) :- (_, _)))` DELETED `d(X) :- X = 1` (an `OpenConjunction`
  pattern matched any tuple, and a single cell goal is a tuple). Scryer
  deletes nothing: `X = 1` is not a conjunction.
- `retract((d(_) :- nl(_)))` DELETED `d(X) :- nl, X = 1` (its body read back
  as the cell `nl(X = 1)`). Scryer deletes nothing.
- `functor/3` failed on a conjunction body that clause/2 returned, and gave
  `nl/1` for `nl, X = 1`.
- A clause/2 conjunction pattern matched single compound goals, and the
  reverse.

Fix wanted: clause/2 and retract read a conjunction body as the ISO term
`','(A, ','(B, C))`, both in what clause/2 returns and in what the patterns
match against, without changing how clauses compile or run.

## Resolved (2026-10-14, branch fix/clause-body-conjunction-iso-terms-2026-10-14)

FINAL DESIGN (after fix round 4; the round-by-round history follows):
the native front end keeps each ISO rule's body AS READ
(`Predicate.source_body` -> `Clause.source_body`), with a variable goal
stored as `call(X)` (ISO 7.6.2). clause/2 and retract/1 rename that term
with the head and unify against it. A source term that is not plain data
(a constant, a partial list, `undefined`) goes through the compiler's own
term construction (`clause_ops._source_built`). A body an if_/3 lowering
rewrote, and an ISO rule with no stored term, FAIL CLOSED: only an
unbound pattern takes them. Seam clauses are unchanged. The
`_iso_conjunctions` rewrite and the grouping / fail-spelling metadata
described next were the first designs, removed in round 3.

First fix (superseded by round 3). Fixed at the clause/2 / retract BOUNDARY, not at storage: compiled code
and the stored clause are unchanged. A storage fix would have to change
what the compiler and every loader store and run; the boundary fix touches
only the read-back and the pattern conversion.

- `clause_ops.iso_bodies(db)`: true for a module lowered by the native ISO
  front end (`.pl` and `.clausal`, loader `frontend == "native"`).
- `clause_ops._iso_conjunctions`: for such a clause, `_full_built` rewrites
  every conjunction in a GOAL position (the body, `\+` / `;` / `if_`
  operands, the goal arguments of findall/forall/call/... via
  `_goal_positions`) to the right-nested `','/2` cell BEFORE the special
  forms are spelled as cells. So clause/2 returns `','(A, ','(B, C))`.
- `engine_body_pattern(t, iso)`: for such a procedure a `','/2` pattern
  stays the cell (operands converted), so `(_, _)` matches only a
  conjunction, `(G, Rest)` binds Rest to the ISO rest, and `nl(_)` only a
  call of nl/1. clause/2 and retract now convert the pattern after
  resolving the procedure's home.
- Seam (`.seam`) procedures are unchanged: flat tuple, OpenConjunction.

Tests: `tests/iso_l3/test_l3_clause_body_conjunction.py` (rows checked
against Scryer, in `.pl` and `.clausal`); `test_open_tail_and_negation_patterns`
c1 now expects the ISO rest, as Scryer answers.

Fix round 1 (same branch, 77fbfc0d) closed three wrong deletions the
first fix left:
- A parenthesised sub-conjunction not in last place (`(A, B), C`,
  `A, (B, C), D`) read back right-nested, so `retract((c(_,_) :- (_, _, _)))`
  removed `c(9,X) :- (X = 1, X > 0), X < 5`. The grouping is now recorded
  at load as clause/2 metadata (`Clause.grouping`) and the Body rebuilt
  from it.
- `fail` read back as `false`, so `retract((b(N) :- false))` removed
  `b(1) :- fail`. The native front end records each spelling
  (`Predicate.fail_spellings` -> `Clause.fail_spellings`).
- A seam caller's flat-tuple pattern against a `.pl` procedure: `(_, _, _)`
  matched a 2-goal conjunction and `(_, _)` the cell `nl(X)`. A tuple whose
  first element is not a name is now read as the seam's conjunction.
When the metadata does not fit the stored goals (reif's `if_/3` with mixed
`fail` / `false`), the clause FAILS CLOSED: only an unbound pattern matches
it.

Fix round 2 (same branch) closed three more wrong-deletion classes:
- reif's `if_/3` is lowered into goals the text does not have (call/2,
  must_be/2 and a reified branch -- a hidden 3-goal conjunction for a
  general condition), so `(_, _)`-style patterns deleted it. Every body
  an `if_/3` lowering touched is now FAIL CLOSED (`fail_spellings == "?"`):
  only an unbound pattern matches it.
- A seam flat-tuple pattern INSIDE a goal argument (`once((_, _, _))`,
  `findall(_, (_, _, _), _)`, call/N, catch, forall, bagof/setof under
  `^`, a user meta_predicate) unified with the 2-goal `','` cell. The
  pattern side now converts every argument `_goal_positions` names.
- Goal expansion rebuilt the clause node without `fail_spellings`, and an
  empty record read as "every False is false". The node is now copied with
  `dataclasses.replace`, the front end records a spelling list for EVERY
  clause (`""` when it writes neither), and a body holding a fail/false
  goal with NO record fails closed. Only goal positions are counted: the
  atom `false` as data (`X = false`) is not a goal.

Fix round 3 (same branch) REDESIGNED the read-back by ruling: rebuilding
the ISO body from the lowered goals plus side metadata (grouping, fail
spellings) kept disagreeing with the lowering about goal positions and
dropped module qualifiers -- fail/false landed on the wrong goals
(`call(false), m:once(fail)`), `lists:` and user-module qualifiers were
erased, and `\+` / `;` inside call/N or meta arguments missed. Now the
native front end keeps each rule's body AS READ (`Predicate.source_body`
-> `Clause.source_body`: the body lowered as DATA over the clause's own
variables, built by the module's code, so it is in the bytecode cache),
and clause/2 / retract/1 rename it with the head and unify against it.
The grouping and fail-spelling reconstruction is gone. A body an if_/3
lowering rewrote (`source_rewritten`) and an ISO rule with no source term
FAIL CLOSED (only an unbound pattern matches). Seam clauses are unchanged.

Fix round 4 (same branch) closed one wrong-deletion class and two leaks
that round 3 introduced:
- A variable goal was stored as the bare variable, so `p(X) :- X` unified
  with every pattern: `retract((p(_) :- foo))` deleted it (21 of 24
  Scryer-oracled rows wrong). The body as read now applies ISO 7.6.2's
  body conversion: a variable at a goal position of `,` `;` `->` `*->`
  `\+` (and the body itself) is `call(X)`. The positions come from one
  table, `iso_l3._BODY_GOAL_CONTROL`, which `lw.goal` follows. A
  meta-argument (`findall(_, X, _)`) keeps the bare variable, as in Scryer.
- `constant(Name)` was stored as the lowering's internal PyThunk, so
  clause/2 handed out an engine object, and `clause(H, B), call(B)` raised.
  The same held for a partial list's StarUnpack node (`k([1|T])`) and
  `undefined`'s LoadName node. A source term that holds anything but
  data is now built by the compiler's own construction (`Out = <source>`,
  `clause_ops._source_built`, cached per clause), so Body is the term the
  compiled body sees: the constant's value and the partial list. If a node
  or thunk is still left after that, the call fails closed with a
  permission_error, never a leaked object.
- `node_class` now marks opaque data fields explicitly
  (`opaque_field`, metadata `opaque`) instead of keying on an `Any`
  annotation.
Row sets at round 4: 645 rows, 0 wrong deletions. The only 31 misses are
if_/3 rows.
Filed: todo/native-pl-stored-bodies-are-unexpanded-no-user-expansion-hooks-2026-10-16.md,
todo/load-time-doubles-per-nested-negation-mark-undo-invariant-2026-10-16.md.

Remaining (not fixed here):
- if_/3 rules fail closed by ruling (bound patterns miss them), although
  their source term is now kept.
- Seam has the same ambiguity by design: `('nl', Unify(..))` is both the
  conjunction `nl, X is 1` and the cell `nl(X is 1)`.
- A seam caller's pattern spelled with seam nodes other than not/or
  (`X is 1`, `X > 0`) matches nothing in an ISO procedure (a miss).
- `catch(fail, _, G)` crashes the load: filed separately.
