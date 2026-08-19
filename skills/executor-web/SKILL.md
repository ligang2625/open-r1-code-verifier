---
name: executor-web
description: Web GPT + CodexPro routed execution protocol。仅由 execution-router backend=web 使用，在准确 stage worktree 中执行一次 implementation 或 repair；source SINGLE 直接执行，source MULTI 保留 sealed routing 并按 workstreams 串行化。共用 v2 execution_record/provenance，不调用 Local Codex execution agent，不做 review/finalization。
---

# Executor Web

Routing compatibility marker: `execution-routing-v2`。

## 边界

- 仅接受 routed v2 `backend=web`；没有完整 router provenance 时停止，不提供 legacy direct mode。
- 当前 Web GPT + CodexPro 自己完成 execution，不 spawn/调用 Local Codex execution agent，也不模拟 subagent topology。
- 不重判、不改写 `execution_routing` / `repair_routing`。
- `task_kind=implementation|repair` 严格互斥。
- 所有代码读取、写入、测试与 Git commit 都在 router 给定的**绝对 stage worktree**；不得在 primary checkout 实现阶段代码。
- 不修改 plan、review、proceedings、`third_party/open-r1/`；不 push、不 review、不 finalize。

## 必需输入

共同：stage_id、绝对 worktree、stage branch、plan path、plan_commit、task_kind、`backend=web`、完整 source routing、source_mode、effective_execution_mode、`stage_profile`、`control_plane_hardware`、`target_hardware`、`evidence_class`、`development_terminal`。Web executor 默认在 GTX 1660 Ti control plane；validation 普通 dispatch 不要求 4090 `artifact_root/hf_home/formal_data_root`，target roots 由 portable operator script 在 4090 runtime 解析。

- source_mode=single → effective 必须为 `single`
- source_mode=multi → effective 必须为 `serialized_multi`
- repair 额外必须有 review path、整数 source_review_round、review_commit、repair_issue_ids
- resume 额外必须有 `resume=true`、resume_checkpoint_id/commit、resume_from_code_commit、resume_interruption_class、completed_scope、remaining_scope；只能消费 router 验证的 current-head checkpoint。operator resume 还必须接收 router 验证过的 operator_gate_id/operator_restart_policy/script/script_sha256/status/log/expected_artifacts。

Artifact：`ai-work/executor/{stage_id}-executor.md`，append-only。若已有 committed execution report，当前 report 内容必须与最新 committed 版本一致；正常完成只在 EOF 追加 completed `execution_record`，合法 environment/operator 暂停只追加 `execution_checkpoint`；不得改写旧 E0/E1/... 或 checkpoint 历史。

## 前置校验

1. 使用当前 CodexPro 打开/绑定准确 stage worktree，并验证实际 branch/worktree 与 sealed plan metadata 一致；否则 `WEB_EXECUTION_WORKTREE_MISMATCH`。
2. plan 内容必须等于 plan_commit seal 版本。
3. implementation：report 不得已有 matching completed E0。普通 execution 要求 `HEAD == plan_commit`；resume 要求 `HEAD == resume_checkpoint_commit`，并精确匹配 checkpoint task/source/completed_scope/remaining_scope。
4. repair：普通 execution 要求 `HEAD == review_commit`；resume 要求 `HEAD == resume_checkpoint_commit` 且 checkpoint 精确绑定 latest committed review round/commit/issues。
5. 解析 plan 的 `stage_profile / control_plane_hardware / target_hardware / evidence_class / development_terminal` 并与 router 输入逐项一致：control plane 固定 GTX 1660 Ti；development target=GTX 1660 Ti+engineering；validation 固定 real-training/numerical+terminal=false，target 可为 GTX 1660 Ti（formal-evidence-only analysis）或 24GB GPU（含新的 target-GPU gates）。target=24GB 时全部 24GB acceptance 必须由 operator block覆盖；Web executor 自身仍在 control plane。
6. 在任何新的业务文件修改或 commit **之前**完整执行 plan 的 `Execution preflight`；普通 execution preflight 失败时保持 plan/review baseline，不写 report；resume 若环境仍未修好则保持 checkpoint HEAD，不追加重复 checkpoint，修复后可再次显式 resume。
7. validation：Web executor 不解析/校验 4090 roots，也不通过 CodexPro tool call 启动真实 target-GPU training/evaluation。sealed formal 命令只使用 `$CODE_VERIFIER_ARTIFACT_ROOT/$HF_HOME/$CODE_VERIFIER_DATA_ROOT` target-runtime templates；portable `run.sh` 在 4090 读取 target-local machine record 后设置并验证真实 roots。synthetic/mock/fake artifact 仍不能满足真实 gate。
8. 当前环境必须具备 workspace write、Git 和 plan 所需验证命令能力；缺失则停止，不自动改用 local。
9. stage `.venv` 默认是 lifecycle 创建的 primary-dependency overlay。若本次 execution 修改 `pyproject.toml` 或 `uv.lock`，必须在继续依赖相关测试前运行 `skills/stage-lifecycle/scripts/bootstrap_stage_env.py --primary-root <primary> --stage-worktree <stage> --mode full`，切换为完整 stage-local pinned environment；不能让 primary overlay 掩盖 dependency contract 的变化。

**Transport hard guard**：开始任何业务修改前必须确认 `git ls-files .ai-bridge` 为空；否则返回 `WEB_EXECUTION_TRANSPORT_TRACKED`。`.ai-bridge/**` 只允许作为 ignored 本地 transport state。每个 code/test/config/report commit 都必须显式暂存目标文件，并在 commit 前确认 staged path 不包含 `.ai-bridge/**`。

## 环境中断 checkpoint / resume

当已经有本次 task 的有效 commits、stage clean，之后遇到无需 tracked 仓库修改即可修复的环境/基础设施故障时，Web executor 可以暂停而不是要求 retire。源码 lint/type/test failure、tracked config/dependency bug、模型/acceptance 逻辑失败不是 environment interruption。

暂停时捕获 partial `result_code_commit=HEAD`，在 execution report EOF 追加 `execution_checkpoint(version=1, checkpoint_id=Cn, exact task/source provenance, result_code_commit, interruption_class=environment, resume_allowed=true, failed_command, blocker, completed_scope, remaining_scope, status=interrupted)`，单独 docs commit report，然后返回 `EXECUTION_ENV_INTERRUPTED` 并结束当前 execution 对话。不得把 dirty business diff checkpoint，不得自动调用 reviewer/finalize/retire。

resume 必须来自 router 验证的 current-head checkpoint。source SINGLE 从 remaining_scope 继续；source MULTI/serialized_multi 跳过 completed_scope 已提交 lanes，只串行执行 remaining_scope 对应 lanes/集成/acceptance，sealed source routing 不变。可以重新运行 preflight/测试/全局验收。完成后的 execution_record 额外记录 `resumed_from_checkpoint_id/commit`。

## Operator terminal gate / resume

sealed validation plan 只有在 `target_hardware=24GB GPU` 时使用 `operator_terminal_execution`，且该 block 覆盖全部 24GB acceptance gates（短 smoke 与长训练一致）。Web executor/CodexPro 不启动任何 target-GPU command；gate 前只完成/commit code/config/test 与 1660 Ti control-plane preflight/lint/unit/CPU/non-4090 integration/Piston。

Web executor 生成唯一 tracked secret-free immutable `ai-work/executor/operator/<stage>/<gate>/<checkpoint>/run.sh`。checkpoint 显式记录 `operator_handoff_mode: portable_target`、repo-relative path/SHA、target templates/evidence directory/expected artifacts，并用一个 provenance commit 只提交 execution report + 这份新 script，parent=result_code_commit。返回 operator action 时明确 workflow 不自动 push：用户先通过 Git 让 exact checkpoint commit 在 4090 可达，再 checkout/detach 到该 commit、确认 clean、重算 SHA 并直接运行 tracked script。script 在 target 端验证 current commit/parent/latest checkpoint/script SHA、machine READY、>=22528 MiB GPU、roots/model/data/cache/storage、锁与 `1660ti-wsl` Piston tunnel（如 required）。

script 执行 start preflight → target command → sealed post-run acceptance；必须可靠记录 `command_rc`，command=0 后立即运行 strict completed-run/checkpoint loader、metrics/schema/artifact identity 等短 postcheck。只有 `command_rc=0 && postcheck_rc=0` 才 `gate_status=passed`。每 attempt 生成 versioned secret-free `operator-evidence.json`，绑定 stage/plan/operator-checkpoint/result-code/checkpoint/gate/script path+SHA、machine-record SHA、GPU/roots/Piston、timestamps、rc/status、formal run 与 expected-artifact inventory。exact-rerun/trainer-checkpoint/latest-valid-checkpoint/quarantine/no-overwrite 语义保持。

operator resume 在 1660 Ti 计算 received evidence SHA256并严格验证上述 schema/provenance、tracked script SHA、`command_rc=0/postcheck_rc=0/gate_status=passed`、formal artifacts；同步回来的 identity/metadata files 重算 SHA。证据不足以证明 required large-artifact property 时保持 checkpoint 并要求短时只读 target check。成功后继续 remaining_scope，并在 completed execution record记录 gate/checkpoint/evidence SHA256；不得替用户重跑/监控 target command。

## source SINGLE

### implementation

1. 全文读取 plan/spec/相关代码；resume 同时读取 checkpoint，确认 completed_scope 已提交。
2. 普通 stage 按 plan steps 顺序执行“实现 → 定向测试 → 验证 → 修正”；resume 只从 remaining_scope 继续。`DEV-CLOSEOUT` 是 verification-only：不得修改业务代码/配置/测试，只执行 preflight 与 closeout gates。遇到 operator terminal gate 时执行到 gate 前置条件后转入 Operator terminal protocol，禁止直接运行长命令。
3. 普通 stage 每个可独立步骤验证后显式暂存其文件并 commit；禁止 `git add -A`。`DEV-CLOSEOUT` 不制造 code commit。
4. 运行 plan 中 executor-owned 的全局短时 acceptance/gates；operator long gate 只在 resume 对真实 artifacts 验收。

### repair

1. 只处理 dispatch `repair_issue_ids` 对应的 latest committed review findings；resume 只继续 checkpoint remaining_scope 中尚未完成的 issue/验证。
2. 每个 issue 做最小修复与定向测试；其它 finding 不自动进入 scope，也不重复修改 completed_scope 已提交的 repair。
3. 运行受影响测试 + plan 中 executor-owned 的全局 regression/acceptance；全局验证不扩大 repair scope。若需要重跑受影响的 operator long gate，按 Operator terminal protocol 生成新的 checkpoint/script，不由 Web executor 直接运行。
4. 显式提交修复 code/test/config；只有需要重跑的 operator gates 经 resume artifact 验收后才允许写 completed repair record。

## source MULTI → serialized_multi

`serialized_multi` 是 Web backend 的正式执行拓扑；**source routing 仍然是 MULTI**。

### implementation

- 普通 execution 使用 sealed `execution_routing.workstream_candidates` 作为完整 lane 清单并全部覆盖；resume 保持同一 sealed 清单，但只重新执行 checkpoint remaining_scope 对应 lanes/集成，completed_scope 已提交 lanes 视为已覆盖。
- 默认按 candidate 在 plan 中的顺序执行；resume 保持剩余 lanes 的原相对顺序。
- 若真实代码依赖要求改变先后，只允许调整**运行顺序**；不得改 routing/candidate 内容，并在 report 记录原因。
- 每个 lane：读取 assigned steps/write_scope → 实现 → 定向测试 → 显式 commit → 再进入下一 lane。
- 因为当前只有一个 Web executor，不需要并行 filesystem isolation；但不得借串行化扩大各 lane 的业务范围。
- 所有 lanes 完成后统一跑 executor-owned 的 integration/global acceptance；若下一步是 operator long gate，转入 Operator terminal protocol 并停止，不由 Web executor 自行运行。

### repair

- 使用 latest `repair_routing.workstream_candidates`；candidate issue_ids 并集仍必须恰好等于 dispatch repair_issue_ids。resume 仅执行 remaining_scope 对应 candidates，completed_scope 已提交 candidates 不重做。
- 每个剩余 lane 只处理自己的 issue_ids，完成定向测试并 commit 后再进入下一 lane。
- 最后统一跑受影响测试 + plan 中 executor-owned 的 regression/acceptance；全局验证不扩大 repair scope。若必须重跑 operator long gate，生成新的 operator checkpoint/script，等待用户终端执行后 resume 验收。

若 source MULTI candidate schema 本身非法，返回对应 routing contract error；不得自行构造新的 routing。

## Execution record / commit ordering

所有代码/测试/config commits 完成、所有需要的 operator gates 已通过显式 resume 的真实 artifact 验收、且其它必须验收通过后；`DEV-CLOSEOUT` 可以没有任何 code/config/test commit：

1. 捕获 `result_code_commit=HEAD`；`DEV-CLOSEOUT` 要求此时 `HEAD == plan_commit`，因此 `result_code_commit=plan_commit` 合法；
2. append execution report 的下一 record 与人类可读摘要；追加前再次确认旧 report 历史未变化；
3. 单独 docs commit report；该 commit 只包含本次 EOF append。
4. execution report commit 成功后立即结束本次 execution 对话。下一步 reviewer-ex 必须在新的 Web GPT conversation/context 中运行；不要在当前对话自审。

Implementation 示例：

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
  result_code_commit: <code HEAD>
  execution_backend: web_codexpro
  effective_execution_mode: single  # or serialized_multi
  status: completed
```

Repair 使用 E1/E2/... 并填 source_review_round/source_review_commit/repair_issue_ids。只有全部必须验收满足才可 completed。

`execution_backend/effective_execution_mode` 只用于审计，不改变 reviewer provenance。若本次来自 resume，completed record 额外记录 `resumed_from_checkpoint_id` 与 `resumed_from_checkpoint_commit`。

## 报告

至少记录：source mode、effective mode、真实命令/结果、修改文件、step/workstream 或 issue/lane 映射、任何执行顺序调整及原因、阻塞/偏差。

## 自检

- [ ] 当前 workspace 是准确 stage worktree；
- [ ] 未调用 Local Codex execution agent；
- [ ] source routing 未修改；MULTI 只在运行时 serialized；
- [ ] implementation/repair 只执行一个 task_kind；`DEV-CLOSEOUT` 如无业务 diff，已确认 `result_code_commit == plan_commit` 且没有人为制造 code commit；
- [ ] Execution preflight 在首次/恢复后的新业务修改前完成；baseline preflight 失败未产生业务 commit/report；已有 partial commits 后的 environment interruption 如需暂停，已写合法 checkpoint 而不是强制 retire；
- [ ] validation target=24GB 时全部 24GB gates 均由 operator boundary 承担；Web executor 未启动 target command；tracked script/commit-parent/diff/SHA、target preflight、mandatory postcheck、atomic status/append-only log、trainer checkpoint/quarantine 均正确；resume 已验证 evidence schema、command/postcheck/gate_status 与 evidence SHA，并把成功 gate 的 evidence SHA 写入 completed record；
- [ ] validation 的正式 checkpoint/result 只写 target persistent artifact_root；control plane 不要求挂载该 root，portable operator evidence 足以跨机器核验，真实 checkpoint/result 未写入 `.worktrees/...`；
- [ ] serialized_multi 覆盖全部 source candidates/repair_issue_ids；
- [ ] result_code_commit 在 report docs commit 之前捕获；
- [ ] `.ai-bridge/**` 保持 ignored/untracked，所有 staged/committed path 都不包含 transport state；
- [ ] execution_record 使用统一 v2 provenance；
- [ ] 未修改 plan/review/proceedings/third_party，未 push/review/finalize。
