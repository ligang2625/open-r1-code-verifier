# Execution + Repair Routing / Workflow State Contract v2

## 1. Stage identity

完整 `stage_id` 是阶段 artifact 唯一键，例如 `WP5-b`：

- plan `ai-work/planner/{stage_id}-plan.md`
- execution `ai-work/executor/{stage_id}-executor.md`
- review `ai-work/reviewer/{stage_id}-review.md`
- plan metadata 必须记录 `planning_base_commit`，即 planner-ex 实际规划时读取的 `main HEAD`

不同 stage 不共用 execution/review 文件。`bootstrap_plan` 与 `finalize` 都要求 primary HEAD 仍等于该 planning base；正常流程不自动换基线或 rebase。

## 2. Plan routing

```yaml
execution_routing:
  version: 1
  mode: single
  complexity: normal
  single_class: normal
  parallelizability: low
  multi_benefit: low
  independent_workstreams: 1
  rationale: ["...", "..."]
  workstream_candidates: []
```

SINGLE：single_class==complexity；candidate=[]。MULTI：single_class=null、complexity!=very_simple、parallelizability=high、multi_benefit=high、workstreams>=2；candidate 数量相等且 steps/tracked write_scope 不重叠。

## 3. Execution record

每次 implementation/repair 必须在 stage execution report 追加一个结构化记录：

```yaml
execution_record:
  version: 1
  stage_id: WP5-b
  execution_id: E0
  task_kind: implementation  # implementation | repair
  source_plan_commit: <plan seal commit>
  source_review_round: null
  source_review_commit: null
  repair_issue_ids: []
  result_code_commit: <HEAD after code/test commits, before report docs commit>
  status: completed
```

Repair 示例：

```yaml
execution_record:
  version: 1
  stage_id: WP5-b
  execution_id: E1
  task_kind: repair
  source_plan_commit: <plan commit>
  source_review_round: 1
  source_review_commit: <committed R1 review commit>
  repair_issue_ids: [R1-M1]
  result_code_commit: <code HEAD>
  status: completed
```

规则：
- execution_id 在 stage 内单调：implementation 固定 E0，repair 为 E1/E2/...；
- code/test 修改先提交，再捕获 result_code_commit；随后追加 execution record 并用 docs commit 封存 report，避免 commit hash 自引用；
- **`execution_report_commit` 不写进 record**，由 Git 历史定位“首次包含该 execution_record 的 docs commit”；reviewer 开始审查前必须 `HEAD == execution_report_commit`；
- 同一 source_plan_commit 的 completed implementation 只能有一次；
- 同一 source_review_commit 的 completed repair 只能有一次。

## 4. Review record

```yaml
review_record:
  version: 1
  stage_id: WP5-b
  review_round: 1
  source_execution_id: E0
  reviewed_head_commit: <stage HEAD before editing review file>
  conclusion: needs_repair  # needs_repair | pass
```

review_round 为正整数。R2+ 必须消费上一 review 后产生的新 completed repair execution。

stage-lifecycle checkpoint_review 提交 review 时，review commit 的父提交必须等于 reviewed_head_commit。

## 5. Repair routing

```yaml
repair_routing:
  version: 1
  required: true
  source_review_round: 1
  mode: single
  complexity: normal
  single_class: normal
  parallelizability: low
  multi_benefit: low
  independent_workstreams: 1
  repair_issue_ids: [R1-M1]
  rationale: ["...", "..."]
  workstream_candidates: []
```

- source_review_round 必须是整数且等于同轮 review_round。
- `review_record.conclusion` 与 `repair_routing.required` 必须一致：`pass ⇔ false`，`needs_repair ⇔ true`。
- required=false：mode/complexity/single_class/parallelizability/multi_benefit=null；workstreams=0；repair_issue_ids/candidates=[]。
- required=true：repair_issue_ids 非空且唯一，并覆盖所有 reviewer 要求下一轮 executor 行动的 finding。
- Repair MULTI candidate：`id`、非空 `issue_ids`、tracked `write_scope`；issue/path 不重叠，所有 repair_issue_ids 恰好覆盖一次。

## 6. Actionable issue invariant

任何 failed plan step / acceptance / independent test / reviewer-required blocker-major-minor 都必须映射至少一个 stable issue ID，并进入 repair_issue_ids。非必修 suggestion 可以不进入。

## 7. State machine

- PLANNED：plan seal committed，无 completed E0；plan 的 planning_base_commit 与当前 primary baseline 一致。
- IMPLEMENTED：completed E0，尚无 committed R1。
- REPAIR_REQUIRED：latest committed review conclusion=needs_repair 且 required=true，stage HEAD==review_commit，尚无 matching repair execution。
- REPAIR_EXECUTED：存在 completed repair，source_review_commit==上一 review_commit，等待新 review。
- PASSED：latest committed review conclusion=pass 且 required=false，stage HEAD==review_commit。
- FINALIZED：stage-lifecycle merge + finalization docs + cleanup 完成。

非法转移必须 fail closed。

## 8. Idempotency / stale guards

- completed E0 已存在 → `ROUTING_IMPLEMENTATION_ALREADY_EXECUTED`
- completed E0 不存在但 `HEAD != plan_commit` → `ROUTING_INCOMPLETE_IMPLEMENTATION`，不得自动重跑 plan
- latest review 尚未 commit → `ROUTING_REVIEW_NOT_COMMITTED`
- 指定 round 不是 latest committed → `ROUTING_STALE_REVIEW`
- matching completed repair 已存在 → `ROUTING_REPAIR_ALREADY_EXECUTED`
- required=false → `ROUTING_NO_REPAIR_REQUIRED`
- HEAD/provenance 无法解释 → `ROUTING_STAGE_STATE_INVALID`
- reviewer 没有新 execution → `REVIEW_NO_NEW_EXECUTION`
- checkpoint 时 HEAD != reviewed_head_commit → `STAGE_REVIEW_STALE`
- finalize 时 stage HEAD != latest review_commit → `STAGE_FINALIZE_STALE`

## 9. Version compatibility

Router / executor / executor-ex / stage-lifecycle 当前 compatibility marker：`execution-routing-v2`。目标 worktree 缺失该 marker 时不得 routed execution。
