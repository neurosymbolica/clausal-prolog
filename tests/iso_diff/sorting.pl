% sorting (sort/2, keysort/2) and the standard order across types.
t(s01, X, sort([c, a, b, a], X)).
t(s02, X, sort([], X)).
t(s03, X, sort([1, 1.0], X)).
t(s04, X, sort([2, 1.0, 1, 2.0], X)).
t(s05, X, sort(foo, X)).
t(s06, X, sort([a|_], X)).
t(s07, X, sort([b, a], [a|X])).
t(s08, x, sort([a], foo)).
t(s09, X, sort([[b], [a, c], [a]], X)).
t(s10, X, sort(["b", "a"], X)).
t(s11, X, sort([1.5, 1, 2, 0.5, -1, -1.0], X)).
t(s12, X, sort([f(1, 2), g(1), f(2), a, 3], X)).
t(s13, X, sort([a, b|c], X)).
t(s14, X, keysort([a-1, x], X)).
t(s15, X, sort([10000000000000000000000, 1.0e22], X)).
t(s16, X, sort([-0.0, 0.0, 0], X)).
t(s17, X, keysort([b-2, a-1.0, a-1, b-1], X)).
t(s18, X, keysort([1.0-a, 1-b, 0.5-c], X)).
t(s19, x, sort([b, a], [a, b])).
t(s20, x, sort([b, a], [b, a])).
t(s21, X, sort([f(a), f(_), f(b)], X)).
t(s22, X, sort(['B', b, 'A', a, '_', '0'], X)).
t(s23, X, sort([[], '[]', [a]], X)).
t(s24, X, keysort(X, [a-1])).
t(s25, X, keysort([a-1|foo], X)).
t(s26, X, sort([1, 2|_], X)).
t(s27, X, sort([x, y], [X, y])).
t(s28, X, sort([z, 2.0, 2, "a", 1], X)).
t(s29, X, sort([abc, ab, abcd, b], X)).
t(s30, X, sort([f(b, a), f(a, b), f(a)], X)).
