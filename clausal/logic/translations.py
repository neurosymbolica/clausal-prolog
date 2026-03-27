"""clausal.logic.translations — bidirectional translation registry for predicate/atom names.

Stores mappings between English predicate/atom names and their translations
in other languages.  Registered via the ``-translations(lang, {...})`` directive
and queried by the ``translate/3`` builtin and ``term_str(locale=...)`` display.

The registry is a module-level singleton (like ``_BUILTINS`` in builtins._registry).
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class TranslatedEntry:
    """One predicate translation: English functor ↔ translated functor + arg map."""

    english_functor: str
    translated_functor: str
    arity: int
    arg_map: dict[str, str] = field(default_factory=dict)          # eng_arg → trans_arg
    reverse_arg_map: dict[str, str] = field(default_factory=dict)  # trans_arg → eng_arg


# ── Global registry ───────────────────────────────────────────────────────────

# Forward predicate lookup: (lang, english_functor, arity) → TranslatedEntry
_PREDICATES: dict[tuple[str, str, int], TranslatedEntry] = {}

# Reverse predicate lookup: (lang, translated_functor, arity) → TranslatedEntry
_REVERSE_PREDICATES: dict[tuple[str, str, int], TranslatedEntry] = {}

# Forward atom lookup: (lang, english_atom) → translated_atom
_ATOMS: dict[tuple[str, str], str] = {}

# Reverse atom lookup: (lang, translated_atom) → english_atom
_REVERSE_ATOMS: dict[tuple[str, str], str] = {}


# ── Registration ──────────────────────────────────────────────────────────────

def register_predicate(
    lang: str,
    english_functor: str,
    translated_functor: str,
    arity: int,
    arg_map: dict[str, str] | None = None,
) -> None:
    """Register a predicate name translation.

    *arg_map* maps English argument names to translated argument names.
    The reverse map is computed automatically.
    """
    if arg_map is None:
        arg_map = {}
    reverse_arg_map = {v: k for k, v in arg_map.items()}
    entry = TranslatedEntry(
        english_functor=english_functor,
        translated_functor=translated_functor,
        arity=arity,
        arg_map=arg_map,
        reverse_arg_map=reverse_arg_map,
    )
    _PREDICATES[(lang, english_functor, arity)] = entry
    _REVERSE_PREDICATES[(lang, translated_functor, arity)] = entry


def register_atom(lang: str, english_atom: str, translated_atom: str) -> None:
    """Register an atom translation (bidirectional)."""
    _ATOMS[(lang, english_atom)] = translated_atom
    _REVERSE_ATOMS[(lang, translated_atom)] = english_atom


# ── Lookup ────────────────────────────────────────────────────────────────────

def translate_predicate(
    lang: str, english_functor: str, arity: int,
) -> TranslatedEntry | None:
    """Forward lookup: English → translated.  Returns None if not registered."""
    return _PREDICATES.get((lang, english_functor, arity))


def reverse_translate_predicate(
    lang: str, translated_functor: str, arity: int,
) -> TranslatedEntry | None:
    """reverse lookup: translated → English.  Returns None if not registered."""
    return _REVERSE_PREDICATES.get((lang, translated_functor, arity))


def translate_atom(lang: str, english_atom: str) -> str | None:
    """Forward atom lookup.  Returns None if not registered."""
    return _ATOMS.get((lang, english_atom))


def reverse_translate_atom(lang: str, translated_atom: str) -> str | None:
    """reverse atom lookup.  Returns None if not registered."""
    return _REVERSE_ATOMS.get((lang, translated_atom))


# ── Introspection ─────────────────────────────────────────────────────────────

def get_all_predicates(lang: str) -> list[TranslatedEntry]:
    """Return all predicate translations for *lang*."""
    return [e for (l, _, _), e in _PREDICATES.items() if l == lang]


def get_all_atoms(lang: str) -> dict[str, str]:
    """Return all atom translations for *lang* as {english: translated}."""
    return {ea: ta for (l, ea), ta in _ATOMS.items() if l == lang}


def get_languages() -> set[str]:
    """Return the set of all registered language codes."""
    langs: set[str] = set()
    for l, _, _ in _PREDICATES:
        langs.add(l)
    for l, _ in _ATOMS:
        langs.add(l)
    return langs


# ── Test helper ───────────────────────────────────────────────────────────────

def _clear() -> None:
    """Clear all registrations.  For use in tests only."""
    _PREDICATES.clear()
    _REVERSE_PREDICATES.clear()
    _ATOMS.clear()
    _REVERSE_ATOMS.clear()
