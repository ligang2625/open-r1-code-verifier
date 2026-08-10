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

## 输入

1. `PROJECT_SPEC_Open-R1_CodeVerifier.md`：至少精读目标 WP 相关章节、§20 WP 注册表、§21 Code Review、§19 测试、§29 默认决策。
2. `proceedings.md`：确认已完成、部分完成、受阻阶段。
3. 当前 `src/`、`tests/` 与只读 Git/worktree 状态。
4. `references/plan-template.md`。

## Active-stage guard

规划下一 stage 前先记录 `planning_base_commit = main HEAD`，并快照当前 `git worktree list` 与相关 stage branches。然后枚举尚未合并的 stage worktree/branch：

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

1. 阅读 proceedings，按 §20 顺序找到第一个未完全完成 WP。
2. 若该 WP 部分完成，计划只覆盖剩余交付。
3. 若规模超过单 stage 上限，拆成连续 stage（如 `WP5-a`、`WP5-b`），但**不要仅因内部可并行而拆 stage**。
4. 每个 stage 必须有独立验收边界。

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
