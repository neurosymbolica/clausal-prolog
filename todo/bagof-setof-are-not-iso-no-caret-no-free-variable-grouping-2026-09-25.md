# bagof/3 and setof/3 are not ISO: no `^`, no free-variable grouping

Found 2026-09-25 (fix/call-runs-special-form-cells-2026-09-25).  `call/N` of a
bagof/setof cell now runs exactly what the compiled body runs, so it inherits
this gap.  The gap is in the compiler, not in call/N.

## What the engine does

`clausal/logic/compiler/_lower_goalop_shared.py`:

```python
    if kind == "bagof":
        return _compile_find_all_core(
            ctx, margs["template"], margs["inner"], margs["bag"], k_stmts,
            fail_on_empty=True, dedup=False,
        )
    if kind == "setof":
        return _compile_find_all_core(
            ctx, margs["template"], margs["inner"], margs["bag"], k_stmts,
            fail_on_empty=True, dedup=True,
        )
```

bagof is findall that fails on an empty result; setof also sorts and
dedups.  There is no grouping.

## What ISO requires (13211-1 §8.10.2, §8.10.3; §7.1.1.4 free variables)

The free variables of `Template^Goal` are the variables of Goal that are
neither in Template nor bound by `^`.  bagof enumerates ONE solution per
distinct binding of those variables, on backtracking:

```prolog
age(peter, 7). age(ann, 11). age(pat, 8). age(tom, 5). age(mike, 11).

?- bagof(N, age(N, A), L).
%  ISO / Scryer:  A = 5,  L = [tom] ;
%                 A = 7,  L = [peter] ;
%                 A = 8,  L = [pat] ;
%                 A = 11, L = [ann, mike].
%  Clausal:       L = [peter, ann, pat, tom, mike]   (A unbound, one answer)

?- bagof(N, A^age(N, A), L).
%  ISO / Scryer:  L = [peter, ann, pat, tom, mike].
%  Clausal:       the module does not LOAD -- `^` is BitXor in the surface:
%    NotImplementedError terms_to_goalop: goal shape not yet supported
%    (BitXor): BitXor(left=A, right=Call(func=LoadName(name='age'), ...))
```

(Both Clausal answers measured 2026-09-25 on the branch.)

## Needed

- A spelling and a lowering of `^` (`V^G` calls G; the variables of V are existentially
  bound) inside bagof/setof, and `^/2` as a goal outside them (ISO:
  `call(V^G)` calls G).
- Free-variable analysis of the goal term at RUN time (the goal may be a
  variable bound to a term, as through call/N), then collect `W-T` pairs,
  keysort by witness W (setof: sort each group), and enumerate the groups
  on backtracking, unifying W with each.
- Scryer's `library(lists)`/builtins bagof is the reference implementation.
- The row table in tests/test_call_runs_special_form_cells.py (rows 4-6)
  only uses goals with no free variables, so it will not move.  Add rows
  with free variables when this is fixed.
