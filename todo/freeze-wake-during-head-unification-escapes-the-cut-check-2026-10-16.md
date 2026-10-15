# A goal woken by freeze/2 during head unification escapes the run-time cut check

**Status: OPEN, Minor, fails open** (final re-review, 2026-10-16). Documented in docs/importing_prolog.md ("Not checked").

The run-time half of the cut-over-a-table rule (`tabling.cut_over_incomplete`) compares against a mark the clause body reads at its start (`_cutm = $tab_ctx.cut_seq`, `cut_scope.cut_guard_entry`). A goal that `freeze/2` wakes while the clause HEAD is unified runs before that mark is read. So a tabled call it makes looks "outside" the clause's cut scope:

```prolog
:- table(t/1).
t(1). t(2). t(3).
tq(X) :- t(X).
p(1) :- !.
q(R) :- freeze(V, tq(_)), p(V), R = ok.
% Clausal: ok   XSB: error (cut over an incomplete table)
```

Fix: read the mark before head unification in a clause whose body cuts. That is the arm's entry, next to `_mark = trail.mark()`. The head-match builder would need to emit it.
