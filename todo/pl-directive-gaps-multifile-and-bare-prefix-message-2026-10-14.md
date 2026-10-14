# .pl directives: `multifile/1` is unknown; the bare-prefix `dynamic` message isn't actionable

Found in the Fable review of the D43 flip. Both are pre-existing and behave the same under both front ends.

- **`:- multifile(p/1).` is reported as "unknown directive" and fails the whole file.** ISO 7.4.2.3 defines multifile/1 and Scryer accepts it. Also refused by both front ends:
  - text after `end_of_file.` (Scryer stops reading there);
  - `:- include/1`.
- **`:- dynamic counter/1.` (bare prefix spelling) gives "Expected '.', got 'atom' ('counter') at 1:12".** The same happens for `multifile`, `discontiguous`, `table` and `meta_predicate`. Rejecting it is correct: ISO Table 7 and Scryer have no prefix operator for these, and Scryer raises `syntax_error(incomplete_reduction)`. But the message doesn't help. Add a hint: "write `:- dynamic(counter/1).`". The canonical spelling already loads.
