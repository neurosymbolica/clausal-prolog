"""Ecuador — sucre."""
from clausal.modules.countries._currency import _make_currency

sucre = _make_currency("sucre", iso_code="ECS", scale=2, symbol="ECS", start="1884-04-01", end="2000-10-02", historical=True)
