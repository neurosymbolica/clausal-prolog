from decimal import Decimal

from clausal.terms import term_str, Compound


class TestDecimalRendering:
    def test_bare_decimal_renders_plainly(self):
        assert term_str(Decimal("7.89")) == "7.89"

    def test_decimal_no_trailing_zeros_lost(self):
        # str(Decimal) preserves scale; repr would wrap it in Decimal('...').
        assert term_str(Decimal("7.90")) == "7.90"

    def test_decimal_nested_in_compound(self):
        s = term_str(Compound("price", (Decimal("1.50"),)))
        assert "1.50" in s
        assert "Decimal(" not in s
