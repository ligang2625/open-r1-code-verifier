---
name: executor
description: Local Codex MULTI execution protocol。仅用于 execution-router backend=local；Sol/medium coordinator 将 routed implementation/repair 拆给 Luna/max workers，要求至少 2 个真实独立 lane，并写统一 v2 execution_record。不得重判 routing、不得 review/finalize。
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

本 skill **只支持 routed v2**。调用必须同时包含 `source_mode=multi`、`backend=local`、`task_kind`、`stage_id`、`plan_commit`；缺少任一项返回 `EXECUTOR_ROUTING_CONTEXT_INCOMPLETE`。不提供 legacy direct mode，也不自行从文件名/当前分支猜 execution source。

## Routed MULTI 前置

router 必须传：stage_id、绝对 worktree、plan path、plan_commit、`task_kind=implementation|repair`、`source_mode=multi`、`backend=local`、`stage_profile`、`control_plane_hardware`、`target_hardware`、`evidence_class`、`development_terminal`。`control_plane_hardware` 固定 GTX 1660 Ti；validation 普通 dispatch 不要求/传入 4090 roots。repair/resume 继续携带既有 review/checkpoint provenance；portable operator resume 传 `operator_handoff_mode/operator_gate_id/operator_restart_policy/operator_script/operator_script_sha256/target path templates/control-plane evidence directory/expected_artifacts`，legacy operator 兼容其旧 absolute fields。

`task_kind` 两条路径互斥；repair 完成后不得继续 implementation。

main 开始任何拆分/修改前先进入 stage worktree、读 plan/spec/代码和对应 routing source，并解析 `stage_profile / control_plane_hardware / target_hardware / evidence_class / development_terminal`，与 router 输入逐项一致。control plane 固定 GTX 1660 Ti；development target=GTX 1660 Ti+engineering；validation 固定 real-training/numerical+terminal=false，target 可为 GTX 1660 Ti（formal-evidence-only analysis）或 24GB GPU（含新的 target-GPU gates）。target=24GB 时全部 24GB acceptance 必须由 operator block 覆盖。workers/coordinator 始终只做 control-plane scope，fixture/mock/synthetic 不得满足真实 gate。普通 execution/resume HEAD/checkpoint guards 保持不变；任何业务修改/worker spawn 前 coordinator 串行执行 control-plane preflight。validation 不读取本机 4090 machine record、不要求 24GB GPU，也不解析 target roots。若有 operator gate，coordinator 负责集成、1660 Ti validation、tracked operator script/evidence contract；任何 worker/coordinator 都不得启动 target-GPU command。execution report 继续 append-only。

stage `.venv` 默认是 lifecycle 创建的 primary-dependency overlay。若任一 routed workstream 需要修改 `pyproject.toml` 或 `uv.lock`，必须由 coordinator 在 spawn 相关 worker/继续依赖测试前串行运行 `skills/stage-lifecycle/scripts/bootstrap_stage_env.py --primary-root <primary> --stage-worktree <stage> --mode full`，建立完整 stage-local pinned environment；之后全部 workers/tests 使用该 stage `.venv`，不能继续借 primary overlay 隐式满足依赖。

**Transport hard guard**：coordinator 在 spawn worker 或业务修改前必须确认 `git ls-files .ai-bridge` 为空；否则返回 `EXECUTION_TRANSPORT_TRACKED`。`.ai-bridge/**` 不得进入 worker tracked write_scope。所有 coordinator code/test/config/report commits 都显式暂存目标文件，并在 commit 前确认 staged path 不包含 `.ai-bridge/**`。

## 环境中断 checkpoint / resume

仅当 coordinator 已经集成并 commit 了可保留的部分 workstreams/repair，stage clean，随后遇到无需修改 tracked 仓库即可修复的环境/基础设施故障时，才允许暂停。源码 lint/type/test failure、tracked config/dependency bug 或 acceptance 逻辑失败不是 environment interruption。

暂停时 coordinator 捕获 partial `result_code_commit=HEAD`，在 execution report EOF 追加 `execution_checkpoint(version=1, checkpoint_id=Cn, task/source provenance, result_code_commit, interruption_class=environment, resume_allowed=true, failed_command, blocker, completed_scope, remaining_scope, status=interrupted)`，只提交 report docs commit，并返回 `EXECUTION_ENV_INTERRUPTED`。checkpoint docs commit 的 parent 必须是 result_code_commit；不得 checkpoint 未 commit 的 worker diff，也不得自动 retire。

resume 必须来自 router 的 current-head checkpoint。coordinator 不重新执行 completed_scope 对应的已提交 lanes，只为 remaining_scope 重新形成需要的 worker tasks；原 source MULTI routing 不改变。允许重新跑 plan preflight、受影响测试与最终 acceptance。若环境仍坏且没有新 code commit，保持原 checkpoint；若 resume 后又产生新有效 commit 再被环境阻塞，可追加下一 Cn。完成后 execution_record 额外记录 `resumed_from_checkpoint_id/commit` 供审计。

## Operator terminal gate / resume

sealed validation plan 只有在 `target_hardware=24GB GPU` 时使用 operator block，且它覆盖全部 24GB acceptance gates。workers 只能实现/测试 control-plane workstreams；coordinator 集成后负责 tracked operator handoff，任何 worker/coordinator 都不启动 target-GPU command。

coordinator 预分配 checkpoint_id，生成唯一 tracked secret-free immutable `ai-work/executor/operator/<stage>/<gate>/<checkpoint>/run.sh`。script 在 4090 验证 exact checkpoint commit/parent/latest checkpoint/script SHA、clean tree、target machine READY、>=22528 MiB GPU、roots/model/data/cache/storage/lock，以及需要时唯一 `1660ti-wsl` Piston tunnel。它执行 start preflight → target command → sealed post-run acceptance；只有 `command_rc=0 && postcheck_rc=0` 才 `gate_status=passed`。每 attempt 生成 versioned evidence，绑定 stage/plan/operator-checkpoint/result-code/checkpoint/gate/script path+SHA、machine-record SHA、GPU/roots/Piston、timestamps、rc/status、formal run 与 expected-artifact inventory/hashes。

coordinator 计算 script SHA，append portable operator checkpoint，并显式记录 `operator_handoff_mode: portable_target`；一个 provenance commit 只提交 execution report + 该新 script，parent=result_code_commit。返回 `EXECUTION_OPERATOR_ACTION_REQUIRED` 时明确不自动 push：用户先经 Git 让 exact checkpoint commit 在 4090 可达，再 checkout/detach、clean-check、重算 SHA并运行 tracked script。exact-rerun/trainer-checkpoint/latest-valid Trainer checkpoint/strict-loader/quarantine/no-overwrite 语义保持。

operator resume 由 coordinator 在 1660 Ti 计算 received evidence SHA256并严格验证 schema/provenance、tracked script SHA、`command_rc=0/postcheck_rc=0/gate_status=passed`、formal artifact identity与 synced small-file hashes。required large-artifact property未被 evidence/postcheck证明时保持 checkpoint并要求短时只读 target check。成功 gate 的 evidence SHA256必须写入最终 completed execution record；环境故障保持 current checkpoint/HEAD，无合法 trainer checkpoint或 tracked bug 时按原 MULTI routing 最小修复并 quarantine旧 run。

## Anti-fake-parallel hard guard

routed MULTI 必须基于真实代码形成 ≥2 个 mutually independent subplans：tracked write file/symbol ownership 可分离、无未完成 public API 前置依赖、各自有独立测试。

若只能形成 1 个：不 spawn worker、不实现，返回 `ROUTING_MISMATCH`；不得退化为 Sol coordinator + 1 Luna。

- implementation：复核 plan candidate `steps`。
- repair：只复核/拆分 router 的 `repair_issue_ids`，worker issue 并集必须恰好等于这些 IDs。

## task_kind=implementation（仅 routed v2）

1. 确认 report 不存在 matching completed E0。普通 execution 要求 stage `HEAD == plan_commit`；resume 要求 `HEAD == resume_checkpoint_commit`，并从 remaining_scope 恢复，不重新执行 completed_scope。其它 HEAD 前进停止并报告 unknown incomplete implementation。
2. 普通 execution 按 plan steps 拆独立 subplans；resume 只为 remaining_scope 中尚未完成的 lanes/集成工作拆任务，sealed routing 本身不改。
3. 每个 worker 任务必须自包含：worktree、plan、assigned steps、唯一 tracked write_scope、禁止项、定向测试、汇报格式。
4. workers 只改 assigned tracked scope，不 stage/commit、不写总报告。
5. coordinator 汇总 diff、解决集成顺序、亲自运行定向 + executor-owned 全局短时验收。若下一步命中 operator long gate，转入 Operator terminal protocol，禁止直接执行长命令。
6. coordinator 按独立 subplan 显式暂存并 commit 集成后的 code/test/config；禁止 `git add -A`。
7. 只有所有 operator gates 已经通过显式 resume 的真实 artifact 验收后，才捕获最终 `result_code_commit=HEAD`。
8. append `ai-work/executor/{stage_id}-executor.md` 的 E0 execution_record 和人类摘要，再 docs commit report。

## task_kind=repair（仅 routed v2）

1. 普通 repair 开始修改前 stage HEAD 必须等于 router `review_commit`；resume repair 要求 `HEAD == resume_checkpoint_commit`，且 checkpoint 精确绑定同一 review round/commit/issues。其它状态停止。
2. 普通 repair 只按 `repair_issue_ids` 拆 subplans；resume 只处理 remaining_scope 中尚未完成的 repair lanes。其它 review finding/plan step 不自动进入 scope。
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
  status: completed
```

Repair：E1/E2/...；填整数 source_review_round、source_review_commit、repair_issue_ids，并同样记录 `execution_backend: local_codex`、`effective_execution_mode: multi`。

backend/effective mode 只用于审计，不参与 reviewer provenance 判定。若本次来自 resume，completed record 额外记录 `resumed_from_checkpoint_id` 与 `resumed_from_checkpoint_commit`。只有所有必须验收通过才标 completed。code commits 在前，report docs commit 在后。

## 边界

- 不修改 plan/review/proceedings/third_party；不 push。
- 不自行改 routing/model/effort。
- review 由 reviewer-ex；Git checkpoint/finalization 由 stage-lifecycle。

## 自检

- [ ] task_kind 互斥；
- [ ] Execution preflight 在首次/恢复后的新业务修改或 worker spawn 前完成；baseline preflight 失败未产生业务 commit/report；已有 partial commits 后的 environment interruption 如需暂停，已写合法 checkpoint 而不是强制 retire；
- [ ] validation target=24GB 时全部 24GB gates 均由 operator boundary 承担；workers/coordinator 未启动 target command；tracked script/commit-parent/diff/SHA、target preflight、mandatory postcheck、atomic status/append-only log、trainer checkpoint/quarantine 均正确；resume 已验证 evidence schema、command/postcheck/gate_status 与 evidence SHA，并把成功 gate 的 evidence SHA 写入 completed record；
- [ ] validation 的正式 checkpoint/result 只写 target persistent artifact_root；control plane 不要求挂载该 root，portable operator evidence 足以跨机器核验，真实 checkpoint/result 未写入 `.worktrees/...`；
- [ ] routed MULTI ≥2 真实 subplans，否则已 ROUTING_MISMATCH；
- [ ] repair worker issue 并集恰好等于 repair_issue_ids；
- [ ] worker tracked write_scope/临时输出互不冲突；
- [ ] coordinator 亲自完成整体验收与 commits；
- [ ] result_code_commit 在 report docs commit 前捕获；
- [ ] `.ai-bridge/**` 保持 ignored/untracked，workers/coordinator 没有把 transport state 纳入 tracked write_scope、staging 或 commit；
- [ ] completed execution_record provenance 完整；
- [ ] 未改 plan/review/proceedings，未 push。
