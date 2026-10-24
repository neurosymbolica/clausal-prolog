"""The built-in predicates of ISO 13211-1 (with Technical Corrigenda 1-3), by
predicate indicator: the procedures a Prolog text may not define.

ISO 7.5.1 makes a built-in predicate a static procedure, and 7.5.2 / 8.9
refuse to modify one: a clause for it in a Prolog text, ``dynamic/1`` of it,
and ``assertz``/``retract`` of it are each
``permission_error(modify, static_procedure, Name/Arity)``.  Scryer refuses a
file that defines one with that error from ``load/1``.

Only ISO's own built-ins are here.  A library predicate (``append/3``,
``length/2``, ``between/3``, ``forall/2``, ``msort/2``, ``numbervars/3``, ...)
is no built-in in ISO, and a user's file may define it, as in Scryer.

The set is ISO's, not the engine's: a builtin ISO names and the engine does
not yet provide (``read/1``, ``open/3``, ...) is listed too, so a program
that defines one is refused here as by any conforming processor.

Pure data: no engine import (the native front end reads it while lowering).
"""

from __future__ import annotations

#: 7.8 control constructs.
ISO_CONTROL_CONSTRUCTS: frozenset = frozenset({
    ("call", 1), (",", 2), (";", 2), ("->", 2), ("!", 0),
    ("true", 0), ("fail", 0), ("catch", 3), ("throw", 1),
})

#: Clause 8 built-in predicates (Cor.2 additions marked).
ISO_BUILTIN_PREDICATES: frozenset = frozenset({
    # 8.2 term unification
    ("=", 2), ("unify_with_occurs_check", 2), ("\\=", 2),
    ("subsumes_term", 2),                                   # Cor.2
    # 8.3 type testing
    ("var", 1), ("atom", 1), ("integer", 1), ("float", 1), ("atomic", 1),
    ("compound", 1), ("nonvar", 1), ("number", 1),
    ("callable", 1), ("ground", 1), ("acyclic_term", 1),    # Cor.2
    # 8.4 term comparison
    ("@=<", 2), ("==", 2), ("\\==", 2), ("@<", 2), ("@>", 2), ("@>=", 2),
    ("compare", 3), ("sort", 2), ("keysort", 2),            # Cor.2
    # 8.5 term creation and decomposition
    ("functor", 3), ("arg", 3), ("=..", 2), ("copy_term", 2),
    ("term_variables", 2),                                  # Cor.2
    # 8.6 arithmetic evaluation, 8.7 arithmetic comparison
    ("is", 2),
    ("=:=", 2), ("=\\=", 2), ("<", 2), ("=<", 2), (">", 2), (">=", 2),
    # 8.8 clause retrieval and information
    ("clause", 2), ("current_predicate", 1),
    # 8.9 clause creation and destruction
    ("asserta", 1), ("assertz", 1), ("retract", 1), ("abolish", 1),
    ("retractall", 1),                                      # Cor.2
    # 8.10 all solutions
    ("findall", 3), ("bagof", 3), ("setof", 3),
    # 8.11 stream selection and control
    ("current_input", 1), ("current_output", 1), ("set_input", 1),
    ("set_output", 1), ("open", 3), ("open", 4), ("close", 1), ("close", 2),
    ("flush_output", 0), ("flush_output", 1), ("stream_property", 2),
    ("at_end_of_stream", 0), ("at_end_of_stream", 1),
    ("set_stream_position", 2),
    # 8.12 character input/output
    ("get_char", 1), ("get_char", 2), ("get_code", 1), ("get_code", 2),
    ("peek_char", 1), ("peek_char", 2), ("peek_code", 1), ("peek_code", 2),
    ("put_char", 1), ("put_char", 2), ("put_code", 1), ("put_code", 2),
    ("nl", 0), ("nl", 1),
    # 8.13 byte input/output
    ("get_byte", 1), ("get_byte", 2), ("peek_byte", 1), ("peek_byte", 2),
    ("put_byte", 1), ("put_byte", 2),
    # 8.14 term input/output
    ("read_term", 2), ("read_term", 3), ("read", 1), ("read", 2),
    ("write_term", 2), ("write_term", 3), ("write", 1), ("write", 2),
    ("writeq", 1), ("writeq", 2), ("write_canonical", 1),
    ("write_canonical", 2), ("op", 3), ("current_op", 3),
    ("char_conversion", 2), ("current_char_conversion", 2),
    # 8.15 logic and control
    ("\\+", 1), ("once", 1), ("repeat", 0),
    ("call", 2), ("call", 3), ("call", 4), ("call", 5), ("call", 6),
    ("call", 7), ("call", 8), ("false", 0),                 # Cor.2
    # 8.16 atomic term processing
    ("atom_length", 2), ("atom_concat", 3), ("sub_atom", 5),
    ("atom_chars", 2), ("atom_codes", 2), ("char_code", 2),
    ("number_chars", 2), ("number_codes", 2),
    # 8.17 implementation defined hooks
    ("set_prolog_flag", 2), ("current_prolog_flag", 2),
    ("halt", 0), ("halt", 1),
})

#: Every ISO built-in: the procedures a Prolog text may not define.
ISO_BUILTINS: frozenset = ISO_CONTROL_CONSTRUCTS | ISO_BUILTIN_PREDICATES


def is_iso_builtin(name: str, arity: int) -> bool:
    """True when *name*/*arity* is an ISO 13211-1 built-in predicate or
    control construct."""
    return (name, arity) in ISO_BUILTINS
