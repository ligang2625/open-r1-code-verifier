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

共同：`stage_id`、绝对 worktree、plan path、`plan_commit`、stage branch、task_kind、`backend=local`、`source_mode=single`、`stage_profile`、`control_plane_hardware`、`target_hardware`、`evidence_class`、`development_terminal`。`control_plane_hardware` 固定 GTX 1660 Ti；validation 普通 dispatch 不要求 router 提供 4090 `artifact_root/hf_home/formal_data_root`，target roots 由 portable operator script 在 4090 runtime 解析。router 若对已封存旧 stage 使用迁移兼容，还会传 `legacy_control_plane_default=true` 与 exact `workflow_runtime_commit`；executor 只能消费这两个显式字段，不能自行给缺失字段补默认值。

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
5. 解析 plan 的 `stage_profile / control_plane_hardware / target_hardware / evidence_class / development_terminal` 并与 router 输入逐项一致；`control_plane_hardware` 固定 GTX 1660 Ti。development target=GTX 1660 Ti + engineering；validation 固定 real-training/numerical+terminal=false，但 target 可为 GTX 1660 Ti（formal-evidence-only analysis）或 24GB GPU（含新的 target-GPU gate）。target=24GB 时所有 24GB acceptance 都必须由 operator block覆盖；当前 executor 本机仍只做 control-plane scope，不把 synthetic/mock 当真实 validation evidence。若 plan 缺少 `control_plane_hardware`，只有 router 已传 `legacy_control_plane_default=true` 且 execution/review provenance 证明这是迁移前已进入执行/review 的 sealed stage 时才运行时解释为 GTX 1660 Ti；不得改写 plan，也不得扩展到纯 PLANNED stage。
6. 在任何新的业务文件修改或 commit **之前**执行 plan 的 `Execution preflight`。正常新 plan 必须完整执行。对 `legacy_control_plane_default=true` 的旧 sealed stage，按当前硬件职责重新分类旧 preflight：control-plane 可执行且与本次 task 相关的 Git/transport/stage-env/Piston/data/readback/短测试必须重跑；旧 plan 中仅用于 4090 target-start 的 CUDA/VRAM/BF16/target machine record/target roots/target-local model-cache 等检查不得在 1660 Ti 强制重跑，只能由已 committed 的 target/operator evidence 保持历史证明，并且仅当本次 repair 真正要求新的 target-GPU execution 时才重新进入 operator boundary。此兼容只移动检查地点，不降低 formal evidence/identity 要求。普通 execution 若此时失败，implementation 保持 `HEAD == plan_commit`、repair 保持 `HEAD == review_commit`，不写 checkpoint/report；resume 若仍因环境失败则保持 `HEAD == resume_checkpoint_commit`，不追加重复 checkpoint。修好环境后可再次显式 resume。
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

仅当 sealed `stage_profile=validation,target_hardware=24GB GPU` plan 含合法 `operator_terminal_execution` gate 时使用。该 block 覆盖全部 24GB acceptance gates，包括短时 4090-only smoke；executor 不直接启动任何 target-GPU command。

到达某个 operator gate 时：

1. 先完成并 commit gate 前全部 tracked code/config/test，完成 control-plane preflight、lint/unit/CPU/non-4090 integration/Piston 与其它 1660 Ti 可做的验证；stage 必须 clean。解析 restart policy，SFT/GRPO=`trainer_checkpoint`。若 gate 前无 tracked 修改，允许 result_code_commit 等于 plan/review baseline。
2. 预分配 `checkpoint_id=Cn`，生成唯一 tracked、secret-free、immutable `ai-work/executor/operator/{stage_id}/{gate_id}/{checkpoint_id}/run.sh` 与 ignored control-plane evidence 接收目录。script 使用 target-runtime templates，不硬编码 1660 Ti 路径。它在 4090 验证 current HEAD/parent/latest checkpoint/script SHA、working tree clean、target-local machine record、>=22528 MiB GPU、persistent roots/model/data/cache/storage；需要 Piston 时只接受 `1660ti-wsl` tunnel helper + exact loopback runtime。
3. script 获锁后执行 target-start preflight；失败则原子写非零状态并生成 evidence，不进入 target command。target command 必须可靠捕获自身 rc。若 `command_rc=0`，立即运行 sealed post-run acceptance（strict completed-run/checkpoint loader、metrics/schema/artifact identity 等）；只有 `postcheck_rc=0` 才 `gate_status=passed`。最终 status 原子写、log append-only，任何失败都保留 evidence并非零退出。
4. 每次 attempt 生成 versioned secret-free `operator-evidence.json`，至少绑定 stage/plan/operator-checkpoint/result-code/checkpoint/gate/script path+SHA、machine-record SHA、GPU/roots/Piston、timestamps、`command_rc/postcheck_rc/gate_status`、formal run identity 与 expected-artifact inventory（identity/metadata files SHA256）。既有 exact-rerun/trainer-checkpoint/latest-valid-checkpoint/quarantine/no-overwrite 语义不变。
5. 计算 script SHA，在 execution report append portable operator checkpoint，显式记录 `operator_handoff_mode: portable_target`、repo-relative tracked script path/SHA、target templates/evidence directory/expected artifacts/scopes/status。一个 checkpoint commit **只**提交 execution report + 这一份新 script；parent=result_code_commit。返回 `EXECUTION_OPERATOR_ACTION_REQUIRED`，明确 workflow 不自动 push：用户必须先通过 Git 让 exact checkpoint commit 在 4090 可达，再 checkout/detach 到 exact commit、确认 clean、重算 SHA、直接运行 tracked script。立即停止。

Active-stage migration repair 另允许 `operator_handoff_mode: control_plane_manual`，但只在 router 已传 `legacy_control_plane_default=true` + exact `workflow_runtime_commit`、`task_kind=repair`、latest reviewer 明确要求补迁移前 operator provenance 且命令不需要新的 24GB GPU execution 时。它仍使用本 checkpoint 新增的 tracked immutable script 与“report + 单一 script”commit，但 script 在 1660 Ti 手工运行，status/log/evidence 写 worktree 外 persistent namespace，并严格绑定 frozen generation/data/verifier/Open-R1/dependency/Piston/formal namespace、fresh non-overwriting repair output、command/postcheck/gate status；不得用于 implementation/新 plan/普通 offload，也不得覆盖历史 formal evidence。

operator resume 只接受 router 已验证的 current-head checkpoint：

1. 在 1660 Ti 计算 evidence SHA256。`portable_target` 验证 evidence version/所有 provenance fields、tracked script SHA、machine/GPU/roots/Piston（如 required）、`command_rc=0`、`postcheck_rc=0`、`gate_status=passed`、formal run/expected artifact inventory，并对同步回来的 identity/metadata files 重算 SHA。`control_plane_manual` 验证 plan/review/workflow-runtime/checkpoint/script、frozen generation/data/verifier/Open-R1/dependency/Piston/formal namespace、fresh repair output inventory及同样的 command/postcheck/gate status，不要求/接受伪造的 4090 machine/GPU fields。legacy checkpoint 继续按旧 absolute-root规则。
2. evidence/postcheck 足以证明 gate acceptance 时才加入 completed_scope；若 required large-artifact property 尚未被证明，保持 checkpoint 不变并要求短时只读 4090 check，不能猜 PASS。所有 gates/acceptance 通过后，completed execution record 必须记录每个 operator gate 的 evidence SHA256。
3. 纯 target 环境故障保持同一 checkpoint/HEAD，用户修复后重跑同一 tracked script；trainer checkpoint 自动选 latest valid same-run checkpoint，不为 resume flag 改 HEAD。
4. 若无合法 Trainer checkpoint或真实运行暴露 tracked bug，保留旧 run；必要修复在 control plane commit/test，并在 target persistent root quarantine旧 incomplete run 后生成新的 operator checkpoint/script。

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
  workflow_runtime_commit: <required for active-stage workflow migration; otherwise omit>
  legacy_control_plane_default: true  # required with workflow_runtime_commit; otherwise omit
  status: completed
```

只有所有必须验收通过才写 `status: completed`。active-stage workflow migration 时 `workflow_runtime_commit` 与 `legacy_control_plane_default=true` 必须成对记录，绑定本轮实际加载的 maintenance runtime；普通 stage 省略二者。若本次来自 resume，在 completed record 额外记录 `resumed_from_checkpoint_id` 与 `resumed_from_checkpoint_commit`；若消费 portable operator evidence，还必须记录每个完成 gate 的 `operator_evidence_sha256`（以及 gate/checkpoint id），把 control-plane 收到的 evidence byte identity 纳入 Git provenance。普通 execution 省略这些字段。`execution_backend/effective_execution_mode` 是审计 metadata，不参与 reviewer provenance 判定。非环境型代码失败继续在同一 execution 中修复；只有满足 environment checkpoint contract 才以 `EXECUTION_ENV_INTERRUPTED` 暂停，不能伪造 completed E0。

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
  workflow_runtime_commit: <required for active-stage workflow migration; otherwise omit>
  legacy_control_plane_default: true  # required with workflow_runtime_commit; otherwise omit
  status: completed
```

同一 review_commit 只能有一个 completed repair record。全部 repair_issue_ids 必须已修复或附证据处置，且 regression/acceptance 满足后才 completed。

## 报告与提交

- 普通 stage code/test commit 在先、report docs commit 在后；`DEV-CLOSEOUT` 是唯一 verification-only 例外，允许没有 code commit，直接以 `result_code_commit=plan_commit` 追加并提交 E0 report。不得为了满足提交顺序制造空改动。
- report 包含真实 control-plane preflight/测试、修改文件、issue/step 映射、偏差/阻塞。validation target=24GB 时，operator checkpoint 先记录 target-runtime path templates；只有在 resume 消费 target evidence 后，completed report 才记录 evidence 中解析出的 persistent roots/formal run/checkpoint identities 与 `operator_evidence_sha256`。control plane 不得为了写 report 假造或预先要求一个本机可见的 4090 absolute root。
- 不自动 push；review 由 reviewer-ex；Git checkpoint/finalization 由 stage-lifecycle。

## 自检

- [ ] task_kind 只执行了一个互斥流程；repair 后没有继续 implementation；
- [ ] stage_id 与 report 路径使用完整 stage id；
- [ ] Execution preflight 在首次/恢复后的新业务修改前完成；baseline preflight 失败未产生业务 commit/report；已有 partial commits 后的 environment interruption 如需暂停，已使用合法 committed checkpoint，未强制 retire；
- [ ] validation target=24GB 时全部 24GB gates（短/长）均由 operator boundary 承担；executor 未启动 target command；tracked script/commit-parent/diff/SHA guard 正确，target preflight + mandatory postcheck + atomic status/append-only log 完整；trainer checkpoint/quarantine 语义保持；resume 已验证 versioned evidence、command/postcheck/gate_status 与 evidence SHA，并把成功 gate 的 evidence SHA 写入 completed record；
- [ ] validation 的正式 checkpoint/result 只写 target persistent artifact_root；control plane 不要求挂载该 root，portable operator evidence 足以跨机器核验，真实 checkpoint/result 未写入 `.worktrees/...`；
- [ ] implementation source_plan_commit 正确且没有重复 completed E0；`DEV-CLOSEOUT` 如无业务 diff，已确认 `result_code_commit == plan_commit` 且没有人为制造 code commit；
- [ ] repair source_review_round/review_commit/issues 与 router 完全一致且没有扩大 scope；
- [ ] repair 总体验收没有被误解释成“修所有 review 问题”；
- [ ] result_code_commit 在 report docs commit 之前捕获；
- [ ] `.ai-bridge/**` 保持 ignored/untracked，所有 staged/committed path 都不包含 transport state；
- [ ] completed execution_record schema 完整；
- [ ] 未修改 plan/review/proceedings/third_party；未 push。
