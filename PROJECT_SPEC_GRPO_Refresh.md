# Open-R1 CodeVerifier GRPO Refresh Specification

**状态：** Active v1.0  
**日期：** 2026-08-31  
**范围：** 在已完成 seed-42 A/B/C/D 实验之后，对 GRPO 数据、reward signal、训练吞吐与 400 题评测效率进行第二阶段改造。  
**与原项目关系：** 本规格是当前 post-WP8 / WP9 active research addendum，不追溯修改、不覆盖、不重新解释 `PROJECT_SPEC_Open-R1_CodeVerifier.md`、`proceedings.md` 与 `report/` 中已经完成的 A/B/C/D 证据。对于 WP9 范围内与原规格冲突的默认值，本文件优先；依据本规格产生的新实验必须使用新的 run identity，且与历史 C/D artifact 严格区分。active track 与 next stage 由 `proceedings.md` 最新 decision record 锚定。

---

# 1. 背景与动机

第一轮正式实验已经形成有效的单训练 seed 基线，但同时暴露出两个需要在下一轮 GRPO 前修正的设计/效率问题。

## 1.1 SFT 与 GRPO 训练题目重合过高

正式 SFT、Public-GRPO 与 Hidden-GRPO 训练 artifact 都来自同一个 2500 题 train split。正式 C/D 实际消费了 600 个不同 GRPO problem group，而这 600 道题全部已经在 SFT 中以监督 solution trajectory 的形式出现过。

这不是 evaluation leakage：`eval_hidden_tests` 仍然保持隔离。但是，它改变了 GRPO 结果的科学含义。当前设置更接近研究：

> 在模型已经通过 SFT 看过正确解法的题目上，verifier-based RL 能否进一步重塑输出策略？

而不充分覆盖：

> GRPO 能否依靠 trial-and-error 与 executable verifier，在 SFT 没有直接监督过的新训练问题上获得新的学习信号？

下一轮必须显著降低 SFT/GRPO problem overlap，但**不要求完全不重合**。保留少量重合有利于连续性、难度标定以及同题对照。

## 1.2 Zero-variance GRPO group 比例过高

原正式 C/D 使用 `num_generations=4`。按 total reward 统计：

- Public-RLVR：193 / 600 = 32.17% group 内 total reward 全相同；
- Hidden-RLVR：191 / 600 = 31.83% group 内 total reward 全相同。

按 test reward 粗分类：

- 约 12% group 为 4 个 completion 全部测试通过；
- 约 26% group 为 4 个 completion 全部 test reward 为 0；
- 其余 group 才存在明显 test-derived reward 差异。

GRPO 依赖同组候选之间的相对 reward。大量 zero-variance group 会消耗 generation、verification 与 GPU 时间，却几乎不提供 reward-driven ranking signal。

下一轮必须把“当前 policy 下这道题是否能产生 reward variance”提升为数据筛选与训练监控的一等指标，而不是假定所有合法 coding problem 都同样适合 GRPO。

## 1.3 GPU 与端到端吞吐需要提升

第一轮工程优先级是可信、可恢复、可审计。下一轮必须保留这些性质，同时提高吞吐：

- `num_generations` 从 4 提高到 8；
- Public/Hidden 是否能并行必须通过 benchmark 决定，不能预设；
- 一个 rollout group 内的 verifier execution 应尽量使用安全的 bounded concurrency；
- 400 题正式 evaluation 不应继续默认逐题单条 GPU generation，如果 batching 可以保持完全相同的 metric 语义；
- generation、verification、optimizer 三段耗时必须分开记录，能明确看出 GPU 是否在等待 verifier。

---

# 2. 新一轮核心研究问题

**RQ-R1 — New-problem GRPO**  
当绝大多数 GRPO 训练题没有用于 SFT solution supervision 时，GRPO 是否能在独立 held-out code correctness 上超过冻结的 B checkpoint？

**RQ-R2 — Verifier quality**  
在 parent SFT checkpoint、问题池、sampling、训练预算、优化配置和最终评测完全匹配的条件下，Hidden-RLVR 是否比 Public-RLVR 提供更有效的 learning signal 或更好的 held-out generalization？

**RQ-R3 — Reward informativeness**  
基于冻结 B 的 offline difficulty / reward-variance calibration，能否显著降低 zero-variance group，并提高单位 GPU-hour 的有效更新密度？

**RQ-R4 — Systems efficiency**  
generation batching、verifier concurrency 与受控并行能否在不改变模型、reward、数据隔离和评测语义的前提下降低 wall-clock cost？

---

# 3. 非目标

本规格不要求：

- 更换 `Qwen/Qwen2.5-Coder-1.5B-Instruct` 主模型；
- 将 executable verifier 替换为 LLM judge 或 learned reward model；
- 使用 `eval_hidden_tests` 做训练、curriculum、candidate filtering、candidate selection 或 early stopping；
- 追溯重写第一轮 A/B/C/D 的结论；
- 未经 benchmark 就直接切换 vLLM、CUDA MPS、DeepSpeed 或多 GPU 训练；
- 在主 C2/D2 对照实验中使用会导致两个实验臂看到明显不同数据分布的 arm-local dynamic rejection sampling；
- 为提高吞吐而降低 artifact provenance、checkpoint resume、安全沙箱或 hidden-test isolation 要求。

---

# 4. 规范性术语

本文使用：

- **MUST / MUST NOT**：正式 refreshed run 的硬要求；
- **SHOULD / SHOULD NOT**：默认应遵守，只有在正式 run seal 前已有 benchmark / documented constraint 时才允许偏离；
- **MAY**：可选扩展，不能在未修订规格的情况下改变 primary result 定义。

---

# 5. 实验身份

原实验保持不可变：

- A：原 Instruct baseline；
- B：原正式 SFT seed-42 checkpoint；
- C：原 Public-RLVR seed-42；
- D：原 Hidden-RLVR seed-42。

刷新后的 GRPO 必须使用新的实验身份，推荐：

- **C2 — Public-RLVR Refresh**；
- **D2 — Hidden-RLVR Refresh**。

除非后续规格明确重新训练 SFT，C2/D2 MUST 从同一个冻结 B checkpoint 出发。任何新 run MUST NOT 覆盖历史 C/D artifact directory。

---

# 6. GRPO 数据设计

## 6.1 Public/Hidden 必须共享同一问题池

C2 与 D2 MUST 使用：

- 同一个 canonical GRPO problem pool；
- 同一 frozen sampling/order manifest；
- 同一 prompt construction；
- 同一 visible information；
- 同一 source/difficulty composition。

主实验唯一预期差异仍然是：

```text
C2: visible_tests reward
D2: train_hidden_tests reward
```

## 6.2 SFT/GRPO overlap policy

不追求 SFT 与 GRPO 完全不同，而是显式控制重合比例。

最终 canonical GRPO pool 的默认要求：

```yaml
sft_grpo_overlap:
  target_fraction_of_grpo: 0.05-0.10
  hard_max_fraction_of_grpo: 0.15
  min_new_fraction_of_grpo: 0.85
```

含义：

- 推荐 5–10% GRPO problem 在 SFT 中出现过；
- **硬上限 15%**；
- 至少 **85% GRPO problem 必须是相对 SFT 的新问题**。

分母是最终 canonical GRPO pool 大小。

重合统计 MUST 同时计入：

- exact `problem_id` / source-ID match；
- 规范化题面一致；
- 被 near-dedup 判定为同一道题的轻度改写、重命名或格式变化。

不能通过重命名问题或轻度改写题面把 SFT problem 伪装成“新 GRPO 数据”。

### 6.2.1 重合子集的选择

允许重合的 5–10% SHOULD 使用冻结、可重复的 deterministic selection 规则，并尽量保持 source/difficulty 分布代表性。

重合题必须和新题一样通过 calibration gate，不能因为“它来自已有 SFT 集”而免除 reward-informativeness 要求。

## 6.3 Evaluation 数据仍要求 0 overlap

以下重合仍然严格禁止：

```yaml
overlap_with_validation: 0
overlap_with_project_test: 0
overlap_with_external_final_evaluation: 0
```

任何 GRPO candidate 如果与以下数据存在 exact 或 accepted near-duplicate，MUST 被排除：

- 项目 validation split；
- 当前 400 题 project test split；
- HumanEvalPlus 或其它已冻结 external final evaluation；
- 在 GRPO 数据封存前已经确定的未来 final-evaluation set。

## 6.4 新 candidate data source

新一轮 SHOULD 先建立明显大于最终 GRPO pool 的候选池。

当前优先候选包括：

1. `PrimeIntellect/verifiable-coding-problems`；
2. `agentica-org/DeepCoder-Preview-Dataset`；
3. `open-thoughts/CodeContests` 或其 underlying CodeContests executable tasks；
4. 后续发现的其它可验证 competitive-programming / function-level coding 数据。

这些只是 candidate source，不代表可以直接进入训练。

每个 source MUST 在正式 materialization 前冻结：

- dataset revision / commit / snapshot identity；
- license / provenance；
- raw file hash 或等价 dataset fingerprint；
- source-specific schema mapping。

由于 PrimeIntellect / DeepCoder 等候选源本身可能包含 TACO、APPS、LeetCode 或 LiveCodeBench 派生内容，跨 source dedup 是硬要求。

## 6.5 数据规模

推荐：

```yaml
candidate_pool_after_basic_validation: 10000-30000
calibrated_eligible_pool_min: 2500
formal_grpo_pool_target: 2500-4000
```

第一轮默认目标：

```yaml
formal_grpo_pool_target: 3000
```

最终 pool SHOULD 大于正式训练预计实际消费的 unique problem 数，避免训练很快反复消费一个过小的 problem set。

## 6.6 Dedup 要求

每个 candidate MUST 至少经过：

1. exact source ID / in-source ID 去重；
2. normalized problem-statement hash；
3. function signature / I/O contract 对比（可用时）；
4. canonical token / n-gram similarity；
5. source URL / source metadata 比对（可用时）；
6. reference-solution / test fingerprint 相似度（合法且可用时）；
7. 与 SFT、validation、project test、external evaluation manifest 的显式比对。

必须输出 machine-readable dedup manifest，至少包含：

- candidate ID；
- retained/rejected；
- rejection reason；
- matched existing problem（如存在）；
- overlap class；
- source identity。

## 6.7 新问题的三层测试要求

新 GRPO problem MUST 继续遵守项目原有三层 test contract：

- `visible_tests`：允许进入 prompt；Public-RLVR 使用；
- `train_hidden_tests`：不得进入 prompt；Hidden-RLVR 使用；
- `eval_hidden_tests`：任何 training reward / calibration selection 均不得使用。

新题经过 normalization 后 SHOULD 至少有 8 个互不重复、已验证 executable tests。

推荐最低分配：

```yaml
visible_tests: 2+
train_hidden_tests: 3+
eval_hidden_tests: 3+
```

少于 8 个测试的题 MAY 保留在 candidate pool，但进入正式 active pool 前必须经过独立 data-quality gate，证明 Public/Hidden verifier 区分仍有意义。

如果需要 test repair / synthetic test generation：

- 必须使用可信 reference solution 验证；
- 必须做 test-level dedup；
- 必须保持与现有 leakage contract 相同的隔离等级。

---

# 7. Offline Difficulty / Reward-Variance Calibration

## 7.1 Calibration model

MUST 使用冻结 parent SFT checkpoint B。

MUST NOT 使用：

- 原 C/D；
- 新 C2/D2 中间 checkpoint；
- `eval_hidden_tests`；
- 最终 test performance。

这样可以避免 post-treatment data selection。

## 7.2 Calibration sampling

每个 candidate 初始生成 8 个独立 sampled completions：

```yaml
calibration_generation:
  num_generations: 8
  do_sample: true
  temperature: 0.8
  top_p: 0.95
  max_new_tokens: 512
```

per-problem seed MUST deterministic/reproducible。

同一题的同 8 个 B completions SHOULD 同时跑：

- Public verifier (`visible_tests`)；
- Hidden verifier (`train_hidden_tests`)。

这样 Public/Hidden informativeness 的差异不会被不同 sampled code 混淆。

## 7.3 Calibration 必须记录的指标

每题至少记录：

- 8 个 Public `test_reward`；
- 8 个 Hidden `test_reward`；
- Public/Hidden total reward；
- Public/Hidden reward mean/std；
- all-correct flag；
- all-zero-test-reward flag；
- full-pass completion count；
- parse/execution/timeout counts；
- completion length / truncation；
- source / difficulty / overlap class。

主 pool 的 informativeness MUST 主要依据 test-derived reward variance，而不是仅靠 executable/format penalty 产生的人为差异。

推荐定义：

```text
public_informative = std(public_test_reward) > 0
hidden_informative = std(hidden_test_reward) > 0
```

如果一组 completion 的 test reward 完全相同，只是因为 parse/executable penalty 不同而 total reward 有波动，可以记录为 auxiliary-only variance，但 SHOULD NOT 单独因此进入 main active pool。

## 7.4 Calibration class

每题 MUST 冻结为四类之一：

1. **dual-informative**：Public 与 Hidden 均有 non-zero test-reward variance；
2. **public-only informative**：只有 Public 有 variance；
3. **hidden-only informative**：只有 Hidden 有 variance；
4. **dual-uninformative**：两边都没有 test-reward variance。

## 7.5 Final active pool composition

默认：

```yaml
calibration_composition:
  dual_informative_min_fraction: 0.70
  public_only_max_fraction: 0.15
  hidden_only_max_fraction: 0.15
  dual_uninformative_fraction: 0.00
```

理由：

- 至少 70% 题对两个实验臂都提供初始 learning signal；
- 保留少量 Public-only / Hidden-only 题，因为“哪个 verifier 在哪些题上更有区分度”本身就是研究信息；
- B 下对两个 verifier 都没有任何 test-reward variance 的题，不进入主 active pool。

不能把 final pool 限制为 100% dual-informative，因为这样会系统性删除 verifier 差异最大的题，反而弱化 RQ-R2。

## 7.6 All-zero retry

第一次 0/8 不足以证明真实 success probability 为 0。

当同一 candidate 对 Public 和 Hidden 都为 0/8 时，SHOULD 再追加一个 deterministic 8-sample block。

```text
initial: 0/8
retry:   +8
```

如果累计 16 个 samples 仍然 dual-uninformative，则 SHOULD 归入 `hard_pool`，不进入主 active pool。

如果 8/8 在 Public 与 Hidden 下都完全正确，通常可以直接归入 `easy/saturated_pool`，无需追加采样。

## 7.7 Calibration artifacts

必须保存：

- candidate manifest identity；
- frozen B identity；
- generation config；
- per-problem seed namespace；
- calibration result；
- class；
- final selection reason；
- output pool hash。

正式 C2/D2 dataset 必须 hash-bind 到这个 calibration manifest。

---

# 8. GRPO 正式配置更新

## 8.1 `num_generations=8`

C2/D2 正式默认：

```yaml
num_generations: 8
```

替代第一轮 `num_generations=4`。

Public 与 Hidden MUST 完全相同。

## 8.2 C2/D2 公平性

C2/D2 MUST 匹配：

- parent B checkpoint；
- canonical GRPO problem pool；
- problem scheduling policy；
- seed policy；
- `num_generations=8`；
- temperature / top-p；
- prompt/completion length；
- optimizer；
- LR schedule；
- KL coefficient；
- LoRA config；
- gradient accumulation / effective update semantics；
- checkpoint cadence；
- total training budget；
- dtype；
- executor/verifier runtime；
- final evaluation protocol。

主要差异只有：

```text
Public -> visible_tests
Hidden -> train_hidden_tests
```

## 8.3 `num_generations=8` 后的 batch 语义必须重新 benchmark

从 4 提升到 8 会改变：

- GPU memory；
- 每个 problem 的 generated tokens；
- reward verification 量；
- 一个 optimizer update 对应的 rollout 数；
- wall-clock step time。

因此在正式 run seal 前 MUST benchmark：

- `per_device_train_batch_size`；
- `gradient_accumulation_steps`；
- group generation batching；
- verifier concurrency；
- peak VRAM；
- effective completions per optimizer update。

MUST NOT 为了“抵消 k=8 成本”而静默减少训练 step、只修改一个实验臂，或使用无法解释的 effective batch 变化。

所有变化必须出现在 resolved config 和 benchmark artifact 中。

---

# 9. Zero-variance group 的正式处理

## 9.1 第一原则：优先在训练前减少，而不是训练时盲目 rejection

主 C2/D2 实验采用：

> **offline calibration + fixed shared active pool**

而不是一开始就让两个实验臂根据各自当前 reward 独立 dynamic sampling。

原因：如果 Public 因 zero-variance 丢题、Hidden 不丢，最终两个实验臂会逐步看到不同的题目分布，Public-vs-Hidden 就不再是干净的 verifier ablation。

## 9.2 每个 group 必须记录

正式训练每个 group MUST 记录：

- `test_reward_mean`；
- `test_reward_std`；
- `total_reward_mean`；
- `total_reward_std`；
- `all_test_correct`；
- `all_test_zero`；
- `all_total_reward_equal`；
- `sample_count=8`；
- reward mode；
- problem ID；
- calibration class。

滚动窗口 MUST 记录：

- all-correct group fraction；
- all-zero-test-reward fraction；
- total-reward zero-variance fraction；
- mean / median group reward std；
- effective non-zero-variance group count；
- rollout time；
- verifier time；
- backward/optimizer time。

## 9.3 不允许为了制造 variance 任意增加 proxy reward

正式主实验 MUST NOT 仅为了降低 zero-variance 而加入：

- code length reward；
- style reward；
- AST reward；
- arbitrary heuristic reward；
- 未经单独 ablation 的 learned score。

现有 test/executable/timeout/format reward contract 可以保留。

如果以后研究 dense reward，必须作为独立实验。

## 9.4 主实验不允许单边 online resampling

主 C2/D2 中：

- Public 不得因为自身某题 all-equal 就单独换题；
- Hidden 不得因为自身某题 all-equal 就单独换题；
- 不得在看到 final evaluation 后重新定义 active pool。

否则 problem exposure 会成为新的 confound。

## 9.5 正式 pilot saturation gate

完整训练前，C2/D2 SHOULD 各完成至少 100 个 `num_generations=8` group 的 pilot。

默认 gate：

```yaml
zero_variance_pilot_gate:
  target_total_reward_all_equal_fraction: < 0.20
  warning_fraction: 0.20-0.25
  stop_and_recalibrate_fraction: > 0.25
```

这里的 threshold 可以在工程 benchmark 后进一步收紧，但 MUST 在 formal C2/D2 前冻结。

如果任一实验臂 >25%，优先处理顺序：

1. 检查 data/calibration；
2. 检查 active-pool composition；
3. 检查测试层是否过弱/过强；
4. 必要时从已校准 reserve pool 替换问题；
5. 最后才考虑修改算法。

不应第一反应是增加 training step。

## 9.6 Full run 中发生 saturation

如果 rolling 50-group window 连续多个窗口超过冻结阈值，SHOULD pause 并分析。

允许的预注册处理包括：

- 从已提前 calibration 的 reserve pool 切入问题；
- 使用冻结 curriculum rule；
- 按提前定义的 saturation stop rule 提前结束。

所有规则必须：

- 在 formal run 前注册；
- 对 C2/D2 对称；
- reproducible；
- 不使用 `eval_hidden_tests`。

## 9.7 Dynamic sampling 作为后续独立 ablation

DAPO-style online rejection / dynamic sampling MAY 做，但必须：

- 使用新的实验 identity；
- 单独报告；
- 不能悄悄替代 primary fixed-pool C2/D2。

这样既保留方法探索，也不污染主 causal comparison。

---

# 10. GPU 利用率与 GRPO 吞吐

## 10.1 优化目标

目标不是单纯追求 `nvidia-smi` 上 100% utilization，而是最大化：

```text
useful completions / wall-clock hour
useful non-zero-variance groups / GPU-hour
```

必须/应该记录：

- periodic GPU utilization；
- allocated/reserved/peak VRAM；
- generated tokens；
- generation tokens/s；
- completions/s；
- verifier requests/s；
- verifier wait time/group；
- backward/optimizer time；
- end-to-end step time；
- GPU 等 verifier 的 idle fraction；
- GPU-hours / informative group。

## 10.2 Public/Hidden 是否并行：先 benchmark，后决定

### 10.2.1 当前单 RTX 4090 场景

两个独立 GRPO trainer 在同一张 24GB 4090 上并行 **不是默认方案**。

只有同时满足以下条件，才 MAY 用 same-GPU Public/Hidden concurrency：

1. 两个 job 能同时稳定 fit，留有安全显存余量；
2. 无 OOM / retry instability；
3. C2/D2 artifact、checkpoint、log namespace 完全隔离；
4. 与顺序跑相比，两臂总 wall-clock 至少降低 15%，或存在等价的 aggregate useful-throughput 提升证据；
5. 没有明显增加 verifier starvation / step jitter；
6. 不增加 numerical/runtime failure；
7. 不改变 C2/D2 的科学公平性。

如果达不到这些条件，SHOULD 在单 4090 上顺序执行 C2、D2。

### 10.2.2 如果未来有两张等价 GPU

如果有两张满足相同正式要求的 target GPU，MAY 采用：

```text
GPU 0 -> C2 Public
GPU 1 -> D2 Hidden
```

但两边必须使用冻结同一 code/config/data identity，并使用独立 persistent artifact namespace。

## 10.3 单卡上优先优化 intra-arm，而不是双 trainer 争抢 GPU

在当前单 4090 条件下，优先级：

1. 单 arm 内 8-generation batched sampling；
2. 8 个 completion 的 verifier 并发；
3. tokenization / input prefetch；
4. 降低 Python/serialization/synchronization overhead；
5. 最后才 benchmark same-GPU C2/D2 concurrency。

## 10.4 GRPO verifier concurrency

同一个 group 内不同 completion 的 executable verification SHOULD 并发，只要保持：

- completion -> reward 顺序完全正确；
- 每个 completion 使用正确 test layer；
- deterministic failure accounting；
- Piston resource limit；
- infrastructure failure fail-closed；
- 不混用 Public/Hidden payload。

建议 benchmark：

```yaml
verification_concurrency_candidates: [8, 16, 32, 64]
```

最终 formal 值必须基于：

- throughput；
- P95 latency；
- sandbox/infrastructure error；
- host CPU/memory；
- Piston 稳定性。

GPU compute 与 verifier MAY pipeline/overlap，但不能使用 stale reward，也不能破坏 GRPO 正确依赖顺序。

---

# 11. 400 题正式 Evaluation 的吞吐优化

## 11.1 Metric 语义优先

现有 400-problem held-out evaluation 保持 primary comparable evaluation set，除非后续规格明确修改。

任何 batching MUST NOT 改变：

- problem order；
- prompt 内容；
- deterministic Pass@1 decoding；
- per-problem seed/provenance；
- verifier test layer；
- aggregation rule。

## 11.2 GPU batched generation

当前逐题单条 generation 路径 SHOULD 增加 deterministic batched generation。

建议 benchmark：

```yaml
generation_batch_candidates: [1, 2, 4, 8, 16]
```

最终 batch size 不在本规格中硬编码，由 4090 benchmark 决定。

正式候选 batch MUST：

- 有安全 VRAM headroom；
- 在冻结 parity set 上与 batch=1 产生相同 completion text，或在正式采用前给出明确、预注册的等价性判据；
- 不降低 end-to-end generation throughput；
- 继续记录 per-record token/latency/provenance。

默认优先要求 exact completion parity。

## 11.3 Verification 批处理/并发

generation bundle 冻结后，400 题 verification SHOULD 使用已有 bounded batch executor，并 benchmark：

```yaml
verification_concurrency_candidates: [8, 16, 32, 64]
```

选中的 `max_concurrency` 必须：

- 不引入 unexplained sandbox/infrastructure failure；
- 不改变逐题 correctness；
- SHOULD 明显快于 concurrency=1。

## 11.4 Staged evaluation topology

正式评测 SHOULD 保持：

```text
RTX 4090
  batched generation
        |
        v
immutable + hashed generation bundle
        |
        v
GTX 1660 Ti / Piston control plane
  concurrent verification
        |
        v
aggregation + statistics
```

原则：

> 4090 不应因为可以离线执行的逐题 Piston verification 而长时间空等。

## 11.5 为未来 Pass@k 留接口

batch generation 设计 SHOULD 可以扩展到未来 sampled Pass@k 的 problem × sample 批量生成。

本规格本身不改变当前 deterministic Pass@1 的 primary metric 定义。

---

# 12. Throughput Benchmark Contract

正式 C2/D2 之前 MUST 有单独 benchmark artifact，至少覆盖：

1. legacy `num_generations=4` 小规模 reference；
2. `num_generations=8` candidate；
3. GRPO verifier concurrency sweep；
4. single-GPU sequential C2/D2 估计；
5. 如果显存允许，single-GPU Public/Hidden concurrent trial；
6. evaluation generation batch-size sweep；
7. evaluation verification-concurrency sweep。

每个 benchmark 必须记录：

- model/checkpoint identity；
- runtime/package identity；
- config；
- problem/sample count；
- wall-clock；
- GPU utilization；
- peak VRAM；
- generated tokens；
- tokens/s；
- verifier request count/time；
- OOM/retry/error count；
- final selected configuration；
- selection rationale。

不能因为某配置让 GPU utilization 数字更漂亮，就在 end-to-end throughput 更差的情况下采用它。

---

# 13. 必须产出的 Artifacts

## 13.1 Data artifacts

必须包括：

- candidate source/revision manifest；
- exact/near dedup report；
- SFT/GRPO overlap report；
- validation/test/external-eval zero-overlap report；
- normalized canonical problems；
- Public/Hidden training view；
- test-layer leakage audit；
- calibration records/generations；
- calibration classification manifest；
- final active-pool manifest；
- reserve/hard/easy rejected-pool manifest。

## 13.2 Training artifacts

C2/D2 各自必须保留：

- resolved config；
- parent B identity；
- dataset/pool/calibration hashes；
- per-group reward + reward components；
- test/total reward variance flag；
- rollouts；
- trainer metrics；
- throughput telemetry；
- checkpoints；
- resume provenance；
- reward mode/verifier identity；
- completed status。

## 13.3 Evaluation artifacts

必须保留：

- generation batch config；
- per-problem generation identity/order；
- immutable generation bundle hash；
- verification concurrency config；
- per-problem result；
- aggregate result；
- 与 batch=1 / legacy sequential path 的 throughput/parity evidence。

---

# 14. 正式运行前 Acceptance Gates

## 14.1 Data gate

必须满足：

- final GRPO pool 数量处于冻结目标范围；
- SFT/GRPO exact+near overlap <= 15%；
- 推荐 overlap 处于 5–10%；
- validation/test/external-final-eval overlap = 0；
- Public/Hidden canonical problem IDs 完全相同；
- Public/Hidden problem scheduling policy 完全相同；
- leakage checks 全部通过；
- source revision/license/provenance 已记录。

## 14.2 Calibration gate

必须满足：

- 使用冻结 B；
- calibration `num_generations=8`；
- active pool >=70% dual-informative；
- dual-uninformative 不进入 main active pool；
- manifest hash-bind 到正式 training dataset；
- `eval_hidden_tests` 未参与 calibration。

## 14.3 8-generation pilot gate

必须满足：

- C2/D2 都完成 bounded pilot；
- `sample_count == 8`；
- 无 OOM；
- 无 NaN/Inf；
- verifier/test-layer identity 正确；
- zero-variance rate 满足冻结 pilot threshold；
- throughput + VRAM telemetry 完整。

## 14.4 Systems gate

必须满足：

- 正式 training mode 有 benchmark evidence；
- 如果启用 same-GPU C2/D2 concurrency，满足 §10.2；
- verifier concurrency 已验证；
- 400 题 batched generation 已有 parity evidence；
- staged generation -> verification provenance 完整。

## 14.5 Scientific fairness gate

必须满足：

- C2/D2 仅在预期 reward verifier source 上有主要差异；
- 不存在根据 final result 做的 arm-specific post-hoc filtering；
- parent B identity 冻结；
- 400 题 evaluation identity 冻结；
- 无论结果方向如何都报告。

---

# 15. Reporting Requirements

最终 report MUST 明确区分：

1. **problem overlap**：GRPO 中有多少题曾经用于 SFT；
2. **calibration informativeness**：冻结 B 在训练前的 reward variance；
3. **online training informativeness**：C2/D2 训练过程中 reward variance 如何变化；
4. **final generalization**：最终 held-out performance。

至少报告：

- Eval-Hidden Pass@1；
- Visible / Train-Hidden / Eval-Hidden 指标；
- all-correct / all-zero / mixed group fraction over time；
- total-reward zero-variance fraction over time；
- reward std distribution；
- informative groups / GPU-hour；
- generation tokens/s；
- verifier throughput；
- C2-vs-D2 paired comparison + confidence interval；
- 与原 B/C/D 的比较，并显式标记 protocol changed。

未来 Pass@k 或 verifier-selected best-of-k 必须标记为 supplemental，除非另有规格修订，否则不能替代 deterministic Pass@1 primary result。

---

# 16. 第一轮 Refresh 推荐默认值

除非后续 benchmark 在正式 seal 前给出明确修改理由，默认：

```yaml
refresh_defaults:
  parent_model: B-sft-formal-seed42

  grpo_pool:
    target_size: 3000
    sft_overlap_target: 0.05-0.10
    sft_overlap_hard_max: 0.15
    dual_informative_min_fraction: 0.70

  calibration:
    num_generations: 8
    temperature: 0.8
    top_p: 0.95
    max_new_tokens: 512
    retry_all_zero_with_additional_samples: 8

  grpo:
    num_generations: 8
    temperature: 0.8
    top_p: 0.95
    max_completion_length: 512
    public_hidden_same_problem_pool: true

  pilot:
    groups_per_arm_min: 100
    zero_variance_target_max: 0.20
    zero_variance_stop_threshold: 0.25

  performance:
    same_gpu_public_hidden_parallelism: benchmark_only
    same_gpu_parallel_min_wallclock_gain: 0.15
    verification_concurrency_candidates: [8, 16, 32, 64]
    evaluation_generation_batch_candidates: [1, 2, 4, 8, 16]
```

这些是后续 implementation/planning 的默认输入，不代表可以跳过 data/calibration/pilot/provenance/operator gate 直接启动正式训练。

---

# 17. 后续规划与 stage 路由

本规格已经激活为 WP9 research track。Git lifecycle、函数级实施细节、operator script、正式训练时间和 execution backend 仍由当前项目 workflow、后续 stage plan / lifecycle / router 决定；sealed plan/routing 是默认执行基线而非普通 Git SHA 状态锁，用户明确的实现/routing/recovery override 可以形成 recorded effective contract。**这种 workflow 灵活性不改变本规格的 MUST/MUST NOT、数据隔离、实验身份、真实 calibration/pilot/formal evidence 或 WP9 依赖顺序。**为了让新对话可以从仓库状态自动确定下一步，本规格冻结以下高层依赖顺序。

## 17.1 WP9-a — Refresh data foundation

**类型：** development  
**默认 target：** GTX 1660 Ti control plane / CPU + Piston  
**范围：**

- external candidate-data ingestion + source provenance/revision pinning；
- cross-source exact/near dedup；
- 与 SFT、validation、400-test、external final-eval 的 overlap audit；
- 实现 SFT/GRPO 5–10% overlap target、15% hard max 的 deterministic selection/materialization；
- 将新题规范化为项目 canonical schema 与三层 test contract；
- 产出 Public/Hidden training views、machine-readable manifests 与 leakage checks。

**明确不做：** 真实 B calibration、真实 GRPO、正式 C2/D2、400 题重新 evaluation。

在没有新的 finalized proceedings record 改写 active stage 前，`WP9-a` 是唯一 next dependency-ready stage。

## 17.2 WP9-b — Calibration / k=8 / throughput engineering

**类型：** development。实现 B-based offline calibration 与 active-pool tooling、reward-informativeness metrics、`num_generations=8` GRPO config/telemetry、verifier concurrency、batched evaluation generation 与 benchmark harness。只用 engineering evidence 关闭。

## 17.3 WP9-c — Real calibration and pilot

**类型：** validation。使用冻结 B 做真实 calibration，冻结 active pool，完成 k=8 Public/Hidden pilot、zero-variance gate 与训练/评测吞吐 benchmark。需要模型 generation 的部分走 24GB operator boundary。

## 17.4 WP9-d — Formal C2/D2

**类型：** validation。使用同一 B、同一 frozen pool、同一 sampling/optimizer/budget，仅改变 reward test source，执行正式 Public C2 / Hidden D2。

## 17.5 WP9-e — Evaluation and refresh analysis

**类型：** validation/control-plane。完成 400 题 batched generation parity、concurrent verification、aggregation、paired statistics、zero-variance/efficiency analysis 与最终 report。

## 17.6 当前 RTX 4090 单系统盘存储合同

当前 WP9-c → WP9-d → WP9-e 使用的 RTX 4090 provider 已停用项目侧 `/data` volume。该变更只调整机器存储布局，不改变 calibration、active-pool、C2/D2 公平性、checkpoint、resume、hidden-test isolation 或其它科学合同。

正式 target-GPU 工作 MUST 遵守：

- persistent scientific roots 继续以 target-local `.ai-bridge/validation-machine.json` 为唯一 machine authority；当前机器的 `artifact_root`、`hf_home`、`formal_data_root` 必须全部位于 `/root` 系统文件系统；
- 当前 machine-local uv cache、temporary root、bootstrap resume state 分别使用 `/root/.cache/uv`、`/root/tmp`、`/root/.local/state/open-r1-code-verifier/`；这些属于运行环境配置，不进入实验身份；
- 新的 WP9 operator、bootstrap、benchmark 或 recovery command MUST NOT 把 `/data` 作为 active input/output/cache/temp/state path，也不得通过 compatibility symlink 隐式恢复 `/data` 依赖；
- dated legacy bootstrap、历史 terminal log、historical evidence 中已有的 `/data` 字符串可以作为 immutable provenance 保留，但不得作为当前命令模板或 recovery authority；
- 每个新的 4090 gate 仍必须在启动真实 GPU command 前检查实际 `artifact_root` 所在 filesystem 的 free bytes/inodes，并使用该 gate 已冻结的 storage threshold；系统盘空间不足时必须 fail closed、清理可重建 cache/临时文件或显式修订 storage provisioning，不能静默重新启用 `/data`；
- bootstrap staging archive 与完整可复用 uv cache 不属于科学 artifact，但如果迁移后 `artifact_root` 所在系统盘仍满足后续 gate 的冻结 free-bytes/free-inodes threshold，则 SHOULD 优先直接复制到 `/root` 下的 machine-local archive/cache 路径，避免不必要的重新下载或重建；复制必须保留 cache 内相对 symlink/metadata 并在切换后通过 `uv sync --check --frozen` 或等价只读检查。未完成的 uv `.tmp*`、pytest/torch 临时目录和其它 attempt-local scratch 不得作为可复用 cache 迁移。无论是否保留 archive/cache，都不得重新建立 active `/data` 依赖。

后续 planner MAY 因单 stage 规模过大进一步细分，但 MUST 保持上述依赖顺序和 development-first / target-GPU boundary；不得把旧 second-seed replication 重新提升为 WP9-a 之前的默认下一任务。

## 17.7 WP9-c active-pool 2500 audited protocol amendment

自 2026-09-04 起，用户明确授权 `wp9c-active-pool-2500-amendment-v1` 作为 WP9-c 后续 active-pool construction 的 effective contract。该 amendment **不修改或覆盖**已经 sealed 的 3000-problem planner/reviewer/proceedings evidence；旧 3000/225 合同继续作为 historical baseline 可追溯，但未执行完成的旧 calibration/retry/operator 不得据此继续推进。

新的 formal active-pool quota 冻结为：

- active pool exact = **2500**；
- SFT reuse exact = **225**，必须作为整数 quota 直接验证，不得通过浮点 fraction/rounding 推导；
- external-new exact = **2275**；
- dual-informative >= **1750**；
- public-only <= **375**；
- hidden-only <= **375**；
- dual-uninformative = **0**；
- `quality_gate_required=true` 或任何尚未通过 required quality gate 的数据不得进入 formal pool；
- >=8 unique tests、frozen dedup/leakage policy、Exact Formal-B context <=2048、source/provenance/license identity、reference-solution execution/Piston validation 与 informativeness threshold 均不得为了凑数降低。

该 amendment 同时冻结以下 recovery/data-order 约束：

1. 旧 5000-problem stdio-dominated calibration 保留为 failure/diagnostic evidence，不得作为新 2500 pool 的 scoring source；旧 retry 与 RTX4090 calibration operator 继续 frozen。
2. source admission/selection 不得使用已观察到的旧 Public/Hidden reward outcome，避免 post-hoc contamination；只能依赖 source/provenance/schema/static quality/context/tests/dedup 等 reward-independent 信息。
3. 新 function-level external-new supply 在 formal Piston 前 SHOULD 准备约 **2600–2800** 个 dedup + Exact-B context-qualified candidates，以避免 2275 exact target 在 Piston/quality attrition 后失去 buffer。
4. 已发布 aggregate C0 的 `1278 ready + 1126 APPS-under8 = 2404 zero-attrition potential` 必须保留为 historical engineering evidence，不能覆盖或重写。但后续代码审计确认：该 aggregate 对新增 candidate 的 context filter 直接 tokenized `candidate.prompt`，而正式 calibration/GRPO context contract 是 `build_code_prompt`（problem statement + function signature + visible examples + fixed wrapper）后再套 Exact Formal-B chat template/tokenizer。`wp9c-function-supply-context-correction-v1` 已由 C6-r1 完成并发布 correction report：corrected current-ready Exact-B context count = **1276**（相对历史 1278 为 -2）；APPS-under8 pre-augmentation planning/proxy pass count = **1119**（相对历史 1126 为 -7），但其 formal context-eligible count 继续为 **null**；zero-attrition planning potential = **2395**（相对历史 2404 为 -9）。该 correction 不修改 historical aggregate evidence，且 `formal_eligible=false`。
5. context correction MUST 保持旧 aggregate report/digest 与 frozen formal-reference/ready-dedup decisions 可追溯，只纠正 Formal-B prompt/context gate；APPS-under8 必须在 corrected ready survivors 之后按原 priority 重新 dedup。由于 under8 后续 augmentation 会改变 visible examples，其 context 结果仍只是 pre-augmentation planning evidence，并须在最终 generated tests 冻结后再次 Exact-B 检查。对已有 4–7 tests 的 under8 行，pre-augmentation prompt projection MUST 与 production `canonicalize_refresh_candidate(seed=42) -> build_code_prompt` byte-exact cross-check；对仅有 1–3 tests、production canonicalizer 按设计拒绝构造无效三层 test split 的行，只允许报告显式标记的 planning proxy，且该 proxy 既不是最终 Formal-B pass 的上/下界，也不得填充 formal context-eligible count。
6. full BAAI/TACO 仍优先于 APPS synthetic augmentation。C6 full-TACO >=8 static audit 已完成：25443 source rows 中得到 715 个 >=8-test direct-signature candidates；formal/current-ready/intra-TACO dedup 后只保留 2 个，二者 production `canonicalize_refresh_candidate(seed=42) -> build_code_prompt` Exact-B prompt 分别为 2799/3335 tokens，均超过 2048，因此 incremental TACO context-eligible supply = **0**。C7 TACO-under8 static audit 随后得到 1041 个 pre-augmentation planning rows，但与 corrected APPS-under8 高度重叠，最终 under8 union = **1126**，加上 1276 ready 后 zero-attrition planning union = **2402**。C8 对本地 pinned DeepCoder Preview `primeintellect/train` + `taco/train` 全量 function-call projection 的静态审计已完成：2251 个 structural direct-signature candidates 中，1243 个 natural >=8 rows 经 frozen dedup 后只剩 4 个，四者 production Exact-B prompt 均超过 2048，因此新增 natural-ready 仍为 **0**；1–7-test 部分最终新增 **542** 个 pre-augmentation planning rows（541 PrimeIntellect projection + 1 TACO projection）。将 C7 union 再按 DeepCoder 优先级重 dedup 后保留 687 个（602 TACO + 85 APPS），最终 under8 planning union = **1229**，zero-attrition planning union = **2505**，相对 C7 净增 **103**。该 union 距 2600/2800 desired pre-Piston buffer 仍差 95/295，达到 2275 exact target 仍需 under8 最终成功 999/1229（约 81.29%），所以 test generation 继续 frozen。provenance 审查显示：602 个 TACO survivor 均保留 source URL hash，upstream 分布为 599 Codewars / 1 LeetCode / 2 HackerRank；541 个 DeepCoder-PrimeIntellect survivor 在 DeepCoder projection 中缺少逐行 source URL/provenance。C9 已补齐并全量审计历史固定、非 reward-tested 的 `open-r1/verifiable-coding-problems-python_decontaminated@0d251c23...` 六 shard：27839 rows 中仅 188 个 pure function-call rows，全部来自 TACO，且 188/188 在冻结的 explicit positional-argument parser 下不可解析，因此 structural direct-signature / incremental supply 均为 **0**；对 541 个 DeepCoder-PrimeIntellect rows 的 normalized problem + exact gold-solution provenance match 也为 **0/541**。该 0/541 后续由上游资料解释为 source-family mismatch：DeepCoder `primeintellect` 来自 PrimeIntellect SYNTHETIC-1，而 C9 decontaminated projection 不是其逐行等价镜像。下一 gate MUST 使用 Open-R1 官方 raw Python mirror `open-r1/verifiable-coding-problems-python@db558678436c3c1275212172746e1dd67a990059`（35735 rows / 11 parquet shards）；该 mirror 明确是 PrimeIntellect `verifiable-coding-problems` 全部 Python tasks，仅把 `metadata` / `verification_info` 格式化为字典且其余数据不变。C10 首次 download 尝试使用 auto-generated parquet-converter orphan commit `fd70d66a6ec418cb1c30d350ccbe08a4aec64862` 并在 manifest 发布前失败；随后改 pin 正常 source-data commit `db558678436c3c1275212172746e1dd67a990059`。Hugging Face commit metadata 显示二者 11 个 parquet LFS object SHA256 与 byte size 逐一相同，因此该 repair 不改变 dataset bytes、reported supply counts 或 historical evidence。C10 必须将 provenance recovery 与 supply 增量分开：provenance match 不计入 supply，只有在完整 C8 union 后仍 genuinely-new 的 raw function-call rows 才可计作新增 planning supply。该 raw mirror 的 dataset-level license 仍未声明，因此 C10 本身不得把任何候选升级为 formal admission；任何 under8 candidate 的 formal context count 在最终 augmentation 后重检前仍必须为 null。APPS/DeepCoder/Open-R1 augmentation 如仍需要，必须形成独立 audited protocol/checkpoint，并通过 deterministic generation proposal、multiple accepted source-solution consensus 与 project Piston validation 后才可升级为 formal candidate。
   - **C10 completion amendment:** C10 已完成并发布 digest-verified engineering evidence（report SHA256 `b3964526b1d5d4760a6af18be5aec70d617f5b3abc88ab17ac60821709ee1cd2`）。完整 raw Python mirror 共扫描 **35735** rows（apps 5355 / code_contests 13315 / codeforces 840 / TACO 16225）；仅发现 **198** 个 pure function-call rows，全部来自 TACO，且 **198/198** 在冻结的 explicit positional-argument parser 下不可解析，所以 structural direct-signature = **0**、incremental ready = **0**、incremental under8 planning = **0**。541 个 DeepCoder-PrimeIntellect target 在 C10 冻结的 `(normalized problem, exact DeepCoder-solution hash == raw VCP gold_standard_solution hash)` key 下为 **0 unique / 0 ambiguous / 541 unmatched**。该 strict result MUST 保留且不得 retroactively 放宽；但后续审计确认 C8 `raw_reference_solution_hash` 是对 DeepCoder `solutions` 列表本身求 hash，而 raw VCP 使用独立的 `gold_standard_solution` 字段，两者并无已建立的等价 lineage contract。因此 C10 的 0/541 证明该 strict key 不成立，**不证明 task-level lineage 不存在**，也不改变任何 reported supply count。C8/C9/C10 后有效 supply baseline 仍是 **1276 ready + 1229 under8 planning = 2505**，距 2600/2800 buffer 仍差 95/295，exact 2275 仍需 under8 最终成功 999/1229（约 81.29%）。DeepCoder card 公开说明其 16K PrimeIntellect 部分来自 SYNTHETIC-1，而 PrimeIntellect 的 SYNTHETIC-1 card 将 algorithmic coding 的 task dataset 明确指向 `PrimeIntellect/verifiable-coding-problems`；所以下一 gate MUST 采用更直接的 **response-level lineage**（优先 `PrimeIntellect/SYNTHETIC-1` / `PrimeIntellect/SYNTHETIC-1-SFT-Data` 的 `response_id`/`problem_id`/prompt/assistant-response 链）去绑定 DeepCoder `problem` / `solutions` 的 transformation，再回接 raw VCP `problem_id` / source URL。该 lineage gate 只允许 provenance diagnostic，不得新增 supply、不得使用其 score 做 source selection、不得执行 source solution、不得生成 tests、不得跑 Piston/calibration/GRPO/RTX4090；541 条在 lineage 未闭合前继续禁止 formal admission/augmentation。
   - **C11 preparation amendment:** 当前唯一 gate 已实例化为 `C11-synthetic1-sft-response-lineage`，使用 pinned `PrimeIntellect/SYNTHETIC-1-SFT-Data@e8d30e75e8da4fdb176b7aa0c345eb88a8bbf2e8`（`default/train`，17 parquet shards，894086 rows，dataset-card Apache-2.0）作为 **provenance-index-only** 数据源。由于该 SFT derivative 是 verifier-score filtered，C11 MUST 要求 source schema 中存在 `score` 字段但不得把该列加载到 scan batch；score value 不得用于 matching、selection、ordering 或 supply，且 C11 incremental supply 按协议固定为 **0**。target 必须恰为 C8 冻结 artifact 中 541 个 `deepcoder-primeintellect` survivors；静态 preflight 已确认 541/541 accepted solutions 都可由共享 `extract_python_code()` 确定性提取 final Python fenced block。lineage match MUST 同时满足 project `normalize_text` 后 user prompt exact equality 与共享 extractor 输出 code bytes exact equality；prompt-only hit 仅可作 diagnostic，fuzzy prompt/code matching 禁止。只有一个 target 的全部 exact response hits 最终落到唯一 `problem_id` 时才可记为 unique lineage；多 problem ID 为 ambiguous，零 exact hit 为 unmatched。即使 C11 unique match，也只证明 response-level lineage，不得 formal-admit；仍必须把 `problem_id` 回接 raw VCP 的 source URL/upstream terms 后再进入任何 reference-solution execution/augmentation/final Exact-B/Piston gate。C11 checkpoint 当前仅授权 manual download + offline provenance scan；generation、Piston、calibration/retry、GRPO 与 RTX4090/GPU 全部继续 frozen。
7. **2026-09-04 fixed-supply user override:** 从该用户决策起，停止为了 2600–2800 pre-Piston buffer 继续 source discovery/download/import；第 3 条的 2600–2800 仅保留为此前 planning rationale，不再是当前 source-expansion action。candidate universe 冻结为 C8/C10 已得到的 **1276 ready + 1229 under8 = 2505**，不得通过 APPS/TACO/DeepCoder/Open-R1/PrimeIntellect 或其它来源增加 candidate。C11 `PrimeIntellect/SYNTHETIC-1-SFT-Data` 3.64GB download/audit 因此改为 `paused_by_user`；其 pause 前 checkpoint SHA256 `c40d38ed02db42dac16e7fed07e686fa84f4c3d613ee7a35d819ebf451dab98c` 保留为历史 prepared evidence。若 541 个 `deepcoder-primeintellect` 最终 formal admission 确实需要 lineage，C11 MAY 以后只作为 provenance-only gate 经显式审计重新开启，但 incremental supply 必须固定为 **0**，且不得成为补题入口。C12 fixed-universe freeze 已只读复用既有 C6-correction/C7/C8/C10 artifacts，最终以 `C12-r1` 发布 exactly **2505** 行 planning manifest（ready **1276** / under8 **1229**；manifest SHA256 `98fca412643057e6a992c288d0121e83569e3fa77369b3bb617bc3d331b61840`；report SHA256 `fc37c6792403d1ddc7c6336cb793b49a8a2d09587aed0d6dba3126f36fafb15b`；report 同时绑定最终 audit script digest）。under8 formal context eligibility 继续为 **null**；541 个 PrimeIntellect rows 逐行保留 unresolved-provenance formal-admission blocker。后续顺序冻结为：只对该 1229 frozen IDs 做 audited test augmentation -> tests digest 冻结 -> production `canonicalize_refresh_candidate(seed=42) -> build_code_prompt -> Formal-B chat template/tokenizer` 最终 Exact-B -> formal function-level project Piston -> reward-independent exact 2275 external-new selection；若全 gate 通过者不足 2275，只报告 shortfall 并等待用户决定，不自动恢复 source expansion，也不得降低任何 threshold/quality/provenance/context/Piston/informativeness gate。
8. **C13/C14 augmentation-oracle amendment:** C13-r1 已在固定 C12 manifest 上只读构造 exactly **1229** 个 under8 augmentation jobs，冻结 deterministic input-only proposal protocol 与 source-solution transformation；未执行 source solution、generation 或 Piston。C13 report SHA256 `649679f6ce415a93ce698199ea991dc19181a988f38f7b344f6eb4009a6e83fe`，jobs SHA256 `186158e2d96bc78044e26d87d5ed4447d0f82d12348987632ba99436578eaf2d`。在坚持至少两份 independently qualified source solutions 的 consensus gate 下，仅 **638/1229** jobs 当前 static-ready；545 jobs 少于两份 transformable source solutions，其中 **541 个 deepcoder-primeintellect rows 的原始 accepted-source-solution count 恰为 1**，不得降级成 single-oracle augmentation。C14 随后只扫描已下载的 C10 raw-VCP 35735 rows，未联网、未执行 code、未增加 candidate；report SHA256 `cf9aade38c9b4f775c4db180685af7be7df6544c4845c78948757a2a6bb350ee`。541 个 DeepCoder-PrimeIntellect target 在 raw VCP 中 normalized-prompt match 为 **0/541**，normalized-prompt + exact extracted-code strict lineage 亦为 **0/541**，因此现有 C10 raw mirror 不能直接闭合这些 rows 的 task lineage 或提供第二独立 oracle。由于 exact 2275 external-new 在 1276 ready 全通过时仍需 999 under8 successes，而非 PrimeIntellect under8 只有 688，故即使这 688 全部成功，仍至少需要 **311** 个 DeepCoder-PrimeIntellect rows；provenance/second-oracle recovery 已成为 fixed-2505 路线的必要 gate，而不是 source expansion。为此新建 C15 `wp9c-synthetic1-provenance-reopen`，旧 C11 必须继续保持 `paused_by_user`；C15 incremental candidate supply 固定为 **0**，当前只授权人工下载/hash pinned `PrimeIntellect/SYNTHETIC-1-SFT-Data@e8d30e75e8da4fdb176b7aa0c345eb88a8bbf2e8` provenance index。C15 manual download 已完成并经 control plane 重新核验全部 **17/17 shards / 894086 rows / 3638559349 bytes**；manifest SHA256 `b910233e8adf693834f122de74db440bcbd64b562f5fe24cec800c2b62210858`，download log SHA256 `aa545d2a625160c1070bd561d1cf7ea4be82b53b102528c6d937abc951cd1117`，incremental supply 仍为 **0**，旧 C11 仍保持 `paused_by_user`。因此 C15 已封账，当前唯一 gate 改为 C16 `wp9c-synthetic1-response-lineage-rejoin`：它只允许人工离线扫描已下载 SFT provenance index，以 exact normalized prompt + shared extractor exact code bytes 建立 response lineage；仅 unique `problem_id` 可再用 exact `problem_id` 回接已有 C10 raw VCP 的 `gold_standard_solution`。C16 中只有 rejoin 唯一、raw gold 可解析且 code bytes 与 DeepCoder solution 不同的行可标记为 **static second-oracle candidate**；该标记仍不是 oracle qualification，source-solution transformation、upstream terms review 与 project Piston 必须在后续独立 gate 完成。C16 不得执行 source solution、不得生成 tests、不得跑 Piston/calibration/GRPO/GPU、不得新增 candidate。score 必须存在于 SFT schema，但不得加载/用于 matching、selection、supply 或 test generation。**C16 completion amendment:** manual C16 已完成并经 control plane 验收；report/log SHA256 均为 `0004c0cd04550b03765db39bad53d8358baa4179525f70d3b7ca1fa68ee4458e`。实际扫描 894086 SFT rows 与 35735 raw-VCP rows，541 个 frozen DeepCoder-PrimeIntellect targets 的 exact normalized-prompt source hits 为 **0**、exact response-code hits 为 **0**，因此 unique `problem_id` lineage **0** / ambiguous **0** / unmatched **541**，raw-VCP rejoin rows **0**，static second-oracle candidates **0**。candidate supply 仍为 0，score 未加载/使用，source solution/test generation/Piston/calibration/GRPO/GPU 均未运行。由于 frozen exact-2275 路线在零其它 attrition 的最佳情况下仍至少需要 **311** 个 PrimeIntellect successes，当前 frozen exact-lineage contract 下 0/311 的 static prerequisite 未满足，故 C17 source-solution transformation/Piston **不得启动**，当前路线必须 stop for user decision。该结果只证明本次 frozen exact normalized-prompt + exact extracted-code lineage contract 失败；不得将其扩大解释为任何 fuzzy lineage 的授权，任何新的 deterministic provenance-only identity chain 都必须单独形成 audited protocol，且不得放宽 single-oracle、quality、context、Piston、informativeness 或 supply freeze。
9. 新 active-pool manifest MUST 记录 `active_pool_protocol=wp9c-active-pool-2500-amendment-v1`，并由 strict checker 重新计算 exact SFT/external-new counts 与 informativeness counts。
10. **2026-09-05 reduced-quota user amendment:** 用户明确允许“题目少一点”，要求先固定当前能够继续走正式验证流程的题，剩余找不到/闭合不了的题直接放弃。因此从本条起，旧 `external_new_exact=2275` / `active_pool_exact=2500` 不再是必须补满的阻塞目标；不得为了补数量恢复 source expansion、fuzzy lineage、single-oracle、降低 quality/context/Piston/dedup gate 或使用 reward outcome 做 source selection。C17 `wp9c-current-viable-pool-freeze` 已只读绑定 C12/C13/C16 evidence 并完成：从 frozen 2505 中保留 exactly **1914** 个 current viable pipeline candidates，其中 **1276** 个为 `ready_for_final_piston`，**638** 个为 `ready_for_augmentation_execution`；其余 **591** 个 under8 直接 drop 且 `backfill_required=false`（541 `deepcoder-primeintellect` + 35 BAAI/TACO + 15 APPS）。C17 report SHA256 `6c16e3f95311759a8679915fc44ff199de61ee33d78680eed7ac41b4e179d322`，viable manifest SHA256 `a98d83aa59eda30081199e665c05df116de0a9d059984ea19e7c1282586f91bf`，dropped manifest SHA256 `e4d03e5312f3f6fb88d480c1ba5cb2c8395b838281cef498528ab712433f1249`。这里的 1914 是“当前可继续验证的候选池”，**不是 final formal usable count**：1276 ready 仍须 final formal function-level Piston；638 under8 仍须至少两份 source solution 的 Piston qualification、deterministic consensus augmentation、exactly 8 tests freeze、final Exact-B recheck 与 final formal Piston。后续任何 candidate 在这些 gate 失败即直接丢弃、不替补；最终 external-new 数量等于所有 remaining gates 的实际 passers，minimum external-new count 为 null。旧 2500-size-dependent informativeness absolute composition counts 不再要求通过补题凑满；strict checker 仍必须报告实际 dual/public-only/hidden-only counts，并继续硬排除 `dual-uninformative`，不得用降低单题 informativeness 标准来维持数量。历史 225 SFT reuse 只在最终 active-pool assembly 时按原独立质量/重复约束重新核算，不得拿来掩盖 external-new shortfall。
11. **C18/C19 ready-lane formal-Piston amendment:** C18 在 reduced-quota 协议下只读重建 C17 的 1276 `ready_for_final_piston` rows 对应 frozen source/reference-solution evidence，并明确未执行 candidate/source code 或 Piston。历史 654 incumbent canonical records 的 `reference_solution` 字段全部为空，因此 C18 只允许从原 pinned source identity 重建 accepted source solutions，不允许凭空补 oracle。结果：100 个 `deepcoder-lcbv5-train` rows 的冻结 upstream projection 根本没有 source solution 字段，直接 drop；另有 9 个 `deepcoder-primeintellect` rows 的 accepted source solution 在 frozen C13 deterministic wrapper 下无可 transform target，亦直接 drop。无 backfill。C18 最终准备 exactly **1167** 个 ready formal-Piston jobs：5 APPS / 530 DeepCoder-PrimeIntellect / 15 DeepCoder-TACO / 420 OpenCoder-Educational / 197 LeetCode。C18 report SHA256 `1d87bb7d87f55af65b08fd96636283bf93933d8f841dea1b61d41e409d594737`，jobs SHA256 `f83455c5baf4c2e0a360db74e641b24cfc8976b6535356e86f5d5c7c39b50188`，pre-Piston dropped SHA256 `fa1670860994df87b914be4a5dd5d841019bafee909508e13665a5145c760d93`。C19 manual formal Piston 已完成并经 control plane 逐题复算验收：1167 jobs 恰分成 **1030 `formal_pass` + 137 `formal_fail` + 0 `infrastructure_blocked`**，Piston runtime 为 frozen Python 3.10.0；1167 个 checkpoint/candidate IDs 唯一且与 job SHA 一一绑定，日志无 traceback。137 correctness failures 按 user reduced-quota policy 直接 drop 且不 backfill。C19 report SHA256 `3a2b135d61125d794136f2ee4c68b1f436c216398e98ccd47a7b2e14cafcf3c4`，formal passers SHA256 `aef07311638fd3bd292003aa4097d0adf22ef6ac7e7432530b29546511dccb8f`，formal failures SHA256 `50df6e4befe85b2f4673d80e0dad914d57051c7f87292502378ffaa10e7a2973`，C19 closed checkpoint SHA256 `e1a828515797b43871606d2a60e6b9dff592986f0ba10b606b8a9f6514fe5ad6`。ready lane 因此最终 formal survivors 固定为 **1030**。
12. **C20 under8 source-oracle qualification amendment:** 剩余 under8 current viable lane 固定为 exactly **638** rows（567 BAAI/TACO + 70 codeparrot/apps + 1 deepcoder-taco），且与 C13 `static_augmentation_ready=true` IDs 和 C17 `ready_for_augmentation_execution` IDs 完全一致；这 638 rows 的 `formal_admission_provenance_blocked=false`，每题至少 2 个 distinct transformable accepted source solutions，并已有 1–7 个 frozen tests 与足够 deterministic input proposals，但 quality gate / augmented tests / final Exact-B / final formal Piston 均仍未通过。C20 preparation 不执行任何 candidate code/Piston/proposal，仅冻结 qualification jobs，SHA256 `3239b22f817506a5ef944f1f844191128b6ce0566106974986276e8256675b25`，prep report SHA256 `ebb861e2f309f48ad5446651620029f916fe7813fa6f0c9e38bd51b611970a2f`。C20 manual qualification 已完成并经 control plane 逐题复算验收：638 jobs 恰分成 **615 `oracle_pair_qualified` + 23 `oracle_pair_fail` + 0 `infrastructure_blocked`**，共执行 2118 次 source-solution Piston；615 个 pair 均为 frozen SHA order 中前两份 full-existing-tests pass 的 distinct solutions，23 个 correctness failures 均已穷尽全部 transformable solutions 且无 structured infra。23 题按 reduced-quota policy 直接 drop 且不 backfill。C20 report SHA256 `02f372efd135a77ffcac6fcabc5bfbe6703be369ee9b905848bae904bc2fb6bb`，qualified manifest SHA256 `e13c9f06be73b9b010d623fe1fe72d7866ea057bc18405e237acb4c5972b5bed`，closed checkpoint SHA256 `ee5f2659537fcd0c169e1f632b318eb32e5b9b1a65cd421ba08f11504cfc81f8`。
13. **C21 deterministic proposal-consensus amendment:** 仅 C20 的 **615** 个 `oracle_pair_qualified` rows 可进入 C21（552 BAAI/TACO + 62 APPS + 1 DeepCoder-TACO）。C21 preparation 只读绑定 C20 qualified pair、C20 qualification jobs 与 C13 frozen ranked proposals，未执行 Piston/proposal；r2 consensus jobs SHA256 `b353fbe74695239a38ade1fc4102c19a0ffa2ded3a03abc72b7a889928bb5f84`，prep report SHA256 `513bdad54dc3c352e273d7abc81cd137eda0101ad1bdeeffea17a5458f8b3fbd`。C21 manual gate MUST 对每个 proposal 按 C13 `proposal_rank_sha256` frozen order，仅执行 C20 frozen qualified oracle pair；通过受信父进程 + 独立 result pipe 的 `wp9c-piston-json-output-probe-v1` 获取 JSON return，父进程在启动 candidate 子进程前关闭 stdin 并 `PR_SET_DUMPABLE=0`，candidate stdout 不得作为 expected-output evidence。两份 oracle 只有在 JSON **同类型且递归值完全相等**时 proposal 才成为 formal candidate test；runtime/non-JSON/output-limit 或 oracle disagreement 仅 reject proposal 并继续，structured infrastructure failure 在凑齐槽位前则整题标记 `infrastructure_blocked`。按 frozen proposal order 取前 `additional_tests_required` 个 consensus-valid proposals，与原 existing tests 顺序拼接并冻结 **exactly 8 unique tests**；穷尽 proposals 仍不足则 `proposal_consensus_fail` 并无替补 drop。probe limits 固定 2.0s / 512MB / 65536-byte result packet，correctness retry 禁止，仅 frozen safe transport retry 允许。C21 不得运行 final Exact-B/final formal Piston/calibration/GRPO/GPU。只有 C21 输出经 control plane 验收后才可进入 final Exact-B。C21 manual consensus 已完成并经 control plane 逐题复算验收：615 jobs 恰分成 **572 `consensus_frozen` + 43 `proposal_consensus_fail` + 0 `infrastructure_blocked`**，共执行 8121 次 oracle probes；成功题严格使用 frozen proposal prefix，最终均为 exactly 8 unique tests，43 个 correctness failures 均已穷尽全部 proposals。43 题按 reduced-quota policy drop 且不 backfill。C21 report SHA256 `45c173edcd986d3aa58dd0cb88b069ba65863d69c37fb0bd078161f7d3431d6f`，frozen exact8 SHA256 `10e78d00792cfccacf389cdeebcb5ca68ad662cb8ab56308eb7272a9e0260555`，closed checkpoint SHA256 `80bbe53787ae7b59cd3b5b781069d543c806d9f0d991a6ab0d625b4791659af6`。
14. **C22/C23 final under8 admission amendment:** C22 对 C21 的 **572** 个 exact8 survivors 使用 production `canonicalize_refresh_candidate(seed=42) -> build_code_prompt` 与 C6 已验证 Formal-B tokenizer/chat-template identity 进行 final Exact-B；结果 **572/572 context pass、0 fail**，全部 canonical split 为 2 visible + 3 train-hidden + 3 eval-hidden，最大 prompt **2019 tokens <= 2048**。C23 manual final formal Piston 随后完成并经 control plane 逐题复算验收：572 jobs 恰分成 **572 `formal_pass` + 0 `formal_fail` + 0 `infrastructure_blocked`**；每题两份 frozen qualified oracle 均实际执行，合计 **1144/1144** solution executions 全部为 8/8 pass，Piston runtime 为 Python 3.10.0，checkpoint/job SHA 一一绑定且日志无 traceback。C23 report SHA256 `cdbb796e7f64abdaa50eab43203ab2ee564425e42fb12a03080750c167e65995`，formal passers SHA256 `3f4992359a4828331b155931c0a6d64c739e9d1e3f07aa60c67308a2e47780e0`，closed checkpoint SHA256 `3ae90108af2b9fe91a7bcf239230f74c7c12352750074077a45a4e33e6b5478a`。under8 lane 最终 formal survivors 因此固定为 **572**；与 C19 ready-lane 1030 合并后，formal external-new supply 固定为 **1602**。
15. **C24 final reduced-pool / SFT-reuse amendment:** C24 在不执行 candidate code、Piston、generation、calibration scoring、GRPO 或 GPU 的前提下，重新从 pinned source identity 重建 C19 的 1030 ready formal passers，并与 C22/C23 的 572 augmented formal passers 合并。最终得到 exactly **1602 external-new formal rows**，全部 `quality_gate_required=false`，再次使用冻结 Formal-B identity 验证后 **1602/1602 context pass**，prompt 最大 **2019 <= 2048**。source counts 为 513 BAAI/TACO + 62 APPS + 507 DeepCoder-PrimeIntellect + 14 DeepCoder-TACO + 418 OpenCoder-Educational + 88 LeetCode。历史 SFT reuse 同时按独立原约束重审：WP9-a frozen selection 中 exactly 750 个 `sft_reuse` rows **750/750 均为 `quality_gate_required=true`**，且当前 lineage 不存在独立已通过的 quality-gate artifact，因此 formal SFT reuse **0/750 eligible、old requested 225 中 0 admitted**；不得为维持旧 quota 伪造证据或 backfill。C24 report SHA256 `a5be86d847282f61e4497baafd095adad58e02ddc2015531c73d8c798843b6b6`，external formal problems SHA256 `d94c5216ef28272fb1e0ee0ec50667c423711d8587227a4feee84687c7509a6f`，precalibration selection SHA256 `fc85f5482747e09decec3dae68883727ec578f0f3a2c9c5486f01e37251a1b62`，SFT reuse audit SHA256 `c24a9909e3ce06f4db95ff7639254e1a083b8a447d0f565a466d921f28fc5f6c`，closed checkpoint SHA256 `48ac639cc3fba0c540437bfbba0b65403575f424c06eefd6b8c51d00771313f1`。因此当前 **pre-calibration formal pool = 1602 external-new + 0 SFT reuse = 1602**。informativeness 四分类现在必须保持 `null/pending_fresh_calibration`：第 17.7.1 条已禁止旧 5000-problem calibration 作为新 pool scoring source，且旧 reward outcomes 也不得用于 selection；下一 gate 必须对这 1602 题使用同一冻结 B 与 k=8 sampling contract 做 fresh Public/Hidden calibration，随后只报告实际 `dual_informative/public_only/hidden_only/dual_uninformative` counts，并继续排除 `dual_uninformative`，不 backfill、不通过降低 threshold 维持数量。
16. **C25 fresh initial calibration-generation handoff amendment:** C25 当前仅完成 input preparation 与 target-operator 静态审查，**尚未运行 RTX4090 generation**。fresh input bundle exactly **1602 external-new / 0 SFT**，input manifest SHA256 `bdccb68febe85f1da381ba01671fb220246dac9e74cdfacb89e4d1da7e334aff`、inputs SHA256 `dbb6f18a472e390acbec641daab65db6d3f2cb07d3469f8e46ef2d90bf867d18`，严格 loader 与 Formal-B recheck 均通过，max prompt 2019。C25 sampling 固定为同一 `B-sft-formal-seed42`、k=8、temperature 0.8、top_p 0.95、max_new_tokens 512、problem_batch_size 4，预期 exactly **12,816** fresh rows，旧 5000-problem completions/reward outcomes 禁止复用。最初的 `/home/dzy` control-plane-path shell 已被明确 supersede 并 fail-closed；唯一允许的新入口为 `C25/run.sh` portable-target operator。该脚本使用 target-local `.ai-bridge/validation-machine.json`，要求 `/root` 下的 artifact/HF/formal roots、禁止 `/data`、至少 20 GiB free + 100000 inodes、clean exact handoff commit、RTX4090 >=22528 MiB、fresh/resume 前 >=20000 MiB free VRAM、BF16、HF offline/local-files-only、flock、mandatory postcheck、operator evidence。generation persistence 继续使用 production exact-prefix contract：JSONL append+fsync 后才原子推进 progress；resume 截断仅 uncommitted tail，durable prefix 必须为完整 k=8 groups。control-plane 额外以 `problem_batch_size=4` 模拟中断并手工追加损坏 tail，确认 restart 只删除未提交 tail、保留前 4 题/32 rows 并从第 5 题继续；completed bundle 也通过 CPU-only 1602x8 strict-reuse 模拟，runner 在 CUDA/model load 前直接验证并复用。C25 operator handoff commit `322db1e1649d8c87b51352f57c0884b0b9a24bfc`；runner SHA256 `e56e5942ccfe05b255a11beb5ca99503eca8fad31a0287194909f0b0b87f41b4`，portable `run.sh` SHA256 `4e32badaa11a21d19beb2029233df626bf3abaded406c1892ae9f85e4bf36674`，checkpoint SHA256 `0ba51b0b502357482d6eba137d900b6686a19bab3470255992502a9ebb750916`，input-sync manifest SHA256 `7f640953b7010d150788b0c7a259497ed42c85ca24253f447ec73121a6a8a9c6`；Ruff/strict mypy、generation unit/integration tests 与 `bash -n` 通过，`shellcheck` 当前控制机未安装，因此未作为通过项声明。窄的 actual operator-handoff commit 已形成并从 committed bytes 反向验收：`322db1e1649d8c87b51352f57c0884b0b9a24bfc`，其中 `run.sh` mode 为 100755；按项目 policy 不 auto-push。下一操作是使该 commit 在 4090 可达，把完整 2,574,292-byte / 6-file C25 input bundle 依据 tracked `INPUT-SYNC.md` 与 `input-sync-manifest.json` byte-identically 同步并在 target 验证，再由用户在 4090 clean checkout 上设置 exact `WP9C_HANDOFF_COMMIT` 并运行 portable `run.sh`。C25 验收后才开放 fresh Public/Hidden scoring；initial 两臂均全零的题仍必须进入独立 fresh retry k=8（sample indices 8..15）后才可做最终 informativeness 分类。

---

# 18. External Source Notes

本规格起草时确认的 candidate source，应在真正实施时再次验证并 pin revision：

- PrimeIntellect verifiable coding problems: `https://huggingface.co/datasets/PrimeIntellect/verifiable-coding-problems`
- DeepCoder Preview Dataset: `https://huggingface.co/datasets/agentica-org/DeepCoder-Preview-Dataset`
- OpenThoughts CodeContests: `https://huggingface.co/datasets/open-thoughts/CodeContests`

source 出现在这里不等于直接批准导入。进入正式数据前仍须经过 license、provenance、schema、test quality、dedup 与 leakage validation。
