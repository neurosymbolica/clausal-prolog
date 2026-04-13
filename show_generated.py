"""Show clausal source alongside generated trampoline Python code.

Run from the clausal-opt directory after building the C extensions:

    cd clausal-opt
    pip install -e .          # builds _variables and _trampoline C extensions
    python show_generated.py

If pip install fails due to a missing compiler, install build tools first:
    macOS:   xcode-select --install
    Ubuntu:  sudo apt install python3-dev build-essential

──────────────────────────────────────────────────────────────────────────────
READING THE GENERATED CODE
──────────────────────────────────────────────────────────────────────────────

Every compiled predicate is a Python generator with this signature:

    def pred__N(this_generator, _tramp_parent, arg0, ..., argN-1, trail)

The trampoline protocol uses two kinds of yield:

    yield (_tramp_parent, None)   →  solution found; parent resumes
    yield (_tramp_parent, _DONE)  →  search exhausted; parent can stop

A sub-call is driven by:

    _gen = StepGenerator(callee._get_dispatch(), this_generator, args..., trail)
    _st  = yield (_gen, None)           # hand off to callee
    while _st is not _DONE:
        <use solution>
        _st = yield (_gen, None)        # ask for next solution

This means no Python stack grows with recursion depth: every call returns
to the trampoline, which loops at O(1) stack depth.

The trail records variable bindings.  trail.mark() / trail.undo(mark) bracket
each clause so that on backtrack every binding is undone atomically.

Phase 7 (locked-predicate dispatch cache): when the callee is locked at the
caller's compile time, the dispatch closure is captured as _disp_pred_N in
base_globals so the call site becomes StepGenerator(_disp_pred_N, ...) —
one attribute lookup saved on every call.

Phase 10 (call-site bucket specialisation): when a locked callee is called
with a statically-known literal argument in an indexed position, the dispatch
closure is bypassed entirely and the specific bucket function is referenced
directly, e.g. StepGenerator(color.bucket(pos=0, 'red'), ...).  The globals
key is an arbitrary string resolved by dict lookup — not a valid identifier,
but ast.unparse renders it readably.
"""
import ast
from clausal.tools.visualize import predicate_to_source
from clausal.logic.database import Clause
from clausal.logic.variables import Var
from clausal.logic.compiler import (
    _inject_bucket_refs_trampoline,
    _bucket_key, compile_predicate_trampoline,
    _build_predicate_trampoline_funcdef, _make_body_compiler_trampoline,
)
from clausal.logic.compiler.compile_ctx import CompilationContext
from clausal.logic.predicate import PredicateMeta
from clausal.logic.builtins import _normalize_fact_clause
from clausal.terms import (
    Unify as Is,
    Add, Sub, Mult,
    Gt, Lt, GtE, LtE,
    Or, Not, And,
    Call, LoadName,
    Compound,
    ArithEq,
)

SEP = "=" * 72


def show(title, clausal_src, notes, functor, arity, clauses, db=None):
    print(SEP)
    print(f"# {title}")
    print()
    print("# CLAUSAL:")
    for line in clausal_src.strip().splitlines():
        print("  " + line)
    print()
    print("# GENERATED (trampoline):")
    print(predicate_to_source(functor, arity, clauses, db, trampoline=True))
    print("# NOTES:")
    for line in notes.strip().splitlines():
        print("  " + line)
    print()


# ── 1. Simple facts ──────────────────────────────────────────────────────────

clauses_color = [
    _normalize_fact_clause(Compound("color", (a,)))
    for a in ["red", "green", "blue", "yellow", "purple"]
]
show(
    "1. Simple facts  color/1",
    """
color("red").
color("green").
color("blue").
color("yellow").
color("purple").
""",
    """
Each clause becomes a separate `match` arm.  The single argument is deref'd
once into _d0 at the top; each arm captures it as a wildcard (_v0, _v1, …)
and then calls unify() to attempt binding it to the literal.

The trail.mark() / trail.undo() pair around each arm ensures that any
bindings made during that clause are rolled back on backtracking.

The final `yield (_tramp_parent, _DONE)` signals to the trampoline that
there are no more solutions to try.

Note: below the indexing threshold these fall-through matches are the only
dispatch path.  Above the threshold (5+ clauses, as here), the compiler also
builds per-key bucket functions and a groundness-keyed dispatch closure that
routes ground calls directly to the right bucket, bypassing these matches.
""",
    "color", 1, clauses_color,
)


# ── 2. Fibonacci (recursive, arithmetic) ─────────────────────────────────────

N_ = Var(); F_ = Var(); N1_ = Var(); F1_ = Var(); N2_ = Var(); F2_ = Var()
clauses_fib = [
    Clause(head=Compound("fib", (0, 0)), body=[]),
    Clause(head=Compound("fib", (1, 1)), body=[]),
    Clause(
        head=Compound("fib", (N_, F_)),
        body=[
            Gt(left=N_, right=1),
            Is(left=N1_, right=Sub(left=N_, right=1)),
            Call(func=LoadName(name="fib"), args=[N1_, F1_]),
            Is(left=N2_, right=Sub(left=N_, right=2)),
            Call(func=LoadName(name="fib"), args=[N2_, F2_]),
            Is(left=F_, right=Add(left=F1_, right=F2_)),
        ],
    ),
]
show(
    "2. Fibonacci  fib/2",
    """
fib(0, 0).
fib(1, 1).
fib(N_, F_) <-
    N_ > 1,
    N1_ is N_ - 1,
    fib(N1_, F1_),
    N2_ is N_ - 2,
    fib(N2_, F2_),
    F_ is F1_ + F2_.
""",
    """
The two base cases compile to `case [0, 0]` / `case [1, 1]` MatchValue
patterns — no unify() call needed because both arguments are ground literals.

The recursive clause pre-allocates all body-only variables (_v7–_v10) at the
top of its match arm, before any generator is created.  This is necessary
because Python's scoping would otherwise raise UnboundLocalError when a
nested continuation references a variable allocated deeper in the chain.

Each recursive call becomes a StepGenerator loop:
  _gen = StepGenerator(fib._get_dispatch(), this_generator, _v7, _v8, trail)
  _st  = yield (_gen, None)
  while _st is not _DONE:
      <body>
      _st = yield (_gen, None)

The two loops are nested, not sequential: the outer loop (first fib call)
iterates solutions for F1_, and for each one the inner loop iterates F2_.
This is the standard CPS continuation chain compiled into generator nesting.

Crucially, `yield` returns control to the trampoline at O(1) stack depth
regardless of how deep the recursion goes.  No Python stack overflow.
""",
    "fib", 2, clauses_fib,
)


# ── 3. List member (structural recursion) ────────────────────────────────────

X_ = Var(); H_ = Var(); T_ = Var(); REST_ = Var()
clauses_member = [
    Clause(head=Compound("member", (X_, [X_, REST_])), body=[]),
    Clause(
        head=Compound("member", (X_, [H_, T_])),
        body=[Call(func=LoadName(name="member"), args=[X_, T_])],
    ),
]
show(
    "3. List member  member/2",
    """
member(X_, [X_ | _]).
member(X_, [_ | T_]) <- member(X_, T_).
""",
    """
List heads are handled by _head_list_unify_input / _head_list_unify_output,
a two-phase protocol.  The "input" phase attempts to unify the runtime list
value with the expected pattern [Head | Tail] and returns either:
  - a mark (int)  → structural match succeeded, bindings on the trail
  - None          → the list was already a concrete Python list (no bindings)
  - False         → mismatch, clause fails immediately

The "output" phase (_head_list_unify_output) is called at yield time only
when the input phase returned None, to reconstruct the list from bound vars.

The first clause uses _v11__dup0 (a dup of _v11) because the same logical
variable X_ appears in both argument positions.  The compiler detects this
aliasing and emits unify(_v11, _v11__dup0, trail) to enforce it.

The second clause's recursive call `member._get_dispatch()` is a runtime
lookup: member is being compiled, so it isn't locked yet and can't be
cached at compile time (that would be Phase 7 / Phase 10 territory).
""",
    "member", 2, clauses_member,
)


# ── 4. List append (three-way) ───────────────────────────────────────────────

L_ = Var(); R_ = Var(); OUT_ = Var()
H2_ = Var(); T2_ = Var(); REST2_ = Var()
clauses_append = [
    Clause(head=Compound("append", ([], L_, L_)), body=[]),
    Clause(
        head=Compound("append", ([H2_, T2_], R_, [H2_, REST2_])),
        body=[Call(func=LoadName(name="append"), args=[T2_, R_, REST2_])],
    ),
]
show(
    "4. List append  append/3",
    """
append([], L_, L_).
append([H_ | T_], R_, [H_ | REST_]) <- append(T_, R_, REST_).
""",
    """
First-argument indexing is visible here: the compiler emits a top-level
isinstance(_d0, list) / is_var(_d0) guard before any match arms.

  - If _d0 is a concrete list and empty → only the base clause is tried.
  - If _d0 is a concrete list and non-empty → only the recursive clause.
  - If _d0 is a Var (unbound) → both clauses are tried in order (the
    predicate is being used in "generate" mode, e.g. to split a list).

This avoids trying the wrong clause for ground calls — a significant saving
when append is called with a known first argument.

The shared variable H_ appears in both the second and third head arguments.
The compiler detects this alias and emits _lr0/_lr1 for the two list-unify
phases, then ANDs their guards: `if _lr0 is not False and _lr1 is not False`.
""",
    "append", 3, clauses_append,
)


# ── 5. Disjunction (OR in body) ──────────────────────────────────────────────

V_ = Var()
clauses_primary = [
    Clause(
        head=Compound("primary", (V_,)),
        body=[Or(
            left=ArithEq(left=V_, right="red"),
            right=Or(
                left=ArithEq(left=V_, right="blue"),
                right=ArithEq(left=V_, right="yellow"),
            ),
        )],
    ),
]
show(
    "5. Disjunction in body  primary/1",
    """
primary(V_) <-
    V_ == "red" ; V_ == "blue" ; V_ == "yellow".
""",
    """
Or/2 compiles to sequential trail.mark() / trail.undo() blocks, one per
branch.  Each branch is tried in order; the trail is rewound between them
so bindings from a failed branch don't leak.

_fd_eq (finite-domain equality) is used here instead of unify() because ==
is structural equality — it doesn't bind variables, it just checks.

The nested Or tree flattens naturally: the compiler recurses into both sides
of each Or node, so three alternatives produce three sequential if blocks.

Contrast with clauses: clauses are separate match arms (one per clause), while
disjunction within a clause body is inlined as sequential branches sharing the
same match arm's trail scope.
""",
    "primary", 1, clauses_primary,
)


# ── 6. Negation-as-failure ───────────────────────────────────────────────────

Q_ = Var()
clauses_not_blue = [
    Clause(
        head=Compound("not_blue", (Q_,)),
        body=[
            Call(func=LoadName(name="color"), args=[Q_]),
            Not(operand=ArithEq(left=Q_, right="blue")),
        ],
    ),
]
show(
    "6. Negation-as-failure  not_blue/1",
    """
not_blue(Q_) <- color(Q_), \\+ Q_ == "blue".
""",
    """
\\+ (NAF) compiles to an inline miniature trampoline inside the outer body.

_naf_gen_fn is a locally-defined generator that tries the negated goal.
It is driven by a hand-unrolled trampoline loop (_naf_g24 / _naf_v25) that
runs entirely within a single yield step of the outer generator — the outer
trampoline never sees the inner search.

The flag _naf22 starts True.  If the inner search finds any solution, it
flips to False.  After the inner trampoline exits, the outer body continues
only if _naf22 is still True (i.e. the negated goal had no solutions).

The trail is marked/undone around the inner search (_m26) so that any
speculative bindings made while testing the negated goal are discarded,
even if the inner goal partially succeeded before failing.

The outer StepGenerator loop (for color/1) is the continuation: for each
color solution _v22 is bound, then the NAF check is applied, and solutions
that pass it are yielded upward.
""",
    "not_blue", 1, clauses_not_blue,
)


# ── 7. Phase 10: call-site bucket specialisation ─────────────────────────────

print(SEP)
print("# 7. Phase 10: call-site bucket specialisation")
print()
print("# CLAUSAL (caller with literal arg):")
print("""  find_red(X_) <- color("red").
""")

# Build and lock color/1
color_pred = PredicateMeta("color", (), {"_fields": ("name",)})
compile_predicate_trampoline("color", 1, clauses_color, pred_cls=color_pred)
color_pred._locked = True

# Build find_red/1 caller clause
X2_ = Var()
caller_clauses = [
    Clause(
        head=Compound("find_red", (X2_,)),
        body=[Call(func=LoadName(name="color"), args=["red"])],
    ),
]

# Inject bucket refs, then generate AST with the context in place.
# The body_compiler captures ctx_template by reference; mutating
# ctx_template.bucket_ref_map after construction is visible at compile time.
base_globals = {"color": color_pred}
db_placeholder = None

ctx_phase10 = CompilationContext(
    db=db_placeholder, var_context={}, trail_name="trail",
)
_inject_bucket_refs_trampoline(ctx_phase10, caller_clauses, base_globals)

body_compiler_p10 = _make_body_compiler_trampoline(
    db_placeholder, ctx_template=ctx_phase10,
)
func_def = _build_predicate_trampoline_funcdef(
    "find_red", 1, caller_clauses, db_placeholder, body_compiler_p10,
)
raw = ast.unparse(func_def)
try:
    import black
    raw = black.format_str(raw, mode=black.Mode())
except Exception:
    pass
print("# GENERATED (trampoline, Phase 10 — direct bucket ref):")
print(raw)

# Compare: same caller with only Phase 7 (locked dispatch, no static key).
ctx_phase7 = CompilationContext(
    db=db_placeholder, var_context={}, trail_name="trail",
    locked_dispatch_keys=frozenset(["_disp_color_1"]),
)
body_compiler_p7 = _make_body_compiler_trampoline(
    db_placeholder, ctx_template=ctx_phase7,
)
func_def2 = _build_predicate_trampoline_funcdef(
    "find_red", 1, caller_clauses, db_placeholder, body_compiler_p7,
)
raw2 = ast.unparse(func_def2)
try:
    raw2 = black.format_str(raw2, mode=black.Mode())
except Exception:
    pass
print("# GENERATED (trampoline, Phase 7 only — cached dispatch closure):")
print(raw2)

print("# NOTES:")
print("""
  The two versions differ by exactly one identifier in the StepGenerator call:

    Phase 10:  StepGenerator(color.bucket(pos=0, 'red'), this_generator, ...)
    Phase 7:   StepGenerator(_disp_color_1,             this_generator, ...)

  Phase 7 (_disp_color_1) is the pre-captured dispatch closure for color/1.
  At runtime it calls deref(args[0]), then does a dict lookup to find the
  right bucket.  That's one deref + one dict.get per call.

  Phase 10 (color.bucket(pos=0, 'red')) is the bucket function itself,
  looked up once at compile time and stored in base_globals under that string
  key.  At runtime there is no dispatch at all — the bucket is called directly.

  The key `color.bucket(pos=0, 'red')` is not a valid Python identifier, but
  Python's `compile(ast_tree, ...)` resolves `ast.Name(id=k)` via a plain dict
  lookup on the function's globals dict, so any string works.  `ast.unparse`
  renders it verbatim, making the generated code self-documenting.

  This only fires for *locked* predicates (predicates whose clauses are frozen
  at compile time of the caller).  Dynamic predicates always go through
  `._get_dispatch()` because their clause set may change at runtime.
""")

print(SEP)
