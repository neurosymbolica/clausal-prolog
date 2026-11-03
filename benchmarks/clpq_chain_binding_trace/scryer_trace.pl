:- use_module(clpq_tr).
:- use_module(library(lists)).
:- use_module(library(format)).
chain([_]).
chain([A,B|T]) :- {A =< B}, chain([B|T]).
nums(I, N, []) :- I >= N, !.
nums(I, N, [I|T]) :- I1 is I + 1, nums(I1, N, T).
bind_each([], _, _).
bind_each([X-V|T], L, [F|_]) :- format("~n== bind ~w~n", [V]), X = V, clpq:tr_store(F), bind_each(T, L, [F]).
pairs([], [], []).
pairs([X|Xs], [V|Vs], [X-V|Ps]) :- pairs(Xs, Vs, Ps).
run(N, Mode) :- length(L, N), clpq:tr_name_vars(L), chain(L), format("after posting the chain:~n", []), L = [F|_], lst(L, La), clpq:tr_store(La),
   nums(0, N, Ns), pairs(L, Ns, Ps),
   ( Mode = forward -> bind_each(Ps, L, [La])
   ; Mode = backward -> reverse(Ps, Rs), bind_each(Rs, L, [F])
   ; format("~n== bind all~n", []), L = Ns ).
lst([X],X) :- !.
lst([_|T],X) :- lst(T,X).
