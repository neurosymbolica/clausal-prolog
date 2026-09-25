"""A side-effect counter for tests/test_clause_2_iso.py: a goal-position
``++`` thunk bumps it, and clause/2 must not."""
COUNT = [0]


def bump():
    COUNT[0] += 1
    return None
