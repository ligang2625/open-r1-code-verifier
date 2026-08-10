# Execution + Repair Routing / Workflow State Contract v2

## 1. Stage identity and artifact ownership

完整 `stage_id` 是阶段 artifact 唯一键，例如 `WP5-b`：

- plan `ai-work/planner/{stage_id}-plan.md`
- execution `ai-work/executor/{stage_id}-executor.md`
- review `ai-work/reviewer/{stage_id}-review.md`
- plan metadata 必须记录 `planning_base_commit`，即 planner-ex 实际规划时读取的 `main HEAD`

不同 stage 不共用 execution/review 文件。`bootstrap_plan` 与 `finalize` 都要求 primary HEAD 仍等于 planning base；正常流程不自动换基线或 rebase。

Canonical ownership：

- `planner-ex`：Web/CodexPro planning producer；在 primary root 只读规划，唯一传输输出是 `.ai-bridge/current-plan.md`；不得创建/修改 branch/worktree。
- `stage-lifecycle`：Web/Local 共用 Git lifecycle control plane；`bootstrap_plan` 是 v2 中唯一创建 stage branch/worktree 的 owner，`checkpoint_review` 提交 review，`finalize` merge + proceedings/finalization + cleanup。无 backend 参数。
- `execution-router`：从 primary root 推导 stage/provenance，并在运行时选择 `backend=local|web`；不修改 source routing。
- `executor-ex` / `executor`：Local backend 的 SINGLE/MULTI execution。
- `executor-web`：Web backend execution；source SINGLE → `single`，source MULTI → `serialized_multi`。
- `reviewer-ex`：Web reviewer；必须审查准确 stage worktree，不因 execution backend/effective mode 改变审查标准。

`.ai-bridge/current-plan.md` 只是 pending transport；bootstrap seal 成功后，stage worktree 中的 committed plan 是唯一 authoritative plan。

## 2. Official workflows

### Hybrid / Local execution

`planner-ex (Web) → stage-lifecycle bootstrap_plan (Web or Local) → execution-router backend=local → executor-ex|executor (Local) → reviewer-ex (Web) → stage-lifecycle checkpoint_review (Web or Local) → ... → stage-lifecycle finalize (Web or Local)`

### Full Web

`planner-ex → stage-lifecycle bootstrap_plan → execution-router backend=web → executor-web → reviewer-ex → stage-lifecycle checkpoint_review → ... → stage-lifecycle finalize`

这些步骤可在同一个 Web GPT + CodexPro 会话完成；web backend 不调用 Local Codex execution agent。

### Mixed

backend 按**每次 execution**选择，而不是按 stage/project 固定。因此 `E0=local, E1=web, E2=local` 合法；唯一必须连续的是 Git/provenance 链。

## 3. Runtime execution backend

backend 不写入 plan/review routing：

- `backend=local`（默认）：SINGLE → executor-ex；MULTI → executor。
- `backend=web`：当前 Web GPT + CodexPro → executor-web。

Web effective mode：

- source SINGLE → `single`
- source MULTI → `serialized_multi`

`backend=web + source MULTI` 的串行化是正式 backend 语义，不是 fallback。sealed `mode=multi`、workstream candidates 和 routing rationale 不得改写为 SINGLE。

## 4. Plan routing

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

SINGLE：single_class==complexity；candidate=[]。

MULTI：single_class=null、complexity!=very_simple、parallelizability=high、multi_benefit=high、workstreams>=2；candidate 数量相等且 steps/tracked write_scope 不重叠。

Planner 只描述任务本身，不选择 backend/model/effort。

## 5. Execution record

每次 routed implementation/repair 在 stage execution report 追加：

```yaml
execution_record:
  version: 1
  stage_id: WP5-b
  execution_id: E0
  task_kind: implementation
  source_plan_commit: <plan seal commit>
  source_review_round: null
  source_review_commit: null
  repair_issue_ids: []
  result_code_commit: <HEAD after code/test commits, before report docs commit>
  execution_backend: web_codexpro
  effective_execution_mode: serialized_multi
  status: completed
```

Repair：E1/E2/...；填写整数 source_review_round、committed source_review_commit、repair_issue_ids。

规则：

- E0 固定 implementation；repair 单调 E1/E2/...。
- code/test/config 先 commit，再捕获 `result_code_commit`；随后 append report 并单独 docs commit。
- `execution_report_commit` 不写进 record，由 Git 历史定位首次包含该 execution_record 的 docs commit；reviewer 开始前必须 `HEAD == execution_report_commit`。
- 同一 source_plan_commit 的 completed implementation 只能一次。
- 同一 source_review_commit 的 completed repair 只能一次。
- 新 routed execution 应写 `execution_backend` 与 `effective_execution_mode`；二者只用于审计，不参与 provenance 判定。历史 record 缺失仍可读取。

合法审计值：

- `execution_backend`: `local_codex | web_codexpro`
- `effective_execution_mode`: `single | multi | serialized_multi`

## 6. Review record

```yaml
review_record:
  version: 1
  stage_id: WP5-b
  review_round: 1
  source_execution_id: E0
  reviewed_head_commit: <stage HEAD before editing review file>
  conclusion: needs_repair
```

review_round 为正整数。R2+ 必须消费上一 review 后的新 completed repair execution。

Reviewer 只依赖 Git/provenance/code/tests/spec；`execution_backend/effective_execution_mode` 不改变 review 标准或 conclusion。

stage-lifecycle checkpoint_review 提交 review 时，review commit 的父提交必须等于 reviewed_head_commit。

## 7. Repair routing

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

- source_review_round 必须等于同轮 review_round。
- `pass ⇔ required=false`，`needs_repair ⇔ required=true`。
- required=false：routing 维度 null、workstreams=0、repair_issue_ids/candidates=[]。
- required=true：repair_issue_ids 非空唯一，并覆盖 reviewer 要求下一轮 executor 行动的 findings。
- Repair MULTI candidate：`id`、非空 `issue_ids`、tracked `write_scope`；issue/path 不重叠，所有 repair_issue_ids 恰好覆盖一次。

Web backend 对 repair MULTI 同样使用 `serialized_multi`，不改 repair_routing。

## 8. Actionable issue invariant

任何 failed plan step / acceptance / independent test / reviewer-required blocker-major-minor 都必须映射至少一个 stable issue ID，并进入 repair_issue_ids。非必修 suggestion 可以不进入。

## 9. State machine

- PLANNED：plan seal committed，无 completed E0；planning_base_commit 与 primary baseline 一致。
- IMPLEMENTED：completed E0，尚无 committed R1。
- REPAIR_REQUIRED：latest committed review `needs_repair + required=true`，stage HEAD==review_commit，尚无 matching repair。
- REPAIR_EXECUTED：存在 matching completed repair，等待新 review。
- PASSED：latest committed review `pass + required=false`，stage HEAD==review_commit。
- FINALIZED：stage-lifecycle merge + finalization docs + cleanup 完成。

非法转移 fail closed。

## 10. Idempotency / stale guards

- completed E0 已存在 → `ROUTING_IMPLEMENTATION_ALREADY_EXECUTED`
- 无 completed E0 但 `HEAD != plan_commit` → `ROUTING_INCOMPLETE_IMPLEMENTATION`
- latest review 尚未 commit → `ROUTING_REVIEW_NOT_COMMITTED`
- 指定 round 非 latest committed → `ROUTING_STALE_REVIEW`
- matching completed repair 已存在 → `ROUTING_REPAIR_ALREADY_EXECUTED`
- required=false → `ROUTING_NO_REPAIR_REQUIRED`
- HEAD/provenance 无法解释 → `ROUTING_STAGE_STATE_INVALID`
- Web backend 能力不可用 → `ROUTING_WEB_BACKEND_UNAVAILABLE`，不得自动 local
- reviewer 没有新 execution → `REVIEW_NO_NEW_EXECUTION`
- checkpoint 时 HEAD != reviewed_head_commit → `STAGE_REVIEW_STALE`
- finalize 时 stage HEAD != latest review_commit → `STAGE_FINALIZE_STALE`

## 11. Version compatibility

Router / executor / executor-ex / executor-web / stage-lifecycle 当前 compatibility marker：`execution-routing-v2`。目标 worktree 缺失所需 skill/marker 或 `.agents/skills` discovery entry 时不得开始 routed execution。
