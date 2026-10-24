"""ISO term input (ISO 13211-1 §8.14.1) against Scryer: ``read/1,2`` and
``read_term/2,3`` over streams -- the terms read, ``variables/1``,
``variable_names/1``, ``singletons/1``, ``end_of_file``, the layout left
after an end token, syntax errors and the resync after one, the
``double_quotes`` flag, operators, and the error terms.

Rows run as ``tests/iso/test_streams_scryer.py``'s do (see
``tests/iso/_stream_rows.py``).  ``rd(S)`` reads every term of a stream
with the three options and prints them; a syntax error prints as
``syntax_error`` alone (its argument is implementation-defined: Scryer's
``incomplete_reduction``, this engine's message).  Variable names are
normalised, so ``foo(_A,_B,_A)`` compares as ``foo(_,_,_)`` -- the
sharing is pinned by ``tests/test_read_term.py``.
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
rd(S) :-
    catch(read_term(S, T, [variable_names(VN), singletons(Si), variables(Vs)]),
          error(E, _), true),
    (   nonvar(E) ->
        ( E = syntax_error(_) -> p(syntax_error) ; p(E) ), rd(S)
    ;   p(T-VN-Si-Vs), ( T == end_of_file -> true ; rd(S) )
    ).
rd1(S) :-
    catch(read(S, T), error(E, _), true),
    (   nonvar(E) ->
        ( E = syntax_error(_) -> p(syntax_error) ; p(E) ), rd1(S)
    ;   p(T), ( T == end_of_file -> true ; rd1(S) )
    ).
"""

_TERMS = (
    "'foo(X, _Y, _, X, Z). \"str\". end_of_file. f(X :- Y). :- dir. ?- q. "
    "[1|2]. [a,b|T]. 0\\'a. 1.5e3. -1. a- -1. p :- q, r ; s. \\'hello world\\'. "
    "[]. \\'[]\\'. {x,y}. f(A, B, A). \"\". - (1). -(-(1)). 1 + 2 * 3. (a , b). "
    "a =.. b. [x|[y|[z]]]. \\'\\\\n\\'. \"a\\\\\"b\". x('"
)

ROWS = [
    ("terms_and_options",
     f"open(FILE, write, W), write(W, {_TERMS}), close(W), "
     "open(FILE, read, R), rd(R), stream_property(R, end_of_stream(E)), p(E), close(R)"),
    ("layout_after_end_token",
     "open(FILE, write, W), write(W, 'foo(X, Y) :- bar(X). '), close(W), "
     "open(FILE, read, R), read(R, T), p(T), get_char(R, C), p(C), "
     "get_char(R, C2), p(C2), close(R)"),
    ("resync_after_syntax_error",
     "open(FILE, write, W), write(W, 'foo(. bar. )(. baz(1).'), close(W), "
     "open(FILE, read, R), rd1(R), close(R)"),
    ("unterminated_last_term",
     "open(FILE, write, W), write(W, 'foo'), close(W), "
     "open(FILE, read, R), rd1(R), stream_property(R, end_of_stream(E)), p(E), "
     "read(R, T), p(T), close(R)"),
    ("read_2_variable_names",
     "open(FILE, write, W), write(W, 'one. two(X).'), close(W), "
     "open(FILE, read, R), read(R, T1), p(T1), "
     "read_term(R, T2, [variable_names(V)]), p(T2-V), read(R, T3), p(T3), close(R)"),
    ("bound_result",
     "open(FILE, write, W), write(W, 'foo(bar). [a,b|T]. 7. x. '), close(W), "
     "open(FILE, read, R), read(R, T), T = foo(X), p(X), "
     "read(R, L), L = [_, _|Tail], Tail = [c], p(L), "
     "(read(R, 8) -> p(yes) ; p(no)), (read(R, x) -> p(yes) ; p(no)), close(R)"),
    ("eof_actions",
     "open(FILE, write, W), write(W, 'a.'), close(W), "
     "open(FILE, read, R), read(R, T1), p(T1), read(R, T2), p(T2), "
     "stream_property(R, end_of_stream(E1)), p(E1), read(R, T3), p(T3), close(R), "
     "open(FILE, read, R2, [eof_action(error)]), read(R2, U1), p(U1), "
     "read(R2, U2), p(U2), e(read(R2, _)), e(read_term(R2, _, [])), close(R2)"),
    ("read_errors",
     "t(read(_, _)), t(read(user_output, _)), t(read(nostream, _)), "
     "t(read_term(user_output, _, [])), t(read_term(user_input, _, foo)), "
     "t(read_term(user_input, _, [foo])), t(read_term(user_input, _, [_])), "
     "t(read_term(user_input, _, [a|_])), t(read_term(user_input, _, _)), "
     "t(read(1, _)), t(read_term(user_output, _, [variables(_)]))"),
    ("read_from_binary_or_output",
     "open(FILE, write, W, [type(binary)]), e(read(W, _)), close(W), "
     "open(FILE, read, B, [type(binary)]), e(read(B, _)), e(read_term(B, _, [])), close(B), "
     "open(FILE, write, W2), e(read_term(W2, _, [variables(_)])), close(W2)"),
    ("operators_in_force",
     "open(FILE, write, W), write(W, 'a === b. x ^^ y ^^ z. - 1. a = \\\\+ b.'), close(W), "
     "open(FILE, read, R), rd1(R), close(R)"),
]

#: Programs with a double_quotes directive: each reads "abc" under it.
DQ_ROWS = [
    ("chars", "[a,b,c]"),
    ("codes", "[97,98,99]"),
    ("atom", "abc"),
]

#: Rows where Scryer departs from ISO 8.14.1 (the expected lines are the
#: standard's; each comment says what Scryer does).
ISO_ROWS = [
    # 8.14.1.1: at the end of the stream the term is end_of_file -- layout
    # and comments before the end are skipped like any other layout.
    # Scryer raises syntax_error(incomplete_reduction) when only layout
    # remains.
    ("layout_then_end_of_file",
     "open(FILE, write, W), write(W, 'a. \\n% comment\\n /* block */ '), close(W), "
     "open(FILE, read, R), rd1(R), stream_property(R, end_of_stream(E)), p(E), close(R)",
     ["a", "end_of_file", "past"]),
    # 8.11.3: read/1 and read_term/2 read the CURRENT input stream;
    # Scryer's read/1 keeps reading user_input after set_input/1.
    ("read_1_and_current_input",
     "open(FILE, write, W), write(W, 'one. two(X).'), close(W), "
     "open(FILE, read, R), set_input(R), read(T1), p(T1), "
     "read_term(T2, [variable_names(V)]), p(T2-V), read(T3), p(T3), "
     "current_input(S), (S == R -> p(same) ; p(other)), "
     "set_input(user_input), close(R)",
     ["one", "two(_)-['X'=_]", "end_of_file", "same"]),
    # 8.14.1.1: end_of_file has no variables, so the option lists are
    # empty; Scryer leaves them unbound once the stream is past its end.
    ("eof_options_empty",
     "open(FILE, write, W), write(W, 'a.'), close(W), open(FILE, read, R), "
     "read(R, _), read_term(R, T, [variable_names(V), singletons(S), variables(Vs)]), "
     "p(T-V-S-Vs), read_term(R, T2, [variables(Vs2)]), p(T2-Vs2), close(R)",
     ["end_of_file-[]-[]-[]", "end_of_file-[]"]),
    # 8.14.1.3 b: a stream-or-alias that is neither is
    # domain_error(stream_or_alias, S); Scryer: existence_error(stream, f).
    ("read_not_a_stream",
     "t(read_term(f(x), _, [])), t(read(f(x), _))",
     ["domain_error(stream_or_alias,f(x))", "domain_error(stream_or_alias,f(x))"]),
]

DIRECTIVES = """\
:- op(700, xfx, ===).
:- op(200, xfy, ^^).
"""


def _text(name: str, body: str, tmp_path, flags: str = "") -> str:
    return (DIRECTIVES + flags + PRELUDE_EXTRA
            + program(body, file_for(tmp_path, name)))


@pytest.mark.parametrize("name,body", ROWS, ids=[r[0] for r in ROWS])
def test_matches_scryer(name, body, tmp_path, scryer):
    text = _text(name, body, tmp_path)
    ours = normalise(run_clausal(tmp_path, f"read_{name}", text))
    theirs = normalise(run_oracle(tmp_path, f"read_{name}", text))
    assert theirs, "Scryer printed nothing (load error?)"
    assert ours == theirs


@pytest.mark.parametrize("flag,expected", DQ_ROWS, ids=[r[0] for r in DQ_ROWS])
def test_double_quotes_flag(flag, expected, tmp_path, scryer):
    body = ("open(FILE, write, W), write(W, '\"abc\". '), close(W), "
            "open(FILE, read, R), read(R, T), p(T), close(R)")
    text = _text(f"dq_{flag}", body, tmp_path,
                 flags=f":- set_prolog_flag(double_quotes, {flag}).\n")
    ours = normalise(run_clausal(tmp_path, f"read_dq_{flag}", text))
    theirs = normalise(run_oracle(tmp_path, f"read_dq_{flag}", text))
    assert ours == [expected]
    assert theirs == [expected]


@pytest.mark.parametrize("name,body,expected", ISO_ROWS, ids=[r[0] for r in ISO_ROWS])
def test_iso_rows(name, body, expected, tmp_path):
    text = _text(name, body, tmp_path)
    ours = normalise(run_clausal(tmp_path, f"read_{name}", text))
    assert ours == expected
