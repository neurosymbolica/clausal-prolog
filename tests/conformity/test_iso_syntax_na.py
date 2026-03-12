"""ISO Prolog conformity tests: syntax — NOT APPLICABLE to clausal.

Source: https://www.complang.tuwien.ac.at/ulrich/iso-prolog/conformity_testing
(365 test cases for ISO/IEC 13211-1:1995)

Clausal uses Python syntax, so the entire Prolog lexer/parser surface area
is irrelevant.  This file enumerates the categories with representative
original test numbers so the coverage gap is documented, not hidden.

Categories and why they don't apply
────────────────────────────────────

1. writeq/1, write_canonical/1, write_term/2  (tests 1,6-10,13-18,28-37,
   40,135-156,181-192,215-218,222-223,234,236,238-260,264,266-269,274-283,
   290-298,304-310,318-319,322-337,341-365)

   Prolog term writing and round-tripping. Clausal terms are Python objects;
   their repr() is Python's.

2. Escape sequences in atoms / strings  (tests 1-26,100-113,228-232,269,
   284,300-301,315-317,339)

   Python handles string escapes: \\n, \\t, \\x41, etc.  No Prolog-style
   \\141\\ octal or 0'X character-code syntax.

3. Character codes / char_code  (tests 19,21,123-130,177,225,270-271)

   Python uses ord() and chr().  No 0'X syntax.

4. Number literal syntax  (tests 43-54,121-122,172-176,272,363)

   Python handles 0x, 0o, 0b, float, scientific notation natively.
   No Prolog-style 0X1 (upper-case X error), 2'1 (base syntax), etc.

5. Operator declarations — op/3  (tests 42,45,49-52,63,118-120,131-134,
   142,157-158,166-168,195,215,237,265,268,334,340,347)

   Clausal has no user-defined operators.  Python operators (and, or, not,
   is, :=, <, >, etc.) are fixed.

6. Prefix operator parsing  (tests 56-64,135-140,180,182-185,188-192,
   216,260,274-275,286-288)

   Python parses -1 as a negative literal.  No Prolog fy/fx distinction.

7. Quoting / atom syntax  (tests 38-41,100-113,165,198-199,264,302,324)

   Python strings are quoted with "" or ''.  Prolog atom quoting rules
   (backslash-quote, backtick, single-quote doubling) don't exist.

8. Comment syntax  (tests 186-187,258,307)

   Python uses # for line comments.  No /* */ block comments in source.
   (Note: Prolog block-comment nesting edge cases are N/A.)

9. List dot-syntax / cons-cell representation  (tests 32,34,68,141-144,
   194,219,221,285,298,320,337,348)

   Clausal uses Python lists.  No dot-pair (./2) representation.
   [H|T] in Prolog corresponds to [H, *T] in clausal head patterns.

10. DCG notation (-->)  (test 181)

    No DCG support in clausal.

11. $VAR / numbervars  (tests 145-146,244-247,289,296,355)

    Not applicable.  Clausal has its own Var() representation.

12. Curly braces / {} syntax  (tests 189-190,268,294-295,309-310,325,
    351,356,359)

    Python dicts, not Prolog {} terms.

Semantic tests extracted from the syntax suite
──────────────────────────────────────────────

A small number of the 365 tests touch on semantics (unification, type
checks).  Those are ported to other files in this package:

- integer(- 1)  (test 56)  → test_iso_type_checking.py
- [a|[]] = [a]  (test 219) → test_iso_unification.py
- -1 = -0x1     (test 174) → test_iso_unification.py
- t(0b1,0o1,0x1) = t(1,1,1) (test 175) → test_iso_unification.py
"""
