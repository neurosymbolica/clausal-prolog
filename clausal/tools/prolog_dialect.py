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
    """
    if name == "_":
        return "_"
    if name.startswith("_"):
        return "_" + name[1:].lower()
    if len(name) == 1 and name.isupper():
        return name
    return "_" + name.lower()


# ── Builtin name mapping ────────────────────────────────────────────

# clausal name -> (ISO Prolog, SWI-specific, Scryer-specific)
# None means "use the ISO entry" or "not available in this dialect"
BUILTIN_NAME_MAP: dict[str, tuple[str | None, str | None, str | None]] = {
    "assertz":       ("assertz",        None, None),
    "asserta":       ("asserta",        None, None),
    "retract":       ("retract",        None, None),
    "findall":       ("findall",        None, None),
    "bagof":         ("bagof",          None, None),
    "setof":         ("setof",          None, None),
    "forall":        ("forall",         None, None),
    "copy_term":     ("copy_term",      None, None),
    "term_variables": ("term_variables", None, None),
    "numbervars":    ("numbervars",     None, None),
    "all_different": (None,             "all_different", "all_distinct"),
    "in_":           ("in",             None, None),
    "in_domain":     ("in_domain",       "ins",           "ins"),
    "label":         ("label",          "label",         "label"),
    "labeling":      ("labeling",       "labeling",      "labeling"),
    "maplist":       ("maplist",        None, None),
    "writeln":       ("writeln",        None, None),
    "write":         ("write",          None, None),
    "nl":            ("nl",             None, None),
    "tab":           ("tab",            None, None),
    "call":          ("call",           None, None),
    "functor":       ("functor",        None, None),
    "arg":           ("arg",            None, None),
    "length":        ("length",         None, None),
    "member":        ("member",         None, None),
    "append":        ("append",         None, None),
    "reverse":       ("reverse",        None, None),
    "last":          ("last",           None, None),
    "permutation":   ("permutation",    None, None),
    "between":       ("between",        None, None),
    "sort":          ("sort",           None, None),
    "msort":         ("msort",          None, None),
    "flatten":       ("flatten",        None, None),
    "select":        ("select",         None, None),
    "subtract":      ("subtract",       None, None),
    "intersection":  ("intersection",   None, None),
    "union":         ("union",          None, None),
    "list_to_set":   ("list_to_set",    None, None),
    "sum_list":      ("sum_list",       None, None),
    "max_list":      ("max_list",       None, None),
    "min_list":      ("min_list",       None, None),
    "numlist":       ("numlist",        None, None),
    "same_length":   ("same_length",    None, None),
    "in_check":      ("memberchk",      None, None),
    "get_item":      ("nth0",           "nth0",    "nth0"),
    "take":          ("take",           None, None),
    "drop":          ("drop",           None, None),
    "zip_":          ("zip",            None, None),
    "replicate":     ("replicate",      None, None),
    "var":           ("var",            None, None),
    "nonvar":        ("nonvar",         None, None),
    "number":        ("number",         None, None),
    "integer":       ("integer",        None, None),
    "float_":        ("float",          None, None),
    "atom":          ("atom",           None, None),
    "is_str":        ("atom",           None, None),
    "is_list":       ("is_list",        None, None),
    "ground":        ("ground",         None, None),
    "callable_":     ("callable",       None, None),
    "compound":      ("compound",       None, None),
    "IsAtomic":      ("atomic",         None, None),
    "succ":          ("succ",           None, None),
    "plus":          ("plus",           None, None),
    "phrase":        ("phrase",         None, None),
    "time_goal":     (None,             "time",          "time"),
    "include":       (None,             "include",       "include"),
    "exclude":       (None,             "exclude",       "exclude"),
    "foldl":         (None,             "foldl",         "foldl"),
    "sign":          ("sign",           None, None),
    "gcd":           ("gcd",            None, None),
    "divmod_":       (None,             "divmod",        "divmod"),
    "dif":           ("dif",            None, None),
    "unpack":        ("unpack",         None, None),
    "must_be":       ("must_be",        None, None),
    "can_be":        ("can_be",         None, None),
    "is_chars":      ("is_chars",       None, None),
    "char_code":     ("char_code",      None, None),
    "char_type":     ("char_type",      None, None),
    "atom_chars":    ("atom_chars",     None, None),
    "atom_codes":    ("atom_codes",     None, None),
    "atom_length":   ("atom_length",    None, None),
    "atom_concat":   ("atom_concat",    None, None),
    "number_chars":  ("number_chars",   None, None),
    "number_codes":  ("number_codes",   None, None),
    "number_string": ("number_string",  None, None),
    "assertz":       ("assertz",        None, None),
    "asserta":       ("asserta",        None, None),
    "retractall":    ("retractall",     None, None),
    "catch_error":   ("catch",          None, None),
    "once":          ("once",           None, None),
    "freeze":        ("freeze",         None, None),
    "when":          ("when",           None, None),
    "call_nth":      ("call_nth",       None, None),
    "count_all":     ("count_all",      None, None),
    "setup_call_cleanup": ("setup_call_cleanup", None, None),
    "call_cleanup":  ("call_cleanup",   None, None),
    "catch_recover": ("catch_recover",  None, None),
    "writef":        ("writef",         None, None),
    "print":         ("print",          None, None),
    "read":          ("read",           None, None),
    "succ_or_zero":  ("succ_or_zero",   None, None),
    "abs_":          ("abs",            None, None),
    "float_":        ("float",          None, None),
    "truncate_":     ("truncate",       None, None),
    "round_":        ("round",          None, None),
    "ceiling_":      ("ceiling",        None, None),
    "floor_":        ("floor",          None, None),
    "sin_":          ("sin",            None, None),
    "cos_":          ("cos",            None, None),
    "tan_":          ("tan",            None, None),
    "exp_":          ("exp",            None, None),
    "log_":          ("log",            None, None),
    "sqrt_":         ("sqrt",           None, None),
    "min_":          ("min",            None, None),
    "max_":          ("max",            None, None),
}


def resolve_name(clausal_name: str, dialect: Dialect) -> str:
    """Resolve a clausal predicate name to the Prolog name for *dialect*.

    Checks BUILTIN_NAME_MAP first, then falls back to pascal_to_snake.
    """
    entry = BUILTIN_NAME_MAP.get(clausal_name)
    if entry is not None:
        iso_name, swi_name, scryer_name = entry
        if dialect.name == "swi" and swi_name is not None:
            return swi_name
        if dialect.name == "scryer" and scryer_name is not None:
            return scryer_name
        if iso_name is not None:
            return iso_name
    return pascal_to_snake(clausal_name)
