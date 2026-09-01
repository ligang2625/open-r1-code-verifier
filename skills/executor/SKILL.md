---
name: executor
description: Local Codex execution protocol。默认执行 router 的 MULTI routing，但用户明确指令或当前代码依赖可覆盖 sealed workstream 方式；coordinator 由 LLM 判断 continuation/resume 和有效 lane 拆分。保留必要 stage/operator/transport 完整性边界，不把普通 commit/SHA 漂移或无法维持原 MULTI 形式当作机械阻塞。
---

# Codex Executor

Routing compatibility marker: `execution-routing-v2`。

## 固定 agent topology

入口 agent 只做一件事：创建 1 个 main coordinator：

- model: `gpt-5.6-sol`
- reasoning_effort: `medium`
- fork_turns: `none`

main coordinator 为每个独立 subplan 创建 1 个 worker：

- model: `gpt-5.6-luna`
- reasoning_effort: `max`
- fork_turns: `none`

worker 不再创建 agent。模型配置不由 router 覆盖。

## Invocation mode

本 skill 默认消费 routed v2 上下文；`stage_id`、准确 worktree 和 task_kind 是必要身份信息。`plan_commit`/routing/checkpoint 等字段应尽量提供以便审计，但缺少普通 provenance 字段时，先尝试从 repo state 唯一恢复；只有 stage/source 无法可靠定位时才返回 `EXECUTOR_ROUTING_CONTEXT_INCOMPLETE`。

## Routed MULTI 前置

router 应尽量提供 stage_id、绝对 worktree、plan path/plan_commit、task_kind、source/effective routing、backend、profile/hardware/evidence metadata，以及 repair/resume context。`stage_id`、worktree、task_kind 与实际 backend 是必要身份；plan/review/workflow-runtime/checkpoint commits 是审计 anchors，缺失或漂移时可从 repo state 恢复，不要求 exact SHA。portable operator resume 仍必须提供足够的 handoff checkpoint/script/evidence context来证明实际 target run。

`task_kind` 两条路径互斥；repair 完成后不得继续 implementation。

main 开始任何拆分/修改前先进入 stage worktree、读 plan/spec/代码、Git history 和对应 routing source，并解析 stage profile/hardware/evidence boundary。sealed routing 和 preflight 是默认执行合同；用户明确指令优先，LLM 也可在真实依赖变化时调整 effective lane 划分、顺序或从 MULTI 降为更合适的执行方式，只要记录偏差且不突破 operator/证据/安全边界。普通 HEAD/checkpoint SHA 只用于定位，不作为单独的硬停止条件。workers/coordinator 始终只做 control-plane scope，fixture/mock/synthetic 不得满足真实 validation gate；operator target command 仍不得由 worker/coordinator 启动。execution report 继续 append-only。

stage `.venv` 默认是 lifecycle 创建的 primary-dependency overlay。若任一 routed workstream 需要修改 `pyproject.toml` 或 `uv.lock`，必须由 coordinator 在 spawn 相关 worker/继续依赖测试前串行运行 `skills/stage-lifecycle/scripts/bootstrap_stage_env.py --primary-root <primary> --stage-worktree <stage> --mode full`，建立完整 stage-local pinned environment；之后全部 workers/tests 使用该 stage `.venv`，不能继续借 primary overlay 隐式满足依赖。

**Transport hard guard**：coordinator 在 spawn worker 或业务修改前必须确认 `git ls-files .ai-bridge` 为空；否则返回 `EXECUTION_TRANSPORT_TRACKED`。`.ai-bridge/**` 不得进入 worker tracked write_scope。所有 coordinator code/test/config/report commits 都显式暂存目标文件，并在 commit 前确认 staged path 不包含 `.ai-bridge/**`。

## 环境中断 checkpoint / resume

仅当 coordinator 已经集成并 commit 了可保留的部分 workstreams/repair，stage clean，随后遇到无需修改 tracked 仓库即可修复的环境/基础设施故障时，才允许暂停。源码 lint/type/test failure、tracked config/dependency bug 或 acceptance 逻辑失败不是 environment interruption。

暂停时 coordinator 捕获 partial `result_code_commit=HEAD`，在 execution report EOF 追加 environment checkpoint 并提交 report。`result_code_commit` 是 partial-code provenance anchor；checkpoint docs commit parent 不要求机械等于它，只要中间 history 可解释且没有未记录的冲突业务修改。不得把无法归属的 worker diff 伪装成 checkpoint，也不得自动 retire。

resume/continue 优先利用最新可靠 checkpoint，但不要求 checkpoint commit 恰好等于 current HEAD。coordinator 根据 commits、diff、report、tests 和用户指令推导 effective completed/remaining scope，避免重复已完成 lane；若原 MULTI 划分已不合适，可调整 effective workers 或直接由 coordinator 完成串行剩余工作，并在 report 记录 continuation judgment。

## Operator terminal gate / resume

sealed validation plan 只有在 `target_hardware=24GB GPU` 时使用 operator block，且它覆盖全部 24GB acceptance gates。workers 只能实现/测试 control-plane workstreams；coordinator 集成后负责 tracked operator handoff，任何 worker/coordinator 都不启动 target-GPU command。

coordinator 预分配 checkpoint_id，生成唯一 tracked secret-free immutable `ai-work/executor/operator/<stage>/<gate>/<checkpoint>/run.sh`。target 端必须验证 clean tree、current HEAD 就是用户 handoff 的 checkpoint commit、stage/gate/script path 可归属并且 tracked script SHA 匹配；parent/result_code/latest-checkpoint 等普通 SHA 只作诊断，不要求机械等式。随后验证 target machine/GPU/roots/model/data/cache/storage/lock/Piston（如需要）。script 执行 start preflight → target command → post-run acceptance；只有 `command_rc=0 && postcheck_rc=0` 才 `gate_status=passed`，evidence 绑定实际 handoff commit、script SHA、运行环境和 artifact identity。

coordinator 计算 script SHA，append portable operator checkpoint，并记录 `operator_handoff_mode: portable_target`。checkpoint commit 应尽量保持为 execution report + script 的窄范围；若包含可解释且不改变待运行业务代码的 provenance/docs 变化也可接受。`result_code_commit` 是审计 anchor，不要求 parent SHA 机械相等。用户仍必须让实际 handoff checkpoint commit 在 4090 可达并 checkout 后重算 script SHA；exact-rerun/trainer-checkpoint/quarantine/no-overwrite 语义保持。

`operator_handoff_mode: control_plane_manual` 只用于明确的 control-plane-only repair，且命令不能包含新的 24GB GPU execution。latest review 或用户明确指令必须能说明为何需要该 path。`workflow_runtime_commit`、review/source commits 可记录为审计 anchors，但不要求 exact SHA 关系；tracked script SHA、frozen input/output identity、command/postcheck status 仍需可独立验证。不得用它绕过真正 target-GPU gate。

operator resume 由 coordinator 计算 received evidence SHA256。严格校验只集中在证明实际运行对象所需的内容：handoff checkpoint identity、tracked script SHA、evidence bytes、`command_rc/postcheck_rc/gate_status`、formal artifact identity及必要 synced-file hashes。plan/review/workflow-runtime/result-code 等 commit SHA 作为审计 anchors；有漂移时检查 lineage/diff，不要求逐字段相等。证据不足以证明 required large-artifact property 时才要求短时只读 target check。成功 gate 的 handoff mode/evidence SHA 写入 completed record。

## Parallelism judgment

routed MULTI 默认应基于真实代码形成 ≥2 个 mutually independent subplans；sealed MULTI 是 planner 的先验判断，不要求 executor 为了形式一致制造并行。

若当前代码状态只能形成 1 个可靠 lane，coordinator 可以退化为单 lane/串行执行，或在用户明确要求时采用用户指定拓扑；记录 `effective_execution_mode` 和原因即可。只有无法形成安全、完整的执行方案时才停止。

- implementation：复核 plan candidate `steps`。
- repair：只复核/拆分 router 的 `repair_issue_ids`，worker issue 并集必须恰好等于这些 IDs。

## task_kind=implementation（仅 routed v2）

1. 确认 report 不存在 matching completed E0。比较 plan baseline、current HEAD、partial commits/checkpoints 和 working tree；只要状态可归因且剩余范围可可靠判断，就从当前状态继续。HEAD 前进本身不是 blocker。
2. 用户未覆盖时按 plan steps/默认 routing 拆 subplans；resume/continue 只处理实际剩余范围。用户明确方案或真实依赖可以改变 effective routing，而无需改写 sealed plan。
3. 每个 worker 任务必须自包含：worktree、plan、assigned steps、唯一 tracked write_scope、禁止项、定向测试、汇报格式。
4. workers 只改 assigned tracked scope，不 stage/commit、不写总报告。
5. coordinator 汇总 diff、解决集成顺序、亲自运行定向 + executor-owned 全局短时验收。若下一步命中 operator long gate，转入 Operator terminal protocol，禁止直接执行长命令。
6. coordinator 按独立 subplan 显式暂存并 commit 集成后的 code/test/config；禁止 `git add -A`。
7. 只有所有 operator gates 已经通过显式 resume 的真实 artifact 验收后，才捕获最终 `result_code_commit=HEAD`。
8. append `ai-work/executor/{stage_id}-executor.md` 的 E0 execution_record 和人类摘要，再 docs commit report。

## task_kind=repair（仅 routed v2）

1. repair 以 latest review 为默认基线；比较 review 后 commits/checkpoints/diff，LLM 判断哪些问题已完成、哪些仍需处理。普通 HEAD 漂移或 checkpoint 不完全匹配不单独构成停止条件。
2. 默认按 `repair_issue_ids` 拆 subplans；用户明确增加、替换或重定义 repair scope 时，以用户指令为准并记录 effective scope。resume/continue 只处理实际尚未完成部分。
3. worker issue_ids 不重叠、tracked write_scope 不重叠；全部 repair_issue_ids 恰好覆盖一次。
4. worker 做最小修复和定向测试；不提交。
5. coordinator 集成后运行受影响测试 + plan 中 executor-owned 的全局 regression/acceptance。全局测试只验证，不扩大 repair scope。若需要重跑受影响的 operator long gate，按 Operator terminal protocol 生成新的 checkpoint/script，禁止 coordinator/worker 直接执行。
6. coordinator commit 修复代码/测试；只有需要重跑的 operator gates 已通过显式 resume 的真实 artifact 验收后，才捕获最终 result_code_commit。
7. append En repair execution_record，再 docs commit report。同一 review_commit 只能产生一次 completed repair。

## Parallel filesystem isolation

worker 除 assigned tracked files 外不得写共享业务 artifact。pytest/cache/output/temp 若可能冲突：

- 使用每 worker 独立临时目录/输出路径；或
- 将共享生成/共享验证留给 coordinator 串行执行。

不要让多个 worker 并发写 `.coverage`、同一 output JSON、同一 cache DB 等共享状态。

## Execution record

Implementation：

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
  execution_backend: local_codex
  effective_execution_mode: multi
  workflow_runtime_commit: <required for active-stage workflow migration; otherwise omit>
  legacy_control_plane_default: true  # required with workflow_runtime_commit; otherwise omit
  status: completed
```

Repair：E1/E2/...；填整数 source_review_round、source_review_commit、repair_issue_ids，并同样记录 `execution_backend: local_codex`、`effective_execution_mode: multi`。

backend/effective mode 只用于审计，不参与 reviewer provenance 判定。active-stage workflow migration 时 `workflow_runtime_commit` 与 `legacy_control_plane_default=true` 必须成对记录，绑定本轮实际加载的 maintenance runtime；普通 stage 省略二者。若本次来自 resume，completed record 额外记录 `resumed_from_checkpoint_id` 与 `resumed_from_checkpoint_commit`。只有所有必须验收通过才标 completed。code commits 在前，report docs commit 在后。

## 边界

- 不修改 plan/review/proceedings/third_party；不 push。
- 不自行改 routing/model/effort。
- review 由 reviewer-ex；Git checkpoint/finalization 由 stage-lifecycle。

## 自检

- [ ] task_kind 互斥；
- [ ] 已执行当前 task 必要的 preflight；partial/incomplete 状态优先 continuation assessment，没有因缺少 exact checkpoint 或普通 SHA 漂移强制 retire；
- [ ] validation target=24GB 时全部真实 target gates 均由 operator boundary 承担；workers/coordinator 未启动 target command；actual handoff commit、tracked script SHA、target preflight/postcheck、evidence/artifact identity 可验证，普通 parent/source SHA 仅作审计；
- [ ] validation 的正式 checkpoint/result 只写 target persistent artifact_root；control plane 不要求挂载该 root，portable operator evidence 足以跨机器核验，真实 checkpoint/result 未写入 `.worktrees/...`；
- [ ] effective topology 基于真实依赖；MULTI 不足两 lane 时已合理降级/串行化并记录，而不是制造假并行；
- [ ] repair effective issue scope 已完整覆盖；用户未覆盖时默认覆盖 router issues，用户 override 时已记录新的 effective scope；
- [ ] worker tracked write_scope/临时输出互不冲突；
- [ ] coordinator 亲自完成整体验收与 commits；
- [ ] result_code_commit 在 report docs commit 前捕获；
- [ ] `.ai-bridge/**` 保持 ignored/untracked，workers/coordinator 没有把 transport state 纳入 tracked write_scope、staging 或 commit；
- [ ] completed execution_record provenance 完整；
- [ ] 未改 plan/review/proceedings，未 push。
