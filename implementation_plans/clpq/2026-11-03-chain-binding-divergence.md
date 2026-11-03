# CLP(Q) port: why binding a solved chain is cubic (2026-11-03)

Follow-up to finding R2 of `2026-11-03-port-complexity-survey.md`.
Investigation only: no solver code was changed. The tools are in
`benchmarks/clpq_chain_binding_trace/` and the facts are pinned by
`tests/clpq_port/test_chain_binding_order.py`.

## The question

After posting `X1 =< X2 =< ... =< Xn`, binding the list to `[0, ..., n-1]`
in one unification costs the port n^3.0 (7.9 s at n = 800) and Scryer's copy
of the 1.3.3 text n^1.96 (by inferences). Bound one at a time, first to
last, the survey saw the port rewrite n^2/2 rows and stay cubic while Scryer
stayed quadratic. The hypothesis was that bv.pl's `select_dependent`
(`sd/7`) / `preference/3` picks a different variable in the port, because of
the order of variables (D4/D11) or because of D3 (the hook runs after the
binding).

## Answer in short

- **The hypothesis is wrong in its detail.** `select_dependent` and
  `preference/3` read the same input in both systems and choose the same
  variable. Rows hold their terms in the same order, the component's member
  list is in the same order, and every back substitution rewrites the same
  rows. With one binding per unification the two decision traces are
  identical, first to last and last to first, at n = 6 and n = 10.
- **One unification (the survey's `bind_numbers`): the first divergence is
  the order in which the bound variables' work is done.** Scryer, and
  SICStus by its documented semantics, run `verify_attributes/3` for X1, X2,
  ..., Xn in the order of the bindings. Each one runs while the later ones
  are still unbound. The port does all of the work inside the first hook
  (X1's), in `attribute_hooks._stand_in_for_bound_members`, and there it
  takes the other bound members in the order of the component's member
  list. That list is newest first, so the order is X1, Xn, Xn-1, ..., X2.
  With that order 1.3.3's own algorithm is cubic: Scryer's copy, given
  the port's order (X1, then Xn down to X2, one at a time), takes 3.5M,
  25.3M and 191.6M inferences at n = 100, 200 and 400 (n^2.9). In its own
  order it takes 0.58M, 2.19M and 8.55M (n^1.96).
- **One at a time, first to last: the decisions are the same and the
  remaining cubic cost is the port's own per-row work.** 1.3.3 rewrites each
  of the n^2/2 rows in O(1): the variable is the row's first term, so
  `delete_factor_hom/4` stops there and shares the tail, and
  `add_linear_f1h([], _, Ys, Ys)` shares it again. The port copies each row
  (`linear_forms.delete_factor_homogeneous` slices a Python list). Its D3
  stand-in pass also checks every row of the component on each binding
  (`attribute_hooks._rename_in_component` → `_rename_in_form`'s
  `isdisjoint`). Both of these run in C, so the constant is small, but the
  exponent is 3.
- **Classification: (b), a consequence of the recorded deviation D3,** in
  a choice that D3 does not record: the order of the stand-ins' work. It is
  not a porting defect in any 1.3.3 rule. It is not Scryer-specific either:
  Scryer's order is SICStus's order, as far as the SICStus manual describes
  it (inference, see below).

## The traces (n = 6)

Naming: `Sk` is the slack of `Xk =< X(k+1)`, the variable that X(k+1)'s row
holds and Xk's does not. In both systems the store after posting is the
same:

```
members: S5 X6 S4 X5 S3 X4 S2 X3 X1 X2 S1        (both systems, this order)
X6 = X1 + S1 + S2 + S3 + S4 + S5                  every Sk is t_l(0) (lower bound 0),
X5 = X1 + S1 + S2 + S3 + S4                       every Xk is t_none,
...                                               X1 and the Sk are independent
X2 = X1 + S1
```

### One variable at a time, first to last: identical

```
Scryer                                         port
verify_lin x1 = 0 (indep)                      verify X1 = 0
  solve_for_variable x1                          solve_for_variable X1
  bs_collect x1: rewrote x6 x5 x4 x3 x2          bs_collect X1: rewrote X6 X5 X4 X3 X2
verify_lin x2 = 1 (dep)                        verify X2 = 1
  solve 4 s1   (terms [1*s1])                    solve 4 S1
  bs_collect s1 := 1: rewrote x6 x5 x4 x3 s1     bs_collect S1 := 1: rewrote X6 X5 X4 X3 S1
verify_lin s1 = 1 (dep)                        verify S1 = 1
...                                            ...
verify_lin x6 = 5 (dep)                        verify X6 = 5
  solve 4 s5                                     solve 4 S5
  bs_collect s5 := 1: rewrote s5                 bs_collect S5 := 1: rewrote S5
```

Rows read: 10, 9, 7, 5, 3, 1 in both. Rows rewritten: 20 in both, n(n-1)/2
+ n - 1 in general. Last to first is identical as well: X6 = 5 selects X1
(category 2), and then S5, S4, ..., S1 (category 4). Both systems are cubic
in that order, because X1's definition puts every slack into every row.

### One unification `L = [0, ..., 5]`: diverges at the second variable

```
Scryer                                          port
verify_lin x1 = 0 (indep)                       verify X1 = 0
  solve_for_variable x1                           solve_for_variable X1
  bs_collect x1: rewrote x6 x5 x4 x3 x2           bs_collect X1: rewrote X6 X5 X4 X3 X2
verify_lin x2 = 1 (dep)                    <>   verify X6 = 5
  solve 4 s1   (terms [1*s1])                     solve 4 S5   (terms S1..S5, ties -> last)
  bs_collect s1 := 1: rewrote x6 x5 x4 x3 s1      bs_collect S5 := 5 - S1 - S2 - S3 - S4: rewrote S5
verify_lin s1 = 1 (dep)                         verify X5 = 4
verify_lin x3 = 2 (dep)                           solve 4 S4
  solve 4 s2                                      bs_collect S4 := 4 - S1 - S2 - S3: rewrote S5 S4
  ...                                           ... X4, X3, X2; then the queued S5..S1 = 1
```

`compare_traces.py` reports the first divergence at event 3, `verify x2=1`
against `verify x6=5`, at n = 6 and at n = 10. In the port's order, each
Xj = j-1 is a row `S1 + ... + S(j-1) = j-1` whose terms are all category 4.
`preference/3` takes the later term on a tie, so it picks S(j-1), whose
definition has j-2 terms. `bs/3` then reads every remaining member row and
scans the X rows, which do not hold S(j-1), to their end. That is O(j^2)
work for each j, and O(n^3) in all: the same cost as 1.3.3 bound last to
first.

## Which rule decides, and what it reads

- **No bv.pl rule makes the choice.** `sd/7` (clpq.pl:3291-3310) and
  `preference/3` (clpq.pl:3315-3324) read the row's terms in their stored
  order (D4 creation order in the port, Scryer's standard order of
  variables in Scryer). The two orders give the same row here, and the
  choice inside each binding is the same.
- **The input that differs is the sequence of bindings that `verify_lin/2`
  (clpq.pl:1142-1162) is called with.**
  - In Scryer this sequence comes from the engine. `'$atts':driver/2`
    (`src/machine/attributed_variables.pl`, `iterate/3`, lines 8-13) first
    undoes every binding of the unification. Then, for each variable in
    binding order, it calls `verify_attributes/3` (clpq.pl:91, which goes
    through `verify_itf/3` at :1057 to `verify_lin/2`) and redoes that one
    binding. The goals run at the end. `export_binding/1` (clpq.pl:2735)
    binds the implied slack inside X2's call at once, so its own
    `verify_attributes/3` nests there (`verify_lin s1 = 1`).
  - In the port the engine calls the CLPQ hooks in binding order too
    (`_variables.c` `fire_wakeups_dispatch`). But X1's hook already finds
    X2..Xn bound. To keep rows free of bound variables (D3, "Several
    variables bound in one unification"), `_stand_in_for_bound_members`
    (attribute_hooks.py:266) collects every bound member by walking
    `component_all_variables(component)` (line 289). It puts X first
    (line 297) and appends the rest in member-list order (line 299).
    `_verify_stand_ins` then does their work in that order. The member
    list is class.pl's, newest first, and it is identical in both systems
    (above). The later hooks find their variable gone from the component
    and return. The implied bindings go to `bind_queued` after all of the
    stand-ins, not nested in each one, so the slack rows stay members a
    little longer. This changes rows read (45 against 35 at n = 6), not
    any decision.
- So the order comes from D3's construct, not from D4 or D11, and not
  from the before/after timing of the hook as such. The 1.3.3 text has no
  loop over the bound variables. The loop and its order are the port's.

## Classification and options

**(b), a consequence of D3.** D3 records that the first hook does every
bound member's work. It does not record the order of that work, and the
order is observable in principle: which variable each solve selects, and so
the basis, which can show in a residual when some variables stay unbound.

Experiment (scratch copy of the tree, reverted; never in the worktree):
sort the stand-ins after X by `Var._id`. This is creation order, which
equals binding order for this shape but not in general. Results:

- The n = 10 trace then matches Scryer's decision for decision. The only
  difference is where the queued `S = 1` verifies come (they come after
  all of the stand-ins instead of nested), and that is harmless.
- `tests/clpq_port/test_attribute_hooks.py`,
  `test_unify_constrained_variables.py`, `test_against_oracle.py` and
  `test_rename_preserves_answers.py` gave 326 passed, 6 skipped, the same
  as the unpatched tree.
- The differential identity gate (`CLPQ_DIFFERENTIAL=full`): 5 passed,
  byte-identical, the same as the unpatched tree (both runs took 450 s).
  But this says little. Every `["bind", i, v]` step in
  `tests/clpq_port/differential/_workloads.py` binds one variable per
  unification, so the corpus never reaches the order in question. A gate
  for option 1 needs workloads that bind several members of one component
  in one unification, with some variables left unbound and dumped.
- Time with the GC off: 0.16, 0.74 and 3.9 s at n = 200, 400 and 800,
  against 0.18, 1.06 and 7.3 s. With the GC on: 0.23, 1.19 and 14.8 s,
  against 0.20, 1.20 and 8.7 s (one run each, load about 18).
  - The Scryer order rewrites n^2/2 rows instead of about 2n. Each rewrite
    is a new Python list, so the cyclic GC's full collections, which walk
    the n^2/2 live term tuples, now dominate.
  - The port's per-row costs below then set the exponent. The order alone
    does not make the port quadratic.

Options:

1. **Do the stand-ins' work in binding order** (not implementation-only).
   - Best form: each hook keeps doing only its own variable's work, on a
     stand-in that the first hook made for every bound member. This is
     what `verify_attributes/3` sees in Scryer and SICStus: the later
     variables unbound and constrained.
   - It needs a way to find a member's stand-in from its later hook (a
     record kept from the first hook), or the engine's binding order exposed
     to the first hook.
   - It changes which variable is selected whenever two or more
     constrained variables of one component are bound in one unification.
     So it can change the basis and the residual text of the variables
     left unbound. The gate result above and Task 12's oracle cases are
     the check. It would follow 1.3.3 more closely than now, and it needs
     a ruling and a DEVIATIONS.md entry (D3 amended).
2. **Keep the order and record it** in D3: "the bound members' work is done
   in member-list order, newest first; 1.3.3 does it in binding order".
   Cost: binding a chain in one unification stays cubic in 1.3.3's own
   work units (a shape whose binding order is newest first would favour
   the port instead).
3. **Implementation-only costs, independent of 1 and 2**, seen in the
   one-at-a-time profile at n = 800 with the GC off (about 14 s profiled):
   - `_rename_in_component` scans every row on every binding: 6.5 s
     cumulative, 3.9 s of it `isdisjoint`, n^2 calls of O(n). A bound
     *dependent* member occurs in no other row of a solved form, so only
     its own row and the member list and basis need renaming. This needs
     a proof that covers D3's "A stand-in left in a row" case, and a check
     mode that cross-checks against the full scan.
   - `delete_factor_homogeneous` copies the row (1.7 s, a C slice).
     1.3.3 shares the tail. Python lists cannot do that without a change
     of representation, so leave it.
   - The cyclic GC over the many long-lived term tuples (see the
     experiment). `gc.freeze()` after posting, or fewer tracked objects,
     would be implementation only.
   - `components.delete_first` (class.pl's, O(n) per drop) is quadratic as
     in 1.3.3 and is not a cause.

## What SICStus would do (inference)

The SICStus manual describes `verify_attributes/3` this way. When one
unification binds several attributed variables, all of the bindings are
first undone. Then, for each variable in turn, the hook is called and that
binding is redone, and the returned goals are called afterwards. Scryer's
`driver/2` implements exactly this, so SICStus would process X1..Xn in
binding order, as Scryer does. That `L = Ns` binds the elements left to
right is also inferred (the usual head-then-tail unification of lists). It
was not checked on SICStus, which is not available here.

## Measured and inferred

- **Measured:** both traces at n = 6 and 10, in all three orders (forward,
  backward, one unification). Scryer's inference counts in the three
  orders. The port's timings and profiles. The scratch-patch trace, its
  test runs and its gate run.
- **Inferred:** SICStus's order. That option 1 changes no answers beyond
  the gate's corpus. The proof needed for option 3's renaming shortcut.

## Reproduce

```
sh benchmarks/clpq_chain_binding_trace/run.sh /tmp/out 10 all       # first divergence
sh benchmarks/clpq_chain_binding_trace/run.sh /tmp/out 10 forward   # identical
```

(`PYTHON=` selects the interpreter with the engine built. `CLAUSAL_SCRYER=`
and `SCRYER_CLPQ_PL=` select the Scryer binary and the clpq.pl to
instrument. The instrumented copy is written to the output directory.)

## Resolution (2026-11-03)

The owner ruled for option 1 ("Follow 1.3.3"): the bound variables of one
unification are processed in binding order.

- **Harness first.** The identity harness gained three families that bind
  several variables of one store in one unification (`chain_bind`,
  `dense_bind`, `implied_bind`, 414 workloads, `["unify", ...]` steps), and
  the exact Scryer comparison gained 40 (default) and 300 (full)
  multi-binding queries with a baseline of every difference
  (`_MULTIBIND_BASELINE` in `test_differential_scryer.py`).
- **Option 3, implementation only.** The stand-in pass reads no row when
  every bound member is dependent (a dependent variable is in no other row
  of a solved form; `CLAUSAL_CLPQ_CHECK_ROW_INDEX=1` cross-checks).
  Byte-identical goldens. The row copies of `delete_factor_homogeneous`
  and the cyclic GC were left (below).
- **Option 1, the order.** The first hook still makes every stand-in, but
  does only its own variable's work; each later member's own hook takes
  its stand-in and does its work, each followed by the bindings it implies
  (`attribute_hooks._TURNS`, `_take_turn`, `_verify_turn`; D3 amended).
  An implied binding of a later member's stand-in is checked against that
  member's own binding at its turn.
- **Traces.** `run.sh` at n = 6 and 10, `all`, `forward` and `backward`:
  identical to Scryer's, event for event (23 and 39 events). The queued
  implied verifies now come nested in each turn, as in Scryer.
- **Changed records.** The 963 single-binding workloads: byte-identical.
  Of the 414 multi-binding ones, 266 changed their trace and 1 its
  observation: `dense_bind-6-11`, step 27, `dump([X3, X5])` after
  `f(X2, X0, X5) = f(4, 6, 0)` under a mark. The new residual is exactly
  Scryer's (`_I1+1/5*_I2>182/185, X3=64/15+1/3*_I1+1/15*_I2, ...`); the
  old one was equivalent in another basis. The 265 trace-only changes
  keep their answers, so their agreement with Scryer is unchanged.
- **Scryer, multi-binding queries.** Before: 46 differences (44 where
  Scryer fails the one unification and answers the same bindings made one
  at a time, 2 text). After: 45. `scryer-multibind-40-98` now agrees; no
  query that agreed differs. The remaining text difference,
  `scryer-multibind-40-215`, is not about bindings: the posts alone dump
  in another order (`{X1 = X0 + 2}, {X1 =< X2}, {X0 >= -2}`: the port
  `X1>=0, X0=-2+X1`, Scryer `X0=-2+X1, X1>=0`). Open, not investigated.
- **Cost.** `bind_numbers` now rewrites the same rows as Scryer:
  n(n-1)/2 + n - 1 (5,049, 20,099, 80,199 at n = 100, 200, 400), and
  reads n^2. 1.3.3's work is quadratic. The port's time is not:
  0.039, 0.167, 0.90, 10.0 s at n = 100..800 (slope 2.65, top 3.5),
  against 0.032, 0.118, 0.58, 2.68 s in the old order, which rewrote
  about 2n rows. With the GC off: 0.039, 0.151, 0.68, 3.7, 37 s at
  100..1600 (slopes 2.0, 2.2, 2.5, 3.3). What is left per rewritten row is
  the port's: the cyclic GC walking the n^2/2 long-lived term tuples, and
  the row copy of `delete_factor_homogeneous`, where 1.3.3 shares the tail.
  Both need a change of representation or of GC policy, not of algorithm.
