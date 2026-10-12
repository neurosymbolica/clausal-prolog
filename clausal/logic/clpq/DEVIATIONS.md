# Deviations from clp(q,r) 1.3.3

Every difference between the port and 1.3.3 is listed here.  An entry for an
optimisation names the measurement that justifies it.  Names are the
full-word names of `NAMES.md`; the 1.3.3 name follows in parentheses where
it helps.

## D1: rationals are (numerator, denominator) pairs of ints

1.3.3 represents a rational as the term `rat(N, D)` and evaluates arithmetic
through `evaluate_arithmetic/1,2` (`arith_eval`), which `arith_q.pl`
expands at compile time: `compile_rational_normalized` (`compile_Qn`) and
`linearize` in `arith.pl` turn each expression into a sequence of calls to
`addq`, `mulq`, ... (`add_rational`, `multiply_rational`, ... in the reading
copy).

The port has no compile-time goal expansion.  A rational is a
`(numerator, denominator)` pair of Python ints, normalised (denominator
positive, greatest common divisor 1), and the arithmetic is plain functions
in `clausal/logic/clpq/arithmetic.py` that map one-to-one onto C over
PyLong.  `compile_Qn`, `compile_Q`, `compile_R`, `linearize` and the
`specialize_*` predicates are not ported.

The functions and what they replace (`NAMES.md` gives both names; the
module drops the `_rational` suffix):

| 1.3.3 | Port | Difference |
|---|---|---|
| `addq/6`, `subq/6`, `mulq/6`, `divq/6` | `add`, `subtract`, `multiply`, `divide` | Take and return pairs, not four or six integer arguments.  `divide` by zero raises `ZeroDivisionError`, a programming error, never solver failure. |
| `comq/5` | `compare` | Returns -1, 0 or 1 instead of binding `<`, `=` or `>`. |
| `signumq/4` | `sign` | Returns the int sign; 1.3.3 returns it as the rational `S/1`. |
| `putq/3` | `make_rational` | `putq` builds `rat(N, D)` from an already-normal pair; `make_rational` also normalises (sign of the denominator, gcd) and raises `ZeroDivisionError` on a zero denominator. |
| `getq/3` | `from_number` | `getq` accepts an integer, a float (through `float_rat`) or a normal `rat(N, D)`.  `from_number` accepts an `int`, a `Fraction` or a finite `Decimal`, and raises `TypeError` for anything else, including floats, `bool`, subclasses and non-finite Decimals.  Floats are refused because the interface takes exact numbers only. |
| (none) | `to_number` | The way out: an `int` when the denominator is 1, otherwise a `Fraction`, as `present_number` does. |
| (none) | `negate`, `is_zero`, `ZERO`, `ONE` | 1.3.3 writes these inline (`N is -Na`, `N =:= 0`, `0, 1`). |

The runtime functions `nf.pl` evaluates besides `+ - * /` came with Task 10,
in `arith.pl`'s file order:

| 1.3.3 | Port | Difference |
|---|---|---|
| `limit_encoding_length/5` | `limit_encoding_length` | Returns the pair. |
| `expq/4`, `logq/4`, `sinq/4`, `cosq/4`, `tanq/4`, `asinq/4`, `acosq/4`, `atanq/4` | `exponential`, `logarithm`, `sine`, `cosine`, `tangent`, `arc_sine`, `arc_cosine`, `arc_tangent` | Through a float, as 1.3.3's are.  Outside a function's domain (`asin(2)`, `log(0)`) they raise `evaluation_error(undefined)`, past the float range `evaluation_error(float_overflow)` (ruling R19, `test_functions_outside_their_domain_raise_evaluation_errors`); Scryer gives `evaluation_error(undefined)` for `{sin(X) = 2}` and `{X = 0^(-1/2)}`. |
| `expq/6` | `exponential_power` | Exact for an integer exponent, through a float otherwise.  For `0^-N` 1.3.3 builds `rat(1, 0)`, which `arithmetic_normalize/2` then refuses, so `nf.pl`'s caller fails; the port raises `ZeroDivisionError`, and `normal_form.evaluate_nonlinear` fails before calling it (`test_integer_powers_expand_binomially`). |
| `powq/7` | `power` | The recursion is a loop. |
| `minq/6`, `maxq/6` | `minimum`, `maximum` | Return the rational. |
| `abs(rat(N, D))` (`specialize_rational_function//2`) | `absolute` | |
| `rat_float/3` | `rational_to_float` | A result past the float range raises `evaluation_error(float_overflow)`.  bv.pl's `float(X)` in `decrease_evaluate/2` uses it too. |
| `float_rat/3,9` | `float_to_rational` | The recursion is a loop; NaN raises `evaluation_error(undefined)` and an infinity `evaluation_error(float_overflow)`. |
| `arith_normalize/2` (`arith_q.pl`) | `arithmetic_normalize` | Takes an engine number or a rational pair.  A float goes through `float_to_rational`, as `get_rational/3` reads one, so `{X = 0.1}` gives `X = 1/10` (`test_numbers_are_exact_and_a_float_is_its_short_convergent`); Scryer's own `library(clpq)` gives the float's exact binary value instead. |
| `truncateq/4`, `floorq/4`, `ceilingq/4`, `roundq/4` | `truncate_rational`, `floor_rational`, `ceiling_rational`, `round_rational` (Task 13, for bb.pl) | Take and return a pair.  They keep the `_rational` suffix, so they do not shadow Python's `round`.  SICStus `//` truncates toward zero and Python's floors; `_truncated_quotient` gives SICStus's.  `round_rational` rounds to the nearest integer, a half away from zero (ISO `round/1`), where 1.3.3's `roundq/4` gives `1` on (-1, -1/2] (D18). |
| `integerp/2` (`arith_q.pl`) | `rational_integer` | Returns the int, or None. |
| `number/1` as nf.pl applies it | `is_number` | An int, Fraction, Decimal or float, not a bool. |

`Fraction` and `Decimal` are used only in `from_number` (to accept one),
`to_number` and `is_number` (to recognise one), the conversion edges, all in
this module; the solver core never computes with them.

## D2: `compenv.pl` is not ported

`compenv.pl` set up SICStus's compile environment for `fcompile`.  SICStus
itself marks it obsolete (it begins `end_of_file.`), and nothing in the
solver calls it.

## D3: the unification hook

1.3.3's `verify_attributes/3` (`itf3.pl`, `geler.pl`, `class.pl`) runs
before the binding of X takes effect and returns goals to run afterwards.
Clausal's attribute hook runs after the binding.  Each site in `itf3.pl`
that reads X's attributes or tests `var(X)` expecting X still unbound is
listed here with what the port does instead.

Sites in `class.pl` and `geler.pl` (Task 7):

- `class.pl` `delete_first/3` compares `X == Y`.  Called from `itf3.pl`'s
  hook, X is already bound in Clausal, so the port matches an element whose
  chain of bindings passes through X, which is what `==` sees before the
  binding (`test_delete_first_matches_a_variable_through_its_bindings`).
  The match goes one way only: an element whose bindings lead to X.  When
  X itself is bound to an element variable E, `X == E` holds after the
  binding but the port does not match; before the binding X is unbound, so
  `==` cannot see that direction either.  Every 1.3.3 caller passes X in
  the before-the-binding state: `component_drop/2` from `itf3.pl`'s
  `verify_attributes/3`, with X the variable being bound, and the bv.pl
  basis predicates (`basis_drop/1`, `basis_pivot/2`) with a constrained
  variable that is unbound, whose bindings lead to nothing.
- `class.pl` `verify_attributes/3` tests `var(Y)` and reads Y's attributes;
  Y is the variable X was bound to, still unbound, so nothing changes.
- `geler.pl` `verify_attributes/3` reads Y the same way; its Later goals go
  on a `LaterWork` queue and run after the hook
  (`test_verify_delayed_against_a_value_queues_the_goals`).

The engine's hook contract, which Task 11 builds on (checked 2026-10-12
with a probe key, Task 10 fix round 1):

- The engine binds the newer variable to the older, whichever argument
  order `unify` is given.
- It calls hooks only for the keys of the variable it binds, as
  `hook(value, other, trail)`, after the binding: `value` is that
  variable's attribute, `other` what it is now bound to.  Binding a
  variable without attributes to an attributed one calls nothing.
- `get_attr` dereferences: for a variable bound to another it reads the
  other's attributes (not its own), and for one bound to a number it
  returns None.

So for the X the hook is handling, `state_of(X)`,
`compare_variable_order(X, _)`, `normal_form_right_hand_side(Form, X)` and
`normal_form_coefficient_of(Form, X)` all return None, and
`delete_factor_homogeneous` finds X only by the identity of the bound
object.  `put_attr` on X raises when X is bound to a number, and when X is
bound to another variable it writes THAT variable's attributes.

What the port does (`attribute_hooks.py`, Task 11).  The hook takes X out
of the store before anything walks it: it replaces X by a fresh unbound
stand-in that carries X's state (the same `variable_order`, so every row
stays sorted) in the component's member list, its basis and every row.
The stand-in is X as 1.3.3's `verify_attributes/3` sees it, unbound, so
itf3.pl's code then runs on it unchanged: `detach_bounds/1`,
`back_substitute/2`, `normal_form_coefficient_of/3` and the rest need no
variants that take the state (`test_a_binding_reaches_the_rows_of_the_other_variables`,
`test_a_variable_whose_row_holds_the_other_one`).  Afterwards the
stand-in is, except in the case "A stand-in left in a row" below, out of
the component (`component_drop/2`) and out of every row
(`solve_for_variable/2`).  So class.pl's
`delete_first/3` (above) now gets the unbound stand-in from itf3.pl, not
the bound X.

Sites in `itf3.pl` (the `grep -n "verify_\|var("` list), with what the port
does instead:

- `verify_attributes/3` clause 1, `get_atts(X, [-component(_), ...,
  -nonzero])`: reads the state handed in.  `strictness(0)` counts as
  absent, because the port's two strictness fields cannot tell 0 from no
  attribute; with no other attribute, clause 1 and clause 3 do the same.
- Clause 2, `get_atts(X, forward(F))`: reads the state handed in.  The
  engine never hands a state with `forward`: only `bind_queued` sets it, on
  a variable it is about to bind (below), so the hook that binding wakes
  takes clause 2.  geler.pl's part has run for that variable already, so
  clause 2 does not run it again.
- Clause 3, `numbers_only(Y, X)`: runs first, before the stand-ins are made,
  for X and for every bound member a stand-in is made for, so the
  `type_error` leaves before any trailed change
  (`test_a_non_number_raises_a_type_error`).  Until the engine change
  64d5e9f6 (engine bug F5) this order was needed: the undo after a hook
  raised cleared the exception, and `unify` raised `SystemError`.  The
  engine now keeps it, so a later hook of the same unification after an
  earlier one changed the trail also gives the `type_error`:
  `{X >= 0}, {Y >= 0}, f(X, Y) = f(1, a)` (X and Y in different
  components) raises `type_error(rational, a)` (the same test).
  Y is accepted when it is a variable or an exact number (an int, a
  Fraction, a finite Decimal); a float raises `type_error(rational, Y)` as
  1.3.3's `arith_normalize(Y, Y)` test does (Scryer's clpq accepts it).
- Clause 3, `put_atts(X, forward(Y))`: never written on X.  It goes on the
  stand-in, where nothing reads it, and on a variable `bind_queued` binds,
  before the binding.
- `forward_dereference/2`, `var(X)`, `get_atts(X, forward(F))`: X here is a
  forward value, unbound, so nothing changes.  The recursion is a loop.
- `verify_nonzero/2`, `get_atts(X, nonzero)`: the state handed in.
  `var(Y)` and `put_atts(Y, nonzero)`: Y is unbound, nothing changes; a
  PlainVar Y cannot take the attribute and the hook fails there.
- `verify_type//2`, `get_atts(X, [type(Type), strictness(Strict)])`: the
  state handed in.  `verify_type//3`'s `var(Y)`: Y is what X is bound to,
  so nothing changes.
- `verify_linear/2`, `get_atts(X, [component(Class), linear_form(LinX)])`,
  `independent(LinX, X)`, `detach_bounds(X)`, `component_drop(Class, X)`,
  `normal_form(X-Y, Lin)`, `normal_form_coefficient_of(Lind, X, _)`,
  `solve_for_variable(Lind, X)`: all on the stand-in.  `solve/1` and
  `solve_for_variable/2` end in `export_binding/1`; the hook calls bv.pl's
  `solve/5` and `solve_for_variable/6` itself and hands their bindings to
  `bind_queued` (below).  A PlainVar Y cannot become a linear variable; the
  hook fails there.
- geler.pl's `verify_attributes/3` (`verify_delayed`) reads the state
  handed in, as Task 7 wrote it.

Several variables bound in one unification.  The engine makes every
binding of a unification first, then calls the hooks in turn.  So while X's
hook runs, another constrained variable W of the same unification can be
bound with its hook still to come ("unhooked"), and W can be in rows and
member lists the solver walks.  Before X's hook reads a row, it makes a
stand-in for every bound member of X's component, of Y's, and of the
component each such member's value is in, transitively, and does each
one's work (`_stand_in_for_bound_members`).  An unhooked W whose work was
done this way is no longer a member; when its own hook comes it finds that
and returns at once.  Components are scanned once each: X's and Y's are
one component when the binding is inside it
(`test_a_binding_within_one_component_makes_one_stand_in`).

Nothing else runs inside that window, as long as one rule holds (ruling
R27, a stated contract, not enforced in code): **no attribute hook body
calls an entry point of the port** (`post_constraint` and the other `{}/1`
forms, `inf`, `sup`, `minimize`, `maximize`, `entailed`, `bb_inf`,
`dump/3`, `projecting_assert/1`, `attribute_goal`).  A hook body runs while
other variables of the same unification are bound and their hooks are
still to come, so an entry point called there reads rows and member lists
that hold unhooked bindings.  The rule holds bare and under a driver
alike, because `trail.defer` is True inside every hook (below).  The
reason, a hook registered on another key that dumps and posts in its body:

```python
def hook(state, other, trail):
    out['dump'] = rc.dump([W], ["W"], trail)
    return post(trail, ("=<", Q, 1))
register_attr_hook("other_key", hook)
post(t, ("=", ("+", X, Q), 3), (">=", W, ("+", Q, Fraction(1, 2))),
     ("=<", W, 20))
put_attr(Z, "other_key", 1, t); unify(("f", Z, X), ("f", 1, 2), t)
```

Z's hook runs before X's.  At f0081942 the dump gives `[W =< 20]` and Q
is left unbound with sup 1; with the retired entry catch-up (800048a2) it
gave `[W >= 3/2, W =< 20]` and Q = 1.  A `post`, `inf`, `entailed` or
`bb_inf` from a hook body was wrong already at 800048a2.  The hooks the
engine registers keep the rule: `freeze/2` and `when/2` queue their goals,
and dif, clpfd, clpb, clpr, the two units keys, the legacy clpq key and
COMPONENT_KEY call no entry point.  The tripwire
`test_the_registered_attribute_hooks_are_the_known_set` fails when a hook
is registered or removed, and says to check this rule before extending
its list.  It scans the source under `clausal/` for
`register_attr_hook(KEY, ...)` at the start of a line, so it misses a hook
registered from C, from outside `clausal/`, or through a qualified or
aliased call.

The engine contract since 9b38a0f1 (`clausal/logic/pending.py`,
`docs/coroutining.md`): every unification, bare or under a driver, sets
`trail.defer` while it binds and runs the hooks, so the goals a hook wakes
through the queue (the port's Later goals, `freeze/2`, `when/2`) wait on
it; a bare unify then runs the queue to its first answer, after every hook
of the unification, and fails (undone) when the goals have no answer.  So
a hook never sees another hook's Later work run before it, and a woken
goal (a Later goal, a frozen goal that posts or reads the store) runs
after every hook of the unification, bare and under a driver alike.  A
solver step reaches no other part of the store: a constraint dereferences
its variables, and a binding runs that variable's hook, which makes the
stand-ins for its own components.

The checks: `test_one_unification_binding_two_constrained_variables`,
`test_a_later_goal_reads_no_unhooked_binding` (and `_the_other_way`),
`test_a_frozen_goal_reads_no_unhooked_binding` (Z frozen and bound before
X, bare, one at a time and under a driver: a post that must fail, one that
must hold, `W = Q + X`, and `inf(Q)` read in the goal),
`test_a_goal_another_key_wakes_answers_the_same_bare_and_under_a_driver`
(the same four goals, Z first and X first, bare equal to driver), and
`test_one_unification_bare_one_at_a_time_and_under_a_driver_agree`: 2,000
random stores of two components joined by a delayed goal, two or three
members bound in one unification, bare, one at a time and under a driver,
with 0 disagreements (20,000 seeds with `CLPQ_PORT_PROPERTY_SEEDS=20000`
also gave 0).  Scryer's clpq fails `{X + Y = 3}, f(X, Y) = f(1, 2)`; the
port answers it.

History (rulings R20, R21, R22; retired in Task 13c).  Before 9b38a0f1 a
bare unify ran no queue: outside a driver the port's hook ran its Later
goals in place, and `freeze/2` ran its goal in place, while sibling hooks
of the unification had not run yet (50 of 2,000 random stores disagreed
between bare and driver, and frozen posts failed unsoundly).  The port
covered that with `catch_up` (a stand-in pass over the components a Later
goal reached, before it ran), `catch_up_entry` (the same at every
store-reading entry point: nf.pl's `{}/1` comparisons, `wait_linear/3`,
`bb_inf`, `dump/3`, `projecting_assert/1`, `attribute_goal` with a trail),
the R22 skip of `catch_up_entry` under a driver (its tripwire test on the
registered hook keys stays, for ruling R27 above), and the `DRAINING` marker (below, "Later
goals").  On the rebased branch, counted over the regression set
(`tests/clpq_port tests/test_sandbox.py tests/test_clpq*.py`), `catch_up`
and `catch_up_entry` scanned 67,514 times and made 0 stand-ins (270 on the
old engine), and `DRAINING` was met 0 times (2,732 on the old engine), so
the catch-ups, the skip and the marker went (the tripwire stays, R27).
The cost they carried: posting a chain `{X(i+1) = X(i)}` into one
component was quadratic outside a driver.

PERF-BASELINE (Task 13c, 2026-10-12, the same engine build at 800048a2,
best of 3, two interleaved rounds within 0.05 s of each other), chain
posts, bare / under a driver:

| Posts | With the catch-up | Without |
|---|---|---|
| 2,500 | 0.24 / 0.04 s | 0.04 / 0.04 s |
| 5,000 | 0.83 / 0.09 s | 0.08 / 0.09 s |
| 10,000 | 3.46 / 0.17 s | 0.20 / 0.17 s |

Implied bindings are queued, not nested.  bv.pl's `export_binding/1` binds
each `X = Value` at once, and in 1.3.3 each binding runs X's
`verify_attributes/3` inside the one before.  The port's `bind_queued`
takes the bindings from a list: for each one it sets `forward` on X, runs
clause 3 on X while X is still unbound (the order 1.3.3 has), appends the
bindings that implies to the end of the list, and only then binds X; the
hook that binding wakes takes clause 2 and returns
(`test_implied_bindings_are_queued_not_nested`,
`test_a_cascade_of_delayed_goals_needs_no_recursion`).
`bounded_simplex.export_bindings` (bv.pl `export_binding/1`, from `solve/1`,
`solve_for_variable/2` and ineq.pl's reconsider) goes through the same list
(`attribute_hooks.bind_all`).  So the bindings are checked in breadth-first
order, where 1.3.3 checks each one's implied bindings before the next of
its own.

Later goals.  1.3.3 runs X's Later goals right after X's binding, inside
the binding that caused it.  The port puts them on the trail's pending
queue (`PendingLater`, `run_later`), so they run after every hook of the
unification: at the next goal boundary under a driver, and in the bare
unify's own drain otherwise.  `bind_all` (bv.pl's `export_binding/1` from a
post, with no unification around it) owns the queue the same way when no
driver does: it sets `trail.defer`, queues the Later work and runs the
queue to its first answer.  A cascade of delayed goals, each waking the
next, runs in the engine's one drain loop
(`test_a_cascade_of_delayed_goals_needs_no_recursion`, started by a unify
and by a post).  itf3.pl's Later goals (the bounds `{L =< Y}`) run before
geler.pl's (the delayed goals) for the same variable; SICStus's order
between the two modules' hooks is not checked.  Before 9b38a0f1 the
outermost hook outside a driver drained the Later work itself, behind a
`DRAINING` marker at the front of the queue (retired, Task 13c).  On the
new engine that marker no longer held a cascade flat: rebased with it
still in place, the cascade started by a post (each binding implied by
bounds, so `bind_all` makes it) raised `RecursionError` at 300 links.

Goals a probe or a search wakes (Task 13 fix round 1, ruling R24).  In
1.3.3 the goals a `{}/1` wakes run inside it, so `\+ {Cn}` in nf.pl's
`entailed/1` and every `{}/1` of bb.pl's search (`bb_branch/3`,
`bb_narrow_lower/1`, `bb_narrow_upper/1`) fail when a woken goal fails.
In the port such a goal is queued on the trail when a driver owns it, and
also as a goal a bare unify woke, in its drain, which owns the queue the
same way.  The probe's and the search's mark and undo then
dropped the queued goals unrun, so `{X >= -1/2, X =< 1/2, X*Y = 1},
bb_inf([X], X, I)` answered `I = 0` under a driver where Scryer fails.
Now `entailed` and `branch_and_bound_infimum_internal` take the queue
they were entered with (the undo puts it back, so work queued before them
is neither run nor dropped), and after each post run what it queued to its
first answer with `clausal.logic.pending.run_first`; no answer fails the
post, so a branch is pruned and a narrowing fails as a failed post would.
Checks, bare and under a driver: `test_a_goal_woken_by_narrowing_runs_in_it`,
`test_a_goal_woken_by_a_branch_runs_in_it`,
`test_a_goal_woken_by_the_narrowing_s_entailed_runs_in_it`,
`test_a_woken_bb_inf_runs_the_goals_its_search_wakes` (bare too: on the
old engine the search's goals waited behind the retired `DRAINING` marker
and were dropped),
`test_work_queued_before_bb_inf_stays_queued`,
`test_entailed_runs_the_goals_its_probe_wakes`, and every case of
`BB_INF_CASES` run both ways (`test_bb_inf_answers_as_the_oracle`).  D17's
nested case gives the same answer both ways (`I = 1, V = [0]`): the inner
`bb_inf` runs on each of the four bindings of X (two from the narrowing's
`entailed` probes, one from each branch), bare and under a driver.

A stand-in left in a row.  Where X is independent and Y's row holds X
(`{Y = X + Z}, X = Y`), `X - Y` has no X and 1.3.3 calls `solve/1` instead
of solving for X ("If X is indep and we do _not_ solve for it, we are in
deep shit because the ordering is violated", itf3.pl); X stays in Y's row
and is then bound to Y.  In the port the stand-in stays in the row,
unbound, and nothing binds it, so the store holds `Y = stand-in` with Z = 0
(`test_a_variable_whose_row_holds_the_other_one`, and the oracle cases
`{Y = X + Z, X >= 1}, X = Y`).  The stand-in stays a member of the
component in X's place (Task 12): `verify_linear` drops it only where it
solves for it.  In 1.3.3 X is Y once bound, and Y is a member, so the bound
that the Later goal `{L =< Y}` leaves on the stand-in must reach `dump/3`.
Before this, the residual of `{0*Z + Y = X + Z, X >= 1}, X = Y` was `X = Y`
without `X >= 1` (`test_a_stand_in_left_in_a_row_is_a_member`; the oracle
case now gives Scryer's `X = Y, X >= 1`).

`dump/3` and `projecting_assert/1` (Task 12) project with `trail.defer`
off and restore it after, as a bare call runs: the trial posts of
redund.pl's `negate_lower/3` and `negate_upper/3`, which 1.3.3 runs inside
`\+` with everything they wake, then run what they wake inside the trial
and undo it.  It shows with another key's goal:
`{X < 1, X + W =< 1, W >= 0}` with `freeze(W, fail)` dumps `X =< 1` bare
and under a driver, because the trial `{1 =< X}` binds W = 0 and the
frozen goal fails it; without the switch, under a driver, the goal waits
on the pending queue, the trial succeeds and the dump keeps `X < 1`
(`test_a_frozen_goal_woken_in_a_trial_post_runs_inside_it`).  With clpq
goals alone no difference was found (1,330 random stores): inside a dump
the non-linear goals are already marked run.
`test_dump_under_a_driver_matches_a_bare_dump` also checks that `defer` is
restored.  Since 9b38a0f1 a bare binding runs the whole queue, so the
projection first takes the queue it was entered with, as `entailed` does,
and the undo puts it back: a trial runs only what it wakes itself.
Without that, a failing goal already queued under a driver made every
trial fail and `dump/3` fail (`test_work_queued_before_dump_stays_queued`).

A dump in a goal the unification wakes.  `{X + Q = 3, Q >= 0}`,
`freeze(Z, dump([Q], [Q1], C))`, `f(Z, X) = f(1, 2)` (Z first): the frozen
goal runs after X's hook has bound Q = 1, so `dump/3` raises
`uninstantiation_error(1)`, as 1.3.3's `must_be/4` does with Q bound, and
`projecting_assert/1` projects nothing
(`test_dump_in_a_frozen_goal_sees_the_unification_s_bindings`,
`test_projecting_assert_in_a_frozen_goal_sees_the_unification_s_bindings`).
Such a dump cannot see the Later bound of a variable-variable binding of
the same unification (`{L =< Y}` from `verify_type`), which is queued
behind the frozen goal; 1.3.3 has the same gap, since the order of a
frozen goal and the Later goals of the hook is implementation-defined
(Task 12 review, probe `window.py` case (b)).

## D4: the order of variables is creation order

1.3.3 gives each constrained variable the attribute `order(_)` (bv.pl
`variable_intern`), a fresh variable, and compares two of them with
`compare/3` (itf3.pl's `nf_ordering/3` expansion; store.pl `nf_coeff_hom/3`).
project.pl's `order/3` later binds some of them to integers 1, 2, ... in the
order `arrangement/2` (ordering.pl) gives.  The standard order of two distinct
unbound variables is implementation-defined (ISO 7.2.1).  ordering.pl also sorts its graphs (`keysort/2`, `sort/2`,
library(ugraphs)) by the standard order of the constrained variables
themselves.

The port keeps the representation: `variable_order` holds a fresh `Var`,
which projection may bind to an int.  It fixes the order of two unbound
values as creation order, `Var._id` (the engine's monotonic creation
counter), not the engine's own `compare/3`, which orders variables by
`id()` (a memory address, which varies from run to run).  An unbound value
sorts before any int, and ints by value, as in standard order.
`variable_ordering.py` sorts graph vertices the same way, so `top_sort` is
deterministic.

What 1.3.3 needs from the order, and the tests that show the port has it:

- identity: equal only for the same variable
  (`test_variable_order_follows_creation_and_is_an_identity`);
- stability for the life of the variable, across backtracking and garbage
  collection (`test_variable_order_is_stable_across_backtracking_and_collection`);
- consistency with `ordering/1`: values bound by projection sort after all
  unbound ones and among themselves by number, and `renormalize` re-sorts a
  form under the new order
  (`test_order_values_bound_by_projection_sort_after_unbound_ones_by_number`,
  `test_renormalize_follows_an_imposed_order`).

What the order decides, and what checks it:

- Coefficients do not depend on it.  Every store.pl operation gives the same
  rational coefficient for each variable whatever the order
  (`test_scaled_addition_agrees_with_fraction_dicts` and the other
  `*_agrees_with_fraction_dicts` tests compare against order-free dicts;
  `test_renormalize_follows_an_imposed_order` shows the same pairs under two
  orders).
- It decides where a term sits in a form, and so which variable comes first.
  project.pl's `arrange_pivot/1` (project.pl:136-145) pivots X with the
  first variable Y of its form when `nf_ordering(Y, X, <)`, so the order
  decides which variables a residual answer solves for.  Through pivoting it
  also decides which optimal Vertex `bb_inf/5` returns when there are several
  optima.  Where SICStus's order of two unbound variables differs from
  creation order, the port can give a different residual or a different
  optimal vertex.  The check for those is the oracle tests of Task 12
  (residuals) and Task 13 (`bb_inf`), not this task's tests.
  The Task 13 result (2026-10-12): `BB_INF_CASES` in
  `tests/clpq_port/test_against_oracle.py` compares the Vertex of
  `bb_inf/5` with Scryer's, and agrees in every case, including the ones
  with several optimal vertices: `{X + Y >= 3/2, X >= 0, Y >= 0}` gives
  `[1, 1]` (of `[1, 1]`, `[2, 0]`, `[0, 2]`) with the list in either
  order, `{X + Y + Z >= 5/2, ...}` gives `[2, 0, 1]`, and the three
  knapsacks give `[2, 1, 0]`, `[2, 1, 0, 0]` and `[2, 1, 0, 1, 1, 0]`.
  No order difference was found.

Component variables are ordered the same way.  bv.pl `select_dependent/7`
collects the components of a new equation's old variables with
`ord_add_element/3`, an ordered set in the standard order of the component
variables; the port orders them by `Var._id`
(`test_select_dependent_orders_components_by_creation`).  The first of them
is the one `equate/2` unifies the others with, so with D8 this order decides
which component variable is bound and so the order of the merged member
list.  The check is again Task 12's oracle tests.

Task 12 sites.  `project_attributes/2` sorts its two variable lists with
`sort/2` (`projection.sort_variables`), and `related_linear_systems/3`
keys an assoc by the component variables; both use creation order.  The
order decides which variable a residual solves for and the order of the
residual's constraints.  The result of the oracle check (2026-10-12): the
residual text, order included, equals Scryer's dump in every oracle case
of `tests/clpq_port/test_against_oracle.py` (the 40 listed cases, the 4
hook cases, 40 random stores bound through the hook, the Review Focus 3
chain) and for each variable of the projection fuzz's first 30 seeds.  No
order difference was found, so `_KNOWN_TEXT_DIFFERENCES` there is empty;
`check_against_oracle` fails on a new one.  The only text difference is
the delayed goal Scryer drops (ruling R8, D7).  Scryer, not SICStus, is the
oracle, so an order difference between creation order and SICStus's
order of variables is not excluded.

## D5: renormalize of a form with no variables raises

store.pl `renormalize/2` calls `renormalize_log(Len, ...)` with the length of
the homogeneous part.  For length 0 no clause of the first two matches and
the third splits 0 into 0 and 0 and calls itself again, without end; SICStus
would run out of stack.  The port raises `ValueError` at once
(`test_renormalize_of_an_empty_homogeneous_part_raises`).  1.3.3 gives no
answer in this case either, so no answer changes.  Whether a caller can
reach it (project.pl `renorm_all`) is for Task 12 to show.

## D6: an unsatisfiable ordering raises the system error 1.3.3 intends

ordering.pl `arrangement/2` calls `illarg(system(unsatisfiable_ordering), 0,
0)` when `top_sort/2` fails (a cycle).  In SICStus 4.10.1 this misuses
`illarg/3`: `0` is not callable, so `normalize_culprit/4` fails and the
second clause's `must_be(Goal, callable, ...)` raises
`type_error(callable, 0)` (library/types.pl:194-201, 228-232).  The port
raises what 1.3.3 evidently means, `error(system_error(unsatisfiable_ordering),
arrangement/2)` (ruling R13; `test_a_cyclic_ordering_raises_the_system_error`).
A program that catches the SICStus `type_error` would not catch the port's
error.

## D7: delayed goals are (procedure, argument) pairs; `all_nonlinear/1` is not kept

`geler.pl` delays a Prolog goal and runs it with `call/1`.  The port delays
a `DelayedGoal(mutex, procedure, argument)` and runs
`procedure(argument, trail)`, which returns True or False (`delay_goal`,
1.3.3's `geler/2`).  So:

- A delayed goal is deterministic: it has one answer or none.  The goals
  `nf.pl` delays are `resubmit_equal`, `resubmit_less_than`,
  `resubmit_less_or_equal`, `resubmit_not_equal` (argument: the normal
  form) and `wait_linear_retry` (argument: a `WaitLinearRetry` record of
  Nf, Res, the procedure and its argument).  Each is deterministic in
  1.3.3: `repair/2` and the `submit_*` predicates commit with a cut or an
  if-then-else in every clause that can match more than one way
  (`submit_equal_single_term/1` b2, b3; `submit_equal_several_terms/3`;
  `submit_equal_constant_first/3` c11, whose `(P = 1, ! ; P = -1, !)` cuts,
  c12, c13; `submit_less_than_single_term/2`,
  `submit_less_than_several_terms/3` and the `=<` twins), `linear/1` and
  `linear_power_products/1` are indexed on their first argument, and
  `repair_power/5`'s two clauses test `var/1` and `nonvar/1`, so its
  leftover choice point fails at once.  What they call (bv.pl `solve/1`,
  `'solve_<'/1`, ineq.pl `inequality_one_variable/4`, ...) is already
  deterministic (Tasks 8, 9).  `wait_linear_retry`'s Goal is bv.pl's
  `minimize_linear/1` or `infimum_linear/4`, both deterministic, or bb.pl's
  `branch_and_bound_infimum_internal/5`.  That one is deterministic too
  (Task 13): its first clause always ends in `fail`, and its second, the
  last, runs `bb_delete/2`, a unification of the vertex lists and
  `{Inf =:= InfVal}`, none of which leaves a choice point.  The port's
  `branch_and_bound_infimum_internal` returns True or False and runs once
  per wake (`test_the_delayed_goal_is_deterministic`).  bb.pl's goal is
  `bb_inf_internal(Is, Nf, EpsN, Inf, Vertex)`, with Nf second;
  `translate_goal` writes it that way, `branch_and_bound_infimum_internal(Is,
  Res, Eps, Inf, Vertex)` (`test_the_delayed_goal_shows_nf_second`,
  `test_a_delayed_bb_inf_shows_in_the_residual`).
- Translation.  `geler/2` is a meta-predicate (`geler.pl`, `compenv.pl`
  `nfq:geler(?,:)`), so 1.3.3 stores `nfq:G`, and `translate_goal//1`'s
  `M:G` clause calls nfq.pl's exported `translate_goal//1` (the `transg` of
  the original).  That turns `resubmit_*(Nf)` into `clpq:{Term Rel 0}` and
  `wait_linear_retry(Nf, Res, Goal)` into `[clpq:{Term = Res}, Goal]`, the
  shape dump.pl's `nonlinear_strip/3` reads.  The port's `translate`,
  `collect_nonlinear` and `project_nonlinear` take that nfq.pl predicate as
  the parameter `translate_goal(procedure, argument) -> list of goal terms`
  (`test_translate_hands_each_goal_to_translate_goal_in_order`).
  nfq.pl's `translate_goal//1` is `normal_form.translate_goal`, the
  default of that parameter (`test_translate_is_plugged_into_delayed_goals`).
  Its goals are compound cells: `M:G` is `(":", M, G)` with M the atom
  `"clpq"` (`normal_form.SOLVER_MODULE`), which `nonlinear_strip/3` compares
  with `M == Solver`; `{C}` is `("{}", C)`; C is `(Rel, Term, Z)` with Term
  from `normal_form_to_term/2` (cells such as `("+", A, B)`, numbers as
  engine numbers) and Z = 0.  `wait_linear_retry`'s Goal is
  `(":", "clpq", (Name, Res, Arguments...))`, Name being the port
  procedure's name (`minimize_linear`, `infimum_linear`); 1.3.3's Goal is
  qualified `clpq:` by `wait_linear/3`'s meta-argument, bv.pl being part of
  module clpq (`test_translate_goal_of_resubmit_goals`,
  `test_translate_goal_of_wait_linear_retry_reaches_res_and_the_goal`).
  1.3.3 binds Res to the normal form before calling Goal; in the port Res
  is a variable of the record that nothing binds, and the procedure gets
  the normal form as its first argument.  The conjunction clause of
  `translate_goal//1` has nothing to do, because a port goal is never a
  conjunction.
- `project_nonlinear/3`'s reachable variables are the variables of the
  TRANSLATED goals, as in 1.3.3 (`term_variables_set/2` on them), so they
  include `wait_linear_retry`'s `Res` and every variable of its `Goal`
  (`test_project_nonlinear_reaches_what_translate_goal_emits`,
  `test_translate_goal_of_wait_linear_retry_reaches_res_and_the_goal`).  The
  walk covers tuples, lists and `__slots__` records; nf.pl's argument
  records (`Monomial`, `NonlinearBase`, `WaitLinearRetry`) are `__slots__`
  records.
- In `dump/3`, dump.pl's `nonlinear_crux/2` runs `collect_nonlinear//1`
  before `project_attributes/2`, so every goal is marked run when
  `project_nonlinear/3` collects again inside it: its reachable set is
  empty in a dump, as in 1.3.3.  dump.pl's `nonlinear_strip/3` drops a
  goal `M:What` whose M is not `clpq`, while `project_nonlinear/3` counts
  that goal's variables (`test_a_goal_of_another_module_is_stripped_yet_counts_as_reachable`).
  `wait_linear_retry`'s Goal is not such a goal: bv.pl is part of module
  `clpq` (clpq.pl `ensure_loaded`s it), so `nfq:wait_linear/3`'s
  meta-argument qualifies the Goal `clpq:`, and `nonlinear_strip/3` keeps
  it.  A residual can show `infimum_linear(R, ...)` beside `{Term = R}`
  (`test_wait_linear_retry_s_goal_is_clpq_qualified_so_it_is_kept`); not
  checked against SICStus.
- `project_nonlinear/3` also sorts the collected goals and puts them on a
  fresh variable as `all_nonlinear/1`, which `attribute_goal/2`'s second
  clause reads.  The variable is local to `project_nonlinear/3`, so no
  answer can reach it; the port skips the sort and the attribute.  The
  reachable variables are returned in creation order; 1.3.3's
  `term_variables_set/2` gives a set, and `project.pl` only marks each
  variable `target`, so the order does not matter
  (`test_project_nonlinear_gives_the_variables_the_goals_reach`).
- A PlainVar (an engine variable that cannot carry attributes; 1.3.3 has no
  such variable) cannot hold a delayed goal: `delay_goal` returns False for
  one, attaching nothing, and `verify_delayed` returns False when X's goals
  would move onto one (`test_delay_goal_on_a_plain_var_fails_closed`,
  `test_verify_delayed_onto_a_plain_var_fails_closed`).

## D8: components are a separate attribute key; binding direction is by age

`class.pl`'s `component_attributes/4` is its own attribute module in 1.3.3;
the port keeps it apart from `SolverState`, under
`components.COMPONENT_KEY`, with its own hook `verify_component`.

- SICStus binds a plain variable to an attributed one without calling
  `verify_attributes/3`; `component_new/4`'s `Su = Class` relies on that.
  This engine binds the newer variable to the older and calls the newer
  one's hook, so `verify_component` moves X's record onto a Y with no
  attributes (`test_component_new_puts_the_record_on_a_plain_variable`).
- When two components merge, the member and basis lists of the component
  bound (X) come before Y's.  The engine binds the newer component variable
  to the older (`test_a_merge_through_verify_component_is_undone_to_two_components`).
  Which of two attributed variables SICStus binds is not checked; if it is
  the other, the merged member order differs, and the member order decides
  `project.pl`'s numbering of unordered variables.  Task 12's oracle tests
  are the check: no residual order differs from Scryer's (D4, "Task 12
  sites"), including the merges of the 40 random stores bound through the
  hook.
- A PlainVar Y (an engine variable that cannot carry attributes; 1.3.3 has
  none) cannot take the record, so `verify_component` fails there
  (`test_verify_component_fails_closed_on_a_plain_var`).  1.3.3 would bind
  the plain variable and succeed; the port refuses rather than lose the
  component.
- `delete_first/3`, finding nothing to delete, rebuilds an equal list in
  1.3.3; the port returns the list itself.  `component_basis_drop/2`'s
  `Basis0 \== Basis` then becomes `is not`
  (`test_delete_first_of_an_absent_element_gives_the_list_itself`).

## D9: dereference of a monomial that is not `K*X^1` raises

bv.pl `dereference_balanced/4` (`log_deref/4`) reads one or two monomials
through its clause heads `[monomial(K,[X^1])|Vs]`.  For any other monomial
those heads fail, and the last clause splits a count of 1 into 0 and 1 and
calls itself on 1 again, without end.  nf.pl calls it only on linear normal
forms, so 1.3.3 never gets there.  The port raises `ValueError` at once
(`test_dereference_of_a_non_linear_monomial_raises`), as D5 does for
`renormalize`.  1.3.3 gives no answer in this case either, so no answer
changes.

## D10: `decrease_evaluate` returns `unlimited` outright

bv.pl `decrease_evaluate/2` (`dec_eval/2`) builds its result as
`Res = [Delta-Action | Tail]` and recurses on `Tail`.  When a later term is
unlimited, `Tail = unlimited(V, T)` closes the list with that term, giving
the improper list `[Delta-Action | unlimited(V, T)]`.  `decrease_step_best/2`
then matches `E = [_|_]` and calls `keysort/2` on it, which raises a type
error.  Only an unlimited first term comes back as `unlimited(V, T)` itself.
The port returns the unlimited status whatever its position
(`test_decrease_evaluate_returns_unlimited_after_a_listed_term`), so
`decrease_step_best` reports `unlimited` where 1.3.3 raises.  Both
predicates are dead code in 1.3.3: the one call, in `iterate_decrease/2`, is
commented out.

## D11: the standard order of two variables in a power product is creation order

nf.pl keeps a normal form sorted by `compare/3` on its power products
(`normal_form_add/4`, `normal_form_add_two/3`) and a power product sorted by
`compare/3` on its bases (`merge_power_products/4`): the standard order of
terms.  The port writes that order out for the terms that occur
(`compare_power_products`, `compare_bases`, `compare_normal_forms`): a power
`X^P` is the compound `^/2`, a power product a list (`[]` before any
non-empty list), a monomial `v/2`, a coefficient `rat/2`, a skeleton
compared by arity, then name, then arguments
(`test_power_products_follow_the_standard_order`).  Two unbound variables
are in creation order (`Var._id`), as in D4; SICStus orders them by age,
which can differ.  The order decides the order of monomials in a normal
form, which `normal_form_to_term/2` shows in a delayed goal's residual
(Task 12's oracle tests check it), and which monomial comes first in the
`submit_*` cases; a linear normal form reaches bv.pl through
`dereference/2`, which re-sorts it by `compare_variable_order` (D4), so
linear answers do not depend on it.

## D12: a posted `{C1 ; C2}` hands its choice points to the caller

nf.pl's `{R ; Rs}` (`{}/1` clause 3, "for entailment checking") is a choice
point: on backtracking `{C1 ; C2}` gives the answers of C2 after those of C1.
Port goals return a bool (D7), so the choice points are data:

- Inside one `{}`, a later failure undoes to the latest choice point and
  takes the other branch
  (`test_a_disjunction_is_retried_when_a_later_constraint_fails`).
- `post_constraint_with_choices` posts and returns a `ConstraintChoices`
  (the stack of trail mark, other branch and the goals after it), or None
  where it fails.  `resume_constraint(state, trail)` undoes to the newest
  choice point, takes its other branch and the goals after it, and returns
  True or, when no branch is left, False
  (`test_a_caller_resumes_a_posted_disjunction`,
  `test_resuming_keeps_the_choices_of_the_branch_taken`).
- `post_constraint` drops the choice points; `entailed/1` needs only
  whether `{Cn}` has an answer, so it uses that
  (`test_entailed_leaves_the_store_as_it_was`).

Ruling R18: the API must keep the choice point.  Task 14's adapter for
`{}` posts with `post_constraint_with_choices`, yields one answer, and on
backtracking calls `resume_constraint` with the same state until it
returns False, as a generator over the engine's backtracking.  It must not
call `post_constraint` for a constraint that holds `;`.

## D13: an nf.pl binding of a stored variable raised until Task 11 (resolved)

Resolved by Task 11: the interim error is gone, and nf.pl's bindings go
through the CLPQ_KEY hook (`test_binding_a_variable_the_store_holds_goes_through_the_hook`).
The entry as Task 10 wrote it:


nf.pl binds a variable outside bv.pl's `solve/5` in three places:
`submit_equal_single_term/1` b3 (`n*X^P = 0`), `submit_equal_constant_first/3`
c11 (`K*X + I = 0`), and through c11 `minimize_linear/1`'s
`{Dep =:= Inf}`.  In 1.3.3 that binding wakes itf3.pl's
`verify_attributes/3`, which checks X's bounds and takes X out of the rows
and the component.  Clausal has no hook for the port's key until Task 11, so
the binding would leave the store holding a number where X was, and a later
`inf/2` would crash.  The port fails closed: when X has a linear form, a
component, or a delayed goal not yet run, it raises
`system_error(clpq_binding_needs_hook)` instead of binding
(`test_binding_a_variable_the_store_holds_raises`).  A delayed goal that
has run (the one resubmitting now) does not count.  Cost until Task 11:
`{X >= 0}, {X = 1}`, `entailed(X =\= 1)` on a stored X, and `maximize/1`
raise where 1.3.3 answers.  Task 11 removes this check.

## D14: itf3.pl's presentation half

`attribute_goal/2`, `dump_linear//2` and `dump_nonzero//2` are ported in
`attribute_hooks.py`; dump.pl (Task 12) calls the last two.

- `presentation_context/2` keeps the context (`toplevel` or `compiler`) in
  a dynamic predicate.  The port has no module-level state, so the context
  is the parameter `context` of `attribute_goal`, `dump_linear` and
  `dump_nonzero`, `toplevel` by default.
- The `compiler` context calls `compiler_dump_variable//4` and
  `compiler_dump_disequation//3`, which no 1.3.3 file defines.  The port
  raises `ValueError` for that context.
- `wrap/2` writes `clpq:{C}` unless the `typein_module` flag names clpq or a
  module that imports `{}/1` from it.  Clausal has no typein module, so the
  port always writes `{C}` (`test_list_to_wrapped_conjunction`).
- `goal_expansion/5` and `linear_solver_module/1` are compile-time code:
  `nf_ordering/3` is `variable_ordering.compare_variable_order` (Task 6),
  and `decompose/4` is reading a `LinearForm`'s fields.

## D15: dump.pl and redund.pl: what is not ported or differs

- `projecting_assert/1` asserts the projected clause into the caller's
  module.  The solver core has no database, so the port's
  `projecting_assert(clause, trail)` returns the clause to assert, with
  `clpq:{Conj}` as its first goal (or the clause itself where 1.3.3's
  second clause applies), and its caller asserts it
  (`test_projecting_assert_puts_the_projection_first`).
- `dump/3`'s `must_be(Target, proper_list(var), ...)`: the target list is a
  Python list, so a partial list cannot occur; an element that is not an
  unbound variable raises `uninstantiation_error(E)`, the error
  library(types) documents for a bound term where a variable is expected
  (`test_dump_raises_for_a_bound_target_and_fails_for_unequal_lengths`).
  The context term is `dump/3`, not SICStus's goal and argument number.
- `dump/3` is a `findall/3` of the target list and the goals, unified with
  `[NewVars-Constraints]`.  The port takes a trail mark, projects, copies
  the goals with each target replaced by its name, and undoes; where a
  target occurs twice, it then unifies the two names, which is what the
  unification with `NewVars` does
  (`test_dump_of_a_repeated_target_unifies_its_names`).
- `redundancy_variables/1`'s second clause, which times the first clause's
  call, is unreachable after the first clause's cut and is not ported.

## D16: residual terms hold engine numbers

1.3.3's `dump/3` answers hold rationals as `rat(N, D)` terms, which
SICStus prints through `portray/1`.  The port's rational is a pair
`(n, d)` (D1), and a pair inside a compound cell reads as a compound.  So
store.pl's `normal_form_to_sum/3` and `homogeneous_to_sum/3` and bv.pl's
`dump_variable//4` and `dump_disequation//3` write each rational as an
engine number (`to_number`: an int, or a Fraction), as nf.pl's
`normal_form_to_term/2` already does
(`test_normal_form_to_sum_writes_engine_numbers`,
`test_dump_variable_and_dump_disequation_write_engine_numbers`,
`test_dump_emits_engine_numbers_never_rational_pairs`).

## D17: the incumbent of `bb_inf` is local to each search

bb.pl keeps the best leaf found so far in one global record,
`bb_put(incumbent, Inf-Vertex)`, which `branch_and_bound_infimum_internal/5`
clears at the start (`bb_delete(incumbent, _)`) and takes at the end.  A
second `bb_inf` that runs inside the search, a delayed one woken when a
branch binds the variable it waits on, clears and takes the same record.
The outer search then has no incumbent: `branch_and_bound_better_bound/1`
lets every later node through, and the leaf it records last is its
answer, which can be worse than the optimum, or none, so that the outer
`bb_inf` fails.

The port keeps the incumbent in a local of `branch_and_bound_loop`
(the plan's Task 13 brief), so each search has its own.  The
case `{W >= 1/2}, bb_inf([W], W*X, I2), {X >= 0, X =< 1, Z + 2*X >= 1,
Z - 2*X >= 0}, bb_inf([X], Z, I, [VX], 0)`: the minimum of Z is 1, at
X = 0.  Scryer answers `I = 2, VX = 1`, the port `I = 1, VX = 0`
(`test_a_nested_bb_inf_differs_from_the_oracle`,
`test_a_nested_bb_inf_keeps_the_outer_incumbent`); without the inner
`bb_inf` both answer 1.  A copy of the port with one shared record in
place of the local (the Task 13 report) answers 2, as Scryer does.  Not
checked against SICStus.

## D18: `round_rational` is ISO `round/1`, not 1.3.3's `roundq/4`

arith.pl's `roundq/4` (lines 614-626) takes `I is N//D`, keeps I when
`|x - I| < 1/2`, and otherwise adds one when `I >= 0` and subtracts one
when not.  The sign it tests is I's, not x's, and I is 0 for every x in
(-1, -1/2], so all of them round to `+1`: `round(-1/2) = 1` and
`round(-3/4) = 1`.  bb.pl's `round_values/2` rounds the vertex with it,
so a leaf whose value is within Eps of -1 gets the vertex 1.

The port rounds correctly, as for D17 (correctness first, ruling R25):
the nearest integer, a half away from zero, so `-1/2` and `-3/4` give
`-1` (`test_round_rational_is_nearest_with_half_away_from_zero`, over
-3/2, -1, -3/4, -1/2, -1/4, 0, 1/2 and 3/2).  Scryer agrees with the port:
`{X >= -1, Y >= 0, X + Y >= -3/4}, bb_inf([X], X + 2*Y, I, [V], 1/2)`
gives `I = -3/4, V = -1` on both (`test_bb_inf_answers_as_the_oracle`,
`test_the_vertex_rounds_a_value_in_minus_one_to_minus_a_half_down`).
Not checked against SICStus.

## D19: a binding checks that its strict bounds can still hold

bv.pl's `solve/5` ends in `rcbl/3` (`reconsider_basis_list`, bv.pl lines
682 and 697), which walks the basis once (lines 1055-1060) and keeps its
Continuation across pivots (`rcbl_app/5`, `rcbl_unl/7`, lines 1166-1193).
It tests strictness only for the culprit it is handling, at its optimum
(`rcbl_opt/5`, lines 1121-1162).  A variable that an applied or unlimited
pivot moves into the basis is not in the Continuation and is never
examined.  When it sits at a strict bound it cannot leave, the store is
unsatisfiable and the binding is accepted.  itf3.pl's `verify_lin/2`
(itf3.pl line 242) reaches `solve/5` for every binding of a constrained
variable, and nf.pl reaches it for every posted equation.  A posted bound
does not show this (`udu/5`, ineq.pl, reconsiders the bounded variable
first): 17,047 random bound posts agree with z3.

The reproducer (found by the Task 12 projection fuzz, seed 30):

    {-X0 - 3*X4 + X1 =< 4, -3*X0 =< 3, -3*X3 + 3*X4 < 4,
     -X0 - 2*X4 - X3 < -2, 3*X0 - X1 - 3*X4 < 0}, X4 = -1

Here `X0 - 1/3*X1 < -1` and `X0 - X1 >= -1` give `X0 < -1`, against
`X0 >= -1`.  Scryer's clpq accepts it as `X4 = -1` and as `{X4 = -1}`;
z3 says unsatisfiable; `{X4 =< -1}` fails on both.

The port keeps 1.3.3's pass unchanged.  When that pass has changed the
store (the trail grew), `strictly_satisfiable` (bounded_simplex.py) checks
that every strict bound in the component can still hold.  The store
without strictness is satisfiable there.  The reason is not that every
variable is within its bounds: a nonbasic variable without an active
bound has the implicit value 0, which can be outside them.  The reason
is an invariant of the pass.  The row of every bounded basis variable
holds only nonbasic variables at an active bound, and every basis value
is within its bounds.  So a nonbasic variable without an active bound is
only in rows of unbounded variables, and the point with it anywhere
inside its own interval satisfies the store without strictness.  The
Task 13b review argued the invariant from bv.pl's pivots and measured 0
violations over about 2,900 calls of the check.
`test_the_check_runs_where_its_invariant_holds` asserts it at every call
of the check over the fuzz.  The same assertion, run mid-pass at the
start of each culprit's handling, reports violations at 1,409 of 1,858
entries, so it can fail.

A strict bound can hold when its variable is inside it now.  A nonbasic
variable at a strict active bound can also take a small step inside,
unless a basis variable at one of its bounds has it in its row with the
sign that pushes the basis variable out.  Each remaining variable is
checked with `iterate_decrease` on it (as `infimum_linear` sets that up,
under a mark and undo).  These are the basis variables at a strict bound
and the blocked nonbasic ones.  The walk stops at the first value past
the bound, and the binding fails when it cannot reach one.  If each
strict bound holds at some point of the store, all of them hold at once
at the average of those points, because the store is convex
(`test_a_binding_that_leaves_strict_constraints_unsatisfiable_fails`, and
a z3 fuzz, `test_a_binding_is_accepted_exactly_when_z3_finds_it_satisfiable`,
bare and under a driver).  Each part of the check is needed: removing
the basis-variable candidates, the nonbasic ones, or either sign of
blocking makes those tests fail.  A failed `determine_active_decrease` or
`decrease_step` in the walk refuses the binding.  The invariant makes
both unreachable, and a refusal shows as a missing answer where an
acceptance could hide an unsatisfiable store.  This is a correctness
divergence, ruled by the operator (2026-10-12, R26), with the same
precedent as D17 and D18.

The operator's first choice was a re-walk of the basis until a pass moves
nothing.  It was built and does not terminate.  Two variables at strict
bounds 0, each unlimited through the other, are exchanged on every pass
(fuzz seed 2582).  Degenerate applied pivots at one vertex also cycle
(seed 1532).  A basis variable whose row is already a constant, its binding
waiting in the bindings list, is found on every pass (seed 40).  A
fixpoint would need an anti-cycling rule that 1.3.3 does not have.  The
check needs none: it reads the store and undoes its pivots.

Cost, measured 2026-10-12: an A/B in one process with the check switched
off, interleaved, the minimum of 5 runs (Task 13b report).  Optimising
every strict variable at a bound to its full optimum made binding a
50-variable store 60 times slower (21.3 s against 0.35 s).  The blocking
filter and the early stop bring it to:

| Workload | With the check | Without | Extra | Checks run |
|---|---|---|---|---|
| 10,000 chain posts and the binding `X0 = 5`, driver | 0.470 s | 0.461 s | +2.0% | 0 |
| bb_inf: the three knapsacks of test_branch_and_bound.py and the 12-variable deep search | 0.170 s | 0.165 s | +3.0% | 12 |
| 200 variables in (0, 10), 200 random constraints tight at a point, the 200 bound to it one at a time, bare | 0.827 s | 0.758 s | +9.1% | 118 |
| the same, driver | 0.848 s | 0.786 s | +8.0% | 118 |
| the z3 fuzz, 3,000 seeds, bare (z3 included) | 7.803 s | 7.747 s | +0.7% | 1,118 |

The fuzz row and the counts below are for the fuzz as first committed
(35144b69), with single-variable bindings only.  Over its 30,000 seeds,
the first pass ran 36,019 times, the check ran 11,050 times (when the
pass changed the store), and it walked a variable 513 times; it refused
73 bindings.  With 39,782 bindings checked in each mode, there were 73
disagreements in each mode before D19, every one an unsatisfiable
binding accepted, and none after it.

The fuzz now also has `=` among the store's constraints and an equation
step `{aX + bY (+ cZ) = K}`, with K at the sum's inf, its sup or a point,
and it checks every store post against z3 as well.  Over 30,000 seeds,
227,426 posts and steps are checked in each mode.  With the check
switched off there are 26 disagreements in each mode, all of them an
unsatisfiable step accepted: 15 equations, 7 `{X = K}` and 4 `X = K`.
No store post disagrees.  With the check on there are none.

Woken goals: the only unification under the check's mark is class.pl's
join of the fresh objective variable's component.  No frozen goal can be
on that variable, and in the fuzz the pending queue had the same length
before and after each check (Task 8's inf/sup is the same case).

Not checked against SICStus: MORNING-SICSTUS (7) stays open.
