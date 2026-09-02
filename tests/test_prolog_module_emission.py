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


# A hand-written -discontiguous(...) for the same predicate the
# interruption tracker would ALSO flag must not be duplicated.
DUPLICATE_DISCONTIG_SRC = """-module(m, [Foo(X)])
-discontiguous(Foo(X))
Foo(1),
Bar(2),
Foo(3),
"""


def test_discontiguous_directive_not_duplicated_when_hand_written():
    out = clausal_source_to_prolog(DUPLICATE_DISCONTIG_SRC, strict=True)
    assert out.count(":- discontiguous(foo/1).") == 1


# Two DCG rules of one nonterminal interrupted by an ordinary clause —
# the emitted indicator carries the +2 hidden difference-list state args
# (the same arity module_export_signature would report for this rule).
DCG_INTERRUPTED_SRC = """greeting >> (["hi"])
other(x),
greeting >> (["yo"])
"""

DCG_CONTIGUOUS_SRC = """greeting >> (["hi"])
greeting >> (["yo"])
"""


def test_discontiguous_directive_emitted_for_interrupted_dcg_run():
    out = clausal_source_to_prolog(DCG_INTERRUPTED_SRC, strict=True)
    assert ":- discontiguous(greeting/2)." in out


def test_no_discontiguous_directive_for_contiguous_dcg_run():
    out = clausal_source_to_prolog(DCG_CONTIGUOUS_SRC, strict=True)
    assert ":- discontiguous(greeting/2)." not in out
