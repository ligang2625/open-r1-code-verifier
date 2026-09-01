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

后续 planner MAY 因单 stage 规模过大进一步细分，但 MUST 保持上述依赖顺序和 development-first / target-GPU boundary；不得把旧 second-seed replication 重新提升为 WP9-a 之前的默认下一任务。

---

# 18. External Source Notes

本规格起草时确认的 candidate source，应在真正实施时再次验证并 pin revision：

- PrimeIntellect verifiable coding problems: `https://huggingface.co/datasets/PrimeIntellect/verifiable-coding-problems`
- DeepCoder Preview Dataset: `https://huggingface.co/datasets/agentica-org/DeepCoder-Preview-Dataset`
- OpenThoughts CodeContests: `https://huggingface.co/datasets/open-thoughts/CodeContests`

source 出现在这里不等于直接批准导入。进入正式数据前仍须经过 license、provenance、schema、test quality、dedup 与 leakage validation。
