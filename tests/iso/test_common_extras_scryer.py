"""The common non-ISO extras: sort/4, predsort/3, print/1, atom_string/2,
term_to_atom/2 and atom_to_term/3.

Scryer has none of the six (each is ``existence_error(procedure, _)``
there; ``test_oracle_lacks_them`` pins that), so they are defined as
SWI-Prolog defines them -- its manual and, where the manual is silent, its
source (``src/pl-list.c`` sort/4, ``library(sort)`` predsort/3,
``src/pl-string.c`` atom_string/2, ``src/pl-read.c`` term_to_atom/2 and
atom_to_term/3).  A string in Clausal is the chars carrier, the list of its
characters, as it is in Scryer; SWI's own string type has no counterpart.

Each ROW is one goal binding ``R``.  The ENGINE half runs every row in a
``.pl`` module and in a ``.clausal`` module, through one driver clause
written in ISO Prolog that prints each answer with ``writeq/1`` (or the
error term the goal raises).  Where Scryer can compute the same answer
through ISO builtins (``sort/2``, ``msort/2``, ``keysort/2``, ``writeq/1``,
``library(charsio)``), the row carries that goal too and the ORACLE half
runs it, through the same driver text, in Scryer: both must print the
row's expected column.  The rows without a Scryer goal are pinned from the
SWI definition.  Variables are compared by their sharing, as in
``test_iso_answers_scryer.py``.
"""

from __future__ import annotations

import contextlib
import io
import os
import re
import tempfile
import textwrap

import pytest

import clausal.import_hook  # noqa: F401 -- installs the meta-path finder
from clausal._suffixes import PROLOG_SUFFIX
from clausal.import_hook import _load_module
from clausal.logic.solve import solve

from .conftest import run_scryer

CLAUSAL_PROLOG = ".clausal"

_VAR = re.compile(r"(?<![\w'])_[A-Za-z0-9_]*")


def _normalise(line: str) -> str:
    names = _VAR.findall(line)
    counts = {n: names.count(n) for n in names if n != "_"}
    order: dict[str, str] = {}

    def rename(m):
        n = m.group(0)
        if n == "_" or counts.get(n, 0) < 2:
            return "_"
        if n not in order:
            order[n] = f"_{len(order) + 1}"
        return order[n]
    return _VAR.sub(rename, line)


#: Helper predicates both engines load (plain ISO Prolog).
HELPERS = """\
by_length(O, A, B) :- atom_length(A, LA), atom_length(B, LB), compare(O, LA, LB).
reversed(O, A, B) :- compare(O, B, A).
on_arg(N, O, A, B) :- arg(N, A, X), arg(N, B, Y), compare(O, X, Y).
either_way(O, A, B) :- compare(O, A, B).
either_way(O, A, B) :- compare(O, B, A).
any_order(_, _, _).
never(_, _, _) :- fail.
bad_delta(foo, _, _).
key_pair(N, E, K-E) :- arg(N, E, K).
self_pair(E, E-E).
"""

#: The driver: one ``row(I)`` clause per row (appended below).  Each prints
#: ``ROW I``, then ``A <answer>`` per answer (``A <error>`` for an error) and
#: ``O <line>`` for a line the goal itself printed.
DRIVER = """\
run_row(I, G, R) :-
    write('ROW '), write(I), nl,
    catch(( call(G), nl, write('A '), writeq(R), nl, fail ; true ),
          E, ( nl, write('A '), writeq(E), nl )).
"""

S = "error(syntax_error(_),_)"   # a syntax error, whatever its kind


def syntax(goal: str) -> str:
    """*goal*, with a syntax error it raises answered as ``R = syntax``."""
    return f"catch(({goal}), {S}, R = syntax)"


#: (id, engine goal, Scryer goal or None, expected answers)
ROWS = [
    # ── sort/4 ──────────────────────────────────────────────────────────
    ("sort4_asc_dedup", "sort(0, @<, [c,a,b,a], R)",
     "sort([c,a,b,a], R)", ["[a,b,c]"]),
    ("sort4_asc_keep", "sort(0, @=<, [c,a,b,a], R)",
     "maplist(self_pair, [c,a,b,a], Ps), keysort(Ps, S), pairs_values(S, R)", ["[a,a,b,c]"]),
    ("sort4_desc_dedup", "sort(0, @>, [c,a,b,a], R)",
     "sort([c,a,b,a], S), reverse(S, R)", ["[c,b,a]"]),
    ("sort4_desc_keep", "sort(0, @>=, [c,a,b,a], R)",
     "maplist(self_pair, [c,a,b,a], Ps), keysort(Ps, S), pairs_values(S, V), "
     "reverse(V, R)", ["[c,b,a,a]"]),
    # (Scryer's own sort/2 raises type_error(list, L) on an atom followed by
    # a float in a consulted clause, ``sort([b, 1.0], R)``: the order here
    # keeps the row off that.)
    ("sort4_standard_order", "sort(0, @<, [f(x), 2, 1.0, b], R)",
     "sort([f(x), 2, 1.0, b], R)", ["[1.0,2,b,f(x)]"]),
    ("sort4_float_before_equal_int", "sort(0, @=<, [1, a, 1.0], R)", None,
     ["[1.0,1,a]"]),
    ("sort4_string_is_its_chars", 'sort(0, @<, "cab", R)',
     'sort("cab", R)', ["[a,b,c]"]),
    ("sort4_key_keep_is_keysort", "sort(1, @=<, [f(2,a),f(1,b),f(2,c)], R)",
     "maplist(key_pair(1), [f(2,a),f(1,b),f(2,c)], Ps), keysort(Ps, S), "
     "pairs_values(S, R)", ["[f(1,b),f(2,a),f(2,c)]"]),
    ("sort4_key_dedup_keeps_first", "sort(1, @<, [f(2,a),f(1,b),f(2,c)], R)",
     None, ["[f(1,b),f(2,a)]"]),
    ("sort4_key_desc_stable", "sort(1, @>=, [f(2,a),f(1,b),f(2,c)], R)",
     None, ["[f(2,a),f(2,c),f(1,b)]"]),
    ("sort4_key_desc_dedup", "sort(1, @>, [f(2,a),f(1,b),f(2,c)], R)",
     None, ["[f(2,a),f(1,b)]"]),
    ("sort4_second_arg", "sort(2, @<, [f(2,b),f(1,a),f(3,b)], R)",
     None, ["[f(1,a),f(2,b)]"]),
    ("sort4_key_path", "sort([1,2], @<, [f(g(1,b)), f(g(2,a))], R)",
     None, ["[f(g(2,a)),f(g(1,b))]"]),
    ("sort4_plain_order_atoms", "sort(0, <, [b,a,b], R)", None, ["[a,b]"]),
    ("sort4_plain_order_atoms_desc", "sort(0, >=, [1,2,1], R)", None,
     ["[2,1,1]"]),
    ("sort4_empty", "sort(1, @<, [], R)", None, ["[]"]),
    ("sort4_sorted_bound", "sort(0, @<, [b,a], [a,b]), R = yes", None,
     ["yes"]),
    ("sort4_sorted_mismatch", "sort(0, @<, [b,a], [b|R])", None, []),
    ("sort4_key_unbound", "sort(_, @<, [a], R)", None,
     ["error(instantiation_error,sort/4)"]),
    ("sort4_key_float", "sort(1.5, @<, [a], R)", None,
     ["error(type_error(sort_key,1.5),sort/4)"]),
    ("sort4_key_negative", "sort(-1, @<, [a], R)", None,
     ["error(domain_error(not_less_than_one,-1),sort/4)"]),
    ("sort4_key_path_zero", "sort([1,0], @<, [f(a)], R)", None,
     ["error(domain_error(not_less_than_one,0),sort/4)"]),
    ("sort4_atom_key_on_compound", "sort(k, @<, [f(1)], R)", None,
     ["error(type_error(dict,f(1)),sort/4)"]),
    ("sort4_order_unbound", "sort(0, _, [a], R)", None,
     ["error(instantiation_error,sort/4)"]),
    ("sort4_order_not_atom", "sort(0, 1, [a], R)", None,
     ["error(type_error(atom,1),sort/4)"]),
    ("sort4_order_unknown", "sort(0, foo, [a], R)", None,
     ["error(domain_error(order,foo),sort/4)"]),
    ("sort4_key_checked_first", "sort(_, foo, bar, R)", None,
     ["error(instantiation_error,sort/4)"]),
    ("sort4_order_checked_before_list", "sort(1, foo, bar, R)", None,
     ["error(domain_error(order,foo),sort/4)"]),
    ("sort4_partial_list", "sort(0, @<, [a|_], R)", None,
     ["error(instantiation_error,sort/4)"]),
    ("sort4_not_a_list", "sort(0, @<, foo, R)", None,
     ["error(type_error(list,foo),sort/4)"]),
    ("sort4_element_not_compound", "sort(1, @<, [f(1), a], R)", None,
     ["error(type_error(compound,a),sort/4)"]),
    ("sort4_single_element_checked", "sort(1, @<, [a], R)", None,
     ["error(type_error(compound,a),sort/4)"]),
    ("sort4_arity_too_small", "sort(2, @<, [f(1)], R)", None,
     ["error(existence_error(argument,2,f(1)),sort/4)"]),
    # ── predsort/3 ──────────────────────────────────────────────────────
    ("predsort_compare_is_sort", "predsort(compare, [c,a,b,a,c], R)",
     "sort([c,a,b,a,c], R)", ["[a,b,c]"]),
    ("predsort_numbers", "predsort(compare, [3,1,2,1.0], R)",
     "sort([3,1,2,1.0], R)", ["[1.0,1,2,3]"]),
    ("predsort_equal_drops", "predsort(by_length, [abc,a,de,xy], R)", None,
     ["[a,de,abc]"]),
    ("predsort_reversed", "predsort(reversed, [1,3,2], R)", None,
     ["[3,2,1]"]),
    ("predsort_closure", "predsort(on_arg(1), [f(2,x),f(1,y)], R)", None,
     ["[f(1,y),f(2,x)]"]),
    ("predsort_empty", "predsort(compare, [], R)", None, ["[]"]),
    ("predsort_one_not_compared", "predsort(never, [a], R)", None, ["[a]"]),
    ("predsort_comparator_fails", "predsort(never, [a,b], R)", None, []),
    ("predsort_bad_delta_fails", "predsort(bad_delta, [a,b], R)", None, []),
    ("predsort_every_comparator_answer", "predsort(either_way, [b,a], R)",
     None, ["[a,b]", "[b,a]"]),
    ("predsort_unbound_delta", "predsort(any_order, [a,b], R)", None,
     ["[a,b]", "[a]", "[b,a]"]),
    ("predsort_partial_list", "predsort(compare, [a|_], R)", None,
     ["error(instantiation_error,predsort/3)"]),
    ("predsort_not_a_list", "predsort(compare, foo, R)", None,
     ["error(type_error(list,foo),predsort/3)"]),
    # ── print/1: writeq, i.e. write_term(T, [portray(true),
    #    numbervars(true), quoted(true)]) with no portray hook ─────────────
    ("print_quoted", "print(f('A', 'b c', [x])), R = x",
     "writeq(f('A', 'b c', [x])), R = x", ["O f('A','b c',[x])", "x"]),
    ("print_numbervars", "print(g('$VAR'(1), '$VAR'(27))), R = x",
     "writeq(g('$VAR'(1), '$VAR'(27))), R = x", ["O g(B,B1)", "x"]),
    ("print_string_is_chars", 'print("ab"), R = x',
     'writeq("ab"), R = x', ["O [a,b]", "x"]),
    ("print_operators", "print(1-(2*3)+(-(1))), R = x",
     "writeq(1-(2*3)+(-(1))), R = x", ["O 1-2*3+ - (1)", "x"]),
    ("print_curly_and_tail", "print({a,[b|c]}), R = x",
     "writeq({a,[b|c]}), R = x", ["O {a,[b|c]}", "x"]),
    # ── term_to_atom/2 ──────────────────────────────────────────────────
    ("t2a_write_quoted", "term_to_atom(f(x,'A',\"s\",1+2), R)",
     "write_term_to_chars(f(x,'A',\"s\",1+2), [quoted(true)], Cs), "
     "atom_chars(R, Cs)", ["'f(x,\\'A\\',[s],1+2)'"]),
    ("t2a_write_quoted_atom", "term_to_atom('hello world', R)",
     "write_term_to_chars('hello world', [quoted(true)], Cs), "
     "atom_chars(R, Cs)", ["'\\'hello world\\''"]),
    ("t2a_parse", "term_to_atom(R, 'foo(X,Y,X)')",
     "atom_chars('foo(X,Y,X).', Cs), read_term_from_chars(Cs, R, [])",
     ["foo(_1,_,_1)"]),
    ("t2a_parse_list_and_ops", "term_to_atom(R, '[1,2|T]-a:b')",
     "atom_chars('[1,2|T]-a:b.', Cs), read_term_from_chars(Cs, R, [])",
     ["[1,2|_]-a:b"]),
    ("t2a_parse_double_quotes", "term_to_atom(R, '\"ab\"')",
     "atom_chars('\"ab\".', Cs), read_term_from_chars(Cs, R, [])",
     ["[a,b]"]),
    ("t2a_variables_shared", "term_to_atom(f(X,_,X), A), R = A", None,
     ["'f(_1,_,_1)'"]),
    ("t2a_both_unbound_writes_the_variable",
     "term_to_atom(_, A), atom_chars(A, [R|_])", None, ["'_'"]),
    ("t2a_parse_then_unify", "term_to_atom(f(X), 'f(a)'), R = X", None,
     ["a"]),
    ("t2a_atom_bound_wins", "term_to_atom(f(b), 'f(a)'), R = x", None, []),
    ("t2a_parse_trailing_end", "term_to_atom(R, 'foo(X). ')", None,
     ["foo(_)"]),
    ("t2a_parse_number_text", "term_to_atom(R, 42)", None, ["42"]),
    ("t2a_parse_string_text", 'term_to_atom(R, "f(x)")', None, ["f(x)"]),
    ("t2a_not_text", "term_to_atom(_, f(x))", None,
     ["error(type_error(string,f(x)),term_to_atom/2)"]),
    ("t2a_syntax_error", syntax("term_to_atom(_, 'foo(')"), None, ["syntax"]),
    ("t2a_two_terms", syntax("term_to_atom(_, 'a. b')"), None, ["syntax"]),
    ("t2a_only_layout", syntax("term_to_atom(_, '  % c')"), None,
     ["syntax"]),
    # ── atom_to_term/3 ──────────────────────────────────────────────────
    ("a2t_bindings", "atom_to_term('foo(X,Y,X)', T, B), R = T-B",
     "atom_chars('foo(X,Y,X).', Cs), "
     "read_term_from_chars(Cs, T, [variable_names(B)]), R = T-B",
     ["foo(_1,_2,_1)-['X'=_1,'Y'=_2]"]),
    ("a2t_anonymous_left_out", "atom_to_term('f(_,_A,_)', T, B), R = B",
     "atom_chars('f(_,_A,_).', Cs), "
     "read_term_from_chars(Cs, T, [variable_names(B)]), R = B",
     ["['_A'=_]"]),
    ("a2t_ground", "atom_to_term(abc, T, B), R = T-B",
     "atom_chars('abc.', Cs), "
     "read_term_from_chars(Cs, T, [variable_names(B)]), R = T-B",
     ["abc-[]"]),
    ("a2t_variable", "atom_to_term('X', T, B), R = T-B", None,
     ["_1-['X'=_1]"]),
    ("a2t_unify_term", "atom_to_term('f(X)', f(a), B), R = B", None,
     ["['X'=a]"]),
    ("a2t_unbound_text", "atom_to_term(_, _, _)", None,
     ["error(instantiation_error,atom_to_term/3)"]),
    ("a2t_not_text", "atom_to_term(f(x), _, _)", None,
     ["error(type_error(string,f(x)),atom_to_term/3)"]),
    ("a2t_bindings_not_list", "atom_to_term(foo, _, x)", None,
     ["error(type_error(list,x),atom_to_term/3)"]),
    ("a2t_syntax_error", syntax("atom_to_term('foo(', _, _)"), None,
     ["syntax"]),
    # ── atom_string/2 ───────────────────────────────────────────────────
    ("as_atom_to_string", "atom_string(abc, R)", "atom_chars(abc, R)",
     ["[a,b,c]"]),
    ("as_string_to_atom", 'atom_string(R, "abc")', 'atom_chars(R, "abc")',
     ["abc"]),
    ("as_number_to_string", "atom_string(42, R)", "number_chars(42, R)",
     ["['4','2']"]),
    ("as_nil_to_string", "atom_string([], R)", "atom_chars([], R)",
     ["['[',']']"]),
    ("as_number_text_to_atom", "atom_string(R, 42)", None, ["'42'"]),
    ("as_codes_to_atom", "atom_string(R, [0'a, 0'b])", None, ["ab"]),
    ("as_chars_to_atom", "atom_string(R, [a, b])", None, ["ab"]),
    ("as_both_bound", 'atom_string(abc, "abc"), R = yes', None, ["yes"]),
    ("as_types_not_enforced", 'atom_string(1, "1"), R = yes', None,
     ["yes"]),
    ("as_mismatch", 'atom_string(abc, "abd"), R = yes', None, []),
    ("as_both_unbound", "atom_string(_, _)", None,
     ["error(instantiation_error,atom_string/2)"]),
    ("as_atom_side_not_text", "atom_string(f(x), _)", None,
     ["error(type_error(atom,f(x)),atom_string/2)"]),
    ("as_string_side_not_text", "atom_string(_, f(x))", None,
     ["error(type_error(string,f(x)),atom_string/2)"]),
]

ORACLE_ROWS = [r for r in ROWS if r[2] is not None]


def _program(goals: list[str]) -> str:
    return HELPERS + DRIVER + "".join(
        f"row({i}) :- run_row({i}, ({g}), R).\n" for i, g in enumerate(goals))


def _parse(stdout: str) -> list[list[str]]:
    rows: list[list[str]] = []
    for line in stdout.splitlines():
        if line.startswith("ROW "):
            rows.append([])
        elif not rows or not line.strip():
            continue
        elif line.startswith("A "):
            rows[-1].append(_normalise(line[2:].strip()))
        elif not line.startswith("   "):      # Scryer's toplevel answer lines
            rows[-1].append("O " + _normalise(line.strip()))
    return rows


@pytest.fixture(scope="module", params=[PROLOG_SUFFIX, CLAUSAL_PROLOG])
def engine_rows(request, tmp_path_factory):
    """Every row's answers from the engine, the program loaded as ``.pl``
    and as ``.clausal``."""
    import clausal
    assert os.getcwd() in clausal.__file__, clausal.__file__
    suffix = request.param
    name = "common_extras" + suffix.replace(".", "_")
    src = _program([r[1] for r in ROWS])
    if suffix == CLAUSAL_PROLOG:
        src = f":- module({name}, []).\n" + src + f":- end_module({name}).\n"
    path = tmp_path_factory.mktemp("extras") / f"{name}{suffix}"
    path.write_text(src)
    mod = _load_module(name, str(path))
    out = []
    for i in range(len(ROWS)):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            n = sum(1 for _ in solve(("row", i), mod))
        assert n == 1, (ROWS[i][0], n)
        parsed = _parse(buf.getvalue())
        assert len(parsed) == 1, (ROWS[i][0], buf.getvalue())
        out.append(parsed[0])
    return out


@pytest.mark.parametrize("i", range(len(ROWS)), ids=[r[0] for r in ROWS])
def test_engine(engine_rows, i):
    assert engine_rows[i] == ROWS[i][3], (ROWS[i][1], engine_rows[i])


def _scryer_rows(goals: list[str]) -> list[list[str]]:
    prelude = ":- use_module(library(lists)).\n" \
              ":- use_module(library(pairs)).\n" \
              ":- use_module(library(charsio)).\n"
    with tempfile.TemporaryDirectory() as d:
        pl = os.path.join(d, "oracle.pl")
        with open(pl, "w") as fh:
            fh.write(prelude + _program(goals))
        proc = run_scryer(pl, [f"row({i})." for i in range(len(goals))],
                          timeout=120)
    rows = _parse(proc.stdout)
    assert len(rows) == len(goals), proc.stdout[-2000:] + proc.stderr[-2000:]
    return rows


def test_oracle(scryer):
    del scryer      # the fixture only asserts the binary is there
    got = _scryer_rows([r[2] for r in ORACLE_ROWS])
    want = [r[3] for r in ORACLE_ROWS]
    bad = [(r[0], g, w) for r, g, w in zip(ORACLE_ROWS, got, want) if g != w]
    assert not bad, bad


def test_oracle_lacks_them(scryer):
    """Scryer defines none of the six: the SWI definition is the reference
    (keep this so a Scryer that grows one becomes the oracle for it)."""
    del scryer
    goals = ["sort(0, @<, [a], _)", "predsort(compare, [a], _)", "print(a)",
             "atom_string(a, _)", "term_to_atom(a, _)",
             "atom_to_term(a, _, _)"]
    got = _scryer_rows([f"catch(({g}), error(existence_error(procedure, PI), _),"
                        f" true), R = PI" for g in goals])
    assert got == [["sort/4"], ["predsort/3"], ["print/1"],
                   ["atom_string/2"], ["term_to_atom/2"],
                   ["atom_to_term/3"]], got


def test_sort4_dict_key():
    """An atom key (or an integer one) on a dict selects that key's value,
    as SWI's sort/4 does on dicts; a missing key is
    existence_error(key, Key, Dict)."""
    from clausal.logic.database import Module
    from clausal.logic.exceptions import LogicException
    from clausal.logic.solve import _deref_walk
    from clausal.logic.variables import Trail, Var
    from clausal.terms import DictTerm
    d1, d2 = DictTerm({"k": 2, "j": 1}), DictTerm({"k": 1, "j": 2})
    r = Var()
    sols = [_deref_walk(r) for _ in solve(
        ("sort", "k", "@<", [d1, d2], r), Module("_sort4_dicts"), Trail())]
    assert sols == [[d2, d1]]
    with pytest.raises(LogicException) as exc:
        list(solve(("sort", "z", "@<", [d1], Var()),
                   Module("_sort4_dicts2"), Trail()))
    assert exc.value.term[1] == ("existence_error", "key", "z", d1)


def test_term_to_atom_reads_under_the_double_quotes_flag(tmp_path):
    """A ``"..."`` in the text is read as the double_quotes flag says
    (ISO 7.11.2.5), as read_term/2 reads it."""
    src = textwrap.dedent("""\
        :- set_prolog_flag(double_quotes, atom).
        r(R) :- term_to_atom(R, '"ab"').
        """)
    path = tmp_path / f"_t2a_dq{PROLOG_SUFFIX}"
    path.write_text(src)
    mod = _load_module("_t2a_dq", str(path))
    from clausal.logic.solve import _deref_walk
    from clausal.logic.variables import Var
    r = Var()
    assert [_deref_walk(r) for _ in solve(("r", r), mod)] == ["ab"]
