# fix-A01: Compound Var-functor broken across the layer (A01-F003)

**Severity: correctness. BLOCKED on parked design decision A01-D004**
(`investigate-A01-parked-design-decisions.md` §3) — the user must choose
between full support / deref-only / reject-at-construction. The deref-only
subset below is correct under BOTH of the first two options.

The docstring (`terms.py:70-73`) advertises `Compound(functor_var, args)`,
but (all probe-confirmed, `TestF003CompoundVarFunctor`):

1. `Compound.__unify__` (`terms.py:92`) compares `self.functor != other.functor`
   without deref — a functor Var **bound to `"f"`** still fails to match
   `Compound("f", ...)`; an unbound functor Var never binds.
2. `c_copy_term` (`_variables.c:2734`) passes the functor through uncopied —
   an unbound functor Var is aliased between original and copy.
3. `c_is_ground` (`_variables.c:2120-2124`) answers False for a functor Var
   bound to a str (no deref).
4. `c_collect_vars` (`_variables.c:2985-3005`) never visits the functor slot.
5. `term_str` (`terms.py:1903-1907`) renders a bound functor Var as anon `_`
   (`term_str` hits the Var branch before deref).

## Fix (deref-only floor)

- `Compound.__unify__`: deref both functors before comparing (and, if D004
  lands on full support, `unify` them instead).
- `c_is_ground`: deref the functor before the `PyUnicode_Check`.
- `c_copy_term`: run the functor through `c_copy_term` too (no-op for str).
- `c_collect_vars`: visit the functor slot when it isn't a str.
- `term_str` / `term_html` / `term_pformat`: deref the functor first.

If D004 → reject-at-construction: instead validate in `Compound` and delete
the `functor: str | Var` annotation + docstring claim; the five sites above
then need only assert-str.

## Verify

Flip the six `TestF003CompoundVarFunctor` xfails per the chosen direction
(the output-mode test `test_unbound_var_functor_binds` stays xfail under
deref-only). Rebuild the C extension before testing.
