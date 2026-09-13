# A C bridge from term-tuples to Z3, and how SMT compares to our CLP — measured

**2026-09-13, engine-lane.** Everything here was RUN on this machine (aarch64). The prototype and
every harness are in this directory; `BUILD.sh` rebuilds and re-measures. Nothing here is engine
code — it is a measurement artefact, kept so the numbers can be re-derived rather than trusted.

## 1. The C bridge works, and the prize is ~100x on marshalling

`_z3bridge.c` (117 lines) walks functor-first term-tuples straight into `Z3_mk_*`.

    clausal_to_z3, AST construction only     83.4 ms     8.347 us/node
    C bridge,      AST construction only      0.82 ms     0.082 us/node
    LIKE-FOR-LIKE                                       101.7x

**The 101.7x is the honest number.** An earlier figure of 153.8x compared the bridge against
construction PLUS `solver.add` (41.5 ms), which the bridge did not do. Splitting them was the
difference between a real number and a flattering one.

End-to-end on the rulebase-shaped workload (2000 vars, 3998 linear constraints):

    today    marshal 125.9 ms + solve 53.6 ms = 179.5 ms    marshal is 70% of wall clock
    bridged  marshal  ~0.8 ms + solve 53.6 ms =  54.4 ms    marshal is  1.5%     ~3.3x

Why the layer costs so much, measured in three levels:

    L1  full Z3 Python API (ExprRef + operator overloading)   17.69 us/node
    L2  raw ctypes Z3_mk_*, no ExprRef                         3.30 us/node   5.35x
    L3  bare ctypes crossing floor                             1.75 us/node
    C   the bridge                                             0.082 us/node

**81% of today's cost is Python-wrapper tax before ctypes is even reached.** Independent
confirmation: cvc5's binding is COMPILED rather than ctypes and marshals 3.3x faster than Z3's
Python path on the same problem — same diagnosis, different vendor.

## 2. The tuple representation is what makes it cheap — and one trap

Dispatch is a POINTER COMPARE on the interned functor: `PyTuple_GET_ITEM(t,0)` then compare
against pointers cached at module init. No attribute lookup, no dict, no per-node Python object.

**THE TRAP, found by a positive control and not by reading:** CPython auto-interns only
IDENTIFIER-LIKE strings. `'+'`, `'>='`, `'=<'` are NOT auto-interned, so a literal `'+'` in Python
source is a DIFFERENT object from the C module's interned `"+"` and the fast path misses. Clausal
is safe because `mint()` interns through the atom table (`mint('foo')[0] is sys.intern('foo')` is
True) — but the bridge must not ASSUME it. The prototype re-interns on a miss, so correctness does
not depend on where the term came from and only non-atom-table terms pay.

The first control run failed with `unknown functor '>='`. **A benchmark without that control would
have reported a beautiful number for a marshaller that rejected every term.**

Controls that now pass, and any rewrite must keep them:

    ('>=', ('+', ('v',0), ('v',1)), 7)   -> Z3 renders (>= (+ x0 x1) 7)
    ('=', ('*', ('v',2), 3), ...)        -> (= (* x2 3) (- x3 1))
    ('nosuchop', 1, 2)                   -> ValueError
    ('v', 99)                            -> IndexError

Rendering with `Z3_ast_to_string` is the control that matters: it proves Z3 received the structure,
where a node COUNT would pass on an empty AST.

## 3. The blocker for productionising it

**The Z3 path does not consume tuples today.** `clausal_to_z3` dispatches on `pythonic_ast`
dataclass nodes (`Add`, `ArithEq`, ...). From C those are attribute lookups back through Python,
which eats most of the win. So the work is NOT "write a C bridge" — it is **"get constraint
expressions to the bridge in functor-first tuple form"**. That question should be settled before
any production C is written.

Riding along: `clausal_to_z3` is RECURSIVE and blows the Python stack at ~20k depth. A C bridge
wants an explicit stack, so this is a correctness fix as well as a speed one.

## 4. SMT vs our CLP — and the answer is not one-directional

**Speed, and there is a crossover rather than a winner.** N-queens, CLP(Z)'s home turf:

     8-queens   CLP(Z)      4.4 ms   Z3     32.6 ms    CLP(Z) 7.4x faster
    12-queens   CLP(Z)     23.1 ms   Z3     18.1 ms    even
    16-queens   CLP(Z)   1577.7 ms   Z3    127.8 ms    Z3 12x
    20-queens   CLP(Z)  52752.4 ms   Z3    399.3 ms    Z3 132x

Linear rational systems are worse for CLP(Q) — 36x at 200 vars, **326x at 1000** — and it scales
about quadratically (2.3 s -> 62.8 s for 5x the size) where Z3 is near-linear (63 -> 193 ms).

**CORRECTION 2026-09-13, and it matters more than the original claim.** This section first said
"that is our PYTHON CLP against Z3's C++". **That is TRUE of CLP(Q) and FALSE of CLP(Z).** Checked
by observation after the fact:

    CLP(FD)/CLP(Z)   C.  _clpfd_propagate.c (3484 lines) + _clpfd_core.c (676) +
                     _clpfd_domain_ops.h (530). At runtime _USE_C_DOMAINS and
                     _USE_C_PROPAGATE are both True, and the C module REPLACES
                     FDVar, every constraint class, propagate, _narrow and
                     _post_constraint. The Python fd_eq/fd_ne are thin wrappers
                     that unit-strip, type-check, then delegate to _c_impl.
    CLP(Q)           PURE PYTHON. There is no _clpq_core.c at all -- 1767 lines of
                     Python with no C counterpart. (CLP(R) and CLP(B) DO have one:
                     _clpr_core.c, _clpb_core.c. CLP(Q) is the one that does not.)

So the **326x for CLP(Q) is Python against C++**, as claimed, and the obvious question is whether a
C core closes it given CLP(R) and CLP(B) already have one. But the **132x for CLP(Z) at 20-queens
is a C PROPAGATOR losing**, which cannot be waved away the way the original caveat waved it away.
See section 7.

What remains true: the benchmarks post-everything-then-check, which flatters SMT against the
incremental, backtracking use a Prolog engine actually makes of a constraint store; and Scryer's
`clpz`, SICStus or Gecode would still sit somewhere else again.

**Capability cuts the OTHER way on the thing this project cares about.** Under-determined system,
`X + Y >= 10`, nothing else:

    CLP(Q):  {-_0 - _1 =< -10}        residual constraint, both variables still free
    Z3:      sat, model {X=10, Y=0}   one arbitrary witness

CLP answers with **the general solution**; SMT answers with **one example**. For a legal rulebase
that is not cosmetic: "the obligation holds provided the leverage ratio is at least 3%" IS a
residual constraint, and a witness satisfying it is a different statement. `dump_q` gives that;
a model does not.

So SMT is richer in THEORIES (nonlinear arithmetic — CLP(Q) is linear-only — bitvectors, strings,
arrays, quantifiers, MaxSMT). CLP is richer in ANSWER SHAPE, and integrates with unification and
backtracking natively instead of through push/pop-and-recheck.

## 5. cvc5 — installed, measured, and NOT a drop-in

`cvc5 1.3.4` via pip. Its Python binding is a compiled `.so`, not ctypes.

    LINEAR (2000 vars)   marshal          solve           total
      Z3                 146.5 ms         58.9 ms        205.4 ms
      cvc5                44.4 ms        107.0 ms        151.4 ms
                         cvc5 3.30x       cvc5 0.55x     cvc5 1.36x

    N-QUEENS             Z3               cvc5
       8                  41.7 ms          71.0 ms       cvc5  1.70x slower
      16                  73.2 ms        2322.5 ms       cvc5 31.74x slower
      20                 618.7 ms       11006.8 ms       cvc5 17.79x slower

cvc5 wins on MARSHALLING only because its binding is compiled — an argument for the C bridge, not
for cvc5. It loses on solving everywhere measured, catastrophically on combinatorial integers.
cvc5's total win on the linear case evaporates the moment Z3's marshalling is fixed.

**And a C bridge to cvc5 is not currently possible here: the wheel ships `libcvc5.so` but NO
HEADERS.** That needs cvc5 built from source. Z3, by contrast, ships `z3.h` and `z3_api.h` inside
its own wheel, which is why the prototype exists at all.

**Recommendation: Z3 first, behind a seam; cvc5 as a second backend only if a theory it is
genuinely better at shows up.** Nothing measured here argues for cvc5 on speed.

## 6. Not established

* corpus-scale behaviour — every benchmark here is synthetic and uniform
* the bridge handles 8 operators over integers; no reals, rationals, bitvectors, strings, no
  variable binding back into the trail, no push/pop, no model extraction
* incremental/backtracking use, which is the pattern that would actually flatter CLP
* whether SMT can produce residual constraints at all for our purposes (Z3 has no `dump_q`
  equivalent in the path we use)
