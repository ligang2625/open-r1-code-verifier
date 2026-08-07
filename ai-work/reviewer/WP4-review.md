# WP4-b 独立审查报告

- **审查计划**：`ai-work/planner/WP4-b-plan.md`
- **目标阶段**：WP4：Verifier 与 Reward（子阶段 b：Reward Layer、测试层隔离与 WP4 整体收口）
- **阶段分支**：`feat/wp4-b`
- **阶段 worktree**：`.worktrees/wp4-b`
- **本轮**：R1（首轮审查）
- **审查日期**：2026-08-07

> 阶段切换说明：原 `ai-work/reviewer/WP4-review.md` 记录的是 `WP4-a-plan.md`。当前计划已切换为 `WP4-b-plan.md`，按 `wp-plan-reviewer` 的阶段重置规则，本文件从 WP4-b R1 重新记录；WP4-a 历史仍保留在 Git 历史与 `proceedings.md` 中。

## R1：首轮独立审查

### 1. 审查范围与方法

- 计划文件：`ai-work/planner/WP4-b-plan.md`。
- executor 报告：`ai-work/executor/WP4-executor.md` 中 `# WP4-b Executor 执行报告` 部分。
- 规格依据：`PROJECT_SPEC_Open-R1_CodeVerifier.md` §6.2 Reward Layer、§10.1–§10.6、§12.3、§19、§20、§21，以及 plan §3.5–§3.6 的硬性规则和明确实现决策。
- 审查方式：逐条核对 6 个实施步骤、阅读 Reward 源码与单元/集成测试、核查分支范围、独立运行 lint/全量测试/WP4 定向测试/CLI，并增加两个一次性边界探针验证 infrastructure failure 与 executor 配置错误。
- 审查纪律：未修改 `src/`、`tests/` 或 `third_party/open-r1/`；本轮只重置并写入当前阶段审查报告。

### 2. 计划完成度核验（逐条对照 plan）

| 计划步骤 / 交付项 | 计划要求 | 状态 | 证据 |
|---|---|---|---|
| 步骤 1：Reward 输入合同、completion 提取与 batch 对齐 | `RewardContractError`、四列严格对齐、raw/chat completion、全批 completion 预解析、executor guard | 部分完成 | `src/code_verifier/rewards/common.py:19-77` 与 `tests/unit/rewards/test_common.py:99-203` 已覆盖 batch/completion/guard；但 `_require_executor()` 未应用于公开 `compute_code_rewards()`，导致直接 core 调用可把无效 executor 静默转成 sandbox reward，见 M2。 |
| 步骤 2：统一 reward 公式、component record 与 `compute_code_rewards()` | 唯一 §10 公式、有限值、严格 record、失败关闭 | 部分完成 | `common.py:80-237` 已实现统一公式和 record；但 `test_reward = pass_rate` 对 `infrastructure_failure=True` 无归零，合法的部分通过 + `SANDBOX_ERROR` 可得到正 reward，违反 plan §3.6 决策 13，见 M1。 |
| 步骤 3：Public wrapper | 只使用 visible tests；拒绝 train-hidden/eval-hidden；绑定 executor；返回 `list[float]` | 已完成 | `src/code_verifier/rewards/public_reward.py:8-29`；`tests/unit/rewards/test_public_reward.py:47-144`。hidden/eval-hidden guard 均在 common/verifier 前执行。 |
| 步骤 4：Hidden wrapper | 只使用 train-hidden；忽略 visible；拒绝 eval-hidden；与 Public 共用 core | 已完成 | `src/code_verifier/rewards/hidden_reward.py:8-27`；`tests/unit/rewards/test_hidden_reward.py:47-177`。Mock call 明确只收到 train-hidden tests。 |
| 步骤 5：公共 API 与 Mock 集成 | 稳定导出；chat/raw completion；Public/Hidden source isolation；失败状态；record 对齐/脱敏 | 部分完成 | `src/code_verifier/rewards/__init__.py:1-15` 与 `tests/integration/test_wp4b_reward_pipeline.py:102-315` 已覆盖主要路径；sandbox 测试只覆盖 `passed_tests=0`，未覆盖真实可出现的“先通过、后 sandbox”状态，因此漏掉 M1。 |
| 步骤 6：文档与 WP4 整体验收 | README/AGENTS、全量/定向测试、CLI、范围核查、无配置变化 | 部分完成 | README/AGENTS 与命令验收均存在且全绿；但 WP4 reward 语义仍有 M1/M2，不能完成 WP4 整体收口。 |
| 新增文件清单 | 4 个 Reward 业务模块、Reward tests、WP4-b integration | 已完成 | `git log --oneline --name-status main..HEAD` 仅显示计划内 Reward 源码/测试与 plan。 |
| 修改文件清单 | `README.md`、`AGENTS.md`、executor 报告 | 已完成 | 分支提交记录与 plan 一致。 |
| 明确不修改项 | verification/execution/parser/data/training/config/Makefile/pyproject/third-party/proceedings | 已完成 | `main..HEAD` 无这些生产路径净改动；CLI 命令集合未扩展；executor 未修改 `proceedings.md`。 |

### 3. WP4 交付与验收核验

| 验收项 | 状态 | 证据 |
|---|---|---|
| WP4-a verifier 无回归 | 通过 | WP4 定向 suite 中 Verification tests 全绿；全量回归通过。 |
| reward common 已实现 | 部分通过 | API/公式/record 已实现，但 infrastructure failure 与 invalid executor 两个合同缺陷仍存在。 |
| Public 只使用 visible tests | 通过 | `public_reward.py:16-27`；Public unit/integration Mock calls。 |
| Hidden 只使用 train-hidden tests | 通过 | `hidden_reward.py:16-25`；Hidden unit/integration Mock calls。 |
| eval-hidden 无法通过已知 wrapper 字段进入计分 | 通过 | Public/Hidden 都对 `eval_hidden_tests` fail-before-execution；Public 额外拒绝 `train_hidden_tests`。 |
| Public/Hidden 共用同一公式与辅助项 | 通过 | 两个 wrapper 只调用 `compute_code_rewards()`；公式常量仅存在于 `common.py:115-119`。 |
| §10.5 参数名、顺序与返回形态 | 通过 | `public_code_reward(completions, visible_tests, function_name, metadata, **kwargs)`、`hidden_code_reward(...)` 与 `compute_code_rewards(completions, tests_batch, function_names, metadata_batch, executor, mode)` 均保持计划顺序；wrapper 返回 `list[float]`。 |
| batch 不一致在执行前失败 | 通过 | `common.py:52-69`；`test_common.py:115-130,412-423`；未使用 zip 做核心对齐。 |
| reward/component 数量与 completion 严格对齐 | 通过 | 索引循环 `common.py:216-237`；unit/integration 对齐断言通过。 |
| reward/component 数值有限 | 通过 | `_validate_component_record()` 与 append 前双重 finite 检查；定向与全量测试通过。 |
| parser failure / timeout 公式 | 通过 | parse = -0.1；timeout 保留 pass-rate +0.1 -0.2；对应 unit/integration 断言通过。 |
| sandbox/infrastructure failure 不获得正确答案正分 | **未通过** | 合法 `SANDBOX_ERROR` 若前序已有 passed tests，当前 `test_reward` 仍取正 `pass_rate`，独立实证得到 total `0.5`，见 M1。 |
| 输入/配置合同错误抛 `RewardContractError` | **未完全通过** | wrapper 的 executor guard 正确；但直接公共 core 接受无效 executor 时返回 sandbox `0.0` 而不是 `RewardContractError`，见 M2。 |
| component records JSON-safe / payload-free | 通过 | exact fields，无 completion/code/tests/metadata/stdout/stderr/execution_result；集成 sentinel 测试通过。 |
| `make lint` | 通过 | 独立重跑：Ruff check passed；63 files formatted；strict mypy success。 |
| `make test` | 通过 | 独立重跑：`530 passed, 3 skipped`；3 个 skip 均为既有真实 Piston tests。 |
| WP4 定向 suite | 通过 | 独立重跑：`86 passed, 0 failed, 0 skipped`。 |
| CLI 边界 | 通过 | `python -m code_verifier.cli --help` exit 0，仅有既有 5 个命令。 |
| 无配置、依赖、上游及后续 WP 越界变更 | 通过 | 分支提交范围符合 plan；未新增 GRPO/training/evaluation 功能。 |

### 4. Executor 报告声明核验

| Executor 声明 | 核验状态 | 证据 |
|---|---|---|
| 6 个步骤全部实现 | 部分核实 | 交付文件齐全，但步骤 1/2/5/6 存在 M1/M2，不能认定计划语义全部完成。 |
| Reward 统一公式正确 | 与事实部分不符 | 常规 passed/partial/timeout/parse/sandbox(0 pass) 正确；部分通过后 infrastructure failure 会得到正 test reward，见 M1。 |
| executor infrastructure failure 不获得测试/可执行正分 | 与事实不符 | executor 报告 §5 声称符合；独立合法结构探针得到 reward `0.5`。 |
| batch 对齐、completion payload、测试源隔离 | 核实通过 | 代码与独立测试证据一致。 |
| component records JSON-safe 且 payload-free | 核实通过 | unit/integration sentinel 与 JSON strict serialization 通过。 |
| `make lint` 全绿 | 核实通过 | 独立重跑一致。 |
| `make test` 530 passed / 3 skipped | 核实通过 | 独立重跑一致。 |
| WP4 联合定向 86 passed | 核实通过 | 独立重跑一致。 |
| CLI 未扩展 | 核实通过 | 独立 help 命令一致。 |
| 无越界改动 | 核实通过 | `main..HEAD` 文件范围符合 plan。 |

### 5. 问题清单

| 严重级别 | 位置 | 问题 | 依据 | 建议 |
|---|---|---|---|---|
| **主要（M1）** | `src/code_verifier/rewards/common.py:115-119`；测试缺口 `tests/unit/rewards/test_common.py:286-306`、`tests/integration/test_wp4b_reward_pipeline.py:176-210` | `SANDBOX_ERROR` / `infrastructure_failure=True` 时仍无条件使用 `result.pass_rate` 作为 `test_reward`。Piston 是逐测试执行，允许前序测试 passed 后下一测试发生 transport/harness sandbox error，因此合法 verification 可同时有 `status=SANDBOX_ERROR`、`passed_tests>0`、`pass_rate>0`。当前实现会给这种基础设施失败正 reward。 | plan §3.6 决策 13 明确规定 sandbox/infrastructure failure 的 test/executable 正分均为 0、总 reward 0；spec §10.1/§10.6 要求 reward 异常不得静默高分、executor infrastructure error 不得当成正确答案。`PistonExecutor.execute()` 在 `piston.py:461-488` 可先累积 passed test 再遇 sandbox 并保留 pass_rate。独立合法探针：`SANDBOX_ERROR, passed_tests=1,total_tests=2,pass_rate=0.5` → 当前 reward `[0.5]`。 | 在 `_reward_components_from_verification()` 中对 `result.infrastructure_failure` 明确将 `test_reward` 归零（并保持 executable=0、无自造 penalty），确保 total=0.0；新增 unit + integration 回归，至少覆盖 passed→sandbox early-stop。 |
| **主要（M2）** | `src/code_verifier/rewards/common.py:72-77,195-237` | `_require_executor()` 已实现但 `compute_code_rewards()` 不调用它。由于 WP4-a verifier 会把普通 `AttributeError` fail-closed 为 `SANDBOX_ERROR`，直接调用公开 core 并传 `executor=object()` 时会静默返回 reward `0.0`，把配置错误伪装成模型/基础设施失败。 | plan §3.5 明确“输入/配置合同错误应抛脱敏 `RewardContractError`，不得转换成默认 reward”；`compute_code_rewards` 被 `code_verifier.rewards` 公共导出，plan §3.6/§8 还要求 WP7 component logging 直接消费/包装 common core。独立探针：`compute_code_rewards(..., object(), "public")` 返回 `([0.0], sandbox_error record)`，未抛异常。 | 在 common core 开始计分前调用 `_require_executor(executor)` 并使用验证后的 executor；增加 direct-core 无效 executor 回归（含空/非空 batch 的预期语义），保证配置错误不能变成 sandbox reward。 |

### 6. 独立测试与边界探针

- `make VENV=../../.venv lint` → Ruff check passed；63 files already formatted；strict mypy success。
- `make VENV=../../.venv test` → `530 passed, 3 skipped in 5.78s`。
- `../../.venv/bin/python -m pytest tests/unit/verification tests/unit/rewards tests/integration/test_wp4a_verifier_pipeline.py tests/integration/test_wp4b_reward_pipeline.py` → `86 passed in 0.14s`。
- `../../.venv/bin/python -m code_verifier.cli --help` → exit 0；命令集合未扩展。
- M1 探针：构造合同合法的 `ExecutionResult(status=SANDBOX_ERROR, passed_tests=1, total_tests=2, pass_rate=0.5, test_results=[PASSED, SANDBOX_ERROR])`，经 `MockExecutor → verify_completion → compute_code_rewards` 得到 `test_reward=0.5,total_reward=0.5,infrastructure_failure=True`，确认缺陷可复现。
- M2 探针：直接 `compute_code_rewards(..., executor=object(), mode="public")`，当前返回 `SANDBOX_ERROR` component record 与 `[0.0]`，未抛 `RewardContractError`。
- 范围核查：`git log --oneline --name-status main..HEAD` 仅含 `WP4-b-plan.md`、Reward 源码/测试、README、AGENTS、executor 报告；无 verification/execution/parser/data/training/config/Makefile/pyproject/third-party/proceedings 净改动。

### 7. 结论

- **结论：需修改**。
- 理由：静态检查、全量测试、WP4 定向测试、CLI 和测试层隔离均通过，但 M1 会让真实可发生的 infrastructure failure 获得正 reward，直接违反 WP4 reward 验收；M2 会把公开 common-core 的 executor 配置错误静默伪装成 sandbox `0.0`，违反配置错误 fail-closed 合同。两项均为主要问题。
- 本轮禁止合并 `feat/wp4-b`，不更新 `proceedings.md`，不将 WP4 整体标记完成，不清理 worktree/分支，不 push。
- 后续复审必须逐条核验 M1、M2，并完整重跑 lint、全量测试、WP4 联合定向测试、CLI 以及上述两个边界探针。

## R2：修复后复审

### 1. 复审范围与方法

- 复审基准：R1 主要问题 M1、M2，以及 WP4 最终验收中的 infrastructure failure / timeout 失败状态语义。
- 修复声明来源：`ai-work/executor/WP4-executor.md` 的“代码修复报告（WP4-b R1）”；修复提交 `8125115 fix: enforce reward failure contracts`，报告提交 `07b8a1b docs: record wp4 reward fixes`。
- 独立方法：阅读修复代码与新增测试，重跑 lint、全量测试、WP4 Verification + Reward 联合定向测试与 CLI；重新执行 R1 两个边界探针，并使用项目自己的 `PistonExecutor` 测试 transport 验证多失败状态聚合。
- 审查纪律：未修改 `src/`、`tests/` 或 `third_party/open-r1/`；本轮只追加审查报告。

### 2. 上轮问题核验

| 上轮问题 | 严重级别 | R2 状态 | 证据 |
|---|---|---|---|
| M1：top-level `SANDBOX_ERROR` 在已有 passed tests 时仍得到正 test reward | 主要 | **已修复** | `src/code_verifier/rewards/common.py:115-119` 现对 `result.infrastructure_failure` 将 `test_reward` 固定为 `0.0`；`tests/unit/rewards/test_common.py:286-309` 与 `tests/integration/test_wp4b_reward_pipeline.py:176-210` 已改为 passed→sandbox 场景。独立复现原 M1 得到 reward `[0.0]`。 |
| M2：公开 `compute_code_rewards()` 未校验 executor | 主要 | **已修复** | `common.py:203-210` 在空 batch 早返回前调用 `_require_executor()` 并使用 validated executor；新增 direct-core 空/非空 batch 回归。独立传 `executor=object()` 现抛 `RewardContractError("executor must provide a callable execute method")`。 |

### 3. 回归与计划完成度复核

| 项目 | R2 状态 | 证据 |
|---|---|---|
| R1 步骤 1 executor guard 缺口 | 已完成 | public common core 自身现在 fail-fast，wrapper 与 direct-core 语义一致。 |
| R1 步骤 2 top-level infrastructure failure reward | 已完成 | `infrastructure_failure=True` 时 test/executable reward 均为 0，无新增 penalty。 |
| R1 步骤 5 sandbox 回归测试缺口 | 已完成 | unit + integration 均覆盖 `PASSED → SANDBOX_ERROR`。 |
| 修复范围 | 通过 | `54212d6..HEAD` 仅修改 `common.py`、两项 Reward 测试及 executor 修复报告，无越界生产代码。 |
| 静态检查 / 全量 / WP4 定向 / CLI | 通过 | 独立命令全部通过，见第 5 节。 |
| WP4 最终失败状态语义 | **未通过** | 新发现 M3：真实 Piston 多失败序列可让后续 sandbox/timeout 被早先普通失败的 top-level status 掩盖，Reward 仍把该结果当普通模型失败计分。 |

### 4. 新问题

| 严重级别 | 位置 | 问题 | 依据 | 建议 |
|---|---|---|---|---|
| **主要（M3）** | `src/code_verifier/execution/piston.py:461-488`；`src/code_verifier/verification/verifier.py:183-205`；`src/code_verifier/rewards/common.py:115-119` | Piston 在 `stop_on_first_failure=false` 时会继续执行普通 `WRONG_ANSWER/RUNTIME_ERROR`，但最终 top-level status 固定取“第一个非 PASSED”；后续 `SANDBOX_ERROR` 或 `TIMEOUT` 虽记录在 `test_results` / `failure_counts`，却不会成为 top-level status。Verification 的 `infrastructure_failure` 只看 top-level `SANDBOX_ERROR`，Reward 的 infrastructure/timeout 逻辑又只看 `infrastructure_failure` / top-level `TIMEOUT`。因此真实可达的 `WRONG_ANSWER → PASSED → SANDBOX_ERROR` 被计为普通可执行结果，得到 `0.433333...` 正 reward；`WRONG_ANSWER → TIMEOUT` 得到 `0.1`，漏掉 `-0.2` timeout penalty。 | spec §8.4 要求“记录沙箱错误，不将其误判为模型错误”；§10.1 要求奖励异常不能静默变成高分；§10.6 要求 executor infrastructure error 不当成正确答案、timeout 有惩罚。默认 `configs/execution/piston-local.yaml` 为 `stop_on_first_failure: false`。独立使用项目 `PistonExecutor` 的测试 transport 实证得到：`status=wrong_answer, failure_counts={'sandbox_error':1,'wrong_answer':1}` → reward `0.433333...`；`failure_counts={'timeout':1,'wrong_answer':1}` → reward `0.1`。 | 在不破坏 WP4-a 公共签名的前提下统一“终止/基础设施状态”语义。优先修复 Verification/Reward 边界，使 nested `sandbox_error` 必须按 infrastructure failure 处理并清零正分，nested timeout 必须应用 timeout penalty；或调整 ExecutionResult 聚合规则，使资源/基础设施终止状态具有高于普通模型失败的 top-level 优先级。无论选哪一层，需补真实 Piston 聚合回归与 Reward 集成回归，覆盖 `wrong→sandbox`、`wrong→timeout`。 |

### 5. 独立测试与边界探针

- `make VENV=../../.venv lint` → Ruff check passed；63 files already formatted；strict mypy success。
- `make VENV=../../.venv test` → `532 passed, 3 skipped`；3 个 skip 仍为既有真实 Piston tests。
- `../../.venv/bin/python -m pytest tests/unit/verification tests/unit/rewards tests/integration/test_wp4a_verifier_pipeline.py tests/integration/test_wp4b_reward_pipeline.py` → `88 passed, 0 failed, 0 skipped`。
- `../../.venv/bin/python -m code_verifier.cli --help` → exit 0；仍仅有既有 5 个命令。
- 原 M1 探针：`SANDBOX_ERROR + passed_tests=1/2` → reward `[0.0]`，确认修复。
- 原 M2 探针：direct-core `executor=object()` → 脱敏 `RewardContractError`，确认修复。
- M3 Piston 实证：用项目 `PistonExecutor` + 测试 transport 产生 `wrong_answer → passed → sandbox_error`，执行结果 top-level 为 `wrong_answer`、`pass_rate=1/3`；经完整 Reward 路径得到 `test_reward=1/3`、`executable_reward=0.1`、total `0.433333...`，同时 component `failure_counts` 已明确含 `sandbox_error: 1`。
- M3 timeout 实证：`wrong_answer → timeout` 聚合为 top-level `wrong_answer`；Reward 返回 `0.1`，`timeout_penalty=0.0`，而 `failure_counts` 含 `timeout: 1`。

### 6. Executor 修复报告声明核验

- “M1 已修复”：**核实通过**。
- “M2 已修复”：**核实通过**。
- “受影响专项测试 37 passed”：本轮未单独依赖该声明；完整 WP4 定向套件独立得到 88 passed。
- “`make lint` 全绿”：**核实通过**。
- “`make test` 532 passed / 3 skipped”：**核实通过**。
- “WP4 联合定向 88 passed”：**核实通过**。
- “WP4-b 已满足最终失败合同”：**无法认定**；M3 表明现有测试未覆盖 Piston 多失败聚合后 nested sandbox/timeout 的 Reward 解释。

### 7. R2 结论

- **结论：需修改**。
- R1 的 M1、M2 已完整修复，修复未引入 lint/test 回归或越界改动。
- 但新增主要问题 M3 直接影响 WP4 §10 reward 失败状态和 §20 整体验收：真实 Piston 路径可把 infrastructure/timeout 终止状态掩盖为早先普通失败，从而产生不应有的正 reward 或漏掉 timeout penalty。存在主要问题时不得判定通过。
- 本轮不合并 `feat/wp4-b`，不更新/整合 `proceedings.md`，不将 WP4 标记完成，不清理阶段 worktree/分支，不 push。
- 下一轮复审需重点验证 M3 的 `wrong→sandbox` 与 `wrong→timeout` 两条真实 Piston 聚合路径，并再次完整运行 lint、全量测试、WP4 定向测试和 CLI。

## R3：M3 修复后复审

### 1. 复审范围与修复基线

- 复审基准：R2 新增主要问题 M3，以及 R1 已关闭的 M1/M2 回归。
- 修复声明：`ai-work/executor/WP4-executor.md` 的“代码修复报告（WP4-b R2）”；实现提交 `6c8f94b fix: honor nested terminal reward failures`，修复报告提交 `7a2f293`、`89d4892`。
- 修复范围核查：`85d8d51..HEAD` 仅修改 `src/code_verifier/rewards/common.py`、Reward unit/integration tests 与 executor 报告；未修改 execution、verification、parser、data、training、配置、依赖、CLI、`third_party/open-r1/**` 或 `proceedings.md`。

### 2. 上轮问题核验

| 上轮问题 | 严重级别 | R3 状态 | 证据 |
|---|---|---|---|
| M3：较早普通失败掩盖后续 nested sandbox/timeout，导致 infrastructure 正 reward 或漏 timeout penalty | 主要 | **已修复** | `src/code_verifier/rewards/common.py:115-138` 从已验证 `failure_counts` 计算 effective infrastructure/timeout：nested `sandbox_error` 会清零 test/executable 正分并令 component `infrastructure_failure=True`；nested `timeout` 会应用 `-0.2` penalty。unit 回归见 `tests/unit/rewards/test_common.py:312-348`；CPU-only 真实 `PistonExecutor + fake transport` 集成回归覆盖同两条路径。独立 Piston 探针得到 sandbox total `0.0`、timeout total `-0.1`。 |
| R1 M1：top-level sandbox 已部分通过时仍有正 test reward | 主要 | **保持修复** | 独立原 M1 探针仍得到 reward `[0.0]`。 |
| R1 M2：公开 core 无效 executor 被吞成 sandbox reward | 主要 | **保持修复** | direct-core `executor=object()` 仍在执行前抛脱敏 `RewardContractError`。 |

### 3. WP4 最终验收复核

- WP4-a Verification 全部回归通过，无语义回退。
- Reward common、Public/Hidden wrappers、§10.5 参数顺序与返回形态均保持稳定。
- Public 仅使用 `visible_tests`；Hidden 仅使用 `train_hidden_tests`；eval-hidden guard 与 source isolation 回归继续通过。
- batch mismatch 在执行前失败；reward/component record 与 completion 数量严格对齐；所有 reward/component 数值有限。
- parser failure、top-level/nested timeout、top-level/nested sandbox/infrastructure failure 均符合最终 reward 语义；infrastructure failure 不获得正 reward，timeout penalty 不再被早先普通失败掩盖。
- component records 继续 JSON-safe、payload-free，不含 completion/code/tests/metadata/stdout/stderr/`execution_result`。
- 未发现新的阻断、主要或次要问题；未发现测试预期迁就实现或阶段越界改动。

### 4. 独立测试与边界探针

- `make VENV=../../.venv lint` → Ruff check passed；63 files already formatted；strict mypy success。
- `make VENV=../../.venv test` → `536 passed, 3 skipped`；3 个 skip 均为既有真实 Piston tests，无新增 skip/xfail。
- `../../.venv/bin/python -m pytest tests/unit/verification tests/unit/rewards tests/integration/test_wp4a_verifier_pipeline.py tests/integration/test_wp4b_reward_pipeline.py` → `92 passed, 0 failed, 0 skipped`。
- `../../.venv/bin/python -m code_verifier.cli --help` → exit 0；命令集合仍为 `record-environment`、`prepare-data`、`check-data`、`parse-code`、`execute-batch`。
- M3 sandbox 实证：项目自身 `PistonExecutor(stop_on_first_failure=false)` 产生 `wrong_answer → passed → sandbox_error`，top-level 仍为 `wrong_answer`；Reward 现返回 total `0.0`、`infrastructure_failure=True`。
- M3 timeout 实证：`wrong_answer → timeout` top-level 仍为 `wrong_answer`；Reward 现返回 total `-0.1`，其中 `executable_reward=0.1`、`timeout_penalty=-0.2`。
- M1/M2 原探针再次通过，无回归。

### 5. Executor 修复报告声明核验

- M3 已修复：**核实通过**。
- 真实 Piston 聚合回归已加入：**核实通过**。
- `make lint`、`make test`、WP4 联合定向测试与 CLI 声明：**独立重跑均核实通过**。
- 无 execution/verification 等越界修改：**核实通过**。

### 6. R3 结论

- **结论：通过**。
- R1 M1/M2 与 R2 M3 均已完整处置；无新增阻断或主要问题，WP4-b 计划最终验收项全部满足。
- 按 `wp-plan-reviewer` 流程，本轮审查提交后可合并 `feat/wp4-b` 回 main，并因 WP4-a/WP4-b 均已完成，将 proceedings 中 WP4 子阶段记录整合为一条 WP4 整体完成记录。
- 最终合并提交：`588e78e`（`feat: complete WP4 verifier and rewards`）。
- 合并后 main 再次通过 `make lint`、`make test`（`536 passed, 3 skipped`）以及 WP4 联合定向测试（`92 passed, 0 failed, 0 skipped`）。
- WP4-a/WP4-b 均已完成，proceedings 按最终子阶段规则整合为一条 WP4 整体完成记录。
