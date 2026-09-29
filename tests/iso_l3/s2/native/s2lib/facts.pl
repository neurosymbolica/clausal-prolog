% Slice 2 exit rulebase: a .pl library-style module.  Imported by the .pl
% main module (both path spellings) and by the .seam module shapes.seam.
:- module(facts, [base/1, pair/2, counter/1, bump/1, add_note/1, notes/1,
                  op(700, xfx, ===>)]).

:- dynamic(counter/1).

base(10).
base(20).

pair(a, 1).
pair(b, 2).

% The module's own op/3 export governs its own clauses too (as in Scryer).
rel(a ===> b).
rel(c ===> d).

counter(0).

bump(N) :- retract(counter(M)), N is M + 1, assertz(counter(N)).

% jotting/1 is never declared: assertz creates it as dynamic
% (assert_creates_dynamic is on for a .pl module).
add_note(X) :- assertz(jotting(X)).
notes(L) :- findall(X, jotting(X), L).
