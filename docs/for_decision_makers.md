# Clausal for Decision Makers

This page is for non-technical stakeholders — project managers, CTOs, product
owners, compliance officers — who need to understand what Clausal is and why it
matters for their organisation.

No code. Just the business case.

---

## What is Clausal?

Clausal is a logic programming system embedded in Python. It lets developers
write **rules** — formal statements about what is true under what conditions —
and have the computer automatically reason about them: finding solutions,
checking validity, and exploring possibilities.

It is not a replacement for Python. It is a complement: Python handles
computation, data, and I/O; Clausal handles reasoning, rules, and constraints.
They run together on the same runtime with no overhead.

---

## Why should you care?

### 1. Explainability reduces risk

When a traditional program makes a decision, the "why" is buried in layers of
imperative code — loops, conditionals, state mutations. Extracting the
reasoning requires a developer to trace through the execution manually.

In Clausal, the rules **are** the explanation. Each rule reads as a sentence:
"A customer is eligible for a discount if they have been a member for more than
two years and their annual spend exceeds $10,000." The gap between the business
rule and the code is near zero.

This matters for:

- **Regulatory compliance.** Auditors can read the rules directly and verify
  they match the policy. No reverse-engineering of source code.
- **Dispute resolution.** When a customer asks "Why was I denied?", the system
  can trace its reasoning through the rules and provide a clear answer.
- **Liability.** If a decision is challenged, the organisation can demonstrate
  exactly which rules were applied and why. The reasoning is not a black box.

### 2. Reliability decreases costs

Logic programs have formal properties that imperative programs do not.
Specifically, pure logic programs guarantee:

- **Monotonicity**: adding a new rule can only extend what the system knows,
  never silently break existing behaviour. This means incremental changes are
  safe.
- **Separability**: each rule can be read and verified in isolation. A change
  to one rule does not affect others. This reduces the cost of code review and
  testing.
- **No hidden state**: there are no mutable variables, no global state, no
  race conditions. The same inputs always produce the same outputs.

The practical effect: fewer bugs, cheaper testing, safer deployments. The
industry average cost of fixing a production bug is 30 times the cost of fixing
it in development. Logic programming reduces the number that reach production.

### 3. Rules change faster than code

Business rules evolve. Regulations change. Policies are updated. In a
traditional system, changing a rule means modifying imperative code, testing
it, reviewing it, and deploying it. The rule is entangled with the code that
implements it.

In Clausal, rules are separate from the engine that executes them. Changing a
rule means changing a logical statement. The impact is bounded and predictable.
Testing is cheap — a test is just a question: "Does this hold?"

This is particularly valuable in domains where rules change frequently:
insurance underwriting, tax calculation, compliance screening, eligibility
determination, access control.

### 4. Constraint solving replaces custom search

Many business problems are constraint satisfaction problems in disguise:
employee scheduling, resource allocation, configuration management, route
optimisation, capacity planning.

In a traditional approach, these require custom algorithms — expensive to
develop, hard to maintain, and brittle when requirements change. Clausal
includes built-in constraint solvers (CLP(ℤ), CLP(B), CLP(ℝ)) that let
developers describe the constraints and have the system find solutions
automatically.

Describe what a valid schedule looks like. The system finds one.

### 5. Complementary to machine learning

Machine learning excels at pattern recognition in noisy, unstructured data —
images, natural language, sensor readings. But ML models are opaque, expensive
to run, and impossible to formally verify.

Logic programming excels at structured reasoning — applying rules, checking
constraints, deriving consequences. It is transparent, cheap to run, and
formally verifiable.

The most powerful systems combine both:

| ML handles | Logic handles |
|---|---|
| Image recognition | Object classification rules |
| Natural language understanding | Policy application |
| Anomaly detection | Root cause analysis |
| Prediction | Decision rules and compliance |
| Recommendation scoring | Eligibility and constraint checking |

Clausal runs natively in Python — the lingua franca of ML — making this
combination natural. No separate systems, no data marshalling, no integration
overhead.

### 6. Rules as code

Governments, regulators, and large organisations are increasingly interested
in "rules as code" — encoding legislation, regulations, and policies in
machine-executable form. This enables:

- **Automated compliance checking**: does this transaction satisfy all
  applicable regulations?
- **Policy simulation**: if we change this rule, what cases would be affected?
- **Consistency verification**: are there contradictions in our rule set?
- **Citizen-facing explanation**: why was this application approved or denied?

Logic programming is the natural technology for rules-as-code because the
rules **are** the code. There is no translation layer between the policy
document and the executable system.

---

## What does adoption look like?

### Low risk, incremental adoption

Clausal is not an all-or-nothing proposition. It embeds in existing Python
projects:

1. **Start with one rule set.** Pick a domain where business rules are
   complex and change frequently — eligibility, pricing, compliance. Encode
   those rules in Clausal.
2. **Keep the rest in Python.** The data pipeline, the API, the UI — all
   stay the same. Clausal handles just the reasoning layer.
3. **Expand as value proves out.** As the team gains confidence, move more
   rule-heavy logic into Clausal.

### Developer availability

Clausal uses Python syntax. Any Python developer can learn it. The learning
curve is steeper than a new library but shallower than a new language, because
the syntax, tooling, and runtime are all familiar.

For organisations with Prolog expertise, the transition is even faster — the
concepts are identical, only the surface syntax differs.

### No new infrastructure

Clausal is a Python package. It runs wherever Python runs: local machines,
Docker containers, cloud functions, CI pipelines. No new servers, no new
databases, no new deployment processes.

---

## The bottom line

| Concern | Traditional approach | With Clausal |
|---|---|---|
| **Explainability** | Trace through imperative code | Read the rules directly |
| **Rule changes** | Modify, test, review, deploy code | Change a logical statement |
| **Testing** | Test harnesses, mocks, fixtures | A test is a question |
| **Compliance** | Manual audit of source code | Auditors read the rules |
| **Constraint problems** | Custom algorithms | Describe constraints; system solves |
| **ML integration** | Separate systems, data marshalling | Same Python runtime |
| **Adoption risk** | All-or-nothing rewrite | Incremental, one module at a time |

---

*For a technical introduction, see the [Tutorial](tutorial.md).*

*For the conceptual foundations, see
[Thinking Relationally](thinking_relationally.md).*
