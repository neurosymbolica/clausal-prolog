# A multi-hole pattern unified as a value binds only its first split

Ruled 2026-10-08: `[*A, *B] = [1, 2]` has three answers wherever it is
written, in the order `append/3` gives them:

    A = [],     B = [1, 2] ;
    A = [1],    B = [2] ;
    A = [1, 2], B = []

Clause heads and `is` goals already do this, because the compiler enumerates
the splits itself. When the pattern reaches `unify` as a value, `unify`
returns one bool and binds the first split. This happens through
`P is [*A, *B], P is [1, 2]`, through `call/N`, and through `member/2` and
other builtins.

    via_head(A, B)  <- head([1, 2], A, B)           % 3 answers
    via_value(A, B) <- (P is [*A, *B], P is [1, 2])  % 1 answer

The strict expected-failures in
`tests/audit_2026_05_25/test_class_C02_nondet_first_only.py` (F015, F016)
pin this.

The earlier fix called unify again on the same trail to resume at the next
split, keyed by the target's content. It lost answers when two targets were
equal (`P = [1|T], member(P, [[1,2],[1,2]])`) and hashed the whole target on
every call. It was removed on 2026-10-08.

## Proposed: a nondeterministic pending-goal channel

When unify meets a pattern with two or more holes and more than one possible
split:
- it succeeds without binding the holes;
- it pushes a goal onto the trail that enumerates the splits (in effect
  `append`), and the push is undone on backtracking.

Every unify site then drains the pending goals as a generator before it
continues. That covers:
- compiled clause code, at each `unify(...)`;
- builtins that unify from Python or C (`member`, `nth0`/`nth1`, `select`,
  `findall` result unify, ...);
- the drive loop, in both the C core and the Python twin.

## Open questions

- **Hot path cost:** one check per unify site, of whether the trail has
  pending goals. Measure with the interleaved A/B perf gate.
- **Builtins that unify more than once per answer**, for example
  `msort`/`sort` comparing terms: draining inside them changes their arity
  of answers. Decide which builtins drain and which raise an
  instantiation error.
- **`freeze/2` and `when/2` have the same gap today.** `_freeze_hook`
  (`clausal/logic/coroutining.py`) drives a woken goal to its FIRST
  solution only (`break  # one solution suffices`). That is a committed
  choice, which the 2026-09-09 ruling says never to have. Reproduced on
  3c55340a:

      f(Y) :- freeze(X, member(Y, [1, 2, 3])), X = go.   % Y = 1 only
      g(Y) :- member(Y, [1, 2, 3]).                      % Y = 1 ; 2 ; 3

  The same channel fixes it: wake the goal as a pending goal.
- **ISO/Scryer reference:** Scryer wakes attributed-variable goals as a
  conjunction run after the unification, nondeterministically. Prefer that
  shape.

## 2026-10-09: the channel exists

Ruled: build it, in two candidates. Candidate 1 adds the channel and moves
`freeze/2` and `when/2` onto it (`clausal/logic/pending.py`; the trail's
`push_pending`/`take_pending`; `$unify_iter` and `$pending` in compiled
code; `StepGenerator.send` on a solution step). Candidate 2 queues the
split goal here: unify checks that one split fits, leaves the holes
unbound, and pushes a goal that enumerates the splits in append/3 order.
Under a driver only (`trail.defer`); a bare unify keeps the first split.

## 2026-10-10: done (candidate 2)

`_drive_seg_unify` (clausal/terms.py), the one driver behind
`SegList`/`SegString`/`SegBytes.__unify__`: under `trail.defer`, when a split
fits and another candidate remains, it undoes the split, leaves the holes
unbound and pushes a pending goal that binds each split in `append/3` order.
(First version: the last candidate was bound in place; since the security
review every multi-hole split is queued, so the occurs-checked builtins see
it. One hole binds in place.) A bare `unify` keeps the first split. F015/F016 are ordinary tests now;
`tests/test_value_pattern_keeps_every_split.py` covers `member/2`, equal
targets, `findall`, `call/N`, `not (P is T)`, `'\\='/2`, `dif/2`, `'='/3`,
`freeze/2`, text and bytes.

`dif/2` and `'='/3` needed no change: the pending push is a trail entry, so
the structural probe sees trail growth and suspends (`dif`) or answers
`true` per split and then `false` with the constraint (`'='/3`).

Not covered: two OPEN patterns unified with each other
(`[*A, *B] = [*C, *D]`, `_unify_open_seglists`) still bind one solution;
that has infinitely many answers in general.

Security review (2026-10-10), fixed in the same candidate:
- `unify_with_occurs_check/2` returned cyclic answers: the queued goal binds
  each split with plain unification. It now drains the goals itself and
  keeps an answer only when both terms are acyclic, which also fixes the
  first split (never occurs-checked before). `subsumes_term/2` took a
  Specific with queued holes as unbound; it drains the same way.
  `_acyclic_children` read a SegList through `_walk_raw`, which recursed
  into a cycle; it reads the segments now.
- Known cost, by design: a pattern of k holes against a list of n elements
  followed by a failing goal now visits every split, about n^(k-1) of them,
  each sliced afresh (3 holes, n = 400: ~4 s). That is the enumeration the
  ruling asks for; a bare first-split unify stays O(n). It matters only
  where outside data meets a pattern with 3+ holes.
