---
name: executor-ex
description: SINGLE execution protocol。由 execution-router 传入明确 task_kind 与 provenance，在 stage worktree 中执行一次 implementation 或一次 repair（严格二选一），提交代码/测试后写结构化 execution_record。不得 subagent、不得重新 routing、不得做 review/finalization。
---

# Executor Ex

Routing compatibility marker: `execution-routing-v2`。

## 单 agent 边界

- 恰好一个 execution agent；不得 spawn/subagent。
- 不重判 execution_routing/repair_routing，不改 model/effort。
- `task_kind` 必须显式为 `implementation` 或 `repair`，两个流程**互斥**；repair 完成后绝不继续跑 implementation 流程。
- 所有操作先进入 router 给定的 stage worktree，不在 main checkout 切 stage branch。

## 必需输入

共同：`stage_id`、绝对 worktree、plan path、`plan_commit`、stage branch、task_kind。

- implementation：plan `execution_routing` 只作为已由 router 消费的上游决策；本 skill 按完整 plan 实施。
- repair：额外必须有 review path、整数 `source_review_round`、`review_commit`、`repair_issue_ids`；只处理这些 issue IDs。plan 只提供规格、禁止范围与总体验收约束。

Artifact：

- execution report：`ai-work/executor/{stage_id}-executor.md`
- review：`ai-work/reviewer/{stage_id}-review.md`（只读）

同一 stage report append-only，不因“重跑”自动清空。

## 前置校验

1. 当前目录/branch 必须等于 plan metadata 指定 stage worktree/branch。
2. plan 必须是 plan_commit 中 seal 的同一文件。
3. implementation：report 不得已有 matching completed E0，且开始修改前 `HEAD` 必须精确等于 `plan_commit`；若 HEAD 已前进，视为不完整/未知 execution baseline，停止而不是重跑 plan。
4. repair：开始修改前 stage HEAD 必须等于 router 传入的 `review_commit`；latest review round/issues 必须与任务消息完全一致；若不一致停止。
5. 不修改 review、plan、proceedings、`third_party/open-r1/`。

## task_kind=implementation

1. 全文读 plan/spec/相关代码。
2. 按 plan steps 顺序循环“实现 → 测试 → 验证 → 修正”；不修改测试预期迁就实现。
3. 每个可独立步骤验证后显式暂存该步骤文件并 commit；禁止 `git add -A`。
4. 完整运行 plan 总体验收（至少 `make lint`、`make test` 与 stage 特有 gate）。
5. 所有代码/测试提交完成后记录当前 HEAD 为 `result_code_commit`。
6. 在 execution report 追加 E0 记录与人类可读摘要，再单独 docs commit report。E0：

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
  result_code_commit: <code HEAD before report docs commit>
  status: completed
```

只有所有必须验收通过才写 `status: completed`。阻塞/失败可如实写 narrative/blocked attempt，但不得伪造 completed E0。

## task_kind=repair

1. 只解析 router 指定 `repair_issue_ids` 对应的 latest committed review findings。
2. 不把其它 minor/suggestion/plan step 自动加入 scope；人工严重级别默认规则不适用于 routed repair。
3. 每个 issue 做最小修复；异议/无法复现记录证据，不静默忽略。
4. 运行受影响定向测试，再运行 plan 的全局 regression/acceptance。**全局测试是验证约束，不会扩大 repair scope**。
5. 修复代码/测试提交完成后记录 `result_code_commit=HEAD`。
6. 追加下一 execution_id（E1/E2/...）并 docs commit report：

```yaml
execution_record:
  version: 1
  stage_id: WP5-b
  execution_id: E1
  task_kind: repair
  source_plan_commit: <plan_commit>
  source_review_round: 1
  source_review_commit: <review_commit>
  repair_issue_ids: [R1-M1]
  result_code_commit: <code HEAD>
  status: completed
```

同一 review_commit 只能有一个 completed repair record。全部 repair_issue_ids 必须已修复或附证据处置，且 regression/acceptance 满足后才 completed。

## 报告与提交

- code/test commit 在先；report docs commit 在后，避免在同一 commit 中自引用 hash。
- report 包含真实命令/结果、修改文件、issue/step 映射、偏差/阻塞。
- 不自动 push；review 由 reviewer-ex；Git checkpoint/finalization 由 stage-lifecycle。

## 自检

- [ ] task_kind 只执行了一个互斥流程；repair 后没有继续 implementation；
- [ ] stage_id 与 report 路径使用完整 stage id；
- [ ] implementation source_plan_commit 正确且没有重复 completed E0；
- [ ] repair source_review_round/review_commit/issues 与 router 完全一致且没有扩大 scope；
- [ ] repair 总体验收没有被误解释成“修所有 review 问题”；
- [ ] result_code_commit 在 report docs commit 之前捕获；
- [ ] completed execution_record schema 完整；
- [ ] 未修改 plan/review/proceedings/third_party；未 push。
