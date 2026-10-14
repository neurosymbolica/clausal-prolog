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
| `getq/3` | `from_number` | `getq` accepts an integer, a float (through `float_rat`) or a normal `rat(N, D)`.  `from_number` accepts an `int`, a `Fraction` or a finite `Decimal`, and raises `TypeError` for anything else, including floats, `bool` and subclasses (a programming error: nf.pl's callers read a float through `float_to_rational`).  A Decimal is an engine number a program can write, so its refusals are ISO errors (ruling R19, Task 16): NaN is `evaluation_error(undefined)` and an infinity `evaluation_error(float_overflow)`, as for a float; an exponent of ten past `DECIMAL_EXPONENT_LIMIT` (100,000) is `representation_error(max_integer)`, because `Decimal('1E+999999999')` would build an integer of a billion digits and never return (`test_a_decimal_without_a_rational_raises`). |
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
| `float_rat/3,9` | `float_to_rational` | The recursion is a loop; NaN raises `evaluation_error(undefined)` and an infinity `evaluation_error(float_overflow)`.  Where the next step's reciprocal is past the float range (a remainder under about 5.6e-309, a subnormal float such as 5.0e-324), the answer is the float's exact value; the step raised `OverflowError` before Task 16, and SICStus's float division would overflow there.  Not checked against SICStus (`test_the_smallest_float_is_read_exactly`). |
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

Nothing else runs inside that window, because one rule holds (ruling
R27, fail-closed on the hook's own trail since ruling R30, with the
per-trail limit of ruling R31 below): **no attribute hook body calls an
entry point of the port**.  A hook body runs while other variables of the
same unification are bound and their hooks are still to come, so an
entry point called there reads rows and member lists that hold unhooked
bindings.  The engine's `trail.hooks_running` is above 0 inside every
hook and 0 at every goal, bare and under a driver (a750f58c,
docs/coroutining.md "Inside a hook or at a goal";
`test_the_port_hook_runs_inside_the_counter_and_its_later_work_at_a_goal`).
The reason, a hook registered on another key that dumps and posts in its body:

```python
def hook(state, other, trail):
    out['dump'] = rc.dump([W], ["W"], trail)
    return post(trail, ("=<", Q, 1))
register_attr_hook("other_key", hook)
post(t, ("=", ("+", X, Q), 3), (">=", W, ("+", Q, Fraction(1, 2))),
     ("=<", W, 20))
put_attr(Z, "other_key", 1, t); unify(("f", Z, X), ("f", 1, 2), t)
```

Z's hook runs before X's.  At f0081942 the dump gave `[W =< 20]` and Q
was left unbound with sup 1; with the retired entry catch-up (800048a2) it
gave `[W >= 3/2, W =< 20]` and Q = 1.  A `post`, `inf`, `entailed` or
`bb_inf` from a hook body was wrong already at 800048a2.

How the rule is enforced (ruling R30, Task 14b).  Every public entry
point that reads or writes the store, called with a trail whose hooks are
running, raises
`error(permission_error(call, goal, Culprit), Name/Arity)` while
`trail.hooks_running` is above 0, the shape the engine's `solve`/`call`
raise there (`attributes.refuse_inside_attribute_hooks`).  The port's own
entry points (1.3.3's user predicates): nf.pl's `{}/1`
(`post_constraint`, `post_constraint_with_choices`, and
`resume_constraint`), `entailed/1`, bv.pl's `inf/2` and `inf/4`, `sup/2`
and `sup/4`, `maximize/1`, `minimize/1`, bb.pl's `bb_inf/3` and
`bb_inf/5`, dump.pl's `dump/3` and
`projecting_assert/1`, ordering.pl's `ordering/1`.  The adapter's
(`holzbaur.py`): `in_q/1` and `in_q/3`, `inf/2`, `sup/2`, `maximize/2`, `minimize/2`,
`bb_inf/3`, `entailed/1`, `dump_q/2` (and the `clpq.dump` builtin through
it), `residual_q/1`, `ordering/1`, `{}/1` (`clpq_constraint_block`,
`clpq_constraint_answers`) and `promote_fd_to_q/1`; the Culprit is the
goal as the entry point was called.  An omitted optional argument is a
fresh variable in the Culprit, never a Python None (`in_q(X)` is
`in_q/1`, `in_q(X, 0, None)` is `in_q(X, 0, _)`), and the port's
`inf/4`, `sup/4` and `bb_inf/5` report those arities with every argument.
The indicator names the entry point, not the builtin that reached it:
`rational/1` reports `in_q/1`, `int_minimize/3` reports `bb_inf/3`,
`clpq.supremum/2` and `clpq.infimum/2` report `sup/2` and `inf/2`, and
`clpq.rational/1` reports `{}/1` (the adapter does not know the builtin's
name, and threading it through would change the legacy API the two
solvers share).  The
repro above now raises `permission_error(call, goal, dump([W], [W], _))`
from `dump/3`, and the unification raises with it
(`test_the_d3_repro_raises_instead_of_answering_wrong`; with the check
removed it answers `[W =< 20]` and Q unbound with sup 1 again, the
mutation check of Task 14b).  Each entry point is refused from a probe
hook and runs at a goal, bare and under a driver
(tests/clpq_port/test_refused_inside_a_hook.py).  The port's own hook and
its internals call no public entry point inside the dispatch: its Later
goals (`PostBound` and the others) post through `{}/1` from the pending
queue, at a goal (`test_the_port_s_own_hook_is_not_refused`, the gate
set and the hook-window fuzz under both switches).  `attribute_goal`
takes no trail and is not checked; only tests call it (the engine's
toplevel prints residuals through `residual_q`, which is checked).

The check is per trail (ruling R31).  It reads the counter of the trail
the entry point is given, and the engine counts hook dispatch per trail.
A hook body that reaches the store through another trail (a fresh
`Trail()`) reads 0 there, is not refused, and gets the wrong answer
above: D3's repro through a fresh trail dumps `[W =< 20]` and leaves Q
unbound (`test_a_fresh_trail_inside_a_hook_is_not_seen_by_the_check`,
which pins this limit so that an engine-wide dispatch depth flips it).
This was so before R30 as well.  So a hook must not reach the store
through another trail; R27 stays a contract there.

clpfd's calls into CLP(Q) are the exception.  They are calls, not
registrations, and some run inside a hook (clpfd's propagation in its own
hook, its reified comparisons, the units hook).  Under
`CLAUSAL_CLPQ=holzbaur` the adapter's `q_eq`, `q_ne`, `q_le`, `q_lt`,
`q_gt`, `q_ge` and `sync_fd_bounds` are not refused: they queue the post
while `trail.hooks_running` is above 0 and post in place at a goal
(ruling R28c, `holzbaur.py`'s docstring,
`test_a_comparison_from_clpfd_inside_a_hook_is_queued` and
`test_a_comparison_from_clpfd_inside_a_hook_is_queued_on_any_store`).
The same post made in place inside the hook gives the wrong answer above:
through `q_le` from Z's hook, Q is left unbound with sup 1, `inf(W)` fails
and `dump/3` raises "renormalize: empty homogeneous part" (Task 14b's
mutation check).  Queueing every post, at a goal too, is the other
mutation: since a750f58c a seam goal still answers right, because the
engine's boundary after an inline comparison runs the queued post before
the next goal (`in_q(X, 0, 100), X =< 10, X >= 3, inf(X, Lo)` gives
Lo = 3).  The callers it breaks are those that post at a goal through the
Python API and read before any boundary: Lo = 0, with the posts left on
the queue, and 114 tests of test_switch.py and test_attribute_hooks.py
fail (among them `test_a_comparison_from_clpfd_at_a_goal_is_posted_in_place`
and every seed of `test_a_post_from_clpfd_at_a_goal_is_never_queued`).

The hooks the engine registers keep the rule (`freeze/2` and `when/2`
queue their goals, and dif, clpfd, clpb, clpr, the two units keys, the
legacy clpq key and COMPONENT_KEY call no entry point), and the tripwire
`test_the_registered_attribute_hooks_are_the_known_set` stays as a second
net: it fails when a hook is registered or removed, and says to check
this rule before extending its list.  It scans the source under
`clausal/` for `register_attr_hook(KEY, ...)` at the start of a line, so
it misses a hook registered from C, from outside `clausal/`, or through a
qualified or aliased call.

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

The precondition of `resume_constraint`: the trail must not have been
undone below the post since the answer was given.  Each choice point holds
the trail mark taken where its `;` was met, after the conjuncts before
it; `resume_constraint` undoes to that mark and runs the other branch.
Undone below the post first, the mark is past the end of the trail, the
undo does nothing, and the other branch runs without the conjuncts before
the `;` (and on a store that may have been changed since).  The adapter
(`holzbaur.clpq_constraint_answers`, behind the `clpq.rational` builtin)
keeps it: a builtin's generator undoes its own bindings between answers,
the engine does not, so when the engine asks for the next answer the
trail is where the previous answer left it, above the post.  After the
last answer the generator undoes to the mark it took before posting.
`{X + Y = 4, (X = 1 ; X = 3)}` answers `X = 1, Y = 3` then `X = 3, Y = 1`,
as Scryer does
(`test_a_block_with_a_disjunction_gives_every_answer`,
`test_a_disjunction_in_a_block_answers_once_per_branch` under the engine,
`test_the_disjunction_answers_are_the_oracle_s`).  The `.pl` front end
and the seam's set goal accept comparisons only, so today a `;` reaches the
adapter only from a goal built at run time.

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

## D20: the legacy API in front of the port (`holzbaur.py`)

`CLAUSAL_CLPQ=holzbaur` puts the port behind legacy's names
(`clausal/logic/clpq/__init__.py`, Task 14).  Where the adapter answers
differently from 1.3.3 itself:

- A variable against a number in an equation (`q_eq(X, N)`, a block's
  `X == N`) is the unification `X = N` with the number as written, as
  legacy's fast path does, so a Decimal keeps its scale: `X == 2.50`
  binds `Decimal('2.50')`.  nf.pl's `{X = N}` would bind the rational
  5/2.  The two are equal numbers; the scale is Clausal's (ruled
  2026-09-17) (`test_a_decimal_keeps_its_scale_through_an_equation`).
- A variable that dump/3 keeps and that is not a target (the slack of a
  disequation) is named `_Q1`, `_Q2`, ... in `dump_q`/`residual_q`, as
  legacy names its internal variables, where 1.3.3 prints a fresh
  variable (`_A`).  Each constraint is written in braces (`{X >= 2}`), as
  the `-g` printer writes it (D14's `wrap/2`).
- `in_q(X)` with no bound makes X a linear variable without bounds
  (bv.pl's `var_intern/2`, which ordering/1 uses), so X carries CLPQ_KEY
  state and clpfd sends its later comparisons on X to CLP(Q).  1.3.3 has no
  `in_q`.
- An FD variable in a CLP(Q) post first gets its FD bounds as `{Lo =< X,
  X =< Hi}` (legacy's promotion, ruling R4), and clpfd's narrowing of a
  variable that has CLPQ_KEY state posts the new bounds
  (`sync_fd_bounds`).  clpfd's C propagation narrows without that call
  (its `c_narrow` syncs CLP(R) only), so with the C extension loaded, as
  it is in every build, a narrowing reaches neither solver's store; the
  Python twin's does (`test_fd_to_q_bare_and_under_a_driver_against_legacy_and_the_oracle`).

- `dump_q(targets, trail, name_of, toplevel=...)`: `toplevel` is accepted
  for legacy's signature and ignored.  `dump_q/2` and `clpq.dump/2` (and
  the `-g` printer through `residual_q`) always give 1.3.3's dump/3 form,
  each constraint oriented as 1.3.3 writes it (`{X >= 2}`).  Legacy's
  `dump_q` without `toplevel` wrote its own normal form and flipped only
  rows whose coefficients were all negative under `toplevel`
  (`{-X =< -2}` vs `{X >= 2}`), so `dump_q/2`'s spelling changes under the
  switch (`test_dump_q_projection.py`, `test_strict_bounds`).
- A post from clpfd is queued iff `trail.hooks_running` is above 0
  (ruling R28c), an O(1) read of the engine's counter (a750f58c).  It
  replaced Task 14's scan of the components a post reads for an unhooked
  binding, which was linear in their size per post under a driver.
  PERF-BASELINE (Task 14b, 2026-10-12, one engine build at a750f58c, the
  two adapters in otherwise identical copies of the package, best of 3,
  two interleaved rounds): a chain of 4,000 variables `{X(i+1) = X(i) +
  1}` posted through `q_eq`, then one bound per variable through `q_ge`,
  bare (`defer` False) and as a driver leaves the trail at a goal (`defer`
  True):

  | | chain posts bare | chain posts driver | bound posts bare | bound posts driver |
  |---|---|---|---|---|
  | scan (rebased Task 14) | 0.20 s, 0.18 s | 1.24 s, 1.13 s | 0.057 s, 0.053 s | 1.97 s, 1.96 s |
  | counter (R28c) | 0.20 s, 0.17 s | 0.17 s, 0.18 s | 0.051 s, 0.052 s | 0.052 s, 0.053 s |

  Under a driver the bound posts are 38x faster and now cost what they
  cost bare; the chain posts about 6.5x.
  The trigger's two mutation checks (D3): posting in place inside a hook
  gives R27's wrong answer.  Queueing at a goal too no longer breaks a
  seam goal, since a750f58c's boundary after an inline comparison runs the
  queued post.  It does break the Python-API callers that post at a goal
  and read before a boundary (`in_q`, `q_le`, `q_ge`, `inf` gives Lo = 0),
  and 114 tests catch it.  The Task 14b brief expected the seam goal
  `in_q(X, 0, 100), X =< 10, X >= 3, inf(X, Lo)` to catch it.  That was
  true before a750f58c and is not now.
- The adapter's entry points other than clpfd's posts refuse to run while
  `trail.hooks_running` is above 0 (ruling R30, D3).  Legacy has no such
  check.  A program whose hook body called `inf/2`, `{}/1`, `dump_q/2`
  and the others got an answer from legacy, and gets
  `permission_error(call, goal, Goal)` from the port.  The cost is one
  attribute read per call.
- A constrained variable bound to an older PlainVar (a variable that
  cannot carry attributes) raises `system_error(plain_variable)` from the
  hook, before any trailed change; 1.3.3's `put_atts` cannot meet such a
  variable, and the port failed in silence before (Task 14 review,
  `test_a_plain_var_cannot_take_the_constraint`).  system_error, not
  type_error: the program's term is a variable, the right type; the limit
  is the engine's variable kind.

- Errors (ruling R19, Task 16 fix round; `tests/clpq_port/test_iso_errors.py`
  asserts each whole term).  A block node that is no comparison raises
  nf.pl clause 13's `type_error(constraint, Node)` from `{}/1`, an unbound
  block clause 1's `instantiation_error` (so `clpq.rational(X)` with X
  unbound); the culprit is the node, as the port's `{}/1` names the goal,
  not `{Node}`.  A block that holds `;` given to `clpq_constraint_block`,
  which answers once, raises `type_error(constraint, Block)` whose prose
  names `clpq_constraint_answers`; legacy refuses the same node.
  `entailed/4` with a relation it does not know raises negate/2's
  `type_error(constraint, Rel)`, with Rel the cell `(Type, L, R)`.
  `bb_inf/3` and `dump_q/2` take a proper list: a variable or a partial
  list is `instantiation_error`, anything else `type_error(list, X)`
  (Scryer's `must_be(list, X)`, clpz_surface's `_proper_list`); legacy
  iterated whatever it was given.  A failing dump/3 under a store that
  holds is `system_error(clpq_dump_failed)` (it was a RuntimeError), and a
  number past 4,300 digits prints through Decimal, as chars.py prints one.
- `in_q/3`'s bounds are engine numbers only: an unbound bound is
  `instantiation_error`, any other term `type_error(rational, X)` (the
  atom `'1/3'` and the string "1" included; legacy and the port before
  Task 16 read them through `Fraction(...)`).  A bound is read as nf.pl
  reads the number in `{Lo =< X}`, so a float is its short convergent
  (`in_q(X, 0.1, 1)` gives inf 1/10; `Fraction(0.1)` before).
- The Decimal-scale fast path above also holds in a block that holds `;`
  (Fable M5): each `X = N` branch is posted through
  `_post_comparison_keeping_scale`, which `post_constraint_with_choices`
  takes as an argument and keeps for `resume_constraint`, so
  `{X = 2.50 ; X = 3.750}` binds `Decimal('2.50')`, then
  `Decimal('3.750')` (it bound 5/2 before;
  `test_a_decimal_keeps_its_scale_in_a_disjunction`).  The fast path takes
  an int, a Fraction or a Decimal `from_number` takes; a Decimal NaN, an
  infinity or one past `DECIMAL_EXPONENT_LIMIT` goes through nf.pl and
  raises (D1).

## D21: inf/4 and sup/4 raised on an unbound Vertex until Task 15 (resolved)

Resolved by Task 15.  bv.pl's `infimum_linear/4` ends with
`assign([Infimum|Vertex], L)`; with Vertex unbound, or a partial list,
`assign/2`'s clause choice binds it to a list as long as Vector.  The port
built `[infimum] + list(vertex)`, so an unbound Vertex raised a Python
`TypeError` (an `AttVar` is not iterable) and a partial list (`[A|T]`, a
`SegList`) gave a wrong answer.  The failure was in the port's own
`bounded_simplex.infimum_linear`, not in shared code: `vertex_value`
reads Vector, which was always a list.  `assign/2` is now ported clause by
clause, with its recursion as a loop: `{Infimum =:= Inf}` is posted first,
then each cell of Vertex is matched (`[X|Xs]`) and posted before the next
is matched, and `[]` is matched at the end.  An unbound tail is bound one
cell at a time (`test_inf_4_and_sup_4_bind_the_vertex_as_the_oracle`, bare
and under a driver, against the local clpq.pl port of 1.3.3 on Scryer:
two ports of the same source agreeing, not an independent check).

The order is observable.  Task 15's first fix unified the whole Vertex
before posting anything, so `inf(X+Y, foo, [X,Y], [])` failed (`[]` does
not match a list of two) where 1.3.3 posts `{foo =:= 3}` first and raises
`type_error(expression, ...)`; `[foo, B, C]` likewise.  The port now
raises there too (`test_inf_4_posts_before_it_matches_the_vertex`).  The
culprit differs from the oracle's: the port raises with `foo`, as nf.pl's
`illarg(type(expression), normal_form(Term, Norm), 1)` names Term; the
local clpq.pl port names `nf(foo, _)`.  The test compares the error kind
and type only, as `test_a_function_in_the_list_raises_a_type_error` does.

Not changed: an unbound VECTOR.  1.3.3's `vertex_value/2` then enumerates
lists of growing length inside a failure-driven loop; on the oracle the
query does not terminate.  The port raises the engine's
`UnboundVarCoercionError` there (`if vector:` on an unbound variable).

## D22: acceptance: filled_rectangle, and the first timing baseline (Task 15)

Not a deviation from 1.3.3; the evidence the port answers as 1.3.3 on a
whole program, and the baseline any later optimisation entry measures
against.

The program is Colmerauer's filled rectangle, the clp(q,r) distribution's
`examples/squares.pl`: `filled_rectangle(A, C)` with C a list of n squares.
No perfect squared rectangle has fewer than 9 squares, so n = 2..8 has no
solution.  `tests/clpq_port/test_acceptance.py` checks, under the port
through the `clausal` CLI with `CLAUSAL_CLPQ=holzbaur`: n = 1 gives the
trivial answer and n = 2..7 give none, in the default suite; with
`CLAUSAL_SLOW_TESTS=1` (ruling R32), n = 8 gives none and n = 9 gives the
same 8 solutions in the same order as the oracle, the first two being the
two `squares.pl` documents (A = 33/32, then A = 69/61).  The oracle is the
LOCAL clpq.pl port of 1.3.3 on Scryer (upstream Scryer has no CLP(Q)):
agreement is two ports of the same source agreeing, not an independent
check; the two documented answers are the only values from neither port.

Legacy is WRONG on this program below n = 9.  Evidence (2026-10-12,
answers counted with findall over the CLI's `-g`; not tested, since they
are wrong):

| n | legacy answers | port answers | oracle answers |
|---|---|---|---|
| 6 | 19 | 0 | 0 |
| 7 | 50 | 0 | 0 |
| 8 | 152 | 0 | 0 |
| 9 | 457 | 8 | 8 |

PERF-BASELINE (2026-10-12, local aarch64, 8 cores, engine a750f58c +
the port at Task 15).  Wall time of every answer of
`C = [C1, ..., Cn], filled_rectangle(A, C)` through the `clausal` CLI
(start-up included, about 0.6 s), and of the same query as
`findall` + `length` on Scryer with the local clpq.pl port:

| n | port | legacy | local clpq.pl port on Scryer |
|---|---|---|---|
| 2..5 | 0.7 s each, 0 answers | | |
| 6 | 0.8 s, 0 answers | 1.7 s, 19 answers, WRONG | |
| 7 | 1.2 s, 0 answers | 7.3 s, 50 answers, WRONG | |
| 8 | 2.9 s, 0 answers | 38.1 s, 152 answers, WRONG | |
| 9 | 10.7 s (first answer 1.6 s), 8 answers | 351.6 s, 457 answers, WRONG | 21.0 s, 8 answers |

The machine is SHARED.  Every port row (n = 2..9) and the Scryer row ran
with load average 0.35 (no other jobs).  The legacy rows ran in the background
while the acceptance test ran, with load up to 5.7, so they are upper
bounds.  Two later interleaved rounds of the port and Scryer at load
5.6 to 6.0 gave the port 27.8 s, 25.7 s (first answer 4.2 s, 3.8 s) and
Scryer 50.6 s, 52.9 s: the same ratio, about 2x.  An earlier
measurement on the same machine during gate runs (the Task 14b ledger)
gave port 42.5 s, legacy 652 s, Scryer 64.2 s.

cProfile of the port's n = 9 run (`python -m cProfile -m clausal -g ...`,
107.3 s under the profiler at load about 5.7), top 15 by own time:

| ncalls | tottime | cumtime | function |
|---|---|---|---|
| 1,244,004 | 11.07 | 39.01 | linear_forms.py add_homogeneous_parts_first_scaled |
| 14,266,938 | 6.66 | 9.45 | arithmetic.py make_rational |
| 1,388,602 | 6.08 | 9.83 | attributes.py with_changes |
| 5,002,721 | 5.35 | 8.20 | variable_ordering.py compare_order_values |
| 4,144,850 | 4.27 | 16.06 | variable_ordering.py compare_variable_order |
| 13,775,827 | 4.24 | 8.19 | attributes.py state_of |
| 13,973,539 | 4.01 | 4.01 | _variables.get_attr (C) |
| 27,374,183 | 3.90 | 3.90 | _variables.deref (C) |
| 2,327,398 | 3.81 | 5.22 | linear_forms.py delete_factor_homogeneous |
| 7,716,414 | 3.56 | 8.65 | arithmetic.py multiply |
| 1,244,004 | 3.37 | 48.01 | linear_forms.py add_linear_forms_first_scaled |
| 6,211,296 | 3.19 | 7.31 | arithmetic.py add |
| 16,730,984 | 2.88 | 2.88 | builtins.getattr |
| 18,953 | 2.82 | 53.74 | bounded_simplex.py back_substitute_variables |
| 14,268,365 | 2.79 | 2.79 | math.gcd |

By cumulative time, 88.07 s of the 107.3 s is in `{}` posts
(`holzbaur.clpq_constraint_answers`, 87.03 s of it through `_post_now`).
`back_substitute_variables` holds 53.74 s, of which 42.86 s is its calls
of `normal_form_substitute` (1,399,194 of that function's 2,274,948 calls,
56.81 s over all callers).  The linear-form merge
`add_linear_forms_first_scaled` (48.01 s) is called only from
`normal_form_substitute`, so it is that merge over all of its callers, not
back substitution's share alone.  Rational arithmetic
(`make_rational` with its `gcd`) and the variable-order comparison of the
merge are the next costs.

The fuzzers (`tests/clpq_port/fuzz/`, the 2026-10-11 reviewer scripts
rewritten for the port, each bare and under a driver): LP against
scipy's HiGHS with each optimum confirmed exactly by z3; satisfiability
with strict, non-strict, equal and not-equal constraints and bindings
against z3; undo against a replay of the base store; projection against
the store with the other variables existentially closed, proved by z3.
Each was checked to fail on a mutant (q_lt as q_le, sup as inf, no undo,
a dropped residual constraint, every post failing, `put_attr` on a trail
that is never undone).  A store the port rejects is checked against z3,
and the undo and projection fuzzers require more than half their cases to
reach the undo or the projection.

## D23: a cyclic term raises type_error(evaluable, F/A)

1.3.3's `nf/2` recurses on the term, so on a cyclic term (`X = 1 + X`) it
recurses for ever; the local clpq.pl port on Scryer does not answer
`X = 1+X, {Y >= X}`, `X = 1+X, bb_inf([X], 0, I)`, `X = 1+X, inf(X, I)` or
`{Y*Y >= Z}, Z = 1+Z` within 10 s (checked 2026-10-12).  The port's
`normal_form` walks the term with an explicit stack, so it looped with
growing memory instead (security review High 2): `c3(I) :- X = 1 + X,
bb_inf([X], 0, I)` and `c9(Y) :- {Y*Y >= Z}, Z = 1 + Z` (the second through
the delayed goal Z's binding wakes).

`normal_form` now keeps the set of compounds on the path from the root to
the term it reads (each compound's `_LEAVE` work item takes it off), and a
compound met again while on the path raises
`error(type_error(evaluable, F/A), normal_form/2)`, F/A the functor of
that compound.  The check is per path, so a shared subterm (`S = X + X`,
`{Y = S + S}`) is no cycle (`test_a_shared_subterm_is_not_a_cycle`).

Why this error.  ISO terms are finite, so the standard has no case for a
cyclic one; Scryer's `is/2` on `X = 1+X, Y is X` raises
`type_error(evaluable, (+)/2)` and on `X = f(X)` `type_error(evaluable,
f/1)` (checked 2026-10-12).  nf.pl's own refusal of a non-expression is
`type_error(expression, nf(Term, Norm))`, but its culprit would be the
cyclic term itself, which no printer can write; Scryer's form names a
finite culprit.  The context is `normal_form/2`, as the port's
`type_error(expression, ...)` names it.

The adapter (`holzbaur.py`) runs the same check (`refuse_cyclic_term`, one
walk that does not revisit a compound it has left) on each expression
before clpfd's cell walk, which recursed on a cyclic term and raised
`RecursionError` (`c1(Y) :- X = 1 + X, {Y >= X}`), so `q_*`, `{}/1`,
`inf/2`, `sup/2`, `maximize/2`, `minimize/2`, `bb_inf/3` and `entailed/1`
raise the same term.  Tests (bare and as a driver leaves the trail):
`test_normal_form_of_a_cyclic_term_raises`,
`test_bb_inf_of_a_cyclic_term_raises`,
`test_a_cyclic_binding_of_a_delayed_variable_raises`,
`test_the_adapter_refuses_a_cyclic_term`; through the engine,
`test_switch_engine.py`'s `test_a_cyclic_term_raises_through_the_engine`.

Not covered: the `inf/2` and `sup/2` builtins ask CLP(R) first
(`clpr.is_real_expression`), whose cell walk recurses before CLP(Q) is
reached, so `X = 1 + X, inf(X, I)` through the engine still raises
`RecursionError`, under both switches (shared code; D24, deep terms).

## D24: known limits, deferred by ruling R34; the first three capped (rulings D42, D51)

The security review of Task 16 measured these; ruling R34 defers them, the
first three to the operator as one question (resource limits beyond
1.3.3) and the last two as follow-ups, all before the default flip.
Ruling D42 asks for a cap on each of the first three before any flip, and
ruling D51 says what a cap does: past it the port raises
`error(resource_error(R), _)`, as Scryer shapes it (the context is a
variable, the explanation goes to the exception's message).  It never
fails in place of an answer and never answers in part, and the defaults
refuse no query 1.3.3 answers in reasonable time.  1.3.3 has no such
caps, so these are deviations; the port answers as 1.3.3 does below them.

| Resource R | Flag | What one call counts | Default |
|---|---|---|---|
| `clpq_nodes` | `clpq_max_nodes` | the nodes of one bb_inf search (passes of `branch_and_bound_loop`) | 20,000 |
| `clpq_work` | `clpq_max_work` | the work of one bb_inf search: a unit for each row its pivots' back substitution reads, and for each row it writes a unit per term and per 64 bits of a coefficient (`bounded_simplex.row_size`) | 2,000,000 |
| `clpq_projection` | `clpq_max_projection` | the same work for one projection, plus each row Fourier-Motzkin derives, charged before it is made as wide as the widest row it comes from | 4,000,000 |
| `clpq_expansion` | `clpq_max_expansion` | the terms one normal form (or repair) makes in powers, `binomial(N + T - 1, T - 1)` for a sum of T terms to the N or -N, and in products of sums, `len(A) * len(B)` each, counted before each is built | 20,000 |
| `clpq_expansion` | `clpq_max_expansion_bits` | the bits those terms' coefficients take, estimated before each is built: `terms * N * (bits of the base's largest coefficient + bits of T)` for a power, `terms * (largest of A + largest of B)` for a product | 200,000,000 |

**Where they live.** `clausal/logic/clpq/limits.py` holds the caps
(`limit`, `set_limit`) and the meters.  Each count belongs to one call: a
`Meter` on a context variable, so two threads or two asyncio tasks never
share a count (review F5: a process global made 70 of 80 threaded
projections raise for each other's work).  A metered call inside another,
a projection under a search or a bb_inf woken in a search, is charged to
its own meter and to every meter around it, so the outer cap bounds the
whole.  The caps bound one call; a program that calls again in a loop is
the host's to bound (docs/sandbox.md: time and memory limits).

**Configuration.** A program reads and sets the caps with
`current_prolog_flag/2` and `set_prolog_flag/2`; each flag is process wide
and takes a positive integer (anything else is
`domain_error(flag_value, F+V)`).  The flags exist only under
`CLAUSAL_CLPQ=holzbaur`, so the legacy switch's flag set is unchanged
(`test_the_legacy_switch_has_no_cap_flags`).  The engine's flag mechanism
(`clausal/logic/builtins/flags.py`) was chosen over an environment
variable because it is what ISO gives a program for implementation-defined
limits.  In the sandbox the caps are the host's: a program sets them
neither with the goal (refused before) nor with a load-time directive of
any front end (`flags.sandbox_refusal`, checked where the setting is
validated and again where it is written; only the module-scoped
`assert_creates_dynamic` and `double_quotes` are allowed,
`SANDBOX_DIRECTIVE_FLAGS`).  The host calls `limits.set_limit`.

**Why work, not nodes or rows alone.** The work of a node grows with the
store: under the node cap alone, the store with no integer point plus 20,
60 and 200 variables tied to X and Y took 79 s (490 MB), 163 s (1.4 GB) and
an estimated 46 min (review F2).  Most of it is the back substitution's
walk over every row of the component, most of which do not hold the
variable, so a row read counts as well as a row written; and a row with
big coefficients costs as much as a long one (the D24 probe with
coefficients up to 10^9 ran 51 s to a cap counting terms alone), so a
written row counts its coefficients' size too.  Measured at a load
average of 4 to 5 on 8 cores, the work runs at 270,000 to 750,000 units a
second across the wide searches, the D24 projections and the big
coefficients, so time tracks the count within about three times; derived
constraints alone did not (176 took over 20 s, 316 took 9 s).  Posting a
wide store is not metered: the program pays for the store it builds
(review F7: n = 50, 150 rows took 29 s to post, then its projection
raised 9 s later).

**Why bits as well as terms.** `(10^1000*Y + 1)^2000` has 2,001 terms but
took 46 s and 1.7 GB (review F4): the coefficients are the cost.

**Headroom.** Measured 2026-10-14 by recording the most each cap saw,
with every cap lifted, over tests/clpq_port (CLAUSAL_SLOW_TESTS=1: the
examples, filled_rectangle n = 9, the fuzz tests and the nested legacy
suites under the port) and every other test file that names clpq, bb_inf
or dump_q, all under `CLAUSAL_CLPQ=holzbaur`:

| Cap | Most used | Default | Headroom |
|---|---|---|---|
| nodes | 1,167 | 20,000 | 17 times |
| work | 72,216 | 2,000,000 | 27 times |
| projection | 45,055 | 4,000,000 | 89 times |
| expansion terms | 27 | 20,000 | 740 times |
| expansion bits | 126 | 200,000,000 | 1.6 million times |

The projection default is set by the D24 probe, not by the tests: over
seeds 100 to 119 at n = 5 the most work was 2,011,385 (seed 101, 5 to
8 s), so every one of them answers with 2 times to spare, and seed 101 at
n = 6 (212 s to answer uncapped) raises after 12 to 15 s.  The work
default raises the wide searches (20 to 400 more variables) after 6 to
7 s.  The expansion terms default admits a product of 13 sums (16,380
terms) and refuses 14 (32,764); the bits default admits `(Y + 1)^7000`
(3 s) and `(10^1000*Y + 1)^240` (0.5 s to expand; printing its 241
coefficients of 240,000 digits is slow, as printing any such integer is).

- **bb_inf/3 on a store with no integer point does not terminate in 1.3.3**
  (High 1).  `noint(I) :- {X >= 0, Y >= 0, 2*X - 2*Y =:= 1},
  bb_inf([X, Y], X, I).`  bb.pl branches for ever; memory grows by about
  30 MB/s.  Legacy caps its depth at 50 and fails.  The port raises
  `resource_error(clpq_nodes)` at the node cap, and on a wide store
  `resource_error(clpq_work)` first
  (`test_bb_inf_without_an_integer_point_raises_at_the_default_cap`,
  `test_a_wide_search_raises_clpq_work_at_the_default_cap`).
- **Projection is exponential** (Medium 3).  dump/3 on two of n variables
  under 3n random `=<` constraints (coefficients in -3..3, bounds in
  1..9), the security review's probe `secport/proj.py SEED N COUNT` (Task
  16 scratchpad): worst over the seeds tried, 0.70 s at n = 4 and 13.50 s
  at n = 5; the 13.5 s case is seed 101 (15 constraints, a 13-constraint
  answer), which ANSWERS at the default cap; n = 6 runs past two minutes
  and raises `resource_error(clpq_projection)`.  The `-g` printer
  projects every answer, so a sandboxed program reaches it: past the cap
  the printer reports the error and prints no answer
  (`test_the_answer_printer_reports_the_projection_cap`).
  Fourier-Motzkin in 1.3.3 is the same, uncapped.
- **Expansions are polynomial in the exponent and exponential in the
  factors** (Medium 4, review F3 and F4).  `{X = (Y + 1)^N}` takes 0.04 s,
  0.12 s and 0.45 s at N = 1000, 2000 and 4000, `(Y + Z + W)^240` 7.1 s,
  and `(Y + 1)^(10^7)` did not finish; a product of 18 sums ran past 120 s
  and 1 GB.  Each now raises `resource_error(clpq_expansion)` before it
  expands.  Every front end reaches them: `.pl` and `.clausal` refuse a
  literal non-linear `{}` at load, but a term bound at run time is posted
  (`power(N, X, Y) :- E = (Y + 1)^N, {X = E}.`,
  `test_catch_takes_the_errors_in_a_program`), and a seam `{...}` accepts
  a product literal.  nf.pl expands as the port does.  A power of a
  constant (`7^N`) is ordinary arithmetic, uncapped here as in `is/2`.
- **Unifying constrained variables with constrained variables is slower
  than legacy** (Low 8).  `X1 =< X2 =< ... =< Xn`, each `Yi >= 0`, then
  `[X1, ..., Xn] = [Y1, ..., Yn]` (`secport/hookscale.py N`, mode
  `varvar`; legacy `secport/hookscale_leg.py N`): n = 100 takes 1.17 s on
  the port against 0.15 s on legacy, n = 200 12.25 s against 0.77 s.  A
  measured regression against legacy.  The other shape is not: unifying
  the chain with numbers, `[X1, ..., Xn] = [0, ..., n-1]` (mode `list`),
  is FASTER on the port, n = 200 1.16 s against legacy 10.09 s.
- **Deep terms raise RecursionError in shared clpfd code** (Medium 7):
  a sum nested 100,000 deep (`lsum(N, X, T) :- ..., lsum(N1, X + 1, T)`,
  then `{Y >= T}`) raises `RecursionError` from clpfd's cell walk before
  the port is reached.  Legacy the same.  The cyclic case of the same walk
  under `inf/2`/`sup/2` is in D23.
