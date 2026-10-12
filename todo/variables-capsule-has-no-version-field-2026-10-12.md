# The _variables capsule has no version field (2026-10-12)

a750f58c appended `hooks_running` to `TrailObject` in `_variables_capi.h`. An extension built against
the OLD header is safe: the field sits in the struct's old tail padding, and no earlier offset moved.
The reverse is not detectable: an extension built against the NEW header and loaded with an OLD
`_variables.so` reads uninitialised padding as `hooks_running`.

Every consumer is in-tree and rebuilt together today, so the risk is low.

Fix: add a version (or a struct-size) field to the capsule, and have consumers check it at import.
