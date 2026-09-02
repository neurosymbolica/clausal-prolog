"""Module export filtering + discontiguous emission (Tasks 4-5).

Scryer raises permission_error(...module_does_not_contain_claimed_export...)
when a :- module export has no clauses backing it (signature-only kernels,
term constructors like cite/1, 0-arity atoms) — Task 4 filters those dead
exports out.

Scryer also silently OVERWRITES a clause run that gets interrupted by
another predicate's clauses unless a :- discontiguous directive names it —
Task 5 emits that directive automatically.
"""

from clausal.tools.clausal_to_prolog import (
    clausal_source_to_prolog,
    clausal_source_to_prolog_ast,
    module_export_signature,
)

KERNEL_SRC = """-module(kernel, [ai_act_verdict(S, L, E, C), met, unmet])
"""

MIXED_SRC = """-module(citations, [cite(C), citation(A, M), some_atom])
citation(a1, meta1),
citation(a2, meta2),
"""


def test_signature_only_module_exports_nothing():
    out = clausal_source_to_prolog(KERNEL_SRC, strict=True)
    assert ":- module(kernel, [])." in out


def test_declaration_only_names_dropped_from_exports():
    out = clausal_source_to_prolog(MIXED_SRC, strict=True)
    assert ":- module(citations, [citation/2])." in out


def test_module_export_signature_helper():
    pmod = clausal_source_to_prolog_ast(MIXED_SRC)
    assert module_export_signature(pmod) == {("citation", 2)}


DISCONTIG_SRC = """exception_a(P) <- get(P, k1, true)
other(x),
exception_a(P) <- get(P, k2, true)
"""


def test_discontiguous_directive_emitted():
    out = clausal_source_to_prolog(DISCONTIG_SRC, strict=True)
    assert ":- discontiguous(exception_a/1)." in out
    # contiguous predicates get no directive
    assert ":- discontiguous(other/0)." not in out
