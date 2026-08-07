# WP5-a 实施计划（Deterministic Generation、逐题 Pass@1 与可恢复评测运行）

## 1. 元信息

| 项 | 值 |
|---|---|
| 目标 WP | WP5：统一评测（子阶段 a：Generation + 逐题 Pass@1 + 可恢复 JSONL 运行） |
| 规格依据 | `PROJECT_SPEC_Open-R1_CodeVerifier.md` §6.2 Generation/Evaluation Layer、§7.2–§7.4、§13.1–§13.4、§16、§17、§18、§19、§20 WP5、§29 |
| 前置 WP | WP4（`proceedings.md` 状态：已完成，验收通过） |
| 分支 | `feat/wp5-a` |
| worktree | `.worktrees/wp5-a` |
| 计划文件 | `ai-work/planner/WP5-a-plan.md` |
| 面向的执行 agent | 仅文件读写 + 基础 shell；可运行仓库自带 `make`、pytest、CLI；不依赖 Codex/MCP/其它 skill |
| 计划粒度 | WP5 的第一个子阶段；8 个实施步骤；新增业务模块不超过 3 个（`evaluation/__init__.py`、`evaluation/generate.py`、`evaluation/evaluate.py`） |
| 后续阶段 | WP5-b：`metrics.py`、`bootstrap.py`、聚合结果、paired bootstrap、Base 实际主结果与 WP5 整体验收 |

> 本计划只建立“可信且可恢复的逐题评测数据面”。聚合指标、bootstrap、主结果表以及真正的 Base 模型结果明确留到 WP5-b；执行者不得提前实现 WP6 SFT、WP7 GRPO 或 WP8 分析报告。

## 2. 目标与范围

### 2.1 WP5 目标（规格 §20 原文）

在训练前先建立可信评测。

### 2.2 WP5 交付（规格 §20 原文）

- generation；
- pass@1 evaluator；
- JSONL 输出；
- 聚合指标；
- bootstrap；
- Base 模型结果。

### 2.3 WP5 验收（规格 §20 原文）

- 同一模型、seed 和配置可复现；
- 可恢复中断；
- 输出逐题结果；
- 生成主结果表；
- Base 的错误类型可统计。

### 2.4 本子阶段目标

WP5-a 完成 WP5 前半段并形成可独立审查的稳定输入工件：

1. 按 §7.2 构造只包含题面、函数签名和 `visible_tests` 的固定 prompt，禁止任何 hidden test 进入模型输入。
2. 实现固定 deterministic pass@1 generation backend，默认参数与 §13.2 一致：`do_sample=false`、`temperature=null`、`top_p=null`、`max_new_tokens=512`。
3. 对每个 completion 使用现有 `extract_python_code()` 和 `verify_completion()`，分别评测 `visible_tests`、`train_hidden_tests`、`eval_hidden_tests`；不得复制 parser/executor/verifier 逻辑。
4. 写出 §13.4 要求的逐题 JSONL，并补充可统计的三层 execution status、failure counts、prompt/config/dataset identity；结果不得包含任何测试内容。
5. 运行目录采用 §18 的 `outputs/evaluation/{run_id}/` 形态，保存 resolved config、environment、run manifest、progress metrics 与日志。
6. 通过“已有 JSONL 必须是目标题目序列的合法前缀”的方式实现严格恢复：中断后继续下一题；重复、乱序、配置漂移、dataset/model identity 漂移一律 fail closed。
7. 新增 `evaluate` CLI，遵守全局参数合同；真实模型加载失败、配置错误或 Piston 不可用时输出脱敏错误并退出 2。
8. 本子阶段只用 fake generator + MockExecutor / 可选真实 Piston 验证管线；真实 Base checkpoint 的完整生成、聚合和 bootstrap 在 WP5-b 执行。

### 2.5 范围内

- 新建 `src/code_verifier/evaluation/__init__.py`。
- 新建 `src/code_verifier/evaluation/generate.py`：prompt 构造、generation 合同、Transformers deterministic backend。
- 新建 `src/code_verifier/evaluation/evaluate.py`：严格配置、逐题结果、三层 verifier 编排、run identity、append/resume、run artifacts。
- 新增 `configs/eval/pass1.yaml`。
- 修改 `src/code_verifier/cli.py`，加入 `evaluate` 子命令，并允许该命令在 `--config` 必填的同时把 `--output-dir` 默认设为 `outputs`。
- 必要时扩展 `src/code_verifier/environment.py`，使评测运行能记录 §18 所需 CUDA/GPU/依赖 identity；不得删除现有字段。
- 新增 generation/evaluation 单元测试与一个 WP5-a 端到端集成测试。
- 更新 `README.md`、`AGENTS.md`，登记 WP5-a 稳定边界和 WP5-b 尚未完成项。

### 2.6 范围外

- 不实现 `src/code_verifier/evaluation/metrics.py`、`bootstrap.py`；这些属于 WP5-b。
- 不实现 `aggregate` CLI、CSV 主结果表、paired bootstrap、置信区间或 C/D 对比。
- 不把一次 debug generation 结果登记为 Base 主结果；WP5-b 必须用固定 model revision + 固定 dataset + 真实 Piston 完成 Base 评测。
- 不实现 pass@4 / sampling generation。
- 不实现 WP6 SFT、checkpoint 训练或任何 optimizer/trainer。
- 不实现 WP7 Public/Hidden GRPO。
- 不实现 §14 的完整 reward-hacking AST/代码启发式分析；WP5-a 只生成足够后续统计的稳定字段和粗粒度自动错误类别。
- 不修改 `third_party/open-r1/**`；不得直接 import `open_r1.*`。本阶段 generation 使用固定 Open-R1 环境中已 pin 的 Transformers 依赖，但不依赖上游训练脚本。
- 不允许评测脚本继续训练模型；production backend 必须 `eval()` + inference mode。
- 不允许 `eval_hidden_tests`、`train_hidden_tests`、reference solution 或 expected values 进入 prompt、completion generation 输入、stdout/stderr 日志或 run manifest。
- 执行阶段不得修改 `proceedings.md`；只有 WP5 全部子阶段通过 reviewer 后才登记 WP5 完成。

## 3. 前置条件、现状与硬性约束

### 3.1 当前仓库状态

- `proceedings.md` 已登记 WP0–WP4 全部完成；WP5 是 §20 顺序中第一个未完成 WP。
- 当前 main 在 WP4 完成后已经提供：
  - `CodeProblem` 三层测试 schema；
  - `extract_python_code()`；
  - `CodeExecutor` / `MockExecutor` / `PistonExecutor`；
  - `verify_completion()` 与稳定 `VerificationResult`；
  - Public/Hidden reward，但 WP5 不经 reward 计算评测正确率。
- `src/code_verifier/evaluation/` 当前不存在。
- `PROJECT_SPEC` §16 明确规划 `evaluation/generate.py`、`evaluate.py`、`metrics.py`、`bootstrap.py`；WP5-a 只创建前两个实现文件。

### 3.2 必须复用的现有接口

评测语义必须唯一复用：

```python
def extract_python_code(completion: str, expected_function_name: str | None = None) -> ParseResult:
    ...
```

```python
def verify_completion(
    completion: str,
    tests: Sequence[Mapping[str, object]],
    function_name: str,
    metadata: Mapping[str, object],
    executor: CodeExecutor,
) -> VerificationResult:
    ...
```

执行者不得在 `evaluation/` 中重新实现 AST 解析、候选代码执行、测试比较、timeout/sandbox 状态判断。

### 3.3 Prompt 与泄漏边界

固定 prompt 必须逐字保留 §7.2 的骨架：

```text
You are given a Python programming problem.

Problem:
{problem_statement}

Function signature:
{function_signature}

Visible examples:
{visible_examples}

Return a correct implementation.
The final answer must contain exactly one Python code block.
Do not read from stdin unless the problem explicitly requires it.
Do not print debugging information.
```

`visible_examples` 只允许来自 `problem.visible_tests`，采用稳定 JSON 表示；构造函数签名只接收完整 `CodeProblem`，但实现必须显式只读取 `prompt`、`function_signature`、`visible_tests`。单元测试必须放入 hidden sentinel 并断言 prompt 中完全不存在。

### 3.4 固定 generation 规则

主结果 generation 固定为 §13.2：

```yaml
generation:
  do_sample: false
  temperature: null
  top_p: null
  max_new_tokens: 512
```

本阶段禁止添加“best of N”、sampling、temperature fallback 或自动重试生成。单题生成失败属于 run-level infrastructure/config error，不得静默产生空 completion 并继续。

### 3.5 Transformers / Open-R1 环境约束

固定 `third_party/open-r1/setup.py` 已 pin：

- `transformers==4.52.3`
- `torch==2.6.0`

但本项目 `make install` 使用 `--no-deps` 安装 Open-R1，并不会安装完整模型推理依赖；真实模型 generation 必须使用 `make install-full` 准备完整环境。实现必须 lazy import `torch` / `transformers`，因此 CPU 单元测试和 `make install` 环境仍可导入 `code_verifier.evaluation`。

不得直接 import `open_r1.*`；未来若确需 Open-R1 API，必须经 `code_verifier.training.open_r1_adapter`。

### 3.6 评测数据集与测试层规则

- 只从 WP1 prepared canonical dataset / HF dataset 解码为 `CodeProblem`；不得读取 training artifact 做最终评测。
- 默认只评测 `split == "test"`；配置允许 `validation` 用于 debug，但 production Base 主结果在 WP5-b 固定 `test`。
- 同一 completion 必须分别调用 verifier 三次：visible、train-hidden、eval-hidden；同一 evaluator 不得基于模型类型改变测试集合。
- `eval_hidden_tests` 只用于 verifier；不得传给 generator。
- 输出 JSONL 不保存 tests、expected values、reference solution、metadata 全量对象或 executor stdout/stderr。

### 3.7 中断恢复与 run identity

恢复采用严格“前缀协议”：

1. run 目标 problem 列表顺序由 prepared dataset 原始顺序过滤 split 后得到，禁止 shuffle。
2. `samples/results.jsonl` 每完成一题 append 一行并 flush；已有行必须严格对应目标 problem 列表从第 1 条开始的前缀。
3. 每条已有 record 的 `run_id`、`model_id`、`checkpoint`、`dataset_hash`、`config_hash`、`problem_id`、`prompt_hash` 必须与当前运行一致。
4. 任意 duplicate、乱序、截断 JSON、unknown field、非有限数、identity 不一致均拒绝恢复并退出 2；不得删除已有结果重新开始。
5. 只有完全合法前缀才从下一个 problem 继续；全部完成时重复执行应零 generation / 零 executor 调用并返回 0。

### 3.8 输出布局与敏感字段

WP5-a 固定：

```text
outputs/evaluation/{run_id}/
├── resolved_config.yaml
├── environment.json
├── run.json
├── metrics.jsonl
├── stdout.log
├── stderr.log
└── samples/
    └── results.jsonl
```

`results.jsonl` 允许且必须保存 completion / extracted_code（§13.4），但 run metadata、日志、metrics 不得复制 completion/code/tests。完整 outputs 继续由 `.gitignore` 管理，不提交生成结果。

### 3.9 WP5-a 对 §13.4 单条结果的解释

至少保留规格字段：

- `run_id`
- `model_id`
- `checkpoint`
- `problem_id`
- `prompt_hash`
- `completion`
- `extracted_code`
- `parse_success`
- `visible_pass_rate`
- `train_hidden_pass_rate`
- `eval_hidden_pass_rate`
- `execution_status`
- `runtime_ms`
- `completion_tokens`
- `error_category_auto`

并增加为 WP5-b 聚合所需、仍不泄漏测试内容的字段：

- `dataset_hash`
- `config_hash`
- `target_function_found`
- `generation_latency_ms`
- `visible_execution_status`
- `train_hidden_execution_status`
- `eval_hidden_execution_status`
- `visible_failure_counts`
- `train_hidden_failure_counts`
- `eval_hidden_failure_counts`
- `parse_error_type`

定义：

- `execution_status` 等于 `eval_hidden_execution_status`，因为主指标唯一来自 eval-hidden；三层 status 同时单独保存。
- `runtime_ms` 等于三次 verifier 中 `execution_result.runtime_ms` 的有限和；未执行层按 0 计。
- `target_function_found` 在当前 parser 合同下等价于 `parse_success`，但单独保存以支持 §13.3 指标稳定命名。
- `error_category_auto` 只做粗粒度：`passed`、`visible_only_success`、`large_public_eval_gap`、`parse_error:<type>`、`timeout`、`sandbox_failure`、`runtime_error`、`wrong_answer`、`other`；不得在本阶段实现 §14.1 的 AST/常量启发式。

## 4. 实施步骤

### 步骤 1：建立 Evaluation package 与 deterministic generation 合同

**目标文件**：

- `src/code_verifier/evaluation/__init__.py`（新建）
- `src/code_verifier/evaluation/generate.py`（新建）

**新增符号**：

```python
class GenerationError(RuntimeError):
    """Raised when model generation cannot satisfy the configured inference contract."""


@dataclass(frozen=True)
class GenerationConfig:
    do_sample: bool
    temperature: float | None
    top_p: float | None
    max_new_tokens: int


@dataclass(frozen=True)
class GenerationResult:
    completion: str
    completion_tokens: int
    latency_ms: float


class CompletionGenerator(Protocol):
    def generate(self, prompt: str, *, seed: int) -> GenerationResult: ...


def validate_generation_config(config: GenerationConfig) -> None: ...


def build_evaluation_prompt(problem: CodeProblem) -> str: ...
```

**主要功能**：

- `validate_generation_config()` 只接受 WP5-a deterministic pass@1：
  - `do_sample is False`；
  - `temperature is None`；
  - `top_p is None`；
  - `max_new_tokens` 为正整数且上限明确（建议 `<= 4096`，默认配置固定 512）。
- `build_evaluation_prompt()` 按 §7.2 固定模板生成 UTF-8 prompt；`visible_tests` 用 `test_case_to_mapping()` + `json.dumps(..., sort_keys=True, allow_nan=False)` 稳定序列化。
- prompt 不读取 `train_hidden_tests`、`eval_hidden_tests`、`reference_solution`、`sft_response`。
- `GenerationResult` 所有数值必须 finite / non-negative，completion 必须合法 UTF-8 字符串。

**测试方案**：

- 测试文件：`tests/unit/evaluation/test_generate.py`
- 新增测试：
  - `test_build_evaluation_prompt_matches_spec_template`
  - `test_build_evaluation_prompt_contains_visible_examples_only`
  - `test_build_evaluation_prompt_excludes_hidden_sentinels`
  - `test_generation_config_accepts_exact_pass1_defaults`
  - `test_generation_config_rejects_sampling_or_nonfinite_values`
  - `test_generation_result_contract_rejects_invalid_values`（若通过 validator/helper 落地）

**验证命令与通过标准**：

```bash
.venv/bin/python -m pytest tests/unit/evaluation/test_generate.py -q
make lint
```

通过标准：新增 generation 单测全部通过；mypy/ruff 全绿；hidden sentinel 不出现在任何 prompt。

### 步骤 2：实现 frozen Transformers generation backend

**目标文件**：`src/code_verifier/evaluation/generate.py`（修改）

**新增符号**：

```python
class TransformersCompletionGenerator:
    @classmethod
    def from_pretrained(
        cls,
        model_id: str,
        *,
        model_revision: str | None,
        device: str,
        config: GenerationConfig,
    ) -> TransformersCompletionGenerator: ...

    def generate(self, prompt: str, *, seed: int) -> GenerationResult: ...
```

如为测试隔离需要，可增加私有 lazy-import helper，但不得把 torch/transformers 放到模块顶层 import：

```python
def _load_transformers_runtime() -> tuple[object, object, object]: ...
```

**主要功能**：

- lazy import `torch` 与 `transformers`；缺失时抛 `GenerationError`，错误信息只说明运行 `make install-full`，不输出环境变量/路径秘密。
- `from_pretrained()`：
  - `model_id` 必须非空；
  - `model_revision` 记录到 run identity；若为空允许 debug，但 WP5-b Base 验收必须使用固定 revision；
  - `device` 来自 YAML，不在代码中硬编码 GPU id；至少支持 `cpu`、`cuda`、`auto` 的显式配置语义；
  - tokenizer/model 必须来自同一 model id/revision；
  - `trust_remote_code=False`，除非后续 reviewer 有明确、记录过的模型兼容阻断理由；
  - model 加载后调用 `.eval()`，不创建 optimizer/trainer。
- `generate()`：
  - 使用 tokenizer chat template（单一 user message，content 为 `build_evaluation_prompt()` 产物，`add_generation_prompt=True`）；若 tokenizer 明确无 chat template，则 fail closed，不自行猜模板；
  - 通过 `transformers.set_seed(seed)` / torch seed helper 固定运行；
  - 用 inference mode 调用 `model.generate()`；
  - 只解码新生成 token，不把 prompt token 计入 `completion_tokens`；
  - generation kwargs 只能来自 `GenerationConfig`，sampling 参数为 `None` 时不得伪造数值；
  - 记录单次 wall-clock latency；必须 finite 且 >= 0；
  - 不执行生成代码、不访问任何 tests。

**测试方案**：

- 测试文件：`tests/unit/evaluation/test_generate.py`
- 使用 fake tokenizer/model/runtime，不下载真实模型：
  - `test_transformers_generator_lazy_imports_runtime`
  - `test_transformers_generator_uses_user_chat_template`
  - `test_transformers_generator_calls_eval_and_inference_path`
  - `test_transformers_generator_decodes_only_new_tokens`
  - `test_transformers_generator_reports_completion_token_count_and_latency`
  - `test_transformers_generator_rejects_missing_chat_template`
  - `test_transformers_generator_missing_dependencies_mentions_install_full`

**验证命令与通过标准**：

```bash
.venv/bin/python -m pytest tests/unit/evaluation/test_generate.py -q
make lint
```

通过标准：CPU/mock 环境不需要 torch/transformers 即可收集并运行单测；所有真实依赖均 lazy import；无直接 `open_r1.*` import。

### 步骤 3：定义严格 Evaluation 配置、逐题 record 与 JSON mapping

**目标文件**：`src/code_verifier/evaluation/evaluate.py`（新建）

**新增符号**：

```python
class EvaluationError(RuntimeError):
    """Raised when an evaluation run violates configuration, artifact, or resume contracts."""


@dataclass(frozen=True)
class EvaluationConfig:
    dataset_dir: Path
    split: Literal["validation", "test"]
    piston_config: Path
    model_revision: str | None
    checkpoint: str
    device: str
    generation: GenerationConfig


@dataclass(frozen=True)
class EvaluationRecord:
    run_id: str
    model_id: str
    checkpoint: str
    dataset_hash: str
    config_hash: str
    problem_id: str
    prompt_hash: str
    completion: str
    extracted_code: str
    parse_success: bool
    target_function_found: bool
    visible_pass_rate: float
    train_hidden_pass_rate: float
    eval_hidden_pass_rate: float
    execution_status: str
    visible_execution_status: str
    train_hidden_execution_status: str
    eval_hidden_execution_status: str
    visible_failure_counts: dict[str, int]
    train_hidden_failure_counts: dict[str, int]
    eval_hidden_failure_counts: dict[str, int]
    parse_error_type: str | None
    runtime_ms: float
    generation_latency_ms: float
    completion_tokens: int
    error_category_auto: str


@dataclass(frozen=True)
class EvaluationRunSummary:
    run_id: str
    total_problems: int
    completed_before_run: int
    generated_this_run: int
    results_path: Path


def evaluation_config_from_mapping(value: object) -> EvaluationConfig: ...


def load_evaluation_config(path: Path) -> EvaluationConfig: ...


def evaluation_record_to_mapping(record: EvaluationRecord) -> dict[str, object]: ...


def evaluation_record_from_mapping(value: object) -> EvaluationRecord: ...
```

**配置文件**：`configs/eval/pass1.yaml`（新建）

固定结构，不接受 unknown key：

```yaml
dataset_dir: data/processed/wp1-smoke
split: test
piston_config: configs/execution/piston-local.yaml
model_revision: null
checkpoint: base
device: auto
generation:
  do_sample: false
  temperature: null
  top_p: null
  max_new_tokens: 512
```

说明：`model_revision: null` 只用于 WP5-a debug/smoke 模板；WP5-b 生成 Base 正式结果前必须改为明确不可变 revision，并在 plan/review 中记录。

**主要功能**：

- 使用现有 `load_yaml_mapping()`，严格 exact-field 校验；unknown/missing/unconsumed 配置必须报错。
- 路径相对仓库根/CLI 当前工作目录解析，不把绝对机器路径写死到代码。
- `EvaluationRecord` mapping 必须：
  - JSON-safe；
  - 所有 rate 在 `[0,1]` 且 finite；
  - latency/runtime finite non-negative；
  - completion token 为非负整数；
  - failure_counts 是已知 `ExecutionStatus` -> positive int 的稳定字典；
  - execution status 必须是已知 `ExecutionStatus.value`；
  - `execution_status == eval_hidden_execution_status`；
  - 不含 tests/expected/metadata/reference solution/stdout/stderr。
- `evaluation_record_from_mapping()` 使用 strict exact fields，供 resume 读取；禁止忽略 unknown field。

**测试方案**：

- 测试文件：`tests/unit/evaluation/test_evaluate.py`
- 新增测试：
  - `test_load_evaluation_config_accepts_pass1_yaml`
  - `test_evaluation_config_rejects_unknown_or_missing_keys`
  - `test_evaluation_config_rejects_training_split`
  - `test_evaluation_record_round_trip_is_exact_and_json_safe`
  - `test_evaluation_record_rejects_nan_inf_and_out_of_range_rates`
  - `test_evaluation_record_rejects_unknown_status_or_failure_count`
  - `test_evaluation_record_mapping_contains_no_test_payload_keys`

**验证命令与通过标准**：

```bash
.venv/bin/python -m pytest tests/unit/evaluation/test_evaluate.py -q
make lint
```

通过标准：配置 unknown key 全拒绝；record round-trip 精确；`json.dumps(..., allow_nan=False)` 成功；payload guard 全通过。

### 步骤 4：实现三层逐题 Pass@1 评测与错误分类

**目标文件**：`src/code_verifier/evaluation/evaluate.py`（修改）

**新增符号**：

```python
def dataset_hash(problems: Sequence[CodeProblem]) -> str: ...


def prompt_hash(prompt: str) -> str: ...


def classify_evaluation_error(
    *,
    parse_error_type: str | None,
    visible_pass_rate: float,
    eval_hidden_pass_rate: float,
    eval_hidden_status: ExecutionStatus,
) -> str: ...


def evaluate_completion(
    *,
    run_id: str,
    model_id: str,
    checkpoint: str,
    dataset_hash_value: str,
    config_hash: str,
    problem: CodeProblem,
    prompt: str,
    generation: GenerationResult,
    executor: CodeExecutor,
) -> EvaluationRecord: ...
```

**主要功能**：

- `dataset_hash()` 对“当前 selected split 的完整 canonical records + 顺序”计算稳定 SHA-256；必须包含三层测试 identity，以便数据变化导致 run identity 变化，但 hash 输入不得写入日志。
- `prompt_hash()` 对实际传给 generator 的 §7.2 prompt UTF-8 bytes 做 SHA-256。
- `evaluate_completion()`：
  1. 用 `extract_python_code(generation.completion, expected_function_name=problem.function_name)` 生成 `extracted_code` / parse 字段；不得依赖 reward layer。
  2. 把三层 `TestCase` 各自经 `test_case_to_mapping()` 转为 verifier 输入。
  3. metadata 只传 verifier 所需资源限制：`time_limit_seconds`、`memory_limit_mb`。
  4. 三次调用 `verify_completion()`，依次 visible -> train_hidden -> eval_hidden；三层使用同一个 completion、function name、executor 和资源限制。
  5. 复制 `VerificationResult` 的 pass rate/status/failure counts，绝不保存 `execution_result`、stdout/stderr 或 tests。
  6. `runtime_ms` 是三层实际 execution runtime 的和；parse failure / unexecuted layer 为 0。
  7. `error_category_auto` 按 §3.9 粗分类，优先级固定：parse error -> sandbox/timeout/runtime -> visible-only -> large gap -> passed/wrong-answer/other。
- parser 或 verifier 对合法 `CodeProblem` 仍发生 contract error，应上抛 `EvaluationError`，不得把 infrastructure/config bug伪装成普通 wrong answer。

**测试方案**：

- 测试文件：`tests/unit/evaluation/test_evaluate.py`
- 使用 `MockExecutor` 队列精确提供三层结果：
  - `test_evaluate_completion_verifies_all_three_layers_in_order`
  - `test_evaluate_completion_never_sends_hidden_tests_to_generator`（结合 fake generator/调用记录）
  - `test_evaluate_completion_uses_eval_hidden_as_primary_execution_status`
  - `test_evaluate_completion_sums_execution_runtime`
  - `test_evaluate_completion_preserves_parse_failure_without_execution_payload`
  - `test_classify_evaluation_error_visible_only_success`
  - `test_classify_evaluation_error_large_public_eval_gap`
  - `test_classify_evaluation_error_timeout_sandbox_runtime_and_parse`
  - `test_evaluation_output_does_not_contain_test_values_or_metadata`

**验证命令与通过标准**：

```bash
.venv/bin/python -m pytest tests/unit/evaluation/test_evaluate.py -q
make lint
```

通过标准：每个合法 completion exactly 3 次 verifier/executor layer 路径；测试顺序可观测且固定；eval-hidden 为主 status；无 hidden payload 落盘字段。

### 步骤 5：实现 run artifacts、严格 append/resume 与可复现 identity

**目标文件**：

- `src/code_verifier/evaluation/evaluate.py`（修改）
- `src/code_verifier/environment.py`（必要的向后兼容扩展）
- `tests/unit/test_environment.py`（修改）

**新增 / 修改符号**：

```python
def evaluation_config_hash(
    config: EvaluationConfig,
    *,
    model_id: str,
    seed: int,
) -> str: ...


def load_evaluation_problems(config: EvaluationConfig) -> list[CodeProblem]: ...


def initialize_or_resume_run(
    *,
    output_root: Path,
    run_id: str,
    model_id: str,
    seed: int,
    config: EvaluationConfig,
    problems: Sequence[CodeProblem],
) -> tuple[Path, list[EvaluationRecord]]: ...


def append_evaluation_record(path: Path, record: EvaluationRecord) -> None: ...


def run_pass1_evaluation(
    *,
    run_id: str,
    model_id: str,
    seed: int,
    output_root: Path,
    config: EvaluationConfig,
    generator: CompletionGenerator,
    executor: CodeExecutor,
) -> EvaluationRunSummary: ...
```

若扩展环境信息，保持原 `collect_environment()` / `write_environment_record()` 签名不变；只向 `EnvironmentRecord` 增加可选/稳定字段，例如：

```python
class EnvironmentRecord(TypedDict):
    project_commit: str | None
    open_r1_commit: str | None
    python_version: str
    platform: str
    packages: dict[str, str | None]
    cuda_version: str | None
    gpu_name: str | None
    gpu_count: int
    dependency_lock_hash: str
```

**主要功能**：

- `load_evaluation_problems()` 必须先调用 `check_prepared_data(dataset_dir)`，确保 WP1 leakage/data invariants 仍成立；随后要求 `PreparationSummary.hf_dataset_dir` 非空并调用现有 `load_hf_dataset()` 解码完整 canonical records。若 prepared dataset 没有 HF artifact，本阶段明确 fail closed 并提示重新用 `hf_dataset` 输出格式准备数据，不直接调用私有 `_load_canonical()`，也不在 Evaluation Layer 新造宽松 JSONL parser。
- 过滤 `validation|test` split，至少 1 题；保持原始顺序；重复 problem id 视为阻断错误。
- `evaluation_config_hash()` 必须覆盖 resolved YAML、`model_id`、`model_revision`、`checkpoint`、`device`、generation settings、seed、selected split、Piston config identity；不能只 hash 配置文件路径。
- `initialize_or_resume_run()` 创建/验证：
  - `resolved_config.yaml`：保存合并后的最终 config + CLI model id/seed/run id；
  - `environment.json`：使用项目环境记录，加入可安全探测的 CUDA/GPU/依赖 identity；torch 不存在时字段为 null/0，不导致 CPU 单测失败；
  - `run.json`：至少含 §18 run_id/timestamp/git/open-r1/model/dataset/config/seed/command/status identity；
  - `metrics.jsonl`：只记录安全 progress event（problem id、status、latency、完成数量），不含 completion/code/tests；
  - `stdout.log` / `stderr.log`：只记录 CLI 摘要/脱敏错误；
  - `samples/results.jsonl`。
- run directory 不存在时原子创建基本 metadata；存在时必须验证 resolved identity，不能覆盖。
- resume 读取 `samples/results.jsonl` 使用 `loads_strict()`；每行 `evaluation_record_from_mapping()`；严格前缀验证。
- append 每题后 flush；如平台允许使用 `os.fsync()`，应对文件 descriptor fsync，确保崩溃时最多丢失当前尚未完成 append 的题。
- `run_pass1_evaluation()`：
  - 从已完成前缀长度继续；
  - 每题先 `build_evaluation_prompt()`，再 `generator.generate()`，再 `evaluate_completion()`，再 append record/progress；
  - 全部完成时更新 `run.json status=completed`；发生普通 exception 时更新为 `failed` 后重新抛出；不得捕获 `BaseException`；
  - 已全部完成的 resume 必须不调用 generator/executor。

**环境记录约束**：

- `dependency_lock_hash`：若仓库存在 `uv.lock`，hash 文件 bytes；当前仓库无 lock 时，hash `pyproject.toml` + 固定 tracked distribution version mapping，并在 `run.json` 额外记录 `dependency_identity_source="pyproject+installed_versions"`，不得伪称真实 lockfile。
- GPU 探测 lazy import torch；无 torch / 无 CUDA 时 `cuda_version=null`、`gpu_name=null`、`gpu_count=0`。

**测试方案**：

- `tests/unit/evaluation/test_evaluate.py`：
  - `test_run_pass1_evaluation_writes_results_in_dataset_order`
  - `test_resume_continues_after_valid_prefix_without_regenerating_completed_items`
  - `test_resume_completed_run_is_noop`
  - `test_resume_rejects_duplicate_out_of_order_or_corrupt_records`
  - `test_resume_rejects_model_seed_config_dataset_or_prompt_drift`
  - `test_run_artifacts_do_not_copy_completion_or_tests_into_logs_or_manifest`
  - `test_metrics_jsonl_contains_only_safe_progress_fields`
- `tests/unit/test_environment.py`：
  - 现有测试继续通过；
  - 新增 CPU/no-torch fallback 与 mocked CUDA identity 测试。

**验证命令与通过标准**：

```bash
.venv/bin/python -m pytest tests/unit/evaluation/test_evaluate.py tests/unit/test_environment.py -q
make lint
```

通过标准：合法前缀恢复只执行剩余题；全部完成重复运行 0 generation；所有 identity 漂移 fail closed；run metadata 无 test/completion payload 泄漏。

### 步骤 6：接入 `evaluate` CLI，并保持现有 CLI 向后兼容

**目标文件**：

- `src/code_verifier/cli.py`（修改）
- `tests/unit/test_cli.py`（修改）

**修改 / 新增符号**：

为避免 `config_required=True` 强制所有配置命令都必须显式传 `--output-dir`，允许 helper 独立控制 output requirement，保持已有调用行为不变：

```python
def _add_common_arguments(
    parser: argparse.ArgumentParser,
    *,
    config_required: bool = False,
    output_dir_default: Path | None = None,
    output_dir_required: bool | None = None,
) -> None: ...
```

新增：

```python
def _evaluate(args: argparse.Namespace) -> int: ...
```

`build_parser()` 新增：

```text
code-verifier evaluate \
  --config configs/eval/pass1.yaml \
  --model-id Qwen/Qwen2.5-Coder-0.5B-Instruct \
  --run-name base-debug \
  [--output-dir outputs] \
  [--seed 42] \
  [--log-level INFO]
```

参数：

- `--model-id`：必填，非空；
- `--run-name`：必填，作为 run_id；只允许安全文件名字符 `[A-Za-z0-9._-]`，禁止 `/`、`..`、空白-only；
- `--config`：必填；
- `--seed`：沿用全局参数；
- `--output-dir`：默认 `outputs`；
- `--log-level`：沿用全局参数。

**主要功能**：

- `_evaluate()`：
  1. `load_evaluation_config()`；
  2. 创建 `PistonExecutor` 并 `validate_runtime()`；
  3. 创建 `TransformersCompletionGenerator.from_pretrained(...)`；
  4. 调用 `run_pass1_evaluation()`；
  5. stdout 只打印 non-sensitive summary：run id、总题数、resume 数、当前执行数、results path。
- 捕获 `EvaluationError`、`GenerationError`、现有 Piston/config/data errors，统一 CLI exit 2；正常完成 exit 0。
- 不因模型代码错误返回 exit 1；模型代码错误是逐题 evaluation record 的正常结果。只有 run infrastructure/config/artifact error 阻断 CLI。
- 修改 `_add_common_arguments()` 时必须保证 `prepare-data`、`execute-batch` 仍保持原有 `--output-dir` required 行为，`check-data` / `parse-code` 等原有默认不变。

**测试方案**：

- `tests/unit/test_cli.py`：
  - `test_evaluate_help_exposes_required_and_common_arguments`
  - `test_evaluate_output_dir_defaults_to_outputs`
  - `test_evaluate_rejects_unsafe_run_name`
  - `test_evaluate_wires_config_generator_executor_and_runner`（monkeypatch/fakes，不加载模型/Piston）
  - `test_evaluate_reports_generation_dependency_error_as_exit_2`
  - `test_existing_configured_commands_keep_output_dir_requirement`
  - `test_build_parser_help_still_lists_all_existing_commands`

**验证命令与通过标准**：

```bash
.venv/bin/python -m pytest tests/unit/test_cli.py -q
.venv/bin/code-verifier evaluate --help
make lint
```

通过标准：`evaluate --help` 返回 0；示例参数形态成立；现有 CLI 单测无回归；不下载模型即可完成单测。

### 步骤 7：建立 WP5-a 端到端集成测试与恢复测试

**目标文件**：`tests/integration/test_wp5a_evaluation_pipeline.py`（新建）

**测试辅助类型/函数**（可以仅存在于测试文件）：

```python
class FakeGenerator:
    def generate(self, prompt: str, *, seed: int) -> GenerationResult: ...


def test_wp5a_fake_generation_to_three_layer_jsonl(tmp_path: Path) -> None: ...


def test_wp5a_interrupted_run_resumes_from_exact_prefix(tmp_path: Path) -> None: ...
```

**主要场景**：

- 从 `tests/fixtures/wp1/raw_problems.jsonl` 现有 20 题准备 artifact，或复用测试中临时构造的 `CodeProblem` 子集；不得依赖仓库 `data/processed` 的本地状态。
- 选至少 3 个 test problems；fake generator 为每题返回确定 completion。
- `MockExecutor` 为每题三层提供可预测结果，覆盖：全通过、visible-only、parse/runtime/timeout 中至少两类。
- 断言：
  - 每题只有一次 generation；
  - 每个 parsed completion 按三层发生预期 verifier/executor 调用；parse failure 由 verifier 保持结构化；
  - 输出行顺序与 problem 顺序相同；
  - §13.4 必需字段全部存在；
  - `eval_hidden_tests` sentinel 不在 prompt、run logs、manifest、metrics；results 只含 completion/code，不含 tests；
  - 人为中断在第 N 条后，再次运行只生成 N+1 后的题；最终文件无 duplicate。

如现有 Piston fixture 环境可复用，可额外加入 `@pytest.mark.piston` 的真实 sandbox 小用例，但不得把真实 Piston 设为默认 `make test` 的硬依赖；WP5-b Base 验收会强制真实 Piston。

**验证命令与通过标准**：

```bash
.venv/bin/python -m pytest tests/integration/test_wp5a_evaluation_pipeline.py -q
make test
```

通过标准：新增集成测试全绿；全仓默认测试全绿；真实模型/GPU/Piston 不可用时默认测试仍可执行。

### 步骤 8：文档、静态检查与 WP5-a 阶段验收

**目标文件**：

- `README.md`（修改）
- `AGENTS.md`（修改）

**文档内容**：

- README 新增 WP5-a evaluation 使用说明：
  - `make install` 可跑 CPU 单测；
  - `make install-full` 才具备真实 Transformers generation 环境；
  - 本地真实评测还要求 `configs/execution/piston-local.yaml` 对应 Piston 服务可用；
  - 示例 `evaluate` 命令；
  - run artifacts 与 resume 行为；
  - 明确 `model_revision: null` 仅 debug，正式 Base 在 WP5-b 必须 pin revision。
- AGENTS 更新当前 scope：WP0–WP4 完成；WP5-a 实现 generation/逐题/resume；WP5-b metrics/bootstrap/Base 尚未实现。
- 明确 evaluation 不得进入训练路径、不修改 frozen checkpoint、不访问训练 reward。

**最终验证命令**：

```bash
make lint
make test
.venv/bin/code-verifier --help
.venv/bin/code-verifier evaluate --help
```

如本机具备完整推理依赖，可做不纳入默认 CI 的 import smoke：

```bash
.venv/bin/python -c "import torch, transformers; print(torch.__version__, transformers.__version__)"
```

本阶段不得要求下载 0.5B 模型作为自动化验收前置；真实 Base 运行属于 WP5-b。

**通过标准**：

- `make lint`：Ruff check / format --check / strict mypy 全绿。
- `make test`：0 failed；既有 Piston tests 可继续按项目规则默认 skipped。
- `evaluate --help` 返回 0。
- WP5-a unit/integration 定向测试 0 failed。
- fake deterministic run 重跑产生相同 completion/result identity；中断恢复不重复已完成 generation。
- 输出逐题 JSONL 满足 §13.4 必需字段，且无 hidden test payload。
- `third_party/open-r1/**` 无修改。
- 不存在 `metrics.py`、`bootstrap.py`、SFT/GRPO 新实现。

## 5. 总体验收与测试计划

### 5.1 单元测试汇总

- `tests/unit/evaluation/test_generate.py`
  - §7.2 prompt；
  - §13.2 deterministic generation；
  - hidden-test prompt leakage；
  - Transformers lazy import / frozen inference contract。
- `tests/unit/evaluation/test_evaluate.py`
  - §13.4 per-problem schema；
  - 三层 verifier；
  - status/rate/runtime/error category；
  - config strictness；
  - run identity、append/resume、payload safety。
- `tests/unit/test_cli.py`
  - §17 `evaluate` 命令；
  - 全局参数；
  - existing command compatibility。
- `tests/unit/test_environment.py`
  - §18 environment identity 向后兼容与 CPU/GPU fallback。

### 5.2 集成测试

`tests/integration/test_wp5a_evaluation_pipeline.py` 必须覆盖：

1. prepared problem -> prompt -> fake generation -> parser -> 三层 verifier -> JSONL；
2. deterministic fixed seed；
3. interrupted prefix -> resume；
4. no hidden payload in prompt / logs / manifest / metrics；
5. output order 与 input problem 顺序一致。

### 5.3 WP5-a 独立验收清单

- [ ] generation 已实现且仅支持 deterministic pass@1 主路径。
- [ ] prompt 严格使用 visible examples，不含 train/eval hidden。
- [ ] pass@1 evaluator 通过现有 `verify_completion()` 对三层测试分别评测。
- [ ] §13.4 逐题 JSONL 已实现。
- [ ] run 具备 config/dataset/model/seed identity。
- [ ] 合法中断前缀可恢复；错误前缀 fail closed。
- [ ] 相同 fake model + seed + config + dataset 的结果稳定可复现。
- [ ] Base 错误类型所需原始字段已可统计。
- [ ] `make lint` 全绿。
- [ ] `make test` 全绿。
- [ ] `third_party/open-r1/**` 无修改。
- [ ] 未实现 WP5-b/WP6+ 范围。

> 注意：WP5 §20 的“聚合指标 / bootstrap / Base 模型结果 / 主结果表”在 WP5-a 后仍未完成，因此 reviewer 只能把 **WP5-a 子阶段**标记为完成，不能把 WP5 整体登记为已完成。

## 6. WP5-b 明确后续接口（只定义边界，不在本阶段实现）

WP5-a 的 `EvaluationRecord` / `samples/results.jsonl` 必须足以让下一阶段无模型重跑地实现：

- `parse_success_rate`
- `target_function_found_rate`
- `executable_rate`
- `syntax_error_rate`
- `runtime_error_rate`
- `timeout_rate`
- `visible_pass@1`
- `train_hidden_pass@1`
- `eval_hidden_pass@1`
- `eval_hidden_average_test_pass_rate`
- `public_eval_gap`
- Base error-category counts
- completion token / generation latency / execution latency 汇总

因此 WP5-a 不得在 JSONL 中遗漏 `parse_error_type`、三层 status、三层 pass rate、completion_tokens、generation latency、execution runtime 或 failure counts。WP5-b 将新增 `metrics.py` / `bootstrap.py`，运行真实 Base model revision，并完成 §13.5 bootstrap 与 §20 总体验收。

## 7. 风险与注意事项

1. **隐藏测试泄漏**：最高优先级风险。prompt builder 测试必须用唯一 sentinel 同时验证 train-hidden/eval-hidden 不可见；日志/manifest/metrics 同样禁止测试 payload。
2. **评测与训练耦合**：Evaluation Layer 只能加载 frozen model，不能创建 trainer/optimizer 或写 checkpoint。
3. **恢复污染**：不得“发现旧结果就跳过相同 problem_id”；必须验证完整 identity + 严格前缀，否则旧模型/旧配置结果可能混入新 run。
4. **模型 revision 漂移**：WP5-a debug 可允许 null revision，但 WP5-b Base 正式结果必须固定 immutable revision；reviewer 不得接受 `main`/null 作为最终 Base 可复现证据。
5. **依赖环境差异**：`make install` 与 `make install-full` 能力不同；模型 runtime 必须 lazy import，默认 CI 不应因 torch/transformers 缺失而失败。
6. **Piston availability**：默认单测使用 MockExecutor；真实 Base 结果必须由 WP5-b 通过真实 loopback Piston 完成。
7. **运行目录泄漏**：`results.jsonl` 规格要求保存 completion/code，但其它文件不得复制它们；outputs 不提交 Git。
8. **数值污染**：所有 runtime/rate/latency 必须 finite；JSON 使用 `allow_nan=False`。
9. **接口漂移**：评测层不得修改 WP4 `verify_completion()` 或执行器公共合同以图方便；如发现阻断缺陷必须先在 reviewer 中明确记录。
10. **性能优化越界**：WP5-a 不做 vLLM、continuous batching、并行 generation 或 pass@k；先保证可信、可恢复、可审计。

## 8. 关联文档索引

- `PROJECT_SPEC_Open-R1_CodeVerifier.md`
  - §6.2 Generation Layer / Evaluation Layer
  - §7.2 Prompt 输出合同
  - §7.3–§7.4 三层测试与泄漏防护
  - §13.1–§13.5 统一评测设计
  - §16 仓库结构
  - §17 CLI
  - §18 日志与可复现性
  - §19 Metrics / 集成测试 / CI
  - §20 WP5
  - §29 默认决策
- `proceedings.md`
  - WP4：已完成，WP5 为下一未完成阶段
- `src/code_verifier/data/schema.py`
  - `CodeProblem` / `TestCase`
- `src/code_verifier/data/prepare.py`
  - `check_prepared_data()` / `load_hf_dataset()`
- `src/code_verifier/parsing/code_extractor.py`
  - `extract_python_code()`
- `src/code_verifier/verification/verifier.py`
  - `verify_completion()`
- `src/code_verifier/execution/base.py`
  - `CodeExecutor` / `ExecutionStatus`
- `src/code_verifier/execution/piston.py`
  - `PistonExecutor`
- `third_party/open-r1/setup.py`（只读依据）
  - 固定 `torch==2.6.0` / `transformers==4.52.3`

---

## Planner 自检

- [x] 只覆盖 WP5，不进入 WP6+。
- [x] 因 WP5 跨 generation、evaluation、metrics、bootstrap、真实 Base 运行，已拆为 WP5-a / WP5-b；本文件只覆盖第一个独立阶段。
- [x] 实施步骤 8 个，≤ 10。
- [x] 新增业务模块 ≤ 8，且沿用规格 §16 的 evaluation 目录结构。
- [x] 每个代码步骤提供文件路径、主要函数/类完整签名、测试和可判定通过标准。
- [x] 规格已有 parser/verifier 接口逐字复用，不另造冲突实现。
- [x] 明确禁止修改 `third_party/open-r1/**`。
- [x] 计划不依赖 Codex/MCP/其它 skill，不包含创建执行 agent 的步骤。
- [x] 分支 `feat/wp5-a` 与 worktree `.worktrees/wp5-a` 已创建。
- [x] 计划文件位于该 worktree 的 `ai-work/planner/WP5-a-plan.md`。
- [x] main 未写入本阶段改动；计划将在 `feat/wp5-a` 上提交。
