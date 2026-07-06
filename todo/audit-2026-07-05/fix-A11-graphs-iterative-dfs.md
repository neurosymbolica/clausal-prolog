# fix(A11-F043/F044): recursive DFS in has_cycle/find_path — silent wrong answers on deep graphs

`modules/graphs.py:488-505` (has_cycle color-DFS) and :292-299 (find_path)
recurse per node; at ~sys.getrecursionlimit() depth the RecursionError is
eaten by the trampoline (A09-F007) and the predicate FAILS: a 3001-node
directed cycle answers "no cycle"; a 2500-edge chain answers "no path"
(executed, controls succeed). A silently wrong "no" from decision predicates.

**Fix**: rewrite both iteratively (explicit stack / neighbor-iterator stack)
— every other traversal in the file is already iterative.

**Tests**: test_F043_has_cycle_deep_graph, test_F044_find_path_long_chain
(xfail).
