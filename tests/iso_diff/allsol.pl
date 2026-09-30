% findall/3, findall/4, bagof/3, setof/3 with ^ and free variables, forall/2.
p(1, a). p(2, b). p(3, a). p(1, c).
q(1, x, 10). q(2, y, 20). q(1, y, 30).
t(f01, L, findall(X, p(X, _), L)).
t(f02, Y-L, bagof(X, p(X, Y), L)).
t(f03, L, bagof(X, Y^p(X, Y), L)).
t(f04, L, setof(X, Y^p(X, Y), L)).
t(f05, L, setof(Y-X, p(X, Y), L)).
t(f06, Y-L, setof(X, p(X, Y), L)).
t(f07, L, bagof(X, p(X, z), L)).
t(f08, L, findall(_, fail, L)).
t(f09, L, setof(X, member(X, [c, a, b, a]), L)).
t(f10, L, bagof(X, member(X, [c, a, b, a]), L)).
t(f11, L, setof(X-Y, member(X-Y, [b-1, a-2, a-1]), L)).
t(f12, L, bagof(X, (member(X, [1, 2]), member(_Y, [a, b])), L)).
t(f13, E, catch(bagof(_, _, _), E, true)).
t(f14, E, catch(bagof(_, 1, _), E, true)).
t(f15, L, setof(X, Y^Z^q(X, Y, Z), L)).
t(f16, Y-Z-L, bagof(X, q(X, Y, Z), L)).
t(f17, L, findall(X-Y, (member(X, [1, 2]), member(Y, [a])), L)).
t(f18, L, setof(K, V^member(K-V, [b-1, a-1, b-2]), L)).
t(f19, L, bagof(X, member(X, [A, _B, A]), L)).
t(f20, L-T, findall(X, member(X, [1, 2, 3]), L, T)).
t(f21, L, setof(X, member(X, [1, 1.0, 2]), L)).
t(f22, L, bagof(X, Y^(p(X, Y), Y \== c), L)).
t(f23, L, setof(Y, X^p(X, Y), L)).
t(f24, Y, bagof(X, p(X, Y), [1, 3])).
t(f25, x, forall(member(X, [1, 2]), X > 0)).
t(f26, x, forall(member(X, [1, 2]), X > 1)).
t(f27, L, setof(X, (member(X, [b, a]) ; X = c), L)).
t(f28, L, bagof(X-_Y, member(X, [1, 2]), L)).
t(f29, Y, bagof(X, p(X, Y), _)).
t(f30, L, setof((X, Y), p(X, Y), L)).
t(f31, Y-L, setof(X-Z, q(X, Y, Z), L)).
t(f32, L, setof(X, Y^Z^(q(X, Y, Z), Z > 15), L)).
t(f34, L, findall(X, (member(X, [3, 1, 2]), X > 1), L)).
t(f35, E, catch(findall(X, member(X, [1]), foo), E, true)).
t(f36, E, catch(setof(X, member(X, [1]), [a|b]), E, true)).
t(f37, L, bagof(X, Y^Z^q(X, Y, Z), L)).
t(f38, L, setof(N, X^Y^(p(X, Y), N is X * 10), L)).
t(f39, L, (L = [_|_], findall(X, member(X, [a]), L))).
t(f40, E, catch(setof(X, _^foo_undefined_q(X), _), E, true)).
