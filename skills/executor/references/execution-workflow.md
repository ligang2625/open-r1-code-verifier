# MULTI execution workflow reference v2

## Scope

`task_kind=implementation` 与 `task_kind=repair` 互斥。Implementation 按 plan steps；repair 只按 router 的 repair_issue_ids。Plan 的全局验收在 repair 中只是 regression gate，不扩大修复范围。

## Worker boundaries

- 每个 worker 只写 assigned tracked write_scope；
- 不 stage/commit、不写总 execution report；
- 不继续 spawn；
- 定向测试使用隔离 temp/output/cache；共享 `.coverage`、同一 output 文件、共享 cache DB 等由 coordinator 串行处理。

## Coordinator

- 基于真实代码复核 ≥2 独立 subplans，否则 routed MULTI 返回 ROUTING_MISMATCH；
- 汇总 diff，亲自跑整体验收；
- 仅 coordinator commit；
- code/test commit 完成后捕获 result_code_commit，再 append execution report 并 docs commit。

## Execution record

同一 stage 使用 `ai-work/executor/{stage_id}-executor.md`，append-only；已有 committed report 时旧内容必须保持不变，每次 execution docs commit 只在 EOF 追加恰好 1 个新 record + 摘要。

```yaml
execution_record:
  version: 1
  stage_id: WP5-b
  execution_id: E0
  task_kind: implementation
  source_plan_commit: <sha>
  source_review_round: null
  source_review_commit: null
  repair_issue_ids: []
  result_code_commit: <sha>
  execution_backend: local_codex
  effective_execution_mode: multi
  status: completed
```

Repair E1/E2/... 填整数 review round、review commit 和 exact repair_issue_ids。

## Repair scope

不存在“blocker/major/minor 默认全部修复”的 routed 规则。只有 repair_issue_ids 是本轮可修改问题；routing 外 finding 记录给 reviewer，不顺手修。

## Failure

plan/review provenance、worktree/branch、scope ownership、测试/规格冲突任一不满足时 fail closed；不改 routing，不伪造 completed record。
