"""clausal.logic.builtins — built-in and standard-library predicates.

This package is organized into submodules by category:

- _registry    — decorator system, BuiltinPredicate adapter, lookup API
- _helpers     — shared term-inspection helpers
- inspection   — Functor/3, Arg/3, Unpack/2, CopyTerm/2, TermVariables/2, NumberVars/3
- database_ops — Assert/1, AssertFirst/1, Retract/1, ClearTable/2, ClearAllTables/0
- keyword_ops  — Vary/3, Extend/3, UnboundKeys/2, Signature/3
- constraints  — Dif/2, Eq/3, DifT/3, InDomain/3, Label/1, AllDifferent/1, Equivalent/2
- type_checks  — IsVar/1, IsBound/1, IsStr/1, IsNumber/1, IsInt/1, IsFloat/1, etc.
- arithmetic   — Between/3, Succ/2, Plus/3, Abs/2, Max/3, Min/3, Sign/2, Gcd/3, DivMod/4
- lists        — In/2, Append/3, Length/2, Sort/2, Select/3, etc.
- pairs        — Unzip/3, PairKeys/2, PairValues/2
- higher_order — CallGoal/1..8, Call/1..8, MapList/2,3, Filter/3, Exclude/3, FoldLeft/4
- io           — Write/1, Writeln/1, PrintTerm/1, Nl/0, Tab/1, WriteToString/2, TermToString/2
- dcg          — phrase/2, phrase/3
- control      — CallNth/2, CountAll/2, SetupCallCleanup/3, CallCleanup/2, Freeze/2, When/2
- chars        — CharType/2, CharCode/2, UpcaseAtom/2, DowncaseAtom/2, AtomLength/2, AtomChars/2, AtomCodes/2, AtomConcat/3, SubAtom/5
- attributes   — PutAttr/3, GetAttr/3, DelAttr/2, GetAttrs/2, PutAttrs/2, IsAttVar/1, TermAttributedVariables/2
- translations_builtin — Translate/3
"""

# Import registry infrastructure (must come first — provides decorators).
from clausal.logic.builtins._registry import (  # noqa: F401
    # Registry dicts
    _BUILTINS,
    _DB_BUILTINS,
    _BUILTIN_FIELDS,
    _BUILTIN_CLASSES,
    # Decorators (used by submodules)
    _builtin,
    _trampoline_builtin,
    _db_builtin,
    _simple_to_trampoline,
    _ensure_trampoline_dispatch,
    # Adapter classes
    BuiltinPredicate,
    MultiArityBuiltin,
    # Public lookup API
    get_builtin_predicate,
    get_builtin_dispatch,
    get_builtin_class,
    # Unification
    structural_unify,
    # Class builder
    _build_all_builtin_classes,
)

# Import all submodules to trigger decorator registration.
# Order doesn't matter — all decorators write to the same registry dicts.
from clausal.logic.builtins import inspection      # noqa: F401
from clausal.logic.builtins import database_ops    # noqa: F401
from clausal.logic.builtins import keyword_ops     # noqa: F401
from clausal.logic.builtins import constraints     # noqa: F401
from clausal.logic.builtins import type_checks     # noqa: F401
from clausal.logic.builtins import arithmetic      # noqa: F401
from clausal.logic.builtins import lists           # noqa: F401
from clausal.logic.builtins import pairs           # noqa: F401
from clausal.logic.builtins import higher_order    # noqa: F401
from clausal.logic.builtins import io              # noqa: F401
from clausal.logic.builtins import dcg             # noqa: F401
from clausal.logic.builtins import dict_set        # noqa: F401
from clausal.logic.builtins import control           # noqa: F401
from clausal.logic.builtins import chars             # noqa: F401
from clausal.logic.builtins import attributes        # noqa: F401
from clausal.logic.builtins import translations_builtin  # noqa: F401

# Import units_constraint to register HasUnits/2 before _build_all_builtin_classes runs.
import clausal.logic.units_constraint               # noqa: F401

# Re-export private names used by tests and other modules.
from clausal.logic.builtins.database_ops import _normalize_fact_clause  # noqa: F401
from clausal.logic.builtins.higher_order import (  # noqa: F401
    _map_list__2, _map_list__3, _include__3, _exclude__3, _foldl__4,
)

# Build predicate classes now that all decorators have run.
_build_all_builtin_classes()


__all__ = [
    "BuiltinPredicate",
    "MultiArityBuiltin",
    "get_builtin_predicate",
    "get_builtin_class",
    "get_builtin_dispatch",
    "_BUILTINS",
    "_DB_BUILTINS",
    "_BUILTIN_CLASSES",
    "_BUILTIN_FIELDS",
    "structural_unify",
]
