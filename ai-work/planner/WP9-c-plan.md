# WP9-c 实施计划（Real calibration and pilot validation）

## 1. 元信息

| 项 | 值 |
|---|---|
| stage_id | `WP9-c` |
| stage_profile | `validation` |
| control_plane_hardware | `GTX 1660 Ti (6GB)` |
| target_hardware | `24GB GPU` |
| evidence_class | `real-training/numerical` |
| development_terminal | `false` |
| 目标 WP | `WP9`：Real calibration and pilot |
| 规格依据 | `PROJECT_SPEC_GRPO_Refresh.md` §7–§14、§16–§17；`PROJECT_SPEC_Open-R1_CodeVerifier.md` §19–§21、§29；`proceedings.md` 最新 WP9 finalized/routing records |
| 前置状态 | `WP9-a` finalized；`WP9-b` 于 2026-09-02 finalized / PASS（R6）；当前唯一 dependency-ready stage=`WP9-c` |
| planning_base_commit | `f1ffe6291182084146c557129efc6d121d872684` |
| proposed branch | `feat/wp9-c` |
| proposed worktree | `.worktrees/wp9-c` |
| final plan path | `ai-work/planner/WP9-c-plan.md` |
| execution report path | `ai-work/executor/WP9-c-executor.md` |
| review path | `ai-work/reviewer/WP9-c-review.md` |
| plan lifecycle | planner-ex handoff → `stage-lifecycle bootstrap_plan` → committed plan seal → execution-router/executor |

Planning-time guard：`main` clean，`HEAD=f1ffe6291182084146c557129efc6d121d872684`；当前只有 main linked worktree；`.ai-bridge/current-plan.md` 在本次 handoff 前不存在，`git ls-files .ai-bridge` 为空。历史 `archive/*` 与两个未 linked 的 `chore/*` 分支不构成 active stage。`proceedings.md` 已明确 WP9-b finalized，因此不得再规划 WP9-b 或退回旧 C/D replication。

## 2. 目标与范围

### 2.1 目标（active Refresh contract）

使用冻结的正式 SFT checkpoint B 做真实 WP9 calibration，冻结唯一共享 active pool；在 24GB target 上完成 k=8 主协议的真实 throughput benchmark 与 Public/Hidden pilot，在 1660 Ti control plane 完成 dual-verifier scoring、eval verification、artifact aggregation/strict checks；最终冻结供 WP9-d 消费的 calibration manifest、benchmark report、selected runtime choices 与 pilot zero-variance gate evidence。

k=8 是用户已授权的 Refresh 主协议。k=4 仅保留一个小型、受控、同 B/同 pool/同 seed/同 reward arm/同 runtime 的 diagnostic reference；不得把它重新升级为与 k=8 对等的主协议选择或新增 k=4 C2/D2 campaign。

### 2.2 必须交付

1. 从已严格通过 WP9-a `check_refresh_data()` 的 10,000 题 artifact 生成 Public-safe calibration input bundle；formal provenance 必须锚定：
   - WP9-a root manifest SHA256 `98a0fb8192661f6358c29819d8a70eb4039397cc2a3ec5444f0581cfbcb81625`；
   - selected IDs/order SHA256 `355cfec302a38c3c05e4237be178c5f34207cabb432d2b65f1b4a027cf42d001`；
   - 10,000 selected / 750 SFT reuse / 9,250 external-new / 1,086 quality-gate-required。
2. 4090 使用 formal B（logical run `B-sft-formal-seed42`）完成 initial `10,000 × 8` sampled generation；固定 k=8、temperature=0.8、top_p=0.95、max_new_tokens=512、seed namespace 不变。
3. 1660 Ti 对完全相同 completion bytes 分别用 Public visible 与 Hidden train-hidden tests 做真实 Piston scoring；只对 initial 两边都 0/8 的 exact sorted retry IDs 生成第二块 8 samples，并再次 dual score。
4. 构建并严格重算 formal active pool：exact 3,000；SFT reuse exact 225 (7.5%，且 <=15%)；dual-informative >=70%；public-only <=15%；hidden-only <=15%；dual-uninformative=0；`quality_gate_required=true` 默认排除；不能满足则 fail closed，不放宽协议。
5. 新增仅用于 WP9-c validation 的 bounded tracked configs：
   - `configs/grpo/refresh-benchmark-public.yaml`
   - `configs/grpo/refresh-benchmark-hidden.yaml`
   - `configs/grpo/refresh-benchmark-k4-public.yaml`
   - `configs/grpo/refresh-benchmark-k4-hidden.yaml`
   - `configs/grpo/refresh-pilot-public.yaml`
   - `configs/grpo/refresh-pilot-hidden.yaml`
   k=8 benchmark 使用 20 steps；k=4 diagnostic 也使用同一 20-step workset，除 `num_generations=4` 外保持 k=8 benchmark scientific/runtime fields相同；pilot k=8 使用 100 steps。正式 `refresh-public.yaml` / `refresh-hidden.yaml` 300-step config不改。
6. 4090 完成 deterministic B eval generation batch sweep `[1,2,4,8,16]`，同一 formal 400 题、seed42、decode/model/checkpoint/order；full 400 exact completion/token/truncation parity 相对 batch=1。
7. 1660 Ti 对同一个 immutable batch=1 B generation bundle 完成 eval verification baseline workers=1 与 candidates `[8,16,32,64]`；结果/aggregate identity exact parity，formal host runtime telemetry完整。
8. 4090 基于 frozen active pool 完成真实 GRPO throughput benchmark sources：
   - k=8 Public workers 8 baseline + 16/32/64 candidates；
   - 一个 Public k=4 diagnostic（workers=8）与 k=8 workers=8 使用完全相同 bounded workset；
   - same-GPU Public/Hidden sequential pair + concurrent pair（workers=8，20-step bounded trial），用于 >=15% gain/stability rule；
   - 所有 source run 使用 `--benchmark-role k8_candidate|k4_diagnostic`，不要求尚未存在的 final benchmark report。
9. 在 target-local source artifacts 与从 control plane 同步回来的小型 eval-verification artifacts齐备后，构造 `wp9b-refresh-benchmark-v1` / `evidence_class: formal` manifest，运行 `summarize-refresh-benchmark` 并立即 strict `check_refresh_benchmark_report()`；冻结：
   - selected GRPO verification workers；
   - selected eval generation batch size；
   - selected eval verification workers；
   - paired GRPO mode (`sequential` 默认；只有 stable 且 >=15% wall-clock gain 才可 `concurrent`)；
   - k4 diagnostic warning signals；
   - canonical calibration/active-pool identity。
10. 使用 final benchmark report + formal calibration manifest 跑 k=8 Public/Hidden pilot，每 arm 至少 100 `group_metrics` groups，固定 sample_count=8；只改变 reward test source。记录真实 zero-variance、reward std、all-correct/all-zero、verifier/backward/optimizer/step timing、GPU util/VRAM、tokens/s、Piston retry/error telemetry。
11. WP9-c execution report 冻结给 WP9-d 的 exact artifact identities/hashes、runtime selections、pilot gate结果与 warnings；不生成 300-step C2/D2 formal checkpoints，不运行 C2/D2 400-problem evaluation。

### 2.3 范围外

- 不修改 WP9-a 数据协议、source/dedup/test-layer 定义；
- 不修改 formal B；不使用旧 C/D 或任何 C2/D2 intermediate checkpoint 做 calibration；
- 不读取或用于 calibration/pool selection 的 `eval_hidden_tests`；
- 不修改 Public/Hidden reward 公式、optimizer/LR/KL/LoRA/sampling 等 scientific config；
- 不把 k=4 升级为 formal alternate training campaign；
- 不运行 WP9-d 的 300-step C2/D2；
- 不运行 WP9-e 的 C2/D2 400题 final evaluation / paired statistics / final report；
- 不修改 `third_party/open-r1/`；
- planner 阶段不创建 branch/worktree/commit，也不启动任何 4090 command。

## 3. 前置条件与约束

- `proceedings.md` 是当前路由 authority：WP9-a/WP9-b 已 finalized；WP9-c 必须消费其正式 artifacts/contracts，不重做 development。
- Formal B 使用 `Qwen/Qwen2.5-Coder-1.5B-Instruct` 固定 revision、seed42、completed optimizer SFT checkpoint；operator-start 通过 production `load_completed_sft_checkpoint()` 重验，不接受 caller 手填 identity。
- Formal held-out B evaluation source保持历史 400 题：dataset SHA256 `770b772c738514888c5900f815fc074ddb3f6c3c5f67fc5346073565536138ae`；ordered problem IDs SHA256 `2d811d62613c122da6ee73f372008e44a40464ec9ad7c8df628ae01de4a234c9`；seed42/decode contract不变。
- Piston definition继续使用项目唯一 `1660ti-wsl` host / Python 3.10.0；4090 端只访问 `http://127.0.0.1:2000`。canonical transport是 1660 Ti 主动连接 provider public SSH endpoint并建立 loopback-only reverse forward `-R 127.0.0.1:2000:127.0.0.1:2000`；4090 不启动 legacy tunnel helper。
- 真实大型 artifacts留 persistent roots，不放 stage worktree，不提交 completion/checkpoint payload；Git只提交 config/test/plan/report/operator scripts等小型 provenance。
- Calibration scoring fixed control-plane operational workers=`8`。这是非 scientific latency choice；任何 infra failure都 fail closed，不自动把失败 completion记0、不在同一正式 score artifact中混用不同 workers。
- Formal benchmark builder当前要求全部 formal sections（eval generation/verification、GRPO verification、group-size diagnostic、paired GRPO）。若 20-step real concurrent pair不能产生 completed stable artifacts（例如双进程根本无法 fit），不得伪造“concurrent” source；停止 WP9-c 并记录 target-only blocker/repair need。

### 3.1 Execution preflight（首次业务修改/commit 前）

1. lifecycle bootstrap 后必须在 `.worktrees/wp9-c` / `feat/wp9-c`，worktree clean，`HEAD == plan_commit`，`.ai-bridge/**` zero tracked；不得在 main实现。
2. 确认 plan seal 的 `planning_base_commit` 是 `f1ffe6291182084146c557129efc6d121d872684`；若 bootstrap 前 main已变化则 replan，不静默沿用旧 base。
3. 读取当前 pinned runtime与当前 CLI/API；重点验证：
   - `prepare/generate/score/build-refresh-calibration`；
   - `load_grpo_benchmark_binding()` / `load_grpo_refresh_binding()`；
   - `train-grpo --benchmark-role --verification-workers`；
   - `generate-eval --batch-size`；`verify-eval --workers`；
   - `summarize-refresh-benchmark` / `check_refresh_benchmark_report()`。
4. 增加六个 validation config 与 config-contract tests后，在第一次 target gate前运行 focused tests、`make lint`、`make test`。任何源代码/API defect先作为 WP9-c tracked repair修复并重新过 gates；不得在 operator script里 monkeypatch production semantics。
5. 1660 Ti strict `check-refresh-data` 当前 formal WP9-a root，并确认上述 root/order hashes；准备 fresh Public-safe calibration input bundle。若 hash/10k count不匹配立即停止。
6. 若 control plane 可读 formal B，提前 strict load；若 B只在 target persistent root，则由 operator-start gate重验，不要求为了 planner/bootstrap复制大 checkpoint。

## 4. Operator terminal execution

```yaml
operator_terminal_execution:
  version: 1
  required: true
  gates:
    - gate_id: wp9c-calibration-initial-generation
      run_kind: calibration_generation
      executor_runs_command: false
      restart_policy: exact_rerun
      expected_artifacts:
        - "$CODE_VERIFIER_ARTIFACT_ROOT/wp9c/calibration/initial/run.json"
        - "$CODE_VERIFIER_ARTIFACT_ROOT/wp9c/calibration/initial/samples/generations.jsonl"
    - gate_id: wp9c-calibration-retry-generation
      run_kind: calibration_generation
      executor_runs_command: false
      restart_policy: exact_rerun
      expected_artifacts:
        - "$CODE_VERIFIER_ARTIFACT_ROOT/wp9c/calibration/retry/run.json"
        - "$CODE_VERIFIER_ARTIFACT_ROOT/wp9c/calibration/retry/samples/generations.jsonl"
    - gate_id: wp9c-eval-generation-sweep
      run_kind: evaluation
      executor_runs_command: false
      restart_policy: exact_rerun
      expected_artifacts:
        - "$CODE_VERIFIER_ARTIFACT_ROOT/wp9c/eval-generation/b1/generation/wp9c-b-eval-b1-seed42/run.json"
        - "$CODE_VERIFIER_ARTIFACT_ROOT/wp9c/eval-generation/b2/generation/wp9c-b-eval-b2-seed42/run.json"
        - "$CODE_VERIFIER_ARTIFACT_ROOT/wp9c/eval-generation/b4/generation/wp9c-b-eval-b4-seed42/run.json"
        - "$CODE_VERIFIER_ARTIFACT_ROOT/wp9c/eval-generation/b8/generation/wp9c-b-eval-b8-seed42/run.json"
        - "$CODE_VERIFIER_ARTIFACT_ROOT/wp9c/eval-generation/b16/generation/wp9c-b-eval-b16-seed42/run.json"
    - gate_id: wp9c-grpo-throughput-benchmark
      run_kind: grpo_benchmark
      executor_runs_command: false
      restart_policy: trainer_checkpoint
      expected_artifacts:
        - "$CODE_VERIFIER_ARTIFACT_ROOT/wp9c/benchmark/report/refresh_benchmark_report.json"
        - "$CODE_VERIFIER_ARTIFACT_ROOT/wp9c/benchmark/report/benchmark_manifest.yaml"
    - gate_id: wp9c-grpo-pilot
      run_kind: grpo
      executor_runs_command: false
      restart_policy: trainer_checkpoint
      expected_artifacts:
        - "$CODE_VERIFIER_ARTIFACT_ROOT/wp9c/pilot/wp9c-public-pilot100-seed42/run.json"
        - "$CODE_VERIFIER_ARTIFACT_ROOT/wp9c/pilot/wp9c-hidden-pilot100-seed42/run.json"
        - "$CODE_VERIFIER_ARTIFACT_ROOT/wp9c/pilot/wp9c-public-pilot100-seed42/group_metrics.jsonl"
        - "$CODE_VERIFIER_ARTIFACT_ROOT/wp9c/pilot/wp9c-hidden-pilot100-seed42/group_metrics.jsonl"
```

`wp9c-calibration-retry-generation` 是 protocol-conditional gate：只有 control-plane initial scoring 产生非空 canonical `retry_problem_ids.jsonl` 时才 materialize operator checkpoint/run.sh；若 exact retry manifest为空，execution report记录 `retry_required=false` + manifest SHA/count=0，不创建伪造的 target generation evidence，并直接以 `retry_scoring_dir=None` 构建 pool。

### 4.1 通用 portable operator contract

每个实际触发 gate 由 1660 executor在前置 acceptance 后生成一份 tracked、secret-free、immutable：
`ai-work/executor/operator/WP9-c/<gate>/<checkpoint>/run.sh`。

用户使 exact handoff commit 在4090可达，checkout/detach exact commit，确认 clean，重算 script SHA，再手工运行。Web GPT/CodexPro不得启动或持续监控 target command。

每次 attempt 取得 exclusive lock 后重新检查：
- exact handoff commit + script SHA + Git clean；
- target READY machine record；
- NVIDIA GPU总显存 >=22528 MiB、CUDA/BF16可用；
- `$CODE_VERIFIER_ARTIFACT_ROOT` / `$CODE_VERIFIER_DATA_ROOT` / `$HF_HOME` 存在、持久、writable；
- exact formal B可由 `load_completed_sft_checkpoint()` strict load，本地 base model/revision/cache可离线访问；
- 需要Piston的GRPO gates：4090 `127.0.0.1:2000` listener、`/api/v2/runtimes`与项目 `PistonExecutor.validate_runtime()` 均确认 exact Python 3.10.0；
- 不把 credential、provider hostname/port/auth、test payload写进Git/evidence。

每个 gate command rc后必须运行 plan-specific strict postcheck。只有 `command_rc=0 && postcheck_rc=0` 才允许 `gate_status=passed`。`operator-evidence.json` 记录 exact commit/script SHA、machine-record SHA、GPU/runtime/root identity、Piston identity（若适用）、timestamps、command/postcheck rc、formal source/output hashes/counts、expected-artifact inventory；不能证明的大artifact property由postcheck现场验证并写aggregate/hash evidence。

### 4.2 Gate A — initial calibration generation

触发前：1660 已生成并 strict check Public-safe 10k calibration input bundle，并把 exact bundle同步到 target data root；formal B ready。

命令模板：
```bash
B_RUN="$CODE_VERIFIER_ARTIFACT_ROOT/sft/B-sft-formal-seed42"
INPUT="$CODE_VERIFIER_DATA_ROOT/wp9c/calibration-input"
OUT="$CODE_VERIFIER_ARTIFACT_ROOT/wp9c/calibration/initial"

code-verifier generate-refresh-calibration \
  --config configs/grpo/refresh-calibration.yaml \
  --input-bundle-dir "$INPUT" \
  --sft-run-dir "$B_RUN" \
  --block initial \
  --output-dir "$OUT"
```

storage gate：至少 30 GiB free、100000 free inodes。

Postcheck：production `load_completed_calibration_generation()` PASS；block=0；10,000 problems / 80,000 records；sample indices/order/hash exact；B identity exact；input manifest/hash exact；completion/token/truncation fields finite/typed；bundle中没有 visible/train-hidden/eval-hidden tests、reference solution、SFT response。然后把完整 immutable generation bundle + small operator evidence同步回1660。

Restart：same identity允许 production exact-prefix resume；identity变化时保留旧 incomplete attempt并 quarantine，不能覆盖。

### 4.3 Control-plane initial score / retry decision

1660 收到 initial bundle后：
```bash
code-verifier score-refresh-calibration \
  --dataset-dir <formal-wp9a-root> \
  --reference-dataset-dir <formal-reference-root> \
  --input-bundle-dir <formal-calibration-input> \
  --generation-run-dir <synced-initial-generation> \
  --piston-config configs/execution/piston-local.yaml \
  --workers 8 \
  --output-dir <fresh-initial-score-root>
```

接受标准：同completion bytes双 verifier；0 infrastructure failures；records覆盖exact 10k；retry manifest只含两边初始 test reward 都0/8的sorted unique IDs；score manifest绑定 generation/input/WP9-a/B identity。若Piston infra失败，不发布formal score，修环境后对同bundle fresh重跑；不得把infra failure降格为reward0。

### 4.4 Gate B — conditional retry generation

若 retry_count>0：同步 exact retry manifest到target，运行：
```bash
code-verifier generate-refresh-calibration \
  --config configs/grpo/refresh-calibration.yaml \
  --input-bundle-dir "$CODE_VERIFIER_DATA_ROOT/wp9c/calibration-input" \
  --sft-run-dir "$CODE_VERIFIER_ARTIFACT_ROOT/sft/B-sft-formal-seed42" \
  --block retry \
  --retry-manifest "$CODE_VERIFIER_DATA_ROOT/wp9c/retry_problem_ids.jsonl" \
  --output-dir "$CODE_VERIFIER_ARTIFACT_ROOT/wp9c/calibration/retry"
```

storage gate：20 GiB / 100000 inodes。
Postcheck：block=1；record_count=`retry_count*8`；problem IDs/order exactly retry manifest；sample indices8..15；同B/input identity；strict loader PASS。同步bundle回1660后用同样 `score-refresh-calibration --workers 8` 真实双 verifier scoring。

### 4.5 Control-plane active-pool freeze

```bash
code-verifier build-refresh-active-pool \
  --config configs/grpo/refresh-calibration.yaml \
  --dataset-dir <formal-wp9a-root> \
  --reference-dataset-dir <formal-reference-root> \
  --input-bundle-dir <formal-calibration-input> \
  --initial-scoring-dir <formal-score0> \
  [--retry-scoring-dir <formal-score1>] \
  --seed 42 \
  --output-dir <fresh-formal-active-pool>
```

紧接 production `check_calibrated_active_pool()` 重算。必须 exact 3000 / SFT 225 / dual>=2100 / public-only<=450 / hidden-only<=450 / dual-uninformative0；quality-required全部排除；Public/Hidden IDs/order相同且test-layer隔离正确；manifest evidence_class=`formal_calibration`。若 selector/quality constraints失败，WP9-c停止并报告真实 population，不调阈值。

### 4.6 Gate C — formal B evaluation generation batch sweep

把 formal 400题 prepared data + B同步/确认在 target。对 batch `1,2,4,8,16` 分别fresh output root运行：
```bash
code-verifier generate-eval \
  --config configs/eval/base.yaml \
  --dataset-dir "$CODE_VERIFIER_DATA_ROOT/prepared" \
  --sft-run-dir "$CODE_VERIFIER_ARTIFACT_ROOT/sft/B-sft-formal-seed42" \
  --run-name "wp9c-b-eval-b${BATCH}-seed42" \
  --seed 42 \
  --batch-size "$BATCH" \
  --output-dir "$CODE_VERIFIER_ARTIFACT_ROOT/wp9c/eval-generation/b${BATCH}"
```

storage gate：20 GiB / 100000 inodes。

Postcheck：每bundle v2 completed / 400 rows；dataset hash/order hash与 frozen 400题一致；same B/checkpoint/seed/decode/scientific identity；formal runtime utilization完整；调用 `compare_generation_bundle_parity(batch1, candidate)` 对2/4/8/16全部 exact（completion bytes、completion_tokens、hit_max_new_tokens）；任何candidate不parity只会被report拒绝，不能篡改completion。同步5个immutable小generation bundles回1660。

### 4.7 Control-plane eval verification sweep

仅使用同一 batch=1 generation bundle，分别用workers `1,8,16,32,64` 运行 fresh `verify-eval` roots；每次真实 local Piston。所有run必须 400/400、结果/aggregate semantic exact parity、0 infrastructure failure、host CPU/RSS + timing telemetry完整。记录CLI返回的exact run_dir。随后把这5个verification run dirs（小型，不含秘密）同步回target `$CODE_VERIFIER_DATA_ROOT/wp9c/eval-verification-sources/`，供 formal benchmark report target-local strict rebuild。

### 4.8 Gate D — GRPO throughput sources + formal benchmark freeze

触发前：formal active pool已同步target，并在target用 production strict checker重验；eval generation sweep仍在target；5个1660 eval-verification source已同步target；Piston reverse tunnel ready。

新增的 bounded configs固定：
- k8 benchmark Public/Hidden：num_generations=8，max_steps=20；除 run_name/reward_mode/dataset path外成对一致，其余scientific fields匹配refresh formal config；
- k4 diagnostic Public/Hidden：与k8 benchmark完全同workset/runtime/config，唯一主protocol差异num_generations=4；max_steps=20；
- 不修改300-step formal refresh configs。

所有GRPO benchmark命令共同参数：same B、same active pool、seed42、same Public/Hidden config pair、fresh unique run names；使用 `--calibration-manifest <pool>/calibration_manifest.json --refresh-dataset-dir <wp9a> --reference-dataset-dir <reference>`；pre-freeze source只传 `--benchmark-role`，**不传** `--benchmark-report`。

实际source set：
1. Public k8 workers=8（baseline）；
2. Public k8 workers=16；
3. Public k8 workers=32；
4. Public k8 workers=64；
5. Public k4 workers=8 diagnostic；
6. Hidden k8 workers=8 sequential pair source；
7. Public k8 workers=8 concurrent-trial source；
8. Hidden k8 workers=8 concurrent-trial source。

前6个按顺序单独运行；7/8在同一个script attempt中同时启动并wait，必须有真实 timestamp overlap。每个run expected role/group size、calibration identity、B/pool/problem order、reward source、20-step config、runtime telemetry、reward/group parity schema严格。

storage gate：至少50 GiB free、200000 inodes；并发trial启动前必须确认两trainer估算峰值可在24GB内保留合理headroom。若preflight或真实trial表明不能fit/不能完成，不能伪造concurrent evidence；WP9-c fail closed并返回control plane。

Restart：单独worker/diagnostic/sequential source可从其same-run最新合法Trainer checkpoint恢复，但发生中断的attempt不得作为formal throughput timing source；保留checkpoint用于恢复/诊断，随后由lifecycle明确产生新的formal benchmark attempt。并发pair若任一member未在同一overlap attempt完整完成，则该pair不作为formal paired source，不能用一个arm完成记录拼另一个arm。

全部source完成后，target生成 fresh `benchmark_manifest.yaml`：
```yaml
version: wp9b-refresh-benchmark-v1
evidence_class: formal
eval_generation:
  baseline: <target batch1 generation run dir>
  candidates:
    - <batch2>
    - <batch4>
    - <batch8>
    - <batch16>
eval_verification:
  baseline: <synced workers1 verification run dir>
  candidates:
    - <synced workers8>
    - <synced workers16>
    - <synced workers32>
    - <synced workers64>
grpo_verification:
  baseline: <k8-public-workers8>
  candidates:
    - <k8-public-workers16>
    - <k8-public-workers32>
    - <k8-public-workers64>
grpo_group_size_diagnostic:
  k4: <k4-public-workers8>
  k8: <k8-public-workers8>
paired_grpo:
  sequential:
    public: <k8-public-workers8>
    hidden: <k8-hidden-workers8-sequential>
  concurrent:
    public: <k8-public-workers8-concurrent>
    hidden: <k8-hidden-workers8-concurrent>
```

然后：
```bash
code-verifier summarize-refresh-benchmark \
  --manifest "$CODE_VERIFIER_ARTIFACT_ROOT/wp9c/benchmark/benchmark_manifest.yaml" \
  --output-dir "$CODE_VERIFIER_ARTIFACT_ROOT/wp9c/benchmark/report"

python -c 'from pathlib import Path; from code_verifier.throughput import check_refresh_benchmark_report; check_refresh_benchmark_report(Path("<report>/refresh_benchmark_report.json"))'
```

Postcheck必须证明：formal evidence；GRPO sections共享exact calibration identity；selected workers来自8/16/32/64且reward/group parity无drift；k4 diagnostic仅产生warning，不改变primary_protocol=k8；eval selected batch exact parity且tokens/s不低于batch1；eval selected verification exact parity；paired mode只有 stable + >=15% gain才是concurrent，否则sequential。报告 + snapshotted manifest + small source-hash inventory同步回1660；大GRPO source默认留target。

若 `grpo_group_size_diagnostic.reconsider_k8=true`，不得静默进入WP9-d：WP9-c仍完成证据收集，但 advancement必须由独立review明确处理warning/决定是否replan。

### 4.9 Gate E — selected-runtime Public/Hidden k=8 pilot

触发前：formal benchmark report strict PASS，active pool/B exact，selected GRPO workers和paired mode已冻结。Pilot config k=8/max_steps100，与formal refresh scientific hyperparameters保持一致，区别仅bounded budget/run identity。

Public/Hidden都使用：
```text
--calibration-manifest <formal pool>/calibration_manifest.json
--refresh-dataset-dir <formal wp9a root>
--reference-dataset-dir <formal reference root>
--benchmark-report <formal benchmark report>/refresh_benchmark_report.json
--verification-workers <report selected_grpo_verification_workers>
--seed 42
```

各自从同一个B独立初始化，不允许Public→Hidden parent链。若report paired mode=`sequential`，顺序运行两arm；若=`concurrent`，在同一attempt并发两arm且仍各自独立B/run dir。

storage gate：至少40 GiB free、150000 inodes。

Postcheck：
- 两run `status=completed`，parent B/config/pool/calibration/benchmark/worker identity一致，reward modes分别public/hidden；
- 每arm `group_metrics.jsonl` 至少100 groups；每group sample_count=8；
- no OOM / NaN / Inf / infrastructure failure；real nonempty rewards/rollouts/group/metrics；final adapter strict loadable；
- test/total reward std、all-correct/all-zero、zero-variance、verifier/backward/optimizer/step timing全部finite nonnegative；formal GPU utilization/VRAM/token throughput完整；
- 计算 `total_reward all-equal` zero-variance fraction：
  - `<0.20`：green / target met；
  - `0.20..0.25`（含边界20%，不超过25%）：warning，记录raw evidence并要求独立review在推进WP9-d前显式处置；不得自动调参；
  - `>0.25`：stop/recalibrate，WP9-c不得解锁WP9-d；优先回查pool/calibration/test-layer/reserve，而不是立即改算法。
- 若k8 diagnostic warning或pilot warning存在，execution report保留原始数字、artifact hashes与明确status，不做选择性报告。

## 5. 实施步骤

### 步骤1：增加 bounded WP9-c GRPO validation configs及静态合同测试

**目标文件**：
- 新增 `configs/grpo/refresh-benchmark-public.yaml`
- 新增 `configs/grpo/refresh-benchmark-hidden.yaml`
- 新增 `configs/grpo/refresh-benchmark-k4-public.yaml`
- 新增 `configs/grpo/refresh-benchmark-k4-hidden.yaml`
- 新增 `configs/grpo/refresh-pilot-public.yaml`
- 新增 `configs/grpo/refresh-pilot-hidden.yaml`
- 新增 `tests/unit/training/test_grpo_refresh_validation_configs.py`

**新增/修改符号**：无production Python symbol；仅tracked config + contract tests。

测试断言：
- k8 benchmark pair `validate_grpo_config_pair()` PASS，num_generations=8/max_steps=20；
- k4 diagnostic pair PASS，num_generations=4/max_steps=20；k4/k8 benchmark除group size与run/reward/dataset identity外scientific/runtime fields一致；
- pilot pair num_generations=8/max_steps=100，除bounded max_steps/run identity外与300-step refresh formal scientific hyperparameters一致；
- legacy `configs/grpo/public.yaml` / `hidden.yaml`仍k=4；formal `refresh-public.yaml` / `refresh-hidden.yaml`仍k=8/max_steps300；
- config pair的Public/Hidden只在允许fields不同。

验证：focused pytest + `make lint` + `make test`。

### 步骤2：prepare formal calibration input并冻结source identity

**消费符号**：`prepare_calibration_input_bundle()` / `check_refresh_data()`。

1660 fresh output生成10k Public-safe input；strict readback + hash inventory；禁止任何hidden/reference/SFT response字段。把bundle作为Gate A input同步target。

### 步骤3：执行Gate A，回1660完成initial dual scoring

按§4.2/4.3；output不进Git；execution report记录operator evidence SHA、generation run/records SHA、retry count、class summary前的raw source identity。

### 步骤4：若需要执行Gate B；冻结formal active pool

按§4.4/4.5；最终 `check_calibrated_active_pool()` 是唯一pool acceptance authority。把完整active pool（3k Public/Hidden training views + manifests/reports）同步target供benchmark/pilot。

### 步骤5：执行Gate C并在1660完成eval verification sweep

按§4.6/4.7。验证candidate generation exact parity、verification parity、formal runtime telemetry；同步verification source dirs到target。

### 步骤6：执行Gate D，冻结formal throughput report

按§4.8。所有benchmark数字只能由actual source artifacts推导。不得手填tokens/s、walltime、VRAM、zero-var等scientific/system metrics。

### 步骤7：执行Gate E，应用zero-variance pilot gate

按§4.9。Public/Hidden必须同B、同pool、同benchmark、同selected workers、同seed和同scientific config；只有reward test source不同。

### 步骤8：control-plane completion inventory与WP9-d handoff evidence

目标文件：`ai-work/executor/WP9-c-executor.md`（executor append-only lifecycle写入）；不修改spec/proceedings。

记录：
- WP9-a/B/calibration/pool hashes；
- initial/retry counts与class composition；
- benchmark report SHA与selections；
- k4 diagnostic warning fields；
- paired mode/gain/stability；
- pilot每arm group count/zero-var fraction/核心telemetry/errors；
- 每个operator evidence byte SHA；
- 明确 `ready_for_wp9d: true|false` 及原因。

只有独立 reviewer PASS + lifecycle finalize 后才能由 proceedings 推进next stage；executor不得自行改proceedings。

## 6. 总体验收与测试计划

### 6.1 Control-plane code/config gates

```bash
.venv/bin/python -m pytest \
  tests/unit/training/test_grpo_refresh_validation_configs.py \
  tests/unit/training/test_calibration.py \
  tests/unit/training/test_grpo_refresh_binding.py \
  tests/unit/test_throughput_grpo.py \
  tests/unit/test_throughput.py \
  tests/unit/evaluation/test_generate.py \
  tests/unit/evaluation/test_staged.py \
  tests/integration/test_wp9b_refresh_engineering.py

make lint
make test
```

如果 config-only 增量不需要production source repair，除六个config/测试/执行报告/operator scripts外不应产生业务代码diff。若真实target暴露API/schema defect，必须以明确WP9-c repair commit+tests解决，不能在run.sh里绕过strict checker。

### 6.2 Real evidence gates

- Calibration：formal B / 10k initial k8 generation / exact conditional retry / dual real-Piston scoring；无mock/synthetic替代。
- Pool：formal strict active pool exact 3000、225 SFT overlap、class caps、quality exclusion、hash/provenance重算。
- Evaluation throughput：formal B 400题 batch1/2/4/8/16 real generation + 1660 workers1/8/16/32/64 real verification。
- GRPO throughput：real 24GB k8 workers sweep、real k4 diagnostic、real sequential/concurrent bounded trials；all source artifacts strict。
- Pilot：real 24GB k8 Public/Hidden >=100 groups/arm，selected runtime binding，real Piston rewards。

### 6.3 最终标准

- [ ] WP9-b finalized base未被重写，third_party/open-r1未修改
- [ ] formal calibration只使用B，不使用旧C/D/C2/D2/eval-hidden
- [ ] initial 10k×8和conditional retry contract严格完成
- [ ] active pool strict=3000；SFT=225；dual>=70%；single-arm各<=15%；dual-uninformative=0；quality-required排除
- [ ] k8仍是primary protocol；k4只是一条20-step controlled diagnostic
- [ ] formal benchmark report strict可重算于target source locality，且canonical calibration identity跨GRPO sections一致
- [ ] selected GRPO workers ∈ {8,16,32,64}
- [ ] eval batch selection来自full-400 exact parity；selected eval verification来自exact-result parity
- [ ] same-GPU只有stable且gain>=15%才可concurrent，否则sequential
- [ ] Public/Hidden pilot各>=100 groups，sample_count=8，same B/pool/benchmark/seed/config，仅reward source不同
- [ ] no OOM/NaN/Inf/infra failure；formal GPU/runtime/Piston telemetry完整
- [ ] zero-var >25%时明确STOP；20–25% warning不被隐藏；<20% target明确记录
- [ ] diagnostic `reconsider_k8=true` 时不自动推进WP9-d
- [ ] `make lint` PASS；`make test` PASS；focused tests PASS
- [ ] `.ai-bridge/**` zero tracked；大型payload未进入Git
- [ ] 未运行300-step C2/D2、未生成C2/D2 formal checkpoint、未做WP9-e final evaluation/analysis

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
    - "WP9-c存在严格证据链：formal input → initial generation → control-plane scoring/retry → active pool → eval/GRPO benchmark sources → frozen benchmark report → selected-runtime pilot；后续每一步都hash-bind前一步真实artifact。"
    - "跨1660/4090虽然有多个物理任务，但Public/Hidden fairness、operator checkpoint、target-local benchmark source locality、conditional retry与最终zero-variance gate都要求一个串行orchestrator维持唯一execution truth；并行executor会增加pool/report/run identity漂移风险。"
  workstream_candidates: []
```

## 8. 风险与注意事项

- **Calibration规模**：10k×8真实B generation是大任务；exact-prefix resume必须保留，禁止因中断重新采样不同seed。
- **Pool不足**：如果quality exclusions + real variance无法满足3000/70-15-15，不得降低threshold；这本身是WP9-c科学结果/blocker。
- **Cross-machine benchmark locality**：formal GRPO strict source会递归验证parent B path，因此最终benchmark report应在4090 source locality内生成/strict check；1660的eval-verification小artifacts反向同步target。control-plane保留report/evidence SHA；review如需重新证明大source property可做短时target read-only check，不篡改artifact。
- **Concurrent trial**：当前formal report schema要求paired section。若双trainer实际不能fit，不能用顺序run冒充concurrent；这是target-only blocker，需repair/replan。
- **20-step benchmark vs 100-group pilot**：benchmark只决定operational throughput，不产生模型质量结论；pilot才应用zero-variance gate。不得把20-stepk8/k4差异写成held-out learning conclusion。
- **k4 warning**：`reconsider_k8`只是诊断信号；不得自动切协议，也不得忽略。任何主协议变更必须用户/独立review明确决定并replan。
- **Runtime retry**：transport retry/error不能被记成正常reward；formal benchmark candidates要求parity/stability。被中断的throughput attempt不得拿恢复后混合walltime冒充clean formal timing。
- **Pair fairness**：Public/Hidden pilot各从B独立启动；不能Public checkpoint喂Hidden。若concurrent mode后续暴露不稳定，不得只重跑一arm或单侧改config。
- **No eval-hidden leakage**：calibration input/generation完全不携带hidden tests；control-plane dual scoring只用visible/train-hidden；eval-hidden只属于独立held-out evaluation数据，不参与pool/pilot selection。
- **Artifact paths**：plan只使用persistent-root变量和logical run names；operator machine的provider路径/credentials永不写入tracked files。

## 9. 关联文档/代码索引

- `proceedings.md`：WP9 track activation；WP9-a finalized；WP9-b finalized / next=`WP9-c`；control-plane/portable-target/reverse-SSH amendments。
- `PROJECT_SPEC_GRPO_Refresh.md`：§7 calibration；§8–§10 k8/zero-var/throughput/concurrency；§11 eval batching；§12 benchmark contract；§13 artifacts；§14 pre-formal gates；§16 defaults；§17.2 WP9-c。
- `PROJECT_SPEC_Open-R1_CodeVerifier.md`：§19 validation evidence；§20 development/control-plane/operator lifecycle；§21 review；§29 defaults。
- `ai-work/reviewer/WP9-b-review.md` R4 user-authorized k8 primary / k4 diagnostic override；R6 PASS/target-ready contracts。
- `src/code_verifier/training/calibration.py`：`prepare_calibration_input_bundle`, `run_calibration_generation`, `score_calibration_generation`, `build_calibrated_active_pool`, `check_calibrated_active_pool`。
- `src/code_verifier/training/grpo.py`：`load_grpo_benchmark_binding`, `load_grpo_refresh_binding`, `run_grpo_training`, completed checkpoint loaders。
- `src/code_verifier/throughput.py`：`compare_generation_bundle_parity`, `summarize_refresh_benchmarks`, `check_refresh_benchmark_report`。
- `src/code_verifier/evaluation/staged.py` / `generate.py`：batched generation + staged verification。
- `src/code_verifier/cli.py`：refresh calibration, train-grpo benchmark/final binding, generate/verify eval, benchmark summary commands。

## 10. Handoff

1. 下一步只能运行 `$stage-lifecycle bootstrap_plan`：使用本正文创建/复用 `feat/wp9-c` + `.worktrees/wp9-c`，把计划写入 `ai-work/planner/WP9-c-plan.md` 并commit plan seal。
2. bootstrap前再次要求primary `HEAD == f1ffe6291182084146c557129efc6d121d872684`、worktree set没有新增active stage、`.ai-bridge/current-plan.md`仍是本plan、`.ai-bridge/**` zero tracked。任何不一致→停止/replan。
3. bootstrap成功得到 `plan_commit` 后才调用execution-router；routing=`single / difficult_serial`。
4. execution先完成六个bounded config + tests/control-plane preflight；遇到第一个24GB gate生成tracked portable run.sh并停在`AWAITING_OPERATOR`。每次用户同步evidence后显式resume，直到下一gate。
5. WP9-c completed execution后必须由新的独立conversation运行 reviewer-ex；executor不自review、不改proceedings。
6. 只有 reviewer PASS + lifecycle finalize 后，proceedings才能把next dependency-ready推进至 WP9-d formal C2/D2。

## Implementation contract

- Work from this plan in small, reviewable steps.
- Keep edits scoped to WP9-c validation configs/evidence contracts; do not alter scientific definitions without explicit replan.
- Run focused verification before each operator handoff.
- Update `.ai-bridge/agent-status.md` with files touched, checks run, results, blockers, operator checkpoint/evidence state, and review notes.
- Save final review diff to `.ai-bridge/implementation-diff.patch` when practical.
- Append notable execution events to `.ai-bridge/execution-log.jsonl` when supported.

## Implementation contract

- Work from this plan in small, reviewable steps.
- Keep edits scoped to the requested task and existing project conventions.
- Run focused verification before handing work back.
- Update .ai-bridge/agent-status.md with files touched, checks run, results, blockers, and review notes.
- Save the final review diff to .ai-bridge/implementation-diff.patch when practical.
- Append notable execution events to .ai-bridge/execution-log.jsonl when the implementation agent supports logging.
