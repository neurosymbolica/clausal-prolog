% Imports an ATOM (not a predicate) from the package facade, then uses it as
% data; builds data with functors it never declares (attribute/2, tag/1)
% and with the package's constructor pt/2.
:- module(s3main, [cmp/1, kind_of/2, tagged/1, ox/1, sig/1, ub/1,
                   attr_val/2, made/1]).
:- use_module(s3pkg, [class_comparison]).
:- use_module(s3pkg, [classify/2, pt/2, origin/1]).
cmp(X) :- classify(X, class_comparison).
kind_of(X, K) :- classify(X, K).
tagged(T) :- T = tag(class_comparison).
ox(X) :- origin(pt(X, _)).
sig(N) :- signature(pt, 2, N).
ub(K) :- unbound_keys(pt(1, _), K).
attrs([attribute(color, red), attribute(size, 3)]).
attr_val(K, V) :- attrs(L), member(attribute(K, V), L).
made(P) :- P = pt(3, 4).
