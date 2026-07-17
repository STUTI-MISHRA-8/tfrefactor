"""Lossless top-level HCL block splitter.

Terraform files are, at the top level, exclusively a sequence of block
declarations: `IDENT ("label")* "{" ... "}"`. That invariant means we can
find exact source spans for every top-level block (resource, data, module,
variable, output, provider, locals, terraform, moved, import, check) with a
brace/string/heredoc/comment-aware scanner instead of a full HCL grammar.
This is what lets refactors (extract module, split file, rename) cut and
paste *exact original text* rather than re-serializing through a lossy AST.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

_LABEL_RE = re.compile(r'"((?:[^"\\]|\\.)*)"')
_KEYWORD_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_-]*")
_HEREDOC_RE = re.compile(r"<<-?(\w+)")


def _skip_trivia(text: str, pos: int) -> int:
    """Advance past whitespace and comments to find the next real token."""
    n = len(text)
    while pos < n:
        ch = text[pos]
        if ch in " \t\r\n":
            pos += 1
        elif ch == "#" or text[pos : pos + 2] == "//":
            nl = text.find("\n", pos)
            pos = nl if nl != -1 else n
        elif text[pos : pos + 2] == "/*":
            end = text.find("*/", pos + 2)
            pos = end + 2 if end != -1 else n
        else:
            break
    return pos


@dataclass(frozen=True)
class Block:
    keyword: str
    labels: tuple[str, ...]
    start: int
    end: int
    text: str

    @property
    def header(self) -> str:
        return self.text[: self.text.index("{")]

    @property
    def address(self) -> str:
        if self.keyword in ("resource", "data") and len(self.labels) >= 2:
            prefix = "data." if self.keyword == "data" else ""
            return f"{prefix}{self.labels[0]}.{self.labels[1]}"
        if self.labels:
            return f"{self.keyword}.{self.labels[0]}"
        return self.keyword


def split_top_level_blocks(text: str) -> list[Block]:
    """Return every top-level block in `text` with exact source spans."""
    blocks: list[Block] = []
    frames = ["CODE"]  # stack of "CODE" | "STRING"; len==1 == file top level
    i = 0
    n = len(text)
    header_start = 0
    block_start: int | None = None

    while i < n:
        top = frames[-1]
        ch = text[i]

        if top == "CODE":
            if ch == "<" and text[i : i + 2] == "<<":
                m = _HEREDOC_RE.match(text, i)
                if m:
                    term = m.group(1)
                    nl = text.find("\n", i)
                    body_start = nl + 1 if nl != -1 else n
                    term_re = re.compile(r"^[ \t]*" + re.escape(term) + r"\s*$", re.M)
                    match = term_re.search(text, body_start)
                    i = match.end() if match else n
                    continue
            if ch == "#" or text[i : i + 2] == "//":
                nl = text.find("\n", i)
                i = nl if nl != -1 else n
                continue
            if text[i : i + 2] == "/*":
                end = text.find("*/", i + 2)
                i = end + 2 if end != -1 else n
                continue
            if ch == '"':
                frames.append("STRING")
                i += 1
                continue
            if ch == "{":
                frames.append("CODE")
                if len(frames) == 2:
                    block_start = _skip_trivia(text, header_start)
                i += 1
                continue
            if ch == "}":
                frames.pop()
                if len(frames) == 1 and block_start is not None:
                    end = i + 1
                    raw = text[block_start:end]
                    header_text = raw[: raw.index("{")]
                    kw_match = _KEYWORD_RE.match(header_text.strip())
                    keyword = kw_match.group(0) if kw_match else ""
                    labels = tuple(m.group(1) for m in _LABEL_RE.finditer(header_text))
                    blocks.append(Block(keyword, labels, block_start, end, raw))
                    block_start = None
                    header_start = end
                i += 1
                continue
            i += 1
            continue

        else:  # STRING
            if ch == "\\":
                i += 2
                continue
            if text[i : i + 2] == "$$":
                i += 2
                continue
            if text[i : i + 2] == "${":
                frames.append("CODE")
                i += 2
                continue
            if ch == '"':
                frames.pop()
                i += 1
                continue
            i += 1
            continue

    return blocks
