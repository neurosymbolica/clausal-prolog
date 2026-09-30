% the ISO 9.1 evaluables and Scryer's extras.
t(e01, X, X is 7 // 2).
t(e02, X, X is -7 // 2).
t(e03, X, X is 7 // -2).
t(e04, X, X is -7 // -2).
t(e05, X, X is 7 mod 2).
t(e06, X, X is -7 mod 2).
t(e07, X, X is 7 mod -2).
t(e08, X, X is -7 mod -2).
t(e09, X, X is 7 rem 2).
t(e10, X, X is -7 rem 2).
t(e11, X, X is 7 rem -2).
t(e12, X, X is -7 rem -2).
t(e13, X, X is 7 div 2).
t(e14, X, X is -7 div 2).
t(e15, X, X is 7 div -2).
t(e16, X, X is -7 div -2).
t(e17, X, X is 7 / 2).
t(e18, X, X is 4 / 2).
t(e19, X, X is -7 / 2).
t(e20, X, X is gcd(12, 18)).
t(e21, X, X is gcd(-12, 18)).
t(e22, X, X is gcd(0, 0)).
t(e23, X, X is gcd(12, 0)).
t(e24, X, X is gcd(1.0, 2)).
t(e25, X, X is msb(1)).
t(e26, X, X is msb(1000)).
t(e27, X, X is msb(0)).
t(e28, X, X is msb(-1)).
t(e29, X, X is truncate(-2.5)).
t(e30, X, X is round(-2.5)).
t(e31, X, X is round(2.5)).
t(e32, X, X is ceiling(-2.5)).
t(e33, X, X is floor(-2.5)).
t(e34, X, X is round(0.5)).
t(e35, X, X is round(-0.5)).
t(e36, X, X is float_integer_part(-2.5)).
t(e37, X, X is float_fractional_part(-2.5)).
t(e38, X, X is 2 ** 3).
t(e39, X, X is 2 ** (-1)).
t(e40, X, X is 2 ^ 3).
t(e41, X, X is 2 ^ -1).
t(e42, X, X is 1 ^ -1).
t(e43, X, X is -1 ^ -1).
t(e44, X, X is 0 ^ -1).
t(e45, X, X is 2.0 ^ 3).
t(e46, X, X is 2 ** 3.0).
t(e47, X, X is 0 ** 0).
t(e48, X, X is 0.0 ** 0).
t(e49, X, X is min(1, 1.0)).
t(e50, X, X is max(1, 1.0)).
t(e51, X, X is min(1, 2.0)).
t(e52, X, X is max(2, 1.0)).
t(e53, X, X is min(a, 1)).
t(e54, X, X is sign(-3)).
t(e55, X, X is sign(0)).
t(e56, X, X is sign(-2.5)).
t(e57, X, X is sign(0.0)).
t(e58, X, X is abs(-9223372036854775808)).
t(e59, X, X is abs(-3.0)).
t(e60, X, X is -(-9223372036854775808)).
t(e61, X, X is -9223372036854775808 // -1).
t(e62, X, X is 1 << 3).
t(e63, X, X is -16 >> 2).
t(e64, X, X is 1 << 100).
t(e65, X, X is 5 /\ 3).
t(e66, X, X is 5 \/ 3).
t(e67, X, X is xor(5, 3)).
t(e68, X, X is \ 5).
t(e69, X, X is sqrt(4)).
t(e70, X, X is sqrt(-1)).
t(e71, X, X is log(0)).
t(e72, X, X is log(-1)).
t(e73, X, X is exp(0)).
t(e74, X, X is sin(0)).
t(e75, X, X is cos(0)).
t(e76, X, X is atan2(1, 1)).
t(e77, X, X is atan(1, 1)).
t(e78, X, X is pi).
t(e79, X, X is e).
t(e80, X, X is float(3)).
t(e81, X, X is 1 // 0).
t(e82, X, X is 1 mod 0).
t(e83, X, X is 1 rem 0).
t(e84, X, X is 1 / 0).
t(e85, X, X is 1 / 0.0).
t(e86, X, X is 0 / 0).
t(e87, X, X is 1 + a).
t(e88, X, X is foo(1)).
t(e89, X, X is _ + 1).
t(e90, X, X is truncate(1.0e20)).
t(e91, X, X is ceiling(2.0)).
t(e92, X, X is 10 ** 20).
t(e93, X, X is 2 ** 0.5).
t(e94, X, X is max(1, 2)).
t(e95, X, X is acos(2)).
t(e96, X, X is 5 / 2.0).
t(e97, X, X is 2 * 3.0).
t(e98, x, 1 =:= 1.0).
t(e99, x, 1 < 1.0).
t(e100, X, X is truncate(-0.5)).
t(e101, X, X is 0.1 + 0.2).
t(e102, X, X is 1.0e10).
t(e103, X, X is 1 / 3).
t(e104, X, X is 2 ** (-1.0)).
t(e105, X, X is log(2, 8)).
t(e106, X, X is truncate(a)).
t(e107, X, X is float_fractional_part(1)).
t(e108, X, X is min(2, 2.0)).
t(e109, X, X is 5 mod 0).
t(e110, X, X is -5 rem 3).
t(e111, X, X is 9223372036854775807 + 1).
t(e112, X, X is -9223372036854775808 - 1).
t(e113, X, X is 2 ** 64).
t(e114, X, X is 2 ^ 100).
t(e115, X, X is -7 >> 1).
t(e116, X, X is 10 / 4).
t(e117, X, X is -10 / 4).
t(e118, X, X is integer(0.5)).
t(e119, X, X is integer(-2.5)).
t(e120, X, X is truncate(3)).
t(e121, X, X is 1 << -1).
t(e122, X, X is atan2(1, 0)).
t(e123, X, X is ceiling(-0.5)).
t(e124, X, X is round(-0.4)).
t(e125, X, X is (1 + 2) * 3 - 4 / 2).
t(e126, X, X is 3 - -2).
t(e127, X, X is 2 ** (-2)).
t(e128, X, X is (-2) ** 3).
t(e129, X, X is (-2) ^ 3).
t(e130, X, X is 7 / -2).
t(e131, X, X is 6 / 3.0).
t(e132, X, X is -7 mod 0).
t(e133, X, X is max(a, 1)).
t(e134, X, X is abs(-9223372036854775809)).
t(e135, X, X is sign(-9223372036854775809)).
t(e136, X, X is 100000000000000000000 // 3).
t(e137, X, X is -100000000000000000000 mod 7).
t(e138, X, X is gcd(100000000000000000000, 15)).
t(e139, X, X is msb(100000000000000000000)).
t(e140, X, X is 3 ** 2.0).
t(e141, X, X is float_integer_part(3)).
t(e142, X, X is round(3)).
t(e143, X, X is floor(3)).
t(e144, X, X is 1.5 // 1).
t(e145, X, X is 3 mod 1.5).
t(e146, X, X is 7.0 rem 2).
t(e147, X, X is \ 2.0).
t(e148, X, X is 1 << 2.0).
t(e149, X, X is tan(0)).
t(e150, X, X is asin(0)).
t(e151, X, X is acos(1)).
t(e152, X, X is atan(0)).
t(e153, X, X is exp(1)).
t(e154, X, X is 0 ^ 0).
t(e155, X, X is 0.0 / 0).
t(e156, X, X is -(3)).
t(e157, X, X is + 3).
t(e158, X, X is sqrt(2.0)).
t(e159, X, X is cot(1.0)).
t(e160, X, X is 2 ^ 2.0).
t(e161, X, X is 2 ^ 0.5).
t(e162, X, X is log(2.0)).
t(e163, X, X is copysign(1, -0.0)).
t(e164, X, X is max(1.0, 1)).
t(e165, X, X is min(1.0, 1)).
t(e166, X, X is 16 ** 0.5).
t(e167, X, X is -1 ^ 3).
t(e168, X, X is 1 ^ -3).
t(e169, X, X is -1 ^ -2).
t(e170, X, X is abs(a)).
