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
    AllDifferent -> all_different
    CLP          -> clp
    CopyTerm     -> copy_term
    DCGRule      -> dcg_rule
    IOStream     -> io_stream
    """
    s = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1_\2", name)
    s = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", s)
    return s.lower()


def snake_to_pascal(name: str) -> str:
    """Convert Prolog snake_case to clausal PascalCase.

    foo_bar       -> FooBar
    all_different -> AllDifferent
    copy_term     -> CopyTerm
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
    "AssertZ":       ("assertz",        None, None),
    "AssertA":       ("asserta",        None, None),
    "Retract":       ("retract",        None, None),
    "FindAll":       ("findall",        None, None),
    "BagOf":         ("bagof",          None, None),
    "SetOf":         ("setof",          None, None),
    "ForAll":        ("forall",         None, None),
    "CopyTerm":      ("copy_term",      None, None),
    "TermVariables": ("term_variables", None, None),
    "NumberVars":    ("numbervars",     None, None),
    "AllDifferent":  (None,             "all_different", "all_distinct"),
    "InDomain":      (None,             "ins",           "ins"),
    "Label":         ("label",          "label",         "label"),
    "Labeling":      ("labeling",       "labeling",      "labeling"),
    "MapList":       ("maplist",        None, None),
    "Writeln":       ("writeln",        None, None),
    "Write":         ("write",          None, None),
    "Nl":            ("nl",             None, None),
    "Tab":           ("tab",            None, None),
    "Call":          ("call",           None, None),
    "Atom":          ("atom",           None, None),
    "Number":        ("number",         None, None),
    "Integer":       ("integer",        None, None),
    "Float":         ("float",          None, None),
    "Var":           ("var",            None, None),
    "NonVar":        ("nonvar",         None, None),
    "Compound":      ("compound",       None, None),
    "Functor":       ("functor",        None, None),
    "Arg":           ("arg",            None, None),
    "Length":        ("length",         None, None),
    "Member":        ("member",         None, None),
    "Append":        ("append",         None, None),
    "Reverse":       ("reverse",        None, None),
    "Last":          ("last",           None, None),
    "Permutation":   ("permutation",    None, None),
    "Between":       ("between",        None, None),
    "IsVar":         ("var",            None, None),
    "IsBound":       ("nonvar",         None, None),
    "IsNumber":      ("number",         None, None),
    "IsInt":         ("integer",        None, None),
    "IsFloat":       ("float",          None, None),
    "IsStr":         ("atom",           None, None),
    "IsList":        ("is_list",        None, None),
    "IsGround":      ("ground",         None, None),
    "IsCallable":    ("callable",       None, None),
    "IsCompound":    ("compound",       None, None),
    "IsAtomic":      ("atomic",         None, None),
    "Succ":          ("succ",           None, None),
    "Plus":          ("plus",           None, None),
    "Phrase":        ("phrase",         None, None),
    "TimeGoal":      (None,             "time",          "time"),
    "Filter":        (None,             "include",       "include"),
    "Exclude":       (None,             "exclude",       "exclude"),
    "FoldLeft":      (None,             "foldl",         "foldl"),
    "Sign":          ("sign",           None, None),
    "Gcd":           ("gcd",            None, None),
    "DivMod":        (None,             "divmod",        "divmod"),
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
