"""Translate/3 builtin — produce a locale-aware string representation of a term.

Translations are a display/surface layer only.  ``Translate/3`` does NOT
create new term structures; it renders the term as a string with functor
and atom names replaced per the translation table.
"""

from __future__ import annotations

from clausal.logic.variables import deref, is_var, unify
from clausal.logic.builtins._registry import _builtin
from clausal.terms import term_str, TermStyle


@_builtin("Translate", 3)
def _translate__3(lang, term, translated_string, trail, k):
    """Translate(Lang, Term, String) — render *Term* as a string in *Lang*.

    *Lang* must be ground (an atom or string naming the target language).
    *Term* must be ground (or partially ground — variables render as ``_``).
    *String* is unified with the resulting translated string.
    """
    lang_val = deref(lang)
    term_val = deref(term)

    if is_var(lang_val):
        return  # language must be ground

    # Accept both atom classes (PredicateMeta with __name__) and plain strings.
    lang_str = (
        lang_val if isinstance(lang_val, str)
        else lang_val.__name__ if hasattr(lang_val, "__name__")
        else str(lang_val)
    )

    style = TermStyle(locale=lang_str)
    result = term_str(term_val, style)

    mark = trail.mark()
    if unify(translated_string, result, trail):
        yield None
    trail.undo(mark)
