% Slice 1 exit rulebase (plan native-iso-reader-step2 §4): recursion,
% disjunction, negation, call/N, arithmetic, == vs =:=, @< and compare.
%
% Driven by tests/iso_l3/test_l3_s1_exit.py, which runs it under
% `python -m clausal.testing` with CLAUSAL_PL_FRONTEND=native, compares every
% helper predicate's all-answers with the hand-written twin
% rulebase_s1_twin.seam, and runs the oracle/2 cases and the whole test/1
% population under Scryer.  Plain ISO: it loads unchanged in Scryer.

edge(a, b).
edge(b, c).
edge(c, d).
edge(b, e).

owns(1, a).
owns(2, a).
owns(3, b).

% ── recursion ──

path(X, Y) :- edge(X, Y).
path(X, Y) :- edge(X, Z), path(Z, Y).

len([], 0).
len([_|T], N) :- len(T, N0), N is N0 + 1.

app([], L, L).
app([H|T], L, [H|R]) :- app(T, L, R).

nrev([], []).
nrev([H|T], R) :- nrev(T, RT), app(RT, [H], R).

fact(0, 1).
fact(N, F) :- N > 0, N1 is N - 1, fact(N1, F1), F is N * F1.

% ── disjunction ──

color(C) :- ( C = red ; C = green ; C = blue ).

sign_of(X, S) :- ( X < 0, S = neg ; X =:= 0, S = zero ; X > 0, S = pos ).

% ── negation ──

source(X) :- edge(X, _), \+ edge(_, X).
leaf(X) :- edge(_, X), \+ edge(X, _).

memb(X, [X|_]).
memb(X, [_|T]) :- memb(X, T).

not_in(X, L) :- \+ memb(X, L).

% ── call/N ──

apply2(F, X, Y) :- call(F, X, Y).
twice(G) :- call(G), call(G).

mapl(_, [], []).
mapl(F, [X|Xs], [Y|Ys]) :- call(F, X, Y), mapl(F, Xs, Ys).

succ_of(X, Y) :- Y is X + 1.

reach_from(X, Ys) :- findall(Y, call(path(X), Y), Ys).
goal_var(G, R) :- G = edge(b, R), G.
all_owned(L) :- setof(X, Y^owns(X, Y), L).

% ── arithmetic ──

arith(X) :- X is 7 - 2 * 3.
arith_int_div(X) :- X is -7 // 2.
arith_pow(X) :- X is 2 ^ 10.
arith_max(X) :- X is max(1, 2.0).
arith_mod(M, R) :- M is -7 mod 2, R is -7 rem 2.

% ── == vs =:=, standard order ──

eq_struct(A, B, R) :- ( A == B, R = same ; \+ A == B, R = differ ).
eq_arith(A, B, R) :- ( A =:= B, R = equal ; A =\= B, R = unequal ).
before(A, B) :- A @< B.
cmp(O, A, B) :- compare(O, A, B).

% ── the Scryer-oracle cases on the ISO-vs-seam hazard names ──

oracle(eq, L) :-
    findall(R, ( eq_struct(1, 1.0, R) ; eq_struct(a, a, R)
               ; eq_struct(1+1, 2, R) ; eq_arith(1+1, 2, R) ), L).
oracle(is, L) :- findall(X, ( arith(X) ; fact(5, X) ; len([p, q], X) ), L).
oracle(caret, L) :-
    findall(X, ( arith_pow(X) ; X is 2.0 ^ 2 ; all_owned(X) ), L).
oracle(intdiv, L) :-
    findall(X, ( arith_int_div(X) ; X is 7 // -2 ; X is -7 // -2 ), L).
oracle(max_min, L) :-
    findall(X, ( arith_max(X) ; X is max(2, 1) ; X is min(-1.5, -2) ), L).

% ── tests ──

test('path: reachable from a, in order') :-
    findall(Y, path(a, Y), L), L == [b, c, e, d].
test('path: nothing from d') :- \+ path(d, _).
test('path: transitive a to d') :- path(a, d).
test('len: recursion with is') :- len([x, y, z], N), N =:= 3.
test('len: empty list') :- len([], 0).
test('app: every split, in order') :-
    findall(A-B, app(A, B, [1, 2]), L), L == [[]-[1, 2], [1]-[2], [1, 2]-[]].
test('nrev: reverses') :- nrev([1, 2, 3], R), R == [3, 2, 1].
test('fact: 5! is 120') :- fact(5, F), F =:= 120.
test('fact: 0! is 1') :- fact(0, 1).
test('disjunction: colors in order') :-
    findall(C, color(C), L), L == [red, green, blue].
test('disjunction: sign of -3') :- sign_of(-3, neg).
test('disjunction: sign of 0') :- sign_of(0, zero).
test('disjunction: sign of 2.5') :- sign_of(2.5, pos).
test('negation: a is the only source') :- findall(X, source(X), L), L == [a].
test('negation: leaves') :- findall(X, leaf(X), L), L == [d, e].
test('negation: not_in') :- not_in(z, [a, b]).
test('negation: \\+ of a success fails') :- \+ not_in(a, [a, b]).
test('call/N: a closure with two added arguments') :-
    apply2(app([1]), [2], L), L == [1, 2].
test('call/N: twice') :- twice(edge(a, b)).
test('call/N: mapl over succ_of') :- mapl(succ_of, [1, 2, 3], L), L == [2, 3, 4].
test('call/N: closure path(b) under findall') :- reach_from(b, L), L == [c, e, d].
test('call/1: a variable goal') :- findall(R, goal_var(_, R), L), L == [c, e].
test('call/1: a conjunction built as data') :-
    G = (edge(a, X), edge(X, Y)), findall(Y, call(G), L), L == [c, e].
test('setof: the ^ prefix groups nothing') :- all_owned(L), L == [1, 2, 3].
test('arith: precedence') :- arith(X), X =:= 1.
test('arith: // truncates toward zero') :- arith_int_div(X), X == -3.
test('arith: ^ on integers is an integer') :- arith_pow(X), X == 1024.
test('arith: max of mixed types') :- arith_max(X), X == 2.0.
test('arith: mod and rem') :- arith_mod(M, R), M == 1, R == -1.
test('arith: float product') :- X is 1.5 * 2, X == 3.0.
test('arith: comparisons') :- 1 < 2, 2 >= 2, 3 =< 4, 5 > 4.
test('==: 1 and 1.0 differ') :- eq_struct(1, 1.0, differ).
test('=:=: 1 and 1.0 are equal') :- eq_arith(1, 1.0, equal).
test('==: a sum is not evaluated') :- eq_struct(1+1, 2, differ).
test('=:=: a sum is evaluated') :- eq_arith(1+1, 2, equal).
test('==: distinct unbound variables differ') :- eq_struct(_, _, differ).
test('==: one variable is itself') :- X = Y, eq_struct(X, Y, same).
test('\\==: structural') :- a \== b, 1 \== 1.0.
test('=\\=: evaluates') :- 2 =\= 1 + 2.
test('@<: a number before an atom') :- before(1, a).
test('@<: a float before an equal integer') :- before(1.0, 1).
test('@<: atoms alphabetically') :- before(abc, abd).
test('@<: compounds by arity, then name') :- before(f(b), g(a)), before(z(a), a(b, c)).
test('compare: <') :- cmp(O, 1, 2), O == (<).
test('compare: =') :- cmp(O, f(a), f(a)), O == (=).
test('compare: >') :- cmp(O, b, a), O == (>).
test('compare: a variable before a number') :- cmp(O, _, 1), O == (<).
