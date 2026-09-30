% Shared prelude of the differential sweep (tests/iso_diff): prepended to
% each area file, which holds t(Id, Template, Goal) rows.  run/0 prints one
% line per row: the Id and the findall/3 of Template over Goal (or ex(E)
% for an error), variables replaced by '_'(N) so both engines print alike,
% and every error(F, Context) printed as error(F, ctx): ISO leaves the
% context implementation dependent (Scryer names its helpers there).
:- use_module(library(lists)).
:- use_module(library(between)).
:- use_module(library(iso_ext)).
:- use_module(library(freeze)).
:- use_module(library(dif)).

nv(T) :- term_variables(T, Vs), nv_(Vs, 0).
nv_([], _).
nv_(['_'(N)|Vs], N) :- N1 is N + 1, nv_(Vs, N1).

row(Id, L) :- t(Id, T, G), catch(findall(T, G, L), E, L = ex(E)).

strip(T, T) :- var(T).
strip(T, T) :- atomic(T).
strip(T, error(F, ctx)) :- nonvar(T), T = error(F0, _), strip(F0, F).
strip(T, S) :- compound(T), T \= error(_, _), T =.. [N|As],
    maplist(strip, As, Bs), S =.. [N|Bs].

run :- row(Id, L0), nv(L0), once((strip(L0, L) ; L = unstripped(L0))), writeq(Id), write(' '), writeq(L),
    nl, fail.
run.
