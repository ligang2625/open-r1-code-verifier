# WP6-a Reviewer Report

## R1 — latest execution E0

```yaml
review_record:
  version: 1
  stage_id: WP6-a
  review_round: 1
  source_execution_id: E0
  reviewed_head_commit: 21f12a62e375dd44308a806cc108d819b58be286
  conclusion: needs_repair
```

### 1. Provenance 与审查边界

- 目标 stage：`WP6-a`。
- sealed plan：`ai-work/planner/WP6-a-plan.md`，`source_plan_commit=0d17934e101c142d5117c6ec5c05bdf8c938921d`。
- 最新 completed execution：`E0`，`task_kind=implementation`，`result_code_commit=a6f16ab43c4c5c2ed73097064269ba08fd5d9df4`。
- 首次包含该 execution record 的 docs commit：`21f12a62e375dd44308a806cc108d819b58be286`。
- 审查开始前与写 review 前均确认 stage worktree 无 tracked/untracked review 输入变化，且 `HEAD` 始终为 `21f12a62e375dd44308a806cc108d819b58be286`。
- 实际 worktree `/home/dzy/open-r1-code-verifier/.worktrees/wp6-a`、branch `feat/wp6-a` 与 plan metadata 一致。

### 2. 独立验证结果

已由 reviewer 独立执行：

- `PYTHONPATH=src make lint VENV=/home/dzy/open-r1-code-verifier/.venv`：PASS；Ruff check / format / strict Mypy 全绿，84 source files。
- `PYTHONPATH=src make test VENV=/home/dzy/open-r1-code-verifier/.venv`：PASS；`701 passed, 3 skipped`，仅既有显式 Piston cases 默认 skip。
- `PYTHONPATH=src make test-gpu VENV=/home/dzy/open-r1-code-verifier/.venv`：PASS；真实 GTX 1660 Ti 上 `3 passed`，未启动 SFT。
- `PYTHONPATH=src make test-piston VENV=/home/dzy/open-r1-code-verifier/.venv`：PASS；`9 passed, 0 failed, 0 skipped`（2 non-piston tests deselected）。
- `code-verifier train-sft --help`：PASS，返回 0；包含 `--config/--seed/--output-dir/--log-level/--resume-from-checkpoint`。
- pinned runtime：Open-R1 `0.1.0.dev0`、TRL `0.18.0`、Transformers `4.52.3`、Accelerate `1.4.0`、PEFT `0.14.0`。
- shipped `configs/sft/debug.yaml` 真实 guarded CLI probe：PASS（预期 fail-closed）；当前 6GB GPU 返回 exit 2：`SFT training requires at least 20 GiB CUDA memory; detected 6.0 GiB`，未进入训练。
- Open-R1 gitlink：`1416fa0cf21595d2083b399a2a0bbddd7f6e9563`，未变化；`src/code_verifier` 中未发现绕过 adapter 的 `from open_r1 ...` import。

额外 adversarial probes：

1. 将合法 SFT config 的 `min_cuda_memory_gb` 改为 `1.0`，模拟同一 6GB CUDA device 后，`validate_sft_training_hardware()` **成功返回**，输出 `ACCEPTED_6GB`。说明硬件 gate 是用户可下调的软阈值，不是 plan 要求的硬约束。
2. 写入只有一个物理 LF 的合法 UTF-8 JSONL record，令 `prompt` 含 U+2028；`load_training_artifact()` 因 `splitlines()` 把 U+2028 当成行分隔符而报 `Unterminated string`。该文件由标准 JSON `ensure_ascii=False` 可合法生成。

### 3. Plan step / acceptance 核对

| Plan step | 结论 | 说明 |
|---|---|---|
| 1. shared §7.2 prompt builder | PASS | `build_code_prompt()` 与 WP5 wrapper 共享固定 visible-only prompt；现有 prompt tests 与全局回归通过。 |
| 2. SFT artifact visible-only contract | PASS with issue | whitelist 与 canonical mapping 已实现，hidden/reference/starter key 被拒绝；但 loader 的 Unicode JSONL round-trip 存在 `R1-m1`。 |
| 3. target normalization / visible verification / TRL mapping | PASS with issue | 使用 parser + `verify_completion()` + caller-selected visible tests，不在宿主执行 candidate code；payload 在 trainer dataset 前被移除。loader 边界仍受 `R1-m1` 影响。 |
| 4. exact PEFT/runtime preflight | PASS | exact versions 与 adapter boundary 已独立核验。 |
| 5. strict config / hardware guard / trainer / artifacts | PARTIAL | 基础 LoRA mapping 与 artifacts 存在，但 hard hardware policy、resume provenance/cost、spec-default eval path、seed override contract 分别存在 `R1-M1`～`R1-M4`。 |
| 6. `train-sft` CLI / integration | PARTIAL | CLI/help/error sanitation 基本完成，但可配置硬件绕过与 seed override 语义使 acceptance 不能通过。 |
| 7. docs / WP6-b readiness | PARTIAL | hardware split 与 WP6-b gate 已记录；resume 示例/语义因 `R1-M2` 不能视为可靠 continuation contract。 |

本阶段 acceptance 中以下项目已通过：`make lint`、`make test`、CLI help、shared prompt byte-contract、visible-only trainer dataset、target normalization + visible verification、pinned runtime versions、shipped debug config 在真实 1660 Ti 上 fail-closed、未执行真实 SFT、未伪造 checkpoint/B-group 结果。

以下 acceptance / spec 项因 actionable issues 未通过：不可绕过的 1660 Ti training prohibition、resume/run identity 与成本可追溯、§11.3 main SFT eval defaults 可执行、§18.3 config/CLI override 语义、合法 UTF-8 SFT JSONL round-trip。

### 4. Findings

#### R1-M1 — Hardware policy 可通过降低 `min_cuda_memory_gb` 绕过

**位置**：`src/code_verifier/training/sft.py:172-251,269-286`，`configs/sft/*.yaml`。

Plan 明确要求当前 GTX 1660 Ti 不得承担 SFT，并要求 training command 在模型加载前 fail closed。实现把唯一显存门槛暴露为普通 YAML 字段 `min_cuda_memory_gb`，但 parser 只校验其为正数；`validate_sft_training_hardware()` 直接信任该值。

Reviewer 独立 probe 将该值设为 `1.0` 后，同一模拟 6GB device 被接受。因 fp16 config 不需要 BF16 gate，后续即可继续进入 runtime/model loading。这意味着 shipped config 虽安全，但项目级硬约束可由任意自定义 config 绕过。

**要求修复**：将“training-class GPU”门槛做成不可由普通 experiment config 下调的 project invariant。最小方案是 parser 强制 `min_cuda_memory_gb >= 20.0`（或移除该可下调字段并使用代码常量）；补充 6GB + lowered-threshold 必须拒绝的 regression test。不得通过在 1660 Ti 上实际训练来验证。

#### R1-M2 — Resume 可从任意外部 checkpoint 新建 run，且来源/累计成本不进入 run identity

**位置**：`src/code_verifier/training/sft.py:479-517,520-625`；`tests/unit/training/test_sft.py:383-402`；`README.md:441-449`。

Plan 描述的是“crash/interrupt 后已有 checkpoint 的 explicit continuation”。当前实现却允许：

- `run_dir` 尚不存在时，只要 `resume_from_checkpoint` 指向任何 existing directory，就先 `_initialize_run()` 一个全新 run，再把该任意目录传给 `trainer.train()`；
- 不要求 resume path 位于当前 `<run_dir>/checkpoints/`，不验证其来自该 run，也不在 `run.json` 中记录 resume source；
- `run.json` 仍只声明 config 的 `model_id/model_revision/dataset_hash/config_hash/seed`，因此外部 checkpoint 的真实初始化来源可被错误标记成当前 base identity；
- `_validate_resume_run()` 只核对少量字段，不绑定 checkpoint provenance；
- interrupted attempt 已写入的 `gpu_hours` 在下一次完成/失败时被本次 attempt 的时长覆盖，而非累计，导致真实 training cost 被低估；
- README 示例传 `outputs/sft/debug/checkpoints` 根目录，而 interruption recovery 通常需要具体 Trainer `checkpoint-*` continuation 目录，当前代码也没有 latest-checkpoint resolution/validation。

现有 unit test 反而显式构造 `tmp_path/source-checkpoint` + fresh output root 并要求其被接受，证明该行为是当前 contract，而不是仅理论路径。

**要求修复**：resume 必须绑定到已有同一 run；至少要求 `run_dir` 已存在、checkpoint resolve 后位于该 run 的 `checkpoints/` 下，并验证 existing run 的 model/config/dataset/seed 以及 repository/Open-R1/dependency provenance。记录本轮 resume source（可用 run-relative path/identity，不泄漏 payload），并累计而不是覆盖 `gpu_hours`。README 改为真实可恢复的 `checkpoint-*` 示例或实现明确的 latest-checkpoint resolution。补充拒绝 fresh-run + external-checkpoint、拒绝 cross-run checkpoint、累计 cost 的 tests。

#### R1-M3 — Spec 默认 `eval_strategy: steps` 路径没有实现，main config 通过改成 `no` 绕开

**位置**：`configs/sft/main.yaml:17-18`，`src/code_verifier/training/sft.py:406-431,583-590`，`src/code_verifier/data/prepare.py` 的 training artifact export。

`PROJECT_SPEC` §11.3 的默认 SFT config 是 `eval_strategy: steps` / `eval_steps: 100`；sealed plan Step 5 也要求 `main.yaml` 保留 §11.3 默认 LoRA/hyperparameters。当前 implementation 将 main config 改成 `eval_strategy: "no"` / `eval_steps: null`，execution report 将其列为 deviation。

更关键的是，config parser/runtime 仍声称支持 `eval_strategy="steps"`，`_runtime_arguments()` 会设置 `do_eval=True`，但 `run_sft_training()` 无条件向 `SFTTrainer` 传 `eval_dataset=None`。因此一旦恢复 spec 默认配置，真实 trainer 在 eval step 没有可用 validation dataset；该公开配置分支实际上不可执行。

**要求修复**：不要以关闭 eval 掩盖未实现路径。为 main SFT 提供独立 validation SFT mapping/artifact（仍遵守 hidden/reference leakage contract），在 `eval_strategy=steps` 时构造并传入 `eval_dataset`；`configs/sft/main.yaml` 恢复 spec 默认 `steps/100`。debug config 可按明确理由保持 `no`，但 parser 不得接受一个 runtime 无法履行的 eval mode。补充 fake-runtime + dataset tests，证明 validation rows 不进入 train split、trainer 的 eval dataset payload-minimal 且无 hidden tests。

#### R1-M4 — YAML `seed` 是静默的未使用配置项，CLI override 也未打印

**位置**：`src/code_verifier/training/sft.py:217-250,369-372,385-432`，`src/code_verifier/cli.py` common `--seed` default 与 `_train_sft()`。

SFT YAML 强制要求 `seed`，`SFTTrainingConfig.seed` 也被保存进 config hash；但训练实际 seed 完全来自 CLI `args.seed`。由于 common parser 的 `--seed` 默认固定为 42：

- 用户把 YAML `seed` 改成 7、且没有传 `--seed`，实际训练仍使用 42；
- YAML seed 会改变 `config_hash`，却不改变 training RNG，形成“identity changed / behavior unchanged”的假配置维度；
- 显式 `--seed` 与 YAML seed 不同也不会打印或记录一条 override 说明。

这直接违反 §18.3“命令行覆盖必须打印；不允许存在未使用配置项而不警告”的配置解析要求，并削弱可复现性。

**要求修复**：定义唯一的 effective-seed resolution。建议 train-sft 的 CLI `--seed` 默认 `None`：未提供时使用 `config.seed`；显式提供时覆盖 config seed，并打印/记录 `seed: <config> -> <cli>`。`resolved_config.yaml/run.json/config_hash` 应对有效行为给出一致 identity。补充 YAML-only seed、CLI override、override logging 与 resume identity tests。

#### R1-m1 — SFT JSONL loader 会把合法 U+2028/U+2029 内容误切成新行

**位置**：`src/code_verifier/data/leakage_checks.py:206+` 的 `load_training_artifact()`。

loader 使用 `path.read_text(...).splitlines()`。Python `splitlines()` 会把 U+2028/U+2029 当 line boundary；但项目 `write_jsonl()` 使用 `ensure_ascii=False`，所以 prompt/SFT response 中合法的 U+2028/U+2029 可原样存在于一个物理 LF-delimited JSON record。

Reviewer probe 生成一个仅含一个物理 LF、prompt 含 U+2028 的合法 JSONL record；loader 将其拆开并抛 `Unterminated string`。WP5-b 已有同类严格 JSONL physical-LF 边界经验，本 SFT loader 应保持一致。

**要求修复**：按物理 `\n` 分隔 JSONL（并明确处理 CRLF/尾部 LF/blank-line policy），不要使用 Unicode-aware `splitlines()`；增加 U+2028/U+2029 round-trip tests，至少覆盖 SFT prompt 和 response。

### 5. Execution report 核验

- “shared prompt / visible-only mapping / LoRA control plane / CLI 已实现”：基本属实，但存在上述 control-plane defects，因此“implementation complete / blockers none”不成立。
- `make lint`、`make test=701 passed, 3 skipped`、`make test-gpu=3 passed`：reviewer 已独立复现。
- exact runtime versions：reviewer 已独立复现。
- shipped debug config 在真实 1660 Ti fail closed：reviewer 已独立复现；但该结论不能证明 project invariant，因为 `R1-M1` 可通过 custom config 绕过。
- “no real SFT training”：未发现相反证据，且 reviewer 未启动训练。
- Open-R1 gitlink / upstream read-only：核验通过。

### 6. R1 结论

当前 `reviewed_head_commit=21f12a62e375dd44308a806cc108d819b58be286` **不得 PASS**。核心数据隔离、静态检查和现有测试质量较好，但硬件 policy、resume provenance/cost、spec-default validation、seed override reproducibility 均属于正式训练前必须修复的控制面问题；另有一个 training JSONL round-trip edge defect。

```yaml
repair_routing:
  version: 1
  required: true
  source_review_round: 1
  mode: single
  complexity: difficult_serial
  single_class: difficult_serial
  parallelizability: low
  multi_benefit: low
  independent_workstreams: 1
  repair_issue_ids:
    - R1-M1
    - R1-M2
    - R1-M3
    - R1-M4
    - R1-m1
  rationale:
    - "R1-M2/R1-M3/R1-M4 都集中修改 SFT config/run identity/trainer construction/CLI，并与 validation dataset contract 相互依赖；独立拆 lane 会产生同文件与同 public-config surface 的高冲突。"
    - "R1-M1 与 R1-m1 本身较小，但应随同一 repair 串行回归 hardware guard、data leakage、resume identity、TRL mapping 与全局 WP1/WP5/WP6 tests；multi coordination 的净收益低。"
  workstream_candidates: []
```

### 7. 下一步

1. 本 review 由 reviewer-ex 仅写入 stage worktree，未 commit/merge/finalize，也未更新 `proceedings.md`。
2. 本地下一步运行 `$stage-lifecycle checkpoint_review` 封存 R1。
3. checkpoint 成功后运行 `$execution-router`，按 `R1-M1/R1-M2/R1-M3/R1-M4/R1-m1` 执行 repair。
4. repair execution 完成并产生新的 completed execution record 后，再运行 reviewer-ex R2。
