"""W4b-1 completeness census: does arm 3 (the NAME) agree with arm 2 (the
class) everywhere the suite asks?

Wraps ``predicate.field_names_for`` for the session and records, per call,
which arm answered and -- for every arm-2 answer -- what arm 3 WOULD have
said.  Prints N, the per-arm counts and the agreement table at session end.

Every number is printed with its denominator.  N == 0 is a REFUSAL, not a
pass: a census over an empty population is the commonest way an instrument
fails open.

IMPORTANT 1 (final fix wave, 2026-09-23): rebinding ``predmod.field_names_for``
alone is not enough.  ``clausal/logic/builtins/inspection.py`` and
``clausal/logic/compiler/_lower_goalop_shared.py`` (at minimum) do
``from clausal.logic.predicate import field_names_for`` at MODULE level --
by ``pytest_configure`` time those modules are already imported, so their
own ``field_names_for`` name is a SEPARATE binding to the ORIGINAL function
object, and rebinding ``predmod.field_names_for`` does not reach back and
change it.  ``functor/3``'s whole construction path (``_construct_named``)
runs through exactly that stale binding, so a suite that drives ``functor/3``,
``copy_term/2``, ``term_variables/2``, ``numbervars/3`` or ``=../2`` reported
``N == 0`` -- the census counted nothing while claiming to be the gate for
those call sites.  Fixed by walking ``sys.modules`` at configure time and
repointing every attribute that IS the original function object (identity,
not name), restoring them all in ``pytest_unconfigure``, and asserting at
configure that no stale reference to the original survives the sweep -- an
instrument that can go blind without saying so is the exact failure mode
this plugin exists to prevent.
"""
import collections
import sys

import pytest

_STATS = collections.Counter()
_RESIDUE = set()
_DISAGREED = []
_CONFIGURED = False


def _shadow_arm3(cls, original):
    """What arm 3 would answer for the name this class is bound under.

    ``original`` MUST be the pre-patch ``field_names_for`` passed in by the
    caller -- never re-imported here.  ``pytest_configure`` below replaces
    ``predmod.field_names_for`` with the counting wrapper for the whole
    session, so an import of ``clausal.logic.predicate.field_names_for``
    done INSIDE this function, after configure, would fetch the PATCHED
    name and re-enter the counter: every arm-2 call would then also tick
    arm3_name (and N twice), which corrupts the very numbers this census
    exists to report.  Always close over / receive the original.
    """
    row = getattr(cls, "_row", None)
    db = getattr(row, "_db", None) if row is not None else None
    return original(cls.__name__,
                    arity=len(getattr(cls, "_fields", ()) or ()),
                    db=db)


def pytest_configure(config):
    import dataclasses

    global _CONFIGURED
    import clausal.logic.predicate as predmod
    from clausal.logic.predicate import PredicateMeta

    # Refuse a second load in the same process (final fix wave, IMPORTANT 1
    # tail): ``_STATS``/``_RESIDUE``/``_DISAGREED`` are module globals with
    # no per-session reset, and ``pytest_unconfigure`` restores
    # unconditionally.  A double ``-p tools.w4b1_census.plugin`` load would
    # double-patch (the second ``original`` captured would actually be the
    # FIRST load's counting wrapper) and then the first unconfigure to run
    # would restore that counting wrapper as if it were "the original" --
    # silently leaving the real accessor permanently wrapped, and the
    # second unconfigure would restore the true original out from under a
    # still-running first census.  Refusing outright is safer than trying
    # to make the patch/restore idempotent around shared mutable globals.
    if _CONFIGURED:
        raise RuntimeError(
            "tools.w4b1_census.plugin: pytest_configure called a second "
            "time in this process -- refusing to double-patch "
            "field_names_for (_STATS/_RESIDUE/_DISAGREED have no "
            "per-session reset and a second unconfigure would restore the "
            "wrong function). Run the census in its own process.")

    original = predmod.field_names_for

    def counting(value, *, arity=None, db=None, namespace=None):
        result = original(value, arity=arity, db=db, namespace=namespace)
        _STATS["N"] += 1
        if isinstance(value, str):
            _STATS["arm3_name"] += 1
        elif isinstance(value, type) and isinstance(value, PredicateMeta):
            _STATS["arm2_class"] += 1
            try:
                shadow = _shadow_arm3(value, original)
            except Exception as exc:                      # noqa: BLE001
                shadow = ("<raised>", type(exc).__name__)
            if shadow is None:
                _STATS["arm2_shadow_unanswerable"] += 1
                _RESIDUE.add(value.__name__)
            elif shadow == result:
                _STATS["arm2_shadow_agreed"] += 1
            else:
                _STATS["arm2_shadow_disagreed"] += 1
                _DISAGREED.append((value.__name__, result, shadow))
        elif isinstance(value, type) and dataclasses.is_dataclass(value):
            _STATS["arm1_dataclass"] += 1
        else:
            _STATS["arm4_none"] += 1
        return result

    predmod.field_names_for = counting

    # Repoint every OTHER already-imported reference to the ORIGINAL
    # function object -- a ``from clausal.logic.predicate import
    # field_names_for`` module-level import (inspection.py,
    # _lower_goalop_shared.py, at minimum) binds its own module's attribute
    # to the original function object at import time, and that binding is
    # untouched by rebinding ``predmod.field_names_for`` above.  Identity
    # match (``is original``), not name match: a module that happens to
    # define an unrelated function or variable also called
    # ``field_names_for`` must not be touched.
    patched_refs = []
    for mod in list(sys.modules.values()):
        if mod is None or mod is predmod:
            continue
        try:
            mod_vars = vars(mod)
        except TypeError:
            continue
        for attr_name, attr_val in list(mod_vars.items()):
            if attr_val is original:
                mod_vars[attr_name] = counting
                patched_refs.append((mod_vars, attr_name))

    config._w4b1_restore = (predmod, original, patched_refs)

    # Assert no stale reference survives the sweep -- this instrument
    # exists to catch exactly this failure mode, so it must not be able to
    # reintroduce it silently.  Any module attribute (predmod's own
    # included) still pointing at ``original`` after the sweep means the
    # census is still blind somewhere.
    stale = []
    for mod_name, mod in list(sys.modules.items()):
        if mod is None:
            continue
        try:
            mod_vars = vars(mod)
        except TypeError:
            continue
        for attr_name, attr_val in mod_vars.items():
            if attr_val is original:
                stale.append(f"{mod_name}.{attr_name}")
    assert not stale, (
        "w4b1 census: stale reference(s) to the ORIGINAL field_names_for "
        f"survived the rebind sweep -- census would be blind there: {stale}")

    _CONFIGURED = True


def pytest_unconfigure(config):
    restore = getattr(config, "_w4b1_restore", None)
    if restore is None:
        return
    predmod, original, patched_refs = restore
    predmod.field_names_for = original
    for mod_vars, attr_name in patched_refs:
        mod_vars[attr_name] = original
    global _CONFIGURED
    _CONFIGURED = False


def pytest_terminal_summary(terminalreporter):
    w = terminalreporter.write_line
    n = _STATS["N"]
    w("")
    w("=" * 68)
    w("W4b-1 COMPLETENESS CENSUS")
    w("=" * 68)
    if n == 0:
        w("REFUSAL: N == 0 -- field_names_for was never called.  This is not")
        w("a pass.  The plugin did not load, or nothing under test reached")
        w("the accessor.  Fix the instrument before reading any other line.")
        return
    w(f"N (total field_names_for calls)          {n}")
    for key, label in (("arm1_dataclass", "arm 1  @dataclass class"),
                       ("arm2_class", "arm 2  PredicateMeta class"),
                       ("arm3_name", "arm 3  a NAME"),
                       ("arm4_none", "arm 4  not term-shaped")):
        c = _STATS[key]
        w(f"  {label:<38} {c:>7}  ({100.0 * c / n:.1f}% of {n})")
    a2 = _STATS["arm2_class"]
    w("")
    w(f"SHADOW READ, over the {a2} arm-2 answers (the denominator):")
    if a2 == 0:
        w("  arm 2 never answered -- the agreement table is VACUOUS.")
    else:
        for key, label in (("arm2_shadow_agreed", "agreed"),
                           ("arm2_shadow_disagreed", "DISAGREED"),
                           ("arm2_shadow_unanswerable", "could not answer")):
            c = _STATS[key]
            w(f"  {label:<38} {c:>7}  ({100.0 * c / a2:.1f}% of {a2})")
    if _DISAGREED:
        w("")
        w("DISAGREEMENTS (each is a defect, not a fallback):")
        for name, got, shadow in _DISAGREED[:40]:
            w(f"  {name}: arm2={got!r} arm3={shadow!r}")
        if len(_DISAGREED) > 40:
            w(f"  ... and {len(_DISAGREED) - 40} more (of {len(_DISAGREED)})")
    if _RESIDUE:
        w("")
        w(f"RESIDUE -- functors arm 3 could not answer ({len(_RESIDUE)}), BY NAME:")
        for name in sorted(_RESIDUE):
            w(f"  {name}")
        w("  Each must be explained by the out-of-tree make_predicate")
        w("  population named in the spec's section 3.  An unexplained name")
        w("  is a gap W4b-3 would turn into a silent failure.")
    w("=" * 68)
