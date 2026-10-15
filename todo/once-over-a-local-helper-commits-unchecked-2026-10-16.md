# once/1 or Setup over a local helper that calls call/N commits unchecked over an incomplete table

**Status: OPEN, fails open** (final re-review 2, G-1, 2026-10-16). Not a regression: before the run-time check, once/1 committed unchecked everywhere. Documented in docs/importing_prolog.md (the once/1 and Setup bullet).

## Repro

```prolog
% rtu3.pl -- tables nothing, imports nothing
:- module(rtu3, [g1/1, g2/1, g3/1]).
:- meta_predicate(g1(0)). :- meta_predicate(g2(0)). :- meta_predicate(g3(0)).
g1(G) :- once(run(G)).
run(G) :- call(G).
g2(G) :- once(run2(G)).
run2(G) :- G.
g3(G) :- setup_call_cleanup(run(G), true, true).

% user.pl
:- use_module(rtu3).
:- table(path/2).
e(a, b). e(b, a).
path(X, Y) :- e(X, Y).
path(X, Y) :- path(X, Z), e(Z, Y).
u1(Y) :- g1(path(a, Y)).     % Clausal [b] silently; Scryer [a]; XSB: error
```

g2 and g3 behave the same way.

## Why

`cut_scope.commit_check` emits the once/Setup check in a table-blind `.pl` module only when the goal WRITTEN inside once/Setup is open: a variable, or a call/N or control construct called as a predicate (`_goal_is_open`). `run(G)` is a closed call to an ordinary predicate.

## Options

- (a) In a `.pl` db, count a module that holds a variable goal or call/N ANYWHERE as one that may reach a table: `may_reach_a_table` becomes "may run an arbitrary goal". `.clausal`/`.seam` code and table-blind `.pl` modules with no meta-calls stay byte-identical.
- (b) The complete-first design question pending with the operator would cover the NON-recursive case: a root leader completes before its first answer, so the commit prunes a complete table. A recursive table, committed inside its own evaluation as here, still needs (a).
