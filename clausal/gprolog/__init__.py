"""clausal.gprolog — embedded GNU Prolog via a Python C extension.

Usage::

    from clausal.gprolog import GnuProlog

    with GnuProlog() as g:
        g.consult_string("parent(tom, bob). parent(bob, ann).")
        for sol in g.query("parent(tom, X)."):
            print(sol["X"])  # "bob"

To build the GNU Prolog embedding::

    export GPROLOG_HOME=/path/to/gprolog-1.5.0  # built with --disable-regs -fPIC
    cd clausal-gprolog
    pip install -e .

Requires: GNU Prolog compiled from source with --disable-regs and -fPIC.
Standard package installs (apt install gprolog) will NOT work.
See implementation_plans/GPROLOG_EMBEDDING.md for details.

Note: GNU Prolog only supports one engine per process lifetime.
"""

try:
    import _gprolog_ext
    AVAILABLE = True
except ImportError:
    AVAILABLE = False


def _not_available(*args, **kwargs):
    raise ImportError(
        "clausal.gprolog requires the _gprolog_ext C extension.\n"
        "Build: export GPROLOG_HOME=... && cd clausal-gprolog && pip install -e .\n"
        "Requires: GNU Prolog compiled with --disable-regs and -fPIC.\n"
        "See implementation_plans/GPROLOG_EMBEDDING.md for details."
    )


if AVAILABLE:
    from clausal.gprolog._gprolog import GnuProlog
    from clausal.gprolog._bridge import to_prolog
else:
    GnuProlog = _not_available
    to_prolog = _not_available

__all__ = ["GnuProlog", "AVAILABLE", "to_prolog"]
