"""ISO stream I/O (ISO 13211-1 §8.11-8.13) against Scryer: ``open/3,4``,
``close/1,2``, the current streams, ``stream_property/2``,
``set_stream_position/2``, the char/code/byte predicates, ``nl/1`` and the
writers' stream forms.

Each row is a ``.pl`` program (``tests/iso/_stream_rows.py``) run under
Clausal in-process and under Scryer, stdout compared.  ``t(G)`` prints
``ok``/``failed`` or the error's formal term; ``e(G)`` prints the formal
term without its last argument -- for errors whose culprit is a stream
term, which the two systems spell differently (``'$stream'(3)`` here,
``'$stream'(0x...)`` there).  Rows where the Scryer build departs from the
standard's text are in ``ISO_ROWS`` with the ISO answer spelled out (each
says what Scryer answers instead).
"""

from __future__ import annotations

import pytest

from tests.iso._stream_rows import (
    file_for, normalise, program, run_clausal, run_oracle,
)

PRELUDE_EXTRA = """\
:- use_module(library(lists)).
e(G) :- catch((G -> write(ok) ; write(failed)), error(E, _),
              (E =.. L, append(L0, [_], L), writeq(L0))), nl.
chars(S, Cs) :- get_char(S, C),
    ( C == end_of_file -> Cs = [] ; Cs = [C|Cs1], chars(S, Cs1) ).
"""

ROWS = [
    ("open_instantiation",
     "t(open(_, read, _)), t(open(f, _, _)), t(open(f, read, _, _)), "
     "t(open(f, read, _, [_])), t(open(f, read, _, [a|_]))"),
    ("open_types",
     "t(open(1, read, _)), t(open(f, 1, _)), t(open(f, foo, _)), "
     "t(open(f, read, s)), t(open(f, read, _, foo))"),
    ("open_options",
     "t(open(f, read, _, [foo])), t(open(f, read, _, [type(foo)])), "
     "t(open(f, read, _, [alias(1)])), t(open(f, read, _, [eof_action(foo)])), "
     "t(open(f, read, _, [reposition(1)]))"),
    ("open_alias_in_use",
     "open(FILE, write, W), close(W), "
     "t(open(FILE, read, _, [alias(user_input)])), "
     "open(FILE, read, _, [alias(myal)]), "
     "t(open(FILE, read, _, [alias(myal)])), close(myal), "
     "open(FILE, read, R, [alias(myal)]), t(stream_property(R, alias(myal))), close(R)"),
    ("close_errors",
     "t(close(_)), t(close(foo)), t(close(1)), t(close(user_input)), "
     "t(close(user_output, _)), t(close(user_output, [foo])), "
     "t(close(user_output, [force(1)])), t(close(user_output, foo)), "
     "t(close(user_output, [force(true)])), t(close(user_error, [force(false)]))"),
    ("set_input_output_errors",
     "t(set_input(_)), t(set_input(foo)), t(set_output(_)), t(set_output(1)), "
     "t(set_output(nostream))"),
    ("current_input_output",
     "t(current_input(foo)), t(current_input(1)), t(current_input(f(x))), "
     "t(current_output(user_output)), t(current_input(_)), t(current_output(_))"),
    ("flush_output",
     "t(flush_output(user_input)), t(flush_output(_)), t(flush_output(nostream)), "
     "t(flush_output(user_output)), t(flush_output), t(flush_output(1))"),
    ("at_end_of_stream_errors",
     "t(at_end_of_stream(user_output)), t(at_end_of_stream(_)), "
     "t(at_end_of_stream(nostream)), t(at_end_of_stream(1))"),
    ("stream_property_errors",
     "t(stream_property(_, foo)), t(stream_property(_, f(x))), "
     "t(stream_property(foo, _)), t(stream_property(user_input, foo(_)))"),
    ("stream_property_standard",
     "t(stream_property(user_input, alias(user_input))), "
     "t(stream_property(_, alias(user_output))), "
     "t(stream_property(user_output, type(text))), "
     "t(stream_property(user_output, eof_action(eof_code))), "
     "t(stream_property(user_input, reposition(false))), "
     "t(stream_property(user_input, end_of_stream(not))), "
     "t(stream_property(user_input, file_name(_))), "
     "t(stream_property(user_input, input)), t(stream_property(user_input, output)), "
     "t(stream_property(user_output, output)), t(stream_property(user_error, output))"),
    ("set_stream_position_errors",
     "t(set_stream_position(user_input, _)), t(set_stream_position(user_input, foo)), "
     "t(set_stream_position(_, foo)), t(set_stream_position(nostream, foo))"),
    ("get_char_errors",
     "t(get_char(user_output, _)), t(get_char(_, _)), t(get_char(nostream, _)), "
     "t(get_char(user_input, 1)), t(get_char(user_input, ab)), "
     "t(peek_char(user_output, _)), t(peek_char(user_input, 1)), t(peek_char(user_input, f(x)))"),
    ("get_code_errors",
     "t(get_code(user_input, a)), t(get_code(user_input, -2)), "
     "t(peek_code(user_input, -2)), t(get_code(user_input, 1.0)), "
     "t(get_code(user_output, _)), t(peek_code(nostream, _))"),
    ("byte_errors",
     "t(get_byte(user_input, a)), t(get_byte(user_input, _)), "
     "t(peek_byte(user_output, _)), t(peek_byte(user_input, _)), "
     "t(put_byte(_)), t(put_byte(a)), t(put_byte(256)), t(put_byte(user_output, 65)), "
     "t(put_byte(user_input, 65)), t(put_byte(nostream, 65)), t(put_byte(_, 65))"),
    ("put_char_put_code_errors",
     "t(put_char(_)), t(put_char(user_output, _)), t(put_char(1)), t(put_char(ab)), "
     "t(put_char(user_input, a)), t(put_char(nostream, a)), t(put_char(_, a)), "
     "t(put_code(_)), t(put_code(a)), t(put_code(-1)), t(put_code(0x110000)), "
     "t(put_code(user_input, 97)), t(put_code(user_output, _))"),
    ("nl_errors",
     "t(nl(_)), t(nl(user_input)), t(nl(nostream)), t(nl(1)), t(nl(user_error))"),
    ("writer_errors",
     "t(write(_, a)), t(write(user_input, a)), t(write(nostream, a)), t(writeq(1, a)), "
     "t(write_term(user_input, a, [])), t(write_term(user_output, a, foo)), "
     "t(write_term(user_output, a, [foo])), t(write_canonical(nostream, a)), "
     "t(write_canonical(_, a)), t(writeq(user_input, a))"),
    ("writers_on_user_output",
     "write(user_output, hello), nl(user_output), writeq(user_output, 'A b'), "
     "nl(user_output), write_canonical(user_output, [a,'B']), nl(user_output), "
     "write_term(user_output, 'a b', [quoted(true)]), nl(user_output), "
     "put_char(user_output, x), put_char(y), put_code(0'z), put_code(user_output, 0'!), "
     "nl, current_output(S), write(S, via_s), nl(S), "
     "set_output(user_output), write(still), nl, flush_output(user_output)"),
    ("text_file_round_trip",
     "open(FILE, write, W), write(W, foo(a, 'A', \"str\")), nl(W), "
     "writeq(W, 'hello world'), put_char(W, '.'), nl(W), put_code(W, 0'q), "
     "write_canonical(W, [x|y]), write_term(W, 'a b', [quoted(true)]), close(W), "
     "open(FILE, read, R), get_char(R, C1), p(C1), peek_char(R, C2), p(C2), "
     "get_char(R, C3), p(C3), get_code(R, C4), p(C4), peek_code(R, C5), p(C5), "
     "chars(R, Cs), p(Cs), stream_property(R, end_of_stream(E)), p(E), "
     "get_char(R, C6), p(C6), peek_char(R, C7), p(C7), "
     "(at_end_of_stream(R) -> p(yes) ; p(no)), close(R)"),
    ("text_file_get_code_at_end",
     "open(FILE, write, W), write(W, ab), close(W), "
     "open(FILE, read, R), get_char(R, C1), p(C1), get_char(R, C2), p(C2), "
     "stream_property(R, end_of_stream(E1)), p(E1), (at_end_of_stream(R) -> p(yes) ; p(no)), "
     "get_code(R, C3), p(C3), stream_property(R, end_of_stream(E2)), p(E2), close(R)"),
    ("binary_file_round_trip",
     "open(FILE, write, B, [type(binary)]), put_byte(B, 65), put_byte(B, 0), "
     "put_byte(B, 255), e(put_byte(B, 256)), e(put_byte(B, a)), e(put_byte(B, _)), "
     "e(put_char(B, a)), e(put_code(B, 97)), e(nl(B)), e(write(B, a)), e(writeq(B, a)), "
     "e(write_canonical(B, a)), e(write_term(B, a, [])), "
     "t(stream_property(B, type(binary))), t(stream_property(B, mode(write))), "
     "t(stream_property(B, input)), t(stream_property(B, output)), "
     "t(stream_property(B, alias(_))), t(stream_property(B, file_name(FILE))), "
     "t(stream_property(B, end_of_stream(not))), e(get_byte(B, _)), "
     "close(B), "
     "open(FILE, read, B2, [type(binary)]), get_byte(B2, X1), p(X1), "
     "peek_byte(B2, X2), p(X2), get_byte(B2, X3), p(X3), get_byte(B2, X4), p(X4), "
     "e(get_char(B2, _)), e(peek_char(B2, _)), e(get_code(B2, _)), e(read(B2, _)), "
     "e(get_byte(B2, a)), e(get_byte(B2, 256)), e(peek_byte(B2, 1.0)), "
     "stream_property(B2, end_of_stream(E1)), p(E1), get_byte(B2, X5), p(X5), "
     "stream_property(B2, end_of_stream(E2)), p(E2), get_byte(B2, X6), p(X6), "
     "peek_byte(B2, X7), p(X7), t(at_end_of_stream(B2)), close(B2)"),
    ("eof_action_error",
     "open(FILE, write, W, [type(binary)]), put_byte(W, 65), put_byte(W, 66), close(W), "
     "open(FILE, read, R, [type(binary), eof_action(error)]), "
     "t(stream_property(R, eof_action(error))), "
     "get_byte(R, Y1), p(Y1), get_byte(R, Y2), p(Y2), peek_byte(R, Y3), p(Y3), "
     "stream_property(R, end_of_stream(E3)), p(E3), t(at_end_of_stream(R)), "
     "get_byte(R, Y4), p(Y4), stream_property(R, end_of_stream(E4)), p(E4), "
     "e(get_byte(R, _)), e(peek_byte(R, _)), close(R)"),
    ("eof_action_eof_code_text",
     "open(FILE, write, W), write(W, a), close(W), "
     "open(FILE, read, R, [eof_action(eof_code)]), get_char(R, C1), p(C1), "
     "get_char(R, C2), p(C2), get_char(R, C3), p(C3), peek_char(R, C4), p(C4), "
     "stream_property(R, end_of_stream(E)), p(E), close(R)"),
    ("reposition_text",
     "open(FILE, write, W), write(W, ab), nl(W), close(W), "
     "open(FILE, read, R, [reposition(true)]), t(stream_property(R, reposition(true))), "
     "get_char(R, C1), p(C1), stream_property(R, position(P1)), "
     "get_char(R, C2), p(C2), set_stream_position(R, P1), get_char(R, C3), p(C3), "
     "peek_char(R, C4), p(C4), get_char(R, C5), p(C5), peek_char(R, C6), p(C6), "
     "get_char(R, C7), p(C7), stream_property(R, end_of_stream(E4)), p(E4), "
     "peek_char(R, C8), p(C8), get_char(R, C9), p(C9), "
     "set_stream_position(R, P1), get_char(R, C12), p(C12), "
     "stream_property(R, end_of_stream(E6)), p(E6), e(set_stream_position(R, foo)), "
     "close(R), "
     "open(FILE, append, A), t(stream_property(A, mode(append))), "
     "t(stream_property(A, reposition(false))), e(set_stream_position(A, P1)), "
     "t(at_end_of_stream(A)), write(A, more), close(A), "
     "open(FILE, read, R2), chars(R2, Cs), p(Cs), close(R2)"),
    ("alias_and_current_input",
     "open(FILE, write, W), write(W, ab), close(W), "
     "open(FILE, read, _, [alias(foo)]), t(stream_property(_, alias(foo))), "
     "t(stream_property(foo, alias(foo))), t(stream_property(foo, mode(read))), "
     "get_char(foo, D1), p(D1), set_input(foo), peek_code(D2), p(D2), "
     "get_code(D3), p(D3), peek_char(D4), p(D4), get_char(D5), p(D5), "
     "(at_end_of_stream -> p(yes) ; p(no)), close(foo), "
     "t(current_input(user_input))"),
    ("write_to_input_stream",
     "open(FILE, write, W), close(W), open(FILE, read, R), "
     "e(write(R, a)), e(nl(R)), e(put_char(R, a)), e(flush_output(R)), "
     "e(set_output(R)), e(put_byte(R, 1)), close(R), "
     "open(FILE, write, W2), e(get_char(W2, _)), e(set_input(W2)), e(peek_byte(W2, _)), "
     "e(read(W2, _)), t(at_end_of_stream(W2)), close(W2)"),
    ("open_existence_and_permission",
     "open(FILE, write, W), close(W), "
     "t(open(FILE, read, S1)), close(S1), t(open(FILE, append, S2)), close(S2), "
     "t(open(FILE, write, S3, [type(text), eof_action(reset), reposition(false)])), "
     "t(stream_property(S3, reposition(false))), t(stream_property(S3, eof_action(reset))), "
     "close(S3)"),
]

#: Rows whose Scryer answer departs from ISO 13211-1's text; the expected
#: lines are the standard's.  (Scryer's answer is in each comment.)
ISO_ROWS = [
    # 8.11.6.3 b: a compound that is not a stream term is
    # domain_error(stream_or_alias, S); Scryer: existence_error(stream, f).
    ("close_compound",
     "t(close(f(x))), t(write_canonical(f(x), a)), t(nl(f(x))), "
     "t(set_input(f(x))), t(stream_property(f(x), _))",
     ["domain_error(stream_or_alias,f(x))", "domain_error(stream_or_alias,f(x))",
      "domain_error(stream_or_alias,f(x))", "domain_error(stream_or_alias,f(x))",
      "domain_error(stream,f(x))"]),
    # 8.11.3.3 d / 8.11.4.3 d: the culprit is the stream given; Scryer
    # names it `user`.
    ("set_input_output_direction",
     "t(set_input(user_output)), t(set_output(user_input)), t(set_input(user_error))",
     ["permission_error(input,stream,user_output)",
      "permission_error(output,stream,user_input)",
      "permission_error(input,stream,user_error)"]),
    # 7.10.2.11: user_output is opened for append; Scryer says write.
    ("standard_stream_modes",
     "stream_property(user_input, mode(M1)), p(M1), "
     "stream_property(user_output, mode(M2)), p(M2), "
     "stream_property(user_error, mode(M3)), p(M3)",
     ["read", "append", "append"]),
    # 8.11.5.3 h / i: the culprit is the source/sink as given (an atom);
    # Scryer prints it as the list of its characters.
    ("open_missing_file",
     "t(open(FILE, read, _)), t(open(FILE, read, _, [type(binary)]))",
     ["existence_error(source_sink,FILE)", "existence_error(source_sink,FILE)"]),
    ("open_directory",
     "t(open('/', write, _)), t(open('/', read, _))",
     ["permission_error(open,source_sink,/)", "existence_error(source_sink,/)"]),
    # 8.11.4: set_output(user_output) makes user_output the current output
    # again; in Scryer the output stays on the file until it is closed.
    ("set_output_to_file",
     "open(FILE, write, W), set_output(W), write(hello), nl, writeq('A'), "
     "write([a]), put_char(x), put_code(0'y), tab(2), "
     "set_output(user_output), close(W), "
     "open(FILE, read, R), chars(R, Cs), p(Cs), close(R)",
     ["[h,e,l,l,o,'\\n','\\'','A','\\'','[',a,']',x,y,' ',' ']"]),
    # 8.11.6.1: closing the current output (input) stream makes user_output
    # (user_input) current; Scryer keeps writing to the closed file.
    ("close_resets_current_output",
     "open(FILE, write, W), set_output(W), write(to_file), close(W), "
     "write(back), nl, current_output(S), stream_property(S, alias(A)), p(A), "
     "open(FILE, read, R), set_input(R), close(R), "
     "current_input(S2), stream_property(S2, alias(A2)), p(A2), "
     "t(set_input(R)), t(close(R)), t(get_char(R, _))",
     ["back", "user_output", "user_input", "existence_error(stream,'$stream'(_))",
      "existence_error(stream,'$stream'(_))", "existence_error(stream,'$stream'(_))"]),
    # 8.11.6.1 / 8.11.3.3 c: a closed stream's alias names nothing any more;
    # Scryer still answers through it.
    ("closed_alias",
     "open(FILE, write, W, [alias(out)]), write(out, x), close(out), "
     "t(set_output(out)), t(close(out)), t(write(out, y)), t(stream_property(out, _)), "
     "t(open(FILE, read, _, [alias(out)]))",
     ["existence_error(stream,out)", "existence_error(stream,out)",
      "existence_error(stream,out)", "existence_error(stream,out)", "ok"]),
    # 8.11.8.3 a: S is neither a variable nor a stream term ->
    # domain_error(stream, S); Scryer: domain_error(stream_or_alias, 1).
    ("stream_property_not_a_stream",
     "t(stream_property(1, _)), t(stream_property(f(x), input))",
     ["domain_error(stream,1)", "domain_error(stream,f(x))"]),
]


def _run(tmp_path, name: str, body: str) -> tuple:
    text = PRELUDE_EXTRA + program(body, file_for(tmp_path, name))
    return text, normalise(run_clausal(tmp_path, f"streams_{name}", text))


@pytest.mark.parametrize("name,body", ROWS, ids=[r[0] for r in ROWS])
def test_matches_scryer(name, body, tmp_path, scryer):
    text, ours = _run(tmp_path, name, body)
    theirs = normalise(run_oracle(tmp_path, f"streams_{name}", text))
    assert theirs, "Scryer printed nothing (load error?)"
    assert ours == theirs


@pytest.mark.parametrize("name,body,expected", ISO_ROWS, ids=[r[0] for r in ISO_ROWS])
def test_iso_rows(name, body, expected, tmp_path):
    _, ours = _run(tmp_path, name, body)
    file_path = file_for(tmp_path, name)
    expected = [line.replace("FILE", f"'{file_path}'") for line in expected]
    assert ours == expected
