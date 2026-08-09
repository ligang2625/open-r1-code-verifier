---
name: stage-lifecycle
description: 本地 Git 生命周期控制面。接收 planner-ex 的最终 plan handoff，创建/复用阶段 branch+worktree 并封存 plan；在 reviewer-ex 每轮审查后校验 provenance 并提交 review；审查通过后执行 merge、proceedings、finalization record 与 worktree/branch 清理。只做生命周期与 Git，不实现业务代码、不做 routing、不做 review。
---

# Stage Lifecycle

## 目标

本 skill 解决 Web planner/reviewer 与本地 Git mutation 的职责边界。它只在本地 Codex/具有 Git 写能力的环境中运行，支持三个互斥操作：

1. `bootstrap_plan`：把 planner-ex 已完成的计划 handoff 封存为阶段分支上的最终 plan；
2. `checkpoint_review`：把 reviewer-ex 已写好的最新审查轮次做 stale-check 后提交到阶段分支；
3. `finalize`：仅在最新 review 通过后合并到 `main`、更新 proceedings/finalization record，最后清理 worktree/branch。

本 skill **不实现业务代码、不修改 routing 决策、不执行 review、不创建 execution agent、不自动 push**。

Routing compatibility marker: `execution-routing-v2`。

## 通用 stage identity

Open-R1 使用完整 `stage_id` 作为所有阶段 artifact 的唯一键：

- 未拆分：`WP5`
- 拆分：`WP5-a`、`WP5-b`
- plan：`ai-work/planner/{stage_id}-plan.md`
- execution report：`ai-work/executor/{stage_id}-executor.md`
- review：`ai-work/reviewer/{stage_id}-review.md`
- branch：plan 元信息指定的 `feat/wp...`
- worktree：plan 元信息指定的 `.worktrees/wp...`

`WP3-a` 与 `WP3-b` 是不同 stage，绝不共用 execution/review artifact。

## Operation A: bootstrap_plan

输入：planner-ex 的完整最终计划正文（优先来自 `.ai-bridge/current-plan.md` handoff；也可由调用方直接提供），其中必须包含 `stage_id`、`planning_base_commit`、目标 branch、worktree、最终 plan path 与合法 `execution_routing.version: 1`。

步骤：

1. 确认主仓库 `main` 的 tracked working tree 干净，且 `main HEAD == planning_base_commit`；否则返回 `STAGE_PRIMARY_DIRTY` 或 `STAGE_PRIMARY_ADVANCED`，不 stash、不自动换基线。
2. 枚举未合并阶段 worktree。若已有其它 active stage，返回 `STAGE_ACTIVE_EXISTS`；若正是同一 stage，仅允许显式 replan 且它仍处于纯 PLANNED 状态：没有 completed E0，并且 `HEAD` 恰好等于当前 plan seal commit。plan seal 后已有其它 commit 时返回 `STAGE_REPLAN_NOT_CLEAN`。
3. 验证 plan 中 `stage_id/planning_base_commit/branch/worktree/plan path` 互相一致；禁止按“最大 WP 编号”猜测。
4. 创建或复用 plan 指定的 branch/worktree；不得在 `main` 上写阶段文件。
5. 把 handoff 中的完整 plan 正文写入阶段 worktree 的 `ai-work/planner/{stage_id}-plan.md`。
6. 确认 worktree 中 `skills/executor/SKILL.md`、`skills/executor-ex/SKILL.md`、`skills/reviewer-ex/SKILL.md` 均包含 `execution-routing-v2`。任一缺失返回 `STAGE_SKILL_VERSION_MISMATCH`；不要开始 execution/review。
7. 仅暂存最终 plan 文件并提交：`docs: add {stage_id} plan`。该提交是 router 后续推导 `source_plan_commit` 的唯一 plan seal。
8. 报告 `stage_id`、`planning_base_commit`、branch、worktree、plan path、`plan_commit`。不修改 `.ai-bridge` 之外的主仓库文件。

## Operation B: checkpoint_review

输入：stage_id。reviewer-ex 已在阶段 worktree 写好但**尚未提交**最新 review round。

步骤：

1. 定位唯一 stage worktree 与 `ai-work/reviewer/{stage_id}-review.md`；不存在或有歧义则停止。
2. 解析最新 review record，要求至少有：
   - `review_record.version: 1`
   - `review_round`（正整数）
   - `source_execution_id`
   - `reviewed_head_commit`
   - `conclusion`
   - 同轮 `repair_routing.version: 1`
3. reviewer 开始审查时记录的 `reviewed_head_commit` 必须等于**当前阶段 HEAD（提交 review 前）**。若不相等，说明审查期间代码/报告发生变化，返回 `STAGE_REVIEW_STALE`；不得提交该 review。
4. 除 review 文件外不得存在其它 tracked 修改或非忽略 untracked 文件；若存在返回 `STAGE_REVIEW_DIRTY_SCOPE`。reviewer 的一次性验证应放仓库外临时目录，不能把临时脚本/产物混入 stage。
5. `source_execution_id` 必须等于 execution report 最新 completed record 的 execution_id，且 `reviewed_head_commit` 必须等于提交该 record 的 `execution_report_commit`。
6. review 状态必须一致：`conclusion=pass` 当且仅当 `repair_routing.required=false`；`conclusion=needs_repair` 当且仅当 `required=true`。required=true 时 `repair_issue_ids` 必须非空；required=false 时必须为空。否则返回 `STAGE_REVIEW_CONTRACT_INVALID`。
7. `review_round` 必须比已提交的上一轮恰好 +1；R2+ 的最新 execution 必须是 completed repair，且其 `source_review_round/source_review_commit` 精确指向上一轮 review。否则返回 `STAGE_REVIEW_SEQUENCE_INVALID`。
8. 仅暂存 review 文件并提交：`docs: add {stage_id} review round r{review_round}`。
9. 记录/报告 `review_commit=HEAD`。不要把 `review_commit` 自引用写回同一个 review record；router 通过 Git 历史推导它。
10. `repair_routing.required=true` → 状态 `REPAIR_REQUIRED`；`required=false` 且 conclusion=pass → 状态 `PASSED`。

## Operation C: finalize

仅在最新**已提交** review 同时满足 `conclusion=pass` **且** `repair_routing.required=false` 时执行；二者不一致时返回 `STAGE_REVIEW_CONTRACT_INVALID`。

1. 阶段 worktree 必须干净，且当前 stage HEAD 必须恰好等于 latest `review_commit`；其父提交必须等于该 review record 的 `reviewed_head_commit`。任何 review 后的新提交都返回 `STAGE_FINALIZE_STALE`。
2. 主仓库 `main` tracked working tree 必须干净，且 `main HEAD` 必须仍等于 plan 中的 `planning_base_commit`；否则返回 `STAGE_PRIMARY_DIRTY` 或 `STAGE_PRIMARY_ADVANCED`。不 stash、不自动 rebase/换基线。
3. 在主仓库执行 `git merge --no-ff <stage-branch> -m "feat: complete {stage_id} <标题>"`，捕获 `merge_commit`。
4. 在 `main` 上：
   - 按现有 Open-R1 proceedings 规则更新 `proceedings.md`；拆分 stage 先记录子阶段，最后一个子阶段再做 WP 聚合；
   - 在 `ai-work/reviewer/{stage_id}-review.md` 末尾追加 `Finalization Record`，至少写 `review_round`、`review_commit`、`merge_commit`、finalized_at/status；不改审查结论本身。
5. 仅在 merge 成功后提交上述 finalization 文档：`docs: finalize {stage_id}`（若触发 WP 聚合可使用对应 consolidate message）。
6. 再次确认 main/stage worktree 干净后，正常移除 worktree，再 `git branch -d <stage-branch>`；任一步失败就停止并报告当前状态，不自动 `--force`、rollback、rebase 或重试。
7. 不自动 push。finalize 按正常 one-shot 流程执行，不额外设计自动恢复状态。

## 状态守卫

- `PLANNED`：plan 已由 `bootstrap_plan` commit，尚无 completed implementation execution。
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
