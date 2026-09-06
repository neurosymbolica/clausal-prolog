from clausal.logic.atoms import char_atom, mint
from clausal.tools.prolog_ast import PAtom, PCompound, PList, PString, PVar
from clausal.tools.prolog_parser import parse_term
from clausal.tools.prolog_reader import VarRef, transform_term


def tt(src):
    return transform_term(parse_term(src))


class TestCells:
    def test_atoms_numbers(self):
        assert tt("foo")[0] == mint("foo")
        assert tt("'b ar'")[0] == mint("b ar")
        assert tt("42")[0] == 42
        assert tt("1.5")[0] == 1.5

    def test_compound_and_nesting(self):
        cell, spans, vn = tt("f(a, g(1), X)")
        assert cell == ("f", mint("a"), ("g", 1), VarRef(0))
        assert vn == {0: "X"}

    def test_proper_list_is_python_list(self):
        assert tt("[a, 1, [b]]")[0] == [mint("a"), 1, [mint("b")]]

    def test_partial_list_is_cons_cells(self):
        cell, _, vn = tt("[a, b | T]")
        assert cell == (".", mint("a"), (".", mint("b"), VarRef(0)))
        assert vn == {0: "T"}

    def test_double_quoted_is_a_string(self):
        # THE FLIP (spec §9.7): a ``PString`` reads as the ``str`` -- the
        # STRING, which IS the list of its char atoms (spec §6.2), so this
        # inverts the "emit the char list" reading, not its meaning.
        assert tt('"ab"')[0] == "ab"
        assert tt('""')[0] == ""

    def test_curly(self):
        assert tt("{a, b}")[0] == ("{}", (",", mint("a"), mint("b")))

    def test_var_numbering_first_occurrence_and_anon(self):
        cell, _, vn = tt("f(X, Y, X, _, _)")
        assert cell == ("f", VarRef(0), VarRef(1), VarRef(0), VarRef(2), VarRef(3))
        assert vn == {0: "X", 1: "Y", 2: "_", 3: "_"}

    def test_output_is_ground_data(self):
        cell, _, _ = tt("f(g(h(1)), a)")
        assert hash(cell) is not None  # all-tuple trees hash (list caveat documented)


class TestSpanTrees:
    def test_leaf_and_compound_iso_structure(self):
        cell, spans, _ = tt("f(ab, 12)")
        assert spans[0] == (0, 9)        # whole compound
        assert spans[1] == (2, 4)        # ab
        assert spans[2] == (6, 8)        # 12
        assert len(spans) == 1 + (len(cell) - 1)

    def test_list_span_shape(self):
        cell, spans, _ = tt("[a, b]")
        whole, elems = spans
        assert whole == (0, 6)
        assert elems[0] == (1, 2) and elems[1] == (4, 5)

    def test_string_is_leaf_span(self):
        cell, spans, _ = tt('"ab"')
        assert cell == "ab" and spans == (0, 4)

    def test_partial_list_span_outermost_covers_bracket(self):
        # [a, b | T]: the OUTERMOST cons node's span is the PList node's
        # own span verbatim (0, 10) -- covering the opening '[' -- not the
        # remaining-extent rule ((1, 10), start of 'a') that inner levels
        # use. Fix-wave finding #3 (final whole-branch review): the
        # remaining-extent rule applied uniformly made the top span start
        # at the first element instead of the bracket, which is wrong for
        # anything that wants "the span of this list term" (e.g. a
        # diagnostic pointing at `[a, b | T]` as a whole).
        cell, spans, vn = tt("[a, b | T]")
        assert cell == (".", mint("a"), (".", mint("b"), VarRef(0)))
        assert vn == {0: "T"}
        outer, a_span, inner = spans
        assert outer == (0, 10)          # the whole `[a, b | T]`
        assert a_span == (1, 2)          # 'a'
        mid, b_span, tail_span = inner
        assert mid == (4, 10)            # remaining-extent rule: 'b'..']'
        assert b_span == (4, 5)          # 'b'
        assert tail_span == (8, 9)       # 'T', the tail P-node's own span


class TestExtra:
    def test_deep_nesting_full_shape(self):
        cell, spans, vn = tt('f(g(h([X, "ab" | T])))')
        assert cell == (
            "f",
            ("g", ("h", (".", VarRef(0), (".", "ab", VarRef(1))))),
        )
        assert vn == {0: "X", 1: "T"}
        # span tree mirrors the cell shape
        assert isinstance(spans, tuple)
        assert spans[0][0] == 0

    def test_none_span_pnode_emits_placeholder(self):
        # Hand-built P-tree with no spans (span=None everywhere) must not crash.
        term = PCompound("f", (PAtom("a"), PVar("X")))
        cell, spans, vn = transform_term(term)
        assert cell == ("f", mint("a"), VarRef(0))
        assert spans == ((-1, -1), (-1, -1), (-1, -1))
        assert vn == {0: "X"}

    def test_fresh_numbering_per_call(self):
        term = parse_term("f(X, Y, X)")
        cell1, _, vn1 = transform_term(term)
        cell2, _, vn2 = transform_term(term)
        assert cell1 == cell2
        assert vn1 == vn2
        # Independent calls: same numbering result (fresh state per call),
        # but they are separately-computed dicts, not the same object reuse
        # bleeding state across calls.
        assert vn1 is not vn2
