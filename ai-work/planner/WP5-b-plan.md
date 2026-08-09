
# WP5-b 实施计划（聚合指标、Bootstrap 与 Base 正式验收）

## 1. 元信息

| 项 | 值 |
|---|---|
| stage_id | `WP5-b` |
| 目标 WP | `WP5`：统一评测（子阶段 b：metrics + bootstrap + Base acceptance） |
| 规格依据 | `PROJECT_SPEC_Open-R1_CodeVerifier.md` §4.1–§5.2、§13.1–§13.5、§18、§19、§20 WP5、§21.1/§21.5、§29；`ai-work/planner/WP5-a-plan.md` §6–§7 |
| 前置状态 | `proceedings.md`：WP5-a 已完成；GTX 1660 Ti GPU 环境与真实 Piston 已验收；WP5-b 未实现 |
| `planning_base_commit` | `f286df3b8a4187acebdc5157ce1192cf52eb2180` |
| proposed branch | `feat/wp5-b` |
| proposed worktree | `.worktrees/wp5-b` |
| final plan path | `ai-work/planner/WP5-b-plan.md` |
| execution report path | `ai-work/executor/WP5-b-executor.md` |
| review path | `ai-work/reviewer/WP5-b-review.md` |
| plan lifecycle | planner-ex handoff → `stage-lifecycle bootstrap_plan` → committed plan seal |

> 本计划只完成 WP5 的剩余交付。不得提前实现 WP6 SFT、WP7 GRPO 或 WP8 的跨实验分析；不得修改 `third_party/open-r1/**`。本阶段正式 Base gate 使用当前仓库唯一已提交、可审计的 WP1 prepared smoke dataset；因此其数值是工程基线/管线验收结果，不得被表述为最终 300–500 题研究结论。

## 2. 目标与范围

### 目标（规格原文）

WP5：在训练前先建立可信评测。

### 交付（规格原文）

- generation；
- pass@1 evaluator；
- JSONL 输出；
- 聚合指标；
- bootstrap；
- Base 模型结果。

其中前三项已由 WP5-a 完成；WP5-b 只补齐后三项并完成 WP5 整体验收。

### 验收（规格原文）

- 同一模型、seed 和配置可复现；
- 可恢复中断；
- 输出逐题结果；
- 生成主结果表；
- Base 的错误类型可统计。

### 范围内

- 新增 `src/code_verifier/evaluation/metrics.py` 与 `bootstrap.py`。
- 从 WP5-a `EvaluationRecord` 严格计算 §13.3 指标；不重新解析 completion、不重新执行代码、不读取 tests。
- 题目级 deterministic bootstrap 95% CI；同时实现可复用的 paired bootstrap difference，供后续 C/D 使用，但本阶段不产生 C/D 结果。
- `evaluate` 单命令在 run 完成后生成机器可读 `summary.json` 与一行稳定 `main_results.csv`。
- 保持 WP5-a strict resume：允许已知 derived summary artifacts，但 unknown/stale artifacts 仍 fail closed。
- 新增正式 Base 配置 `configs/eval/base.yaml`：固定 test split、真实 Piston、CUDA、FP16、deterministic pass@1，并在实施时解析并写入不可变的模型 revision。
- 使用 `Qwen/Qwen2.5-Coder-1.5B-Instruct` 作为 A/Base 原始模型，与后续 B/C/D 的 main-model 初始化保持一致；真实运行必须使用 immutable revision。
- 在 GTX 1660 Ti + 本地 Piston 上完成 Base 工程 gate，并把实际指标、revision、run path 和测试证据记录到 execution report。
- 更新 README/AGENTS 的 WP5 完成边界；`proceedings.md` 由后续 `stage-lifecycle finalize` 更新，executor 不修改。

### 范围外

- 不实现 SFT、LoRA、trainer、checkpoint 训练或 WP6 配置。
- 不实现 Public/Hidden GRPO、reward trainer adapter 或 WP7 配置。
- 不实现 WP8 A–D 跨 run 汇总、训练曲线、人工错误分析、成本总报告。
- 不实现 pass@4 / sampling generation。
- 不引入 scipy/numpy 仅为 bootstrap；使用 Python 标准库即可。
- 不把 `samples/results.jsonl` 的 completion/extracted_code 复制到 summary、CSV、metrics、日志或 run metadata。
- 不把当前 20 题 fixture（test split 4 题）的 Base 数值包装成最终研究 benchmark；只作为当前可审计数据上的正式工程 gate。

## 3. 前置条件与约束

- WP5-a 已稳定提供：`EvaluationRecord`、严格 `evaluation_record_from_mapping()`、deterministic generation、三层 verification、run identity、`samples/results.jsonl`、exact-prefix resume。
- `EvaluationRecord` 已包含 WP5-b 所需字段：parse flags、三层 pass rate/status/failure counts、completion token、generation latency、execution runtime、`error_category_auto`。
- 指标计算必须仅依赖这些结构化字段；不得从 completion/code 猜状态，也不得重新调用 parser/verifier/executor。
- `executable_rate` 口径与现有 `VerificationResult.executed` 语义一致：一个 record 仅当 `parse_success == true` 且 `eval_hidden_execution_status != "sandbox_error"` 时计为 executed。`syntax_error`/`runtime_error`/`timeout` 等已有 executor result 的状态仍属于 executed；该定义必须用单测冻结，后续 A–D 不得漂移。
- `syntax_error_rate` / `runtime_error_rate` / `timeout_rate` 以“题目”为单位：若 top-level eval-hidden status 为该状态，或 `eval_hidden_failure_counts` 中该状态计数 > 0，则该题命中；不得按测试用例数量加权。
- pass@1 是整题指标：某层 `pass_rate == 1.0` 才记该题 pass@1=1；`eval_hidden_average_test_pass_rate` 才是逐题 pass-rate 的平均。
- `public_eval_gap = visible_pass@1 - eval_hidden_pass@1`；bootstrap 时对每题的 paired difference（visible whole-pass indicator - eval-hidden whole-pass indicator）重采样，不能分别独立抽样两组。
- bootstrap 单位必须是题目，即每个 `EvaluationRecord` 一次抽样单位；严禁按单测试用例/failure count 重采样。
- 正式 Base model revision 不得使用 `null`、`main`、`latest` 或 branch/tag 语义。实施前先通过当前 pinned Hugging Face runtime/本地缓存解析 `Qwen/Qwen2.5-Coder-1.5B-Instruct` 的 40-hex immutable snapshot commit；无法可靠解析时停止并报告 blocker，不猜 SHA、不降级到 0.5B debug model。
- 正式 Base 在 1660 Ti 上固定 `device: cuda`、`dtype: float16`；若 1.5B 模型真实 OOM/不兼容，阶段应明确阻塞并交回规格决策，不得静默切到 CPU、0.5B 或量化模型。
- 不修改 `third_party/open-r1/`；如确需上游能力仍只能经 adapter，但本阶段预期不需要新增 Open-R1 API 调用。

## 4. 实施步骤

### 步骤 1：提供严格的已持久化 EvaluationRecord 读取入口，并扩展 derived-artifact resume 合同

**目标文件**：`src/code_verifier/evaluation/evaluate.py`

**新增 / 修改的符号**：

```python
def load_evaluation_records(path: Path) -> list[EvaluationRecord]:
    ...
```

并修改私有 `_resume_run_artifacts(...)` 的 run-directory 校验。

**主要功能**：

- `load_evaluation_records()` 读取 UTF-8 JSONL；逐行使用 `loads_strict()` + `evaluation_record_from_mapping()`，拒绝 blank row、truncated/invalid JSON、duplicate key、unknown field、非法 UTF-8、NaN/Inf。
- helper 只负责“严格反序列化”，允许空文件（因为 partial/new run 合法）；非空/重复 problem/mixed identity 由 aggregator 负责。
- 保持已有 exact-prefix resume 逻辑不变，不用 helper 替换后引入宽松匹配。
- WP5-b 完成后 run dir 允许两个已知 derived 文件：`summary.json`、`main_results.csv`。其余 unknown artifact 仍拒绝。
- derived 文件只允许在 `run.json.status == "completed"` 且 `results.jsonl` 已覆盖完整 split 时存在；partial/failed run 若出现 derived artifact，返回 `EvaluationError`，防止 stale summary 与继续生成混用。
- 完成 run 的 no-op resume 可保留 derived 文件；CLI 随后会根据严格 records 原子重算并覆盖，不能盲信旧 summary。

**测试方案**：

- 测试文件：`tests/unit/evaluation/test_runner_resume.py`、`tests/unit/evaluation/test_evaluate.py`
- 测试函数：
  - `test_load_evaluation_records_rejects_blank_invalid_or_unknown_rows`
  - `test_load_evaluation_records_round_trips_strict_rows`
  - `test_resume_allows_known_derived_artifacts_for_completed_run`
  - `test_resume_rejects_derived_artifacts_for_partial_run`
  - `test_resume_still_rejects_unknown_run_artifacts`

**验证命令与通过标准**：

```bash
.venv/bin/python -m pytest tests/unit/evaluation/test_evaluate.py tests/unit/evaluation/test_runner_resume.py -q
```

通过标准：WP5-a resume 的原有测试全绿；新 derived 文件不会放宽 identity/prefix/unknown-artifact guard。

### 步骤 2：实现无第三方统计依赖的 deterministic problem-level bootstrap

**目标文件**：`src/code_verifier/evaluation/bootstrap.py`（新建）

**新增符号**：

```python
class BootstrapError(ValueError):
    ...


@dataclass(frozen=True)
class BootstrapInterval:
    estimate: float
    lower: float
    upper: float
    confidence_level: float
    resamples: int
    seed: int


def bootstrap_mean_interval(
    values: Sequence[float],
    *,
    seed: int,
    resamples: int = 10_000,
    confidence_level: float = 0.95,
) -> BootstrapInterval:
    ...


def paired_bootstrap_difference(
    left: Sequence[float],
    right: Sequence[float],
    *,
    seed: int,
    resamples: int = 10_000,
    confidence_level: float = 0.95,
) -> BootstrapInterval:
    ...
```

**主要功能**：

- 只接受非空、finite numeric sequence；bool 不视作 numeric input；`seed` 必须 int、`resamples` 为正整数、`0 < confidence_level < 1`。
- 使用局部 `random.Random(seed)`，不得污染全局 RNG。
- `bootstrap_mean_interval` 每次重采样 n 个题目 index（有放回），统计样本均值。
- `paired_bootstrap_difference` 要求左右长度相等且非空；每次对同一 index 序列同时抽 left/right，再计算 mean(left-right)，保持 pairing。
- estimate 始终使用原始样本统计值，不使用 bootstrap 均值替代。
- percentile bounds 使用固定、单测冻结的线性分位数：对排序后的 replicate statistics，位置 `q * (m - 1)`，在 floor/ceil 两点线性插值；两侧 q 分别为 `(1-confidence)/2` 与 `1-(1-confidence)/2`。
- 所有输出必须 finite，且 `lower <= upper`；正常均值 CI 应覆盖/围绕 estimate，但不以强制 clamp 篡改统计结果。

**测试方案**：`tests/unit/evaluation/test_bootstrap.py`（新建）

- `test_bootstrap_mean_is_deterministic_for_seed`
- `test_bootstrap_mean_rejects_empty_nonfinite_bool_and_bad_parameters`
- `test_bootstrap_single_problem_collapses_interval`
- `test_paired_bootstrap_uses_shared_problem_indices`
- `test_paired_bootstrap_rejects_mismatched_lengths`
- `test_bootstrap_linear_percentile_definition_is_stable`

**验证命令与通过标准**：

```bash
.venv/bin/python -m pytest tests/unit/evaluation/test_bootstrap.py -q
```

通过标准：同 seed 完全稳定；paired 抽样测试可证明 index 配对未被打散；不新增 package dependency。

### 步骤 3：实现 WP5 聚合指标、错误统计与问题级 confidence intervals

**目标文件**：`src/code_verifier/evaluation/metrics.py`（新建）

**新增符号**：

```python
class MetricsError(RuntimeError):
    ...


@dataclass(frozen=True)
class EvaluationMetrics:
    total_problems: int
    parse_success_rate: float
    target_function_found_rate: float
    executable_rate: float
    syntax_error_rate: float
    runtime_error_rate: float
    timeout_rate: float
    visible_pass_at_1: float
    train_hidden_pass_at_1: float
    eval_hidden_pass_at_1: float
    eval_hidden_average_test_pass_rate: float
    public_eval_gap: float
    mean_completion_tokens: float
    p50_completion_tokens: float
    p95_completion_tokens: float
    mean_generation_latency_ms: float
    mean_execution_runtime_ms: float
    error_category_counts: dict[str, int]
    execution_status_counts: dict[str, int]


@dataclass(frozen=True)
class EvaluationAggregate:
    metrics: EvaluationMetrics
    confidence_intervals: dict[str, BootstrapInterval]


def aggregate_evaluation_records(
    records: Sequence[EvaluationRecord],
    *,
    bootstrap_seed: int,
    bootstrap_resamples: int = 10_000,
    confidence_level: float = 0.95,
) -> EvaluationAggregate:
    ...


def evaluation_aggregate_to_mapping(aggregate: EvaluationAggregate) -> dict[str, object]:
    ...
```

**主要功能**：

- 拒绝空 records、重复 `problem_id`、mixed `run_id/model_id/checkpoint/dataset_hash/config_hash`。
- 每题 whole-pass indicator：对应层 `pass_rate == 1.0` → 1.0，否则 0.0；不使用平均 pass-rate 冒充 pass@1。
- 指标公式：
  - `parse_success_rate = mean(parse_success)`；
  - `target_function_found_rate = mean(target_function_found)`；
  - `executable_rate = mean(parse_success and eval_hidden_execution_status != sandbox_error)`；
  - syntax/runtime/timeout rate 为“该题 top-level eval-hidden status 或 eval-hidden failure_counts 出现对应状态”的题目比例；
  - `visible_pass@1` / `train_hidden_pass@1` / `eval_hidden_pass@1` 为 whole-pass indicator 平均；
  - `eval_hidden_average_test_pass_rate = mean(eval_hidden_pass_rate)`；
  - `public_eval_gap = visible_pass@1 - eval_hidden_pass@1`；
  - completion token 的 mean/P50/P95 使用题目级 values；P50/P95 使用与 bootstrap 相同的稳定线性 quantile helper/等价实现，口径单测冻结；
  - latency/runtime 为题目级均值，单位 ms。
- `error_category_counts` 对 `error_category_auto` 做稳定字典计数；`execution_status_counts` 对 top-level eval-hidden `execution_status` 计数。两者计数和必须等于 total_problems。
- 至少为以下指标提供题目级 95% CI：`visible_pass@1`、`train_hidden_pass@1`、`eval_hidden_pass@1`、`eval_hidden_average_test_pass_rate`、`public_eval_gap`。
- `public_eval_gap` CI 必须调用 paired difference；其它四项调用 mean bootstrap。
- mapping 使用规格指标名（JSON key 可包含 `@`）：`visible_pass@1` 等；所有值 JSON-safe/finite，`allow_nan=False` 可序列化。

**测试方案**：`tests/unit/evaluation/test_metrics.py`（新建）

- `test_aggregate_metrics_matches_exact_problem_level_definitions`
- `test_executable_rate_matches_verification_executed_semantics`
- `test_error_rates_use_problem_not_test_case_weighting`
- `test_pass_at_1_is_not_average_test_pass_rate`
- `test_public_eval_gap_and_ci_preserve_pairing`
- `test_aggregate_rejects_empty_duplicates_and_mixed_identity`
- `test_error_category_and_execution_status_counts_cover_all_records`
- `test_metric_mapping_is_finite_json_safe_and_payload_free`

**验证命令与通过标准**：

```bash
.venv/bin/python -m pytest tests/unit/evaluation/test_bootstrap.py tests/unit/evaluation/test_metrics.py -q
```

通过标准：§13.3 的 WP5-b 指标全部有明确、题目级且可重复的口径；Metrics tests 覆盖 §19.1 的 pass rate/gap/bootstrap/empty/duplicate cases。

### 步骤 4：实现 completed-run 聚合与 `summary.json` / `main_results.csv`

**目标文件**：`src/code_verifier/evaluation/metrics.py`、`src/code_verifier/evaluation/__init__.py`

**新增符号**：

```python
@dataclass(frozen=True)
class EvaluationAggregateSummary:
    run_id: str
    total_problems: int
    summary_path: Path
    main_results_path: Path
    aggregate: EvaluationAggregate


def aggregate_evaluation_run(
    run_dir: Path,
    *,
    bootstrap_seed: int,
    bootstrap_resamples: int = 10_000,
    confidence_level: float = 0.95,
) -> EvaluationAggregateSummary:
    ...
```

将稳定公共统计 API 从 `evaluation/__init__.py` 导出；不要导出大量私有 I/O helpers。

**主要功能**：

- `aggregate_evaluation_run()` 只接受完整 WP5 run dir；严格读取 `run.json` 与 `samples/results.jsonl`。
- 要求 `run.json.status == "completed"`；run metadata 的 `run_id/model_id/checkpoint/dataset_hash/config_hash` 必须与全部 records 一致；`seed` 必须 int；`model_revision` 对正式 Base 由 config 保证非空 immutable，但 generic debug run 可为 null。
- 输出 `summary.json`（schema version 1），至少包含：run/model/revision/checkpoint/dataset/config/seed/project/open-r1 identity、bootstrap 参数、metrics、confidence intervals、error/status counts。不得包含 completion/code/tests/reference solution/stdout/stderr。
- 输出 `main_results.csv` 一行稳定主结果表，固定列至少包含：
  - identity：run_id/model_id/model_revision/checkpoint/seed/total_problems；
  - code-output rates；
  - visible/train-hidden/eval-hidden pass@1；
  - eval-hidden pass@1 CI low/high；
  - eval-hidden average test pass rate；
  - public_eval_gap + CI low/high；
  - mean/P50/P95 completion tokens；
  - mean generation/execution latency。
- CSV 使用标准库 `csv`，UTF-8/newline 稳定；JSON/CSV 都通过同目录 temporary file + `os.replace()` 原子更新，不留下 partial derived artifact。
- 重跑 aggregation 必须 deterministic overwrite derived files；bootstrap seed/resamples/confidence level 写入 summary，不能隐式丢失。
- `summary.json` 与 CSV 不纳入 Git；仍位于 ignored `outputs/` 下。

**测试方案**：继续使用 `tests/unit/evaluation/test_metrics.py`

- `test_aggregate_run_requires_completed_status`
- `test_aggregate_run_rejects_run_record_identity_mismatch`
- `test_aggregate_run_writes_stable_summary_and_one_row_csv`
- `test_summary_and_csv_exclude_completion_code_and_test_payloads`
- `test_reaggregating_same_run_is_byte_stable_except_no_variable_fields`（实现中 summary 不写当前时间，因此应可 byte-stable）

**验证命令与通过标准**：

```bash
.venv/bin/python -m pytest tests/unit/evaluation/test_metrics.py -q
```

通过标准：completed run 可无模型重跑地产生稳定主结果表；任何 partial/mixed/tampered run fail closed。

### 步骤 5：把聚合接入现有 `evaluate` 单命令，不改变 generation/resume 身份

**目标文件**：`src/code_verifier/cli.py`、`tests/unit/test_cli.py`

**修改的符号**：

```python
def _evaluate(args: argparse.Namespace) -> int:
    ...
```

**主要功能**：

- 保持 `run_pass1_evaluation()` 的 generation/resume 责任不变；CLI 在其成功返回后调用：

```python
aggregate_evaluation_run(
    summary.results_path.parent.parent,
    bootstrap_seed=int(args.seed),
)
```

- 不新增第二套评测命令；一条现有 `code-verifier evaluate ...` 同时完成逐题结果与最终 aggregation，满足 §4.1 “一条命令能够运行 Base/SFT 模型评测”。
- CLI 成功输出增加 `summary=<path>`、`main_results=<path>`，不得打印 completion/code/tests。
- aggregation 失败属于评测失败，走现有脱敏 error/exit 2 路径；不得把 generation run 标记回 running，也不得删掉已经正确生成的逐题结果。
- no-op resume（0 generation）仍重新严格聚合，便于恢复一次“generation 已完成但 summary 写出前中断”的场景。

**测试方案**：`tests/unit/test_cli.py`

- `test_evaluate_cli_aggregates_completed_run`
- `test_evaluate_cli_reaggregates_zero_generation_resume`
- `test_evaluate_cli_surfaces_aggregation_error_without_payload`

**验证命令与通过标准**：

```bash
.venv/bin/python -m pytest tests/unit/test_cli.py -q
.venv/bin/code-verifier evaluate --help
```

通过标准：现有 CLI 参数兼容；成功 run 必有 results + summary + CSV；错误脱敏。

### 步骤 6：增加 WP5-b 端到端 aggregation 集成回归

**目标文件**：`tests/integration/test_wp5b_metrics_pipeline.py`（新建）

**主要功能 / 测试函数**：

- 使用现有 WP1 smoke prepared dataset + deterministic fake generator + `MockExecutor`（或计划内构造的严格 synthetic records）完成无 GPU 的可重复 pipeline；不得下载模型。
- 建议测试：
  - `test_wp5b_completed_run_generates_results_summary_and_main_table`
  - `test_wp5b_summary_metrics_trace_back_to_per_problem_rows`
  - `test_wp5b_same_records_and_seed_reproduce_identical_aggregate`
  - `test_wp5b_summary_artifacts_do_not_contain_sensitive_payloads`
- 对每个聚合数值从 `results.jsonl` 独立复算关键断言，避免只测试“函数返回自身结果”。
- 明确断言 bootstrap `resamples`/seed/confidence level、error count 总和、CSV row count=1。

**验证命令与通过标准**：

```bash
.venv/bin/python -m pytest tests/integration/test_wp5b_metrics_pipeline.py -q
```

通过标准：CPU/mock 环境即可完整验证 aggregation；真实模型/Piston 留给步骤 8 gate。

### 步骤 7：创建 immutable Base 配置并更新文档边界

**目标文件**：

- `configs/eval/base.yaml`（新建）
- `README.md`（修改）
- `AGENTS.md`（修改）

**Base revision 前置验证**：

- 先确认当前 `huggingface_hub`/Transformers runtime 能解析 `Qwen/Qwen2.5-Coder-1.5B-Instruct`。
- 通过官方 Hub metadata 或已存在的本地 snapshot cache 得到 exact snapshot commit；必须正则满足 `[0-9a-f]{40}`。
- 将该 exact SHA 写入 `configs/eval/base.yaml:model_revision`。若无法得到可信 immutable SHA，停止本步骤并报告 blocker；不得提交 placeholder/null/main。

**`configs/eval/base.yaml` 最终结构**：

```yaml
dataset_dir: data/processed/wp1-smoke
split: test
piston_config: configs/execution/piston-local.yaml
model_revision: <resolved immutable 40-hex commit>
checkpoint: base
device: cuda
generation:
  do_sample: false
  temperature: null
  top_p: null
  max_new_tokens: 512
  dtype: float16
```

**主要功能**：

- 保留 `configs/eval/pass1.yaml` 为 debug/smoke 配置，不把其 `model_revision: null` 偷换成正式配置。
- README 增加正式 Base command、summary/CSV schema、指标定义与“当前 smoke fixture 只作工程 gate”声明。
- AGENTS 当前 scope 更新为 WP0–WP5 implemented；WP6 SFT 是下一阶段；保留正式 Base 必须 immutable revision + real Piston + payload isolation 的约束。
- 不修改 `proceedings.md`；finalization 时由 stage-lifecycle 根据 review 结论整合 WP5。

**测试方案**：

- `test_load_evaluation_config_accepts_immutable_base_yaml`（可放 `tests/unit/evaluation/test_evaluate.py`）
- 断言 base config `split=test`、`device=cuda`、`dtype=float16`、revision 为 40-hex 且非 null。

**验证命令与通过标准**：

```bash
.venv/bin/python -m pytest tests/unit/evaluation/test_evaluate.py -q
make lint
```

通过标准：正式配置无 placeholder；debug config 继续可用；文档不宣称 4 题 fixture 是最终研究 benchmark。

### 步骤 8：全套回归与真实 Base 工程验收

**代码级验证**：

```bash
make lint
make test
make test-piston PISTON_CONFIG=configs/execution/piston-local.yaml
make test-gpu
```

通过标准：

- `make lint` 全绿；
- `make test` 0 failed（真实 Piston 仍按既有 marker 规则）；
- `make test-piston` 0 failed / 0 skipped；
- GTX 1660 Ti 上 `make test-gpu` 0 failed / 0 skipped。

**正式 Base run**（真实 model + immutable revision + real Piston）：

```bash
.venv/bin/code-verifier evaluate \
  --config configs/eval/base.yaml \
  --model-id Qwen/Qwen2.5-Coder-1.5B-Instruct \
  --run-name base-main-r1 \
  --seed 42 \
  --output-dir outputs
```

要求：

- 真实 CUDA/FP16 加载 1.5B model；不可降级 0.5B/CPU/quantized；
- Piston runtime validation 成功；
- 当前 committed smoke dataset 的 test split 全部完成（按现状应为 4 题；若数据已合法变化，以 strict prepared dataset 实际数量为准并记录 hash/count）；
- `outputs/evaluation/base-main-r1/samples/results.jsonl` 行数等于 test problems；
- `summary.json` 与 `main_results.csv` 存在、可严格解析、无 completion/code/tests；
- summary 的 Base error-category counts 总和等于 total problems；
- `eval_hidden_pass@1`、CI、public_eval_gap 等均 finite 且可从 per-problem rows 追溯。

**resume gate**：原命令原 run-name 再执行一次，必须 `generated_this_run=0`，并成功重新生成相同聚合内容；不得调用 generator/executor 处理已完成 rows。

**真实 deterministic reproducibility probe**：使用同一 immutable config/model/seed 运行第二个新 run（例如 `base-main-repro`）。对两个 `samples/results.jsonl` 忽略 `run_id` 与 timing 字段后比较：problem order、prompt hash、completion、extracted code、parse/status/pass-rate/failure counts、completion_tokens 必须一致；主 correctness metrics 必须一致。latency/runtime 不要求逐字相等。

若真实 1.5B run 因模型下载、immutable revision、CUDA OOM、Piston 或硬件约束无法完成：不得以 mock/0.5B 代替正式 gate，也不得把 WP5-b 标为完成；execution report 必须记录 blocker。

## 5. 总体验收与测试计划

- 单元测试：bootstrap、metrics、strict records、resume derived-artifact guards、CLI integration 全绿。
- 集成测试：CPU/mock WP5-b pipeline 全绿，且聚合结果能从逐题 rows 独立复算。
- 真实 gate：GTX 1660 Ti CUDA FP16 + immutable 1.5B Base + loopback Piston；同 run no-op resume + 第二 run deterministic probe 均通过。
- 数据/安全：
  - summary/CSV/log/run metadata 不含 completion/code/tests/reference solution；
  - aggregation 不调用 generator/parser/verifier/executor；
  - bootstrap 单位是题目；
  - Base config 使用 immutable model revision；
  - `third_party/open-r1/**` 无修改。
- 最终标准：
  - [ ] WP5 §20 剩余“聚合指标 / bootstrap / Base 模型结果”完成；
  - [ ] 主结果表由程序生成，不手工录入；
  - [ ] Base 错误类别可统计并总和正确；
  - [ ] pass@1 与 average test pass rate 未混淆；
  - [ ] 95% CI 题目级而非测试用例级；
  - [ ] `make lint` 全绿；
  - [ ] `make test` 全绿；
  - [ ] `make test-piston` 0 failed / 0 skipped；
  - [ ] `make test-gpu` 在 GPU 机器上 0 failed / 0 skipped；
  - [ ] 正式 Base run + no-op resume + independent deterministic rerun 通过；
  - [ ] 未实现 WP6+。

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
    - "统计内核（metrics/bootstrap）与 run/CLI/artifact 集成在文件所有权上部分可分，但 CLI、resume 合同、summary schema 和真实 Base gate 都依赖最终统计 API，存在明确串行集成点。"
    - "工作量是常规多文件实现与测试；MULTI coordinator/merge 成本高于收益，而且真实 immutable-model/Piston/GPU acceptance 必须在集成后串行完成。"
  workstream_candidates: []
```

## 7. 风险与注意事项

- **统计单位错误**：最高风险。bootstrap、error rates、pass@1 都按 problem record，而不是 test cases；用单测冻结。
- **pass@1 口径漂移**：整题通过 (`pass_rate == 1.0`) 与平均 test pass rate 必须分开。
- **paired gap 错误**：public_eval_gap 的 CI 必须在同一问题 pair 上重采样；以后 C/D paired difference 可复用同一 helper。
- **derived artifact 污染 resume**：只允许 completed run 存在 summary/CSV；unknown/stale 文件仍 fail closed。
- **payload 泄漏**：只有 `samples/results.jsonl` 可持久化 completion/code；summary/CSV 不得复制。
- **Base revision 漂移**：正式 config 必须 40-hex immutable snapshot；无法解析则阻塞。
- **硬件降级掩盖失败**：1.5B Base 若在 1660 Ti 不可运行，不能自动改 0.5B、CPU 或量化；需要显式规格决策。
- **fixture 规模**：当前 committed WP1 smoke test split 很小；其 Base 数值只作为工程 gate。不要在 README/proceedings 中夸大为最终研究结果。
- **接口边界**：不要修改 WP4 verifier/executor 语义来方便统计；统计只消费 WP5-a records。

## 8. 关联文档索引

- `PROJECT_SPEC_Open-R1_CodeVerifier.md`
  - §4.1/§4.2：一条命令评测与 A–D 定义
  - §5.1/§5.2：main/debug model 与 GPU dtype 决策
  - §13.1–§13.5：统一评测、核心指标、统计要求
  - §18：run artifacts/reproducibility
  - §19：Metrics 单测与结果聚合集成测试
  - §20 WP5：交付/验收
  - §21.5：结果 review
  - §29：主指标与 paired bootstrap 95% CI
- `proceedings.md`：WP5-a 已完成；WP5-b 是下一 stage
- `ai-work/planner/WP5-a-plan.md` §6–§7：明确留给 WP5-b 的 metrics/bootstrap/Base 边界
- `src/code_verifier/evaluation/evaluate.py`：`EvaluationRecord`、strict run/resume contract
- `src/code_verifier/verification/result_types.py`：`VerificationResult.executed` 语义依据
- `src/code_verifier/execution/base.py`：`ExecutionStatus`
- `configs/eval/pass1.yaml`：保留为 debug/smoke，不作为 formal Base config

## 9. Handoff

- 下一步必须由本地 Codex 在主仓库 root 运行 `$stage-lifecycle bootstrap_plan`，消费本 handoff，创建/复用 `feat/wp5-b` + `.worktrees/wp5-b`，并只将本计划正文 seal 到 `ai-work/planner/WP5-b-plan.md`。
- bootstrap 成功并返回 `plan_commit` 前，不得直接改业务代码、不得调用 execution-router。
- plan seal 后，再从 stage worktree 调用 `$execution-router`；router 根据本计划 `execution_routing` 选择 SINGLE executor。
- planner-ex 本轮未创建 branch/worktree、未 commit/merge/push、未在 main 写正式 plan。

