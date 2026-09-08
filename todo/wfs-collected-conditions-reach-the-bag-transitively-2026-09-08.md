# A collected bag's conditions reach it TRANSITIVELY, not by a shared rule

Raised by the opus review of `e618c3ee` (2026-09-08) as a High. **NOT
reproduced** on either shape it names — filed so the reasoning is not lost,
with the measurements that failed to confirm it.

## The concern, as stated

A collecting construct (`findall`/`bagof`/`setof`/`count_all`) binds its
condition target ONCE at entry (`_fa_cl = $current_leader()`). The two ways a
condition is credited are stack-RELATIVE instead:

* `_credit_consumer` at a streaming site targets `_streaming_consumer_leader(entry)`
  — the leader immediately below THAT table's frame;
* `_delay_negation` targets `current_leader()` — the stack top right then.

These name the same frame only when the conditional row's table sits directly
on top of `_fa_cl`. Park a second table in between and they diverge, and the
harvest would collect nothing.

## What was measured, on both `a6baeaf1` and the branch

Both of the review's own witnesses, built and run A/B:

* `findall(X, (wins(X), tb(X)), L)` over two cold tables → raises
  `UndefinedAnswer` on BOTH trees (correct);
* `findall(X, (wins(X), not zz(X)), L)`, a tabled negation after a streaming
  tabled goal → raises `UndefinedAnswer` on BOTH trees (correct).

So the conditions do reach the bag. The route is transitive rather than
direct: the inner table credits the leader below IT, which folds the condition
into its own answers' delay sets, and when THAT table streams an answer the
condition is credited one frame further down — arriving at the collecting
leader after as many hops as there are tables in between.

Both shapes are now pinned
(`test_a_bag_over_two_tabled_goals_keeps_their_conditions`,
`test_a_negation_after_a_streaming_tabled_goal_in_a_bag`) so the transitive
path cannot silently regress.

## What is NOT settled

The review's residual worry is an ordering one, and the two witnesses do not
address it: a conditional row arriving under the inner table's LAST answer has
no further answer to be folded into. Nobody has built that shape. If someone
does and it loses the condition, the review's proposed fix is the right one and
is written down here:

> Give the collection an explicit sink. Push the construct's bag onto a small
> thread-local stack at entry, have `_charge_delays`/`_credit_consumer` also
> deposit into the innermost open sink so the condition is captured wherever on
> the leader stack it lands, and pop-and-charge at exit.

That replaces a transitive, ordering-sensitive route with a direct one, and it
would also subsume the entry-time-vs-stack-relative mismatch rather than
reconciling it. It is a real design change to the condition channel, which is
why it was not made on an unreproduced finding.

## Related

- `clausal/logic/tabling.py::harvest_conditions`, `::charge_conditions`,
  `::_credit_consumer`, `::_delay_negation`, `::_streaming_consumer_leader`
- `clausal/logic/compiler/control_constructs.py::_leader_stmt`
- `todo/done/wfs-delays-through-composite-goals-in-goal-position-2026-09-08.md`
