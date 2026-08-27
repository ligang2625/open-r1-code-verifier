# WP7-c 实施计划（Formal Public/Hidden GRPO C/D validation、paired provenance 与 staged C/D 统一评测）

## 1. 元信息

| 项 | 值 |
|---|---|
| stage_id | `WP7-c` |
| stage_profile | `validation` |
| control_plane_hardware | `GTX 1660 Ti (6GB)` |
| target_hardware | `24GB GPU` |
| evidence_class | `real-training/numerical` |
| development_terminal | `false` |
| 目标 WP | `WP7`：正式 Public GRPO C / Hidden GRPO D 训练、checkpoint/reward/cost evidence 与 staged unified evaluation |
| 规格依据 | `PROJECT_SPEC_Open-R1_CodeVerifier.md` §12.1–§12.4、§13、§19.2.2、§20.0、WP7、§21、§29 |
| 前置状态 | `proceedings.md`：WP7-a / WP7-b development 已 finalized；合法 Development Complete Record 已存在；WP6-d 已 finalized，正式 SFT B 已成为后续 C/D 的共同 baseline；proceedings 明确下一 validation dependency 转入 WP7 C/D。 |
| `planning_base_commit` | `aebe85f7c15baedba182d8c811fdf8a4af0a019b` |
| proposed branch | `feat/wp7-c` |
| proposed worktree | `.worktrees/wp7-c` |
| final plan path | `ai-work/planner/WP7-c-plan.md` |
| execution report path | `ai-work/executor/WP7-c-executor.md` |
| review path | `ai-work/reviewer/WP7-c-review.md` |
| plan lifecycle | planner-ex handoff → `stage-lifecycle bootstrap_plan` → committed plan seal |

### Stage selection basis

当前 main 已完成 WP7-a/WP7-b 的 GRPO control-plane、reward isolation、resume、completed GRPO identity、`A → merge B → C/D adapter` reload 与 unified evaluation development；WP6-d 又已产生正式 B 并明确把后续 validation 依赖交给 WP7 C/D。因此下一 dependency-ready 正式 stage 是新的 `WP7-c`，而不是重新做 WP7 implementation，也不是提前进入 WP8 final A–D analysis。

规划时在 GTX 1660 Ti 做了只读 source verification：
- formal `public_grpo.jsonl`：2500 rows，SHA256 `94ef48888d2b2edaa0080b9b412c274ada692c9546fe135572d48ab20fd49223`；
- formal `hidden_grpo.jsonl`：2500 rows，SHA256 `79af3c2a3742e0cda8d02901a07241afce12a54c0b6d334e3012bcd0b69f77f7`；
- 当前 production `validate_grpo_artifact_pair()` 对这两份 formal artifacts PASS；
- 正式 B strict identity：run `B-sft-formal-seed42`，model `Qwen/Qwen2.5-Coder-1.5B-Instruct@2e1fd397ee46e1388853d2af2c993145b0f1098a`，seed 42，dataset hash `4b90cf95de2d8f12bdc98decbfb712b8eacf5987b02b02b868075ed9ca69eb0c`，config hash `250fbc15ececb040d2b90d3cb1606e412d1256e10ab9063c073c4ad2b1fb5244`，dependency lock hash `59e6292f72bdc6f7f9d889d1969d87715c83ccb09ed95766a50f81d9d762d560`；
- canonical B evaluation：400 rows，dataset hash `770b772c738514888c5900f815fc074ddb3f6c3c5f67fc5346073565536138ae`，ordered problem IDs SHA256 `2d811d62613c122da6ee73f372008e44a40464ec9ad7c8df628ae01de4a234c9`，Piston definition SHA256 `f049f4ea344285e2b732bb2a602e7c8888ae3ac449320039144c8a0dff62657e`。

## 2. 目标与范围

### 正式实验图

```text
        ┌→ C = Public GRPO (visible_tests only)
A → B ──┤
        └→ D = Hidden GRPO (train_hidden_tests only)
```

C 与 D 在 smoke、pilot、formal 三个 phase 都必须分别从**同一个正式 completed B** fresh 初始化或恢复各自 same-run trainer checkpoint。禁止把 C adapter/checkpoint/optimizer state 作为 D parent，禁止 `B → C → D`。4090 上先执行 C 再执行 D仅是单卡调度顺序，不构成训练依赖。

### C/D 公平性不变量

- 同一个 B identity、同一 2500 training problems/order、同一 prompt input、同一 visible tests、同一 metadata、同一 seed 42。
- 同一 `num_generations=4`、max prompt 1024、max completion 512、batch 1、grad accumulation 8、LR `5e-6`、warmup `.05`、cosine、temperature `.8`、top-p `.95`、beta `.01`、BF16、gradient checkpointing、LoRA r16/alpha32/dropout.05、logging 1。
- C reward 只能读取 `visible_tests`；D reward 只能读取 `train_hidden_tests`；两者都不得把 `eval_hidden_tests`、reference solution、starter code、SFT response放入 trainer/reward/log path。
- 根据 spec §12.2：先做 **20-step paired smoke**，再做 **固定 100-step paired pilot**（合法的 50–100 范围上界，用于完整观察两个 save cadence），reward/generation behavior正常后才做正式 **300-step** run。smoke/pilot 只属于 validation gating，不作为正式 C/D checkpoint/研究指标。
- C/D 正式 evaluation 使用同一 400 formal test set、seed 42、deterministic decoding、Piston definition 与 existing evaluator/aggregator；reward mode 不进入 evaluator 分支。

### 本 stage 交付

1. 给 `train-grpo` 增加 paired、portable 的 formal dataset/run-name binding，避免 checked-in development YAML 的 repo-local smoke path被正式训练误用。
2. 增加 payload-free `paired_definition_sha256`，使 C/D 每个 run 能事后证明训练前验证的是同一完整 pair，并把该 identity纳入 resume/completed checkpoint/evaluation checkpoint identity。
3. 补齐 spec §12.3 formal GRPO durability 中当前 production path缺失的 telemetry：attempt/cumulative GPU-hours、GPU count/semantics、peak CUDA allocated/reserved、global step，以及 all-finite trainer scalars；继续使用既有 rollout/reward/group logs得到 reward components、group std/all-equal、completion length/truncation、parse/execution/timeout/pass/runtime等。
4. 用户在4090 exact tracked scripts中执行 paired 20-step smoke、paired 100-step pilot、paired 300-step formal C/D。
5. 4090 对 completed formal C/D 各生成一次完整 400-row deterministic frozen generation bundle；不在4090等待Piston verification。
6. generation bundles同步回1660 Ti后，用 real local Piston完成 C/D `verify-eval`，再 `aggregate-eval`；形成 canonical C/D evaluation 与 WP8 可消费的 pairing/readiness evidence。

### 范围外

- 不重跑、改写或删除 Base A、SFT B、WP6-d export/verified/operator artifacts。
- 不做 WP8 final `analyze-results`、人工20-case analysis、最终 A–D 结论/论文表格/figure；这些在 C/D finalized 后另行规划。
- 不做超参搜索、多 seed、quantization、vLLM、DeepSpeed redesign、dependency upgrade 或 `third_party/open-r1/**` 修改。
- 不 push。

## 3. 前置条件与约束

- authoritative repository 仅 `/home/dzy/open-r1-code-verifier`；planning base固定当前 main `aebe85f7c15baedba182d8c811fdf8a4af0a019b`。
- control-plane formal data固定 `/home/dzy/wp6d-b-export/required/formal-data/prepared`；formal B source固定 `/home/dzy/wp6d-b-export/recommended_backup/sft/B-sft-formal-seed42`。这些1660路径可用于executor readback，但4090 script不得硬编码；target只从 machine record解析 `$CODE_VERIFIER_DATA_ROOT` / `$CODE_VERIFIER_ARTIFACT_ROOT` / `$HF_HOME`。
- pinned runtime保持 TRL 0.18.0 / Transformers 4.52.3 / Accelerate 1.4.0 / PEFT 0.14.0 / current locked torch / pinned Open-R1。
- canonical Piston host是 `1660ti-wsl`。4090 GRPO reward只允许使用既有 SSH local forward后的loopback `127.0.0.1:2000`；generation不需要live Piston，但必须绑定exact Piston definition SHA。
- formal optimizer checkpoints不写stage worktree。numeric `checkpoint-*`默认留4090；operator evidence、必要小型 run metadata/log/final LoRA adapter与完整 generation bundles按合同同步回1660。

### Execution preflight（首次业务修改/commit 前；全部在 GTX 1660 Ti）

1. **Git/source binding**：stage `HEAD == plan_commit`；primary/stage `.ai-bridge/**` zero-tracked；stage `.venv` ruff/mypy/pytest可用；`code_verifier.__file__` / `open_r1.__file__`解析到stage checkout。
2. **Pinned GRPO API**：exact版本导入；bounded introspection确认 `GRPOTrainer`、Open-R1 GRPOConfig、PEFT read-only load/safe merge、Trainer telemetry flags的当前接口。若某 telemetry flag在 pinned版本不存在，停止并按现有API做等价project-owned采集，不升级依赖。
3. **Formal data**：对 `/home/dzy/wp6d-b-export/required/formal-data` 现有checksums只读验证；`check-data`确认3200=2500/300/400；strict load Public/Hidden 2500 rows，pair validator PASS，并重算上述two SHA。
4. **Formal B**：`load_completed_sft_checkpoint()` strict load上述B archive，逐字段匹配sealed identity；canonical B evaluation仍completed 400且test dataset/order/Piston SHA匹配上述值。
5. **Piston/GPU baseline**：real local `make test-piston PISTON_CONFIG=configs/execution/piston-local.yaml`要求9/9、0 skipped；`make test-gpu`要求GTX1660Ti current smoke全绿。此处不启动4090。
6. **Baseline tests**：至少GRPO/CLI/GRPO-checkpoint/staged-evaluation相关unit+integration全绿。

任一 preflight失败：停止本次execution并保持 `HEAD == plan_commit`；修复环境后重新调用execution-router。4090 READY/VRAM/target roots/model cache不属于此preflight。

## 4. 实施步骤

### 步骤 1：formal paired CLI binding

**目标文件**：`src/code_verifier/cli.py`、`tests/unit/test_cli.py`、README最小说明。

- `train-grpo`新增 `--dataset-dir <prepared>`：一次性把Public/Hidden dataset分别绑定为 `<prepared>/training/public_grpo.jsonl` / `hidden_grpo.jsonl`，禁止只override单侧。
- 新增 `--public-run-name SAFE_NAME` 与 `--hidden-run-name SAFE_NAME`；必须同时提供或同时省略。formal operator每次C/D invocation都传同一pair names，使完整resolved pair一致，唯一选择差异仅 `--reward-mode`。
- override发生在selected config/seed/Piston/training orchestration之前；stderr只打印old→new path/name，不打印payload。
- 不新增model/hyperparameter override；不改变现有 hardware guard/model-load boundary；1660 formal pair prevalidation使用strict loaders/helpers而不是尝试optimizer entry。
- old CLI无override工程行为保持兼容。

formal names固定：`C-public-grpo-formal-seed42` / `D-hidden-grpo-formal-seed42`。

### 步骤 2：持久化 paired-definition provenance，并纳入 resume/checkpoint identity

**目标文件**：`src/code_verifier/training/grpo.py`、`tests/unit/training/test_grpo.py`，必要时GRPO evaluation identity tests。

新增稳定non-sensitive canonical pair identity，至少绑定：
- effective Public/Hidden resolved config hashes；
- Public/Hidden dataset byte SHA256；
- seed；
- strict completed B non-sensitive identity（run/model/revision/data/config/dependency/seed/checkpoint path identity）；
- pair schema/version。

`run.json`保存 `paired_definition_sha256` 及必要payload-free component hashes。Public和Hidden在同一phase必须得到同一pair hash；fresh/resume都重算exact-match，任一counterpart config/data/B drift后不得错误resume。

把 `paired_definition_sha256` 加入 `GRPOCheckpointIdentity` 与 `grpo_evaluation_checkpoint_id()` canonical payload；`load_completed_grpo_checkpoint()`要求合法64-hex并fail closed。identity不得持久化tests/prompt/completion。

### 步骤 3：补 formal GRPO telemetry/cost durability，不改变训练数学定义

**目标文件**：`src/code_verifier/training/grpo.py`、`tests/unit/training/test_grpo.py`；复用WP6-d SFT模式但不新建通用framework。

- `run.json`增加 `gpu_count_used`、明确 `gpu_hours_semantics`、append-only attempt history：attempt start/end/status/resume checkpoint/attempt GPU-hours；cumulative GPU-hours必须finite/nonnegative且可复算。
- model/trainer前reset CUDA peak；成功或失败都保存peak allocated/reserved bytes。
- 保存final `global_step`；Trainer log history所有持久化numeric scalars必须finite；final `train_result.metrics` 的finite numeric scalars进入summary。
- 若pinned GRPOConfig支持，则显式设置 `skip_memory_metrics=False`、`logging_nan_inf_filter=False`、`save_total_limit=None`、`save_only_model=False`；不支持时只用project-owned等价采集，禁止升级依赖。
- 不改变既有 reward math。继续使用 `rollouts.jsonl` / `rewards.jsonl` / `group_metrics.jsonl`，使spec §12.3中的total/component reward、group mean/std/all-equal、completion length/truncation、parse/execution/timeout/pass/runtime等能由production artifacts重算；KL/step time等使用pinned trainer实际提供的finite scalars。
- `build_cost_row()` 与 `load_training_curve_rows()`必须能直接消费completed smoke/pilot/formal C/D；non-sample artifacts继续payload-safe。

### 步骤 4：封存 paired validation smoke/pilot configs

新增：
- `configs/grpo/validation-smoke-public.yaml`
- `configs/grpo/validation-smoke-hidden.yaml`
- `configs/grpo/validation-pilot-public.yaml`
- `configs/grpo/validation-pilot-hidden.yaml`

每个phase内Public/Hidden除 `run_name/reward_mode/dataset_path` 外完全相同。
- smoke：`max_steps=20`；允许 `save_steps=10` 只为短gate interruption recovery。
- pilot：固定 `max_steps=100`；`save_steps=50`。
- formal：继续使用已finalized main `public.yaml` / `hidden.yaml`，`max_steps=300`、`save_steps=50`，其它formal超参零变化。
- smoke/pilot/formal target execution全部显式 `--dataset-dir "$CODE_VERIFIER_DATA_ROOT/prepared"`，不把repo-local development dataset当formal data。

### 步骤 5：control-plane acceptance 与第一 operator checkpoint

在1660 Ti完成：focused新旧GRPO/CLI/checkpoint/staged-eval tests；`make lint`、`make test`、`make test-gpu`、real `make test-piston`；formal B/data/pair hashes重验；config pair fairness重验；无critical stub/TODO/fake进入formal path。所有业务代码/config/tests/docs commit且stage clean后，生成第一份tracked portable `grpo-cd-smoke` operator checkpoint并停止。

### 步骤 6：4090 paired 20-step smoke

用户手工运行exact `grpo-cd-smoke` script。Public/Hidden两个subrun分别从同一B fresh/resume自己的same-run trainer checkpoint；Hidden不得引用Public run。两者completed、global step20、real reward/Piston/telemetry/adapter/postcheck全部PASS后，用户同步evidence回1660并resume。

### 步骤 7：4090 paired 100-step pilot

smoke resume strict通过后，由executor生成新的`grpo-cd-pilot` checkpoint并停止。用户手工运行两组100-step pilot，同样从B独立初始化。postcheck必须输出spec §12.4相关reward std/all-equal、parse/execution/timeout/truncation、KL/loss等实际finite telemetry；NaN/Inf、Public/Hidden实际同测试源、hard sandbox/identity failure直接fail closed。对“明显下降/过高/异常增长”等spec未给数值阈值的条件不得擅自发明新阈值；executor在resume时基于原始指标记录是否存在明确停止信号，若存在则停止formal并记录，不自行调参。

### 步骤 8：4090 formal C/D 300-step training

pilot resume通过且无spec §12.4明确停止信号后，executor生成`grpo-cd-formal` checkpoint。正式C/D各300 steps，分别从同一个B fresh初始化/各自same-run resume。completed run必须具有相同 `paired_definition_sha256`、相同parent B/seed/project/Open-R1/dependency pair context；reward source严格public vs hidden。checkpoint、curve、reward/group、cost、attempt/GPU peak evidence全部验收后才允许generation。

### 步骤 9：4090 C/D deterministic generation bundles

formal training resume strict通过后，executor生成`grpo-cd-generate-eval` checkpoint。4090仅对completed C/D执行 `generate-eval`，各400 deterministic completions；不执行Piston verification。bundle必须绑定 model/revision/GRPO checkpoint+parent B+paired-definition identity、seed42、ordered dataset、decode config、Piston definition SHA、project commit、Open-R1 commit、dependency identity、records SHA。target postcheck还要做exact-prefix quick readback `resumed=400, generated=0`。用户同步**完整C/D generation bundles**与evidence回1660后resume。

### 步骤 10：1660 Ti real Piston verification、aggregation 与 WP7-c completion

在generation operator checkpoint commit仍是stage HEAD时，先验evidence/bundle/current-code identity，再在stage外fresh persistent control-plane root（推荐 `/home/dzy/wp7c-verified`，execution开始时记录实际路径）执行C/D `verify-eval` + `aggregate-eval`。

要求：
- each `verify-eval` 400 rows；再次exact-prefix readback `resumed=400, verified=0`；
- C/D evaluation dataset hash=`770b772c...38ae`、ordered IDs SHA=`2d811d...34c9`、Piston SHA=`f049f4...657e`、seed42、decode/split/evaluator与A/B一致；
- aggregate结果finite并可追溯400 rows；
- C/D checkpoint identities分别strict绑定formal C/D且共同绑定同一B/pair identity；
- small synced training evidence可由curve/cost/reward loaders消费且无eval-hidden泄漏。

本stage只记录C/D正式数值与pairing readiness，不运行WP8最终A–D `analyze-results`。全部验收通过后写completed execution E0，然后停止并交给**新的独立conversation**运行reviewer-ex。

## 5. Operator terminal execution

```yaml
operator_terminal_execution:
  version: 1
  required: true
  gates:
    - gate_id: grpo-cd-smoke
      run_kind: grpo
      executor_runs_command: false
      restart_policy: trainer_checkpoint
      expected_artifacts:
        - "$CODE_VERIFIER_ARTIFACT_ROOT/grpo-validation/smoke/C-public-grpo-smoke20-seed42/run.json"
        - "$CODE_VERIFIER_ARTIFACT_ROOT/grpo-validation/smoke/C-public-grpo-smoke20-seed42/checkpoints/adapter_model.safetensors"
        - "$CODE_VERIFIER_ARTIFACT_ROOT/grpo-validation/smoke/D-hidden-grpo-smoke20-seed42/run.json"
        - "$CODE_VERIFIER_ARTIFACT_ROOT/grpo-validation/smoke/D-hidden-grpo-smoke20-seed42/checkpoints/adapter_model.safetensors"
    - gate_id: grpo-cd-pilot
      run_kind: grpo
      executor_runs_command: false
      restart_policy: trainer_checkpoint
      expected_artifacts:
        - "$CODE_VERIFIER_ARTIFACT_ROOT/grpo-validation/pilot/C-public-grpo-pilot100-seed42/run.json"
        - "$CODE_VERIFIER_ARTIFACT_ROOT/grpo-validation/pilot/C-public-grpo-pilot100-seed42/checkpoints/adapter_model.safetensors"
        - "$CODE_VERIFIER_ARTIFACT_ROOT/grpo-validation/pilot/D-hidden-grpo-pilot100-seed42/run.json"
        - "$CODE_VERIFIER_ARTIFACT_ROOT/grpo-validation/pilot/D-hidden-grpo-pilot100-seed42/checkpoints/adapter_model.safetensors"
    - gate_id: grpo-cd-formal
      run_kind: grpo
      executor_runs_command: false
      restart_policy: trainer_checkpoint
      expected_artifacts:
        - "$CODE_VERIFIER_ARTIFACT_ROOT/grpo/C-public-grpo-formal-seed42/run.json"
        - "$CODE_VERIFIER_ARTIFACT_ROOT/grpo/C-public-grpo-formal-seed42/resolved_config.yaml"
        - "$CODE_VERIFIER_ARTIFACT_ROOT/grpo/C-public-grpo-formal-seed42/environment.json"
        - "$CODE_VERIFIER_ARTIFACT_ROOT/grpo/C-public-grpo-formal-seed42/metrics.jsonl"
        - "$CODE_VERIFIER_ARTIFACT_ROOT/grpo/C-public-grpo-formal-seed42/rollouts.jsonl"
        - "$CODE_VERIFIER_ARTIFACT_ROOT/grpo/C-public-grpo-formal-seed42/rewards.jsonl"
        - "$CODE_VERIFIER_ARTIFACT_ROOT/grpo/C-public-grpo-formal-seed42/group_metrics.jsonl"
        - "$CODE_VERIFIER_ARTIFACT_ROOT/grpo/C-public-grpo-formal-seed42/checkpoints/adapter_config.json"
        - "$CODE_VERIFIER_ARTIFACT_ROOT/grpo/C-public-grpo-formal-seed42/checkpoints/adapter_model.safetensors"
        - "$CODE_VERIFIER_ARTIFACT_ROOT/grpo/D-hidden-grpo-formal-seed42/run.json"
        - "$CODE_VERIFIER_ARTIFACT_ROOT/grpo/D-hidden-grpo-formal-seed42/resolved_config.yaml"
        - "$CODE_VERIFIER_ARTIFACT_ROOT/grpo/D-hidden-grpo-formal-seed42/environment.json"
        - "$CODE_VERIFIER_ARTIFACT_ROOT/grpo/D-hidden-grpo-formal-seed42/metrics.jsonl"
        - "$CODE_VERIFIER_ARTIFACT_ROOT/grpo/D-hidden-grpo-formal-seed42/rollouts.jsonl"
        - "$CODE_VERIFIER_ARTIFACT_ROOT/grpo/D-hidden-grpo-formal-seed42/rewards.jsonl"
        - "$CODE_VERIFIER_ARTIFACT_ROOT/grpo/D-hidden-grpo-formal-seed42/group_metrics.jsonl"
        - "$CODE_VERIFIER_ARTIFACT_ROOT/grpo/D-hidden-grpo-formal-seed42/checkpoints/adapter_config.json"
        - "$CODE_VERIFIER_ARTIFACT_ROOT/grpo/D-hidden-grpo-formal-seed42/checkpoints/adapter_model.safetensors"
    - gate_id: grpo-cd-generate-eval
      run_kind: evaluation
      executor_runs_command: false
      restart_policy: exact_rerun
      expected_artifacts:
        - "$CODE_VERIFIER_ARTIFACT_ROOT/generation/C-public-grpo-formal-seed42/run.json"
        - "$CODE_VERIFIER_ARTIFACT_ROOT/generation/C-public-grpo-formal-seed42/resolved_config.yaml"
        - "$CODE_VERIFIER_ARTIFACT_ROOT/generation/C-public-grpo-formal-seed42/environment.json"
        - "$CODE_VERIFIER_ARTIFACT_ROOT/generation/C-public-grpo-formal-seed42/samples/generations.jsonl"
        - "$CODE_VERIFIER_ARTIFACT_ROOT/generation/D-hidden-grpo-formal-seed42/run.json"
        - "$CODE_VERIFIER_ARTIFACT_ROOT/generation/D-hidden-grpo-formal-seed42/resolved_config.yaml"
        - "$CODE_VERIFIER_ARTIFACT_ROOT/generation/D-hidden-grpo-formal-seed42/environment.json"
        - "$CODE_VERIFIER_ARTIFACT_ROOT/generation/D-hidden-grpo-formal-seed42/samples/generations.jsonl"
```

### 通用 tracked portable operator contract

每个gate都由1660 executor在其前置acceptance后生成**一份且仅一份** tracked secret-free immutable `ai-work/executor/operator/WP7-c/<gate>/<checkpoint>/run.sh`。operator checkpoint commit parent=`result_code_commit`，且只提交execution report + 这份新script；workflow不push。用户使exact commit在4090可达、checkout/detach exact commit、确认clean、重算script SHA，再在SSH/tmux手工执行。Web GPT/CodexPro不得启动/监控4090 command。

script每attempt必须：验证stage/plan/result-code/operator-checkpoint/script SHA/Git clean、target READY machine record SHA、persistent roots、exclusive flock；GRPO gates再验证CUDA/VRAM>=22528MiB/native BF16、pinned runtime、exact 1.5B revision local-only、formal B identity、formal paired data hashes、`1660ti-wsl` Piston tunnel/loopback Python3.10.0；generation gate不要求live Piston，但Piston YAML definition SHA必须exact。

真实command rc必须被捕获；mandatory postcheck后只有 `command_rc=0 && postcheck_rc=0` 才写 `gate_status=passed`。每attempt产生versioned secret-free `operator-evidence.json`，绑定stage/gate/checkpoint、plan/result-code/operator commits、script path/SHA、machine-record SHA、GPU/roots/Piston identity、timestamps、rc/status、每个subrun formal identities、expected-artifact inventory及identity/metadata SHA。不得写credentials或training/eval test payload。

### `grpo-cd-smoke`

两条命令共用 exact pair/B/data，仅reward mode不同：

```bash
B_RUN="$CODE_VERIFIER_ARTIFACT_ROOT/sft/B-sft-formal-seed42"
code-verifier train-grpo \
  --public-config configs/grpo/validation-smoke-public.yaml \
  --hidden-config configs/grpo/validation-smoke-hidden.yaml \
  --dataset-dir "$CODE_VERIFIER_DATA_ROOT/prepared" \
  --public-run-name C-public-grpo-smoke20-seed42 \
  --hidden-run-name D-hidden-grpo-smoke20-seed42 \
  --public-sft-run-dir "$B_RUN" --hidden-sft-run-dir "$B_RUN" \
  --reward-mode public --seed 42 \
  --output-dir "$CODE_VERIFIER_ARTIFACT_ROOT/grpo-validation/smoke" \
  [--resume-from-checkpoint <C latest valid same-run checkpoint>]

code-verifier train-grpo <same pair/B/data/run-name args> \
  --reward-mode hidden --seed 42 \
  --output-dir "$CODE_VERIFIER_ARTIFACT_ROOT/grpo-validation/smoke" \
  [--resume-from-checkpoint <D latest valid same-run checkpoint>]
```

Operator-start storage最低：20 GiB free、100000 free inodes。postcheck要求C/D completed/global step20、finite telemetry、same B、same pair SHA、real nonempty rollout/reward/group logs、correct reward modes、payload safety、final adapters strict-loadable、curve/cost loaders成功；记录最大complete trainer checkpoint bytes/inodes `S/F`。

### `grpo-cd-pilot`

使用validation-pilot configs、run names `C-public-grpo-pilot100-seed42` / `D-hidden-grpo-pilot100-seed42`、output `$CODE_VERIFIER_ARTIFACT_ROOT/grpo-validation/pilot`，其余pair/B/data完全同smoke；C/D仍各自从B，不从smoke adapter继续训练。storage最低 `max(30 GiB, 6*S + 10 GiB)`，inodes `max(100000, 6*F + 20000)`。

postcheck要求global step100、finite telemetry、same B/pair SHA、reward-source isolation；输出§12.4相关raw metrics，不发明新停止阈值；记录pilot最大checkpoint `P/Fp`供formal storage gate。

### `grpo-cd-formal`

```bash
B_RUN="$CODE_VERIFIER_ARTIFACT_ROOT/sft/B-sft-formal-seed42"
code-verifier train-grpo \
  --public-config configs/grpo/public.yaml --hidden-config configs/grpo/hidden.yaml \
  --dataset-dir "$CODE_VERIFIER_DATA_ROOT/prepared" \
  --public-run-name C-public-grpo-formal-seed42 \
  --hidden-run-name D-hidden-grpo-formal-seed42 \
  --public-sft-run-dir "$B_RUN" --hidden-sft-run-dir "$B_RUN" \
  --reward-mode public --seed 42 --output-dir "$CODE_VERIFIER_ARTIFACT_ROOT/grpo" \
  [--resume-from-checkpoint <C latest valid same-run checkpoint>]

code-verifier train-grpo <same pair/B/data/run-name args> \
  --reward-mode hidden --seed 42 --output-dir "$CODE_VERIFIER_ARTIFACT_ROOT/grpo" \
  [--resume-from-checkpoint <D latest valid same-run checkpoint>]
```

storage最低 `max(40 GiB, 14*P + 10 GiB)`、inodes `max(100000, 14*Fp + 20000)`。postcheck要求C/D status completed/global step300、final adapters strict-load、same parent B/pair SHA、same seed/project/Open-R1/dependency context、formal hyperparameters一致、all numeric telemetry finite、curve/cost/reward/group artifacts可消费、payload安全。

Trainer checkpoint policy对C/D各自独立：run不存在→fresh；`running|failed`且有合法same-run numeric `checkpoint-*`→最大合法checkpoint resume；已completed的前置subrun只strict postcheck并skip。无合法checkpoint/损坏时fail closed，1660 resume后把旧incomplete run移到unique quarantine并生成新operator checkpoint；不得删除/覆盖。若identity-changing tracked repair导致pair code identity变化，则旧未完成formal pair不能与新代码下的另一member拼成最终C/D。

### `grpo-cd-generate-eval`

```bash
code-verifier generate-eval \
  --config configs/eval/base.yaml \
  --dataset-dir "$CODE_VERIFIER_DATA_ROOT/prepared" \
  --grpo-run-dir "$CODE_VERIFIER_ARTIFACT_ROOT/grpo/C-public-grpo-formal-seed42" \
  --run-name C-public-grpo-formal-seed42 --seed 42 \
  --output-dir "$CODE_VERIFIER_ARTIFACT_ROOT"

code-verifier generate-eval \
  --config configs/eval/base.yaml \
  --dataset-dir "$CODE_VERIFIER_DATA_ROOT/prepared" \
  --grpo-run-dir "$CODE_VERIFIER_ARTIFACT_ROOT/grpo/D-hidden-grpo-formal-seed42" \
  --run-name D-hidden-grpo-formal-seed42 --seed 42 \
  --output-dir "$CODE_VERIFIER_ARTIFACT_ROOT"
```

storage最低15 GiB、100000 inodes。restart=`exact_rerun`，各bundle按exact-prefix恢复；identity变化时旧incomplete bundle quarantine。postcheck两个bundle各400 unique ordered rows，dataset/order/seed/decode/Piston definition/model/checkpoint/pair/project/Open-R1/dependency/records SHA全部strict，target quick readback各`resumed=400, generated=0`。不执行Piston verification。

### Evidence / Resume

每个gate后用户把`operator-evidence.json`及必要small artifacts byte-for-byte同步回1660 Ti，再显式 `$execution-router resume backend=web stage_id=WP7-c`。generation gate还必须同步完整C/D generation bundle。resume重算evidence/bundle SHA并绑定current checkpoint。numeric trainer checkpoints默认留4090；证据不足才允许短时只读target check。

## 6. 总体验收与测试计划

- **Unit/integration**：paired CLI overrides、single-sided run-name reject、pair hash drift/resume、checkpoint/eval identity binding、attempt/GPU telemetry、smoke/pilot config fairness、existing reward/checkpoint/staged-eval regressions。
- **Control plane**：`make lint`、`make test`、`make test-gpu`、real `make test-piston` 9/9；formal B/data hashes strict重验。
- **Target smoke**：C/D各20 steps，real Piston reward path、finite logs/adapter/cost证据；不作formal result。
- **Target pilot**：C/D各100 steps，收集§12.4 raw stop-condition telemetry；不作formal result，不调参。
- **Target formal**：C/D各300 steps，从同一B独立启动；checkpoint/reward/curve/cost/attempt/GPU peak完整。
- **Target generation**：C/D各400 deterministic frozen completions；4090不等待Piston。
- **Control-plane evaluation**：1660 local Piston verify C/D各400，exact-prefix 400/0；aggregate finite；identity fail closed。
- **最终标准**：
  - [ ] C/D所有phase都从同一formal B独立启动；无C→D parent chain
  - [ ] C只读visible、D只读train-hidden；训练路径无eval-hidden
  - [ ] 20-step smoke、100-step pilot、300-step formal按spec完成且未改变formal hyperparameters
  - [ ] formal C/D checkpoint、paired-definition、training/reward/cost telemetry完整
  - [ ] C/D generation bundle各400/400并完整绑定跨机identity
  - [ ] 1660 real Piston verification+aggregation各400完成
  - [ ] C/D evaluation与A/B共享同400题/order/seed/decode/Piston/evaluator definition
  - [ ] `make lint` / `make test` / `make test-gpu` / real `make test-piston`全绿
  - [ ] 未修改third_party/dependency/A/B artifacts，未进入WP8 final analysis，未push

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
    - "formal binding/provenance/telemetry必须先在1660Ti完成并封存，随后paired smoke→pilot→formal→generation→1660 verification逐gate消费前一真实evidence，存在严格串行provenance依赖。"
    - "C/D虽是两个独立B分支，但公平性要求同一sealed pair definition/B/data/code identity且只有一张4090；拆成不同stage或并行executor会增加pair drift与错误parent风险。"
  workstream_candidates: []
```

## 8. 风险与注意事项

- 任何D command/run metadata/postcheck若引用C checkpoint作为parent立即fail closed。
- 不因OOM/结果不好只修改C或D；formal hyperparameter改变必须同时对pair并重新规划，当前stage不得自行做。
- pilot停止条件中spec未定义数值阈值的项目只报告原始指标，不擅自创造阈值；NaN/Inf、same-test-source、identity/sandbox hard failure直接阻断formal。
- generation bundle由generation operator checkpoint commit产生；同步回1660后必须在该checkpoint HEAD上先verify/aggregate，再提交新的completed execution report，否则current-code identity guard会正确失败。
- numeric checkpoints留4090；small identity/log/final LoRA adapter与generation bundles按evidence contract同步。control-plane evaluation必须写stage worktree外persistent root。
- 本stage可以记录C/D正式individual metrics与pairing readiness，但最终A–D paired bootstrap/error analysis/cost conclusion/report/figures属于下一validation stage。

## 9. 关联文档索引

- `PROJECT_SPEC_Open-R1_CodeVerifier.md`：§12.1–§12.4、§13、§19.2.2、§20.0、WP7、§21、§29
- `proceedings.md`：Development Complete Record、WP7-a、WP7-b、WP6-d、workflow amendments
- `README.md`：1660 control plane / 4090 worker / staged formal evaluation
- `AGENTS.md`：GRPO fairness/reward boundary、portable operator、Piston/staged-eval invariants
- `src/code_verifier/training/grpo.py`
- `src/code_verifier/evaluation/staged.py`
- `ai-work/planner/WP7-a-plan.md`
- `ai-work/planner/WP7-b-plan.md`
- `ai-work/planner/WP6-d-plan.md`

## 10. Handoff

- 下一步运行 `$stage-lifecycle bootstrap_plan`，从exact planning base创建/复用 `feat/wp7-c` + `.worktrees/wp7-c`，bootstrap stage-local `.venv`，只把本计划写入并commit `ai-work/planner/WP7-c-plan.md` 作为plan seal，然后消费`.ai-bridge/current-plan.md`。
- bootstrap成功后本次任务停止在`PLANNED` lifecycle boundary；**不要调用execution-router、不要训练、不要生成或执行任何4090 command**。
- 下一次execution入口显式 `$execution-router backend=web stage_id=WP7-c`；executor在1660完成implementation/preflight/tests，遇到第一24GB gate时生成tracked portable run.sh并停在`AWAITING_OPERATOR`。
- execution完成后必须在新的独立conversation运行reviewer-ex；execution conversation不得自review。
