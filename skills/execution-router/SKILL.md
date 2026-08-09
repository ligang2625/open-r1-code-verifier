---
name: execution-router
description: 本地 routed execution 控制面。消费已由 stage-lifecycle seal 的 plan execution_routing 或已 checkpoint 的最新 review repair_routing；结合 Git/provenance 状态阻止重复 implementation、重复 repair、stale/uncommitted review，再调度 single executor-ex 或 multi executor。只做校验与调度，不实现代码、不做 review/Git finalization。
---

# Execution Router

Routing compatibility marker: `execution-routing-v2`。

## 输入与 stage 定位

标准入口是在**主仓库 root checkout** 调用 execution-router；用户不需要手动进入最新 worktree。若从 linked stage worktree 调用，也必须先解析主仓库 root，再通过 Git worktree 状态定位目标 stage；router 自己不 `git switch` stage branch。

必须定位唯一 `stage_id` 与 stage worktree。优先使用调用方给出的 plan/stage_id；未给时只能在尚未合并 stage worktree 中**恰好一个候选**时继续：0 → `ROUTING_PLAN_MISSING`；>1 → `ROUTING_PLAN_AMBIGUOUS`。禁止最大编号、mtime、最近创建等猜测。

Open-R1 artifact：

- plan：`ai-work/planner/{stage_id}-plan.md`
- execution：`ai-work/executor/{stage_id}-executor.md`
- review：`ai-work/reviewer/{stage_id}-review.md`

plan 必须已经由 `stage-lifecycle bootstrap_plan` commit；router 通过 Git 历史推导 `plan_commit`。未提交/dirty plan → `ROUTING_PLAN_NOT_SEALED`。

## 状态推导与 source precedence

Router 不再简单按“文件是否存在”选择 source，而先推导状态。任何 dispatch 前 stage worktree 必须干净：若只有 review 文件存在未提交修改，返回 `ROUTING_REVIEW_NOT_COMMITTED`；其它 tracked 或非忽略 untracked 改动返回 `ROUTING_STAGE_DIRTY`。不得在未知 dirty baseline 上启动 execution。

当前 plan 文件内容还必须与 `plan_commit` 中 seal 的版本一致，且 plan_commit 之后没有 commit 修改该 plan；否则 `ROUTING_PLAN_NOT_SEALED`。

### A. 尚无 committed review

- 若已有 `task_kind=implementation,status=completed,source_plan_commit=<plan_commit>`：返回 `ROUTING_IMPLEMENTATION_ALREADY_EXECUTED`，等待 reviewer-ex；不得再次跑 plan。
- 若没有 completed E0 且当前 `HEAD == plan_commit`：`task_kind=implementation`，消费 plan `execution_routing`。
- 若没有 completed E0 但 `HEAD != plan_commit`：说明此前 execution 可能已产生部分提交却未封存 completed record，返回 `ROUTING_INCOMPLETE_IMPLEMENTATION`。不得自动重跑整份 plan；先由人工/同一 execution context 查明并完成或回退该不完整尝试。

### B. 已有 committed review

只允许消费**最新 committed review round**。显式指定旧 round 也必须返回 `ROUTING_STALE_REVIEW`。

先校验 review 状态一致性：`conclusion=pass` 必须且只能对应 `required=false`；`conclusion=needs_repair` 必须且只能对应 `required=true`。不一致直接 `ROUTING_REPAIR_CONTRACT_INVALID`。

- latest review `required=false` → `ROUTING_NO_REPAIR_REQUIRED`；不得启动 executor。
- latest review `required=true`：
  1. 找到该 review 文件最新 round 对应的 `review_commit`；
  2. 若当前 stage HEAD 恰好等于 `review_commit`，且 execution report 尚无 completed repair record 同时匹配 `source_review_round` + `source_review_commit` → `task_kind=repair`；
  3. 若已有匹配 completed repair record → `ROUTING_REPAIR_ALREADY_EXECUTED`，等待下一轮 reviewer-ex；
  4. 若 HEAD 既不是 review_commit，也没有合法 matching repair record → `ROUTING_STAGE_STATE_INVALID`，不得猜测。

### C. 未 checkpoint review

若 review 文件存在 staged/unstaged 修改，或首轮 review 文件仍是未提交的 untracked 文件，返回 `ROUTING_REVIEW_NOT_COMMITTED`，要求先 `$stage-lifecycle checkpoint_review`。Router 绝不消费 Web reviewer 尚未 checkpoint 的结果。

## Routing contract

共同字段：`version=1`、mode、complexity、parallelizability、multi_benefit、independent_workstreams、rationale。

- `complexity`: `very_simple | normal | difficult_serial`
- `parallelizability/multi_benefit`: `low | medium | high`
- rationale：2–5 条具体理由
- SINGLE：`single_class==complexity`、independent_workstreams≥1、workstream_candidates=[]
- MULTI：single_class=null、complexity≠very_simple、parallelizability=high、multi_benefit=high、independent_workstreams≥2

Implementation MULTI candidate：唯一 id、非空 `steps`、tracked `write_scope`；steps/write_scope 跨 candidate 不重叠，candidate 数量等于 workstreams。

Repair 额外：

- `source_review_round` 必须是整数并等于 latest committed review_round；
- required=true 时 repair_issue_ids 非空唯一，并全部存在于该 round actionable issue list；
- repair MULTI candidate 使用 `issue_ids` + tracked `write_scope`；issue_ids/write_scope 不重叠，issue_ids 并集恰好等于 repair_issue_ids；
- required=false 的 null/empty schema 只产生 NO_REPAIR，不执行。

错误分别使用 `ROUTING_CONTRACT_MISSING/INVALID`、`ROUTING_REPAIR_CONTRACT_MISSING/INVALID`。

## SINGLE model mapping（唯一执行模型真源）

| single_class | model | reasoning_effort |
|---|---|---|
| `very_simple` | `gpt-5.6-luna` | `max` |
| `normal` | `gpt-5.6-sol` | `medium` |
| `difficult_serial` | `gpt-5.6-sol` | `high` |

`fork_turns=none`。planner/reviewer 不写 model/effort。

## SINGLE dispatch

1. 目标 worktree `skills/executor-ex/SKILL.md` 必须包含 `execution-routing-v2`，否则 `ROUTING_SKILL_VERSION_MISMATCH`。
2. 创建恰好 1 个 execution agent。
3. 任务消息必须给出：stage_id、绝对 worktree、plan path、`plan_commit`、task_kind、routing_mode=single、single_class。
4. repair 额外给 review path、整数 source_review_round、`review_commit`、repair_issue_ids。
5. 明确要求先进入 stage worktree；不得在主 checkout `git switch` 已被 linked worktree 使用的分支。
6. 明确 agent 不得 subagent，先读 worktree 内 executor-ex skill/references。
7. agent 不能可靠单 agent 完成时返回证据；router 不自动改 mode。

## MULTI dispatch

1. `skills/executor/SKILL.md` 必须含 `execution-routing-v2`。
2. 调用现有 `$executor` 协议，传 stage_id/worktree/plan/plan_commit/task_kind/routing_mode=multi；repair 还传 review round/review_commit/repair_issue_ids。
3. candidate 只是上游证据；main coordinator 必须按真实代码复核，最终不足 2 个独立 subplans → `ROUTING_MISMATCH`，不得退化单 worker。
4. subagent 除 assigned tracked write_scope 外不得写共享业务 artifact；需要产生临时/cache/output 时使用各自隔离临时目录。共享验证/共享生成 artifact 由 coordinator 串行执行。
5. multi 模型/effort 继续由 executor 管理。

## 输出/错误

报告 task_kind、stage_id、plan_commit、routing source、mode/path；repair 报 review_round/review_commit/repair_issue_ids；SINGLE 报实际 model/effort。

关键状态错误：

- `ROUTING_PLAN_MISSING` / `ROUTING_PLAN_AMBIGUOUS` / `ROUTING_PLAN_NOT_SEALED`
- `ROUTING_STAGE_DIRTY`
- `ROUTING_REVIEW_NOT_COMMITTED` / `ROUTING_STALE_REVIEW`
- `ROUTING_IMPLEMENTATION_ALREADY_EXECUTED` / `ROUTING_INCOMPLETE_IMPLEMENTATION`
- `ROUTING_REPAIR_ALREADY_EXECUTED`
- `ROUTING_NO_REPAIR_REQUIRED`
- `ROUTING_STAGE_STATE_INVALID`
- `ROUTING_SKILL_VERSION_MISMATCH`
- `ROUTING_CONTRACT_*` / `ROUTING_REPAIR_CONTRACT_*`
- `ROUTING_MISMATCH`

## 禁止事项

- 不修改 routing/plan/review。
- 不写业务代码、review、proceedings。
- 不 commit/merge/cleanup；Git lifecycle 归 stage-lifecycle。
- 不重复消费已 completed 的 plan/review source。
- 不消费 uncommitted/stale review。
