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

共同：stage_id、绝对 worktree、stage branch、plan path、plan_commit、task_kind、`backend=web`、完整 source routing、source_mode、effective_execution_mode。

- source_mode=single → effective 必须为 `single`
- source_mode=multi → effective 必须为 `serialized_multi`
- repair 额外必须有 review path、整数 source_review_round、review_commit、repair_issue_ids

Artifact：`ai-work/executor/{stage_id}-executor.md`，append-only。

## 前置校验

1. 使用当前 CodexPro 打开/绑定准确 stage worktree，并验证实际 branch/worktree 与 sealed plan metadata 一致；否则 `WEB_EXECUTION_WORKTREE_MISMATCH`。
2. plan 内容必须等于 plan_commit seal 版本。
3. implementation：report 不得已有 matching completed E0，且开始修改前 `HEAD == plan_commit`。
4. repair：开始修改前 `HEAD == review_commit`，latest committed review round/issues 与 dispatch 完全一致。
5. 当前环境必须具备 workspace write、Git 和 plan 所需验证命令能力；缺失则停止，不自动改用 local。

## source SINGLE

### implementation

1. 全文读取 plan/spec/相关代码。
2. 按 plan steps 顺序执行“实现 → 定向测试 → 验证 → 修正”。
3. 每个可独立步骤验证后显式暂存其文件并 commit；禁止 `git add -A`。
4. 运行 plan 全局 acceptance/gates。

### repair

1. 只处理 dispatch `repair_issue_ids` 对应的 latest committed review findings。
2. 每个 issue 做最小修复与定向测试；其它 finding 不自动进入 scope。
3. 运行受影响测试 + plan 全局 regression/acceptance；全局验证不扩大 repair scope。
4. 显式提交修复 code/test/config。

## source MULTI → serialized_multi

`serialized_multi` 是 Web backend 的正式执行拓扑；**source routing 仍然是 MULTI**。

### implementation

- 使用 sealed `execution_routing.workstream_candidates` 作为完整 lane 清单，必须全部覆盖。
- 默认按 candidate 在 plan 中的顺序执行。
- 若真实代码依赖要求改变先后，只允许调整**运行顺序**；不得改 routing/candidate 内容，并在 report 记录原因。
- 每个 lane：读取 assigned steps/write_scope → 实现 → 定向测试 → 显式 commit → 再进入下一 lane。
- 因为当前只有一个 Web executor，不需要并行 filesystem isolation；但不得借串行化扩大各 lane 的业务范围。
- 所有 lanes 完成后统一跑 integration/global acceptance。

### repair

- 使用 latest `repair_routing.workstream_candidates`；candidate issue_ids 并集必须恰好等于 dispatch repair_issue_ids。
- 每个 lane 只处理自己的 issue_ids，完成定向测试并 commit 后再进入下一 lane。
- 最后统一跑受影响测试 + plan regression/acceptance；全局验证不扩大 repair scope。

若 source MULTI candidate schema 本身非法，返回对应 routing contract error；不得自行构造新的 routing。

## Execution record / commit ordering

所有代码/测试/config commits 完成且必须验收通过后：

1. 捕获 `result_code_commit=HEAD`；
2. append execution report 的下一 record 与人类可读摘要；
3. 单独 docs commit report。

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

`execution_backend/effective_execution_mode` 只用于审计，不改变 v2 provenance。

## 报告

至少记录：source mode、effective mode、真实命令/结果、修改文件、step/workstream 或 issue/lane 映射、任何执行顺序调整及原因、阻塞/偏差。

## 自检

- [ ] 当前 workspace 是准确 stage worktree；
- [ ] 未调用 Local Codex execution agent；
- [ ] source routing 未修改；MULTI 只在运行时 serialized；
- [ ] implementation/repair 只执行一个 task_kind；
- [ ] serialized_multi 覆盖全部 source candidates/repair_issue_ids；
- [ ] result_code_commit 在 report docs commit 之前捕获；
- [ ] execution_record 使用统一 v2 provenance；
- [ ] 未修改 plan/review/proceedings/third_party，未 push/review/finalize。
