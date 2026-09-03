"""Phase 1 funnel guard: no NEW direct-probe patterns outside the funnel.

Tasks 1-3 (see ``docs/superpowers/plans/2026-09-03-phase1-funnel.md``) filled
the term-probe accessor funnel (``is_atom``, ``functor_arity``,
``term_field_names_of_class``, ``term_field_dict``, ...) in
``clausal/logic/predicate.py`` / ``clausal/logic/builtins/_helpers.py`` and
migrated the safe call sites onto it.  This test *freezes that state*: it
greps the runtime tree for the two hand-rolled idioms the funnel replaces and
fails if either appears anywhere that isn't:

  1. one of the two funnel modules themselves (they ARE the canonical
     definitions and are allowed to contain the raw idiom once, at the
     ``is_atom``/``_functor_name`` implementation sites), or
  2. a file/line-range on the ALLOWLIST below, which transcribes the plan's
     Global Constraints exclusion list verbatim (source: "EXCLUSION LIST —
     do not touch these" in
     ``docs/superpowers/plans/2026-09-03-phase1-funnel.md``, plus the two
     task-level "skip for cause" sites recorded in ``task-2-report.md`` /
     ``task-3-report.md``, plus one additional pre-existing site this test
     found that was outside the Phase 1 site inventory — see its entry
     below).

The two patterns:

  * ``atom_bypass``  — ``isinstance(X, PredicateMeta) and not X._fields``
    (the hand-rolled "is this a zero-arity atom class" check that
    ``is_atom`` replaces; also matches the
    ``isinstance(X, type) and isinstance(X, PredicateMeta) and not X._fields``
    three-clause variant).
  * ``functor_fallback`` — ``getattr(X, "functor", None) or type(X).__name__``
    (the hand-rolled functor-name-with-fallback idiom that
    ``clausal.logic.builtins._helpers._functor_name`` replaces — a
    ``type(x).__name__``-as-functor probe).

This is deliberately a narrow, literal, "grep-driven" check (per the task
brief) rather than a general AST classifier: it catches the *exact* idioms
the funnel migration removed, not every legitimate ``isinstance(x,
PredicateMeta)`` or ``type(x).__name__`` use (of which there are many, e.g.
dispatch-table membership tests and error-message formatting — those are
NOT the funnel's concern and are correctly ignored by the narrow regexes
below).

Caveat: the scan is textual, not AST-aware, so it would false-positive on
either idiom appearing verbatim inside a comment or a string literal (e.g.
a docstring quoting the pattern for exposition). This is an accepted
tradeoff for a "grep-driven" check per the task brief; there is no live
instance of it in the tree today, and a real occurrence would be an easy,
obvious false positive to diagnose and silence with a one-line ALLOWLIST
entry rather than a silent miss.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from fnmatch import fnmatch
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parent.parent
_CLAUSAL_ROOT = _REPO_ROOT / "clausal"
_PLAN = "docs/superpowers/plans/2026-09-03-phase1-funnel.md"


# ── the two disallowed idioms ─────────────────────────────────────────────────

# isinstance(X, PredicateMeta) and not X._fields
#   -- optionally preceded by "isinstance(X, type) and " (the three-clause
#      variant used where callers first need to rule out non-class objects)
#   -- tolerant of a "\<newline>" line-continuation between the isinstance
#      clause and the "not X._fields" clause (predicate.py's own definition
#      is written that way).
_ATOM_BYPASS_RE = re.compile(
    r"isinstance\(\s*(\w+)\s*,\s*"
    r"(?:type\s*\)\s*and\s*isinstance\(\s*\1\s*,\s*)?"
    r"PredicateMeta\s*\)\s*and\s*(?:\\\s*\n\s*)?not\s+\1\._fields"
)

# getattr(X, "functor", None) or type(X).__name__
_FUNCTOR_FALLBACK_RE = re.compile(
    r'getattr\(\s*(\w+)\s*,\s*["\']functor["\']\s*,\s*None\s*\)\s*or\s*'
    r"type\(\s*\1\s*\)\.__name__"
)

_PATTERNS = {
    "atom_bypass": _ATOM_BYPASS_RE,
    "functor_fallback": _FUNCTOR_FALLBACK_RE,
}


# ── funnel modules: the canonical definition sites, exempt wholesale ─────────
#
# These are the two files Task 1 (see the plan) added the accessors to; the
# raw idioms are their *implementation*, not a bypass of themselves.
_FUNNEL_MODULES = {
    "clausal/logic/predicate.py",
    "clausal/logic/builtins/_helpers.py",
}


@dataclass(frozen=True)
class AllowEntry:
    path: str  # relative to repo root; may contain fnmatch wildcards
    lines: tuple[int, int] | None  # inclusive 1-based range, or None = whole file
    reason: str
    patterns: frozenset[str] = frozenset(_PATTERNS)  # which pattern(s) it covers


# ── ALLOWLIST ──────────────────────────────────────────────────────────────
#
# Transcribed from the Global Constraints "EXCLUSION LIST" of
# docs/superpowers/plans/2026-09-03-phase1-funnel.md (items numbered to
# match), plus the Task 2/3 "skip for cause" sites, plus one pre-existing
# site (last entry) this lint found outside that inventory.
ALLOWLIST: tuple[AllowEntry, ...] = (
    # 1. hand-ordered hot cascade; branch order load-bearing. Scoped to the
    #    two named functions (not the whole file, which also has plenty of
    #    unrelated dispatch-building code worth keeping lint-checked).
    AllowEntry("clausal/logic/compiler/arg_index.py", (84, 181),
               "plan exclusion #1: _runtime_arg_key/_arg_to_index_key hot cascade"),
    # 2. byte-parity with the C tabling core twin. Scoped to the named
    #    function only, for the same reason as #1.
    AllowEntry("clausal/logic/tabling.py", (396, 443),
               "plan exclusion #2: _normalize_for_key_py, C-twin byte parity"),
    # 3. the five synced walkers (Python arms only; C arms aren't .py).
    AllowEntry("clausal/logic/solve.py", (58, 122),
               "plan exclusion #3: _deref_walk_py, synced with its C arm"),
    AllowEntry("clausal/logic/builtins/inspection.py", (22, 91),
               "plan exclusion #3: _copy_term_py, synced with its C arm"),
    AllowEntry("clausal/logic/builtins/inspection.py", (92, 188),
               "plan exclusion #3: _collect_vars_py, synced with its C arm"),
    # 4. unify inner loop, already funneled.
    AllowEntry("clausal/logic/constraints.py", (161, 205),
               "plan exclusion #4: _structural_unify_oc, unify inner loop"),
    # 5. deliberately narrower than term_field_names (drops compare=False
    #    dataclass fields) -- must stay hand-rolled, not funneled.
    AllowEntry("clausal/logic/compiler/head_match.py", (71, 104),
               "plan exclusion #5: _matched_field_names, deliberately narrower"),
    # 6. nominal-only by design; funnel would WIDEN matching.
    AllowEntry("clausal/logic/coroutining.py", None,
               "plan exclusion #6: nonvar/ground name probes, nominal-only"),
    # 7. KWTerm._fields is a keyword dict, NOT PredicateMeta._fields.
    AllowEntry("clausal/terms.py", (180, 280),
               "plan exclusion #7: KWTerm._fields is a dict, not PredicateMeta._fields"),
    # 8. class-registry _fields/PredicateMeta uses (class-level ops, not term
    #    probes) -- except the two migrated compiler_v2.py class-arity reads,
    #    which no longer match these patterns anyway.
    AllowEntry("clausal/logic/specialization.py", None,
               "plan exclusion #8: class-registry op, not a term probe"),
    AllowEntry("clausal/logic/compiler_v2.py", None,
               "plan exclusion #8: class-registry op, not a term probe"),
    AllowEntry("clausal/logic/compiler/predicate.py", None,
               "plan exclusion #8/#9: class-registry op / CPython-ast site"),
    # 9. CPython-`ast` sites.
    AllowEntry("clausal/codegen.py", None, "plan exclusion #9: CPython-ast site"),
    AllowEntry("clausal/logic/compiler/_ast_helpers.py", None,
               "plan exclusion #9: CPython-ast site"),
    AllowEntry("clausal/logic/compiler/invariants.py", None,
               "plan exclusion #9: CPython-ast site"),
    AllowEntry("clausal/templating/*.py", None, "plan exclusion #9: CPython-ast site"),
    AllowEntry("clausal/tools/prolog_ast.py", None, "plan exclusion #9: CPython-ast site"),
    AllowEntry("clausal/reflection.py", (1011, 1049),
               "plan exclusion #9: CPython-ast site (Embedded Python "
               "classification, ~1027; note this is clausal/reflection.py, "
               "NOT clausal/modules/reflection.py -- exclusion #13 below is "
               "the modules/ one)"),
    # 10. type(x).__name__-in-error-message sites (functor_fallback pattern
    #     only -- these files legitimately use type(x).__name__ in messages).
    AllowEntry("clausal/logic/clp*.py", None,
               "plan exclusion #10: type(x).__name__ in error messages",
               frozenset({"functor_fallback"})),
    AllowEntry("clausal/logic/clportools*.py", None,
               "plan exclusion #10: type(x).__name__ in error messages",
               frozenset({"functor_fallback"})),
    AllowEntry("clausal/modules/py/*.py", None,
               "plan exclusion #10: type(x).__name__ in error messages",
               frozenset({"functor_fallback"})),
    AllowEntry("clausal/logic/_trampoline_py.py", None,
               "plan exclusion #10: type(x).__name__ in error messages",
               frozenset({"functor_fallback"})),
    # 11. deliberately tolerant getattr for foreign-copy objects.
    AllowEntry("clausal/predicate_diagnostics.py", None,
               "plan exclusion #11: tolerant getattr for foreign-copy objects"),
    AllowEntry("clausal/import_diagnostics.py", None,
               "plan exclusion #11: tolerant getattr for foreign-copy objects"),
    # 12. predicate-class-in-term-position ERROR check -- not an atom probe.
    AllowEntry("clausal/logic/compiler/terms_to_ast.py", (734, 740),
               "plan exclusion #12: PredicateAsTermError check, not an atom probe"),
    # 13. name lookup may be funneled but the class-identity re-check stays.
    AllowEntry("clausal/modules/reflection.py", (285, 296),
               "plan exclusion #13: class-identity re-check must stay hand-rolled"),
    # 14. goal_expansion.py has an unrelated module-local _functor_name;
    #     prefer not touching the file.
    AllowEntry("clausal/logic/goal_expansion.py", None,
               "plan exclusion #14: unrelated local _functor_name, prefer not touching"),

    # ── Task-level "skip for cause" sites (not plan-exclusion-list items;
    #    recorded per-task after the site inventory showed migrating them
    #    would change behavior) ──────────────────────────────────────────
    # task-2-report.md: functor/3's _functor_name + _arity double walk is
    # deliberately NOT collapsed to functor_arity() -- functor_arity is
    # narrower on KWTerm/atomic shapes and migrating would change behavior.
    AllowEntry("clausal/logic/builtins/inspection.py", (235, 282),
               "task-2 skip: functor/3's composed _functor_name+_arity calls "
               "(functor_arity is narrower here; migrating would change behavior)"),
    # task-3-report.md: testing.py's clause-leaves diagnostic head-name
    # fallback semantics diverge from _functor_name and must stay hand-rolled.
    AllowEntry("clausal/testing.py", (2046, 2160),
               "task-3 skip: diagnostic head-name fallback, semantics diverge "
               "from _functor_name (see task-3-report.md determination)"),
    # task-2-report.md / plan Task 2 text: "leave head_key itself as-is (it
    # is the canonical pair function; do not rewrite it this phase)".
    AllowEntry("clausal/logic/database.py", (524, 556),
               "task-2 instruction: head_key is the canonical pair function, "
               "left as-is this phase (plan Task 2 file list)"),

    # ── Pre-existing site found by this lint, outside the Phase 1 site
    #    inventory (never named in the plan or any Task 1-3 file list).
    #    Not migrated this phase; see
    #    todo/funnel-term-str-locale-atom-bypass-not-migrated-2026-09-03.md ──
    AllowEntry("clausal/terms.py", (2355, 2457),
               "pre-existing, out-of-inventory site: term_str's locale-"
               "translation atom-display branch; parked as a todo, not "
               "migrated this phase"),
)


def _matches_entry(rel_posix: str, line: int, pattern_name: str, entry: AllowEntry) -> bool:
    if pattern_name not in entry.patterns:
        return False
    if not fnmatch(rel_posix, entry.path):
        return False
    if entry.lines is None:
        return True
    lo, hi = entry.lines
    return lo <= line <= hi


@dataclass(frozen=True)
class Violation:
    path: str
    line: int
    pattern: str
    snippet: str

    def __str__(self) -> str:  # pragma: no cover - formatting only
        return f"{self.path}:{self.line}: disallowed {self.pattern} pattern: {self.snippet!r}"


def find_violations(
    scan_root: Path,
    *,
    allowlist: tuple[AllowEntry, ...] = ALLOWLIST,
    funnel_modules: frozenset[str] = frozenset(_FUNNEL_MODULES),
    repo_root: Path | None = None,
) -> list[Violation]:
    """Scan every ``*.py`` under *scan_root* for the two disallowed idioms.

    Paths are reported (and matched against *allowlist* / *funnel_modules*)
    relative to *repo_root* (default: *scan_root* itself, so a self-test
    pointed at a bare tmp directory gets paths relative to that tmp dir --
    which then can't collide with any real allowlist entry).
    """
    root_for_relpath = repo_root if repo_root is not None else scan_root
    violations: list[Violation] = []
    for path in sorted(scan_root.rglob("*.py")):
        rel = path.relative_to(root_for_relpath).as_posix()
        if rel in funnel_modules:
            continue
        text = path.read_text(encoding="utf-8")
        for pattern_name, regex in _PATTERNS.items():
            for m in regex.finditer(text):
                line = text.count("\n", 0, m.start()) + 1
                if any(_matches_entry(rel, line, pattern_name, e) for e in allowlist):
                    continue
                snippet = m.group(0).replace("\n", " ")
                violations.append(Violation(rel, line, pattern_name, snippet))
    return violations


# ── Test 1: the lint passes on the migrated tree ─────────────────────────────


def test_migrated_tree_has_no_disallowed_funnel_bypass_patterns():
    violations = find_violations(_CLAUSAL_ROOT, repo_root=_REPO_ROOT)
    assert not violations, (
        "New (or un-allowlisted) funnel-bypass pattern(s) found -- either "
        "migrate the site onto the funnel (predicate.is_atom / "
        f"_helpers.functor_arity) or add a justified entry to ALLOWLIST in "
        f"this file, citing {_PLAN}:\n"
        + "\n".join(f"  {v}" for v in violations)
    )


# ── Test 1b: ALLOWLIST self-check -- every entry must point at something real
#
# This is the structural fix for the two "transcribed against the wrong
# file" bugs a review caught (a nonexistent `compiler/specialization.py`
# path, and a line range checked against the wrong `reflection.py` of two
# same-named files): a glob-free entry whose path doesn't exist, or whose
# line range falls outside the file it names, is silently a dead no-op --
# it exempts nothing, so the corresponding plan-exclusion item goes
# unencoded without the real-tree scan (Test 1) necessarily failing (it
# only fails if that dead entry's file *also* happens to contain the
# pattern). Checking existence/bounds mechanically, rather than trusting a
# transcription by eye, is exactly what would have caught both bugs.


def test_allowlist_entries_point_at_real_paths_and_in_range_lines():
    problems = []
    for entry in ALLOWLIST:
        if any(ch in entry.path for ch in "*?["):
            # Glob entry (e.g. "clausal/logic/clp*.py") -- must match at
            # least one real file, and globs don't carry a line range.
            matches = [
                p for p in _CLAUSAL_ROOT.rglob("*.py")
                if fnmatch(p.relative_to(_REPO_ROOT).as_posix(), entry.path)
            ]
            if not matches:
                problems.append(f"{entry.path}: glob matches no file under clausal/")
            if entry.lines is not None:
                problems.append(f"{entry.path}: glob entry must not carry a line range")
            continue
        full = _REPO_ROOT / entry.path
        if not full.is_file():
            problems.append(f"{entry.path}: no such file (reason: {entry.reason!r})")
            continue
        if entry.lines is not None:
            lo, hi = entry.lines
            n_lines = sum(1 for _ in full.open(encoding="utf-8"))
            if not (1 <= lo <= hi <= n_lines):
                problems.append(
                    f"{entry.path}: line range {entry.lines} out of bounds "
                    f"(file has {n_lines} lines)"
                )
    assert not problems, "ALLOWLIST entries pointing at nothing real:\n" + "\n".join(
        f"  {p}" for p in problems
    )


# ── Test 2: self-test, proves BOTH directions ────────────────────────────────
#
# A synthetic bad file is written to tmp_path (never the real repo) so these
# tests prove the checker actually *fires* on the exact disallowed idioms,
# not merely that the (possibly-miscalibrated) real-tree scan above is quiet.


_BAD_ATOM_BYPASS_SNIPPET = '''\
from clausal.logic.predicate import PredicateMeta

def _sneaky_is_atom(x):
    return isinstance(x, PredicateMeta) and not x._fields
'''

_BAD_FUNCTOR_FALLBACK_SNIPPET = '''\
def _sneaky_functor(term):
    return getattr(term, "functor", None) or type(term).__name__
'''

_CLEAN_SNIPPET = '''\
from clausal.logic.predicate import is_atom
from clausal.logic.builtins._helpers import functor_arity

def _proper_is_atom(x):
    return is_atom(x)

def _proper_functor(term):
    return functor_arity(term)

def _unrelated_isinstance_use(x):
    # A legitimate isinstance(..., PredicateMeta) check with no ._fields
    # probe at all -- must NOT be flagged.
    return not isinstance(x, PredicateMeta)
'''


@pytest.mark.parametrize(
    "snippet, expected_pattern",
    [
        (_BAD_ATOM_BYPASS_SNIPPET, "atom_bypass"),
        (_BAD_FUNCTOR_FALLBACK_SNIPPET, "functor_fallback"),
    ],
)
def test_lint_catches_injected_bypass_pattern(tmp_path, snippet, expected_pattern):
    bad_file = tmp_path / "sneaky_bypass.py"
    bad_file.write_text(snippet, encoding="utf-8")

    violations = find_violations(tmp_path)

    assert len(violations) == 1, violations
    (v,) = violations
    assert v.pattern == expected_pattern
    assert v.path == "sneaky_bypass.py"


def test_lint_does_not_flag_funneled_or_unrelated_code(tmp_path):
    clean_file = tmp_path / "proper.py"
    clean_file.write_text(_CLEAN_SNIPPET, encoding="utf-8")

    violations = find_violations(tmp_path)

    assert violations == []


def test_lint_ignores_bypass_pattern_inside_a_funnel_module(tmp_path):
    """The funnel modules' own is_atom/_functor_name implementations are the
    canonical *definition* sites for the raw idiom, not a bypass of it."""
    fake_module_dir = tmp_path / "clausal" / "logic"
    fake_module_dir.mkdir(parents=True)
    (fake_module_dir / "predicate.py").write_text(_BAD_ATOM_BYPASS_SNIPPET, encoding="utf-8")

    violations = find_violations(tmp_path, funnel_modules=frozenset({"clausal/logic/predicate.py"}))

    assert violations == []


def test_lint_ignores_bypass_pattern_inside_an_allowlisted_line_range(tmp_path):
    """A site matching an ALLOWLIST (path, line-range) entry is not flagged,
    but the same pattern one line outside that range still is -- proves the
    allowlist is line-scoped, not whole-file-by-accident."""
    target = tmp_path / "scoped.py"
    target.write_text(
        "x = 1\n"  # line 1
        "def allowed():\n"  # line 2
        "    return isinstance(x, PredicateMeta) and not x._fields\n"  # line 3
        "def not_allowed():\n"  # line 4
        "    return isinstance(x, PredicateMeta) and not x._fields\n",  # line 5
        encoding="utf-8",
    )
    scoped_allowlist = (
        AllowEntry("scoped.py", (2, 3), "test fixture: only lines 2-3 allowed"),
    )

    violations = find_violations(tmp_path, allowlist=scoped_allowlist)

    assert len(violations) == 1, violations
    assert violations[0].line == 5
