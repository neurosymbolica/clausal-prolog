# Does a predicate's self-denoting atom stay plain-spelled or become mangled post-flip?

Raised during F3 (`implementation_plans/w4b2-f2b-and-hard-families-2026-09-23.md`
section F3), while turning its three INFERENCE call sites into verified
yes/no for `is_zero_field_class`'s callers outside the F1/F2/F2b/F5
migration population.

## What was verified (probes run this session, `is_zero_field_class`'s
non-`head_key` callers, given a mangled-atom `str` in place of a
zero-arity `PredicateMeta` CLASS):

    P0 = make_predicate("F3ProbeZeroArity", [])
    mangled = mangle("some_mod", "some_pred")

    is_zero_field_class(P0)       -> True
    is_zero_field_class(mangled)  -> False   # str is never a PredicateMeta instance

    term_to_ast_expr(P0, {})      -> Constant(value='F3ProbeZeroArity')   # term.__name__
    term_to_ast_expr(mangled, {}) -> Constant(value='some_mod\x1fsome_pred')  # verbatim

    _templatize_query_goal(Goal(a=P0))      -> param bound to the CLASS object itself
    _templatize_query_goal(Goal(a=mangled)) -> param bound to the mangled STRING itself

    _is_ground_py(P0)      -> True
    _is_ground_py(mangled) -> True

`logic/solve.py:487` (`_ground_value`) and `builtins/_helpers.py:207`
(`_is_ground_py`): CONFIRMED, not just inference. Both pass the resolved
value through **verbatim**, unchanged, whichever era it came from (a class
object today, a mangled string post-flip) -- no exception, no `None`
fallback, no divergent boolean. The INFERENCE in the F3 design brief
holds for these two.

`compiler/terms_to_ast.py:1099` (`term_to_ast_expr`'s
`is_zero_field_class` branch): the mechanical claim in the F3 brief also
holds -- no exception, the pre-existing `isinstance(term, (int, float,
str, bytes, complex))` branch (line ~731, ~370 lines earlier in the same
function) already intercepts a mangled-atom `str` before code ever
reaches the `is_zero_field_class` check, exactly as the brief predicted.

**But the emitted literal's SPELLING is not the same across eras**, and
this is a genuinely different fact than the other two sites, not just a
restatement of the same "harmless" finding:

- Today: the class branch explicitly mints from `term.__name__` --
  the CLASS's plain, unqualified name -- because a live class object is
  not a marshal-safe `ast.Constant` value and must be converted to one.
- Post-flip (per this probe): the str branch bakes `term` **as-is**,
  which is the full mangled spelling (`module\x1fname`), never demangled
  back to the plain functor name.

## Why this is not simply "the same gap `_ground_value` also has"

`_ground_value`'s mangled-case output is *also* the raw mangled string,
unreconciled with the plain name -- so on its face this looks like the
identical situation. The difference: `_ground_value`'s job is "pass this
resolved value through as a bound runtime parameter, unchanged" -- it
already treats the class object the same way (passes the class itself,
not `class.__name__`), so passing the mangled string through unchanged is
*consistent* with what it does today, not a new asymmetry.
`term_to_ast_expr`'s job is different: TODAY it explicitly discards the
class identity and reconstructs an atom from `.__name__` specifically
*because* the resolved value is not what should be baked in verbatim. Post-
flip it has no such extraction step for the string case, so the question
"is the mangled spelling supposed to be baked in verbatim, or does this
site need a `demangle()` step" is unresolved by anything in the existing
code, whereas `_ground_value`'s pass-through-unchanged behavior is already
the intended behavior in both eras.

## The actual design question, parked rather than guessed at

`is_declared_predicate_name`'s own docstring (F2b, `predicate.py:1816`) is
unambiguous that a bare predicate reference in DATA position "denotes the
ATOM of its own name" -- the plain name, e.g. a bare `p/3` denotes the atom
`p`. The 12 F2b-covered call sites (F5's row 39 pair included) honour this
by minting from the SOURCE spelling (`term.func.name`, `sys.intern(fname)`)
and deliberately never touching the resolved BINDING's value -- see
`head_match.py`'s `_cell_match_pattern(sys.intern(term.func.name), ...)`
branch, which is the establishing precedent for "never bake the resolved
handle's own spelling; always use the declared name."

The four F3 call sites cannot use that technique: by the time a value
reaches `_ground_value`/`_is_ground_py`/`term_to_ast_expr`'s
`is_zero_field_class` branch, there is no source AST node with a `.name`
in scope any more -- only the already-resolved runtime/compile-time VALUE.
So if the ruling is "a predicate's self-atom must stay plain-spelled in
both eras" (matching F2b's own stated invariant), `term_to_ast_expr` needs
a real fix here (something like `_mint_atom(demangle(term)[1])` ahead of
the generic `str` branch, mirrored for symmetry at `_ground_value` even
though today it happens to already produce a usable, if mangled, atom).
If instead the ruling is "a predicate's self-atom is *allowed* to become
its mangled handle once W4b-2d lands" (a policy the currently-unbuilt flip
has not stated either way), no change is needed anywhere and this note can
be closed.

**This is exactly the class of question `w4b2-f2b-and-hard-families-2026-09-23.md`
recommends parking rather than deciding now** ("recommend this be the
first thing verified once W4b-2d lands, not designed further now") --
except the F3 section's own text treats all three non-`head_key` sites as
uniformly "harmless," which undersells this one specific asymmetry. No
code change made in this session for `term_to_ast_expr`; not enough is
known about the not-yet-built flip's atom-mangling policy to pick a fix
with confidence, and inventing one without an operator ruling risks
guessing wrong in either direction (over-eager demangling that breaks a
deliberate mangled-self-atom design, or leaving a real spelling bug that
only a post-flip corpus probe would catch).

## Related, not reopened

`database.py`'s `head_key` (the brief's row-9 example) is explicitly
*already* ruled "verified, no change needed" by the F3 design brief, and
this note does not reopen that ruling -- a clause HEAD is asserted through
its own predicate's own database, a narrower population than "any DATA
value that happens to hold a self-denoting predicate atom," and the brief's
verification stands as given. Flagging only that if the exit-criterion
probe below turns up a real mangled-vs-plain policy for the self-atom
case, `head_key`'s own `if type(head) is str: return head, 0` line is
worth a second look at the same time, for the same reason -- it is the
identical shape, just for a narrower input population.

## Exit criterion

Once W4b-2d (the flip itself) lands: build a fixture that declares a
zero-arity predicate, references it bare as a DATA value that reaches each
of these three sites (a query argument for `_ground_value`, a
`ground/1` call for `_is_ground_py`, a nested compound argument for
`term_to_ast_expr`), and diff the resulting atom's spelling against the
same predicate's plain declared name. That answers the policy question by
observation instead of by design debate.

## Resolved (2026-09-24, branch fix/w4b-self-atom-plain-2026-09-24)

Operator ruling: the self-denoting atom in data position stays PLAIN
("the default in Prolog is global, but be cognizant of directive hide/1").
Discriminator is `is_declared_predicate_name`, never `is_mangled`: a
`-hide` DATA atom is mangled too, and its mangled spelling is its identity.

- `term_to_ast_expr`: CHANGED. New arm ahead of the generic `str` arm --
  a `str` binding that `is_declared_predicate_name` accepts bakes
  `mint(predicate_binding_name(term))`; a `-hide` atom falls through and is
  baked verbatim.
- `_templatize_query_goal` / `_ground_value`: CHANGED. Evidence: its scalar
  arm intercepts every `str` BEFORE `term_to_ast_expr` is reached, so a
  top-level mangled predicate argument would bind the mangled spelling on
  the parameterized path while the unparameterized path bakes the plain one
  (the fix above would be bypassed). Review round (roborev MEDIUM): ONE arm,
  ahead of the scalar arm, `if is_declared_predicate_name(dv): return
  mint(predicate_binding_name(dv))`, for BOTH eras; the old zero-field
  CLASS arm (which bound the class object itself) is gone. Measured before
  changing it: across 68 targeted test files (2626 tests) the class arm
  fired ONCE, in `tests/test_f3_is_zero_field_class_callers.py`'s pin of
  the pre-ruling behaviour (updated). And the class it returned was
  useless: a `.clausal` fact `q(z)` (z/0 a predicate) stores the plain str
  `'z'`, so `solve(("q", m.z), m)` answered 0 with the class, 1 with the
  plain atom (now 1 in both eras).
- `_is_ground_py`: NO CHANGE. Answers a bool, never a spelling; `True` for
  both eras and for a `-hide` atom -- the ruling has nothing to act on.
- `head_key` (database.py): not reopened, per the note above.

- A mangled str whose owner module does NOT resolve (roborev LOW): kept
  VERBATIM in both sites, not refused. It cannot be told apart from a
  `-hide` DATA atom, and an unresolvable `-hide` atom is legitimate: a
  module loaded under a `sys.modules` key other than its `-module` name
  mints `hide_owner\x1fhide_secret`, `_resolve_mangled_owner` answers None,
  and the atom round-trips into a query today. The cost, documented at the
  `term_to_ast_expr` arm: a predicate handle whose owner is not loaded keeps
  its mangled spelling (load-state dependent, like every
  `is_declared_predicate_name` caller).

Tests: `tests/test_self_denoting_predicate_atom_plain.py` (fixtures
`hide_owner.clausal` loaded as `hide_owner`, new `self_atom_zero.clausal`
for a zero-arity predicate; a subprocess test for the alt-key `-hide`
round-trip). Mutations: reverting both sites, restoring the class arm,
swapping the gate to `is_mangled`, and refusing an unresolvable mangled
str each fail tests.

Not in scope, observed while probing (filed as
`todo/bare-predicate-name-in-clause-source-is-the-binding-not-the-atom-2026-09-24.md`):
a bare ARITY>=1 predicate name written in a `.clausal` clause (e.g. the
fact `r(b)` where `b/1` is a predicate) evaluates at runtime to the BINDING
(the class today, the mangled handle post-flip), not the plain atom; a
zero-arity one (`q(z)`) stores the plain atom. So the self-atom is not yet
plain on the clause-source side.

Review round 2 (roborev): both arms make ONE resolver call,
`predicate_binding_name(x, db=...)` (no second `_resolve_mangled_owner`, no
window between the check and the read), and pass the ruling-Q0 `db=` hint --
`_ground_value` gets the querying module's db from `_compile_as_query`;
`term_to_ast_expr` reads the lowering scope's `$module` db. A local handle in
a module popped from `sys.modules` now lowers plain on both paths (test fails
if either hint, or the `_compile_as_query` pass-through, is removed). The
tests resolve every fixture handle through its owner's db, so a peer test
popping `hide_owner` cannot empty the compared population.
