---
name: planner-ex
description: Web/CodexPro 规划入口。根据 Open-R1 规格、proceedings 与代码现状生成下一 stage 的函数级最终 plan 和 execution_routing；不做 Git mutation、不选择 execution backend。计划通过 handoff 交给 Web/Local 共用 stage-lifecycle bootstrap_plan 封存，再由 execution-router 在运行时选择 local/web backend。
---

# Planner Ex

## 目标与边界

本 skill 负责生成一个**完整、可执行、可验证、可路由**的 stage plan。它是 Web-side planning artifact producer，不负责 Git 生命周期：

- 不创建/删除 branch 或 worktree；
- 不 commit/merge/push；
- 不启动 executor；
- 不在 `main` 写最终 plan 文件；
- 最终 plan 交给共用 `stage-lifecycle bootstrap_plan` 写入并 commit；该 lifecycle 可由 Web GPT + CodexPro 或 Local Codex 执行。

planner-ex 必须以**主仓库 root checkout** 为工作区。它可以读取 `git worktree list` / branch / log 等只读状态，但不得进入已有 stage worktree 继续规划，也不得创建、删除、移动或修改任何 worktree/branch。

如果 CodexPro handoff 可用，优先把完整最终 plan 发布到 `.ai-bridge/current-plan.md`（例如 handoff_to_codex）；`.ai-bridge/**` 必须是 gitignored、zero-tracked 的本地传输层，不是仓库 stage artifact。planner 开始时若 `git ls-files .ai-bridge` 非空，返回 `PLANNER_TRANSPORT_TRACKED`，先修复 workflow state，不继续发布 handoff。handoff 工具可以在 plan 外增加 `Updated/Workspace/Target agent/## Plan` 等 transport wrapper；真正 payload 始终是完整 plan 正文。若 handoff 不可用，返回完整 plan 正文与 stage descriptor，供调用方传给 `stage-lifecycle`。

若规划开始时主仓库已经存在非空 `.ai-bridge/current-plan.md`，说明上一份 plan 仍待 bootstrap。默认返回 `PLANNER_PENDING_HANDOFF_EXISTS`，不要覆盖；只有用户明确要求替换这份 pending handoff 时才允许继续规划并覆盖它。

## 输入

1. `PROJECT_SPEC_Open-R1_CodeVerifier.md`：至少精读目标 WP 相关章节、§20 WP 注册表、§21 Code Review、§19 测试、§29 默认决策。
2. `proceedings.md`：确认已完成、部分完成、受阻阶段。
3. 当前 `src/`、`tests/` 与只读 Git/worktree 状态。
4. `references/plan-template.md`。

## Active-stage guard

规划下一 stage 前先记录 `planning_base_commit = main HEAD`，并快照当前 `git worktree list` 与相关 stage branches。然后枚举尚未合并的 stage worktree/branch。`archive/*` 这类无 linked worktree、仅用于保存已明确废弃/被新规格取代的历史 commit 的分支不是 active stage，不得因此阻塞规划；其它带 sealed stage plan 的未合并 worktree/branch 仍按 active stage 处理。

- 0 个 active stage：允许规划下一 stage；
- 1 个或多个 active stage：默认返回 `PLANNER_ACTIVE_STAGE_EXISTS`，不得规划后续 stage；
- 只有用户明确要求“重规划当前 stage”才允许进入 replan；replan 仅允许该 stage 仍处于纯 PLANNED 状态：没有 completed implementation record，且 stage `HEAD` 仍等于当前 plan seal commit。只要 plan seal 后已有任何其它 commit，就返回 `PLANNER_REPLAN_AFTER_EXECUTION`，不得覆盖原 plan，后续变化交给 execution/review 流程处理。

禁止按“最近创建”“最大 WP 编号”猜当前 stage。

## Stage identity

每个计划必须定义唯一 `stage_id`：

- 未拆分 WP：`WP5`
- 拆分：`WP5-a`、`WP5-b`
- 当所有 WP0–WP8 development deliverables 都已经由 finalized stage 覆盖、但 `proceedings.md` 尚无合法 machine-readable completion block 时，允许使用唯一特殊 stage：`DEV-CLOSEOUT`；它只执行开发收口验收，不新增业务功能。

规划开始时记录只读 Git 基线 `planning_base_commit = main HEAD`。并给出 proposed lifecycle metadata：

- `planning_base_commit`：`<main HEAD sha>`
- branch：`feat/wp5` 或 `feat/wp5-b`；`DEV-CLOSEOUT` 固定 `chore/dev-closeout`
- worktree：`.worktrees/wp5` 或 `.worktrees/wp5-b`；`DEV-CLOSEOUT` 固定 `.worktrees/dev-closeout`
- final plan path：`ai-work/planner/{stage_id}-plan.md`
- execution report path：`ai-work/executor/{stage_id}-executor.md`
- review path：`ai-work/reviewer/{stage_id}-review.md`
- `control_plane_hardware`：固定 `GTX 1660 Ti (6GB)`；表示 planner/reviewer/lifecycle/router 与默认短时 execution 所在机器，与 target hardware 正交。
- `development_terminal`：development stage 必填布尔值；只有该 stage 完成后 **WP0–WP8 的全部 development deliverables 都已被 finalized evidence 或本 stage 覆盖**时才为 `true`。validation stage 固定为 `false`。

完整 `stage_id` 是 artifact key。拆分 stage 不得共用 `WP5-executor.md` / `WP5-review.md`。

## 确定下一 stage

### Development-first stage selection

先阅读 proceedings 与规格 §20.0，把所有未完成交付按证据依赖分类，而不是简单选择“编号最小的未完成 WP”：

- `development`：生产代码、配置、CLI、adapter、artifact/checkpoint/resume、evaluation/aggregation/analysis 等能够在 GTX 1660 Ti/CPU + Piston + fixture/mock/synthetic evidence 上完成工程验收的工作；
- `validation`：必须依赖**正式 evidence**才能成立的 gate，例如正式规模数据、真实 SFT/GRPO run/checkpoint、正式 A–D 数值或基于这些 artifacts 的最终统计/报告。validation 描述证据级别，不等价于 24GB execution：若本 stage 只消费已经产生的 formal artifacts 做 aggregation/CI/error analysis/report，则 `target_hardware` 应为 GTX 1660 Ti；只有需要新执行真实模型/GPU 计算的 gate 才把 `target_hardware` 设为 24GB GPU。

选择规则：

1. 只要还有 dependency-ready 的 `development` 工作，就**必须优先规划 development stage**。较早 WP 只剩 deferred validation gate 时，不得因为它“未完全完成”而阻塞较晚 WP 的可独立开发工作。
2. 典型例子：WP6 真实 SFT/B 数值尚未完成时，仍可继续规划 WP7 的 GRPO adapter/reward/config/CLI/resume 开发；真实 B checkpoint 尚不存在时，仍可规划 WP8 的 aggregation/error-analysis tooling，并用 deterministic fixture 验证 schema/计算。
3. development stage 的缺失 24GB GPU、正式训练数据、真实 checkpoint **不是 blocker**；plan 不得要求 executor 为了 completed E0 去运行真实 SFT/GRPO。对 `train-sft`/`train-grpo` 的 1660 Ti fail-closed hardware guard 可以作为开发测试证据。
4. fixture/mock/synthetic 可以满足 development-stage contract test，但 plan 必须明确禁止把这些 artifact 记录为正式 B/C/D checkpoint、研究指标、训练成本或 final validation evidence。
5. terminal 判定不能只看“当前是否还有 dependency-ready 工作”。Planner 必须建立 **Development Completion Inventory**，逐项覆盖 WP0–WP8 的 development deliverables；每个 WP 恰好一项，状态只能是 `finalized` 或 `covered_by_this_stage`，并给出 proceedings/finalized stage 或当前 plan step 的证据。只有 inventory 全覆盖时才允许 `development_terminal: true`。`DEV-CLOSEOUT` 中所有 WP 都必须已经是 `finalized`，不能用它补做缺失功能。
6. 只有 `stage-lifecycle finalize` 已因一个 terminal PASS stage 在 `proceedings.md` 写入**合法结构化 completion block**后，才允许规划 `validation` stage。合法 block 必须位于精确标题 `## Development Complete Record` 下、紧随一个 YAML fenced block，且顶层键为 `development_complete_record`、`version: 1`、`development_complete: true`、`completion_inventory_verified: true`，并含 terminal stage/review/merge/finalized_at 字段；自然语言中出现同名词句不算 marker。
7. 从 development 切换到 validation 不再切换 control plane。terminal finalize 仍记录 `development_complete_commit`，但 validation 的 planner-ex/bootstrap/reviewer/routing 默认继续在 GTX 1660 Ti 上运行，且 4090 可以离线。Planner 必须按**本 stage 实际需要执行的新计算**选择 `target_hardware`：纯 formal-artifact aggregation/CI/error analysis/report 使用 `GTX 1660 Ti (6GB)`；只要 stage 包含任何必须在目标 24GB GPU 上执行的新 gate，就使用 `24GB GPU`。不得为了规划而实时连接或探测 4090；真正进入 target-GPU gate 时才在 4090 fail-closed 验证 READY record、CUDA/VRAM、model/data/cache/persistent roots。
8. validation stage 原则上只运行已冻结代码/配置并收集真实 evidence；若真实运行暴露实现缺陷，优先走该 validation stage 的 execution/resume 或 review/repair 闭环，修复后重新跑受影响 gate，不在训练机上顺手扩展功能或改变实验定义。
9. **所有**需要 `target_hardware=24GB GPU` 的 stage acceptance gate 都必须进入 Operator target-GPU boundary，不区分“短 smoke”还是“长训练”。这样 router 不需要第二条隐式 4090 dispatch 路径。短时但 4090-only 的 GPU smoke/数值验收使用 `restart_policy=exact_rerun`；optimizer-based SFT/GRPO 使用 `trainer_checkpoint`。**正式 evaluation 按动作拆分，不默认把整条 evaluation 留在 4090**：当 production staged-evaluation contract 可用时，只有加载模型/生成 completion 的 `generate-eval` 属于 target-GPU operator gate；生成 bundle 完整、hash/provenance 验收并同步后，`verify-eval`（local Piston）和 `aggregate-eval` 回到 GTX 1660 Ti control plane。plan 必须把 generation bundle 的 model/revision/checkpoint/seed/ordered-data/decode/Piston-definition/code/Open-R1/dependency/record-hash identity 写成跨机器 contract，并禁止因为 `stage_profile=validation,target_hardware=24GB GPU` 就让 4090 等待 Piston。只有确实无法拆分且模型计算与验证不可分离的 legacy gate 才允许整段 target-GPU evaluation，并必须在 plan 中解释原因。executor 在 1660 Ti 负责代码/配置、control-plane preflight、lint/unit/CPU/Piston/其它非 4090 short tests 与 tracked operator script 生成；到 target-GPU gate 时提交 operator checkpoint并停止，用户在 4090 手工运行后显式 `$execution-router resume`。只有不需要目标 24GB GPU 的命令才继续由 control-plane executor运行。
10. 若一个 WP 同时包含 development 与 validation 内容，必须拆 stage，确保 development stage 可在 1660 Ti 上独立 completed；不得把 24GB gate 与开发代码绑定在同一个 E0 completion contract 中。
11. 若规模超过单 stage 上限，继续拆成连续 stage（如 `WP5-a`、`WP5-b`），但**不要仅因内部可并行而拆 stage**；每个 stage 必须有独立验收边界。

每份 plan 必须在元信息中明确：

- `stage_profile: development | validation`
- `control_plane_hardware: GTX 1660 Ti (6GB)`
- `target_hardware: GTX 1660 Ti (6GB) | 24GB GPU`
- `evidence_class: engineering | real-training/numerical`
- `development_terminal: true | false`

每份 plan 还必须包含一个 **Execution preflight** 小节，列出在首次业务修改/commit 前可由 control plane 完成的非破坏性环境检查及通过标准，例如 `1660ti-wsl` Piston、必要 Python imports、control-plane data/cache 与本 stage 真正需要的本地服务。**不要**把 4090 是否在线、4090 的 `.ai-bridge/validation-machine.json`、>=22528 MiB CUDA、4090 model cache 或 target persistent roots 放进 planner/bootstrap/control-plane Execution preflight；这些条件属于具体 target-GPU gate 的 operator-start short preflight。4090 若需要 Piston，唯一合法拓扑是通过 SSH local forward 把 `1660ti-wsl:127.0.0.1:2000` 映射为 4090 本机 `127.0.0.1:2000`，并在该 target-start preflight 验证 exact runtime。preflight 失败时 executor 必须在相应 plan/review baseline 停止；无法在实施前判定的逻辑/测试失败不强行塞入 preflight。

若 validation stage 的 `target_hardware=24GB GPU`，plan 必须包含唯一一份结构化 **Operator terminal execution** block（schema 名称为兼容性保留，语义覆盖所有 target-GPU gate，不只长任务），并为每个 gate 提供对应的命令模板/成功条件：

```yaml
operator_terminal_execution:
  version: 1
  required: true
  gates:
    - gate_id: base-a-formal
      run_kind: evaluation
      executor_runs_command: false
      restart_policy: exact_rerun
      expected_artifacts:
        - "$CODE_VERIFIER_ARTIFACT_ROOT/evaluation/<run-id>/run.json"
```

- `gate_id` 在 stage 内唯一；`run_kind` 为非空描述；`executor_runs_command` 固定 `false`；`restart_policy` 必须是 `exact_rerun | trainer_checkpoint`；`expected_artifacts` 非空，使用 `$CODE_VERIFIER_ARTIFACT_ROOT/...` 这类 **target-runtime template**，不得要求 control plane 已解析 4090 绝对路径，也不得指向 stage worktree。staged formal evaluation 的 target operator gate 通常只覆盖 generation bundle 并使用 `exact_rerun`；随后 control-plane `verify-eval`/`aggregate-eval` 不应伪装成 24GB gate。`train-sft` / `train-grpo` 必须使用 `trainer_checkpoint`。
- 每个 gate 的正文必须给出 executor 生成 `run.sh` 所需的**完整命令模板**、环境变量、成功/失败判据、resume 后需要核验的 artifact/identity，以及与 `restart_policy` 一致的失败恢复策略。必须同时定义：① **operator-start short preflight**：取得锁后、目标命令前重新验证 GPU/CUDA、Piston（如适用）、model/data/cache、persistent roots 与 bytes/inodes；② **operator post-run acceptance**：目标命令返回 0 后，在 4090 上立即执行短时 strict loader/completed-status/metrics-schema/artifact-identity 等 plan-specific 验证。只有 `command_rc=0` 且 `postcheck_rc=0` 才能产生 `gate_status=passed`；postcheck 失败必须让 script 非零退出并保留 evidence。存储阈值按本 stage 规模给出可判定规则；不得把真实机器绝对路径硬编码进 sealed plan，统一使用 `$CODE_VERIFIER_ARTIFACT_ROOT/$HF_HOME/$CODE_VERIFIER_DATA_ROOT`。
- operator handoff 必须是**Git 自包含且可跨机器执行**的。control-plane executor 生成唯一 tracked、immutable、secret-free `ai-work/executor/operator/{stage_id}/{gate_id}/{checkpoint_id}/run.sh`；operator checkpoint 记录 repo-relative script path、SHA256、target status/log/evidence templates 与 expected-artifact contract，并以一个 checkpoint commit 同时提交 execution report + **恰好这一份新 script**。`.ai-bridge/**` 仍完全不 tracked。operator action 必须提醒用户先通过 Git 让 exact checkpoint commit 在 4090 可达（例如 control plane push 后 target fetch；workflow 本身不自动 push），然后在 4090 checkout/detach 到 exact commit、确认 working tree clean、重新计算 script SHA256 并直接运行 tracked script；不存在权威的 out-of-band script copy。script 不硬编码 1660 Ti 路径，而从 target checkout/显式 `CODE_VERIFIER_TARGET_REPO` 解析当前 repo；它验证 current `HEAD` 就是包含 latest operator checkpoint 与自身的 commit、其 parent 等于 `result_code_commit`、该 checkpoint commit 只新增/修改本 stage execution report 与该 tracked script、latest checkpoint 的 stage/gate/checkpoint-id/script-path/SHA 与自身一致。随后验证 target-local `.ai-bridge/validation-machine.json`、READY/Piston identity、persistent roots 与 >=22528 MiB GPU，取得锁，执行 start preflight、target command 与 post-run acceptance。
- `restart_policy=exact_rerun` 时，环境故障可在**不改变 stage HEAD/checkpoint**的前提下重跑同一 immutable script，由底层 exact-prefix resume 验证 identity；`restart_policy=trainer_checkpoint` 时，同一个 script 必须在再次运行时检测 canonical run 是否已有合法同-run `checkpoint-*`，存在则自动把 latest numeric checkpoint 作为 `--resume-from-checkpoint` 传给 `train-sft/train-grpo`，从而保持 operator checkpoint commit / training `project_commit` 不漂移。已有 run 但没有合法 checkpoint 时必须 fail closed，不能删除/覆盖 run；若最高编号 checkpoint 在 Trainer 实际加载时被判为不完整/损坏，resume 诊断必须先把该 checkpoint 单独移动到 persistent quarantine 并记录，再保持同一 stage HEAD 重跑 script 让其退回前一个合法 checkpoint。
- 若失败需要 tracked source/config/test 修复，或 incomplete run 与新 code identity 不再兼容，旧 persistent run **不得删除或覆盖**；executor 必须先把它移动到 artifact root 下唯一 quarantine 路径并在 execution report 记录 original/quarantine path 与原因，再用新的 operator checkpoint/script 从 canonical run path fresh restart。没有 checkpoint 的早期中断也走同一 quarantine + fresh-restart 路径。
- executor 在 operator pause 前完成并 commit 所有应有的 tracked code/config/test；若该 validation stage 在 gate 前不需要任何 tracked 修改，也允许 operator checkpoint 的 `result_code_commit == plan_commit`（repair 时可等于 `review_commit`），不得为了制造 code commit 改文件。
- 每次 target attempt 都必须写 versioned、secret-free `operator-evidence.json`。最小字段绑定 `stage_id/source_plan_commit/operator_checkpoint_commit/result_code_commit/checkpoint_id/operator_gate_id/operator_script_path/operator_script_sha256`，target machine-record SHA256、GPU identity/VRAM、resolved roots、Piston identity（如 required）、attempt timestamps、`command_rc/postcheck_rc/gate_status`、formal run identity，以及 expected-artifact inventory（至少 path/size；identity/metadata artifacts 必须 SHA256）。只有 command + postcheck 都通过才能 `gate_status=passed`。用户把 evidence 与必要 status/log/manifest/metrics 小文件 byte-for-byte 同步回 control plane 后再显式 resume；resume 计算 received evidence SHA256、逐字段绑定 current checkpoint，并把该 SHA256 写入最终 completed execution record。大型 checkpoint 默认不复制；若 evidence/postcheck 不能证明某个 required large-artifact property，则在 PASS 前做一次短时只读 target check。用户口头结果或 exit code 单独永远不是 evidence。
- `target_hardware=GTX 1660 Ti (6GB)` 的 validation stage 不写该 block；`target_hardware=24GB GPU` 时该 block 必须覆盖全部 24GB acceptance gates，即使其中某个 gate 很短。

`development_terminal: true` 的 plan 必须包含结构化 `Development Completion Inventory`，并额外把 development closeout 全局 gate 写入总体验收：`make lint`、`make test`、`make test-gpu`、`make test-piston`（项目配置的真实 loopback Piston，0 failed/0 skipped）以及生产关键路径无 stub/TODO/fake implementation 的检查。`DEV-CLOSEOUT` 仅运行这些收口检查并写 execution evidence，不新增功能；其 routing 固定为 SINGLE，且允许 zero-code E0。

规模约束：通常实施步骤 ≤10、新模块 ≤8；超过或无法在一次可靠执行/验收中完成时拆分。

## 计划内容要求

计划必须：

- 精确到文件、函数/类完整签名；
- 逐步说明输入/输出/错误处理/调用关系；
- 保留规格已定义接口，不另造冲突签名；
- 每个步骤给测试文件、测试函数、断言与验证命令；
- 不确定外部 API/runtime 行为写入前置验证，不臆造；
- 不修改 `third_party/open-r1/`；Open-R1 访问只经 adapter；
- 实施步骤只依赖仓库文件、项目命令与执行 agent 自身文件/shell 能力，不依赖 MCP/其它 skill；
- validation plan 的真实 target-GPU 命令不得硬编码 stage-worktree 内的 `outputs/...` 或机器专属 `/data/...`；统一使用 `$CODE_VERIFIER_ARTIFACT_ROOT`、`$HF_HOME`、`$CODE_VERIFIER_DATA_ROOT` target-runtime variables，由 tracked operator script 在 4090 从 target-local machine record 解析并 fail closed 验证。纯 control-plane validation analysis 只可消费已同步的小型 formal evidence/允许的本地数据，不得伪造 target roots。真实 checkpoint/result 的唯一副本不得位于 `.worktrees/...`。
- validation plan 若声明 `operator_terminal_execution`，每个 gate 必须在实施步骤和总体验收中有明确的“executor prepare → committed operator checkpoint → user terminal run → explicit router resume → artifact validation”边界；不得让 executor 在首次 dispatch 中越过该 gate 直接运行长命令。

## Execution Routing Assessment

完整 plan 写完后再计算 routing。计划中包含且只包含一份：

```yaml
execution_routing:
  version: 1
  mode: single
  complexity: normal
  single_class: normal
  parallelizability: low
  multi_benefit: low
  independent_workstreams: 1
  rationale:
    - "..."
    - "..."
  workstream_candidates: []
```

### 三个独立维度

- `complexity`: `very_simple | normal | difficult_serial`，衡量单 agent 推理/调试强度；
- `parallelizability`: `low | medium | high`；
- `multi_benefit`: `low | medium | high`，必须考虑 coordinator/context/integration 成本。

### MULTI hard gate

只有以下全部满足才允许 `mode=multi`：

1. `complexity != very_simple`；
2. `parallelizability == high`；
3. `multi_benefit == high`；
4. 至少 2 个 substantive implementation workstream；
5. tracked write file/symbol ownership 基本互斥；
6. 无 lane 依赖另一 lane 尚未实现/定稿的 public API；
7. 每 lane 有独立、有意义的定向测试；
8. worker 完成后 coordinator 主要做集成验证，不需大量新 glue implementation。

“能并行”不等于“值得 MULTI”。多个很小 lane 仍用 SINGLE。

### SINGLE

- `very_simple`：机械、低风险局部实现，通常步骤≤3、生产/配置文件≤2、核心 public symbols≤4，且不涉及外部 runtime 探索、GPU/网络、事务/并发/状态机、checkpoint、安全、hidden-data、核心持久化格式、跨模块 public API 或关键真实 integration。
- `normal`：默认常规多文件实现/debug。
- `difficult_serial`：强串行高推理/调试风险。

SINGLE 时 `single_class == complexity`；`independent_workstreams` 填实际数量（可 >1），`workstream_candidates: []`。

MULTI 时 `single_class: null`；candidate 数量必须等于 `independent_workstreams`，每项含唯一 `id`、互不重叠 `steps`、互不重叠 tracked `write_scope`。candidate 只是证据，executor 仍按实际代码复核。

planner-ex 不写模型名/effort，也不选择 execution backend。`backend=local|web` 只由 execution-router 在每次 implementation/repair 调用时消费；sealed routing 只描述任务本身。single 模型映射只由 execution-router 维护。

## 输出与 handoff

最终产物是**完整 plan 正文**，使用 `references/plan-template.md`。完成后：

1. 自检 schema、范围、验收与 stage metadata；
2. 不写入 main 的 `ai-work/planner/`；
3. handoff 前再次确认 `main HEAD == planning_base_commit`，且 `git worktree list` / stage branch 集合与规划开始时一致；若 planner 运行期间出现新的 branch/worktree 或 primary HEAD 改变，返回 `PLANNER_GIT_STATE_CHANGED`，不要发布可执行 handoff；
4. 优先通过 CodexPro handoff 发布完整正文，并明确下一步：`$stage-lifecycle bootstrap_plan`；调用方可在当前 Web GPT + CodexPro 或 Local Codex 中执行同一个 lifecycle skill；
5. 若只能文本返回，必须同时返回 `stage_id / planning_base_commit / branch / worktree / final plan path`，供 bootstrap 使用。

`stage-lifecycle` commit 完 plan 后，execution-router 才能消费；未 seal 的 handoff plan 不可执行。

## 自检

- [ ] 无 active stage，或本次是明确且允许的 pre-execution replan；
- [ ] stage_id 唯一且完整，拆分 stage 使用 `WPn-a/b/...`；
- [ ] 已明确 `stage_profile / target_hardware / evidence_class / development_terminal`，development stage 不包含 24GB 真实训练 gate，validation stage 不接受 synthetic/mock 作为完成证据；
- [ ] 已写 control-plane Execution preflight，只包含当前 1660 Ti 实施前可判断的 Piston/import/local data-cache 等 blocker；target 4090 CUDA/model/cache/roots 没有被错误提前要求；
- [ ] validation target=1660 时只消费有 identity/hash 绑定的 formal evidence；target=24GB 时真实输出使用 target-runtime persistent `CODE_VERIFIER_ARTIFACT_ROOT` 语义，唯一 checkpoint/result 不在 stage worktree；
- [ ] validation target=24GB 时所有 24GB acceptance gates（包括短 smoke）均在合法 `operator_terminal_execution` block 中；每 gate 有正确 restart policy（SFT/GRPO=`trainer_checkpoint`）、tracked Git script provenance、target-start preflight、mandatory post-run acceptance、versioned evidence schema/evidence-SHA resume binding 与 quarantine/no-overwrite；
- [ ] 若仍有 development deliverable 未覆盖，没有错误标记 terminal；若 `development_terminal=true`，Development Completion Inventory 已逐项覆盖 WP0–WP8 且包含完整 closeout gates；
- [ ] 若将进入 validation，plan 仍在 GTX 1660 Ti control plane 发布/封存，并显式记录 `control_plane_hardware` 与 `target_hardware`；没有为了规划实时要求 4090 在线或 >=22528 MiB GPU，真正 target-GPU gate 的硬件/roots/Piston 检查已放入 operator-start preflight；
- [ ] 已记录 planning_base_commit，且与本次规划读取的 `main HEAD` 一致；
- [ ] plan/execution/review artifact 都使用完整 stage_id；
- [ ] 只覆盖一个可独立验收 stage；
- [ ] 每步函数级、可测试、可判定；
- [ ] 没有 plan 外范围蔓延或 `third_party/open-r1/` 修改；
- [ ] routing 三维独立评估，MULTI 通过 hard gate；
- [ ] plan 未写模型/effort；
- [ ] planner-ex 没有创建 worktree/branch、commit/merge/push，也没有在 main 写最终 plan；
- [ ] `.ai-bridge/**` 是 ignored/untracked transport，planner 没有把它纳入任何 Git artifact；
- [ ] planner-ex 前后的 primary HEAD、worktree 集合与 stage branch 集合一致；
- [ ] 最终正文已准备交给 `stage-lifecycle bootstrap_plan`。
