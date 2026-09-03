from clausal.tools.toklex.annotate import annotate
from clausal.tools.toklex.driver import IncrementalLexer, NEED_MORE, EOF
from clausal.tools.toklex.decode import Utf8Feeder
from tests.toklex.test_driver import SPEC


def blex(data: bytes):
    f = Utf8Feeder(IncrementalLexer(annotate(SPEC)))
    f.feed(data)
    f.close()
    out = []
    while (t := f.next_token()) is not EOF:
        assert t is not NEED_MORE
        out.append(t)
    return out


def test_plain_ascii_roundtrip():
    assert [t.lexeme for t in blex(b"ab 12 ")] == ["ab", "12"]


def test_invalid_byte_is_error_token_and_lexing_continues():
    toks = blex(b"ab \xff cd ")
    assert [t.kind for t in toks] == ["name", "error", "name"]
    assert toks[1].value == ("invalid_encoding", b"\xff")


def test_stray_continuation_and_overlong():
    assert [t.kind for t in blex(b"\x80x ")] == ["error", "name"]
    assert [t.kind for t in blex(b"\xc0\xafx ")][0] == "error"   # overlong '/'


def test_split_multibyte_is_pending_not_invalid():
    f = Utf8Feeder(IncrementalLexer(annotate(SPEC)))
    f.feed(b"ab \xc3")            # correct UTF-8 lead byte of 'é' (C3 A9), split across feed()
    toks = [f.next_token()]        # 'ab' emits (space ends it)
    assert toks[0].lexeme == "ab"
    assert f.next_token() is NEED_MORE      # held prefix: waiting
    f.feed(b"\xa9 ")               # completes 'é' (not in any SPEC class -> error tok)
    f.close()
    t = f.next_token()
    assert t.kind == "error" and t.value[1] == "é"


def test_truncated_multibyte_at_close_is_bad():
    f = Utf8Feeder(IncrementalLexer(annotate(SPEC)))
    f.feed(b"x \xe2\x82")          # 2 of 3 bytes of '€'
    f.close()
    kinds = []
    while (t := f.next_token()) is not EOF:
        kinds.append(t.kind)
    assert kinds == ["name", "error"]
