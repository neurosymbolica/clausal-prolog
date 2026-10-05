"""clausal.scryer — embedded Scryer Prolog via PyO3.

Usage::

    from clausal.scryer import Scryer

    with Scryer() as s:
        s.load_string("parent(tom, bob). parent(bob, ann).")
        for sol in s.query("parent(tom, X)."):
            print(sol["X"])  # "bob", "ann"

To build the Scryer embedding::

    cd packages/clausal-scryer
    maturin develop --release

Requires: Rust toolchain, scryer-prolog source at ../../scryer-prolog
"""

try:
    import _scryer_ext
    AVAILABLE = True
except ImportError:
    AVAILABLE = False


def _not_available(*args, **kwargs):
    raise ImportError(
        "clausal.scryer requires the _scryer_ext extension.\n"
        "Build it with: cd packages/clausal-scryer && maturin develop --release"
    )


if AVAILABLE:
    from clausal.scryer._scryer import Scryer
    from clausal.scryer._bridge import to_prolog
else:
    Scryer = _not_available
    to_prolog = _not_available

__all__ = ["Scryer", "AVAILABLE", "to_prolog"]
