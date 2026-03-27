"""
Verification script for the TitleCase → snake_case predicate rename.

Run from the repo root:
    python implementation_plans/bigrename/verify.py

Zero output (plus the "KNOWN INTENTIONAL" lines) means the rename is clean.
Any other output is either a bug or a new item for the DECISION RECORD in
verification_plan.txt.
"""

import re
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent.parent
# Ensure we import from this repo, not any installed (possibly stale) package.
sys.path.insert(0, str(ROOT))

# ── Check 1: TitleCase entries in BUILTIN_NAME_MAP ────────────────────────────

print("=== Check 1: TitleCase entries in BUILTIN_NAME_MAP ===")

from clausal.tools.prolog_dialect import BUILTIN_NAME_MAP

titlecase_builtins = [
    name for name in BUILTIN_NAME_MAP
    if name[0].isupper()
]

if titlecase_builtins:
    for name in sorted(titlecase_builtins):
        print(f"  TITLECASE BUILTIN: {name}")
else:
    print("  OK - all Clausal builtin names are snake_case (modulo known exceptions)")

# ── Check 2: Round-trip bijection ─────────────────────────────────────────────

print("\n=== Check 2: Clausal→Prolog→Clausal round-trip ===")

from clausal.tools.prolog_to_clausal import _REVERSE_BUILTIN_MAP

KNOWN_INTENTIONAL_ASYMMETRIES = {
    # (clausal_name, prolog_name): reason
    ("is_str", "atom"): (
        "Prolog has no separate string/atom distinction; "
        "both `atom` and `is_str` map to `atom/1`. "
        "prolog_to_clausal resolves `atom` to Clausal `atom`, not `is_str`. Intentional."
    ),
}

broken = []
for clausal_name, (iso, swi, scryer) in BUILTIN_NAME_MAP.items():
    for prolog_name in sorted(set(filter(None, [iso, swi, scryer]))):
        back = _REVERSE_BUILTIN_MAP.get(prolog_name)
        if back != clausal_name:
            key = (clausal_name, prolog_name)
            if key in KNOWN_INTENTIONAL_ASYMMETRIES:
                print(f"  KNOWN INTENTIONAL: {clausal_name} -> {prolog_name} -> {back}")
                print(f"    Reason: {KNOWN_INTENTIONAL_ASYMMETRIES[key]}")
            else:
                broken.append((clausal_name, prolog_name, back))

if broken:
    for c, p, b in sorted(broken):
        print(f"  BUG: {c} -> {p} -> {b}  (reverse map returns {b!r}, expected {c!r})")
else:
    print("  OK - all round-trips intact (modulo known intentional asymmetries)")

# ── Check 3: TitleCase builtin calls in .clausal files ────────────────────────

print("\n=== Check 3: Remaining TitleCase builtin calls in .clausal files ===")

from clausal.logic.builtins import _BUILTIN_CLASSES

builtin_names = set(_BUILTIN_CLASSES.keys())
# Also include old TitleCase names that may have been missed
# (derive them from the current snake_case names via pascal conversion)
from clausal.tools.prolog_dialect import snake_to_pascal
old_titlecase_names = {snake_to_pascal(n): n for n in builtin_names if n != snake_to_pascal(n)}

hits = []
for path in sorted(ROOT.glob("**/*.clausal")):
    # Skip golden files (they're derived, not source)
    if "prolog_golden" in str(path):
        continue
    try:
        text = path.read_text()
    except Exception:
        continue
    for lineno, line in enumerate(text.splitlines(), 1):
        # Skip comment lines
        stripped = line.strip()
        if stripped.startswith("#") or stripped.startswith("%"):
            continue
        for m in re.finditer(r'\b([A-Z][A-Za-z_0-9]+)\s*\(', line):
            name = m.group(1)
            if name in old_titlecase_names:
                hits.append((str(path.relative_to(ROOT)), lineno, name,
                             old_titlecase_names[name]))

if hits:
    for filepath, lineno, old, new in hits:
        print(f"  MISSED RENAME: {filepath}:{lineno}: {old}(  (should be {new}()")
else:
    print("  OK - no old TitleCase builtin calls found in .clausal source files")

# ── Check 4: Duplicate Prolog targets in BUILTIN_NAME_MAP ─────────────────────

print("\n=== Check 4: Multiple Clausal names mapping to the same Prolog name ===")
print("    (these cause first-occurrence-wins bugs in the reverse map)")

KNOWN_INTENTIONAL_DUPES = {
    # prolog_name: [clausal_names]  — documented intentional many-to-one
    "atom": ["atom", "is_str"],
}

from collections import defaultdict
prolog_to_clausal_list = defaultdict(list)
for clausal_name, (iso, swi, scryer) in BUILTIN_NAME_MAP.items():
    for prolog_name in set(filter(None, [iso, swi, scryer])):
        prolog_to_clausal_list[prolog_name].append(clausal_name)

dupes_found = False
for prolog_name, clausal_names in sorted(prolog_to_clausal_list.items()):
    if len(clausal_names) > 1:
        known = KNOWN_INTENTIONAL_DUPES.get(prolog_name, [])
        if sorted(clausal_names) == sorted(known):
            print(f"  KNOWN INTENTIONAL: {prolog_name} <- {clausal_names}")
        else:
            print(f"  COLLISION: Prolog `{prolog_name}` is the target of multiple "
                  f"Clausal names: {clausal_names}")
            print(f"    Only the first one wins in the reverse map.")
            dupes_found = True

if not dupes_found:
    print("  OK - no unexpected collisions (modulo known intentional ones)")

# ── Summary ───────────────────────────────────────────────────────────────────

print("\n=== Summary ===")
issues = len(titlecase_builtins) + len(broken) + len(hits) + (1 if dupes_found else 0)
if issues == 0:
    print("  All checks passed. Rename looks clean.")
else:
    print(f"  {issues} issue category/categories found. See output above.")
    sys.exit(1)
