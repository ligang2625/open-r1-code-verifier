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

## 步骤 3：`parse-code` CLI 调试命令

### 实现

- `_add_common_arguments()` 新增 `output_dir_default`，保持 `prepare-data` 必填参数和 `check-data` 的 `outputs/check-data` 默认值。
- 新增 `_read_completion()`：`-` 读取 stdin，其他值按 UTF-8 文件读取。
- 新增 `_parse_code()`：成功/结构化失败均输出单行 JSON；退出码分别为 0 / 1；I/O 错误写 stderr 并返回 2。
- 新增 `parse-code` 子命令及 `--completion-file`、`--expected-function-name`，并保留五项公共参数。
- 新增 CLI 注册、公共参数、stdin/file、失败 JSON、I/O 错误和 WP1 默认值回归测试。

### 实际验证

- `make lint`：通过；30 个源文件静态检查全绿。
- `.venv/bin/python -m pytest tests/unit/test_cli.py`：19 passed。
- 工具策略禁止 shell 管道，因此使用 Python `StringIO` 等价注入 stdin 调用 `parse-code --completion-file - --expected-function-name solve`：退出 0，stdout 为单行 JSON，`success=true`、`error_type=null`，代码不含 fence。
- 第一次等价 smoke 的 shell 字符串包含未转义反引号，被 shell 命令替换并返回结构化 `empty_completion`；改用 `chr(96) * 3` 构造 fence 后验证通过。该失败属于验证命令转义问题，不是 parser/CLI 缺陷。

## 步骤 4：文档与 WP2 全量验收

### 文档变更

- `README.md` 更新项目状态并新增“WP2 code parser”小节，包含 Python API、文件/stdin CLI、0/1/2 退出码、默认禁用完整 completion 回退，以及“不执行代码、不判断语义”的边界说明。
- `AGENTS.md` 增加 Parsing Layer 与 parser 测试路径，并将当前范围更新为 WP0–WP2 已实现、不得提前实现 WP3+。
- `proceedings.md` 保持只读，未修改。

### 最终实际验证

- `make lint`：通过；Ruff check、Ruff format check、strict Mypy 全绿，30 个源文件无问题。
- `make test`：171 passed（WP1 基线 135 项无回归，WP2 parser/CLI 新增测试全部收集）。
- `.venv/bin/code-verifier --help`：退出 0，列出 `parse-code`。
- `.venv/bin/code-verifier parse-code --help`：退出 0，列出 `--completion-file`、`--expected-function-name` 与五项公共参数。
- README stdin smoke 的等价 `StringIO` 执行：退出 0；JSON 中 `success=true`、`error_type=null`、`num_code_blocks=1`，代码仅为 `def solve...`，不含 reasoning 或 fence。
- `third_party/open-r1`：无 changed files、无 diff；commit 为 `1416fa0cf21595d2083b399a2a0bbddd7f6e9563`。

## 完成结果

### 新建文件

- `src/code_verifier/parsing/__init__.py`
- `src/code_verifier/parsing/code_extractor.py`
- `tests/unit/parsing/__init__.py`
- `tests/unit/parsing/test_code_extractor.py`
- `ai-work/planner/WP2-plan.md`（从主工作区复制到独立分支）
- `ai-work/executor/WP2-executor.md`

### 修改文件

- `src/code_verifier/cli.py`
- `tests/unit/test_cli.py`
- `README.md`
- `AGENTS.md`

### 主要公共交付

- `ParseResult`
- `extract_python_code()`
- `parse-code` CLI
- 29 项 parser 单元测试与 7 项新增/扩展 CLI 测试场景

### 计划偏离与限制

- CodexPro 安全根目录不允许打开仓库同级 worktree，因此 worktree 建在主仓库内部 `.worktrees/wp2`；仍是独立 Git worktree 与 `feat/wp2` 分支，主工作区业务文件未被修改。
- 远程 submodule 初始化失败后使用本地固定 checkout 作为 clone 源；目标 commit 与计划一致，上游内容未修改。
- 工具策略禁止 shell 管道，stdin smoke 使用 `StringIO` 等价执行；CLI 单元测试同时直接覆盖真实 stdin 路径。
- parser 只覆盖计划定义的 fenced block 子集，不实现完整 CommonMark、语义/安全判断或代码执行。

### 状态与下一步

WP2 计划的 4 个步骤均已实现并通过实际验收。改动已提交到独立分支 `feat/wp2`，未 push、未合并到 `main`。下一步应使用 `wp-plan-reviewer` 对该分支进行独立审查；审查通过后由 reviewer 合并并更新 `proceedings.md`。
