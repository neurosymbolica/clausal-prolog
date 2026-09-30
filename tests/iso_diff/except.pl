% catch/throw and the error terms of common misuse.
t(x01, E, catch(atom_length(_, _), E, true)).
t(x02, E, catch(atom_length(f(x), _), E, true)).
t(x03, E, catch(call(1), E, true)).
t(x04, E, catch(call((true, 1)), E, true)).
t(x05, E, catch(call(_), E, true)).
t(x06, E, catch(undefined_pred_xyz, E, true)).
t(x07, X, catch(throw(my), X, true)).
t(x08, Z, catch(throw(f(_)), f(Z), true)).
t(x09, E, catch(throw(_), E, true)).
t(x10, E, catch(number_codes(_, "3x"), E, true)).
t(x11, E, catch(_ is foo + 1, E, true)).
t(x12, E, catch(arg(x, f(a), _), E, true)).
t(x13, E, catch(functor(_, _, _), E, true)).
t(x14, E, catch(atom_codes(_, _), E, true)).
t(x15, E, catch((X = 1, throw(X)), E, true)).
t(x16, E, catch(catch(throw(a), b, true), E, true)).
t(x17, x, catch(throw(a), a, fail)).
t(x18, X, catch(member(X, [1, 2]), _, true)).
t(x19, Y, catch((member(X, [1, 2, 3]), X >= 2, throw(x(X))), x(Y), true)).
t(x20, E, catch(sub_atom(abc, _, _, _, 1), E, true)).
t(x21, E, catch(char_code(_, a), E, true)).
t(x22, E, catch(_ =.. [f|a], E, true)).
t(x23, E, catch(call(foo_undefined, 1), E, true)).
t(x24, E, catch(length(_, -1), E, true)).
t(x25, E, catch(length(a, _), E, true)).
t(x26, E, catch(length(_, a), E, true)).
t(x27, E, catch(atom_length(1, _), E, true)).
t(x28, E, catch(number_codes(_, [0'1|_]), E, true)).
t(x29, E, catch(findall(_, _, _), E, true)).
t(x30, E, catch(findall(_, 1, _), E, true)).
t(x31, E, catch(setof(X, foo_unknown(X), _), E, true)).
t(x32, E, catch(atom_length(abc, 1.0), E, true)).
t(x33, E, catch(number_codes(_, "a"), E, true)).
t(x34, E, catch(atom_chars(_, [a|_]), E, true)).
t(x35, E, catch(_ is 1 / 0, E, true)).
t(x36, E, catch(call(foo:bar), E, true)).
t(x37, E, catch(atom_concat(a, _, _), E, true)).
t(x38, E, catch(sub_atom(abc, _, _, _, f(x)), E, true)).
t(x39, E, catch(_ =.. foo, E, true)).
t(x40, E, catch(copy_term(_, _), E, true)).
t(x41, E, catch(\+ 1, E, true)).
t(x42, E, catch(once(1), E, true)).
t(x43, E, catch(call((fail, 1)), E, true)).
t(x44, E, catch(call((fail ; 1)), E, true)).
t(x45, E, catch(catch(throw(a), E0, throw(b(E0))), E, true)).
t(x46, E, catch(number_chars(_, ['1', a]), E, true)).
t(x47, E, catch(atom_codes(_, [-1]), E, true)).
t(x48, E, catch(char_code(_, -1), E, true)).
t(x49, E, catch(functor(_, foo, -1), E, true)).
t(x50, E, catch(functor(_, f(a), 1), E, true)).
t(x51, E, catch(arg(0, _, _), E, true)).
t(x52, E, catch(msort(a, _), E, true)).
t(x53, E, catch(keysort([a], _), E, true)).
t(x54, E, catch(succ(_, _), E, true)).
t(x55, E, catch(between(1, a, _), E, true)).
t(x56, E, catch(atom_length(_, foo), E, true)).
t(x57, E, catch(throw(error(type_error(integer, a), ctx)), E, true)).
t(x58, E, catch(nth0(a, [x], _), E, true)).
t(x59, E, catch(sum_list([a], _), E, true)).
t(x60, E, catch(call(1, a), E, true)).
