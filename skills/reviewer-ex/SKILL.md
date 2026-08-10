---
name: reviewer-ex
description: Web/CodexPro 独立审查入口。审查 execution-router 产生的最新 completed execution，绑定具体 stage HEAD 与 execution_id，输出 append-only review record 和本轮 repair_routing；不做 Git commit/merge/finalize。审查文件由 Web/Local 共用 stage-lifecycle checkpoint_review 封存，审查标准与 execution backend 无关。
---

# Reviewer Ex

Workflow compatibility marker: `execution-routing-v2`。

## 目标与边界

reviewer-ex 是独立 Web-side reviewer：亲自读代码、核对 plan、重跑测试、生成问题和 repair routing。它不信任 executor 自报通过，也不关心 `local_codex/web_codexpro` 或 SINGLE/MULTI/serialized_multi 实现拓扑；所有 backend 使用同一审查标准。

**独立性边界**：reviewer-ex 必须运行在一个没有参与 latest execution 实现/修复的全新 Web GPT conversation/context 中。若当前对话刚刚执行过该 stage 的 executor-web，则停止并返回 `REVIEW_FRESH_CONTEXT_REQUIRED`，要求新开 Web conversation 后重新从 Git/sealed artifacts 定位 stage。reviewer 不依赖上一执行对话的任何记忆或口头 handoff。

它**不执行 Git mutation 生命周期**：

- 不 commit review；
- 不 merge；
- 不更新 proceedings；
- 不删除 worktree/branch；
- 不启动 executor。

每轮 review 写完后交共用 `$stage-lifecycle checkpoint_review` 做 provenance/stale-check 并 commit；该 lifecycle 可在 Web GPT + CodexPro 或 Local Codex 中执行。PASS checkpoint 后再由同一个 `$stage-lifecycle finalize` 完成 merge/proceedings/cleanup。

## Stage identity 与输入

必须显式定位唯一 `stage_id`，例如 `WP5-b`。不得按“最大 WP 编号”猜 stage。

reviewer-ex 可以从主仓库 root 的 CodexPro workspace 被调用，但**审查工作区必须切换到目标 stage worktree**：

1. 根据显式 `stage_id`、项目 branch/worktree 命名规则与 `git worktree list --porcelain` 定位唯一候选；
2. 得到绝对 stage worktree 后，若当前 CodexPro workspace 不是该路径，先使用 workspace 切换/打开能力进入该 worktree；
3. 打开后读取 sealed plan，并再次验证 plan metadata 中的 stage_id/branch/worktree 与实际 Git worktree 完全一致；不一致返回 `REVIEW_WORKTREE_MISMATCH`；
4. 从此之后所有代码读取、Git history、测试、临时状态检查以及 review artifact 写入都以该 stage worktree 为根。不得把 review 写到 primary checkout 的同名相对路径。

输入：

- plan：`ai-work/planner/{stage_id}-plan.md`
- execution：`ai-work/executor/{stage_id}-executor.md`
- review：`ai-work/reviewer/{stage_id}-review.md`
- stage worktree/branch：来自 plan metadata
- spec / proceedings / 当前 src/tests
- `skills/execution-router/references/routing-contract.md`

开始审查前要求当前 CodexPro workspace 已是上述 stage worktree，且 stage tracked working tree 干净；review 文件若存在，必须是该 stage 的 append-only 历史。

## Review/execution provenance guard

reviewer 只能审查一个**新的 completed execution record**：

1. 读取 execution report 的最新 completed `execution_record`，并从 Git 历史定位**提交该 record 的 `execution_report_commit`**。
2. 开始审查前 stage worktree 必须干净，且当前 `HEAD == execution_report_commit`；execution record 之后若出现任何额外 commit 或未提交改动，返回 `REVIEW_EXECUTION_NOT_HEAD`，不得把未知变化悄悄纳入本轮。
3. 首轮 R1：最新 record 必须是 `task_kind=implementation`。
4. R2+：最新 record 必须是 `task_kind=repair`，且 `source_review_round == 上一已提交 review_round`，其 `source_review_commit` 必须指向上一 review commit。
5. 若上一轮 review 之后没有新的 completed execution，返回 `REVIEW_NO_NEW_EXECUTION`；不得仅因 review 文件存在就生成下一 round。
6. 若 execution provenance 与当前 stage/plan 不匹配，返回 `REVIEW_EXECUTION_PROVENANCE_INVALID`。
7. 将当前 `execution_report_commit` 记录为 `reviewed_head_commit`；审查期间若 HEAD 改变，停止并返回 `REVIEW_CODE_CHANGED_DURING_REVIEW`。

## 审查流程

1. 全文读取 plan 和最新 execution record/report。
2. 对照 plan 每个实施步骤、交付、总体验收，核对实际 diff/代码。
3. 精读适用 spec/审查清单；检查接口、范围、安全、数据泄漏、测试真实性等。
4. 在 stage worktree 独立运行 `make lint`、`make test` 和 plan 特有验收；一次性验证脚本放仓库外临时目录，不污染 tracked/untracked stage artifact。
5. 核验 execution report 声明，标记核实通过/与事实不符/无法核实。
6. 生成稳定 issue IDs：`R{round}-B1`/`M1`/`m1`/`S1` 等；上一轮未解决问题沿用原 ID，新问题用当前 round 新 ID。
7. 生成结论与 repair routing。
8. 把本轮 record **追加**到 `ai-work/reviewer/{stage_id}-review.md`；同一 stage 永不因“重跑”自动清空历史。
9. 不提交；调用方下一步必须运行 `$stage-lifecycle checkpoint_review`。

## Actionable issue coverage invariant

所有需要 executor 行动的失败项必须映射到问题 ID：

- 未完成/部分完成/与计划不符的 plan step；
- 未通过的 acceptance item；
- 独立测试失败；
- blocker/major/minor 中 reviewer 要求修复的项。

上述每个 actionable finding 必须至少对应 1 个稳定 issue ID，并且该 ID 必须出现在本轮 `repair_issue_ids`。纯 suggestion 若明确不要求执行方修改，可以保留在问题列表但不得进入 `repair_issue_ids`。

因此不能出现“计划完成度表写未通过，但 repair_issue_ids 没有对应问题”的状态。

## Review Record

每轮必须先写结构化 provenance：

```yaml
review_record:
  version: 1
  stage_id: WP5-b
  review_round: 1
  source_execution_id: E0
  reviewed_head_commit: <stage HEAD before writing this review>
  conclusion: needs_repair  # needs_repair | pass
```

`review_round` 固定为整数。不要写 `R1`；问题 ID 才使用 `R1-...`。

## Repair Routing

每轮必须有且只有一份：

```yaml
repair_routing:
  version: 1
  required: true
  source_review_round: 1
  mode: single
  complexity: normal
  single_class: normal
  parallelizability: low
  multi_benefit: low
  independent_workstreams: 1
  repair_issue_ids:
    - R1-M1
  rationale:
    - "..."
    - "..."
  workstream_candidates: []
```

规则：

- `source_review_round` 必须等于同一 record 的整数 `review_round`。
- `conclusion` 与 `required` 是同一状态的两种表达，必须严格一致：`pass ⇔ required=false`，`needs_repair ⇔ required=true`。
- PASS：`required=false`；`mode/complexity/single_class/parallelizability/multi_benefit=null`；`independent_workstreams=0`；`repair_issue_ids=[]`；`workstream_candidates=[]`；rationale 只说明本轮通过无需 repair。
- needs_repair：required=true 且 `repair_issue_ids` 非空；只按当前 `repair_issue_ids` 重新评估复杂度/并行性/净收益，不继承 plan 或上一轮 routing。
- SINGLE：`single_class==complexity`，workstream_candidates=[]。
- MULTI：仅在非 very_simple、parallelizability=high、multi_benefit=high、≥2 真正独立 repair lane 时；candidate 每项含唯一 id、非空且互不重叠 `issue_ids`、互不重叠 tracked `write_scope`，所有 repair_issue_ids 恰好覆盖一次。
- 不写具体 model/effort。

## 判定

以下任何一项存在时不得 PASS：计划/验收未完成、独立测试失败、关键 spec/safety/leakage 违规、测试预期为迁就实现而改、execution report 与事实实质不符、仍存在必须修复 blocker/major/actionable issue。

PASS 只表示“当前 reviewed_head_commit 的代码在本轮证据下通过”。它不是永久状态；`stage-lifecycle checkpoint_review/finalize` 会检查 review 后是否发生新 commit。

## 输出后续

- needs_repair：review 文件写完 → `$stage-lifecycle checkpoint_review` → `$execution-router` repair → 下一轮 reviewer-ex。
- pass：review 文件写完 → `$stage-lifecycle checkpoint_review` → `$stage-lifecycle finalize`。

## 自检

- [ ] 当前是未参与 latest execution 的全新 Web GPT conversation/context；
- [ ] stage_id 唯一明确，没有最大编号猜测；
- [ ] 当前 CodexPro workspace 已绑定到 plan 指定的绝对 stage worktree，未在 primary checkout 写 review；
- [ ] latest execution 是上一 review 之后的新 completed record，否则已返回 REVIEW_NO_NEW_EXECUTION；
- [ ] recorded `reviewed_head_commit` 在审查期间未变化；
- [ ] 全部结论有代码/命令/spec 证据；
- [ ] 所有 actionable failed plan/acceptance/test finding 都映射到 repair_issue_ids；
- [ ] conclusion 与 required 严格一致（pass=false / needs_repair=true）；
- [ ] review_round/source_review_round 都是整数且相等；
- [ ] repair routing 只按本轮剩余问题重算；
- [ ] review history append-only；
- [ ] reviewer-ex 未 commit/merge/update proceedings/cleanup；
- [ ] 已明确下一步交给 stage-lifecycle checkpoint_review。
