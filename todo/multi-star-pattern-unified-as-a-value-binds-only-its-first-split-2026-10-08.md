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
