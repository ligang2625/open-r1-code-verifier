---
name: executor
description: Local Codex MULTI execution protocol。仅用于 execution-router backend=local；Sol/medium coordinator 将 routed implementation/repair 拆给 Luna/max workers，要求至少 2 个真实独立 lane，并写统一 v2 execution_record。不得重判 routing、不得 review/finalize。
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

本 skill **只支持 routed v2**。调用必须同时包含 `source_mode=multi`、`backend=local`、`task_kind`、`stage_id`、`plan_commit`；缺少任一项返回 `EXECUTOR_ROUTING_CONTEXT_INCOMPLETE`。不提供 legacy direct mode，也不自行从文件名/当前分支猜 execution source。

## Routed MULTI 前置

router 必须传：stage_id、绝对 worktree、plan path、plan_commit、`task_kind=implementation|repair`、`source_mode=multi`、`backend=local`。repair 再传 review path、整数 source_review_round、review_commit、repair_issue_ids。

`task_kind` 两条路径互斥；repair 完成后不得继续 implementation。

main 开始任何拆分/修改前先进入 stage worktree、读 plan/spec/代码和对应 routing source。execution report 必须保持 append-only：若已有 committed report，本次只能在 EOF 追加恰好 1 个新的 execution record 与对应摘要，不得改写旧 E0/E1/... 历史。

## Anti-fake-parallel hard guard

routed MULTI 必须基于真实代码形成 ≥2 个 mutually independent subplans：tracked write file/symbol ownership 可分离、无未完成 public API 前置依赖、各自有独立测试。

若只能形成 1 个：不 spawn worker、不实现，返回 `ROUTING_MISMATCH`；不得退化为 Sol coordinator + 1 Luna。

- implementation：复核 plan candidate `steps`。
- repair：只复核/拆分 router 的 `repair_issue_ids`，worker issue 并集必须恰好等于这些 IDs。

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
  execution_backend: local_codex
  effective_execution_mode: multi
  status: completed
```

Repair：E1/E2/...；填整数 source_review_round、source_review_commit、repair_issue_ids，并同样记录 `execution_backend: local_codex`、`effective_execution_mode: multi`。

backend/effective mode 只用于审计，不参与 provenance 判定。只有所有必须验收通过才标 completed。code commits 在前，report docs commit 在后。

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
