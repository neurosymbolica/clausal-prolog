"""clausal.logic.builtins — built-in and standard-library predicates.

This package is organized into submodules by category:

- _registry    — decorator system, BuiltinPredicate adapter, lookup API
- _helpers     — shared term-inspection helpers
- inspection   — functor/3, arg/3, unpack/2, copy_term/2, term_variables/2, numbervars/3
- database_ops — assertz/1, asserta/1, retract/1, abolish_table/2, abolish_all_tables/0
- keyword_ops  — vary/3, extend/3, unbound_keys/2, signature/3
- constraints  — dif/2, eq/3, dif_t/3, in_domain/3, label/1, all_different/1, structural_eq/2
- type_checks  — var/1, nonvar/1, is_str/1, number/1, integer/1, float_/1, etc.
- arithmetic   — between/3, succ/2, plus/3, abs_/2, max_/3, min_/3, sign/2, gcd/3, divmod_/4
- lists        — in_/2, append/3, length/2, sort/2, select/3, etc.
- pairs        — pairs_keys_values/3, pairs_keys/2, pairs_values/2
- higher_order — call_goal/1..8, call/1..8, maplist/2,3, include/3, exclude/3, foldl/4
- io           — write/1, writeln/1, print_term/1, nl/0, tab/1, write_to_string/2, term_to_string/2
- dcg          — phrase/2, phrase/3
- control      — call_nth/2, count_all/2, setup_call_cleanup/3, call_cleanup/2, freeze/2, when/2
- chars        — char_type/2, char_code/2, upcase_atom/2, downcase_atom/2, atom_length/2, atom_chars/2, atom_codes/2, atom_concat/3, sub_atom/5
- attributes   — put_attr/3, get_attr/3, del_attr/2, get_attrs/2, put_attrs/2, attvar/1, term_attvars/2
- translations_builtin — translate/3
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
from clausal.logic.builtins import z3_constraints  # noqa: F401
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
from clausal.logic.builtins import iso_compare       # noqa: F401  (registers by import)

# Import units_constraint to register has_units/2 before _build_all_builtin_classes runs.
import clausal.logic.units_constraint               # noqa: F401
import clausal.logic.units_clp                      # noqa: F401  (registers the units_link hook)

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
