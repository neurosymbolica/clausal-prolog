"""Actionable diagnostics for a predicate lookup that found nothing.

A call whose ``(functor, arity)`` resolves to no dispatch function used to
raise the bare::

    KeyError: 'Predicate citation/2 not found'

which states an absence and nothing else.  See
``todo/done/predicate-not-found-should-list-candidates.md``: with goal-level test
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

from clausal._suffixes import SOURCE_SUFFIXES
from clausal.logic.exceptions import LogicException, existence_error
from clausal.import_diagnostics import (
    _INDENT,
    _WIDTH,
    _arrow,
    _declared_exports,
    _name_list_lines,
    _sentence,
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

_SOURCE_SUFFIXES = SOURCE_SUFFIXES


# ── the exception ────────────────────────────────────────────────────────────


def procedure_existence_term(functor, arity, message):
    """``error(existence_error(procedure, Name/Arity), Message)`` -- the ISO
    term Scryer raises for a call to a procedure that does not exist, with the
    engine's own diagnostic *message* as the context (its "why").

    *functor* may be a mangled predicate handle; only its demangled NAME goes
    into the indicator (ruling 2026-09-24: the culprit is the bare
    ``Name/Arity``, the module named in the message only).  Shared by the two
    dual-typed lookup errors below.
    """
    from clausal.logic.atoms import demangle, is_mangled, mint  # noqa: PLC0415
    from clausal.terms import Compound  # noqa: PLC0415
    name = demangle(functor)[1] if is_mangled(functor) else functor
    return existence_error(
        "procedure", Compound("/", (mint(name), arity)), message)


class PredicateNotFoundError(LogicException, KeyError):
    """``KeyError`` whose ``str()`` is its message, verbatim.

    The raise site has always been a ``KeyError`` and callers catch it as one
    (``tests/test_solve.py``, ``tests/test_import.py``, ``docs/import.md``), so
    the class stays inside the ``KeyError`` hierarchy.  But ``str(KeyError(m))``
    is ``repr(m)``: it wraps the text in quotes and escapes every newline,
    which would turn a multi-line candidate list into one unreadable line.
    Overriding ``__str__`` is the smallest change that keeps both properties.

    Also a ``LogicException`` (operator ruling 2026-09-25: a DIRECT call of an
    unknown procedure raises ISO ``existence_error``, like Scryer, whose
    ``catch(nosuch(1), E, true)`` gives
    ``E = error(existence_error(procedure, nosuch/1), nosuch/1)``).  ``.term``
    is ``error(existence_error(procedure, Name/Arity), Message)``, the "defines:
    ... / -> define it or import it" candidate list as the context, so
    ``catch/3`` binds the ISO term where it bound the transliterated
    ``PredicateNotFoundError(Message)`` compound before.  ADD, not replace:
    ``except KeyError`` / ``except PredicateNotFoundError`` and a
    ``++KeyError`` catcher (``exceptions._dual_typed_match``) keep working;
    ``args``/``str()`` stay the message alone.

    *functor* / *arity* build the indicator.  Built without them (an
    out-of-tree caller with only a message) the term is the
    ``PredicateNotFoundError(Message)`` compound ``catch/3`` bound before
    2026-09-25.  The same design as ``PredicateArityMismatchError``.
    """

    def __init__(self, message, functor=None, arity=None):
        # Exception.__init__, not LogicException's: ``args`` stays the
        # message itself, so ``str()``, ``repr()`` and ``e.args[0]`` read as
        # they always did.
        Exception.__init__(self, message)
        if isinstance(functor, str) and isinstance(arity, int):
            term = procedure_existence_term(functor, arity, message)
        else:
            from clausal.logic.exceptions import python_error_term  # noqa: PLC0415
            term = python_error_term(self)
        self.term = term
        self.functor = functor
        self.arity = arity

    def __str__(self) -> str:  # noqa: D105
        if len(self.args) == 1 and isinstance(self.args[0], str):
            return self.args[0]
        return Exception.__str__(self)


def predicate_not_found(functor, arity, db=None, module_globals=None):
    """Build the exception for a failed ``functor/arity`` lookup.

    Callers ``raise predicate_not_found(...)`` — the message is assembled here
    so that every raise site tells the same story.
    """
    return PredicateNotFoundError(
        describe_missing_predicate(functor, arity, db, module_globals),
        functor, arity,
    )


class PredicateArityMismatchError(LogicException, TypeError):
    """The call named a predicate that exists, at an arity it does not have.

    A ``TypeError`` because that is what the raw failure already was — the
    generated dispatch function ran out of positional arguments — so any
    ``except TypeError`` around a goal keeps catching it.  What changes is the
    message: see :func:`describe_arity_mismatch`.

    Also a ``LogicException`` (operator ruling 2026-09-25, "do what Scryer
    does"): ISO has no arity-mismatch error -- a predicate is name + arity, so
    ``pk/2`` simply does not exist when only ``pk/1`` does, and Scryer answers
    ``catch(call(pk(3), _), E, true)`` with
    ``E = error(existence_error(procedure, pk/2), pk/2)``, the indicator at
    the CALLED arity.  ``.term`` is that ISO term, with this message (the
    "takes 1 argument" diagnostic) as its context, the way an unknown
    procedure's ``existence_error`` carries its "why" text
    (``predicate._dispatch_at``).  ``catch/3`` reads ``.term`` of any
    ``LogicException``, so a source catcher
    ``error(existence_error(procedure, PI), _)`` catches it; ``except
    TypeError`` / ``except PredicateArityMismatchError`` in Python keep
    working, and ``str()`` is the message alone, as before.

    *functor* / *called_arity* build the indicator.  Built without them (an
    out-of-tree caller with only a message) the term is the
    ``PredicateArityMismatchError(Message)`` compound ``catch/3`` bound
    before 2026-09-25.
    """

    def __init__(self, message, functor=None, called_arity=None):
        if isinstance(functor, str) and isinstance(called_arity, int):
            from clausal.logic.atoms import demangle, is_mangled, mint  # noqa: PLC0415
            from clausal.terms import Compound  # noqa: PLC0415
            name = demangle(functor)[1] if is_mangled(functor) else functor
            term = existence_error(
                "procedure", Compound("/", (mint(name), called_arity)),
                message)
        else:
            term = None
        # Exception.__init__, not LogicException's: ``args`` stays the
        # message itself, so ``str()`` and ``repr()`` read as they always did.
        Exception.__init__(self, message)
        if term is None:
            from clausal.logic.exceptions import python_error_term  # noqa: PLC0415
            term = python_error_term(self)
        self.term = term
        self.functor = functor
        self.called_arity = called_arity

    def __str__(self) -> str:  # noqa: D105
        return Exception.__str__(self)


def predicate_arity_mismatch(functor, called_arity, defined_arity, site=None):
    """Build the exception for a call to *functor* at the wrong arity."""
    return PredicateArityMismatchError(
        describe_arity_mismatch(functor, called_arity, defined_arity, site),
        functor, called_arity,
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
    refuses to take: a second head of the same name at another arity in the
    same file is a load-time SyntaxError
    (``todo/done/same-name-two-arities-silently-merge.md`` — before that fix
    it was silently padded with a wildcard and absorbed into the existing
    predicate, which was worse).  Renaming is the only remedy that works, and
    the sentence says why so the reader does not have to try the other one —
    see ``docs/predicates.md``.
    """
    lines = [head]
    if isinstance(site, tuple) and len(site) == 2:
        lines.extend(_sentence(
            f"{functor}/{defined_arity} is defined at {site[0]}:{site[1]}."))
    lines.extend(_arrow([
        f"pass {_arguments(defined_arity)} to {functor}, or give the "
        f"{called_arity}-argument predicate a different name: a second "
        f"{functor} head with {_arguments(called_arity)} in the same file does "
        f"not define {functor}/{called_arity} — one name has one arity, and "
        f"the head is refused at load."
    ]))
    return lines


# ── namespace introspection ──────────────────────────────────────────────────


def _items(namespace):
    """``namespace.items()`` defensively — a diagnostic must not raise."""
    try:
        return list(namespace.items())
    except Exception:  # noqa: BLE001 - a broken namespace is not our failure
        return []


def _arities_of(obj, cache=None, db=None):
    """The SET of arities *obj* is a predicate at; empty if it is not one.

    F4, ruling 3.  This was ``_arity_of``, answering one arity or ``None``,
    and both pool builders guarded it with ``if arity:`` -- so a ``p/0``
    predicate was falsy and never reached the near-miss pool.  The empty set
    now carries "not a predicate here", and several arities are several
    suggestions.  Era-agnostic (a ``PredicateMeta`` class or a mangled atom),
    and read from the owner's lossless ``predicate_arities``, never the
    lossy ``Database.arities_for`` -- see
    ``clausal.logic.predicate.predicate_arities_for``, which also says why
    an arity known only by declaration (a bare export entry, an adopted
    row) is not answered beside a defined one.  *cache* is the per-call
    index memo created in :func:`_describe`.
    """
    from clausal.logic.predicate import predicate_arities_for

    try:
        return predicate_arities_for(obj, cache=cache, db=db)
    except Exception:  # noqa: BLE001 - a diagnostic must not raise
        return set()


def _owner_of(obj):
    """The module that owns the predicate *obj* denotes, era-agnostic."""
    from clausal.logic.predicate import predicate_owner_module

    try:
        return predicate_owner_module(obj)
    except Exception:  # noqa: BLE001
        return None


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


def _local_entries(module_globals, modname, db, cache=None):
    """``[(name, arity)]`` this module defines itself, sorted.

    Two stores hold the answer and neither is complete on its own: the
    database carries every predicate with clauses (including ones with no
    class in the namespace — exactly the case that reaches the failing
    lookup), and the namespace carries the predicate classes.  Union them.

    Zero-arity namespace entries are kept (F4): they used to be dropped by
    an ``if arity:`` guard, on the stated ground that a bare atom was a
    fieldless predicate class and would bury the real predicates.  No atom
    is a class any more: at stage 2 of the atoms-as-str flip an atom IS the
    interned Python ``str`` (``clausal.logic.atoms.is_atom`` is ``type(term)
    is str``; ``mint`` returns ``sys.intern(spelling)``, and ``'[]'`` is the
    empty list), and a non-mangled ``str`` answers the empty set.  A
    ``-hide`` atom is a mangled ``str``, looked up at its owner, and answers
    only if that module defines a predicate of the same name.  The zero-arity
    entries left are real ``p/0`` predicates -- the ones the guard was
    wrongly hiding.
    """
    from clausal.import_hook import predicate_builtins

    found: dict[tuple[str, int], None] = {}
    for key in getattr(db, "_clauses", None) or ():
        if isinstance(key, tuple) and len(key) == 2 and isinstance(key[0], str):
            found[key] = None
    for name, value in _items(module_globals):
        if not isinstance(name, str) or name.startswith("_") or "$" in name:
            continue
        # Equality, never identity, for an atom (spec §2/§5.2): two
        # equal atoms are the same atom whether or not they are the
        # same tuple object, and ``mint`` returns a fresh tuple each
        # call.  THE FLIP retired the last of these ``is`` pins.
        if predicate_builtins.get(name) == value:
            continue
        if modname is not None and _owner_of(value) != modname:
            continue  # imported or re-exported; not this module's own
        for arity in _arities_of(value, cache, db):
            found[(name, arity)] = None
    return sorted(found)


def _imported_entries(module_globals, modname, cache=None):
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
        # Equality, never identity, for an atom (spec §2/§5.2): two
        # equal atoms are the same atom whether or not they are the
        # same tuple object, and ``mint`` returns a fresh tuple each
        # call.  THE FLIP retired the last of these ``is`` pins.
        if predicate_builtins.get(name) == value:
            continue
        origin = _owner_of(value)
        if origin is None or origin == modname:
            continue
        for arity in _arities_of(value, cache):
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


def _defines(mod, functor, cache=None):
    """Arities at which the loaded module *mod* defines *functor*, sorted;
    empty when it does not."""
    try:
        obj = getattr(mod, functor, None)
    except Exception:  # noqa: BLE001
        return []
    return sorted(_arities_of(obj, cache))


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


def _imported_module_hits(functor, module_globals, modname, path,
                          cache=None):
    """Where the name is defined among modules this file can already see."""
    hits, seen = [], set()

    def _consider(dotted, mod, alias):
        if mod is None or dotted in seen:
            return
        if getattr(mod, "__name__", None) == modname:
            return
        seen.add(dotted)
        for arity in _defines(mod, functor, cache):
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


def _declared_export_entry(path, functor):
    """The ``-module(...)`` entry for *functor* in *path*, as declared.

    ``'cite/1'`` for ``-module(m, [cite(KEY)])`` and ``'art_9'`` for a bare atom
    export; ``False`` means the file was read and does not export the name;
    ``None`` means the question could not be answered (unreadable or
    unparseable).  For an un-imported sibling this is all that can be
    established without executing it, and executing a module to improve an
    error message is not a trade this makes.

    Split out of :func:`_declared_arity` so the undefined-name diagnostic can
    ask the weaker question the todo specifies — *is the bare name in that
    export list at all* — without having to re-derive "exported, but at an
    arity I could not read" from a ``None`` that also means "I could not read
    the file".
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
            return rendered
    return False


def _declared_arity(path, functor):
    """Arity *functor* is exported at by the ``-module(...)`` line in *path*.

    ``False`` means the file was read and does not export the name; ``None``
    means the question could not be answered (unreadable, unparseable, or
    exported without an arity).
    """
    rendered = _declared_export_entry(path, functor)
    if rendered is False or rendered is None:
        return rendered
    _, _, arity = rendered.partition("/")
    return int(arity) if arity.isdigit() else None


def _sibling_hits(functor, siblings, already, cache=None):
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
            arities = (_defines(mod, functor, cache)
                       if dotted not in already else [])
        else:
            dotted = label
            arity = (_declared_arity(sibling, functor)
                     if dotted not in already else False)
            arities = [] if arity is False or arity is None else [arity]
        for arity in arities:
            hits.append(_Hit(dotted, arity, "sibling"))
        if len(hits) >= _MAX_HITS:
            break
    return hits


# ── message assembly ─────────────────────────────────────────────────────────


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
    # Deduplicated: a name at two arities is ONE candidate name (scored once,
    # counted once by the tie guard) rendered as two suggestions below.
    names = _suggestions(functor, list(dict.fromkeys(name for name, _ in pool)))
    if not names:
        return []
    # One name can stand at several arities -- several suggestions (F4),
    # so group rather than let ``dict(pool)`` keep only the last.
    rendered: dict[str, list[str]] = {}
    for name, text in pool:
        if text not in rendered.setdefault(name, []):
            rendered[name].append(text)
    shown = ", ".join(", ".join(rendered.get(name) or [name])
                      for name in names)
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

    # One functor -> arities index per database for the whole message,
    # instead of a scan of every store per binding (roborev on F4).
    cache: dict = {}
    local = _local_entries(module_globals, modname, db, cache)
    imported = _imported_entries(module_globals, modname, cache)
    here = sorted({a for name, a in local if name == functor})

    # Cheapest and most exact answers first; each one that lands makes the
    # next search unnecessary, which is also what keeps the sibling scan off
    # the common cases.
    builtin = _builtin_arities(functor) if not here else []
    hits, searched, total = [], 0, 0
    if not here and not builtin:
        hits = _imported_module_hits(functor, module_globals, modname, path,
                                     cache)
        siblings, total = _sibling_source_files(path)
        searched = len(siblings)
        hits.extend(_sibling_hits(functor, siblings,
                                  {hit.module for hit in hits}, cache))
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


# ── an undefined bare name a sibling module exports ──────────────────────────
#
# The third fault this file answers, and the one with the worst measured
# recovery rate.  A module in a decomposed-DAG package uses a predicate a
# sibling exports and forgets to import it; the name is simply absent from the
# compiled code's globals, so what the author sees is CPython's stock line::
#
#     NameError: name 'cite' is not defined
#
# The owner is fully decidable — it is in the sibling's ``-module(...)`` list,
# in the same directory — and the message said nothing about it.  In a 24-run
# local-model formalization study that message burned 16 attempts across 3 runs
# and never recovered once, every retry byte-identical, because there was
# nothing in it to act on.  Contrast the strict-atoms message for the exactly
# analogous mistake on an *atom*, which lists all five declaration routes.
# See ``todo/done/nameerror-does-not-name-the-sibling-that-exports-it.md``.
#
# The scan is the one already written above — ``_sibling_source_files`` plus
# ``_declared_export_entry`` — and it runs only from an ``except NameError``.
#
# It stays silent unless a sibling *genuinely* declares the name.  A NameError
# has many other causes (real Python code, a typo, a missing builtin, an
# undeclared atom) and the todo is explicit that the no-sibling case is
# undecidable and must keep today's message.


class _Export:
    """One sibling file's ``-module(...)`` entry for the missing name."""

    __slots__ = ("module", "rendered", "path")

    def __init__(self, module, rendered, path):
        self.module = module      # dotted path to write in -import_from
        self.rendered = rendered  # 'cite/1', or 'art_9' for a bare atom
        self.path = path          # the sibling source file


def _sibling_dotted(sibling, modname):
    """The dotted path *sibling* is importable under, best-effort.

    An already-loaded sibling knows its own ``__name__``, which is the only
    fully reliable answer.  Otherwise the file stem is qualified with the
    failing module's own package, because a decomposed-DAG package is exactly
    the case where that holds: ``eu.mar.constants`` next to ``citations.clausal``
    means ``eu.mar.citations``.
    """
    mod = _loaded_module_for(sibling)
    loaded = getattr(mod, "__name__", None) if mod is not None else None
    if isinstance(loaded, str) and loaded:
        return loaded
    stem = os.path.basename(sibling)
    for suffix in _SOURCE_SUFFIXES:
        if stem.endswith(suffix):
            stem = stem[: -len(suffix)]
    package = modname.rpartition(".")[0] if isinstance(modname, str) else ""
    return f"{package}.{stem}" if package else stem


def _exporting_sibling(name, path, modname):
    """The sibling whose ``-module(...)`` list holds *name*, or ``None``.

    Matching is on the bare name, per the todo: the arity is wanted for the
    text (``cite(KEY)`` → ``cite/1``) but a name declared at all is enough to
    decide that there is something to say.

    **The cap is a deliberate silent decline here**, unlike the
    predicate-not-found path, which reports ``total`` so the reader knows the
    scan was bounded.  Past ``_MAX_SIBLING_FILES`` this returns ``None`` and the
    stock ``NameError`` stands with nothing added.  The alternative — saying
    "no exporter found, but only 60 of N siblings were scanned" — would have to
    be attached to a *plain* ``NameError``, i.e. to every typo'd Python name in
    a package that large, which buys a rare true positive at the cost of noise
    on the common case.  The asymmetry is that the other diagnostic is already
    being printed, so its cap note is free, while this one would have to
    manufacture a message to carry it.  Recorded in
    ``todo/done/nameerror-does-not-name-the-sibling-that-exports-it.md``.
    """
    siblings, _total = _sibling_source_files(path)
    for sibling in siblings:
        rendered = _declared_export_entry(sibling, name)
        if rendered is False or rendered is None:
            continue
        dotted = _sibling_dotted(sibling, modname)
        if dotted == modname:
            continue  # the failing module itself, reached by another path
        return _Export(dotted, rendered, sibling)
    return None


def _module_label(modname, path):
    """What to call the module that used the name.

    A dotted name is the author's own vocabulary for the file and is worth
    printing.  An undotted one is not: modules loaded from a loose file get a
    synthetic top-level name (``clausal.testing`` mints ``_clausal_test_<stem>``)
    that appears nowhere in the source, so the file's own basename is both truer
    and the thing the reader is looking at.
    """
    if isinstance(modname, str) and "." in modname:
        return modname
    return os.path.basename(path)


def _rendered_import_names(entries):
    """The import list as the author wrote it, or ``None`` if it cannot be.

    ``None`` rather than a filtered list, because the remedy below reprints this
    list as the line to *replace* the directive with: quietly dropping an entry
    it could not render would tell the author to delete an import they need.
    Aliases are spelled the way ``import_diagnostics._import_targets`` spells
    them, so the two messages quote the same syntax back.
    """
    out = []
    for entry in entries or ():
        if isinstance(entry, str):
            out.append(entry)
        elif isinstance(entry, (tuple, list)) and len(entry) == 2:
            out.append(f"alias({entry[0]}, {entry[1]})")
        else:
            return None
    return out


def _import_from_directives(path):
    """``[(declared, resolved, [names])]`` for each ``-import_from`` in *path*.

    Re-parses the source for the same reason the rest of this file does: the
    directives are the author's own statement of what this file can see, and
    they are not retained at runtime.
    """
    from clausal.import_hook import _extract_module_items
    from clausal.pythonic_ast.nodes import ImportFromDirective
    from clausal.templating.term_rewriting import _resolve_import_path

    try:
        with open(path, encoding="utf-8") as handle:
            items = _extract_module_items(handle.read(), path)
    except Exception:  # noqa: BLE001 - source may be gone or unparseable
        return []

    out = []
    for item in items or ():
        if not isinstance(item, ImportFromDirective):
            continue
        try:
            resolved = _resolve_import_path(item.module)
        except Exception:  # noqa: BLE001
            resolved = item.module
        names = _rendered_import_names(item.names)
        if names is None:
            continue
        out.append((item.module, resolved, names))
    return out


def _import_remedy(name, export, path, label):
    """The ``->`` block: extend the existing import, or write a new one.

    Which of the two it is matters.  The reported failure had
    ``-import_from(…citations, [reg_y_art_9])`` already in the file, so "add
    ``-import_from(…citations, [cite])``" would have told the author to write a
    second directive for a module they were already importing from.  Quoting
    their own list back with one name added is unambiguous.
    """
    for declared, resolved, names in _import_from_directives(path):
        if export.module not in (declared, resolved):
            continue
        if name in names:
            # Already imported from the very module that exports it, and still
            # undefined — so whatever went wrong, it is not a missing import.
            # Falling through to the "write a new directive" form below would
            # advise a duplicate of a directive the file already has.  Say
            # nothing: the sentence above still names the exporter, which is
            # the decidable part.
            return []
        extended = ", ".join([*names, name])
        return _arrow([f"add `{name}` to this file's existing import:"]) + [
            f"{_INDENT}    -import_from({declared}, [{extended}])"
        ]
    return _arrow([f"add the import to {label}:"]) + [
        f"{_INDENT}    -import_from({export.module}, [{name}])"
    ]


def _undefined_name_lines(name, modname, path):
    """The hint block for an undefined *name*, or ``[]`` when there is none.

    ``[]`` is the whole no-misattribution rule: unless a sibling in the same
    directory declares the name in its ``-module(...)`` list, this says nothing
    and the stock message stands.
    """
    if not name or not isinstance(path, str) or not path.endswith(_SOURCE_SUFFIXES):
        return []
    export = _exporting_sibling(name, path, modname)
    if export is None:
        return []
    label = _module_label(modname, path)
    lines = _sentence(f"`{name}` is neither defined nor imported in {label}.")
    lines.extend(_sentence(f"{export.rendered} IS exported by a sibling module "
                           f"in the same package:"))
    lines.append(f"{_INDENT}    {export.module}")
    lines.extend(_import_remedy(name, export, path, label))
    return lines


class UndefinedNameError(NameError):
    """``NameError`` that also names the sibling module exporting the name.

    ``args`` is CPython's own, byte for byte, and the hint is rendered in
    ``__str__`` alone — the same discipline as the ``is``/``==`` note in
    ``clausal.logic.exceptions``.  A ``catch/3`` that swallows this converts it
    with ``python_error_term``, which reads ``str(exc)``… so the guarantee that
    matters here is the weaker, sufficient one: ``args`` and ``repr`` stay
    clean, and the class stays inside ``NameError`` so every existing handler
    keeps working.

    The hint lines are computed once, by the caller that decided this class was
    warranted, and handed in.  ``enrich_undefined_name`` has to compute them
    anyway to decide whether there is anything worth saying, so recomputing
    here would scan the package directory a second time — and again on every
    later render, of which there is at least one more whenever ``catch/3``
    converts the exception through ``python_error_term``.  ``__str__`` still
    computes them when it was handed none, so an instance built directly is not
    silently hintless.
    """

    def __init__(self, *args, name=None, module_name=None, module_file=None,
                 hint_lines=None):
        super().__init__(*args, name=name)
        self.module_name = module_name
        self.module_file = module_file
        self.hint_lines = hint_lines

    def __str__(self):  # noqa: D105
        message = super().__str__()
        extra = self.hint_lines
        if extra is None:
            try:
                extra = _undefined_name_lines(self.name, self.module_name,
                                              self.module_file)
            except Exception:  # noqa: BLE001 - a hint may not out-fail its error
                return message
        return "\n".join([message, *extra]) if extra else message


def _clausal_frame_of(exc):
    """``(module name, file)`` of the innermost Clausal frame in *exc*'s
    traceback, or ``(None, None)``.

    Compiled predicates carry their defining module's ``__name__`` and
    ``__file__`` in their globals, so the frame that raised is enough to say
    *which* module used the name — no caller has to pass it in, which is what
    lets one helper serve both the load-time and the solve-time seam.

    Innermost first, and only a ``.clausal``/``.pl`` frame counts: a NameError
    from ordinary Python code sitting in the same package must not be
    attributed to a Clausal module further up the stack.
    """
    frames = []
    tb = exc.__traceback__
    while tb is not None:
        frames.append(tb.tb_frame)
        tb = tb.tb_next
    for frame in reversed(frames):
        try:
            namespace = frame.f_globals
            path = namespace.get("__file__")
            modname = namespace.get("__name__")
        except Exception:  # noqa: BLE001
            continue
        if isinstance(path, str) and path.endswith(_SOURCE_SUFFIXES):
            return (modname if isinstance(modname, str) else None), path
    return None, None


def enrich_undefined_name(exc):
    """A replacement for *exc* that names the exporting sibling, or ``None``.

    ``None`` means "there is nothing decidable to add" and the seam re-raises
    the original untouched.  Never raises: a diagnostic that fails must not
    replace one failure with a different one.
    """
    if isinstance(exc, UndefinedNameError):
        return None
    try:
        name = getattr(exc, "name", None)
        if not isinstance(name, str) or not name:
            return None
        modname, path = _clausal_frame_of(exc)
        if path is None:
            return None
        lines = _undefined_name_lines(name, modname, path)
        if not lines:
            return None
        return UndefinedNameError(*exc.args, name=name, module_name=modname,
                                  module_file=path, hint_lines=lines)
    except Exception:  # noqa: BLE001 - see docstring
        return None
