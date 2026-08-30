# WP7-d 实施计划（single-seed 最终人工分析、技术报告与 README 收口；replication 暂缓）

## 1. 元信息

| 项 | 值 |
|---|---|
| stage_id | `WP7-d` |
| stage_profile | `validation` |
| control_plane_hardware | `GTX 1660 Ti (6GB)` |
| target_hardware | `GTX 1660 Ti (6GB)` |
| evidence_class | `real-training/numerical` |
| development_terminal | `false` |
| 目标 WP | `WP8`：正式人工失败案例分析、结果解释、README 与技术报告收口；`WP7-d` 仅因 lifecycle 的纯 PLANNED pre-execution replan 合同保留当前 stage identity |
| 规格依据 | `PROJECT_SPEC_Open-R1_CodeVerifier.md` §13.3–§14.3、§20 WP8、§21.5、§23、§25–§28、§29；`proceedings.md` WP7-c/WP8-a finalized evidence |
| 前置状态 | Development Complete Record 合法；Base A / SFT B / Public C / Hidden D 已 finalized；WP8-a formal automated analysis 已 finalized，653 个 deterministic failure candidates 已生成；当前 `WP7-d` 旧 plan 仅 seal、从未执行/review，用户明确决定暂缓第二 seed，先完成最终分析与展示 |
| planning_base_commit | `f06107594d797ad9ed0e994586f9ceac19fb48ad` |
| proposed branch | `feat/wp7-d` |
| proposed worktree | `.worktrees/wp7-d` |
| final plan path | `ai-work/planner/WP7-d-plan.md` |
| execution report path | `ai-work/executor/WP7-d-executor.md` |
| review path | `ai-work/reviewer/WP7-d-review.md` |
| plan lifecycle | planner-ex handoff → `stage-lifecycle bootstrap_plan` pre-execution replan → committed replacement plan seal |

> **Pre-execution replan provenance**：本计划显式 supersede 已 seal 但从未执行的旧 `WP7-d` plan commit `47e6fc7d8f5884155c7ebbbe7be1a3329eb5aaf8`。旧 stage worktree 当前 clean，`HEAD` 恰好等于旧 plan seal；不存在 `WP7-d-executor.md`、review 或任何 plan 后提交，因此符合 planner-ex / stage-lifecycle 的纯 `PLANNED` replan 窄路径。bootstrap 必须删除/重建同一 `feat/wp7-d` / `.worktrees/wp7-d`，不得把旧 GRPO replication plan 与本计划混合执行。

> **用户实验决策**：当前不执行第二 training seed 或完整 C/D rerun。该决定只改变执行顺序，不改写现有 seed-42 formal evidence。最终 README/报告必须明确：规格 §13.5 与 Definition of Done 中“核心实验已重跑或使用第二 seed”在本 stage 结束后仍为 **pending**；不得把项目描述为已完成 replication。项目完成本 stage 后由用户做全项目审查，再决定是否值得单独开新 replication stage。

> 本 stage 是 **formal-evidence-only control-plane validation**：不产生新的 24GB GPU 计算，不连接/要求 4090，不包含 `operator_terminal_execution`。默认不修改 `src/`、训练/eval config、数据或实验定义；现有 production Analysis Layer 已能消费至少 20 条 manual labels，本 stage 优先使用冻结实现完成真实人工案例分析与最终叙事。若真实 formal input 暴露 acceptance-critical analysis defect，才允许最小修复并重新跑受影响 regression；不得借机改变指标、candidate definition 或实验结果。

## 2. 目标与范围

### 目标

基于 WP8-a 已冻结、finalized 的 seed-42 A–D formal evidence，把尚未完成的 WP8 人工与展示层做完整：

1. 在**看任何 selected code 之前**预注册并冻结 deterministic manual-case selection；
2. 对至少 20 个真实 formal failure candidates 做逐例语义审查，本 stage 固定为 Public-RLVR 10 + Hidden-RLVR 10 + SFT 5，共 25 例；
3. 用现有 `manual_labels_path` contract 生成可被 production `analyze-results` 严格验证的 25-case labels，并重新产出 `manual_analysis_status=completed` 的 final formal analysis；
4. 形成可审计的 manual failure-analysis 文档、结果解释、限制说明、最终技术报告；
5. 重构 README 首屏，展示真实主结果、方法、复现命令、成本、两个人工案例与项目限制；
6. 明确区分：观察事实、数据支持结论、定性解释、推测、后续假设；尤其禁止把单 seed 或 automated candidate proxy 写成稳定因果结论。

### 已冻结的 formal evidence

WP8-a canonical inputs / outputs 必须作为本 stage 唯一 numerical authority：

- input manifest `/home/dzy/wp8-analysis/wp8-a-input-ab87fea-e0/formal-analysis.yaml` SHA256 `118093d5befbd43bdd0e08527847d23f40626284f8e73b49dbe2df033d1e0da8`；
- source inventory `/home/dzy/wp8-analysis/wp8-a-input-ab87fea-e0/source-inventory.json` SHA256 `b79718d096be441b2d3d0e45b88b4b95ce1d458696617dafd80f1b11cfca18f1`；
- canonical output `/home/dzy/wp8-analysis/wp8-a-formal-ab87fea-e0/`；
- `main_results.csv` SHA256 `02030685f05f0ed04d8e007cc0eb1a4455aacfbcbe6f505c13afd8849e63804e`；
- `paired_comparisons.csv` SHA256 `0ae767e7e9e918d9fe2109a7f65b4aca39b4446c615beb694eb175adb80a3eed`；
- `report_data.json` SHA256 `fd03754215297643aec8d32f1df65b9fd8df669c29983cd7573c5f3ff3fc74c2`；
- `failure_candidates.jsonl` SHA256 `4410a05e2838a0be92997141bf19bb2b518a4985a8afabdc87442812827408ed`，653 rows；
- `manual_labels_template.csv` SHA256 `bad8b08c658ebfe10039b352d4f41a1b2a0615c4442dd286eeb892121529e79b`，653 rows；
- `costs.csv` SHA256 `7a7a4bc0f92b011ce6faa4167b71669833745bcf519a31b94d7f13d3102b4505`。

Formal seed-42 point estimates（production output 为 authority）：

- Base: Visible `0.1225`, Train-Hidden `0.1175`, Eval-Hidden `0.1150`；
- SFT: `0.3525 / 0.3350 / 0.3775`；
- Public-RLVR: `0.3625 / 0.3400 / 0.3750`；
- Hidden-RLVR: `0.3625 / 0.3400 / 0.3750`；
- Public-vs-SFT 与 Hidden-vs-SFT Eval-Hidden delta 均为 `-0.0025`，95% CI `[-0.0125, 0.0075]`；
- Hidden-vs-Public 的预定义 whole-pass / candidate-proxy paired metrics 均为 `0.0`，CI `[0.0, 0.0]`；
- SFT GPU-hours `0.5215871774233367`；Public `4.012272991803669`；Hidden `3.5036727118225017`；无冻结 USD/GPU-hour 费率，因此不得编造美元成本。

### 交付

Tracked repository artifacts：

1. `report/manual_case_selection.json`
   - deterministic 25-case selection manifest；
   - 绑定 source candidate SHA、selection algorithm/namespace、selected `(method, run_id, problem_id)`；
   - 不包含 completion、tests、reference solution 或 hidden payload。
2. `report/manual_labels.csv`
   - production `load_manual_labels()` 可直接读取的 25 行 labels；
   - schema 保持当前 `_MANUAL_FIELDS`：`method,run_id,problem_id,candidate_reasons,auto_error_category,manual_category,notes,source_results_path`；
   - `notes` 使用稳定的可审计格式记录人工语义判断：`reward_hacking=<yes|no|uncertain>; reason=<...>; improvement=<...>`；
   - 不把 automated reason 直接复制成人工结论。
3. `report/manual_failure_analysis.md`
   - 25 个 case 的逐例记录；
   - 每例至少包含 problem ID、method/model/run、候选规则、visible/train-hidden/eval-hidden 表现、execution status、**model extracted code**、auto label、manual category、原因分析、Reward Hacking 判断及理由、奖励/数据改进建议；
   - 不包含 eval-hidden test bodies、reference solutions、expected outputs、SFT private responses 或其它受保护 payload。
4. `report/final_evidence.json`
   - machine-readable final evidence snapshot；
   - 绑定 WP8-a source/output hashes、manual selection/labels/report hashes、final labeled-analysis hashes、核心 numerical values、cost values、known limitations；
   - `replication_status` 必须明确是 `pending_second_seed_or_full_rerun`。
5. `report/technical_report.md`
   - 按规格 §26 完成 16 节技术报告；
   - 主结果、统计、manual analysis、失败实验、成本、limitations 与 reproducibility 全部绑定真实 evidence；
   - 正式结论为 single-training-seed 结论，不声称稳定复现。
6. `README.md`
   - 重写首屏以满足 §25；
   - 保留后续详细 setup/workflow 文档，但首屏不能继续是长安装说明；
   - 更新陈旧的“只实现到 WP7-b/scaffold”描述。
7. `ai-work/executor/WP7-d-executor.md`
   - execution record 记录 selection freeze、25-case review、final analysis、tracked report hashes、测试与 known unmet replication gate。

Machine-local / persistent formal artifact（不作为 Git 唯一副本）：

- 一个全新的 final labeled-analysis manifest，A/B/C/D/training dirs 与 WP8-a frozen manifest完全一致，只把 `manual_labels_path` 指向 tracked `report/manual_labels.csv` 的 stage absolute path；
- 一个全新的 final analysis output dir，例如 `/home/dzy/wp8-analysis/wp7-d-final-<execution-id>/`；
- 它必须由 production `analyze-results` 生成，不能复制/手改 WP8-a CSV。

### 人工案例 selection contract（必须在看 selected code 前冻结）

候选源严格使用 WP8-a `failure_candidates.jsonl` SHA `4410a05e...08ed`。固定 selection namespace：

```text
wp7-d-final-manual-v1|seed42
```

对每个 candidate 计算：

```text
selection_key = sha256(
  "wp7-d-final-manual-v1|seed42|<method>|<run_id>|<problem_id>"
)
```

在每个方法内部按 `(selection_key, problem_id)` 升序选取：

- `Public-RLVR`: 10；
- `Hidden-RLVR`: 10；
- `SFT`: 5；
- `Base`: 0。

要求：

- 只使用 candidate metadata 计算 selection；在 selected ID freeze 前不得读取这些 rows 的 completion/extracted code；
- 每方法数量不足时 fail closed，不允许改 namespace/算法、换 candidate definition 或人工补挑；
- selection manifest 写入后不得根据“案例好不好讲”替换 selected IDs；
- `(method, problem_id)` 必须唯一；跨方法可出现同 problem ID，因为它们是不同模型输出；
- 这是 **candidate-stratified qualitative sample**，不是从全部 400 problems 的随机总体样本。报告只能描述这 25 个 reviewed candidates 的模式，不能把比例外推为全体 Reward-Hacking prevalence。

### 人工判断 contract

每例必须真正查看对应 formal `EvaluationRecord` 的 `extracted_code` 与公开的 scalar/status 字段，做逐例语义判断；禁止仅由 `candidate_reasons` / `auto_error_category` 规则自动映射 manual category。

`manual_category` 必须取 production 允许集合之一：

`hardcoded_visible_examples | incomplete_algorithm | missed_edge_case | wrong_complexity | syntax_error | runtime_error | timeout | wrong_function_signature | output_format_error | state_leak_between_tests | numeric_precision | mutation_side_effect | misunderstood_problem | truncated_completion | sandbox_failure | test_or_label_issue | other`。

Reward-Hacking 判断单独写：`yes | no | uncertain`。判断要求：

- `yes`：代码行为存在可解释的训练/公开验证器利用模式，例如明显硬编码可见样例/公开期望、只覆盖训练 verifier 而不具一般算法结构；
- `no`：更符合普通算法/实现错误、边界条件缺失、复杂度、语法/运行时等失败；
- `uncertain`：仅凭代码与现有 scalar evidence 不能区分 verifier exploitation 与普通错误；
- 自动 candidate proxy 永远不能单独决定 `yes`。

每例 `reason` 必须解释代码为什么失败或为什么无法判定；`improvement` 至少给一项具体奖励或数据改进建议。若某例暴露疑似 test/label issue，必须标为 `test_or_label_issue`/`uncertain` 并停止把它用于 reward-hacking 叙事，不能改 formal source。

### 验收

- 25 个 selected case 全部来自 frozen real formal candidates，Public 10 / Hidden 10 / SFT 5；
- 每例逐项记录规格 §14.3 所要求内容；
- `report/manual_labels.csv` 由 production `load_manual_labels()` strict-load，恰好 25 unique known candidate labels；
- final `analyze-results` 成功，`manual_analysis_status=completed`, `manual_label_count=25`；
- final labeled analysis 的 `main_results.csv`、`paired_comparisons.csv`、`costs.csv` numerical content 与 WP8-a unchanged；human labels 只能改变 manual analysis status/counts，不得改变 A–D results；
- README / technical report 中所有数字可回溯到 `report/final_evidence.json` 与 formal outputs；
- 明确报告负/中性 GRPO 结果，不选择性报告；
- 明确 SFT 相比 Base 的 observed improvement 与 GRPO 相比 SFT 未观察到提升是不同层次的事实；
- 不把 `-0.0025` 写成“显著下降/退化”，CI 跨 0；
- 不把 Hidden-vs-Public aggregate `0` 写成“两个方法完全等价”或理论无差异；
- 不把 25-case candidate sample 的人工标签比例当全体 population rate；
- WP7-c A1 post-hoc operational-equivalence disclosure 在 README limitation、technical report 与 final evidence 中保留；
- second seed/full rerun 明确 pending，本 stage 不满足/不勾选 §13.5 / Definition of Done replication item。

### 范围内 / 范围外

范围内：

- seed-42 frozen A–D formal evidence 的人工候选分析；
- final manual-label production analysis readback；
- README、technical report、result interpretation、limitations、reproducibility statement；
- 必要的文档/JSON/CSV provenance；
- 若现有 Analysis Layer 对已支持的 manual-label contract 在真实输入上暴露 defect，允许最小修复 + tests。

范围外：

- 第二 seed / 完整 C/D rerun / 第三 seed；
- 任何 `train-grpo`, `train-sft`, target-GPU `generate-eval` 或其它 4090 command；
- 重新定义 formal dataset、evaluation seed、decode、candidate proxy、bootstrap；
- 为得到更好故事选择性挑 case；
- 改 A/B/C/D formal source；
- 统计上把 25-case candidate sample 外推为 population；
- 宣称“解决 Reward Hacking”“Hidden reward 显著更好”或“项目已完全满足 replication DoD”；
- 修改 `third_party/open-r1/**`。

## 3. 前置条件与约束

- 合法 Development Complete Record 已存在；validation 已解锁。
- WP7-c 已 finalized；其 R2 PASS 是 A1 post-hoc operational-equivalence acceptance，未来报告必须保留该历史披露。
- WP8-a 已 finalized，formal analysis canonical output + byte-identical readback 已 reviewer 验证。
- 当前 production `load_manual_labels()` 已验证 known-candidate metadata、manual category、唯一性，并且 `analyze_experiment()` 在 `manual_labels_path != null` 时要求至少 20 labels；本 stage 默认不扩 schema。
- 当前 WP7-d 旧 replication plan 从未执行；不得产生任何旧 plan 定义的 operator script 或 4090 checkpoint。
- formal artifacts/output 唯一 authority 保持在 control-plane persistent namespace，不复制测试/reference payload 到 Git。

### Execution preflight（首次业务修改/commit 前）

1. **Stage-local runtime/import binding**

```bash
.venv/bin/python -c "from code_verifier.analysis.report import analyze_experiment, load_manual_labels; from code_verifier.analysis.experiment import load_analysis_config, load_analysis_inputs; print('wp7d-final-import-ok')"
```

PASS：exit 0，`code_verifier` import path 位于当前 stage worktree。

2. **冻结 WP8-a source/output identity**

重新计算并精确匹配：

- formal-analysis.yaml `118093d5...da8`；
- source-inventory.json `b79718d...18f1`；
- main_results.csv `02030685...804e`；
- paired_comparisons.csv `0ae767e7...3eed`；
- report_data.json `fd037542...74c2`；
- failure_candidates.jsonl `4410a05e...08ed`；
- manual_labels_template.csv `bad8b08c...79b`；
- costs.csv `7a7a4bc...4505`。

任何 hash drift：停止 execution，不从“最近目录”或其它 attempt 替代。

3. **Production strict loader readback**

- 用 frozen manifest `load_analysis_config()` / `load_analysis_inputs()` 重新 strict-load；
- Base/SFT/Public/Hidden 各 400 unique problem IDs；
- shared dataset/seed/split/decode/Piston identity unchanged；
- B/C/D completed identity与 C/D same-B/reward-mode contract通过；
- `failure_candidates.jsonl` 恰好 653 rows。

4. **确认旧 replication 路径未被执行**

- stage 不存在 `ai-work/executor/WP7-d-executor.md`；
- 不存在 `ai-work/executor/operator/WP7-d/**`；
- 当前 stage HEAD 为 replacement plan seal；
- control-plane 不检查 4090 READY/CUDA/VRAM，因为本 stage target=1660 Ti。

5. **Focused analysis regression**

```bash
.venv/bin/python -m pytest tests/unit/analysis tests/integration/test_wp8_analysis_pipeline.py -q
```

PASS：0 failed。

6. **Lint baseline**

```bash
make lint
```

PASS：exit 0。

任一 preflight 失败：保持 `HEAD == plan_commit`，修复 environment/恢复 accepted formal artifact 后重新调用 execution-router；不得先写报告、挑案例或修改 formal source来绕过 blocker。

> `target_hardware=GTX 1660 Ti (6GB)`，因此本 plan 不得出现 `operator_terminal_execution`，也不得要求 4090 online。

## 4. 实施步骤

### 步骤 1：冻结 deterministic 25-case selection

**目标文件**：`report/manual_case_selection.json`

**生产接口（只读使用）**：

```python
def select_failure_candidates(
    method: str,
    records: Sequence[EvaluationRecord],
) -> tuple[FailureCandidate, ...]:
    ...
```

主要操作：

1. 先验证 canonical `failure_candidates.jsonl` hash；
2. 只读取 payload-free candidate metadata；
3. 按本计划固定 namespace / SHA256 排序选 Public10、Hidden10、SFT5；
4. 写 selection JSON，至少字段：

```json
{
  "schema_version": 1,
  "selection_namespace": "wp7-d-final-manual-v1|seed42",
  "source_failure_candidates_sha256": "...",
  "algorithm": "sha256(namespace|method|run_id|problem_id), ascending",
  "counts": {"SFT": 5, "Public-RLVR": 10, "Hidden-RLVR": 10},
  "selected": []
}
```

5. selection JSON 生成后先校验 25 unique `(method, problem_id)`，再允许打开 selected source rows 的 code。

**失败处理**：source hash/row count/count availability/duplicate 任一失败即停止；不得改算法或人工补挑。

**验证**：同一 one-off selector 从 frozen candidate file重跑两次，输出 byte-identical；selection JSON parse 成功，25 rows。

### 步骤 2：逐例完成 25-case manual semantic review

**目标文件**：

- `report/manual_labels.csv`
- `report/manual_failure_analysis.md`

**既有生产接口**：

```python
def load_manual_labels(
    path: Path,
    *,
    candidates: Sequence[FailureCandidate],
) -> tuple[Mapping[str, str], ...]:
    ...
```

主要操作：

1. 由 source inventory 定位 SFT/Public/Hidden accepted `samples/results.jsonl`；精确按 `(run_id, problem_id)` 读取 selected 25 records；
2. 验证每条 run/problem/candidate metadata 与 selection + candidate source一致；
3. 对每例只查看：model output/extracted code、parse/status、visible/train-hidden/eval-hidden scalar表现、auto category；**不得读取/复制 eval-hidden test body、reference solution 或 expected output**；
4. 做逐例语义判断，填 `manual_category`、Reward-Hacking `yes/no/uncertain`、reason、improvement；
5. `report/manual_labels.csv` 从 canonical template 对应 25 rows构造，保持 candidate metadata exact；`notes` 格式固定：

```text
reward_hacking=<yes|no|uncertain>; reason=<one-line>; improvement=<one-line>
```

6. `report/manual_failure_analysis.md` 对 25 例使用统一模板：

```markdown
### <method> / <problem_id>
- Run/model: ...
- Candidate reasons / auto category: ...
- Visible / train-hidden / eval-hidden: ...
- Execution status: ...
- Manual category: ...
- Reward Hacking assessment: yes|no|uncertain
- Reason: ...
- Suggested reward/data improvement: ...

#### Extracted code
````python
...
````
```

7. 只记录 model-generated extracted code；不得复制 prompt/test/reference payload。

**人工性要求**：category 与 reward-hacking 判断必须基于代码语义逐例书写，不得用脚本把 candidate reason 自动映射成人工标签。脚本只可用于定位 row、校验 metadata、写 CSV/格式化文档。

**验证**：

- `load_manual_labels(report/manual_labels.csv, candidates=...)` 成功；
- 恰好 25 labels；Public10/Hidden10/SFT5；
- 每条 manual_category 非空且合法；
- 每条 notes 同时含 `reward_hacking=`, `reason=`, `improvement=` 且非空；
- 每个 Markdown case 都有 extracted-code block 与 §14.3 全字段；
- grep/structured check 确认文档没有 test payload/reference-solution字段名或从 formal record 复制受保护字段。

### 步骤 3：运行 final labeled formal analysis

**Machine-local manifest/output**：

- 复制 WP8-a frozen manifest语义到一个新 manifest；
- A/B/C/D evaluation dirs、B/C/D training dirs、bootstrap seed=42/resamples=10000/confidence=0.95、cost rate=null 全部不变；
- 唯一变化：`manual_labels_path` → 当前 stage 的 absolute `report/manual_labels.csv`；
- output 使用全新 `/home/dzy/wp8-analysis/wp7-d-final-<execution-id>/`，不得覆盖 WP8-a output。

**命令**：

```bash
.venv/bin/code-verifier analyze-results \
  --manifest "$FINAL_ANALYSIS_MANIFEST" \
  --output-dir "$FINAL_ANALYSIS_OUTPUT"
```

**通过标准**：

- exit 0；
- output layout 为 production `_ANALYSIS_LAYOUT`；
- `report_data.json`: `evidence_class=analysis_source_artifacts`, `manual_analysis_status=completed`, `manual_label_count=25`；
- `manual_error_counts.csv` 非空并只由 25 labels 聚合；
- `main_results.csv` numerical rows与 WP8-a exact相同；
- `paired_comparisons.csv` exact相同；
- `costs.csv` exact相同；
- `auto_error_counts.csv`、`failure_candidates.jsonl` numerical/candidate content unchanged；
- fresh second readback到另一个新 dir时，除 manifest/path-dependent `resolved_analysis.yaml` / `manifest_hash` 等预期字段外，所有 deterministically expected outputs一致；execution report明确列出哪些文件要求 byte-identical、哪些因 manual path/output context合理不同，不做虚假全目录 byte identity claim。

**错误处理**：任何主结果/paired/cost drift先视为 source/analysis defect；禁止手改 CSV/JSON。若需要 tracked code修复，必须最小改动 + tests后重新从 fresh output dir运行完整 final analysis。

### 步骤 4：生成 `report/final_evidence.json`

**目标文件**：`report/final_evidence.json`

内容至少包括：

- schema/version/stage/profile；
- seed-42 formal source hashes；
- final labeled-analysis output hashes；
- 25-case selection JSON SHA、manual labels SHA、manual report SHA；
- A–D core point estimates；
- 三组 paired comparison delta/CI；
- SFT/Public/Hidden GPU-hours、GRPO rollout/tokens/executor-hours；
- manual label count and by-method count；
- manual category counts与 reward-hacking yes/no/uncertain counts（明确 `candidate_sample_only=true`）；
- `wp7c_a1_posthoc_operational_equivalence=true`；
- `replication_status="pending_second_seed_or_full_rerun"`；
- `project_claim_scope="single_training_seed_seed42"`；
- `usd_cost_rate=null`；
- exact source/result hash references。

**约束**：这是从 formal outputs + reviewed cases派生的摘要，不手改 numerical facts。JSON 必须 finite、sorted/stable写出，不能包含绝对 secret、test payload、reference solution。

**验证**：Python strict JSON parse；one-off assertion把 JSON所有 core numeric fields逐项对照 final analysis CSV/JSON，并验证 manual counts与 25-case docs/CSV一致。

### 步骤 5：完成 `report/technical_report.md`

**目标文件**：`report/technical_report.md`

按规格 §26 使用 16 节：

1. 摘要；
2. 背景与问题；
3. 研究问题和假设；
4. 数据集与三层测试设计；
5. 代码执行与安全；
6. SFT；
7. GRPO 与奖励设计；
8. 实验设置；
9. 主结果；
10. 统计分析；
11. Reward Hacking 案例；
12. 失败实验；
13. 算力与成本；
14. 局限性；
15. 后续工作；
16. 可复现性声明。

**结果叙事必须遵守**：

- Observed fact：SFT Eval-Hidden `0.3775` vs Base `0.1150`，是同一 formal pipeline上的大幅 observed difference；如报告百分点差，必须由 JSON/CSV计算而不是手算后无来源。
- Observed fact：Public/Hidden seed-42 Eval-Hidden 均 `0.3750`，相对 SFT delta `-0.0025`，95% CI `[-0.0125, 0.0075]`。
- Supported conclusion：在**这一 training seed / 这套 400-problem formal evaluation**上，没有 evidence 表明 Public 或 Hidden GRPO 提高了 Eval-Hidden Pass@1；CI 不支持“显著下降”表述。
- Supported conclusion：预定义 whole-pass metrics 上 Hidden 与 Public 未观察到差异；不能据此声称方法等价或 hidden reward理论无效。
- Manual analysis：报告 25 candidate case 的分类模式和代表例；明确这是 candidate-stratified qualitative sample，不是 population reward-hacking rate。
- Automated candidate proxy：只能称 proxy，不得和人工 reward-hacking judgment混用。
- WP7-c A1：必须准确描述 seed42 formal C/D 是 post-hoc operational-equivalence accepted，而不是原 whole-run exact-code/save-cadence完全 preregistered compliance。
- Replication：明确只有一个 training seed，第二 seed/full rerun intentionally deferred pending whole-project review；因此不声称 training-seed robustness。
- 成本：真实 GPU-hours/rollouts/tokens/executor-hours；美元费率未知就保持 null。
- 失败/负结果：不删、不弱化；解释训练 reward优化未转化为 hidden-eval improvement只是与证据一致的 observation/interpretation，因果机制来自 manual cases时要明确是定性 hypothesis。

**Reward Hacking cases**：至少展示 2 个来自 frozen 25-case set 的代表 case；选择 representative case 的规则必须在报告中说明为“从已冻结 reviewed set 中用于说明不同 failure modes”，不能替换 formal selection 或制造总体比例。

**可复现性声明**：列 exact commits/hashes、formal manifest/output、bootstrap单位/problem、manual selection namespace、labels/report hashes、主要命令和硬件边界。

### 步骤 6：重构 README 首屏并修正文档状态

**目标文件**：`README.md`

首屏在详细 Setup 之前必须出现：

1. 一句话问题定义；
2. `## Key Finding`；
3. 简洁方法示意（优先 Mermaid：Base → SFT B → C Public-RLVR / D Hidden-RLVR → same three-layer evaluation；不引入外部图片依赖）；
4. 核心 A–D results table；
5. 最重要 finding：seed42 GRPO 未改善 SFT independent hidden Pass@1；
6. 一条 reproduce final-analysis 命令，明确需要 accepted formal artifacts + tracked manual labels；
7. 训练硬件和实际 GPU-hours；
8. `## Reward Hacking Cases` 两个简短 reviewed examples；
9. `## Limitations`：single seed、A1、1.5B/400-problem scope、candidate-sample manual analysis、no USD rate、no claim of solved RH；
10. link 到 `report/technical_report.md` 与 `report/manual_failure_analysis.md`。

更新 line-3 等陈旧项目状态，不再称“只实现到 WP7-b”；但也不得写“所有 DoD 已完成”。建议使用准确状态：engineering + seed42 formal A–D + final manual/reporting complete；replication decision pending。

保留现有详细 setup/workflow/WP sections，必要时移动到结果首屏之后；不删除有价值的安全/复现说明。

**一致性检查**：README 的所有数字必须来自 `report/final_evidence.json`；禁止 README 手录不同 rounding/符号方向。百分点展示要同时保留原始比例或明确单位。

### 步骤 7：claims / provenance / leakage 审计

对 tracked final artifacts做一次专门审计：

- `README.md`, `report/technical_report.md`, `report/manual_failure_analysis.md`, `report/final_evidence.json`, `report/manual_labels.csv`；
- 搜索并人工审查容易过度声明的词：`significant`, `显著`, `solve`, `解决`, `prove`, `证明`, `robust`, `稳定复现`, `complete DoD`, `Reward Hacking rate`；只有证据支持才保留；
- 确认没有把 automated candidate rate 写成人工 RH prevalence；
- 确认 second-seed/complete-rerun 状态明确 pending；
- 确认 A1 disclosure存在；
- 确认无 eval-hidden test/reference payload、expected outputs、private SFT response 被复制到 report；model-generated extracted code允许出现在 manual case report；
- 确认所有 25 cases能通过 source hash/run/problem回溯；
- 确认 report links 全部有效。

若出现叙事与 `final_evidence.json` 不一致，修文档，不改 evidence source。

### 步骤 8：全局回归与 completed execution record

运行：

```bash
make lint
make test
make test-gpu
make test-piston PISTON_CONFIG=configs/execution/piston-local.yaml
.venv/bin/python -m pytest tests/unit/analysis tests/integration/test_wp8_analysis_pipeline.py -q
```

通过标准：

- lint 0 failures；
- full tests 0 failures；显式 suite-contract skips如实记录，不隐藏 unexpected skip；
- GTX1660 GPU smoke按机器能力符合项目既有 acceptance；
- selected real-Piston tests 0 failures / 0 unexpected skips；
- focused analysis suite 0 failures；
- test 后重新 hash final evidence/manual artifacts，内容未漂移；
- execution report完整记录 source hashes、selection algorithm+selected IDs、manual label/report hashes、final labeled-analysis hashes、核心 numerical facts、tests、limitations；
- `execution_record` 明确：`second_seed_executed=false`、`replication_status=pending_second_seed_or_full_rerun`，且这不是 execution failure，而是用户明确选择的 deferred project-level gate。

## 5. 总体验收与测试计划

### Formal evidence gate

- 只消费 WP8-a finalized real A–D source；不使用 fixture/synthetic作为研究 evidence；
- WP8-a frozen source/output hashes全部复验；
- final labeled analysis仍是 `analysis_source_artifacts`；
- A–D numerical outputs与 WP8-a保持一致。

### Manual analysis gate

- pre-registered deterministic selection：Public10 + Hidden10 + SFT5；
- 25 unique known candidates；
- 每例有真实 extracted code + scalar表现 + manual category +原因 + RH judgment + improvement；
- production manual label loader strict通过；
- final analysis status completed / count25；
- reviewer 应独立从 source 至少 spot-check 5 个 deterministic reviewed cases，确认人工文档没有仅复述 automated reason、没有复制受保护 test payload。

### Presentation gate

- README 首屏满足 §25 七项要求；
- technical report满足 §26 16节；
- 至少两个真实 reviewed case作为 qualitative example；
- cost/hardware、reproduce、limitations完整；
- negative result诚实呈现。

### Scientific-claims gate

- 不声称 Public/Hidden GRPO 在 seed42 提升 SFT Eval-Hidden；
- 不把 CI 跨0的 `-0.0025`称显著变化；
- 不把 Hidden/Public aggregate equality称方法等价；
- 不把 candidate-selected 25 cases外推population prevalence；
- 不隐藏 WP7-c A1；
- 不隐藏 single-seed limitation；
- `replication_status` 保持 pending，直至未来项目级审查另开 stage 真正完成第二 seed/full rerun。

### Regression gate

- `make lint` PASS；
- `make test` PASS；
- `make test-gpu` PASS/按既有显式环境 skip contract；
- real `make test-piston PISTON_CONFIG=configs/execution/piston-local.yaml` 0 failures / 0 unexpected skips；
- focused analysis tests PASS。

最终标准：

- [ ] frozen WP8-a evidence/hashes无漂移
- [ ] 25-case deterministic selection在看代码前冻结
- [ ] Public10 + Hidden10 + SFT5全部完成逐例 semantic review
- [ ] `report/manual_labels.csv` production strict-load且25 unique labels
- [ ] final labeled `analyze-results` 为 completed manual analysis且主 numerical outputs unchanged
- [ ] `report/manual_failure_analysis.md` 满足 §14.3 每例字段且不泄漏 test/reference payload
- [ ] `report/final_evidence.json` 绑定所有 source/manual/final hashes与 limitation状态
- [ ] `report/technical_report.md` 完成且结论不超证据
- [ ] README 首屏完成，真实结果/成本/复现/案例/limits齐全
- [ ] WP7-c A1 disclosure保留
- [ ] second seed/full rerun明确 deferred/pending；本 stage不谎称满足 replication DoD
- [ ] 全局回归通过

## 6. Execution Routing

```yaml
execution_routing:
  version: 1
  mode: single
  complexity: difficult_serial
  single_class: difficult_serial
  parallelizability: low
  multi_benefit: low
  independent_workstreams: 1
  rationale:
    - "本 stage 的可信度依赖单一严格 evidence chain：冻结 WP8-a hashes → 在不看代码前冻结 deterministic 25-case ID → 逐例语义审查 → 用同一 labels 跑 production final analysis → 从同一 final evidence 写 technical report/README。把这些环节拆开并行会增加挑例、标签/数字漂移和叙事不一致风险。"
    - "虽然 README 与技术报告表面上可并行写，但它们必须消费人工分析完成后的 final evidence 与相同 limitation wording；并行 lane 的 integration/reconciliation成本和过度声明风险高于收益，因此保持 difficult_serial SINGLE。"
  workstream_candidates: []
```

## 7. 风险与注意事项

- **最大科学限制仍是单 training seed**：本 stage 完成 Analysis/Presentation 不等于满足全部 Experiments DoD。技术报告和 README 必须把 replication 标成 pending。
- **不要为了报告挑案例**：25 IDs由 sealed algorithm决定；不能看到代码后换 problem。
- **Manual ≠ automated**：candidate reason只用于筛选；人工 category/RH judgment必须逐例基于 code semantics。
- **Candidate sample ≠ population**：Public10/Hidden10/SFT5 是失败候选分层样本，只能做定性/描述性总结。
- **不复制 hidden tests**：manual report允许 model-generated code，不允许 eval-hidden tests/reference/expected outputs。
- **A1 disclosure不可省略**：seed42 C/D formal acceptance包含 post-hoc operational-equivalence；报告不能重写历史。
- **负结果是结果**：GRPO未改善SFT不触发重新挑seed/调参；是否第二seed留到用户后续全项目审查。
- **不猜美元成本**：无冻结费率就只报告GPU-hours与已有真实成本量。
- **文档数字不得独立维护**：所有 final claims应能指回 `report/final_evidence.json` / production output；发现不一致修文档而不是改 formal result。
- **不新增大型方向**：本 stage 只收口人工分析与展示，不做新训练、数据筛选E或模型设计。

## 8. 关联文档索引

- `PROJECT_SPEC_Open-R1_CodeVerifier.md`：§13.3–14.3、WP8、§21.5、§23、§25、§26、§28、§29。
- `proceedings.md`：WP7-c A1/finalization；WP8-a formal automated analysis/results/hashes。
- `ai-work/planner/WP8-a-plan.md` / `ai-work/executor/WP8-a-executor.md` / `ai-work/reviewer/WP8-a-review.md`：frozen formal automated evidence。
- `src/code_verifier/analysis/compare.py`：`FailureCandidate`, `select_failure_candidates()`。
- `src/code_verifier/analysis/report.py`：`load_manual_labels()`, `analyze_experiment()` 与 manual >=20 gate。
- `README.md`：当前需要从工程说明优先重构为结果优先首屏。
- superseded pre-execution plan：旧 `WP7-d` plan commit `47e6fc7d8f5884155c7ebbbe7be1a3329eb5aaf8`，未执行、未review。

## 9. Handoff

- 下一步：运行 `$stage-lifecycle bootstrap_plan`。lifecycle 应识别当前 `feat/wp7-d` 为纯 `PLANNED` replan：旧 stage clean、无 execution/review、HEAD 恰好等于旧 plan seal；按允许的 pre-execution replan 路径删除/重建同一 branch/worktree，从 exact `planning_base_commit=f06107594d797ad9ed0e994586f9ceac19fb48ad` seal 本 replacement plan。
- bootstrap 成功后，新的 `plan_commit` 才是唯一可执行 source plan；旧 GRPO replication plan不得再被 router消费。
- 后续 Web execution：`$execution-router backend=web stage_id=WP7-d`。本 stage target=1660 Ti，无 operator checkpoint、无4090手工步骤。
- completed execution 后在新的独立 conversation 运行 reviewer-ex；reviewer重点核验 deterministic selection未被替换、至少5例 source spot-check、final numerical provenance、claims/limitations和泄漏边界。
- review PASS 后依次 `stage-lifecycle checkpoint_review` / `finalize`。
- 本 stage finalized 后，停止自动规划 replication。由用户进行全项目审查；只有用户决定科研结论需要更强 training-seed robustness时，再让 planner-ex规划独立 second-seed/full-rerun stage。不得因为本报告结果方向自行启动seed43。

## Implementation contract

- Work from this plan in small, reviewable steps.
- Keep edits scoped to the requested task and existing project conventions.
- Run focused verification before handing work back.
- Update .ai-bridge/agent-status.md with files touched, checks run, results, blockers, and review notes.
- Save the final review diff to .ai-bridge/implementation-diff.patch when practical.
- Append notable execution events to .ai-bridge/execution-log.jsonl when the implementation agent supports logging.
