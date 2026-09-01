---
name: executor-web
description: Web GPT + CodexPro execution protocol。默认消费 execution-router 的 sealed routing，但允许用户明确覆盖实现方式、scope、顺序或 routing；由 LLM 结合当前项目状态判断 continuation/resume。保留 stage identity、operator evidence 和 transport 等必要完整性边界，不把普通 commit/SHA 漂移当作机械阻塞。
---

# Executor Web

Routing compatibility marker: `execution-routing-v2`。

## 边界

- 仅接受 routed v2 `backend=web`；没有完整 router provenance 时停止，不提供 legacy direct mode。
- 当前 Web GPT + CodexPro 自己完成 execution，不 spawn/调用 Local Codex execution agent，也不模拟 subagent topology。
- 用户没有明确覆盖时，不自行扩大或改写 `execution_routing` / `repair_routing`；用户明确指定新的实现、scope、顺序或执行方式时，以用户指令为准，并在 execution report 记录 override 与原因。
- `task_kind=implementation|repair` 严格互斥。
- 所有代码读取、写入、测试与 Git commit 都在 router 给定的**绝对 stage worktree**；不得在 primary checkout 实现阶段代码。
- 不修改 plan、review、proceedings、`third_party/open-r1/`；不 push、不 review、不 finalize。

## 必需输入

router 应尽量提供 stage_id、绝对 worktree/branch、plan path/plan_commit、task_kind、`backend=web`、source/effective routing、profile/hardware/evidence metadata，以及 repair/resume context。stage/worktree/task_kind/backend 是必要身份；普通 plan/review/workflow-runtime/checkpoint commits 是审计 anchors，可从 repo state 恢复，不要求 exact SHA。

- source SINGLE → 默认 effective `single`；source MULTI → 默认 `serialized_multi`，但用户明确指令或真实依赖可改变 effective topology并记录。
- repair review path/round/commit/issues 是默认 context；用户明确改变 repair scope 时以用户指令为准。
- resume checkpoint/scope context 用于辅助恢复而非唯一入口；Git history/report/diff/tests/user intent 可共同推导 continuation。operator resume 仍必须具备足够的 handoff checkpoint/script/evidence 信息。

Artifact：`ai-work/executor/{stage_id}-executor.md`，append-only。若已有 committed execution report，当前 report 内容必须与最新 committed 版本一致；正常完成只在 EOF 追加 completed `execution_record`，合法 environment/operator 暂停只追加 `execution_checkpoint`；不得改写旧 E0/E1/... 或 checkpoint 历史。

## 前置校验

1. 使用当前 CodexPro 打开/绑定准确 stage worktree，并验证实际 branch/worktree 与 sealed plan metadata 一致；否则 `WEB_EXECUTION_WORKTREE_MISMATCH`。
2. 用 `plan_commit` 定位 sealed baseline，并比较当前 plan/Git 状态。未获用户授权的 plan 漂移必须查明；但用户已明确改变实现方式时，不因当前内容或 HEAD 与 seal SHA 不完全一致而机械停止，也不要求为了旧 hash guard 回退代码。
3. implementation：report 不得已有 matching completed E0。比较 `HEAD`、plan baseline、已有 partial commits/checkpoints 和 working tree；若当前状态可归因于本 stage、已完成范围可识别且没有不可修复冲突，则允许从当前状态继续。仅在 provenance 无法判定、存在明显互斥实现或会重复消费 completed execution 时停止。
4. repair：以 latest committed review 为默认问题基线，结合 review 后 commits/checkpoint/diff 判断实际剩余问题。普通 HEAD 前移本身不是错误；只在无法判断这些变化是否属于本轮 repair、会跳过未审查实质变更或与用户目标冲突时停止。
5. 解析 plan/router/user override 得到 **effective stage profile/hardware/evidence contract**。用户未覆盖时以 sealed plan 为准；普通 metadata 差异先由 LLM判断实际 stage 意图，不要求逐字段机械一致。硬边界仍保留：Web executor 自身仍在 control plane；真实 24GB gate 必须走 operator boundary；synthetic/mock 不得冒充 formal validation evidence。旧 plan 缺失 metadata 时可从项目现状可靠推导并记录，无需为了补字段改写 sealed plan。
6. 在新的业务修改前执行**当前任务真正必要**的 Execution preflight。sealed plan 的 preflight 是默认清单；LLM 可依据当前项目状态跳过已被可靠证据覆盖、已过时或与本次 scope 无关的检查，并说明理由。安全边界、必要服务/依赖以及会影响结果真实性的检查不能省略。preflight 失败时优先判断是可修环境问题、可修代码问题还是明确 blocker，不要求为了保持某个 baseline SHA 而停住。
7. validation：Web executor 不解析/校验 4090 roots，也不通过 CodexPro tool call 启动真实 target-GPU training/evaluation。sealed formal 命令只使用 `$CODE_VERIFIER_ARTIFACT_ROOT/$HF_HOME/$CODE_VERIFIER_DATA_ROOT` target-runtime templates；portable `run.sh` 在 4090 读取 target-local machine record 后设置并验证真实 roots。synthetic/mock/fake artifact 仍不能满足真实 gate。
8. 当前环境必须具备 workspace write、Git 和 plan 所需验证命令能力；缺失则停止，不自动改用 local。
9. stage `.venv` 默认是 lifecycle 创建的 primary-dependency overlay。若本次 execution 修改 `pyproject.toml` 或 `uv.lock`，必须在继续依赖相关测试前运行 `skills/stage-lifecycle/scripts/bootstrap_stage_env.py --primary-root <primary> --stage-worktree <stage> --mode full`，切换为完整 stage-local pinned environment；不能让 primary overlay 掩盖 dependency contract 的变化。

**Transport hard guard**：开始任何业务修改前必须确认 `git ls-files .ai-bridge` 为空；否则返回 `WEB_EXECUTION_TRANSPORT_TRACKED`。`.ai-bridge/**` 只允许作为 ignored 本地 transport state。每个 code/test/config/report commit 都必须显式暂存目标文件，并在 commit 前确认 staged path 不包含 `.ai-bridge/**`。

## 环境中断 checkpoint / resume

当已经有本次 task 的有效 commits、stage clean，之后遇到无需 tracked 仓库修改即可修复的环境/基础设施故障时，Web executor 可以暂停而不是要求 retire。源码 lint/type/test failure、tracked config/dependency bug、模型/acceptance 逻辑失败不是 environment interruption。

暂停时捕获 partial `result_code_commit=HEAD`，在 execution report EOF 追加 environment `execution_checkpoint`，记录当时采用的 task/source provenance、completed/remaining scope、failed command/blocker，并提交 report，然后返回 `EXECUTION_ENV_INTERRUPTED`。task/source 普通 commit 字段是恢复审计 anchors，不要求后续 resume 与 current HEAD 机械相等；不得把来源不明的 dirty business diff 伪装成 checkpoint，也不得自动 retire。

resume/continue 优先消费最新可靠 checkpoint；若没有完全匹配 current HEAD 的 checkpoint，则由 LLM 根据 commits、diff、report 和测试推导 effective completed/remaining scope。source SINGLE/MULTI 都应避免重复已完成工作，并可根据真实依赖调整剩余执行方式。若偏离 sealed routing 或 checkpoint scope，记录 `user_override` 或 `continuation_judgment` 及依据。

## Operator terminal gate / resume

sealed validation plan 只有在 `target_hardware=24GB GPU` 时使用 `operator_terminal_execution`，且该 block 覆盖全部 24GB acceptance gates（短 smoke 与长训练一致）。Web executor/CodexPro 不启动任何 target-GPU command；gate 前只完成/commit code/config/test 与 1660 Ti control-plane preflight/lint/unit/CPU/non-4090 integration/Piston。

正常新 target-GPU gate 使用 `operator_handoff_mode=portable_target`。Web executor 生成唯一 tracked secret-free immutable `ai-work/executor/operator/<stage>/<gate>/<checkpoint>/run.sh`。checkpoint 记录 repo-relative path/SHA、target templates/evidence directory/expected artifacts；checkpoint commit 应尽量只含 execution report + script，但可容纳已解释且不改变待运行业务代码的 provenance/docs 变化。`result_code_commit`/parent 是审计线索，不要求机械相等。用户仍必须通过 Git 让**实际 handoff checkpoint commit**在 4090 可达，并 checkout/detach 到该 commit、确认 clean、重算 script SHA 后运行。target 端必要校验是：current HEAD 等于用户 handoff commit、stage/gate/script path 可归属、tracked script SHA 匹配，以及 machine/GPU/roots/model/data/cache/storage/Piston（如需要）满足运行合同；parent/latest-checkpoint 等普通 SHA 只用于诊断。script 执行 start preflight → target command → post-run acceptance；只有 `command_rc=0 && postcheck_rc=0` 才 `gate_status=passed`，并生成 versioned evidence 绑定实际 handoff commit、script SHA、运行环境和 artifact identity。

**`control_plane_manual` repair exception**：仅用于明确的 control-plane-only repair，且不能包含新的 target-GPU training/inference。latest review 或用户明确指令必须能说明为何使用该 path。script 仍必须验证 stage/gate/script identity、tracked script SHA、stage cleanliness、真正影响结果的 frozen verifier/Open-R1/dependency/generation/data/Piston/formal identity、fresh non-overwriting output 和真实 command/postcheck status。plan/review/workflow-runtime/planning-base/parent 等 commit SHA 是审计 anchors，有漂移时看 lineage/diff，不要求机械相等。不得用此模式把真正 24GB gate 挪回 1660 Ti。

operator resume 计算 received evidence SHA256。严格校验只集中在实际 handoff checkpoint/script identity、evidence bytes、`command_rc/postcheck_rc/gate_status`、formal artifact identity以及必要 synced-file hashes；plan/review/workflow-runtime/result-code 等 commit SHA 作为审计 anchors，有漂移时检查 lineage/diff。证据不足以证明 required large-artifact property 时才要求短时只读 target check。`control_plane_manual` 同样严格验证 tracked script、frozen input/output identity和真实 command/postcheck status，不要求普通 commit SHA 机械相等。成功后继续 effective remaining scope，并记录 handoff/evidence SHA。

## source SINGLE

### implementation

1. 全文读取 plan/spec/相关代码；resume/continue 同时读取可用 checkpoint、Git history 和当前 diff，识别实际 completed/remaining scope。
2. 用户未覆盖时按 plan steps 顺序执行“实现 → 定向测试 → 验证 → 修正”；用户明确指定新的实现、步骤顺序或范围时执行用户方案，并记录与 sealed plan 的偏差。`DEV-CLOSEOUT` 是 verification-only；operator terminal gate 仍不得由 executor 越权执行。
3. 普通 stage 每个可独立步骤验证后显式暂存其文件并 commit；禁止 `git add -A`。`DEV-CLOSEOUT` 不制造 code commit。
4. 运行 plan 中 executor-owned 的全局短时 acceptance/gates；operator long gate 只在 resume 对真实 artifacts 验收。

### repair

1. 默认只处理 dispatch `repair_issue_ids` 对应的 latest committed review findings；若用户明确增加、替换或重新定义修复范围，则以用户指令为准，并在 report 中记录 effective repair scope。
2. 每个 issue 做最小完整修复与定向测试；LLM 根据当前 diff 避免重复已完成 repair。
3. 运行受影响测试 + plan 中 executor-owned 的全局 regression/acceptance；全局验证不扩大 repair scope。若需要重跑受影响的 operator long gate，按 Operator terminal protocol 生成新的 checkpoint/script，不由 Web executor 直接运行。
4. 显式提交修复 code/test/config；只有需要重跑的 operator gates 经 resume artifact 验收后才允许写 completed repair record。

## source MULTI → serialized_multi

`serialized_multi` 是 Web backend 的正式执行拓扑；**source routing 仍然是 MULTI**。

### implementation

- 用户未覆盖时使用 sealed `execution_routing.workstream_candidates` 作为默认 lane 清单；resume/continue 根据实际 completed scope 跳过已完成工作。若用户明确改变 workstream 划分，或真实依赖表明原划分不再合适，可调整 effective lanes/mode，并记录原因，不必为了维持 sealed MULTI 形式制造假 lane。
- 默认按 candidate 在 plan 中的顺序执行；resume/continue 可按真实依赖调整剩余顺序。
- 若真实代码依赖或用户指令要求改变先后、合并/拆分 lane，可调整 effective execution；sealed routing 保留为历史 baseline，不必回写 plan。
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

1. 捕获 `result_code_commit=HEAD`；`DEV-CLOSEOUT` 不应制造业务代码 diff，但若存在可解释的 provenance/docs commit，不要求 HEAD 精确等于 plan_commit，记录实际 result_code_commit 即可；
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
  workflow_runtime_commit: <required for active-stage workflow migration; otherwise omit>
  legacy_control_plane_default: true  # required with workflow_runtime_commit; otherwise omit
  status: completed
```

Repair 使用 E1/E2/... 并填 source_review_round/source_review_commit/repair_issue_ids。只有全部必须验收满足才可 completed。

`execution_backend/effective_execution_mode` 只用于审计，不改变 reviewer provenance。active-stage workflow migration 时 `workflow_runtime_commit` 与 `legacy_control_plane_default=true` 必须成对记录，绑定本轮实际加载的 maintenance runtime；普通 stage 省略二者。若本次来自 resume，completed record 额外记录 `resumed_from_checkpoint_id` 与 `resumed_from_checkpoint_commit`。

## 报告

至少记录：source mode、effective mode、真实命令/结果、修改文件、step/workstream 或 issue/lane 映射、任何执行顺序调整及原因、阻塞/偏差。

## 自检

- [ ] 当前 workspace 是准确 stage worktree；
- [ ] 未调用 Local Codex execution agent；
- [ ] 用户未覆盖时遵循 source routing；若 user override/LLM judgment 改变 effective mode/lanes，已记录原因，没有为了 sealed 形式制造假工作；
- [ ] implementation/repair 只执行一个 task_kind；`DEV-CLOSEOUT` 没有人为制造业务 code diff，result_code_commit 记录实际 provenance anchor；
- [ ] 已执行当前 task 必要的 preflight；partial/incomplete 状态优先 continuation assessment，没有因缺少 exact checkpoint 强制 retire；
- [ ] validation target=24GB 时全部 24GB gates 均由 operator boundary 承担；Web executor 未启动 target command；actual handoff commit、tracked script SHA、target preflight/postcheck、evidence/artifact identity 可验证，普通 parent/source SHA 仅作审计；
- [ ] validation 的正式 checkpoint/result 只写 target persistent artifact_root；control plane 不要求挂载该 root，portable operator evidence 足以跨机器核验，真实 checkpoint/result 未写入 `.worktrees/...`；
- [ ] effective execution 覆盖全部有效 implementation/repair scope；用户未覆盖时 source candidates/issues 默认全覆盖，用户 override 时已记录替换后的 effective scope；
- [ ] result_code_commit 在 report docs commit 之前捕获；
- [ ] `.ai-bridge/**` 保持 ignored/untracked，所有 staged/committed path 都不包含 transport state；
- [ ] execution_record 使用统一 v2 provenance；
- [ ] 未修改 plan/review/proceedings/third_party，未 push/review/finalize。
