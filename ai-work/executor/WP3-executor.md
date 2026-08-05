# WP3 执行报告

## 基于 plan 的执行结果

- **执行计划**：`ai-work/planner/WP3-a-plan.md`
- **目标阶段**：WP3-a（安全执行器基础合同与 Mock 基线）
- **执行分支**：`feat/wp3`
- **独立 worktree**：`.worktrees/wp3`
- **执行状态**：本子阶段计划已完成并通过验收；WP3 整体仍为部分完成。

## 1. 已完成事项

1. 实现规格 §8.3 的稳定执行合同：
   - `ExecutionStatus`
   - `TestCaseResult`
   - `ExecutionResult`
   - `CodeExecutor`
2. 实现严格执行请求与结构化结果校验：
   - 非空代码与合法 Python 函数名；
   - 精确 `{input, expected}` 测试 mapping；
   - JSON 值、NaN/Inf、资源限制、计数、通过率和状态一致性；
   - 支持提前停止下 `len(test_results) <= total_tests`。
3. 实现 `execution_result_to_mapping()`，以稳定字段和字符串枚举值生成 JSON-safe mapping。
4. 实现不会解释或执行代码的 FIFO `MockExecutor`：
   - 构造时验证并深复制预置结果；
   - 调用时校验请求、记录调用、按 FIFO 消费结果；
   - 请求、调用历史和返回结果均采用防御性深复制；
   - 队列耗尽时抛固定 `AssertionError`，不伪装成沙箱错误。
5. 增加 Data test mapping → parser → `CodeExecutor` → Mock → JSON mapping 的最小集成闭环。
6. 更新 README 与 AGENTS，明确 WP3-a 只建立合同与测试替身，真实不可信代码执行和安全隔离尚未实现。

## 2. 新增与修改文件

### 新增

- `ai-work/planner/WP3-a-plan.md`
- `src/code_verifier/execution/__init__.py`
- `src/code_verifier/execution/base.py`
- `src/code_verifier/execution/mock.py`
- `tests/unit/execution/__init__.py`
- `tests/unit/execution/test_base.py`
- `tests/unit/execution/test_mock.py`
- `tests/integration/test_wp3a_mock_execution.py`

### 修改

- `README.md`
- `AGENTS.md`

### 明确未修改

- `pyproject.toml`
- `Makefile`
- `configs/**`
- `src/code_verifier/cli.py`
- `src/code_verifier/parsing/**`
- `src/code_verifier/data/**`
- `src/code_verifier/training/open_r1_adapter.py`
- `third_party/open-r1/**`
- `proceedings.md`

## 3. 新增公开符号

- `ExecutionStatus`
- `TestCaseResult`
- `ExecutionResult`
- `CodeExecutor`
- `ExecutionContractError`
- `validate_execution_request()`
- `validate_test_case_result()`
- `validate_execution_result()`
- `execution_result_to_mapping()`
- `MockExecutionCall`
- `MockExecutor`

## 4. 分步提交

- `b7d34d8` — `feat: add execution contract types`
- `acd1987` — `feat: validate execution contracts`
- `e164d8e` — `feat: add non-executing mock executor`
- `94a008c` — `test: add wp3a execution integration`

## 5. 实际验证结果

### 静态检查

```text
make lint
```

最终结果：通过。

- Ruff check：通过；
- Ruff format check：37 files already formatted；
- strict Mypy：Success: no issues found in 37 source files。

### Execution Layer 专项测试

```text
.venv/bin/python -m pytest tests/unit/execution tests/integration/test_wp3a_mock_execution.py
```

最终结果：`80 passed`。

### 全量回归

```text
make test
```

最终结果：`257 passed`。

首次全量运行出现 `256 passed, 1 failed`，失败原因为新 worktree 的 Open-R1 submodule 尚未完成初始化，环境采集将父仓库提交误识别为 submodule commit。未修改业务代码、环境采集实现或测试预期；完成 worktree submodule 初始化并确认：

```text
git -C third_party/open-r1 rev-parse HEAD
1416fa0cf21595d2083b399a2a0bbddd7f6e9563
```

随后重新运行 `make test`，全部 257 个测试通过。

### 导入 smoke

```text
.venv/bin/python -c "from code_verifier.execution import CodeExecutor, ExecutionResult, ExecutionStatus, MockExecutor, TestCaseResult; print(ExecutionStatus.PASSED.value)"
```

结果：输出 `passed`，退出码 0。

### 禁止直接代码执行检查

在 `src/code_verifier/execution/` 中分别搜索 `exec(`、`eval(`、`compile(`，均无匹配。Mock 的恶意代码字符串测试确认不会创建 sentinel 文件。

## 6. 配置与上游影响

- 未修改项目配置、依赖版本、Makefile 或 YAML。
- 未修改 `third_party/open-r1/**`；仅在独立 worktree 中初始化既有 pinned submodule 工作副本，commit 保持 `1416fa0cf21595d2083b399a2a0bbddd7f6e9563`。
- 未写入 `proceedings.md`；阶段最终审查与合并后由 reviewer 统一登记。

## 7. 与计划的偏离

- 计划默认建议在主仓库同级目录创建 worktree。CodexPro 只允许打开主仓库根目录以内的工作区，因此改为 `.worktrees/wp3`。该路径仍是独立 Git worktree，所有 WP3-a 代码、测试、文档和报告修改均在 `feat/wp3` 分支完成，主工作区未直接修改。
- 无接口、功能范围、测试预期或配置方面的计划偏离。

## 8. 已知限制与下一步

本阶段没有实现真实沙箱，不能运行不可信代码，也不能宣称满足 WP3 的网络、文件系统、CPU、wall-clock、内存、PID、输出限制和宿主环境隔离验收。

下一步应分别执行：

- WP3-b：本地 Piston 执行、函数测试 harness、安全资源限制与真实沙箱状态映射；
- WP3-c：批量并发、可选缓存、CLI 和 WP3 完整验收。

---

## 代码修复报告（R1）

- **审查依据**：`ai-work/reviewer/WP3-review.md` R1
- **修复提交**：`2bcd2ab` — `fix: harden execution contract validation`
- **修复状态**：P1、P2 两个“主要”问题均已修复，无异议项或未处理项。

### 1. P1：非法请求逃逸为 `RecursionError` / `OverflowError`

已完成以下最小修复：

- `_is_finite_number()` 不再直接把任意大小整数传给 `math.isfinite()`；先安全转换为 float，并将 `OverflowError` 归一为非法数值。
- request timeout、per-test runtime、aggregate runtime 和 pass rate 中无法表示为有限 float 的超大整数均由公共校验函数拒绝，并统一抛出 `ExecutionContractError`。
- 新增 `_validate_request_json_value()`，将底层 `SchemaError` 与递归 JSON 结构产生的 `RecursionError` 统一转换为 `ExecutionContractError`。
- 增加自引用 list 和四类超大整数边界回归测试。

### 2. P2：错误文本泄漏用户控制的 JSON 键名

已完成以下修复：

- execution 层不再透传 `validate_json_value()` 的原始 `SchemaError` 文本。
- 非法 input / expected JSON 值统一使用固定格式：`tests[index].input|expected contains an invalid JSON value`。
- 新增 input 与 expected 参数化测试，确认嵌套对象键名和合法 sibling 字符串值均不会出现在异常文本中。

### 3. 修改文件

- `src/code_verifier/execution/base.py`
- `tests/unit/execution/test_base.py`

未修改审查报告、`proceedings.md`、配置、依赖或 `third_party/open-r1/**`。

### 4. 实际复测结果

```text
PYTHONPATH=src /home/dzy/open-r1-code-verifier/.venv/bin/python -m pytest tests/unit/execution/test_base.py
→ 74 passed

make lint VENV=/home/dzy/open-r1-code-verifier/.venv
→ Ruff check passed
→ 37 files already formatted
→ strict Mypy: no issues found in 37 source files

PYTHONPATH=src /home/dzy/open-r1-code-verifier/.venv/bin/python -m pytest \
  tests/unit/execution tests/integration/test_wp3a_mock_execution.py
→ 86 passed

PYTHONPATH=src make test VENV=/home/dzy/open-r1-code-verifier/.venv
→ 263 passed

PYTHONPATH=src /home/dzy/open-r1-code-verifier/.venv/bin/python -c \
  "from code_verifier.execution import CodeExecutor, ExecutionResult, ExecutionStatus, MockExecutor, TestCaseResult; print(ExecutionStatus.PASSED.value)"
→ passed
```

在 `src/code_verifier/execution/` 中分别精确搜索 `exec(`、`eval(`、`compile(`，均无匹配。一次正则组合搜索因当前环境未安装 `rg` 无法运行，随后使用上述三次精确搜索完成同等核对。

### 5. 环境说明

当前独立 worktree 仍未包含自己的 `.venv`，因此复测沿用审查报告采用的主仓库虚拟环境，通过显式 `VENV` 与 `PYTHONPATH=src` 确保导入和执行的是本 worktree 源码。未为此修改项目配置或提交环境文件。
