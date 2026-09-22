"""W4b-1 completeness census: does arm 3 (the NAME) agree with arm 2 (the
class) everywhere the suite asks?

Wraps ``predicate.field_names_for`` for the session and records, per call,
which arm answered and -- for every arm-2 answer -- what arm 3 WOULD have
said.  Prints N, the per-arm counts and the agreement table at session end.

Every number is printed with its denominator.  N == 0 is a REFUSAL, not a
pass: a census over an empty population is the commonest way an instrument
fails open.
"""
import collections

import pytest

_STATS = collections.Counter()
_RESIDUE = set()
_DISAGREED = []


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

    import clausal.logic.predicate as predmod
    from clausal.logic.predicate import PredicateMeta

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
    config._w4b1_restore = (predmod, original)


def pytest_unconfigure(config):
    predmod, original = config._w4b1_restore
    predmod.field_names_for = original


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
