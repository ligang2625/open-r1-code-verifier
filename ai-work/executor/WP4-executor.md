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

---

# WP4-b Executor 执行报告

- **依据计划**：`ai-work/planner/WP4-b-plan.md`
- **目标阶段**：WP4：Verifier 与 Reward（子阶段 b：Reward Layer、测试层隔离与 WP4 整体收口）
- **执行分支**：`feat/wp4-b`
- **独立 worktree**：`.worktrees/wp4-b`
- **执行状态**：计划 6 个步骤已全部实现。Reward Layer、Public/Hidden 测试源隔离、component records、Reward 单元/集成测试、README/AGENTS 边界文档均完成；最终静态检查、全量 CPU 回归、WP4 联合定向测试与 CLI 边界验收通过。Executor 未修改 `proceedings.md`，WP4 最终登记仍需 `wp-plan-reviewer` 独立复审、合并后完成。

## 1. 分步交付与提交

### 步骤 1：Reward 输入合同、completion 提取与 batch 对齐

提交：

```text
a8f4adf  feat: add reward input contracts
```

新增 `RewardContractError`、batch sequence/长度校验、raw/Open-R1 chat completion 精确文本提取、全批 completion 预校验和 executor 结构 guard。四列长度在任何验证执行前显式比较，不使用 `zip` 作为对齐机制；错误消息不回显 completion 或 dataset payload。

专项验证：

```text
../../.venv/bin/python -m pytest tests/unit/rewards/test_common.py -k "batch or completion or executor"
→ 16 passed

make VENV=../../.venv lint
→ Ruff check passed
→ Ruff format check passed
→ strict Mypy passed
```

### 步骤 2：统一 reward 公式与 component record

提交：

```text
31d8d49  feat: add unified code reward scoring
```

`compute_code_rewards()` 只接收调用方已选择的单一 `tests_batch`，固定调用 WP4-a `verify_completion()`。实现的唯一总分公式为：

```text
total_reward = test_reward + executable_reward + timeout_penalty + invalid_format_penalty
```

其中：

- `test_reward = verification.pass_rate`；
- parsed + executed + 非 infrastructure failure 时 `executable_reward = 0.1`；
- `TIMEOUT` 时 `timeout_penalty = -0.2`；
- `PARSE_ERROR` 时 `invalid_format_penalty = -0.1`；
- 不 round、不 clamp、不加入长度奖励或规格外 penalty。

`VerificationContractError` 被转换为脱敏 `RewardContractError("reward item violates verification input contract")`；executor 普通异常沿用 WP4-a fail-closed sandbox 语义，Reward Layer 正常得到有限低分而不是训练级异常。

每条 component record 固定包含：

```text
mode
test_reward
executable_reward
timeout_penalty
invalid_format_penalty
total_reward
status
parsed
executed
infrastructure_failure
passed_tests
total_tests
parse_error_type
failure_counts
```

记录严格 JSON-safe 且不包含 completion、code、tests、function name、metadata、stdout、stderr 或 `execution_result`。

专项验证：

```text
../../.venv/bin/python -m pytest tests/unit/rewards/test_common.py
→ 29 passed

make VENV=../../.venv lint
→ 全绿
```

### 步骤 3：Public reward 薄封装

提交：

```text
7f91a73  feat: add public code reward wrapper
```

`public_code_reward()` 保留规格参数顺序与 `list[float]` 返回形态，只把 `visible_tests` 传给 common core。若 kwargs 出现 `train_hidden_tests` 或 `eval_hidden_tests`，在任何 verifier/executor 调用前抛 `RewardContractError`；其它无关 dataset 列可忽略。Executor 必须由调用方通过 `executor=` 绑定。

专项验证：

```text
../../.venv/bin/python -m pytest tests/unit/rewards/test_public_reward.py
→ 7 passed

make VENV=../../.venv lint
→ 全绿
```

### 步骤 4：Hidden reward 薄封装

提交：

```text
e1b8760  feat: add hidden code reward wrapper
```

`hidden_code_reward()` 只把 `train_hidden_tests` 传给 common core，合法的 `visible_tests` callback 列被忽略而不参与 fallback 或混合计分；`eval_hidden_tests` 在执行前拒绝。Public/Hidden 对相同 verification result 的记录除 `mode` 标签外完全相同，证明公共辅助项与失败解释没有分叉。

专项验证：

```text
../../.venv/bin/python -m pytest \
  tests/unit/rewards/test_hidden_reward.py \
  tests/unit/rewards/test_public_reward.py
→ 14 passed

make VENV=../../.venv lint
→ 全绿
```

### 步骤 5：Rewards 公共 API 与 Mock 集成

提交：

```text
7cdc7c8  test: add wp4 reward integration coverage
```

`code_verifier.rewards` 公开导出：

- `RewardContractError`
- `compute_code_rewards`
- `public_code_reward`
- `hidden_code_reward`

WP4-b Mock 集成覆盖当前固定 Open-R1 chat-style completion、raw string completion、Public visible-only、Hidden train-hidden-only、eval-hidden fail-before-execution、passed/partial/wrong/timeout/parse/sandbox/executor exception、reward/record 一一对齐、有限值、严格 JSON serialization 与 payload isolation。

专项验证：

```text
../../.venv/bin/python -m pytest \
  tests/unit/rewards \
  tests/integration/test_wp4b_reward_pipeline.py
→ 49 passed

make VENV=../../.venv lint
→ 全绿
```

### 步骤 6：文档与 WP4 整体验收

更新：

- `README.md`：记录完整 WP4 Reward Layer、Public/Hidden API、统一公式、executor 注入、Open-R1 chat completion 兼容、component record 边界与 WP7 后续接入边界；未宣称已有 GRPO/trainer/evaluation 命令。
- `AGENTS.md`：增加 rewards 源码/测试结构，scope 更新为 WP0–WP4 已实现、WP5+ 未实现，并明确 reward 只能经 verifier → executor、Public/Hidden 必须共享 core、eval-hidden 禁止进入训练 reward、WP7 trainer/config 不得提前进入 WP4。

本阶段未修改 YAML、CLI、Makefile、`pyproject.toml`、Open-R1 生产内容或 pin，也未修改 verification/execution/parser/data/training 生产代码；未修改 reviewer 报告或 `proceedings.md`。

## 2. 最终实际验收结果

### 静态检查

```text
make VENV=../../.venv lint
→ Ruff check: All checks passed
→ Ruff format: 63 files already formatted
→ strict Mypy: Success, no issues found in 63 source files
```

### 默认全量 CPU 回归

第一次运行：

```text
make VENV=../../.venv test
→ 529 passed, 3 skipped, 1 failed
```

唯一失败为既有 `test_collect_environment_records_pinned_submodule`：当前新 worktree 的 `third_party/open-r1` 尚未初始化，环境记录将当前 feature HEAD 误识别为 Open-R1 commit。Reward/Verification 测试均已通过。随后仅初始化固定的只读 submodule checkout：

```text
git submodule update --init --recursive --reference ../../third_party/open-r1
→ third_party/open-r1 checked out 1416fa0cf21595d2083b399a2a0bbddd7f6e9563
```

未修改 submodule 内容或 pin。重跑结果：

```text
make VENV=../../.venv test
→ 530 passed, 3 skipped
```

三个 skip 均为既有真实 Piston tests，未显式设置 `CODE_VERIFIER_RUN_PISTON=1` 时按项目既有机制跳过；WP4-b 未新增 skip 或 xfail。

### WP4 Verification + Reward 联合定向验收

```text
../../.venv/bin/python -m pytest \
  tests/unit/verification \
  tests/unit/rewards \
  tests/integration/test_wp4a_verifier_pipeline.py \
  tests/integration/test_wp4b_reward_pipeline.py
→ 86 passed, 0 failed, 0 skipped
```

其中 Reward 定向 suite 为 49 passed；WP4-a Verification 全部回归通过，无语义回退。

### CLI 边界

```text
../../.venv/bin/python -m code_verifier.cli --help
→ exit 0
→ commands: record-environment, prepare-data, check-data, parse-code, execute-batch
```

未新增 reward、training、GRPO 或 evaluation CLI 命令。

### 范围与安全检查

- `src/code_verifier/rewards/common.py` 中搜索 `zip(` 无匹配，核心不存在 silent truncation 路径。
- `src/code_verifier/rewards/` 中搜索 `extract_python_code` 无匹配，Reward Layer 不自行解析代码。
- `eval_hidden_tests` 在 Reward 生产代码中只出现在 Public/Hidden 的拒绝 guard。
- `train_hidden_tests` 在 Public 生产代码中只出现在拒绝 guard。
- 当前步骤 6 工作区变更仅为 `README.md`、`AGENTS.md` 与本 executor 报告；已提交的前 5 步均只涉及计划中的 Reward 源码/测试文件。
- 未修改配置、依赖声明、CLI、`third_party/open-r1/**` 内容/pin、verification/execution/parser/data/training 生产代码或 `proceedings.md`。

## 3. WP4-b 新增与修改文件

新增：

- `src/code_verifier/rewards/__init__.py`
- `src/code_verifier/rewards/common.py`
- `src/code_verifier/rewards/public_reward.py`
- `src/code_verifier/rewards/hidden_reward.py`
- `tests/unit/rewards/__init__.py`
- `tests/unit/rewards/test_common.py`
- `tests/unit/rewards/test_public_reward.py`
- `tests/unit/rewards/test_hidden_reward.py`
- `tests/integration/test_wp4b_reward_pipeline.py`

修改：

- `README.md`
- `AGENTS.md`
- `ai-work/executor/WP4-executor.md`

计划文件 `ai-work/planner/WP4-b-plan.md` 由 planner 阶段创建，本轮 executor 未修改。

## 4. 配置、依赖与环境影响

- **配置变化：无。** 未新增或修改 YAML。
- **依赖声明变化：无。** 未修改 `pyproject.toml`、Makefile 或 Open-R1 pin。
- **CLI 变化：无。** 未增加参数或命令。
- **后续 WP 功能：无。** 未实现 WP5 evaluation、WP6 SFT、WP7 GRPO/trainer adapter、reward registry 或持久化 reward logging。
- 独立 worktree 未初始展开 submodule，最终验收前仅初始化了固定 commit `1416fa0...e9563` 的只读 checkout；该操作不改变 Git pin。
- shared venv 初始未绑定当前 worktree。一次 `make VENV=../../.venv install` 因 worktree submodule 未初始化而失败，并曾让 `uv` 默认创建 Python 3.12 venv；随后显式恢复为项目目标 Python 3.10.12，并用 `uv` 将当前 worktree和主工作区固定 Open-R1 checkout以 editable 方式安装，再安装项目既有锁定数据/开发依赖。上述操作只改变本地虚拟环境，不修改仓库依赖声明。

## 5. WP4 整体交付判断

从 executor 的计划执行与验收结果看，WP4 §20 计划交付已经齐备：

- WP4-a unified verifier 保持全绿；
- reward common 已实现；
- Public reward 只使用 visible tests；
- Hidden reward 只使用 train-hidden tests；
- 两种 reward 只在测试来源与 component `mode` 标签上不同；
- eval-hidden 无法通过已知 wrapper 字段进入训练 reward；
- batch 长度不一致在执行前失败；
- reward 与 component record 数量严格对齐；
- reward/component 数值均有限；
- parser failure、timeout、sandbox/infrastructure failure 符合既定合同；
- component records JSON-safe 且 payload-free；
- 全量测试、WP4 定向测试、lint/type/format 与 CLI 边界均通过。

因此 WP4-b 已达到提交给 reviewer 的验收状态，但 executor **不自行宣布主分支 WP4 完成**。下一步必须由 `wp-plan-reviewer` 在 `feat/wp4-b` 独立复测与审查；只有 reviewer 最终通过并合并后，才能更新 `proceedings.md` 将 WP4 登记为整体完成。

Executor 未执行 push 或 merge，也未修改 `proceedings.md`。

---

# 代码修复报告（WP4-a R1）

## 1. 修复依据与范围

- 审查报告：`ai-work/reviewer/WP4-review.md`
- 审查轮次：WP4-a R1
- 审查结论：需修改
- 修复范围：全部主要/次要问题 M1、m1
- 未处理项：无
- 异议项：无
- 修复分支 / worktree：`feat/wp4` / `.worktrees/wp4`

本轮严格按 R1 问题清单修复 Verification Layer；未修改 reviewer 报告、`proceedings.md`、execution/parser/data/training、配置、依赖或 `third_party/open-r1/**`。

## 2. M1：保留 PARSE_ERROR 作为 parser-only taxonomy

修复提交：

```text
eb21727  fix: reserve parse errors for parser failures
```

修复内容：

- `validate_verification_result()` 新增强约束：`status is ExecutionStatus.PARSE_ERROR` 只能出现在 `parsed=False` 的 parser failure 结果中；`parsed=True/status=PARSE_ERROR` 直接拒绝。
- 对 `executed=True` 的嵌套 `ExecutionResult` 增加 Verification 层约束：顶层 status 或任一 `TestCaseResult.status` 为 `PARSE_ERROR` 均视为非法 executor result。
- `verify_completion()` 在 executor 返回并通过既有 `validate_execution_result()` 后，额外拒绝顶层或逐测试 `PARSE_ERROR`；该异常仍位于 executor 接收边界的普通 `Exception` fail-closed 区域，因此统一转为 sanitized `SANDBOX_ERROR`。
- executor 返回非法 parse taxonomy 后的结果固定保持：`parsed=True`、`executed=False`、`infrastructure_failure=True`、`pass_rate=0.0`、`execution_result=None`，所有测试计入 `sandbox_error`。
- 新增直接合同回归，覆盖顶层 `PARSE_ERROR` 与 nested per-test `PARSE_ERROR`。
- 新增 `verify_completion()` 回归，确认两种 executor-side parse status 都 fail-closed 为 sandbox failure，不再污染 parser taxonomy 或 WP4-b 的 invalid-format 判定语义。

专项验证：

```text
../../.venv/bin/python -m pytest \
  tests/unit/verification/test_result_types.py \
  tests/unit/verification/test_verifier.py
→ 34 passed

make VENV=../../.venv lint
→ Ruff check passed
→ Ruff format check passed
→ strict Mypy passed
```

## 3. m1：补齐 Verification 包 future annotations 规则

修复提交：

```text
1daefd6  fix: align verification package annotations
```

修复内容：

- 在 `src/code_verifier/verification/__init__.py` 模块 docstring 后新增 `from __future__ import annotations`。
- 公共导出、运行时行为与 API 签名均未改变。

专项验证：

```text
make VENV=../../.venv lint
→ Ruff check passed
→ Ruff format check passed
→ strict Mypy passed
```

## 4. R1 最终总体验收

### 静态检查

```text
make VENV=../../.venv lint
→ Ruff check: All checks passed
→ Ruff format: 54 files already formatted
→ strict Mypy: Success, no issues found in 54 source files
```

### 默认全量 CPU 回归

```text
make VENV=../../.venv test
→ 481 passed, 3 skipped
```

三个 skip 均为既有真实 Piston tests；本轮未新增 skip 或 xfail。

### Verification 定向验收

```text
../../.venv/bin/python -m pytest \
  tests/unit/verification \
  tests/integration/test_wp4a_verifier_pipeline.py
→ 37 passed, 0 failed, 0 skipped
```

相比 R1 审查前的 34 项，新增 3 个 M1 回归实例：一个直接结构化合同测试，以及顶层/逐测试 executor `PARSE_ERROR` 两个 verifier fail-closed 实例。

### CLI 边界

首次直接运行 `../../.venv/bin/code-verifier --help` 时，console-script shebang 仍指向 worktree 本地 `.venv/bin/python`，而该忽略链接此前不存在，因此命令未启动。恢复 reviewer 已使用的本地忽略链接：

```text
ln -s ../../.venv .venv
```

随后实际运行：

```text
.venv/bin/code-verifier --help
→ exit 0
→ commands: record-environment, prepare-data, check-data, parse-code, execute-batch
```

未新增 verifier、reward、training 或 evaluation CLI 子命令；`.venv` 链接不属于跟踪文件。

## 5. 修复完成状态

- R1 M1、m1 均已修复并有对应验证。
- `PARSE_ERROR` 在 Verification Layer 中现在严格等价于 parser failure；executor 无法通过顶层或逐测试状态注入该 taxonomy。
- executor-side 非法 `PARSE_ERROR` 统一失败关闭为 sanitized `SANDBOX_ERROR`。
- 无未处理问题、异议项或无法复现项。
- 未修改审查报告、`proceedings.md` 或 `third_party/open-r1/**`。
- 未执行 push 或 merge。
- 下一步由 `wp-plan-reviewer` 执行 WP4-a R2 独立复审；只有复审通过后才可合并并登记 WP4-a 子阶段完成。

---

# 代码修复报告（WP4-b R1）

## 1. 修复依据与范围

- 审查报告：`ai-work/reviewer/WP4-review.md`
- 审查轮次：WP4-b R1
- 审查结论：需修改
- 修复范围：全部主要问题 M1、M2
- 未处理项：无
- 异议项：无
- 修复分支 / worktree：`feat/wp4-b` / `.worktrees/wp4-b`

本轮只修复 Reward Layer 被 reviewer 点名的两个合同缺陷及对应回归测试；未修改 reviewer 报告、`proceedings.md`、verification/execution/parser/data/training、配置、依赖或 `third_party/open-r1/**`。

## 2. M1：infrastructure failure 的正 reward 归零

修复提交：

```text
8125115  fix: enforce reward failure contracts
```

修复内容：

- `src/code_verifier/rewards/common.py` 的 `_reward_components_from_verification()` 现在在 `result.infrastructure_failure=True` 时固定令 `test_reward=0.0`。
- 既有 `executable_reward` 规则保持不变：infrastructure failure 时为 `0.0`；不新增任何 sandbox penalty，因此 `SANDBOX_ERROR` 的总 reward 固定为 `0.0`。
- unit 回归改为合法的“前序一个测试 passed、下一测试 sandbox error”结构，明确断言 `passed_tests=1` 但 `test_reward=0.0`、`executable_reward=0.0`、总 reward `0.0`。
- WP4-b integration 同样覆盖 passed→sandbox early-stop，避免只测试 `passed_tests=0` 的弱场景。

## 3. M2：公开 common core 强制校验 executor 配置

同一修复提交：

```text
8125115  fix: enforce reward failure contracts
```

修复内容：

- `compute_code_rewards()` 在进入计分前调用 `_require_executor(executor)`，并把验证后的 executor 传给 `verify_completion()`。
- direct-core 不再把 `executor=object()` 等配置错误交给 verifier fail-closed 成 `SANDBOX_ERROR`；现在直接抛出脱敏 `RewardContractError`。
- executor guard 位于 empty-batch 早返回之前，因此空 batch 与非空 batch 都执行相同配置合同校验。
- 新增参数化 unit 回归，分别覆盖 batch size 0 与 1 的无效 executor。

## 4. R1 修复验证

### 受影响专项测试

```text
../../.venv/bin/python -m pytest \
  tests/unit/rewards/test_common.py \
  tests/integration/test_wp4b_reward_pipeline.py
→ 37 passed
```

### 静态检查

```text
make VENV=../../.venv lint
→ Ruff check: All checks passed
→ Ruff format: 63 files already formatted
→ strict Mypy: Success, no issues found in 63 source files
```

### 默认全量 CPU 回归

```text
make test VENV=../../.venv
→ 532 passed, 3 skipped
```

三个 skip 均为既有真实 Piston tests；本轮未新增 skip 或 xfail。

### WP4 联合定向验收

```text
../../.venv/bin/python -m pytest \
  tests/unit/verification \
  tests/unit/rewards \
  tests/integration/test_wp4a_verifier_pipeline.py \
  tests/integration/test_wp4b_reward_pipeline.py
→ 88 passed, 0 failed, 0 skipped
```

### CLI 边界

```text
../../.venv/bin/python -m code_verifier.cli --help
→ exit 0
→ commands: record-environment, prepare-data, check-data, parse-code, execute-batch
```

未新增 verifier、reward、training 或 evaluation CLI 子命令。

## 5. 修复完成状态

- WP4-b R1 M1、M2 均已修复并有 unit/integration 回归。
- infrastructure failure 即使已有部分 passed tests，也不会获得 test/executable 正分。
- direct `compute_code_rewards()` 的 executor 配置错误不会再伪装成 sandbox reward，空/非空 batch 均 fail-fast。
- `make lint`、`make test`、WP4 联合定向测试与 CLI 边界均实际运行通过。
- 无未处理问题、异议项或无法复现项。
- 未修改审查报告、`proceedings.md` 或 `third_party/open-r1/**`。
- 未执行 push 或 merge。
- 下一步由 `wp-plan-reviewer` 对 WP4-b 执行下一轮独立复审；只有复审通过后才可合并并登记 WP4 整体完成。

---

# 代码修复报告（WP4-b R2）

## 1. 修复依据与范围

- 审查报告：`ai-work/reviewer/WP4-review.md`
- 审查轮次：WP4-b R2
- 审查结论：需修改
- 修复范围：主要问题 M3
- 未处理项：无
- 异议项：无
- 修复分支 / worktree：`feat/wp4-b` / `.worktrees/wp4-b`

本轮只处理 reviewer 新发现的 Piston 多失败聚合下 nested sandbox/timeout Reward 语义，不修改 Piston/Verification 公共签名，不修改 reviewer 报告、`proceedings.md`、配置、依赖或 `third_party/open-r1/**`。

## 2. M3：识别 nested terminal failures

修复提交：

```text
6c8f94b  fix: honor nested terminal reward failures
```

修复内容：

- `src/code_verifier/rewards/common.py` 在生成 reward components 时读取已由 verifier 提供的 `failure_counts`，识别 top-level status 被早先普通模型失败遮蔽的 nested terminal failure。
- 若 `failure_counts` 含 `sandbox_error`，Reward 将该结果按 infrastructure failure 处理：`test_reward=0.0`、`executable_reward=0.0`，且不自造额外 penalty，因此总 reward 为 `0.0`。
- 若 `failure_counts` 含 `timeout` 且不存在 infrastructure failure，则按 timeout 处理并应用 `-0.2` penalty；普通可执行分量仍按既有规则为 `0.1`。
- component record 的 `infrastructure_failure` 反映 Reward 层最终采用的 infrastructure 语义，`failure_counts` 保持 payload-free。
- 新增 unit 回归覆盖 `WRONG_ANSWER → PASSED → SANDBOX_ERROR` 与 `WRONG_ANSWER → TIMEOUT`。
- 新增使用项目真实 `PistonExecutor` + 测试 transport 的 integration 回归，验证默认 `stop_on_first_failure=False` 下上述两条多失败聚合路径。

## 3. R2 修复验证

### 受影响专项测试

```text
../../.venv/bin/python -m pytest \
  tests/unit/rewards/test_common.py \
  tests/integration/test_wp4b_reward_pipeline.py
→ 41 passed
```

### 静态检查

```text
make VENV=../../.venv lint
→ Ruff check: All checks passed
→ Ruff format: 63 files already formatted
→ strict Mypy: Success, no issues found in 63 source files
```

### 默认全量 CPU 回归

```text
make test VENV=../../.venv
→ 536 passed, 3 skipped
```

三个 skip 均为既有真实 Piston tests；本轮未新增 skip 或 xfail。

### WP4 联合定向验收

```text
../../.venv/bin/python -m pytest \
  tests/unit/verification \
  tests/unit/rewards \
  tests/integration/test_wp4a_verifier_pipeline.py \
  tests/integration/test_wp4b_reward_pipeline.py
→ 92 passed, 0 failed, 0 skipped
```

### CLI 边界

```text
../../.venv/bin/python -m code_verifier.cli --help
→ exit 0
→ commands: record-environment, prepare-data, check-data, parse-code, execute-batch
```

未新增 verifier、reward、training 或 evaluation CLI 子命令。

## 4. 修复完成状态

- WP4-b R2 M3 已修复，并覆盖 reviewer 指定的 `wrong→sandbox` 与 `wrong→timeout` 两条真实 Piston 聚合路径。
- nested sandbox 不再获得 test/executable 正分；nested timeout 会应用既定 `-0.2` penalty。
- R1 M1/M2 修复保持有效，无回归。
- `make lint`、`make test`、WP4 联合定向测试和 CLI 均实际运行通过。
- 无未处理问题、异议项或无法复现项。
- 未修改审查报告、`proceedings.md` 或 `third_party/open-r1/**`。
- 未执行 push 或 merge。
- 下一步由 `wp-plan-reviewer` 对 WP4-b 执行下一轮独立复审；只有复审通过后才可合并并登记 WP4 整体完成。

---

# 代码修复报告（WP4-b R2）

## 1. 修复依据与范围

- 审查报告：`ai-work/reviewer/WP4-review.md`
- 审查轮次：WP4-b R2
- 审查结论：需修改
- 修复范围：主要问题 M3
- 未处理项：无
- 异议项：无
- 修复分支 / worktree：`feat/wp4-b` / `.worktrees/wp4-b`

R2 指出：`PistonExecutor(stop_on_first_failure=false)` 的 top-level status 取首个非 PASSED，因此真实多失败序列中的后续 `SANDBOX_ERROR` 或 `TIMEOUT` 可能只存在于 `VerificationResult.failure_counts`，Reward 若只看 top-level status 会错误计分。

本轮遵守 `WP4-b-plan.md` §4.3 的阶段边界，没有修改 `src/code_verifier/execution/**` 或 `src/code_verifier/verification/**`；按 reviewer 给出的“Verification/Reward 边界”修复方向，仅在 Reward Layer 解释现有 `failure_counts` 终止状态证据，并补真实 `PistonExecutor + fake transport` 的 Reward 集成回归。

## 2. M3：识别 nested sandbox / timeout 终止状态

修复提交：

```text
6c8f94b  fix: honor nested terminal reward failures
```

修复内容：

- `_reward_components_from_verification()` 先把已验证的 `result.failure_counts` 转成局部 mapping。
- effective infrastructure failure 现在满足任一条件即为真：
  - `result.infrastructure_failure is True`；
  - `failure_counts` 中包含 `sandbox_error`。
- effective timeout 现在满足任一条件即为真：
  - top-level `result.status is TIMEOUT`；
  - `failure_counts` 中包含 `timeout`。
- 发现 nested sandbox 时：
  - `test_reward=0.0`；
  - `executable_reward=0.0`；
  - 不自造 infrastructure penalty；
  - component record 的 `infrastructure_failure=True`，同时保留原 top-level `status` 和完整 `failure_counts` 供下游诊断。
- 发现 nested timeout 且不存在 infrastructure failure 时，应用既有 `-0.2` timeout penalty；其它公式分量保持规格定义。
- 若同一合法结果同时含 infrastructure failure 与 timeout 证据，infrastructure failure 的“总 reward 不自造负 penalty”规则优先，不叠加 timeout penalty。

## 3. 新增回归

### Reward unit

新增两条结构化回归：

- `WRONG_ANSWER → PASSED → SANDBOX_ERROR`：top-level 仍为 `wrong_answer`，但 Reward 识别 nested sandbox，最终 reward `0.0`，component `infrastructure_failure=True`。
- `WRONG_ANSWER → TIMEOUT`：top-level 仍为 `wrong_answer`，Reward 从 `failure_counts` 识别 timeout，应用 `-0.2` penalty，最终 reward `-0.1`。

### 真实 Piston 聚合路径集成

`tests/integration/test_wp4b_reward_pipeline.py` 新增 CPU-only fake transport，通过项目自身 `PistonExecutor` 的真实聚合逻辑进入 `verify_completion() → compute_code_rewards()`：

- `wrong_answer → passed → Piston XX/sandbox`：实际保留 top-level `wrong_answer` 与 `pass_rate=1/3`，Reward 最终清零为 `0.0`。
- `wrong_answer → Piston TO/timeout`：实际保留 top-level `wrong_answer`，Reward 最终应用 timeout penalty，得到 `-0.1`。

这些测试不依赖外部 Piston 服务，也没有修改 WP3 execution 实现或其测试预期。

## 4. R2 修复验证

### 受影响专项测试

```text
../../.venv/bin/python -m pytest \
  tests/unit/rewards/test_common.py \
  tests/integration/test_wp4b_reward_pipeline.py
→ 41 passed
```

### 静态检查

首次 `make VENV=../../.venv lint` 仅发现新增 integration import 的 Ruff I001/E501 格式问题；按 Ruff 建议调整 import 后重新运行：

```text
make VENV=../../.venv lint
→ Ruff check: All checks passed
→ Ruff format: 63 files already formatted
→ strict Mypy: Success, no issues found in 63 source files
```

### 默认全量 CPU 回归

```text
make test VENV=../../.venv
→ 536 passed, 3 skipped
```

三个 skip 均为既有真实 Piston tests；本轮未新增 skip 或 xfail。

### WP4 联合定向验收

```text
../../.venv/bin/python -m pytest \
  tests/unit/verification \
  tests/unit/rewards \
  tests/integration/test_wp4a_verifier_pipeline.py \
  tests/integration/test_wp4b_reward_pipeline.py
→ 92 passed, 0 failed, 0 skipped
```

### CLI 边界

```text
../../.venv/bin/python -m code_verifier.cli --help
→ exit 0
→ commands: record-environment, prepare-data, check-data, parse-code, execute-batch
```

未新增 verifier、reward、training 或 evaluation CLI 子命令。

## 5. 修复完成状态

- WP4-b R2 M3 已修复，并有 Reward unit 与真实 Piston 聚合集成回归。
- nested sandbox 不再因较早普通失败的 top-level status 而获得测试通过率或 executable 正分。
- nested timeout 不再因较早普通失败的 top-level status 而漏掉 timeout penalty。
- R1 的 M1/M2 行为继续由全量与联合定向测试覆盖，无回归。
- 未修改 execution/verification/parser/data/training、配置、依赖、审查报告、`proceedings.md` 或 `third_party/open-r1/**`。
- 未执行 push 或 merge。
- 下一步由 `wp-plan-reviewer` 对 WP4-b 执行 R3 独立复审；只有复审通过后才可合并并登记 WP4 整体完成。
