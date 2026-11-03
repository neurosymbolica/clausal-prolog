"""Write an instrumented copy of Scryer's clpq.pl (argv[1] -> argv[2]): format/2
prints at verify_lin/2, solve/5, solve_x/6, bs/3, bs_collect_bindings/5 and
pivot/2,3.  The installed library is not modified.  Used by run.sh."""
import sys
src = open(sys.argv[1]).read()
def rep(old, new, count=1):
    global src
    assert src.count(old) == count, (old, src.count(old))
    src = src.replace(old, new)
rep(":- use_module( library(atts)).", ":- use_module( library(atts)).\n:- use_module( library(format)).")
rep("             class_atts/4.", "             class_atts/4, tr_name/1.")
# helpers
helpers = r'''
% ---- TRACE helpers (scratch instrumentation) ----
tr_name_vars(Xs) :- bb_put(tr_cnt, 0), tr_name_vars(Xs, 1).
tr_name_vars([], _).
tr_name_vars([X|Xs], I) :- atom_chars(x, [C]), number_chars(I, Ds), atom_chars(N, [C|Ds]), put_atts(X, tr_name(N)), I1 is I+1, tr_name_vars(Xs, I1).
tr_n(V, N) :- var(V), get_atts(V, tr_name(N0)), !, N = N0.
tr_n(V, N) :- var(V), !, bb_get(tr_cnt, C), C1 is C+1, bb_put(tr_cnt, C1), number_chars(C1, Ds), atom_chars(N, [s|Ds]), put_atts(V, tr_name(N)).
tr_n(V, V).
tr_lin(Lin, S) :- Lin = [I,_|H], tr_terms(H, Ts), S = Ts+I.
tr_terms([], []).
tr_terms([X*K|Xs], [K*N|Ns]) :- tr_n(X, N), tr_terms(Xs, Ns).
tr_store(V) :- var(V), get_atts(V, class(C)), !, class_allvars(C, All), class_basis(C, B),
   tr_open(All, AllL), tr_names(AllL, AN), tr_names(B, BN),
   format("  members: ~w~n  basis: ~w~n", [AN, BN]), tr_rows(AllL).
tr_store(_) :- format("  (no component)~n", []).
tr_open(L, []) :- var(L), !.
tr_open([X|Xs], [X|Ys]) :- tr_open(Xs, Ys).
tr_names(L, []) :- var(L), !.
tr_names([], []).
tr_names([X|Xs], [N|Ns]) :- tr_n(X, N), tr_names(Xs, Ns).
tr_rows([]).
tr_rows([X|Xs]) :- ( var(X), get_atts(X, lin(L)) -> tr_n(X, N), (get_atts(X, type(T)) -> true ; T = '?'), ( indep(L, X) -> format("    ~w indep ~w~n", [N, T]) ; tr_lin(L, S), format("    ~w = ~w  ~w~n", [N, S, T]) ) ; true ), tr_rows(Xs).
tr_bs_open(V, Lin, Label) :- tr_n(V, N), tr_lin(Lin, S), format("    ~w ~w := ~w ; rewrote:", [Label, N, S]).
tr_rw(X) :- tr_n(X, N), format(" ~w", [N]).
tr_cnt_read(Xs, K) :- tr_open(Xs, L), length(L, K).
'''
rep("% ---- Solver identity ----", helpers + "\n% ---- Solver identity ----")
# verify_lin
rep("""verify_lin( X, Y) :-
  get_atts( X, class(Class)),
    get_atts( X, lin(LinX)),
  !,
""", """verify_lin( X, Y) :-
  get_atts( X, class(Class)),
    get_atts( X, lin(LinX)),
  !,
  tr_n(X, TrN), ( indep(LinX, X) -> TrI = indep ; TrI = dep ), format("  verify_lin ~w = ~w (~w)~n", [TrN, Y, TrI]),
""")
# solve/5
rep("""  sd( H, [],ClassesUniq, 9-9-0,Category-Selected-_, NV,NVT),
""", """  sd( H, [],ClassesUniq, 9-9-0,Category-Selected-_, NV,NVT),
  tr_n(Selected, TrS), tr_terms(H, TrH), format("    solve ~w ~w   (terms ~w)~n", [Category, TrS, TrH]),
""")
rep("""  sd( H, [],ClassesUniq, 9-9-0,_, NV,NVT),
""", """  sd( H, [],ClassesUniq, 9-9-0,_, NV,NVT),
  tr_n(Selected, TrS), tr_terms(H, TrH), format("    solve_for_variable ~w   (terms ~w)~n", [TrS, TrH]),
""")
# bs
rep("""bs( Xs,     _, _) :- var( Xs), !.
bs( [X|Xs], V, Lin) :-
  ( get_atts( X, lin(LinX)),
    nf_substitute( V, Lin, LinX, LinX1) ->
      put_atts( X, lin(LinX1)),
      bs( Xs, V, Lin)
  ;
      bs( Xs, V, Lin)
  ).""", """bs( Xs, V, Lin) :- tr_bs_open(V, Lin, bs), tr_cnt_read(Xs, K), bs0(Xs, V, Lin), format(" ; read ~w~n", [K]).
bs0( Xs,     _, _) :- var( Xs), !.
bs0( [X|Xs], V, Lin) :-
  ( get_atts( X, lin(LinX)),
    nf_substitute( V, Lin, LinX, LinX1) ->
      tr_rw(X),
      put_atts( X, lin(LinX1)),
      bs0( Xs, V, Lin)
  ;
      bs0( Xs, V, Lin)
  ).""")
rep("""bs_collect_bindings( Xs,     _, _,   Bind0,BindT) :- var( Xs), !, Bind0=BindT.
bs_collect_bindings( [X|Xs], V, Lin, Bind0,BindT) :-
  ( get_atts( X, lin(LinX)),
    nf_substitute( V, Lin, LinX, LinX1) ->
      put_atts( X, lin(LinX1)),
      decompose( LinX1, Hom, _, Inhom),
      bs_collect_binding( Hom, X, Inhom, Bind0,Bind1),
      bs_collect_bindings( Xs, V, Lin, Bind1,BindT)
  ;
      bs_collect_bindings( Xs, V, Lin, Bind0,BindT)
  ).""", """bs_collect_bindings( Xs, V, Lin, Bind0, BindT) :- tr_bs_open(V, Lin, bs_collect), tr_cnt_read(Xs, K), bs_collect_bindings0(Xs, V, Lin, Bind0, BindT), format(" ; read ~w~n", [K]).
bs_collect_bindings0( Xs,     _, _,   Bind0,BindT) :- var( Xs), !, Bind0=BindT.
bs_collect_bindings0( [X|Xs], V, Lin, Bind0,BindT) :-
  ( get_atts( X, lin(LinX)),
    nf_substitute( V, Lin, LinX, LinX1) ->
      tr_rw(X),
      put_atts( X, lin(LinX1)),
      decompose( LinX1, Hom, _, Inhom),
      bs_collect_binding( Hom, X, Inhom, Bind0,Bind1),
      bs_collect_bindings0( Xs, V, Lin, Bind1,BindT)
  ;
      bs_collect_bindings0( Xs, V, Lin, Bind0,BindT)
  ).""")
rep("""pivot( Dep, Indep, IndAct) :-
  get_atts( Dep, lin(H)),""", """pivot( Dep, Indep, IndAct) :-
  tr_n(Dep, TrD), tr_n(Indep, TrI), format("    pivot ~w ~w~n", [TrD, TrI]),
  get_atts( Dep, lin(H)),""")
rep("""pivot( Dep, Indep) :-
  get_atts( Dep, lin(H)),""", """pivot( Dep, Indep) :-
  tr_n(Dep, TrD), tr_n(Indep, TrI), format("    pivot_ignoring_bounds ~w ~w~n", [TrD, TrI]),
  get_atts( Dep, lin(H)),""")
open(sys.argv[2], "w").write(src)
