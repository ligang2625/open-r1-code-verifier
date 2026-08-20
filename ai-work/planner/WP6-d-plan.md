# WP6-d 实施计划（Formal SFT B validation、durable evaluation identity 修复、一次训练完整遥测与 B 组统一评测）

## 1. 元信息

| 项 | 值 |
|---|---|
| stage_id | `WP6-d` |
| stage_profile | `validation` |
| target_hardware | `24GB GPU` |
| evidence_class | `real-training/numerical` |
| development_terminal | `false` |
| 目标 WP | `WP6`：SFT validation acceptance、正式 B checkpoint 与 B 组统一评测；同时修复 validation 中暴露的 finalized-worktree evaluation identity readback 缺陷 |
| planning_base_commit | `a683602f22de7f7b0ba24f01d12a183eea7ddca7` |
| proposed branch | `feat/wp6-d` |
| proposed worktree | `.worktrees/wp6-d` |
| final plan path | `ai-work/planner/WP6-d-plan.md` |
| execution report path | `ai-work/executor/WP6-d-executor.md` |
| review path | `ai-work/reviewer/WP6-d-review.md` |
| lifecycle | pre-execution replan → `stage-lifecycle bootstrap_plan` → `execution-router backend=web` → durable identity repair → short real SFT smoke → formal SFT operator checkpoint → user terminal → explicit resume → B evaluation operator checkpoint → user terminal → explicit resume → completed E0 |

### Replan reason

上一版 WP6-d 在首次业务修改前的 Base A strict readback 暴露了一个真实持久化设计缺陷：`resolved_config.yaml` 保存的是生成该 run 的 stage worktree 内 `piston_config` 绝对路径；stage finalize 删除 worktree 后，`resolved_evaluation_config_hash()` 与 WP8 Piston-definition comparison 再次打开该路径，导致已完成且具有完整 `run.json.piston_config_sha256` 的正式 Base A 无法长期 strict readback。该问题属于 validation 暴露的实现缺陷，不允许通过重跑 Base A、伪造旧 worktree 或修改历史 artifact 绕过。

本 replan 保持正式实验定义、模型、数据、训练超参、A artifact、Piston 内容 identity 和 operator gate 不变，只把 durable evaluation identity 修复放在 WP6-d 的第一项 tracked implementation，并把依赖该修复的 Base A strict readback 从“首次业务修改前”移动到该修复后的强制 gate。

## 2. 目标与范围

### 目标

1. 修复 evaluation/analysis 的长期 identity contract：`run.json.piston_config_sha256` 是 finalized worktree 消失后的持久化 Piston definition identity；`resolved_config.yaml.piston_config` 路径继续保留为审计字段，但 analysis/hash readback 不得要求该历史路径仍存在。
2. 保持 tamper fail-closed：resolved config 内容漂移、persisted Piston digest 漂移、A/B/C/D digest 不一致仍必须失败。
3. 不修改 `/root/sj-tmp/open-r1-code-verifier-outputs/evaluation/A-base-formal-seed42/**`；用现有 Base A artifact 直接证明 durable readback 修复有效。
4. 使用正式 2,500 train + 300 validation SFT 数据、Qwen2.5-Coder-1.5B exact revision、LoRA、seed 42 完成正式 B optimizer run，并一次性保存后续分析不可再生的训练遥测/checkpoint/cost evidence。
5. 严格重载 completed B，在与 Base A 相同 400 题 test/evaluator/aggregator/seed/deterministic generation/Piston semantics 下完成 B full evaluation，并验证 A/B pairing readiness。

### 范围外

- 不重跑或改写 Base A。
- 不修改 `third_party/open-r1/**`。
- 不进行 Public/Hidden GRPO C/D、C/D evaluation、最终 A–D 结论、超参搜索、多 seed、量化/vLLM/DeepSpeed。
- 不把旧 worktree 路径恢复成永久依赖，不创建 compatibility symlink，不把 formal artifact 复制回 stage worktree。

## 3. Execution preflight（首次业务修改/commit 前）

以下检查全部在 `HEAD == plan_commit` 时完成；失败则保持 plan baseline，不写 execution report，不做业务修改。

1. **Validation machine / Git / persistent roots**
   - `.ai-bridge/validation-machine.json` 为 version 1 / `READY_FOR_VALIDATION_PLANNER`；readiness/Piston identity 一致；bootstrap commit 为当前 main 祖先。
   - `artifact_root`、`hf_home`、`formal_data_root` 为 stage worktree 外的绝对路径；artifact root 可写；primary/stage `git ls-files .ai-bridge` 为空。

2. **Pinned CUDA/BF16 gate**
   - stage `.venv` pinned PyTorch 可导入，CUDA true，GPU total memory `>=22528 MiB`，native BF16 true。
   - 记录 GPU identity；正式环境当前预期 `NVIDIA GeForce RTX 4090`、PyTorch `2.6.0+cu124`。

3. **Pinned training API**
   - exact `trl==0.18.0`、`transformers==4.52.3`、`accelerate==1.4.0`、`peft==0.14.0`。
   - `SFTConfig` 必须支持 `skip_memory_metrics/include_num_input_tokens_seen/save_total_limit/save_only_model/logging_nan_inf_filter`。

4. **Formal data integrity**
   - 从 `$CODE_VERIFIER_DATA_ROOT` 自身目录执行 `sha256sum -c checksums.sha256`。
   - `check-data --dataset "$CODE_VERIFIER_DATA_ROOT/prepared"` 必须确认 3200=2500/300/400；selection manifest `sft_max_seq_length_required=1536`、实际 train+validation max tokens=1519。
   - 不重新 prepare/reselect。

5. **Exact model cache**
   - `HF_HOME=<router hf_home>`、offline/local-only 加载 `Qwen/Qwen2.5-Coder-1.5B-Instruct@2e1fd397ee46e1388853d2af2c993145b0f1098a`，BF16 GPU lightweight probe 通过，无下载/revision drift。

6. **真实 tunneled Piston**
   - `make test-piston`；必须 9/9 passed、0 skipped，endpoint `127.0.0.1:2000`、Python 3.10.0 identity 与 machine record 一致。

7. **Formal Base A structural evidence（不依赖已删除历史路径）**
   - 只读 `$CODE_VERIFIER_ARTIFACT_ROOT/evaluation/A-base-formal-seed42/run.json`、`resolved_config.yaml`、`samples/results.jsonl` 与 machine Piston identity。
   - 要求 `status=completed`、400 unique problem IDs、model/revision/seed/dataset identity 与 WP5-c evidence 一致；`run.json.piston_config_sha256` 为合法 64-hex，等于 machine/current exact Piston YAML digest。
   - 允许 `resolved_config.yaml.piston_config` 指向已经 finalize 删除的历史 worktree；此处不得调用需要重新打开该历史路径的旧 strict hash helper。真正 strict config/hash readback 是步骤 1 修复后的强制 gate。

8. **Baseline focused tests**
   - `.venv/bin/python -m pytest tests/unit/training/test_sft.py tests/unit/test_cli.py tests/unit/analysis -q`。

## 4. 实施步骤

### 步骤 1：修复 finalized-worktree evaluation identity 的 durable readback

**目标文件**
- `src/code_verifier/evaluation/evaluate.py`
- `src/code_verifier/analysis/experiment.py`
- `tests/unit/analysis/test_experiment.py`
- 必要时 `tests/unit/evaluation/test_evaluate.py`，仅补对应 identity helper 单测

**符号/合同**

```python
def resolved_evaluation_config_hash(value: object, *, piston_config_sha256: str) -> str:
    ...
```

如实现上更简洁，可增加一个仅内部使用的 canonical hash helper，例如：

```python
def _evaluation_config_hash_from_resolved(
    config: EvaluationConfig,
    *,
    model_id: str,
    seed: int,
    piston_config_sha256: str,
) -> str:
    ...
```

要求：
- active/new evaluation 的 `evaluation_config_hash()` 仍先读取当前真实 `config.piston_config`，计算 digest，再进入同一个 canonical hash payload；运行时仍 fail closed，不允许缺失当前 Piston config。
- persisted readback 的 `resolved_evaluation_config_hash()` 不再重新读取 `resolved_config.yaml.piston_config`；它必须显式接收已经持久化的 `run.json.piston_config_sha256`，验证为 64-hex，并用**原 resolved path 字符串 + persisted digest**重算当时的 exact config hash，因此 Base A 已有 `config_hash` 不发生变化。
- `analysis.experiment._load_evaluation_run()` 先 strict 读取 `run.json`，验证 `piston_config_sha256`，再用该 digest 重算 `resolved_config_hash`；不得根据路径存在性降级验证。
- A/B/C/D shared Piston-definition comparison 使用各 run metadata 中的 persisted `piston_config_sha256`，而不是重新打开每个 stage 的历史 path。
- 当前 live Piston 的内容身份仍在 validation preflight/operator-start preflight 中与 machine record/当前 config digest 比较；durable analysis 不把“路径仍存在”混同为“definition identity 正确”。
- 不修改 persisted schema，不给历史 artifact 写 compatibility 字段；当前正式 A 已经具有 `piston_config_sha256`，缺失/malformed digest 的 source 必须 fail closed。

**测试**
- fixture writer 在 `run.json` 写入 Piston digest，并用该 digest生成 config hash。
- `test_load_analysis_inputs_accepts_finalized_evaluation_with_missing_historical_piston_path`：创建 A–D fixture 后删除原 `piston.yaml`，仍能 strict load，证明 analysis 只依赖 persisted digest。
- resolved config 内容 tamper 仍失败。
- persisted digest tamper 仍失败。
- A/B/C/D persisted digest 不一致仍失败。
- active `evaluation_config_hash()` 在当前 Piston config 缺失时仍失败。

**验证**
```bash
.venv/bin/python -m pytest tests/unit/analysis/test_experiment.py tests/unit/evaluation/test_evaluate.py -q
```

**修复后真实 Base A gate（必须在进入 SFT instrumentation 前通过）**
- 用项目 strict `_load_evaluation_run()` 直接读取现有 `$CODE_VERIFIER_ARTIFACT_ROOT/evaluation/A-base-formal-seed42`。
- 必须得到 completed、400 unique IDs、原 `config_hash=fd1aaebe1b076c9a062826eae32bb94e2e0caf20b876ac7ddd3911bb65ab7d32`，且不创建 `.worktrees/wp5-c`、不改 A artifact。
- 同时确认 persisted Piston digest等于 machine/current definition digest。

该 gate 失败视为源码/identity logic failure，继续在步骤 1 内修复，不得启动正式训练。

### 步骤 2：为 `train-sft` 增加正式数据/run 显式 binding，并封存 formal SFT config

**目标文件**
- `src/code_verifier/cli.py`
- `configs/sft/main.yaml`
- 新增 `configs/sft/validation-smoke.yaml`
- `tests/unit/test_cli.py`
- `tests/unit/training/test_sft.py`
- `README.md`

**主要功能**
- `train-sft` 增加 `--dataset-dir PATH` 与 `--run-name SAFE_NAME`；dataset-dir 显式绑定 `<prepared>/training/sft.jsonl`，eval enabled 时绑定 `sft_validation.jsonl`。
- `--run-name` 进入 config/run/config-hash identity；override 只打印 old→new path/name，不打印数据内容。
- `configs/sft/main.yaml`：`max_seq_length=1536`、`logging_steps=1`；模型/revision、2 epochs、batch size 1、grad accumulation 16、LR 2e-4、warmup 0.05、cosine、BF16、LoRA r16/alpha32/dropout0.05、seed 42 保持冻结定义。
- `configs/sft/validation-smoke.yaml`：同 exact 1.5B revision、BF16、LoRA/LR/max length 1536，`max_steps=2`、`logging_steps=1`、`save_steps=1`、`eval_strategy=no`，输出到 persistent smoke namespace；只验证 runtime/telemetry，不作为 B evidence。

### 步骤 3：强化 SFT analysis-ready telemetry 与完整 checkpoint 保留

**目标文件**
- `src/code_verifier/training/sft.py`
- `tests/unit/training/test_sft.py`

**要求**
- pinned `SFTConfig` 设置 `skip_memory_metrics=False`、`include_num_input_tokens_seen=True`、`logging_nan_inf_filter=False`、`save_total_limit=None`、`save_only_model=False`，继续 `report_to=[]`、`push_to_hub=False`。
- `metrics.jsonl` 保留 `trainer.state.log_history` 中所有 finite numeric scalars；summary 合并 `train_result.metrics` 所有 finite numeric scalars。
- project-owned telemetry：`global_step`、train/eval sample counts、peak CUDA allocated/reserved bytes、gpu_count_used、gpu_hours、gpu_hours_semantics。
- `run.json` 保存 payload-free attempt history：attempt start/end/status/resume checkpoint/attempt GPU-hours/cumulative GPU-hours；NaN/Inf fail closed。
- 不自动 pruning numeric `checkpoint-*`；final `checkpoints/` 仍为 completed PEFT adapter。
- 不新增通用 telemetry framework；保持最小 private helper。

### 步骤 4：真实 4090 2-step SFT smoke 与 analysis-readiness readback

executor 自己运行短时 smoke，不交给 operator：
- 显式设置 `CODE_VERIFIER_ARTIFACT_ROOT`、`HF_HOME`、`CODE_VERIFIER_DATA_ROOT`、offline env。
- 使用 `configs/sft/validation-smoke.yaml` 和仓库现有小型/受控 smoke dataset binding；模型必须是同一 exact 1.5B revision、BF16。
- 验证每 step `step/loss/grad_norm/learning_rate/epoch`、final numeric summary、global_step、CUDA peak、attempt history、checkpoint-1/checkpoint-2 resume state、final adapter。
- `load_training_curve_rows(..., method="SFT")` 与 `build_cost_row(..., method="SFT")` 必须直接消费 smoke artifact。
- 记录最大 complete smoke checkpoint bytes `S` 与文件/inode数 `F`，供 formal operator storage threshold。
- 缺字段只修 instrumentation 并重跑 2-step smoke；不得先启动 2500 条 formal SFT。

### 步骤 5：全局短时 acceptance 并生成 formal SFT operator checkpoint

formal gate 前 executor 运行：
- focused SFT/CLI/analysis tests；
- `make lint`、`make test`、`make test-gpu`、真实 `make test-piston`；
- formal data/model/Base A durable strict readback 再确认；
- stage clean，tracked code/config/tests 已 commit。

通过后进入 `sft-b-formal` operator protocol，不由 Web executor 启动长训练。

### 步骤 6：formal SFT resume acceptance 与 B evaluation operator gate

用户执行 SFT script 后显式 resume。executor 必须 strict 验证 formal B training artifact、checkpoint inventory、curve/cost loader、payload safety、identity；通过后生成新的 `sft-b-evaluation` operator checkpoint。用户执行 B evaluation script 后再次显式 resume，完成 400 题、exact-prefix 0-generation quick resume、A/B pairing readback及最终 E0。

## 5. Operator terminal execution

```yaml
operator_terminal_execution:
  version: 1
  required: true
  gates:
    - gate_id: sft-b-formal
      run_kind: sft
      executor_runs_command: false
      restart_policy: trainer_checkpoint
      expected_artifacts:
        - "$CODE_VERIFIER_ARTIFACT_ROOT/sft/B-sft-formal-seed42/run.json"
        - "$CODE_VERIFIER_ARTIFACT_ROOT/sft/B-sft-formal-seed42/resolved_config.yaml"
        - "$CODE_VERIFIER_ARTIFACT_ROOT/sft/B-sft-formal-seed42/environment.json"
        - "$CODE_VERIFIER_ARTIFACT_ROOT/sft/B-sft-formal-seed42/metrics.jsonl"
        - "$CODE_VERIFIER_ARTIFACT_ROOT/sft/B-sft-formal-seed42/checkpoints/adapter_config.json"
        - "$CODE_VERIFIER_ARTIFACT_ROOT/sft/B-sft-formal-seed42/checkpoints/adapter_model.safetensors"
    - gate_id: sft-b-evaluation
      run_kind: evaluation
      executor_runs_command: false
      restart_policy: exact_rerun
      expected_artifacts:
        - "$CODE_VERIFIER_ARTIFACT_ROOT/evaluation/B-sft-formal-seed42/run.json"
        - "$CODE_VERIFIER_ARTIFACT_ROOT/evaluation/B-sft-formal-seed42/resolved_config.yaml"
        - "$CODE_VERIFIER_ARTIFACT_ROOT/evaluation/B-sft-formal-seed42/environment.json"
        - "$CODE_VERIFIER_ARTIFACT_ROOT/evaluation/B-sft-formal-seed42/samples/results.jsonl"
        - "$CODE_VERIFIER_ARTIFACT_ROOT/evaluation/B-sft-formal-seed42/summary.json"
        - "$CODE_VERIFIER_ARTIFACT_ROOT/evaluation/B-sft-formal-seed42/main_results.csv"
```

### Gate `sft-b-formal`

**触发点**：步骤 1–5 已完成并 commit；durable Base A strict readback 与同模型 2-step smoke/analysis-readiness 全部通过；stage clean。

**namespace**：`$CODE_VERIFIER_ARTIFACT_ROOT/operator/WP6-d/<plan_commit>/sft-b-formal/<checkpoint_id>/`。非空同名目录 fail closed，不覆盖。

**script runtime provenance/lock/status-log**
- secret-free immutable `run.sh` 固定 stage worktree/branch、primary root、planning_base_commit、result_code_commit、stage/gate/checkpoint identity 和三个 machine roots，但不预先硬编码未来 checkpoint docs commit。
- 长命令前验证 stage clean/branch；`HEAD^ == result_code_commit`；`HEAD^..HEAD` 只修改本 stage execution report；latest checkpoint 中 stage/gate/checkpoint/path/SHA256 与脚本自身一致。
- primary `main HEAD == a683602f22de7f7b0ba24f01d12a183eea7ddca7` 且 non-ignored clean；persistent roots仍与 machine record一致。
- 取得 `flock` 排他锁。每 attempt 获锁后清除旧 status/temp-status，terminal log append attempt start/preflight/resume source/end/exit；status 通过 temp→atomic rename 写真实训练 rc。
- 不允许 `set -e` 在 status 写入前吞失败；若使用 `tee`，启用 `pipefail` 并捕获训练进程自身 `PIPESTATUS[0]`。

**operator-start short preflight**
- CUDA true、VRAM>=22528 MiB、native BF16；
- Piston loopback exact runtime快速 probe；
- formal SFT train/validation hashes/counts仍与 sealed evidence一致；
- exact 1.5B revision在 `$HF_HOME` local-only可载入；
- canonical run状态符合 fresh/resume branch；artifact root writable；
- free bytes `>= max(20 GiB, 5*S + 5 GiB)`，free inodes `>= max(20000, 5*F + 10000)`，其中 S/F 来自步骤 4 最大完整 smoke checkpoint实测。

**formal command template**

```bash
export CODE_VERIFIER_ARTIFACT_ROOT=<router artifact_root>
export HF_HOME=<router hf_home>
export CODE_VERIFIER_DATA_ROOT=<router formal_data_root>
export HF_HUB_OFFLINE=1
export TRANSFORMERS_OFFLINE=1
export NO_PROXY=127.0.0.1,localhost
export no_proxy=127.0.0.1,localhost
cd "$STAGE_WORKTREE"
"$STAGE_WORKTREE/.venv/bin/code-verifier" train-sft \
  --config configs/sft/main.yaml \
  --dataset-dir "$CODE_VERIFIER_DATA_ROOT/prepared" \
  --run-name B-sft-formal-seed42 \
  --seed 42
```

**trainer checkpoint policy**
- canonical run不存在：fresh。
- `run.json.status in {running,failed}`：同一 immutable script 只枚举 canonical run 的 numeric `checkpoints/checkpoint-*`，选择最大合法 same-run checkpoint并追加 `--resume-from-checkpoint`。
- valid checkpoint 至少具有当前 pinned Trainer smoke 合同的 optimizer/scheduler/RNG/trainer state及所需 adapter/state文件。
- run存在但无合法 checkpoint：fail closed，不删除/覆盖。显式 router resume 后 executor 把旧 run 移到 persistent unique quarantine并记录，再生成新 checkpoint/script fresh。
- 最高 checkpoint静态通过但 Trainer加载损坏：resume executor只 quarantine该 checkpoint并记录；保持同一 immutable script重跑，让其退回前一个合法 checkpoint。
- tracked source/config/test修复改变 formal identity：旧 incomplete canonical run整体 quarantine，再生成新 operator checkpoint fresh。

**SFT resume acceptance**
- status file rc=0 只是必要条件；必须 `run.json.status=completed`，model/revision/seed/project/open-r1/dependency/data/config identity完整。
- resolved config为2500/300、max_seq_length1536、logging_steps1、冻结优化定义。
- 所有 trainer/summary numeric有限；step/eval/final telemetry完整；global_step/CUDA peak/gpu_count/gpu-hours/attempt history完整。
- 所有 numeric `checkpoint-*` 未 pruning且resume state完整；final PEFT adapter可由 `load_completed_sft_checkpoint()` strict加载，独立新进程local-only reload通过。
- `load_training_curve_rows(..., method="SFT")` 非空；`build_cost_row(..., method="SFT")`成功。
- payload safety通过；所有正式 artifact位于 persistent root。

成功后才能准备 `sft-b-evaluation`。

### Gate `sft-b-evaluation`

**namespace/guard**：`$CODE_VERIFIER_ARTIFACT_ROOT/operator/WP6-d/<plan_commit>/sft-b-evaluation/<checkpoint_id>/`，使用与 SFT gate 相同的 stage/report SHA、primary main、machine roots、flock、atomic status、append-only log、真实 rc捕获规则。

**operator-start short preflight**
- CUDA/4090/exact model cache正常；Piston loopback Python 3.10.0；formal test split 400 unique problems；completed B strict loader/独立 PEFT reload通过。
- Base A durable strict readback仍通过；当前 live Piston digest与 A/B formal definition digest一致。
- artifact root writable；free bytes至少10 GiB、free inodes至少100000。

**command template**

```bash
export CODE_VERIFIER_ARTIFACT_ROOT=<router artifact_root>
export HF_HOME=<router hf_home>
export CODE_VERIFIER_DATA_ROOT=<router formal_data_root>
export HF_HUB_OFFLINE=1
export TRANSFORMERS_OFFLINE=1
export NO_PROXY=127.0.0.1,localhost
export no_proxy=127.0.0.1,localhost
cd "$STAGE_WORKTREE"
"$STAGE_WORKTREE/.venv/bin/code-verifier" evaluate \
  --config configs/eval/base.yaml \
  --dataset-dir "$CODE_VERIFIER_DATA_ROOT/prepared" \
  --sft-run-dir "$CODE_VERIFIER_ARTIFACT_ROOT/sft/B-sft-formal-seed42" \
  --run-name B-sft-formal-seed42 \
  --seed 42
```

**restart policy**：`exact_rerun`。无 tracked 修改的环境中断复用同一 immutable script，evaluation exact-prefix resume跳过已完成 rows；若 tracked修复改变 identity，旧 incomplete B evaluation移到 persistent unique quarantine并记录，再生成新 checkpoint/script fresh，禁止删除/覆盖。

**B resume acceptance**
- status rc=0 + `run.json.status=completed`；400 unique IDs与 Base A exact set相同；dataset hash/eval definition/seed/decode/Piston semantics相同，checkpoint严格绑定 completed B。
- `samples/results.jsonl`保留 completion/code、三层 verdict、parser/execution/error category、generation latency、hit_max_new_tokens；non-sample artifacts payload-free。
- summary/main_results finite，含 B Pass@1/bootstrap CI/gap/error/status aggregates。
- 同命令 quick exact-prefix resume报告 `resumed=400, generated=0`。
- A/B source identities可被现有 analysis strict loaders消费；不得提前写 C/D/final conclusion。

## 6. 总体验收

- durable identity regression：删除 fixture 的原 Piston YAML 后，A–D strict analysis仍可由 persisted digest验证；digest/config tamper仍 fail closed。
- 真实已有 Base A 在旧 `.worktrees/wp5-c` 不存在的情况下 strict readback通过，且 A artifact零修改。
- formal data 2500/300/400与1536长度约束通过；正式模型/revision/LoRA/optimizer定义冻结。
- 2-step exact-model BF16 smoke证明 Trainer telemetry/checkpoint/analysis loader合同。
- formal SFT只由用户终端运行；trainer checkpoint恢复政策有效；正式曲线、成本、CUDA峰值、attempt history、中间checkpoints、final adapter完整。
- B full evaluation只由用户终端运行；400题、exact-prefix resume、A/B pairing与durable Piston identity通过。
- `make lint`、`make test`、`make test-gpu`、真实 `make test-piston` 全绿。
- 不修改 `third_party/open-r1`，不重跑/改写 Base A，不进入 C/D。

## 7. Execution Routing

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
    - "durable identity修复必须先用现有Base A验证，之后SFT instrumentation→真实2-step smoke→formal SFT→completed B strict reload→B evaluation严格串行，后一步消费前一步真实artifact identity。"
    - "正式训练昂贵且一次运行必须采全遥测；单一 difficult-serial execution最能避免identity/config/operator checkpoint漂移。"
  workstream_candidates: []
```

## 8. Handoff

- 本计划是对纯 PLANNED `WP6-d` 的显式 pre-execution replan；旧 stage `HEAD` 仍等于旧 plan seal，无 completed E0/review，因此允许由 `stage-lifecycle bootstrap_plan` 删除旧 plan-only worktree/branch并从同一 `main` base重新封存。
- bootstrap 成功后立即调用 `$execution-router backend=web`。
- executor 必须先完成步骤 1 durable identity修复并用真实 Base A readback证明，然后才允许继续 SFT instrumentation/smoke。
- 到 formal SFT/B evaluation gate 必须停在 operator checkpoint，不由 Web GPT/CodexPro 启动长命令。
