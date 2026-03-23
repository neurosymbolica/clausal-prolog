"""Control builtins: CallNth/2, CountAll/2, SetupCallCleanup/3, CallCleanup/2.

These predicates are primarily compiled as **compiler special forms** in
``compiler.py`` (the goal arguments are compiled inline at compile time).
This module registers the field names so that ``_build_all_builtin_classes``
creates the PredicateMeta classes for term construction.
"""

from __future__ import annotations

from clausal.logic.builtins._registry import _BUILTIN_FIELDS


# Register field names for class construction.
# The actual dispatch is handled by compiler special forms in compiler.py.
_BUILTIN_FIELDS[("CallNth", 2)] = ("goal", "n")
_BUILTIN_FIELDS[("CountAll", 2)] = ("goal", "count")
_BUILTIN_FIELDS[("SetupCallCleanup", 3)] = ("setup", "call", "cleanup")
_BUILTIN_FIELDS[("CallCleanup", 2)] = ("call", "cleanup")
_BUILTIN_FIELDS[("Freeze", 2)] = ("variable", "goal")
_BUILTIN_FIELDS[("When", 2)] = ("condition", "goal")
