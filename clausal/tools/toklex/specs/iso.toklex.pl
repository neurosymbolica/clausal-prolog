% clausal: no-collect
% iso.toklex.pl — ISO Prolog token layer, matching clausal/tools/prolog_tokenizer.py
% dialect choices: '_' digit separators, nested block comments (nesting is
% a driver flag, not a spec change).
%
% 2026-10-15 (Ulrich conformity pass, clausal-bug-fix lane): the escape and
% number grammars below were TIGHTENED to match ISO 6.4.2.1's closed
% escape-sequence set and the ISO <integer>/<float number> token grammar's
% lowercase-only radix/exponent letters and mandatory fraction part. This
% file previously advertised "lenient unknown escapes, 1e5 floats" here as
% deliberate dialect choices; per-clause review against the standard's
% grammar text (not just Ciao's iso_tests_parsing_lexing corpus) found
% these were defects, not dialect choices, for the NATIVE ISO reader this
% spec compiles. `clausal.toklex.pl` (the separate Clausal surface
% dialect) is NOT touched for the escape grammar -- see its own header for
% why it isn't trying to be ISO-conformant here -- but IS tightened for the
% number grammar below, since that half was accidental duplication of this
% same non-dialect-specific grammar, not a deliberate difference (see that
% file's "kept in sync with iso.toklex.pl" comments on hex_int/oct_int/bin_int).
encoding(chars).

class(layout,    [' ', '\t', '\n', '\r', '\f', '\v']).
class(small,     range(a, z) + unicode('Ll')).
class(capital,   range('A', 'Z') + unicode('Lu')).
class(digit,     range('0', '9')).
class(alnum,     class(small) + class(capital) + class(digit) + ['_']).
class(graphic,   ['#','$','&','*','+','-','.','/',':','<','=','>','?','@','\\','^','~']).
class(hexdig,    class(digit) + range(a, f) + range('A', 'F')).
class(octdig,    range('0', '7')).
class(bindig,    ['0', '1']).
class(quote,     ['''']).
class(dquote,    ['"']).
class(bslash,    ['\\']).
class(nl,        ['\n']).
class(sign,      ['+', '-']).
% ISO 6.4.2.1's quoted-token content excludes raw layout text other than
% space -- a literal (unescaped) tab/newline/CR/FF/VT byte inside a quoted
% atom or string is a syntax error; only `\<newline>` (continuation) or a
% named escape (`\n`, `\t`, ...) may stand for one. Space itself is a
% distinct, explicitly-permitted literal, so it is NOT in this set.
class(ctrl_layout, layout - [' ']).
% ISO 6.4.2.1 Table 2's CLOSED set of symbolic escape sequences: exactly
% these ten single-char-after-backslash forms (plus the octal/hex/
% continuation forms handled separately below). `\e` (ESC) and `\s`
% (space) are SWI/non-ISO extensions and are deliberately NOT in this set
% -- `\e`/`\s`/`\c`/anything else after a backslash is not a valid escape
% at all and must raise a syntax error, not be kept verbatim.
class(symbolic_escape, ['a','b','f','n','r','t','v','\\','''','"','`']).

% `escape` (unlooped, combined octal/hex/simple form) is kept ONLY for
% char_code's `0'\...` construct, where the driver's ordinary longest-match
% (not qitem*/ditem*-style repetition) already resolves greedily without
% any adjacency ambiguity -- there is nothing after a `0'`-escape's optional
% closing backslash to be confused with a "next" escape, since char_code is
% a single escape, not a repeated sequence of them. See the quoted_atom/
% string grammar surgery below for the repeated case, where this shape DOES
% create a real ambiguity.
%
% `any - nl`: a backslash-newline is the continuation escape, which stands
% for NO character, so `0'\<newline>` names no code and is not a
% char_code token. Excluding it lets maximal munch back up to the integer
% `0`, leaving the quote to open a quoted token in which the continuation
% is read (Ulrich's conformity row #213, `X is 0'\<newline>+'1.` -> X = 1).
%
% NOT narrowed to `symbolic_escape` here (2026-10-15 pass): unlike
% quoted_atom/string's `esc_other`, this grammar-level leniency is already
% caught one layer down -- `char_code`'s builder (`builders.char_code`)
% decodes the escape and raises unless the result is EXACTLY one
% character, so `0'\q` (and `0'\141` missing its closing backslash
% decoding to a single char) already raise a positioned TokenizeError
% today (see tests/toklex/test_parity.py's MALFORMED_INPUTS /
% test_unknown_escape_in_char_code_raises_positioned_error). Narrowing the
% grammar here too would be redundant belt-and-suspenders for the same
% outcome, not a behavior change, so it's left alone to keep this change
% targeted to the construct that actually has the bug (the repeated
% qunit*/dunit* case below, where the lenient fallback silently keeps
% backslash+char as 2 literal chars instead of raising).
def(escape,   bslash then ( octdig then octdig* then bslash?
                          | 'x' then hexdig then hexdig* then bslash?
                          | (any - nl) )).
def(udigits,  digit then (digit | '_')*).
% ISO's <float number> exponent letter and the radix letters in
% <integer>'s 0x/0o/0b forms (see hex_int/oct_int/bin_int below) are
% lowercase-only terminals in the token grammar -- 'E'/'X'/'O'/'B' are not
% part of any number token at all. Previously accepted here as a lenient
% extension; removed 2026-10-15 (Ulrich conformity pass).
def(exp,      'e' then sign? then digit then digit*).

% ── quoted_atom / string escape grammar ──────────────────────────────────
%
% 2026-10-15 (Ulrich conformity pass): ISO 6.4.2.1 requires an octal/hex
% escape's closing backslash (`\NNN\`, `\xHH\`) -- it is NOT optional, so
% `'\141'` (no closing backslash before the delimiter) must be a syntax
% error, not octal 141. This retires the ENTIRE `esc_open_hex`/
% `esc_open_oct`/`qplain_no_hex`/`qplain_no_oct`/`dplain_no_hex`/
% `dplain_no_oct` apparatus that earlier rounds (Task 10, rounds 1-4) built
% to support an optional-closing-backslash reading without ambiguity: with
% the closing backslash now mandatory, only `esc_term` is needed, and
% `esc_term` was ALREADY unambiguous on its own (its mandatory trailing
% backslash pins the digit run's length exactly -- a shorter digit run
% would leave a non-backslash character where the backslash is required,
% so it simply fails to match; there is no rival shorter-digit-run parse
% to disambiguate against, unlike the old optional-close case). See git
% history (`git log -p` on this file) for the retired rules' full
% round-1-4 derivation if the shape ever needs resurrecting.
%
% `esc_other` is also narrowed here (Bug 1a): previously `bslash then (any
% - octdig - 'x')`, i.e. ANY character after a backslash that isn't a
% digit/`x` was accepted as a "lenient unknown escape" and kept verbatim
% (backslash + char, 2 literal chars) by the builder. ISO 6.4.2.1's escape
% set is CLOSED -- `\c`, `\e`, `\s`, an incomplete `\u1`, etc. are not
% escape sequences at all and must be syntax errors. Narrowed to exactly
% the closed `symbolic_escape` set plus the backslash-newline continuation
% (`nl`) -- the only two things `\<char>` may still mean here.
def(esc_term,      bslash then ( (octdig then octdig* then bslash)
                                | ('x' then hexdig then hexdig* then bslash) )).
def(esc_other,     bslash then (symbolic_escape | nl)).

% Bug 1b: ISO 6.4.2.1's quoted-token content excludes raw layout bytes
% other than space (see `ctrl_layout` above) -- a literal, unescaped
% newline/tab/CR/FF/VT inside a quoted atom or string is now excluded from
% `qplain`/`dplain` (previously only `quote`/`bslash` were excluded, so a
% raw newline byte was silently accepted as 1 literal char).
def(qq,     quote then quote).
def(qplain, (any - quote - bslash - ctrl_layout)).
def(qunit,  (qq | esc_term | esc_other | qplain)).

def(dqq,    dquote then dquote).
def(dplain, (any - dquote - bslash - ctrl_layout)).
def(dunit,  (dqq | esc_term | esc_other | dplain)).

token(lparen,   '(').
token(rparen,   ')').
token(lbracket, '[').
token(rbracket, ']').
token(lcurly,   '{').
token(rcurly,   '}').
token(bar,      '|').
token(comma,    ',').
token(cut,      '!').
token(semicolon, ';').
token(end,      '.' followed_by (layout | '%' | eof)).
token(variable, (capital | '_') then alnum*).
token(name_atom, small then alnum*).
token(char_code, '0' then quote then (quote then quote | escape | (any - bslash))) value char_code.
% hex_int/oct_int/bin_int require at least one REAL digit somewhere in the
% run (underscores alone don't count) -- `'_'* then hexdig then (hexdig |
% '_')*` generates exactly the language "any string over {hexdig,'_'} that
% contains >=1 hexdig", matching the old hand-written tokenizer's rule
% (collect the whole digit-or-'_' run, then `int(run.replace('_',''), 16)`,
% which raises on an all-underscore run). `0x_1`/`0x1_` still match (>=1
% real digit present); `0x_` does not, so maximal munch backs up to `0`
% (integer) + a fresh name_atom for `x_` -- the same ratified 0x./1.5e.
% shape (Task 10 divergence set), extended here to the underscore-only
% case; see tests/toklex/test_parity.py's EXPECTED_DIVERGENCES.
%
% Bug 2 (2026-10-15, Ulrich conformity pass): the radix letters in ISO's
% <integer> token grammar (`x`/`o`/`b`) and the exponent letter in
% <float number> (`e`, in `exp` above) are lowercase-only terminals --
% `0X1`/`0O17`/`0B101`/`1E9` are not number tokens at all under ISO, so
% the uppercase alternatives (previously `('x'|'X')` etc.) are removed.
% Maximal munch then falls back exactly the way it already does for
% `0x.`/`1.5e.` (see EXPECTED_DIVERGENCES above): with no hex_int match,
% `0X1` lexes as `integer` `0` followed by `X1` as a fresh token -- here a
% VARIABLE (capital-initial), not an atom, since `variable` (capital then
% alnum*) is the rule that actually claims a capital-led run in this
% grammar; same for `1E9` -> `integer` `1` then VARIABLE `E9`.
token(hex_int,  '0' then 'x' then '_'* then hexdig then (hexdig | '_')*) value int_16.
token(oct_int,  '0' then 'o' then '_'* then octdig then (octdig | '_')*) value int_8.
token(bin_int,  '0' then 'b' then '_'* then bindig then (bindig | '_')*) value int_2.
% Bug 3 (2026-10-15, Ulrich conformity pass): ISO's <float number> is
% <integer part> . <fraction part> [<exponent part>] -- the decimal point
% and fraction are MANDATORY; an exponent can never appear without them.
% The old second alternative (`udigits then exp`, no '.') let `1e9` lex as
% the float 1000000000.0 with no fractional part at all. Removed outright:
% `1.5e9` (has the mandatory `.5`) still matches the first alternative
% unchanged, but `1e9` (no '.') now fails `float_num` entirely, and
% maximal munch falls back to `integer` `1` followed by a fresh token for
% `e9` -- `e` is lowercase/small-initial, so that's a NAME_ATOM `e9`
% (matching `name_atom`'s `small then alnum*`), available to be parsed as
% e.g. a postfix operator atom rather than silently fused into the number.
token(float_num, (udigits then '.' then udigits then exp?)) value float_of.
token(integer,  udigits) value int_10.
token(quoted_atom, quote then qunit* then quote) value quoted_atom_val.
token(string,   dquote then dunit* then dquote) value string_val.
token(graphic_tok, graphic then graphic* but_not ('/' then '*' then any*)).

trivia(whitespace, layout then layout*).
trivia(line_comment, '%' then (any - nl)*).
trivia(block_comment, '/' then '*' then body('*' then '/')) nest self.
