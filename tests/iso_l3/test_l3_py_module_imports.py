"""D28 + D32: a Python-backed engine module's predicate signatures
(``clausal.module_signatures``) and importing it from a native ``.pl`` file.

D32 (operator-ruled spelling): ``:- use_module(py/datetime, [date_add/3,
...]).`` applies the seam's ``py.X`` -> ``clausal.modules.py.X`` redirect,
CHECKS each ``name/N`` against the module's signatures (an unknown name or
a wrong arity is a load error naming the ``.pl`` line and listing what the
module offers), and ``use_module(py/datetime)`` imports every predicate the
module has.  A bare atom in the list stays a counted no-op (D11).  The
seam's own ``-import_from`` is unchanged.

Every ``.pl`` load goes through the ``native`` fixture, which asserts the
native loader ran over a non-zero population.
"""
from __future__ import annotations

import textwrap
import warnings

import pytest

import clausal
from clausal.lint_warnings import ClausalBareAtomImportWarning
from clausal.logic.exceptions import LogicException

DATES = """\
due(D) :- timedelta(30, 0, TD), date_add(date(2026, 1, 15), TD, D).
gap(N) :- days_between(date(2026, 1, 15), date(2026, 3, 1), N).
back(N) :- days_between(date(2026, 3, 1), date(2026, 1, 15), N).
"""

SEAM_TWIN = """\
-import_from(py.datetime, [date, date_add, timedelta, days_between])
due(D) <- (timedelta(30, 0, TD), date_add(date(2026, 1, 15), TD, D))
gap(N) <- days_between(date(2026, 1, 15), date(2026, 3, 1), N)
back(N) <- days_between(date(2026, 3, 1), date(2026, 1, 15), N)
"""


def _answers(mod, ans):
    return {p: ans(mod, p) for p in ("due", "gap", "back")}


def _refusal(native, name, text):
    with pytest.raises(SyntaxError) as ei:
        native.load(name, textwrap.dedent(text))
    return ei.value


# ── D28: the accessor ──


def test_signatures_of_a_python_backed_module():
    sig = clausal.module_signatures("py.datetime")
    assert sig["date_add"] == frozenset({3})
    assert sig["timedelta"] == frozenset({3})
    assert sig["days_between"] == frozenset({3})
    assert sig["date_of"] == frozenset({2})
    # date/3 is a term constructor (a plain function), not a predicate.
    assert "date" not in sig
    assert list(sig) == sorted(sig)
    assert len(sig) >= 20, sig


def test_signatures_list_every_arity_of_a_multi_arity_predicate():
    sig = clausal.module_signatures("py.re")
    assert sig["match"] == frozenset({2, 3})


def test_signatures_take_the_import_spellings_and_the_module_object():
    import clausal.modules.py.datetime as pydt
    by_name = clausal.module_signatures("py.datetime")
    assert clausal.module_signatures("date_time") == by_name
    assert clausal.module_signatures(pydt) == by_name
    assert clausal.module_signatures("clausal.modules.py.datetime") == by_name


def test_unit_and_currency_constants_are_not_predicates():
    units = clausal.module_signatures("units")
    assert "metre" not in units and units["strip_units"] == frozenset({2})
    assert clausal.module_signatures("thailand") == {}
    assert clausal.module_signatures("currency")["money"] == frozenset({3})


def test_signatures_of_a_clausal_module(native):
    native.load("d28_lib", "-module(d28_lib, [])\n"
                           "p(1),\np(2),\n"
                           "q(X, Y) <- (p(X), p(Y))\n"
                           "q(X) <- p(X)\n"
                           "-dynamic(counter/1)\n", suffix=".seam")
    assert clausal.module_signatures("d28_lib") == {
        "counter": frozenset({1}), "p": frozenset({1}),
        "q": frozenset({1, 2})}


def test_a_clausal_module_does_not_list_what_it_imports(native):
    native.load("d28_imp", "-module(d28_imp, [r/1])\n"
                           "-import_from(py.datetime, [date_add])\n"
                           "r(X) <- date_add(X, X, X)\n", suffix=".seam")
    assert clausal.module_signatures("d28_imp") == {"r": frozenset({1})}


def test_a_listless_seam_that_is_no_package_offers_its_own(native):
    """Operator ruling M3 applies to a listless PACKAGE __init__ only: a
    plain listless .seam still does not offer what it imports."""
    native.load("d28_imp2", "-import_from(py.datetime, [date_add])\n"
                            "r(X) <- date_add(X, X, X)\n", suffix=".seam")
    assert clausal.module_signatures("d28_imp2") == {"r": frozenset({1})}


def test_an_adapter_without_a_table_answers_from_its_dispatch():
    import types

    class Fixed:
        def _get_dispatch(self):
            def run(this_generator, _proceed, _fail, _catcher, a, b, trail):
                yield from ()
            return run

    class Varargs:
        def _get_dispatch(self):
            def run(this_generator, _proceed, _fail, _catcher, *args):
                yield from ()
            return run

    m = types.ModuleType("d28_fake")
    m.fixed, m.varargs, m.helper = Fixed(), Varargs(), len
    assert clausal.module_signatures(m) == {
        "fixed": frozenset({2}), "varargs": frozenset()}


def test_a_module_predicate_overriding_get_dispatch_is_listed():
    # A ModulePredicate subclass that overrides _get_dispatch and never
    # registers an arity (the table stays EMPTY) is still a predicate: its
    # dispatch does not read the table.  Only an adapter keeping the base
    # _get_dispatch with an empty table (a unit/currency constant) is not.
    import types
    from clausal.logic.solve import defines_predicate, has_predicate
    from clausal.modules.py import ModulePredicate

    class Varargs(ModulePredicate):
        def _get_dispatch(self):
            return self._run

        def _run(self, this_generator, _proceed, _fail, _catcher, *args):
            yield from ()

    class Fixed(ModulePredicate):
        def _get_dispatch(self):
            def run(this_generator, _proceed, _fail, _catcher, a, b, c, trail):
                yield from ()
            return run

    m = types.ModuleType("d28_mp_override")
    m.anyarity, m.three = Varargs("anyarity"), Fixed("three")
    m.constant = ModulePredicate("constant")     # base dispatch, no arity
    assert clausal.module_signatures(m) == {
        "anyarity": frozenset(), "three": frozenset({3})}
    assert has_predicate(m, "anyarity", 4) and defines_predicate(m, "anyarity")
    assert has_predicate(m, "three", 3) and not has_predicate(m, "three", 2)
    assert not has_predicate(m, "constant")


def test_an_unknown_module_name_is_an_existence_error():
    with pytest.raises(LogicException) as ei:
        clausal.module_signatures("no_such_module_d28")
    assert ei.value.term[1] == ("existence_error", "module",
                                "no_such_module_d28")


def test_a_non_module_argument_is_a_type_error():
    with pytest.raises(TypeError):
        clausal.module_signatures(42)


# ── D32: use_module(py/X, ...) from a native .pl ──


def test_a_pl_imports_the_date_predicates_by_indicator(native, ans):
    pl = native.load(
        "d32_ind", ":- use_module(py/datetime, "
                   "[date_add/3, timedelta/3, days_between/3]).\n" + DATES)
    twin = native.load("d32_twin", SEAM_TWIN, suffix=".seam")
    got = _answers(pl, ans)
    assert got == _answers(twin, ans)
    # days_between(A, B, N) is N = A - B in days.
    assert got["gap"] == [-45] and got["back"] == [45]
    assert len(got["due"]) == 1


def test_py_redirect_when_py_is_not_a_package(native, ans, monkeypatch):
    """Outside pytest nothing may have made ``py`` a package: the ``py.X``
    lookup has to be redirected, not left to ``find_spec('py.X')``."""
    import sys
    import types
    monkeypatch.setitem(sys.modules, "py", types.ModuleType("py"))
    monkeypatch.delitem(sys.modules, "py.datetime", raising=False)
    pl = native.load("d32_redir", ":- use_module(py/datetime, "
                                  "[days_between/3]).\n"
                                  "gap(N) :- days_between(date(2026, 1, 15), "
                                  "date(2026, 3, 1), N).\n")
    assert ans(pl, "gap") == [-45]


def test_a_listless_use_module_imports_every_predicate(native, ans):
    pl = native.load("d32_all", ":- use_module(py/datetime).\n" + DATES
                     + "wd(W) :- weekday(date(2026, 9, 30), W).\n")
    twin = native.load("d32_twin2", SEAM_TWIN, suffix=".seam")
    assert _answers(pl, ans) == _answers(twin, ans)
    assert len(ans(pl, "wd")) == 1


def test_a_wrong_arity_is_a_load_error_listing_the_offer(native):
    err = _refusal(native, "d32_arity",
                   "a.\n:- use_module(py/datetime, [date_add/2]).\n")
    assert err.lineno == 2
    msg = str(err)
    assert "date_add/2" in msg and "date_add/3" in msg
    assert "days_between/3" in msg          # lists what the module offers


def test_an_unknown_name_is_a_load_error(native):
    err = _refusal(native, "d32_unk",
                   "a.\n\n:- use_module(py/datetime, [no_such_pred/1]).\n")
    assert err.lineno == 3
    assert "no_such_pred/1" in str(err) and "date_add/3" in str(err)


def test_a_bare_atom_entry_stays_a_counted_no_op(native, ans):
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        pl = native.load("d32_bare", ":- use_module(py/datetime, "
                                     "[date_add, timedelta/3]).\n"
                                     "t(TD) :- timedelta(1, 0, TD).\n")
    assert [x for x in w
            if issubclass(x.category, ClausalBareAtomImportWarning)]
    assert len(ans(pl, "t")) == 1


def test_a_missing_py_module_is_a_located_error(native):
    err = _refusal(native, "d32_nopy",
                   "a.\n:- use_module(py/no_such_py_mod, [p/1]).\n")
    assert err.lineno == 2 and "py.no_such_py_mod" in str(err)


def test_the_seam_still_refuses_an_indicator_against_a_python_module(native):
    with pytest.raises(ImportError, match="not a Clausal module"):
        native.load("d32_seam", "-import_from(py.datetime, [date_add/3])\n"
                                "a,\n", suffix=".seam")


# ── review round: the routes around the Python path ──

_ADAPTERS = '''\
class _Varargs:
    def _get_dispatch(self):
        def run(this_generator, _proceed, _fail, _catcher, *args):
            yield (_proceed, None)
        return run


class _Fixed:
    def _get_dispatch(self):
        def run(this_generator, _proceed, _fail, _catcher, x, trail):
            yield (_proceed, None)
        return run


anyarity = _Varargs()
one = _Fixed()
'''


def _pyfile(native, name, text):
    (native.tmp / f"{name}.py").write_text(text, encoding="utf-8")
    native._names.append(name)


def test_an_adapter_of_unknown_arity_is_accepted_and_offered_as_n_q(native):
    _pyfile(native, "d32_adapters", _ADAPTERS)
    assert clausal.module_signatures("d32_adapters") == {
        "anyarity": frozenset(), "one": frozenset({1})}
    native.load("d32_anyok", ":- use_module(d32_adapters, [anyarity/5]).\n"
                             "t :- anyarity(1, 2, 3, 4, 5).\n")
    err = _refusal(native, "d32_anybad",
                   "a.\n:- use_module(d32_adapters, [one/2]).\n")
    assert "anyarity/?" in str(err) and "one/1" in str(err)


def test_only_bare_atoms_from_a_python_module_import_nothing(native, ans):
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", ClausalBareAtomImportWarning)
        pl = native.load("d32_onlybare", ":- use_module(py/datetime, "
                                         "[date_add]).\nt(1).\n")
    assert ans(pl, "t") == [1]
    assert "date_add" not in vars(pl)


def test_a_python_file_carrying_a_clausal_database_keeps_the_clausal_route(
        native):
    """A Python module with a ``$module`` database (built through the Python
    API) is a Clausal module: its entries go to the seam as indicators, and
    the seam's own existence check answers -- not the D32 signature check."""
    _pyfile(native, "d32_pydb",
            "from clausal.logic.database import Module\n"
            "globals()['$module'] = Module('d32_pydb', "
            "module_dict=globals())\n")
    with pytest.raises(Exception) as ei:
        native.load("d32_viadb", "a.\n:- use_module(d32_pydb, [reach/2]).\n")
    assert "reach" in str(ei.value)
    assert "offers" not in str(ei.value)        # not the D32 refusal


def test_a_module_with_a_missing_dependency_is_not_reported_absent(native):
    _pyfile(native, "d32_brokendep", "import no_such_dependency_d32\n")
    with pytest.raises(ModuleNotFoundError) as ei:
        clausal.module_signatures("d32_brokendep")
    assert ei.value.name == "no_such_dependency_d32"
