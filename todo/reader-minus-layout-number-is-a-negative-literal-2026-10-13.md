# Reader: "- 1" (layout between - and a number) is the negative literal (Ulrich conformity, WDCor4)

Ruled (operator, 2026-10-13): Ulrich Neumerkel's conformity suites are the gold standard.
The syntax suite (https://www.complang.tuwien.ac.at/ulrich/iso-prolog/conformity_testing) gives:
- #56  `integer(- 1).`        succeeds: "- 1" with layout IS the integer -1
- #174 `-1 = -0x1.`           succeeds
- #286 `(- (1)) = -(1).`      succeeds: "-" + layout + "(" is the COMPOUND -(1) (footnote: WDCor4)
- #288 `(- 1^2) = ^(-1,2).`   succeeds: the collapse also happens inside a larger expression
- #135 `writeq(-(1)).`        prints `- (1)` (Cor.3 7.10.5(h_2)). Clausal's writer ALREADY does this, so loosening the reader reopens no round-trip.

Rule: "-" + optional layout + a bare number token gives the negative literal. "-" + optional layout + "(" gives the prefix operator applied to a parenthesised term.

Fix shape: the negative-literal checks in prolog_parser.py (`_parse_prefix` and the other site) are gated on `self._adjacent(tok, nxt)`. Loosen that to allow optional layout for this literal-collapse branch only. The `nxt.type in (INTEGER, FLOAT)` check already excludes "(". Audit the other `_adjacent` call sites before touching them.

History: F037 (todo/audit-2026-07-05/done/fix-A11-prolog-token-spans.md, citing ISO 6.3.1.2) required adjacency to fix a write/read round trip. WDCor4 supersedes that reading. Re-run F037's round-trip test after the change.

Consequence: number_chars(- 1,"- 1") succeeds (number_chars_cont #91). Also check the native ISO reader (toklex/Pratt), not only the translator's parser.
