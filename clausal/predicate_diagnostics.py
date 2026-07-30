"""Actionable diagnostics for a predicate lookup that found nothing.

A call whose ``(functor, arity)`` resolves to no dispatch function used to
raise the bare::

    KeyError: 'Predicate citation/2 not found'

which states an absence and nothing else.  See
``todo/predicate-not-found-should-list-candidates.md``: with goal-level test
diagnostics already in place — the goal index and the full goal term are both
printed — this was the last failure mode in the census with a 0% recovery
rate, precisely *because* everything around it was good.  The missing piece is
the candidate list.

Three situations look identical from the bare message and want three
different fixes:

1. the name exists here at **another arity** — fix the call;
2. the name is defined in a module this file **imports**, or in a **sibling
   file** in the same directory, but is not in scope here — fix the import;
3. the name was never written — define it.  Saying that plainly, and naming
   what *is* defined, is what separates it from case 2.

Nothing here runs unless a lookup has already failed, so re-reading source
files to recover a sibling's ``-module(...)`` list costs nothing in the normal
case.  ``describe_missing_predicate`` is the entry point.

A second, near-identical fault lives here too: the name resolved, but at
another arity.  That is *not* case 1 — case 1 is reached only when the name is
absent from the caller's namespace, and the common in-module call resolves the
class directly and used to fail as a bare Python ``TypeError`` about a missing
``trail``.  See ``describe_arity_mismatch`` and
``todo/done/arity-mismatch-reports-a-missing-trail-argument.md``.  It gets its
own message rather than being folded into case 1, because ``Predicate
citation/2 not found`` states an absence that is not the fault when
``citation`` is right there in the file.

The near-miss scoring is deliberately *not* reimplemented: it is imported from
:mod:`clausal.import_diagnostics` so the two messages agree on what counts as
a suggestion (plain ``difflib`` scores ``within_limit`` vs ``exceeds_limit`` at
0.48 and would say nothing, which is why that scorer blends token overlap in).
"""

from __future__ import annotations

import os
import sys
import textwrap
import types

from clausal.import_diagnostics import (
    _INDENT,
    _WIDTH,
    _arrow,
    _declared_exports,
    _name_list_lines,
    _suggestions,
)

#: Sibling files opened when hunting for the name.  The scan is bounded because
#: a package directory can be arbitrarily large and this runs while an author
#: is waiting for a failure report.  A substring pre-filter means most of these
#: cost a read and nothing more.
_MAX_SIBLING_FILES = 60

#: Distinct "defined over there" reports shown.  More than a few stops being a
#: suggestion and starts being a search result.
_MAX_HITS = 3

_SOURCE_SUFFIXES = (".clausal", ".pl")


# ── the exception ────────────────────────────────────────────────────────────


class PredicateNotFoundError(KeyError):
    """``KeyError`` whose ``str()`` is its message, verbatim.

    The raise site has always been a ``KeyError`` and callers catch it as one
    (``tests/test_solve.py``, ``tests/test_import.py``, ``docs/import.md``), so
    the class stays inside the ``KeyError`` hierarchy.  But ``str(KeyError(m))``
    is ``repr(m)``: it wraps the text in quotes and escapes every newline,
    which would turn a multi-line candidate list into one unreadable line.
    Overriding ``__str__`` is the smallest change that keeps both properties.
    """

    def __str__(self) -> str:  # noqa: D105
        if len(self.args) == 1 and isinstance(self.args[0], str):
            return self.args[0]
        return super().__str__()


def predicate_not_found(functor, arity, db=None, module_globals=None):
    """Build the exception for a failed ``functor/arity`` lookup.

    Callers ``raise predicate_not_found(...)`` — the message is assembled here
    so that every raise site tells the same story.
    """
    return PredicateNotFoundError(
        describe_missing_predicate(functor, arity, db, module_globals)
    )


class PredicateArityMismatchError(TypeError):
    """The call named a predicate that exists, at an arity it does not have.

    A ``TypeError`` because that is what the raw failure already was — the
    generated dispatch function ran out of positional arguments — so any
    ``except TypeError`` around a goal keeps catching it.  What changes is the
    message: see :func:`describe_arity_mismatch`.
    """


def predicate_arity_mismatch(functor, called_arity, defined_arity, site=None):
    """Build the exception for a call to *functor* at the wrong arity."""
    return PredicateArityMismatchError(
        describe_arity_mismatch(functor, called_arity, defined_arity, site)
    )


def describe_arity_mismatch(functor, called_arity, defined_arity, site=None):
    """The message for calling *functor* at *called_arity* when it takes another.

    Unlike :func:`describe_missing_predicate` this is not a search: the name
    resolved, to a predicate we are holding.  So the message states the fault
    outright rather than reporting an absence and leaving the reader to infer
    it — ``Predicate citation/2 not found`` is true, but it is the wrong
    sentence when ``citation`` is right there in the file.

    *site* is the ``(file, line)`` the predicate was registered at, or ``None``.

    Never raises: a diagnostic that fails must degrade to a plain statement of
    the two arities, not replace one failure with a different one.
    """
    if not isinstance(defined_arity, int):
        return f"{functor} does not accept {_arguments(called_arity)}"
    head = (f"{functor} takes {_arguments(defined_arity)}, "
            f"but this call passes {called_arity}")
    try:
        return "\n".join(_describe_mismatch(head, functor, called_arity,
                                            defined_arity, site))
    except Exception:  # noqa: BLE001 - see docstring
        return head


def _arguments(n):
    return f"{n} argument" + ("" if n == 1 else "s")


def _describe_mismatch(head, functor, called_arity, defined_arity, site):
    """The site line and the remedy line under *head*.

    The remedy does not say "define ``functor/called_arity`` as a predicate of
    its own", which was the first wording and is advice the implementation
    refuses to take: a second head of the same name at another arity in the same
    file is padded with a wildcard and absorbed into the existing predicate
    (``todo/same-name-two-arities-silently-merge.md``), so a reader who followed
    it wrote the clause, watched it vanish, and got this same message again.
    Renaming is the only remedy that works today, and the sentence says why so
    the reader does not have to try the other one — see ``docs/predicates.md``.
    """
    lines = [head]
    if isinstance(site, tuple) and len(site) == 2:
        lines.extend(_sentence(
            f"{functor}/{defined_arity} is defined at {site[0]}:{site[1]}."))
    lines.extend(_arrow([
        f"pass {_arguments(defined_arity)} to {functor}, or give the "
        f"{called_arity}-argument predicate a different name: a second "
        f"{functor} head with {_arguments(called_arity)} in the same file does "
        f"not define {functor}/{called_arity} — it is padded with a wildcard "
        f"and absorbed into {functor}/{defined_arity}."
    ]))
    return lines


# ── namespace introspection ──────────────────────────────────────────────────


def _items(namespace):
    """``namespace.items()`` defensively — a diagnostic must not raise."""
    try:
        return list(namespace.items())
    except Exception:  # noqa: BLE001 - a broken namespace is not our failure
        return []


def _arity_of(obj):
    """Declared arity of a predicate class, or ``None`` if it is not one."""
    from clausal.logic.predicate import PredicateMeta

    if not isinstance(obj, PredicateMeta):
        return None
    fields = getattr(obj, "_fields", None)
    if fields is not None:
        return len(fields)
    arity = getattr(obj, "_arity", None)
    return arity if isinstance(arity, int) else None


def _modname(module_globals):
    if not module_globals:
        return None
    try:
        name = module_globals.get("__name__")
    except Exception:  # noqa: BLE001
        return None
    return name if isinstance(name, str) else None


def _module_file(module_globals):
    if not module_globals:
        return None
    try:
        path = module_globals.get("__file__")
    except Exception:  # noqa: BLE001
        return None
    return path if isinstance(path, str) else None


def _local_entries(module_globals, modname, db):
    """``[(name, arity)]`` this module defines itself, sorted.

    Two stores hold the answer and neither is complete on its own: the
    database carries every predicate with clauses (including ones with no
    class in the namespace — exactly the case that reaches the failing
    lookup), and the namespace carries the predicate classes.  Union them.

    Zero-arity namespace entries are dropped unless the database confirms
    clauses for them: in Clausal a bare atom is a fieldless predicate class, so
    keeping them would bury three callable predicates under fifty atoms.
    """
    from clausal.import_hook import predicate_builtins

    found: dict[tuple[str, int], None] = {}
    for key in getattr(db, "_clauses", None) or ():
        if isinstance(key, tuple) and len(key) == 2 and isinstance(key[0], str):
            found[key] = None
    for name, value in _items(module_globals):
        if not isinstance(name, str) or name.startswith("_") or "$" in name:
            continue
        if predicate_builtins.get(name) is value:
            continue
        if modname is not None and getattr(value, "__module__", None) != modname:
            continue  # imported or re-exported; not this module's own
        arity = _arity_of(value)
        if arity:
            found[(name, arity)] = None
    return sorted(found)


def _imported_entries(module_globals, modname):
    """``[(name, arity, origin)]`` for predicate classes imported into here.

    They cannot explain an exact-name miss — a name bound here would have been
    found — but they are part of the vocabulary in scope, so they belong in
    the near-miss pool.
    """
    from clausal.import_hook import predicate_builtins

    out = []
    for name, value in _items(module_globals):
        if not isinstance(name, str) or name.startswith("_") or "$" in name:
            continue
        if predicate_builtins.get(name) is value:
            continue
        origin = getattr(value, "__module__", None)
        if origin is None or origin == modname:
            continue
        arity = _arity_of(value)
        if arity:
            out.append((name, arity, origin))
    out.sort()
    return out


def _builtin_arities(functor):
    """Arities at which *functor* is a builtin, sorted.

    Without this the message for ``atom_length/3`` would read "no predicate
    named `atom_length` … define it" — a worse diagnosis than the bare line it
    replaces, because ``atom_length/2`` is right there in the library.  The
    registry is keyed by ``(functor, arity)``, so this is a scan of its keys,
    not a probe.
    """
    from clausal.logic.builtins import _BUILTINS, _DB_BUILTINS

    found = set()
    for registry in (_BUILTINS, _DB_BUILTINS):
        for name, arity in registry:
            if name == functor:
                found.add(arity)
    return sorted(found)


# ── where else the name could live ───────────────────────────────────────────


class _Hit:
    """One place the missing name *is* defined."""

    __slots__ = ("module", "arity", "how", "alias")

    def __init__(self, module, arity, how, alias=None):
        self.module = module      # dotted module path, or file stem
        self.arity = arity        # int, or None when only the name is known
        self.how = how            # 'imported' | 'sibling'
        self.alias = alias        # the name this file binds that module under


def _defines(mod, functor):
    """Arity at which the loaded module *mod* defines *functor*, or ``None``."""
    try:
        obj = getattr(mod, functor, None)
    except Exception:  # noqa: BLE001
        return None
    return _arity_of(obj)


def _import_directive_targets(path):
    """``[(dotted, alias)]`` for every import directive in the file at *path*.

    Re-parses the source, as ``import_diagnostics`` does and for the same
    reason: the directives are the author's own statement of what this file can
    see, and they are not retained at runtime.
    """
    from clausal.import_hook import _extract_module_items
    from clausal.pythonic_ast.nodes import (
        ImportFromDirective, ImportModuleDirective,
    )
    from clausal.templating.term_rewriting import _resolve_import_path

    try:
        with open(path, encoding="utf-8") as handle:
            source = handle.read()
        items = _extract_module_items(source, path)
    except Exception:  # noqa: BLE001 - source may be gone or unparseable
        return []

    out = []
    for item in items or ():
        if not isinstance(item, (ImportFromDirective, ImportModuleDirective)):
            continue
        try:
            dotted = _resolve_import_path(item.module)
        except Exception:  # noqa: BLE001
            dotted = item.module
        alias = (dotted.rsplit(".", 1)[-1]
                 if isinstance(item, ImportModuleDirective) else None)
        out.append((dotted, alias))
    return out


def _imported_module_hits(functor, module_globals, modname, path):
    """Where the name is defined among modules this file can already see."""
    hits, seen = [], set()

    def _consider(dotted, mod, alias):
        if mod is None or dotted in seen:
            return
        if getattr(mod, "__name__", None) == modname:
            return
        seen.add(dotted)
        arity = _defines(mod, functor)
        if arity is not None:
            hits.append(_Hit(dotted, arity, "imported", alias))

    if path:
        for dotted, alias in _import_directive_targets(path):
            _consider(dotted, sys.modules.get(dotted), alias)
    for name, value in _items(module_globals):
        if (isinstance(name, str) and not name.startswith("_")
                and isinstance(value, types.ModuleType)):
            _consider(getattr(value, "__name__", name), value, name)
    return hits


def _sibling_source_files(path):
    """``(files, total)`` — sibling sources in *path*'s directory, capped.

    ``total`` is the true number of siblings, which is what lets the message
    say "of N" when the cap bit.  A silently truncated search would let the
    message claim an absence it never established.
    """
    if not path:
        return [], 0
    try:
        directory = os.path.dirname(os.path.abspath(path))
        names = sorted(os.listdir(directory))
    except OSError:
        return [], 0
    here = os.path.abspath(path)
    out = []
    for name in names:
        if not name.endswith(_SOURCE_SUFFIXES):
            continue
        full = os.path.join(directory, name)
        if full != here:
            out.append(full)
    return out[:_MAX_SIBLING_FILES], len(out)


def _loaded_module_for(path):
    """The already-imported module whose ``__file__`` is *path*, if any."""
    try:
        target = os.path.abspath(path)
    except Exception:  # noqa: BLE001
        return None
    for mod in list(sys.modules.values()):
        try:
            other = getattr(mod, "__file__", None)
        except Exception:  # noqa: BLE001
            continue
        if other and os.path.abspath(other) == target:
            return mod
    return None


def _declared_arity(path, functor):
    """Arity *functor* is exported at by the ``-module(...)`` line in *path*.

    ``False`` means the file was read and does not export the name; ``None``
    means the question could not be answered (unreadable, unparseable, or
    exported without an arity).  For an un-imported sibling this is all that
    can be established without executing it, and executing a module to improve
    an error message is not a trade this makes.
    """
    from clausal.import_hook import _extract_module_items

    try:
        with open(path, encoding="utf-8") as handle:
            source = handle.read()
    except OSError:
        return None
    if functor not in source:
        return False  # cheap pre-filter: not even mentioned
    try:
        entries, _ = _declared_exports(_extract_module_items(source, path))
    except Exception:  # noqa: BLE001
        return None
    for bare, rendered in entries:
        if bare == functor:
            _, _, arity = rendered.partition("/")
            return int(arity) if arity.isdigit() else None
    return False


def _sibling_hits(functor, siblings, already):
    """Where the name is defined among sibling files not already reported."""
    hits = []
    for sibling in siblings:
        label = os.path.basename(sibling)
        for suffix in _SOURCE_SUFFIXES:
            if label.endswith(suffix):
                label = label[: -len(suffix)]
        mod = _loaded_module_for(sibling)
        if mod is not None:
            dotted = getattr(mod, "__name__", label)
            arity = _defines(mod, functor) if dotted not in already else False
        else:
            dotted = label
            arity = (_declared_arity(sibling, functor)
                     if dotted not in already else False)
        if arity is not False and arity is not None:
            hits.append(_Hit(dotted, arity, "sibling"))
        if len(hits) >= _MAX_HITS:
            break
    return hits


# ── message assembly ─────────────────────────────────────────────────────────


def _sentence(text):
    """A ``  …`` block wrapped at the shared width, continuations hanging."""
    return textwrap.wrap(
        text, width=_WIDTH, initial_indent=_INDENT,
        subsequent_indent=_INDENT + "  ",
        break_long_words=False, break_on_hyphens=False,
    ) or [_INDENT + text]


def _hit_line(functor, hit):
    """One ``… is defined in …`` sentence."""
    what = f"{functor}/{hit.arity}" if hit.arity is not None else functor
    if hit.how == "imported":
        tail = (f"which this file imports as `{hit.alias}` — but `{functor}` "
                f"itself is not in scope here"
                if hit.alias else
                f"which this file imports, but not the name `{functor}`")
    else:
        tail = ("a sibling file in the same directory, which this file does "
                "not import")
    return _sentence(f"{what} is defined in {hit.module}, {tail}.")


def _builtin_line(functor, arity, builtin):
    shown = ", ".join(f"{functor}/{a}" for a in builtin)
    return _sentence(f"{shown} is a builtin — this call passes {arity} "
                     f"argument{'' if arity == 1 else 's'}.")


def _suggestion_line(functor, arity, here, builtin, hits, pool):
    """The ``did you mean:`` line, or ``[]`` when there is nothing to say.

    Never emitted empty: an empty suggestion suggests nothing, but reads as if
    it were an answer.
    """
    if here:
        shown = ", ".join(f"{functor}/{a}" for a in here[:_MAX_HITS])
        return _sentence(f"did you mean: {shown} ?   "
                         f"(same name, different arity)")
    if builtin:
        shown = ", ".join(f"{functor}/{a}" for a in builtin[:_MAX_HITS])
        return _sentence(f"did you mean: {shown} ?   "
                         f"(same name, different arity — a builtin)")
    if hits:
        hit = hits[0]
        what = f"{functor}/{hit.arity}" if hit.arity is not None else functor
        note = ("same name, another module" if hit.arity == arity
                else "same name, different arity, another module")
        return _sentence(f"did you mean: {what} from {hit.module} ?   "
                         f"({note})")
    names = _suggestions(functor, [name for name, _ in pool])
    if not names:
        return []
    rendered = dict(pool)
    shown = ", ".join(rendered.get(name, name) for name in names)
    return _sentence(f"did you mean: {shown} ?   (similar name)")


def _remedy(functor, arity, label, here, builtin, hits):
    if here:
        arities = ", ".join(f"{functor}/{a}" for a in here)
        return [f"call it at an arity it is defined at ({arities}), or define "
                f"{functor}/{arity}."]
    if builtin:
        arities = ", ".join(f"{functor}/{a}" for a in builtin)
        return [f"call the builtin at its own arity ({arities}) — or, if you "
                f"meant a predicate of your own, define {functor}/{arity} "
                f"here (it will shadow the builtin)."]
    if hits:
        hit = hits[0]
        at = hit.arity if hit.arity is not None else arity
        lines = [f"add -import_from({hit.module}, [{functor}]) to this file, "
                 f"then call {functor}/{at}."]
        if hit.alias:
            lines.append(f"or call it qualified: {hit.alias}.{functor}(...).")
        return lines
    return [f"define {functor}/{arity} in {label}, or import it from the "
            f"module that does define it."]


def _absent_line(functor, label, path, searched, total):
    """State the absence in exactly the terms it was established in.

    An un-imported sibling is only read for its ``-module(...)`` list, so the
    claim about siblings is "does not export it", never the stronger "does not
    define it"; and if the scan was capped, the count says so.  Overstating
    here would send the author to define something that already exists.
    """
    text = (f"no predicate named `{functor}` is defined in {label} or in any "
            f"module it imports")
    if searched:
        where = os.path.dirname(os.path.abspath(path))
        noun = "sibling file" if total == 1 else "sibling files"
        if searched >= total:
            scanned = f"the {total} {noun}"
            tail = ""
        else:
            scanned = f"the first {searched} of {total} {noun}"
            tail = f" ({total - searched} NOT searched)"
        text += (f", and none of {scanned} in {where} exports it either"
                 f"{tail}")
    return _sentence(text + ".")


def describe_missing_predicate(functor, arity, db=None, module_globals=None):
    """The full multi-line message for a failed ``functor/arity`` lookup.

    Never raises: a diagnostic that fails must degrade to the original one-line
    message, not replace one failure with a different one.
    """
    head = f"Predicate {functor}/{arity} not found"
    try:
        return "\n".join(_describe(head, functor, arity, db, module_globals))
    except Exception:  # noqa: BLE001 - see docstring
        return head


def _describe(head, functor, arity, db, module_globals):
    if not module_globals and db is not None:
        module_globals = getattr(db, "module_dict", None)
    modname = _modname(module_globals)
    path = _module_file(module_globals)
    label = modname or "this module"

    local = _local_entries(module_globals, modname, db)
    imported = _imported_entries(module_globals, modname)
    here = sorted({a for name, a in local if name == functor})

    # Cheapest and most exact answers first; each one that lands makes the
    # next search unnecessary, which is also what keeps the sibling scan off
    # the common cases.
    builtin = _builtin_arities(functor) if not here else []
    hits, searched, total = [], 0, 0
    if not here and not builtin:
        hits = _imported_module_hits(functor, module_globals, modname, path)
        siblings, total = _sibling_source_files(path)
        searched = len(siblings)
        hits.extend(_sibling_hits(functor, siblings,
                                  {hit.module for hit in hits}))
        hits = hits[:_MAX_HITS]

    lines = [head]

    # What this module has.  Never an empty list — an empty list reads as
    # "nothing is defined here", which is a different and misleading claim.
    if local:
        lines.extend(_name_list_lines(
            f"{label} defines:",
            [(name, f"{name}/{a}") for name, a in local], path))
    else:
        lines.append(f"{_INDENT}{label} defines no predicates of its own.")

    if builtin:
        lines.extend(_builtin_line(functor, arity, builtin))
    for hit in hits:
        lines.extend(_hit_line(functor, hit))

    if not here and not builtin and not hits:
        lines.extend(_absent_line(functor, label, path, searched, total))

    pool = [(name, f"{name}/{a}") for name, a in local]
    pool += [(name, f"{name}/{a} (from {origin})")
             for name, a, origin in imported]
    lines.extend(_suggestion_line(functor, arity, here, builtin, hits, pool))
    lines.extend(_arrow(_remedy(functor, arity, label, here, builtin, hits)))
    return lines
