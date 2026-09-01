# MULTI execution workflow reference v2

## Scope

`task_kind=implementation` 与 `task_kind=repair` 互斥。用户未覆盖时 implementation 按 plan steps、repair 按 router issue scope；用户明确改变实现/scope/order时按 effective contract执行并记录。Plan 的全局验收在 repair 中只是 regression gate，不自动扩大修复范围。

## Worker boundaries

- 每个 worker 只写 assigned tracked write_scope；
- 不 stage/commit、不写总 execution report；
- 不继续 spawn；
- 定向测试使用隔离 temp/output/cache；共享 `.coverage`、同一 output 文件、共享 cache DB 等由 coordinator 串行处理。

## Coordinator

- 基于真实代码复核 effective topology；默认 MULTI 应有 ≥2 独立 subplans，但若只剩 1 个可靠 lane，可降级/串行化并记录，不为形式制造假并行；
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

Repair E1/E2/... 记录 review provenance anchor 与 effective repair issue scope；普通 review commit SHA 漂移不要求 exact 等式。

## Repair scope

用户未覆盖时不存在“blocker/major/minor 默认全部修复”的规则，默认按 repair_issue_ids；用户明确增加/替换 scope 时按 effective issues 执行并记录。

## Failure

worktree/stage 身份错误、scope 无法归属、测试/规格不可调和冲突时 fail closed。普通 plan/review provenance SHA 漂移先看 lineage/diff；routing 可因用户指令或真实依赖调整 effective topology，但不得伪造 completed record。
