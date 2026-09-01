---
name: execution-router
description: Routed execution 控制面。默认消费 sealed plan / latest review routing，但允许用户明确指令覆盖执行方式；结合 Git/provenance 与当前项目状态由 LLM 判断 continuation/resume 是否安全，并按运行时 backend=local|web 调度。只保留必要的身份/完整性校验，不把普通 commit/SHA 漂移当作机械阻塞。
---

# Execution Router

Routing compatibility marker: `execution-routing-v2`。

## Workflow precedence 与宽松 provenance 原则

本 workflow 的目标是可靠推进项目，而不是维护一个不可变的 Git 状态机。发生冲突时按以下优先级处理：

1. **用户当前明确指令**最高。用户在 execution、repair、resume 或其它阶段明确指定新的实现、顺序、routing、范围或恢复方式时，只要不违反仓库安全边界和不可伪造的 evidence contract，就以用户指令为准；sealed plan/review 只作为默认基线。
2. 用户没有覆盖时，严格按 sealed plan / latest committed review 执行，避免 agent 自行扩大 scope。
3. commit/SHA/provenance 字段主要用于定位和审计。除跨机器 operator script/evidence 内容完整性、stage/worktree 身份、防止重复消费已完成 execution、以及 `.ai-bridge` 不得 tracked 等必要边界外，不因普通 HEAD 前移、parent 不完全相等、workflow runtime commit 漂移或缺少某个历史 hash 就机械拒绝。
4. 遇到 partial/incomplete execution 时，router 必须先由 LLM 结合 plan/review、Git history/diff、execution report、测试结果和当前 working tree 判断是否可安全继续。**可恢复是默认方向**；只要没有明确不可修复冲突、不可判定的数据损坏或用户要求放弃，就允许 resume/continue，并记录判断依据。
5. 若采用用户 override 或 LLM continuation judgment 与 sealed artifact 不完全一致，把偏差、原因、受影响 scope 和采用的 provenance anchor 写入 execution report；不要为了满足旧 hash guard 制造无意义 commit 或强迫 retire/replan。

## 入口与 backend

标准入口是在**主仓库 root checkout** 调用。若从 linked stage worktree 调用，先解析 primary root，再基于 Git worktree 状态定位目标 stage；router 自己不在 primary checkout `git switch` stage branch。

每次 execution 都有一个**运行时** backend。backend 必须按**实际执行 runtime 与可用 capability**判定，而不是按控制界面、连接方式或“remote/web”字样猜测：

- `backend=local`：SINGLE → `executor-ex`；MULTI → `executor`。适用于运行在本机 Codex `app-server` / Codex CLI 上、可直接访问本地 repo/worktree 并具备所需 Codex execution capability 的会话。通过 Happy mobile/web/remote control 连接到本机 Codex **仍属于 Local Codex runtime**；Happy 的 `remote` 只表示 control surface，不得据此判成 Web GPT。Local Codex 中未显式指定 backend 时默认 local。
- `backend=web`：仅适用于当前会话本身是 **Web GPT + CodexPro**，由 Web GPT 通过 CodexPro workspace/tool 操作本地 repo 的情况；在同一对话中继续执行 `executor-web`，不得创建或调用 Local Codex execution agent。Web 环境必须显式指定 `backend=web`。

runtime 判定遵循 common-case capability guard：

1. 优先使用当前线程的实际 host/tool surface，而不是提示词中的环境描述：由 Codex CLI/app-server 承载、使用当前 Codex thread 的原生命令/文件/Git 工具直接操作 workspace → `local_codex`；当前模型会话是 Web GPT、repo 操作只通过 CodexPro MCP/tool surface 完成 → `web_codexpro`。
2. Happy 只改变 control surface。只要底层仍是本机 Codex CLI/app-server，即使存在 Happy MCP、`--happy-starting-mode remote`、手机或浏览器控制，也仍判为 `local_codex`。
3. Local SINGLE 至少要求可直接操作目标 worktree；Local MULTI 还要求当前 Codex runtime 具备 execution-agent/subagent 调用能力。缺少 MULTI 所需 agent capability 时停止并报告 `ROUTING_LOCAL_AGENT_CAPABILITY_UNAVAILABLE`，不得因此改判 `backend=web`。
4. control surface 与 execution runtime 正交；不得使用 `remote`、mobile、browser、Happy 等 UI/transport 信号单独决定 backend。
5. 若没有足够的 runtime/tool-surface 证据区分 `local_codex` 与 `web_codexpro`，返回 `ROUTING_RUNTIME_UNDETERMINED`；不得默认猜成 web，也不得为了继续执行静默切 backend。

backend 不是 plan/review routing 字段，不写回 sealed plan/review，不影响 plan 的 `mode/complexity/parallelizability/multi_benefit`，也不参与 provenance 合法性判断。implementation 与每轮 repair 可以分别选择不同 backend。

Router 接受显式 `resume`，但 resume 不再要求存在某个完全匹配当前 HEAD 的 formal checkpoint。checkpoint 是恢复提示和审计材料，不是唯一入口。router 应结合 execution report、Git history/diff、测试结果和当前 workspace 状态判断 continuation：若已完成范围可识别、剩余范围可继续、没有不可修复冲突，则允许 resume/continue 并记录依据；只有明确不可继续时才进入 retire/replan。operator handoff 仍必须等待用户完成外部 command/evidence，不得由 router 越权执行。

真正的 Web GPT + CodexPro 环境请求 `backend=local`（或未指定 backend）时返回 `ROUTING_LOCAL_BACKEND_REQUIRES_LOCAL_CODEX`。Local Codex 的 MULTI execution 若缺少 execution-agent 能力则返回 `ROUTING_LOCAL_AGENT_CAPABILITY_UNAVAILABLE`；这不改变 runtime/backend 判定。若显式 `backend=web` 但当前环境不是 Web GPT + CodexPro，或没有可写 CodexPro workspace、Git、所需验证命令能力，则返回 `ROUTING_WEB_BACKEND_UNAVAILABLE`。以上情况都不得自动切 backend。

## Stage 定位

必须定位唯一 `stage_id` 与 stage worktree。优先使用调用方显式 stage_id；未给时，尚未合并 stage worktree 必须**恰好一个候选**：

- 0 → `ROUTING_PLAN_MISSING`
- >1 → `ROUTING_PLAN_AMBIGUOUS`

禁止按最大编号、mtime、最近创建等猜测。

Open-R1 artifact：

- plan：`ai-work/planner/{stage_id}-plan.md`
- execution：`ai-work/executor/{stage_id}-executor.md`
- review：`ai-work/reviewer/{stage_id}-review.md`

正常 stage 应存在由 `stage-lifecycle bootstrap_plan` 提交的 plan baseline；router 从 Git 推导 `plan_commit` 作为 provenance anchor。当前 plan/HEAD 与 seal 不同不自动等于 `ROUTING_PLAN_NOT_SEALED`：若差异来自用户明确 override、合法 amendment 或可解释 continuation，可形成 effective contract 并记录；只有无法找到可信 baseline、stage identity 不明或未经授权的 plan 漂移会让执行范围不可判定时才报该错误。同时从 plan/user/current state 推导 effective profile/hardware/evidence contract；真正 target-GPU 与 formal evidence 安全边界仍必须满足。

**旧 stage / workflow migration 兼容**：sealed plan 缺少后来新增的 metadata 时，router 不要求为了采用新 workflow 重写历史 plan。优先从 proceedings、已有 execution/review、当前代码与用户意图推导 effective metadata，并记录 `workflow_runtime_commit` 等实际 runtime anchors（如可得）。这些普通 commit SHA 用于审计，不要求与旧 plan/review 逐项精确匹配；只有 profile/hardware/evidence 语义无法可靠确定或会突破安全边界时才返回 `ROUTING_PLAN_PROFILE_INVALID`。

## Control-plane dispatch 与 target-GPU boundary

Router 默认只调度 **control-plane execution**。无论 `stage_profile=development|validation`，planner/bootstrap/router/reviewer 与普通 code edit、lint/unit/CPU/non-4090 integration、Piston、data preparation、analysis/report、operator-handoff preparation 都在 GTX 1660 Ti 上完成；`backend=web|local` 只描述当前执行 runtime，不等价于 target hardware。

对 `stage_profile=validation`，router 在普通 dispatch 前**不得**读取本机 `.ai-bridge/validation-machine.json`、不得要求 >=22528 MiB GPU，也不得要求 4090 的 `artifact_root/hf_home/formal_data_root` 已挂载。它只验证 sealed plan/provenance/stage environment 和 control-plane Execution preflight，并把 `control_plane_hardware/target_hardware` 传给 executor。

真正的 target-GPU boundary 由 sealed `operator_terminal_execution` gate 表示；validation `target_hardware=24GB GPU` 的**全部** 24GB acceptance gates（包括短 smoke）都经该边界，不存在 router 直接把 executor 切到 4090 的第二路径。control-plane executor 生成并提交 tracked portable script + operator checkpoint 后停止。用户通过 Git 把 exact checkpoint commit 同步到 4090，checkout/detach 到该 commit并运行 repo 内 hash-matching script。script 在 target start 时才读取/验证 `.ai-bridge/validation-machine.json`、READY/Piston identity、persistent roots、CUDA/VRAM >=22528 MiB、exact model/data/cache/storage；需要 Piston 时只验证 1660 Ti control plane 已建立的 canonical reverse-forward loopback endpoint 与 exact runtime，不启动旧 4090-side tunnel helper。训练入口 >=20 GiB guard 保留为第二层保护。

正式 artifacts 不回退到 control-plane repo-local `outputs/`。target script 在目标命令后立即运行 sealed post-run acceptance，并生成 versioned secret-free `operator-evidence.json`；只有 `command_rc=0 && postcheck_rc=0 && gate_status=passed` 才能完成 gate。用户把 evidence 与必要小型 status/log/manifest/metrics byte-for-byte 同步回 checkpoint 指定的 control-plane evidence 目录。router resume 必须验证 evidence schema/provenance、tracked script SHA 与 operator checkpoint commit，并计算 received evidence SHA256；大型 checkpoint 不默认复制。只有 evidence/postcheck 无法证明 required large-artifact property 时才允许短时只读 4090 check。

## Transport preflight

任何 dispatch 前都确认 primary checkout 与目标 stage worktree 的 `git ls-files .ai-bridge` 均为空；`.ai-bridge/**` 只能是 ignored 本地 transport state。任一 checkout 存在 tracked transport path 时返回 `ROUTING_TRANSPORT_TRACKED`，不得把它当作普通 dirty state继续 dispatch，也不得依赖 executor/finalize 在后续提交或 merge 时过滤。

## Stage environment preflight

任何 backend dispatch/executor 创建之前，router 都要验证 stage worktree 的 lifecycle environment contract：

1. `<stage-worktree>/.venv/bin/python` 必须存在；
2. 使用该 Python 导入 `code_verifier` 与 `open_r1`，二者 `__file__` 必须都解析到目标 stage worktree 下；
3. 不允许 stage `.venv` 直接软链接为 primary `.venv`，也不允许 editable source 仍指向 primary checkout；
4. `stage/.venv/bin/ruff` 必须存在，并且 stage Python 的 `-m ruff --version`、`-m mypy --version`、`-m pytest --version` 都必须成功。这样能在 dispatch 前捕获“site-packages 可见但 venv-local executable 缺失”的 overlay 错误。

任一条件失败返回 `ROUTING_STAGE_ENV_UNAVAILABLE`，在 dispatch 前停止。不要 spawn executor 后再让 plan preflight 因 `.venv`/tool 缺失失败。环境由 `stage-lifecycle bootstrap_plan` 自动创建；若用户手工删除/破坏 ignored `.venv`，先按 lifecycle 的 stage-environment helper 恢复，再重新调用 router。

## 状态推导与 source precedence

dispatch 前必须先检查 working tree，但 **dirty 不再自动等于不可执行**：

- 未提交 review 文件仍不直接交给 router 消费；默认返回 `ROUTING_REVIEW_NOT_COMMITTED`，除非用户明确要求基于该草稿执行并且来源/round 可可靠判断。
- 其它 tracked 或非忽略 untracked 改动由 LLM 判断归属。若它们明显属于当前 partial execution、用户刚指定的实现调整或可安全纳入的 continuation，可继续并在 report 记录 baseline；只有来源不明、与当前 stage 冲突、可能覆盖他人工作或无法判断时返回 `ROUTING_STAGE_DIRTY`。

不得在**无法解释**的 dirty baseline 上执行；可解释且可恢复的 dirty state 不应被机械阻塞。

### Resumable execution checkpoint

Router 优先使用 execution report 中最新可信的 `execution_checkpoint` 作为恢复 anchor，但 checkpoint commit **不必恰好等于 current HEAD**。恢复判断分两层：

- 必要身份：stage_id/task_kind 能归属于当前 stage、没有同一 source 的 completed execution、completed/remaining scope 或实际 Git diff 可以被可靠推导。
- 审计线索：source_plan/review commit、result_code_commit、checkpoint parent、checkpoint 后 commits 等用于判断历史，不要求逐项 SHA 完全相等。若它们有漂移，LLM 检查 diff/commit 内容并记录采用的 anchor。

只有 operator checkpoint 的 tracked script SHA/evidence SHA、跨机器 artifact identity 等内容完整性继续按 strict contract 校验，因为这些 hash 用于证明实际执行对象而非维护状态机形式。

然后按 `interruption_class` 分支校验：

- **environment**：`status: interrupted`；`failed_command`、`blocker` 非空。仅用于已有有效部分业务 commit 后的外部环境/基础设施故障。普通 router 调用返回 `ROUTING_RESUME_AVAILABLE`，报告 failed command/blocker/remaining scope，提示修复环境后显式 resume。
- **operator**：用于 effective validation contract 中确实需要 target-GPU/manual operator action 的 gate。`portable_target` 必须能唯一识别 gate、实际 handoff checkpoint commit、repo-relative tracked script 与 script SHA、expected artifacts/evidence destination；router 从 handoff commit 的 Git tree 读取并重算 script SHA，确认 `.ai-bridge/**` 未 tracked。是否该 script“恰好由本 commit 新增”、checkpoint parent/result-code/source-plan SHA 等只作审计，不是硬门槛。`control_plane_manual` 仅用于明确的 control-plane-only repair，latest review 或用户明确指令必须说明该 path，且不得执行新的 24GB GPU training/inference；workflow/review/source commit 只作 audit anchors，tracked script/frozen inputs/outputs/evidence identity 仍严格。普通调用返回 operator action，router 不自动 push或执行 script。

显式 `resume` 表示用户希望优先继续当前 stage。若用户指定 checkpoint_id，优先以它作为恢复 anchor；即使它不是 current HEAD 的 latest checkpoint，也可在确认后续 commits 与该恢复路径兼容时继续。缺失 formal checkpoint、普通 provenance 字段不匹配或 checkpoint 后存在额外 commits 都不单独触发 `ROUTING_RESUME_INVALID`；LLM 先做 continuation assessment。只有 stage/source 无法唯一归属、存在不可调和的状态冲突/损坏，或 operator script/evidence 内容 hash 失败时才判 resume invalid。不得因此自动 retire。

显式 resume 时重新执行当前任务必要的 stage-environment preflight；validation 在 control plane 不伪造 4090 preflight。operator resume 传 handoff checkpoint/script/evidence context，executor 计算 received evidence SHA256。严格校验只保留证明实际运行对象和结果所需的 identity：handoff checkpoint、tracked script SHA、evidence bytes、target machine/runtime（如适用）、`command_rc/postcheck_rc/gate_status`、formal run 与 required artifact hashes/inventory。plan/review/workflow-runtime/result-code 等普通 commit SHA 只作审计 anchors；漂移时检查 lineage/diff。证据不足以证明 required large-artifact property 时才要求短时只读 target check。通过后从 effective remaining scope 继续，并把 received evidence hash 以固定字段 `operator_evidence_sha256` 写入 completed execution record；不得替用户重跑任何 operator command。

### A. 尚无 committed review

- 已有 matching `task_kind=implementation,status=completed` → `ROUTING_IMPLEMENTATION_ALREADY_EXECUTED`，避免重复消费；普通 source_plan SHA 漂移不掩盖一个事实上已完成的 E0。
- 无 completed E0 时，以 plan 为默认基线，检查 current HEAD/partial commits/checkpoint/working tree。若尚未开始则正常 implementation；若已有可识别部分工作则进入 continuation/resume assessment。
- environment/operator checkpoint 存在时优先利用其 scope；operator 未完成外部 action 时仍返回 `ROUTING_OPERATOR_ACTION_REQUIRED`。
- 没有 formal checkpoint 但当前状态仍可可靠恢复时，也允许 `task_kind=implementation` continue。只有 LLM 明确认定状态不可恢复或 provenance 无法归属时才返回 `ROUTING_INCOMPLETE_IMPLEMENTATION`；此时再由用户决定修复、replan 或 retire。

### B. 已有 committed review

只允许消费**最新 committed review round**。显式指定旧 round → `ROUTING_STALE_REVIEW`。

先校验：

- `conclusion=pass ⇔ repair_routing.required=false`
- `conclusion=needs_repair ⇔ repair_routing.required=true`

不一致 → `ROUTING_REPAIR_CONTRACT_INVALID`。

- required=false → `ROUTING_NO_REPAIR_REQUIRED`
- required=true：
  1. 从 Git 定位 latest review 作为默认 repair baseline；
  2. 已有 matching completed repair → `ROUTING_REPAIR_ALREADY_EXECUTED`；
  3. 否则检查 review 后 commits/checkpoint/working tree，推导已完成与剩余 repair scope；`HEAD != review_commit` 本身不是错误。
  4. environment/operator checkpoint 存在时优先利用；没有 formal checkpoint但状态可可靠归因时，也允许 repair continuation。用户明确改变 repair 方式/scope 时以用户指令形成 effective repair contract。
  5. 只有无法确认当前变化属于哪轮 review/repair、存在互斥状态或不可恢复损坏时才返回 `ROUTING_STAGE_STATE_INVALID`。

Router 默认消费 latest committed review。若用户明确要求基于未 checkpoint 的 review 草稿执行，且 stage/round/issues 可可靠归属，可将其作为临时 effective repair contract；必须在 execution report 记录来源，不能把草稿伪装成 committed provenance。

## Routing contract

共同字段：`version=1`、mode、complexity、parallelizability、multi_benefit、independent_workstreams、rationale。

- `complexity`: `very_simple | normal | difficult_serial`
- `parallelizability/multi_benefit`: `low | medium | high`
- SINGLE：`single_class==complexity`、independent_workstreams≥1、workstream_candidates=[]
- MULTI：single_class=null、complexity≠very_simple、parallelizability=high、multi_benefit=high、independent_workstreams≥2
- implementation MULTI candidate：唯一 id、非空 `steps`、tracked `write_scope`；steps/write_scope 跨 candidate 不重叠，candidate 数量等于 workstreams
- repair required=true：repair_issue_ids 非空唯一；MULTI candidate 使用 `issue_ids` + tracked `write_scope`，issue_ids/write_scope 不重叠且 issue_ids 并集恰好等于 repair_issue_ids
- required=false 的 null/empty schema 只产生 NO_REPAIR，不执行

这些 schema 是默认 planning/review contract。字段缺失或内部不完全一致时，先判断是否能从 plan/review/代码和用户指令唯一推导 effective routing；能可靠恢复时继续并记录 normalization，只有 stage/task/scope 无法确定时才使用 `ROUTING_CONTRACT_MISSING/INVALID` 或 `ROUTING_REPAIR_CONTRACT_MISSING/INVALID`。

**用户未覆盖时优先保留 source routing；用户明确指令或真实代码依赖表明原 routing 不再合适时，router/LLM 可以调整 effective mode、lane 划分或顺序。** sealed routing 保留为审计 baseline，不必回写 plan/review。

## backend=local

### SINGLE

唯一执行模型映射：

| single_class | model | reasoning_effort |
|---|---|---|
| `very_simple` | `gpt-5.6-luna` | `max` |
| `normal` | `gpt-5.6-sol` | `medium` |
| `difficult_serial` | `gpt-5.6-sol` | `high` |

`fork_turns=none`。planner/reviewer 不写 model/effort。

1. 目标 worktree `skills/executor-ex/SKILL.md` 必须含 `execution-routing-v2`，否则 `ROUTING_SKILL_VERSION_MISMATCH`。
2. 创建恰好 1 个 execution agent。
3. 传：stage_id、绝对 worktree、stage branch、plan path、plan_commit、task_kind、`backend=local`、`source_mode=single`、single_class，以及 `stage_profile/control_plane_hardware/target_hardware/evidence_class/development_terminal`。普通 validation control-plane dispatch **不传 4090 `artifact_root/hf_home/formal_data_root`**；operator gate 使用 sealed target-runtime templates，并由 4090 script 解析真实 roots。
4. repair 再传 review path、source_review_round、review_commit、repair_issue_ids；resume 再传 `resume=true`、resume_checkpoint_id/commit、resume_from_code_commit、completed_scope、remaining_scope。
5. agent 必须先进入 stage worktree；不得 subagent。
6. single 实际无法可靠完成时，LLM 可根据当前代码状态和用户指令升级为更合适的 effective execution topology；若改变 source routing，记录原因和 effective mode，不必为了维持 sealed SINGLE 强行继续。

### MULTI

1. 目标 worktree `skills/executor/SKILL.md` 必须含 v2 marker。
2. 调用 `$executor`，传 stage/provenance、`backend=local`、`source_mode=multi`、`stage_profile/control_plane_hardware/target_hardware/evidence_class/development_terminal`；validation 的普通 control-plane dispatch 不要求/传入 4090 roots，operator target roots由 portable script 在 4090 解析；repair 同样传 review provenance/issues；resume 同样传 resume checkpoint context。
3. coordinator 基于真实代码复核 effective subplans。若不足 2 个独立 lane，可退化为 single/serialized execution 并记录理由；只有无法形成完整安全的执行方案时才返回 `ROUTING_MISMATCH`。
4. multi 模型/effort 继续由 executor 管理。

## backend=web

目标 worktree 必须同时满足：

- `skills/executor-web/SKILL.md` 存在并含 `execution-routing-v2`
- `.agents/skills/executor-web` 可解析到 repo-local `skills/executor-web`

否则 `ROUTING_SKILL_VERSION_MISMATCH`。

router **不 spawn execution agent**。它把 stage/provenance 和完整 source routing 交给当前 Web GPT，并在当前对话中继续按 `$executor-web` 协议执行。默认不是只返回 dispatch；除非调用方明确要求 dry-run，否则 router 选择 web backend 后应继续完成本次 execution。

传入 executor-web：

- stage_id、绝对 worktree、stage branch、plan path、plan_commit、task_kind
- `backend=web`
- `stage_profile/control_plane_hardware/target_hardware/evidence_class/development_terminal`；validation 普通 dispatch 不要求 4090 roots，operator gate 使用 target-runtime templates
- source routing 的完整结构和 `source_mode`
- repair 时：review path、source_review_round、review_commit、repair_issue_ids
- resume 时：`resume=true`、resume_checkpoint_id、resume_checkpoint_commit、resume_from_code_commit、completed_scope、remaining_scope

运行时 effective mode 默认映射为：source SINGLE → `single`，source MULTI → `serialized_multi`。但这只是默认 topology；用户明确指定或 executor 根据真实依赖判断需要调整时，可以记录不同的 `effective_execution_mode`，只要 stage/task scope 可追踪且执行完整。

`backend=web + source MULTI` 默认串行化原 workstreams；不要求为了保留 sealed MULTI 形式覆盖已经失效或人为拆分的 lane。effective topology 改变时记录 override/judgment，sealed plan/review 保留为历史 baseline。

Web execution 完成并提交 execution report 后，本次 execution 对话必须停止在 execution 边界；**不得在同一 GPT conversation/context 中继续调用 reviewer-ex 审查自己刚完成的 execution**。下一步应在新的 Web GPT conversation 中连接同一 repo 并调用 `$reviewer-ex`；可显式提供 stage_id，若只有一个 active stage 也可省略。review 所需状态全部从 Git/sealed artifacts 重建，不依赖 execution 对话上下文。

## Execution record backend metadata

Local/Web 共用同一 `execution_record.version: 1` provenance。新 routed execution 应额外记录：

```yaml
execution_backend: local_codex       # local_codex | web_codexpro
effective_execution_mode: single    # single | multi | serialized_multi
```

这两个字段仅用于审计，不参与 reviewer/router provenance 判定；历史 record 缺失它们仍可读取。

## 输出

报告：task_kind、stage_id、plan_commit、routing source、source_mode、backend、effective_execution_mode、绝对 worktree、`control_plane_hardware`、stage profile 与 `target_hardware`；若使用旧 sealed-plan 迁移兼容，额外报告 `legacy_control_plane_default=true`，明确没有改写 plan。validation control-plane dispatch 不声称当前拥有 target GPU。到 operator boundary 时报告 source script/hash、target commit、target-runtime path/evidence contract 与 manual-run 要求；target GPU identity/VRAM/roots 来自 4090 `operator-evidence.json`，不从 control-plane runtime伪造。repair 再报告 review provenance/issues；resume 再报告 checkpoint 与 remaining scope；local SINGLE 报实际 model/effort。

## 关键错误

- `ROUTING_PLAN_MISSING` / `ROUTING_PLAN_AMBIGUOUS` / `ROUTING_PLAN_NOT_SEALED` / `ROUTING_PLAN_PROFILE_INVALID`
- `ROUTING_OPERATOR_ACTION_REQUIRED` / `ROUTING_OPERATOR_EVIDENCE_MISSING` / `ROUTING_OPERATOR_EVIDENCE_INVALID`（target machine/GPU/storage 的 fail-closed 错误由 4090 operator-start script 记录进 evidence；历史 `ROUTING_VALIDATION_*` record 仍可审计读取）
- `ROUTING_STAGE_ENV_UNAVAILABLE`
- `ROUTING_RESUME_AVAILABLE` / `ROUTING_RESUME_INVALID`
- `ROUTING_STAGE_DIRTY`
- `ROUTING_REVIEW_NOT_COMMITTED` / `ROUTING_STALE_REVIEW`
- `ROUTING_IMPLEMENTATION_ALREADY_EXECUTED` / `ROUTING_INCOMPLETE_IMPLEMENTATION`
- `ROUTING_REPAIR_ALREADY_EXECUTED`
- `ROUTING_NO_REPAIR_REQUIRED`
- `ROUTING_STAGE_STATE_INVALID`
- `ROUTING_SKILL_VERSION_MISMATCH`
- `ROUTING_CONTRACT_*` / `ROUTING_REPAIR_CONTRACT_*`
- `ROUTING_MISMATCH`
- `ROUTING_RUNTIME_UNDETERMINED`
- `ROUTING_LOCAL_BACKEND_REQUIRES_LOCAL_CODEX`
- `ROUTING_LOCAL_AGENT_CAPABILITY_UNAVAILABLE`
- `ROUTING_WEB_BACKEND_UNAVAILABLE`

## 禁止事项

- router 不回写 sealed plan/review artifact；effective routing 可因用户明确指令或真实代码依赖调整，并记录在 execution report。
- router 自身不写业务代码；Web implementation 必须进入 executor-web 协议。
- 不做 review/proceedings/finalize/cleanup。
- 不重复消费事实上已 completed 的 effective source。默认不消费 uncommitted/stale review；用户明确要求且 stage/round/issues 可可靠归属时可使用其内容，但必须保留其草稿/stale 身份并记录依据。
- 不静默切 backend；backend 仍由实际 runtime/capability 决定。effective SINGLE/MULTI/serialized topology 可独立于 backend 调整。
