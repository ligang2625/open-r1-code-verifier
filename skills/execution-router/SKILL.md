---
name: execution-router
description: Routed execution 控制面。消费 stage-lifecycle seal 的 plan execution_routing 或 checkpoint 的最新 review repair_routing，结合 Git/provenance 状态阻止重复、stale 或 incomplete execution，并按运行时 backend=local|web 选择 Local Codex 或当前 Web GPT + CodexPro 执行。只做状态推导与执行调度，不自行重判 routing、不做 review/finalization。
---

# Execution Router

Routing compatibility marker: `execution-routing-v2`。

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

Router 还接受一个**显式恢复意图**：`resume`（例如 `$execution-router resume` 或等价明确指令）。`resume` 不是 routing 字段，也不能选择任意历史 commit；它只允许消费**当前 HEAD 对应的最新合法 resumable execution checkpoint**，即 `interruption_class=environment` 或 `interruption_class=operator`。普通调用遇到 environment checkpoint 时返回 `ROUTING_RESUME_AVAILABLE`；遇到 operator checkpoint 时返回 `ROUTING_OPERATOR_ACTION_REQUIRED` 并报告 exact script/status/log/expected artifacts；两者都不自动续跑。只有用户明确 resume 后才 dispatch，且继续消费原 plan/review 的 sealed routing，不重新规划、不改变 mode/backend。

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

plan 必须已经由 `stage-lifecycle bootstrap_plan` commit；router 通过 Git 历史推导 `plan_commit`。未提交、dirty 或 seal 后又修改 plan → `ROUTING_PLAN_NOT_SEALED`。同时解析 plan 的 `stage_profile / control_plane_hardware / target_hardware / evidence_class / development_terminal`；`control_plane_hardware` 必须是 `GTX 1660 Ti (6GB)`，并与 profile/target 映射一致，否则返回 `ROUTING_PLAN_PROFILE_INVALID`。`target_hardware=24GB GPU` 只描述 formal gate 的执行目标，不决定当前 Web/Local backend 或 router 所在机器。

## Control-plane dispatch 与 target-GPU boundary

Router 默认只调度 **control-plane execution**。无论 `stage_profile=development|validation`，planner/bootstrap/router/reviewer 与普通 code edit、lint/unit/CPU/non-4090 integration、Piston、data preparation、analysis/report、operator-handoff preparation 都在 GTX 1660 Ti 上完成；`backend=web|local` 只描述当前执行 runtime，不等价于 target hardware。

对 `stage_profile=validation`，router 在普通 dispatch 前**不得**读取本机 `.ai-bridge/validation-machine.json`、不得要求 >=22528 MiB GPU，也不得要求 4090 的 `artifact_root/hf_home/formal_data_root` 已挂载。它只验证 sealed plan/provenance/stage environment 和 control-plane Execution preflight，并把 `control_plane_hardware/target_hardware` 传给 executor。

真正的 target-GPU boundary 由 sealed `operator_terminal_execution` gate 表示：control-plane executor 只生成 portable handoff + operator checkpoint，用户在 4090 手工运行。portable `run.sh` 在 4090 启动时才读取/验证 target-local `.ai-bridge/validation-machine.json`、READY/Piston identity、绝对 `artifact_root/hf_home/formal_data_root`、CUDA/VRAM >=22528 MiB、exact model/data/cache、storage capacity 与（若需要）到唯一 Piston host `1660ti-wsl` 的 loopback tunnel。训练入口原有 >=20 GiB guard 继续作为第二层保护。

正式 artifacts 不回退到 control-plane repo-local `outputs/`。target script 将 checkpoint/results 保留在 4090 persistent root，并生成 secret-free `operator-evidence.json` 与必要小型 status/log/manifest/metrics。用户把这些 evidence 同步回 checkpoint 指定的 control-plane ignored evidence 目录后，router resume/reviewer 默认在 1660 Ti 完成 strict readback/aggregation/provenance 验证；只有 evidence 不足且确实需要 target GPU 或大 artifact 本地读取时，才允许短时只读连接 4090。

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

任何 dispatch 前 stage worktree 必须干净：

- 只有 review 文件存在 staged/unstaged/untracked 修改 → `ROUTING_REVIEW_NOT_COMMITTED`
- 其它 tracked 或非忽略 untracked 改动 → `ROUTING_STAGE_DIRTY`

不得在未知 dirty baseline 上启动 execution。

### Resumable execution checkpoint

Router 只把 execution report 中**最新 committed**、且提交该 checkpoint 的 docs commit 恰好等于当前 stage HEAD 的 `execution_checkpoint` 视为 resumable。所有 class 共同要求：

- `version: 1`、非空唯一 `checkpoint_id`、`resume_allowed: true`；
- `stage_id/task_kind/source_plan_commit` 与当前 stage 精确一致；implementation 的 `source_review_round/source_review_commit` 必须为 null、`repair_issue_ids=[]`；repair 必须精确绑定 latest committed review round/commit/issues；
- `result_code_commit` 必须是 checkpoint docs commit 的 parent HEAD，且该 docs commit 只允许改 execution report；
- `completed_scope` 与非空 `remaining_scope` 可解析；当前不存在同一 source 的 completed execution，也不存在 checkpoint 之后的其它 commit。

然后按 `interruption_class` 分支校验：

- **environment**：`status: interrupted`；`failed_command`、`blocker` 非空。仅用于已有有效部分业务 commit 后的外部环境/基础设施故障。普通 router 调用返回 `ROUTING_RESUME_AVAILABLE`，报告 failed command/blocker/remaining scope，提示修复环境后显式 resume。
- **operator**：只允许 `stage_profile=validation` 且 sealed plan 存在匹配 `operator_terminal_execution.gates[].gate_id`；匹配 gate 的 `restart_policy` 必须是 `exact_rerun|trainer_checkpoint`，SFT/GRPO gate 必须为 `trainer_checkpoint`；`status: awaiting_operator`。新 checkpoint 使用 `operator_handoff_mode=portable_target`：必须有唯一 gate id、control-plane-local 绝对 `operator_script`、64-hex SHA256、target status/log/evidence templates、control-plane evidence directory 与非空 `expected_artifacts`；router 重新确认本地 source script 存在且 hash 匹配，但**不要求 4090 root 在 control plane 可见**。旧版没有 `operator_handoff_mode` 且记录 absolute persistent-root script/status/log 的已提交 checkpoint 继续按 legacy v1 规则验证。普通调用返回 `ROUTING_OPERATOR_ACTION_REQUIRED`，报告 exact source script/hash、目标 commit、target path templates/evidence contract/restart_policy 和 resume 语法；不得自动执行 script。operator checkpoint 的 `result_code_commit` 可以等于 plan/review baseline。

只有显式 resume 才继续；若用户还指定 checkpoint_id，它必须等于当前 HEAD 的 latest checkpoint，不能选择 stale checkpoint。用户显式要求 resume 但当前 HEAD 不存在合法 checkpoint、checkpoint provenance/class 字段不匹配、operator script hash 漂移或 checkpoint 之后又有其它 commit 时返回 `ROUTING_RESUME_INVALID`，不得猜断点或自动 retire。Web GPT + CodexPro 的显式 resume 仍必须带 `backend=web`；仅写 `resume` 不改变 Web backend 的显式选择规则。

显式 resume 时先重新执行 Stage environment preflight；validation 在 control plane **不再**重新执行本机 4090 machine/GPU preflight。通过后按原 plan/review routing dispatch，并传完整 resume context。portable operator 再传 `operator_handoff_mode/operator_gate_id/operator_restart_policy/operator_script/operator_script_sha256/target path templates/control-plane evidence directory/expected_artifacts`；legacy operator 继续传其原 absolute fields。executor 必须从 checkpoint 继续，不重做 completed_scope；operator resume 先验证已同步回来的 evidence/status/log/真实 artifact identity，默认在 1660 Ti 做 strict readback/aggregation，不能把用户口头结果或 exit code 单独视为 gate 完成，也不得在 resume 中直接替用户重跑 operator long command。

### A. 尚无 committed review

- 已有 `task_kind=implementation,status=completed,source_plan_commit=<plan_commit>` → `ROUTING_IMPLEMENTATION_ALREADY_EXECUTED`，等待 reviewer-ex。
- 无 completed E0 且 `HEAD == plan_commit` → `task_kind=implementation`，消费 plan `execution_routing`。
- 无 completed E0、`HEAD != plan_commit`，但当前 HEAD 是合法 implementation resumable checkpoint → environment 普通调用返回 `ROUTING_RESUME_AVAILABLE`，operator 普通调用返回 `ROUTING_OPERATOR_ACTION_REQUIRED`；显式 resume 后 `task_kind=implementation`，消费原 plan `execution_routing` 并传完整 resume context。
- 无 completed E0 且 `HEAD != plan_commit`，又不存在合法 current-head checkpoint → `ROUTING_INCOMPLETE_IMPLEMENTATION` / `INCOMPLETE_UNKNOWN`；不得自动重跑整份 plan。只有用户明确放弃当前半截 stage 时才提示 `$stage-lifecycle retire_incomplete stage_id/reason`，archive 后重新 planner-ex。

### B. 已有 committed review

只允许消费**最新 committed review round**。显式指定旧 round → `ROUTING_STALE_REVIEW`。

先校验：

- `conclusion=pass ⇔ repair_routing.required=false`
- `conclusion=needs_repair ⇔ repair_routing.required=true`

不一致 → `ROUTING_REPAIR_CONTRACT_INVALID`。

- required=false → `ROUTING_NO_REPAIR_REQUIRED`
- required=true：
  1. 从 Git 推导 latest `review_commit`；
  2. `HEAD == review_commit` 且尚无 matching completed repair (`source_review_round` + `source_review_commit`) → `task_kind=repair`；
  3. 已有 matching completed repair → `ROUTING_REPAIR_ALREADY_EXECUTED`；
  4. 尚无 matching completed repair，且当前 HEAD 是精确绑定该 latest review 的合法 repair resumable checkpoint → environment 普通调用返回 `ROUTING_RESUME_AVAILABLE`，operator 普通调用返回 `ROUTING_OPERATOR_ACTION_REQUIRED`；显式 resume 后 `task_kind=repair`，消费原 `repair_routing` 并传完整 resume context；
  5. 其它不可解释状态 → `ROUTING_STAGE_STATE_INVALID`。

Router 永不消费未 checkpoint review。

## Routing contract

共同字段：`version=1`、mode、complexity、parallelizability、multi_benefit、independent_workstreams、rationale。

- `complexity`: `very_simple | normal | difficult_serial`
- `parallelizability/multi_benefit`: `low | medium | high`
- SINGLE：`single_class==complexity`、independent_workstreams≥1、workstream_candidates=[]
- MULTI：single_class=null、complexity≠very_simple、parallelizability=high、multi_benefit=high、independent_workstreams≥2
- implementation MULTI candidate：唯一 id、非空 `steps`、tracked `write_scope`；steps/write_scope 跨 candidate 不重叠，candidate 数量等于 workstreams
- repair required=true：repair_issue_ids 非空唯一；MULTI candidate 使用 `issue_ids` + tracked `write_scope`，issue_ids/write_scope 不重叠且 issue_ids 并集恰好等于 repair_issue_ids
- required=false 的 null/empty schema 只产生 NO_REPAIR，不执行

错误分别使用 `ROUTING_CONTRACT_MISSING/INVALID`、`ROUTING_REPAIR_CONTRACT_MISSING/INVALID`。

**Router 不得重新计算、降级或改写 source routing。** backend 只改变执行拓扑。

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
6. single 实际无法可靠完成时返回证据；router 不自动改 MULTI。

### MULTI

1. 目标 worktree `skills/executor/SKILL.md` 必须含 v2 marker。
2. 调用 `$executor`，传 stage/provenance、`backend=local`、`source_mode=multi`、`stage_profile/control_plane_hardware/target_hardware/evidence_class/development_terminal`；validation 的普通 control-plane dispatch 不要求/传入 4090 roots，operator target roots由 portable script 在 4090 解析；repair 同样传 review provenance/issues；resume 同样传 resume checkpoint context。
3. coordinator 必须基于真实代码复核 ≥2 个独立 subplans；不足 → `ROUTING_MISMATCH`，不得假并行或退化单 worker。
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

运行时 effective mode：

- source `mode=single` → `effective_execution_mode=single`
- source `mode=multi` → `effective_execution_mode=serialized_multi`

**`backend=web + source MULTI` 的串行化是正式执行语义，不是 fallback。** sealed plan/review 仍保持 `mode=multi` 及原 candidates；router 不改成 single，也不因无法并行而报 `ROUTING_MISMATCH`。executor-web 必须按原 workstreams/repair lanes 串行覆盖全部范围后统一验收。

Web execution 完成并提交 execution report 后，本次 execution 对话必须停止在 execution 边界；**不得在同一 GPT conversation/context 中继续调用 reviewer-ex 审查自己刚完成的 execution**。下一步应在新的 Web GPT conversation 中连接同一 repo 并调用 `$reviewer-ex`；可显式提供 stage_id，若只有一个 active stage 也可省略。review 所需状态全部从 Git/sealed artifacts 重建，不依赖 execution 对话上下文。

## Execution record backend metadata

Local/Web 共用同一 `execution_record.version: 1` provenance。新 routed execution 应额外记录：

```yaml
execution_backend: local_codex       # local_codex | web_codexpro
effective_execution_mode: single    # single | multi | serialized_multi
```

这两个字段仅用于审计，不参与 reviewer/router provenance 判定；历史 record 缺失它们仍可读取。

## 输出

报告：task_kind、stage_id、plan_commit、routing source、source_mode、backend、effective_execution_mode、绝对 worktree、`control_plane_hardware`、stage profile 与 `target_hardware`；validation control-plane dispatch 不声称当前拥有 target GPU。到 operator boundary 时报告 source script/hash、target commit、target-runtime path/evidence contract 与 manual-run 要求；target GPU identity/VRAM/roots 来自 4090 `operator-evidence.json`，不从 control-plane runtime伪造。repair 再报告 review provenance/issues；resume 再报告 checkpoint 与 remaining scope；local SINGLE 报实际 model/effort。

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

- 不修改 routing/plan/review。
- router 自身不写业务代码；Web implementation 必须进入 executor-web 协议。
- 不做 review/proceedings/finalize/cleanup。
- 不重复消费已 completed source，不消费 uncommitted/stale review。
- 不静默切 backend；只有调用方选择 `backend=web` 时才使用 serialized_multi。
