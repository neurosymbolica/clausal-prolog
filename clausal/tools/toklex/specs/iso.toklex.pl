% iso.toklex.pl — ISO Prolog token layer, matching clausal/tools/prolog_tokenizer.py
% dialect choices: '_' digit separators, lenient unknown escapes, 1e5 floats,
% nested block comments (nesting is a driver flag, not a spec change).
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

% `escape` (unlooped, combined octal/hex/simple form) is kept ONLY for
% char_code's `0'\...` construct, where the driver's ordinary longest-match
% (not qitem*/ditem*-style repetition) already resolves greedily without
% any adjacency ambiguity -- there is nothing after a `0'`-escape's optional
% closing backslash to be confused with a "next" escape, since char_code is
% a single escape, not a repeated sequence of them. See the quoted_atom/
% string grammar surgery below for the repeated case, where this shape DOES
% create a real ambiguity.
def(escape,   bslash then ( octdig then octdig* then bslash?
                          | 'x' then hexdig then hexdig* then bslash?
                          | any )).
def(udigits,  digit then (digit | '_')*).
def(exp,      ('e' | 'E') then sign? then digit then digit*).

% ── quoted_atom / string escape grammar (Task 10 round 4 surgery) ───────
%
% Round 1-3 found a real ambiguity in the old, unlooped `escape` def when
% used inside a REPEATED qitem*/ditem* body: after a digit/hex escape's
% run of digits, an immediately-following backslash is genuinely ambiguous
% between "this escape's own optional closing backslash" and "the leading
% backslash of the NEXT escape" (whose lenient `any` fallback can then
% swallow the quoted_atom/string's own closing delimiter, e.g. `'\x41\'.`).
%
% `prolog_tokenizer.py`'s actual behavior resolves this with no ambiguity
% at all, because its `_read_escape` is a simple, irrevocable, 1-character
% lookahead: after reading a digit/hex escape's digits, if the very next
% character is a backslash, it is ALWAYS consumed as this escape's
% terminator -- full stop, no reconsideration, never re-interpreted as the
% start of a different construct, and the digit run itself is always read
% maximally (a plain `while peek() in hexdigits: advance()` scan -- it
% never stops early). The fix here states that rule DECLARATIVELY in the
% grammar (R5: derived, not hand-maintained): an unterminated digit/hex
% escape run may NOT be immediately followed by another backslash-led item
% in the SAME repetition step, AND its own digit run must be MAXIMAL (not
% merely "some prefix of the available digits") wherever it's used without
% a mandatory closing backslash.
%
% `esc_term`      -- a digit/hex escape WITH its closing backslash
%                    consumed: a complete, self-contained qunit/dunit on
%                    its own. No ambiguity: the mandatory trailing bslash
%                    pins the digit run's length exactly (a shorter digit
%                    run would leave a non-backslash character where the
%                    mandatory bslash is required, so it fails to match).
% `esc_open_hex`/
% `esc_open_oct`  -- the SAME escape WITHOUT a closing backslash. Used in
%                    two places: (a) at the very end of qunit*/dunit*
%                    (see the token rules below), where "what comes next"
%                    is unambiguously the closing delimiter; (b) mid-qunit*
%                    followed by `qq` (a doubled delimiter) or `qplain`
%                    (an ordinary character) -- e.g. `'\x41 b'`, a hex
%                    escape with no closing backslash immediately followed
%                    by ordinary content. Case (b) is exactly where round
%                    4's FIRST attempt at this surgery still had a hole:
%                    `hexdig*`/`octdig*` can stop at ANY prefix of the
%                    available digits, not just the maximal one -- so
%                    `'\x41\'` could ALSO be read as
%                    `esc_open_hex="\x4"` (digit run stopped after just
%                    "4") `then qplain='1'` (the leftover "1" reinterpreted
%                    as ordinary content) `then` a FRESH qunit starting at
%                    the interior backslash, which `esc_other` then reads
%                    as an "unknown escape" whose argument is the real
%                    closing quote -- reproducing the exact swallowed-
%                    delimiter bug through a different split of the SAME
%                    input. Closed by pairing `esc_open_hex`/`esc_open_oct`
%                    ONLY with `qplain_no_hex`/`qplain_no_oct` (`qplain`
%                    with the corresponding digit class ALSO excluded): a
%                    non-maximal digit-run split always leaves a
%                    hexdig/octdig character immediately after it (that's
%                    what "non-maximal" means -- there's more of the same
%                    digit class still there to consume), and
%                    `qplain_no_hex`/`qplain_no_oct` refuse to match that
%                    character, so only the maximal split survives. The
%                    trailing, before-the-closing-delimiter position (the
%                    token rules' own `(esc_open_hex | esc_open_oct)?`)
%                    doesn't need this treatment: what follows there is
%                    always `then quote`/`then dquote`, never qplain/qq,
%                    so a non-maximal split just fails outright (a leftover
%                    digit character is never a delimiter).
% `esc_other`     -- everything else `\c` can mean (`\'`, `\"`, `\\`,
%                    `\n`, line continuation, and the lenient "unknown
%                    escape, kept verbatim" fallback) -- deliberately
%                    excludes octdig/`x` so it never competes with
%                    esc_term/esc_open_hex/esc_open_oct for the same input.
def(esc_term,      bslash then ( (octdig then octdig* then bslash)
                                | ('x' then hexdig then hexdig* then bslash) )).
def(esc_open_hex,  bslash then 'x' then hexdig then hexdig*).
def(esc_open_oct,  bslash then octdig then octdig*).
def(esc_other,     bslash then (any - octdig - 'x')).

def(qq,            quote then quote).
def(qplain,        (any - quote - bslash)).
def(qplain_no_hex, (any - quote - bslash - hexdig)).
def(qplain_no_oct, (any - quote - bslash - octdig)).
def(qunit,         (qq | esc_term | esc_other | qplain
                    | (esc_open_hex then (qq | qplain_no_hex))
                    | (esc_open_oct then (qq | qplain_no_oct)))).

def(dqq,           dquote then dquote).
def(dplain,        (any - dquote - bslash)).
def(dplain_no_hex, (any - dquote - bslash - hexdig)).
def(dplain_no_oct, (any - dquote - bslash - octdig)).
def(dunit,         (dqq | esc_term | esc_other | dplain
                    | (esc_open_hex then (dqq | dplain_no_hex))
                    | (esc_open_oct then (dqq | dplain_no_oct)))).

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
token(hex_int,  '0' then ('x' | 'X') then '_'* then hexdig then (hexdig | '_')*) value int_16.
token(oct_int,  '0' then ('o' | 'O') then '_'* then octdig then (octdig | '_')*) value int_8.
token(bin_int,  '0' then ('b' | 'B') then '_'* then bindig then (bindig | '_')*) value int_2.
token(float_num, (udigits then '.' then udigits then exp?
               | udigits then exp)) value float_of.
token(integer,  udigits) value int_10.
% `(esc_open_hex | esc_open_oct)?` immediately before the closing
% delimiter: an escape run with no closing backslash yet consumed is fine
% to end the token on -- what follows IS unambiguously the delimiter here
% (there's nothing else it could be), unlike mid-qunit* where a
% non-maximal digit run would collide with the next qunit (see the
% `qplain_no_hex`/`qplain_no_oct` comment above for why THAT position
% needs the extra restriction and this one doesn't).
token(quoted_atom, quote then qunit* then (esc_open_hex | esc_open_oct)? then quote) value quoted_atom_val.
token(string,   dquote then dunit* then (esc_open_hex | esc_open_oct)? then dquote) value string_val.
token(graphic_tok, graphic then graphic* but_not ('/' then '*' then any*)).

trivia(whitespace, layout then layout*).
trivia(line_comment, '%' then (any - nl)*).
trivia(block_comment, '/' then '*' then body('*' then '/')) nest self.
