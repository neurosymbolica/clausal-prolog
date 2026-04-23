# Relational Documentation Rewrite

A multi-phase plan to rewrite the Clausal documentation so that it faithfully
expresses the relational paradigm — both explicitly (new foundational pages) and
implicitly (language throughout existing pages).

## Motivation

Markus Triska's central observation: when documentation says things like
"pattern matching on lists in clause heads" or "the first clause handles the
empty list," it frames logic programming in imperative terms. Readers absorb
this framing and think of predicates as procedures with fixed input/output
roles. This undermines the core insight of logic programming — that a predicate
defines a **relation**, usable in any direction, and that clauses state
**conditions under which the relation holds**.

Ulrich Neumerkel's complementary insight: logical purity (monotonicity,
steadfastness) is not an abstract ideal but a practical property that enables
declarative debugging, multi-directional use, and formal reasoning. If the
documentation never introduces these concepts, programmers never learn to write
code that has these properties.

The current Clausal docs are well-structured and technically correct, but they
use imperative framing throughout. This plan fixes that at every level.

---

## Source Material: Triska's Own Words

The following quotes from "The Power of Prolog" video lectures provide the
exact vocabulary and framing we should adopt. These are not paraphrases — they
are Triska's deliberate word choices, refined over years of teaching.

### On "describing" as the master verb

> "We say we're *describing* the curve because it wouldn't do the code justice
> to say we only generate the curve because we can do more with it — we have a
> general description and we can use it in different modes."
> — *Describing a Dragon Curve with Prolog*

> "To capture this generality we say that the predicate *describes* or *defines*
> the relation between the coordinates of a square and the corresponding
> integer. This wording captures both usage modes and also more."
> — *Describing a Knight's Tour with Prolog*

> "If we say the rule generates a list or the rule consumes a list then we only
> capture specific usage modes even though the same rule can be used in other
> modes too."
> — *Definite Clause Grammars (DCGs)*

> "We therefore say for example 'the grammar describes a sequence' in order to
> subsume all possible usage modes."
> — *Definite Clause Grammars (DCGs)*

### On relations vs functions

> "Suppose we want to find the maximum in a list of integers — first of all
> that's a very imperative way to phrase this task and suggests only one
> direction of use. [...] As declarative programmers we of course want to aim
> for something more general — we want to *describe* the maximum in a list of
> integers because we want to be able to generate, test, and complete such
> lists in all directions."
> — *Meta-Predicates in Prolog*

> "First of all that's not how we talk about relations because 'remove' is very
> imperative wording and it suggests only one direction."
> — *Argument Indexing in Prolog*

> "The name 'flatten' is already problematic in itself because it's an
> imperative and thinking about the relation imperatively already limits the
> generality and what we can describe with it."
> — *Prolog Antipatterns*

### On "when does this hold?"

> "We say this holds if — and now we think about it: *when does this hold?* So
> we state the conditions that make this relation true for its arguments."
> — *A Tour of Prolog*

> "in_ Prolog our job is to use horn clauses to state what holds under what
> conditions. This is declarative programming because we describe the situation
> and we leave it to Prolog to derive logical consequences of our description."
> — *A Tour of Prolog*

### On reading clauses declaratively

> "We can read the first clause as: list_length holds for the empty list and 0."
> — *Reading Prolog Code*

> "We can read the second clause as an implication: if list_length holds for
> [element|LS] and L0, and L is equal to L0 plus 1, then list_length holds for
> these arguments."
> — *Reading Prolog Code*

> "This way of reading the code does justice to the full generality of the code
> because we can use the code in several directions: to generate, to complete,
> and also to test solutions."
> — *Reading Prolog Code*

### Against procedural reading

> "Procedural reading is usually too hard to apply and also isn't able to
> capture the full generality of Prolog programs."
> — *Reading Prolog Code*

> "The key drawback of procedural reading is rather that it's also quite
> pointless in addition to being hard. So all effort we put into it is mostly
> wasted because when we slightly change the program or the execution strategy
> then we have to trace the steps again. And also a procedural reading doesn't
> do justice to the different modes in which we can use Prolog code and it
> encourages a procedural view that takes us away from the true generality of
> Prolog."
> — *Reading Prolog Code*

> "We simply cannot go through the code in the way Prolog does it. [...] So
> this simply doesn't scale, and we'd have tremendous difficulty to even
> understand such a simple and basic relation between lists and integers if we
> started to think in terms of stack frames and such low-level operations."
> — *Memory Usage of Prolog Programs*

> "What we actually want is rather the opposite of this, namely we want to
> reason declaratively about our code and focus on the meaning, not on virtual
> machine instructions."
> — *Memory Usage of Prolog Programs*

### On the most general query

> "A query where all arguments are fresh variables is called the most general
> query of a predicate. It asks for any case whatsoever for which the predicate
> holds."
> — *Prolog Queries and Answers*

> "when working with Prolog programs it is often a good idea to try the most
> general query to see which solutions there are in general."
> — *Prolog Queries and Answers*

### On purity and monotonicity

> "Pure means informally that the program has the properties we expect from a
> relation. So for instance a pure program doesn't perform destructive changes
> and doesn't have side effects. And monotonic means monotonicity of the
> inference relation like in logic. This means for example that adding a clause
> or removing a goal makes a program at most more general, never more specific."
> — *Reading Prolog Code*

> "Prolog has a pure monotonic core and we automatically get all desirable
> declarative properties as long as we keep to this core."
> — *Prolog Antipatterns*

> "The power of Prolog is rooted in the logical properties we ensure, and if we
> violate them then we can no longer depend on them and then the core
> attractions of Prolog are lost."
> — *Prolog Antipatterns*

> "Monotonicity means that adding a constraint can at most yield fewer
> solutions, never more solutions."
> — *Prolog Antipatterns*

Four key properties of pure code (from *Prolog Antipatterns*):
- **Monotonicity**: adding a constraint can at most reduce solutions
- **Commutativity of conjunction**: A,B means the same as B,A
- **Idempotency**: stating a goal once means the same as stating it many times
- **Separability**: clauses can be read and reasoned about in isolation

### On naming

> "Let us first consider a suitable name for this relation... one suitable name
> would be for example integer_next, because clearly we are talking about an
> integer and the next integer."
> — *Collatz Conjecture in Prolog*

> "I like to use an underscore at the end of auxiliary predicates especially
> when a predicate has more arguments that are not part of the name."
> — *Meta-Predicates in Prolog*

> "A good naming convention for non-terminals is to reflect what they are
> describing — so when choosing a name we ask: which sequences are we
> describing?"
> — *Definite Clause Grammars (DCGs)*

### On "how not what" (surprising reversal)

> "One sentiment I sometimes see about declarative programming is 'what not
> how' and at least in my opinion this does not adequately characterize
> declarative programming. in_ fact we may rightly say the opposite: 'how not
> what' — because it matters *how* we express our task, not *what* is being
> executed."
> — *Describing a Knight's Tour with Prolog*

### On beginners and simplicity

> "Just in the last few years I've seen great Prolog code also and especially
> from total beginners. And they knew nothing about any of this. They didn't
> know there's a global stack, didn't know there's a local stack, didn't know
> what an environment is, didn't know what a choice point is, didn't know
> anything about tail call optimization. They knew nothing about any of this,
> and still wrote great Prolog code — elegant, general, efficient, easy to
> understand, short — just great code, simply by following a few basic
> principles."
> — *Memory Usage of Prolog Programs*

### On working against reasoning

> "A very common mistake by Prolog programmers is to work against reasoning.
> Because a decisive property of good Prolog code is that it can be reasoned
> about in several ways."
> — *Prolog Antipatterns*

### On algorithm = logic + control

> "Clearly n-queens specifies the logic — that is, what must hold for a
> solution — and labeling specifies the control — that is, how to search for
> solutions."
> — *N-Queens in Prolog*

> "We as programmers are of course far more concerned with the logic. Our goal
> is to state the logic as clear as we can, and the control can be changed
> flexibly outside of the program."
> — *Faster Labeling for N-Queens*

### On correctness over speed

> "We need invulnerable software systems, even if they are 10 times slower
> than our current systems."
> — *Cryptography with Prolog*

### On answers being declaratively equivalent to queries

> "The basic invariant of an ideal top level interaction is clear from these
> examples, namely we post queries — Prolog terms — and we get answers as
> Prolog terms. And the answers are declaratively equivalent to the queries."
> — *The Prolog Toplevel*

### On describing output declaratively

> "We don't just write output on the terminal, because if the output appears
> only on the terminal then we can't easily reason about it with Prolog.
> Instead, we declaratively describe the output we want to emit, and only then
> emit it as the very last step."
> — *Formatting Output with Prolog*

### On the importance of languages for expressing problems

> "This is a key task for us as software engineers: devising languages that let
> us represent our problems."
> — *Describing Domino Tilings with Prolog*

---

## Terminology Guide

This table governs language choices across all phases.

### Words and phrases to AVOID

| Avoid | Why | Replace with |
|---|---|---|
| "pattern matching" (for clause heads) | Implies one-directional inspection of a value against a template | "unification", "the clause head unifies with the goal" |
| "matches" (for clause selection) | Same | "applies", "holds", "unifies with" |
| "returns" / "return value" | Predicates don't return | "the relation holds between X and Y" |
| "checks if" / "tests whether" | Implies boolean function | "holds when", "is true when" |
| "executes" / "runs" (for resolution) | Implies procedure | "holds", "is satisfied", "Clausal searches for" |
| "handles" (for clauses) | Implies case-dispatch | "holds when", "states that", "describes the case where" |
| "input" / "output" (for arguments) | Pure predicates have no fixed direction | "arguments", or name them by role |
| "computes X from Y" | Implies function | "relates X and Y", "describes the relation between" |
| "iterates over" | Implies looping | "holds for each element" |
| "assigns" / "sets" | Implies mutation | "unifies with", "binds to" |
| "the function" | Wrong abstraction | "the predicate", "the relation" |
| "destructures" | Implies input | "unifies the first argument with [HEAD, *TAIL]" |
| "peels off" | Imperative metaphor | "the first element HEAD and the remaining elements TAIL" |
| "calls" (for sub-goals) | Acceptable sometimes, but prefer | "the condition ... holds" |

### Words and phrases to PREFER

| Prefer | when to use |
|---|---|
| "holds" / "is true" | Describing when a predicate or clause applies |
| "the relation between X and Y" | Describing what a predicate defines |
| "unifies with" | Describing how clause heads interact with goals |
| "alternatives" | Describing multiple clauses for the same predicate |
| "conditions" | Describing body goals |
| "describes" / "states" | Describing what a clause or program does |
| "in all directions" / "multi-directional" | Describing generality of pure predicates |
| "the most general query" | The diagnostic for relational generality |
| "a constraint" | Describing CLP goals |

### Declarative readings of clauses

Instead of:
> "The first clause handles the empty list."

write:
> "The first clause states that the sum of the empty list is 0."

Instead of:
> "The second peels off HEAD, recurses on TAIL, and adds HEAD to the subtotal."

write:
> "The second clause states that the sum of a list [HEAD, *TAIL] is TOTAL when
> the sum of TAIL is SUBTOTAL and TOTAL is SUBTOTAL + HEAD."

The pattern is: **read the clause as a logical statement about when the relation holds**, not as a sequence of steps.

---

## Phase 1: New Foundational Pages

Create two new documentation pages that explicitly lay out the theoretical
foundation and the mental model.

### Page 1: `docs/thinking_relationally.md` — "Thinking Relationally"

Target audience: programmers coming from imperative/functional backgrounds.
This is the single most important new page. It should be linked early in the
tutorial and from the index.

#### Outline

**1. What is a relation?**

A relation is a set of tuples for which a statement holds. `parent("alice",
"bob")` is not an assignment or a function call — it states that the parent
relation holds between "alice" and "bob". A predicate in Clausal defines a
relation by describing, through its clauses, all the combinations of arguments
for which it is true.

Use Triska's framing: *"in_ Prolog our job is to use horn clauses to state what
holds under what conditions. This is declarative programming because we describe
the situation and we leave it to Prolog to derive logical consequences of our
description."*

**2. Relations vs. functions**

A function maps inputs to outputs. A relation holds (or doesn't) between its
arguments — there is no privileged direction. `append([1,2], [3,4], [1,2,3,4])`
is a relation between three lists. The same definition can:

- Concatenate (given first two, find the third)
- Split (given the third, enumerate all ways to divide it)
- Verify (given all three, confirm they are related)
- Generate (given partial information, enumerate completions)

Show all four modes with a single `append/3` definition. This is the crown
jewel — the moment of insight for imperative programmers.

Use Triska's framing from Meta-Predicates: calling something "find the maximum"
*"is a very imperative way to phrase this task and suggests only one direction
of use"* — instead we want to *"describe the maximum in a list of integers
because we want to be able to generate, test, and complete such lists in all
directions."*

Similarly from Argument Indexing: *"'remove' is very imperative wording and it
suggests only one direction."*

**3. The key question: "when does this hold?"**

Triska's teaching method: when writing a predicate, don't ask "what should the
program do?". Ask "what are the conditions that make this relation true?"

His exact framing: *"We say this holds if — and now we think about it: when
does this hold? So we state the conditions that make this relation true for its
arguments."*

Walk through `list_length/2` using Triska's own reading:
- *"list_length holds for the empty list and 0."*
- *"If list_length holds for [element|LS] and L0, and L is equal to L0 plus 1,
  then list_length holds for these arguments."*

These are **statements**, not instructions. And crucially: *"This way of
reading the code does justice to the full generality of the code because we can
use the code in several directions: to generate, to complete, and also to test
solutions."*

**4. The most general query**

Introduce the diagnostic: call the predicate with all variables. Triska: *"A
query where all arguments are fresh variables is called the most general query
of a predicate. It asks for any case whatsoever for which the predicate holds."*

And: *"when working with Prolog programs it is often a good idea to try the
most general query to see which solutions there are in general."*

Show examples of predicates that pass and fail this test. Demonstrate how the
most general query reveals the true nature of a predicate — whether it is
genuinely relational or secretly directional.

**5. Reading clauses declaratively**

Show how to read any clause as a logical statement:
- Fact: "It is true that parent('alice', 'bob')."
- Rule: "ancestor(X, Y) holds when parent(X, Z) holds and ancestor(Z, Y)
  holds."
- Clauses are logical alternatives: if *any* clause is true, the whole
  predicate is true.

Contrast with the procedural reading. Use Triska's devastating critique:
*"Procedural reading is usually too hard to apply and also isn't able to capture
the full generality of Prolog programs."* And: *"The key drawback of procedural
reading is rather that it's also quite pointless in addition to being hard. [...]
it encourages a procedural view that takes us away from the true generality of
Prolog."*

Also cite the Memory Usage insight: *"We simply cannot go through the code in
the way Prolog does it. [...] this simply doesn't scale."*

**6. Why this matters: generality, correctness, reasoning**

- **Generality**: one definition, many uses. No need to write separate
  "compute", "check", and "generate" functions. We say we are *describing* a
  relation *"because it wouldn't do the code justice to say we only generate
  [...] because we can do more with it — we have a general description and we
  can use it in different modes."* (Dragon Curve)
- **Correctness**: pure predicates can be reasoned about declaratively. Adding a
  constraint can only reduce solutions; removing one can only add solutions.
  This monotonicity property enables declarative debugging.
- **Debugging**: if a predicate gives wrong answers, you can locate the mistake
  by generalizing away goals (Neumerkel's failure slices). This is impossible
  with impure code.
- **Testability**: tests are just queries that should hold or not hold. No mock
  objects, no test harnesses.
- **Working with reasoning, not against it**: *"A very common mistake by Prolog
  programmers is to work against reasoning. Because a decisive property of good
  Prolog code is that it can be reasoned about in several ways."* (Antipatterns)

**7. Naming predicates relationally**

Follow Triska's convention: name predicates after their arguments and the
relation between them, not after what they "do" in one mode.

Triska is explicit: *"The name 'flatten' is already problematic in itself
because it's an imperative and thinking about the relation imperatively already
limits the generality and what we can describe with it."*

| Imperative name | Relational name | Why |
|---|---|---|
| `get_length(List, N)` | `list_length(LIST, N)` | Describes what is related |
| `compute_sum(List, S)` | `list_sum(LIST, SUM)` | No verb implies direction |
| `find_path(A, B, P)` | `path(A, B, P)` | The predicate IS the path relation |
| `check_member(X, L)` | `in_(X, LIST)` | Membership, not checking |

Note: Clausal uses PascalCase for builtins, but user predicates can be
lowercase. The principle is the same: describe the relation, not the action.

For auxiliary predicates with extra arguments: *"I like to use an underscore at
the end of auxiliary predicates especially when a predicate has more arguments
that are not part of the name."* (Meta-Predicates)

**8. "How not what" — a surprising insight**

A common claim about declarative programming is "what not how." Triska's
surprising reversal: *"at least in my opinion this does not adequately
characterize declarative programming. in_ fact we may rightly say the opposite:
'how not what' — because it matters how we express our task, not what is being
executed."* (Knight's Tour)

This means: the *form* of our description matters deeply. A well-chosen
representation, good naming, and relational framing are not cosmetic — they
determine whether the code can be used in all directions.

**9. Common traps for imperative programmers**

- Thinking of clauses as cases in a switch statement (they are logical
  alternatives)
- Thinking of the body as "steps to execute" (they are conditions that must
  hold)
- Thinking of variables as "slots to fill" (they are logical unknowns that
  participate in unification)
- Using arithmetic `is/:=` when constraints would be more general
- Naming predicates with verbs that imply a fixed direction
- Trying to understand execution at the low level — Triska: *"You don't need
  to know any of this to write great Prolog code."* Great code comes *"simply
  by following a few basic principles."* (Memory Usage)


### Page 2: `docs/purity.md` — "Purity and Monotonicity"

Target audience: intermediate users who want to understand *why* certain
patterns are preferred. This is the more advanced counterpart to
`thinking_relationally.md`.

#### Outline

**1. What is logical purity?**

Triska: *"Pure means informally that the program has the properties we expect
from a relation. So for instance a pure program doesn't perform destructive
changes and doesn't have side effects."* (Reading Prolog Code)

Pure predicates:
- Can be used in all directions
- Can have their clauses reordered without changing the set of solutions
- Can have goals in the body reordered (modulo termination)
- Are automatically thread-safe

*"Prolog has a pure monotonic core and we automatically get all desirable
declarative properties as long as we keep to this core."* (Antipatterns)

**2. Monotonicity and the four key properties**

Triska identifies four key properties of the pure monotonic core (Antipatterns):

1. **Monotonicity**: *"Adding a constraint can at most yield fewer solutions,
   never more solutions."*
2. **Commutativity of conjunction**: *"We can rely on A and B to mean the same
   as B and A, so we can exchange goals and therefore also automatically try
   different orders of goals."*
3. **Idempotency**: *"Stating a goal G once means the same as stating it
   several times. So with this property we can automatically eliminate
   duplicated or entailed goals."*
4. **Separability**: *"Clauses and predicates can be read and reasoned about in
   isolation."*

Also from Reading Prolog Code: *"Monotonic means monotonicity of the inference
relation like in logic. This means for example that adding a clause or removing
a goal makes a program at most more general, never more specific."*

Neumerkel's formal test: for a goal G containing subterm S, if there exists a
term T such that `(G, S=T)` succeeds unconditionally but `(S=T, G)` fails,
then G is not monotonic.

Show examples: `dif/2` is monotonic. `not/1` (NAF) is not (demonstrate with
unbound variables). The arithmetic comparison `>` is not (demonstrate with
unbound variable).

**3. Steadfastness**

The dual of monotonicity: for a goal G containing subterm S, if there exists T
such that `(G, S=T)` fails but `(S=T, G)` succeeds, then G is not steadfast.

**4. What breaks purity**

*"The power of Prolog is rooted in the logical properties we ensure, and if we
violate them then we can no longer depend on them and then the core attractions
of Prolog are lost."* (Antipatterns)

What violates purity:
- Negation as failure with unbound variables
- Arithmetic evaluation (`is/:=`) requiring ground arguments
- I/O side effects (but see the declarative output pattern below)
- assertz/retract at runtime
- The cut (Clausal doesn't have one — by design)

**5. Constraints as the pure alternative**

CLP(FD) instead of arithmetic evaluation. `dif/2` instead of `\=`. Reified
if-then-else instead of cut. Show how each impure pattern has a pure
counterpart in Clausal.

**6. Declarative output**

Triska's pattern for keeping I/O pure: *"We don't just write output on the
terminal, because if the output appears only on the terminal then we can't
easily reason about it with Prolog. Instead, we declaratively describe the
output we want to emit, and only then emit it as the very last step."*
(Formatting Output)

This means: build the output as a term, then emit it once. This keeps the
description pure and testable.

**7. Declarative debugging**

Neumerkel's technique: if the program is too general (gives unwanted answers),
add constraints to narrow down which clause is wrong. If too specific (fails
when it shouldn't), generalize goals to find which condition is too strong.

This only works for pure, monotonic programs — another reason purity matters.

**8. Algorithm = Logic + Control**

Triska (N-Queens): *"Clearly n-queens specifies the logic — that is, what must
hold for a solution — and labeling specifies the control — that is, how to
search for solutions."*

And (Faster Labeling): *"We as programmers are of course far more concerned
with the logic. Our goal is to state the logic as clear as we can, and the
control can be changed flexibly outside of the program."*

This separation is only possible with pure code. The N-Queens example shows
how the same pure description can be executed with different labeling
strategies — the logic stays the same, only the control changes.

**9. Practical guidance**

- Use CLP(FD) constraints instead of `:=` where possible
- Use `dif/2` (`is not`) instead of `not (X is Y)`
- Use reified if-then-else instead of NAF for conditional logic
- Name predicates relationally
- Test with the most general query
- Describe output as terms, emit as the last step
- *"Clean data structures aren't only good for semantic reasons but also good
  for performance."* (Memory Usage) — purity and efficiency go hand in hand

---

## Phase 2: Rewrite the Tutorial

The tutorial is the first thing new users read. It must model relational
thinking from the very first paragraph.

### Specific changes

**Opening paragraph** (lines 3-5): Change "walks you through the essentials"
to a more declarative framing. Something like: "This tutorial introduces the
core concepts of logic programming in Clausal: defining relations, querying
them, and understanding how unification connects goals to clauses."

**Section: "Your first .clausal file"** (lines 9-38): Good as-is. The
explanation of facts as "unconditional statements that something is true" is
already relational.

**Section: "Facts and rules"** (lines 42-84):
- Line 65: "`<-` arrow means 'is true if'" — good, keep this.
- Lines 77-84: "Multiple solutions and backtracking" — reframe. Instead of
  "Clausal searches all matching clauses" say "Clausal finds all clauses whose
  heads unify with the goal — these represent logical alternatives." Instead of
  "a rule body fails partway through, it backtracks" say "if a condition in the
  body does not hold, Clausal explores the remaining alternatives."

**Section: "How unification works"** (lines 113-123):
- Line 115: **"Unification is two-way pattern matching"** — this is the exact
  phrase Triska objects to. Unification is NOT "two-way pattern matching";
  pattern matching is a special (one-directional) case of unification.
  Rewrite to: "Unification finds the most general way to make two terms
  identical. Both terms can contain variables, and variables on either side can
  be bound."
- Lines 119-122: "it looks for facts of the form ... and binds CHILD to each
  matching second argument" — procedural. Rewrite: "Clausal searches for
  clauses whose heads unify with the goal. For the query
  `parent("alice", CHILD)`, the clause `parent("alice", "bob")` unifies when
  CHILD is bound to "bob"."

**Section: "Lists"** (lines 127-183):
- Line 138: "`[HEAD, *TAIL]` matches any non-empty list" — say "unifies with".
- **Line 158: "Pattern matching on lists in clause heads"** — **this is the
  exact heading Markus objected to**. Rename to "Describing list relations" or
  "List structure in clause heads."
- Lines 160-161: "You can pattern-match directly in the head of a clause" →
  "Clause heads can describe the structure of list arguments directly."
- Lines 171-172: "The first clause handles the empty list. The second peels
  off HEAD, recurses on TAIL, and adds HEAD to the subtotal." — fully
  procedural. Rewrite: "The first clause states that the sum of the empty
  list is 0. The second states that the sum of [HEAD, *TAIL] is TOTAL when
  the sum of TAIL is SUBTOTAL and TOTAL is SUBTOTAL + HEAD."
- Lines 182-183: "Each clause head matches a different list shape. Clausal
  tries them top-to-bottom and backtracks if a match fails." → "Each clause
  describes a different case in which the relation holds. Clauses are logical
  alternatives — Clausal searches for those whose heads unify with the goal."

**Section: "Arithmetic"** (lines 187-237):
- Largely fine (arithmetic is inherently directional due to `:=`).
- Add a note somewhere: "The `:=` operator evaluates the right-hand side and
  unifies the result with the left. This requires the right-hand side to be
  ground (all variables bound to values). For arithmetic with unbound
  variables, see [CLP(FD) constraints](constraints.md), which work in all
  directions."

**Section: "Negation"** (lines 240-283):
- Mostly good. The warnings about unbound variables are already present.
- Add a brief forward reference to purity: "Negation as failure is inherently
  non-monotonic — adding information can cause a previously successful goal to
  fail. For a monotonic alternative, see `dif/2` for disequality constraints."

**Section: "Graph reachability"** (lines 333-365):
- Lines 352-354: "There are two clauses for reachable/2: the base case (a
  direct edge) and the recursive case (hop through an intermediate node).
  Clausal tries both clauses and returns all paths." → "The first clause
  states that SOURCE and DEST are reachable if there is a direct edge between
  them. The second states that they are reachable if there is an edge from
  SOURCE to some MID and MID reaches DEST. These two clauses are logical
  alternatives — together they define the complete reachability relation."

**New section after "Your first .clausal file"**: Add a brief "Thinking
relationally" callout or paragraph that links to the full
`thinking_relationally.md` page. Something like: "in_ Clausal, each predicate
defines a **relation** — it describes when something is true about its
arguments. This is different from functions, which compute outputs from inputs.
See [Thinking Relationally](thinking_relationally.md) for a deeper exploration
of this idea."

**"Where to go next"**: Add link to `thinking_relationally.md` prominently.

---

## Phase 3: Rewrite Core Reference Pages

### `predicates.md`

- Line 1: "A predicate is a named relation — it describes when something is
  true." — already good! Keep this.
- Line 39: "Multiple facts for the same predicate are tried in order during
  search." → "Multiple facts for the same predicate are logical alternatives.
  Clausal searches for those that unify with the goal, in source order."
- Line 45: "The head is true when all goals in the body succeed" → "The head
  holds when all conditions in the body hold."
- Line 51: "'C is a warm color if color(C, warm) succeeds'" → "'C is a warm
  color if color(C, warm) holds.'"
- Line 65: "Goals are tried left-to-right. If any goal fails, the rule fails
  and Clausal backtracks to try alternatives." → "The conditions in the body
  must all hold for the head to hold. If a condition does not hold, Clausal
  explores the remaining clause alternatives."
- Lines 69-83: "Multi-Clause Dispatch" — rename to "Multiple Clauses" or
  "Clause Alternatives". Remove "dispatch" framing.
- Line 83: "The first clause matches when N is 0. The second clause handles all
  other cases. This is pattern matching by example." → "The first clause holds
  when N is 0 and the factorial is 1. The second clause states the recursive
  relationship. These clauses are logical alternatives."
- Lines 86-95: "Guards" — "They act as filters on the pattern match" →
  "They state additional conditions under which the clause holds."
- Lines 98-109: "Overlapping Patterns" — rename to "Overlapping Clauses" or
  "Clause Ordering." "when multiple clauses could match" → "when multiple
  clause heads unify with the goal."
- Line 150: "This pattern — base case as a fact, recursive case as a rule — is
  the fundamental building block" — fine, keep.
- Line 156: "Recursion is the primary iteration mechanism" → "Recursive
  predicates define relations over inductively structured data (like lists or
  natural numbers)."
- Line 169: "the recursive case destructures [HEAD, *TAIL]" → "the recursive
  clause relates a non-empty list [HEAD, *TAIL] to its length."

### `lists.md`

- Line 3: "Lists are the fundamental data structure in logic programming." —
  fine.
- Line 29: "Head/tail patterns work in clause heads for recursive processing"
  → "Clause heads can describe list structure using [HEAD, *TAIL], relating the
  whole list to its parts."
- Predicate descriptions: Many already use "relates" language. Where they say
  "compute", change to relational framing:
  - Line 109: "compute the length of a list" → "relates a list to its length"
  - Line 118: "0-based indexing. Can enumerate index/element pairs." →
    "relates a 0-based index, a list, and an element."

### `goals.md`

- Audit for procedural language. Goals are conditions that can hold or not
  hold, not steps to execute.

### `syntax.md`

- Line 67: "unification against it always succeeds (matching Python's existing
  convention)" → "unification with it always holds."
- Otherwise mostly fine (it's a reference page, not a teaching page).

---

## Phase 4: Audit All Remaining Pages

Systematically go through every doc page and apply the terminology guide.
Priority order:

1. **constraints.md** — already fairly relational, but some procedural
   language: "fires", "re-evaluated", "posts a constraint". Some of this is
   fine (describing implementation), but the introductory descriptions should
   be relational.
2. **dcg.md** — DCGs have their own framing, but Triska is very specific about
   terminology here: *"We therefore say for example 'the grammar describes a
   sequence' in order to subsume all possible usage modes."* And: *"If we say
   the rule generates a list or the rule consumes a list then we only capture
   specific usage modes even though the same rule can be used in other modes
   too."* Also: *"A good naming convention for non-terminals is to reflect what
   they are describing."* Audit dcg.md for "generates", "consumes", "parses"
   used as the primary framing — these should be secondary to "describes".
3. **tabling.md**, **wfs.md** — mostly technical, but introductions should
   frame relationally.
4. **higher_order.md**, **lambdas.md** — check for "calls", "executes".
5. **exceptions.md**, **control.md** — inherently operational, but can still
   avoid "pattern matching."
6. **reified_ite.md** — important! This is the pure alternative to cuts. Frame
   it as such.
7. **python_integration.md** — bridge page, some procedural language is
   inevitable.
8. **All stdlib module pages** — check predicate descriptions for "computes",
   "returns", "checks".

### Specific patterns to find-and-fix across all pages

Use grep for these patterns:

```
"pattern match"     → rewrite (always)
"matches"           → check context; if clause selection, rewrite
"returns"           → rewrite to relational framing
"checks if"         → "holds when"
"tests whether"     → "holds when"
"handles"           → "holds when" / "describes the case where"
"executes"          → "holds" / "Clausal searches for"
"computes X from Y" → "relates X and Y"
"iterates"          → "holds for each"
"input"/"output"    → check context; may be fine for Python API, not for predicates
```

---

## Phase 5: Index Page and Navigation

### Update `index.md`

- Add "Thinking Relationally" and "Purity and Monotonicity" to the table of
  contents, prominently (near the top, before or just after the tutorial).
- The "What's inside" table should list these under a "Concepts" or
  "Foundations" section header.

### Cross-linking

Every page that introduces a predicate or concept should, where natural, link
to `thinking_relationally.md` or `purity.md`. Key link points:

- Tutorial: after the first example, and in "where to go next"
- Predicates: in the introduction
- Lists: where multi-directional use is shown (append/3)
- Constraints: link to purity.md from the introduction
- Negation: link to purity.md for monotonicity discussion
- Reified ITE: link to purity.md

---

## Phase 6: Examples Audit

Review all `.clausal` example files and test fixtures for imperative naming and
comments. The code itself is fine — it's the comments and test descriptions
that may use imperative language.

Files to check:
- `clausal/examples/*.clausal`
- `tests/fixtures/*.clausal`
- Any inline code examples in docs

---

## Execution Order

| Phase | Scope | Dependencies |
|---|---|---|
| 1a | write `thinking_relationally.md` | None (can start immediately) |
| 1b | write `purity.md` | None (can run parallel with 1a) |
| 2 | Rewrite `tutorial.md` | Phase 1 (needs to link to new pages) |
| 3 | Rewrite `predicates.md`, `lists.md`, `goals.md` | Phase 1 |
| 4 | Audit all other pages | Phase 3 (terminology stabilized) |
| 5 | Update `index.md` and cross-links | Phase 1 |
| 6 | Examples audit | Phase 4 |

Phases 1a and 1b can be done in parallel. Phase 2 and 3 can be done in
parallel. Phase 5 can be done with Phase 2/3.

---

## Key References

### Markus Triska — "The Power of Prolog"

Website: metalevel.at/prolog

Written material:
- "Writing Prolog Programs" — naming conventions, relational thinking
- "Reading Prolog Programs" — declarative vs procedural readings
- "Facets of Prolog" — multi-directional use, generality
- "Logical Purity" — monotonicity, steadfastness, purity
- "Debugging Prolog Programs" — declarative debugging, failure slices
- "Basic Concepts" — terminology, "what holds"
- "Horror Stories" — why impure constructs destroy generality

Video lectures (subtitles in `/workspace/subtitles/`):

| Video | Key insights for docs rewrite |
|---|---|
| Reading Prolog Code | Declarative vs procedural reading; "holds for"; most general query; purity definition |
| A Tour of Prolog | "when does this hold?"; horn clauses; state relations; embedding procedural in declarative |
| Prolog Antipatterns | Reasoning properties (4 key); "flatten" naming critique; cut destroys power; working against reasoning |
| Meta-Predicates in Prolog | "Describe the maximum" not "find the maximum"; multi-directional use; auxiliary naming |
| Describing a Dragon Curve | "Describing" as master verb; why we don't say "generate" |
| Describing a Knight's Tour | "How not what" reversal; naming relations; correct mental model |
| Describing Domino Tilings | Languages for expressing problems; auxiliary naming convention |
| DCGs | "Describes a sequence"; naming non-terminals; generality of grammar rules |
| N-Queens in Prolog | Logic + control separation; correlation vs search; same program, different queries |
| Faster Labeling for N-Queens | Pure monotonic core enables control flexibility; declarative generality |
| Argument Indexing | "Remove is imperative wording"; clean data structures; indexing preserves generality |
| Collatz Conjecture | Naming relations (integer_next → collatz_next); multi-directional use with constraints |
| Memory Usage of Prolog | Beginners write great code; don't think at VM level; declarative reasoning scales |
| Preparing Prolog | Edinburgh mistake (silent failure vs instantiation error); si predicates; monotonicity |
| Prolog Queries and Answers | Most general query definition; provability vs truth; answers equivalent to queries |
| The Prolog Toplevel | Goal clauses; refutation; answers as terms |
| Horn Clauses | "State what holds"; programming as theory building (Naur reference) |
| Predicate Logic | Predicates express relations; most general query; monotonicity of entailment |
| Logic | Formal foundations |
| Formatting Output | Declarative output description; reasoning about output; extra-logical effects |
| Clean vs Defaulty | Clean representations; symbolic distinction; performance + correctness alignment |
| Cryptography with Prolog | Correctness over speed; invulnerable systems; symbolic reasoning |
| Datalog | Executable specifications; execution strategies; code = data; syntax matters |
| Meta-interpreters | Clean representations for meta-interpretation; defaulty pitfalls |
| List Differences | Pure relations in all directions |
| Pairs in Prolog | Data representation choices |

### Ulrich Neumerkel

- Failure slices (1999 PPDP paper) — finding non-termination declaratively
- library(reif) — if_/3 for pure conditionals (with Stefan Kral)
- "Indexing dif/2" (arXiv:1607.01590, with Stefan Kral)
- GUPU teaching system (TU Wien, since 1991) — side-effect-free teaching
- ISO/IEC JTC1 SC22 WG17 Convenor — Prolog standardization
- "Declarative Language Extensions for Prolog Courses" (2008, with Triska & Wielemaker)
- "Programming as Theory Building" — Peter Naur (recommended by Triska in Horn Clauses video)
