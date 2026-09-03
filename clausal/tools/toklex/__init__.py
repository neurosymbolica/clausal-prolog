import functools
import os

from clausal.tools.toklex.annotate import Lexer, annotate
from clausal.tools.toklex.driver import EOF, NEED_MORE, IncrementalLexer, Tok
from clausal.tools.toklex.spec import load_spec

__all__ = ["NEED_MORE", "EOF", "Tok", "IncrementalLexer", "load_lexer"]


@functools.lru_cache(maxsize=None)
def load_lexer(name: str = "iso") -> Lexer:
    """Load and compile the named token spec from ``specs/<name>.toklex.pl``.

    Cached: repeated calls with the same ``name`` return the same
    ``Lexer`` instance without re-parsing or re-compiling.
    """
    path = os.path.join(os.path.dirname(__file__), "specs", name + ".toklex.pl")
    return annotate(load_spec(path))
