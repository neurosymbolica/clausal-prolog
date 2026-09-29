% Slice 2 exit rulebase: the .pl main module.  It imports a .seam module
% (shapes) and a .pl module (facts) under BOTH path spellings, resolves a
% name clash with a qualified call, declares its own dynamic, table,
% discontiguous and meta_predicate procedures, and switches double_quotes.
:- module(s2main, [shape_area/2, big/1, local_base/1, their_base/1,
                   bumped/1, noted/1, seen_all/1, fib/2, kind/2, twice/1,
                   op(200, xfy, ^^)]).

:- use_module(s2lib/shapes).
:- use_module(s2lib/facts, [bump/1, counter/1, op(700, xfx, ===>)]).
:- use_module('s2lib/facts', [add_note/1, notes/1]).
:- use_module(library(lists)).
:- use_module(library(dif)).
:- use_module(library(tabling)).

:- dynamic(seen/1).
:- discontiguous(kind/2).
:- table(fib/2).
:- meta_predicate(twice(0)).

shape_area(sq(2), A) :- area(sq(2), A).
shape_area(rect(2, 3), A) :- area(rect(2, 3), A).

big(Y) :- scaled(3, Y), Y > 40.

% A local base/1 beside facts' base/1: the unqualified call is the local
% one, facts:base/1 is facts'.
base(local).
local_base(X) :- base(X).
their_base(X) :- facts:base(X).
their_base(X) :- shapes:kinds(X).

bumped([A, B, C]) :- bump(A), bump(B), bump(C).

noted(L) :- add_note(x), add_note(y), notes(L).

seen_all(L) :- assertz(seen(1)), assertz(seen(2)), findall(X, seen(X), L).

fib(0, 0).
fib(1, 1).
fib(N, F) :- N > 1, N1 is N - 1, N2 is N - 2, fib(N1, F1), fib(N2, F2),
    F is F1 + F2.

kind(a, vowel).
twice(G) :- call(G), call(G).
inc(X, Y) :- Y is X + 1.
memb(X, [X|_]).
memb(X, [_|T]) :- memb(X, T).
kind(b, consonant).

ops(X) :- X = (a ^^ b ^^ c).
ops(X) :- X = (a ===> b).
ops(X) :- memb(X, [1, 2]).
ops(X) :- maplist(inc, [1, 2], X).
ops(X) :- memb(X, [p, q, r]), dif(X, q).

dq_chars(X) :- X = "ab".
:- set_prolog_flag(double_quotes, codes).
dq_codes(X) :- X = "ab".
:- set_prolog_flag(double_quotes, atom).
dq_atom(X) :- X = "ab".
dq_atom(X) :- X = "[]".
:- set_prolog_flag(double_quotes, chars).
dq_back(X) :- X = "ab".
