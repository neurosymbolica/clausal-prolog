"""clausal.modules.py.uuid — UUID predicates under the ``py.uuid`` name.

Re-exports everything from :mod:`clausal.modules.uuid_mod` so that
``.clausal`` files can use the familiar name::

    -import_from(py.uuid, [UUIDv4, UUIDStr, IsUUID])
"""

from clausal.modules.uuid_mod import (  # noqa: F401
    UUIDv4,
    UUIDv1,
    UUIDv3,
    UUIDv5,
    UUIDStr,
    UUIDHex,
    UUIDUrn,
    UUIDBytes,
    UUIDInt,
    UUIDVersion,
    UUIDFields,
    IsUUID,
)
