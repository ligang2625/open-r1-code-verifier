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

---

## R2 — latest execution E1

```yaml
review_record:
  version: 1
  stage_id: WP6-a
  review_round: 2
  source_execution_id: E1
  reviewed_head_commit: 0965d88ef5944ac9da07d0d8c97ca5b553ebfcd6
  conclusion: needs_repair
```

### 1. Provenance 与审查边界

- 目标 stage：`WP6-a`，实际 worktree `/home/dzy/open-r1-code-verifier/.worktrees/wp6-a`，branch `feat/wp6-a`，与 sealed plan metadata 一致。
- 上一轮已提交 review：R1 commit `8638d4b648a811ee093463a6cdf89ec0075fabdd`，结论 `needs_repair`。
- 最新 completed execution：`E1`，`task_kind=repair`，`source_review_round=1`，`source_review_commit=8638d4b648a811ee093463a6cdf89ec0075fabdd`，repair issue 集合恰为 `R1-M1/R1-M2/R1-M3/R1-M4/R1-m1`。
- E1 `result_code_commit=66045604468dc475127cd26ef160f8b7398e1ea7`；首次包含 E1 record 的 execution report commit 为当前 `HEAD=0965d88ef5944ac9da07d0d8c97ca5b553ebfcd6`。
- 审查开始前和写入本 record 前均确认 worktree 干净；审查期间 HEAD 未变化。

### 2. R1 repair 核验

| Issue | R2 结论 | 独立证据 |
|---|---|---|
| `R1-M1` hardware floor | RESOLVED | parser 强制 `min_cuda_memory_gb >= 20`，runtime 又以 `max(config floor, project floor)` 二次保护；reviewer 独立 lowered-threshold probe 返回 `SFTTrainingError min_cuda_memory_gb must be at least 20 GiB`。 |
| `R1-M2` resume provenance/cost | RESOLVED | resume 只接受已存在同 run 的直接子目录 `checkpoints/checkpoint-*`；fresh/external/cross-run checkpoint 被拒；run identity 绑定 train/validation hash、git/Open-R1/dependency/GPU runtime identity；source 使用 run-relative path 记录；`gpu_hours` 在 attempts 间累计。相关 unit tests 与全量回归通过。 |
| `R1-M3` spec-default validation | RESOLVED | data pipeline 新增 canonical validation-only `sft_validation.jsonl`；main config 恢复 `eval_strategy: steps` / `eval_steps: 100`；runtime 为 validation records 构造独立 payload-minimal eval dataset，并检查 train/validation problem IDs 不重叠。 |
| `R1-M4` seed override | RESOLVED | `train-sft --seed` 默认 `None`，未指定时使用 YAML seed；显式不同值会打印 override，effective seed 进入 resolved config/config hash/trainer/run identity；reviewer 真实 CLI probe 输出 `override: seed: 42 -> 7` 后再按硬件 gate fail closed。 |
| `R1-m1` SFT artifact physical-LF loader | RESOLVED | `load_training_artifact()` 改为物理 `\n` 分隔并保留 CRLF/blank-line policy；U+2028/U+2029 SFT prompt/response regression 已加入并通过。 |

R1 五项均不再需要继续沿用原 issue ID。

### 3. 独立验证结果

Reviewer 在 `0965d88...` 上独立执行：

- focused data/training/CLI/WP1/WP6-a suite：`144 passed`。
- `PYTHONPATH=src make lint VENV=/home/dzy/open-r1-code-verifier/.venv`：PASS；Ruff check/format 与 strict Mypy 全绿，84 source files。
- `PYTHONPATH=src make test VENV=/home/dzy/open-r1-code-verifier/.venv`：PASS；`709 passed, 3 skipped`，仅既有 opt-in Piston tests 默认 skip。
- `PYTHONPATH=src make test-gpu VENV=/home/dzy/open-r1-code-verifier/.venv`：PASS；真实 GTX 1660 Ti `3 passed`，未执行 SFT。
- `PYTHONPATH=src make test-piston VENV=/home/dzy/open-r1-code-verifier/.venv`：PASS；`9 passed`，2 non-Piston tests deselected。
- pinned runtime versions：Open-R1 `0.1.0.dev0`、TRL `0.18.0`、Transformers `4.52.3`、Accelerate `1.4.0`、PEFT `0.14.0`。
- `code-verifier train-sft --help`：PASS，seed help 已变为 `default: config seed`。
- real guarded debug CLI：当前 6GB GTX 1660 Ti 返回 exit 2，错误为 `requires at least 20 GiB`，未启动真实训练。
- E1 repair range 未修改 `third_party/open-r1/**`。

### 4. 新 finding

#### R2-m1 — Physical-LF JSONL 修复未覆盖 WP1 raw/canonical readers，合法 Unicode line separator 仍会阻断 `prepare-data`

**位置**：`src/code_verifier/data/adapters.py:115-133`、`src/code_verifier/data/prepare.py:321-337`。

E1 正确修复了 `load_training_artifact()`，但同一 WP1 pipeline 还有两个 JSONL reader 继续使用 `str.splitlines()`：

- `load_raw_jsonl()` 对用户输入 raw JSONL 使用 `splitlines()`；
- `_load_canonical()` 对项目自己通过 `write_jsonl(..., ensure_ascii=False)` 输出的 canonical JSONL 使用 `splitlines()`。

Python `splitlines()` 会把 U+2028/U+2029 当作行边界，而 JSON 字符串允许这些 Unicode 字符原样存在。由于项目 writer 明确使用 `ensure_ascii=False`，这不是非法输入。

Reviewer 独立做了两个仓库外临时文件 probe：

1. 将现有 WP1 raw fixture 的 `prompt` 改为 `before\u2028after`，用标准 `json.dumps(..., ensure_ascii=False)` 写成只有 **1 个物理 LF** 的合法 JSONL；`load_raw_jsonl()` 报 `Unterminated string`。
2. 直接构造合法 `CodeProblem(prompt="before\u2028after")`，调用项目 `export_canonical_jsonl()`；文件同样只有 **1 个物理 LF**，但随后 `_load_canonical()` 无法读取项目自己写出的 record，报 `Unterminated string`。

这会使合法 Unicode problem 在进入 SFT mapping 前就失败，也会使 canonical export → `check_prepared_data()` 自身不具备 round-trip closure；因此 Step 2 的 WP1/SFT data contract 仍有一个实际可复现的边界缺口。

**要求修复**：统一 raw/canonical reader 与已修复的 training artifact reader 的 physical-LF contract。至少：

- `load_raw_jsonl()` 和 `_load_canonical()` 不得使用 Unicode-aware `splitlines()`；按物理 `\n` 分隔，并明确兼容 CRLF、尾部 LF 与既有 blank-line policy；
- 增加 raw input U+2028/U+2029 regression；
- 增加 canonical writer → reader / `check_prepared_data()` U+2028/U+2029 round-trip regression；
- 不改变 JSON duplicate-key、schema、split/leakage 等既有 fail-closed 行为。

### 5. Plan / acceptance 复核

- Steps 1、3、4：PASS。
- Step 5 的 R1 控制面问题已修复；LoRA mapping、hardware guard、resume、validation、seed/run identity 均通过本轮证据。
- Step 6：PASS；CLI/help/error sanitation/seed override 与 non-training integration 可用。
- Step 7：PASS with no new documentation blocker；README 的 resume、hardware split、WP6-b gate 与现代码一致。
- Step 2：**PARTIAL**，仅因 `R2-m1` 的 WP1 raw/canonical JSONL round-trip 缺口未通过；该 failed plan item 已映射到本轮 repair issue。

其余本阶段 acceptance 均通过：shared prompt、visible-only trainer/eval datasets、hidden/reference isolation、single fenced target + visible verification、pinned runtime、20 GiB non-lowerable guard、1660 Ti no-training gate、`make lint`/`make test`、未伪造 checkpoint/B-group 结果。

### 6. Execution report 核验

- E1 对 `R1-M1`～`R1-M4`、`R1-m1` 的 disposition：与当前代码和 reviewer 独立验证一致。
- `709 passed, 3 skipped`、GPU `3 passed`、exact runtime versions、real guarded CLI：已独立复现。
- “no real SFT training”：未发现相反证据，reviewer 本轮也未执行 SFT。
- “deviations/blockers: none”：就 E1 routed R1 issues 而言成立；但本轮新发现 `R2-m1`，因此 stage 仍不能 finalize。

### 7. R2 结论

当前 `reviewed_head_commit=0965d88ef5944ac9da07d0d8c97ca5b553ebfcd6` **needs_repair**。R1 的五项 repair 已全部关闭；剩余仅一个新发现的 WP1 JSONL physical-line 边界问题，但它会让合法 Unicode raw/canonical data 无法通过项目自己的 preparation/round-trip，因此在 stage PASS 前应修复。

```yaml
repair_routing:
  version: 1
  required: true
  source_review_round: 2
  mode: single
  complexity: normal
  single_class: normal
  parallelizability: low
  multi_benefit: low
  independent_workstreams: 1
  repair_issue_ids:
    - R2-m1
  rationale:
    - "修复集中在 WP1 两个 JSONL readers 与对应数据回归测试，接口简单但必须同时保持 raw ingestion、canonical round-trip、duplicate-key/schema/leakage 行为一致，适合单路串行修复。"
    - "只有一个 issue，拆成 multi lane 不会产生净收益；repair 后应重跑 data focus 与全量 lint/test。"
  workstream_candidates: []
```

### 8. 下一步

1. reviewer-ex 本轮只追加 R2 review record，未 commit/merge/finalize，也未修改 `proceedings.md`。
2. 本地运行 `$stage-lifecycle checkpoint_review` 封存 R2。
3. checkpoint 成功后运行 `$execution-router`，仅 repair `R2-m1`。
4. 新 completed repair execution 产生后，再运行 reviewer-ex R3。

---

## R3 — latest execution E2

```yaml
review_record:
  version: 1
  stage_id: WP6-a
  review_round: 3
  source_execution_id: E2
  reviewed_head_commit: 287f3f67c1d2ffbf0899d72f2cc14faf44a38af2
  conclusion: pass
```

### 1. Provenance 与审查边界

- 目标 stage：`WP6-a`，worktree `/home/dzy/open-r1-code-verifier/.worktrees/wp6-a`，branch `feat/wp6-a`，与 sealed plan 一致。
- 上一轮已提交 review：R2 commit `00cf7487e0d95a8ff22e7597acbee84c2ab15725`，结论 `needs_repair`，唯一 issue `R2-m1`。
- 最新 completed execution：`E2`，`task_kind=repair`，`source_review_round=2`，`source_review_commit=00cf7487e0d95a8ff22e7597acbee84c2ab15725`，`repair_issue_ids=[R2-m1]`。
- E2 `result_code_commit=7a8d5ddb1fa7d68318624d562f9841e7f18650c2`；首次包含 E2 record 的 execution report commit 为当前 `HEAD=287f3f67c1d2ffbf0899d72f2cc14faf44a38af2`。
- 审查开始前与写入前 worktree 均干净；审查期间 HEAD 未变化。

### 2. `R2-m1` repair 核验

`R2-m1` **RESOLVED**。

- `src/code_verifier/data/adapters.py::load_raw_jsonl()` 已从 Unicode-aware `splitlines()` 改为仅按物理 `\n` 分隔；CRLF 仍由 JSON whitespace 规则正常接受，blank/trailing lines 沿用既有 ignore policy。
- `src/code_verifier/data/prepare.py::_load_canonical()` 使用相同 physical-LF contract，因此项目 `ensure_ascii=False` 写出的 U+2028/U+2029 canonical JSONL 可重新加载。
- 新增 raw U+2028/U+2029 regressions，以及完整 `prepare_data()` canonical export → `check_prepared_data()` round-trip regressions。
- Reviewer 搜索确认 `src/code_verifier/data` 中已无 `splitlines()` 残留；training artifact、raw、canonical 三类 JSONL reader 的物理行语义已统一。
- duplicate-key、schema、split/leakage 等 fail-closed 路径未被放宽，相关 data/full tests 均通过。

### 3. 独立验证结果

Reviewer 在 `287f3f67...` 上独立执行：

- focused raw/canonical/WP1 suite：`51 passed`。
- `PYTHONPATH=src make lint VENV=/home/dzy/open-r1-code-verifier/.venv`：PASS；Ruff check/format 与 strict Mypy 全绿，84 source files。
- `PYTHONPATH=src make test VENV=/home/dzy/open-r1-code-verifier/.venv`：PASS；`713 passed, 3 skipped`，仅三个显式 real-Piston opt-in cases 默认 skip。
- `PYTHONPATH=src make test-gpu VENV=/home/dzy/open-r1-code-verifier/.venv`：PASS；真实 GTX 1660 Ti 上 `3 passed`，未运行 SFT。
- `code-verifier train-sft --help`：PASS，返回 0；CLI 仍采用 config-seed default 与 explicit resume contract。
- pinned runtime versions：Open-R1 `0.1.0.dev0`、TRL `0.18.0`、Transformers `4.52.3`、Accelerate `1.4.0`、PEFT `0.14.0`。
- 真实 guarded debug CLI：当前 6GB GTX 1660 Ti 返回 exit 2：`SFT training requires at least 20 GiB CUDA memory; detected 6.0 GiB`；未启动真实训练。
- E2 scope 未修改 `third_party/open-r1/**`、sealed plan 或 `proceedings.md`。

### 4. Stage acceptance 最终复核

- Step 1 shared §7.2 prompt builder：PASS；WP5/SFT prompt contract 未漂移。
- Step 2 visible-only SFT artifact / WP1 data contract：PASS；train + independent validation mapping、physical-LF JSONL round-trip 与 hidden/reference isolation 均成立。
- Step 3 SFT target normalization / visible-only verification / payload-minimal TRL dataset：PASS。
- Step 4 PEFT/Open-R1/TRL exact runtime integration：PASS。
- Step 5 strict config / non-lowerable hardware guard / LoRA runtime / validation / resume provenance / run artifacts：PASS。
- Step 6 `train-sft` CLI 与 non-training integration：PASS。
- Step 7 documentation / WP6-b handoff readiness：PASS。

总体验收：`make lint`、`make test`、GPU smoke、CLI help、runtime pins、visible-only isolation、20 GiB hardware fail-closed、no-real-SFT-on-1660、no fabricated checkpoint/B-group result 全部满足。WP6-b 的 24GB GPU、>=50 validated SFT examples、real smoke/checkpoint reload/B-group evaluation/cost gates 仍按计划保留，不属于 WP6-a 未完成项。

### 5. Execution report 核验

- E2 对 `R2-m1` 的 disposition 与当前代码及 reviewer 独立结果一致。
- E2 自报 focused `51 passed`、全量 `713 passed, 3 skipped`、GPU `3 passed` 均已独立复现。
- runtime version 与 no-real-SFT 声明已核验，无实质不一致。
- 未发现新的 blocker/major/minor actionable finding。

### 6. R3 结论

当前 `reviewed_head_commit=287f3f67c1d2ffbf0899d72f2cc14faf44a38af2` **PASS**。R1 与 R2 的全部 actionable findings 均已关闭；在本轮证据下不存在需要下一轮 executor 行动的问题。

```yaml
repair_routing:
  version: 1
  required: false
  source_review_round: 3
  mode: null
  complexity: null
  single_class: null
  parallelizability: null
  multi_benefit: null
  independent_workstreams: 0
  repair_issue_ids: []
  rationale:
    - "E2 已关闭 R2-m1，R1/R2 全部 actionable findings 均 resolved；独立 focused/full/GPU/CLI/runtime/hardware 验收均通过，因此无需 repair。"
  workstream_candidates: []
```

### 7. 下一步

1. reviewer-ex 本轮只追加 R3 PASS review，未 commit/merge/finalize，也未修改 `proceedings.md`。
2. 本地运行 `$stage-lifecycle checkpoint_review` 封存 R3。
3. checkpoint 成功后运行 `$stage-lifecycle finalize`，由 lifecycle 完成 merge、proceedings/finalization record 与 worktree/branch cleanup。
