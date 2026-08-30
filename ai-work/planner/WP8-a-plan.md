# WP8-a 实施计划（正式 A–D 自动统计、paired bootstrap、成本与失败候选）

## 1. 元信息

| 项 | 值 |
|---|---|
| stage_id | `WP8-a` |
| stage_profile | `validation` |
| control_plane_hardware | `GTX 1660 Ti (6GB)` |
| target_hardware | `GTX 1660 Ti (6GB)` |
| evidence_class | `real-training/numerical` |
| development_terminal | `false` |
| 目标 WP | `WP8`：实验聚合与错误分析（formal automated-analysis 子阶段） |
| 规格依据 | `PROJECT_SPEC_Open-R1_CodeVerifier.md` §20 WP8（目标/交付/验收）、§21.1、§19 metrics/bootstrap 约束；`proceedings.md` WP5-c/WP6-d/WP7-c formal validation evidence |
| 前置状态 | `proceedings.md` 已存在合法 `## Development Complete Record`；正式 Base A、SFT B、Public GRPO C、Hidden GRPO D 均已完成真实 validation，WP7-c 明确指向下一 dependency-ready 工作为 WP8 正式 A–D comparison/bootstrap/statistical analysis/error analysis/report |
| `planning_base_commit` | `4c3675439a445663e3a158c65601b73785ba78a5` |
| proposed branch | `feat/wp8-a` |
| proposed worktree | `.worktrees/wp8-a` |
| final plan path | `ai-work/planner/WP8-a-plan.md` |
| execution report path | `ai-work/executor/WP8-a-executor.md` |
| review path | `ai-work/reviewer/WP8-a-review.md` |
| plan lifecycle | planner-ex handoff → `stage-lifecycle bootstrap_plan` → committed plan seal |

> 本 stage 是 **formal-evidence-only control-plane validation**：不产生新的 24GB GPU 计算，不包含 operator target-GPU gate。A/B/C/D 的 generation/training/verification 已由 finalized WP5-c/WP6-d/WP7-c 提供；本 stage 只消费这些正式 artifacts 做严格 identity 绑定、A–D 聚合、problem-level paired bootstrap、training-curve/cost 汇总、failure-candidate 生成以及后续人工 20-case analysis 的标注包。

## 2. 目标与范围

### 目标（规格原文对应）

WP8 要“形成可写入 README 和简历的结果”；validation track 最终需基于真实 A–D artifacts 生成 A–D 主结果表、gap 指标、bootstrap CI、训练曲线、失败候选、人工标注模板和成本报告，并保证所有数字可追溯到逐样本结果、C/D comparison 为 paired comparison、至少 20 个案例由人工分析、报告包含正向或负向结论。

本 `WP8-a` 只关闭其中**自动、可重复、无需人工判断**的一层：以 finalized A/B/C/D 正式 artifacts 为唯一输入，生成正式 A–D 自动统计结果和 deterministic failure-candidate/manual-label template。人工至少 20 case 的分类与最终 narrative/report conclusion 明确留给后续 stage；不得在本 stage 将 `manual_analysis_status=pending` 冒充人工验收完成。

### 交付

- 由 production `analyze-results` 生成的正式 `main_results.csv`；
- `Public-RLVR vs SFT`、`Hidden-RLVR vs SFT`、`Hidden-RLVR vs Public-RLVR` 三组 problem-level paired comparison 与 bootstrap CI；
- 正式 A–D confidence intervals、gap 指标与逐方法聚合；
- SFT/Public/Hidden 的正式 training-curve long-form CSV；
- SFT/Public/Hidden 的正式 GPU-hours / rollout / generated-token / executor-hours 成本输入；
- deterministic `failure_candidates.jsonl` 和 `manual_labels_template.csv`，供后续至少 20 case 人工分析；
- `report_data.json` / `resolved_analysis.yaml`，包含 formal source identity、逐源 `results_sha256`、bootstrap contract、`manual_analysis_status=pending`；
- execution report 中记录输入 formal evidence identities、输出文件 hashes、关键数值和 reproducibility/readback evidence。

### 验收

- 所有自动分析数字由正式逐样本 evaluation/training artifacts 计算，不手工录入；
- A/B/C/D evaluation 必须通过 production strict loader，使用相同 problem-id set、dataset hash、seed、split、device/generation definition 与 Piston definition；
- B checkpoint 必须通过 completed SFT identity loader；C/D 必须通过 completed GRPO identity loader并共享同一个 B parent，reward mode 分别为 public/hidden；
- C/D paired comparison 必须按 `problem_id` 成对，bootstrap unit 为 problem；
- 输出 `evidence_class` 必须是 `analysis_source_artifacts`，禁止 `engineering_fixture_synthetic`；
- `manual_analysis_status` 必须保持 `pending` 且 `manual_label_count=0`，直到后续人工 stage；
- 自动结果必须至少与 finalized proceedings 中已公开的 A/B/C/D point estimates一致；任何不一致都视为 provenance/input mismatch 或分析缺陷，不能手改 CSV；
- 本 stage 不声称已满足 WP8 “至少 20 个案例人工分析”或最终正/负 narrative conclusion。

### 范围内 / 范围外

- 范围内：正式 A–D artifact discovery/binding、strict loader、现有 production Analysis Layer 的真实 execution、bootstrap/paired comparison、cost/curve/failure candidate、artifact hash/readback、必要的最小 bug repair（若真实 formal input 暴露 production 实现缺陷，则在同一 validation stage execution/review 闭环修复并重新跑受影响分析）。
- 范围外：新的 Base/SFT/GRPO generation/training/verification；任何 4090 command；修改 A–D experiment definition；重新定义 bootstrap/candidate 指标；人工填至少 20 labels；最终 README/简历 narrative；把 WP7-c post-hoc A1 历史偏差隐藏掉。
- 不修改 `third_party/open-r1/**`。
- 不把 formal artifact 唯一副本复制进 stage worktree；分析输出写入 control-plane persistent artifact root。

## 3. 前置条件与约束

- planner guard 已在整理后确认：primary checkout clean；只剩主 worktree；已合并 `feat/wp7-c-piston-resilience` worktree/branch 已删除；`piston-reverse-ssh-maintenance` clean worktree 已删除但其未合并 provenance branch保留；旧 `backup/wp7-c-concurrent-660c` 已改名 `archive/wp7-c-concurrent-660c`；其它未合并 stage history 均为 `archive/*`，两条 `chore/*` 为 workflow-maintenance history，不是 active stage。
- `.ai-bridge/current-plan.md` 在本次 planner 开始时不存在；`git ls-files .ai-bridge` 为空。
- `proceedings.md` 的合法 `Development Complete Record`：terminal stage `WP8`，`completion_inventory_verified: true`，`development_complete: true`。
- 正式 source facts：
  - Base A finalized by WP5-c；proceedings records Visible `0.1225` / Train-Hidden `0.1175` / Eval-Hidden `0.115` and 400 problems.
  - SFT B finalized by WP6-d；proceedings records Visible `0.3525` / Train-Hidden `0.335` / Eval-Hidden `0.3775`, global step 314.
  - Public C finalized by WP7-c；proceedings records Visible `0.3625` / Train-Hidden `0.34` / Eval-Hidden `0.375`, 400 verified problems, completed GRPO step 300.
  - Hidden D finalized by WP7-c；same three Pass@1 values `0.3625 / 0.34 / 0.375`, 400 verified problems, completed GRPO step 300.
- WP7-c R2 PASS 使用 committed A1 post-hoc operational-equivalence acceptance；本 stage 的 report/provenance 必须保留这一事实，不得把 C/D 描述为“原 sealed preregistered exact-code/save-cadence 全部严格满足”。自动 numerical computation 本身仍只消费 accepted canonical C/D artifacts。
- production Analysis Layer 已存在并已通过 development fixture validation：`load_analysis_config()`, `load_analysis_inputs()`, `compare_evaluation_records()`, `load_training_curve_rows()`, `build_cost_row()`, `load_manual_labels()`, `analyze_experiment()`；本 stage 默认先运行冻结实现，不因“validation”而主动重写代码。

### Execution preflight（首次业务修改/commit 前）

1. **Stage runtime / imports**
   - 命令：`.venv/bin/python -c "from code_verifier.analysis.experiment import load_analysis_config, load_analysis_inputs; from code_verifier.analysis.report import analyze_experiment; print('analysis-import-ok')"`
   - 通过标准：exit 0，import 必须来自当前 `WP8-a` stage worktree。
2. **Control-plane test runtime**
   - 命令：`.venv/bin/python -m pytest tests/unit/analysis -q`
   - 通过标准：analysis 单元测试全绿。
3. **真实 loopback Piston 健康性**
   - 命令：`make test-piston PISTON_CONFIG=configs/execution/piston-local.yaml`
   - 通过标准：selected real-Piston tests 0 failed / 0 skipped。虽然本 stage 不重新 verify 400 completions，但正式 A/B/C/D metadata 的 Piston definition 仍属于 source identity；control plane 必须处于项目 canonical Piston 环境。
4. **Formal source availability / identity**
   - 解析 control-plane 已同步的正式 artifact roots；不得从 fixture、`tests/fixtures/**`、repo-local synthetic outputs 或 archived failed/quarantine attempt 代替 canonical source。
   - 对 A/B/C/D 四个 evaluation run 分别要求 `run.json`, `resolved_config.yaml`, `samples/results.jsonl` 存在且 `status=completed`；每组应为 400 unique problems。
   - 对 B/C/D training run 要求 production completed-checkpoint loader 可加载；C/D 必须绑定同一 completed B。
   - 若 control plane 尚未拥有这些 formal small/analysis-required artifacts，停止 execution，不提交业务修复；先由用户按既有 workflow byte-for-byte 同步 accepted canonical artifacts/evidence。不得连接 4090 重新生成。
5. **Baseline global checks can start**
   - 命令：`make lint`。
   - 通过标准：exit 0。

任一 preflight 失败：保持 `HEAD == plan_commit`；这是 input/environment blocker，不通过修改 source 绕过 formal provenance。

> `target_hardware=GTX 1660 Ti (6GB)`，因此本 plan **不得**包含 `operator_terminal_execution` block，也不得要求 4090 READY/GPU/cache/root 在线。

## 4. 实施步骤

### 步骤 1：冻结 formal A/B/C/D source manifest 与 expected identity

**目标文件**：默认无 tracked source 修改。execution 在 `$CODE_VERIFIER_ARTIFACT_ROOT/analysis/wp8-a-input/`（或等价 control-plane persistent namespace）创建 machine-local、非 Git 的 `formal-analysis.yaml` 与 `source-inventory.json`；正式输出不能放 stage worktree。

**既有生产符号（只读调用）**：
```python
def load_analysis_config(path: Path) -> AnalysisConfig:
    ...


def load_analysis_inputs(config: AnalysisConfig) -> AnalysisInputs:
    ...
```

**主要功能**：
- machine-local manifest 精确绑定 accepted canonical Base A / SFT B / Public C / Hidden D evaluation dirs，以及 B/C/D completed training dirs；`manual_labels_path: null`。
- bootstrap 固定使用项目正式分析合同（seed/resamples/confidence level 取现有 WP8 development 定义；不得为获得更好 CI 而临时调整）。
- `gpu_hour_cost_usd` 若项目没有预先冻结可审计费率，保持 `null`；不得事后猜一个价格。成本表仍必须包含真实 gpu_hours/rollouts/tokens/executor-hours，`estimated_cost_usd` 可为 null。
- 在真正分析前调用 `load_analysis_inputs()`；把四个 `run_id/model_id/model_revision/checkpoint/dataset_hash/config_hash/project_commit/open_r1_commit/dependency_lock_hash/piston_config_sha256/results_sha256`、B/C/D completed checkpoint identity、formal source absolute path 记录到 `source-inventory.json`。
- inventory 必须明确 C/D accepted-under-A1 disclosure，引用 `ai-work/planner/WP7-c-amendments.md` / `ai-work/reviewer/WP7-c-review.md` 的已提交 provenance，不改变 numerical source。

**错误处理**：任一 identity mismatch、mixed rows、duplicate problem IDs、A–D shared evaluation contract mismatch、C/D parent/reward mode mismatch均 fail closed；禁止编辑 formal source artifacts来“修到能读”。

**测试方案**：
- 运行 `tests/unit/analysis/test_experiment.py`；
- 对真实 manifest 用一个 Python/CLI read-only preflight 调用 `load_analysis_inputs()`，要求成功且四组 records 各 400。

**验证命令与标准**：
```bash
.venv/bin/python -m pytest tests/unit/analysis/test_experiment.py -q
```
以及 execution 记录的 real-input loader 命令；全绿且 inventory hashes 完整。

### 步骤 2：运行正式 `analyze-results` 自动分析

**目标文件**：无 tracked source 修改；写 control-plane persistent output，例如 `$CODE_VERIFIER_ARTIFACT_ROOT/analysis/wp8-a-formal-<run-id>/`，该 output dir 必须全新且不存在。

**既有生产符号**：
```python
def analyze_experiment(
    config: AnalysisConfig,
    *,
    output_dir: Path,
    evidence_class: Literal[
        "analysis_source_artifacts", "engineering_fixture_synthetic"
    ] = "analysis_source_artifacts",
) -> AnalysisSummary:
    ...
```

**CLI**：
```bash
.venv/bin/code-verifier analyze-results \
  --manifest "$FORMAL_ANALYSIS_MANIFEST" \
  --output-dir "$FORMAL_ANALYSIS_OUTPUT"
```

**主要功能**：
- 必须使用默认/显式 `analysis_source_artifacts`；不得使用 synthetic evidence class。
- 生成完整 `_ANALYSIS_LAYOUT`：`report_data.json`, `main_results.csv`, `paired_comparisons.csv`, `auto_error_counts.csv`, `training_curves.csv`, `failure_candidates.jsonl`, `manual_labels_template.csv`, `manual_error_counts.csv`, `costs.csv`, `resolved_analysis.yaml`。
- `manual_labels_path=null`，因此本 stage 正式输出应 `manual_analysis_status=pending`, `manual_label_count=0`；`manual_labels_template.csv` 是后续人工输入模板，不是已标注结果。
- output dir 的原子创建语义必须保留；失败 run 不允许留下看似 completed 的 canonical output。

**测试方案**：
- `tests/unit/analysis/test_report.py`；
- `tests/integration/test_wp8_analysis_pipeline.py`（fixture 仍只作为代码 regression test，不作为本 stage validation evidence）。

**验证命令**：
```bash
.venv/bin/python -m pytest tests/unit/analysis tests/integration/test_wp8_analysis_pipeline.py -q
```
通过标准：全绿；formal CLI exit 0；输出 layout 精确完整。

### 步骤 3：核验 A–D 主结果、confidence intervals 与 paired comparisons

**目标文件**：无 tracked source修改；只读正式 output。

**既有生产符号**：
```python
def compare_evaluation_records(
    left_method: str,
    left_records: Sequence[EvaluationRecord],
    right_method: str,
    right_records: Sequence[EvaluationRecord],
    *,
    bootstrap_seed: int,
    bootstrap_resamples: int,
    confidence_level: float,
) -> PairedComparison:
    ...
```

**主要功能**：
- `main_results.csv` 恰好 4 个方法且每组 `total_problems=400`。
- point estimates 必须与 finalized proceedings 的 accepted formal values匹配（以 production recomputation 为 authority，但任何差异都先视为 source identity/analysis defect并停止）：
  - Base A: Visible 0.1225, Train-Hidden 0.1175, Eval-Hidden 0.115；
  - SFT B: Visible 0.3525, Train-Hidden 0.335, Eval-Hidden 0.3775；
  - Public C: Visible 0.3625, Train-Hidden 0.34, Eval-Hidden 0.375；
  - Hidden D: Visible 0.3625, Train-Hidden 0.34, Eval-Hidden 0.375。
- `paired_comparisons.csv` 必须恰好包含三组：Public-SFT、Hidden-SFT、Hidden-Public；每组 400 paired problems；CI finite、有序、estimate 落在合理统计域，bootstrap unit在 `report_data.json` 为 `problem`。
- 对 C/D 特别验证按相同 `problem_id` pairing；不能用两个独立 bootstrap interval 相减替代 paired bootstrap。

**错误处理**：若 C 与 D point estimates相同，也必须保留真实 paired delta/CI；不得因为 aggregate 相同就省略 paired comparison。

**测试方案**：
- `tests/unit/analysis/test_compare.py`；
- execution 另写一次只读 assertion script/one-liner检查 formal CSV，不把临时脚本提交仓库。

### 步骤 4：核验 training curves 与成本 provenance

**目标文件**：只读 `training_curves.csv`, `costs.csv` 及源 B/C/D training artifacts。

**既有生产符号**：
```python
def load_training_curve_rows(run_dir: Path, *, method: str) -> tuple[TrainingCurveRow, ...]:
    ...


def build_cost_row(
    run_dir: Path,
    *,
    method: str,
    gpu_hour_cost_usd: float | None,
) -> CostRow:
    ...
```

**主要功能**：
- training curves 必须来自 source `metrics.jsonl` 中 finite `record_type=trainer` scalars；不得从 README/proceedings 手录。
- 成本行必须至少覆盖 SFT/Public/Hidden；SFT 的 rollouts/generated_tokens/executor_hours 按生产 schema为 null，GRPO 从 strict rollout/reward logs复算。
- B 成功训练 attempt 的 `gpu_hours` 应与 finalized WP6-d provenance `0.5215871774233367` 一致；C/D 的 gpu_hours/rollouts/tokens/executor-hours必须来自 accepted canonical C/D source，不从失败/quarantine attempt混入。
- `gpu_hour_cost_usd=null` 时 `estimated_cost_usd=null` 是合法且更诚实的正式输出；不得为满足“成本报告”强造美元费率。

**测试方案**：`tests/unit/analysis/test_report.py` 中 curve/cost strict schema cases；real-output source-to-derived spot checks至少各抽 SFT/C/D 一项。

### 步骤 5：核验 deterministic failure candidates 与后续人工标注包

**目标文件**：只读 `failure_candidates.jsonl`, `manual_labels_template.csv`, `report_data.json`。

**既有生产符号**：
```python
def select_failure_candidates(
    method: str,
    records: Sequence[EvaluationRecord],
) -> tuple[FailureCandidate, ...]:
    ...
```

**主要功能**：
- candidate selection 必须 deterministic、按 problem_id stable，候选仅包含 pointer/metric/reason，不复制 completion/code/tests/reference payload。
- Hidden-RLVR 专属 `train_hidden_pass_eval_fail` reason 不能泄漏到其它方法。
- `manual_labels_template.csv` 每行必须绑定 `method/run_id/problem_id/candidate_reasons/auto_error_category/source_results_path`，manual fields为空；后续人工 stage 只能从这些 known candidate中至少选择 20 unique labels。
- 如果候选总数少于 20，WP8-a 本身仍可完成自动分析，但 execution report 必须标记后续 WP8-b 的人工验收会被阻塞，需要 reviewer/planner决定是否扩大**预先定义且不改变研究结论的候选机制**；不得在本 stage临时降低人工数量或伪造 labels。
- `report_data.json` 必须明确 `manual_analysis_status=pending`, `manual_label_count=0`, `reward_hacking_candidate_status=automated_proxy_not_human_conclusion`。

### 步骤 6：formal artifact hash/readback 与 execution evidence 封存

**目标文件**：`ai-work/executor/WP8-a-executor.md`（由 executor 按统一 execution record contract写）；正式 analysis output仍留在 persistent artifact root。

**主要功能**：
- 对 input manifest、source inventory、9 个 output files逐一记录 path/size/SHA256；至少 `report_data.json`, `main_results.csv`, `paired_comparisons.csv`, `training_curves.csv`, `failure_candidates.jsonl`, `manual_labels_template.csv`, `costs.csv`, `resolved_analysis.yaml` 都有 SHA256。
- 重新执行只读 strict load/readback，确认同一 manifest重复计算关键 rows/hash deterministic；如果 production output 包含不可避免的绝对路径，至少 numerical tables/candidate ordering/bootstrap outputs必须稳定，并记录 manifest hash/source hashes。
- execution record摘录关键 A–D point estimates、三组 paired deltas/CIs、candidate count、training cost scalars、manual status；完整 raw rows不复制进 Git report。
- 明确记录 WP7-c C/D accepted under A1 post-hoc operational-equivalence disclosure。
- 默认允许 `result_code_commit == plan_commit`：如果 formal execution在冻结代码上一次通过，不为了制造 code commit修改 tracked 文件。若 formal input 暴露真实 production bug，需要最小 tracked repair + targeted regression test，再重新完整运行本 stage受影响分析并记录新 `result_code_commit`。

### 步骤 7：全局短时 regression / acceptance

**目标文件**：无新增范围。

**验证命令**：
```bash
make lint
make test
make test-gpu
make test-piston PISTON_CONFIG=configs/execution/piston-local.yaml
```

**通过标准**：
- lint 0 failures；
- full test 0 failures（项目已有 explicit opt-in skips按当前 suite contract记录，但不得隐藏 unexpected skip）；
- GPU smoke 0 failures；
- selected real-Piston acceptance 0 failures / 0 skipped；
- formal analysis readback仍绑定同一 accepted A/B/C/D artifacts，未因 tests改变。

## 5. 总体验收与测试计划

- **Formal source gate**：A/B/C/D 四组 accepted canonical evaluation artifacts各 400 unique problem IDs；A/B/C/D shared dataset/seed/split/generation/Piston contract strict通过；B/C/D completed checkpoint identity strict通过；C/D共享同一 B parent且 reward modes正确。
- **Formal automated analysis gate**：`analyze-results` 对 real source artifacts exit 0；`evidence_class=analysis_source_artifacts`；9-file output layout完整；`manual_analysis_status=pending`。
- **Numerical traceability gate**：A/B/C/D point estimates与 finalized proceedings一致；每个 derived row可追溯到 source results/training logs；source/result SHA256写入 evidence。
- **Statistical gate**：三组 paired comparisons均有400个 problem-level pairs与 deterministic bootstrap CI；C/D 即使 aggregate点估计相同也保留真实paired delta/CI。
- **Curve/cost gate**：SFT/Public/Hidden curves来自真实 trainer history；cost来自真实 completed run metadata/rollout/reward logs；不猜美元费率。
- **Failure-analysis preparation gate**：candidate generation deterministic、payload-free；manual template完整；不把自动 candidate当人工结论。
- **Regression gate**：focused analysis tests、integration WP8 fixture test、`make lint`、`make test`、`make test-gpu`、真实 selected `make test-piston` 全部通过。
- **明确未关闭的 WP8 validation acceptance**：至少 20 个案例人工分析、manual error summary、最终 README/简历/技术报告 narrative与正向或负向结论。后续 stage 必须消费 WP8-a 的 sealed formal output hashes和manual template，不能重新挑一套更有利的自动结果。

最终标准：
- [ ] formal source identity全部严格通过且无 synthetic/mock替代；
- [ ] A–D main results / gap / CI / paired comparison均由 production代码生成；
- [ ] training curves / costs / candidates全部可追溯；
- [ ] outputs与source hashes记录完整；
- [ ] C/D A1 post-hoc disclosure保留；
- [ ] manual status明确 pending，没有伪造 20-case completion；
- [ ] 全部短时 regression gates通过。

## 6. Execution Routing

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
    - "本 stage 主要是单条 formal provenance chain：先绑定 A/B/C/D accepted sources，再运行同一个 production analyzer，随后对其派生表/CI/curve/cost/candidate 做顺序 readback；输入身份错误会使所有后续工作失效，天然串行。"
    - "默认 zero-code validation execution；即使 formal artifacts 暴露 bug，repair 也需要围绕同一 Analysis Layer最小修改并重新跑完整 formal readback。拆成 MULTI 会增加 source/output identity协调成本，不能带来高并行收益。"
  workstream_candidates: []
```

## 7. 风险与注意事项

- **最主要风险是 source selection 错误**：A/B/C/D 历史中存在失败/quarantine/旧 attempt；必须只绑定 finalized accepted canonical source，不能按“目录最新”猜。
- **WP7-c 历史偏差必须披露**：C/D final numbers可用于正式分析，但 provenance narrative必须说明 R2 是在 A1 post-hoc operational-equivalence amendment 下通过，而不是原 sealed exact-code/save-cadence完全严格满足。
- **人工分析不能自动化冒充**：本 stage只生成候选和模板；至少20个case的人工判断必须由后续独立 stage完成。
- **没有冻结费率就不报美元成本**：真实 GPU-hours等仍是成本报告正式输入，estimated USD可以null。
- **不要运行新的 4090 job**：如果 formal source缺少小文件，优先同步 accepted evidence；本 stage不得重新训练或重新生成 A/B/C/D。
- **不要修改 formal source artifacts**：任何 schema/identity mismatch都应先定位 wrong source或production bug；修代码后从immutable inputs重新分析，不原地“修”source JSON/CSV。

## 8. 关联文档索引

- `PROJECT_SPEC_Open-R1_CodeVerifier.md`：WP8 §目标/交付/验收；§21.1通用 review；metrics/bootstrap相关约束。
- `proceedings.md`：`## Development Complete Record`；WP5-c Formal Base A；WP6-d Formal SFT B；WP7-c Formal Public/Hidden GRPO C/D；WP7-c A1 disclosure；WP7聚合状态指向WP8 final validation。
- `src/code_verifier/analysis/experiment.py`：formal manifest/source identity strict loader。
- `src/code_verifier/analysis/compare.py`：problem-paired comparison与failure candidate。
- `src/code_verifier/analysis/report.py`：curve/cost/manual/output generation与`analyze_experiment()`。
- `tests/unit/analysis/**`、`tests/integration/test_wp8_analysis_pipeline.py`：工程 regression contract。

## 9. Handoff

- 下一步：运行 `$stage-lifecycle bootstrap_plan`，使用本计划正文创建 `feat/wp8-a` / `.worktrees/wp8-a` 并把最终计划 seal 到 `ai-work/planner/WP8-a-plan.md`。
- bootstrap 前仍需重新确认 `main HEAD == 4c3675439a445663e3a158c65601b73785ba78a5`、只有 primary worktree、没有新 active stage、primary clean、`.ai-bridge/**` zero-tracked。
- 在 bootstrap 成功并得到 `plan_commit` 前，不得调用 execution-router。

## Implementation contract

- Work from this plan in small, reviewable steps.
- Keep edits scoped to the requested task and existing project conventions.
- Run focused verification before handing work back.
- Update .ai-bridge/agent-status.md with files touched, checks run, results, blockers, and review notes.
- Save the final review diff to .ai-bridge/implementation-diff.patch when practical.
- Append notable execution events to .ai-bridge/execution-log.jsonl when the implementation agent supports logging.
