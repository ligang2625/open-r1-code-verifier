# WP2 Executor 执行报告

- **计划文件**：`ai-work/planner/WP2-plan.md`
- **目标阶段**：WP2：代码解析器
- **执行分支**：`feat/wp2`
- **独立 worktree**：`.worktrees/wp2`
- **执行类型**：基于 plan 的首次实施
- **proceedings.md**：只读，未修改
- **third_party/open-r1**：仅在 worktree 中从本地固定 checkout 初始化 submodule；未修改上游内容

## 基线检查

- `make lint`：通过，26 个源文件无静态检查问题。
- 初次 `make test`：134 passed、1 failed；失败原因是新 worktree 的 submodule 尚未初始化，环境记录误读父仓库 commit。
- 远程 submodule clone 因 TLS/RPC 失败；随后使用主仓库已有的本地只读 checkout 初始化同一固定 commit `1416fa0cf21595d2083b399a2a0bbddd7f6e9563`。
- 为避免共享 editable 安装指向主工作区，在 worktree 内运行 `make install` 建立独立 `.venv`；安装成功。

## 步骤 1：结果类型、fence 扫描器与候选选择

### 实现

- 新增 `src/code_verifier/parsing/__init__.py`。
- 新增 `src/code_verifier/parsing/code_extractor.py`：
  - `ParseResult`
  - `_FencedCodeBlock`
  - `_normalize_newlines()`
  - `_scan_fenced_code_blocks()`
  - `_select_code_block()`
  - 行级 fence opener / closer 辅助逻辑
- 支持反引号与波浪号 fence、3+ fence 长度、最多 3 个前导空格、最后 Python block 优先、无 Python 时最后无标记 block、未闭合 block 计数和内联反引号保留。
- 新增 `tests/unit/parsing/test_code_extractor.py` 的步骤 1 扫描/选择测试。

### 实际验证

- `make lint`：通过；Ruff check、Ruff format check、strict Mypy 全绿，30 个源文件无问题。
- `.venv/bin/python -m pytest tests/unit/parsing/test_code_extractor.py -k "block or fence or backtick"`：5 passed，2 deselected。

### 偏离说明

- 为满足步骤 1 时 `parsing.__init__` 可重导出公共接口，`extract_python_code()` 在本步骤提供了基于 scanner/selector 的最小实现；输入防御、AST 目标函数检查和完整错误分类在步骤 2 完成。

## 步骤 2：公共提取函数、目标函数检查与失败分类

### 实现

- 完成 `extract_python_code(completion, expected_function_name=None)` 的规格签名与全部防御性边界。
- 新增 `_contains_top_level_function()`，仅通过 `ast.parse()` 检查 module body 的同名 `FunctionDef` / `AsyncFunctionDef`。
- 新增固定错误 taxonomy：`invalid_input`、`invalid_expected_function_name`、`empty_completion`、`no_supported_code_block`、`unclosed_code_block`、`empty_code_block`、`invalid_python_syntax`、`missing_target_function`。
- 所有失败保证 `code=""`；无目标函数要求时不因 Python 语法错误拒绝已提取代码。
- 补充 §9.3 全部边界、不可变结果、换行统一、目标函数与错误 taxonomy 测试。

### 实际验证

- `make lint`：通过；Ruff check、Ruff format check、strict Mypy 全绿，30 个源文件无问题。
- `.venv/bin/python -m pytest tests/unit/parsing/test_code_extractor.py`：29 passed。
