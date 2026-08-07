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
