# The raise-time error copy drops attributes, the same gap as throw/1

Found 2026-10-15 (fix/iso-error-culprit-copy-2026-10-15, re-review round).

`exceptions._copy_at_raise_time` calls `_copy_term(walked, {})` with no
`attvars` list. Any attributed variable in an ISO error's culprit *or*
context comes back plain. `globals_env._throw_ball` (`_findall_copy_row`)
has the identical gap for `throw/1` balls. Both raise paths now behave
the same as each other, but neither matches Scryer, which keeps
attributes on a copied/thrown term.

Repros (Scryer / Clausal head):

```prolog
dif(Y,a), catch(atom_length(f(Y),_), error(type_error(_,C),_), true),
C = f(Z), Z = a.
% refused / succeeds

X #> 3, catch(atom_length(f(X),_), error(type_error(_,C),_), true),
C = f(Z), Z = 1.
% refused / succeeds

dif(Y,a), catch(throw(f(Y)), f(Z), true), Z = a.
% refused / succeeds (throw/1, pre-existing, not new with this fix)
```

freeze is already consistent: `dif(Y,a)` aside, a frozen var that wakes
on neither engine (Scryer notwoke, head notwoke) already matches, so
freeze is not itself a new gap here.

bb_inf's context (`clausal/logic/clpq/branch_and_bound.py:281`): the
raise-time copy detaches the context var from the live clpq store, so
the copy loses its `clpq_holzbaur` attribute entirely (pinned in
`tests/clpq_port/test_branch_and_bound.py::test_a_term_that_is_not_a_variable_raises_an_instantiation_error`,
which only asserts the copy is a fresh unbound var, not that it carries
the constraint).

**dif is the cheap part**, not representative of the whole gap:
`copy_term/2` already copies dif via `_ATTRIBUTE_COPIERS` +
`_copy_attributes(attvars, var_map, trail)`
(`clausal/logic/builtins/inspection.py:636-669`). freeze, clpz, clpq and
units are blocked on the same design questions as
[[copy-term-attributes-freeze-clpz-and-copy-term-3-2026-09-30]].

**Design question specific to this path:** `_copy_attributes` needs a
*trail* to install the copied attributes on, and neither
`_copy_at_raise_time` nor `_throw_ball` has one available at raise time
(the raise is typically mid-unwind, trail state uncertain). On which
trail should attribute copies go so they survive the unwind to the
`catch/3` handler? `_throw_ball` faces the identical question, so a fix
should cover both constructors together, not just the ISO-error one.

**Fix shape:** pass an `attvars` list (and the trail once the design
question above is settled) through to `_copy_term` from both
`_copy_at_raise_time` and `_throw_ball`, and install the copyable
attributes (dif today; freeze/clpz/clpq/units once 2026-09-30's design
questions are ruled on). Add the repros above as Scryer-oracle rows to
whichever test file picks this up.
