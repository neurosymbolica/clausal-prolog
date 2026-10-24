from clausal.logic.atoms import mint
from clausal.tools.prolog_reader import Clause, SyntaxIssue, read_module


class TestRecovery:
    def test_bad_item_resyncs_to_next_end(self):
        items = read_module("foo(a).\n)(bad syntax.\nbar(b).\n")
        assert [type(i).__name__ for i in items] == ["Clause", "SyntaxIssue", "Clause"]
        assert items[2].term == ("bar", mint("b"))
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


class TestDiagnosedQuotedFaults:
    """A refused quoted token is diagnosed with the fault's own line:col
    (D60 fix round 2)."""

    def test_each_error_names_its_own_line(self):
        src = "".join(f"p({i}, 'ab\\zcd').\n" if i % 3 == 0 else f"q({i}).\n"
                      for i in range(30))
        msgs = [i.message for i in read_module(src) if isinstance(i, SyntaxIssue)]
        assert msgs == [f"invalid escape sequence '\\z' in quoted atom at "
                        f"{n + 1}:{len(f'p({n}, ab') + 2}" for n in range(0, 30, 3)]

    def test_the_reader_takes_lines_from_the_lexer_not_a_scan(self, monkeypatch):
        # The line of each diagnosed fault comes from the lexer's line
        # starts (a bisect). Counting newlines from the start of the text
        # made a file with many faults quadratic to read.
        import clausal.tools.prolog_reader as pr
        seen = []
        real = pr._lex_error

        def spy(t, text=None, pos=None):
            seen.append(pos)
            return real(t, text, pos)

        monkeypatch.setattr(pr, "_lex_error", spy)
        read_module("a.\np('\\z').\n")
        assert seen and all(callable(p) for p in seen)

    def test_a_given_pos_is_what_the_message_reports(self):
        from clausal.tools.prolog_reader import PrologReader, _lex_error_message
        r = PrologReader()
        r.feed("p('\\z').\n")
        r.close()
        t = next(t for t in iter(r._lexer.next_token, None)
                 if getattr(t, "kind", None) == "error")
        msg = _lex_error_message(t, r._lexer._text, lambda off: (off, 41, 7))
        assert msg.endswith(" at 41:7")

    def test_last_item_without_a_newline_keeps_its_diagnosis(self):
        msgs = [i.message for i in read_module("y('ab\\zcd').")
                if isinstance(i, SyntaxIssue)]
        assert msgs == ["invalid escape sequence '\\z' in quoted atom at 1:6"]

    def test_a_float_before_a_quote_is_not_a_char_code(self):
        msgs = [i.message for i in read_module("x(X) :- X = 1.0'\\z'.\n")
                if isinstance(i, SyntaxIssue)]
        assert msgs == ["invalid escape sequence '\\z' in quoted atom at 1:17"]

    def test_a_real_0_quote_is_still_labelled_a_char_code(self):
        msgs = [i.message for i in read_module("x(X) :- X = 0'\\z.\n")
                if isinstance(i, SyntaxIssue)]
        assert msgs == ["invalid escape sequence '\\z' in 0' character code at 1:15"]


class TestQuotedEmptyListAtom:
    """ISO: `'[]'` and `[]` are the same atom (D70; Markus Triska
    confirmed 2026-10-16), so the reader reads both as the empty list."""

    def test_quoted_and_bare_read_the_same(self):
        quoted, bare = (read_module(f"t({s}).\n")[0].term for s in ("'[]'", "[]"))
        assert quoted == bare == ("t", [])

    def test_inside_a_term_and_a_list(self):
        (item,) = read_module("t(f('[]'), [a, '[]']).\n")
        assert item.term == ("t", ("f", []), [mint("a"), []])

    def test_other_bracket_atoms_are_unchanged(self):
        (item,) = read_module("t('{}', '[ ]', '[]x').\n")
        assert item.term == ("t", "{}", "[ ]", "[]x")
