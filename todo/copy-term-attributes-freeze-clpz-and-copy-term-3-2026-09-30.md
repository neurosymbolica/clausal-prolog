# copy_term/2 does not copy freeze/2 or CLP attributes; copy_term/3 absent

Found 2026-09-30 (fix/term-walkers-partial-lists-2026-09-30, which made
copy_term/2 copy **dif/2** through `_ATTRIBUTE_COPIERS` in
`clausal/logic/builtins/inspection.py`).

Scryer copies every attribute in copy_term/2.  Clausal still drops these,
silently (each row: Scryer / Clausal):

```prolog
freeze(V, fail), copy_term(V, W), W = 1.          % fails / succeeds
freeze(V, fail), copy_term(f(V), f(W)), W = 1.    % fails / succeeds
X #> 3, copy_term(X, Y), Y = 1.                   % fails / succeeds
X in 1..3, copy_term(X, Y), Y = 7.                % fails / succeeds
dif(A, a), copy_term(A, B, Gs).                   % Gs = [dif:dif(B,a)] / existence_error
```

Why not done: the `freeze` attribute is a list of compiled Python goal
closures (`control_constructs.py` freeze lowering) that capture the
ORIGINAL clause variables -- there is no goal term to rename apart.  The
`fd`/`clpb`/`clpq`/`real`/`units` attributes are propagator networks.
Copying the value as-is would be worse than dropping it (the copy's
wakeup would bind the original's variables).

Design questions (need a ruling):
1. freeze/2: store the goal TERM alongside the thunk so a copier can
   re-post `freeze(V', Goal')`?  Or raise on copy_term of a frozen var?
2. clpz: re-post via attribute_goals-style residual goals (needs a
   residual-goal projection per CLP library -- the same thing copy_term/3
   needs), or refuse loudly?
3. copy_term/3 (Scryer: attribute goals of the copy as a list; the copy
   itself attribute-free): build it on the per-key residual-goal hook from 2.
4. User put_attr/3 attributes (term-valued) could be copied generically,
   as Scryer's put_atts values are; today they are dropped.
