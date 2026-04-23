# `_is_arrow_adjacent` byte-offset fix is Python 3.14-specific

`clausal/templating/term_rewriting.py`, `_is_arrow_adjacent` (line ~209)

Python 3.14 changed `col_offset` / `end_col_offset` to UTF-8 byte offsets.
The fix encodes the source line to bytes and indexes by byte position:

```python
line_bytes = source_lines[usub_line - 1].encode("utf-8")
return usub_col - 1 < len(line_bytes) and line_bytes[usub_col - 1:usub_col] == b"<"
```

This unconditionally assumes byte offsets. On older Python versions where
`col_offset` is character-based, this will **break** arrow detection for any
source line containing multi-byte characters before the `<-` arrow.

Options:
- Add a `sys.version_info >= (3, 14)` guard and keep the old character-index path as fallback.
- Use a try-both approach: check the byte path first, fall back to the character path.
- If only 3.14+ is supported, document that and leave as-is.
