"""Built-in jurisdiction modules exposing currency vocabulary.

Each currency is defined exactly once, in its home jurisdiction module, and
referenced there (bare-imported within a single-currency rulebase, or module-
qualified when several currencies are in play). Currencies are Decimal-backed
units base dimensions — see clausal.modules.countries._currency.
"""
