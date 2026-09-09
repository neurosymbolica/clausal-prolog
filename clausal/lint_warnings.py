"""Warning classes for Clausal's load-time lints.

Kept in a module with no imports so that a layer which only needs to *raise*
one of these — ``clausal.modules.units`` warning about a deprecated unit
spelling from plain Python — does not pull the seam rewriter
(``clausal.templating.term_rewriting``) in to do it.  The rewriter re-exports
them, so ``from clausal.templating.term_rewriting import ClausalLintWarning``
keeps working.
"""


class ClausalLintWarning(UserWarning):
    """Load-time lint diagnostic for a likely-footgun Clausal construct."""


class ClausalSingletonWarning(ClausalLintWarning):
    """A named logic variable occurring exactly once in its clause.

    Suppress per-variable with the ``_UNUSED`` suffix, per-file with
    ``-allow_singletons``. The suffix is the sole canonical spelling —
    case-based exemptions are blind for caseless scripts, which the
    ``isupper()`` rule forces into leading-underscore variables.
    """


class ClausalSeamLiteralWarning(ClausalLintWarning):
    """A ``"..."`` literal inside a ``--`` seam in a module that never said
    which meaning it wants.  Under the engine default ``-double_quotes(atom)``
    the literal is an ATOM; a Python author reads it as a string.  The
    silent version of that mistake is a term that unifies with nothing, so
    the seam says so once and points at the directive."""


class ClausalDeprecatedSpellingWarning(ClausalLintWarning):
    """A construct written with a superseded surface spelling.

    Not a ``DeprecationWarning``: those are silenced by default outside
    ``__main__``, and a load-time lint that nobody sees is the silent alias
    this warning exists to avoid.  Suppress it the way the other lints are
    suppressed — ``warnings.filterwarnings`` on this class.
    """
