from clausal.logic.atoms import mint
from clausal.tools.prolog_reader import (
    Clause, DCGRule, Directive, EOF, NEED_MORE, PrologReader, Query, VarRef, read_module,
)


class TestBatch:
    def test_fact_rule_directive_query_dcg(self):
        items = read_module(
            "foo(a).\n"
            "bar(X) :- foo(X).\n"
            ":- dynamic(baz/1).\n"
            "?- foo(a).\n"
            "greet --> [hello].\n")
        kinds = [type(i).__name__ for i in items]
        assert kinds == ["Clause", "Clause", "Directive", "Query", "DCGRule"]
        assert items[0].term == ("foo", mint("a"))
        assert items[1].term == (":-", ("bar", VarRef(0)), ("foo", VarRef(0)))
        assert items[1].var_names == {0: "X"}
        assert items[2].term == ("dynamic", ("/", mint("baz"), 1))
        assert items[4].term == ("-->", mint("greet"), [mint("hello")])

    def test_shared_var_numbering_across_head_and_body(self):
        (item,) = read_module("p(X, Y) :- q(Y, X).\n")
        assert item.term == (":-", ("p", VarRef(0), VarRef(1)),
                             ("q", VarRef(1), VarRef(0)))

    def test_item_spans_present(self):
        (item,) = read_module("foo(bar).")
        assert item.spans[0] == (0, 8)   # the compound foo(bar)


class TestIncremental:
    def test_need_more_until_end_token(self):
        r = PrologReader()
        r.feed("foo(a)")
        assert r.read_term() is NEED_MORE
        r.feed(". bar")
        item = r.read_term()
        assert isinstance(item, Clause) and item.term == ("foo", mint("a"))
        assert r.read_term() is NEED_MORE   # 'bar' could extend / no end yet
        r.feed("(b).")
        r.close()
        assert r.read_term().term == ("bar", mint("b"))
        assert r.read_term() is EOF
        assert r.read_term() is EOF

    def test_op_directive_applies_to_later_items(self):
        src = ":- op(700, xfx, ===).\na === b.\n"
        items = read_module(src)
        assert items[1].term == ("===", mint("a"), mint("b"))
        # Without the directive, a fresh reader parsing the same item does
        # not parse cleanly -- Task 5's recovery turns that failure into a
        # SyntaxIssue item rather than raising.
        from clausal.tools.prolog_reader import SyntaxIssue
        naked = read_module("a === b.\n")
        assert any(isinstance(i, SyntaxIssue) for i in naked)
