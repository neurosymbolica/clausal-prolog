% clausal: no-collect
% iso.toklex.pl — ISO Prolog token layer, matching clausal/tools/prolog_tokenizer.py
% dialect choices: '_' digit separators, nested block comments (nesting is
% a driver flag, not a spec change).
%
% The escape, quoted-character and number grammars follow ISO 6.4 exactly
% (tightened 2026-10-15/16, operator ruling D60): the closed escape set with
% mandatory closing backslashes on octal/hex escapes, no raw control
% characters in quoted tokens, lowercase-only radix letters, and a mandatory
% fraction before an exponent. docs/iso_lexer_edge_cases.md lists each case
% with its rationale. `clausal.toklex.pl` keeps its lenient escape grammar
% (see its header) but shares this number grammar.
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
% ISO 6.4.2.1: a single quoted character is a graphic, alphanumeric, solo or
% space char, or an escape sequence. A raw control character is none of
% these, so every Unicode Cc character (C0, DEL, C1 -- which includes TAB,
% NL, CR, FF and VT) is refused inside a quoted token and after `0'`, as
% Scryer does. Space is a space char and stays allowed; a newline in the
% text is written `\n`, or continued with backslash-newline.
class(ctrl, unicode('Cc')).
% ISO 6.4.2.1's closed set of symbolic escape sequences: these eleven
% characters after a backslash (meta escapes \\ \' \" \` and control
% escapes a b f n r t v), plus the octal and hex escapes below. `\e` (ESC)
% and `\s` (space) are non-ISO extensions and are not escapes here.
class(symbolic_escape, ['a','b','f','n','r','t','v','\\','''','"','`']).

% The escape after `0'\`: the same closed grammar as inside quotes (see
% esc_term below) -- a symbolic escape, or an octal/hex escape with its
% mandatory closing backslash. Backslash-newline names no character, so
% `0'\<newline>` is not a char code: maximal munch backs up to `0`, and the
% quote opens a quoted token in which the continuation is read (Ulrich
% #213, `X is 0'\<newline>+'1.` -> X = 1). `0'\141` (no closing `\`),
% `0'\e` and `0'\s` are syntax errors, like `'\141'`, `'\e'` and `'\s'`.
def(escape,   bslash then ( (octdig then octdig* then bslash)
                          | ('x' then hexdig then hexdig* then bslash)
                          | symbolic_escape )).
def(udigits,  digit then (digit | '_')*).
% ISO 6.4.5's exponent char is "e" | "E", so `1.0E9` is a float; an exponent
% needs the fraction before it (see float_num).
def(exp,      ('e' | 'E') then sign? then digit then digit*).

% ── quoted_atom / string escape grammar ──────────────────────────────────
%
% ISO 6.4.2.1: an octal/hex escape needs its closing backslash (`'\141'` is a
% syntax error), which also pins the digit run's length, so `esc_term` is
% unambiguous on its own. `esc_other` is the closed symbolic set plus the
% backslash-newline continuation; any other `\<char>` (`\c`, `\e`, `\s`,
% `\u1`) is a syntax error. (The optional-close rules `esc_open_*`/
% `qplain_no_*` that the old reading needed are retired; see git history.)
def(esc_term,      bslash then ( (octdig then octdig* then bslash)
                                | ('x' then hexdig then hexdig* then bslash) )).
def(esc_other,     bslash then (symbolic_escape | nl)).

% No raw control character in quoted content (see `ctrl` above).
def(qq,     quote then quote).
def(qplain, (any - quote - bslash - ctrl)).
def(qunit,  (qq | esc_term | esc_other | qplain)).

def(dqq,    dquote then dquote).
def(dplain, (any - dquote - bslash - ctrl)).
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
% After `0'` comes one single quoted character (ISO 6.4.4, 6.4.2.1): a lone
% quote is not one (it is doubled, `0'''`), nor is a raw control character.
% So `0''` backs up to the integer `0` and the atom `''` (Ulrich #117, #120,
% #197), and `0'<TAB>` is a syntax error (#177).
token(char_code, '0' then quote then (quote then quote | escape | (any - bslash - quote - ctrl))) value char_code.
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
% ISO 6.4.4: the radix letters are lowercase only. `0X1` is not a number
% token, so maximal munch backs up to `0` and a VARIABLE `X1`, the same
% fallback shape as `0x.` and `1.5e.` (see EXPECTED_DIVERGENCES above).
token(hex_int,  '0' then 'x' then '_'* then hexdig then (hexdig | '_')*) value int_16.
token(oct_int,  '0' then 'o' then '_'* then octdig then (octdig | '_')*) value int_8.
token(bin_int,  '0' then 'b' then '_'* then bindig then (bindig | '_')*) value int_2.
% ISO 6.4.5: a float is <integer> . <fraction> [<exponent>]; the fraction is
% mandatory. `1e9` is the integer `1` and the atom `e9` (Ulrich #49/#50 rely
% on `e9` as a postfix operator); `1E9` is `1` and the variable `E9` (#47).
token(float_num, (udigits then '.' then udigits then exp?)) value float_of.
token(integer,  udigits) value int_10.
token(quoted_atom, quote then qunit* then quote) value quoted_atom_val.
token(string,   dquote then dunit* then dquote) value string_val.
token(graphic_tok, graphic then graphic* but_not ('/' then '*' then any*)).

trivia(whitespace, layout then layout*).
trivia(line_comment, '%' then (any - nl)*).
trivia(block_comment, '/' then '*' then body('*' then '/')) nest self.
