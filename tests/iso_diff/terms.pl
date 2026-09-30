% term inspection: functor/3, arg/3, =../2, copy_term/2 (attributed
% variables too), term_variables/2, compare/3 and the standard order.
t(t01, N-A, functor(foo(a, b), N, A)).
t(t02, X, functor(X, foo, 2)).
t(t03, X, functor(X, foo, 0)).
t(t04, X, functor(X, 1.5, 0)).
t(t05, X, functor(X, f(a), 1)).
t(t06, X, functor(X, foo, -1)).
t(t07, X, functor(X, _, 1)).
t(t08, N-A, functor([a], N, A)).
t(t09, N-A, functor("ab", N, A)).
t(t10, N-A, functor(1.5, N, A)).
t(t11, X, functor(X, 1, 1)).
t(t12, X, functor(X, foo, a)).
t(t13, N-A, functor([], N, A)).
t(t14, X, arg(1, foo(a, b), X)).
t(t15, N-X, arg(N, foo(a, b), X)).
t(t16, X, arg(0, foo(a), X)).
t(t17, X, arg(3, foo(a, b), X)).
t(t18, X, arg(a, foo(a), X)).
t(t19, X, arg(1, atom, X)).
t(t20, X, arg(-1, foo(a), X)).
t(t21, X, arg(1, [a|b], X)).
t(t22, X, foo(a, b) =.. X).
t(t23, X, X =.. [foo, a]).
t(t24, X, X =.. [foo]).
t(t25, X, X =.. [1.5]).
t(t26, X, X =.. [f(a), b]).
t(t27, X, X =.. [1, b]).
t(t28, X, X =.. []).
t(t29, X, X =.. [foo|_]).
t(t30, X, abc =.. X).
t(t31, X, [a, b] =.. X).
t(t32, X, 3 =.. X).
t(t33, X, X =.. [_, a]).
t(t34, X, copy_term(f(A, _B, A), X)).
t(t35, A-B-Y, copy_term(f(A, B), f(x, Y))).
t(t36, X, (freeze(V, X = woke), copy_term(V, W), W = 1)).
t(t37, x, (dif(A, a), copy_term(A, B), B = a)).
t(t38, x, (dif(A, a), copy_term(A, B), B = b)).
t(t39, X, term_variables(f(X1, g(_Y1, X1), _Z), X)).
t(t40, X, term_variables([a|_T], X)).
t(t41, X, term_variables(abc, X)).
t(t42, R, compare(R, 1, 1.0)).
t(t43, R, compare(R, 1, 2.0)).
t(t44, R, compare(R, a, 1)).
t(t45, R, compare(R, f(a), a)).
t(t46, R, compare(R, f(a, b), g(a))).
t(t47, R, compare(R, f(b), g(a))).
t(t48, R, compare(R, _, 1)).
t(t49, R, compare(R, "ab", ab)).
t(t50, R, compare(R, [], a)).
t(t51, R, compare(R, [], '[]')).
t(t52, R, compare(R, 1.5, 1)).
t(t53, R, compare(R, -0.0, 0.0)).
t(t54, R, compare(R, 0, -0.0)).
t(t55, R, compare(R, 10000000000000000000000, 1.0e22)).
t(t56, x, compare(foo, a, b)).
t(t57, x, compare(=, a, a)).
t(t58, X, sort([b, 1, a, 2.0, f(x), [c], 1.0, [], g(a, b), 1, -1, 'B'], X)).
t(t59, x, 1 @< 1.0).
t(t60, x, 1.0 @< 1).
t(t61, x, a @< b).
t(t62, x, b @> a).
t(t63, x, 1 == 1.0).
t(t64, x, f(A) \== f(A)).
t(t65, x, unify_with_occurs_check(X, f(X))).
t(t66, x, 2 @> 1.5).
t(t67, x, 1.0 @< 0).
t(t68, R, compare(R, 1, 1)).
t(t69, R, compare(R, f(a), f(a, b))).
t(t70, R, compare(R, 'Z', a)).
t(t71, R, compare(R, [a], [a|b])).
t(t72, X, copy_term([A, _B, A|_C], X)).
t(t73, X, functor(X, '.', 2)).
t(t74, X, X =.. ['.', a, []]).
t(t75, X, arg(2, [a], X)).
t(t76, R, compare(R, 1.0, 1)).
t(t77, R, compare(R, 2, 1.5)).
t(t78, x, a @=< a).
t(t79, x, 1 @>= 1.0).
t(t80, R, compare(R, f(Z, b), f(Z, a))).
t(t81, R, compare(R, 1.0e22, 10000000000000000000001)).
t(t82, R, compare(R, 3, 3.0e0)).
t(t83, X, functor(X, foo, 3)).
t(t84, X, (functor(F, foo, 2), arg(1, F, a), X = F)).
t(t85, X, copy_term(X-X, _)).
t(t86, X, term_variables(f(A, B, A, B), X)).
t(t87, R, compare(R, "a", 'a')).
t(t88, R, compare(R, f(1), f(1.0))).
t(t89, X, sort([f(1.0), f(1), f(0.5)], X)).
t(t90, X, (X = f(Y), Y = 1)).
