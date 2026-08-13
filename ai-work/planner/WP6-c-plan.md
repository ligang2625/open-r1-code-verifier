# WP6-c 实施计划（SFT checkpoint 重载与 B 组统一评测开发）

## 1. 元信息

| 项 | 值 |
|---|---|
| stage_id | `WP6-c` |
| stage_profile | `development` |
| target_hardware | `GTX 1660 Ti (6GB)` |
| evidence_class | `engineering` |
| development_terminal | `false` |
| 目标 WP | `WP6`：SFT 集成的 development acceptance 收口 |
| 规格依据 | `PROJECT_SPEC_Open-R1_CodeVerifier.md` §19.2.1、§20.0、WP6（§1780–1810）、§21、§29 |
| 前置状态 | `WP6-a` 已 finalized；原 WP6-b / WP6-c 未完成历史均已退役到 archive，未进入 `main`。当前仍缺 completed-run/checkpoint identity、PEFT reload 与 B 组统一评测接入的 finalized development evidence。 |
| `planning_base_commit` | `d7c215b4e7aec11c4ace6b3edca273c2508fa921` |
| proposed branch | `feat/wp6-c` |
| proposed worktree | `.worktrees/wp6-c` |
| final plan path | `ai-work/planner/WP6-c-plan.md` |
| execution report path | `ai-work/executor/WP6-c-executor.md` |
| review path | `ai-work/reviewer/WP6-c-review.md` |
| plan lifecycle | planner-ex handoff → `stage-lifecycle bootstrap_plan` → committed plan seal |

## 2. 目标与范围

### 目标（规格原文）

完成 WP6 development acceptance 中尚未进入 `main` 的部分：completed-run/checkpoint identity、PEFT reload 与 B 组统一评测接入必须可通过 fixture/fake runtime 验证；Base 与 SFT 评测共用同一 evaluator/aggregator contract；hidden/reference payload 不泄漏；不要求真实 SFT checkpoint、loss 或 B 数值。

### 交付（规格对应）

- 一个严格、只接受 `status=completed` SFT run 的 checkpoint identity loader；
- 基于 pinned Transformers + PEFT 的只读 LoRA adapter 重载路径；
- `code-verifier evaluate` 对 completed SFT run 的显式输入方式，继续复用现有 `run_pass1_evaluation()` 与 `aggregate_evaluation_run()`；
- fixture/fake runtime 的 unit/integration evidence，证明 checkpoint identity、base-model/adapter 匹配、B 组评测 artifact/resume contract 正确；
- README/AGENTS 中与该新入口直接相关的最小使用与安全约束。

### 验收（规格对应）

- completed-run/checkpoint identity、PEFT reload 与 B 组统一评测接入均有可判定工程测试；
- Base 与 B 组不复制 evaluator/aggregator，不改变 deterministic Pass@1、三层 visible → train-hidden → eval-hidden 验证顺序、聚合/Bootstrap 口径；
- B 组 evaluation run 的 `model_id`、`model_revision`、`checkpoint`、config hash 与 exact-prefix resume 均绑定实际选择的 completed SFT checkpoint；
- 非 completed SFT run、缺失/非法 adapter、adapter/base identity 不一致必须 fail closed；
- 不加载/序列化 hidden tests、reference solution、SFT response 到 evaluation prompt 或非 `samples/results.jsonl` artifact；
- 不执行 optimizer-based SFT，不产生或冒充正式 B checkpoint/指标/成本。

### 范围内 / 范围外

- 范围内：WP6 checkpoint identity、PEFT inference reload、evaluation CLI binding、严格 resume identity、unit/integration、必要文档。
- 范围外：真实 SFT；24GB GPU validation；真实 B checkpoint 与 B 数值；WP7 GRPO；WP8 A–D 最终分析；修改 `third_party/open-r1/`；升级 pinned 依赖。
- 原 `archive/wp6-b-blocked-20260810` 与 `archive/wp6-c-incomplete-20260813-192343` 只可作为审计/思路参考，不得 cherry-pick blocked execution report 或把 archive commit 当 completed evidence；实现以当前 `main` 与本 plan 为唯一基线。

## 3. 前置条件与约束

- `WP6-a` 的 SFT artifact/run layout、训练 hardware guard、pinned runtime 与 visible-only 数据边界保持不变。
- 不修改 `third_party/open-r1/`；Open-R1 training 访问仍仅经 `code_verifier.training.open_r1_adapter`。本 stage 的 PEFT inference reload 使用项目已固定的 `peft==0.14.0` / `transformers==4.52.3` public API，不复制或修改上游源码。
- 不新增 compatibility shim、legacy fallback 或自动猜测“某目录是不是 adapter”；checkpoint 来源必须由显式 SFT run 参数选择并经过严格 identity loader。
- B 组必须继续调用现有 `run_pass1_evaluation()` 与 `aggregate_evaluation_run()`；不得新建第二套 evaluator、第二套结果 schema 或第二套指标口径。
- 若 pinned PEFT 0.14.0 的实际 public API/adapter layout 与预期不同，以 execution preflight 的本地 introspection 为准；只针对当前 pinned version 实现，不加多版本兼容层。

### Execution preflight（首次业务修改/commit 前）

1. **Stage-local 工具链完整性**
   - 命令：
     - `.venv/bin/python -m ruff --version`
     - `.venv/bin/python -m mypy --version`
     - `.venv/bin/python -m pytest --version`
   - 通过标准：三者均从当前 stage `.venv` 成功启动；`ruff` 不再依赖 primary `.venv/bin/ruff` 路径。
2. **Pinned training/inference API**
   - 命令：使用 `.venv/bin/python` 导入 `peft`, `transformers`, `torch`，核对 `peft==0.14.0`、`transformers==4.52.3`、项目 pinned torch；用 `inspect.signature` 确认 `PeftConfig.from_pretrained` 与 `PeftModel.from_pretrained` 可接受本地 adapter path，且 `PeftModel.from_pretrained` 支持只读 inference 所需参数。
   - 通过标准：版本与当前 lock/project contract 一致，所需 public API 存在；若不一致，停止，不升级依赖、不修改 lockfile 来“适配最新版本”。
3. **现有 CUDA/cache 基线**
   - 命令：`make test-gpu`
   - 通过标准：GTX 1660 Ti 上现有 GPU smoke 全绿；若仅因 CUDA/runtime/model cache 等外部环境问题失败，保持 `HEAD == plan_commit`，先修复环境再重新调用 execution-router。
4. **Source binding**
   - 命令：用 `.venv/bin/python` 打印并断言 `code_verifier.__file__` 与 `open_r1.__file__` 均位于当前 `.worktrees/wp6-c` 下。
   - 通过标准：不得指向 primary checkout。

preflight 失败时不得先提交业务修改。若环境故障发生在已有有效业务 commits 之后，则按当前 environment-interrupted execution contract 记录可恢复 checkpoint；用户修复环境后可显式 `$execution-router resume`，不要求自动退役 stage。

## 4. 实施步骤

### 步骤 1：增加 completed SFT checkpoint identity loader

**目标文件**：`src/code_verifier/training/sft.py`、`tests/unit/training/test_sft.py`

**新增符号**：
```python
@dataclass(frozen=True)
class SFTCheckpointIdentity:
    run_dir: Path
    checkpoint_dir: Path
    run_id: str
    model_id: str
    model_revision: str | None
    dataset_hash: str
    config_hash: str
    dependency_lock_hash: str
    seed: int


def load_completed_sft_checkpoint(run_dir: Path) -> SFTCheckpointIdentity:
    ...
```

**主要功能**：
- `run_dir` 必须是可解析的真实目录，并符合 WP6-a 的 SFT run layout；读取 `run.json`，只接受 `status == "completed"`。
- 严格解析上述 identity 字段的类型/非空/有限性；`seed` 必须为整数；hash/ID 不得缺失。
- `checkpoint_dir` 固定为该 run 的直接 `checkpoints/` 目录，不接受用户传入任意子目录或跨 run 路径。
- 使用 execution preflight 已确认的 pinned PEFT adapter layout 判定最终 adapter artifact 是否完整；只实现当前 pinned contract，不加多格式猜测 fallback。
- 该 loader 只返回 non-sensitive identity，不读取训练数据内容，不把 dataset payload、hidden/reference 字段带入返回值。

**测试方案**：
- `test_load_completed_sft_checkpoint_accepts_completed_run`
- `test_load_completed_sft_checkpoint_rejects_non_completed_status`
- `test_load_completed_sft_checkpoint_rejects_missing_or_invalid_identity`
- `test_load_completed_sft_checkpoint_rejects_missing_or_invalid_adapter_artifact`
- `test_load_completed_sft_checkpoint_binds_checkpoint_to_same_run`

**验证命令与通过标准**：
```bash
.venv/bin/python -m pytest tests/unit/training/test_sft.py -q
```
全部通过；既有 SFT config/train/resume tests 无回归。

### 步骤 2：增加严格 PEFT checkpoint inference reload

**目标文件**：`src/code_verifier/evaluation/generate.py`、`tests/unit/evaluation/test_generate.py`

**新增 / 修改符号**：
```python
class TransformersCompletionGenerator:
    @classmethod
    def from_peft_checkpoint(
        cls,
        *,
        base_model_id: str,
        base_model_revision: str | None,
        adapter_dir: Path,
        device: str,
        config: GenerationConfig,
        local_files_only: bool = False,
    ) -> "TransformersCompletionGenerator":
        ...
```

必要时只提取一个最小 private helper，让 `from_pretrained()` 与 `from_peft_checkpoint()` 共享完全相同的 base tokenizer/model safe-loading 逻辑；不要引入 registry/factory 层。

**主要功能**：
- base tokenizer/model 仍通过 `AutoTokenizer` / `AutoModelForCausalLM` 加载，保持 `trust_remote_code=False`、既有 dtype/device/local-files-only 语义。
- adapter 通过 pinned PEFT public API 以 inference-only 方式加载到 base model；完成后 `eval()`，不创建 optimizer/trainer。
- 读取 adapter config 的 base-model identity，并与 `base_model_id`（以及 pinned API 可稳定提供时的 revision）做 fail-closed 一致性校验；不允许 silent mismatch。
- adapter/runtime 错误转换为 `GenerationError`，错误消息仅报告类别/合同，不输出敏感 payload。
- 不改变 `generate()`、prompt、deterministic decoding 或 result schema。

**测试方案**：使用 fake Transformers/PEFT runtime，不下载模型、不真实占用 GPU。
- `test_from_peft_checkpoint_loads_base_then_adapter_with_safe_options`
- `test_from_peft_checkpoint_rejects_base_model_identity_mismatch`
- `test_from_peft_checkpoint_preserves_dtype_device_and_local_only_contract`
- `test_from_peft_checkpoint_wraps_runtime_failure_without_payload`
- 既有 `from_pretrained` tests 必须继续证明 Base 路径行为不变。

**验证命令与通过标准**：
```bash
.venv/bin/python -m pytest tests/unit/evaluation/test_generate.py -q
```
全部通过。

### 步骤 3：把 completed SFT run 显式接入现有 evaluate CLI

**目标文件**：`src/code_verifier/cli.py`、`tests/unit/test_cli.py`

**修改符号**：
```python
def _evaluate(args: argparse.Namespace) -> int:
    ...


def build_parser() -> argparse.ArgumentParser:
    ...
```

**CLI 变更**：
- `evaluate` 的模型来源改为显式互斥二选一：
  - `--model-id <base-model-or-checkpoint-id>`：保留现有 Base 路径；
  - `--sft-run-dir <completed-sft-run>`：新增 B 组路径。
- 不允许同时提供，也不允许都缺失；不通过目录启发式自动判断 PEFT。

**主要功能**：
- Base 路径维持当前行为。
- SFT 路径调用 `load_completed_sft_checkpoint()`；以其 `model_id/model_revision/checkpoint_dir` 构造 `TransformersCompletionGenerator.from_peft_checkpoint()`。
- 对 B 路径只在内存中派生本次有效 `EvaluationConfig`：保持 dataset/split/Piston/device/generation 完全不变，仅把 `model_revision` 绑定到训练 run identity，把 `checkpoint` 绑定到实际 resolved completed SFT checkpoint path；随后继续调用原有 `run_pass1_evaluation()` 和 `aggregate_evaluation_run()`。
- `model_id` 仍记录 base model identity；`checkpoint` 唯一标识实际 B adapter checkpoint。由现有 `evaluation_config_hash()`、run metadata 与 exact-prefix resume 自动把 B checkpoint 纳入 identity。
- 不新增 B 专用 evaluator/aggregator/config schema。

**测试方案**：
- `test_evaluate_parser_requires_exactly_one_model_source`
- `test_evaluate_base_model_path_remains_unchanged`
- `test_evaluate_sft_run_binds_completed_checkpoint_identity`
- `test_evaluate_sft_run_reuses_existing_evaluator_and_aggregator`
- `test_evaluate_sft_run_rejects_incomplete_checkpoint_before_generation`

**验证命令与通过标准**：
```bash
.venv/bin/python -m pytest tests/unit/test_cli.py -q
.venv/bin/code-verifier evaluate --help
```
parser/help 正确；Base 现有调用合同不回归。

### 步骤 4：补 B 组统一评测 integration contract

**目标文件**：新增 `tests/integration/test_wp6c_sft_checkpoint_evaluation.py`；必要时复用已有 `tests/fixtures/` helper/data，但不要复制 prepared-data/evaluator 实现。

**主要功能**：
- 构造最小、确定性的 completed SFT run fixture 与 fake PEFT/Transformers runtime；fake adapter 只能作为 engineering evidence，必须在测试命名/断言中明确不是正式 B checkpoint。
- 从 `--sft-run-dir` 或等价直接调用路径贯通：completed-run identity → PEFT reload → 现有 pass@1 evaluator → existing aggregator。
- 验证生成的 `run.json`、`resolved_config.yaml`、`samples/results.jsonl`、`summary.json` / `main_results.csv` 延续 WP5 schema；B checkpoint identity 被记录且 aggregation 可读。
- 验证 exact-prefix resume：同一 B identity 可以恢复，换另一个 checkpoint/run identity 必须拒绝。
- 验证 prompt 仍只包含题面/函数签名/visible examples；非 samples artifacts 不出现 completion/code/test payload；SFT run metadata 不把 training dataset payload带入 evaluation artifacts。

**测试函数**：
- `test_wp6c_completed_sft_checkpoint_runs_through_existing_evaluator`
- `test_wp6c_b_evaluation_resume_is_bound_to_checkpoint_identity`
- `test_wp6c_b_evaluation_artifacts_preserve_payload_boundaries`
- `test_wp6c_fixture_checkpoint_is_never_reported_as_real_training_evidence`

**验证命令与通过标准**：
```bash
.venv/bin/python -m pytest tests/integration/test_wp6c_sft_checkpoint_evaluation.py -q
```
0 failed；测试无需真实 optimizer step、24GB GPU 或网络模型下载。

### 步骤 5：更新最小文档与 agent 约束

**目标文件**：`README.md`、`AGENTS.md`

**主要功能**：
- README 增加 B 组 development/validation 使用边界：development 可用 completed-run fixture/fake runtime 验证 CLI/reload contract；真实 `--sft-run-dir` 只有在 4090 validation 产生真实 completed SFT run 后才形成正式 B evidence。
- 给出 `evaluate --sft-run-dir ...` 的命令形态，并明确仍使用同一 eval config/aggregator；不声称当前已经有真实 B checkpoint。
- AGENTS 增加最小 invariant：B evaluation 必须来自 `load_completed_sft_checkpoint()` 验证过的 completed run；不得跳过 base/adapter identity check，不得把 fixture checkpoint 记录成正式 B。

**验证命令与通过标准**：
```bash
.venv/bin/code-verifier evaluate --help
```
文档与 CLI 参数一致，无旧 WP6-b validation-heavy 流程残留。

### 步骤 6：全量工程验收

按顺序运行：
```bash
.venv/bin/python -m pytest tests/unit/training/test_sft.py tests/unit/evaluation/test_generate.py tests/unit/test_cli.py tests/integration/test_wp6c_sft_checkpoint_evaluation.py -q
make lint
make test
make test-gpu
```

通过标准：
- focused tests 全绿；
- `make lint` 全绿；
- `make test` 0 failed，允许仅项目既有“需显式启用 real Piston”的 skips；
- GTX 1660 Ti 上 `make test-gpu` 真实 GPU smoke 全绿；
- 不运行 `train-sft` optimizer step，不产生真实 B checkpoint/metric/cost。

`make test-piston` 不是本非 terminal WP6-c 的新增强制 gate，除非本 stage 实际修改 execution/Piston 路径；terminal development closeout 仍会单独要求 real Piston 0 failed/0 skipped。

## 5. 总体验收与测试计划

- **单元测试**：completed SFT identity parsing/fail-closed、PEFT loader safe options/mismatch、CLI exclusivity/binding、Base regression。
- **Development integration**：completed SFT fixture + fake PEFT/Transformers runtime 贯通真实 production contracts；现有 GTX 1660 Ti `make test-gpu` 继续证明 Base inference/CUDA 基线。fixture 绝不登记为 B checkpoint。
- **Evaluator consistency**：A/B 都必须经过现有 `run_pass1_evaluation()` + `aggregate_evaluation_run()`；不得复制 generation/evaluation/metrics 模块。
- **Resume/reproducibility**：B 的 model/checkpoint/revision/config hash 进入现有 run identity；切换 checkpoint 后旧 run 不可被错误 resume。
- **数据泄漏/安全**：B prompt 不含 train/eval hidden、reference solution、SFT response；除 `samples/results.jsonl` 外不得持久化 completion/code/test payload；checkpoint identity metadata 不含训练样本正文。
- **Real training/numerical gate**：本 stage 明确不执行。真实 SFT smoke/checkpoint reload/B 数值与成本继续 deferred 到 Development Complete Record 后的 24GB validation track。

最终标准：
- [ ] WP6 development acceptance 的 completed-run/checkpoint identity、PEFT reload、B 组统一评测接入均有 finalized-quality engineering evidence
- [ ] Base evaluation 行为无回归
- [ ] `make lint` 全绿
- [ ] `make test` 全绿（仅既有显式 Piston skips 可存在）
- [ ] `make test-gpu` 在 GTX 1660 Ti 全绿
- [ ] 没有真实训练、没有伪造 B checkpoint/指标/成本
- [ ] 未修改 `third_party/open-r1/`，未升级 pinned dependency contract

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
    - "checkpoint identity API 是 PEFT reload 的前置，CLI/integration 又依赖二者，公共接口与测试证据存在明显串行依赖。"
    - "范围虽跨 training/evaluation/CLI/tests，但实现是一个单一端到端能力；拆成 MULTI 会增加接口协调与重复 fake-runtime 测试成本，净收益低。"
  workstream_candidates: []
```

## 7. 风险与注意事项

- 最大技术风险是 pinned PEFT 0.14.0 对 adapter config / base model identity / `from_pretrained` 参数的实际行为；必须先 introspect 本地 pinned API，再实现当前版本的最小合同，不写多版本 fallback。
- 不要让 `checkpoint` 退化成固定字符串 `sft`/`B`；它必须绑定实际 completed run 的 resolved checkpoint identity，否则 exact-prefix resume 与结果审查无法证明 checkpoint selection 一致。
- 不要让 `--sft-run-dir` 改变评测数据、generation 参数、Piston、三层测试顺序或 aggregator；B 与 Base 的差异只能是被加载的模型/checkpoint identity。
- fake/fixture checkpoint 只用于 development contract test；execution report 与 review 必须明确它不是真实 B checkpoint，也不得报告任何研究数值。
- 若环境工具（ruff/mypy/pytest、CUDA/cache、PEFT installation）在业务修改前损坏，修复环境后直接重新 dispatch；若已有 commits 后发生纯环境故障，按当前 resumable environment checkpoint contract 处理，不因环境问题强制 retire。

## 8. 关联文档索引

- `PROJECT_SPEC_Open-R1_CodeVerifier.md`：§19.2.1 Development integration；§20.0 Development-first；WP6；§21.1/21.5 Review；§29 默认决策
- `proceedings.md`：WP6-a finalized；2026-08-13 development-first 决策；WP6-b blocked retirement；WP6-c incomplete retirement record
- `src/code_verifier/training/sft.py`：现有 WP6-a run/checkpoint layout
- `src/code_verifier/evaluation/generate.py`：现有 Base Transformers generator
- `src/code_verifier/evaluation/evaluate.py` / `metrics.py`：必须复用的统一 evaluator/aggregator contract

## 9. Handoff

- 下一步：运行 `$stage-lifecycle bootstrap_plan`，由 lifecycle 使用本计划创建 `.worktrees/wp6-c`、建立 stage-local overlay `.venv` 并 commit `ai-work/planner/WP6-c-plan.md` plan seal。
- bootstrap 成功并返回 `plan_commit` 前，不得调用 execution-router。
- 本轮 planner 不创建 branch/worktree、不 commit、不执行实现或测试。

## Implementation contract

- Work from this plan in small, reviewable steps.
- Keep edits scoped to the requested task and existing project conventions.
- Run focused verification before handing work back.
- Update .ai-bridge/agent-status.md with files touched, checks run, results, blockers, and review notes.
- Save the final review diff to .ai-bridge/implementation-diff.patch when practical.
- Append notable execution events to .ai-bridge/execution-log.jsonl when the implementation agent supports logging.
