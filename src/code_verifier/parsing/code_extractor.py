"""Deterministic extraction of Python from Markdown-style fenced code blocks."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass


@dataclass(frozen=True)
class ParseResult:
    """Structured result returned by the completion code parser."""

    success: bool
    code: str
    error_type: str | None
    num_code_blocks: int


@dataclass(frozen=True)
class _FencedCodeBlock:
    """One scanned fenced block and its normalized language marker."""

    language: str | None
    code: str
    closed: bool


def _normalize_newlines(value: str) -> str:
    """Normalize CRLF and CR line endings to LF before fence scanning."""
    return value.replace("\r\n", "\n").replace("\r", "\n")


def _fence_start(line: str) -> tuple[str, int, str | None] | None:
    """Return one valid opener's character, length, and first info token."""
    indent = 0
    while indent < len(line) and line[indent] == " " and indent < 4:
        indent += 1
    if indent > 3 or indent >= len(line) or line[indent] not in {"`", "~"}:
        return None

    fence_character = line[indent]
    end = indent
    while end < len(line) and line[end] == fence_character:
        end += 1
    fence_length = end - indent
    if fence_length < 3:
        return None

    info = line[end:].strip()
    language = info.split(maxsplit=1)[0].lower() if info else None
    return fence_character, fence_length, language


def _is_closing_fence(line: str, *, fence_character: str, minimum_length: int) -> bool:
    """Return whether one line is a matching closing fence."""
    indent = 0
    while indent < len(line) and line[indent] == " " and indent < 4:
        indent += 1
    if indent > 3 or indent >= len(line) or line[indent] != fence_character:
        return False

    end = indent
    while end < len(line) and line[end] == fence_character:
        end += 1
    return end - indent >= minimum_length and not line[end:].strip()


def _scan_fenced_code_blocks(completion: str) -> list[_FencedCodeBlock]:
    """Scan supported Markdown-style fence openers without interpreting code contents."""
    normalized = _normalize_newlines(completion)
    lines = normalized.splitlines(keepends=True)
    blocks: list[_FencedCodeBlock] = []
    fence_character: str | None = None
    fence_length = 0
    language: str | None = None
    code_lines: list[str] = []

    for line in lines:
        line_without_newline = line[:-1] if line.endswith("\n") else line
        if fence_character is None:
            opener = _fence_start(line_without_newline)
            if opener is None:
                continue
            fence_character, fence_length, language = opener
            code_lines = []
            continue

        if _is_closing_fence(
            line_without_newline,
            fence_character=fence_character,
            minimum_length=fence_length,
        ):
            blocks.append(_FencedCodeBlock(language=language, code="".join(code_lines), closed=True))
            fence_character = None
            fence_length = 0
            language = None
            code_lines = []
            continue
        code_lines.append(line)

    if fence_character is not None:
        blocks.append(_FencedCodeBlock(language=language, code="".join(code_lines), closed=False))
    return blocks


def _select_code_block(blocks: Sequence[_FencedCodeBlock]) -> _FencedCodeBlock | None:
    """Select the final Python block, or the final unmarked block when no Python block exists."""
    python_blocks = [block for block in blocks if block.language == "python"]
    if python_blocks:
        return python_blocks[-1]
    unmarked_blocks = [block for block in blocks if block.language is None]
    return unmarked_blocks[-1] if unmarked_blocks else None


def extract_python_code(
    completion: str,
    expected_function_name: str | None = None,
) -> ParseResult:
    """Extract a fenced candidate; target-function validation is completed in WP2 step 2."""
    del expected_function_name
    blocks = _scan_fenced_code_blocks(completion)
    selected = _select_code_block(blocks)
    if selected is None:
        return ParseResult(False, "", "no_supported_code_block", len(blocks))
    if not selected.closed:
        return ParseResult(False, "", "unclosed_code_block", len(blocks))
    if not selected.code.strip():
        return ParseResult(False, "", "empty_code_block", len(blocks))
    return ParseResult(True, selected.code, None, len(blocks))
