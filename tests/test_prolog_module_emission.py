"""Module export filtering (Task 4).

Scryer raises permission_error(...module_does_not_contain_claimed_export...)
when a :- module export has no clauses backing it (signature-only kernels,
term constructors like cite/1, 0-arity atoms) — this post-pass filters
those dead exports out.
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
