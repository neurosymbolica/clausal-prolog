"""clausal.trealla — embedded Trealla Prolog via ctypes.

Usage::

    from clausal.trealla import Trealla

    with Trealla() as t:
        t.load_string("parent(tom, bob). parent(bob, ann).")
        for sol in t.query("parent(tom, X)."):
            print(sol["X"])  # "bob", "ann"

Trealla Prolog is a fast, lightweight ISO Prolog interpreter written in C.
Unlike the Scryer embedding (which requires a Rust toolchain and ~200ms
bootstrap), Trealla starts instantly and uses ~5MB of memory.

To build the shared library::

    cd trealla-prolog
    make NOFFI=1 NOSSL=1 NOTHREADS=1 ISOCLINE=1 CFLAGS+=-fPIC
    cc -shared -o libtpl.so *.o src/*.o library/*.o -lm

Requires: C compiler, trealla-prolog source at ../trealla-prolog
"""

from clausal.trealla._engine import AVAILABLE, TPL_BINARY

if AVAILABLE:
    from clausal.trealla._trealla import Trealla, TreallaError
    from clausal.trealla._bridge import to_prolog
else:
    def _not_available(*args, **kwargs):
        raise ImportError(
            "clausal.trealla requires the libtpl.so shared library.\n"
            "Build it from trealla-prolog source (see clausal/trealla/__init__.py)."
        )

    Trealla = _not_available
    to_prolog = None

__all__ = ["Trealla", "TreallaError", "AVAILABLE", "TPL_BINARY", "to_prolog"]
