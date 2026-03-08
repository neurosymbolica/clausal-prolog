# predicates
# Edge facts: edge(From, To) <- True
edge(1, 2) <- True
edge(2, 3) <- True
edge(1, 3) <- True

# Reachability: reach(X, Y) if there is a path from X to Y
reach(X_, Y_) <- edge(X_, Y_)
reach(X_, Y_) <- (edge(X_, Z_) and reach(Z_, Y_))
