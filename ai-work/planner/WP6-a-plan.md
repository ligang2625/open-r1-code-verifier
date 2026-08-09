
# WP6-a 实施计划（SFT 数据合同与 LoRA 训练集成）

## 1. 元信息

| 项 | 值 |
|---|---|
| stage_id | `WP6-a` |
| 目标 WP | `WP6`：SFT 集成（第一子阶段） |
| 规格依据 | `PROJECT_SPEC_Open-R1_CodeVerifier.md` §4.1、§5.1–5.3、§7.2–7.4、§11、§17–§21、§29 |
| 前置状态 | `proceedings.md`：WP0–WP5 全部完成；WP5-b 已于 2026-08-09 合并，WP6 尚未开始 |
| `planning_base_commit` | `b4314895850eb0f5af224d1f7236cf3fe6e58737` |
| proposed branch | `feat/wp6-a` |
| proposed worktree | `.worktrees/wp6-a` |
| final plan path | `ai-work/planner/WP6-a-plan.md` |
| execution report path | `ai-work/executor/WP6-a-executor.md` |
| review path | `ai-work/reviewer/WP6-a-review.md` |
| plan lifecycle | planner-ex handoff → `stage-lifecycle bootstrap_plan` → committed plan seal |

> WP6 拆成 `WP6-a` / `WP6-b`。原因不是内部并行，而是当前开发机是 GTX 1660 Ti（6GB），规格与 `AGENTS.md` 明确禁止其承担 SFT/GRPO 训练；同时当前仓库只有 20 题 smoke fixture（train split 12 条），不足以完成 §11.4 的 50 条真实 SFT smoke。`WP6-a` 因此只实现并验收可在当前机器可靠完成的 SFT 数据/训练控制面；`WP6-b` 在 24GB 训练机与满足规模的数据到位后完成真实训练、checkpoint reload、B 组统一评测与成本验收。

## 2. 目标与范围

### 目标（规格原文）

WP6 总目标：使用 Open-R1/TRL 完成 LoRA SFT。

本子阶段目标：建立严格、无 hidden-test 泄漏、可复现、可通过 `train-sft` 启动的 LoRA SFT 集成，使后续 WP6-b 只需在训练机上执行真实训练并接入 checkpoint 评测，而无需重做数据合同或训练控制面。

### WP6 总交付（规格原文）

- 数据映射；
- SFT config；
- 训练脚本；
- checkpoint；
- B 组评测。

### WP6-a 本阶段交付

- 单一共享的 §7.2 code-generation prompt builder，WP5 evaluation 与 SFT 共用；
- SFT training artifact 明确只携带 prompt、SFT target、必要的 visible-only 质量验证字段，不含任何 train/eval hidden 或 reference solution；
- SFT target 规范化、解析、visible-test 执行验证、长度门槛与 TRL 数据映射；
- 项目级严格 SFT YAML schema、LoRA/Open-R1/TRL runtime 构建、硬件保护、可复现 run artifact；
- `code-verifier train-sft` CLI 与 `--resume-from-checkpoint`；
- `configs/sft/debug.yaml` 与 `configs/sft/main.yaml`；
- PEFT training dependency 的精确 pin 与安装入口；
- CPU/mock 单元与集成测试，以及 pinned TRL/Open-R1 runtime import/contract preflight。

### 本阶段验收

- `make lint` 全绿；
- `make test` 全绿；
- `code-verifier train-sft --help` 返回 0；
- SFT artifact / mapped dataset 中不存在 `train_hidden_tests`、`eval_hidden_tests`、`reference_solution`；
- SFT prompt 与 WP5 `build_evaluation_prompt()` 字节级一致，且只包含 visible examples；
- SFT target 必须规范为恰好一个 Python fenced block，可解析到目标函数，并通过 caller-selected visible tests；
- pinned stack runtime preflight 明确验证 `trl==0.18.0`、`transformers==4.52.3`、`accelerate==1.4.0`、Open-R1 pinned checkout 与 PEFT 可导入；
- 当前 GTX 1660 Ti 上不得启动真实训练，训练命令必须在模型加载前 fail closed；
- 不要求本阶段生成真实 checkpoint，不要求完成 B 组评测；这些是 WP6-b acceptance gate。

### 范围内 / 范围外

- 范围内：SFT prompt/data contract、visible-only trajectory quality gate、LoRA training runtime、配置、CLI、run metadata、resume plumbing、测试、文档与 dependency pin。
- 范围外：任何 GRPO/WP7 功能；Public/Hidden reward 接入；大规模超参搜索；QLoRA；训练系统优化；修改 `third_party/open-r1/**`；在 GTX 1660 Ti 上实际训练；正式 50 条 SFT smoke；main 1.5B SFT；checkpoint unified evaluation；B 组数值结果。

## 3. 前置条件与约束

- `proceedings.md` 已确认 WP5-a / WP5-b 完成，WP6 是第一个未完成 WP。
- 规划开始与 handoff 前 Git 状态一致：只有 root worktree，branch 只有 `main`，`main HEAD=b4314895850eb0f5af224d1f7236cf3fe6e58737`。
- `third_party/open-r1/` 只读；Open-R1 模块访问仅允许经 `code_verifier.training.open_r1_adapter.import_open_r1_module()`。
- pinned upstream runtime 已预检：`trl==0.18.0`、`transformers==4.52.3`、`accelerate==1.4.0`；当前环境 `peft` 未安装。Open-R1 `setup.py` 允许 `peft>=0.14.0`，本阶段先以 `peft==0.14.0` 作为项目精确 pin；若该版本在 pinned stack 的 import/trainer-construction preflight 失败，不得静默漂移版本，应记录 blocker 交给 review/replan。
- TRL 0.18 的有效序列长度参数是 `SFTConfig.max_length`（默认 1024；`max_seq_length` 为兼容字段且默认 `None`）。项目配置继续使用规格名 `max_seq_length`，runtime 显式映射到 TRL `max_length`，避免同时设置两个字段。
- `ModelConfig` 使用 LoRA：`use_peft=True`、`lora_r=16`、`lora_alpha=32`、`lora_dropout=0.05`、`lora_target_modules=None`（auto）；`trust_remote_code=False`；主实验不启用 4/8-bit。
- 默认主训练模型为 `Qwen/Qwen2.5-Coder-1.5B-Instruct`；`configs/sft/main.yaml` 复用 Base 已冻结 revision `2e1fd397ee46e1388853d2af2c993145b0f1098a`。
- 当前 1660 Ti 是开发/生成 smoke 机，不承担 SFT。任何 executor/reviewer 不得为了“验收”绕过该硬件约束。
- SFT 训练数据和日志禁止包含 hidden tests；训练 logger 默认不得打印 sample prompt/completion/test payload。
- 任何 SFT response 都不得直接在宿主 Python 中 `exec/eval/compile`；正确性验证继续走 `verify_completion()` + configured `CodeExecutor`（CLI 使用 Piston，测试使用 Mock/scripted executor）。
- 不改变 WP5 deterministic pass@1 的生成参数、evaluation artifact、metric 定义或 Base 结果。

## 4. 实施步骤

### 步骤 1：抽取并冻结共享 §7.2 prompt builder

**目标文件**：
- 新增 `src/code_verifier/prompting.py`
- 修改 `src/code_verifier/evaluation/generate.py`
- 新增 `tests/unit/test_prompting.py`
- 修改 `tests/unit/evaluation/test_generate.py`

**新增 / 修改的符号**：
```python
def build_code_prompt(problem: CodeProblem) -> str:
    ...

def build_evaluation_prompt(problem: CodeProblem) -> str:
    ...  # 保留现有 public signature，委托给 build_code_prompt
```

**主要功能**：
- 将当前 `evaluation.generate.build_evaluation_prompt()` 的固定 §7.2 模板原样移到 neutral module；
- `build_evaluation_prompt()` 作为兼容 wrapper，避免 WP5 public API 变化；
- builder 只读取 `problem.prompt`、`function_signature`、`visible_tests`，绝不访问 hidden/reference/SFT 字段；
- 输出字节必须与现有 WP5 行为一致，避免改变 Base evaluation identity。

**测试方案**：
- `tests/unit/test_prompting.py::test_build_code_prompt_matches_section_7_2_contract`
- `tests/unit/test_prompting.py::test_build_code_prompt_uses_visible_examples_only`
- `tests/unit/evaluation/test_generate.py::test_build_evaluation_prompt_delegates_without_behavior_change`
- 断言：固定 fixture 的旧/新 prompt 完全相同；hidden sentinel 不出现在输出。

**验证命令与通过标准**：
```bash
.venv/bin/python -m pytest tests/unit/test_prompting.py tests/unit/evaluation/test_generate.py -q
```
通过标准：全部通过，无 WP5 prompt snapshot/contract 变化。

### 步骤 2：升级 SFT training artifact 为 visible-only 可验证合同

**目标文件**：
- 修改 `src/code_verifier/data/leakage_checks.py`
- 修改 `src/code_verifier/data/prepare.py`（仅必要的 artifact revalidation / documentation wiring）
- 修改 `tests/unit/data/test_leakage_checks.py`
- 修改 `tests/unit/data/test_prepare.py`
- 修改 `tests/integration/test_wp1_data_pipeline.py`

**修改的既有符号**：
```python
def build_training_record(
    problem: CodeProblem,
    *,
    kind: TrainingArtifactKind,
) -> dict[str, JsonValue]:
    ...

def check_training_record(
    record: Mapping[str, object],
    *,
    kind: TrainingArtifactKind,
) -> None:
    ...
```

**主要功能**：
- 将 SFT whitelist 调整为：`problem_id`、完整 rendered `prompt`、`function_name`、`visible_tests`、`sft_response`、`metadata`；
- SFT `prompt` 必须由 `build_code_prompt(problem)` 生成，不再保存裸 problem statement；
- 仅保留 visible tests 作为进入训练前 trajectory correctness gate 的可信输入；不允许 `train_hidden_tests`、`eval_hidden_tests`、`reference_solution`、starter code 等进入 SFT artifact；
- Public/Hidden GRPO artifact 合同不在本阶段修改；
- `check_prepared_data()` 继续要求 SFT artifact 与 canonical train split 一一对应、顺序一致、严格等价。

**测试方案**：
- `test_sft_training_record_uses_shared_prompt_and_visible_tests_only`
- `test_sft_training_record_rejects_train_hidden_eval_hidden_and_reference_solution`
- `test_prepared_sft_artifact_matches_canonical_visible_view`
- integration 中重新断言 `training/sft.jsonl` 不含 hidden/reference key 或 sentinel，并且 prompt 包含 function signature 与 visible examples。

**验证命令与通过标准**：
```bash
.venv/bin/python -m pytest tests/unit/data tests/integration/test_wp1_data_pipeline.py -q
```
通过标准：WP1 数据/泄漏回归全部通过；SFT artifact 仍是 training-safe view。

### 步骤 3：实现 SFT target 规范化与 trajectory quality gate

**目标文件**：
- 新增 `src/code_verifier/training/sft_data.py`
- 新增 `tests/unit/training/test_sft_data.py`

**新增符号**：
```python
@dataclass(frozen=True)
class SFTExample:
    problem_id: str
    prompt: str
    completion: str

class SFTDataError(ValueError):
    ...

def normalize_sft_completion(
    response: str,
    *,
    expected_function_name: str,
) -> str:
    ...

def validate_sft_record(
    record: Mapping[str, object],
    *,
    executor: CodeExecutor,
) -> SFTExample:
    ...

def build_sft_dataset(
    records: Sequence[Mapping[str, object]],
    *,
    executor: CodeExecutor,
    tokenizer: Any,
    max_seq_length: int,
) -> Dataset:
    ...
```

**主要功能**：
- 对 raw `sft_response` 做 UTF-8/非空验证；若是 fenced response，使用既有 parser 提取目标函数；若是裸 Python implementation，只允许在 AST 可解析且含预期 top-level target function 时包装为 fenced block；
- 最终 completion 强制规范成恰好一个 `python` fenced block，移除多代码块/prose 歧义；
- 通过 `verify_completion(completion, function_name, visible_tests, executor)` 验证正确性，仅使用 artifact 中 visible tests；任何 parse/runtime/wrong-answer/sandbox failure 均 fail closed；
- 增加 bounded “明显重复/截断”门槛：拒绝空/截断 fence、重复 fenced blocks，经规范化后仍出现异常重复代码段的 response；规则必须确定、可单测，不进行启发式模型评分；
- 用 tokenizer 的 chat template 计算 user prompt + assistant completion 的总 token 长度，严格 `<= max_seq_length`；超长样本报 `SFTDataError`，不得静默截断 target；
- 输出给 TRL 的 Dataset 只含 `prompt` / `completion` conversational records，不把 `visible_tests`、`function_name`、metadata 带入 trainer dataloader；
- 实现前先用 pinned TRL 0.18 做一个不训练的 contract probe，确认 prompt-completion conversational dataset 形状；若 pinned runtime 不支持预期形状，停止并记录 blocker，不得猜 API。

**测试方案**：
- `test_normalize_raw_python_to_single_fenced_completion`
- `test_normalize_rejects_missing_target_and_duplicate_or_truncated_blocks`
- `test_validate_sft_record_uses_visible_tests_only`
- `test_validate_sft_record_fails_closed_on_wrong_answer_and_sandbox_error`
- `test_build_sft_dataset_drops_validation_payloads_before_trainer`
- `test_build_sft_dataset_rejects_over_max_sequence_length_without_truncation`
- hidden sentinel 注入测试确保从不传给 executor/tokenizer/trainer dataset。

**验证命令与通过标准**：
```bash
.venv/bin/python -m pytest tests/unit/training/test_sft_data.py -q
```
通过标准：所有质量门槛、泄漏门槛、长度门槛均可判定通过。

### 步骤 4：引入精确 PEFT training dependency 与 runtime preflight

**目标文件**：
- 修改 `pyproject.toml`
- 修改 `uv.lock`
- 修改 `Makefile`
- 修改 `src/code_verifier/training/open_r1_adapter.py`（仅在需要更清晰错误包装时）
- 修改 `tests/unit/test_open_r1_adapter.py`

**新增 / 修改的接口**：
- `pyproject.toml` 新增 optional extra：`training = ["peft==0.14.0"]`
- `Makefile` 新增 `install-train`：`uv sync --extra dev --extra gpu --extra training`
- 保持 `install-gpu` / `install-full` 现有 inference 语义不变，避免把训练依赖悄悄塞进日常 1660 环境。

**主要功能**：
- 安装后验证 pinned versions 与 PEFT import；
- 所有 Open-R1 module lookup 仍通过 `import_open_r1_module("open_r1.configs")` / `import_open_r1_module("open_r1.utils")` 等 adapter boundary；
- 不直接 import `open_r1.*` 于其它 project module；
- 允许直接使用 pinned `trl` public API，但要在 runtime construction 处显式检查预期 symbols：`ModelConfig`、`SFTConfig`、`SFTTrainer`、`get_peft_config`。

**测试方案**：
- `test_open_r1_sft_modules_resolve_only_through_adapter`
- import failure 仍转换为脱敏、可操作错误；
- dependency inventory 包含 PEFT exact version。

**验证命令与通过标准**：
```bash
make install-train
.venv/bin/python -c "import peft, trl, transformers, accelerate; print(peft.__version__, trl.__version__, transformers.__version__, accelerate.__version__)"
```
通过标准：PEFT 为精确 pin，TRL/Transformers/Accelerate 保持 pinned Open-R1 stack；不得升级 Open-R1 submodule。

### 步骤 5：实现严格 SFT config、硬件 guard、LoRA trainer construction 与 run artifacts

**目标文件**：
- 新增 `src/code_verifier/training/sft.py`
- 新增 `src/code_verifier/training/__init__.py` export（如现有文件为空则仅增加必要 exports）
- 新增 `configs/sft/debug.yaml`
- 新增 `configs/sft/main.yaml`
- 新增 `tests/unit/training/test_sft.py`

**新增符号**：
```python
@dataclass(frozen=True)
class SFTTrainingConfig:
    run_name: str
    model_id: str
    model_revision: str | None
    dataset_path: Path
    piston_config: Path
    max_seq_length: int
    max_steps: int
    num_train_epochs: float
    per_device_train_batch_size: int
    gradient_accumulation_steps: int
    learning_rate: float
    warmup_ratio: float
    lr_scheduler_type: str
    logging_steps: int
    save_strategy: str
    save_steps: int
    eval_strategy: str
    eval_steps: int | None
    bf16: bool
    fp16: bool
    gradient_checkpointing: bool
    lora_r: int
    lora_alpha: int
    lora_dropout: float
    seed: int
    min_cuda_memory_gb: float

@dataclass(frozen=True)
class SFTTrainingSummary:
    run_dir: Path
    checkpoint_dir: Path
    train_loss: float
    train_samples: int
    gpu_hours: float

class SFTTrainingError(RuntimeError):
    ...

def load_sft_training_config(path: Path) -> SFTTrainingConfig:
    ...

def validate_sft_training_hardware(config: SFTTrainingConfig) -> None:
    ...

def run_sft_training(
    config: SFTTrainingConfig,
    *,
    output_root: Path,
    seed: int,
    executor: CodeExecutor,
    resume_from_checkpoint: Path | None = None,
) -> SFTTrainingSummary:
    ...
```

**主要功能**：
- YAML exact-schema/fail-closed；未知字段、非法 dtype/bf16/fp16 组合、非 LoRA、量化、负数/零超参、危险输出路径全部拒绝；
- `debug.yaml` 使用 0.5B debug model、短程 `max_steps`，但仍声明 `min_cuda_memory_gb` 为训练机级别，防止 1660 实跑；`main.yaml` 使用 1.5B + frozen revision + bf16 + §11.3 默认 LoRA/hyperparameters；
- hardware guard 在 tokenizer/model/trainer 构建前检查 CUDA、GPU memory 与请求 dtype；当前 6GB 1660 必须明确拒绝；
- 用 adapter 获取 Open-R1 `SFTConfig` / `get_model` / `get_tokenizer`，用 TRL `ModelConfig` / `SFTTrainer` / `get_peft_config` 构造 LoRA training；不得复制 `open_r1.sft.py` 的完整训练脚本，也不得修改上游；
- project `max_seq_length` 映射到 TRL `max_length`；`trust_remote_code=False`、`load_in_4bit=False`、`load_in_8bit=False`；
- `build_sft_dataset()` 完成 visible-only validation 后再传 trainer；
- `trainer.train(resume_from_checkpoint=...)` 后要求 train loss finite；保存 trainer state 与 PEFT checkpoint；
- run layout 至少包含：`resolved_config.yaml`、`environment.json`、`run.json`、`metrics.jsonl`、`stdout.log`、`stderr.log`、`checkpoints/`；run metadata 记录 §18.1 的 project/open-r1/dependency/model/dataset/config/seed/start/end/gpu_hours/status；不得写 prompt/completion/test payload；
- 默认 `report_to=[]` 或等价本地-only logging，避免 W&B 意外上传样本；
- crash/interrupt 后已有 checkpoint 可通过 explicit resume 继续，但不实现 WP7 resume 语义。

**测试方案**：
- `test_load_sft_training_config_rejects_unknown_and_unsafe_values`
- `test_main_config_matches_spec_lora_defaults_and_frozen_revision`
- `test_hardware_guard_rejects_six_gb_gpu_before_model_load`
- `test_hardware_guard_accepts_mock_24gb_bf16_gpu`
- `test_runtime_maps_project_max_seq_length_to_trl_max_length`
- `test_runtime_uses_lora_without_quantization_or_remote_code`
- `test_run_artifacts_are_payload_free_and_loss_must_be_finite`
- `test_resume_path_is_forwarded_without_changing_run_identity`
- trainer/model/tokenizer 用 fake runtime；单元测试绝不下载模型、绝不启动真实训练。

**验证命令与通过标准**：
```bash
.venv/bin/python -m pytest tests/unit/training/test_sft.py -q
```
通过标准：配置、runtime mapping、hardware guard、run metadata 与 finite-loss gate 全部通过；本机无真实训练。

### 步骤 6：接入 `train-sft` CLI 并增加 WP6-a 端到端非训练集成测试

**目标文件**：
- 修改 `src/code_verifier/cli.py`
- 修改 `tests/unit/test_cli.py`
- 新增 `tests/integration/test_wp6a_sft_integration.py`

**新增 / 修改的符号**：
```python
def _train_sft(args: argparse.Namespace) -> int:
    ...

def build_parser() -> argparse.ArgumentParser:
    ...  # 描述更新为 WP0-WP6-a commands
```

**CLI 合同**：
```text
code-verifier train-sft \
  --config configs/sft/debug.yaml \
  --seed 42 \
  --output-dir outputs/sft \
  --log-level INFO \
  [--resume-from-checkpoint PATH]
```

**主要功能**：
- 读取 SFT config、Piston config；CLI real path 创建 `PistonExecutor` 并在训练前验证 runtime；
- 然后进入 `run_sft_training()`；
- 退出码：成功 0；配置/依赖/hardware/Piston/data/training infrastructure 错误统一脱敏为 2；训练数据质量失败不得被当成成功；
- `--help` 在 CPU/无 PEFT 环境下仍可显示，不应 eager-import trainer/model runtime；
- integration test 用临时 SFT artifact + scripted/Mock executor + fake trainer runtime 覆盖 data → quality gate → trainer dataset → run artifacts，不执行 candidate code、不加载模型、不使用 GPU。

**测试方案**：
- `tests/unit/test_cli.py::test_train_sft_help_exposes_common_and_resume_arguments`
- `tests/unit/test_cli.py::test_train_sft_reports_hardware_or_runtime_error_without_traceback`
- `tests/integration/test_wp6a_sft_integration.py::test_wp6a_sft_pipeline_maps_visible_only_data_and_writes_reproducible_artifacts`
- `...::test_wp6a_sft_pipeline_rejects_hidden_field_or_failed_trajectory`

**验证命令与通过标准**：
```bash
.venv/bin/python -m pytest tests/unit/training tests/integration/test_wp6a_sft_integration.py tests/unit/test_cli.py -q
.venv/bin/code-verifier train-sft --help
```
通过标准：0 failed；CLI help 不触发 GPU/model loading。

### 步骤 7：文档、回归与 WP6-b handoff readiness

**目标文件**：
- 修改 `README.md`
- 修改 `AGENTS.md`
- 必要时更新 `environment.json` 仅用于安装 training extra 后的依赖记录；不得伪造 24GB 训练机 identity

**主要功能**：
- README 写明 `make install-train`、`train-sft` 命令、输出结构、resume、Piston 与 24GB GPU 前置条件；
- 明确 1660 Ti 只能做开发/生成 smoke，`train-sft` 在该机 fail closed；
- 明确 WP6-a 不产生 B 组数值结果；
- 记录 WP6-b 必须完成的外部 gate：满足规模的 SFT 数据（正式 smoke 至少 50 条）、24GB GPU、1–2 step smoke、finite loss、checkpoint reload、SFT checkpoint 统一 deterministic pass@1 B 组评测、成本数据；
- 不在本阶段修改 proceedings（由 stage-lifecycle finalization/reviewer 流程负责）。

**总验证命令**：
```bash
make lint
make test
make test-gpu
.venv/bin/code-verifier --help
.venv/bin/code-verifier train-sft --help
.venv/bin/python -c "import importlib.metadata as m; print(m.version('open-r1'), m.version('trl'), m.version('transformers'), m.version('accelerate'), m.version('peft'))"
```

**通过标准**：
- `make lint` 全绿；
- `make test` 0 failed；
- `make test-gpu` 继续只验证既有 1660 inference/autograd smoke，不启动 SFT；
- Open-R1 gitlink 未变化；
- 无 `third_party/open-r1/**` diff；
- dependency versions 与 pinned stack 一致，新增 PEFT 精确版本可追溯。

## 5. 总体验收与测试计划

- 单元测试：prompt builder、SFT artifact whitelist、target normalization、visible-only verification、token length、config parser、hardware guard、TRL/Open-R1 argument mapping、finite-loss/run artifact、resume forwarding、CLI error handling。
- 集成测试：基于 prepared smoke-style SFT artifact，使用 Mock/scripted executor + fake trainer runtime 完成非 GPU 的 WP6-a end-to-end；确保 trainer dataset 已移除 tests/metadata/function name。
- 数据泄漏：SFT artifact 和 trainer dataset 都扫描 `train_hidden_tests` / `eval_hidden_tests` / reference solution key 与 sentinel；禁止 payload 进入 logs/run metadata。
- 外部 runtime：只做 import/signature/trainer-construction preflight，不在 1660 执行训练。
- 最终标准：
  - [ ] §7.2 prompt 与 WP5 完全一致
  - [ ] §7.4 hidden-test isolation 保持成立
  - [ ] §11.1/11.2 data mapping 与 trajectory gate 可执行
  - [ ] §11.3 LoRA/default config 可映射到 pinned TRL/Open-R1 runtime
  - [ ] `train-sft` command / resume plumbing 完成
  - [ ] §18 run metadata/artifact contract 完成且 payload-free
  - [ ] `make lint` 全绿
  - [ ] `make test` 全绿
  - [ ] 当前 GTX 1660 Ti 未执行任何 SFT training
  - [ ] WP6-b 的真实 GPU/data gates 被明确保留，未伪造通过

## 6. Execution Routing

```yaml
execution_routing:
  version: 1
  mode: single
  complexity: difficult_serial
  single_class: difficult_serial
  parallelizability: medium
  multi_benefit: low
  independent_workstreams: 2
  rationale:
    - "该 stage 同时修改共享 prompt/data contract、引入 visible-only trajectory verification，并接入 pinned TRL/Open-R1/PEFT runtime；接口与泄漏边界相互依赖，错误会跨 WP1/WP5/WP6 传播，属于高推理/高回归风险串行集成。"
    - "数据合同与 training runtime 表面可分成两个 lane，但 runtime 依赖前者最终确定的 prompt/record/dataset 形状，CLI 与 integration 又要汇合两边；multi coordinator 的接口同步和集成成本高于并行收益，因此采用 SINGLE。"
  workstream_candidates: []
```

## 7. 风险与注意事项

- **最大风险：SFT prompt 漂移。** 必须先抽取共享 builder，并以 byte-for-byte regression 证明 WP5 evaluation 没变。
- **最大安全风险：为验证 SFT target 绕过 Piston。** 禁止 host `exec/eval/compile`；必须走现有 verifier/executor contract。
- **最大泄漏风险：为了质量验证把 hidden tests 带入 trainer。** SFT artifact 只允许 visible tests；trainer dataset 在验证后必须 drop 所有测试 payload。
- **最大 runtime 风险：PEFT/TRL 版本兼容。** 先 preflight exact pin；失败就 blocker，不升级 pinned Open-R1/Transformers/TRL 来“修好”。
- **训练硬件风险：当前 1660 Ti。** hardware guard 必须在模型加载前拒绝，并且 executor 本轮不得真实训练。
- **checkpoint evaluation 未完成。** LoRA adapter 如何进入现有 `TransformersCompletionGenerator` / unified evaluation 属于 WP6-b，不在 WP6-a 预先实现或猜测。
- **数据规模不足。** 当前 12 条 train fixture 只能用于代码路径测试；不得将其冒充 §11.4 的 50 条 SFT smoke acceptance。
- **不做 QLoRA。** 主实验保持非量化 LoRA，除非未来 24GB 实测证明不可行并经过单独 review/replan。

## 8. 关联文档索引

- `PROJECT_SPEC_Open-R1_CodeVerifier.md`：§4.1、§5.1–5.3、§7.2–7.4、§11、§17、§18、§19、§20 WP6、§21、§29
- `proceedings.md`：WP5-b 已完成；环境维护章节明确 1660 Ti 只覆盖 inference/autograd，不覆盖 LoRA/SFT/GRPO/PEFT training
- `AGENTS.md`：当前 scope WP0–WP5 completed，WP6 SFT next；24GB GPU 承担训练，1660 Ti 不承担训练
- `third_party/open-r1/src/open_r1/sft.py`：只读参考 upstream SFT lifecycle
- `third_party/open-r1/src/open_r1/configs.py`：pinned Open-R1 `SFTConfig`
- `third_party/open-r1/src/open_r1/utils/model_utils.py`：pinned tokenizer/model construction
- `third_party/open-r1/setup.py`：pinned TRL/Transformers/Accelerate 与 PEFT compatibility floor

## 9. Handoff

- 下一步：本地运行 `$stage-lifecycle bootstrap_plan`，使用本计划正文创建/复用 `.worktrees/wp6-a` / `feat/wp6-a` 并 commit plan seal。
- bootstrap 成功并得到 `plan_commit` 前，不得调用 execution-router。
- bootstrap 后由 `$execution-router` 消费 sealed plan；本轮 routing 为 SINGLE / difficult_serial。
- executor 不得在当前 GTX 1660 Ti 上启动真实 SFT；本阶段真实训练 gate 明确保留给 WP6-b。

## Implementation contract

- Work from this plan in small, reviewable steps.
- Keep edits scoped to the requested task and existing project conventions.
- Run focused verification before handing work back.
- Update .ai-bridge/agent-status.md with files touched, checks run, results, blockers, and review notes.
- Save the final review diff to .ai-bridge/implementation-diff.patch when practical.
- Append notable execution events to .ai-bridge/execution-log.jsonl when the implementation agent supports logging.
