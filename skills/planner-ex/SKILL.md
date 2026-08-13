---
name: planner-ex
description: Web/CodexPro 规划入口。根据 Open-R1 规格、proceedings 与代码现状生成下一 stage 的函数级最终 plan 和 execution_routing；不做 Git mutation、不选择 execution backend。计划通过 handoff 交给 Web/Local 共用 stage-lifecycle bootstrap_plan 封存，再由 execution-router 在运行时选择 local/web backend。
---

# Planner Ex

## 目标与边界

本 skill 负责生成一个**完整、可执行、可验证、可路由**的 stage plan。它是 Web-side planning artifact producer，不负责 Git 生命周期：

- 不创建/删除 branch 或 worktree；
- 不 commit/merge/push；
- 不启动 executor；
- 不在 `main` 写最终 plan 文件；
- 最终 plan 交给共用 `stage-lifecycle bootstrap_plan` 写入并 commit；该 lifecycle 可由 Web GPT + CodexPro 或 Local Codex 执行。

planner-ex 必须以**主仓库 root checkout** 为工作区。它可以读取 `git worktree list` / branch / log 等只读状态，但不得进入已有 stage worktree 继续规划，也不得创建、删除、移动或修改任何 worktree/branch。

如果 CodexPro handoff 可用，优先把完整最终 plan 发布到 `.ai-bridge/current-plan.md`（例如 handoff_to_codex）；handoff 只是传输层，不是仓库 stage artifact。handoff 工具可以在 plan 外增加 `Updated/Workspace/Target agent/## Plan` 等 transport wrapper；真正 payload 始终是完整 plan 正文。若 handoff 不可用，返回完整 plan 正文与 stage descriptor，供调用方传给 `stage-lifecycle`。

若规划开始时主仓库已经存在非空 `.ai-bridge/current-plan.md`，说明上一份 plan 仍待 bootstrap。默认返回 `PLANNER_PENDING_HANDOFF_EXISTS`，不要覆盖；只有用户明确要求替换这份 pending handoff 时才允许继续规划并覆盖它。

## 输入

1. `PROJECT_SPEC_Open-R1_CodeVerifier.md`：至少精读目标 WP 相关章节、§20 WP 注册表、§21 Code Review、§19 测试、§29 默认决策。
2. `proceedings.md`：确认已完成、部分完成、受阻阶段。
3. 当前 `src/`、`tests/` 与只读 Git/worktree 状态。
4. `references/plan-template.md`。

## Active-stage guard

规划下一 stage 前先记录 `planning_base_commit = main HEAD`，并快照当前 `git worktree list` 与相关 stage branches。然后枚举尚未合并的 stage worktree/branch。`archive/*` 这类无 linked worktree、仅用于保存已明确废弃/被新规格取代的历史 commit 的分支不是 active stage，不得因此阻塞规划；其它带 sealed stage plan 的未合并 worktree/branch 仍按 active stage 处理。

- 0 个 active stage：允许规划下一 stage；
- 1 个或多个 active stage：默认返回 `PLANNER_ACTIVE_STAGE_EXISTS`，不得规划后续 stage；
- 只有用户明确要求“重规划当前 stage”才允许进入 replan；replan 仅允许该 stage 仍处于纯 PLANNED 状态：没有 completed implementation record，且 stage `HEAD` 仍等于当前 plan seal commit。只要 plan seal 后已有任何其它 commit，就返回 `PLANNER_REPLAN_AFTER_EXECUTION`，不得覆盖原 plan，后续变化交给 execution/review 流程处理。

禁止按“最近创建”“最大 WP 编号”猜当前 stage。

## Stage identity

每个计划必须定义唯一 `stage_id`：

- 未拆分 WP：`WP5`
- 拆分：`WP5-a`、`WP5-b`

规划开始时记录只读 Git 基线 `planning_base_commit = main HEAD`。并给出 proposed lifecycle metadata：

- `planning_base_commit`：`<main HEAD sha>`
- branch：`feat/wp5` 或 `feat/wp5-b`
- worktree：`.worktrees/wp5` 或 `.worktrees/wp5-b`
- final plan path：`ai-work/planner/{stage_id}-plan.md`
- execution report path：`ai-work/executor/{stage_id}-executor.md`
- review path：`ai-work/reviewer/{stage_id}-review.md`

完整 `stage_id` 是 artifact key。拆分 stage 不得共用 `WP5-executor.md` / `WP5-review.md`。

## 确定下一 stage

### Development-first stage selection

先阅读 proceedings 与规格 §20.0，把所有未完成交付按证据依赖分类，而不是简单选择“编号最小的未完成 WP”：

- `development`：生产代码、配置、CLI、adapter、artifact/checkpoint/resume、evaluation/aggregation/analysis 等能够在 GTX 1660 Ti/CPU + Piston + fixture/mock/synthetic evidence 上完成工程验收的工作；
- `validation`：必须依赖 24GB GPU、正式规模数据、真实 SFT/GRPO optimizer run、真实 checkpoint 或最终 A–D 数值才能成立的 gate。

选择规则：

1. 只要还有 dependency-ready 的 `development` 工作，就**必须优先规划 development stage**。较早 WP 只剩 deferred validation gate 时，不得因为它“未完全完成”而阻塞较晚 WP 的可独立开发工作。
2. 典型例子：WP6 真实 SFT/B 数值尚未完成时，仍可继续规划 WP7 的 GRPO adapter/reward/config/CLI/resume 开发；真实 B checkpoint 尚不存在时，仍可规划 WP8 的 aggregation/error-analysis tooling，并用 deterministic fixture 验证 schema/计算。
3. development stage 的缺失 24GB GPU、正式训练数据、真实 checkpoint **不是 blocker**；plan 不得要求 executor 为了 completed E0 去运行真实 SFT/GRPO。对 `train-sft`/`train-grpo` 的 1660 Ti fail-closed hardware guard 可以作为开发测试证据。
4. fixture/mock/synthetic 可以满足 development-stage contract test，但 plan 必须明确禁止把这些 artifact 记录为正式 B/C/D checkpoint、研究指标、训练成本或 final validation evidence。
5. 只有 proceedings 明确记录 `development-complete`（所有计划内生产代码与开发机工程 gates 已完成）后，才允许规划 `validation` stage。validation 按真实依赖顺序执行：Base A（如仍需正式数值）→ SFT B → Public/Hidden GRPO C/D → final aggregation/analysis。
6. validation stage 原则上只运行已冻结代码/配置并收集真实 evidence；若真实运行暴露实现缺陷，交给 repair/新的 development stage 修复，不在 validation plan 中顺手扩展功能或改变实验定义。
7. 若一个 WP 同时包含 development 与 validation 内容，必须拆 stage，确保 development stage 可在 1660 Ti 上独立 completed；不得把 24GB gate 与开发代码绑定在同一个 E0 completion contract 中。
8. 若规模超过单 stage 上限，继续拆成连续 stage（如 `WP5-a`、`WP5-b`），但**不要仅因内部可并行而拆 stage**；每个 stage 必须有独立验收边界。

每份 plan 必须在元信息中明确：

- `stage_profile: development | validation`
- `target_hardware: GTX 1660 Ti (6GB) | 24GB GPU`
- `evidence_class: engineering | real-training/numerical`

规模约束：通常实施步骤 ≤10、新模块 ≤8；超过或无法在一次可靠执行/验收中完成时拆分。

## 计划内容要求

计划必须：

- 精确到文件、函数/类完整签名；
- 逐步说明输入/输出/错误处理/调用关系；
- 保留规格已定义接口，不另造冲突签名；
- 每个步骤给测试文件、测试函数、断言与验证命令；
- 不确定外部 API/runtime 行为写入前置验证，不臆造；
- 不修改 `third_party/open-r1/`；Open-R1 访问只经 adapter；
- 实施步骤只依赖仓库文件、项目命令与执行 agent 自身文件/shell 能力，不依赖 MCP/其它 skill。

## Execution Routing Assessment

完整 plan 写完后再计算 routing。计划中包含且只包含一份：

```yaml
execution_routing:
  version: 1
  mode: single
  complexity: normal
  single_class: normal
  parallelizability: low
  multi_benefit: low
  independent_workstreams: 1
  rationale:
    - "..."
    - "..."
  workstream_candidates: []
```

### 三个独立维度

- `complexity`: `very_simple | normal | difficult_serial`，衡量单 agent 推理/调试强度；
- `parallelizability`: `low | medium | high`；
- `multi_benefit`: `low | medium | high`，必须考虑 coordinator/context/integration 成本。

### MULTI hard gate

只有以下全部满足才允许 `mode=multi`：

1. `complexity != very_simple`；
2. `parallelizability == high`；
3. `multi_benefit == high`；
4. 至少 2 个 substantive implementation workstream；
5. tracked write file/symbol ownership 基本互斥；
6. 无 lane 依赖另一 lane 尚未实现/定稿的 public API；
7. 每 lane 有独立、有意义的定向测试；
8. worker 完成后 coordinator 主要做集成验证，不需大量新 glue implementation。

“能并行”不等于“值得 MULTI”。多个很小 lane 仍用 SINGLE。

### SINGLE

- `very_simple`：机械、低风险局部实现，通常步骤≤3、生产/配置文件≤2、核心 public symbols≤4，且不涉及外部 runtime 探索、GPU/网络、事务/并发/状态机、checkpoint、安全、hidden-data、核心持久化格式、跨模块 public API 或关键真实 integration。
- `normal`：默认常规多文件实现/debug。
- `difficult_serial`：强串行高推理/调试风险。

SINGLE 时 `single_class == complexity`；`independent_workstreams` 填实际数量（可 >1），`workstream_candidates: []`。

MULTI 时 `single_class: null`；candidate 数量必须等于 `independent_workstreams`，每项含唯一 `id`、互不重叠 `steps`、互不重叠 tracked `write_scope`。candidate 只是证据，executor 仍按实际代码复核。

planner-ex 不写模型名/effort，也不选择 execution backend。`backend=local|web` 只由 execution-router 在每次 implementation/repair 调用时消费；sealed routing 只描述任务本身。single 模型映射只由 execution-router 维护。

## 输出与 handoff

最终产物是**完整 plan 正文**，使用 `references/plan-template.md`。完成后：

1. 自检 schema、范围、验收与 stage metadata；
2. 不写入 main 的 `ai-work/planner/`；
3. handoff 前再次确认 `main HEAD == planning_base_commit`，且 `git worktree list` / stage branch 集合与规划开始时一致；若 planner 运行期间出现新的 branch/worktree 或 primary HEAD 改变，返回 `PLANNER_GIT_STATE_CHANGED`，不要发布可执行 handoff；
4. 优先通过 CodexPro handoff 发布完整正文，并明确下一步：`$stage-lifecycle bootstrap_plan`；调用方可在当前 Web GPT + CodexPro 或 Local Codex 中执行同一个 lifecycle skill；
5. 若只能文本返回，必须同时返回 `stage_id / planning_base_commit / branch / worktree / final plan path`，供 bootstrap 使用。

`stage-lifecycle` commit 完 plan 后，execution-router 才能消费；未 seal 的 handoff plan 不可执行。

## 自检

- [ ] 无 active stage，或本次是明确且允许的 pre-execution replan；
- [ ] stage_id 唯一且完整，拆分 stage 使用 `WPn-a/b/...`；
- [ ] 已明确 `stage_profile / target_hardware / evidence_class`，development stage 不包含 24GB 真实训练 gate，validation stage 不接受 synthetic/mock 作为完成证据；
- [ ] 若仍有 dependency-ready development 工作，没有因为较早 WP 的 deferred validation gate 而错误规划 24GB stage；
- [ ] 已记录 planning_base_commit，且与本次规划读取的 `main HEAD` 一致；
- [ ] plan/execution/review artifact 都使用完整 stage_id；
- [ ] 只覆盖一个可独立验收 stage；
- [ ] 每步函数级、可测试、可判定；
- [ ] 没有 plan 外范围蔓延或 `third_party/open-r1/` 修改；
- [ ] routing 三维独立评估，MULTI 通过 hard gate；
- [ ] plan 未写模型/effort；
- [ ] planner-ex 没有创建 worktree/branch、commit/merge/push，也没有在 main 写最终 plan；
- [ ] planner-ex 前后的 primary HEAD、worktree 集合与 stage branch 集合一致；
- [ ] 最终正文已准备交给 `stage-lifecycle bootstrap_plan`。
