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


class ClausalCrossModeLiteralWarning(ClausalLintWarning):
    """A ``"..."`` literal inside a goal-position ``--`` seam that targets a
    module whose ``-double_quotes`` mode differs from the host file's.

    A seam literal takes the HOST file's mode (``visit_Constant``), not the
    target's.  So a chars-mode host calling ``--p("x")`` into an atom-mode
    module sends the STRING ``"x"`` to clauses written against the ATOM
    ``x``: the goal compares a string with an atom, never matches, and
    nothing raises.  Fired at load, where the target is statically known
    (an ``-import_from``'d predicate or ``--m.pred(...)`` over an
    ``-import_module``'d base); a base bound at run time is the documented
    gap -- see ``compiler_v2._lint_cross_mode_literals``."""


class ClausalDeprecatedSpellingWarning(ClausalLintWarning):
    """A construct written with a superseded surface spelling.

    Not a ``DeprecationWarning``: those are silenced by default outside
    ``__main__``, and a load-time lint that nobody sees is the silent alias
    this warning exists to avoid.  Suppress it the way the other lints are
    suppressed — ``warnings.filterwarnings`` on this class.
    """


class ClausalBareAtomImportWarning(ClausalDeprecatedSpellingWarning):
    """A bare atom in a ``.pl`` ``use_module/2`` import list (``[cite,
    p/1]``; not ISO).  Accepted during the transition and COUNTED: one
    warning per file gives the number of such entries and their names.  An
    atom is global by spelling, so the entry imports nothing."""


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
    came first (the first head's keywords became the signature), and it was
    the last surface producer of a keyword-term class -- a third term
    representation beside the cell and the class instance, since deleted with
    its machinery.  Refused as of 2026-09-19 by
    ``EmbedTransformer._lint_keyword_argument``.

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
    warning there would fire on every float in downstream code.
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

    The usual convention is ALL_CAPS for exactly these locals (``P``, ``D``,
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



class ClausalAtomExportDefinedAsPredicateWarning(ClausalLintWarning):
    """A bare name exported as an ATOM (``-module(m, [..., foo, ...])``) that
    the same module also makes a PREDICATE, at any arity: clauses (``foo,``,
    ``foo <- ...``, ``foo(1),``), a clause-free ``-dynamic``/``-table``/
    ``-discontiguous``/``-shallow``, or a ``-specialize`` alias.

    ISO allows the atom ``foo`` and the predicate ``foo/0`` together, so this
    is a WARNING, not a refusal (operator ruling 2026-09-26).  The harm is at
    the binding, which is by NAME: once ``foo`` is a predicate at any arity,
    the module attribute ``foo`` --
    in the module and in every importer -- is the predicate's HANDLE, not the
    atom ``'foo'``, so data keyed by the atom that reaches it through
    ``module.foo`` silently stops matching.  Emitted at load, once per
    (module, name).  Remedies: drop the predicate's definition if it is only
    there "for conformance", or rename one of the two; to export the
    predicate, write ``foo/N`` in the export list instead of ``foo``.
    """


class ClausalExportArityMismatchWarning(ClausalLintWarning):
    """An ISO ``name/N`` entry in a ``-module``/``-private`` list names an
    arity the module does nothing with, while the module DOES define
    ``name`` at some other arity: ``-module(m, [base/9])`` over ``base/2``
    clauses.  Almost always a typo in the export entry.

    Not an error (operator ruling 2026-09-29): a ``name/N`` entry for a
    predicate with no clauses here is legal -- it declares a procedure
    whose clauses may come from elsewhere, and calling it with none raises
    ``existence_error`` -- so the export stays, and the warning only fires
    when other-arity clauses make the typo likely.  Silent when ``name/N``
    has clauses here, or a ``-dynamic``/``-table``/``-discontiguous``/
    ``-shallow``/``-meta_predicate`` declaration, or a field-carrying
    export entry at arity N, and silent when ``name`` has no clauses at
    any arity.  Emitted at load, once per export entry, naming the file
    and line of the entry.  Remedy: correct the arity in the entry, or
    declare ``name/N`` (e.g. ``-dynamic``) if it really is a different
    procedure.
    """


class ClausalRetiredQuasiQuoteWarning(ClausalDeprecatedSpellingWarning):
    """``q(...)`` inside a ``term_expansion/4`` clause.

    ``q(expr)`` was a quasi-quotation that stripped itself; it was retired
    2026-09-25 and ``q`` is now an ordinary name.  So an old rule such as
    ``term_expansion(q(fact(X)), [q(fact(X)), q(logged(X))], S, S)`` now
    builds ``('q', ...)`` cells and silently matches nothing -- the module
    loads with the expansion missing.  Write the pattern as a plain term, as
    in ISO ``term_expansion``: ``term_expansion(fact(X), [fact(X),
    logged(X)], S, S)``.  Read only in a clause that has a
    ``term_expansion(_, _, _, _)`` in it, or a clause of a predicate its body
    reaches in the same file; never a ``q(...)`` that is itself a body goal,
    or one inside a ``++`` Python escape.  Once per clause; a rule that means
    a real ``q/1`` term can silence it with ``warnings.filterwarnings`` on
    this class.
    """


class ClausalAtomClassDeprecationWarning(ClausalLintWarning):
    """Constructing the boundary class ``clausal.logic.atoms.atom`` (a ``str``
    subclass).  Deprecated 2026-09-27 (dumb seam, step (f)); removed in 2.0.

    Under the dumb seam an atom IS the plain ``str`` and nothing the engine
    hands out is an ``atom`` instance any more, so the class only ever comes
    from user code.  Write ``'x'`` for the atom ``x``; test with
    ``type(v) is str`` or ``clausal.logic.atoms.is_atom(v)`` -- an
    ``isinstance(v, atom)`` test is now simply False for every answer.

    VISIBLE BY DEFAULT (operator ruling 2026-09-27): a ``UserWarning``
    through ``ClausalLintWarning``, the same base as
    ``ClausalDeprecatedSpellingWarning`` and for the same reason -- a
    ``DeprecationWarning`` is silenced by default outside ``__main__``, and
    a deprecation nobody sees is no notice at all.  Suppress it the way the
    other lints are suppressed: ``warnings.filterwarnings`` on this class.
    Emitted
    once per CALL SITE (file, line), guarded in ``clausal.logic.atoms`` rather
    than by the warnings registry.  The engine's own leak strips test the
    type and never construct, so they never emit it.  Not the builtin
    ``atom/1`` (``from clausal import atom``), which is unaffected.
    """


class ClausalSeamTextCompareWarning(ClausalLintWarning):
    """A name bound by a goal-position ``--`` seam compared with a Python
    ``str`` LITERAL in the same function.

    Under the dumb seam (2026-09-26) a goal-position answer is the engine's
    own term: a string is the carrier ``('$chars', s)`` and an atom is the
    plain ``str``.  So in hosted Python

        for T in --txt(T):
            if T == "some text":       # False for a STRING answer ...
        for X in --colour(X):
            if X == "red":             # ... and True for an ATOM answer

    the same spelling silently answers differently by the answer's type,
    which is the trap.  The right spellings are a seam literal on the other
    side (``T == --"some text"``) or the converter (``to_python(T) ==
    "some text"``).  Emitted at load, once per site (the message names the
    file, line and column, the name, the seam that bound it and both
    spellings), for a seam-bound name -- from ``if``/``elif``/``while``, a
    ``for``, a comprehension's first clause, or a plain alias of one
    (``y = T``) -- that meets a str literal through ``==``, ``!=``, ``in`` /
    ``not in`` a literal list/tuple/set of str, or a ``match``/``case`` str
    pattern.

    NOT CAUGHT, by design (same function, literal on the other side):
    ``d[T]`` and ``T in some_dict`` (a str key never joins a carrier key),
    ``json.dumps(T)``, ``len(T)``, ``T[0]``, str methods and ``+``, a
    comparison inside a helper the name is passed to, a comparison in
    another function, a container built at runtime (``T in NAMES``), and a
    name rebound by plain Python after the seam (still flagged).  Those are
    the seam's documented raw-out contract (docs/python_integration.md).
    """



class ClausalStringInCatchPatternWarning(ClausalLintWarning):
    """A double-quoted ``"..."`` literal naming the type, domain, kind or
    action of an ISO error inside a catch pattern, read as a STRING under
    this file's ``-double_quotes(chars)`` mode (the default).

    The engine's own error terms carry ATOMS there (``domain_error(date,
    X)``), and a string never unifies with an atom, so

        catch(G, error(domain_error("date", _), _), R)

    never catches the error it names: the error propagates past the catch.
    Write the atom, ``'date'`` (an atom in every mode).

    Judged for the catcher argument of ``catch/3``, ``catch_recover/3`` and
    ``catch_error/2``, at the DESCRIPTOR positions of the ISO formals inside
    ``error(Formal, _)``: the first argument of ``type_error/2``,
    ``domain_error/2``, ``existence_error/2``, ``representation_error/1``,
    ``evaluation_error/1``, ``resource_error/1`` and ``syntax_error/1``, and
    the first two of ``permission_error/3``.  The CULPRIT (the last argument
    of the /2 and /3 forms) is the offending term itself and may be a
    string, so ``error(type_error(atom, "hello"), _)`` is not flagged.  Not
    emitted under ``-double_quotes(atom)``, where ``"date"`` already IS the
    atom.  Suppress it with ``warnings.filterwarnings`` on this class.
    """


class ClausalImportedDataNameWarning(ClausalLintWarning):
    """A seam ``-import_from(M, [name])`` of a ``.pl`` module M resolved
    ``name`` to the ATOM ``name`` (M neither defines it as a predicate nor
    binds it; data needs no declaration) while ``name`` sits within a small
    edit distance of a predicate M does define -- a likely misspelled
    predicate import.  Emitted once per (importer, M, name)."""


class ClausalPyRandomDeprecationWarning(ClausalLintWarning):
    """A predicate of ``py.random`` (``library(py_random)``) was called.
    Deprecated 2026-10-07 (operator ruling): it draws from a process-global
    generator seeded from OS entropy, so its answers are not reproducible
    and do not follow backtracking.  Use the pure, state-threaded
    ``pure_random`` library (``library(pure_random)``) instead: the
    generator state is the term ``rng(Seed, N)`` and every draw is a
    relation ``S0 -> S``.  ``py.random`` keeps working until it is removed.

    VISIBLE BY DEFAULT, like ``ClausalAtomClassDeprecationWarning`` and for
    the same reason (a ``DeprecationWarning`` is silenced outside
    ``__main__``).  Emitted ONCE PER PROCESS, on the first call of any
    ``py.random`` predicate, guarded in ``clausal.modules.py.random`` rather
    than by the warnings registry.  Suppress it with
    ``warnings.filterwarnings`` on this class.
    """
