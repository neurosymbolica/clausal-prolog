"""clausal.rewrite -- Clausal-hosted term rewriting with comment survival.

A rewrite rule is an ordinary Clausal predicate, ``RewriteClause(IN, OUT)``,
matching the reified vocabulary of :mod:`clausal.reflection`.  Rules live in
``rules/*.clausal`` and are written the way any other Clausal predicate is
written: patterns over ``Clause`` / ``Goal`` / ``Variable`` / ``Atom`` terms,
with refusal spelled as ordinary failure.

The Python side of the tool -- :mod:`clausal.rewrite.driver` -- reifies each
clause of a file, asks the loaded rules for a replacement, splices the answer
back into the tree the formatter captured, and re-emits through
:mod:`clausal.fmt`.  Two properties come from doing it that way rather than by
rewriting text: comments survive because unchanged goals keep their original
``ast`` nodes, and a comment whose goal was deleted has to be given somewhere
to go or the run fails.
"""
