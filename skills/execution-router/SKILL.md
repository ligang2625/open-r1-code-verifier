---
name: execution-router
description: Routed execution 控制面。消费 stage-lifecycle seal 的 plan execution_routing 或 checkpoint 的最新 review repair_routing，结合 Git/provenance 状态阻止重复、stale 或 incomplete execution，并按运行时 backend=local|web 选择 Local Codex 或当前 Web GPT + CodexPro 执行。只做状态推导与执行调度，不自行重判 routing、不做 review/finalization。
---

# Execution Router

Routing compatibility marker: `execution-routing-v2`。

## 入口与 backend

标准入口是在**主仓库 root checkout** 调用。若从 linked stage worktree 调用，先解析 primary root，再基于 Git worktree 状态定位目标 stage；router 自己不在 primary checkout `git switch` stage branch。

每次 execution 都有一个**运行时** backend：

- `backend=local`：SINGLE → `executor-ex`；MULTI → `executor`。只允许在 **Local Codex runtime** 且具备 execution-agent 调用能力时使用；Local Codex 中未显式指定 backend 时默认 local。
- `backend=web`：由当前 Web GPT + CodexPro 在同一对话中继续执行 `executor-web`；不得创建或调用 Local Codex execution agent。Web 环境必须显式指定 `backend=web`。

backend 不是 plan/review routing 字段，不写回 sealed plan/review，不影响 plan 的 `mode/complexity/parallelizability/multi_benefit`，也不参与 provenance 合法性判断。implementation 与每轮 repair 可以分别选择不同 backend。

Router 还接受一个**显式恢复意图**：`resume`（例如 `$execution-router resume` 或等价明确指令）。`resume` 不是 routing 字段，也不能选择任意历史 commit；它只允许消费**当前 HEAD 对应的最新合法 environment interruption checkpoint**。普通调用遇到可恢复 checkpoint 时只返回 `ROUTING_RESUME_AVAILABLE`，不自动续跑；用户明确 resume 后才 dispatch。resume 继续消费原 plan/review 的 sealed routing，不重新规划、不改变 mode/backend。

Web/CodexPro 环境请求 `backend=local`（或未指定 backend）时返回 `ROUTING_LOCAL_BACKEND_REQUIRES_LOCAL_CODEX`；Local Codex 缺少 execution-agent 能力时同样停止。若显式 `backend=web` 但当前环境没有可写 CodexPro workspace、Git 或所需验证命令能力，返回 `ROUTING_WEB_BACKEND_UNAVAILABLE`。两种情况都不得自动切 backend。

## Stage 定位

必须定位唯一 `stage_id` 与 stage worktree。优先使用调用方显式 stage_id；未给时，尚未合并 stage worktree 必须**恰好一个候选**：

- 0 → `ROUTING_PLAN_MISSING`
- >1 → `ROUTING_PLAN_AMBIGUOUS`

禁止按最大编号、mtime、最近创建等猜测。

Open-R1 artifact：

- plan：`ai-work/planner/{stage_id}-plan.md`
- execution：`ai-work/executor/{stage_id}-executor.md`
- review：`ai-work/reviewer/{stage_id}-review.md`

plan 必须已经由 `stage-lifecycle bootstrap_plan` commit；router 通过 Git 历史推导 `plan_commit`。未提交、dirty 或 seal 后又修改 plan → `ROUTING_PLAN_NOT_SEALED`。同时解析 plan 的 `stage_profile / target_hardware / evidence_class / development_terminal`；profile 映射不合法时返回 `ROUTING_PLAN_PROFILE_INVALID`。

## Validation machine/artifact preflight

只对 `stage_profile=validation` 执行，并且必须发生在 dispatch/executor 创建之前：

1. 使用项目 `.venv` 的 pinned PyTorch runtime 检查 `torch.cuda.is_available()`，并通过 `torch.cuda.get_device_properties(0).total_memory` / `torch.cuda.get_device_name(0)` 读取目标 GPU。CUDA 不可用、torch/CUDA runtime 无法导入或总显存低于 `22528 MiB`（22 GiB）时返回 `ROUTING_VALIDATION_HARDWARE_UNAVAILABLE`。这是用于识别 24GB-class training machine 的简单 common-case dispatch guard；训练入口原有 `>=20 GiB` fail-closed 继续作为第二层运行时保护，不做自动 GPU 调度。若 `nvidia-smi` 可用，可额外记录其 identity/VRAM 作为审计信息，但不得把它作为唯一硬件探测方式。
2. 解析持久 artifact root：若环境变量 `CODE_VERIFIER_ARTIFACT_ROOT` 非空，使用其展开后的绝对路径；否则使用 `<primary_repo_root>/outputs`。最终路径必须是绝对路径，且不得位于目标 stage worktree 内。
3. 创建 artifact root（若不存在）并做一次临时文件 create/delete writable probe；失败返回 `ROUTING_VALIDATION_ARTIFACT_ROOT_UNAVAILABLE`。该目录是 ignored/non-Git 的真实实验持久存储，不随 stage worktree finalize 删除。
4. 将解析后的绝对 `artifact_root` 作为 dispatch 输入传给 executor；validation executor 必须对训练/评测命令设置 `CODE_VERIFIER_ARTIFACT_ROOT=<artifact_root>`，并拒绝把真实 checkpoint/metrics 写入 stage worktree。

Development stage 不运行上述 24GB preflight；其 plan-specific Piston/import/model-cache/CUDA prerequisites 由 plan 的 Execution preflight 在首次业务修改/commit 前执行。

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

### Resumable environment checkpoint

Router 只把 execution report 中**最新 committed**、且提交该 checkpoint 的 docs commit 恰好等于当前 stage HEAD 的 `execution_checkpoint` 视为 resumable。必须同时满足：

- `version: 1`、非空唯一 `checkpoint_id`、`status: interrupted`、`interruption_class: environment`、`resume_allowed: true`；
- `stage_id/task_kind/source_plan_commit` 与当前 stage 精确一致；implementation 的 `source_review_round/source_review_commit` 必须为 null、`repair_issue_ids=[]`；repair 必须精确绑定 latest committed review round/commit/issues；
- `result_code_commit` 必须是提交 checkpoint 前的 parent HEAD，checkpoint docs commit 只允许改 execution report；
- `failed_command`、`blocker`、`remaining_scope` 非空；`completed_scope` 记录已经 commit、恢复时不得重复实现的范围；
- 当前不存在同一 source 的 completed execution，也不存在 checkpoint 之后的其它 commit。

普通 router 调用命中该状态返回 `ROUTING_RESUME_AVAILABLE`，报告 checkpoint_id、checkpoint commit、result_code_commit、failed_command/blocker/remaining_scope，并提示用户修复环境后显式 `$execution-router resume`。只有显式 resume 才继续；若用户还指定 checkpoint_id，它必须等于当前 HEAD 的 latest checkpoint，不能选择 stale checkpoint。用户显式要求 resume 但当前 HEAD 不存在合法 checkpoint、checkpoint provenance 不匹配或环境中断之后又有其它 commit 时返回 `ROUTING_RESUME_INVALID`，不得猜断点或自动 retire。

显式 resume 时先重新执行 Stage environment preflight；通过后按原 plan/review routing dispatch，并额外传 `resume=true`、`resume_checkpoint_id`、`resume_checkpoint_commit`、`resume_from_code_commit`、`completed_scope`、`remaining_scope`。executor 必须从 checkpoint 继续，不重做 completed_scope；允许重新跑 preflight、定向测试和全局 acceptance，因为这些是验证而不是重复实现。

### A. 尚无 committed review

- 已有 `task_kind=implementation,status=completed,source_plan_commit=<plan_commit>` → `ROUTING_IMPLEMENTATION_ALREADY_EXECUTED`，等待 reviewer-ex。
- 无 completed E0 且 `HEAD == plan_commit` → `task_kind=implementation`，消费 plan `execution_routing`。
- 无 completed E0、`HEAD != plan_commit`，但当前 HEAD 是合法 implementation environment checkpoint → 普通调用返回 `ROUTING_RESUME_AVAILABLE`；显式 resume 后 `task_kind=implementation`，消费原 plan `execution_routing` 并传 resume context。
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
  4. 尚无 matching completed repair，且当前 HEAD 是精确绑定该 latest review 的合法 repair environment checkpoint → 普通调用返回 `ROUTING_RESUME_AVAILABLE`；显式 resume 后 `task_kind=repair`，消费原 `repair_routing` 并传 resume context；
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
3. 传：stage_id、绝对 worktree、stage branch、plan path、plan_commit、task_kind、`backend=local`、`source_mode=single`、single_class，以及 `stage_profile/target_hardware/evidence_class/development_terminal`；validation 再传绝对 `artifact_root`。
4. repair 再传 review path、source_review_round、review_commit、repair_issue_ids；resume 再传 `resume=true`、resume_checkpoint_id/commit、resume_from_code_commit、completed_scope、remaining_scope。
5. agent 必须先进入 stage worktree；不得 subagent。
6. single 实际无法可靠完成时返回证据；router 不自动改 MULTI。

### MULTI

1. 目标 worktree `skills/executor/SKILL.md` 必须含 v2 marker。
2. 调用 `$executor`，传 stage/provenance、`backend=local`、`source_mode=multi`、`stage_profile/target_hardware/evidence_class/development_terminal`；validation 再传绝对 `artifact_root`；repair 同样传 review provenance/issues；resume 同样传 resume checkpoint context。
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
- `stage_profile/target_hardware/evidence_class/development_terminal`；validation 另带绝对 `artifact_root`
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

报告：task_kind、stage_id、plan_commit、routing source、source_mode、backend、effective_execution_mode、绝对 worktree、stage profile；validation 额外报告实际 GPU identity/total VRAM 与绝对 persistent `artifact_root`；repair 再报告 review_round/review_commit/repair_issue_ids；resume 再报告 resume_checkpoint_id/commit、resume_from_code_commit 与 remaining_scope；local SINGLE 报实际 model/effort。

## 关键错误

- `ROUTING_PLAN_MISSING` / `ROUTING_PLAN_AMBIGUOUS` / `ROUTING_PLAN_NOT_SEALED` / `ROUTING_PLAN_PROFILE_INVALID`
- `ROUTING_VALIDATION_HARDWARE_UNAVAILABLE` / `ROUTING_VALIDATION_ARTIFACT_ROOT_UNAVAILABLE`
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
- `ROUTING_LOCAL_BACKEND_REQUIRES_LOCAL_CODEX`
- `ROUTING_WEB_BACKEND_UNAVAILABLE`

## 禁止事项

- 不修改 routing/plan/review。
- router 自身不写业务代码；Web implementation 必须进入 executor-web 协议。
- 不做 review/proceedings/finalize/cleanup。
- 不重复消费已 completed source，不消费 uncommitted/stale review。
- 不静默切 backend；只有调用方选择 `backend=web` 时才使用 serialized_multi。
