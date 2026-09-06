"""An interned 0-arity atom used as a ``DictTerm`` key must survive the
Python/cross-module → ``solve()`` boundary **by identity**.

Before the fix the query compiler lowered a ``DictTerm``'s atom keys inline as
bare ``Name(id='<atom>')`` nodes, resolved in the *called* predicate's module
namespace.  When that name was bound to something else there — very commonly a
same-named predicate, since the snake_case convention makes keys and predicates
share spellings — the template silently substituted that other object as the
key, so every read missed:

  * ``V is P[key]``      → bogus ``existence_error(dict_key, key)``
  * ``get(P, key, V)``   → clause failed **silently** (worst case)
  * ``get(P, key, V, D)``→ silently returned the default

String keys lower to ``ast.Constant`` and were never affected; atom keys must
now match that safety property.

See ``todo/query-template-rebinds-atom-dict-keys.md`` and
``implementation_plans/dict-atom-keys-vs-predicates.md`` (Phenomenon B).
"""

from __future__ import annotations

import pytest

from clausal.logic.atoms import mint
import clausal.import_hook  # noqa: F401
from clausal.import_hook import _load_module
from clausal import Var, solve
from clausal.logic import solve as _solve_mod
from clausal.logic.variables import deref
from clausal.terms import DictTerm


ATOMS_SRC = """\
-module(qk_atoms, [mk_profile(P), query_date, other_key])
mk_profile(P) <- ( P is {query_date: 5} )
"""

# ``query_date`` here is a PREDICATE with the same spelling as the key atom
# owned by qk_atoms.  Every read below uses the *qualified* key, so each rule
# is unambiguous by construction — only the dict handed to the goal can be
# wrong.
READER_SRC = """\
-module(qk_reader, [query_date(P, X), soft_read(P, V), strict_read(P, V),
                    default_read(P, V), eligible(P), echo(P, Q)])
-import_module(qk_atoms)
query_date(P, X) <- ( X is 99 )
soft_read(P, V) <- ( get(P, qk_atoms.query_date, V) )
strict_read(P, V) <- ( V is P[qk_atoms.query_date] )
default_read(P, V) <- ( get(P, qk_atoms.query_date, V, -1) )
eligible(P) <- ( get(P, qk_atoms.query_date, V), V > 3 )
echo(P, P),
"""

STR_READER_SRC = """\
-module(qk_str_reader, [query_date(P, X), soft_read(P, V)])
query_date(P, X) <- ( X is 99 )
soft_read(P, V) <- ( get(P, "query_date", V) )
"""

INT_READER_SRC = """\
-module(qk_int_reader, [soft_read(P, V)])
soft_read(P, V) <- ( get(P, 7, V) )
"""


@pytest.fixture(autouse=True)
def _clear_query_cache():
    """``solve._query_cache`` keys on ground argument *values*; clear around
    each test so no entry compiled elsewhere can mask (or be masked by) these."""
    _solve_mod._query_cache.clear()
    yield
    _solve_mod._query_cache.clear()


def _load(tmp_path, name, text):
    src = tmp_path / f"{name}.clausal"
    src.write_text(text)
    return _load_module(name, str(src))


@pytest.fixture
def mods(tmp_path):
    atoms = _load(tmp_path, "qk_atoms", ATOMS_SRC)
    reader = _load(tmp_path, "qk_reader", READER_SRC)
    return atoms, reader


def _clausal_built_profile(atoms):
    """The dict as built *inside* Clausal (crosses the boundary via solve)."""
    P = Var()
    for _ in solve(atoms.mk_profile(P)):
        return deref(P)
    raise AssertionError("mk_profile/1 produced no solution")


def _one(goal):
    """Run a 2-arg reader goal, returning the bound output or None."""
    V = Var()
    for _ in solve(goal(V)):
        return deref(V)
    return None


def test_precondition_bare_name_is_a_different_object(mods):
    """The collision is real: the reader's bare ``query_date`` is its own
    predicate, which is neither identical nor equal to the key atom."""
    atoms, reader = mods
    assert reader.query_date is not atoms.query_date
    assert reader.query_date != atoms.query_date


def test_soft_get3_read_does_not_fail_silently(mods):
    """get/3 — the worst symptom: the clause just failed, no error."""
    atoms, reader = mods
    profile = _clausal_built_profile(atoms)
    assert _one(lambda V: reader.soft_read(profile, V)) == 5


def test_strict_subscript_read_does_not_raise_existence_error(mods):
    """``V is P[key]`` — loud but bogus ``existence_error(dict_key, ...)``."""
    atoms, reader = mods
    profile = _clausal_built_profile(atoms)
    assert _one(lambda V: reader.strict_read(profile, V)) == 5


def test_defaulted_get4_read_does_not_return_the_default(mods):
    """get/4 — silently returned the default instead of the stored value."""
    atoms, reader = mods
    profile = _clausal_built_profile(atoms)
    assert _one(lambda V: reader.default_read(profile, V)) == 5


def test_reported_repro_eligible_yields_one_solution(mods):
    """The exact reproduction filed in the todo."""
    atoms, reader = mods
    profile = _clausal_built_profile(atoms)
    assert len(list(solve(reader.eligible(profile)))) == 1


def test_python_built_dictterm_atom_key_survives(mods):
    """The downstream-harness shape: build the DictTerm in Python from the
    owning module's atom, then query a predicate in another module."""
    atoms, reader = mods
    profile = DictTerm({atoms.query_date: 5})
    assert _one(lambda V: reader.soft_read(profile, V)) == 5


def test_atom_key_identity_preserved_across_the_boundary(mods):
    """Acceptance: the key reaching the callee is the *same object*, not a
    same-named lookup in the callee's namespace."""
    atoms, reader = mods
    profile = DictTerm({atoms.query_date: 5})
    # echo/2 hands the dict straight back, so the key object the callee saw is
    # observable from Python.
    out = _one(lambda V: reader.echo(profile, V))
    assert isinstance(out, DictTerm)
    keys = list(out.keys())
    assert len(keys) == 1
    assert keys[0] == atoms.query_date


def test_atom_in_a_list_argument_survives(mods):
    """Same root cause, same lowering: a bare atom anywhere in a query
    argument was re-resolved in the callee's namespace, not just dict keys."""
    atoms, reader = mods
    out = _one(lambda V: reader.echo([atoms.query_date], V))
    assert out[0] == atoms.query_date


def test_atom_keyed_dict_nested_in_a_list_survives(mods):
    atoms, reader = mods
    out = _one(lambda V: reader.echo([DictTerm({atoms.query_date: 5})], V))
    assert list(out[0].keys())[0] == atoms.query_date


def test_module_internal_atom_reads_still_work(mods):
    """Control: an atom used *within* the module that owns it (the by-name
    lowering, untouched by the fix) still round-trips."""
    atoms, _reader = mods
    profile = _clausal_built_profile(atoms)
    assert list(profile.keys())[0] == atoms.query_date
    assert profile[atoms.query_date] == 5


def test_same_named_atom_from_a_second_load_is_not_conflated(tmp_path):
    """P3-1 §1b/R2 INVERSION: atoms are global-by-spelling interned strs, so
    there is no more by-identity token baked into the cached query template
    to tell apart — a "second load" of the same module mints nothing new at
    all, it just reads the SAME global ``query_date`` str a second time.

    Pre-pivot, loading the owning module twice minted two distinct
    ``query_date`` atom CLASS objects, and a dict keyed by the second load's
    atom was a genuinely different key that had to miss.  Post-pivot both
    loads observe the identical str, so both dict reads must hit.
    """
    atoms = _load(tmp_path, "qk_atoms", ATOMS_SRC)
    reader = _load(tmp_path, "qk_reader", READER_SRC)
    other = _load_module("qk_atoms_second", str(tmp_path / "qk_atoms.clausal"))
    assert other.query_date is atoms.query_date

    assert _one(lambda V: reader.soft_read(DictTerm({atoms.query_date: 5}), V)) == 5
    assert _one(lambda V: reader.soft_read(DictTerm({other.query_date: 5}), V)) == 5
    # ...and back again, for good measure.
    assert _one(lambda V: reader.soft_read(DictTerm({atoms.query_date: 5}), V)) == 5


def test_double_quoted_key_is_an_atom_key(tmp_path):
    """THE FLIP (spec §6.8/§7): the fixture's ``"query_date"`` key is the
    ATOM under the default mode, so an ATOM-keyed dict is what it reads; a
    Python ``str`` key is a STRING key and a different key."""
    reader = _load(tmp_path, "qk_str_reader", STR_READER_SRC)
    assert _one(lambda V: reader.soft_read(
        DictTerm({mint("query_date"): 5}), V)) == 5
    assert _one(lambda V: reader.soft_read(
        DictTerm({"query_date": 5}), V)) is None


def test_int_key_control_still_works(tmp_path):
    reader = _load(tmp_path, "qk_int_reader", INT_READER_SRC)
    profile = DictTerm({7: 5})
    assert _one(lambda V: reader.soft_read(profile, V)) == 5


PRED_KEY_SRC = """\
-module(qk_pred_key, [query_date(P, X), mk(P)])
query_date(P, X) <- ( X is 99 )
mk(P) <- ( P is {query_date: 5} )
"""


def test_predicate_in_key_position_raises_a_named_error(tmp_path):
    """A bare name in key position that resolves to a *predicate* (arity ≥ 1)
    must fail with a Clausal-level diagnostic naming the clash — not a raw
    ``NotImplementedError: unsupported term type PredicateMeta``.

    It must keep failing: a predicate object is not equal to the same-named
    atom, so accepting it would trade a loud crash for a key that can never be
    read back.
    """
    from clausal.logic.compiler.terms_to_ast import PredicateAsTermError

    with pytest.raises(PredicateAsTermError) as exc:
        _load(tmp_path, "qk_pred_key", PRED_KEY_SRC)
    msg = str(exc.value)
    assert "query_date/2" in msg
    assert "is a predicate, not a term value" in msg
    # Points at both escape hatches: qualified atom, or a string key.
    assert "owner.query_date" in msg
    assert '"query_date"' in msg


def test_distinct_dicts_are_not_conflated_by_the_query_cache(mods):
    """Different atom keys/values in back-to-back solves must not share a
    stale compiled template."""
    atoms, reader = mods
    assert _one(lambda V: reader.soft_read(DictTerm({atoms.query_date: 5}), V)) == 5
    assert _one(lambda V: reader.soft_read(DictTerm({atoms.query_date: 7}), V)) == 7
    # A dict whose only key is a DIFFERENT atom must miss (get/3 is soft).
    assert _one(lambda V: reader.soft_read(DictTerm({atoms.other_key: 5}), V)) is None
