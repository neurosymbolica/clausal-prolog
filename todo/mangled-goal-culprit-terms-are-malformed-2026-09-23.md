# The culprit terms for an unresolvable mangled goal are MALFORMED

**Found by:** a review of the error-shape question, 2026-09-23; reproduced by
the controller on main `a5466fa2` before filing. **Pre-existing — NOT
introduced by `8157b2de`** (that path returned the goal untouched under the
old `sys.modules` test too, for the same reason).

## Measured

    list(solve((mangle("no_such_mod_zz", "whatever"), 1)))
      -> LogicException
         term = error(existence_error(module, "('no_such_mod_zz\x1fwhatever', 1)"),
                      "solve/1: the unqualified cell goal no_such_mod_zz\x1fwhatever/1 ...")

    list(solve((mangle("hide_owner", "nosuchpred"), 1)))     # module IS loaded
      -> PredicateNotFoundError, e.term is None

## Three defects, in order of severity

1. **A raw `\x1f` control character sits inside a CATCHABLE term.** A
   `catch/3` pattern written against it would match on a control character
   forever. This is the expensive-to-reverse one: once a program catches it,
   the spelling is load-bearing.
2. **The culprit is a stringified PYTHON TUPLE REPR** — the literal text
   `"('no_such_mod_zz\x1fwhatever', 1)"` — not a Prolog term. Nothing can
   pattern-match it except by string surgery.
3. **The loaded-but-missing case carries NO logic term at all**
   (`e.term is None`); it is catchable only via `python_error_term`'s
   implementation-specific wrapping. So the two failure modes are not merely
   spelled differently, they are of different kinds.

## What the review concluded, and why the vocabulary question is secondary

The module-vs-procedure choice (`existence_error(module, ..)` versus
`existence_error(procedure, Name/Arity)`) was the question asked. The answer
that survives contact with the code is that **it is the wrong first question**:
no conforming program can write a `\x1f` atom, so this is a dangling-handle
invariant rather than an ISO procedure-existence situation, and the only
ISO-relevant constraint that binds here is the one being broken — **a
catchable term must be a clean ground term**, which neither case satisfies.

Proposed, not yet ruled:

* both cases raise `existence_error(procedure, Name/Arity)` as a
  `LogicException`, distinguished in the CONTEXT slot / message rather than in
  the culprit;
* **the mangled spelling never appears in the term** — demangle to
  `M:(Name/Arity)` or put the module in the context, but never emit `\x1f`;
* the argument against: the two mistakes have different remedies (load the
  module vs. define/import the predicate) and a module-carrying culprit lets
  `catch/3` tell them apart without parsing message text. Weigh that against
  defect 1, which is the one that cannot be walked back later.

## Owner

W4b-2a's second half. Defects 1 and 2 are worth fixing INDEPENDENTLY of the
vocabulary ruling — a control character and a Python repr in a catchable term
are wrong under every candidate answer.
