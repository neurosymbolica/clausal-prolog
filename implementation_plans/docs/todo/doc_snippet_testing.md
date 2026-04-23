# Doc Snippet Testing

Every `# skip` code block in `docs/*.md` is an untested documentation snippet
that can silently drift from the actual implementation. There is currently no
mechanism to verify that doc examples are backed by real tests.

## Problem

- Doc snippets use `# skip` to opt out of execution, but nothing checks that
  an equivalent test exists in a `.clausal` fixture file.
- Snippets can become wrong after renames, signature changes, or predicate
  removals without anyone noticing.
- This affects all wrapper docs (`torch.md`, scipy modules, etc.), not just
  one phase.

## Possible approaches

1. **Runnable doc snippets.** Remove `# skip` and give each snippet a proper
   `Test("doc: ...")` wrapper and imports so the doc tooling executes them
   directly. Downside: verbose, every snippet needs full boilerplate.

2. **Doc-test extraction.** A tool that extracts fenced clausal blocks from
   markdown, wraps them in a test harness, and runs them. Like Python's
   `doctest` but for `.clausal`. The `# skip` marker would be replaced by
   the tool auto-wrapping each block.

3. **Cross-reference check.** A linter that scans `# skip` blocks for
   predicate calls and verifies each one appears in at least one `.clausal`
   fixture test. Lighter-weight than running them, but only checks coverage,
   not correctness.

4. **Inline fixture references.** Each `# skip` block includes a comment like
   `# see: torch_comparison_tests.clausal:"eq element-wise"` pointing to the
   backing test. A CI check verifies the referenced test exists.

## Scope

Affects every `docs/*.md` file that contains `# skip` code blocks.
