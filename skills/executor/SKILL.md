---
name: executor
description: MULTI execution protocol。入口创建 Sol/medium coordinator，coordinator 按 routed task_kind 将 implementation steps 或 repair_issue_ids 拆给 Luna/max workers；要求至少 2 个真实独立 lane，提交集成后的代码并写结构化 execution_record。不得重判 routing、不得 review/finalize。
---

# Codex Executor

Routing compatibility marker: `execution-routing-v2`。

## 固定 agent topology

入口 agent 只做一件事：创建 1 个 main coordinator：

- model: `gpt-5.6-sol`
- reasoning_effort: `medium`
- fork_turns: `none`

main coordinator 为每个独立 subplan 创建 1 个 worker：

- model: `gpt-5.6-luna`
- reasoning_effort: `max`
- fork_turns: `none`

worker 不再创建 agent。模型配置不由 router 覆盖。

## Invocation mode

本 skill 支持两种**互斥**入口：

1. **Routed v2 mode（新 hybrid workflow）**：任务中同时存在 `routing_mode=multi`、`task_kind`、`stage_id`、`plan_commit`。后续全部 v2 provenance/idempotency 规则生效。
2. **Legacy direct mode（保留 full-local `planner → executor → reviewer`）**：没有上述 router provenance。此时继续使用 legacy planner/reviewer 给出的 plan/review、branch/worktree 与报告路径；允许最终只有 1 个 subplan；repair 沿用 legacy reviewer 的问题范围/严重级别规则；不要求 `execution_record`、review_commit 或 stage-lifecycle，也**不得把 legacy artifact 当作 v2 router 已消费状态**。

两种模式禁止混合：若只提供部分 v2 provenance，立即返回 `EXECUTOR_ROUTING_CONTEXT_INCOMPLETE`，不得降级成 legacy。

## Routed MULTI 前置

在 routed v2 mode 中，router 必须传：stage_id、绝对 worktree、plan path、plan_commit、`task_kind=implementation|repair`、`routing_mode=multi`。repair 再传 review path、整数 source_review_round、review_commit、repair_issue_ids。

`task_kind` 两条路径互斥；repair 完成后不得继续 implementation。

main 开始任何拆分/修改前先进入 stage worktree、读 plan/spec/代码和对应 routing source。

## Anti-fake-parallel hard guard

routed MULTI 必须基于真实代码形成 ≥2 个 mutually independent subplans：tracked write file/symbol ownership 可分离、无未完成 public API 前置依赖、各自有独立测试。

若只能形成 1 个：不 spawn worker、不实现，返回 `ROUTING_MISMATCH`；不得退化为 Sol coordinator + 1 Luna。

- implementation：复核 plan candidate `steps`。
- repair：只复核/拆分 router 的 `repair_issue_ids`，worker issue 并集必须恰好等于这些 IDs。

## Legacy direct mode

仅当完全没有 v2 router provenance 时使用：

- 完整读取 legacy planner 给出的 plan；若用户/legacy reviewer 明确要求修复则同时读取对应 review。
- 仍由 Sol/medium coordinator 拆分并用 Luna/max workers；若真实依赖只能形成 1 个 subplan，legacy mode 允许 1 个 worker，保持旧 workflow 兼容。
- implementation 按 legacy plan 完整执行；repair 按 legacy review 的问题规则处置，不使用 v2 `repair_issue_ids` gate。
- 从 plan 文件名/元信息得到完整 `stage_id`（如 `WP3-c`）；legacy execution report 使用 `ai-work/executor/{stage_id}-executor.md`，对应 legacy reviewer 使用 `ai-work/reviewer/{stage_id}-review.md`，避免拆分 stage 互相覆盖。
- 其它提交/复审路径按 legacy `planner/reviewer` skill 的约定；不要伪造 v2 `execution_record` 或让 execution-router 消费该结果。
- legacy mode 不调用 stage-lifecycle；最终 merge/proceedings 仍由 legacy reviewer 负责。

## task_kind=implementation（仅 routed v2）

1. 确认 report 不存在 matching completed E0，且开始修改前 stage `HEAD == plan_commit`；若 HEAD 已前进但没有 completed E0，停止并报告 incomplete implementation，不得重新执行整份 plan。
2. 按 plan steps 拆独立 subplans。
3. 每个 worker 任务必须自包含：worktree、plan、assigned steps、唯一 tracked write_scope、禁止项、定向测试、汇报格式。
4. workers 只改 assigned tracked scope，不 stage/commit、不写总报告。
5. coordinator 汇总 diff、解决集成顺序、亲自运行定向 + 全局验收。
6. coordinator 按独立 subplan 显式暂存并 commit 集成后的 code/test/config；禁止 `git add -A`。
7. 捕获 `result_code_commit=HEAD`。
8. append `ai-work/executor/{stage_id}-executor.md` 的 E0 execution_record 和人类摘要，再 docs commit report。

## task_kind=repair（仅 routed v2）

1. 开始修改前 stage HEAD 必须等于 router `review_commit`；review round/issues 与任务完全一致。
2. 只按 `repair_issue_ids` 拆 subplans；其它 review finding/plan step 不自动进入 scope。
3. worker issue_ids 不重叠、tracked write_scope 不重叠；全部 repair_issue_ids 恰好覆盖一次。
4. worker 做最小修复和定向测试；不提交。
5. coordinator 集成后运行受影响测试 + plan 全局 regression/acceptance。全局测试只验证，不扩大 repair scope。
6. coordinator commit 修复代码/测试，捕获 result_code_commit。
7. append En repair execution_record，再 docs commit report。同一 review_commit 只能产生一次 completed repair。

## Parallel filesystem isolation

worker 除 assigned tracked files 外不得写共享业务 artifact。pytest/cache/output/temp 若可能冲突：

- 使用每 worker 独立临时目录/输出路径；或
- 将共享生成/共享验证留给 coordinator 串行执行。

不要让多个 worker 并发写 `.coverage`、同一 output JSON、同一 cache DB 等共享状态。

## Execution record

Implementation：

```yaml
execution_record:
  version: 1
  stage_id: WP5-b
  execution_id: E0
  task_kind: implementation
  source_plan_commit: <plan_commit>
  source_review_round: null
  source_review_commit: null
  repair_issue_ids: []
  result_code_commit: <code HEAD>
  status: completed
```

Repair：E1/E2/...；填整数 source_review_round、source_review_commit、repair_issue_ids。

只有所有必须验收通过才标 completed。code commits 在前，report docs commit 在后。

## 边界

- 不修改 plan/review/proceedings/third_party；不 push。
- 不自行改 routing/model/effort。
- review 由 reviewer-ex；Git checkpoint/finalization 由 stage-lifecycle。

## 自检

- [ ] task_kind 互斥；
- [ ] routed MULTI ≥2 真实 subplans，否则已 ROUTING_MISMATCH；
- [ ] repair worker issue 并集恰好等于 repair_issue_ids；
- [ ] worker tracked write_scope/临时输出互不冲突；
- [ ] coordinator 亲自完成整体验收与 commits；
- [ ] result_code_commit 在 report docs commit 前捕获；
- [ ] completed execution_record provenance 完整；
- [ ] 未改 plan/review/proceedings，未 push。
