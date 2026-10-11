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

`minq`, `maxq` and the float-valued functions (`expq`, `sinq`, ...) are not
in this module.  `Fraction` is used only in `from_number` (to accept one) and `to_number`, the
conversion edges; the solver core never sees it.

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

Sites in `itf3.pl`: to be filled in by Task 11.

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

Component variables are ordered the same way.  bv.pl `select_dependent/7`
collects the components of a new equation's old variables with
`ord_add_element/3`, an ordered set in the standard order of the component
variables; the port orders them by `Var._id`
(`test_select_dependent_orders_components_by_creation`).  The first of them
is the one `equate/2` unifies the others with, so with D8 this order decides
which component variable is bound and so the order of the merged member
list.  The check is again Task 12's oracle tests.

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
  `nf.pl` delays (`resubmit_*`, `wait_linear_retry`) are Task 10's to port
  in that shape; Task 10 confirms each is deterministic in 1.3.3.
- Translation.  `geler/2` is a meta-predicate (`geler.pl`, `compenv.pl`
  `nfq:geler(?,:)`), so 1.3.3 stores `nfq:G`, and `translate_goal//1`'s
  `M:G` clause calls nfq.pl's exported `translate_goal//1` (the `transg` of
  the original).  That turns `resubmit_*(Nf)` into `clpq:{Term Rel 0}` and
  `wait_linear_retry(Nf, Res, Goal)` into `[clpq:{Term = Res}, Goal]`, the
  shape dump.pl's `nonlinear_strip/3` reads.  The port's `translate`,
  `collect_nonlinear` and `project_nonlinear` take that nfq.pl predicate as
  the parameter `translate_goal(procedure, argument) -> list of goal terms`
  (`test_translate_hands_each_goal_to_translate_goal_in_order`).
  **Not done yet:** nfq.pl's `translate_goal//1` itself (Task 10, with
  `normal_form_to_term/2`), and the `clpq:` module tag its output carries,
  which `nonlinear_strip/3` tests (Task 10 and Task 12 agree the term
  shape).  The conjunction clause of `translate_goal//1` has nothing to do,
  because a port goal is never a conjunction.
- `project_nonlinear/3`'s reachable variables are the variables of the
  TRANSLATED goals, as in 1.3.3 (`term_variables_set/2` on them), so they
  include `wait_linear_retry`'s `Res` and every variable of its `Goal` once
  Task 10's translate_goal emits them
  (`test_project_nonlinear_reaches_what_translate_goal_emits`).  The walk
  covers tuples, lists and `__slots__` records; Task 10's argument records
  must be one of those.
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
  are the check.
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

