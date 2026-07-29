"""Actionable diagnostics for failed ``-import_from`` / ``-import_module``.

``-import_from(M, [name])`` lowers to a Python ``from M import name``, so a
stale name surfaces as CPython's stock message::

    cannot import name 'within_limit' from 'eu.aml.amlr_bo_chain.schema'
    (/…/schema.clausal)

which names the file but never the vocabulary — the one thing a repair needs.
See ``todo/import-error-should-list-module-exports.md``: this was the dominant
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

Everything here runs on the error path only, so re-parsing the target module's
source to recover its declarations costs nothing in the normal case.
"""

from __future__ import annotations

import difflib
import re
import sys
import textwrap

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
    """
    from clausal.import_hook import predicate_builtins
    from clausal.logic.predicate import PredicateMeta

    entries = []
    for name, value in vars(mod).items():
        if not isinstance(name, str) or name.startswith("_") or "$" in name:
            continue
        if not isinstance(value, PredicateMeta):
            continue
        if predicate_builtins.get(name) is value:
            continue
        if getattr(value, "__module__", None) != mod.__name__:
            continue  # re-exported from elsewhere; not this module's own
        fields = getattr(value, "_fields", ()) or ()
        entries.append((name, f"{name}/{len(fields)}" if fields else name))
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


def _describe_missing_module(exc, dotted, directive, importer_file):
    """Case 2 — the module named by the directive does not exist."""
    lines = [str(exc), f"{_INDENT}{directive}"]
    if importer_file:
        lines.append(f"{_INDENT}  in {importer_file}")
    lines.extend(textwrap.wrap(
        f"names a module that does not exist: no .clausal file, .pl file or "
        f"Python module called '{dotted}' is on the import path. There is "
        f"therefore no export list to show — this is a MISSING module, not a "
        f"module that exports nothing.",
        width=_WIDTH, initial_indent=_INDENT, subsequent_indent=_INDENT,
        break_long_words=False, break_on_hyphens=False,
    ))
    lines.extend(_arrow([
        "fix the module path (check spelling and package prefix), or create "
        "that module.",
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
    if not dotted or dotted not in targets:
        return None
    declared, directive = targets[dotted]

    missing = getattr(exc, "name_from", None)
    if missing is None:
        # ``from M import …`` where M itself could not be found.
        if not isinstance(exc, ModuleNotFoundError):
            return None
        message = _describe_missing_module(exc, declared, directive,
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
    """``exec(code, module_dict)`` with import failures made actionable."""
    try:
        exec(code, module_dict)
    except ImportError as exc:
        better = enrich_import_error(exc, module_items, importer_file)
        if better is None:
            raise
        # Re-raise on the ORIGINAL traceback so the frame still points at the
        # ``-import_from`` line in the .clausal source, and suppress the
        # chained duplicate — the enriched message already contains
        # ``str(exc)`` as its first line.
        raise better.with_traceback(exc.__traceback__) from None
