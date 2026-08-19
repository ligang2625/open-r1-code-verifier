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
5. 解析 plan 的 `stage_profile / control_plane_hardware / target_hardware / evidence_class / development_terminal` 并与 router 输入逐项一致：control plane 固定 GTX 1660 Ti；development target=GTX 1660 Ti+engineering；validation target=24GB GPU+real-training/numerical+terminal=false，但当前 Web executor 仍在 control plane，不因 target=4090 改变 backend/机器。
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

sealed validation plan 含 `operator_terminal_execution` 时，正式 Base/B/C/D 全量评测、optimizer SFT/GRPO 等 target-GPU 长任务不得由 Web executor/CodexPro tool call 自己启动。达到 gate 前只完成并 commit tracked code/config/test、control-plane Execution preflight、lint/unit/CPU/non-4090 integration/Piston 与其它 1660 Ti 可完成的 short validation；不要为了 handoff 连接 4090。解析 `restart_policy=exact_rerun|trainer_checkpoint`，SFT/GRPO 必须为 `trainer_checkpoint`；若 gate 前无 tracked 修改，允许 result_code_commit 等于 plan/review baseline。

Web executor 在 ignored `.ai-bridge/operator-handoffs/<stage>/<plan>/<gate>/<checkpoint>/` 唯一目录生成 secret-free immutable **portable** `run.sh`，记录 `operator_handoff_mode=portable_target`、SHA256、target status/log/evidence templates、control-plane evidence directory 与 expected artifacts。script 不硬编码 1660 Ti checkout/roots；用户在 4090 fetch/checkout exact operator-checkpoint commit、复制并校验 script hash 后手工运行。script 在目标端解析 `CODE_VERIFIER_TARGET_REPO` 与 target-local `.ai-bridge/validation-machine.json`，验证 Git/report parent、READY identity、>=22528 MiB GPU、persistent roots/model/data/cache/storage、排他锁；若 gate 需要 Piston，确保 `/root/sj-tmp/open-r1-code-verifier-outputs/machine/ensure-piston-1660ti-tunnel.sh` 对唯一 `1660ti-wsl` host 的 loopback tunnel 健康。attempt status atomic、terminal log append-only、long command rc 必须显式可靠捕获；结束时生成 secret-free `operator-evidence.json` 绑定 target machine/GPU/roots/Piston、formal run、checkpoint inventory/hashes/summaries/status/log。

`exact_rerun` 与 `trainer_checkpoint` 的 same-checkpoint resume/latest-valid-checkpoint/strict-loader/quarantine/no-overwrite 语义保持不变。计算 source script SHA 后 append portable operator checkpoint，只提交 report docs commit，返回 `EXECUTION_OPERATOR_ACTION_REQUIRED`，明确 exact target commit、source script/hash、4090 manual-run 步骤与 evidence 回传目录，然后停止。

operator resume 默认在 1660 Ti 重新核验 source script SHA/restart policy 与同步回来的 `operator-evidence.json`/status/log/manifest/metrics，从 evidence 验证 target machine/GPU/roots/formal artifact identity；不要求 control-plane 本机拥有 24GB GPU或挂载 4090 roots，也不得替用户重跑/监控 long command。成功则继续 remaining_scope。纯环境故障保持 current checkpoint/HEAD，让用户修复 target 环境后重跑同一 hash-matching script；无合法 trainer checkpoint或 tracked bug 时按既有 quarantine + fresh portable checkpoint 规则保留旧正式 evidence。

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
- [ ] validation 若含 operator terminal gate，Web executor 未启动长任务；restart_policy/唯一 namespace/Git+lock guard/原子 status+append-only log 正确，trainer_checkpoint 同一 script 可恢复 latest valid checkpoint，失败 formal run 只 quarantine 不删除，并只在显式 resume 验证真实 artifacts 后继续；
- [ ] validation 的正式 checkpoint/result 只写 target persistent artifact_root；control plane 不要求挂载该 root，portable operator evidence 足以跨机器核验，真实 checkpoint/result 未写入 `.worktrees/...`；
- [ ] serialized_multi 覆盖全部 source candidates/repair_issue_ids；
- [ ] result_code_commit 在 report docs commit 之前捕获；
- [ ] `.ai-bridge/**` 保持 ignored/untracked，所有 staged/committed path 都不包含 transport state；
- [ ] execution_record 使用统一 v2 provenance；
- [ ] 未修改 plan/review/proceedings/third_party，未 push/review/finalize。
