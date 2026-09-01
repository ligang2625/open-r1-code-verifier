---
name: executor-ex
description: Local Codex SINGLE execution protocol。默认按 router/sealed plan 执行，但允许用户明确覆盖实现方式、scope、顺序或 routing，并由 LLM 根据当前 Git/测试状态判断 continuation/resume。保留正确 stage、operator evidence、transport 和真实验收等必要边界，不把普通 commit/SHA 漂移当作机械阻塞。
---

# Executor Ex

Routing compatibility marker: `execution-routing-v2`。

## 单 agent 边界

- 默认接受 router 的 `backend=local`、`source_mode=single`；backend 必须符合当前 runtime capability，但 source mode 可在用户明确指令或真实实现需要时作为 effective routing 调整依据，而不是不可突破的形式约束。
- 恰好一个 execution agent；不得 spawn/subagent。若需要真正 MULTI，可交回 router/合适 executor；若单 agent 仍能可靠完成，则不因 sealed mode 不一致机械停止。
- 用户未覆盖时遵循 execution_routing/repair_routing；用户明确指定新的实现/scope/顺序时以用户指令为准，并记录 effective routing。
- `task_kind` 必须显式为 `implementation` 或 `repair`，两个流程**互斥**；repair 完成后绝不继续跑 implementation 流程。
- 所有操作先进入 router 给定的 stage worktree，不在 main checkout 切 stage branch。

## 必需输入

router 应尽量提供 `stage_id`、绝对 worktree、plan path/plan_commit、stage branch、task_kind、actual backend、source/effective routing、profile/hardware/evidence metadata，以及 repair/resume context。`stage_id`、正确 worktree、task_kind 与 actual backend 是必要身份；plan/review/workflow-runtime/checkpoint commits 是审计 anchors，可从 repo state 恢复，不要求 exact SHA。

- implementation：用户未覆盖时按完整 plan/default routing 实施；用户明确改变实现/scope/order时按 effective contract执行并记录。
- repair：review path/round/commit/issues 是默认 repair context；用户明确增加、替换或重定义 repair scope 时以用户指令为准。
- resume：checkpoint id/commit、completed_scope、remaining_scope 等用于帮助恢复，而不是唯一允许入口。executor 应结合当前代码、Git history、测试和用户指令判断 continuation。operator resume 仍必须验证 handoff checkpoint/script/evidence 的必要完整性。

Artifact：

- execution report：`ai-work/executor/{stage_id}-executor.md`
- review：`ai-work/reviewer/{stage_id}-review.md`（只读）

同一 stage report append-only，不因“重跑”或 resume 自动清空。若已有 committed execution report，本次执行开始时它必须与最新 committed 版本一致；正常完成时只在 EOF 追加新的 completed `execution_record`，environment/operator 合法暂停时只在 EOF 追加新的 `execution_checkpoint`；不得改写旧 E0/E1/... 或旧 checkpoint 历史。

## 前置校验

1. 当前目录/branch 必须等于 plan metadata 指定 stage worktree/branch。
2. 用 plan_commit 定位 sealed baseline，并比较当前 plan/Git 状态。未授权的 plan 漂移必须查明；用户明确 override 时不因 plan/HEAD 与 seal SHA 不完全一致而机械停止。
3. implementation：report 不得已有 matching completed E0。检查 current HEAD、partial commits/checkpoints、working tree 和测试；状态可归因且剩余 scope 可可靠推导时允许 continue/resume。只有会重复 completed execution、provenance 无法归属或存在不可调和实现冲突时停止。
4. repair：latest review 是默认 baseline；根据 review 后 commits/checkpoint/diff 判断 effective remaining issues。普通 HEAD 漂移或 checkpoint 字段不完全匹配不单独构成停止条件。
5. 解析 plan/router/user override 得到 **effective stage profile/hardware/evidence contract**。用户未覆盖时以 sealed plan 为准；普通 metadata 差异先由 LLM判断实际 stage 意图，不要求逐字段机械一致。硬边界仍保留：control-plane/target hardware 职责不能被伪造，development 不能把 synthetic evidence冒充 formal validation，真实 24GB gate 必须走 operator boundary。缺失旧 metadata 可从项目现状可靠推导并记录，不要求为了补字段改写 sealed plan。
6. 新业务修改前执行当前 task 真正必要的 Execution preflight。sealed plan preflight 是默认清单；LLM 可跳过已由可靠 evidence 覆盖、已过时或与 effective scope 无关的检查，并记录理由。安全/依赖/结果真实性相关检查仍必须保留。preflight 失败时判断是可修环境、可修代码还是明确 blocker，不要求为了维持 plan/review/checkpoint SHA 而停留在原 HEAD。
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

repair checkpoint 应记录当时采用的 review round/commit/issues 作为恢复 provenance；这些普通 commit 字段用于审计，不要求后续 resume 与 current HEAD/最新 review 机械相等。`failed_command/blocker/remaining_scope` 应足以说明中断和剩余工作，completed_scope 只描述已可靠保存的工作。
3. 提交 execution checkpoint report：`docs: checkpoint {stage_id} execution after environment interruption`。`result_code_commit` 记录 partial-code anchor；checkpoint commit parent 不要求机械等于它，只要 Git history 能说明中间变化且没有未记录的冲突业务修改。checkpoint commit 不写入 record 自引用。
4. 返回 `EXECUTION_ENV_INTERRUPTED`，明确告诉用户先修环境，再显式 `$execution-router resume`；**不要**自动 retire、review 或继续执行。

resume/continue 优先使用 router 给出的 checkpoint，但不要求它与 current HEAD 完全重合。根据 checkpoint、后续 commits、current diff 和测试推导 effective completed/remaining scope，避免重复实现已完成工作；没有 formal checkpoint 时只要状态可可靠恢复也可继续。

## Operator terminal gate / resume

仅当 sealed `stage_profile=validation,target_hardware=24GB GPU` plan 含合法 `operator_terminal_execution` gate 时使用。该 block 覆盖全部 24GB acceptance gates，包括短时 4090-only smoke；executor 不直接启动任何 target-GPU command。

到达某个 operator gate 时：

1. 先完成并 commit gate 前全部 tracked code/config/test，完成 control-plane preflight、lint/unit/CPU/non-4090 integration/Piston 与其它 1660 Ti 可做的验证；stage 必须 clean。解析 restart policy，SFT/GRPO=`trainer_checkpoint`。若 gate 前无 tracked 修改，允许 result_code_commit 等于 plan/review baseline。
2. 预分配 `checkpoint_id=Cn`，生成唯一 tracked、secret-free、immutable `ai-work/executor/operator/{stage_id}/{gate_id}/{checkpoint_id}/run.sh` 与 ignored control-plane evidence 接收目录。script 使用 target-runtime templates，不硬编码 1660 Ti 路径。它在 4090 必须验证 working tree clean、current HEAD 就是用户 handoff 的 checkpoint commit、该 commit 中的 stage/gate/script path 可归属且 script SHA 匹配；parent/result_code/latest-checkpoint 等普通 SHA 只用于诊断，不要求机械等式。随后验证 target-local machine record、GPU、persistent roots/model/data/cache/storage；需要 Piston 时验证 loopback runtime。
3. script 获锁后执行 target-start preflight；失败则原子写非零状态并生成 evidence，不进入 target command。target command 必须可靠捕获自身 rc。若 `command_rc=0`，立即运行 sealed post-run acceptance（strict completed-run/checkpoint loader、metrics/schema/artifact identity 等）；只有 `postcheck_rc=0` 才 `gate_status=passed`。最终 status 原子写、log append-only，任何失败都保留 evidence并非零退出。
4. 每次 attempt 生成 versioned secret-free `operator-evidence.json`，至少绑定 stage/plan/operator-checkpoint/result-code/checkpoint/gate/script path+SHA、machine-record SHA、GPU/roots/Piston、timestamps、`command_rc/postcheck_rc/gate_status`、formal run identity 与 expected-artifact inventory（identity/metadata files SHA256）。既有 exact-rerun/trainer-checkpoint/latest-valid-checkpoint/quarantine/no-overwrite 语义不变。
5. 计算 script SHA，在 execution report append portable operator checkpoint，显式记录 `operator_handoff_mode: portable_target`、repo-relative tracked script path/SHA、target templates/evidence directory/expected artifacts/scopes/status。checkpoint commit 应尽量保持为 execution report + tracked script 的窄范围；若还包含可解释的 provenance/docs 变化，只要不改变待运行业务代码且被记录即可。`result_code_commit` 是审计 anchor，不要求 parent SHA 机械相等。返回 `EXECUTION_OPERATOR_ACTION_REQUIRED` 时仍要求用户让**实际 handoff checkpoint commit**在 4090 可达，并在 target 上 checkout 该 commit、确认 clean、重算 script SHA 后运行；这是证明实际运行代码/脚本身份所必需的。

`operator_handoff_mode: control_plane_manual` 只用于明确的 control-plane-only repair，且命令不能包含新的 24GB GPU execution。latest review 或用户明确指令必须能说明为何需要该 path。workflow/review/source commit 只作为审计 anchors，不要求 exact SHA 关系；tracked script SHA、frozen input/output identity、command/postcheck status 仍需独立验证。不得用它绕过真正 target-GPU gate或覆盖历史 formal evidence。

operator resume 使用 router 已识别的 **target handoff checkpoint anchor**；它不要求该 checkpoint 仍是 control-plane current HEAD，但必须能唯一确认实际 target run 使用了哪一个 checkpoint commit/script：

1. 计算 received evidence SHA256。严格校验聚焦证明实际运行对象所需的内容：handoff checkpoint identity、tracked script SHA、evidence bytes、machine/GPU/roots/Piston（如 required）、`command_rc/postcheck_rc/gate_status`、formal run/expected artifact identity，以及同步回来的 identity/metadata file hashes。plan/review/workflow-runtime/result-code 等 commit SHA 是审计 anchors；有漂移时检查 lineage/diff，不要求逐字段机械相等。`control_plane_manual` 同理验证 tracked script、frozen input/output identity 与真实 command/postcheck status，不伪造 4090 fields。
2. evidence/postcheck 足以证明 gate acceptance 时才加入 completed_scope；若 required large-artifact property 尚未被证明，保持 checkpoint 不变并要求短时只读 4090 check，不能猜 PASS。所有 gates/acceptance 通过后，completed execution record 必须记录每个 operator gate 的 evidence SHA256。
3. 纯 target 环境故障保持同一 checkpoint/HEAD，用户修复后重跑同一 tracked script；trainer checkpoint 自动选 latest valid same-run checkpoint，不为 resume flag 改 HEAD。
4. 若无合法 Trainer checkpoint或真实运行暴露 tracked bug，保留旧 run；必要修复在 control plane commit/test，并在 target persistent root quarantine旧 incomplete run 后生成新的 operator checkpoint/script。

## task_kind=implementation

1. 全文读 plan/spec/相关代码；resume/continue 读取可用 checkpoint、从 anchor 到 current HEAD 的 Git 状态和 working diff，识别实际 completed/remaining scope并避免重复实现。
2. 用户未覆盖时按 plan steps 顺序循环“实现 → 测试 → 验证 → 修正”；用户明确指定新的实现、步骤顺序或 scope 时按用户方案执行并记录 override。`DEV-CLOSEOUT` 仍是 verification-only；operator terminal gate 仍不得由 executor 越权执行。
3. 普通 stage 每个可独立步骤验证后显式暂存该步骤文件并 commit；禁止 `git add -A`。`DEV-CLOSEOUT` 不要求也不允许人为制造 code commit。
4. 完整运行 plan 总体验收中由 executor 负责的短时 gate（至少 `make lint`、`make test` 与 stage 指定的短测试）；operator long gate 只在 resume 对真实 artifacts 验收，不由 executor 首次调用执行。
5. 只有所有必要 operator gates 已通过真实 artifact/evidence 验收后，才记录当前 HEAD 为最终 `result_code_commit`。`DEV-CLOSEOUT` 不应制造业务 diff，但无需为了形式要求 HEAD 精确等于 plan_commit；若存在可解释的非业务 provenance/docs commit，记录实际 result_code_commit 即可。
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

1. 默认解析 router 指定 `repair_issue_ids` 对应的 latest review findings；resume/continue 结合 checkpoint、后续 commits 和 current diff，只处理实际尚未完成部分。若用户明确增加、替换或重定义 repair scope，以用户指令为准并记录 effective scope。
2. 用户未覆盖时不自行加入其它 minor/suggestion/plan step；LLM 根据实际代码避免重复修改已完成 repair。
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
- [ ] validation target=24GB 时全部 24GB gates 均由 operator boundary 承担；executor 未启动 target command；actual handoff commit、tracked script SHA、target preflight/postcheck、evidence/artifact identity 可验证；普通 parent/source SHA 仅作审计；
- [ ] validation 的正式 checkpoint/result 只写 target persistent artifact_root；control plane 不要求挂载该 root，portable operator evidence 足以跨机器核验，真实 checkpoint/result 未写入 `.worktrees/...`；
- [ ] implementation source 可可靠归属且没有重复 completed E0；`DEV-CLOSEOUT` 没有人为制造业务 code diff，result_code_commit 记录实际 provenance anchor而非强求等于 plan_commit；
- [ ] repair effective source/issues 可可靠归属；用户未覆盖时保持 router scope，用户明确 override 时已记录 effective repair scope；普通 review commit SHA 漂移未被当作机械 blocker；
- [ ] repair 总体验收没有被误解释成“修所有 review 问题”；
- [ ] result_code_commit 在 report docs commit 之前捕获；
- [ ] `.ai-bridge/**` 保持 ignored/untracked，所有 staged/committed path 都不包含 transport state；
- [ ] completed execution_record schema 完整；
- [ ] 未修改 plan/review/proceedings/third_party；未 push。
