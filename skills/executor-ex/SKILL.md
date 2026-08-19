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

共同：`stage_id`、绝对 worktree、plan path、`plan_commit`、stage branch、task_kind、`backend=local`、`source_mode=single`、`stage_profile`、`control_plane_hardware`、`target_hardware`、`evidence_class`、`development_terminal`。`control_plane_hardware` 固定 GTX 1660 Ti；validation 普通 dispatch 不要求 router 提供 4090 `artifact_root/hf_home/formal_data_root`，target roots 由 portable operator script 在 4090 runtime 解析。

- implementation：plan `execution_routing` 只作为已由 router 消费的上游决策；本 skill 按完整 plan 实施。
- repair：额外必须有 review path、整数 `source_review_round`、`review_commit`、`repair_issue_ids`；只处理这些 issue IDs。plan 只提供规格、禁止范围与总体验收约束。
- resume：额外必须有 `resume=true`、`resume_checkpoint_id`、`resume_checkpoint_commit`、`resume_from_code_commit`、`resume_interruption_class`、`completed_scope`、`remaining_scope`；这些字段必须来自 router 对当前 HEAD checkpoint 的验证，executor 不自行挑旧 checkpoint。若 `resume_interruption_class=operator`，还必须有 router 验证过的 `operator_gate_id`、`operator_restart_policy`、`operator_script`、`operator_script_sha256`、`operator_status_file`、`operator_log_file`、`expected_artifacts`。

Artifact：

- execution report：`ai-work/executor/{stage_id}-executor.md`
- review：`ai-work/reviewer/{stage_id}-review.md`（只读）

同一 stage report append-only，不因“重跑”或 resume 自动清空。若已有 committed execution report，本次执行开始时它必须与最新 committed 版本一致；正常完成时只在 EOF 追加新的 completed `execution_record`，environment/operator 合法暂停时只在 EOF 追加新的 `execution_checkpoint`；不得改写旧 E0/E1/... 或旧 checkpoint 历史。

## 前置校验

1. 当前目录/branch 必须等于 plan metadata 指定 stage worktree/branch。
2. plan 必须是 plan_commit 中 seal 的同一文件。
3. implementation：report 不得已有 matching completed E0。普通 execution 开始修改前 `HEAD` 必须精确等于 `plan_commit`；resume 则必须 `HEAD == resume_checkpoint_commit`，且 checkpoint task/source/result_code_commit/completed_scope/remaining_scope 与 router 输入逐项一致。其它 HEAD 前进视为未知 baseline，停止。
4. repair：普通 execution 开始修改前 stage HEAD 必须等于 router 传入的 `review_commit`；resume 则必须 `HEAD == resume_checkpoint_commit`，且 checkpoint 精确绑定该 latest review/repair issues。若不一致停止。
5. 解析 plan 的 `stage_profile / control_plane_hardware / target_hardware / evidence_class / development_terminal` 并与 router 输入逐项一致；`control_plane_hardware` 固定 GTX 1660 Ti。development target=GTX 1660 Ti + engineering；validation target=24GB GPU + real-training/numerical + terminal=false，但这**不要求当前 executor 本机是 4090**。当前 executor 只完成 control-plane scope 与 portable handoff；fixture/mock/synthetic 仍不得替代真实 validation gate。
6. 在任何新的业务文件修改或 commit **之前**，完整执行 plan 的 `Execution preflight`。普通 execution 若此时失败，implementation 保持 `HEAD == plan_commit`、repair 保持 `HEAD == review_commit`，不写 checkpoint/report；resume 若仍因环境失败则保持 `HEAD == resume_checkpoint_commit`，不追加重复 checkpoint。修好环境后可再次显式 resume。
7. validation：control-plane executor 不解析/校验 4090 machine roots，也不直接运行真实 target-GPU training/evaluation。sealed 命令只使用 `$CODE_VERIFIER_ARTIFACT_ROOT/$HF_HOME/$CODE_VERIFIER_DATA_ROOT` target-runtime templates；portable `run.sh` 在 4090 读取 machine record 后设置这些变量，并拒绝把真实 checkpoint/metrics 写回 worktree。
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

## Operator terminal gate / resume

仅当 sealed `stage_profile=validation` plan 含合法 `operator_terminal_execution` gate 时使用。正式 Base/B/C/D 全量评测、optimizer-based SFT/GRPO 或 plan 明确标记的其它长任务**不得由 executor 自己启动**。

到达某个 operator gate 时：

1. 先完成并 commit 该 gate 前所有 tracked code/config/test，完整通过 **control-plane** Execution preflight、lint/unit/CPU/non-4090 integration/Piston 与其它可在 1660 Ti 完成的 short validation；不要为了准备 handoff 去连接 4090。stage 必须 clean。解析 `restart_policy=exact_rerun|trainer_checkpoint`，SFT/GRPO 必须为 `trainer_checkpoint`。若 gate 前无需 tracked 修改，implementation 允许 `result_code_commit=plan_commit`，repair 允许 `result_code_commit=review_commit`。
2. 预分配 `checkpoint_id=Cn`，在 ignored `.ai-bridge/operator-handoffs/{stage_id}/{plan_commit}/{gate_id}/{checkpoint_id}/` 唯一目录生成 secret-free immutable **portable** `run.sh` 与 control-plane evidence 接收目录；目录非空则停止而非覆盖。script 固定 stage/gate/checkpoint/result provenance 和 target-runtime path templates，但不得硬编码 1660 Ti primary/stage 绝对路径，也不得假设 4090 roots 已在 control plane 挂载。它通过 `CODE_VERIFIER_TARGET_REPO`（或从运行 cwd 安全解析）定位 4090 checkout，并在目标端验证 exact checkpoint commit/report parent、working tree clean、script SHA、target-local `.ai-bridge/validation-machine.json`、READY/Piston identity、>=22528 MiB CUDA、persistent roots/model/data/cache/storage，取得排他锁后才执行 long command。若 gate 需要 Piston，先调用/等价验证 `/root/sj-tmp/open-r1-code-verifier-outputs/machine/ensure-piston-1660ti-tunnel.sh`，并确认 `127.0.0.1:2000` exact runtime 来自唯一 host `1660ti-wsl`。
3. target script 的 attempt 状态抗 stale/concurrent：获得锁后清旧 status/temp，append UTC attempt-start；target-start preflight失败则原子写非零 status且绝不进入长命令；长命令必须显式捕获自身 rc，pipeline 使用 `pipefail`/正确 `PIPESTATUS`，最终 append attempt-end 并 atomic status rename。完成/失败后都生成 secret-free `operator-evidence.json`，至少绑定 checkpoint commit、script SHA、target machine/GPU identity、resolved roots、Piston identity（如适用）、status/log、formal run identity、expected-artifact inventory/hash/size/selected summaries。
4. `restart_policy=exact_rerun` 与 `trainer_checkpoint` 的既有 same-checkpoint resume、latest valid Trainer checkpoint、strict loader、quarantine/no-overwrite 语义全部保留；环境修复后用户重复运行同一 hash-matching script，不为补 resume 参数改变 stage HEAD。
5. 计算 `run.sh` SHA256，在 execution report EOF 追加 portable operator checkpoint：公共 provenance + `result_code_commit` + `interruption_class: operator` + `resume_allowed: true` + `operator_handoff_mode: portable_target` + `operator_gate_id` + control-plane-local `operator_script` + `operator_script_sha256` + target status/log/evidence templates + control-plane evidence directory + `expected_artifacts` + scopes + `status: awaiting_operator`。只提交 execution report docs commit，然后返回 `EXECUTION_OPERATOR_ACTION_REQUIRED`，报告 exact target commit、source script/hash、用户在 4090 fetch/checkout/copy/hash-check/manual-run 的步骤以及 evidence 回传位置；**立即停止，不运行 script，不进入 reviewer/finalize**。

operator resume 只接受 router 已验证的 current-head operator checkpoint：

1. portable operator resume 在 1660 Ti 重新核验 source script SHA256、restart policy 与已同步回来的 `operator-evidence.json`/status/log/manifest/metrics；从 evidence 校验 target machine/GPU identity、resolved roots、Piston identity（如适用）、formal run/checkpoint inventory 与 selected artifact hashes。**不要求 control-plane 本机挂载 4090 roots 或拥有 24GB GPU**。legacy checkpoint 继续按其原 absolute-root readback 规则。用户口头“跑完了”或 status=0 单独都不是完成证据；evidence/status 缺失表示该 attempt 未形成可靠终态。
2. 若 artifact 满足 gate 的真实 acceptance，则把该 gate 计入 completed_scope，继续 remaining_scope；若后面还有 operator gate，按同一协议使用新的 checkpoint-id/operator namespace；只有所有 gates 与总体验收都通过后才可写 completed E0/En。reviewer 后续只能验证这些 artifacts，不要求重跑 long gate。
3. 若只是 tunnel/GPU/cache 等无需 tracked 修改的环境故障：`exact_rerun` 与 `trainer_checkpoint` 都优先保持当前 operator checkpoint/HEAD 不变，让用户在修复环境后再次运行**同一 immutable script**；后者由 script 自动选择 latest valid Trainer checkpoint，然后再次显式 resume。不得为了添加 `--resume-from-checkpoint` 先提交新的 docs checkpoint，因为训练 resume 的 `project_commit` identity 会因此漂移。
4. 若已有 canonical run 但没有合法 Trainer checkpoint，或 operator run 暴露 tracked source/config/test bug：先停止，不覆盖旧 run。若需要 tracked 修复，做最小修复并 commit、运行定向/回归短测试；随后把旧 incomplete canonical run 移动到 persistent artifact root 下含 stage/gate/checkpoint/UTC identity 的唯一 quarantine 路径，并在 execution report 记录 original path、quarantine path、原因与旧 run status。完成 quarantine 后才生成新的 Cn operator script/checkpoint fresh restart。旧 checkpoint/log/run 全部保留审计历史。

## task_kind=implementation

1. 全文读 plan/spec/相关代码；resume 额外读取 latest checkpoint 与从 checkpoint 到当前 HEAD 的 Git 状态，确认 completed_scope 已提交且不重复实现。
2. 普通 development/validation stage 按 plan steps 顺序循环“实现 → 测试 → 验证 → 修正”；resume 只从 remaining_scope 继续。`DEV-CLOSEOUT` 是 verification-only：不得修改业务代码/配置/测试来制造 diff，只执行 plan preflight 与 closeout gates。若遇到 plan 的 operator terminal gate，执行到 gate 前置条件后转入上面的 Operator terminal protocol，禁止直接运行长命令。
3. 普通 stage 每个可独立步骤验证后显式暂存该步骤文件并 commit；禁止 `git add -A`。`DEV-CLOSEOUT` 不要求也不允许人为制造 code commit。
4. 完整运行 plan 总体验收中由 executor 负责的短时 gate（至少 `make lint`、`make test` 与 stage 指定的短测试）；operator long gate 只在 resume 对真实 artifacts 验收，不由 executor 首次调用执行。
5. 只有所有 operator gates 已经通过合法 resume 验收后，才记录当前 HEAD 为最终 `result_code_commit`；对 `DEV-CLOSEOUT`，要求仍 `HEAD == plan_commit`，并合法记录 `result_code_commit = plan_commit`。
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
4. 运行受影响定向测试，再运行 plan 中 executor-owned 的全局 regression/acceptance。**全局测试是验证约束，不会扩大 repair scope**。若 reviewer/plan 要求重跑受影响的 operator long gate，按 Operator terminal protocol 生成新的 Cn checkpoint/script，禁止 executor 直接运行。
5. 只有所有需要重跑的 operator gates 已通过合法 resume artifact 验收后，才记录最终 `result_code_commit=HEAD`。
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
- [ ] validation 若含 `operator_terminal_execution`，长任务未由 executor 启动；restart_policy 正确，operator namespace 不碰撞，script 有 Git/primary-root/persistent-root/lock guard 与原子 status/append-only log；trainer_checkpoint 可由同一 script 恢复 latest same-run checkpoint，无 checkpoint/identity drift 时旧 run 已 quarantine 而非删除；只有显式 resume 对真实 artifacts 验收后才继续 completed E0/En；
- [ ] validation 的正式 checkpoint/result 只写 target persistent artifact_root；control plane 不要求挂载该 root，portable operator evidence 足以跨机器核验，真实 checkpoint/result 未写入 `.worktrees/...`；
- [ ] implementation source_plan_commit 正确且没有重复 completed E0；`DEV-CLOSEOUT` 如无业务 diff，已确认 `result_code_commit == plan_commit` 且没有人为制造 code commit；
- [ ] repair source_review_round/review_commit/issues 与 router 完全一致且没有扩大 scope；
- [ ] repair 总体验收没有被误解释成“修所有 review 问题”；
- [ ] result_code_commit 在 report docs commit 之前捕获；
- [ ] `.ai-bridge/**` 保持 ignored/untracked，所有 staged/committed path 都不包含 transport state；
- [ ] completed execution_record schema 完整；
- [ ] 未修改 plan/review/proceedings/third_party；未 push。
