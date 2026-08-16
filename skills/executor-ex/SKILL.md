---
name: executor-ex
description: Local Codex SINGLE execution protocol。仅用于 execution-router backend=local；在 stage worktree 中执行一次 implementation 或 repair，提交代码/测试后写统一 v2 execution_record。不得 subagent、不得重新 routing、不得做 review/finalization。
---

# Executor Ex

Routing compatibility marker: `execution-routing-v2`。

## 单 agent 边界

- 仅接受 router 明确传入的 `backend=local`、`source_mode=single`；其它 backend/mode 停止，不自行改路由。
- 恰好一个 execution agent；不得 spawn/subagent。
- 不重判 execution_routing/repair_routing，不改 model/effort。
- `task_kind` 必须显式为 `implementation` 或 `repair`，两个流程**互斥**；repair 完成后绝不继续跑 implementation 流程。
- 所有操作先进入 router 给定的 stage worktree，不在 main checkout 切 stage branch。

## 必需输入

共同：`stage_id`、绝对 worktree、plan path、`plan_commit`、stage branch、task_kind、`backend=local`、`source_mode=single`、`stage_profile`、`target_hardware`、`evidence_class`、`development_terminal`。validation 额外必须有 router 解析出的绝对 `artifact_root`、`hf_home`、`formal_data_root`。

- implementation：plan `execution_routing` 只作为已由 router 消费的上游决策；本 skill 按完整 plan 实施。
- repair：额外必须有 review path、整数 `source_review_round`、`review_commit`、`repair_issue_ids`；只处理这些 issue IDs。plan 只提供规格、禁止范围与总体验收约束。
- resume：额外必须有 `resume=true`、`resume_checkpoint_id`、`resume_checkpoint_commit`、`resume_from_code_commit`、`completed_scope`、`remaining_scope`；这些字段必须来自 router 对当前 HEAD checkpoint 的验证，executor 不自行挑旧 checkpoint。

Artifact：

- execution report：`ai-work/executor/{stage_id}-executor.md`
- review：`ai-work/reviewer/{stage_id}-review.md`（只读）

同一 stage report append-only，不因“重跑”或 resume 自动清空。若已有 committed execution report，本次执行开始时它必须与最新 committed 版本一致；正常完成时只在 EOF 追加新的 completed `execution_record`，环境中断时只在 EOF 追加新的 `execution_checkpoint`；不得改写旧 E0/E1/... 或旧 checkpoint 历史。

## 前置校验

1. 当前目录/branch 必须等于 plan metadata 指定 stage worktree/branch。
2. plan 必须是 plan_commit 中 seal 的同一文件。
3. implementation：report 不得已有 matching completed E0。普通 execution 开始修改前 `HEAD` 必须精确等于 `plan_commit`；resume 则必须 `HEAD == resume_checkpoint_commit`，且 checkpoint task/source/result_code_commit/completed_scope/remaining_scope 与 router 输入逐项一致。其它 HEAD 前进视为未知 baseline，停止。
4. repair：普通 execution 开始修改前 stage HEAD 必须等于 router 传入的 `review_commit`；resume 则必须 `HEAD == resume_checkpoint_commit`，且 checkpoint 精确绑定该 latest review/repair issues。若不一致停止。
5. 解析 plan 的 `stage_profile / target_hardware / evidence_class / development_terminal` 并与 router 输入逐项一致；development 必须是 GTX 1660 Ti (6GB)+engineering，且不得为 completed E0 启动真实 optimizer-based SFT/GRPO；validation 必须是 24GB GPU+real-training/numerical+terminal=false，且不得用 fixture/mock/synthetic 替代真实 gate。profile 不一致直接停止并报告 plan contract error。
6. 在任何新的业务文件修改或 commit **之前**，完整执行 plan 的 `Execution preflight`。普通 execution 若此时失败，implementation 保持 `HEAD == plan_commit`、repair 保持 `HEAD == review_commit`，不写 checkpoint/report；resume 若仍因环境失败则保持 `HEAD == resume_checkpoint_commit`，不追加重复 checkpoint。修好环境后可再次显式 resume。
7. validation：确认 router `artifact_root / hf_home / formal_data_root` 均为绝对路径且不位于 stage worktree 内；对所有真实训练/评测命令设置 `CODE_VERIFIER_ARTIFACT_ROOT=<artifact_root>`、`HF_HOME=<hf_home>`、`CODE_VERIFIER_DATA_ROOT=<formal_data_root>`，不得显式把 `--output-dir` 指回 worktree，也不得用另一套模型 cache/data root。development 不要求这些 machine roots。
8. 不修改 review、plan、proceedings、`third_party/open-r1/`。
9. stage `.venv` 默认是 lifecycle 创建的 primary-dependency overlay。若本次 implementation/repair 修改 `pyproject.toml` 或 `uv.lock`，必须在继续任何依赖相关测试前运行 `skills/stage-lifecycle/scripts/bootstrap_stage_env.py --primary-root <primary> --stage-worktree <stage> --mode full`，建立完整 stage-local pinned environment；不能让 primary overlay 掩盖新增、删除或变更的依赖。

**Transport hard guard**：开始任何业务修改前必须确认 `git ls-files .ai-bridge` 为空；否则返回 `EXECUTION_TRANSPORT_TRACKED`。`.ai-bridge/**` 只允许作为 ignored 本地 transport state。每个 code/test/config commit、environment checkpoint report commit 和 completed execution report commit 都必须显式暂存目标文件，并在 commit 前确认 staged path 不包含 `.ai-bridge/**`。

## 环境中断 checkpoint / resume

只有在已经存在本次 task 的有效部分 commits、stage 当前 clean、且失败可明确归因于**不需要 tracked 仓库修改即可修复**的环境/基础设施问题时，才允许暂停为 resumable checkpoint。源码 lint/type/test failure、tracked config/dependency bug、acceptance 逻辑失败都不是 environment interruption，必须继续正常修复代码。

环境中断时：

1. 记录当前 partial code HEAD 为 `result_code_commit`；不得把未 commit 的业务 diff 藏进 checkpoint。
2. 在 execution report EOF 追加一个新的 `execution_checkpoint`，checkpoint_id 按 C0/C1/... 单调递增；至少写：

```yaml
execution_checkpoint:
  version: 1
  stage_id: WP6-c
  checkpoint_id: C0
  task_kind: implementation
  source_plan_commit: <plan_commit>
  source_review_round: null
  source_review_commit: null
  repair_issue_ids: []
  result_code_commit: <partial code HEAD>
  interruption_class: environment
  resume_allowed: true
  failed_command: "make lint"
  blocker: "stage-local tool/runtime unavailable"
  completed_scope: ["already committed scope"]
  remaining_scope: ["resume from failed validation or remaining plan scope"]
  status: interrupted
```

repair checkpoint 填 exact review round/commit/issues。`failed_command/blocker/remaining_scope` 必须非空，completed_scope 必须只描述已经 commit 的工作。
3. 只提交 execution report：`docs: checkpoint {stage_id} execution after environment interruption`。该 docs commit 的 parent 必须等于 `result_code_commit`；checkpoint commit 不写入 record 自引用。
4. 返回 `EXECUTION_ENV_INTERRUPTED`，明确告诉用户先修环境，再显式 `$execution-router resume`；**不要**自动 retire、review 或继续执行。

resume 时只从 router 给定的 current-head checkpoint 继续：不重新实现 completed_scope，从 remaining_scope 开始；可以重新执行 plan preflight、定向测试与全局 acceptance。若再次发生同类环境故障且没有新的 partial code commit，保持当前 checkpoint 不变；若 resume 后又新增了有效 commits再遇到环境故障，可追加 C1/C2...。

## task_kind=implementation

1. 全文读 plan/spec/相关代码；resume 额外读取 latest checkpoint 与从 checkpoint 到当前 HEAD 的 Git 状态，确认 completed_scope 已提交且不重复实现。
2. 普通 development/validation stage 按 plan steps 顺序循环“实现 → 测试 → 验证 → 修正”；resume 只从 remaining_scope 继续。`DEV-CLOSEOUT` 是 verification-only：不得修改业务代码/配置/测试来制造 diff，只执行 plan preflight 与 closeout gates。
3. 普通 stage 每个可独立步骤验证后显式暂存该步骤文件并 commit；禁止 `git add -A`。`DEV-CLOSEOUT` 不要求也不允许人为制造 code commit。
4. 完整运行 plan 总体验收（至少 `make lint`、`make test` 与 stage 特有 gate）。
5. 所有代码/测试提交完成后记录当前 HEAD 为 `result_code_commit`；对 `DEV-CLOSEOUT`，要求仍 `HEAD == plan_commit`，并合法记录 `result_code_commit = plan_commit`。
6. 在 execution report 追加 E0 记录与人类可读摘要，再单独 docs commit report。E0：

```yaml
execution_record:
  version: 1
  stage_id: WP5-b
  execution_id: E0
  task_kind: implementation
  source_plan_commit: <plan_commit>
  source_review_round: null
  source_review_commit: null
  repair_issue_ids: []
  result_code_commit: <code HEAD before report docs commit>
  execution_backend: local_codex
  effective_execution_mode: single
  status: completed
```

只有所有必须验收通过才写 `status: completed`。若本次来自 resume，在 completed record 额外记录 `resumed_from_checkpoint_id` 与 `resumed_from_checkpoint_commit` 供审计；普通 execution 省略或写 null。`execution_backend/effective_execution_mode` 是审计 metadata，不参与 reviewer provenance 判定。非环境型代码失败继续在同一 execution 中修复；只有满足上面的 environment checkpoint contract 才以 `EXECUTION_ENV_INTERRUPTED` 暂停，不能伪造 completed E0。

## task_kind=repair

1. 只解析 router 指定 `repair_issue_ids` 对应的 latest committed review findings；resume 结合 checkpoint，只继续 remaining_scope 中尚未完成的 issue/验证。
2. 不把其它 minor/suggestion/plan step 自动加入 scope；人工严重级别默认规则不适用于 routed repair，也不重复修改 completed_scope 已提交的 repair。
3. 每个 issue 做最小修复；异议/无法复现记录证据，不静默忽略。
4. 运行受影响定向测试，再运行 plan 的全局 regression/acceptance。**全局测试是验证约束，不会扩大 repair scope**。
5. 修复代码/测试提交完成后记录 `result_code_commit=HEAD`。
6. 追加下一 execution_id（E1/E2/...）并 docs commit report：

```yaml
execution_record:
  version: 1
  stage_id: WP5-b
  execution_id: E1
  task_kind: repair
  source_plan_commit: <plan_commit>
  source_review_round: 1
  source_review_commit: <review_commit>
  repair_issue_ids: [R1-M1]
  result_code_commit: <code HEAD>
  execution_backend: local_codex
  effective_execution_mode: single
  status: completed
```

同一 review_commit 只能有一个 completed repair record。全部 repair_issue_ids 必须已修复或附证据处置，且 regression/acceptance 满足后才 completed。

## 报告与提交

- 普通 stage code/test commit 在先、report docs commit 在后；`DEV-CLOSEOUT` 是唯一 verification-only 例外，允许没有 code commit，直接以 `result_code_commit=plan_commit` 追加并提交 E0 report。不得为了满足提交顺序制造空改动。
- report 包含真实 preflight 命令/结果、修改文件、issue/step 映射、偏差/阻塞；validation 还必须记录绝对 persistent `artifact_root` 以及产生/消费的 checkpoint/result 路径或 identity，确保它们不在 worktree 内。
- 不自动 push；review 由 reviewer-ex；Git checkpoint/finalization 由 stage-lifecycle。

## 自检

- [ ] task_kind 只执行了一个互斥流程；repair 后没有继续 implementation；
- [ ] stage_id 与 report 路径使用完整 stage id；
- [ ] Execution preflight 在首次/恢复后的新业务修改前完成；baseline preflight 失败未产生业务 commit/report；已有 partial commits 后的 environment interruption 如需暂停，已使用合法 committed checkpoint，未强制 retire；
- [ ] validation 的 persistent artifact_root 位于 worktree 外，真实 checkpoint/result 未写入 `.worktrees/...`；
- [ ] implementation source_plan_commit 正确且没有重复 completed E0；`DEV-CLOSEOUT` 如无业务 diff，已确认 `result_code_commit == plan_commit` 且没有人为制造 code commit；
- [ ] repair source_review_round/review_commit/issues 与 router 完全一致且没有扩大 scope；
- [ ] repair 总体验收没有被误解释成“修所有 review 问题”；
- [ ] result_code_commit 在 report docs commit 之前捕获；
- [ ] `.ai-bridge/**` 保持 ignored/untracked，所有 staged/committed path 都不包含 transport state；
- [ ] completed execution_record schema 完整；
- [ ] 未修改 plan/review/proceedings/third_party；未 push。
