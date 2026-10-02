Fixed harvest LLM rewriter leaking the literal `TYPE:` placeholder into memory
content (e.g. `TYPE: convention — ...`) and emitting degenerate label-only or
truncated candidates. The parser now unwraps a leaked `TYPE: <type>` prefix,
recovers the real type, and drops label-only/truncated fragments. The prompt
placeholder changed from `TYPE:` to `<type>:` to stop inducing the leak.

Note: `_parse_response` may now return `None` on the "unknown type" and
"no type prefix" branches when the unwrapped payload is a confirmed-leak
fragment; callers already handle `None`.
