% iso.toklex.pl — ISO Prolog token layer, matching clausal/tools/prolog_tokenizer.py
% dialect choices: '_' digit separators, lenient unknown escapes, 1e5 floats,
% nested block comments (nesting is a driver flag, not a spec change).
encoding(chars).

class(layout,    [' ', '\t', '\n', '\r', '\f', '\v']).
class(small,     range(a, z)).
class(capital,   range('A', 'Z')).
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

def(escape,   bslash then ( octdig then octdig* then bslash?
                          | 'x' then hexdig then hexdig* then bslash?
                          | any )).
def(qitem,    (quote then quote | escape | (any - quote - bslash))).
def(ditem,    (dquote then dquote | escape | (any - dquote - bslash))).
def(udigits,  digit then (digit | '_')*).
def(exp,      ('e' | 'E') then sign? then digit then digit*).

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
token(char_code, '0' then quote then (quote then quote | escape | any)) value char_code.
token(hex_int,  '0' then ('x' | 'X') then (hexdig | '_') then (hexdig | '_')*) value int_16.
token(oct_int,  '0' then ('o' | 'O') then (octdig | '_') then (octdig | '_')*) value int_8.
token(bin_int,  '0' then ('b' | 'B') then (bindig | '_') then (bindig | '_')*) value int_2.
token(float_num, (udigits then '.' then udigits then exp?
               | udigits then exp)) value float_of.
token(integer,  udigits) value int_10.
token(quoted_atom, quote then qitem* then quote) value quoted_atom_val.
token(string,   dquote then ditem* then dquote) value string_val.
token(graphic_tok, graphic then graphic* but_not ('/' then '*' then any*)).

trivia(whitespace, layout then layout*).
trivia(line_comment, '%' then (any - nl)*).
trivia(block_comment, '/' then '*' then body('*' then '/')) nest self.
