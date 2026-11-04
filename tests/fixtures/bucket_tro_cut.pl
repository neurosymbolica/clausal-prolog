% Last-call optimisation inside an index bucket, for a recursive clause that
% is not the bucket's last but cuts before its tail call: the cut drops the
% later clauses, so the in-place restart keeps the order of answers.
:- module(bucket_tro_cut, [count/4]).
count(go, K, A, N) :- K > 0, !, K1 is K - 1, A1 is A + 1, count(go, K1, A1, N).
count(go, _, N, N).
count(stop, _, N, N).
count(other, _, N, N).
count(more, _, N, N).
