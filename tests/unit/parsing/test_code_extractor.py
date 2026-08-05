"""Tests for deterministic fenced-code scanning and Python block selection."""

from __future__ import annotations

from code_verifier.parsing.code_extractor import extract_python_code


def test_multiple_python_blocks_selects_last_python_block() -> None:
    completion = """```python
first = 1
```
text
```python
second = 2
```
"""

    result = extract_python_code(completion)

    assert result.success is True
    assert result.code == "second = 2\n"
    assert result.num_code_blocks == 2
    assert result == extract_python_code(completion)


def test_python_block_has_priority_over_later_unmarked_block() -> None:
    completion = """```python
selected = True
```
```
selected = False
```
"""

    result = extract_python_code(completion)

    assert result.success is True
    assert result.code == "selected = True\n"
    assert result.num_code_blocks == 2


def test_unmarked_block_is_used_when_python_block_is_absent() -> None:
    completion = """```javascript
const value = 1;
```
```
first = 1
```
```
second = 2
```
"""

    result = extract_python_code(completion)

    assert result.success is True
    assert result.code == "second = 2\n"
    assert result.num_code_blocks == 3


def test_unsupported_language_is_counted_but_not_selected() -> None:
    result = extract_python_code("```javascript\nconst value = 1;\n```\n")

    assert result.success is False
    assert result.error_type == "no_supported_code_block"
    assert result.num_code_blocks == 1


def test_inline_backticks_do_not_close_fence() -> None:
    completion = """```python
value = "```"
# `inline` backticks stay in code
```
"""

    result = extract_python_code(completion)

    assert result.success is True
    assert result.code == 'value = "```"\n# `inline` backticks stay in code\n'


def test_longer_opener_requires_matching_closer_length() -> None:
    completion = """````python
value = 1
```
````
"""

    result = extract_python_code(completion)

    assert result.success is True
    assert result.code == "value = 1\n```\n"
    assert result.num_code_blocks == 1


def test_tilde_fence_is_supported() -> None:
    result = extract_python_code("~~~python\nvalue = 1\n~~~\n")

    assert result.success is True
    assert result.code == "value = 1\n"
    assert result.num_code_blocks == 1
