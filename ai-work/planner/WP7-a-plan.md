# WP7-a 实施计划（GRPO control-plane 与奖励日志开发）

## 1. 元信息

| 项 | 值 |
|---|---|
| stage_id | `WP7-a` |
| stage_profile | `development` |
| target_hardware | `GTX 1660 Ti (6GB)` |
| evidence_class | `engineering` |
| development_terminal | `false` |
| 目标 WP | `WP7`：GRPO 集成的 control-plane / reward / artifact development |
| 规格依据 | `PROJECT_SPEC_Open-R1_CodeVerifier.md` §7.2、§7.4、§10、§12、§19.2.1、§20.0、WP7、§21.1/§21.4、§29 |
| 前置状态 | `proceedings.md`：WP6-a / WP6-c 已 finalized，SFT control-plane、completed B checkpoint identity、PEFT reload 与统一 B evaluation development 已进入 main；真实 SFT/B 仍属于 validation。当前无合法 `Development Complete Record`，WP7/WP8 development 尚未完成。 |
| `planning_base_commit` | `0e836995eb2bb05c6cec78aa8e6d056573c9589c` |
| proposed branch | `feat/wp7-a` |
| proposed worktree | `.worktrees/wp7-a` |
| final plan path | `ai-work/planner/WP7-a-plan.md` |
| execution report path | `ai-work/executor/WP7-a-executor.md` |
| review path | `ai-work/reviewer/WP7-a-review.md` |
| plan lifecycle | planner-ex handoff → `stage-lifecycle bootstrap_plan` → committed plan seal |

## 2. 目标与范围

### 目标（规格对应）

完成 WP7 development acceptance 的第一条可独立验收纵向切片：在不启动真实 optimizer-based GRPO 的前提下，建立 pinned Open-R1/TRL GRPO control-plane，使 Public-RLVR 与 Hidden-RLVR 从同一个显式 completed SFT B run 初始化，复用既有 verifier/reward/Piston 边界，具备两组严格等价配置、共享 prompt、reward callback、rollout/reward/group artifact、resume 与 20 GiB hardware guard，并可用 fixture/fake runtime 证明真实生产合同可接通。

C/D 唯一主要实验差异必须保持为 reward test source：Public 使用 `visible_tests`，Hidden 使用 `train_hidden_tests`。`eval_hidden_tests` 不得进入任何 GRPO dataset、callback、日志或 trainer path。

### 交付（本 stage）

- 基于现有 WP1 `public_grpo.jsonl` / `hidden_grpo.jsonl` schema 的 payload-minimal TRL GRPO dataset builder，并与 §7.2 共享 prompt 生成逻辑；
- exact-schema `GRPOTrainingConfig`、Public/Hidden 两组 checked-in config，以及 C/D 公平性 pair validator；
- 适配 pinned TRL 0.18.0 custom reward callback contract 的 Public/Hidden reward wiring，继续调用现有 `compute_code_rewards()`；
- sanitized `rollouts.jsonl`、`rewards.jsonl`、`group_metrics.jsonl` 与 trainer metrics，能够检查 reward 分量、group mean/std/all-equal、截断与错误状态，同时不泄漏测试 payload；
- pinned Open-R1/TRL/PEFT runtime construction：从 completed SFT B adapter 构造真正以 B 为起点/参考策略的 GRPO policy，再叠加新的 GRPO LoRA；
- strict GRPO run layout、identity、resume、failure metadata 与 20 GiB hardware guard；
- `code-verifier train-grpo` CLI，默认输出遵循 `CODE_VERIFIER_ARTIFACT_ROOT/grpo`；
- unit/integration/fake-runtime evidence 与最小 README/AGENTS 更新。

### 验收（本 stage）

- Public/Hidden config 除 `run_name`、`reward_mode`、`dataset_path` 外实验超参数完全一致，实际两份 dataset 题目/order/prompt inputs/visible payload 一致；
- 两组 runtime 均只能通过 `load_completed_sft_checkpoint()` 接受同一个类型的 completed B source，不接受任意 adapter path；
- Public callback 只以 visible tests 计分；Hidden callback 只以 train-hidden tests 计分；两者辅助 reward 公式、Piston/verifier 路径、batch alignment 与日志 schema 相同；
- `eval_hidden_tests`、reference solution、starter code、SFT response 不进入 trainer dataset 或 training log；Public trainer row 不含 `train_hidden_tests`；
- B adapter 必须先安全加载并合并到 base weights，再由 GRPOTrainer 叠加新的 trainable GRPO LoRA；不得把 B adapter 直接作为 GRPOTrainer 的 active PEFT adapter，否则 TRL 禁用 adapter 时 reference 会退回 A/base 而不是 B；
- run/resume identity 绑定 parent SFT run/checkpoint、dataset/config/dependency/environment/seed；切换 B source、config 或 dataset 后不得错误 resume；
- GTX 1660 Ti 上 training entry 在模型加载前因 `<20 GiB` 正确 fail closed；本 stage 不执行真实 optimizer step，不产生或声称真实 C/D checkpoint、指标或成本。

### 范围内 / 范围外

- 范围内：GRPO dataset/prompt、config、公平性 guard、reward wiring、B→GRPO policy construction、run artifacts、resume、hardware guard、CLI、engineering tests/documentation。
- 范围外：真实 SFT/GRPO optimizer run；正式 C/D checkpoint/数值/成本；completed C/D checkpoint 的完整 identity/reload 与统一 C/D evaluation（后续 WP7 development stage 独立完成）；WP8 aggregation/error-analysis；修改 `third_party/open-r1/**`；升级 pinned dependency。
- fixture/mock trainer/checkpoint 只能作为 engineering evidence；不得写成正式 B/C/D evidence。

## 3. 前置条件与约束

- 不修改 `third_party/open-r1/**`；所有 Open-R1 import 仍经 `code_verifier.training.open_r1_adapter.import_open_r1_module()`。
- 使用当前 pinned `trl==0.18.0`、`transformers==4.52.3`、`accelerate==1.4.0`、`peft==0.14.0` 与项目 torch；不为“兼容新版”升级依赖或增加多版本 fallback。
- 已确认 pinned TRL `GRPOTrainer` custom reward function 接收 `prompts`, `completions`, `completion_ids` 与除 prompt/completion 外的 dataset columns；callback 必须按这个 exact contract 实现并严格验证 batch 对齐。
- 已确认 pinned TRL 在传入 `peft_config` 时会把 policy 包装为 PEFT，并在 PEFT 情况下通过禁用当前 adapter 形成 reference；因此 B adapter 不能直接作为 active GRPO adapter。
- 已确认 pinned PEFT `PeftModel.from_pretrained(model, adapter_path, is_trainable=False, ...)` 可加载 B；`merge_and_unload` 由具体 tuner/实例通过 `PeftModel.__getattr__` 委托给底层 LoRA model，不能假设 `PeftModel.merge_and_unload` 是类方法。实现必须检查实际实例上的 callable，并使用当前 pinned LoRA `merge_and_unload(..., safe_merge=True)` 行为。
- 训练 reward 必须继续经过现有 `compute_code_rewards()` → `verify_completion()` → configured `CodeExecutor`，不得在 GRPO 模块复制解析/执行/评分逻辑。
- 真实 artifacts 的默认输出必须通过现有 `CODE_VERIFIER_ARTIFACT_ROOT` 语义，config 不硬编码 `.worktrees/.../outputs`。

### Execution preflight（首次业务修改/commit 前）

1. **Stage-local 工具链与 source binding**
   - 命令：
     - `.venv/bin/python -m ruff --version`
     - `.venv/bin/python -m mypy --version`
     - `.venv/bin/python -m pytest --version`
     - 用 `.venv/bin/python` 打印 `code_verifier.__file__`、`open_r1.__file__`。
   - 通过标准：ruff/mypy/pytest 均从 stage `.venv` 启动；project/Open-R1 editable source 均解析到当前 `.worktrees/wp7-a`，不得指向 primary checkout。
2. **Pinned GRPO/PEFT API**
   - 用 `.venv/bin/python` 导入并核对 exact versions；用 `inspect.signature` / bounded introspection 确认 `trl.GRPOTrainer.__init__`、`trl.GRPOConfig`、`trl.ModelConfig`、`trl.get_peft_config`、`peft.PeftConfig.from_pretrained`、`peft.PeftModel.from_pretrained` 的当前接口，以及实际 LoRA tuner/PEFT instance 可委托调用 `merge_and_unload(safe_merge=...)`。
   - 通过标准：版本与 lock/project contract 一致；custom reward kwargs、PEFT load/merge 能满足本 plan。若不一致，停止并修正计划/实现假设，不升级依赖。
3. **Piston runtime**
   - 用项目 API 加载 `configs/execution/piston-local.yaml`，构造 `PistonExecutor` 并执行 `validate_runtime()`。
   - 通过标准：真实 loopback Piston 可达，版本/安全 probe 成功；不得用 MockExecutor 冒充生产 prerequisite。
4. **Development GPU baseline**
   - 命令：`make test-gpu`。
   - 通过标准：GTX 1660 Ti 上既有 GPU generation smoke 全绿。此 preflight 只证明 CUDA/inference baseline，不允许启动 GRPO optimizer。

任一 preflight 失败时停止本次 execution，保持 `HEAD == plan_commit`；修复环境后重新调用 execution-router，不得先提交部分业务实现。

## 4. 实施步骤

### 步骤 1：建立 GRPO 的共享 prompt 与 payload-minimal dataset

**目标文件**：
- `src/code_verifier/prompting.py`
- 新增 `src/code_verifier/training/grpo_data.py`
- `tests/unit/test_prompting.py`
- 新增 `tests/unit/training/test_grpo_data.py`

**新增 / 修改符号**：
```python
def build_code_prompt_from_fields(
    problem_statement: str,
    function_signature: str,
    visible_tests: Sequence[Mapping[str, object]],
) -> str:
    ...


class GRPODataError(ValueError):
    ...


def build_grpo_dataset(
    records: Sequence[Mapping[str, object]],
    *,
    reward_mode: str,
) -> Dataset:
    ...
```

**主要功能**：
- 把现有 `build_code_prompt(problem: CodeProblem)` 改为委托新的 field-level helper，输出字节级行为保持不变；不要复制 §7.2 模板。
- `build_grpo_dataset()` 对 `reward_mode=public|hidden` 分别调用现有 `check_training_record(..., TrainingArtifactKind.PUBLIC_GRPO|HIDDEN_GRPO)` 合同。
- WP1 GRPO artifact 的 `prompt` 是 problem statement；dataset builder 使用 `prompt + function_signature + visible_tests` 生成与 SFT/evaluation 同一 §7.2 user prompt，然后输出 conversational TRL row：`prompt=[{"role":"user","content":...}]`。
- Public trainer row 只保留 `problem_id`, `function_name`, `metadata`, `visible_tests`；Hidden 在此基础上增加 `train_hidden_tests`。`function_signature` 仅用于构造 prompt，之后从 trainer row 删除。
- 严格拒绝空/非法 UTF-8、重复 problem_id、未知 reward mode、schema/forbidden-key 错误。不得出现 `eval_hidden_tests`、reference solution、starter code、SFT response。

**测试方案**：
- `test_build_code_prompt_from_fields_matches_existing_problem_prompt`
- `test_build_grpo_dataset_public_uses_shared_prompt_and_visible_payload_only`
- `test_build_grpo_dataset_hidden_adds_only_train_hidden_reward_payload`
- `test_build_grpo_dataset_rejects_duplicate_problem_ids`
- `test_build_grpo_dataset_rejects_forbidden_or_malformed_payload`

**验证命令**：
```bash
.venv/bin/python -m pytest tests/unit/test_prompting.py tests/unit/training/test_grpo_data.py -q
```

### 步骤 2：实现 exact GRPO config 与 C/D 公平性 guard

**目标文件**：
- 新增 `src/code_verifier/training/grpo.py`
- 新增 `configs/grpo/public.yaml`
- 新增 `configs/grpo/hidden.yaml`
- 新增 `tests/unit/training/test_grpo.py`

**新增符号**：
```python
@dataclass(frozen=True)
class GRPOTrainingConfig:
    run_name: str
    reward_mode: str
    dataset_path: Path
    piston_config: Path
    num_generations: int
    max_prompt_length: int
    max_completion_length: int
    per_device_train_batch_size: int
    gradient_accumulation_steps: int
    learning_rate: float
    num_train_epochs: float
    max_steps: int
    warmup_ratio: float
    lr_scheduler_type: str
    temperature: float
    top_p: float
    beta: float
    bf16: bool
    fp16: bool
    gradient_checkpointing: bool
    lora_r: int
    lora_alpha: int
    lora_dropout: float
    logging_steps: int
    save_steps: int
    eval_steps: int
    seed: int
    min_cuda_memory_gb: float


class GRPOTrainingError(RuntimeError):
    ...


def grpo_training_config_from_mapping(value: object) -> GRPOTrainingConfig:
    ...


def load_grpo_training_config(path: Path) -> GRPOTrainingConfig:
    ...


def validate_grpo_config_pair(
    public: GRPOTrainingConfig,
    hidden: GRPOTrainingConfig,
) -> None:
    ...


def validate_grpo_artifact_pair(
    public_records: Sequence[Mapping[str, object]],
    hidden_records: Sequence[Mapping[str, object]],
) -> None:
    ...
```

**主要功能**：
- exact mapping：missing/unknown fields fail closed；严格类型、有限值、范围与安全 path 检查。
- checked-in main C/D configs采用 §12 默认：`num_generations=4`, `max_prompt_length=1024`, `max_completion_length=512`, batch=1, grad accumulation=8, lr=5e-6, epochs=1, max_steps=300, warmup=.05, cosine, temperature=.8, top_p=.95, beta=.01, bf16=true, fp16=false, gradient_checkpointing=true, logging=1, save=50, eval cadence=50, seed=42, LoRA 采用当前项目与 SFT 对齐的 r/alpha/dropout；`min_cuda_memory_gb>=20`。
- `use_vllm=False`、`report_to=[]`、`push_to_hub=False`、`trust_remote_code=False`、4/8-bit quantization disabled 作为 runtime hard invariant，不开放成 config toggle。
- config pair 只允许 `run_name`、`reward_mode`、`dataset_path` 不同；Public/Hidden 的其它实验字段必须完全相等。
- artifact pair 必须 problem_id 顺序一致，且原始 problem statement/function signature/visible tests/metadata 等共享字段一致；Hidden 只多 train-hidden reward source。

**测试方案**：exact schema/ranges；两份 checked-in config pair PASS；任一实验超参数不一致 FAIL；dataset row/order/shared field 不一致 FAIL。

### 步骤 3：实现 TRL reward callback 与 sanitized rollout/reward/group artifacts

**目标文件**：`src/code_verifier/training/grpo.py`、`tests/unit/training/test_grpo.py`

**新增符号**：
```python
def build_grpo_reward_callback(
    *,
    reward_mode: str,
    executor: CodeExecutor,
    rollout_log_path: Path,
    reward_log_path: Path,
    group_metrics_log_path: Path,
    num_generations: int,
    max_completion_length: int,
) -> Callable[..., list[float]]:
    ...
```

**主要功能**：
- 返回一个真正的 Python function/closure，并给出稳定 `__name__`，满足 pinned TRL `GRPOTrainer` 对 custom reward function name 的使用方式；不要用无 `__name__` 的 callable object。
- callback 按 pinned contract 接收 `prompts`, `completions`, `completion_ids`, `problem_id`, `function_name`, `metadata`, `visible_tests`，Hidden 额外接收 `train_hidden_tests`，并拒绝 `eval_hidden_tests` 或未预期敏感字段。
- 对所有 columns 做严格 batch alignment；禁止 `zip` 静默截断。
- Public 选择 visible tests，Hidden 选择 train-hidden tests，然后仅调用一次现有 `compute_code_rewards()` 获得 reward values + component records；不重复执行 candidate code。
- `rollouts.jsonl` 保存：稳定 item/group 索引、problem_id、reward_mode、completion、completion token count、truncated flag、total reward；不得写 tests、function_name、metadata、stdout/stderr。
- `rewards.jsonl` 保存：item/group 索引、problem_id + 现有 sanitized component record；不得写 completion/code/tests/function_name/metadata/stdout/stderr。
- 按 problem_id 分组，要求 group size 与 `num_generations` 一致；`group_metrics.jsonl` 保存 finite mean/std、all_equal flag、sample count，不保存 prompt/completion/tests。total reward 必须可由 component fields 重新求和验证。
- completion token 数使用 TRL 传入 `completion_ids`，截断标志基于 `max_completion_length`；不要二次 tokenizer 推断。

**测试方案**：Public/Hidden 只改变 test source；auxiliary components 相同；batch mismatch fail；group size mismatch fail；NaN/Inf fail；日志字段 exact/sanitized；隐藏 test marker 不出现在任何日志；component total 可复算。

### 步骤 4：实现 pinned GRPO runtime、正确的 B→GRPO policy construction 与 hardware guard

**目标文件**：`src/code_verifier/training/grpo.py`、`tests/unit/training/test_grpo.py`

**新增 / 修改符号**：
```python
@dataclass(frozen=True)
class _GRPORuntime:
    model_config_type: Any
    training_config_type: Any
    trainer_type: Any
    get_peft_config: Any
    get_tokenizer: Any
    get_model: Any
    peft_config_type: Any
    peft_model_type: Any


def validate_grpo_training_hardware(config: GRPOTrainingConfig) -> None:
    ...


def _load_grpo_runtime() -> _GRPORuntime:
    ...


def _runtime_arguments(
    config: GRPOTrainingConfig,
    *,
    checkpoint_dir: Path,
    parent_sft: SFTCheckpointIdentity,
    seed: int,
    runtime: _GRPORuntime,
) -> tuple[Any, Any]:
    ...


def _load_merged_sft_policy(
    *,
    parent_sft: SFTCheckpointIdentity,
    model_args: Any,
    training_args: Any,
    runtime: _GRPORuntime,
) -> Any:
    ...
```

**主要功能**：
- `_load_grpo_runtime()` exact-check pinned TRL/Transformers/Accelerate/PEFT versions，并通过 `import_open_r1_module()` 获取 `open_r1.configs.GRPOConfig` 与 `open_r1.utils.model_utils.get_model/get_tokenizer`；不得直接 import third_party path。
- `validate_grpo_training_hardware()` 在任何 tokenizer/model load 之前要求 CUDA、`>=max(config.min_cuda_memory_gb,20)` GiB；bf16 时要求 native BF16。错误转换为 `GRPOTrainingError`。
- `model_args` 的 model id/revision 只来自 `SFTCheckpointIdentity`；config 不能另指定模型。新 GRPO LoRA 参数来自 C/D config，nonquantized、trust_remote_code false。
- 读取 B adapter `PeftConfig`，严格校验 `base_model_name_or_path == parent_sft.model_id`，adapter revision 若 non-null 必须等于 parent SFT revision。
- 用 pinned Open-R1 `get_model()` 加载 base A；用 `PeftModel.from_pretrained(base_model, parent_sft.checkpoint_dir, is_trainable=False, config=adapter_config)` 加载 B adapter；随后检查返回实例上 `merge_and_unload` 是否 callable，并以 pinned LoRA 支持的 `safe_merge=True` 合并，得到 merged-B model。
- 将 merged-B model 传给 `GRPOTrainer(..., peft_config=runtime.get_peft_config(model_args))`。这样被 TRL 禁用的是新的 GRPO LoRA，reference policy 回到 merged B；禁止直接把未 merge 的 B PEFT model 当 active GRPO adapter。
- tokenizer 仍由 parent SFT 的 base id/revision 加载；不通过 adapter directory 启发式猜模型。

**测试方案**：全部用 fake runtime/model，不下载模型：版本/接口 fail closed；hardware guard 在 model loader 之前触发；B adapter identity mismatch fail；调用顺序为 base load → B adapter load(non-trainable) → delegated safe merge → GRPOTrainer + new LoRA；显式回归测试禁止直接 active-B-adapter 路径。

### 步骤 5：实现 GRPO run artifact、strict resume 与 trainer orchestration

**目标文件**：`src/code_verifier/training/grpo.py`、`tests/unit/training/test_grpo.py`

**新增符号**：
```python
@dataclass(frozen=True)
class GRPOTrainingSummary:
    run_dir: Path
    checkpoint_dir: Path
    reward_mode: str
    train_loss: float
    train_samples: int
    gpu_hours: float


def run_grpo_training(
    config: GRPOTrainingConfig,
    *,
    sft_run_dir: Path,
    output_root: Path,
    seed: int,
    executor: CodeExecutor,
    resume_from_checkpoint: Path | None = None,
) -> GRPOTrainingSummary:
    ...
```

**严格 run layout**：
- `resolved_config.yaml`
- `environment.json`
- `run.json`
- `metrics.jsonl`
- `rollouts.jsonl`
- `rewards.jsonl`
- `group_metrics.jsonl`
- `stdout.log`
- `stderr.log`
- `checkpoints/`

**主要功能**：
- 第一顺序：seed/config → hardware guard → `load_completed_sft_checkpoint(sft_run_dir)` → dataset/runtime/model。不得在 hardware guard 前加载大模型。
- 根据 reward mode 使用现有 `load_training_artifact()` 加载 PUBLIC/HIDDEN_GRPO，并构建步骤 1 dataset。
- `run.json` 只保存 non-sensitive identity：run/reward mode、git/open-r1/dependency/python/torch/cuda/GPU、dataset/config hashes、seed、parent SFT run_id/model id/revision/dataset/config/dependency hashes、resolved parent run/checkpoint path、status/start/end/gpu_hours/resume source/command。不得保存训练题文本或 tests。
- trainer 使用步骤 4 merged-B policy + new GRPO LoRA、步骤 3 reward callback；`do_eval=False` / `eval_strategy="no"`，本 stage 不把 eval-hidden 接入 Trainer。config 的 checkpoint-evaluation cadence 只作为冻结实验定义/后续外部统一评测 cadence 记录，不在训练 dataloader 中创建 eval-hidden split。
- fake/real runtime 合同均要求 `trainer.train(resume_from_checkpoint=...)`；train result 必须给出 finite train_loss；保存 trainer state 与最终 adapter 到 run `checkpoints/`；将 `trainer.state.log_history` 中 finite scalar training metrics规范化追加到 `metrics.jsonl`，并记录 train_samples/attempt_gpu_hours/cumulative gpu_hours。
- 异常时 run status 写 `failed`、累计时间保留、stderr 仅写异常类型；不得把异常 payload/test/completion 写入 stderr artifact。
- resume 只接受当前 run `checkpoints/checkpoint-N` 直接子目录；existing run 必须是 running/failed；parent SFT identity、dataset hash、config hash、dependency/environment/seed/reward mode 全部 exact-match；日志 append，不覆盖历史。

**测试方案**：fake trainer 完成/失败/resume；切换 parent B/config/data/seed/dependency 后 resume fail；checkpoint 跨 run/非法 path fail；artifact exact layout；run/environment/resolved config/logs 均无 forbidden payload；finite train_loss enforced。

### 步骤 6：接入 exports、CLI 与 checked-in Public/Hidden configs

**目标文件**：
- `src/code_verifier/training/__init__.py`
- `src/code_verifier/cli.py`
- `configs/grpo/public.yaml`
- `configs/grpo/hidden.yaml`
- `tests/unit/test_cli.py`

**修改 / 新增符号**：
```python
def _train_grpo(args: argparse.Namespace) -> int:
    ...


def build_parser() -> argparse.ArgumentParser:
    ...
```

**CLI 合同**：
```text
code-verifier train-grpo \
  --config <configs/grpo/public.yaml|hidden.yaml> \
  --sft-run-dir <completed-sft-run> \
  [--resume-from-checkpoint <run/checkpoints/checkpoint-N>] \
  [--seed N] \
  [--output-dir <root>]
```

- `--sft-run-dir` required；不提供 `--model-id` 或任意 adapter path shortcut。
- `--output-dir` 未给时使用现有 `_default_artifact_output("grpo")`，因此尊重 `CODE_VERIFIER_ARTIFACT_ROOT`。
- CLI 先加载 config/Piston config，构造 `PistonExecutor` 并 `validate_runtime()`，再调用 `run_grpo_training()`；TRAINING_ERRORS 纳入 `GRPODataError/GRPOTrainingError`。
- seed override 与 SFT 一样显式打印 non-sensitive override；stdout 只打印 samples/loss/run_dir/checkpoint_dir/reward_mode。
- `build_parser()` 文档更新到 WP7-a，并增加 `train-grpo --help`。

**测试方案**：parser required fields/default artifact root；Public/Hidden config；SFT run binding；resume forwarding；Piston/runtime error code=2；不得通过 CLI 绕过 completed SFT identity。

### 步骤 7：端到端 engineering integration、文档与全量验收

**目标文件**：
- 新增 `tests/integration/test_wp7a_grpo_integration.py`
- `README.md`
- `AGENTS.md`

**integration tests**：
- `test_wp7a_public_and_hidden_configs_match_except_reward_source`
- `test_wp7a_grpo_dataset_uses_shared_prompt_and_payload_boundaries`
- `test_wp7a_public_reward_scores_only_visible_tests`
- `test_wp7a_hidden_reward_scores_only_train_hidden_tests`
- `test_wp7a_c_and_d_bind_the_same_completed_sft_identity`
- `test_wp7a_sft_adapter_is_merged_before_new_grpo_lora`
- `test_wp7a_rollout_reward_group_artifacts_are_sanitized_and_recomputable`
- `test_wp7a_resume_requires_same_parent_sft_config_data_and_checkpoint`
- `test_wp7a_hardware_guard_fails_before_model_loading_on_1660`

**integration 方法**：
- 使用 deterministic PUBLIC/HIDDEN_GRPO fixture、completed SFT fixture、Fake runtime/Fake trainer；只在 reward/verifier integration 需要执行代码时注入受控 executor，生产 CLI 仍绑定 real Piston。
- fake trainer 必须触发真实 production callback/artifact/resume 代码，但不得调用 optimizer，不得把 fixture 结果标记为 C/D checkpoint。
- 实机 1660 Ti hardware-guard test 只证明 train entry 在 model load 前 fail closed；不要通过降低 `min_cuda_memory_gb` 绕过 guard。

**README/AGENTS 最小更新**：
- 增加 `train-grpo` 命令形态、Public/Hidden config、completed B source 要求、`CODE_VERIFIER_ARTIFACT_ROOT`；
- 明确 GTX 1660 Ti 仅做 API/engineering tests，真实 GRPO 仍锁定到 Development Complete Record 后的 24GB validation；
- 记录核心 invariant：C/D 同 B、仅 reward source 不同、B 必须 merge 后再创建 GRPO LoRA、training artifacts/logs 不得泄漏 eval hidden；
- 明确 WP7-a 没有产生正式 C/D，也尚未完成 C/D checkpoint reload/unified evaluation。

**全量验证命令**：
```bash
.venv/bin/python -m pytest \
  tests/unit/test_prompting.py \
  tests/unit/training/test_grpo_data.py \
  tests/unit/training/test_grpo.py \
  tests/unit/test_cli.py \
  tests/integration/test_wp7a_grpo_integration.py -q
.venv/bin/code-verifier train-grpo --help
make lint
make test
make test-gpu
```

通过标准：focused 全绿；CLI help=0；lint 全绿；default suite 0 failed（只允许项目既有显式 real-Piston opt-in skips）；1660 Ti GPU smoke 全绿；GRPO hardware guard 的真实机判定在 model load 前拒绝 6GB；没有 optimizer-based GRPO、没有正式 C/D artifact/metric/cost。

本 stage 不修改 execution/Piston 实现，因此 `make test-piston` 不是 WP7-a 的新增 merge gate；terminal development closeout 仍必须单独取得 real `make test-piston` 0 failed / 0 skipped。Execution preflight 已要求 Piston service 可达，确保生产 reward dependency 在实施前已知可用。

## 5. 总体验收与测试计划

- **Unit**：prompt field helper、GRPO schema/data、config/pair fairness、reward callback alignment/components/log sanitization、pinned runtime、B merge/new LoRA、artifact/resume、CLI。
- **Development integration**：fixture completed B + fake pinned runtime/trainer 贯通 `SFT identity → merged B → new GRPO LoRA → dataset → reward callback → artifact → resume`；使用真实项目 reward/verifier contracts，不执行 optimizer。
- **C/D fairness**：checked-in config pair + artifact pair + integration assertions共同保证除 reward source 与必要 run bookkeeping 外相同；两次 run metadata 都绑定同一种 completed SFT identity contract。
- **Leakage/security**：Public 无 train/eval hidden，Hidden 无 eval hidden；训练日志不保存 test payload；reward 继续经过 CodeExecutor/Piston boundary；不出现 host exec/eval。
- **Artifacts**：rollout 可保存 completion 作为训练 evidence，但 reward/group/run/config/environment/stdout/stderr 不保存 hidden tests 或完整敏感 payload；component total 可复算。
- **Hardware**：1660 Ti 仅进行 GPU smoke 与 fail-closed guard，不真实训练。
- **Deferred WP7 development**：completed C/D checkpoint identity、从 merged B + C/D adapter 的独立 reload、统一 evaluator/aggregator 接入与 fixture reload/resume evidence 在后续 WP7 stage 完成；真实 C/D optimizer/checkpoint/数值仍属于 24GB validation。

最终标准：
- [ ] §7.2 shared prompt 无复制/漂移
- [ ] Public/Hidden dataset/reward leakage boundary 严格成立
- [ ] C/D config 仅允许指定差异，pair validator 能捕获 drift
- [ ] custom reward callback 与 pinned TRL 0.18.0 exact contract 匹配且 batch 不静默截断
- [ ] B adapter identity 严格校验，并先安全 merge 后再创建 GRPO LoRA；reference semantics 为 B 而非 A
- [ ] rollout/reward/group metrics artifacts 可检查、有限、可复算且 sanitized
- [ ] strict run/resume identity 绑定 parent B/data/config/deps/env/seed
- [ ] `train-grpo` 默认使用 persistent artifact-root semantics
- [ ] 1660 Ti 在模型加载前 fail closed，不发生 optimizer step
- [ ] `make lint` / `make test` / `make test-gpu` 全绿
- [ ] 未修改 `third_party/open-r1/**`，未升级 pinned dependencies
- [ ] 没有伪造 C/D checkpoint/研究数值/成本

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
    - "数据/reward wiring 与 runtime/artifact control-plane 在文件层面部分可分，但最终必须围绕 pinned TRL custom-reward kwargs、同一 dataset schema 和同一 run artifact identity 精确对接。"
    - "B PEFT adapter 必须先 merge 再创建新的 GRPO LoRA，且 strict resume / sanitized logging 都依赖这一统一初始化合同；这些高风险 public-API 语义需要串行验证和集中 fake-runtime 调试，MULTI 的接口协调成本高于收益。"
  workstream_candidates: []
```

## 7. 风险与注意事项

- **最高风险：B reference policy 语义。** pinned TRL 对 PEFT policy 会通过 disable current adapter 得到 reference；若直接把 B adapter 当 active adapter，会把 reference 错误变回 A。必须严格实现 `base A → load B adapter read-only → delegated safe merge → new GRPO LoRA`。
- **PEFT API 不能按类名臆造。** 当前 `PeftModel`/`PeftModelForCausalLM` 类本身不声明 `merge_and_unload`；该方法通过实例 `__getattr__` 委托到底层 LoRA tuner。实现和测试必须验证实际 instance callable，不写不存在的 static/class method contract。
- **TRL reward kwargs/order 是 pinned 语义。** 不要假设未来版本行为；strict-check columns 和 batch lengths，不用 `zip` 截断。
- **不要把 eval cadence 误变成 trainer hidden-eval。** WP7-a trainer 不加载 eval hidden；后续 C/D checkpoint unified evaluation 仍走已有 deterministic evaluator。
- **日志边界不同于 reward component。** `rollouts.jsonl` 可以保存 completion 作为 rollout evidence；`rewards.jsonl` 只保存 sanitized component record，group/run/config/environment 不得复制 completion/test payload。
- **不扩张 runtime 选项。** 本 stage 不引入 vLLM、W&B、Hub push、quantization、多 backend/factory/plugin 层；先完成最小可工作的 pinned TRL vertical slice。
- **fixture 只能证明工程合同。** fake trainer 的 `save_model()` 产物不得命名/记录为正式 C/D 或用于研究结果。

## 8. 关联文档索引

- `PROJECT_SPEC_Open-R1_CodeVerifier.md`：§7.2 prompt；§7.4 leakage；§10 reward；§12 GRPO；§19.2 development/validation split；§20.0 scheduling；WP7；§21.4 Reward Review；§29 defaults
- `proceedings.md`：2026-08-13 development-first / lifecycle hardening；2026-08-14 WP6-c finalized 与 WP6 development 聚合状态
- `src/code_verifier/training/sft.py`：completed B identity、pinned runtime/hardware/artifact/resume patterns
- `src/code_verifier/training/open_r1_adapter.py`：唯一 Open-R1 import boundary
- `src/code_verifier/data/leakage_checks.py`：PUBLIC_GRPO / HIDDEN_GRPO exact training artifact schema
- `src/code_verifier/rewards/common.py`：必须复用的 verifier-backed reward core/component records
- `src/code_verifier/cli.py`：persistent artifact-root 与 SFT CLI pattern
- pinned read-only `third_party/open-r1/src/open_r1/grpo.py` / `utils/model_utils.py`：仅作为当前 runtime contract 参考，不修改

## 9. Legacy recovery provenance 与收紧合同

本 plan 是 2026-08-14 workflow transport-state 修复后的受控重封存。旧 stage 完整保存在 `archive/wp7-a-legacy-20260814-160709`，archive HEAD 为 `2a96f157b5f28258614c973f36599e87806ee593`；其中旧 plan/review/execution 只作为历史审计证据，**不得**作为新 baseline 的 provenance 继续使用。新 stage 必须从 `main@0e836995eb2bb05c6cec78aa8e6d056573c9589c` 重新形成 plan seal、implementation execution record 和独立 review。

恢复时只移植 archive 中的业务 code/test/config/docs 变更；不得移植 `.ai-bridge/**`、旧 `ai-work/executor/WP7-a-executor.md` 或旧 `ai-work/reviewer/WP7-a-review.md`。`.ai-bridge/**` 只能作为 ignored/untracked local transport state，任何 staged/committed path 都不得包含它。

旧 R1/R2 已证明并要求保留的两项收紧合同成为本次 recovered implementation 的显式验收要求：

1. **C/D production fairness preflight**：production `run_grpo_training()` / `train-grpo` 必须在任一 selected run 创建 output 或加载 trainer runtime 前同时消费 Public/Hidden config、两份 completed-SFT B definition 与 ordered artifact pair；复用 config/artifact pair validator，并 fail closed 于 config drift、不同 completed B identity 或 artifact drift。CLI 必须显式绑定 Public/Hidden definitions 和 selected `reward_mode`，不能退回两个彼此独立的单-run invocation contract。
2. **Pinned TRL cross-field fail-closed**：project config boundary 必须要求 `num_generations >= 2`，并对当前 frozen single-GPU effective generation batch 执行整除约束；pinned model/training argument constructor 的 `ValueError` 必须归一化为 `GRPOTrainingError`。测试至少覆盖 `num_generations=1`、不兼容的 `3`、有效的 `4`，以及 constructor error normalization。

恢复 execution 可以复用 archive 的已审查业务实现作为迁移源，但必须在新 stage 环境下重新运行 Execution preflight、focused WP7-a suite、CLI help、`make lint`、`make test`、`make test-gpu` 和针对上述两项合同的直接 fail-closed 检查；全部通过后才可写新的 completed E0。旧 R2 PASS 不自动继承到新 stage。

## 10. Handoff

- 本次 legacy recovery 已由 control-plane 从 `main@0e836995eb2bb05c6cec78aa8e6d056573c9589c` 建立 `feat/wp7-a` + `.worktrees/wp7-a` 并完成 stage-local environment overlay；本文件提交后形成新的唯一 `plan_commit`。
- plan seal 成功并得到新 `plan_commit` 后，才进入 recovered implementation execution。
- 旧 archive branch 只读保留，不参与新 stage merge。

## Implementation contract

- Work from this plan in small, reviewable steps.
- Keep edits scoped to the requested task and existing project conventions.
- Run focused verification before handing work back.
- `.ai-bridge/**` may be used only as ignored local transport/status state; never stage or commit it.
- If local transport status/diff/log files are updated, keep them outside repository provenance and verify `git ls-files .ai-bridge` remains empty before every commit.
