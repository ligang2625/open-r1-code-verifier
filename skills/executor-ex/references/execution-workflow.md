# SINGLE execution workflow reference v2

## Core rule

`task_kind=implementation` 与 `task_kind=repair` 严格互斥。任何 routed repair 的工作范围只由 `repair_issue_ids` 决定；plan 的全局测试/验收只用于 regression verification，不会把其它 review findings 或 plan steps 拉回 scope。

## Failure table

| 情况 | 动作 |
|---|---|
| 实现错误 | 修实现，不改测试预期迁就实现 |
| 测试预期与规格冲突 | 停止并记录规格/测试证据 |
| plan/review provenance 不一致 | 停止，不猜测 |
| 外部环境缺失 | 如实记录；plan 有替代路径才继续 |
| routed repair 遇到 routing 外问题 | 不顺手修改；在报告遗留/风险中记录，交 reviewer 下一轮决定 |

## Report protocol

同一 `{stage_id}` 使用 `ai-work/executor/{stage_id}-executor.md`，append-only。

### Implementation E0

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
  status: completed
```

### Repair En

```yaml
execution_record:
  version: 1
  stage_id: WP5-b
  execution_id: E1
  task_kind: repair
  source_plan_commit: <sha>
  source_review_round: 1
  source_review_commit: <sha>
  repair_issue_ids: [R1-M1]
  result_code_commit: <sha>
  status: completed
```

每个 record 后写人类可读的文件变更、命令与结果、issue/step 处置、异议和遗留问题。

## Commit ordering

1. code/test/config 修改按计划/repair scope commit；
2. 完成整体验收；
3. 捕获 `result_code_commit=HEAD`；
4. append execution record/report；
5. 单独 docs commit execution report。

因此 report commit 不需要自引用自己的 hash。

## Repair scope

- routed repair：只处理 repair_issue_ids；
- 不存在“blocker/major/minor 默认全部修”的隐式规则；
- suggestion 只有 reviewer 把其 ID 放进 repair_issue_ids 才处理；
- 运行 `make lint`/`make test`/stage gate 是 regression verification，不等于允许修 routing 外问题。

## Workspace

所有操作在 stage worktree；不在 main checkout 切换已被 linked worktree 占用的 branch。不修改 plan/review/proceedings/third_party，不自动 push。
