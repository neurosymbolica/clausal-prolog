from clausal.tools.prolog_reader import Clause, SyntaxIssue, read_module


class TestRecovery:
    def test_bad_item_resyncs_to_next_end(self):
        items = read_module("foo(a).\n)(bad syntax.\nbar(b).\n")
        assert [type(i).__name__ for i in items] == ["Clause", "SyntaxIssue", "Clause"]
        assert items[2].term == ("bar", "b")
        assert items[1].resumable is True
        s, e = items[1].span
        assert s >= 8 and e <= 22

    def test_unterminated_final_item(self):
        items = read_module("foo(a).\nbar(b")
        assert [type(i).__name__ for i in items] == ["Clause", "SyntaxIssue"]
        assert items[1].resumable is False

    def test_lexical_error_becomes_issue(self):
        items = read_module("foo(a).\nb\x01ad.\nok(c).\n")
        kinds = [type(i).__name__ for i in items]
        assert kinds == ["Clause", "SyntaxIssue", "Clause"]

    def test_unterminated_quote_at_eof(self):
        items = read_module("foo(a).\n'never closed")
        assert type(items[-1]).__name__ == "SyntaxIssue"
        assert items[-1].resumable is False

    def test_issue_positions_are_offsets(self):
        items = read_module("foo(a).\n)(x.\n")
        s, e = items[1].span
        assert isinstance(s, int) and isinstance(e, int) and 0 <= s < e
