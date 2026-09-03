from clausal.tools.toklex.charset import CharSet, Partition


class TestCharSet:
    def test_from_chars_and_contains(self):
        cs = CharSet.from_chars("abz")
        assert cs.contains("a") and cs.contains("z") and not cs.contains("c")
        assert cs.ivs == ((97, 98), (122, 122))  # 'ab' merged, 'z' separate

    def test_ranges_union_difference_intersection(self):
        digit = CharSet.from_ranges([("0", "9")])
        low = CharSet.from_ranges([("a", "z")])
        alnum = digit | low
        assert alnum.contains("5") and alnum.contains("m")
        assert (alnum - digit).contains("m") and not (alnum - digit).contains("5")
        assert (alnum & digit).ivs == digit.ivs

    def test_full_minus_char(self):
        hole = CharSet.full() - CharSet.from_chars("\x00")
        assert not hole.contains("\x00") and hole.contains("a")

    def test_unicode_category(self):
        ll = CharSet.from_unicode_category("Ll")
        assert ll.contains("a") and ll.contains("é") and not ll.contains("A")


class TestPartition:
    def test_partition_is_exact_and_total(self):
        digit = CharSet.from_ranges([("0", "9")])
        hexletters = CharSet.from_ranges([("a", "f"), ("A", "F")])
        p = Partition.build([digit, hexletters])
        # totality: every char has a symbol
        for ch in "0a fzé\x00":
            assert 0 <= p.symbol_of(ch) < p.n
        # exactness: a cell never straddles a set boundary
        assert p.symbol_of("0") == p.symbol_of("9")
        assert p.symbol_of("a") != p.symbol_of("g")
        assert p.symbols_of(digit) == {p.symbol_of("0")} | set()
        # symbols_of covers exactly the set
        syms = p.symbols_of(hexletters)
        assert p.symbol_of("b") in syms and p.symbol_of("B") in syms
        assert p.symbol_of("g") not in syms

    def test_sample_roundtrip(self):
        p = Partition.build([CharSet.from_chars("x")])
        s = p.symbol_of("x")
        assert p.symbol_of(p.sample(s)) == s
