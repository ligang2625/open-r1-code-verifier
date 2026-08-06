# WP4-a Executor 执行报告

- **依据计划**：`ai-work/planner/WP4-a-plan.md`
- **目标阶段**：WP4：Verifier 与 Reward（子阶段 a：统一验证器与结构化验证结果）
- **执行分支**：`feat/wp4`
- **独立 worktree**：`.worktrees/wp4`
- **执行状态**：计划 5 个步骤已全部实现并通过静态检查、全量 CPU 回归、Verification 定向测试与 CLI 边界验收。当前只完成 WP4-a；WP4-b Public/Hidden reward、reward 分量日志、训练与评测接入仍未实现。需由 `wp-plan-reviewer` 独立审查、合并并更新 `proceedings.md` 后，才可在主分支登记本子阶段完成。

本文件为新的 WP4 阶段报告，依据计划与既有 executor 报告不同，因此按 `wp-plan-executor` 的阶段重置规则新建。执行过程未修改 reviewer 报告或 `proceedings.md`。

## 1. 分步交付与提交

### 步骤 1：结构化验证结果、合同校验与安全 mapping

提交：

```text
7e90c7a  feat: add structured verification results
```

新增：

- `src/code_verifier/verification/result_types.py`
- `tests/unit/verification/__init__.py`
- `tests/unit/verification/test_result_types.py`

实现：

- `VerificationContractError`
- `FailureCounts`
- frozen `VerificationResult`
- `validate_verification_result()`
- `verification_result_to_mapping()`

合同覆盖状态类型、精确 bool、非 bool 整数、有限 pass rate、计数守恒、failure taxonomy 排序与唯一性、parse/execution/infrastructure 跨字段一致性，以及嵌套 `ExecutionResult` 的严格复用校验。Mapping 不保存 completion、code、tests、function name 或 metadata，并返回独立容器。

专项验证：

```text
.venv/bin/python -m pytest tests/unit/verification/test_result_types.py
→ 9 passed

make lint
→ Ruff check passed
→ Ruff format check passed
→ strict Mypy passed
```

### 步骤 2：函数名、单测试层与资源限制规范化

提交：

```text
2798018  feat: validate verifier inputs
```

新增 helper：

- `_validate_function_name()`
- `_normalize_tests()`
- `_resource_limits_from_metadata()`

实现：

- 函数名必须是 UTF-8 可编码、非 keyword 的 Python identifier，不做 coercion。
- tests 必须是非空有序 sequence，每项字段恰好为 `input`、`expected`。
- 测试值复用 WP1 JSON schema 校验并深度转换为新的 mutable JSON 容器，保持顺序与 bool/int/float 类型。
- metadata 只读取 `time_limit_seconds` 与 `memory_limit_mb`，允许其它字段存在但不读取其值。
- 输入异常统一为不回显 payload 的 `VerificationContractError`，并在 parser/executor side effect 前失败。

专项验证：

```text
.venv/bin/python -m pytest tests/unit/verification/test_verifier.py \
  -k "function_name or normalize_tests or resource_limits or invalid_inputs"
→ 7 passed, 1 deselected

make lint
→ 全绿
```

### 步骤 3：completion → parser → executor 统一验证器

提交：

```text
360402a  feat: add unified completion verifier
```

新增：

- `_summarize_failure_counts()`
- `_parse_failure_result()`
- `_executor_exception_result()`
- `_executed_result()`
- `verify_completion()`

实现：

- 固定调用顺序：函数名 → tests → resource limits → `extract_python_code()` → `CodeExecutor.execute()`。
- parser 失败不调用 executor，保留 parser taxonomy，全部测试归入 `parse_error`。
- executor 返回后复用 `validate_execution_result()`；畸形结果与 test-count mismatch 均 fail closed 为脱敏 `SANDBOX_ERROR`。
- executor 普通 `Exception` 转为 parsed-but-unexecuted sandbox failure；不捕获 `BaseException`。
- timeout 保持 `executed=True` 且不是 infrastructure failure；返回的 `SANDBOX_ERROR` 标为 infrastructure failure。
- 已返回 per-test failures 按 status 统计；提前停止的未运行测试归入 aggregate status，保证失败计数守恒。
- 防御性复制 `ExecutionResult.test_results`，避免 caller 或 executor 后续修改验证历史。

专项验证：

```text
.venv/bin/python -m pytest tests/unit/verification/test_verifier.py
→ 22 passed

make lint
→ 全绿
```

### 步骤 4：公共 API 与 Mock 端到端集成

提交：

```text
d7f102c  test: add verifier pipeline integration
```

新增：

- `src/code_verifier/verification/__init__.py`
- `tests/integration/test_wp4a_verifier_pipeline.py`

公共 API：

- `FailureCounts`
- `VerificationContractError`
- `VerificationResult`
- `validate_verification_result`
- `verification_result_to_mapping`
- `verify_completion`

Mock 集成覆盖 passed、partial wrong answer、timeout early-stop、missing-target parse failure 与 sandbox error。测试断言 parser exact code、函数名、测试顺序、timeout、memory、FIFO 消耗、有限 pass rate、failure count 守恒、严格 JSON serialization 与 payload 隔离。候选代码体包含若被执行即失败的 sentinel，确认 `MockExecutor` 始终不执行代码。

专项验证：

```text
.venv/bin/python -m pytest tests/integration/test_wp4a_verifier_pipeline.py
→ 3 passed

.venv/bin/python -m pytest tests/unit/verification \
  tests/integration/test_wp4a_verifier_pipeline.py
→ 34 passed

make lint
→ 全绿
```

### 步骤 5：文档、边界与独立验收

随本报告提交：

- `README.md`
  - 项目状态更新为 WP4-a verifier 已实现；
  - 增加最小 Python API 示例；
  - 明确单测试层输入、0 tests fail-closed、parse failure 不执行、只经 `CodeExecutor` 执行与 mapping 脱敏边界；
  - 明确 WP4-b rewards/training/evaluation 未实现。
- `AGENTS.md`
  - 增加 Verification 源码与测试结构；
  - 更新当前 scope；
  - 增加 verifier 单测试层、parser/executor 唯一入口与 mapping 禁止字段规则。

未修改 CLI、YAML、Makefile、Python 依赖、execution/parser/data/training 模块、Open-R1 submodule pin 或 `proceedings.md`。

## 2. 最终实际验收结果

### 静态检查

```text
make lint
→ Ruff check: All checks passed
→ Ruff format: 54 files already formatted
→ strict Mypy: Success, no issues found in 54 source files
```

### 默认全量 CPU 回归

```text
make test
→ 478 passed, 3 skipped
```

三个 skip 均为既有真实 Piston tests，未显式设置 `CODE_VERIFIER_RUN_PISTON=1` 时按设计跳过；本阶段未新增 skip 或 xfail。

首次在新 worktree 运行全量测试时，worktree 的 submodule 目录尚未初始化，`test_collect_environment_records_pinned_submodule` 将父仓库 HEAD 误识别为 Open-R1 commit，结果为 `477 passed, 3 skipped, 1 failed`。随后仅使用主工作区已有只读 checkout 作为本地 reference 初始化既有 submodule pin：

```text
git submodule update --init --recursive \
  --reference /home/dzy/open-r1-code-verifier/third_party/open-r1
→ third_party/open-r1 checked out 1416fa0cf21595d2083b399a2a0bbddd7f6e9563
```

未修改 submodule 内容或 pin；初始化后全量测试通过。

### Verification 定向验收

```text
.venv/bin/python -m pytest tests/unit/verification \
  tests/integration/test_wp4a_verifier_pipeline.py
→ 34 passed, 0 failed, 0 skipped
```

### CLI 边界

```text
.venv/bin/code-verifier --help
→ exit 0
→ commands: record-environment, prepare-data, check-data, parse-code, execute-batch
```

未新增 verifier、reward、training 或 evaluation CLI 子命令。

### 范围与安全搜索

- `src/code_verifier/rewards/` 不存在。
- `src/code_verifier/verification/` 中搜索 `exec(`、`eval(`、`compile(`、`subprocess` 均无匹配。
- Verification 生产代码中搜索 `eval_hidden_tests` 与 `test_layer` 均无匹配。
- 最终变更范围仅包含计划文件、Verification 源码/测试、README、AGENTS 与本 executor 报告；没有 execution/parser/data/training/config/Makefile/pyproject/third-party/proceedings 变更。

## 3. 新增与修改文件

新增：

- `ai-work/planner/WP4-a-plan.md`
- `ai-work/executor/WP4-executor.md`
- `src/code_verifier/verification/__init__.py`
- `src/code_verifier/verification/result_types.py`
- `src/code_verifier/verification/verifier.py`
- `tests/unit/verification/__init__.py`
- `tests/unit/verification/test_result_types.py`
- `tests/unit/verification/test_verifier.py`
- `tests/integration/test_wp4a_verifier_pipeline.py`

修改：

- `README.md`
- `AGENTS.md`

## 4. 配置、依赖与安全影响

- 未修改或新增 YAML 配置。
- 未新增 Python package 依赖，未修改 `pyproject.toml` 或 Makefile。
- 未修改 CLI 参数或命令。
- 未修改 execution/parser/data/training 生产代码及其版本常量。
- 未创建 `src/code_verifier/rewards/`。
- 未修改 `third_party/open-r1/**` 内容或 pin。
- 未修改 reviewer 报告或 `proceedings.md`。
- Verification summary 不保存 completion、extracted code、tests、function name 或 metadata。可选嵌套 execution mapping 沿用 WP3 的 bounded stdout/stderr 合同，因此调用方仍应按敏感结果处理。

## 5. 环境与计划偏离

- 受工作区边界限制，独立 worktree 位于主仓库内部 `.worktrees/wp4`，但所有实现与提交均在独立 `feat/wp4` 分支完成。
- worktree 临时创建未提交的 `.venv` 符号链接，复用主仓库虚拟环境。
- 为确保 shared venv 的 editable package 指向当前 worktree，执行了：

```text
uv pip install --python .venv/bin/python --no-deps --editable .
```

该操作只改变本地虚拟环境安装位置，不修改项目依赖声明或仓库文件。
- 为通过既有环境记录测试，初始化了 worktree 内既有只读 Open-R1 submodule checkout；未改 pin。
- 无 API 签名、失败 taxonomy、测试层边界、reward 范围或验收口径偏离。

## 6. 已知限制与后续工作

- WP4-a 只产出结构化验证事实，不计算 reward。
- Public/Hidden 测试来源选择、`compute_code_rewards()`、reward 分量日志、TRL batch 对齐与训练测试层隔离留给 WP4-b。
- 验证器是同步单 completion API；批量 reward orchestration 尚未实现。
- 验证器依赖调用方提供正确、已隔离的单测试层；本阶段通过接口形状阻断 verifier 自行访问其它测试层。

## 7. Reviewer 下一轮重点

独立复审应至少重新验证：

1. `VerificationResult` 全部跨字段与 failure-count invariants；
2. 0 tests、畸形 JSON、UTF-8、函数名和 resource limits 在 parser/executor 前失败；
3. parser 是唯一提取入口、`CodeExecutor` 是唯一执行入口；
4. parse failure、timeout、returned sandbox、executor exception 与 malformed result 的 fail-closed 语义；
5. early-stop 未运行测试归因与 pass-rate/failure-count 守恒；
6. caller tests 和 executor result 的防御性复制；
7. mapping 的 JSON finiteness、独立容器与敏感字段隔离；
8. verifier 接口无法选择或访问 visible/train-hidden/eval-hidden 层；
9. 全量 `make lint`、`make test` 与 Verification 定向测试；
10. rewards、CLI、配置、execution/parser、third-party 和 `proceedings.md` 无越界改动。

Executor 未执行 push 或 merge。审查通过后由 `wp-plan-reviewer` 合并 `feat/wp4`，向 `proceedings.md` 追加 WP4-a 子阶段记录；不得将 WP4 整体标记为完成。
