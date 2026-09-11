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


class ClausalTitleCaseIdentifierWarning(ClausalLintWarning):
    """A TitleCase identifier (``Foo``, ``FooBar``) in Clausal code.

    Clausal identifiers are lowercase (predicates, atoms, functors) or
    ALL_CAPS / underscore-led (logic variables); TitleCase has no role — a
    Python class is reached as ``++ClassName``.  Emitted once per (file,
    identifier) by ``EmbedTransformer._lint_titlecase``, which reads only
    CLAUSAL positions — clause heads and bodies, bodyless facts, directive
    arguments and ``--`` seams.  Hosted Python in the same file (module-level
    assignments, imports, ``def``/``class`` bodies, plain calls) is where a
    TitleCase class belongs and where ``++`` is Python's double unary plus,
    so it is never read.  The severity is ``TITLECASE_IDENTIFIER_SEVERITY``
    (``"error"``: the same sites raise a load-time ``SyntaxError``; set it
    to ``"warn"`` and this warning is emitted instead).
    """


class ClausalCurrencyLiteralWarning(ClausalLintWarning):
    """A money amount written as a float literal carrying enough significant
    digits that the literal may already have been rounded.

    There is no decimal literal syntax, so ``155000.99`` is a Python float
    before any currency code sees it. Measured on this code path: a decimal
    with **15 or fewer significant digits always survives** the
    ``float -> Decimal(str(f))`` round trip; 16 digits loses about 12% of
    amounts, 17 about 83%, 18 about 98%. So the band is a HAZARD and not a
    certainty -- roughly one 17-digit amount in six is still intact -- which
    is why this says the amount *may* not be the one written. What was
    written is unrecoverable by then, but the band is knowable, and saying so
    is the difference between a loud problem and a silent wrong amount.

    Money only. A physical measurement makes no exact-decimal claim, and
    warning there would fire on every float in the corpus.
    """
