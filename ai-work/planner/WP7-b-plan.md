# WP7-b 实施计划（GRPO checkpoint 重载与 C/D 统一评测开发）

## 1. 元信息

| 项 | 值 |
|---|---|
| stage_id | `WP7-b` |
| stage_profile | `development` |
| target_hardware | `GTX 1660 Ti (6GB)` |
| evidence_class | `engineering` |
| development_terminal | `false` |
| 目标 WP | `WP7`：GRPO integration 的 development acceptance 收口 |
| 规格依据 | `PROJECT_SPEC_Open-R1_CodeVerifier.md` §19.2.1、§20.0、WP7（§1812–1844）、§21、§29 |
| 前置状态 | `WP6-a` / `WP6-c` / `WP7-a` 已 finalized。WP7-a 已完成 GRPO control-plane、reward wiring、artifact/resume、fairness 与 hardware guard；`proceedings.md` 明确剩余 completed C/D checkpoint identity、从 merged B + C/D adapter 的独立 reload、统一 C/D evaluation/aggregation 接入。当前没有合法 `Development Complete Record`，WP8 development 仍未完成。 |
| `planning_base_commit` | `d2af80bc77aff2fb539fc8e0ad5cfa85812e897b` |
| proposed branch | `feat/wp7-b` |
| proposed worktree | `.worktrees/wp7-b` |
| final plan path | `ai-work/planner/WP7-b-plan.md` |
| execution report path | `ai-work/executor/WP7-b-executor.md` |
| review path | `ai-work/reviewer/WP7-b-review.md` |
| plan lifecycle | planner-ex handoff → `stage-lifecycle bootstrap_plan` → committed plan seal |

## 2. 目标与范围

### 目标（规格原文对应）

完成 WP7 development acceptance 中 WP7-a 尚未覆盖的 checkpoint/evaluation 部分：使用 fixture/mock checkpoint identity 验证 C/D 初始化与重载合同；completed C/D checkpoint 必须可独立恢复为 `base A → completed B adapter safe-merge → C/D adapter` 的 inference policy；C/D 继续复用现有 deterministic evaluator/aggregator，并保持 Public/Hidden 除 reward 来源外的公平性与 payload 隔离。development evidence 不要求真实 GRPO optimizer step、真实 C/D checkpoint 或研究数值。

### 交付（规格对应）

- 严格的 completed GRPO run/checkpoint identity loader，只接受 `status=completed`、完整 artifact layout、有效 C/D adapter，并把 run 与其唯一 parent completed SFT B identity 绑定；
- 一个 non-sensitive、稳定的 GRPO evaluation checkpoint identity，使 evaluation exact-prefix resume 同时绑定 C/D adapter 与 parent B，而不是只绑定一个可复用目录名；
- 基于 pinned Transformers + PEFT 的只读 C/D inference reload：加载 A，加载 completed B adapter 并 `safe_merge`，再加载选定 C/D adapter；
- `code-verifier evaluate` 增加 completed GRPO run 的显式模型来源，继续调用现有 `run_pass1_evaluation()` 与 `aggregate_evaluation_run()`；
- fixture/fake runtime unit/integration evidence，证明 C/D reload、evaluation identity、resume、artifact schema 与 payload boundaries；
- README/AGENTS 的最小使用说明与 invariant 更新。

### 验收（规格对应）

- completed GRPO identity 只能来自严格 completed run，且 run 内记录的 parent SFT identity 必须可重新通过 `load_completed_sft_checkpoint()` 验证并逐字段一致；
- C/D inference policy 的重建顺序固定为 `base A → B read-only → merge_and_unload(safe_merge=True) → C/D read-only adapter`；不得把 C/D adapter 直接挂到 A，也不得把 B adapter 继续作为 active PEFT adapter；
- C/D evaluation 与 A/B 共用 `run_pass1_evaluation()` / `aggregate_evaluation_run()`、相同 dataset/Piston/generation/三层验证/metrics schema；
- `EvaluationConfig.checkpoint` 必须绑定 C/D run 与 parent B 的 non-sensitive identity，切换 C↔D、GRPO run、parent B、config/data/seed 后旧 evaluation run 不可错误 resume；
- 非 completed/损坏 GRPO run、invalid adapter、parent B drift、adapter/base identity mismatch 均 fail closed；
- eval-hidden/reference/starter/SFT response 不得进入训练 checkpoint identity、generation prompt 或非 `samples/results.jsonl` evaluation artifacts；
- fixture/fake checkpoint 只作为 engineering evidence，不得记录为正式 C/D checkpoint、research metric、loss、cost 或 final validation evidence。

### 范围内 / 范围外

- 范围内：WP7 completed GRPO checkpoint identity、parent-B binding、C/D stacked PEFT inference reload、evaluate CLI binding、exact resume identity、unit/integration、必要文档。
- 范围外：真实 SFT/GRPO optimizer run；正式 B/C/D checkpoint/数值/成本；WP8 aggregation/error-analysis tooling；24GB validation；修改 `third_party/open-r1/**`；改变 A–D 实验定义；升级 pinned dependencies。
- `archive/*` 历史分支仅用于审计，不作为本 stage completed evidence，也不 cherry-pick 旧 execution report。

## 3. 前置条件与约束

- WP7-a 的 Public/Hidden config pair、GRPO run layout、parent SFT metadata、reward artifact schema、resume contract、20 GiB hardware guard保持不变。
- WP6-c 的 `SFTCheckpointIdentity`、`load_completed_sft_checkpoint()` 和 `TransformersCompletionGenerator.from_peft_checkpoint()` 是既有基础；本 stage 复用它们，不复制第二套 SFT identity/evaluator。
- 不修改 `third_party/open-r1/`；训练侧 Open-R1 访问仍仅经 `training/open_r1_adapter.py`。inference reload 使用当前 pinned `peft==0.14.0` / `transformers==4.52.3` public API。
- 不新增自动目录猜测、legacy fallback、多版本兼容层或新的 evaluator/aggregator factory。`evaluate` 的模型来源始终显式互斥。
- C/D adapter 是在 merged-B policy 上训练出的新 LoRA；因此仅校验 adapter config 的 base A identity 还不够，真正 inference 构造必须显式重建 B merge，然后再附加 C/D adapter。
- evaluation 的 `checkpoint` 字段当前是字符串 identity。为保持现有 schema，优先生成一个可追溯的 canonical string/hash 来同时绑定 GRPO checkpoint path + GRPO identity + parent SFT identity；不要为本 stage把整个 evaluation schema 改成嵌套 checkpoint object。

### Execution preflight（首次业务修改/commit 前）

1. **Stage-local 工具链**
   - 命令：
     - `.venv/bin/python -m ruff --version`
     - `.venv/bin/python -m mypy --version`
     - `.venv/bin/python -m pytest --version`
   - 通过标准：三者均从当前 `.worktrees/wp7-b/.venv` 启动成功。

2. **Pinned PEFT/Transformers contract**
   - 命令：用 `.venv/bin/python` 导入 `peft`, `transformers`, `torch`，断言 `peft==0.14.0`、`transformers==4.52.3` 与当前 lock 中 torch；用 `inspect.signature` 核对 `PeftConfig.from_pretrained`、`PeftModel.from_pretrained`、`PeftModel.merge_and_unload` 的当前 pinned 参数，特别确认 inference-only `is_trainable=False` 与 `safe_merge=True` 路径存在。
   - 通过标准：与当前 pinned runtime 一致；若 API 不一致，停止并修复环境/lock mismatch，不升级依赖来追随最新版。

3. **现有 CUDA/model-cache 基线**
   - 命令：`make test-gpu`
   - 通过标准：GTX 1660 Ti 上现有真实 generation smoke 全绿；本 stage 不启动 optimizer-based training。

4. **Piston evaluation prerequisite**
   - 命令：用 `.venv/bin/python` 加载 `configs/execution/piston-local.yaml` 并调用现有 `PistonExecutor.validate_runtime()`。
   - 通过标准：loopback Piston runtime 可达；若仅为服务/环境问题，停止且保持 `HEAD == plan_commit`，修复环境后重新 dispatch。

5. **Source binding**
   - 命令：用 `.venv/bin/python` 输出并断言 `code_verifier.__file__`、`open_r1.__file__` 均来自当前 `.worktrees/wp7-b` checkout/其 pinned submodule，不得指向 primary checkout 的源码。

preflight 失败时不得先提交业务修改。环境修复后按现有 workflow 从断点重新调用 execution-router；不要因为纯环境故障自动退役 stage。

## 4. 实施步骤

### 步骤 1：增加 completed GRPO checkpoint identity 与 parent-B 强绑定

**目标文件**：`src/code_verifier/training/grpo.py`、`tests/unit/training/test_grpo.py`

**新增符号**：
```python
@dataclass(frozen=True)
class GRPOCheckpointIdentity:
    run_dir: Path
    checkpoint_dir: Path
    run_id: str
    reward_mode: str
    dataset_hash: str
    config_hash: str
    dependency_lock_hash: str
    seed: int
    parent_sft: SFTCheckpointIdentity


def load_completed_grpo_checkpoint(run_dir: Path) -> GRPOCheckpointIdentity:
    ...


def grpo_evaluation_checkpoint_id(identity: GRPOCheckpointIdentity) -> str:
    ...
```

**主要功能**：
- `run_dir` 必须 resolve 为真实目录，并严格符合 `_GRPO_RUN_LAYOUT`；`run.json.status` 只能是 `completed`。
- `checkpoint_dir` 固定为该 run 直接子目录 `checkpoints/`；必须存在当前 pinned PEFT final adapter 的 `adapter_config.json` 与非空 `adapter_model.safetensors`，拒绝 symlink/跨 run path。允许 trainer 在 `checkpoints/` 下保留合法 `checkpoint-N` 子目录，不要求目录只含两文件。
- 严格解析 `run_id`、`reward_mode in {public, hidden}`、dataset/config/dependency 64-hex hashes、整数 seed；不把 rollout/reward/test payload读入 identity。
- 从 `run.json` 的 `parent_sft_run_path` 调用 `load_completed_sft_checkpoint()`；随后逐项比对 `parent_sft_run_id/model_id/model_revision/dataset_hash/config_hash/dependency_lock_hash/seed/run_path/checkpoint_path`，任何 drift 均 fail closed。不得只信任 GRPO run 中复制的 parent metadata。
- 读取 C/D adapter config，至少验证 `base_model_name_or_path == parent_sft.model_id`；adapter revision 若非 null，则必须等于 `parent_sft.model_revision`。具体 `revision=None` 语义沿用 WP6-c 的 pinned PEFT合同。
- `grpo_evaluation_checkpoint_id()` 对 non-sensitive canonical identity 做稳定 SHA-256，返回同时包含 resolved GRPO checkpoint path 与 identity digest 的字符串，例如 `<resolved-checkpoint>#identity=<64hex>`；digest 输入至少包括 reward_mode、GRPO run/config/data/dependency/seed、parent SFT run/config/data/dependency/seed/model/revision/checkpoint path。切换 parent B 或 C/D 后 identity 必须变化。

**测试函数**：
- `test_load_completed_grpo_checkpoint_accepts_completed_run_and_parent_identity`
- `test_load_completed_grpo_checkpoint_rejects_running_failed_or_invalid_metadata`
- `test_load_completed_grpo_checkpoint_rejects_missing_or_invalid_adapter_artifact`
- `test_load_completed_grpo_checkpoint_rejects_parent_sft_identity_or_path_drift`
- `test_load_completed_grpo_checkpoint_rejects_adapter_base_or_revision_mismatch`
- `test_grpo_evaluation_checkpoint_id_is_stable_and_binds_parent_and_reward_mode`

**验证命令与通过标准**：
```bash
.venv/bin/python -m pytest tests/unit/training/test_grpo.py -q
```
全部通过；WP7-a training/run/resume tests 无回归。

### 步骤 2：增加 merged-B + C/D adapter 的严格 inference reload

**目标文件**：`src/code_verifier/evaluation/generate.py`、`tests/unit/evaluation/test_generate.py`

**新增 / 修改符号**：
```python
class TransformersCompletionGenerator:
    @classmethod
    def from_grpo_checkpoint(
        cls,
        *,
        base_model_id: str,
        base_model_revision: str | None,
        parent_sft_adapter_dir: Path,
        grpo_adapter_dir: Path,
        device: str,
        config: GenerationConfig,
        local_files_only: bool = False,
    ) -> "TransformersCompletionGenerator":
        ...
```

允许对现有 `from_peft_checkpoint()` 做一个最小 private helper refactor，只为共享 adapter path resolve、`PeftConfig.from_pretrained`、base/revision identity 检查与 inference-only `PeftModel.from_pretrained`；不要引入通用 adapter registry/factory。

建议的最小 private helper 形态：
```python
def _load_identity_checked_peft_adapter(
    *,
    base_model: Any,
    peft_config_type: Any,
    peft_model_type: Any,
    adapter_dir: Path,
    base_model_id: str,
    base_model_revision: str | None,
    local_files_only: bool,
    role: str,
) -> Any:
    ...
```

**主要功能**：
- 继续通过既有 `_validate_model_source()` 与 `_load_base_transformers_model()` 加载 base A/tokenizer，保持 `trust_remote_code=False`、dtype/device/local-only/deterministic generation contract。
- 第一次调用 helper：把 completed B adapter 以 `is_trainable=False` 加载到 A；检查实例暴露 callable `merge_and_unload`，执行 `merge_and_unload(safe_merge=True)` 得到 merged-B。
- 第二次调用 helper：把 C/D adapter 以 `is_trainable=False` 加载到 merged-B；C/D adapter config 的 base model/revision仍按当前 pinned contract与 A identity核对，但模型权重底座必须是 merged-B。
- 最终模型调用既有 `_initialize_inference_model()`，不创建 trainer/optimizer，不启用 adapter training，不改变 `generate()` 与 decoding schema。
- runtime 错误转换为 `GenerationError`，只暴露合同/错误类别，不输出 adapter payload、测试或 completion。
- 现有 `from_peft_checkpoint()` 的 B evaluation 行为必须保持不变。

**测试函数**：
- `test_from_grpo_checkpoint_loads_a_merges_b_then_loads_cd_read_only`
- `test_from_grpo_checkpoint_requires_safe_merge_before_cd_adapter`
- `test_from_grpo_checkpoint_rejects_parent_or_grpo_adapter_identity_mismatch`
- `test_from_grpo_checkpoint_accepts_none_adapter_revision_under_pinned_contract`
- `test_from_grpo_checkpoint_preserves_dtype_device_local_only_and_eval_mode`
- `test_from_grpo_checkpoint_wraps_runtime_failure_without_payload`
- 既有 `from_peft_checkpoint` tests 全部继续通过。

**验证命令与通过标准**：
```bash
.venv/bin/python -m pytest tests/unit/evaluation/test_generate.py -q
```
全部通过，不下载模型、不运行真实训练。

### 步骤 3：把 completed GRPO run 显式接入现有 evaluate CLI

**目标文件**：`src/code_verifier/cli.py`、`tests/unit/test_cli.py`

**修改符号**：
```python
def _evaluate(args: argparse.Namespace) -> int:
    ...


def build_parser() -> argparse.ArgumentParser:
    ...
```

**CLI 变更**：`evaluate` 的模型来源互斥组扩展为三选一：
- `--model-id <base-model-id>`：A/Base；
- `--sft-run-dir <completed-sft-run>`：B；
- `--grpo-run-dir <completed-grpo-run>`：C 或 D。

三者必须且只能提供一个；不允许目录启发式自动判断 checkpoint 类型。

**主要功能**：
- Base 与 SFT 路径行为保持现状。
- GRPO 路径先调用 `load_completed_grpo_checkpoint()`；`model_id/model_revision` 从 `identity.parent_sft` 获取；generator 使用 `from_grpo_checkpoint(base_model_id=..., parent_sft_adapter_dir=identity.parent_sft.checkpoint_dir, grpo_adapter_dir=identity.checkpoint_dir, ...)`。
- 仅在内存中 `replace()` 当前 EvaluationConfig：dataset/Piston/device/generation保持原配置；`model_revision=parent_sft.model_revision`；`checkpoint=grpo_evaluation_checkpoint_id(identity)`。
- 继续调用现有 `run_pass1_evaluation()` 与 `aggregate_evaluation_run()`，不新增 C/D evaluator、metrics schema、bootstrap实现。
- evaluation run metadata / resolved config 中 checkpoint string必须能够追溯到实际 C/D checkpoint path，同时 identity digest绑定 parent B；reward_mode 不作为 evaluation逻辑分支，只存在于被验证的 checkpoint identity中。
- C/D 的 `model_id` 仍是 A/base model identity；实际模型差异由 checkpoint identity表达。

**测试函数**：
- `test_evaluate_parser_requires_exactly_one_of_base_sft_or_grpo_source`
- `test_evaluate_base_and_sft_paths_remain_unchanged`
- `test_evaluate_grpo_run_binds_completed_cd_and_parent_b_identity`
- `test_evaluate_grpo_run_uses_stacked_checkpoint_generator_and_existing_aggregator`
- `test_evaluate_grpo_run_rejects_incomplete_or_parent_drift_before_generation`
- `test_evaluate_grpo_identity_change_prevents_exact_prefix_resume`

**验证命令与通过标准**：
```bash
.venv/bin/python -m pytest tests/unit/test_cli.py -q
.venv/bin/code-verifier evaluate --help
```
help 明确三种互斥来源；A/B 现有调用合同无回归。

### 步骤 4：补 C/D 统一评测 integration contract

**目标文件**：新增 `tests/integration/test_wp7b_grpo_checkpoint_evaluation.py`；复用已有 WP6-c/evaluation fixtures/helpers，避免复制 evaluator/data pipeline。

**主要功能**：
- 构造最小 deterministic completed SFT B fixture，以及两个 completed GRPO fixture（Public C / Hidden D）。adapter bytes/config只用于 engineering contract，不代表真实训练。
- fake PEFT/Transformers runtime必须真实经过 production `from_grpo_checkpoint` 构造顺序，记录 A load → B read-only → safe merge → C/D read-only；禁止测试绕过 production loader直接塞 fake generator结果。
- 贯通 completed GRPO identity → stacked reload → 现有 pass@1 evaluator → existing aggregator。
- C/D 使用同一 prepared evaluation dataset/config/seed/Piston contract；只因所选 checkpoint identity不同而生成不同 evaluation run identity。
- 验证 `run.json`、`resolved_config.yaml`、`samples/results.jsonl`、summary/main_results 延续 WP5 schema；C/D checkpoint identity可追溯，aggregator无需知道 reward_mode。
- exact-prefix resume：相同 C identity可恢复；将 source换成 D、另一 GRPO run、另一 parent B、修改 config/data/seed必须 fail closed。
- prompt 仍只包含题面/函数签名/visible examples；non-sample artifacts不出现 completion/code/visible/train-hidden/eval-hidden/reference/starter/SFT response payload。
- integration assertion中显式标注 fixture C/D不是正式训练 evidence。

**测试函数**：
- `test_wp7b_completed_grpo_checkpoint_runs_through_existing_evaluator`
- `test_wp7b_cd_reload_order_is_a_then_merged_b_then_cd_adapter`
- `test_wp7b_cd_evaluation_resume_is_bound_to_cd_and_parent_b_identity`
- `test_wp7b_cd_evaluation_artifacts_preserve_payload_boundaries`
- `test_wp7b_fixture_cd_is_never_reported_as_real_training_evidence`

**验证命令与通过标准**：
```bash
.venv/bin/python -m pytest tests/integration/test_wp7b_grpo_checkpoint_evaluation.py -q
```
0 failed；测试不要求 24GB GPU、optimizer step 或网络下载。

### 步骤 5：更新最小文档与项目约束

**目标文件**：`README.md`、`AGENTS.md`

**主要功能**：
- README 将项目实现状态推进到 WP7-b，并增加 `evaluate --grpo-run-dir ...` 命令形态；说明真实 C/D run 只有 4090 validation 产生后才是正式 evidence，development fixture只验证工程合同。
- 明确 C/D evaluation重建顺序必须是 A → merge B → load C/D，继续使用同一 evaluator/aggregator。
- AGENTS 增加 invariant：completed GRPO checkpoint必须由 `load_completed_grpo_checkpoint()`验证，parent B必须重新通过 `load_completed_sft_checkpoint()`绑定；C/D evaluation不得接受任意 adapter path或跳过 B merge；fixture不得记成正式 C/D。
- 不加入 WP8 或 validation 实验结果叙述。

**验证命令与通过标准**：
```bash
.venv/bin/code-verifier evaluate --help
```
README 与 CLI 一致；没有声称真实 C/D 已产生。

### 步骤 6：全量工程验收

按顺序运行：
```bash
.venv/bin/python -m pytest tests/unit/training/test_grpo.py tests/unit/evaluation/test_generate.py tests/unit/test_cli.py tests/integration/test_wp7b_grpo_checkpoint_evaluation.py -q
make lint
make test
make test-gpu
```

另执行一次非破坏性 Piston runtime probe（与 preflight相同），确认 unified evaluator的真实 execution prerequisite仍可用。

通过标准：
- focused tests 0 failed；
- `make lint` 全绿；
- `make test` 0 failed，允许仅项目既有“需显式启用 real Piston acceptance”的 skips；
- GTX 1660 Ti 上 `make test-gpu` 真实 generation smoke 全绿；
- Piston runtime probe 成功；
- 不调用 `train-sft` / `train-grpo` optimizer step，不生成或声称真实 B/C/D checkpoint、loss、metric、cost。

`make test-piston` 不是本非 terminal WP7-b 的新增强制 gate，因为本 stage 不修改 execution/Piston 隔离实现；terminal development closeout仍必须单独运行 real `make test-piston` 且 0 failed/0 skipped。

## 5. 总体验收与测试计划

- **单元测试**：completed GRPO identity、parent B drift、adapter artifact/base-revision校验、canonical evaluation identity、stacked PEFT load顺序、CLI三选一与 A/B regression。
- **Development integration**：fixture B+C/D + fake PEFT/Transformers runtime贯通真实 production identity/reload/evaluator/aggregator contract；GPU smoke与Piston probe验证开发机外部基线。
- **Evaluator consistency**：A/B/C/D均必须使用现有 `run_pass1_evaluation()` + `aggregate_evaluation_run()`；不得添加 reward-mode-specific evaluator逻辑。
- **Resume/reproducibility**：C/D evaluation checkpoint identity同时绑定 GRPO run与parent B；切换 C/D、B、data/config/seed后旧 evaluation run无法错误 resume。
- **数据泄漏/安全**：C/D checkpoint identity只含 non-sensitive metadata/hash/path；prompt不含 hidden/reference/SFT response；除 samples结果外非 sample artifact不持久化 completion/code/test payload。
- **Real training/numerical gate**：本 stage明确不执行。真实 B、真实 C/D optimizer/checkpoint/reload/数值/成本继续 deferred 到 Development Complete Record 后的 24GB validation track。

最终标准：
- [ ] WP7 development acceptance 的 completed C/D checkpoint identity、parent B binding、stacked reload 与 unified evaluation均有 finalized-quality engineering evidence
- [ ] A/B evaluation行为无回归
- [ ] `make lint` 全绿
- [ ] `make test` 全绿（仅既有显式 real-Piston opt-in skips可存在）
- [ ] `make test-gpu` 在 GTX 1660 Ti 全绿
- [ ] Piston runtime probe成功
- [ ] 无真实训练、无伪造 C/D checkpoint/指标/成本
- [ ] 未修改 `third_party/open-r1/`，未升级 pinned dependency contract
- [ ] WP8仍未完成，因此本 stage 不写 `Development Complete Record`

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
    - "GRPO completed identity 是 stacked PEFT reload 的前置，CLI 与 integration 又必须消费两者；公共接口、checkpoint identity 和 exact-resume 语义存在强串行依赖。"
    - "虽然改动跨 training/evaluation/CLI/tests，但它们构成一个端到端 checkpoint-evaluation能力；拆成 MULTI 会导致 adapter identity、fake runtime与resume contract重复协调，集成成本高于并行收益。"
  workstream_candidates: []
```

## 7. 风险与注意事项

- **核心正确性风险：C/D 不能直接挂到 A。** WP7-a 的训练合同是在 merged-B policy 上创建新 GRPO LoRA；independent evaluation必须先重建并 merge B，再加载 C/D。
- **PEFT adapter revision 语义**：沿用 WP6-c 对 pinned PEFT 0.14.0 的规则；`revision=None` 可接受，但非 null revision必须与 completed parent run一致。不要添加跨版本 fallback。
- **evaluation identity必须包含 parent B。** 仅把 C/D checkpoint目录路径写进 `EvaluationConfig.checkpoint` 不足以证明 parent B未变化；canonical digest必须绑定 parent identity。
- **不要把 reward mode带入 evaluator逻辑。** Public/Hidden差异只在训练来源与checkpoint identity；评测一律使用 eval-hidden作为最终层并复用同一 pipeline。
- **不要修改实验定义。** 不因fixture方便而改变 configs/grpo、generation、seed、Piston、bootstrap或A–D比较口径。
- **fixture/fake证据边界**：任何 fake C/D adapter、synthetic result、mock runtime只能证明工程合同，不得写入 proceedings为正式 checkpoint/数值/成本。
- 若 preflight 发现 ruff/mypy/pytest、Piston、CUDA/model cache或 pinned runtime环境问题，先修环境再重新 dispatch；环境问题本身不应触发业务兼容代码。

## 8. 关联文档索引

- `PROJECT_SPEC_Open-R1_CodeVerifier.md`：§19.2.1 Development integration；§19.2.2 Final validation；§20.0 Development-first；WP7；§21.1；§29
- `proceedings.md`：WP6-c finalized、WP7-a finalized 及其“WP7 development 状态”剩余项
- `src/code_verifier/training/grpo.py`：WP7-a run layout、parent SFT identity、training/artifact/resume contract
- `src/code_verifier/training/sft.py`：`SFTCheckpointIdentity` / `load_completed_sft_checkpoint()`
- `src/code_verifier/evaluation/generate.py`：Base/B Transformers/PEFT inference loader
- `src/code_verifier/evaluation/evaluate.py` / `metrics.py`：必须复用的 deterministic evaluator/aggregator 与 exact resume identity
- `src/code_verifier/cli.py`：现有 Base/B evaluate 与 GRPO training CLI

## 9. Handoff

- 下一步：运行 `$stage-lifecycle bootstrap_plan`，由 lifecycle 创建/复用 `feat/wp7-b` + `.worktrees/wp7-b`，将本计划写入 `ai-work/planner/WP7-b-plan.md` 并 commit plan seal。
- bootstrap成功并返回 `plan_commit` 前，不得调用 execution-router。
- 本轮 planner-ex不创建 branch/worktree、不修改业务代码、不 commit、不启动 executor。

## Implementation contract

- Work from this plan in small, reviewable steps.
- Keep edits scoped to the requested task and existing project conventions.
- Run focused verification before handing work back.
- Update .ai-bridge/agent-status.md with files touched, checks run, results, blockers, and review notes.
- Save the final review diff to .ai-bridge/implementation-diff.patch when practical.
- Append notable execution events to .ai-bridge/execution-log.jsonl when the implementation agent supports logging.
