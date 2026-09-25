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


class ClausalKeywordArgumentWarning(ClausalLintWarning):
    """A term written with KEYWORD arguments (``point(x=1, y=2)``).

    A term is built positionally.  The keyword spelling is Python's
    keyword-call syntax borrowed as a term form: it has no ISO Prolog
    reading, it made a functor's field NAMES depend on which clause of it
    came first (the first head's keywords became the signature), and it is
    the last surface producer of ``KWTerm`` -- a third term representation
    beside the cell and the class instance.  Refused as of 2026-09-19 by
    ``EmbedTransformer._lint_keyword_argument``; the machinery behind it is
    deleted with the class in P4.

    Two keyword spellings are NOT this warning: a ``-directive``'s options
    (``-specialize(solve, p, alias=q)``), which are options of the directive
    rather than arguments of a term, and an EDCG hidden argument
    (``p(L, _edcg_counter_in=0)``), which is ``_``-led by construction and
    addresses a GENERATED argument rather than declaring a field name.
    Hosted Python in the same file, and anything inside a ``++`` escape, is
    never read.  The severity is ``KEYWORD_ARGUMENT_SEVERITY`` (``"error"``:
    the same sites raise a load-time ``SyntaxError``; set it to ``"warn"``
    and this warning is emitted instead).
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


class ClausalScaleInNameWarning(ClausalLintWarning):
    """A name that claims a SCALE carrying a bare number.

    ``minimum_leverage_bps(300)`` says "basis points" in the identifier and
    nothing anywhere the engine can read. The number is then a bare integer:
    it adds to another currency's integer without complaint, and it compares
    against a threshold in a different scale to give not a wrong number but a
    **reversed answer** -- measured, ``155000 > 1550`` is True while the same
    amounts as money are ``1550.00 > 1550``, which is False.

    Declaring the amount (``-constant_number_currency`` /
    ``-constant_number_units``) moves the scale to where the engine can check
    it, and the declared pair stays recoverable through
    ``constant_number_units/3``. So this lint is a migration worklist, not a
    permanent complaint: a converted site carries a quantity rather than a
    bare literal and goes quiet.

    Emitted once per (file, identifier), as the TitleCase lint is -- 139
    corpus sites warning once each is a worklist; warning per occurrence is
    noise.
    """


class ClausalShadowedVariableWarning(ClausalLintWarning):
    """A Python local whose name is ALL_CAPS, read inside a seam as a logic
    VARIABLE rather than as the local.

    The corpus convention is ALL_CAPS for exactly these locals (``P``, ``D``,
    ``S``, ``C``, ``R``), and the two readings look identical in the source:

        P = 2
        for V in --pair(++P, V): ...        # P is a fresh VARIABLE, not 2

    ``++`` does not rescue it — the name is decided to be a variable before
    the escape is considered — so the goal is silently LESS CONSTRAINED than
    it reads, and it answers every row instead of one.  There is no error and
    no exception; the wrong answer simply comes back.

    THE SIGNAL IS THE CONJUNCTION, and both halves are needed: an ALL_CAPS
    name in a goal is an ordinary logic variable, and an ALL_CAPS Python local
    is ordinary Python.  Only a name that is BOTH is likely a mistake.

    A WARNING, NOT A REFUSAL: the construct is legal, an author may mean the
    variable, and refusing would make the lint unlandable in the middle of a
    migration that is exactly when it is most useful.
    """


class ClausalBooleanSeamWarning(ClausalLintWarning):
    """A ``--goal`` read as a BOOLEAN outside goal position.

    ``--g`` runs the goal only in goal position: the test of ``if`` /
    ``elif`` / ``while`` (also under ``not``), a ``for`` iterable, and a
    comprehension's first iterable.  Everywhere else it builds the CELL, a
    non-empty tuple, and a tuple is always true.  So

        assert --edge(zzz, X)        # passes, whatever edge/2 holds
        ok = --g and ready           # ok is ready, the goal never ran
        x = a if --g else b          # always a

    never test the goal, and nothing raises.  Emitted at load, once per site
    (the message names the file and line), for a ``--`` that is the direct
    operand of ``assert``, ``and``/``or``, a conditional expression's test,
    ``bool(...)``, ``not`` (outside an ``if``/``while`` test), or a
    comprehension's ``if`` filter.  A cell assigned, passed or returned as
    DATA is not this warning.
    """

