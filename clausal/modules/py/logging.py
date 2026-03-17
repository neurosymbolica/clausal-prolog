"""clausal.modules.py.logging — Logging predicates under the ``py.logging`` name.

Re-exports everything from :mod:`clausal.modules.log` so that
``.clausal`` files can use the familiar name::

    -import_from(py.logging, [GetLogger, Info, Debug, Warning, Error])
"""

from clausal.modules.log import (  # noqa: F401
    GetLogger,
    SetLevel,
    GetLevel,
    IsEnabledFor,
    Log,
    Debug,
    Info,
    Warning,
    Error,
    Critical,
    StreamHandler,
    FileHandler,
    SetFormatter,
    AddHandler,
    RemoveHandler,
    BasicConfig,
)
