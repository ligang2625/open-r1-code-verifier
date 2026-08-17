# WP5-c 实施计划（Formal Base A validation、正式数据绑定与 operator terminal handoff）

## 1. 元信息

| 项 | 值 |
|---|---|
| stage_id | `WP5-c` |
| stage_profile | `validation` |
| target_hardware | `24GB GPU` |
| evidence_class | `real-training/numerical` |
| development_terminal | `false` |
| 目标 WP | `WP5`：统一评测的正式 Base A 数值验收 |
| 规格依据 | `PROJECT_SPEC_Open-R1_CodeVerifier.md` §4.2–§4.3、§18.2–§18.3、§19.2.2、§20.0、WP5、§21.5、§29；`proceedings.md` Development Complete Record、4090 machine-state 与 operator-terminal amendments |
| 前置状态 | WP0–WP8 development 已 finalized；4090 machine state READY；validation 固定从 Base A 开始；旧 `WP5-c` pending handoff 尚未 bootstrap，本次按用户明确要求以新 operator workflow 覆盖重规划 |
| `planning_base_commit` | `76490ad0b94ae40532accde2b47ec924fecd8e45` |
| proposed branch | `feat/wp5-c` |
| proposed worktree | `.worktrees/wp5-c` |
| final plan path | `ai-work/planner/WP5-c-plan.md` |
| execution report path | `ai-work/executor/WP5-c-executor.md` |
| review path | `ai-work/reviewer/WP5-c-review.md` |
| plan lifecycle | planner-ex handoff → `stage-lifecycle bootstrap_plan` → execution-router → operator checkpoint → 用户终端 → `execution-router resume backend=web` → completed E0 |

## 2. 目标与范围

### 目标（规格）

在已经完成 development closeout 的 RTX 4090 validation machine 上，使用正式 3,200 题数据包中的 **400 题 test split**、固定 Base 模型 `Qwen/Qwen2.5-Coder-1.5B-Instruct@2e1fd397ee46e1388853d2af2c993145b0f1098a`、deterministic Pass@1 和真实 loopback Piston，产生正式实验组 **A（Base）** 的逐题结果、聚合指标、problem-level bootstrap CI 与错误类型统计；这些结果成为后续 B/C/D 必须对齐的数据集、seed 与 evaluation-definition 基线。

当前 committed `configs/eval/base.yaml` 仍使用 development/smoke `dataset_dir`，而正式 validation 的数据根由 router 从 `.ai-bridge/validation-machine.json` 注入 `$CODE_VERIFIER_DATA_ROOT`。本 stage 只增加一个最小、显式、可审计的 `evaluate --dataset-dir` CLI override，使 A/B/C/D 后续统一评测可以绑定同一个正式 prepared dataset；不重构 evaluation layer，不改变评测算法、模型、decode 参数或指标定义。

正式 400 题 Base A 全量评测是长时间 GPU+Piston 工作，**必须使用 operator terminal gate**，本 gate 固定 `restart_policy=exact_rerun`：executor 负责代码、配置、preflight、短测试和生成 persistent immutable `run.sh`，但不得自己持有长时间 tool call 运行 400 题。用户在普通终端运行 exact script，完成或失败后在当前 Web GPT + CodexPro runtime 显式 `$execution-router resume backend=web`，executor 再读取真实 persistent artifacts 完成验证/诊断；环境中断优先保持同一 operator checkpoint/HEAD 并重跑同一 script，由 evaluation exact-prefix resume 接管。

### 交付

- `evaluate --dataset-dir <prepared-root>` 显式 override；默认不传时保持现有 config 行为；
- override 发生时 stderr 打印旧/新 dataset path，符合“CLI override 必须打印”的规格；
- persistent operator script/status/log + append-only `execution_checkpoint(interruption_class=operator,status=awaiting_operator)`；
- 用户终端执行的正式 Base A persistent evaluation run：400 test problems、seed 42、Base checkpoint、固定 model revision、FP16、deterministic generation；
- 正式 `samples/results.jsonl`、`run.json`、`resolved_config.yaml`、`environment.json`、`metrics.jsonl`、`summary.json`、`main_results.csv`；
- 正式 Base Eval-Hidden Pass@1、95% problem-level bootstrap CI、public-eval gap、error categories 与 execution statuses；
- completed run 的 exact-prefix resume 验证：`resumed=400, generated=0`；
- execution report 记录 operator checkpoint provenance、persistent artifact 绝对路径、dataset/config/model identity 与正式数值。

### 验收

- 正式 A run 使用 `$CODE_VERIFIER_DATA_ROOT/prepared` 的 test split，恰好 400 个唯一 `problem_id`；
- Base model/revision 与 bootstrap readiness 完全一致；`checkpoint=base`；seed=42；`do_sample=false`、`temperature=null`、`top_p=null`、`max_new_tokens=512`、`dtype=float16`；
- Piston endpoint 仍是 `http://127.0.0.1:2000`，Python runtime 3.10.0，real-Piston acceptance 0 failed / 0 skipped；
- operator script 由 executor 生成、secret-free、SHA256 绑定 checkpoint；用户终端而非 executor 运行正式长任务；
- operator resume 后 `run.json.status == completed`，strict artifact/readback 全部通过；所有 aggregate 数值 finite，bootstrap 单位为 problem；
- completed run 同命令 quick resume 报告 `resumed=400, generated=0`；
- `make lint`、`make test`、`make test-gpu`、`make test-piston` 全部通过；
- synthetic/mock/fixture 或用户口头“跑完了”不得替代真实 evidence。

### 范围内 / 范围外

- 范围内：最小 `evaluate --dataset-dir` override、对应 CLI tests/README、operator handoff、正式 Base A 评测和 numerical evidence。
- 范围外：SFT B 训练、`max_seq_length=1536` 封存、B evaluation、Public/Hidden GRPO C/D、C/D evaluation、最终 A–D analysis、manual 20-case conclusions。
- `open-r1-code-verifier-data-4090/external/humanevalplus_157_24tests.jsonl` **不进入 A–D 主结果**；若以后使用，只能作为单独 auxiliary robustness evaluation。
- 不修改 `third_party/open-r1/**`。

## 3. 前置条件与约束

- Planner active-stage guard：重规划时只有 primary `main` worktree，没有未合并 active stage branch/worktree；旧 `.ai-bridge/current-plan.md` 是尚未 bootstrap 的 pending handoff，用户本轮已明确要求替换，因此允许覆盖。
- `.ai-bridge/**` zero-tracked 且 ignored；正式 stage provenance 仍只进入 `ai-work/**`。
- 合法 `Development Complete Record`：terminal stage `WP8`，`completion_inventory_verified=true`、`development_complete=true`。
- 4090 machine record：`.ai-bridge/validation-machine.json` version 1、`machine_status=READY_FOR_VALIDATION_PLANNER`，bootstrap project commit `9174c8e3afca9315426e83c365414c412596e394`；该 commit 是本次 `planning_base_commit` 的祖先。
- Planner-time pinned PyTorch：`2.6.0+cu124`、CUDA 12.4、RTX 4090、约 `24210 MiB` VRAM，满足 `>=22528 MiB` validation gate；`flock=/usr/bin/flock` 可用。
- 本轮 robustness review 已实际重验：`make lint` PASS；使用 readiness exact snapshot path 的 `make test` 为 881 passed / 3 expected Piston skips；同 snapshot 的 `make test-gpu` 为 3/3 passed；real tunneled `make test-piston` 为 9/9 passed、0 skipped；正式数据 `check-data` 为 3200 problems（2500/300/400）。这些只证明 planner-time machine readiness，executor/operator-start 仍须按下面 preflight 重验。
- 当前 persistent artifact filesystem 约有 108 GiB 可用空间、约 283M free inodes；本 stage Base A 输出远低于该量，但 operator-start 仍必须实时重验 writable/free-bytes/free-inodes，不能依赖本次 planner-time 数字。
- Router 提供的 `artifact_root / hf_home / formal_data_root` 是唯一正式 machine roots；所有真实命令显式使用 `CODE_VERIFIER_ARTIFACT_ROOT`、`HF_HOME`、`CODE_VERIFIER_DATA_ROOT`。4090 的 GPU smoke 还必须把 `CODE_VERIFIER_GPU_MODEL` 指向 readiness exact revision 对应的本地 snapshot path `$HF_HOME/hub/models--Qwen--Qwen2.5-Coder-1.5B-Instruct/snapshots/2e1fd397ee46e1388853d2af2c993145b0f1098a`，不得只传裸 model id。真实结果不得写到 `.worktrees/wp5-c`。
- Operator script 可以固定当前 stage worktree 作为 code/runtime cwd，并使用 stage `.venv`；这是为了执行尚未合并的 stage code。stage worktree 不能成为真实 output/checkpoint/result 的存储位置。
- `evaluate --dataset-dir` 只替换 `EvaluationConfig.dataset_dir`；现有 `evaluation_config_hash()`、dataset hash、run identity 与 exact-prefix resume 自动消费替换后的 config，不增加第二套 identity 规则。

### Execution preflight（首次业务修改/commit 前）

1. **Validation machine state / persistent roots**
   - 读取 primary `.ai-bridge/validation-machine.json`，确认 READY、bootstrap commit、readiness/Piston identity paths 与 router dispatch input 一致。
   - 通过标准：`artifact_root`、`hf_home`、`formal_data_root` 均为存在的绝对路径；`artifact_root` 可写且位于 `.worktrees/wp5-c` 外；readiness project commit 为当前 main ancestor；Piston identity `real_piston_acceptance=PASS`。

2. **Pinned CUDA / 24GB gate**
   - 命令：使用 stage `.venv/bin/python` 导入 `torch`，读取 CUDA availability、GPU name、`get_device_properties(0).total_memory`。
   - 通过标准：CUDA true；RTX 4090-class；total memory `>=22528 MiB`；pinned PyTorch/CUDA imports 成功。

3. **正式数据完整性**
   - 环境：`CODE_VERIFIER_DATA_ROOT=<router formal_data_root>`。
   - 命令：在 `$CODE_VERIFIER_DATA_ROOT` 执行 `sha256sum -c checksums.sha256`；随后 `.venv/bin/python -m code_verifier.cli check-data --dataset "$CODE_VERIFIER_DATA_ROOT/prepared"`。
   - 通过标准：checksums PASS；`checked 3200 problems (train=2500, validation=300, test=400)`；不得重新选题/重建数据。

4. **模型 cache / exact revision**
   - 环境：`HF_HOME=<router hf_home>`；使用 offline/local-only smoke。
   - 检查 bootstrap readiness 的 model id/revision/weights hash，并用 pinned Transformers/PyTorch local-only tokenizer/model load FP16 CUDA。
   - 通过标准：exact `Qwen/Qwen2.5-Coder-1.5B-Instruct@2e1fd397ee46e1388853d2af2c993145b0f1098a` 可离线加载，无 revision drift/下载。

5. **真实 tunneled Piston**
   - 命令：`make test-piston`。
   - 通过标准：Python runtime 3.10.0；9 selected tests 全 passed、0 failed、0 skipped；strict loopback endpoint 不变。

6. **基础项目环境**
   - 命令：`.venv/bin/python -c "import torch, transformers, datasets, yaml"`；`.venv/bin/python -m pytest tests/unit/test_cli.py -q`。
   - 通过标准：imports 和 baseline CLI tests 全绿。

任一 preflight 失败：停止 execution，保持 `HEAD == plan_commit`，不创建 operator checkpoint；修复 machine/tunnel/cache/data 后普通重新调用 execution-router。不得先提交部分业务修改。

### Operator terminal execution

```yaml
operator_terminal_execution:
  version: 1
  required: true
  gates:
    - gate_id: base-a-formal
      run_kind: evaluation
      executor_runs_command: false
      restart_policy: exact_rerun
      expected_artifacts:
        - "$CODE_VERIFIER_ARTIFACT_ROOT/evaluation/A-base-formal-seed42/run.json"
        - "$CODE_VERIFIER_ARTIFACT_ROOT/evaluation/A-base-formal-seed42/resolved_config.yaml"
        - "$CODE_VERIFIER_ARTIFACT_ROOT/evaluation/A-base-formal-seed42/environment.json"
        - "$CODE_VERIFIER_ARTIFACT_ROOT/evaluation/A-base-formal-seed42/samples/results.jsonl"
        - "$CODE_VERIFIER_ARTIFACT_ROOT/evaluation/A-base-formal-seed42/summary.json"
        - "$CODE_VERIFIER_ARTIFACT_ROOT/evaluation/A-base-formal-seed42/main_results.csv"
```

#### Gate `base-a-formal`

**触发点**：步骤 1 的 CLI/tests/README 已 commit，Execution preflight 全部通过，且 executor 已运行步骤 1 定向测试、`make lint` 和必要短 smoke。stage clean 后才允许生成 operator handoff。

**Executor 生成脚本的位置语义**：先预分配 checkpoint id `Cn`，再在 persistent root 创建不可碰撞目录 `$CODE_VERIFIER_ARTIFACT_ROOT/operator/WP5-c/<plan_commit>/base-a-formal/<Cn>/`；非空同名目录视为错误，不覆盖。保存 immutable `run.sh`、append-only terminal log、status/temp-status 与 lock file。script 固定 `STAGE_WORKTREE`、stage branch、primary root、`planning_base_commit`、`result_code_commit`、execution report path、gate/checkpoint identity 和 machine roots，但**不得预先硬编码未来 checkpoint docs commit hash**。

**Runtime provenance / concurrency guard**：每次人工 attempt 启动时，script 在执行长命令前必须 fail closed 验证：stage worktree 存在且 clean、branch 正确；`HEAD^ == result_code_commit`；`HEAD^..HEAD` 只修改 `ai-work/executor/WP5-c-executor.md`；当前 report 的 latest checkpoint 的 stage/gate/checkpoint-id/script-path 与本 script 固定 identity 一致，且 report 中 `operator_script_sha256` 等于运行时计算的 script SHA256；primary `main HEAD == 76490ad0b94ae40532accde2b47ec924fecd8e45` 且 non-ignored tree clean；persistent roots 存在。随后用 `flock` 获取本 checkpoint 排他锁，拿不到锁则退出，防止双终端同时写同一 formal run。

**Operator-start short preflight**：取得锁、清除旧 status/temp-status并 append UTC attempt-start 后，长命令前重新检查：
- pinned CUDA 可用且 device 0 VRAM `>=22528 MiB`；
- strict loopback Piston `http://127.0.0.1:2000` 的 Python runtime 仍为 3.10.0（可调用 project executor 的快速 runtime validation，不必再次跑 2 分钟 full Piston suite）；
- `$CODE_VERIFIER_DATA_ROOT/prepared` 可读、formal test split identity仍可解析；
- exact model snapshot/revision 在 `$HF_HOME` 可 local-only load，不联网；
- `$CODE_VERIFIER_ARTIFACT_ROOT` 可写，且当前 free bytes 至少 **10 GiB**、free inodes 至少 **100000**。该阈值针对本 stage 仅保存 400 个文本 evaluation records/log/aggregates，远高于预计输出规模；若未来训练 stage 产生多个 LoRA/optimizer checkpoint，planner 必须重新按其 checkpoint 规模设定阈值，不能沿用 10 GiB。
任一 operator-start preflight 失败：append preflight failure、原子写非零 status并退出，绝不启动正式 400 题命令。

**完整长任务命令模板**：

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
  --model-id Qwen/Qwen2.5-Coder-1.5B-Instruct \
  --run-name A-base-formal-seed42 \
  --seed 42
```

**Attempt status/log contract**：同一 checkpoint 的 script 可重复运行但不可修改。每 attempt 获锁后先删除旧 status/temp-status，terminal log 只 append start/preflight/end/exit；preflight 或长命令都必须显式捕获真实 rc，不能让 `set -e` 在 status 写入前直接结束脚本。若通过 `tee`/pipeline 追加日志，启用 `pipefail` 并取得 long command 自身 rc（例如 `PIPESTATUS[0]`），不能把 `tee` 成功误记为 evaluation 成功。最终 rc 先写 temp-status 再 atomic rename 为 status，并以同 rc 退出。若进程/SIGKILL 导致 status 缺失，resume 视为 interrupted/unknown，绝不沿用上一 attempt 的 success。不得包含 API key、SSH credential 或其它 secret；不得设置 `--output-dir` 指回 stage worktree。

**Operator handoff**：executor 计算 `run.sh` SHA256，append 并单独 commit `execution_checkpoint`，要求 `interruption_class=operator`、`resume_allowed=true`、`operator_gate_id=base-a-formal`、exact script/hash/status/log/expected_artifacts、completed_scope、remaining_scope、`status=awaiting_operator`。随后返回 `EXECUTION_OPERATOR_ACTION_REQUIRED` 并停止；不得自己执行该 400 题命令。

**用户动作**：在普通 SSH 终端或 tmux 中运行 checkpoint 返回的 exact `bash <operator_script>`。运行结束后不需要手工编辑 repository 文件；无论成功或失败，在当前 Web GPT + CodexPro 对话显式调用 `$execution-router resume backend=web`。

**Resume acceptance**：resume 必须先重新验证 operator script SHA/restart policy、machine roots、status/log，再检查真实 artifacts：
- `operator_status_file` 为 0 是必要但不充分条件；status 缺失属于未形成可靠终态；
- `run.json.status == completed`；model id/revision/checkpoint/seed/project/open-r1/dependency identity 合法；
- `resolved_config.yaml.dataset_dir` 为 `$CODE_VERIFIER_DATA_ROOT/prepared` 的展开绝对路径，split=test，其余 Base decode/model 定义与 `configs/eval/base.yaml` 一致；
- `samples/results.jsonl` 恰好 400 个唯一 formal-test `problem_id`，strict loader 可读；
- `summary.json`、`main_results.csv` strict 可读，正式 Eval-Hidden Pass@1/CI/gap/error/status metrics finite；
- non-sample artifacts 不复制 completion/code/tests/reference/starter/SFT response payload；
- 所有 expected artifacts 位于 persistent artifact root，绝不位于 stage worktree。

**失败恢复**：本 gate 为 `exact_rerun`。若 tunnel/GPU/cache 等无需 tracked 修改的环境问题导致 partial run，保持当前 operator checkpoint/HEAD 不变；修复环境后再次运行**同一 immutable script**，evaluation existing exact-prefix resume 负责跳过已完成题目，再显式 `$execution-router resume backend=web`。若失败需要 tracked source/config/test 修复，先保留旧 evidence：把 incomplete canonical `$CODE_VERIFIER_ARTIFACT_ROOT/evaluation/A-base-formal-seed42` 移到 persistent unique quarantine path并在 execution report 记录 original/quarantine path、原因/status；再做最小修复/短测试并生成新的 Cn operator checkpoint/script，从 canonical path fresh restart。禁止删除或覆盖失败 formal run。

## 4. 实施步骤

### 步骤 1：为统一 evaluate CLI 增加显式正式数据目录 override

**目标文件**：
- `src/code_verifier/cli.py`
- `tests/unit/test_cli.py`
- `README.md`

**修改的符号**：

```python
def _evaluate(args: argparse.Namespace) -> int:
    ...


def build_parser() -> argparse.ArgumentParser:
    ...
```

**主要功能**：
- `evaluate` parser 增加可选 `--dataset-dir PATH`，默认 `None`；
- `_evaluate()` 在 `load_evaluation_config()` 后、创建 Piston/generator/run 之前应用 override：`config = replace(config, dataset_dir=Path(...))`；不复制 dataset、不改 split；
- override 存在时 stderr 打印 `override: dataset_dir: <old> -> <new>`，不打印数据内容；
- Base/SFT/GRPO 三种 model source 共用相同 override；后续 B/C/D 可复用同一个 formal problem set；
- 不增加 env-var magic expansion，不修改 `EvaluationConfig` schema，不添加 compatibility layer；正式 data root 由 operator/executor shell 展开后作为 CLI 参数显式传入；
- README 增加 4090 formal evaluation + operator-terminal workflow 示例，强调长任务由生成的 exact script 运行。

**测试方案**：
- `test_evaluate_parser_accepts_optional_dataset_dir_override`
- `test_evaluate_handler_applies_dataset_dir_override_before_runner_and_prints_it`
- 现有 Base/SFT/GRPO handler tests 至少确认未传 override 时 config dataset_dir 保持原值；
- override 后传入 `run_pass1_evaluation()` 的 `EvaluationConfig.dataset_dir` 等于 CLI path；existing config/dataset/run identity 继续负责 resume guard。

**验证命令**：

```bash
.venv/bin/python -m pytest tests/unit/test_cli.py -q
make lint
```

通过标准：全绿；本步骤不启动正式 400 题 evaluation。

### 步骤 2：生成并提交 Base A operator checkpoint

**生产代码变更**：无；消费步骤 1 已提交的 CLI。

**执行职责**：
- executor 重跑必要短时 checks，并确认 stage clean；
- 按 `base-a-formal` gate 生成 persistent `run.sh` / status / log；
- 计算 script SHA256，确认 expected artifacts 都在 persistent root；
- append+commit operator checkpoint；
- 返回 `EXECUTION_OPERATOR_ACTION_REQUIRED`，向用户提供 exact script path；
- **不得运行** 400 题正式 evaluation。

### 步骤 3：用户终端执行正式 Base A

该步骤由用户在普通 terminal/tmux 中运行 checkpoint 指定的 exact `run.sh`。executor/Web GPT/Local Codex 不持有长时间 tool call。

成功目标：完成 `$CODE_VERIFIER_ARTIFACT_ROOT/evaluation/A-base-formal-seed42/` 的 400-problem Base A run。失败时保留 status/log/partial run，由下一次 explicit resume 诊断。

### 步骤 4：显式 resume，验证真实 A artifacts 并做 quick exact-prefix resume

用户终端命令结束后显式 `$execution-router resume backend=web`。executor：

1. 按 Operator resume acceptance 验证真实 run；
2. 若正式 run 完成，使用完全相同的 env/config/dataset/model/run-name/seed 再调用一次 `evaluate`。此时属于 quick resume verification，不是新的全量 operator gate；
3. 通过标准：stdout `resumed=400, generated=0`；`samples/results.jsonl` 行数与逐题记录/hash 不变化；summary/main_results 正式 metric 不漂移；
4. 若真实 run 未完成，按 operator checkpoint 协议诊断，不写 completed E0。

### 步骤 5：运行 WP5-c 总体验收并记录正式 evidence

**Executor-owned 验证命令**：

```bash
export HF_HOME=<router hf_home>
export CODE_VERIFIER_GPU_MODEL="$HF_HOME/hub/models--Qwen--Qwen2.5-Coder-1.5B-Instruct/snapshots/2e1fd397ee46e1388853d2af2c993145b0f1098a"
make lint
make test
make test-gpu
make test-piston
```

并 strict readback `$CODE_VERIFIER_ARTIFACT_ROOT/evaluation/A-base-formal-seed42/`。

**通过标准**：
- lint/type 全绿；default test suite 0 failed；GPU smoke 0 failed/0 skipped；real Piston 0 failed/0 skipped；
- A run 400/400 completed，步骤 4 quick resume `generated=0`；
- execution report 记录 operator gate/checkpoint/script hash、绝对 artifact root/A run path、dataset hash、config hash、model revision、project/open-r1/dependency identity、正式主要 metrics/CI、fresh/resume counts、所有 gate 的实际结果；
- 只有全部通过才 append completed E0；不把正式 results 拷贝进 `.worktrees/wp5-c`，不修改 plan/review/proceedings/third_party。

## 5. 总体验收与测试计划

- 单元测试：`tests/unit/test_cli.py` 覆盖 dataset-dir parser/handler/default 行为。
- Validation runtime：router machine roots、RTX 4090、formal 400-test split、exact cached 1.5B model、真实 tunneled Piston。
- Operator gate：Base A full 400-problem command 只能由用户运行 executor 生成的 SHA-bound persistent script。
- Real numerical gate：Eval-Hidden Pass@1、problem-level bootstrap 95% CI、gap/error metrics 必须来自真实 400-problem A run；synthetic/mock 不接受。
- Resume gate：operator resume 先验证 artifacts；随后 quick exact-prefix command 报 `resumed=400, generated=0`。
- 数据/安全：A–D internal corpus 固定；HumanEval+ 不混入；eval-hidden tests 不进入 prompt；candidate code execution 仍只经 Piston。
- 最终标准：
  - [ ] `--dataset-dir` override 最小实现与 tests/README 通过；
  - [ ] 4090 machine/data/model/Piston preflight 通过；
  - [ ] operator script/checkpoint 合法，executor 没有自行跑 400 题长任务；
  - [ ] 用户 terminal exact script 完成 A-base-formal-seed42 400/400；
  - [ ] resume strict artifact acceptance 通过；
  - [ ] `summary.json` / `main_results.csv` 产生正式 finite 数值；
  - [ ] exact-prefix quick resume `resumed=400, generated=0`；
  - [ ] `make lint` / `make test` / `make test-gpu` / `make test-piston` 全绿；
  - [ ] 正式 artifacts 均位于 persistent artifact root，execution report 记录 identity/path。

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
    - "Tracked implementation 只有一个最小 evaluate data-root override；随后是单一 Base A operator gate 与严格 resume/artifact 验收，关键依赖链天然串行。"
    - "正式 numerical identity、operator checkpoint、persistent run 与 completed E0 provenance 需要一个执行上下文统一维护，MULTI 不会缩短用户终端长任务且增加集成成本。"
  workstream_candidates: []
```

## 7. 风险与注意事项

- 正式 400 题评测依赖模型生成 + 大量 Piston execution；SSH tunnel 延迟/断开可能让 operator script 失败。不要通过放宽 candidate timeout、sandbox、改公网 endpoint 或 host execution 绕过。
- operator script 显式设置 `NO_PROXY/no_proxy=127.0.0.1,localhost`，避免用户终端继承的 HTTP(S) proxy 把 loopback Piston 请求错误送入代理；模型使用 offline cache。
- stage worktree 在 operator checkpoint 到 completed E0 期间必须保持存在且 HEAD 不被手工改动；script 在每次 attempt 前会用 parent/diff/report-self-SHA 结构校验锁定当前 operator checkpoint，任何手工 commit/dirty change 都应 fail closed。
- 用户不需要复制长日志给 agent；`$execution-router resume backend=web` 优先直接读取 checkpoint 记录的 persistent status/log/artifacts。若需要人工反馈，提供 terminal 最后错误即可。
- 不因 4090 显存充足而改变 Base model/revision/decode/seed/formal split。
- `configs/eval/base.yaml` 继续冻结 Base decode/model definition；formal dataset 通过明确 CLI override 绑定，不把机器绝对 data path 写入 tracked YAML。
- 后续 WP6 validation 独立 planner 必须封存 SFT formal dataset 与 `max_seq_length=1536`，正式 SFT/GRPO operator gate 固定 `restart_policy=trainer_checkpoint`，其 immutable script 必须在同一 stage HEAD 自动选择 latest valid same-run `checkpoint-*`；训练 stage 还必须按预计 LoRA/optimizer checkpoint 总量重新设置 operator-start free-bytes/inodes 门槛。后续 B/C/D full evaluation 通常使用 `exact_rerun`。

## 8. 关联文档索引

- `PROJECT_SPEC_Open-R1_CodeVerifier.md`：§4.2–§4.3、§18.2–§18.3、§19.2.2、§20.0、WP5、§21.5、§29
- `proceedings.md`：WP8 terminal closeout、Development Complete Record、4090 machine-state amendment、Validation operator-terminal execution amendment
- `AGENTS.md`：Operator-terminal long validation runs
- `skills/planner-ex/SKILL.md` / `references/plan-template.md`
- `skills/execution-router/SKILL.md`
- `skills/executor-ex/SKILL.md` / `executor-web/SKILL.md` / `executor/SKILL.md`
- `skills/stage-lifecycle/SKILL.md`
- `open-r1-code-verifier-data-4090/README-4090-DATA.md`
- `.ai-bridge/validation-machine.json`
- `$CODE_VERIFIER_ARTIFACT_ROOT/machine/bootstrap-4090-readiness.json`
- `$CODE_VERIFIER_ARTIFACT_ROOT/machine/piston-runtime-identity.json`

## 9. Handoff

- 下一步：运行 `$stage-lifecycle bootstrap_plan`。它应从本 handoff 创建 `feat/wp5-c` / `.worktrees/wp5-c`，把正文写入 `ai-work/planner/WP5-c-plan.md` 并 commit plan seal。
- bootstrap 必须再次验证 Development Complete Record、4090 machine record、>=22528 MiB GPU、persistent roots、READY/Piston identity、operator block schema（含 `restart_policy=exact_rerun`、operator-start short preflight、唯一 namespace/runtime guard/lock/status-log/quarantine 语义），以及 primary clean + `main HEAD == 76490ad0b94ae40532accde2b47ec924fecd8e45`。
- bootstrap 成功后调用 execution-router。首次 execution 只做到 operator checkpoint 并返回用户 exact script；用户运行后在当前 Web GPT + CodexPro runtime 显式 `$execution-router resume backend=web`。
- 在 bootstrap 成功并得到 `plan_commit` 前，不得调用 execution-router。
