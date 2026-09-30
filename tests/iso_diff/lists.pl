% library(lists) predicates Scryer also provides, in all modes.
add(X, A0, A) :- A is A0 + X.
cons(X, T, [X|T]).
add2(X, Y, A0, A) :- A is A0 + X * Y.
t(l01, X-Y, append(X, Y, [1, 2])).
t(l02, X, append([1], X, [1, 2, 3])).
t(l03, X, append(X, [3], [1, 2, 3])).
t(l04, X, append([1, 2], [3], X)).
t(l05, X-Y-Z, once(append(X, Y, Z))).
t(l06, X, append([[1], [2, 3], []], X)).
t(l08, N, length([a, b], N)).
t(l09, L, length(L, 2)).
t(l10, T, length([a|T], 3)).
t(l11, N, once((length(_, N), N >= 2))).
t(l12, N, length([a|b], N)).
t(l13, X, member(X, [a, b, c])).
t(l14, x, member(b, [a, b, b])).
t(l15, X, member(X, [])).
t(l16, X, memberchk(X, [a, b])).
t(l17, x, memberchk(b, [a, b, c])).
t(l18, X, nth0(1, [a, b, c], X)).
t(l19, N-X, nth0(N, [a, b, c], X)).
t(l20, X, nth0(5, [a], X)).
t(l21, X, nth0(-1, [a], X)).
t(l22, N, nth1(N, [a, b, c], c)).
t(l23, X, nth1(0, [a], X)).
t(l24, L, nth0(1, L, x)).
t(l25, E-R, nth0(1, [a, b, c], E, R)).
t(l26, L, nth1(2, L, x, [a, b])).
t(l27, X, reverse([1, 2, 3], X)).
t(l28, X, once(reverse(X, [1, 2]))).
t(l29, X, reverse([], X)).
t(l30, X, sum_list([1, 2, 3], X)).
t(l31, X, sum_list([1, 2.5], X)).
t(l32, X, sum_list([], X)).
t(l33, X, list_to_set([a, b, a, c, b], X)).
t(l34, X, list_to_set([1, 1.0, 1], X)).
t(l35, X, list_to_set([A, _B, A], X)).
t(l36, S, foldl(add, [1, 2, 3], 0, S)).
t(l37, R, foldl(cons, [a, b, c], [], R)).
t(l38, S, foldl(add2, [1, 2], [3, 4], 0, S)).
t(l39, L, maplist(succ, [1, 2], L)).
t(l40, L, maplist(succ, L, [2, 3])).
t(l41, R, select(b, [a, b, c, b], R)).
t(l42, X-R, select(X, [a, b], R)).
t(l43, L, select(x, L, [a, b])).
t(l44, P, permutation([1, 2, 3], P)).
t(l45, L, same_length([a, b], L)).
t(l46, X, transpose([[1, 2], [3, 4]], X)).
t(l47, X, list_max([1, 3, 2], X)).
t(l48, X, list_min([1, 3, 2], X)).
t(l49, L-S, once(sum_list(L, S))).
t(l50, X, list_to_set([], X)).
t(l51, X, nth1(1, [], X)).
t(l52, x, once(member(_, [a | _]))).
t(l53, L, once(select(_, L, _))).
t(l54, X, list_max([1, 3.0, 2], X)).
t(l55, X, list_min([2, 1.0, 1], X)).
t(l56, X, sum_list([1, a], X)).
t(l59, X-Y, append(X, [b|Y], [a, b, c, b])).
t(l60, L, (L = [_, _], maplist(=(z), L))).
t(l61, X, nth0(1.0, [a, b], X)).
t(l62, X, nth1(a, [a, b], X)).
t(l63, X, sum_list(foo, X)).
t(l64, X, list_to_set(foo, X)).
t(l65, X, permutation(foo, X)).
t(l66, X, once(permutation(X, [1, 2]))).
t(l67, X, length([a, b, c], 2)).
t(l68, X, append(foo, [], X)).
t(l69, X, foldl(add, [1, a], 0, X)).
t(l70, X, same_length(X, [a])).
