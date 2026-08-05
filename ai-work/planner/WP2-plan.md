# WP2 实施计划（代码解析器）

## 1. 元信息

| 项 | 值 |
|---|---|
| 目标 WP | WP2：代码解析器 |
| 规格依据 | `PROJECT_SPEC_Open-R1_CodeVerifier.md` §0、§6.2 Parsing Layer、§7.2、§9、§16、§17、§19、§20 WP2、§29 |
| 前置 WP | WP1（`proceedings.md` 状态：已完成，验收通过） |
| 计划文件 | `ai-work/planner/WP2-plan.md` |
| 面向的执行者 | 仅需仓库文件读写和基础 shell，可运行项目自带的 `make`、pytest 与 CLI |
| 计划粒度 | 单一阶段；4 个步骤、1 个新业务模块，无需拆分为 WP2-a / WP2-b |
| 预计配置影响 | 不修改 `pyproject.toml`、Makefile 或 YAML；仅新增解析模块、测试与 CLI/文档增量 |

## 2. 目标与范围

### 2.1 目标（规格 §20 原文）

稳定提取最终 Python 代码。

### 2.2 交付（规格 §20 原文）

- `ParseResult`
- `extract_python_code`
- 单元测试
- CLI 调试命令

### 2.3 验收（规格 §20 原文）

- 规定边界全部覆盖；
- 解析行为确定；
- 不因格式小差异崩溃；
- 解析失败原因可统计。

### 2.4 范围内

- 新建 `code_verifier.parsing` 包，并在 `code_extractor.py` 中实现规格 §9.2 的精确接口。
- 按 §9.1 的固定优先级，从 completion 中选择最后一个 Python fenced code block；不存在时选择最后一个无语言标记 fenced code block。
- 默认关闭“将完整 completion 当作代码”的回退；没有受支持代码块时返回结构化失败。
- 处理 LF、CRLF、CR 换行，支持反引号或波浪号 fenced block，且代码中的普通内联反引号不会提前终止代码块。
- 当传入 `expected_function_name` 时，使用 Python AST 检查模块顶层是否存在同名 `def` 或 `async def`。
- 为所有失败路径定义稳定、有限、可统计的 `error_type` 字符串。
- 新增只读 CLI 调试命令 `parse-code`，从文件或 stdin 读取 completion，以 JSON 输出 `ParseResult`。
- 更新 README 最小使用示例和 AGENTS 当前范围说明。

### 2.5 范围外

- 不实现 WP3 安全执行器、代码运行、测试调用、资源限制或沙箱。
- 不判断代码语义正确性、测试正确率、复杂度、风格或安全性。
- 不自动修复模型输出，不拼接 starter code，不修改函数签名。
- 不把整个 completion 默认当作代码；规格 §9.1(3) 的可选回退保持关闭。
- 不解析 Markdown 的完整 CommonMark 方言，不支持缩进代码块或 HTML code block。
- 不新增 parser YAML 配置；解析器必须是确定性纯函数。
- 不修改 `third_party/open-r1/**`，也不调用 Open-R1。
- 不修改 `proceedings.md`；只有 WP2 实现、独立审查并合并完成后才记录阶段结果。

## 3. 前置条件、现状与约束

### 3.1 proceedings 与当前代码结论

- `proceedings.md` 已将 WP0、WP1 标记为“已完成 / 验收通过”，没有 WP2 的部分实现、遗留任务或受阻事项。
- 当前 `src/code_verifier/` 尚无 `parsing/` 包，因此 WP2 从零新增一个解析模块，不重复现有 Data Layer 功能。
- 当前 CLI 已采用 `build_parser()`、`main()` 和私有 handler 的模式；WP2 必须沿用该模式。
- 当前 `tests/unit/test_cli.py` 对所有子命令统一检查 `--help`、`--config`、`--seed`、`--output-dir`、`--log-level`；`parse-code` 必须加入同一合同。
- `pyproject.toml` 的 strict mypy 已覆盖整个 `src` 与 `tests`，新增包无需修改 mypy 文件清单，也不需要新增依赖。

### 3.2 模块边界与硬性规则

- Parsing Layer 只负责从 completion 提取最终代码、验证输出格式、返回结构化结果；不得判断语义正确性（§6.2）。
- Prompt 合同要求最终答案包含一个 Python code block，但解析器必须对多个 block、无标记 block 和格式错误给出确定行为（§7.2、§9）。
- 新模块必须包含 `from __future__ import annotations`、完整类型标注、简洁 docstring、明确错误处理和单元测试。
- 保持 Ruff 双引号、119 列和 strict mypy；不得使用新的第三方 Markdown parser。
- 不硬编码用户文件路径、模型名、设备、密钥或数据位置。
- 不记录或输出隐藏测试；WP2 CLI 只处理调用者显式提供的 completion。

### 3.3 WP2 明确实现决策

1. **代码块选择顺序**：先检查所有语言标记首 token 为 `python`（大小写不敏感）的 fenced block，选择其中最后一个；只有完全没有 Python block 时，才选择最后一个 info string 为空的 fenced block。其他语言 block 计入 `num_code_blocks`，但不能成为代码候选。
2. **最后 block 优先且不回退**：若最后一个最高优先级候选未闭合或为空，直接返回对应失败；不得静默回退到更早的合法 block，否则“最终代码”行为不确定。
3. **fence 规则**：支持行首最多 3 个空格、长度至少 3 的连续反引号或波浪号 opener；closing fence 必须使用相同字符、长度不少于 opener，且该行除空白外不得含其他文本。代码中的内联反引号或短于 opener 的 fence 原样保留。
4. **换行规则**：扫描前把 `\r\n` 和独立 `\r` 统一为 `\n`；返回代码不包含 opener/closer，不额外缩进、去空格或格式化。
5. **完整 completion 回退**：`extract_python_code()` 的规格签名没有开关参数，因此 WP2 始终保持关闭；没有 Python/无标记 block 时使用 `error_type="no_supported_code_block"`。
6. **目标函数检测**：仅当 `expected_function_name` 非 `None` 时执行 `ast.parse()`；目标必须是 AST module body 中的顶层 `FunctionDef` 或 `AsyncFunctionDef`。嵌套函数、类方法、注释和字符串中的文本均不算目标函数。
7. **语法错误边界**：未要求目标函数时，只负责提取，不因 Python 语法错误拒绝代码；要求目标函数时 AST 无法解析则返回 `error_type="invalid_python_syntax"`，因为无法可靠验证函数存在性。
8. **稳定错误分类**：`error_type` 只允许以下值或 `None`：
   - `invalid_input`
   - `invalid_expected_function_name`
   - `empty_completion`
   - `no_supported_code_block`
   - `unclosed_code_block`
   - `empty_code_block`
   - `invalid_python_syntax`
   - `missing_target_function`
9. **结果字段约定**：成功时 `success=True`、`error_type=None`；失败时 `success=False`、`code=""`；`num_code_blocks` 表示扫描到的 opener 数量，包含不支持语言和未闭合 block，便于统计模型格式行为。
10. **CLI 退出码**：成功解析返回 0；结构化解析失败返回 1；输入文件读取失败或 CLI 参数错误返回 2。解析成功/失败都向 stdout 输出单行 JSON，I/O 错误写 stderr 且不打印 traceback。

## 4. 目标文件总览

### 4.1 新建

- `src/code_verifier/parsing/__init__.py`
- `src/code_verifier/parsing/code_extractor.py`
- `tests/unit/parsing/__init__.py`
- `tests/unit/parsing/test_code_extractor.py`

### 4.2 修改

- `src/code_verifier/cli.py`
- `tests/unit/test_cli.py`
- `README.md`
- `AGENTS.md`

### 4.3 明确不修改

- `pyproject.toml`
- `Makefile`
- `configs/**`
- `src/code_verifier/data/**`
- `src/code_verifier/training/**`
- `third_party/open-r1/**`
- `proceedings.md`

## 5. 实施步骤

### 步骤 1：建立 Parsing Layer 的结果类型、fence 扫描器与确定性候选选择

**目标文件**：

- `src/code_verifier/parsing/__init__.py`（新建）
- `src/code_verifier/parsing/code_extractor.py`（新建）

**新增 / 修改的符号**：

```python
@dataclass(frozen=True)
class ParseResult:
    success: bool
    code: str
    error_type: str | None
    num_code_blocks: int


@dataclass(frozen=True)
class _FencedCodeBlock:
    language: str | None
    code: str
    closed: bool


def _normalize_newlines(value: str) -> str:
    """Normalize CRLF and CR line endings to LF before fence scanning."""


def _scan_fenced_code_blocks(completion: str) -> list[_FencedCodeBlock]:
    """Scan supported Markdown-style fence openers without interpreting code contents."""


def _select_code_block(blocks: Sequence[_FencedCodeBlock]) -> _FencedCodeBlock | None:
    """Select the final Python block, or the final unmarked block when no Python block exists."""
```

**主要功能**：

- `ParseResult` 的字段、顺序和类型必须逐字匹配规格 §9.2，不得增加必填字段或改变 `error_type` 类型。
- `_scan_fenced_code_blocks()` 使用标准库逐行状态机，不使用一个跨全文的贪婪正则：
  - 识别 opener 的 fence 字符、长度和 info string；
  - info string 取去除首尾空白后的第一个 token；空 info 记为 `None`；
  - `python` 大小写不敏感，其他 token 原样规范为小写，仅用于筛选；
  - closing fence 必须匹配同一字符且长度不短于 opener；
  - 遇到 EOF 仍未闭合时保留该 block，`closed=False`；
  - opener 内部的内容逐行收集，不能因字符串或注释中的普通反引号提前结束。
- `_select_code_block()` 必须严格实现 §9.1 的优先级和“最后一个”规则；不能根据代码长度、AST 结果或主观质量选择 earlier block。
- `src/code_verifier/parsing/__init__.py` 只重导出 `ParseResult` 与 `extract_python_code`，不包含业务逻辑。

**测试方案**：

- 测试文件：`tests/unit/parsing/test_code_extractor.py`
- 本步骤先建立以下扫描/选择级测试；可以直接测试私有 helper，也可以通过公共函数间接覆盖，但断言必须精确：
  - `test_multiple_python_blocks_selects_last_python_block`：两个 Python block 返回第二个。
  - `test_python_block_has_priority_over_later_unmarked_block`：存在 Python block 时，不选择更晚的无标记 block。
  - `test_unmarked_block_is_used_when_python_block_is_absent`：无 Python block 时选最后一个无标记 block。
  - `test_unsupported_language_is_counted_but_not_selected`：例如 JavaScript block 计数为 1，但没有候选。
  - `test_inline_backticks_do_not_close_fence`：代码字符串/注释中的反引号保留。
  - `test_longer_opener_requires_matching_closer_length`：四反引号 opener 不被三反引号行关闭。
  - `test_tilde_fence_is_supported`：`~~~python` 能被提取。
- 覆盖规格：§9.1 的解析顺序、§9.3 的多代码块、无语言标记、代码中反引号。

**验证命令与通过标准**：

```bash
make lint
.venv/bin/python -m pytest tests/unit/parsing/test_code_extractor.py -k "block or fence or backtick"
```

通过标准：Ruff / strict Mypy 全绿；上述扫描与选择测试全部通过；同一 completion 重复调用产生完全相同的 block 计数和代码文本。

---

### 步骤 2：实现规格 §9.2 公共提取函数、目标函数检查与稳定失败分类

**目标文件**：`src/code_verifier/parsing/code_extractor.py`（继续修改）

**新增 / 修改的符号**：

```python
def _contains_top_level_function(code: str, expected_function_name: str) -> tuple[bool, bool]:
    """Return (syntax_valid, target_found) for a module-level def or async def."""


def extract_python_code(
    completion: str,
    expected_function_name: str | None = None,
) -> ParseResult:
    """Extract the deterministic final Python code candidate from one model completion."""
```

**主要功能**：

- `extract_python_code()` 必须逐字使用规格 §9.2 签名。
- 运行时防御性处理类型错误，即使调用者绕过类型检查也不能抛未处理异常：
  - `completion` 不是 `str`：返回 `invalid_input`、`num_code_blocks=0`；
  - `expected_function_name` 既非 `None` 也非非空 `str`：返回 `invalid_expected_function_name`；
  - completion 仅含空白：返回 `empty_completion`。
- 调用步骤 1 的 scanner 和 selector：
  - 无候选返回 `no_supported_code_block`；
  - 候选未闭合返回 `unclosed_code_block`；
  - 候选 code 仅含空白返回 `empty_code_block`。
- 目标函数为 `None` 时，不调用 AST，不拒绝语法错误，只返回提取结果。
- 目标函数非 `None` 时：
  - 使用 `ast.parse(code)`；
  - `SyntaxError` 返回 `invalid_python_syntax`；
  - 只遍历 `module.body`，允许顶层 `def` / `async def`；
  - 没有精确同名函数返回 `missing_target_function`。
- 所有失败结果的 `code` 必须为空字符串，防止下游误把失败候选交给执行器；所有成功结果 `error_type` 必须为 `None`。
- 不捕获 `BaseException`；仅处理预期输入、fence 和 `SyntaxError` 边界。

**测试方案**：

- 测试文件：`tests/unit/parsing/test_code_extractor.py`
- 新增测试函数：
  - `test_standard_python_block_succeeds`：标准单 block 返回纯代码、`success=True`、`error_type is None`、计数 1。
  - `test_explanation_only_returns_no_supported_code_block`：只有说明文本时结构化失败。
  - `test_unclosed_final_candidate_returns_unclosed_code_block`：未闭合 block 不抛异常且不回退 earlier block。
  - `test_empty_selected_block_returns_empty_code_block`：空 block 精确分类。
  - `test_empty_completion_returns_empty_completion`：空串和纯空白参数化覆盖。
  - `test_non_string_completion_returns_invalid_input`：用 `cast(Any, value)` 传 `None`、bytes、list，均不崩溃。
  - `test_invalid_expected_function_name_is_rejected`：空名、纯空白和非字符串均失败。
  - `test_expected_top_level_function_is_accepted`：顶层 `def` 存在时成功。
  - `test_expected_top_level_async_function_is_accepted`：顶层 `async def` 存在时成功。
  - `test_missing_target_function_is_reported`：合法 Python 但缺少目标函数时精确失败。
  - `test_nested_function_and_method_do_not_satisfy_target`：嵌套函数和类方法不算顶层目标。
  - `test_invalid_python_syntax_is_only_rejected_when_target_validation_is_requested`：同一代码在无 expected name 时提取成功，有 expected name 时返回 `invalid_python_syntax`。
  - `test_windows_and_unix_newlines_produce_identical_result`：CRLF、CR、LF 输出相同。
  - `test_parse_result_is_frozen`：修改结果字段抛 `FrozenInstanceError`。
  - `test_error_type_is_from_documented_taxonomy`：所有失败 fixture 的 error type 均属于 §3.3 列表。
- 覆盖规格：§9.3 列出的全部边界，包括标准 block、多 block、无标记、解释文本、未闭合、空 block、反引号、缺函数、空 completion、非字符串、Windows/Unix 换行。

**验证命令与通过标准**：

```bash
make lint
.venv/bin/python -m pytest tests/unit/parsing/test_code_extractor.py
```

通过标准：Ruff / strict Mypy 全绿；§9.3 的 11 类边界均至少有一个明确测试；测试文件全部通过；任何失败都返回有限 error taxonomy，未出现 traceback 或未分类异常。

---

### 步骤 3：新增 `parse-code` CLI 调试命令并保持现有命令兼容

**目标文件**：

- `src/code_verifier/cli.py`（修改）
- `tests/unit/test_cli.py`（修改）

**新增 / 修改的符号**：

```python
def _add_common_arguments(
    parser: argparse.ArgumentParser,
    *,
    config_required: bool = False,
    output_dir_default: Path | None = None,
) -> None:
    """Add the common project options while allowing command-specific output defaults."""


def _read_completion(path_text: str) -> str:
    """Read UTF-8 completion text from stdin for '-' or from one local file."""


def _parse_code(args: argparse.Namespace) -> int:
    """Run the WP2 parser and print one deterministic JSON ParseResult."""


def build_parser() -> argparse.ArgumentParser:
    """Build the CodeVerifier command-line parser with WP0-WP2 commands."""
```

**CLI 形态**：

```bash
.venv/bin/code-verifier parse-code \
  --completion-file completion.txt \
  --expected-function-name solve \
  --config optional-unused.yaml \
  --seed 42 \
  --output-dir outputs/parse-code \
  --log-level INFO

printf '%s\n' '```python' 'def solve(x):' '    return x' '```' | \
  .venv/bin/code-verifier parse-code \
    --completion-file - \
    --expected-function-name solve
```

**主要功能**：

- 在 `build_parser()` 中新增 `parse-code` 子命令：
  - `--completion-file`：字符串路径，默认 `-`；`-` 从 `sys.stdin.read()`，其他值按 UTF-8 文本读取；
  - `--expected-function-name`：可选字符串，原样传入 `extract_python_code()`；
  - 调用 `_add_common_arguments()`，因此帮助中必须包含 §17 的五项公共参数。
- 只为消除 WP1 专用默认值而小幅扩展 `_add_common_arguments()`：
  - `prepare-data` 继续要求 `--config` 和 `--output-dir`；
  - `check-data` 的 `--output-dir` 默认值继续是 `outputs/check-data`；
  - 其他命令的 `--output-dir` 可为 `None` 或自己的默认值；不得改变已有 handler 的实际参数转发。
- `_parse_code()` 使用 `dataclasses.asdict()` 和 `json.dumps(..., ensure_ascii=False, sort_keys=True)` 输出单行 JSON，字段必须恰好为 `success/code/error_type/num_code_blocks`。
- 解析成功返回 0；解析失败仍输出 JSON 并返回 1。
- `_read_completion()` 读取失败时，由 `_parse_code()` 捕获 `OSError` / `UnicodeError`，向 stderr 输出单行 `error: ...`，返回 2；不得输出 traceback。
- `--config`、`--seed`、`--output-dir` 在该纯解析调试命令中不改变结果，仅为遵守 §17 的统一 CLI 合同；帮助文本必须明确这一点，避免误导。
- 保持 `record-environment`、`prepare-data`、`check-data` 的已有退出码、输出和测试不变。

**测试方案**：

- 测试文件：`tests/unit/test_cli.py`
- 新增 / 修改测试函数：
  - `test_root_help_lists_wp2_parse_command`：root help 含 `parse-code`。
  - 将 `test_all_subcommands_expose_common_arguments` 的参数列表加入 `parse-code`。
  - `test_parse_code_reads_stdin_and_emits_success_json`：monkeypatch stdin，断言退出码 0、JSON 四字段和提取代码。
  - `test_parse_code_reads_file_and_forwards_expected_function`：临时文件输入，断言目标函数校验生效。
  - `test_parse_code_failure_emits_json_and_returns_one`：只有解释文本时退出码 1，JSON 的 `error_type` 为 `no_supported_code_block`。
  - `test_parse_code_missing_file_returns_two_without_traceback`：不存在文件退出码 2，stderr 有路径且无 `Traceback`。
  - `test_wp1_command_defaults_remain_compatible_after_common_argument_refactor`：`prepare-data` 仍要求 config/output-dir，`check-data` 默认行为不变。
- 覆盖规格：§17 全局参数、§19.3 最小 CLI 测试、§20 WP2 CLI 调试命令。

**验证命令与通过标准**：

```bash
make lint
.venv/bin/python -m pytest tests/unit/test_cli.py
printf '%s\n' '```python' 'def solve(x):' '    return x' '```' | \
  .venv/bin/code-verifier parse-code --completion-file - --expected-function-name solve
```

通过标准：CLI 测试全绿；手工 smoke 命令退出 0，stdout 是可被 `json.loads()` 解析的单行 JSON，`success=true`、`error_type=null`、代码不含 fence；所有旧 CLI 测试仍通过。

---

### 步骤 4：补充最小文档并执行 WP2 全量验收

**目标文件**：

- `README.md`（修改）
- `AGENTS.md`（修改）

**文档变更**：

- README 项目状态更新为 WP0–WP2 已实现，并新增“WP2 code parser”小节，至少包含：
  - Python API 示例：`extract_python_code(completion, expected_function_name="solve")`；
  - 文件输入 CLI 示例；
  - stdin CLI 示例；
  - 退出码 0 / 1 / 2 含义；
  - 明确默认不把完整 completion 当代码；
  - 明确 parser 不执行代码、不判断语义正确性。
- AGENTS 项目结构新增 `src/code_verifier/parsing/code_extractor.py` 和对应测试路径。
- AGENTS 当前范围改为“WP0、WP1、WP2 已完成；不得提前实现 WP3 或后续功能”。
- 不在文档中声称 WP2 已验收，除非本步骤中的实际命令全部通过；`proceedings.md` 仍由后续 reviewer 更新。

**测试方案**：

- 测试文件：复用 `tests/unit/parsing/test_code_extractor.py`、`tests/unit/test_cli.py` 和现有完整测试集。
- 文档 smoke：复制 README 中的 stdin 命令执行，确认输出 JSON 与文档一致。
- 回归范围：WP0 环境记录、WP1 数据准备/检查、WP2 parser 全部测试均需通过。

**验证命令与通过标准**：

```bash
make lint
make test
.venv/bin/code-verifier --help
.venv/bin/code-verifier parse-code --help
printf '%s\n' 'reasoning text' '```python' 'def solve(x):' '    return x + 1' '```' | \
  .venv/bin/code-verifier parse-code --completion-file - --expected-function-name solve
```

通过标准：

- `make lint` 全绿：Ruff check、Ruff format check、strict Mypy 均无错误。
- `make test` 全绿，现有 135 个测试无回归，且 WP2 新增测试全部被收集。
- root help 列出 `parse-code`；`parse-code --help` 列出 `--help`、`--config`、`--seed`、`--output-dir`、`--log-level`、`--completion-file`、`--expected-function-name`。
- smoke 命令退出 0，返回代码仅包含 `def solve...`，不含 reasoning 或 Markdown fence。
- `third_party/open-r1/**` 无任何修改。

## 6. 总体验收与测试计划

### 6.1 单元测试汇总

- `tests/unit/parsing/test_code_extractor.py`
  - 覆盖 §9.3 的全部 11 类边界；
  - 覆盖 Python 优先、最后 block、无标记回退、unsupported language、长 fence、tilde fence；
  - 覆盖 AST 顶层函数检测和有限 error taxonomy；
  - 覆盖 ParseResult 不可变性和重复调用确定性。
- `tests/unit/test_cli.py`
  - 覆盖新命令注册、公共参数、stdin/file 输入、JSON 输出、退出码和 I/O 错误；
  - 回归 WP0/WP1 命令合同。

### 6.2 集成测试判断

WP2 不执行代码、不调用模型、不依赖数据集或沙箱，规格 §19.2 没有要求 parser 独立端到端集成场景。因此本阶段不新增独立 integration 文件；CLI stdin smoke 作为 Parsing Layer 到 CLI 的最小集成验证。WP3/WP4 接入执行与验证时再增加 parser → executor 的 mock/真实集成测试。

### 6.3 最终通过标准

- [ ] §20 WP2 交付项全部存在：`ParseResult`、`extract_python_code`、单元测试、CLI 调试命令。
- [ ] §9.2 两个接口签名逐字匹配规格。
- [ ] §9.3 规定边界全部有明确测试且通过。
- [ ] 相同输入重复解析结果完全一致，不依赖随机数、路径或环境。
- [ ] 所有解析失败都使用 §3.3 的稳定 `error_type`，可直接聚合统计。
- [ ] 格式差异（CRLF/CR/LF、大小写 language tag、3+ fence、内联反引号）不会导致未处理异常。
- [ ] CLI JSON 字段恰好匹配 `ParseResult`，退出码 0/1/2 符合约定。
- [ ] `make lint` 全绿。
- [ ] `make test` 全绿且旧测试无回归。
- [ ] 未修改 `third_party/open-r1/**`、训练配置或 WP3+ 模块。

## 7. 风险与注意事项

- **Markdown 解析过度扩张**：不要实现完整 CommonMark；状态机只覆盖 §9 和本计划明确的 fence 子集，避免引入第三方依赖和边界爆炸。
- **正则贪婪误提取**：禁止用单个 `re.DOTALL` 贪婪表达式匹配全文，否则多 block、未闭合 block 和代码内反引号容易产生非确定结果。
- **错误回退掩盖最终答案**：最后一个高优先级 block 无效时必须失败，不能退回 earlier block；否则模型的最终输出格式错误会被静默隐藏。
- **函数名误判**：不得用简单字符串包含或裸正则判断目标函数，避免注释、字符串、嵌套函数和类方法误命中；使用 AST module body。
- **语义边界漂移**：AST 只用于目标函数存在性，不做复杂度、安全性、import、调用或返回值判断。
- **下游合同稳定性**：`ParseResult` 将被 WP3/WP4 消费，字段与 error taxonomy 一旦落地不得随意改名；后续扩展应保持向后兼容。
- **CLI 兼容回归**：调整公共参数 helper 时必须复跑全部 CLI 测试，不能改变 WP1 的 required 参数和默认行为。

## 8. 关联文档索引

- `PROJECT_SPEC_Open-R1_CodeVerifier.md`
  - §0：实现纪律、类型/测试/错误处理、禁止范围扩张
  - §6.2：Parsing Layer 模块边界
  - §7.2：模型输出合同
  - §9：解析顺序、接口、单元测试边界
  - §16：`src/code_verifier/parsing/code_extractor.py` 目标结构
  - §17：CLI 公共参数合同
  - §19.1 Parser、§19.3 CI
  - §20 WP2：目标、交付、验收
  - §29：Python 函数级代码生成默认决策
- `proceedings.md`
  - WP1 状态：已完成、验收通过
  - WP1 明确未实现 WP2，因此本计划从零增量新增 Parsing Layer
- 当前代码
  - `src/code_verifier/cli.py`：沿用 parser / handler / `main()` 模式
  - `tests/unit/test_cli.py`：沿用公共参数和退出码测试风格
  - `pyproject.toml`：Ruff 119 列、双引号、strict Mypy、pytest 全目录收集
