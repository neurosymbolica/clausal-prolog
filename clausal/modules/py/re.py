"""clausal.modules.py.re — Regex predicates under the ``py.re`` name.

Re-exports everything from :mod:`clausal.modules.regex` so that
``.clausal`` files can use the familiar name::

    -import_from(py.re, [Match, Search, Replace, Split, FindAll])
"""

from clausal.modules.regex import (  # noqa: F401
    Match,
    Search,
    Replace,
    Split,
    FindAll,
)
