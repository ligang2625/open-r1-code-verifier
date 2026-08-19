# Execution + Repair Routing / Workflow State Contract v2

## 1. Stage identity and artifact ownership

完整 `stage_id` 是阶段 artifact 唯一键，例如 `WP5-b`：

- plan `ai-work/planner/{stage_id}-plan.md`
- execution `ai-work/executor/{stage_id}-executor.md`
- review `ai-work/reviewer/{stage_id}-review.md`
- plan metadata 必须记录 `planning_base_commit`，即 planner-ex 实际规划时读取的 `main HEAD`，并记录 `stage_profile / control_plane_hardware / target_hardware / evidence_class / development_terminal`；`control_plane_hardware` 固定为 `GTX 1660 Ti (6GB)`，与 target hardware 正交

不同 stage 不共用 execution/review 文件。`bootstrap_plan` 与 `finalize` 都要求 primary HEAD 仍等于 planning base；正常流程不自动换基线或 rebase。

Existing-stage resolution 对 router、reviewer-ex、stage-lifecycle checkpoint/finalize 统一：显式 stage_id 优先；未提供时仅在恰好 1 个尚未合并 active stage worktree 时自动采用；0 个或多个候选均停止，禁止按编号/mtime/最近创建猜测。bootstrap_plan 始终以 handoff payload 的 stage metadata 为准。

Canonical ownership：

- `planner-ex`：Web/CodexPro planning producer；在 primary root 只读规划，唯一传输输出是 `.ai-bridge/current-plan.md`；不得创建/修改 branch/worktree。
- `stage-lifecycle`：Web/Local 共用 Git lifecycle control plane；`bootstrap_plan` 是 v2 中唯一创建 stage branch/worktree 的 owner，`checkpoint_review` 提交 review，`finalize` merge + proceedings/finalization + cleanup（terminal development 同时写 Development Complete Record），`retire_incomplete` 只归档无 completed E0/review 的半截 stage。无 backend 参数。
- `execution-router`：从 primary root 推导 stage/provenance，并在运行时选择 `backend=local|web`；不修改 source routing。
- `executor-ex` / `executor`：Local backend 的 SINGLE/MULTI execution。
- `executor-web`：Web backend execution；source SINGLE → `single`，source MULTI → `serialized_multi`。
- `reviewer-ex`：Web reviewer；必须审查准确 stage worktree，不因 execution backend/effective mode 改变审查标准。

`.ai-bridge/**` 是本地 gitignored transport namespace，不是 repository/stage artifact，任何 branch 上都必须保持 **zero tracked paths**。planner/router/executor/reviewer/lifecycle 可以读写所需 transport 文件，但不得 stage/commit 它们；若 `git ls-files .ai-bridge` 非空，先返回 workflow-state error，不继续 stage mutation。`.ai-bridge/current-plan.md` 只是 pending transport；bootstrap seal 成功后，stage worktree 中的 committed plan 是唯一 authoritative plan。

## 2. Official workflows

### Hybrid / Local execution

`planner-ex (Web) → stage-lifecycle bootstrap_plan (Web or Local) → execution-router backend=local (Local Codex) → executor-ex|executor (Local) → reviewer-ex (fresh Web conversation) → stage-lifecycle checkpoint_review (Web or Local) → ... → stage-lifecycle finalize (Web or Local)`

### Full Web

`planner-ex → stage-lifecycle bootstrap_plan → execution-router backend=web → executor-web → [new Web conversation] → reviewer-ex → stage-lifecycle checkpoint_review → ... → stage-lifecycle finalize`

Web execution 和 reviewer 不得共享同一个 GPT conversation/context。executor-web 完成 execution report commit 后停止；新的 reviewer conversation 只从 Git/sealed artifacts 重建状态。web backend 不调用 Local Codex execution agent。

### Mixed

backend 按**每次 execution**选择，而不是按 stage/project 固定。因此 `E0=local, E1=web, E2=local` 合法；唯一必须连续的是 Git/provenance 链。每次 Web execution 后仍使用新的 reviewer conversation。

## 3. Runtime execution backend

backend 不写入 plan/review routing，并按**实际 execution runtime 与 capability**判定，不按 control surface/transport 判定：

- `backend=local`：SINGLE → executor-ex；MULTI → executor。本机 Codex CLI/app-server 直接操作 repo/worktree 即属于 Local Codex；Happy mobile/web/remote control 只是控制界面，仍归类为 local。Local Codex 中未指定 backend 时默认 local。
- `backend=web`：仅当前会话本身是 Web GPT，并通过 CodexPro workspace/tool 操作 repo 时使用 executor-web。Web 环境必须显式选择 web；不得因为 `remote`、mobile、browser、Happy 等 UI/transport 信号把 Local Codex 改判为 web。
- Local MULTI 还要求 execution-agent 能力；缺失时报 `ROUTING_LOCAL_AGENT_CAPABILITY_UNAVAILABLE`，不得自动切 web，也不得把 capability 缺失误判成 runtime 类型变化。
- 若当前 thread/tool surface 不足以可靠区分 Local Codex 与 Web GPT + CodexPro，返回 `ROUTING_RUNTIME_UNDETERMINED`；不得默认猜成 web。

Web effective mode：

- source SINGLE → `single`
- source MULTI → `serialized_multi`

`backend=web + source MULTI` 的串行化是正式 backend 语义，不是 fallback。sealed `mode=multi`、workstream candidates 和 routing rationale 不得改写为 SINGLE。

## 4. Plan profile + routing

Profile contract：

- development → `target_hardware=GTX 1660 Ti (6GB)`、`evidence_class=engineering`、`development_terminal=true|false`；不得把真实 SFT/GRPO 作为 completed E0 gate。terminal=true 还必须有 WP0–WP8 Development Completion Inventory；`DEV-CLOSEOUT` inventory 全部 finalized、routing 固定 SINGLE，并允许 zero-code E0 (`result_code_commit==plan_commit`)。
- validation → `control_plane_hardware=GTX 1660 Ti (6GB)`、`target_hardware=24GB GPU`、`evidence_class=real-training/numerical`、`development_terminal=false`。validation plan/bootstrap/router/reviewer 默认仍在 1660 Ti；普通 dispatch 不做本机 24GB GPU preflight。真正的 target-GPU gate 由 portable operator handoff 交给用户在 4090 手工执行，script 在 target start 时 fail closed 验证 READY record、>=22 GiB GPU、persistent roots、model/data/cache/Piston；formal checkpoint/results 留在 target persistent root。
- 每份 plan 必须有 Execution preflight；executor 在首次业务修改前运行。implementation preflight 失败保持 `HEAD==plan_commit`，repair 保持 `HEAD==review_commit`，均不写 blocked commit/report。
- terminal development PASS finalize 只通过 proceedings 中精确 `## Development Complete Record` + 合法 YAML block 写 marker；自然语言提及不算。terminal finalization docs commit 后的 main HEAD 是 `development_complete_commit`，用于解锁 1660 Ti 上的 validation planning；只有后续具体 target-GPU operator checkpoint 的 exact commit/handoff 才需要同步到 4090。

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
- execution report append-only：已有 committed report 时，后续 execution 不得改写旧内容；每次 execution docs commit 只允许在 EOF 追加恰好 1 个新的 execution record 与对应摘要。
- 普通 stage 的 code/test/config 先 commit，再捕获 `result_code_commit`；随后 append report 并单独 docs commit。`DEV-CLOSEOUT` 是 verification-only 例外：不制造业务 diff，允许 `result_code_commit == plan_commit`，随后只提交 execution report。
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

Reviewer 只依赖 Git/provenance/code/tests/spec；`execution_backend/effective_execution_mode` 不改变 review 标准或 conclusion。reviewer-ex 必须运行在未参与 latest execution 的全新 Web conversation/context。

review artifact append-only：已有 committed review history 时，新一轮只能在 EOF 追加恰好 1 个 `review_record` + 同轮 `repair_routing`，不得改写旧轮次。stage-lifecycle checkpoint_review 提交 review 时，review commit 的父提交必须等于 reviewed_head_commit。

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

- PLANNED：plan seal committed，无 completed E0，且 stage `HEAD==plan_commit`。
- INTERRUPTED_ENV：latest current-head execution artifact 是合法 committed `execution_checkpoint(status=interrupted, interruption_class=environment, resume_allowed=true)`，且尚无同 source completed execution；普通 router 只提示 resume，用户显式 `execution-router resume` 后恢复原 task/routing。
- INCOMPLETE_UNKNOWN：无 completed execution，但 HEAD 已超过 plan/review baseline，且不存在可证明当前 HEAD 的合法 resumable checkpoint；router 不自动继续。用户确认放弃时才走 `retire_incomplete`（在该 operation 合法范围内）或其它人工恢复流程。
- IMPLEMENTED：completed E0，尚无 committed R1。
- REPAIR_REQUIRED：latest committed review `needs_repair + required=true`，stage HEAD==review_commit，尚无 matching repair。
- REPAIR_EXECUTED：存在 matching completed repair，等待新 review。
- PASSED：latest committed review `pass + required=false`，stage HEAD==review_commit。
- FINALIZED：stage-lifecycle merge + finalization docs + cleanup 完成。

非法转移 fail closed。

Environment checkpoint contract：checkpoint docs commit 必须只修改 execution report，parent 等于 `result_code_commit`；record 精确绑定 task/source provenance，`failed_command/blocker/remaining_scope` 非空，`interruption_class=environment`、`resume_allowed=true`、`status=interrupted`。修复需要 tracked 仓库修改的 lint/test/config/dependency failure 不能使用该 checkpoint。

## 10. Idempotency / stale guards

- completed E0 已存在 → `ROUTING_IMPLEMENTATION_ALREADY_EXECUTED`
- latest current-head 合法 environment checkpoint + 普通调用 → `ROUTING_RESUME_AVAILABLE`
- latest current-head 合法 environment checkpoint + 显式 resume → 消费原 plan/review routing，从 remaining_scope 继续；若指定 checkpoint_id 必须匹配 latest
- 无 completed E0、`HEAD != plan_commit` 且无合法 checkpoint → `ROUTING_INCOMPLETE_IMPLEMENTATION` / INCOMPLETE_UNKNOWN；只有用户确认放弃时才提示 retire/replan
- latest review 尚未 commit → `ROUTING_REVIEW_NOT_COMMITTED`
- 指定 round 非 latest committed → `ROUTING_STALE_REVIEW`
- matching completed repair 已存在 → `ROUTING_REPAIR_ALREADY_EXECUTED`
- required=false → `ROUTING_NO_REPAIR_REQUIRED`
- HEAD/provenance 无法解释 → `ROUTING_STAGE_STATE_INVALID`
- runtime/tool-surface 证据不足以区分 Local Codex 与 Web GPT + CodexPro → `ROUTING_RUNTIME_UNDETERMINED`，不得猜 backend
- 真正的 Web GPT + CodexPro 请求 local backend（或未指定 backend）→ `ROUTING_LOCAL_BACKEND_REQUIRES_LOCAL_CODEX`
- Local MULTI 缺少 execution-agent capability → `ROUTING_LOCAL_AGENT_CAPABILITY_UNAVAILABLE`，runtime 仍保持 local
- Web backend 能力不可用 → `ROUTING_WEB_BACKEND_UNAVAILABLE`，不得自动 local
- reviewer conversation 参与过 latest Web execution → `REVIEW_FRESH_CONTEXT_REQUIRED`
- reviewer 没有新 execution → `REVIEW_NO_NEW_EXECUTION`
- checkpoint 时 HEAD != reviewed_head_commit → `STAGE_REVIEW_STALE`
- finalize 时 stage HEAD != latest review_commit → `STAGE_FINALIZE_STALE`

## 11. Version compatibility

Router / executor / executor-ex / executor-web / stage-lifecycle 当前 compatibility marker：`execution-routing-v2`。目标 worktree 缺失所需 skill/marker 或 `.agents/skills` discovery entry 时不得开始 routed execution。
