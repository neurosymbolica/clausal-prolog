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
    clpfd_module: str = "clpfd"
    tabling_directive: str = ":- table"
    string_type: str = "string"
    has_dicts: bool = False
    module_system: str = "iso"

    @classmethod
    def iso(cls) -> Dialect:
        return cls(
            name="iso",
            operator_table=OperatorTable.iso_default(),
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
        )

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
        )

    @classmethod
    def gprolog(cls) -> Dialect:
        return cls(
            name="gprolog",
            operator_table=OperatorTable.gprolog_default(),
            library_map={},  # FD constraints are built-in, no library imports
            clpfd_module="fd",
            tabling_directive="",  # GNU Prolog has no tabling support
            string_type="atom",
            has_dicts=False,
            module_system="none",
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
    """Convert clausal variable names to Prolog convention.

    _x       -> X          (strip leading underscore, uppercase)
    _foo     -> Foo        (strip underscore, capitalize)
    _head    -> Head       (strip underscore, titlecase)
    RESULT   -> Result     (ALLCAPS -> titlecase)
    X        -> X          (single uppercase letter stays)
    _        -> _          (anonymous stays)
    """
    if name == "_":
        return "_"
    if name.startswith("_") and not name.startswith("__"):
        name = name[1:]
    # Titlecase: first letter upper, rest lower
    if name.isupper() and len(name) > 1:
        return name[0] + name[1:].lower()
    if name[0].islower():
        return name[0].upper() + name[1:]
    return name


def prolog_var_to_clausal(name: str) -> str:
    """Convert Prolog variable names to clausal convention.

    X        -> X          (single uppercase stays — it's ALLCAPS)
    Foo      -> _foo       (titlecase -> leading underscore lowercase)
    Head     -> _head      (titlecase -> leading underscore lowercase)
    _Ignored -> _ignored   (leading underscore, lowercase)
    _        -> _          (anonymous stays)
    Foo_     -> _foo       (trailing underscore(s) stripped — a variable
                            must never land on Clausal's _x_ constant
                            spelling)
    _PI_     -> _pi        (same: constant-shaped input is de-constant-ed)
    """
    if name == "_":
        return "_"
    if name.startswith("_"):
        candidate = "_" + name[1:].lower()
    elif len(name) == 1 and name.isupper():
        return name
    else:
        candidate = "_" + name.lower()
    # Clausal reserves one-underscore-each-end spellings for constants;
    # a translated VARIABLE must never land on that class.
    while len(candidate) > 1 and candidate.endswith("_"):
        candidate = candidate[:-1]
    return candidate if candidate != "_" else "_v"


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
    "all_different": {"swi": "all_different", "scryer": "all_distinct",
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
    # over: no ISO engine defines in/2 without clpfd, so every kit library
    # that spells membership as a call (query_combinators, formalize_lib,
    # compliance_lib) exported a program that died with
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
    "time_goal":     {"swi": "time", "scryer": "time", "trealla": "time"},
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
