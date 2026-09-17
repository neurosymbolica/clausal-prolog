"""Phase 1 funnel guard: no NEW direct-probe patterns outside the funnel.

Tasks 1-3 (see ``docs/superpowers/plans/2026-09-03-phase1-funnel.md``) filled
the term-probe accessor funnel (``is_zero_field_class``, ``functor_arity``,
``term_field_names_of_class``, ``term_field_dict``, ...) in
``clausal/logic/predicate.py`` / ``clausal/logic/builtins/_helpers.py`` and
migrated the safe call sites onto it.  This test *freezes that state*: it
greps the runtime tree for the two hand-rolled idioms the funnel replaces and
fails if either appears anywhere that isn't:

  1. one of the two funnel modules themselves (they ARE the canonical
     definitions and are allowed to contain the raw idiom once, at the
     ``is_zero_field_class``/``_functor_name`` implementation sites), or
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
    ``predicate.is_zero_field_class`` replaces — Task 12 of the
    atoms-as-cells/strings plan renamed it out of the ``is_atom`` stem,
    which now means the TERM test in ``clausal.logic.atoms``; also matches
    the
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
    r"isinstance\(\s*([\w.]+)\s*,\s*"
    r"(?:type\s*\)\s*and\s*isinstance\(\s*\1\s*,\s*)?"
    r"PredicateMeta\s*\)\s*and\s*(?:\\\s*\n\s*)?not\s+\1\._fields"
)

# getattr(X, "functor", None) or type(X).__name__
#   -- X's group is [\w.]+ (not \w+) so a dotted receiver like "clause.head"
#      is caught, not just a bare name.
_FUNCTOR_FALLBACK_RE = re.compile(
    r'getattr\(\s*([\w.]+)\s*,\s*["\']functor["\']\s*,\s*None\s*\)\s*or\s*'
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
    # Relative to repo root; may contain fnmatch wildcards. Unlike a shell
    # glob or pathlib's Path.glob, fnmatch's "*" is not "/"-aware -- it
    # matches across directory separators too, so e.g. "clausal/templating/
    # *.py" also allowlists a file in a nested subdirectory of templating/,
    # not just one directly under it. Every current glob entry below (see
    # exclusion #9) is a "whole subtree, any depth" exemption anyway, so this
    # is intentional/known, not a gap -- flagged here so a future narrower
    # glob entry isn't added assuming single-level "*" semantics.
    path: str
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
    # 6. nominal-only by design; funnel would WIDEN matching. Scoped to
    #    _install_when_condition, the function containing the nonvar/ground
    #    name probes (not the whole file).
    AllowEntry("clausal/logic/coroutining.py", (127, 174),
               "plan exclusion #6: nonvar/ground name probes, nominal-only"),
    # 7. KWTerm._fields is a keyword dict, NOT PredicateMeta._fields.
    AllowEntry("clausal/terms.py", (180, 280),
               "plan exclusion #7: KWTerm._fields is a dict, not PredicateMeta._fields"),
    # 8. class-registry _fields/PredicateMeta uses (class-level ops, not term
    #    probes) -- except the two migrated compiler_v2.py class-arity reads,
    #    which no longer match these patterns anyway.
    AllowEntry("clausal/logic/specialization.py", None,
               "plan exclusion #8: class-registry op, not a term probe"),
    # compiler_v2.py: scoped to the individual functions that hold
    # class-registry isinstance(x, PredicateMeta) checks, deliberately
    # carving OUT the two migrated class-arity reads (module_dict.get(functor)
    # / isinstance(cls, PredicateMeta) / term_field_names_of_class(cls) at
    # lines 650-654 in _validate_directive_targets and 681-686 in
    # _refuse_untablable_target -- item 7's reorder put the isinstance guard
    # first, so the range shifted from where task 2/3 originally left it) --
    # those lines must stay lint-checked so a regression back to the old
    # "isinstance(...) and not X._fields" idiom there would be caught, not
    # silently re-exempted by a whole-file entry.
    AllowEntry("clausal/logic/compiler_v2.py", (124, 383),
               "plan exclusion #8: class-registry op, not a term probe "
               "(compile_module)"),
    AllowEntry("clausal/logic/compiler_v2.py", (515, 542),
               "plan exclusion #8: class-registry op, not a term probe "
               "(_import_from_origins)"),
    AllowEntry("clausal/logic/compiler_v2.py", (543, 608),
               "plan exclusion #8: class-registry op, not a term probe "
               "(_reject_redefinition_of_imported_predicates)"),
    AllowEntry("clausal/logic/compiler_v2.py", (609, 649),
               "plan exclusion #8: class-registry op, not a term probe "
               "(_validate_directive_targets, before the migrated arity read)"),
    AllowEntry("clausal/logic/compiler_v2.py", (655, 663),
               "plan exclusion #8: class-registry op, not a term probe "
               "(_validate_directive_targets, after the migrated arity read)"),
    AllowEntry("clausal/logic/compiler_v2.py", (664, 680),
               "plan exclusion #8: class-registry op, not a term probe "
               "(_refuse_untablable_target, before the migrated arity read)"),
    AllowEntry("clausal/logic/compiler_v2.py", (687, 723),
               "plan exclusion #8: class-registry op, not a term probe "
               "(_refuse_untablable_target, after the migrated arity read)"),
    AllowEntry("clausal/logic/compiler_v2.py", (742, 775),
               "plan exclusion #8: class-registry op, not a term probe "
               "(_preregister_specializations)"),
    AllowEntry("clausal/logic/compiler_v2.py", (776, 860),
               "plan exclusion #8: class-registry op, not a term probe "
               "(_run_specialization)"),
    AllowEntry("clausal/logic/compiler_v2.py", (940, 1026),
               "plan exclusion #8: class-registry op, not a term probe "
               "(_process_declarations). P3-1 Task 3 shrank the file: "
               "_check_atom_shadowing (which used to follow this function) "
               "is deleted, so _process_declarations now runs to EOF."),
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
    #     prefer not touching the file. Scoped to just that function's
    #     definition, not the whole file.
    AllowEntry("clausal/logic/goal_expansion.py", (503, 509),
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
    # Range shifted 2046-2160 -> 2196-2310 by task-4's atom-aware near-miss
    # rendering additions earlier in the file, then -> 2215-2329 by task-6's
    # -hide is_mangled additions earlier still, then -> 2241-2355 by P3-2
    # task-2's cell-aware diagnostic additions (``_reify_value``'s cell
    # branch and the generic-compound note's registry lookup), all earlier
    # in the file (mechanical line-count shifts, not semantic changes -- see
    # task-4-report.md/task-6-report.md and
    # .superpowers/sdd/p32-cell-default-flip/task-2-report.md).
    # Range shifted 2188-2300 -> 2274-2386 by the test/1 + Test/1 union
    # collection added above the site (a mechanical line-count shift).
    # Range shifted 2274-2386 -> 2277-2389 by the ``.seam`` alias-extension
    # import and docstring line added above the site (mechanical again).
    AllowEntry("clausal/testing.py", (2277, 2389),
               "task-3 skip: diagnostic head-name fallback, semantics diverge "
               "from _functor_name (see task-3-report.md determination)"),
    # task-2-report.md / plan Task 2 text: "leave head_key itself as-is (it
    # is the canonical pair function; do not rewrite it this phase)".
    # Range shifted 524-556 -> 541-573 by P3-2 task-3's cell branch in
    # ``_is_structural_head_value`` earlier in the same file (a mechanical
    # line-count shift, not a semantic change -- see
    # .superpowers/sdd/p32-cell-default-flip/task-3-report.md).
    # Range shifted 541-573 -> 668-700 by P3-3 task-1's additive PredRow
    # class + Database.row() inserted earlier in the same file (again a
    # mechanical line-count shift, not a semantic change -- see
    # .superpowers/sdd/p33-state-relocation/task-1-report.md).
    # Range shifted 668-700 -> 691-723 by task-1's fix-round-1 (Finding 1:
    # PredRow.clauses became a property with its own docstring, adding a
    # few more lines earlier in the same file) -- again mechanical, not
    # semantic; see task-1-report.md's fix-round-1 addendum.
    # Range shifted 691-723 -> 742-774 by P3-3 task-2's fix-round-1 (Finding
    # 2: PredRow.clauses lost its setdefault and gained ensure_clauses() +
    # the _unminted_clauses field, all earlier in the same file).  ``head_key``
    # itself is byte-identical across all four shifts -- only its line number
    # moved; see .superpowers/sdd/p33-state-relocation/task-2-report.md.
    # Range shifted 742-774 -> 1011-1043 by P3-3 task-3's mutation gate (the
    # write policy, ``refusal_error``, ``Database.mutate`` and the author
    # helpers, all earlier in the same file), then -> 1088-1120 by its fix
    # round 1 (``PredRow.db``/``key``/``detached``, ``Database._write_rows``
    # and ``refusal_for``, again all earlier).  ``head_key`` is byte-identical
    # across all six shifts -- only its line number moved; see
    # .superpowers/sdd/p33-state-relocation/task-3-report.md.
    # Range shifted 1088-1120 -> 1214-1246 by P3-3 task-4's backend seam
    # (``DEFAULT_BACKEND``, ``_BACKEND_CHOOSER``/``_BACKEND_INSTALLERS`` and
    # ``Database.set_backend_chooser``/``backend_chooser``/
    # ``register_backend``/``backend_dispatch``, all earlier in the same
    # file).  ``head_key`` is byte-identical across all seven shifts -- only
    # its line number moved, then -> 1223-1255 by that task's fix round 1
    # (M-2: the unregistered-backend refusal moved onto the engine's error
    # family, widening the ``clausal.logic.exceptions`` import and the raise);
    # see .superpowers/sdd/p33-state-relocation/task-4-report.md.
    # Range 1223-1255 -> 1224-1264 by P3-3 task-5 (R11), which is the FIRST
    # change to ``head_key`` itself rather than a line-count shift under it:
    # the function gained a CELL branch (``compound_cell_shape`` -> ``(f, N)``)
    # so a cell can name a predicate head, plus the matching docstring and
    # TypeError-message lines; the START moved by one because that task also
    # widened the ``clausal.logic.exceptions`` import (``type_error``, for
    # ``_stored_head_key`` just below).  The atom_bypass line this entry exists
    # for is untouched.  See
    # .superpowers/sdd/p33-state-relocation/task-5-report.md.
    # Range 1224-1264 -> 1250-1290 by the P3-3 final fix wave, a pure
    # line-count shift: ``refusal_error`` (earlier in the file) gained the
    # optional ``attempted`` key for M-e and ``Database.retract`` gained the
    # ``_stored_head_key`` docstring paragraph for M-c.  ``head_key`` itself
    # is byte-identical, the atom_bypass line this entry exists for included.
    # Range widened 2026-09-11: the site drifted to 1294 when ten lines were
    # added ~250 lines ABOVE it (the constant_units registry). A line-range
    # allowlist moves whenever anything earlier in the file does, so this
    # entry will red on edits that have nothing to do with it -- the range is
    # deliberately loose to absorb that rather than being re-pinned each time.
    #    Range shifted 1240-1320 -> 1240-1400 by the §4 q1 import-plant's
    #    arities_for/adopt_row/owns/_adopted additions earlier in the file.
    AllowEntry("clausal/logic/database.py", (1240, 1400),
               "task-2 instruction: head_key is the canonical pair function, "
               "left as-is this phase (plan Task 2 file list); task-5 (R11) "
               "added its cell branch"),

    # ── Pre-existing site found by this lint, outside the Phase 1 site
    #    inventory (never named in the plan or any Task 1-3 file list).
    #    Not migrated this phase; see
    #    todo/funnel-term-str-locale-atom-bypass-not-migrated-2026-09-03.md ──
    #    Range shifted 2355-2457 -> 2373-2475 by P3-2 task-2's cell branch in
    #    ``term_str`` earlier in the same function, then -> 2391-2493 by
    #    P3-2 task-7's deref-removal + TUPLE_TAG-display additions to that
    #    same cell branch and the new ``TUPLE_TAG`` import line (mechanical
    #    line-count shifts, not semantic changes -- see
    #    .superpowers/sdd/p32-cell-default-flip/task-2-report.md and
    #    task-7-report.md), then -> 2469-2586 by the atoms-as-cells Task 4
    #    writers work (the ISO quoting helpers added above ``term_str`` and
    #    the arity-0 atom case added inside its cell branch), then -> 2474-2591
    #    by fix round 1's lone-dot rule in ``atom_needs_quotes`` -- again purely
    #    mechanical line-count shifts, see
    #    .superpowers/sdd/2026-09-06-atoms-as-cells-strings/task-4-report.md),
    #    then -> 2479-2596 by the same plan's Task 7 (the char helpers added to
    #    the ``clausal.logic.atoms`` import and to SegString's ``__walk__`` /
    #    ``__unify__`` -- a uniform +5 shift, no new site), then -> 2505-2622
    #    by Task 7 fix round 1 (SegList's ``_walk_raw`` split out of
    #    ``__walk__``) -- a further uniform +26 shift, still no new site; see
    #    .superpowers/sdd/2026-09-06-atoms-as-cells-strings/task-7-report.md),
    #    then -> 2482-2688 by the same plan's Task 15 item 4 (``term_str``'s
    #    new ``double_quotes`` keyword, threaded through every recursive call,
    #    and the ``_char_list_str`` helper added above it) -- a +34 shift of
    #    the region's end, no new site; see
    #    .superpowers/sdd/2026-09-06-atoms-as-cells-strings/task-15-report.md),
    #    then -> 2482-2717 by that task's fix round 1 (``term_str``'s third
    #    keyword ``sep``, threaded like the other two, and the ``bytes``
    #    branch that spells a code list out under ``double_quotes(false)``) --
    #    a further +29 shift of the region's end, still no new site), then
    #    -> 2482-2745 by fix round 2 (the empty-tuple nil branch added to
    #    ``term_str`` and the ``b""`` reorder in its bytes branch) -- +28,
    #    still no new site), then -> 2482-2818 by fix round 3 (the nil-key
    #    normalisation in ``DictTerm.__init__``/``normalised_key`` and the
    #    empty-tuple arms added to the three ``Seg*``
    #    ``__unify__``/``__eq__``, all ABOVE ``term_str``) -- a further +73
    #    shift, still no new site), then -> 2482-2901 by fix round 4 (the
    #    ``_EMPTY_SEG_IS_NIL`` rationale block and the empty-Seg nil branch
    #    in the same six ``Seg*`` methods, plus ``DictTerm.mapping_of`` and
    #    the one-shot-iterable materialisation in ``DictTerm.__init__`` --
    #    again all ABOVE ``term_str``) -- a further +83 shift, still no new
    #    site), then -> 2482-3021 by the minor-currency-units landing (the
    #    ``_warn_if_literal_may_be_lost`` helper and the measured-rate table
    #    on its band constant, added beside ``_to_decimal`` and so ABOVE
    #    ``term_str``, then the same-named-dimension disambiguation in
    #    ``_dims_str``/``_colliding_dim_names``) -- still no new site.
    AllowEntry("clausal/terms.py", (2699, 3407),   # re-anchored 2026-09-12 (exact-number currency helpers and // % above; then the re-readable unit renderer _unit_identifier/_unit_expr_str, then the rational rendering, still no new site); END re-anchored 2026-09-15 to 3407 -- this branch's own commits had ALREADY pushed the site past the old end (the test was red in this branch's baseline, which is exactly why the branch gate could not see the drift), and the _dims rekey pushed it further; verified still the only violation in the tree
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
        "migrate the site onto the funnel "
        "(predicate.is_zero_field_class / "
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
from clausal.logic.atoms import char_atom, mint
from clausal.logic.predicate import PredicateMeta

def _sneaky_zero_field_class(x):
    return isinstance(x, PredicateMeta) and not x._fields
'''

_BAD_FUNCTOR_FALLBACK_SNIPPET = '''\
def _sneaky_functor(term):
    return getattr(term, "functor", None) or type(term).__name__
'''

_CLEAN_SNIPPET = '''\
from clausal.logic.predicate import is_zero_field_class
from clausal.logic.builtins._helpers import functor_arity

def _proper_zero_field_class(x):
    return is_zero_field_class(x)

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
    """The funnel modules' own is_zero_field_class/_functor_name
    implementations are the canonical *definition* sites for the raw idiom,
    not a bypass of it."""
    fake_module_dir = tmp_path / "clausal" / "logic"
    fake_module_dir.mkdir(parents=True)
    (fake_module_dir / "predicate.py").write_text(_BAD_ATOM_BYPASS_SNIPPET, encoding="utf-8")

    violations = find_violations(tmp_path, funnel_modules=frozenset({"clausal/logic/predicate.py"}))

    assert violations == []


_BAD_FUNCTOR_FALLBACK_DOTTED_SNIPPET = '''\
def _sneaky_functor(clause):
    return getattr(clause.head, "functor", None) or type(clause.head).__name__
'''


def test_lint_catches_dotted_receiver_functor_fallback(tmp_path):
    """A dotted receiver (``clause.head``, not a bare name) must still be
    caught -- the regex's receiver group must be [\\w.]+, not \\w+. This is
    the exact shape of the real, previously-invisible occurrence at
    clausal/testing.py:2286 (2260 pre-P3-2-task-2, 2241 pre-task-6, 2091
    pre-task-4)."""
    bad_file = tmp_path / "sneaky_dotted.py"
    bad_file.write_text(_BAD_FUNCTOR_FALLBACK_DOTTED_SNIPPET, encoding="utf-8")

    violations = find_violations(tmp_path)

    assert len(violations) == 1, violations
    (v,) = violations
    assert v.pattern == "functor_fallback"
    assert v.path == "sneaky_dotted.py"


def test_testing_py_allowlist_entry_is_load_bearing():
    """clausal/testing.py:2342 (2326 before the P1 fix wave's L4 class-leg
    fallback in ``_note_generic_compound_confusion``, 2323 before P1 Task 3's
    comment lines in the same function, 2322 before the tuple-DATA tag's
    TUPLE_TAG import, 2319 before the ``.seam`` alias-extension
    lines) has a real ``getattr(clause.head, "functor",
    None) or type(clause.head).__name__`` occurrence -- now that the
    receiver group is dotted-aware, the task-3 ALLOWLIST range for
    testing.py (currently 2277-2389, which still covers the site; the entry's
    own comment records how it has moved as code above the site grew) is doing
    real exemption work, not sitting on an already-invisible site.

    This number is a MECHANICAL line count, not a behaviour: every edit above
    the site moves it, and the trail above records each move.  The assertion
    that matters is the pattern and the path."""
    entries_without_testing = tuple(
        e for e in ALLOWLIST if e.path != "clausal/testing.py"
    )
    violations = find_violations(
        _CLAUSAL_ROOT, allowlist=entries_without_testing, repo_root=_REPO_ROOT
    )
    testing_violations = [v for v in violations if v.path == "clausal/testing.py"]
    assert testing_violations, (
        "expected clausal/testing.py to surface a functor_fallback violation "
        "once its allowlist entry is removed -- if this is empty, the "
        "allowlist entry is a dead no-op again"
    )
    assert any(
        v.pattern == "functor_fallback" and v.line == 2342
        for v in testing_violations
    ), testing_violations


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
