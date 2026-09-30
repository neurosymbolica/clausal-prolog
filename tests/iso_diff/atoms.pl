% atoms & strings: atom_codes/atom_chars/char_code/sub_atom/atom_concat/
% atom_length/number_codes/number_chars, all modes.
t(a01, X, atom_codes(abc, X)).
t(a02, X, atom_codes(X, [0'a, 0'b])).
t(a03, X, atom_codes(X, [])).
t(a04, X, atom_codes([], X)).
t(a05, X, atom_codes(123, X)).
t(a06, X, atom_codes(_, X)).
t(a07, X, atom_codes(X, [0'a|_])).
t(a08, X, atom_codes(f(a), X)).
t(a09, X, atom_codes(X, [a])).
t(a10, X, atom_chars(X, [a, b])).
t(a11, X, atom_chars(abc, [a|X])).
t(a12, X, atom_chars(X, [a, f(b)])).
t(a13, X, atom_chars('', X)).
t(a14, X, atom_chars(X, ['1', '2'])).
t(a15, X, atom_chars(12, X)).
t(a16, X, char_code(X, 0'a)).
t(a17, X, char_code(a, X)).
t(a18, X, char_code(ab, X)).
t(a19, X, char_code(X, -1)).
t(a20, X, char_code(_, X)).
t(a21, B-L-A-S, sub_atom(abc, B, L, A, S)).
t(a22, B-A, sub_atom(abcab, B, _, A, ab)).
t(a23, S, sub_atom(abc, 1, 1, _, S)).
t(a24, S, sub_atom(abc, _, 2, 0, S)).
t(a25, B-L, sub_atom(abc, B, L, 1, _)).
t(a26, X, sub_atom(abc, 4, _, _, X)).
t(a27, X, sub_atom(abc, -1, _, _, X)).
t(a28, X, sub_atom(_, _, _, _, X)).
t(a29, X, sub_atom(f(x), _, _, _, X)).
t(a30, X, sub_atom(abc, a, _, _, X)).
t(a31, X-Y, atom_concat(X, Y, abc)).
t(a32, X, atom_concat(ab, X, abcd)).
t(a33, X, atom_concat(X, cd, abcd)).
t(a34, X, atom_concat(ab, cd, X)).
t(a35, X, atom_concat(1, 2, X)).
t(a36, X, atom_concat(_, b, X)).
t(a37, X, atom_concat(f(a), b, X)).
t(a38, X-Y, atom_concat(X, Y, '')).
t(a39, X, atom_length(abc, X)).
t(a40, X, atom_length('', X)).
t(a41, X, atom_length(123, X)).
t(a42, X, atom_length(abc, foo)).
t(a43, X, atom_length(abc, -1)).
t(a44, X, number_codes(X, "12")).
t(a45, X, number_codes(X, " 12")).
t(a46, X, number_codes(X, "12 ")).
t(a47, X, number_codes(X, "0x1A")).
t(a48, X, number_codes(X, "0'a")).
t(a49, X, number_codes(X, "-12")).
t(a50, X, number_codes(X, "- 12")).
t(a51, X, number_codes(X, "1.5e3")).
t(a52, X, number_codes(X, "1e3")).
t(a53, X, number_codes(X, "abc")).
t(a54, X, number_codes(12.5, X)).
t(a55, X, number_codes(X, "0b101")).
t(a56, X, number_codes(X, "0o17")).
t(a57, X, number_chars(X, ['1', '.', '0'])).
t(a58, X, number_chars(X, [a])).
t(a59, X, number_chars(X, ['1', _])).
t(a60, X, number_chars(a, X)).
t(a61, X, number_codes(X, "/**/12")).
t(a62, X, number_chars(X, ['+', '1'])).
t(a63, X, atom_chars(X, [])).
t(a64, X, atom_codes(X, [0'a, -1])).
t(a65, X, char_code(X, 0x1F600)).
t(a66, X, atom_length('日本', X)).
t(a67, X, sub_atom('日本語', 1, 1, _, X)).
t(a68, X, atom_chars(X, [a|b])).
t(a69, X, number_codes(X, [])).
t(a70, X, atom_codes(abc, [0'a|X])).
t(a71, X, atom_length(X, 3)).
t(a72, X, number_codes(X, "0.5")).
t(a73, X, number_codes(X, ".5")).
t(a74, X, number_codes(X, "1.0e-2")).
t(a75, X, number_codes(X, "123456789012345678901234567890")).
t(a76, X, atom_concat(abc, X, abc)).
t(a77, B-A-X, sub_atom(abc, B, 2, A, X)).
t(a78, X, number_chars(X, ['0', '''', a])).
t(a79, X, number_codes(X, "1.0E10")).
t(a80, X, atom_chars(X, ['日', a])).
t(a81, B-L-A, sub_atom(abc, B, L, A, abc)).
t(a82, x, sub_atom(abc, _, _, _, ab)).
t(a83, X, atom_length(abc, 1.0)).
t(a84, X, char_code(X, 0)).
t(a85, X, atom_chars(X, "abc")).
t(a86, X, number_codes(X, "0'\\n")).
t(a87, X, number_chars(X, [' ', '1'])).
t(a88, X, number_chars(X, ['\n', '1'])).
t(a89, X, number_codes(X, "%c\n1")).
t(a90, X, number_chars(X, ['1', ' '])).
