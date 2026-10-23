"""The public builtin registry holds no internal (``$``) helper.

``_BUILTINS`` and ``_DB_BUILTINS`` are what tools enumerate as the
engine's builtins.  A ``$`` name cannot be written in source, so a ``$``
entry there is plumbing that the listing shows as a builtin, and adding one
changes the listing.  An internal goal the compiled code needs is bound
outside the registry instead: see ``$meta_body_check/1``
(``clausal.logic.builtins.control.META_BODY_CHECK``, bound in
``clausal/logic/compiler/predicate.py``'s ``base_globals``).
"""
from __future__ import annotations

from clausal.logic.builtins._registry import _BUILTINS, _DB_BUILTINS

#: Pre-existing; removing it would move the downstream pins of the listing.
#: todo/clpz-sum-internal-helper-is-in-the-public-builtin-registry-2026-10-23.md
#: records moving it out.
ALLOWED = {("$clpz_sum", 3)}

WHERE = ("an internal $ helper belongs outside the public builtin registry: "
         "hold it as a BuiltinPredicate (as clausal.logic.builtins.control."
         "META_BODY_CHECK holds $meta_body_check/1) and bind it in "
         "clausal/logic/compiler/predicate.py's base_globals")


def _internal(registry):
    return {k for k in registry
            if type(k[0]) is str and k[0].startswith("$")}


def test_no_internal_name_is_a_stateless_builtin():
    extra = _internal(_BUILTINS) - ALLOWED
    assert not extra, f"{sorted(extra)}: {WHERE}"


def test_no_internal_name_is_a_db_builtin():
    extra = _internal(_DB_BUILTINS)
    assert not extra, f"{sorted(extra)}: {WHERE}"


def test_the_allowlist_holds_only_what_is_still_there():
    """So the allowlist shrinks when ``$clpz_sum/3`` moves out."""
    assert _internal(_BUILTINS) >= ALLOWED
    assert ("$meta_body_check", 1) not in _BUILTINS
