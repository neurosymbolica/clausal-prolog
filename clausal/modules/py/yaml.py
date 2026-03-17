"""clausal.modules.py.yaml — YAML predicates under the ``py.yaml`` name.

Re-exports everything from :mod:`clausal.modules.yaml_module` so that
``.clausal`` files can use the familiar name::

    -import_from(py.yaml, [Read, Write, Get])
"""

from clausal.modules.yaml_module import (  # noqa: F401
    Read,
    Write,
    ReadAll,
    WriteAll,
    ReadFile,
    WriteFile,
    Get,
)
