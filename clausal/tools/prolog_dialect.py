"""Dialect-specific configuration for Prolog emission/parsing."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from clausal.tools.prolog_operators import OperatorTable


@dataclass
class Dialect:
    """Dialect-specific configuration for Prolog emission/parsing."""
    name: str                                  # "iso", "swi", "scryer"
    operator_table: OperatorTable = field(repr=False)
    library_map: dict[str, str] = field(default_factory=dict)
    clpfd_module: str = "clpz"                 # Scryer/Trealla; swi() overrides "clpfd"
    #: Does emitting a CLP arithmetic goal (`#=`) require importing
    #: :attr:`clpfd_module`, or is the solver built in? GNU Prolog's FD system
    #: is built in and has no `library(fd)` to import; everywhere else the file
    #: does not consult at all without the import.
    clpfd_needs_import: bool = True
    tabling_directive: str = ":- table"
    string_type: str = "string"
    has_dicts: bool = False
    module_system: str = "iso"
    #: How a `-constant_*` declaration can cross. "none" = refuse (the system
    #: cannot receive it); "facts" = emit a fact with the module filled in BY
    #: THE EXPORTER, which knows it statically (for systems without
    #: `prolog_load_context/2`, which is not ISO); "expansion" = emit the
    #: directive for a term_expansion prelude to expand on load. Verified
    #: 2026-09-13: Scryer and Trealla both have prolog_load_context/2, both
    #: report the real module inside `:- module(m, ...)`, and a hook fires and
    #: sees it. See docs/superpowers/specs/2026-09-13-exporter-option-3-design.md
    constants: str = "facts"
    #: For an `expansion` dialect: (load_directive, prelude_module) naming the
    #: term_expansion prelude the emitted file must pull in. None where no
    #: prelude is needed (`facts`) or possible (`none`).
    #:
    #: The DIRECTIVE differs per system and is not cosmetic (measured
    #: 2026-09-13): Scryer takes `use_module` and rejects `ensure_loaded/1` as a
    #: directive; Trealla's prelude must be module-LESS and loaded with
    #: `ensure_loaded`, because its `prolog_load_context(module, M)` inside a
    #: `user:term_expansion` clause reports the module the HOOK is defined in,
    #: so a named prelude module attributes every file to the prelude.
    constants_prelude: tuple | None = None
    #: How an exact decimal magnitude is represented in a constant
    #: DECLARATION. "float" writes `1550.00`, which every system reads as a
    #: float and prints as `1550.0` -- the magnitude survives, the SCALE does
    #: not, because Prolog has no decimal type. "rational" writes the
    #: unevaluated term `1_550_00/100`, which is plain ISO syntax (a compound,
    #: not arithmetic) and keeps both halves, so the scale is recoverable.
    #:
    #: Measured 2026-09-13 in Scryer and Trealla: `155000/100` as a TERM is
    #: preserved exactly in both; `is 155000/100` evaluates to 1550.0 and
    #: `155000 rdiv 100` normalises to 1550, so neither evaluated form helps.
    #: SICStus's infix `r/2` (`155000r100`) is a third option, NOT implemented
    #: because there is no SICStus here to verify it against -- and `3r2` is a
    #: syntax error in both systems that are here.
    #:
    #: Applies to the DECLARATION only. At a use site `F > 155000/100` is
    #: evaluated back to a float, so the rational buys nothing there and
    #: complicates the arithmetic; the declaration is the fidelity channel.
    #:
    #: Default "float" keeps existing output byte-identical -- adopting
    #: "rational" for the roster is a deliberate change that needs its own
    #: export-bytes measurement.
    decimal_repr: str = "float"

    @classmethod
    def iso(cls) -> Dialect:
        return cls(
            name="iso",
            operator_table=OperatorTable.iso_default(),
            # `#=` is not ISO -- the operator table correctly does not carry
            # it, and this dialect emits one only under the 2026-09-18 ruling,
            # as a deliberate exception. When it does, the engines that run
            # this output are Scryer and Trealla, and BOTH spell the library
            # `clpz`. "clpfd" is the SWI name and would not resolve in either.
            clpfd_module="clpz",
        )

    @classmethod
    def swi(cls) -> Dialect:
        return cls(
            name="swi",
            operator_table=OperatorTable.swi_default(),
            library_map={
                "clausal.logic.clpfd": "library(clpfd)",
                "clausal.logic.clpb": "library(clpb)",
                "clausal.logic.tabling": "library(tabling)",
            },
            clpfd_module="clpfd",
            tabling_directive=":- table",
            string_type="string",
            has_dicts=True,
            module_system="swi",
            constants="expansion",
            # UNTESTED: no swipl on this machine. SWI has
            # prolog_load_context/2, so the Scryer-shaped prelude is the
            # likely fit, but nobody has run it.
            constants_prelude=("use_module", "clausal_constants_scryer"),
        )

    @classmethod
    def scryer_reader(cls) -> Dialect:
        """The dialect the ``.pl`` TRANSLATOR reads with by default (ruling
        R11, 2026-09-28): Scryer's operator table -- ISO Table 7 plus
        Scryer's own defaults (``+`` fy 200, ``div`` and ``rdiv`` yfx 400),
        exactly what Scryer's toplevel reports with no library loaded
        (``OperatorTable.scryer_builtin_default``).  It replaced SWI's table,
        whose extra operators (``:- dynamic foo/1`` prefix forms, ``*->``,
        ``=@=``, ``xor``, dict ``:<``) are not ISO and Scryer refuses them
        too.  A file that needs one declares it with ``:- op/3``, as it
        would for Scryer; ``Dialect.swi()`` is still there to pass
        explicitly."""
        d = cls.scryer()
        d.operator_table = OperatorTable.scryer_builtin_default()
        return d

    @classmethod
    def scryer(cls) -> Dialect:
        return cls(
            name="scryer",
            operator_table=OperatorTable.scryer_default(),
            library_map={
                "clausal.logic.clpfd": "library(clpz)",
                "clausal.logic.clpb": "library(clpb)",
                "clausal.logic.tabling": "library(tabling)",
            },
            clpfd_module="clpz",
            tabling_directive=":- use_module(library(tabling))",
            string_type="chars",
            has_dicts=False,
            module_system="iso",
            constants="expansion",
            constants_prelude=("use_module", "clausal_constants_scryer"),
        )

    @classmethod
    def gprolog(cls) -> Dialect:
        return cls(
            name="gprolog",
            operator_table=OperatorTable.gprolog_default(),
            library_map={},  # FD constraints are built-in, no library imports
            clpfd_module="fd",
            # GNU Prolog's FD solver is built in; there is no library(fd).
            clpfd_needs_import=False,
            tabling_directive="",  # GNU Prolog has no tabling support
            string_type="atom",
            has_dicts=False,
            module_system="none",
            constants="none",
        )

    @classmethod
    def trealla(cls) -> Dialect:
        return cls(
            name="trealla",
            operator_table=OperatorTable.trealla_default(),
            library_map={
                "clausal.logic.clpfd": "library(clpz)",
                "clausal.logic.clpb": "library(clpb)",
            },
            clpfd_module="clpz",
            tabling_directive=":- use_module(library(tabling))",
            string_type="chars",
            has_dicts=False,
            module_system="iso",
            constants="expansion",
            constants_prelude=("ensure_loaded", "clausal_constants_trealla"),
        )


# ── Naming conventions ───────────────────────────────────────────────

def pascal_to_snake(name: str) -> str:
    """Convert PascalCase predicate names to Prolog snake_case.

    FooBar       -> foo_bar
    all_different -> all_different
    CLP          -> clp
    copy_term     -> copy_term
    DCGRule      -> dcg_rule
    IOStream     -> io_stream
    """
    s = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1_\2", name)
    s = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", s)
    return s.lower()


def snake_to_pascal(name: str) -> str:
    """Convert Prolog snake_case to clausal PascalCase.

    foo_bar       -> FooBar
    all_different -> all_different
    copy_term     -> copy_term
    """
    return "".join(word.capitalize() for word in name.split("_"))


def clausal_var_to_prolog(name: str) -> str:
    """Return *name* unchanged: Clausal and Prolog variables are spelled alike.

    A capital-initial identifier (``Foo``, ``FOO``, ``N0``, ``X``) names a
    logic variable in Clausal exactly as it does in ISO Prolog, and ``_x`` is
    a variable on both sides too, so there is nothing to translate.  ``_``
    stays ``_`` and stays anonymous.

    This used to titlecase and strip: ``_head`` -> ``Head``, ``RESULT`` ->
    ``Result``.  That rule was **non-injective** — ``_result`` and ``RESULT``
    both landed on ``Result`` — so two distinct variables in one clause
    silently merged, and a per-clause rename table existed only to number the
    loser (``Result2``).  Identity cannot collide, so the rename table went
    with it.  Kept as a function rather than inlined at its one call site
    because it is the documented name of the outbound convention and is
    exported (``clausal_to_prolog.__all__``); the pair with
    :func:`prolog_var_to_clausal` is what makes the round trip readable.
    """
    return name


def prolog_var_to_clausal(name: str) -> str:
    """Return *name* unchanged — the inverse of :func:`clausal_var_to_prolog`.

    Every ISO Prolog variable spelling (capital-initial, or ``_``-led) is
    already a Clausal variable spelling, so an inbound variable keeps its
    name and the round trip is lossless.

    This used to lowercase and prefix: ``Foo`` -> ``_foo``.  Like the
    outbound rule it was non-injective (``Foo`` and ``FOO`` both -> ``_foo``)
    and needed the same per-clause uniquifier behind it.

    Two ISO variable spellings have no Clausal variable spelling: ``_PI_``
    (the module-CONSTANT class) and ``__Foo`` (a dunder).  The old rule
    lowercased and stripped trailing underscores, which hid the first of them
    behind a rename.  Renaming is what made the mapping non-injective, so
    this function no longer does it — and the names are REFUSED instead, by
    ``prolog_to_clausal._checked_var_name``, with a message naming the Prolog
    variable.  Refusing is not renaming: the mapping stays injective.

    The check is deliberately not here.  A partial mapping function invites a
    caller to "fix" the input, which is how non-injectivity arrived the first
    time; the call site can refuse without offering that temptation.  See
    tests/test_prolog_to_clausal_var_names.py.
    """
    return name


# ── Builtin name mapping ────────────────────────────────────────────

# clausal name -> {dialect: prolog_name}
# "iso" is the fallback; dialect-specific entries override it.
BUILTIN_NAME_MAP: dict[str, dict[str, str]] = {
    "assertz":       {"iso": "assertz"},
    "asserta":       {"iso": "asserta"},
    "retract":       {"iso": "retract"},
    "findall":       {"iso": "findall"},
    "bagof":         {"iso": "bagof"},
    "setof":         {"iso": "setof"},
    "forall":        {"iso": "forall"},
    "copy_term":     {"iso": "copy_term"},
    "term_variables": {"iso": "term_variables"},
    "numbervars":    {"iso": "numbervars"},
    "all_different": {"iso": "all_distinct", "swi": "all_different", "scryer": "all_distinct",
                      "gprolog": "fd_all_different", "trealla": "all_distinct"},
    "in_domain":     {"swi": "ins", "scryer": "ins",
                      "gprolog": "fd_domain", "trealla": "ins"},
    "label":         {"iso": "label", "gprolog": "fd_labeling"},
    "labeling":      {"iso": "labeling", "gprolog": "fd_labeling"},
    "maplist":       {"iso": "maplist"},
    "writeln":       {"iso": "writeln"},
    "write":         {"iso": "write"},
    "nl":            {"iso": "nl"},
    "tab":           {"iso": "tab"},
    "call":          {"iso": "call"},
    "functor":       {"iso": "functor"},
    "arg":           {"iso": "arg"},
    "length":        {"iso": "length"},
    "member":        {"iso": "member"},
    # in_/2 is the PREDICATE spelling of membership and is member/2 -- the
    # engine registers the name exactly once, on _member__2 in
    # clausal/logic/builtins/lists.py. It used to sit in the CLP(FD) block
    # above (between all_different and in_domain) mapped to "in", i.e. read
    # as clpfd's ``X in 1..10`` domain constraint. That was wrong twice
    # over: no ISO engine defines in/2 without clpfd, so every downstream library
    # that spells membership as a call exported a program that died with
    # existence_error(procedure, in/2) on first use -- and under a dialect
    # that DOES load clpfd it would have resolved and silently meant a
    # finite-domain constraint instead of list membership, which is worse.
    # The negated call form needs nothing extra here: `not in_(X, L)` is
    # already emitted as `\+ <call>`, and Clausal's `not in` is negation as
    # failure rather than a dif-family constraint (MemberIn(negate=True) in
    # clausal/logic/compiler/_lower_goalop_shared.py undoes its trail mark
    # on both branches; on the live engine `X not in [1,2,3]` with X unbound
    # FAILS, where `X is not 1` succeeds with a residual). So `\+ member/2`
    # is faithful for both spellings and no not_in/2 companion is wanted.
    "in_":           {"iso": "member"},
    # "get" targets attribute-lists (Task 2's dict lowering); member/2 on a
    # dict-valued argument is not statically detectable and is left to gate G4.
    "get":           {"iso": "profile_get"},
    "append":        {"iso": "append"},
    "reverse":       {"iso": "reverse"},
    "last":          {"iso": "last"},
    "permutation":   {"iso": "permutation"},
    "between":       {"iso": "between"},
    "sort":          {"iso": "sort"},
    "msort":         {"iso": "msort"},
    "flatten":       {"iso": "flatten"},
    "select":        {"iso": "select"},
    "subtract":      {"iso": "subtract"},
    "intersection":  {"iso": "intersection"},
    "union":         {"iso": "union"},
    "list_to_set":   {"iso": "list_to_set"},
    "sum_list":      {"iso": "sum_list"},
    "max_list":      {"iso": "max_list"},
    "min_list":      {"iso": "min_list"},
    "numlist":       {"iso": "numlist"},
    "same_length":   {"iso": "same_length"},
    "in_check":      {"iso": "memberchk"},
    "list_item":     {"iso": "nth0"},
    "take":          {"iso": "take"},
    "drop":          {"iso": "drop"},
    "zip_":          {"iso": "zip"},
    "replicate":     {"iso": "replicate"},
    "var":           {"iso": "var"},
    "nonvar":        {"iso": "nonvar"},
    "number":        {"iso": "number"},
    "integer":       {"iso": "integer"},
    "float_":        {"iso": "float"},
    "atom":          {"iso": "atom"},
    "is_str":        {"iso": "atom"},
    "is_list":       {"iso": "is_list"},
    "ground":        {"iso": "ground"},
    "callable_":     {"iso": "callable"},
    "compound":      {"iso": "compound"},
    "is_atomic":     {"iso": "atomic"},
    "succ":          {"iso": "succ"},
    "plus":          {"iso": "plus"},
    "phrase":        {"iso": "phrase"},
    "time_goal":     {"iso": "time", "swi": "time", "scryer": "time", "trealla": "time"},
    "include":       {"swi": "include", "scryer": "include",
                      "gprolog": "include", "trealla": "include"},
    "exclude":       {"swi": "exclude", "scryer": "exclude",
                      "gprolog": "exclude", "trealla": "exclude"},
    "foldl":         {"swi": "foldl", "scryer": "foldl", "trealla": "foldl"},
    "sign":          {"iso": "sign"},
    "gcd":           {"iso": "gcd"},
    "divmod_":       {"swi": "divmod", "scryer": "divmod", "trealla": "divmod"},
    "dif":           {"iso": "dif"},
    "unpack":        {"iso": "unpack"},
    "must_be":       {"iso": "must_be"},
    "can_be":        {"iso": "can_be"},
    "is_chars":      {"iso": "is_chars"},
    "char_code":     {"iso": "char_code"},
    "char_type":     {"iso": "char_type"},
    "atom_chars":    {"iso": "atom_chars"},
    "atom_codes":    {"iso": "atom_codes"},
    "atom_length":   {"iso": "atom_length"},
    "atom_concat":   {"iso": "atom_concat"},
    "number_chars":  {"iso": "number_chars"},
    "number_codes":  {"iso": "number_codes"},
    "number_string": {"iso": "number_string"},
    "retractall":    {"iso": "retractall"},
    "catch_error":   {"iso": "catch"},
    "once":          {"iso": "once"},
    # No "Cut" entry: Clausal has no cut, so exporting a stray Cut() as Prolog
    # `!` would launder cut through "cut-free" Clausal (A11-F036). It emits as a
    # plain `cut` predicate instead.
    "freeze":        {"iso": "freeze"},
    "when":          {"iso": "when"},
    "call_nth":      {"iso": "call_nth"},
    "count_all":     {"iso": "count_all"},
    "setup_call_cleanup": {"iso": "setup_call_cleanup"},
    "call_cleanup":  {"iso": "call_cleanup"},
    "catch_recover": {"iso": "catch_recover"},
    "writef":        {"iso": "writef"},
    "print":         {"iso": "print"},
    "read":          {"iso": "read"},
    "succ_or_zero":  {"iso": "succ_or_zero"},
    "abs_":          {"iso": "abs"},
    "truncate_":     {"iso": "truncate"},
    "round_":        {"iso": "round"},
    "ceiling_":      {"iso": "ceiling"},
    "floor_":        {"iso": "floor"},
    "sin_":          {"iso": "sin"},
    "cos_":          {"iso": "cos"},
    "tan_":          {"iso": "tan"},
    "exp_":          {"iso": "exp"},
    "log_":          {"iso": "log"},
    "sqrt_":         {"iso": "sqrt"},
    "min_":          {"iso": "min"},
    "max_":          {"iso": "max"},
    # The test runner's predicate (clausal.testing).  Mapped to itself so a
    # Prolog ``test/1`` clause stays ``test/1`` across the seam in both
    # directions instead of being PascalCased into the deprecated ``Test/1``.
    "test":          {"iso": "test"},
}


def resolve_name(clausal_name: str, dialect: Dialect) -> str:
    """Resolve a clausal predicate name to the Prolog name for *dialect*.

    Checks BUILTIN_NAME_MAP first (dialect-specific, then ISO fallback),
    then falls back to pascal_to_snake.
    """
    entry = BUILTIN_NAME_MAP.get(clausal_name)
    if entry is not None:
        # Try dialect-specific name first, then ISO fallback
        name = entry.get(dialect.name) or entry.get("iso")
        if name is not None:
            return name
    return pascal_to_snake(clausal_name)
