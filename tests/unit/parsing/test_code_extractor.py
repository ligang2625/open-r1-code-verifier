"""Tests for deterministic fenced-code scanning and Python block selection."""

from __future__ import annotations

from dataclasses import FrozenInstanceError
from typing import Any, cast

import pytest

from code_verifier.parsing.code_extractor import ParseResult, extract_python_code


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


def test_standard_python_block_succeeds() -> None:
    result = extract_python_code("```Python\ndef solve(value):\n    return value\n```\n")

    assert result == ParseResult(
        success=True,
        code="def solve(value):\n    return value\n",
        error_type=None,
        num_code_blocks=1,
    )


def test_explanation_only_returns_no_supported_code_block() -> None:
    result = extract_python_code("The implementation follows from the examples.")

    assert result == ParseResult(False, "", "no_supported_code_block", 0)


def test_unclosed_final_candidate_returns_unclosed_code_block() -> None:
    completion = """```python
first = 1
```
```python
second = 2
"""

    result = extract_python_code(completion)

    assert result == ParseResult(False, "", "unclosed_code_block", 2)


def test_empty_selected_block_returns_empty_code_block() -> None:
    completion = """```python
first = 1
```
```python
   
```
"""

    result = extract_python_code(completion)

    assert result == ParseResult(False, "", "empty_code_block", 2)


@pytest.mark.parametrize("completion", ["", " ", "\n\t\n"])
def test_empty_completion_returns_empty_completion(completion: str) -> None:
    assert extract_python_code(completion) == ParseResult(False, "", "empty_completion", 0)


@pytest.mark.parametrize("value", [None, b"```python\npass\n```", ["not", "text"]])
def test_non_string_completion_returns_invalid_input(value: object) -> None:
    result = extract_python_code(cast(Any, value))

    assert result == ParseResult(False, "", "invalid_input", 0)


@pytest.mark.parametrize("value", ["", "   ", 123, ["solve"]])
def test_invalid_expected_function_name_is_rejected(value: object) -> None:
    result = extract_python_code("```python\ndef solve():\n    pass\n```\n", cast(Any, value))

    assert result == ParseResult(False, "", "invalid_expected_function_name", 0)


def test_expected_top_level_function_is_accepted() -> None:
    result = extract_python_code("```python\ndef solve(value):\n    return value\n```\n", "solve")

    assert result.success is True
    assert result.error_type is None


def test_expected_top_level_async_function_is_accepted() -> None:
    result = extract_python_code("```python\nasync def solve(value):\n    return value\n```\n", "solve")

    assert result.success is True
    assert result.error_type is None


def test_missing_target_function_is_reported() -> None:
    result = extract_python_code("```python\ndef other(value):\n    return value\n```\n", "solve")

    assert result == ParseResult(False, "", "missing_target_function", 1)


def test_nested_function_and_method_do_not_satisfy_target() -> None:
    completion = """```python
def outer():
    def solve():
        return 1
    return solve()

class Solver:
    def solve(self):
        return 2
```
"""

    result = extract_python_code(completion, "solve")

    assert result == ParseResult(False, "", "missing_target_function", 1)


def test_invalid_python_syntax_is_only_rejected_when_target_validation_is_requested() -> None:
    completion = "```python\ndef solve(:\n    pass\n```\n"

    without_target = extract_python_code(completion)
    with_target = extract_python_code(completion, "solve")

    assert without_target == ParseResult(True, "def solve(:\n    pass\n", None, 1)
    assert with_target == ParseResult(False, "", "invalid_python_syntax", 1)


def test_windows_and_unix_newlines_produce_identical_result() -> None:
    unix = "```python\ndef solve():\n    return 1\n```\n"
    crlf = unix.replace("\n", "\r\n")
    cr = unix.replace("\n", "\r")

    assert extract_python_code(unix, "solve") == extract_python_code(crlf, "solve")
    assert extract_python_code(unix, "solve") == extract_python_code(cr, "solve")


def test_parse_result_is_frozen() -> None:
    result = extract_python_code("```python\npass\n```\n")

    with pytest.raises(FrozenInstanceError):
        result.code = "changed"  # type: ignore[misc]


def test_error_type_is_from_documented_taxonomy() -> None:
    documented = {
        "invalid_input",
        "invalid_expected_function_name",
        "empty_completion",
        "no_supported_code_block",
        "unclosed_code_block",
        "empty_code_block",
        "invalid_python_syntax",
        "missing_target_function",
    }
    failures = [
        extract_python_code(cast(Any, None)),
        extract_python_code("```python\npass\n```", cast(Any, " ")),
        extract_python_code(" "),
        extract_python_code("explanation only"),
        extract_python_code("```python\npass"),
        extract_python_code("```python\n \n```"),
        extract_python_code("```python\ndef solve(:\n```", "solve"),
        extract_python_code("```python\ndef other():\n    pass\n```", "solve"),
    ]

    assert all(result.success is False and result.code == "" for result in failures)
    assert {result.error_type for result in failures} == documented
