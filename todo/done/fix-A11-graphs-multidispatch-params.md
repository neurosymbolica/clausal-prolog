# fix(A11-F053): _GraphPredicate._multi_dispatch drops _fail/_catcher (latent)

`modules/graphs.py:50-56` forwards `yield from fn(this_generator, _proceed,
*args)` — the base ModulePredicate (modules/py/__init__.py:82-88) forwards
`_fail, _catcher` too. Latent today (every graph predicate registers exactly
one arity so _get_dispatch returns the fn directly); the first multi-arity
graph predicate will crash with a TypeError at call time (executed by
registering a second arity).

**Fix**: delete _GraphPredicate and subclass/instantiate ModulePredicate like
units does (removes the copy-paste the base class exists to prevent); or just
pass the two params through.

**Test**: test_F053_multi_dispatch_forwards_all_params (xfail).
