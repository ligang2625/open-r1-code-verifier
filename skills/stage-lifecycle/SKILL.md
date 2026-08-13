---
name: stage-lifecycle
description: Git stage lifecycle control plane。可由 Local Codex 或 Web GPT + CodexPro 共用；负责 bootstrap_plan、checkpoint_review、finalize、retire_incomplete 的同一套 Git/provenance contract。无 backend 参数，不调用 execution agent、不实现业务代码、不做 routing/review。
---

# Stage Lifecycle

## 目标

本 skill 是 execution-environment-agnostic 的 Git lifecycle 控制面。只要当前环境能够读写仓库并执行所需 Git/worktree 操作，就可以由 Local Codex 或 Web GPT + CodexPro 运行；**不需要也不接受 backend/environment 参数**。支持四个互斥操作：

1. `bootstrap_plan`：把 planner-ex 已完成的计划 handoff 封存为阶段分支上的最终 plan；
2. `checkpoint_review`：把 reviewer-ex 已写好的最新审查轮次做 stale-check 后提交到阶段分支；
3. `finalize`：仅在最新 review 通过后合并到 `main`、更新 proceedings/finalization record，最后清理 worktree/branch；若 plan 是终结型 development stage，同时写 Development Complete Record；
4. `retire_incomplete`：只处理“plan seal 后已有部分提交、但从未产生 completed E0/review”的常见半截 stage，保留完整历史到 archive branch 后退出 active stage，使 planner 可以重新规划。

本 skill **不实现业务代码、不修改 routing 决策、不执行 review、不创建 execution agent、不自动 push**。四个 operation 在 Web/Local 环境中的输入、校验、Git mutation、错误码与输出必须完全相同。

四个 operation 都以**主仓库 root checkout** 为 control-plane 起点。若调用发生在 linked stage worktree，先解析主仓库 root/primary checkout，再从 root 执行生命周期操作；不得在主 checkout `git switch` 到已被 worktree 占用的 stage branch。

### Primary checkout transport-dirty policy

主仓库 root 下的 `.ai-bridge/**` 是 Web/Local agent 之间的**传输层状态**，不是 stage/repository artifact。CodexPro handoff、status/log 更新可以在 lifecycle 调用前后修改其中的 tracked 或 untracked 文件。因此所有针对 primary checkout 的“working tree 必须干净”检查都按以下统一规则执行：

- 只要 `.ai-bridge/**` 之外存在 tracked 修改、staged 修改或非忽略 untracked 文件，仍视为 primary dirty，并返回原有 `STAGE_PRIMARY_DIRTY` / `STAGE_RETIRE_NOT_ALLOWED`；
- **仅** `.ai-bridge/**` 内存在 tracked/untracked transport 变化时，不得把它们视为 primary dirty，也不得因此阻止 `bootstrap_plan`、`finalize` 或 `retire_incomplete`；
- lifecycle 不自动 commit、stash、restore、reset 这些 transport 文件；除 `bootstrap_plan` seal 成功后消费 `.ai-bridge/current-plan.md` 外，其它 `.ai-bridge/**` 原样保留；
- 该例外只适用于 primary checkout。stage worktree 的 cleanliness/provenance guard 仍按各 operation 的原规则严格执行，不能用 `.ai-bridge` 例外掩盖 stage 内业务或 review dirty state。

Routing compatibility marker: `execution-routing-v2`。

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

## Operation A: bootstrap_plan

输入：planner-ex 的完整最终计划正文（优先来自主仓库 root 的 `.ai-bridge/current-plan.md` handoff；也可由调用方直接提供），其中必须包含 `stage_id`、`planning_base_commit`、目标 branch、worktree、最终 plan path、`stage_profile`、`target_hardware`、`evidence_class`、布尔 `development_terminal` 与合法 `execution_routing.version: 1`。profile 必须一致：development → GTX 1660 Ti (6GB) + engineering + terminal true/false；validation → 24GB GPU + real-training/numerical + `development_terminal=false`。`DEV-CLOSEOUT` 必须是 development 且 terminal=true。

若来源是 `.ai-bridge/current-plan.md`，它是 transport envelope 而不是正式 plan：

- 若存在 `## Plan` wrapper，只取第一个 `## Plan` **之后**的完整 Markdown 作为 plan payload；
- `Updated`、`Workspace`、`Target agent`、handoff 标题与 `## Plan` 本身不得写入正式 plan artifact；
- `Workspace` 若存在，必须解析为当前主仓库 root，否则返回 `STAGE_HANDOFF_WORKSPACE_MISMATCH`；
- 找不到非空 plan payload、或 payload 缺少所需 metadata/routing 时返回 `STAGE_HANDOFF_INVALID`。

步骤分为只读 preflight 和 Git mutation；**preflight 全部通过前不得创建 branch/worktree**：

1. 完整校验 plan payload：`stage_id/planning_base_commit/branch/worktree/plan path` 必须互相一致；`stage_profile/target_hardware/evidence_class/development_terminal` 必须存在并满足 development→GTX 1660 Ti (6GB)+engineering+boolean terminal、validation→24GB GPU+real-training/numerical+terminal=false；`DEV-CLOSEOUT` 只允许 `chore/dev-closeout` / `.worktrees/dev-closeout` / terminal=true，且 `execution_routing.mode` 必须为 `single`；`execution_routing.version: 1` 的其它字段必须满足 execution-router 基础 schema。terminal=true 时 plan 必须包含 `development_completion_inventory.version: 1`，WP0–WP8 恰好各一项、状态仅 `finalized|covered_by_this_stage` 且 evidence 非空；`DEV-CLOSEOUT` 的九项必须全部为 `finalized`。同时总体验收必须显式包含 `make lint`、`make test`、`make test-gpu`、`make test-piston` 及无 production-critical stub/TODO/fake implementation 检查。非法返回 `STAGE_HANDOFF_INVALID`，不得先创建 stage。
2. 若 `stage_profile=validation`，在创建 branch/worktree 前严格解析 `proceedings.md`：只接受精确标题 `## Development Complete Record` 后紧随的 YAML fenced block，顶层 `development_complete_record` 必须满足 `version: 1`、`development_complete: true`、`completion_inventory_verified: true`，并具有非空 terminal_stage_id、40-hex review_commit、40-hex merge_commit 与 finalized_at；其它自然语言出现这些词句一律忽略。不存在合法 block 返回 `STAGE_DEVELOPMENT_NOT_COMPLETE`。随后使用项目 `.venv` pinned PyTorch 验证 CUDA 可用且 device 0 total memory >=22528 MiB；否则返回 `STAGE_VALIDATION_MACHINE_HANDOFF_REQUIRED`，**不得在 1660 Ti 上创建 validation branch/worktree**。
3. 在当前 primary checkout 校验 v2 skill/discovery：`skills/execution-router`、`executor`、`executor-ex`、`executor-web`、`reviewer-ex`、`stage-lifecycle` 均存在且 marker 可解析；对应 `.agents/skills/` entry 必须可解析。缺失返回 `STAGE_SKILL_VERSION_MISMATCH`。
4. 按 **Primary checkout transport-dirty policy** 确认主仓库 `main` 在 `.ai-bridge/**` 之外 working tree 干净，且 `main HEAD == planning_base_commit`；否则返回 `STAGE_PRIMARY_DIRTY` 或 `STAGE_PRIMARY_ADVANCED`。仅 `.ai-bridge/**` transport 变化不阻塞 bootstrap；不 stash、不自动换基线。
5. 枚举未合并阶段 worktree。若已有其它 active stage，返回 `STAGE_ACTIVE_EXISTS`；若正是同一 stage，仅允许显式 replan 且它仍处于纯 PLANNED 状态：没有 completed E0，并且 `HEAD` 恰好等于当前 plan seal commit。plan seal 后已有其它 commit 时返回 `STAGE_REPLAN_NOT_CLEAN`。
6. preflight 全部通过后，才从 `planning_base_commit` 对应的当前 `main` 创建或复用 plan 指定的 branch/worktree；不得在 `main` 上写阶段文件。worktree 的绝对路径必须落在主仓库 `.worktrees/` 下且与 plan metadata 完全一致。
7. 只把上面解析出的 plan payload 写入阶段 worktree 的 `ai-work/planner/{stage_id}-plan.md`，并快速确认 worktree 中上述 v2 skill/discovery 仍可解析；异常则停止，不继续 commit。
8. 仅暂存最终 plan 文件并提交：`docs: add {stage_id} plan`。该提交是 router 后续推导 `source_plan_commit` 的唯一 plan seal。
9. 仅在 plan seal commit 成功后，若输入来自 `.ai-bridge/current-plan.md`，删除该 `current-plan.md`，表示 pending handoff 已消费；正式 plan 从此只以 stage worktree 中的 sealed artifact 为准。其它 `.ai-bridge` 文件不动。
10. 报告 `stage_id`、`planning_base_commit`、branch、worktree 绝对路径、plan path、`plan_commit`。不修改 `.ai-bridge` 之外的主仓库文件。

## Operation B: checkpoint_review

输入：可选 `stage_id`。reviewer-ex 已在阶段 worktree 写好但**尚未提交**最新 review round；若未提供 stage_id，按上面的 Existing-stage resolution 自动解析。

步骤：

1. 从主仓库 root 的 `git worktree list` 定位唯一 stage worktree，并验证其 branch 与 sealed plan metadata 一致；再定位 `ai-work/reviewer/{stage_id}-review.md`。不存在或有歧义则停止。
2. 验证 review history append-only：若已有上一轮 committed review，则当前文件必须以该 committed 文件内容作为**字节级完整前缀**，只允许在 EOF 追加一轮新内容；不得改写/删除旧轮次。违反返回 `STAGE_REVIEW_HISTORY_REWRITTEN`。本次追加必须恰好包含 1 个新的 `review_record` 和同轮 1 个 `repair_routing`。
3. 解析最新 review record，要求至少有：
   - `review_record.version: 1`
   - `review_round`（正整数）
   - `source_execution_id`
   - `reviewed_head_commit`
   - `conclusion`
   - 同轮 `repair_routing.version: 1`
4. reviewer 开始审查时记录的 `reviewed_head_commit` 必须等于**当前阶段 HEAD（提交 review 前）**。若不相等，说明审查期间代码/报告发生变化，返回 `STAGE_REVIEW_STALE`；不得提交该 review。
5. 除 review 文件外不得存在其它 tracked 修改或非忽略 untracked 文件；若存在返回 `STAGE_REVIEW_DIRTY_SCOPE`。reviewer 的一次性验证应放仓库外临时目录，不能把临时脚本/产物混入 stage。
6. `source_execution_id` 必须等于 execution report 最新 completed record 的 execution_id，且 `reviewed_head_commit` 必须等于提交该 record 的 `execution_report_commit`。
7. 完整校验同轮 repair contract：`repair_routing.source_review_round == review_round`；`conclusion=pass ⇔ required=false`，`conclusion=needs_repair ⇔ required=true`。required=false 时 routing 维度必须为 null、workstreams=0、issues/candidates=[]；required=true 时 `repair_issue_ids` 非空唯一，且 SINGLE/MULTI schema 满足 execution-router contract。否则返回 `STAGE_REVIEW_CONTRACT_INVALID`。
8. `review_round` 必须比已提交的上一轮恰好 +1；R2+ 的最新 execution 必须是 completed repair，且其 `source_review_round/source_review_commit` 精确指向上一轮 review。否则返回 `STAGE_REVIEW_SEQUENCE_INVALID`。
9. 仅暂存 review 文件并提交：`docs: add {stage_id} review round r{review_round}`。
10. 记录/报告 `review_commit=HEAD`。不要把 `review_commit` 自引用写回同一个 review record；router 通过 Git 历史推导它。
11. `repair_routing.required=true` → 状态 `REPAIR_REQUIRED`；`required=false` 且 conclusion=pass → 状态 `PASSED`。

## Operation C: finalize

输入：可选 `stage_id`；若未提供，按上面的 Existing-stage resolution 自动解析。

仅在最新**已提交** review 同时满足 `conclusion=pass` **且** `repair_routing.required=false` 时执行；二者不一致时返回 `STAGE_REVIEW_CONTRACT_INVALID`。

1. 阶段 worktree 必须干净，且当前 stage HEAD 必须恰好等于 latest `review_commit`；其父提交必须等于该 review record 的 `reviewed_head_commit`。任何 review 后的新提交都返回 `STAGE_FINALIZE_STALE`。
2. 按 **Primary checkout transport-dirty policy**，主仓库 `main` 在 `.ai-bridge/**` 之外必须干净，且 `main HEAD` 必须仍等于 plan 中的 `planning_base_commit`；否则返回 `STAGE_PRIMARY_DIRTY` 或 `STAGE_PRIMARY_ADVANCED`。仅 `.ai-bridge/**` transport 变化不阻塞 finalize；不 stash、不自动 rebase/换基线。
3. 在主仓库执行 `git merge --no-ff <stage-branch> -m "feat: complete {stage_id} <标题>"`，捕获 `merge_commit`。
4. 在 `main` 上：
   - 按现有 Open-R1 proceedings 规则更新 `proceedings.md`；拆分 stage 先记录子阶段，最后一个子阶段再做 WP 聚合；
   - 若 sealed plan 为 `stage_profile=development` 且 `development_terminal=true`，再次确认 reviewer PASS 明确核验了完整 WP0–WP8 Development Completion Inventory 与 closeout gates，然后在 proceedings 追加唯一 machine-readable block：精确标题 `## Development Complete Record`，其后立即写 YAML fenced block，顶层 `development_complete_record` 至少包含 `version: 1`、`terminal_stage_id`、`review_commit`、`merge_commit`、`finalized_at`、`completion_inventory_verified: true`、`development_complete: true`。不得用其它标题/散文/示例代替，也不得由非 terminal stage 写 marker；
   - 在 `ai-work/reviewer/{stage_id}-review.md` 末尾追加 `Finalization Record`，至少写 `review_round`、`review_commit`、`merge_commit`、finalized_at/status；不改审查结论本身。
5. 仅在 merge 成功后提交上述 finalization 文档：`docs: finalize {stage_id}`（若触发 WP 聚合可使用对应 consolidate message）。若这是 terminal development finalize，提交成功后的当前 `main HEAD` 即 `development_complete_commit`；必须报告该 exact commit，并明确：在 1660 Ti 上到此停止，不 bootstrap validation；先把该 commit 同步到 4090，再在 4090 安装 pinned training environment 并重新运行 planner-ex。lifecycle 不自动 push/传输代码。
6. 再次确认 stage worktree 严格干净、且 main 按 **Primary checkout transport-dirty policy** 在 `.ai-bridge/**` 之外干净后，正常移除 worktree，再 `git branch -d <stage-branch>`；任一步失败就停止并报告当前状态，不自动 `--force`、rollback、rebase 或重试。
7. 不自动 push。finalize 按正常 one-shot 流程执行，不额外设计自动恢复状态。

## Operation D: retire_incomplete

用途：处理最常见的“executor 已提交部分实现，但在 completed E0 之前因环境/测试 blocker 停止”的 stage。它不是通用 rollback，也不恢复执行进度；目标是**保留所有历史并退出 active-stage 状态，再由 planner 重新规划**。

输入：必须显式提供 `stage_id` 和一条简短 `reason`，不得自动猜 stage。

只允许同时满足以下条件：

1. 目标 stage worktree/branch 与 sealed plan metadata 一致，plan_commit 可从 Git 唯一推导；
2. `HEAD != plan_commit`，说明确实已有 plan seal 后提交；若仍 `HEAD == plan_commit`，应使用允许的 pre-execution replan，不走 retire；
3. execution report **不存在任何** `status=completed, task_kind=implementation` 的 E0；
4. 不存在 committed review round；一旦已有 completed E0 或 review，必须继续正常 review/repair/finalize，不能 retire；
5. stage worktree tracked 状态干净，且不存在非忽略 untracked 文件；主仓库 `main` 按 **Primary checkout transport-dirty policy** 在 `.ai-bridge/**` 之外必须干净；
6. 当前没有其它 active stage worktree。

操作：

1. 记录 `plan_commit`、当前 `archived_head=HEAD`、原 branch/worktree 与 reason；
2. 正常移除 stage worktree，不使用 `--force`；失败则停止，不删除任何 branch；
3. 将原 stage branch直接重命名为 `archive/<stage-slug>-incomplete-<YYYYMMDD-HHMMSS>`，使 archive branch 精确指向 `archived_head`；不 cherry-pick、不 squash、不丢提交；
4. 在 `main` 的 `proceedings.md` 追加简短 **Incomplete Stage Retirement Record**：stage_id、plan_commit、archived_head、archive branch、reason、retired_at，并注明没有 completed E0/review、这些提交未被 main 接受；
5. 仅提交该 proceedings 更新：`docs: retire incomplete {stage_id}`；不合并 archive branch；
6. 报告 archive branch 与新的 `main HEAD`，明确下一步重新调用 planner-ex。planner 可以读取 archive diff/commit 作为参考，但新 stage 必须以新的 main HEAD 为 planning_base_commit 重新验收。

任何条件不满足返回 `STAGE_RETIRE_NOT_ALLOWED`。这个操作不处理 merge conflict、已 review stage、已 completed execution 或任意历史回滚。

## 状态守卫

- `PLANNED`：plan 已由 `bootstrap_plan` commit，尚无 completed implementation execution，且 HEAD 仍等于 plan_commit。
- `INCOMPLETE`：无 completed E0/review，但 HEAD 已超过 plan_commit；只能显式 `retire_incomplete`，不能由 router 自动重跑整份 plan。
- `IMPLEMENTED`：execution report 已有 completed implementation record，等待 reviewer-ex。
- `REPAIR_REQUIRED`：最新 review 已 checkpoint，required=true，且该 review 尚未被 repair execution 消费。
- `REPAIR_EXECUTED`：execution report 已有 completed repair record，其 `source_review_commit` 指向上一轮 review commit，等待下一轮 reviewer-ex。
- `PASSED`：最新 review 已 checkpoint，`conclusion=pass` 且 `required=false`，stage HEAD 仍等于该 review commit。
- `FINALIZED`：已 merge + proceedings/finalization commit + cleanup。

任何操作只能执行与当前状态匹配的转移；不允许通过删除/覆盖报告来“重置”同一 stage。

## 禁止事项

- 不在 main 上实现阶段代码。
- 不修改 plan/review 的 routing 内容。
- 不把未 checkpoint 的 review 交给 router。
- 不在 PASS review 后有新 stage commit 的情况下继续 finalize。
- 不自动 stash、rebase、force-delete branch、`--no-verify` 或 push。
- 不通过文件时间戳、最大编号或“最近创建”猜 stage；有多个候选必须报歧义。
