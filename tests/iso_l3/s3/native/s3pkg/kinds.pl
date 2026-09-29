:- module(kinds, [classify/2, pt/2, origin/1]).
% Optional: gives the data functor pt/2 its field names.  Exported as pt/2.
:- constructors([pt(x, y)]).
classify(1, class_comparison).
classify(2, class_other).
origin(pt(0, 0)).
