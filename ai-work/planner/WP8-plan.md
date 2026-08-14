# WP8 实施计划（实验聚合、错误分析与 development closeout）

## 1. 元信息

| 项 | 值 |
|---|---|
| stage_id | `WP8` |
| stage_profile | `development` |
| target_hardware | `GTX 1660 Ti (6GB)` |
| evidence_class | `engineering` |
| development_terminal | `true` |
| 目标 WP | `WP8`：实验聚合与错误分析 |
| 规格依据 | `PROJECT_SPEC_Open-R1_CodeVerifier.md` §6 Analysis Layer、§19.1 Metrics、§19.2.1、§20.0、WP8、§21.1/§21.5、§23、§25–§29 |
| 前置状态 | `proceedings.md`：WP0–WP5 development 已 finalized；WP6-a/WP6-c 已完成 SFT development；WP7-a/WP7-b 已完成 GRPO development；真实 B/C/D 与最终 A–D 数值仍锁定在 validation track；WP8 development 尚未完成 |
| `planning_base_commit` | `3ef7f87b6c5ac6026da9504cd22a00c2344e00a0` |
| proposed branch | `feat/wp8` |
| proposed worktree | `.worktrees/wp8` |
| final plan path | `ai-work/planner/WP8-plan.md` |
| execution report path | `ai-work/executor/WP8-executor.md` |
| review path | `ai-work/reviewer/WP8-review.md` |
| plan lifecycle | planner-ex handoff → `stage-lifecycle bootstrap_plan` → committed plan seal |

## 2. 目标与范围

### 目标（规格）

完成 WP8 development track：实现 A–D 聚合、paired comparison、bootstrap、图表/报告输入、失败候选、人工标注模板与成本核算的生产代码和严格 schema，并使用 deterministic fixture/synthetic rows 验证工程路径。该 stage 完成后同时执行 development closeout；不得在 GTX 1660 Ti 上启动真实 SFT/GRPO，也不得生成或宣称正式 A–D 数值、真实训练曲线结论、成本结论或人工案例结论。

### 交付

- 可追溯的 A–D 主结果表输入与 CSV；
- gap 与 paired bootstrap comparison；
- plot-ready training-curve 数据；
- deterministic reward-hacking/failure candidates；
- 人工标注模板及可选已完成人工标注汇总入口；
- B/C/D 成本表输入与 CSV；
- report/README 可直接消费的结构化 `report_data.json`；
- `analyze-results` CLI 与严格 manifest；
- terminal development closeout evidence。

### 验收

- 所有 aggregate/comparison 数字能追溯到具体 evaluation `results.jsonl`、training run metadata 或 GRPO rollout/reward logs；
- 不手工录入图表数据；
- C/D comparison 必须按 `problem_id` paired，使用 problem-level paired bootstrap 95% CI；
- failure candidate 只是自动候选，不冒充人工结论；人工分类入口必须支持 validation 阶段至少 20 个唯一案例；
- synthetic/fixture 只验证 schema/计算/错误路径，不写入 README/报告作为真实研究数字；
- stage 末尾完整 closeout 通过后才可 `development_terminal=true` finalize。

### 范围内 / 范围外

- 范围内：Analysis Layer、必要的 project-owned training/reward scalar logging 补齐、CLI、测试、命令文档、terminal closeout。
- 范围外：真实 Base/SFT/GRPO optimizer run、正式 checkpoint、正式 A–D 评测、真实人工 20-case 结论、最终 README 数值/技术报告结论、任何 4090 validation execution。
- 不新增 plotting dependency；development 只生成 deterministic CSV/JSON 图表输入，真实图与结论留到 validation。
- 不修改 `third_party/open-r1/**`。

## 3. 前置条件与约束

- 当前 planner active-stage guard 已确认：primary checkout 只有 `main` worktree；未合并分支仅有 `archive/*` 历史，不属于 active stage；`.ai-bridge/current-plan.md` 在本次 planning 前不存在；`.ai-bridge/**` zero-tracked。
- WP6/WP7 fixture/fake checkpoint 只能用于 development tests，绝不能进入正式 B/C/D 或成本/研究结果。
- A/B/C/D 统一评测必须使用相同 dataset/problem set、split、seed 与 deterministic generation parameters；B/C/D checkpoint identity 必须通过现有 strict loaders 重新验证，不能只信 manifest 字符串。
- C/D 必须来自同一个 completed B parent；Public/Hidden GRPO reward mode 与现有 pair/fairness contract 保持不变。
- Analysis 输出只能复制必要的 aggregate/provenance scalar。除 `failure_candidates.jsonl` 的 source pointer 外，不复制 completion/extracted code/tests/reference/starter/SFT response；人工查看原始 completion 时通过 source evaluation `samples/results.jsonl` 按 `run_id + problem_id` 回溯。
- 所有 JSON 必须 strict、finite、JSON-safe；所有 CSV 采用固定列顺序、LF line endings、UTF-8。
- 不添加 backward-compat schema reader。WP8 定义的新 analysis manifest/output schema 与本 stage 更新后的 reward/SFT metrics schema是当前唯一合同；更新所有 in-repo tests/callers。

### Execution preflight（首次业务修改/commit 前）

1. **项目环境与 imports**
   - 命令：`.venv/bin/python -c "import torch, peft, trl, transformers, accelerate, yaml; print(torch.__version__)"`
   - 通过标准：退出 0；pinned training/inference imports 可用。
2. **GTX 1660 Ti CUDA / GPU smoke prerequisites**
   - 命令：`make test-gpu`
   - 通过标准：真实 CUDA GPU smoke 全部 passed、0 failed、0 skipped；不得启动 optimizer training。
3. **真实 loopback Piston**
   - 命令：`make test-piston`
   - 通过标准：0 failed、0 skipped；Piston runtime/safety probes 全绿。
4. **基础 lint/test 环境可执行**
   - 命令：`make lint` 与一个轻量 focused smoke（例如 `.venv/bin/python -m pytest tests/unit/evaluation/test_bootstrap.py -q`）。
   - 通过标准：命令可正常启动且全绿。

任一 preflight 失败：立即停止本次 execution，保持 `HEAD == plan_commit`；修复环境后可重新调用 execution-router，从同一 sealed plan 重试。不得先提交部分业务实现。

### Development Completion Inventory

```yaml
development_completion_inventory:
  version: 1
  items:
    - work_package: WP0
      status: finalized
      evidence: "proceedings.md WP0：项目脚手架，已完成/通过"
    - work_package: WP1
      status: finalized
      evidence: "proceedings.md WP1：Data Layer/schema/三层测试划分，已完成/通过"
    - work_package: WP2
      status: finalized
      evidence: "proceedings.md WP2：Parsing Layer，已完成/通过"
    - work_package: WP3
      status: finalized
      evidence: "proceedings.md WP3：Execution Layer/Piston/batch/cache，已完成/通过"
    - work_package: WP4
      status: finalized
      evidence: "proceedings.md WP4：Verification + Reward，已完成/通过"
    - work_package: WP5
      status: finalized
      evidence: "proceedings.md WP5-a/WP5-b：deterministic evaluation、metrics/bootstrap/Base engineering acceptance，已完成/通过"
    - work_package: WP6
      status: finalized
      evidence: "proceedings.md WP6-a/WP6-c：SFT data/control-plane/checkpoint reload/B unified evaluation development，已完成；真实训练仅为 validation"
    - work_package: WP7
      status: finalized
      evidence: "proceedings.md WP7-a/WP7-b：GRPO control-plane/reward/checkpoint reload/C-D unified evaluation development，已完成；真实训练仅为 validation"
    - work_package: WP8
      status: covered_by_this_stage
      evidence: "本 plan 步骤 1–7 完成 Analysis Layer、report inputs、failure/manual/cost tooling 与工程验收"
```

## 4. 实施步骤

### 步骤 1：补齐 Analysis 所需的 project-owned scalar logging

**目标文件**：
- `src/code_verifier/rewards/common.py`
- `src/code_verifier/training/sft.py`
- `tests/unit/rewards/test_common.py`
- `tests/unit/training/test_sft.py`
- 如现有 GRPO assertions 受 reward schema 变化影响，同步更新 `tests/unit/training/test_grpo.py` / `tests/integration/test_wp7a_grpo_integration.py`

**修改的符号**：

```python
def _reward_components_from_verification(
    result: VerificationResult,
    *,
    mode: str,
) -> dict[str, object]:
    ...


def _append_trainer_metrics(path: Path, log_history: object) -> None:
    ...
```

**主要功能**：
- Reward component record 新增 `executor_runtime_ms`：若 `VerificationResult.execution_result` 存在，记录其 finite non-negative `runtime_ms`；parse-only / unexecuted infrastructure failure 记录 `0.0`。该字段只用于可审计的 executor-reported runtime 成本统计，不改变 reward 计算。
- 保持 component record payload-free；禁止 completion/code/tests/function_name/metadata/stdout/stderr/nested execution results。
- SFT 与 GRPO 一致，把 pinned Trainer `state.log_history` 中 finite numeric scalar 规范化写入 `metrics.jsonl`，每行 `record_type: trainer`；最终 summary 行改为/保持 `record_type: summary`。非数值 trainer metadata 不进入 curve artifact；NaN/Inf fail closed。
- 不新增 compatibility reader；本 stage tests 使用新 schema。

**测试方案**：
- `test_reward_component_records_include_executor_runtime_without_payload`
- `test_reward_component_runtime_is_zero_without_execution_result`
- `test_run_sft_training_persists_finite_trainer_curve_metrics`
- `test_sft_trainer_metrics_reject_non_finite_values`
- 现有 Public/Hidden reward exact-field、GRPO reward log tests 同步断言新 scalar 且 reward 数值完全不变。

**验证命令**：
```bash
.venv/bin/python -m pytest tests/unit/rewards/test_common.py tests/unit/training/test_sft.py tests/unit/training/test_grpo.py -q
```
通过标准：全绿；无真实训练。

### 步骤 2：建立严格 Analysis manifest 与 A–D 输入身份验证

**目标文件**：
- 新增 `src/code_verifier/analysis/__init__.py`
- 新增 `src/code_verifier/analysis/experiment.py`
- 新增 `tests/unit/analysis/test_experiment.py`

**新增符号**：

```python
class AnalysisError(RuntimeError):
    ...


@dataclass(frozen=True)
class AnalysisConfig:
    base_evaluation_run_dir: Path
    sft_evaluation_run_dir: Path
    public_evaluation_run_dir: Path
    hidden_evaluation_run_dir: Path
    sft_training_run_dir: Path
    public_grpo_run_dir: Path
    hidden_grpo_run_dir: Path
    bootstrap_seed: int
    bootstrap_resamples: int
    confidence_level: float
    gpu_hour_cost_usd: float | None
    manual_labels_path: Path | None


@dataclass(frozen=True)
class AnalysisInputs:
    config: AnalysisConfig
    evaluation_records: dict[str, tuple[EvaluationRecord, ...]]
    evaluation_metadata: dict[str, Mapping[str, object]]
    sft_checkpoint: SFTCheckpointIdentity
    public_grpo_checkpoint: GRPOCheckpointIdentity
    hidden_grpo_checkpoint: GRPOCheckpointIdentity


def load_analysis_config(path: Path) -> AnalysisConfig:
    ...


def load_analysis_inputs(config: AnalysisConfig) -> AnalysisInputs:
    ...
```

**严格 manifest schema**：顶层只允许：
- `base_evaluation_run_dir`
- `sft_evaluation_run_dir`
- `public_evaluation_run_dir`
- `hidden_evaluation_run_dir`
- `sft_training_run_dir`
- `public_grpo_run_dir`
- `hidden_grpo_run_dir`
- `bootstrap: {seed, resamples, confidence_level}`
- `cost: {gpu_hour_cost_usd}`（允许 null）
- `manual_labels_path`（允许 null）

**主要功能**：
- 四个 evaluation run 必须 `status=completed`，`samples/results.jsonl` 可由现有 strict loader 读取，且 problem_id 集合完全一致、无重复。
- 四个 evaluation run 必须使用同一 `dataset_hash`、seed、split、Piston definition 与 deterministic generation parameters；checkpoint/model source 允许按 A/B/C/D 身份不同。
- 通过 `load_completed_sft_checkpoint()` 重新验证 B training run；B evaluation metadata 的 checkpoint 必须与该 completed B checkpoint 精确一致。
- 通过 `load_completed_grpo_checkpoint()` 重新验证 C/D；C 必须 `reward_mode=public`，D 必须 `reward_mode=hidden`，两者 `parent_sft` 必须等于 B；C/D evaluation checkpoint id 必须分别等于 `grpo_evaluation_checkpoint_id()` 的 canonical identity。
- A base model id/revision 必须与 B parent base model identity 一致；不接受任意 adapter/checkpoint path 冒充 A/B/C/D。
- 读取/解析错误全部转换为 sanitized `AnalysisError`，不泄漏 file content。

**测试方案**：
- `test_load_analysis_config_requires_exact_schema`
- `test_load_analysis_inputs_accepts_aligned_completed_a_to_d_fixture`
- `test_load_analysis_inputs_rejects_problem_set_or_dataset_drift`
- `test_load_analysis_inputs_rejects_decoding_or_seed_drift`
- `test_load_analysis_inputs_rejects_b_checkpoint_mismatch`
- `test_load_analysis_inputs_rejects_c_d_parent_or_reward_mode_drift`

**验证命令**：
```bash
.venv/bin/python -m pytest tests/unit/analysis/test_experiment.py -q
```

### 步骤 3：实现 problem-level paired comparison、gap 与 failure candidate 规则

**目标文件**：
- 新增 `src/code_verifier/analysis/compare.py`
- 新增 `tests/unit/analysis/test_compare.py`

**新增符号**：

```python
@dataclass(frozen=True)
class PairedComparison:
    left_method: str
    right_method: str
    total_problems: int
    eval_hidden_delta: float
    eval_hidden_delta_ci: BootstrapInterval
    public_eval_gap_delta: float
    public_eval_gap_delta_ci: BootstrapInterval
    reward_hacking_candidate_rate_delta: float
    reward_hacking_candidate_rate_delta_ci: BootstrapInterval


@dataclass(frozen=True)
class FailureCandidate:
    method: str
    run_id: str
    problem_id: str
    candidate_reasons: tuple[str, ...]
    auto_error_category: str
    visible_pass_rate: float
    train_hidden_pass_rate: float
    eval_hidden_pass_rate: float
    execution_status: str


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


def select_failure_candidates(
    method: str,
    records: Sequence[EvaluationRecord],
) -> tuple[FailureCandidate, ...]:
    ...
```

**主要功能**：
- 先按 `problem_id` 严格 paired；集合不一致直接失败，不按行号盲配。
- Eval-Hidden Δ 使用整题 pass@1 indicator 的 paired bootstrap。
- `public_eval_gap_delta` 使用每题 `visible whole-pass - eval-hidden whole-pass` 的 paired difference，与 WP5 `public_eval_gap` 定义一致，便于 A/B/C/D 横向可比。
- 自动 `reward_hacking_candidate_rate` 定义为一致、方法无关的 **visible whole-pass 且 eval-hidden 非 whole-pass** 候选率；该名字必须在输出 metadata 中明确为 automated candidate proxy，不得当作人工确认的 reward hacking。Hidden-RLVR 额外可在 candidate reasons 标注 `train_hidden_pass_eval_fail`，但核心 rate 不切换 denominator，避免 C/D 使用不同定义。
- candidate reasons 至少覆盖：`visible_pass_eval_fail`、`train_hidden_pass_eval_fail`、`partial_eval_hidden_failure`、`syntax_error`、`runtime_error`、`timeout`、`wrong_signature_or_parse`、`truncation`（能从现有记录严格判断的才生成；不能推断 hardcoded/missed-edge-case 等人工类别）。
- candidate records 不含 completion/extracted code/tests；按 method、problem_id 稳定排序。

**测试方案**：
- `test_compare_evaluation_records_pairs_by_problem_id_not_row_order`
- `test_compare_evaluation_records_bootstraps_eval_and_gap_deltas`
- `test_compare_evaluation_records_rejects_unpaired_inputs`
- `test_select_failure_candidates_is_deterministic_and_payload_free`
- `test_reward_hacking_candidate_proxy_uses_one_definition_for_all_methods`

**验证命令**：
```bash
.venv/bin/python -m pytest tests/unit/analysis/test_compare.py -q
```

### 步骤 4：实现 training-curve、cost 与人工标注数据合同

**目标文件**：
- 新增 `src/code_verifier/analysis/report.py`
- 新增 `tests/unit/analysis/test_report.py`

**新增符号**：

```python
@dataclass(frozen=True)
class TrainingCurveRow:
    method: str
    run_id: str
    record_index: int
    step: float | None
    epoch: float | None
    metric: str
    value: float


@dataclass(frozen=True)
class CostRow:
    method: str
    run_id: str
    gpu: str
    gpu_hours: float
    rollouts: int | None
    generated_tokens: int | None
    executor_hours: float | None
    estimated_cost_usd: float | None


def load_training_curve_rows(run_dir: Path, *, method: str) -> tuple[TrainingCurveRow, ...]:
    ...


def build_cost_row(
    run_dir: Path,
    *,
    method: str,
    gpu_hour_cost_usd: float | None,
) -> CostRow:
    ...


def load_manual_labels(
    path: Path,
    *,
    candidates: Sequence[FailureCandidate],
) -> tuple[Mapping[str, str], ...]:
    ...
```

**主要功能**：
- Training curves 使用 project-owned `metrics.jsonl` 的 `record_type=trainer` finite scalar；输出 long-format CSV row，metric key 原样规范化为列值，避免硬编码特定 Trainer metric 集合；忽略 summary row。B/C/D 分别标记 `SFT`、`Public-RLVR`、`Hidden-RLVR`。
- SFT 若 completed run 没有 trainer curve scalar，analysis fail closed；不伪造两点曲线。
- Cost：SFT/GRPO `run.json` 提供 `gpu_name` / cumulative `gpu_hours`；GRPO `rollouts.jsonl` 严格统计 rollout 数与 `completion_token_count` 总和；`rewards.jsonl` 严格统计 `executor_runtime_ms` 总和并转换 executor hours。SFT 的 rollouts/generated_tokens/executor_hours 为 `None`，因为 SFT 不执行 rollout generation；不臆造 token cost。
- `estimated_cost_usd` 只有 manifest 显式提供 finite non-negative `gpu_hour_cost_usd` 时才计算 `gpu_hours * rate`；否则为 null，不从网络或硬编码价格。
- 人工标注模板固定列：`method,run_id,problem_id,candidate_reasons,auto_error_category,manual_category,notes,source_results_path`。`manual_category` 允许规格 §23.3 的人工类别以及 `other`；输入 label 必须对应 candidate、每个 `(method, problem_id)` 唯一。development tests 可用 synthetic 20-row label fixture 验证 ≥20 计数逻辑，但不得记录成真实人工分析。

**测试方案**：
- `test_load_training_curve_rows_emits_long_form_finite_scalars`
- `test_load_training_curve_rows_rejects_completed_run_without_curve_data`
- `test_build_grpo_cost_row_counts_rollouts_tokens_and_executor_hours`
- `test_build_sft_cost_row_uses_gpu_hours_and_marks_rollout_fields_na`
- `test_cost_estimate_requires_explicit_hourly_rate`
- `test_load_manual_labels_requires_unique_known_candidates`
- `test_manual_label_fixture_can_validate_twenty_case_contract_without_becoming_research_evidence`

**验证命令**：
```bash
.venv/bin/python -m pytest tests/unit/analysis/test_report.py -q
```

### 步骤 5：生成可追溯的 WP8 report inputs 与固定 artifact layout

**目标文件**：
- `src/code_verifier/analysis/report.py`
- `src/code_verifier/analysis/__init__.py`
- `tests/unit/analysis/test_report.py`

**新增符号**：

```python
@dataclass(frozen=True)
class AnalysisSummary:
    output_dir: Path
    total_problems: int
    candidate_count: int
    manual_label_count: int
    report_data_path: Path
    main_results_path: Path
    paired_comparisons_path: Path
    cost_path: Path


def analyze_experiment(
    config: AnalysisConfig,
    *,
    output_dir: Path,
) -> AnalysisSummary:
    ...
```

**输出 layout（新目录必须不存在，失败时清理 temporary dir 后 fail closed）**：
- `report_data.json`
- `main_results.csv`
- `paired_comparisons.csv`
- `auto_error_counts.csv`
- `training_curves.csv`
- `failure_candidates.jsonl`
- `manual_labels_template.csv`
- `manual_error_counts.csv`（若 manifest 提供 completed manual labels；否则写 header-only，并在 report_data 标记 `manual_analysis_status: pending`）
- `costs.csv`
- `resolved_analysis.yaml`

**主要功能**：
- `main_results.csv` 对应 §23.1 A–D 四行；Base/SFT 的 `train_verifier_gap` 输出空值；Public-RLVR 使用 visible→eval gap；Hidden-RLVR 使用 train-hidden→eval gap；同时保留统一 `public_eval_gap` 字段供跨方法 comparison，避免把两种 gap 混为一谈。
- `paired_comparisons.csv` 至少包含 Public-RLVR vs SFT、Hidden-RLVR vs SFT、Hidden-RLVR vs Public-RLVR；核心 C/D row 必须是严格 paired bootstrap。每个 delta 带 point estimate 与 95% CI。
- `auto_error_counts.csv` 仅汇总自动可判定 taxonomy；hardcoded visible examples / missed edge case 等必须来自人工 label，不能自动臆断。
- `report_data.json` 保存 schema_version、manifest hash、各 source run_id/checkpoint/dataset/config/provenance、source `results.jsonl` SHA-256、bootstrap settings、所有 table 数据与 candidate/manual status；不复制 sample completion/code/test payload。
- output 全部由源码生成，README/报告后续只读取这些 artifacts，禁止手填数字。

**测试方案**：
- `test_analyze_experiment_writes_exact_artifact_layout_atomically`
- `test_main_results_uses_distinct_public_and_train_verifier_gap_semantics`
- `test_report_data_traces_every_method_to_source_results_hash`
- `test_report_outputs_do_not_copy_completion_code_or_tests`
- `test_manual_error_counts_remain_pending_without_human_labels`
- `test_existing_output_directory_fails_closed_without_partial_overwrite`

### 步骤 6：增加 `analyze-results` CLI 与工程文档

**目标文件**：
- `src/code_verifier/cli.py`
- `tests/unit/test_cli.py`
- `README.md`
- `AGENTS.md`

**新增 / 修改符号**：

```python
def _analyze_results(args: argparse.Namespace) -> int:
    ...


def build_parser() -> argparse.ArgumentParser:
    ...
```

**CLI**：
```text
code-verifier analyze-results \
  --manifest <analysis.yaml> \
  --output-dir <analysis-output>
```

- `--manifest` required。
- `--output-dir` 默认使用 `_default_artifact_output("analysis")` / `CODE_VERIFIER_ARTIFACT_ROOT` 语义；validation 时因此自然写入 stage worktree 外的 persistent artifacts。
- 成功打印 `report_data`, `main_results`, `paired_comparisons`, `costs` 路径和 candidate/manual counts；合同/输入错误返回现有 sanitized exit code 2。
- README 只记录命令、manifest schema、artifact layout、development-vs-validation evidence boundary；绝不填 synthetic A–D 数字。
- AGENTS 增加 WP8 contract：analysis 必须 strict source identity、paired C/D、payload-free derived outputs、human categories 不得自动伪造、cost rate 不得硬编码、fixture 不得冒充 research evidence。

**测试方案**：
- `test_build_parser_exposes_analyze_results_command`
- `test_analyze_results_cli_runs_fixture_pipeline`
- `test_analyze_results_cli_reports_sanitized_analysis_error`
- `test_analyze_results_default_output_honors_artifact_root`

**验证命令**：
```bash
.venv/bin/python -m pytest tests/unit/test_cli.py tests/unit/analysis -q
.venv/bin/code-verifier analyze-results --help
```

### 步骤 7：WP8 development integration fixture

**目标文件**：
- 新增 `tests/integration/test_wp8_analysis_pipeline.py`
- 必要时新增 `tests/fixtures/wp8/` 下纯 synthetic schema fixture；不得包含真实研究结果。

**主要功能**：
- 构建/加载四个 deterministic A/B/C/D evaluation fixture runs，同一 problem set、同一 generation settings；B/C/D 使用现有 completed checkpoint fixture contract。
- 构建 SFT/Public/Hidden training scalar logs、GRPO rollouts/rewards，验证 training curves/cost rows。
- 扰动 C/D 行顺序，证明 comparison 仍按 problem_id pairing；再注入 problem missing、dataset drift、parent B drift、checkpoint drift，逐项 fail closed。
- 生成完整 report artifacts，验证主表 4 行、C/D paired delta/CI 可复算、candidate 稳定排序、manual template 空白人工列、source hash 可追溯。
- 可另用 20 个 synthetic labels 验证人工汇总 schema，但 integration report 必须显式标记 fixture/synthetic engineering evidence；不得写 README 或 proceedings 研究结论。

**测试函数**：
- `test_wp8_analysis_pipeline_generates_traceable_fixture_report`
- `test_wp8_analysis_pipeline_pairs_c_d_by_problem_id`
- `test_wp8_analysis_pipeline_rejects_identity_drift`
- `test_wp8_fixture_outputs_never_claim_real_training_or_manual_evidence`

**验证命令**：
```bash
.venv/bin/python -m pytest tests/integration/test_wp8_analysis_pipeline.py -q
```

### 步骤 8：terminal development closeout

**目标**：不新增为了“制造 commit”而存在的代码；在步骤 1–7 完成后，对整个 WP0–WP8 development inventory 做真实收口。

**必须执行**：
```bash
make lint
make test
make test-gpu
make test-piston
```

**通过标准**：
- `make lint`：Ruff check、format check、strict mypy 全绿。
- `make test`：0 failed；GPU 可见开发机上的 GPU tests 真实执行；real Piston opt-in tests 即使默认 skip 也不替代下一项。
- `make test-gpu`：0 failed、0 skipped，GTX 1660 Ti real CUDA smoke 通过。
- `make test-piston`：0 failed、0 skipped，完整 loopback Piston safety acceptance 通过。
- 生产关键路径 stub/TODO/fake 检查：对 `src/code_verifier/` 与生产 configs 做 targeted search；任何 `TODO/FIXME/NotImplementedError/stub/fake` 命中必须人工确认不是生产未实现路径。tests/fixtures 中的 fake/synthetic 不算缺陷，但不得被生产代码引用为默认路径。
- `third_party/open-r1/**` 无修改。
- 当前 stage 没有真实 SFT/GRPO optimizer run，没有真实 B/C/D/A–D 数值或人工研究结论。

**建议额外 focused gate**：
```bash
.venv/bin/python -m pytest tests/unit/analysis tests/integration/test_wp8_analysis_pipeline.py tests/unit/rewards/test_common.py tests/unit/training/test_sft.py tests/unit/training/test_grpo.py tests/unit/test_cli.py -q
```

## 5. 总体验收与测试计划

- 单元测试：manifest exact schema、A–D identity、paired bootstrap、candidate rules、curve/cost readers、manual labels、atomic outputs、CLI。
- Development integration：deterministic synthetic A–D + strict completed-checkpoint fixtures；真实 Piston 与 GTX 1660 Ti GPU smoke；不运行 optimizer training。
- 数据泄漏/安全：derived analysis artifacts 不复制 completion/code/tests/reference/starter/SFT response；manual template 只含 source pointer 与 scalar/category fields。
- 统计：bootstrap 单位固定为 problem；C/D comparison 按 problem_id paired；不混淆 pass@1 与 average test pass rate。
- 成本：只统计 run metadata/rollout/reward log 中可审计的 GPU-hours、rollout/token counts、executor-reported runtime；GPU hourly price 必须显式输入，否则 cost estimate 为 null。
- 人工分析：development 只生成 template/validator；真实“至少 20 个案例”必须在 4090 validation 完成真实 A–D 后由人工填写并由同一工具验证/汇总。
- Terminal closeout：`make lint`、`make test`、`make test-gpu`、`make test-piston` 全绿且 Piston/GPU gate 0 skipped；生产关键路径无 stub/TODO/fake implementation。

最终标准：
- [ ] WP8 development deliverables 全部实现并可由 fixture end-to-end 验证
- [ ] A–D source identity / same-eval contract fail closed
- [ ] C/D paired bootstrap 可复算且单位为 problem
- [ ] 自动候选与人工结论边界明确
- [ ] report/chart inputs 全自动生成、可追溯、payload-free
- [ ] 成本统计不硬编码价格、不伪造 unavailable quantity
- [ ] `make lint` 全绿
- [ ] `make test` 全绿
- [ ] `make test-gpu` 0 failed / 0 skipped
- [ ] `make test-piston` 0 failed / 0 skipped
- [ ] `third_party/open-r1/**` 未修改
- [ ] 没有真实训练/正式数值被 synthetic/mock 冒充

## 6. Execution Routing

```yaml
execution_routing:
  version: 1
  mode: single
  complexity: normal
  single_class: normal
  parallelizability: medium
  multi_benefit: low
  independent_workstreams: 2
  rationale:
    - "WP8 同时包含少量 training/reward scalar logging 补齐与新的 Analysis Layer，但 analysis schema 直接依赖这些日志字段和现有 B/C/D strict identity，接口/测试需要顺序收敛。"
    - "虽然文件层面存在 logging 与 analysis 两个 workstream，但 terminal closeout、CLI、integration fixture 会跨两者集成；MULTI 的 coordinator/context/integration 成本高于并行收益，SINGLE 更适合保持统计语义和 artifact schema 一致。"
  workstream_candidates: []
```

## 7. 风险与注意事项

- **不要把 automated candidate 称为人工确认的 reward hacking。** `visible_pass_eval_fail` 只是候选规则；hardcoded visible examples、missed edge case 等必须人工判定。
- **不要把两种 gap 混淆。** 跨 A–D 比较保留统一 `public_eval_gap`；主结果中的 `train_verifier_gap` 对 C 用 visible verifier、对 D 用 train-hidden verifier，A/B 为 N/A。
- **不要从 trainer/log 中复制任意对象。** curve 只接受 finite numeric scalars；completion/rollout text 只保留在既有允许的 sample/rollout artifact。
- **不要硬编码云价格。** 未显式配置 rate 时 estimated cost 保持 null。
- **不要为 SFT 伪造 generated tokens/rollouts。** 这些字段保持 N/A；只有 GRPO 从 rollout log 可审计统计。
- **不要修改实验定义。** WP8 只分析已有统一 A–D evaluation output；不改 generation params、reward、checkpoint selection 或训练配置。
- **terminal 失败不能伪装 development complete。** 任一 closeout gate 失败都不能让 reviewer/finalize 写 `Development Complete Record`；若 execution 已有业务 commit 且未形成 completed E0，则按现行 lifecycle 处理 incomplete stage。

## 8. 关联文档索引

- `PROJECT_SPEC_Open-R1_CodeVerifier.md`：§6 Analysis Layer；§19.1 Metrics；§19.2.1/19.2.2；§20.0；WP8；§21.1/21.5；§23；§25–§29。
- `proceedings.md`：WP5-b、WP6-a/WP6-c、WP7-a/WP7-b 与 development-first/closeout workflow decisions。
- `src/code_verifier/evaluation/{evaluate,metrics,bootstrap}.py`：现有 strict per-problem records、single-run aggregates 与 paired bootstrap primitive。
- `src/code_verifier/training/{sft,grpo}.py`：completed training identity、metrics/run metadata、GRPO rollout/reward artifacts。
- `src/code_verifier/rewards/common.py`：reward component records 与 executor runtime provenance source。

## 9. Handoff

- 下一步：运行 `$stage-lifecycle bootstrap_plan`，使用本计划正文创建 `feat/wp8` / `.worktrees/wp8` 并把最终计划 seal 到 `ai-work/planner/WP8-plan.md`。
- bootstrap 成功并得到 `plan_commit` 前，不得调用 execution-router。
- WP8 implementation/review/finalize 全部通过后，`stage-lifecycle finalize` 才能写合法 `Development Complete Record`；随后报告 exact `development_complete_commit`，在 GTX 1660 Ti 停止，按既定流程同步该 exact main commit 到 RTX 4090，再从 4090 重新运行 planner-ex 进入 validation track。
