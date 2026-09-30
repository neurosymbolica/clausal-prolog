% Shared prelude of the differential sweep (tests/iso_diff): prepended to
% each area file, which holds t(Id, Template, Goal) rows.  run/0 prints one
% line per row: the Id and the findall/3 of Template over Goal (or ex(E)
% for an error), variables replaced by '_'(N) so both engines print alike,
% and every error(F, Context) printed as error(F, ctx): ISO leaves the
% context implementation dependent (Scryer names its helpers there).
% The '_'(N) form is a rebuilt COPY, not a binding: binding the tail of a
% partial list to '_'(N) would make an improper list, which Clausal does not
% represent (a partial-list tail binds only to a list).  So the copy ends a
% partial list with the element '$tail'('_'(N)): [A|T] prints as
% ['_'(0),'$tail'('_'(1))] in both engines, while T elsewhere is '_'(1).
:- use_module(library(lists)).
:- use_module(library(between)).
:- use_module(library(iso_ext)).
:- use_module(library(freeze)).
:- use_module(library(dif)).

nv(T, R) :- term_variables(T, Vs), nv_(Vs, T, R).
nv_(Vs, T, '_'(N)) :- var(T), vix(Vs, T, 0, N).
nv_(_, T, T) :- atomic(T).
nv_(Vs, T, [H1|T1]) :- nonvar(T), \+ atomic(T), T = [H|Tl], nv_(Vs, H, H1),
    nvt(Vs, Tl, T1).
nv_(Vs, T, R) :- compound(T), T \= [_|_], T =.. [F|As],
    maplist(nv_(Vs), As, Bs), R =.. [F|Bs].
nvt(Vs, T, ['$tail'('_'(N))]) :- var(T), vix(Vs, T, 0, N).
nvt(Vs, T, R) :- nonvar(T), nv_(Vs, T, R).
vix([V|_], T, N, N) :- V == T.
vix([V|Vs], T, N0, N) :- V \== T, N1 is N0 + 1, vix(Vs, T, N1, N).

row(Id, L) :- t(Id, T, G), catch(findall(T, G, L), E, L = ex(E)).

strip(T, T) :- var(T).
strip(T, T) :- atomic(T).
strip(T, error(F, ctx)) :- nonvar(T), T = error(F0, _), strip(F0, F).
strip(T, S) :- compound(T), T \= error(_, _), T =.. [N|As],
    maplist(strip, As, Bs), S =.. [N|Bs].

run :- row(Id, L1), nv(L1, L0), once((strip(L0, L) ; L = unstripped(L0))), writeq(Id), write(' '), writeq(L),
    nl, fail.
run.
