% between/3, succ/2, numlist/3.
t(b01, X, between(1, 3, X)).
t(b02, X, between(3, 1, X)).
t(b03, x, between(1, 3, 3)).
t(b04, x, between(1, 3, 4)).
t(b05, x, between(1, inf, 3)).
t(b06, X, between(a, 3, X)).
t(b07, X, between(_, 3, X)).
t(b08, x, between(1, 3, a)).
t(b09, X, between(1.0, 3, X)).
t(b10, x, between(1, 3, 2.0)).
t(b11, X, between(-2, 0, X)).
t(b12, X, once((between(1, inf, X), X > 3))).
t(b13, X, once((between(1, infinite, X), X > 3))).
t(b14, X, succ(X, 4)).
t(b15, X, succ(3, X)).
t(b16, X, succ(X, 0)).
t(b17, X, succ(-1, X)).
t(b18, X, succ(a, X)).
t(b19, X-Y, succ(X, Y)).
t(b20, X, succ(1.0, X)).
t(b21, x, succ(2, 3)).
t(b22, X, succ(X, -1)).
t(b23, X, numlist(1, 5, X)).
t(b24, X, numlist(5, 1, X)).
t(b25, X-Y, (between(1, 3, X), between(X, 3, Y))).
t(b26, X, between(1, 1, X)).
t(b27, x, between(0, 10000000000000000000001, 10000000000000000000000)).
t(b28, x, succ(2, 4)).
t(b29, X, succ(X, 1)).
t(b30, X, between(1, 3.0, X)).
t(b31, X, between(1, foo, X)).
t(b32, x, between(1, 3, _)).
t(b33, X, numlist(a, 3, X)).
t(b34, X, numlist(3, 3, X)).
t(b35, X, succ(X, a)).
