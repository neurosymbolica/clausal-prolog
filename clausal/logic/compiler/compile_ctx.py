"""Compile-time context dataclass.

``CompilationContext`` bundles the 3–5 values that are threaded through every
goal / body / predicate compilation routine:

- ``db``           — the database used for dispatch lookups and signature
                     resolution.
- ``var_context``  — mutable Var._id → python-local-name mapping.  Mutated
                     in place as ``term_to_ast_expr`` and
                     ``_preallocate_body_vars`` discover new Vars.
- ``trail_name``   — the name of the compiled function's trail parameter
                     (always ``"trail"`` today; parameterised for
                     historical reasons and potential future use).
- ``self_name``    — (trampoline only) name of the self-generator
                     parameter — ``"this_generator"`` by default.
- ``parent_name``  — (trampoline only) name of the parent-generator
                     parameter — ``"_tramp_parent"`` by default.

The two trampoline-only fields are harmless in shallow mode — shallow
helpers simply don't read them.  Keeping a single ``CompilationContext`` class
(rather than separate shallow/trampoline classes) lets functions that
are strategy-agnostic accept either without branching on type.

Migration status: this dataclass is being introduced incrementally.
The public entrypoints (``compile_goal``, ``compile_body``,
``compile_predicate_*``) keep their positional-tuple signatures for
backward compatibility with external callers (tests, ``solve.py``,
``compiler_v2.py``).  Internal helpers switch to accepting ``ctx``
one function group at a time.
"""

from __future__ import annotations

import dataclasses
from typing import Any

from ._ast_helpers import _THIS_GEN_NAME, _TRAMP_PARENT_NAME


@dataclasses.dataclass
class CompilationContext:
    db: Any  # Database | None — typed loosely to avoid circular import
    var_context: dict[int, str]
    trail_name: str
    self_name: str = _THIS_GEN_NAME
    parent_name: str = _TRAMP_PARENT_NAME

    def replace(self, **overrides) -> "CompilationContext":
        """Return a shallow copy with fields overridden.

        Useful when a nested compilation needs a different ``self_name``
        or ``parent_name`` (e.g., NAF mini-trampoline using ``_naf_self``
        / ``_naf_parent``) but inherits everything else.  ``var_context``
        is shared by reference — mutations in the nested compile are
        visible to the caller, matching current behaviour.
        """
        return dataclasses.replace(self, **overrides)
