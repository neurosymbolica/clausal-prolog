"""translate/3 builtin — produce a locale-aware string representation of a term.

Translations are a display/surface layer only.  ``translate/3`` does NOT
create new term structures; it renders the term as a string with functor
and atom names replaced per the translation table.
"""

from __future__ import annotations

from clausal.logic.cells import chars  # stage 1: the chars carrier
from clausal.logic.variables import deref, is_var, unify
from clausal.logic.builtins._registry import _builtin
from clausal.terms import term_str, TermStyle


@_builtin("translate", 3)
def _translate__3(lang, term, translated_string, trail, k):
    """translate(Lang, Term, String) — render *Term* as a string in *Lang*.

    *Lang* must be ground: the ATOM naming the target language (a plain
    ``str`` is a STRING and raises ``type_error(atom, …)`` — spec §6.4).
    *Term* must be ground (or partially ground — variables render as ``_``).
    *String* is unified with the resulting translated string.
    """
    lang_val = deref(lang)
    term_val = deref(term)

    if is_var(lang_val):
        return  # language must be ground

    # THE FLIP (spec §6.4): *Lang* is an ATOM read by SPELLING.  Task 12
    # deleted the Stage A arm that also took a plain ``str`` as the locale
    # name: a ``str`` is a STRING now, and a string in a name position is
    # ``type_error(atom, …)``, the same refusal ``signature/3`` and the chars
    # family give.  A legacy zero-field atom CLASS is still read by
    # ``__name__`` (spec §4); anything else falls back to ``str()``, which is
    # only reached for a shape that names no locale anyway.
    from clausal.logic.atoms import is_atom as _term_is_atom, spelling
    if _term_is_atom(lang_val):
        lang_str = spelling(lang_val)
    elif isinstance(lang_val, str):
        from clausal.logic.exceptions import LogicException, type_error
        raise LogicException(type_error("atom", lang_val, "translate/3"))
    elif hasattr(lang_val, "__name__"):
        lang_str = lang_val.__name__
    else:
        lang_str = str(lang_val)

    style = TermStyle(locale=lang_str)
    result = term_str(term_val, style)

    mark = trail.mark()
    if unify(translated_string, chars(result), trail):   # stage 1
        yield None
    trail.undo(mark)
