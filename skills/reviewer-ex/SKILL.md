---
name: reviewer-ex
description: Web/CodexPro 独立审查入口。以最新 completed execution 和当前 stage 实际代码为审查对象，结合用户 override 与 sealed plan 默认目标进行审查；普通 commit/SHA 漂移由 LLM 判断是否属于可审查 continuation，而不是机械拒绝。保留独立审查、stage identity、真实 evidence 等必要边界。
---

# Reviewer Ex

Workflow compatibility marker: `execution-routing-v2`。

## 目标与边界

reviewer-ex 是独立 Web-side reviewer：亲自读代码、核对 plan、重跑适用测试、生成问题和 repair routing。它默认运行在 GTX 1660 Ti control plane，即使 latest formal artifacts 来自 RTX 4090；reviewer location、artifact source machine 与 `target_hardware` 是三个不同概念。它不信任 executor 自报通过，也不关心 `local_codex/web_codexpro` 或 SINGLE/MULTI/serialized_multi 实现拓扑；所有 backend 使用同一审查标准。

**独立性边界**：reviewer-ex 必须运行在一个没有参与 latest execution 实现/修复的全新 Web GPT conversation/context 中。若当前对话刚刚执行过该 stage 的 executor-web，则停止并返回 `REVIEW_FRESH_CONTEXT_REQUIRED`，要求新开 Web conversation 后重新从 Git/sealed artifacts 定位 stage。reviewer 不依赖上一执行对话的任何记忆或口头 handoff。

它**不执行 Git mutation 生命周期**：

- 不 commit review；
- 不 merge；
- 不更新 proceedings；
- 不删除 worktree/branch；
- 不启动 executor。

每轮 review 写完后交共用 `$stage-lifecycle checkpoint_review` 做 provenance/stale-check 并 commit；该 lifecycle 可在 Web GPT + CodexPro 或 Local Codex 中执行。PASS checkpoint 后再由同一个 `$stage-lifecycle finalize` 完成 merge/proceedings/cleanup。

## Stage identity 与输入

stage resolution 与 execution-router 使用同一规则：调用方显式提供 `stage_id` 时精确使用；未提供时，只在尚未合并的 active stage worktree **恰好 1 个**时自动采用该 stage。0 个候选返回 `REVIEW_STAGE_MISSING`；多个候选返回 `REVIEW_STAGE_AMBIGUOUS`。不得按最大编号、mtime、最近创建等猜 stage。

reviewer-ex 可以从主仓库 root 的 CodexPro workspace 被调用，但**审查工作区必须切换到目标 stage worktree**：

1. 根据已解析的 `stage_id`、项目 branch/worktree 命名规则与 `git worktree list --porcelain` 定位唯一候选；
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

开始审查前要求当前 CodexPro workspace 已是上述 stage worktree，`git ls-files .ai-bridge` 为空，且 stage 对所有非 ignored repository artifact 的 working tree 干净；transport 被 tracked 时返回 `REVIEW_TRANSPORT_TRACKED`。review 文件若存在，必须是该 stage 的 append-only 历史。

## Review/execution provenance guard

reviewer 只能审查一个**新的 completed execution record**：

1. 读取 execution report 的最新 completed `execution_record`，并从 Git 历史定位**提交该 record 的 `execution_report_commit`**。
2. 开始审查前比较 current HEAD/working tree 与 `execution_report_commit`。若 execution record 之后还有 commits 或 attributable diff，reviewer 判断它们是否属于同一 stage 的用户授权 continuation/必要修正；可可靠归因时直接把当前实际代码纳入本轮审查并记录差异。只有来源不明、互相冲突或无法确认是否应纳入的实质变化才返回 `REVIEW_EXECUTION_NOT_HEAD`。
3. 首轮 R1 默认以最新 implementation record 为 provenance anchor；只要当前代码可唯一归属于该 stage，不要求 report commit 必须是最后一个 commit。
4. R2+ 默认期望最新 record 为 repair 且关联上一 review；若用户明确改变 repair 方式或 provenance 字段不完整，reviewer 结合 Git/report/issues 判断是否仍能唯一确认本轮修复来源。普通 hash 字段不完全一致不单独判 invalid。
5. 若上一轮 review 之后既没有新的 completed execution，也没有可明确归因的用户授权 continuation，则返回 `REVIEW_NO_NEW_EXECUTION`。
6. stage/worktree 身份错误、execution 属于其它 stage、或 evidence 无法归属时返回 `REVIEW_EXECUTION_PROVENANCE_INVALID`；普通 plan/review/commit SHA 漂移作为审计信息，由 LLM 判断是否影响审查可靠性。
7. 将**实际被审查的 current HEAD**记录为 `reviewed_head_commit`。审查期间若 HEAD 改变，先检查变化是否影响被审查代码；只有影响结论或无法判断时才停止。

## 审查流程

1. 全文读取 plan、用户 override、最新 execution record/report 与当前代码，形成 **effective stage profile/hardware/evidence contract**；显式核对 `stage_profile / control_plane_hardware / target_hardware / evidence_class / development_terminal`。用户未覆盖时以 sealed plan 为默认；旧 plan metadata 缺失或普通 commit/runtime anchor 漂移时可从项目现状可靠推导并记录，不要求 exact workflow/runtime SHA 才允许审查。硬边界仍保留：control plane 默认 GTX 1660 Ti，reviewer location 与 target hardware 分离，真实 24GB gate 必须有真实 target evidence，synthetic/mock 不能冒充 formal validation。
2. 对照 sealed plan 的默认目标、用户明确 override、execution report 和实际 diff/代码建立 **effective execution contract**。用户没有覆盖的部分仍按 sealed plan 严格审查；用户明确改变的实现方式/顺序/scope 不因“与 sealed plan 不同”本身判失败，而按用户新指令、spec、安全边界和可验证结果审查。
3. 精读适用 spec/审查清单；检查接口、范围、安全、数据泄漏、测试真实性等。
4. 在 stage worktree 独立运行适用的 lint/test 与 reviewer-owned 短时验收。validation target=GTX 1660 Ti 时审查 formal source identity与分析结果；target=24GB 时 reviewer **不得重新运行** target-GPU gate，而是独立核验必要 operator evidence。严格 SHA 只保留证明实际运行对象/结果所需的内容：实际 handoff checkpoint、tracked operator script SHA、completed record 中的 `operator_evidence_sha256` / received evidence bytes、machine/runtime identity、`command_rc/postcheck_rc/gate_status`、formal run identity 以及 required artifact/metadata hashes。plan/review/workflow-runtime/result-code 等普通 commit SHA 作为审计 anchors；漂移时检查 lineage/diff，不因不完全相等直接 FAIL。`control_plane_manual` 同样只严格核验 script、frozen inputs/outputs 与真实 command/postcheck evidence，不伪造 4090 fields，也不得绕过真正 target-GPU gate。若 evidence 不能证明 required large-artifact property，再做短时只读 target check。
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
  workflow_runtime_commit: <required for active-stage workflow migration; otherwise omit>
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

## Stage-profile evidence boundary

reviewer 默认按 sealed plan 的 profile 审查；用户没有明确覆盖时不能自行提高或降低验收门槛。若用户明确改变了本 stage 的实现/验收方式，reviewer 应以用户指令形成 effective contract，但仍不得放宽不可伪造的 formal evidence、安全、数据泄漏和 target-GPU 边界：

- `stage_profile=development` / `evidence_class=engineering`：只要求 plan 规定的开发机工程证据。缺少 24GB GPU、正式规模训练数据、真实 B/C/D checkpoint 或研究数值本身**不是失败项**，也不得作为 blocker；相反，若 development plan 把真实 optimizer-based SFT/GRPO 作为 completed 前置，应视为 plan/spec 违反并要求重新规划，而不是要求 executor 去训练。fixture/mock/synthetic 可以作为工程 contract evidence，但必须确认没有被冒充为正式训练/数值结果。若 `development_terminal=true`，reviewer 必须独立核验 Development Completion Inventory：WP0–WP8 恰好全部覆盖，`finalized` evidence 与 proceedings/Git 一致，`covered_by_this_stage` 确由本 stage 完成；`DEV-CLOSEOUT` 必须九项全为 finalized。随后还必须确认 closeout 全局 gate（lint/test/GPU smoke/真实 Piston 0 failed 0 skipped/无关键 stub-TODO-fake implementation）全部通过，否则不得 PASS。
- `stage_profile=validation` / `evidence_class=real-training/numerical`：synthetic/mock/fake artifact 永远不能满足真实 gate。若 `target_hardware=GTX 1660 Ti (6GB)`，本 stage 应只消费已有 formal artifacts/evidence；reviewer 核验这些 source identities/hashes、正式数据/metrics provenance 与分析结果，不要求新的 GPU evidence。若 `target_hardware=24GB GPU`，必须核验 target evidence 确实证明实际 GPU/VRAM、正式数据、真实 checkpoint/metrics/cost provenance，并按上面的 tracked-script/evidence-SHA/postcheck contract独立复核；`gate_status=passed` 但 command/postcheck/evidence 任一不一致都不得 PASS。大型 checkpoint 不要求复制到 reviewer；只有 postcheck/evidence 无法证明 required property 时才短时只读 target。validation 中若顺手加入未计划的新功能或改变实验定义，也不得 PASS。
- reviewer 不得因 development stage 在 1660 Ti 上触发预期的显存 fail-closed guard 而判失败；该 guard 只需证明没有开始真实训练且错误信息/边界符合计划。

## 判定

以下任何一项存在时不得 PASS：effective execution contract/必要验收未完成、独立测试失败、关键 spec/safety/leakage 违规、测试预期为迁就实现而改、execution report 与事实实质不符、仍存在必须修复 blocker/major/actionable issue。仅仅因为实现偏离 sealed plan 的非本质细节、普通 commit hash 漂移或恢复路径不同，不构成失败。

PASS 只表示“当前 reviewed_head_commit 的代码在本轮证据下通过”。它不是永久状态；`stage-lifecycle checkpoint_review/finalize` 会检查 review 后是否发生新 commit。

`DEV-CLOSEOUT` 的 completed E0 允许没有业务代码 diff：`result_code_commit == plan_commit` 是合法且期望的。Reviewer 不得要求为了产生 diff 而修改代码；应审查真实 preflight/closeout evidence、completion inventory 与 report provenance。

## 输出后续

- needs_repair：review 文件写完 → `$stage-lifecycle checkpoint_review` → `$execution-router` repair → 下一轮 reviewer-ex。
- pass：review 文件写完 → `$stage-lifecycle checkpoint_review` → `$stage-lifecycle finalize`。

## 自检

- [ ] 当前是未参与 latest execution 的全新 Web GPT conversation/context；
- [ ] stage_id 已显式提供，或未提供时仅因恰好 1 个 active stage 自动解析；没有编号/时间猜测；
- [ ] 当前 CodexPro workspace 已绑定到 plan 指定的绝对 stage worktree，未在 primary checkout 写 review；
- [ ] 存在新的 completed execution 或可明确归因的用户授权 continuation；否则返回 REVIEW_NO_NEW_EXECUTION；
- [ ] `reviewed_head_commit` 代表实际被审查代码；审查期间若 HEAD 有变化，已判断是否影响结论，而不是仅凭 SHA 改变停止；
- [ ] 已按 effective profile/hardware/evidence contract 使用正确证据边界；workflow runtime/plan/review commits 作为审计 anchors，不要求 exact 等式；target=24GB 时已独立重算实际 handoff script/evidence/required artifact hashes，未重跑 target gate；
- [ ] 全部结论有代码/命令/spec/用户 override 证据；
- [ ] 所有 actionable failed effective-contract/acceptance/test finding 都映射到 repair scope；
- [ ] conclusion 与 required 的语义一致；routing schema 如有非关键形式差异已 normalization；
- [ ] review round / repair source 可可靠归属，没有因普通 source commit SHA 漂移误判；
- [ ] repair routing 按本轮 effective remaining issues 生成，用户明确 override 已记录；
- [ ] review history append-only；
- [ ] `.ai-bridge/**` 保持 ignored/untracked，没有 transport path 混入被审查 execution 或本轮 review staging；
- [ ] reviewer-ex 未 commit/merge/update proceedings/cleanup；
- [ ] 已明确下一步交给 stage-lifecycle checkpoint_review。
