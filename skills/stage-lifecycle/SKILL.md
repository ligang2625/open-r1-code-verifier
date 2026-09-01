---
name: stage-lifecycle
description: Git stage lifecycle control plane。负责 bootstrap_plan、checkpoint_review、finalize、retire_incomplete，但把普通 commit/SHA 视为审计 anchors 而非不可变状态锁；main/stage 漂移先由 LLM判断语义兼容性，partial stage 优先 continuation，只有明确放弃或不可恢复才 retire。保留 stage identity、review coverage、operator evidence 等必要完整性边界。
---

# Stage Lifecycle

## 目标

本 skill 是 execution-environment-agnostic 的 Git lifecycle 控制面。只要当前环境能够读写仓库并执行所需 Git/worktree 操作，就可以由 Local Codex 或 Web GPT + CodexPro 运行；**不需要也不接受 backend/environment 参数**。生命周期默认遵循 sealed plan，但 sealed plan 是执行基线而不是不可修改协议：用户明确指定的新方案、实现方式或恢复策略优先于旧 plan。支持四个互斥操作：

1. `bootstrap_plan`：把 planner-ex 已完成的计划 handoff 封存为阶段分支上的最终 plan；
2. `checkpoint_review`：把 reviewer-ex 已写好的最新审查轮次做 stale-check 后提交到阶段分支；
3. `finalize`：仅在最新 review 通过后合并到 `main`、更新 proceedings/finalization record，最后清理 worktree/branch；若 plan 是终结型 development stage，同时写 Development Complete Record；
4. `retire_incomplete`：只作为明确 abandon path；先由 LLM 根据当前代码/history/tests 判断 continuation 是否仍可行，只有用户明确放弃或确认状态不可恢复时才归档退出 active stage。

本 skill **不实现业务代码、不修改 routing 决策、不执行 review、不创建 execution agent、不自动 push**。四个 operation 在 Web/Local 环境中的输入、校验、Git mutation、错误码与输出必须完全相同。

四个 operation 都以**主仓库 root checkout** 为 control-plane 起点。若调用发生在 linked stage worktree，先解析主仓库 root/primary checkout，再从 root 执行生命周期操作；不得在主 checkout `git switch` 到已被 worktree 占用的 stage branch。

### Transport-state policy

主仓库与所有 stage worktree 下的 `.ai-bridge/**` 都是 Web/Local agent 之间的**本地传输层状态**，不是 stage/repository artifact。它们必须由 `.gitignore` 排除，并且所有 branch 上都必须保持 **zero tracked paths**。

- 每个 lifecycle operation 的 preflight 都先确认 primary checkout 的 `git ls-files .ai-bridge` 为空；涉及既有 stage worktree 时，同样确认该 stage 没有 tracked `.ai-bridge/**`。任一非空返回 `STAGE_TRANSPORT_TRACKED`，不得继续 Git mutation。
- `.ai-bridge/**` 的 ignored 本地变化不参与 primary/stage cleanliness 判定；正常 `git status` 本就不会把它们计入 dirty scope。
- lifecycle 永远不 stage/commit `.ai-bridge/**`，也不需要为 merge 对它们执行 stash/reset/restore。唯一允许的 lifecycle mutation 是 `bootstrap_plan` seal 成功后删除 ignored 的 `.ai-bridge/current-plan.md` 以消费 pending handoff；其它 transport 文件原样保留。
- plan/execution/review/proceedings 等 authoritative provenance 只能位于其正式 repository artifact 路径。若 executor/reviewer 曾把 transport state 写入 Git history，应先修复该 workflow state，不能依赖 finalize 的 merge fallback 吞掉它。

Routing compatibility marker: `execution-routing-v2`。

### Stage environment contract

每个 linked stage worktree 都必须拥有自己的 `.venv/bin/python`，且 project editable source 必须指向**当前 stage worktree**，不能直接把 primary checkout 的 `.venv` 目录软链接进 stage。原因是 primary `.venv` 的 editable install 指向 `main` 源码，直接复用会导致 stage 测试实际执行错误 checkout 的代码。

默认 bootstrap 使用仓库内 `skills/stage-lifecycle/scripts/bootstrap_stage_env.py --mode overlay`：

- primary `.venv` 提供已经安装并验证过的 pinned 第三方依赖；
- stage worktree 创建独立 lightweight `.venv`，通过只读 site-packages overlay 复用 primary dependencies；
- `open-r1-code-verifier` 与 `third_party/open-r1` 在 stage `.venv` 中重新 editable-bind 到当前 worktree；
- 对依赖 venv-local executable 的开发工具不能只靠 site-packages overlay。当前至少把 primary 中 pinned 的 `ruff` 版本以 `--no-deps` 安装进 stage `.venv`，并验证 `python -m ruff`、`python -m mypy`、`python -m pytest` 都能从 stage runtime 启动；
- stage submodule 在环境创建前执行 `git submodule update --init --recursive third_party/open-r1`；primary submodule 可用时使用它作为本地 `--reference`，避免每个 stage 重复网络 clone；
- bootstrap 必须验证 `code_verifier.__file__` 与 `open_r1.__file__` 都位于当前 stage worktree 下。

若某个 execution 实际修改 `pyproject.toml` 或 `uv.lock`，从该修改开始不得继续依赖 primary overlay；executor 必须在 stage 中运行同一 helper 的 `--mode full`，建立完整独立 pinned environment 后再继续测试。普通不改依赖的 stage 不重复下载/安装整套 CUDA/PyTorch 环境。

### Resumable execution checkpoint contract

`execution_checkpoint` 支持两类明确、可恢复的暂停：**environment interruption** 与 **operator target-GPU handoff**。二者都要求生成 checkpoint 前 stage 对所有非 ignored repository artifact 已 clean。environment checkpoint 仍只追加 execution report 并单独 docs commit；新 portable operator checkpoint 允许同一个 provenance commit **只修改 execution report + 新增恰好一份 tracked secret-free operator script** `ai-work/executor/operator/{stage_id}/{gate_id}/{checkpoint_id}/run.sh`。其它未知 HEAD 前进仍是 `INCOMPLETE_UNKNOWN`。

#### Environment interruption

环境/基础设施故障不再自动等价于“必须退役 stage”。如果 execution 已经产生了有效的部分 code/test/config commits，随后因为**无需修改 tracked 仓库内容即可修复**的外部环境问题停止，executor 可以把当前进度封存为 committed `execution_checkpoint`；用户修好环境后，再显式要求 `$execution-router resume` 从该 checkpoint 继续。

可判定为 `interruption_class=environment` 的常见情况包括：stage `.venv`/tool 安装缺失或损坏、外部 Piston/service 暂时不可达、CUDA/runtime/device 临时不可用、模型 cache/network/credential/artifact-root permission 等运行环境问题。以下情况**不是**环境中断：ruff/mypy/pytest 已正常运行后发现的源码 lint/type/test failure、tracked config 错误、当前实现引入的 dependency contract 错误、模型/指标结果不满足 acceptance。只要修复需要修改 tracked source/config/test/lockfile，就继续按正常 execution 修代码，不能伪装成 environment checkpoint。

Environment checkpoint 至少记录 `version/stage_id/checkpoint_id/task_kind/source_plan_commit/source_review_round/source_review_commit/repair_issue_ids/result_code_commit/interruption_class/resume_allowed/failed_command/blocker/completed_scope/remaining_scope/status`；其中 `interruption_class=environment`、`resume_allowed=true`、`status=interrupted`，且 `failed_command/blocker/remaining_scope` 非空。它只允许在已经存在本次 task 的有效部分 code/test/config commit 后创建；若环境问题发生在任何业务 commit **之前**，HEAD 保持 plan/review baseline，不写 checkpoint，修好环境后普通重新调用 router 即可。

#### Operator terminal handoff

当 effective validation contract 的 `target_hardware=24GB GPU` 时，全部 target-GPU acceptance gates 必须经过 operator boundary；这是硬件/证据安全边界，不因 sealed plan override 而绕过。control-plane executor 不得自己启动 target-GPU command。每个 gate 需要明确 restart policy；SFT/GRPO 默认使用 trainer checkpoint。executor 生成 tracked、immutable、无密钥的 operator script，记录 repo-relative path/SHA256、target templates、expected artifacts 与 evidence contract。checkpoint commit 应尽量窄，但不要求为了“只含 report+script”的形式拒绝可解释且不改变待运行业务代码的 provenance/docs 变化。

新生成的 portable target Operator checkpoint 至少记录公共 provenance 字段以及 `interruption_class=operator`、`resume_allowed=true`、唯一 `operator_gate_id`、`operator_handoff_mode=portable_target`、**repo-relative tracked** `operator_script`、64-hex `operator_script_sha256`、target status/log/evidence templates、非空 `expected_artifacts`、control-plane evidence 接收目录、`completed_scope`、非空 `remaining_scope`、`status=awaiting_operator`。`result_code_commit` 是代码 provenance anchor；不要求 checkpoint commit 的 parent 机械等于它，只要 lifecycle/LLM 能确认 checkpoint 所运行的 tree 包含预期代码且没有未说明的业务漂移。4090 上仍必须验证 working tree clean、current HEAD 是被 handoff 的 checkpoint+script commit，并重算 tracked script SHA；这些是跨机器执行完整性的必要校验。

active-stage migration 的 reviewer-authorized repair 另允许 `operator_handoff_mode=control_plane_manual`，但只允许 task_kind=repair、命令本身不需要新的 24GB GPU execution，并且 review/用户意图能明确证明这是所需 repair path。它仍使用 tracked script + script SHA 和独立 evidence；workflow_runtime/review/result_code commit 用作审计 anchor，不要求普通 parent SHA 关系机械相等。它不得替真正 target-GPU gate，也不得伪造历史 formal evidence。

`portable_target` 的 target script 必须执行 start preflight → target command → post-run acceptance，并写 versioned secret-free `operator-evidence.json`。严格 identity 只保留证明**实际运行对象和结果**所需的字段：handoff checkpoint commit、stage/gate/script path + script SHA、target machine/runtime identity、`command_rc/postcheck_rc/gate_status`、formal run identity 与 required artifact hashes/inventory。plan/review/result-code/workflow-runtime 等普通 commit SHA 可保留为审计 anchors；有漂移时检查 lineage/diff，不要求逐字段机械相等。resume 计算 received evidence SHA 并验证 gate 仍适用于当前 effective contract；大型 checkpoint 不默认复制，证据不足时才做短时只读 target check。

- `INTERRUPTED_ENV` 与 `AWAITING_OPERATOR` 都可以显式 `execution-router resume` 恢复。其它 partial/incomplete 状态也应先由 LLM 根据当前代码、execution report、测试和用户意图判断是否可继续；retire 是明确放弃或确认不可修复时的 abandon path，不是未知状态的默认恢复方式。
- checkpoint commit 本身由 Git 历史推导，不在 record 内自引用。`result_code_commit`/parent 关系主要用于审计；environment checkpoint 不因普通 parent 漂移失效。operator checkpoint 仍要求 checkpoint tree 中的 tracked script/evidence contract 可唯一识别且 script SHA 正确，但不把 parent SHA 等式本身当成必要完整性条件。

## 通用 stage identity

Open-R1 使用完整 `stage_id` 作为所有阶段 artifact 的唯一键：

- 未拆分：`WP5`
- 拆分：`WP5-a`、`WP5-b`
- 开发收口：`DEV-CLOSEOUT`（branch `chore/dev-closeout`，worktree `.worktrees/dev-closeout`）
- plan：`ai-work/planner/{stage_id}-plan.md`
- execution report：`ai-work/executor/{stage_id}-executor.md`
- review：`ai-work/reviewer/{stage_id}-review.md`
- branch：plan 元信息指定的 `feat/wp...`
- worktree：plan 元信息指定的 `.worktrees/wp...`

`WP3-a` 与 `WP3-b` 是不同 stage，绝不共用 execution/review artifact。

### Existing-stage resolution

`checkpoint_review` 与 `finalize` 使用与 execution-router/reviewer-ex 相同的 stage resolution：调用方显式提供 `stage_id` 时精确使用；未提供时，只在尚未合并的 active stage worktree **恰好 1 个**时自动采用。0 个候选返回 `STAGE_NOT_FOUND`；多个候选返回 `STAGE_AMBIGUOUS`。不得按最大编号、mtime、最近创建或文件排序猜 stage。`bootstrap_plan` 不使用这条自动解析规则，它始终以 handoff/plan payload 内的 stage metadata 为准。

**Active-stage workflow migration**：workflow maintenance 可以在 active stage 期间落地。优先用 clean maintenance worktree 加载新 runtime，避免无谓污染 stage；但 primary main 前移或 workflow_runtime_commit 变化不再因 SHA guard 自动破坏 stage。新 execution/review 应记录实际 workflow runtime anchor；若 main/stage 同时变化，LLM 检查这些变化是否与当前业务 scope 冲突。只有会改变被执行/审查代码语义、导致 provenance 无法归属时才阻塞。

## Operation A: bootstrap_plan

输入：planner-ex 的完整最终计划正文（优先来自主仓库 root 的 `.ai-bridge/current-plan.md` handoff；也可由调用方直接提供），其中必须包含 `stage_id`、`planning_base_commit`、目标 branch、worktree、最终 plan path、`stage_profile`、`control_plane_hardware`、`target_hardware`、`evidence_class`、布尔 `development_terminal` 与合法 `execution_routing.version: 1`。`control_plane_hardware` 固定为 `GTX 1660 Ti (6GB)`；development → target GTX 1660 Ti + engineering + terminal true/false；validation → real-training/numerical + terminal=false，target 根据 stage 是否包含新的 24GB execution 为 GTX 1660 Ti 或 24GB GPU。`DEV-CLOSEOUT` 必须是 development 且 terminal=true。

若来源是 `.ai-bridge/current-plan.md`，它是 transport envelope 而不是正式 plan：

- 若存在 `## Plan` wrapper，只取第一个 `## Plan` **之后**的完整 Markdown 作为 plan payload；
- `Updated`、`Workspace`、`Target agent`、handoff 标题与 `## Plan` 本身不得写入正式 plan artifact；
- `Workspace` 若存在，必须解析为当前主仓库 root，否则返回 `STAGE_HANDOFF_WORKSPACE_MISMATCH`；
- 找不到非空 plan payload、或 payload 缺少所需 metadata/routing 时返回 `STAGE_HANDOFF_INVALID`。

步骤分为只读 preflight 和 Git mutation；**preflight 全部通过前不得创建 branch/worktree**：

1. 完整校验 plan payload：`stage_id/planning_base_commit/branch/worktree/plan path` 必须互相一致；`stage_profile/control_plane_hardware/target_hardware/evidence_class/development_terminal` 必须存在，且 `control_plane_hardware` 固定为 `GTX 1660 Ti (6GB)`。development 固定为 `target_hardware=GTX 1660 Ti (6GB)` + engineering + boolean terminal；validation 固定为 real-training/numerical + terminal=false，但 `target_hardware` 可为 GTX 1660 Ti（只消费既有 formal evidence 做 aggregation/CI/analysis/report）或 24GB GPU（stage 含新的 target-GPU execution）。`DEV-CLOSEOUT` 只允许 `chore/dev-closeout` / `.worktrees/dev-closeout` / terminal=true，且 routing=SINGLE；terminal inventory/closeout gates 继续按原严格合同。若 validation `target_hardware=24GB GPU`，必须存在 `operator_terminal_execution.version:1,required:true` 且 gates 非空，并覆盖全部 24GB acceptance gates；每 gate 的 id/run_kind 唯一非空、`executor_runs_command:false`、restart policy 合法、expected artifacts 非空，SFT/GRPO 必须 `trainer_checkpoint`。若 validation target=GTX 1660 Ti，则不得包含需要 24GB execution 的 operator gate。每个 operator gate 正文必须同时定义 command template、tracked-script Git provenance/lock/status-log contract、operator-start preflight、operator post-run acceptance（strict loader/completed-status/metrics/artifact identity）、`command_rc/postcheck_rc/gate_status` success rule、versioned evidence schema、restart/quarantine 与 explicit resume。非法返回 `STAGE_HANDOFF_INVALID`，不得先创建 stage。
2. 若 `stage_profile=validation`，在创建 branch/worktree 前仍严格解析 `proceedings.md` 的 `## Development Complete Record` machine-readable block；不存在合法 completion marker 返回 `STAGE_DEVELOPMENT_NOT_COMPLETE`。**到此为止即可在 GTX 1660 Ti control plane 创建/seal validation stage**：bootstrap 不读取本机 `.ai-bridge/validation-machine.json`，不探测 4090 CUDA/VRAM，也不要求 target artifact/HF/data roots 已挂载。只有 `target_hardware=24GB GPU` 的 operator gate 才在 4090 target-start 时 fail closed 验证 READY record、>=22528 MiB GPU、persistent roots、exact model/data/cache；需要 Piston 时验证由 1660 Ti control plane 预先建立的 canonical reverse-forward loopback endpoint 与 exact runtime，不在 4090 启动旧 tunnel helper。control-plane-only validation 不制造这些要求。这样只移动机器验收时点，不放宽 formal evidence 要求。
3. 在当前 primary checkout 校验 v2 skill/discovery：`skills/execution-router`、`executor`、`executor-ex`、`executor-web`、`reviewer-ex`、`stage-lifecycle` 均存在且 marker 可解析；对应 `.agents/skills/` entry 必须可解析。`skills/stage-lifecycle/scripts/bootstrap_stage_env.py` 也必须存在。缺失返回 `STAGE_SKILL_VERSION_MISMATCH`。
4. 校验 control-plane primary execution environment：`<primary>/.venv/bin/python` 必须存在且 `uv` 可执行。缺失返回 `STAGE_PRIMARY_ENV_UNAVAILABLE`；不得先创建 stage worktree。这里不做 target 4090/24GB hardware check。
5. 按 **Transport-state policy** 确认 primary 没有 tracked `.ai-bridge/**`，并检查 main working tree / current HEAD 相对 `planning_base_commit` 的变化。planning_base 是 provenance anchor，不要求 current main 机械相等；若 main 已前移但变化与 plan scope/依赖兼容，可采用 current main 作为 effective base 并记录两者。只有 dirty/advanced 状态来源不明、与 stage 冲突或会使 plan 失效时返回 `STAGE_PRIMARY_DIRTY` / `STAGE_PRIMARY_ADVANCED`。
6. 枚举未合并阶段 worktree。若已有其它 active stage，返回 `STAGE_ACTIVE_EXISTS`。若正是同一 stage，仅允许**显式 pre-execution replan**且它仍处于纯 PLANNED 状态：没有 completed E0/review，stage tracked/untracked 状态干净，并且 `HEAD` 恰好等于当前 plan seal commit；plan seal 后已有其它 commit 时返回 `STAGE_REPLAN_NOT_CLEAN`。当新的 `planning_base_commit` 已前移时，这个窄场景允许 lifecycle 在确认 stage 与 `third_party/open-r1` submodule 都无本地修改后先执行 `git submodule deinit --all`，再使用 `git worktree remove --force <worktree>` 删除旧 worktree；这里的 `--force` 仅用于 Git 对“包含过 submodule 的 clean worktree”强制要求的删除语义，不允许跳过 cleanliness guard。仅在再次确认旧 branch HEAD 就是旧 plan seal、没有其它提交后删除旧 stage branch，再从新 base 重建。这不是 incomplete-stage rollback，也不得用于已有 execution/review 的 stage。
7. preflight 通过后，从经上一步确认兼容的 **effective base** 创建 plan 指定的 branch/worktree；通常是 current main。`planning_base_commit` 保留为规划时审计 anchor，不要求为了它回退 main。不得在 `main` 上写阶段文件，worktree 身份仍必须唯一且正确。
8. **在写 plan/commit plan seal 之前**创建 stage environment：使用 primary `.venv/bin/python` 执行 `skills/stage-lifecycle/scripts/bootstrap_stage_env.py --primary-root <primary> --stage-worktree <stage> --mode overlay`。必须成功初始化 pinned submodule、创建 worktree-local `.venv/bin/python`，验证 `code_verifier` / `open_r1` source path 都位于 stage worktree，并确认 stage-local `ruff` executable 以及 `python -m ruff/mypy/pytest` 均可启动。失败返回 `STAGE_ENV_BOOTSTRAP_FAILED`，不得写 plan seal；若 branch/worktree 是本次调用新建且仍无 tracked stage artifact/commit，先尽力正常 deinit 已初始化 submodule，再在确认 worktree 仍无 tracked stage 修改后使用 `git worktree remove --force` 清理这个临时 worktree，并删除尚未承载 stage history 的临时 branch，避免留下半初始化 active stage。
9. 只把上面解析出的 plan payload 写入阶段 worktree的 `ai-work/planner/{stage_id}-plan.md`，并快速确认 worktree 中上述 v2 skill/discovery 仍可解析；异常则停止，不继续 commit。
10. 仅暂存最终 plan 文件并提交：`docs: add {stage_id} plan`。该提交是 router 后续推导 `source_plan_commit` 的唯一 plan seal。
11. 仅在 plan seal commit 成功后，若输入来自 `.ai-bridge/current-plan.md`，删除该 `current-plan.md`，表示 pending handoff 已消费；正式 plan 从此只以 stage worktree 中的 sealed artifact 为准。其它 `.ai-bridge` 文件不动。
12. 报告 `stage_id`、`planning_base_commit`、branch、worktree 绝对路径、plan path、`plan_commit`，以及 stage `.venv/bin/python` 与 verified source bindings。不修改 `.ai-bridge` 之外的主仓库文件。

## Operation B: checkpoint_review

输入：可选 `stage_id`。reviewer-ex 已在阶段 worktree 写好但**尚未提交**最新 review round；若未提供 stage_id，按上面的 Existing-stage resolution 自动解析。

步骤：

1. 从主仓库 root 的 `git worktree list` 定位唯一 stage worktree，并验证其 branch 与 sealed plan metadata 一致；按 **Transport-state policy** 确认 primary/stage 都没有 tracked `.ai-bridge/**`；再定位 `ai-work/reviewer/{stage_id}-review.md`。不存在、有歧义或 transport 被 tracked 则停止。
2. 验证 review history append-only：若已有上一轮 committed review，则当前文件必须以该 committed 文件内容作为**字节级完整前缀**，只允许在 EOF 追加一轮新内容；不得改写/删除旧轮次。违反返回 `STAGE_REVIEW_HISTORY_REWRITTEN`。本次追加必须恰好包含 1 个新的 `review_record` 和同轮 1 个 `repair_routing`。
3. 解析最新 review record，要求至少有：
   - `review_record.version: 1`
   - `review_round`（正整数）
   - `source_execution_id`
   - `reviewed_head_commit`
   - `conclusion`
   - 同轮 `repair_routing.version: 1`
4. 比较 `reviewed_head_commit` 与提交 review 前的 current HEAD。相等是最清晰情况；若不相等，先检查中间 commits 是否只是已知 provenance/docs 或 reviewer 已明确纳入的用户 continuation。只有存在未审查的实质代码/配置变化或无法判断时才返回 `STAGE_REVIEW_STALE`。
5. 除 review 文件外原则上不应有未提交 repository artifact；若存在，只有能证明这些变化已被本轮 review 覆盖且会在 finalize 前形成可审计 commit 时才可继续，否则返回 `STAGE_REVIEW_DIRTY_SCOPE`。
6. `source_execution_id` 应能定位本轮的 execution provenance anchor；`reviewed_head_commit` 可以是该 execution report commit 的后续 descendant/current effective code HEAD，不要求二者 SHA 相等。无法确认 lineage/scope 时才视为 provenance invalid。
7. 校验 conclusion/required 和 repair scope 的语义一致性。routing 维度/schema 有缺失或形式差异时，可按 execution-router 的宽松规则 normalization；只有无法确定是否需要 repair、issue scope 或执行方式时才返回 `STAGE_REVIEW_CONTRACT_INVALID`。
8. review_round 默认单调递增，R2+ 默认关联上一轮 repair。source_review_round/commit SHA 有普通漂移时检查实际 issue/commit lineage；能唯一确认 repair 来源即可继续，只有 round/source 混淆时返回 `STAGE_REVIEW_SEQUENCE_INVALID`。
9. 仅暂存 review 文件并提交：`docs: add {stage_id} review round r{review_round}`。
10. 记录/报告 `review_commit=HEAD`。不要把 `review_commit` 自引用写回同一个 review record；router 通过 Git 历史推导它。
11. `repair_routing.required=true` → 状态 `REPAIR_REQUIRED`；`required=false` 且 conclusion=pass → 状态 `PASSED`。

## Operation C: finalize

输入：可选 `stage_id`；若未提供，按上面的 Existing-stage resolution 自动解析。

仅在最新**已提交** review 同时满足 `conclusion=pass` **且** `repair_routing.required=false` 时执行；二者不一致时返回 `STAGE_REVIEW_CONTRACT_INVALID`。

1. 阶段 worktree 在 finalize 时必须没有未审查的实质业务变化。latest review_commit / reviewed_head_commit 用于定位审查边界；若 review 后有额外 commits，LLM 检查它们是否仅为 review/provenance/docs 或已被 review 明确覆盖。只有存在未审查的代码/配置/验收变化时返回 `STAGE_FINALIZE_STALE`，不要求 parent/HEAD SHA 机械相等。
2. 按 **Transport-state policy** 确认 primary/stage 都没有 tracked `.ai-bridge/**`；检查 current main 相对 planning_base 的变化。main 前移本身不阻塞 finalize：若这些变化与 stage 可安全合并、不会使 review 结论失效，则在 current main 上 merge 并记录 original planning_base/effective merge base。只有冲突、语义失效或 provenance 无法判断时返回 `STAGE_PRIMARY_DIRTY` / `STAGE_PRIMARY_ADVANCED`。
3. 在主仓库执行 `git merge --no-ff <stage-branch> -m "feat: complete {stage_id} <标题>"`，捕获 `merge_commit`。
4. 合并后恢复 primary runtime 可直接执行的环境状态：
   - 若 stage 相对 `planning_base_commit` 改变了 `third_party/open-r1` gitlink，先在 primary 执行 `git submodule update --init --recursive third_party/open-r1`；
   - 若改变了 `pyproject.toml` 或 `uv.lock`，在 primary 执行 `uv sync --extra dev --extra gpu --extra training`，使主 `.venv` 与新 dependency contract 对齐；未改依赖时不得重复完整 sync；
   - 验证 primary `.venv/bin/python` 导入的 `code_verifier.__file__` 与 `open_r1.__file__` 都位于 primary checkout，而不是已存在/将删除的 stage worktree。失败返回 `STAGE_PRIMARY_ENV_SYNC_FAILED` 并停止 finalization docs，不伪造环境已可运行。
5. 在 `main` 上：
   - 按现有 Open-R1 proceedings 规则更新 `proceedings.md`；拆分 stage 先记录子阶段，最后一个子阶段再做 WP 聚合；
   - 若 sealed plan 为 `stage_profile=development` 且 `development_terminal=true`，再次确认 reviewer PASS 明确核验了完整 WP0–WP8 Development Completion Inventory 与 closeout gates，然后在 proceedings 追加唯一 machine-readable block：精确标题 `## Development Complete Record`，其后立即写 YAML fenced block，顶层 `development_complete_record` 至少包含 `version: 1`、`terminal_stage_id`、`review_commit`、`merge_commit`、`finalized_at`、`completion_inventory_verified: true`、`development_complete: true`。不得用其它标题/散文/示例代替，也不得由非 terminal stage 写 marker；
   - 在 `ai-work/reviewer/{stage_id}-review.md` 末尾追加 `Finalization Record`，至少写 `review_round`、`review_commit`、`merge_commit`、finalized_at/status；不改审查结论本身。
6. 仅在 merge 成功后提交上述 finalization 文档：`docs: finalize {stage_id}`（若触发 WP 聚合可使用对应 consolidate message）。若这是 terminal development finalize，提交成功后的当前 `main HEAD` 即 `development_complete_commit`；必须报告该 exact commit。**control plane 不迁移**：后续 validation planner/bootstrap 仍在 GTX 1660 Ti 上进行；只有具体 target-GPU gate 的 exact commit/operator handoff 才同步到 4090。lifecycle 不自动 push/传输代码。
7. 再次确认 primary/stage 均无 tracked `.ai-bridge/**`、stage worktree 对所有非 ignored repository artifact 严格干净、`third_party/open-r1` submodule 无本地修改、且 main 对所有非 ignored repository artifact 干净后，先在 stage worktree 执行 `git submodule deinit --all`，再使用 `git worktree remove --force <worktree>` 删除这个已证明 clean、但包含过 submodule 的 worktree，最后 `git branch -d <stage-branch>`；这个 `--force` 不能替代任何 clean guard。任一步失败就停止并报告当前状态，不自动 rollback、rebase 或重试。
8. 不自动 push。finalize 按正常 one-shot 流程执行，不额外设计自动恢复状态。

## Operation D: retire_incomplete

用途：当用户明确决定**放弃**一个 plan seal 后已有部分提交、但尚未完成对应 execution/review 的 stage 时，保留完整历史并退出 active-stage 状态，再由 planner 重新规划。它不是通用 rollback，也不是合法 resumable checkpoint 的默认恢复方式；`INTERRUPTED_ENV` 优先在环境修复后显式 resume，`AWAITING_OPERATOR` 优先在用户运行 exact terminal script 后显式 resume，只有用户决定不继续该 stage 时才 retire。

输入：必须显式提供 `stage_id` 和一条简短 `reason`，不得自动猜 stage。

只允许同时满足以下条件：

1. 目标 stage worktree/branch 与 sealed plan metadata 一致，plan_commit 可从 Git 唯一推导；
2. `HEAD != plan_commit`，说明确实已有 plan seal 后提交；若仍 `HEAD == plan_commit`，应使用允许的 pre-execution replan，不走 retire；
3. execution report **不存在任何** `status=completed, task_kind=implementation` 的 E0；
4. 不存在 committed review round；一旦已有 completed E0 或 review，必须继续正常 review/repair/finalize，不能 retire；
5. primary/stage 均无 tracked `.ai-bridge/**`；stage worktree 对所有非 ignored repository artifact 干净，且不存在非忽略 untracked 文件；主仓库 `main` 对所有非 ignored repository artifact 必须干净；
6. 当前没有其它 active stage worktree。

操作：

1. 记录 `plan_commit`、当前 `archived_head=HEAD`、原 branch/worktree 与 reason；
2. 确认 stage worktree 与 `third_party/open-r1` submodule 都无本地修改后，先执行 `git submodule deinit --all`，再使用 `git worktree remove --force <worktree>` 删除这个 clean、但包含过 submodule 的 worktree；这个 `--force` 不能替代 clean guard。失败则停止，不删除任何 branch；
3. 将原 stage branch直接重命名为 `archive/<stage-slug>-incomplete-<YYYYMMDD-HHMMSS>`，使 archive branch 精确指向 `archived_head`；不 cherry-pick、不 squash、不丢提交；
4. 在 `main` 的 `proceedings.md` 追加简短 **Incomplete Stage Retirement Record**：stage_id、plan_commit、archived_head、archive branch、reason、retired_at，并注明没有 completed E0/review、这些提交未被 main 接受；
5. 仅提交该 proceedings 更新：`docs: retire incomplete {stage_id}`；不合并 archive branch；
6. 报告 archive branch 与新的 `main HEAD`，明确下一步重新调用 planner-ex。planner 可以读取 archive diff/commit 作为参考，但新 stage 必须以新的 main HEAD 为 planning_base_commit 重新验收。

任何条件不满足返回 `STAGE_RETIRE_NOT_ALLOWED`。这个操作不处理 merge conflict、已 review stage、已 completed execution 或任意历史回滚。

## 状态守卫

- `PLANNED`：plan 已由 `bootstrap_plan` commit，尚无 completed implementation；plan_commit 是默认 baseline，current HEAD 有可解释的非业务变化时仍可视为 planned/ready。
- `INTERRUPTED_ENV`：存在可识别的 environment interruption/checkpoint 或等价 partial state；current HEAD 不必恰好等于 checkpoint commit。环境修复后优先 resume/continue。
- `AWAITING_OPERATOR`：存在尚未完成的 operator handoff。用于实际 target run 的 checkpoint commit/script 必须可唯一识别且 script SHA 正确；stage 当前 HEAD 可以因后续可解释 control-plane commits 前移，由 LLM 判断该 gate 是否仍适用。
- `INCOMPLETE_UNKNOWN`：无 completed E0/review，且 partial state 暂时不能直接由 formal checkpoint解释。router 必须先做 LLM continuation assessment；可恢复则 resume/continue，只有确认不可恢复或用户放弃才 retire/replan。
- `IMPLEMENTED`：execution report 已有 completed implementation record，等待 reviewer-ex；普通 provenance SHA 漂移不改变事实状态。
- `REPAIR_REQUIRED`：latest effective review requires repair，且尚无 completed repair 覆盖该 effective issue scope。
- `REPAIR_EXECUTED`：已有 completed repair，等待 reviewer 根据实际代码/issue lineage审查，不要求 source_review_commit SHA 机械相等。
- `PASSED`：latest review 结论为 pass 且没有未审查的实质 stage 变化；HEAD 不要求机械等于 review_commit。
- `FINALIZED`：已 merge + proceedings/finalization commit + cleanup。

任何操作只能执行与当前状态匹配的转移；不允许通过删除/覆盖报告来“重置”同一 stage。

## 禁止事项

- 不在 main 上实现阶段代码。
- 不允许任何 branch track 或 commit `.ai-bridge/**`；发现即返回 `STAGE_TRANSPORT_TRACKED`，不要通过 merge strategy、stash 或 reset 隐藏它。
- lifecycle 自身不擅自改写 plan/review routing；用户明确 override 由 execution/review 形成 effective contract 并记录，不要求回写 sealed artifact。
- 默认把 committed review 交给 router；用户明确要求使用 review 草稿时，必须保留其未 committed 身份并确保 stage/round/issues 可归属。
- PASS review 后若有新 stage commit，先判断是否包含未审查的实质变化；只有会影响 review 结论的变化才阻塞 finalize。
- 不自动 stash、rebase、`--no-verify` 或 push；仅 `bootstrap_plan` 已证明为纯 PLANNED、无 execution/review 的显式 pre-execution replan 可以删除旧 plan-only stage branch，其它场景仍禁止 force-delete。
- 不通过文件时间戳、最大编号或“最近创建”猜 stage；有多个候选必须报歧义。
