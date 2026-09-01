# Execution + Repair Routing / Workflow State Contract v2

## 1. Stage identity and artifact ownership

完整 `stage_id` 是阶段 artifact 唯一键，例如 `WP5-b`：

- plan `ai-work/planner/{stage_id}-plan.md`
- execution `ai-work/executor/{stage_id}-executor.md`
- review `ai-work/reviewer/{stage_id}-review.md`
- plan metadata 必须记录 `planning_base_commit`，即 planner-ex 实际规划时读取的 `main HEAD`，并记录 `stage_profile / control_plane_hardware / target_hardware / evidence_class / development_terminal`；`control_plane_hardware` 固定为 `GTX 1660 Ti (6GB)`，与 target hardware 正交

不同 stage 不共用 execution/review 文件。`planning_base_commit` 是规划时 provenance anchor，不是 immutable base lock；`bootstrap_plan` / `finalize` 若发现 primary HEAD 前移，应由 LLM 判断变化是否与 stage scope/依赖兼容。兼容时使用 effective current base 并记录，只有冲突或 provenance 无法归属时停止。

Existing-stage resolution 对 router、reviewer-ex、stage-lifecycle checkpoint/finalize 统一：显式 stage_id 优先；未提供时仅在恰好 1 个尚未合并 active stage worktree 时自动采用；0 个或多个候选均停止，禁止按编号/mtime/最近创建猜测。bootstrap_plan 始终以 handoff payload 的 stage metadata 为准。

Canonical ownership：

- `planner-ex`：Web/CodexPro planning producer；在 primary root 只读规划，唯一传输输出是 `.ai-bridge/current-plan.md`；不得创建/修改 branch/worktree。
- `stage-lifecycle`：Web/Local 共用 Git lifecycle control plane；`bootstrap_plan` 是 v2 中唯一创建 stage branch/worktree 的 owner，`checkpoint_review` 提交 review，`finalize` merge + proceedings/finalization + cleanup（terminal development 同时写 Development Complete Record），`retire_incomplete` 只归档无 completed E0/review 的半截 stage。无 backend 参数。
- `execution-router`：从 primary root 推导 stage/provenance，并在运行时选择 `backend=local|web`；用户未覆盖时保留 source routing，用户明确指令或真实依赖需要时可形成 effective routing。
- `executor-ex` / `executor`：Local backend execution；SINGLE/MULTI 是默认 topology，不要求为了 sealed 形式制造不合理 lane。
- `executor-web`：Web backend execution；默认 source SINGLE → `single`、source MULTI → `serialized_multi`，但 effective mode 可根据用户指令/真实依赖调整并记录。
- `reviewer-ex`：Web reviewer；必须审查准确 stage worktree，不因 execution backend/effective mode 改变审查标准。

`.ai-bridge/**` 是本地 gitignored transport namespace，不是 repository/stage artifact，任何 branch 上都必须保持 **zero tracked paths**。planner/router/executor/reviewer/lifecycle 可以读写所需 transport 文件，但不得 stage/commit 它们；若 `git ls-files .ai-bridge` 非空，先返回 workflow-state error，不继续 stage mutation。`.ai-bridge/current-plan.md` 只是 pending transport；bootstrap 后 committed plan 是**默认执行基线和历史 provenance**。用户后续明确指令可以形成 effective execution contract，无需改写 sealed plan。

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

Web effective mode 默认是 source SINGLE → `single`、source MULTI → `serialized_multi`。这是默认 backend topology，不是 immutable contract；用户明确指定或真实依赖变化时可调整 effective mode/lanes，并记录原因。sealed routing 保留为历史 baseline，不要求回写或为了形式维持 MULTI。

## 4. Plan profile + routing

Profile contract：

- development → `target_hardware=GTX 1660 Ti (6GB)`、`evidence_class=engineering`、`development_terminal=true|false`；不得把真实 SFT/GRPO 作为 completed E0 gate。terminal=true 还必须有 WP0–WP8 Development Completion Inventory；`DEV-CLOSEOUT` inventory 全部 finalized、默认 routing SINGLE，并允许 zero-code E0。若存在可解释的 provenance/docs commits，`result_code_commit` 记录实际 HEAD，不要求等于 plan_commit。
- validation → `control_plane_hardware=GTX 1660 Ti (6GB)`、`evidence_class=real-training/numerical`、`development_terminal=false`；`target_hardware` 按本 stage 是否执行新的 target-GPU 计算选择。只消费既有 formal evidence 做 aggregation/CI/analysis/report 时 target=GTX 1660 Ti；含任何新 24GB execution 时 target=24GB GPU。后者的全部 24GB acceptance gates必须经 operator boundary；target 上实际 handoff commit、tracked script SHA、evidence/artifact identity 保持严格，普通 parent/source SHA 只用于审计。
- 每份 plan 必须有 Execution preflight；executor 在首次业务修改前运行当前 task 的必要最小集合。sealed preflight 是默认清单，可跳过已被可靠 evidence 覆盖、过时或与 effective scope 无关的项；失败后按可修环境/代码/blocker 判断，不要求保持某个 exact HEAD。
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

SINGLE/MULTI schema 描述 planner 的默认 routing assessment。用户没有 override 时 executor 应优先遵循；字段轻微缺失/不一致可由 LLM 从 plan/code 恢复，真实依赖或用户明确指令也可改变 effective topology。不要为了满足 schema 形式制造假 lane。只有 stage/task/scope 无法可靠确定时才把 routing contract 视为阻塞。

Planner 只描述任务本身，不选择 backend/model/effort；后续 effective routing 变化记录在 execution artifact，不必改写 sealed plan。

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
- 普通 stage 的 code/test/config 完成后捕获 `result_code_commit`，随后 append report；report commit 应尽量窄。`DEV-CLOSEOUT` 不制造业务 diff，但若存在可解释的 provenance/docs commit，记录实际 `result_code_commit`，不要求等于 plan_commit。
- `execution_report_commit` 不写进 record，由 Git 历史定位为 provenance anchor。reviewer 比较 current HEAD/diff 与该 anchor；可归因的用户 continuation/必要修正可以纳入审查，只有未知或冲突的实质变化才阻塞。
- 一个 effective implementation source 只能有一个 completed E0；不能利用普通 source_plan SHA 漂移重复执行。
- 一个 effective repair source/issue scope 只能有一个 completed repair；不能利用普通 source_review SHA 漂移重复消费。
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

review_round 为正整数。R2+ 默认关联上一 review 后的 repair/continuation；普通 source commit SHA 漂移不单独使 round 无效，只要 issue/commit lineage 可唯一确认。

Reviewer 只依赖 Git/provenance/code/tests/spec 与用户明确 override；`execution_backend/effective_execution_mode` 不改变安全/证据审查标准。reviewer-ex 必须运行在未参与 latest execution 的全新 Web conversation/context。

review artifact append-only：已有 committed review history 时，新一轮只在 EOF 追加新 record/routing。`reviewed_head_commit` 是实际审查代码的 anchor；review commit parent 不要求机械等于它，只要两者之间没有未审查的实质代码/配置变化。

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

- `source_review_round` / conclusion / required / repair_issue_ids 用于表达本轮默认 repair contract；`pass ⇔ required=false`、`needs_repair ⇔ required=true` 的语义必须清楚。
- routing 维度或 candidate schema 有轻微缺失/不一致时，先从 findings/code/user intent normalization；只有是否需要 repair 或 effective issue scope 无法确定时才阻塞。
- 用户未覆盖时 repair_issue_ids 应覆盖 reviewer 要求下一轮行动的 findings；用户明确重新定义 repair scope 时，以用户指令形成 effective repair contract并记录。
- Web backend 默认把 repair MULTI 串行化；真实依赖/用户指令可以调整 effective topology，不必改写 sealed repair_routing。

## 8. Actionable issue invariant

任何 failed plan step / acceptance / independent test / reviewer-required blocker-major-minor 都必须映射至少一个 stable issue ID，并进入 repair_issue_ids。非必修 suggestion 可以不进入。

## 9. State machine

- PLANNED：plan seal committed，无 completed E0；plan_commit 是 baseline，current HEAD 有可解释的非业务变化时仍可开始。
- INTERRUPTED_ENV：存在可识别 environment interruption/checkpoint 或等价 partial state；current HEAD 不必等于 checkpoint commit，环境修复后优先 continuation。
- INCOMPLETE_UNKNOWN：partial state 暂不能由 formal checkpoint直接解释；router 先做 LLM continuation assessment。能可靠识别 completed/remaining scope则继续，只有不可恢复/无法归属或用户放弃才 retire/replan。
- IMPLEMENTED：存在 completed E0；普通 SHA 漂移不改变已完成事实。
- REPAIR_REQUIRED：latest effective review 需要 repair，且 effective issue scope 尚未被 completed repair 覆盖。
- REPAIR_EXECUTED：存在 completed repair，等待 reviewer 审查实际 code/issue lineage。
- PASSED：latest effective review pass，且没有未审查的实质变化；HEAD 不要求等于 review_commit。
- FINALIZED：stage-lifecycle merge + finalization docs + cleanup 完成。

无法安全解释的状态转移 fail closed；可解释的 commit/hash 漂移不应被当成非法转移。

Environment checkpoint 是推荐的恢复记录，不是 resume 的唯一凭证。`result_code_commit`/parent/source commits 是审计 anchors；普通 SHA 漂移可由 Git diff/history解释。只有 stage/task 归属、completed/remaining scope、以及不能重复消费 completed execution等必要状态必须可靠。

## 10. Idempotency / stale guards

- effective completed E0 已存在 → `ROUTING_IMPLEMENTATION_ALREADY_EXECUTED`；普通 source_plan SHA 漂移不能绕过幂等保护。
- environment checkpoint 存在 → 优先作为 resume anchor；checkpoint 不是 current HEAD 也可在后续 commits兼容时继续。
- 无 formal checkpoint但 partial execution 可由 Git/report/tests可靠恢复 → continuation；只有无法归属/不可恢复才 `ROUTING_INCOMPLETE_IMPLEMENTATION`。
- latest review 未 commit → 默认 `ROUTING_REVIEW_NOT_COMMITTED`；用户明确要求使用可可靠归属的草稿时可形成 temporary effective repair contract。
- 指定旧 round/source → 先判断用户是否明确要求消费该范围以及当前 lineage 是否仍适用；只有 stale source 会导致错误执行时才 `ROUTING_STALE_REVIEW`。
- matching effective completed repair 已存在 → `ROUTING_REPAIR_ALREADY_EXECUTED`。
- effective review required=false → `ROUTING_NO_REPAIR_REQUIRED`。
- HEAD/provenance **无法安全解释** → `ROUTING_STAGE_STATE_INVALID`；普通 hash/parent 漂移不够构成该错误。
- runtime/tool-surface 证据不足以区分 Local Codex 与 Web GPT + CodexPro → `ROUTING_RUNTIME_UNDETERMINED`，不得猜 backend。
- 真正的 Web GPT + CodexPro 请求 local backend（或未指定 backend）→ `ROUTING_LOCAL_BACKEND_REQUIRES_LOCAL_CODEX`。
- Local MULTI 缺少 execution-agent capability 时可调整 effective topology；只有用户要求真正 MULTI 且无可用 capability/替代方案时报告 capability error。
- Web backend 能力不可用 → `ROUTING_WEB_BACKEND_UNAVAILABLE`，不得静默改 backend。
- reviewer conversation 参与过 latest Web execution → `REVIEW_FRESH_CONTEXT_REQUIRED`。
- reviewer 没有新 completed execution或可归因 continuation → `REVIEW_NO_NEW_EXECUTION`。
- checkpoint/finalize 发现 HEAD 与记录 anchor 不同 → 检查差异；只有存在未审查的实质变化才 `STAGE_REVIEW_STALE` / `STAGE_FINALIZE_STALE`。

## 11. Version compatibility

Router / executor / executor-ex / executor-web / stage-lifecycle 当前 compatibility marker：`execution-routing-v2`。目标 worktree 缺失所需 skill/marker 或 `.agents/skills` discovery entry 时不得开始 routed execution。
