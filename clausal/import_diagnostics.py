"""Actionable diagnostics for failed ``-import_from`` / ``-import_module``.

``-import_from(M, [name])`` lowers to a Python ``from M import name``, so a
stale name surfaces as CPython's stock message::

    cannot import name 'within_limit' from 'acme.compliance.schema'
    (/…/schema.clausal)

which names the file but never the vocabulary — the one thing a repair needs.
See ``todo/done/import-error-should-list-module-exports.md``: this was the dominant
failure mode for machine authors (hit by 22/22 runs, 85 repair attempts burned,
84% of attempts failing to escape it), because the correct names were sitting
in the very file the message points at, invisible.

The loader knows exactly which of three situations obtains, and the three want
different words:

1. **the module exists, is Clausal, and does not export that name** — append
   its ``-module(...)`` export list and a near-miss suggestion;
2. **the module does not exist at all** — say so, and say explicitly that
   there is *no* export list.  Printing an empty one would read as "exports
   nothing", which is a different and wrong diagnosis;
3. **the module exists but is not a Clausal module** — say nothing.  A Clausal
   file importing a Python library must get Python's own error, unmodified;
   inventing a Clausal-flavoured export list for ``re`` or ``numpy`` would be
   noise at best and misdirection at worst.

Case 2 has a sub-case worth its own words.  A package directory's name IS its
import segment, so ``eu/state-aid/`` can never be the ``state_aid`` of a dotted
import — ``state-aid`` is not a Python identifier.  Saying "no module of that
name is on the import path" to someone looking straight at the directory sends
them hunting for a typo, or worse, creating a second copy of a package they
already have; the hierarchical-namespace migration lost real time to exactly
that.  So when the miss is explained by a misnamed entry sitting on the search
path, say which entry and say the rule (see ``_misnamed_path_entry``).

Everything here runs on the error path only, so re-parsing the target module's
source to recover its declarations costs nothing in the normal case.
"""

from __future__ import annotations

import difflib
import os
import re
import sys
import textwrap
from typing import NamedTuple

from clausal._suffixes import SOURCE_SUFFIXES

# Display cap for the export list.
#
# Justification: the point of the list is to be *read* — an author (human or
# model) scans it for the name they meant.  40 names wrap to about five lines
# at 78 columns, which still reads as a list rather than a wall, and covers
# the overwhelming majority of real vocabulary modules.  Past that the list
# stops informing and starts burying the rest of the message.  A truncated
# list is only safe if it says it is truncated — a silent cut reads as
# authoritative and would send the author looking for a name that IS there,
# so the notice below is mandatory, carries the true total, and points at the
# file for the full list.  Near-miss suggestions are computed over the FULL
# list, never the truncated one.
_MAX_EXPORTS_SHOWN = 40

_WIDTH = 78
_INDENT = "  "

# Similarity floor for "did you mean".  Below this the suggestion is noise.
_SUGGEST_CUTOFF = 0.6
_MAX_SUGGESTIONS = 3

_ENRICHED_FLAG = "_clausal_import_diagnostic"


# ── name similarity ──────────────────────────────────────────────────────────


def _tokens(name: str) -> list[str]:
    """Split ``within_limit`` / ``WithinLimit`` into lowercase word tokens."""
    parts = []
    for chunk in name.split("_"):
        parts.extend(re.findall(r"[A-Z]+(?![a-z])|[A-Z][a-z]*|[a-z]+|\d+",
                                chunk))
    return [p.lower() for p in parts if len(p) >= 3]


def _normalized(name: str) -> str:
    return name.replace("_", "").lower()


def _similarity(missing: str, candidate: str) -> float:
    """Blend character similarity with shared-token similarity.

    Pure ``difflib`` scores ``within_limit`` vs ``exceeds_limit`` at 0.48 and
    would miss the very rename the report is about.  Clausal names are
    snake_case compounds, so a shared token (``…_limit``) is a much stronger
    signal than character overlap: weight it explicitly.
    """
    ratio = difflib.SequenceMatcher(None, missing, candidate).ratio()
    ta, tb = set(_tokens(missing)), set(_tokens(candidate))
    shared = ta & tb
    if shared:
        ratio = max(ratio, 0.5 + 0.5 * len(shared) / max(len(ta), len(tb)))
    return ratio


def _suggestions(missing: str, candidates: list[str]) -> list[str]:
    """Names from ``candidates`` a reader would plausibly have meant."""
    if not candidates:
        return []
    target = _normalized(missing)
    exact_ci = [c for c in candidates
                if c != missing and _normalized(c) == target]
    if exact_ci:
        return exact_ci[:_MAX_SUGGESTIONS]
    scored = [(_similarity(missing, c), i, c)
              for i, c in enumerate(candidates) if c != missing]
    scored = [s for s in scored if s[0] >= _SUGGEST_CUTOFF]
    if not scored:
        return []
    scored.sort(key=lambda s: (-s[0], s[1]))
    # A name shared by a whole family (``wide_export_00`` … ``wide_export_59``)
    # scores every sibling identically.  Pointing at three of sixty equally
    # plausible names is not a suggestion, it is a coin toss dressed up as
    # advice — say nothing rather than mislead.
    top = scored[0][0]
    if sum(1 for s in scored if s[0] == top) > _MAX_SUGGESTIONS:
        return []
    return [c for _, _, c in scored[:_MAX_SUGGESTIONS]]


# ── target-module introspection ──────────────────────────────────────────────


def _clausal_loader_of(mod):
    """The ``.clausal``/``.pl`` loader for ``mod``, or ``None`` if it is not
    a Clausal module at all (case 3)."""
    from clausal.import_hook import _ClausalSourceLoader

    spec = getattr(mod, "__spec__", None)
    for loader in (getattr(mod, "__loader__", None),
                   getattr(spec, "loader", None)):
        if isinstance(loader, _ClausalSourceLoader):
            return loader
    return None


def _render_entry(entry):
    """``('verdict', ['A', 'B'])`` → ``('verdict', 'verdict/2')``;
    ``'holdings'`` → ``('holdings', 'holdings')``.

    Predicates carry their arity and bare atoms do not, matching how
    ``-module(...)`` declares each.
    """
    if isinstance(entry, str):
        return entry, entry
    if isinstance(entry, (tuple, list)) and len(entry) == 2:
        functor, fields = entry
        if isinstance(functor, str):
            return functor, f"{functor}/{len(fields or ())}"
    return None


def _declared_exports(module_items):
    """``(entries, saw_module_directive)`` from every ``-module(...)``.

    ``entries`` is a list of ``(bare_name, rendered)`` in declaration order,
    deduplicated on the bare name.
    """
    from clausal.pythonic_ast.nodes import ModuleDeclaration

    entries, seen, saw = [], set(), False
    for item in module_items or ():
        if not isinstance(item, ModuleDeclaration):
            continue
        saw = True
        for export in item.exports:
            rendered = _render_entry(export)
            if rendered is None or rendered[0] in seen:
                continue
            seen.add(rendered[0])
            entries.append(rendered)
    return entries, saw


def _defined_names(mod):
    """Public predicate/atom names ``mod`` actually binds.

    The fallback when a module declares no ``-module(...)``: those names are
    still importable (``from M import f`` is a plain ``getattr``), so this is
    the honest answer to "what may I import from here?".

    Era-agnostic (PredicateMeta retirement, W4b-2d): TODAY a module-dict
    predicate binding is a ``PredicateMeta`` CLASS; after the flip it is a
    module-qualified MANGLED ATOM (a plain ``str``).  The population test
    is ``is_declared_predicate_name`` -- NOT a bare ``is_mangled`` swap,
    which would select nothing at all until the flip lands (every binding
    is still a class today) and silently empty this diagnostic with no test
    to catch it.  ``is_declared_predicate_name`` answers correctly in BOTH
    eras: ``True`` for a ``PredicateMeta`` class or a mangled atom naming a
    declared predicate, ``False`` for anything else -- a plain module-level
    string or int, an imported non-predicate callable, a data functor's
    ``@dataclass`` class, or a mangled atom naming a DATA atom (e.g. one
    hidden via ``-hide``, which is registered as neither "predicate" nor
    "data" anywhere) -- so none of those false-positive shapes can appear.
    See ``test_import_diagnostics_defined_names.py`` for the population
    (non-empty, both eras) and false-positive evidence.
    """
    from clausal.import_hook import predicate_builtins
    from clausal.logic.atoms import demangle
    from clausal.logic.predicate import (
        PredicateMeta, field_names_for, is_declared_predicate_name,
    )

    entries = []
    for name, value in vars(mod).items():
        if not isinstance(name, str) or name.startswith("_") or "$" in name:
            continue
        if not is_declared_predicate_name(value):
            continue
        # Equality, never identity, for an atom (spec §2/§5.2): two
        # equal atoms are the same atom whether or not they are the
        # same tuple object, and ``mint`` returns a fresh tuple each
        # call.  THE FLIP retired the last of these ``is`` pins.  (A
        # mangled atom never collides with this pool -- the pool holds
        # only unmangled spellings -- so this is a no-op, not a branch,
        # for the mangled arm below.)
        if predicate_builtins.get(name) == value:
            continue
        if isinstance(value, PredicateMeta):
            if getattr(value, "__module__", None) != mod.__name__:
                continue  # re-exported from elsewhere; not this module's own
            fields = getattr(value, "_fields", ()) or ()
            arity = len(fields)
        else:
            # ``is_declared_predicate_name`` only ever answers True for a
            # PredicateMeta class (handled above) or a mangled atom -- so
            # this is the mangled-atom arm by elimination.
            owner_module, functor = demangle(value)
            if owner_module != mod.__name__:
                continue  # re-exported from elsewhere; not this module's own
            fields = field_names_for(value) or ()
            if fields:
                arity = len(fields)
            else:
                # ``field_names_for`` answers None for an ordinary clause-
                # defined predicate -- it only records names for an
                # explicit structural declaration, never a bare
                # ``p(X, Y) <- ...`` head (see its own docstring).  Fall
                # back to the owner db's arity registry so an N-ary
                # predicate still renders ``name/N`` rather than silently
                # dropping the suffix and reading as 0-ary.  Same idiom as
                # ``testing.py``/``compiler_v2.py``: a loaded module's
                # Database lives at ``mod.__dict__["$module"].db``.
                owner_mod = sys.modules.get(owner_module)
                owner_db = getattr(
                    getattr(owner_mod, "__dict__", {}).get("$module"),
                    "db", None,
                )
                arities = owner_db.arities_for(functor) if owner_db else set()
                arity = arities.pop() if len(arities) == 1 else 0
        entries.append((name, f"{name}/{arity}" if arity else name))
    entries.sort()
    return entries


def _module_items_of(mod, loader):
    """Recover the target module's declarations by re-reading its source."""
    path = getattr(mod, "__file__", None)
    if not path:
        return None
    try:
        return loader._recover_module_items(path)
    except Exception:
        return None


def _short_name(module_items, dotted: str) -> str:
    """The name to use as the label: the declared ``-module`` name if there
    is one, else the last segment of the dotted path."""
    from clausal.pythonic_ast.nodes import ModuleDeclaration

    for item in module_items or ():
        if isinstance(item, ModuleDeclaration) and item.module_name:
            return item.module_name
    return dotted.rsplit(".", 1)[-1]


# ── message assembly ─────────────────────────────────────────────────────────


def _wrap(label: str, body: str) -> list[str]:
    """``  label: a, b, c`` wrapped at _WIDTH with continuations aligned
    under the first item."""
    lead = f"{_INDENT}{label} "
    return textwrap.wrap(
        body, width=_WIDTH, initial_indent=lead,
        subsequent_indent=" " * len(lead),
        break_long_words=False, break_on_hyphens=False,
    ) or [lead.rstrip()]


def _sentence(text: str) -> list[str]:
    """A ``  …`` block wrapped at the shared width, continuations hanging."""
    return textwrap.wrap(
        text, width=_WIDTH, initial_indent=_INDENT,
        subsequent_indent=_INDENT + "  ",
        break_long_words=False, break_on_hyphens=False,
    ) or [_INDENT + text]


def _arrow(lines: list[str]) -> list[str]:
    out = []
    for i, line in enumerate(lines):
        prefix = f"{_INDENT}-> " if i == 0 else f"{_INDENT}   "
        out.extend(textwrap.wrap(
            line, width=_WIDTH, initial_indent=prefix,
            subsequent_indent=f"{_INDENT}   ",
            break_long_words=False, break_on_hyphens=False,
        ))
    return out


def _name_list_lines(heading: str, entries, path: str | None):
    """A ``  <heading> a, b, c`` block, capped, with a truncation notice.

    The notice is not optional: a silently cut list reads as authoritative and
    would send the reader hunting for a name that is in fact exported.
    """
    total = len(entries)
    shown = entries[:_MAX_EXPORTS_SHOWN]
    lines = _wrap(heading, ", ".join(rendered for _, rendered in shown))
    if total > _MAX_EXPORTS_SHOWN:
        hidden = total - _MAX_EXPORTS_SHOWN
        lines.append(
            f"{_INDENT}...and {hidden} more, NOT SHOWN ({total} total) — "
            f"full list in:"
        )
        lines.append(f"{_INDENT}    {path or '(source file unknown)'}")
    return lines


def _describe_missing_name(exc, missing, dotted, mod, loader):
    """Case 1 — Clausal module, name not there."""
    module_items = _module_items_of(mod, loader)
    label = _short_name(module_items, dotted)
    path = getattr(mod, "__file__", None)
    entries, saw_module_decl = _declared_exports(module_items)

    lines = [str(exc)]
    if module_items is None:
        # Source unreadable/unparseable now.  Say so — do not report an
        # absence we did not actually establish.
        lines.append(
            f"{_INDENT}(could not re-read {label}'s source to recover its "
            f"-module(...) list)"
        )
        defined = _defined_names(mod)
        if defined:
            lines.extend(_name_list_lines(f"{label} does bind:", defined,
                                          path))
        pool = [bare for bare, _ in defined]
        remedy = [
            f"open that file and check whether `{missing}` is exported.",
        ]
    elif entries:
        lines.extend(_name_list_lines(f"{label} exports:", entries, path))
        pool = [bare for bare, _ in entries]
        remedy = [
            f"either add `{missing}` to that -module(...) list and define it "
            f"there, or stop importing it and remove every use.",
        ]
    else:
        defined = _defined_names(mod)
        lines.append(
            f"{_INDENT}{label} has "
            + ("an EMPTY -module(...) export list"
               if saw_module_decl else "no -module(...) export list")
            + " — it declares no public API."
        )
        if defined:
            lines.extend(_name_list_lines(f"{label} does define:",
                                          defined, path))
        pool = [bare for bare, _ in defined]
        remedy = [
            f"add `{missing}` to a -module({label}, [...]) list in that file "
            f"(and define it there), or import it from the module that does "
            f"define it.",
        ]

    hits = _suggestions(missing, pool)
    if hits:
        lines.append(f"{_INDENT}did you mean: {', '.join(hits)} ?")
    lines.extend(_arrow(remedy))
    return "\n".join(lines)


#: Extensions an entry on the search path can be imported under.
_SOURCE_SUFFIXES = (*SOURCE_SUFFIXES, ".py")


class _MisnamedEntry(NamedTuple):
    """A search-path entry that would BE the wanted segment but for its name."""
    path: str    # /…/eu/state-aid
    entry: str   # state-aid          (as it appears in the directory)
    stem: str    # state-aid          (entry minus any source suffix)
    kind: str    # 'directory' | 'file'


def _search_dirs_for(failed: str) -> list[str]:
    """The directories the import machinery looked in for *failed*.

    For ``eu.state_aid`` that is ``eu.__path__`` — ``eu`` must have imported,
    or the failure would have been reported against ``eu`` instead.  For a
    bare top-level name it is ``sys.path``.  If the parent is not in
    ``sys.modules`` there is no search path to scan, and guessing at
    ``sys.path`` would look in the wrong place, so decline.
    """
    parent, _, _segment = failed.rpartition(".")
    if not parent:
        return [p for p in sys.path if isinstance(p, str)]
    search = getattr(sys.modules.get(parent), "__path__", None)
    try:
        return [p for p in search if isinstance(p, str)]
    except TypeError:
        return []


def _misnamed_path_entry(failed: str) -> _MisnamedEntry | None:
    """The entry whose *name* is why *failed* did not resolve, or ``None``.

    A directory or source file counts only when its name is not a Python
    identifier *and* replacing the characters an identifier cannot hold with
    ``_`` yields exactly the wanted segment.  Under that test the report is a
    tautology rather than a guess: ``state-aid`` cannot be ``state_aid``, and
    the reader is told which of the two they have.

    Two things keep it from firing where the old sentence was right.  A
    correctly-spelled entry anywhere on the search path aborts the scan — the
    import then failed for some other reason (a directory with no
    ``__init__``, an unreadable file, a stale cache) and the neighbouring
    hyphen is not the story.  And an entry that is neither a directory nor a
    recognised source file is skipped, so ``state-aid.txt`` is not offered as
    a package.

    "Anywhere" is why the scan takes two passes over the same listings.  Asking
    both questions of one directory at a time makes the answer depend on which
    directory came first: a hyphen in an early ``sys.path`` entry would be
    reported while ``state_aid`` sat correctly spelled in a later one, and the
    reader would be told to rename a directory that is not the reason for
    anything.  So the whole path is swept for a correct spelling before any
    misnamed candidate is considered.
    """
    segment = failed.rpartition(".")[2]
    if not segment:
        return None
    correct = {segment, *(segment + s for s in _SOURCE_SUFFIXES)}
    listings = []
    for dir_entry in _search_dirs_for(failed):
        try:
            names = os.listdir(dir_entry)
        except OSError:
            continue
        if correct & set(names):
            return None
        listings.append((dir_entry, names))
    for dir_entry, names in listings:
        for name in sorted(names):
            full = os.path.join(dir_entry, name)
            if os.path.isdir(full):
                stem, kind = name, "directory"
            elif name.endswith(_SOURCE_SUFFIXES) and os.path.isfile(full):
                stem, kind = name.rsplit(".", 1)[0], "file"
            else:
                continue
            if stem.isidentifier() or re.sub(r"\W", "_", stem) != segment:
                continue
            return _MisnamedEntry(full, name, stem, kind)
    return None


def _rename_remedy(near: _MisnamedEntry, segment: str) -> str:
    """The one repair there is: the directory or file has to change its name.

    It says so outright, because the repair a reader reaches for first is to
    adjust the import — and there is no spelling of the import that works.  The
    rule is stated here rather than repeated from the evidence line above.
    """
    if near.kind == "file":
        want = near.entry.replace(near.stem, segment, 1)
        what = "a module file"
    else:
        want = segment
        what = "a package directory"
    return (f"rename the {near.kind} '{near.entry}' to '{want}'. Renaming is "
            f"the only repair: {what} is importable only under its own name, "
            f"so the import cannot be adjusted to meet it.")


def _describe_missing_module(exc, dotted, failed, directive, importer_file):
    """Case 2 — the module named by the directive does not exist.

    *dotted* is the path the directive asks for; *failed* is the dotted prefix
    at which resolution actually stopped, which is *dotted* itself unless an
    intermediate package is the missing one.
    """
    segment = failed.rpartition(".")[2]
    lines = [str(exc), f"{_INDENT}{directive}"]
    if importer_file:
        lines.append(f"{_INDENT}  in {importer_file}")
    if failed != dotted:
        # Naming only the whole path would leave the reader checking segments
        # that resolved perfectly well.  The sentence claims the segment and
        # the entailment, not the route: *this* directive need not be the
        # import that raised (see _prefix_target), so "resolution of the
        # declared path stops here" would assert a path possibly not taken.
        lines.extend(_sentence(
            f"the segment '{segment}' did not resolve, so neither can "
            f"'{dotted}'."))

    near = _misnamed_path_entry(failed)
    if near is not None:
        lines.extend(_sentence(
            f"{near.path} is there, but '{near.stem}' is not a valid Python "
            f"identifier, so no dotted import can name it — '{segment}' is a "
            f"different segment, not a spelling of it. There is therefore no "
            f"export list to show."))
        lines.extend(_arrow([_rename_remedy(near, segment)]))
        return "\n".join(lines)

    if failed != dotted:
        claim = (f"No .clausal file, .pl file or Python module called "
                 f"'{failed}' is on the import path")
    else:
        claim = (f"names a module that does not exist: no .clausal file, .pl "
                 f"file or Python module called '{dotted}' is on the import "
                 f"path")
    lines.extend(textwrap.wrap(
        f"{claim}. There is therefore no export list to show — this is a "
        f"MISSING module, not a module that exports nothing.",
        width=_WIDTH, initial_indent=_INDENT, subsequent_indent=_INDENT,
        break_long_words=False, break_on_hyphens=False,
    ))
    lines.extend(_arrow([
        "fix the module path (check spelling and package prefix), or create "
        "that module.",
    ]))
    return "\n".join(lines)


# ── redefining an imported predicate ─────────────────────────────────────────


def _clause_author(row, exporter, exporter_module):
    """``(name, where)`` of the module that supplied *row*'s clauses.

    ``-import_from`` binds a SHARED class, so the clauses sitting on it are not
    automatically the exporter's: a clause-free export implemented downstream
    leaves them owned by the *importer* that implemented it.  Blaming the
    exporter for those is the defect the previous attempt at this refusal
    shipped — see ``todo/done/imported-clause-refusal-misattributes-ownership.md``.

    Returns ``(None, None)`` when nothing was recorded, so the caller can say
    so rather than guess.
    """
    # The ROW, not the `_clauses_source` facade (W2, 2026-09-22), and now
    # handed in rather than read off a class (F1 row 29): the caller
    # resolves it with ``resolve_predicate_row``, which answers for a
    # mangled-atom binding as well as a class.  ``None`` -- no row -- reads
    # as "nothing recorded", exactly as a class with no row did.
    source = row.source if row is not None else None
    if not (isinstance(source, tuple) and len(source) == 2):
        return None, None
    name, path = source
    exporter_path = getattr(exporter_module, "__file__", None)
    if exporter_path:
        try:
            same = path is not None and os.path.realpath(exporter_path) == path
        except OSError:  # pragma: no cover — defensive
            same = False
        if same:
            # The exporter really is the author; prefer the spelling the
            # -import_from used, which is the one the reader wrote.
            return exporter, path
    return name, path


def describe_imported_predicate_redefinition(
    functor, arity, importer, exporter, row, exporter_module=None,
    declared_at=None,
):
    """Why a clause for an ``-import_from``'d, already-defined predicate is
    refused — and what to write instead.

    ``-import_from`` binds the *exporter's* predicate class, so a clause
    written here lands on that shared class and used to overwrite its clause
    list outright: the clauses already on it vanished, from their own module's
    queries, with no error (see
    ``todo/done/imported-functor-clause-list-replaced-not-extended.md``).  The
    message leads with what is about to be lost — the count is the size of the
    hole — names **who actually wrote those clauses** rather than assuming the
    exporter did, and then names the two places a clause could legitimately go,
    because "you cannot write this" alone leaves the author with a rule and
    nowhere to put it.

    *row* is the imported predicate's row (``None`` if it has none) and
    *declared_at* its ``(file, line)`` declaration site if one is known.
    Both used to be read off the predicate CLASS; taking them as values is
    what lets the caller pass a mangled-atom binding's row after the flip
    (F1 row 29).  The declaration site is recorded only on a class today,
    so after the flip that one line is omitted until the site has another
    home -- the rest of the message is unchanged.
    """
    n = len(row.clauses) if row is not None else 0
    plural = "clause" if n == 1 else "clauses"
    subject = "that 1 clause" if n == 1 else f"those {n} clauses"
    was = "was" if n == 1 else "were"
    author, author_path = _clause_author(row, exporter, exporter_module)
    lines = [
        f"{importer} defines a clause for {functor}/{arity}, which it "
        f"-import_from's from {exporter}."
    ]
    lines.extend(textwrap.wrap(
        f"An -import_from binds the EXPORTER's predicate, so this clause would "
        f"not add to the {n} {plural} already on {functor} — it would replace "
        f"{'it' if n == 1 else 'all of them'}, for every module that can reach "
        f"it. Clausal has no -multifile: a predicate has exactly one defining "
        f"module.",
        width=_WIDTH, initial_indent=_INDENT, subsequent_indent=_INDENT,
        break_long_words=False, break_on_hyphens=False,
    ))
    if author is None:
        lines.append(
            f"{_INDENT}{subject} {was} not recorded against a module")
    elif author == exporter:
        lines.append(
            f"{_INDENT}{subject} {'is' if n == 1 else 'are'} {exporter}'s own")
    else:
        # The exporter merely DECLARES the name; a different module supplies
        # the clauses.  Saying "exporter already defines it" here would be a
        # lie, and would point the reader at a file with nothing in it.
        lines.extend(textwrap.wrap(
            f"{subject} {was} supplied by {author}, not by "
            f"{exporter} — {exporter} only declares {functor}.",
            width=_WIDTH, initial_indent=_INDENT, subsequent_indent=_INDENT,
            break_long_words=False, break_on_hyphens=False,
        ))
    if author_path:
        lines.append(f"{_INDENT}  {author_path}")
    site = declared_at
    if isinstance(site, tuple) and len(site) == 2:
        lines.append(f"{_INDENT}{functor} is declared at {site[0]}:{site[1]}")
    elif site:
        lines.append(f"{_INDENT}{functor} is declared at {site}")
    # With no recorded author the honest remedy is a HEDGE: the line above has
    # just said ownership is unknown, and naming the exporter as the supplier
    # anyway would state as fact the very attribution this diagnostic exists to
    # get right (todo/done/imported-clause-refusal-misattributes-ownership.md).
    if author is not None:
        supplies = (f"move this clause into {author}, which supplies "
                    f"{functor}'s clauses — that is the only module whose "
                    f"clauses for it are compiled together;")
    else:
        supplies = (f"move this clause into the module that supplies "
                    f"{functor}'s clauses — likely {exporter}, though this "
                    f"process has no record of which module wrote them;")
    lines.extend(_arrow([
        supplies,
        f"or, if it is meant to be a predicate of this module, drop "
        f"{functor} from the -import_from({exporter}, [...]) list and give "
        f"the local one a name of its own.",
    ]))
    return "\n".join(lines)


def describe_imported_declaration_implemented(
    functor, arity, importer, exporter, imported_as=None,
):
    """Why clauses for an ``-import_from``'d predicate the exporter only
    DECLARES are refused -- and where they go instead.

    The "vocabulary-implements" idiom (the exporter declares, an importer
    supplies the clauses, everyone else imports the exporter's name) was
    dropped by operator ruling, 2026-09-24
    (``todo/done/vocabulary-implements-steal-has-no-row-form-2026-09-24.md``):
    a predicate has one defining module, and here that is the importer.
    *imported_as* is the local alias when the ``-import_from`` renamed it.
    """
    spelled = (f"{functor} (imported as {imported_as})"
               if imported_as else functor)
    lines = [
        f"{importer} defines clauses for {functor}/{arity}, which it "
        f"-import_from's from {exporter} -- but {exporter} only declares "
        f"{functor}/{arity}; it does not define it."
    ]
    lines.extend(textwrap.wrap(
        f"Supplying the clauses for a predicate imported from a module that "
        f"only declares it is not supported: a predicate has exactly one "
        f"defining module, and the module that writes its clauses is that "
        f"module.",
        width=_WIDTH, initial_indent=_INDENT, subsequent_indent=_INDENT,
        break_long_words=False, break_on_hyphens=False,
    ))
    lines.extend(_arrow([
        f"define {functor}/{arity} in {importer} and export it from "
        f"{importer}: drop {spelled} from the -import_from({exporter}, "
        f"[...]) list and add {functor}/{arity} to {importer}'s -module "
        f"export list;",
        f"then have the modules that use it import it from {importer}, "
        f"not from {exporter} (and remove the declaration from {exporter} "
        f"if nothing else needs it).",
    ]))
    return "\n".join(lines)


def describe_imported_python_predicate_implemented(
    functor, arity, importer, exporter, imported_as=None,
):
    """Why clauses for a predicate CLASS a Python module exports are refused.

    The class was created in Python (``make_predicate``, or a class with
    ``metaclass=PredicateMeta``); no Clausal module defines it, and a load
    may not become its defining module from the outside (the
    vocabulary-implements drop, 2026-09-24).  The remedies are Python-shaped:
    there is no ``-module`` export list on the exporter's side.
    """
    spelled = (f"{functor} (imported as {imported_as})"
               if imported_as else functor)
    lines = [
        f"{importer} defines clauses for {functor}/{arity}, which it "
        f"-import_from's from {exporter} -- but {functor}/{arity} is a "
        f"predicate class created in Python module {exporter}, not a "
        f"predicate a Clausal module defines."
    ]
    lines.extend(textwrap.wrap(
        "A load cannot supply the clauses of a predicate that another module "
        "hands out: a predicate has exactly one defining module.",
        width=_WIDTH, initial_indent=_INDENT, subsequent_indent=_INDENT,
        break_long_words=False, break_on_hyphens=False,
    ))
    lines.extend(_arrow([
        f"define the clauses in a Clausal module that owns the predicate: "
        f"drop {spelled} from the -import_from({exporter}, [...]) list and "
        f"define {functor}/{arity} in {importer} (export it from there);",
        f"or have {exporter} define it -- give the Python-side predicate "
        f"its clauses where it is created.",
    ]))
    return "\n".join(lines)


def describe_imported_runtime_dynamic_implemented(
    functor, arity, importer, exporter, n_runtime, imported_as=None,
):
    """Why a LOAD may not add clauses to an imported ``-dynamic`` predicate
    that holds clauses asserted at runtime -- and what to write instead.

    Not "only declares": the exporter's row holds *n_runtime* clauses, put
    there by ``assertz`` rather than by a load.  Letting the load through used
    to move the shared predicate onto the importer's row, and those runtime
    clauses then vanished from every caller (round-3 review, 2026-09-24).
    """
    spelled = (f"{functor} (imported as {imported_as})"
               if imported_as else functor)
    plural = "clause" if n_runtime == 1 else "clauses"
    lines = [
        f"{importer} defines clauses for {functor}/{arity}, imported from "
        f"{exporter}, whose {functor}/{arity} is a -dynamic predicate holding "
        f"{n_runtime} {plural} asserted at runtime."
    ]
    lines.extend(textwrap.wrap(
        f"A load cannot add clauses to another module's predicate: "
        f"{functor}/{arity} has exactly one defining module, {exporter}.",
        width=_WIDTH, initial_indent=_INDENT, subsequent_indent=_INDENT,
        break_long_words=False, break_on_hyphens=False,
    ))
    lines.extend(_arrow([
        f"assert them at runtime instead -- an assertz of {functor}/{arity} "
        f"from {importer} lands on {exporter}'s row;",
        f"or define a predicate of {importer}'s own: drop {spelled} from the "
        f"-import_from({exporter}, [...]) list, define {functor}/{arity} in "
        f"{importer} and export it from there.",
    ]))
    return "\n".join(lines)


# ── entry point ──────────────────────────────────────────────────────────────


def _import_targets(module_items):
    """``{resolved_path: (declared_path, directive_text)}`` for every import
    directive in the file being executed.

    Keying on the *resolved* path is what makes the interception precise: an
    ImportError whose module is not one this file asks for came from deeper in
    the import graph and is none of our business.
    """
    from clausal.pythonic_ast.nodes import (
        ImportFromDirective, ImportModuleDirective,
    )
    from clausal.templating.term_rewriting import _resolve_import_path

    targets = {}
    for item in module_items or ():
        if isinstance(item, ImportFromDirective):
            names = []
            for entry in item.names:
                if isinstance(entry, str):
                    names.append(entry)
                elif isinstance(entry, (tuple, list)) and len(entry) == 2:
                    names.append(f"alias({entry[0]}, {entry[1]})")
            directive = f"-import_from({item.module}, [{', '.join(names)}])"
        elif isinstance(item, ImportModuleDirective):
            directive = f"-import_module({item.module})"
        else:
            continue
        try:
            resolved = _resolve_import_path(item.module)
        except Exception:
            resolved = item.module
        targets.setdefault(resolved, (item.module, directive))
    return targets


def _prefix_target(failed, targets):
    """``(declared, directive)`` for the directive whose path stops at *failed*.

    ``-import_from(eu.state_aid.reg_w_scheme, …)`` against a hyphenated
    ``eu/state-aid/`` raises with ``name='eu.state_aid'`` — a strict prefix of
    the declared path, so the exact-key lookup above misses it and CPython's
    bare one-liner escaped for a directive we can see.

    Only a prefix of the *declared text* counts.  A name the author never wrote
    (an alias rewrite such as ``date_time`` → ``clausal.modules.py.date_time``,
    which fails at ``clausal.modules.py`` when the install is broken) cannot be
    quoted back at them as "the segment that did not resolve", so those keep
    Python's own message.

    The match is on the name, not on the route: a transitive ``import a.b``
    failing deep inside some unrelated module is indistinguishable here from
    this file's own ``-import_from(a.b.c, …)``, and gets attributed to that
    directive.  Harmless, because ``a.b`` is unreachable either way and so the
    named directive would fail identically (Python's traceback still shows who
    actually raised) — but it is why the message speaks of the segment and what
    follows from it, never of the resolution having been attempted.
    """
    prefix = failed + "."
    for declared, directive in targets.values():
        if declared.startswith(prefix):
            return declared, directive
    return None


def enrich_import_error(exc, module_items, importer_file=None):
    """Return a replacement ``ImportError``, or ``None`` to re-raise ``exc``.

    ``module_items`` are the declarations of the file currently being
    executed, used to tell "this file's import directive failed" from "an
    import somewhere deeper in the graph failed".
    """
    if getattr(exc, _ENRICHED_FLAG, False):
        return None

    targets = _import_targets(module_items)
    dotted = getattr(exc, "name", None)
    if not dotted:
        return None
    missing = getattr(exc, "name_from", None)
    if dotted in targets:
        declared, directive = targets[dotted]
    elif missing is None and isinstance(exc, ModuleNotFoundError):
        hit = _prefix_target(dotted, targets)
        if hit is None:
            return None
        declared, directive = hit
    else:
        return None

    if missing is None:
        # ``from M import …`` where M itself could not be found.
        if not isinstance(exc, ModuleNotFoundError):
            return None
        message = _describe_missing_module(exc, declared, dotted, directive,
                                           importer_file)
    else:
        mod = sys.modules.get(dotted)
        loader = _clausal_loader_of(mod) if mod is not None else None
        if loader is None:
            # Case 3: a real Python module.  Hands off.
            return None
        message = _describe_missing_name(exc, missing, declared, mod, loader)

    # Keep the concrete class: callers that catch ModuleNotFoundError
    # specifically must keep catching it.
    try:
        new = type(exc)(message, name=exc.name,
                        path=getattr(exc, "path", None))
    except TypeError:  # pragma: no cover - exotic ImportError subclass
        new = ImportError(message, name=exc.name,
                          path=getattr(exc, "path", None))
    try:
        new.name_from = missing
    except AttributeError:  # pragma: no cover - defensive
        pass
    setattr(new, _ENRICHED_FLAG, True)
    return new


def exec_with_import_diagnostics(code, module_dict, module_items,
                                 importer_file=None):
    """``exec(code, module_dict)`` with import failures made actionable.

    Also the load-time half of the undefined-name diagnostic.  A name a sibling
    exports and this file forgot to import surfaces here when the module body
    itself evaluates it (``REF = cite(art_9)`` at module scope), and at
    :func:`clausal.logic.solve._drive_trampoline` when a goal does — two seams,
    because the module body and the compiled predicates are executed at
    different times, and one helper, because both recover the module from the
    raising frame rather than from their caller.
    """
    try:
        exec(code, module_dict)
    except NameError as exc:
        from clausal.predicate_diagnostics import (  # noqa: PLC0415
            enrich_undefined_name,
        )
        better = enrich_undefined_name(exc)
        if better is None:
            raise
        raise better.with_traceback(exc.__traceback__) from None
    except ImportError as exc:
        better = enrich_import_error(exc, module_items, importer_file)
        if better is None:
            raise
        # Re-raise on the ORIGINAL traceback so the frame still points at the
        # ``-import_from`` line in the .clausal source, and suppress the
        # chained duplicate — the enriched message already contains
        # ``str(exc)`` as its first line.
        raise better.with_traceback(exc.__traceback__) from None
