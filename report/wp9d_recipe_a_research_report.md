# WP9-d 项目研究报告：Verifier-Guided GRPO Recipe A

**项目：** Open-R1 Code Verifier / WP9-d GRPO Optimization  
**结项日期：** 2026-09-09  
**状态：** WP9-d 预定训练、checkpoint generation、400 题 verification/scoring 与稳定性裁决均已结束  
**核心结论：** Recipe A GRPO 在 canonical eval400 上相对刷新后的 SFT baseline B 获得明确提升；但 Public/Hidden 配对实验没有证明 Hidden reward 相比 Public reward 具有显著独立优势。

---

## 0. 摘要

WP9-d 的核心研究问题来自上一阶段 WP9-c 的负结果：300-step GRPO 虽然训练 reward 正常、没有明显 collapse，但 Eval-Hidden Pass@1 相对 B 没有提升。诊断显示，更可能的原因不是 reward 无效，而是 **active pool 覆盖不足 + cosine LR 在仅 300 step 内衰减到接近 0，导致有效 policy movement 不足**。

因此，本阶段从同一个冻结 SFT baseline B 独立初始化两个 Recipe A GRPO arm：

- **Public arm：** 训练 reward 只使用 `visible_tests`；
- **Hidden arm：** 训练 reward 只使用 `train_hidden_tests`；
- **eval-hidden tests 从未进入 GRPO reward。**

Recipe A 将训练拉长到 `1200` optimizer steps，约覆盖 active1354 的 `0.89 epoch`；采用 `5e-6` constant-with-warmup LR、`num_generations=8`、`beta=0.01`，并在安全合并 SFT B 后训练 fresh q/k/v/o LoRA。

最终 canonical 400 题结果：

- 刷新后的 B：**37.75% Eval-Hidden Pass@1 = 151/400**；
- Public1200：**44.25% = 177/400**；
- Hidden1200：**44.75% = 179/400**。

对同一 400 题做 problem-level paired bootstrap（10,000 resamples，seed 42）：

- **Public1200 − B：+6.50 pp，95% CI `[+2.25, +10.75] pp`**；
- **Hidden1200 − B：+7.00 pp，95% CI `[+2.74, +11.50] pp`**；
- **Hidden1200 − Public1200：+0.50 pp，95% CI `[-3.00, +4.00] pp`**。

因此，本阶段最强、最稳健的结论不是“Hidden reward 更好”，而是：

> **延长覆盖、维持非零学习率后的 Recipe A GRPO 确实能够显著提高 canonical eval400 上的代码求解能力；但提升主要来自 GRPO optimization regime 本身，当前证据不支持 Hidden reward 相比 Public reward 具有明确优势。**

两条 learning curve 均从 step300 持续上升到 step1200，但 900→1200 只增加 `+0.75 pp`，paired CI 包含 0，说明当前 recipe 已开始进入平台区。

---

# STAR 研究叙事

## S — Situation：问题背景与研究动机

### S1. 上一阶段的负结果

WP9-c 的 formal 300-step Public/Hidden GRPO 在 Eval-Hidden Pass@1 上都没有超过 B。该结果并不是简单的训练失败：reward variance 仍然存在，没有明显 group collapse；但训练只覆盖约 `0.22 epoch` active pool，而且 cosine LR 在 300 step 内从 `5e-6` 衰减到接近 0。

训练侧还表现出非常小的 KL，说明策略相对 parent B 的移动幅度很有限。因此最合理的下一步假设是：

> **原 reward signal 可能是有效的，但训练覆盖率、scheduler 和有效更新预算不足。**

### S2. WP9-d 要回答的两个核心问题

本阶段明确拆成两个研究问题：

1. **Coverage / scheduler hypothesis**  
   如果保持相同 verifier-guided reward，但把训练扩展到约 1 个 active-pool epoch，并避免 LR 提前衰减到 0，GRPO 是否能带来持续 policy movement 和 Eval-Hidden 性能提升？

2. **Reward-source hypothesis**  
   在所有非 reward 参数完全一致、且都从同一个 B 独立初始化时，使用 train-hidden tests 的 Hidden reward 是否优于只使用 visible tests 的 Public reward？

### S3. 公平性约束

为了避免把多变量变化误当成 reward-source 差异，本阶段冻结以下原则：

- Public/Hidden 从同一个 frozen B 独立初始化；
- active problem pool 和顺序相同；
- LR、beta、sampling、LoRA、batch、max_steps、runtime 全部一致；
- 两个 arm 唯一的科学差异是 reward test source；
- eval-hidden tests 只用于最终评测，不进入训练 reward；
- 所有测过的 checkpoint 必须保留，不允许 winner-only reporting。

---

## T — Task：实验目标、指标与判定规则

WP9-d 的任务被定义为五个可验收目标。

### T1. 验证 coverage/scheduler 假设

将 GRPO 从历史 300 step 扩展到 1200 step，同时把 scheduler 改为 `constant_with_warmup`，使 warmup 后 LR 维持在 `5e-6`，而不是在训练中途持续衰减。

### T2. 严格比较 Public vs Hidden reward

分别训练：

- Public reward arm；
- Hidden reward arm；

两个 arm 的非 reward 配置必须逐项一致。

### T3. 刷新 B baseline

由于 WP9-d 的 eval generation runtime 与历史 WP9-c 不完全相同，不能直接拿旧 B 数值混用。必须在同一 WP9-d protocol 下重新生成并验证 B，所有 delta 都相对这个 refreshed B 解释。

### T4. 评估完整 checkpoint trajectory

固定测量：

```text
step 300 / 600 / 900 / 1200
```

预先冻结 checkpoint selection rule：

1. Eval-Hidden Pass@1 越高越优；
2. exact tie 时，average eval-hidden test pass 越高越优；
3. 再 tie 时，runtime-error rate 越低越优；
4. 再 tie 时，parse-error rate 越低越优；
5. 再 tie 时，较早 checkpoint 优先。

### T5. 将 infrastructure failure 与模型能力分开

Generation bundle 一经产生即冻结；verification 由 1660Ti 上的 local Piston 完成。任何 `sandbox_error` 都不能被静默当成模型 wrong answer，也不能透明 replay 后覆盖历史结果。

因此本阶段把“模型输出”“Piston 执行结果”“基础设施异常”三者分别记录和裁决。

### T6. Primary metric

Trainer reward 上升本身不构成成功。

主指标固定为：

> **canonical eval400 的 Eval-Hidden Pass@1**

同时监控：

- visible Pass@1；
- train-hidden Pass@1；
- average eval-hidden test pass rate；
- parse success；
- executable rate；
- runtime error；
- timeout；
- completion length；
- KL 与训练稳定性。

---

## A — Action：算法设计、训练参数与实验实现

# A1. Parent policy 与 LoRA 初始化

Formal parent：

- 模型：`Qwen/Qwen2.5-Coder-1.5B-Instruct`；
- revision：`2e1fd397ee46e1388853d2af2c993145b0f1098a`；
- SFT parent：`B-sft-formal-seed42`；
- seed：`42`。

GRPO policy 构造不是直接继续训练旧 adapter，而是：

```text
Qwen2.5-Coder-1.5B-Instruct
  -> 只读加载完成的 SFT B adapter
  -> safe merge B 到 base policy
  -> 新建 fresh GRPO LoRA
```

这样可以保证：

- B 本身不被修改；
- Public/Hidden 都从完全相同的 SFT policy 起点出发；
- GRPO 的参数变化可以通过 fresh adapter 独立追踪。

Fresh GRPO LoRA：

| 参数 | 值 |
|---|---:|
| LoRA rank | 16 |
| LoRA alpha | 32 |
| LoRA dropout | 0.05 |
| target modules | `q_proj,k_proj,v_proj,o_proj` |

相较只训练 q/v，qkvo 覆盖所有 attention projection，使 policy 有更充分的可训练自由度，同时仍保持 parameter-efficient training。

---

# A2. Verifier-guided reward 设计

每个 completion 首先解析代码，然后由 Piston 对指定测试源执行程序。Reward 不是单纯的 binary pass/fail，而是结构化组合：

```text
total_reward
  = test_reward
  + executable_reward
  + timeout_penalty
  + invalid_format_penalty
```

精确定义：

- `test_reward = pass_rate`；
- 如果代码成功 parse 且能够执行，`executable_reward = +0.1`；
- genuine timeout 时，`timeout_penalty = -0.2`；
- parse error 时，`invalid_format_penalty = -0.1`；
- `sandbox_error` 等 infrastructure failure 不作为普通 reward outcome，单独 fail closed。

两个 arm 唯一的 reward-source 差异：

| Arm | 训练 reward test source | 不允许进入训练的信号 |
|---|---|---|
| Public | `visible_tests` | `eval_hidden_tests` |
| Hidden | `train_hidden_tests` | `eval_hidden_tests` |

因此 Hidden arm 并不是“直接优化最终 eval-hidden benchmark”，而是优化训练阶段预留的 hidden tests；真正 eval-hidden 仍保持在训练 reward 之外。

---

# A3. GRPO group-relative optimization

Formal Recipe A：

- `num_generations = 8`；
- `per_device_train_batch_size = 1`；
- `gradient_accumulation_steps = 8`。

Pinned single-GPU effective generation batch 为 8 completion，因此：

> **每个 optimizer step 对一个 problem group 采样 8 个 completion。**

这些 completion 通过 verifier 得到 reward，TRL GRPO 使用组内相对 reward/advantage 进行 policy optimization，并由 `beta=0.01` 对策略偏移进行 KL regularization。

1200 step 对应：

- 每个 arm 处理约 1200 problem groups；
- active pool 为 1354 题；
- `1200 / 1354 ≈ 0.886 epoch`；
- 每个 arm 约 `1200 × 8 = 9,600` rollout completions；
- Public+Hidden 合计约 `19,200` training rollouts。

这正面针对 WP9-c 的“覆盖不足”问题。

---

# A4. Formal Recipe A 全量参数

| 类别 | 参数 | Formal value |
|---|---|---:|
| Data | active pool | 1,354 problems |
| Sampling | num_generations | 8 |
| Sampling | temperature | 0.8 |
| Sampling | top_p | 0.95 |
| Length | max_prompt_length | 2048 |
| Length | max_completion_length | 512 |
| Optimizer | learning_rate | `5e-6` |
| Optimizer | scheduler | `constant_with_warmup` |
| Optimizer | warmup_ratio | 0.05 |
| Training | max_steps | 1200 |
| Training | num_train_epochs | 1.0 |
| Training | per-device train batch | 1 |
| Training | gradient accumulation | 8 |
| Precision | bf16 | true |
| Precision | fp16 | false |
| Memory | gradient checkpointing | true，non-reentrant |
| GRPO | beta | 0.01 |
| LoRA | rank / alpha / dropout | 16 / 32 / 0.05 |
| LoRA | targets | q/k/v/o |
| Runtime | vLLM | colocated |
| Runtime | vLLM GPU memory fraction | 0.4 |
| Reward execution | workers | 8 |
| Logging | logging_steps | 1 |
| Checkpoint | save_steps | **50** |
| Evaluation | eval_steps | 300 |
| Evaluation | measured checkpoints | 300/600/900/1200 |
| Hardware guard | min_cuda_memory_gb | 20.0 |
| Seed | seed | 42 |

说明：早期 spec draft 记录过 `save_steps=100`，但 formal operator 按用户 amendment 实际使用 **save_steps=50**；本报告以真正执行的 formal identity 为准。

Active pool provenance：

- problem count：1354；
- Public training dataset SHA256：`558250d06043702e153f88067a88d34378923255ef015cfbc97e106592d9188c`；
- Hidden training dataset SHA256：`9aae7ce46347236f69a67aadb60a719c76f089451873a4fd8d4b92147f74abec`。

---

# A5. Formal training runtime

训练使用 first RTX 4090：

- single-GPU；
- colocated vLLM rollout generation；
- `vllm_gpu_memory_utilization=0.4`；
- reward verification workers=8；
- Public 先跑完并 strict postcheck，再从同一个 B 独立构建 Hidden；
- 两个 arm 不共享 mutable adapter state。

Formal training handoff：

- commit `7b5e097b448b6c42fb9faf1f27711a65e00d2075`；
- operator `ai-work/executor/operator/WP9-d/wp9d-recipe-a-formal/C0/run.sh`；
- script SHA256 `64cd1d6accf7c4a79cbcaa825540bea43d86cf43ec703dd98a5209efdd9867b4`。

两条 1200-step formal training 均通过 provenance、checkpoint 和 artifact-integrity gate。

---

# A6. Canonical eval400 protocol

Canonical benchmark：

- problems：400；
- dataset SHA256：`770b772c738514888c5900f815fc074ddb3f6c3c5f67fc5346073565536138ae`；
- ordered IDs SHA256：`2d811d62613c122da6ee73f372008e44a40464ec9ad7c8df628ae01de4a234c9`；
- eval config SHA256：`3fa1b8f0dbc6853c894ac9f02b6820afd838ff68ca9f090ecbbef4ae495dbac3`；
- Piston config SHA256：`f049f4ea344285e2b732bb2a602e7c8888ae3ac449320039144c8a0dff62657e`；
- seed 42；
- deterministic decode：`do_sample=false`；
- max new tokens 512；
- generation dtype=float16；
- generation batch=4；
- 每个 checkpoint `parallel_generators=1`；
- first 4090 上每个 wave 同时生成两个 checkpoint；
- Public/Hidden 不混 wave；
- generation 全部结束后，统一在 1660Ti control plane 使用 local Piston verification；
- verification workers=64。

最终需要评分的 frozen generation bundle：

```text
B: 1 × 400
Recipe A: 2 arms × 4 checkpoints × 400
Total: 9 bundles / 3600 completions
```

Official eval-generation handoff：

- commit `f17b4f607daa3bb03b08682bbbd841118d36c4af`；
- run.sh SHA256 `59bed201d6f57025fcbfb22a0afed3a88298fabc04029af71ac23413f224aae4`。

---

# A7. Verification infrastructure 异常与最终裁决

本阶段没有把 infrastructure noise 混入模型结论。

### C0

九个 bundle 都完成 verify + aggregate，但 Hidden300 出现两行 Piston `sandbox_error`：

- row55 `leetcode-earliest-possible-day-of-full-bloom`；
- row59 `leetcode-expressive-words`。

因此 C0 strict gate fail，历史结果保留，不作为最终 Hidden300。

### C1

完整重新验证 Hidden300 的全部 400 题，而不是只补两行。

结果：

- 400/400；
- **0 sandbox_error**；
- 原 row55/59 都稳定变成 `wrong_answer`；
- 另有 `apps-4392` 从 C0 timeout 变为 passed。

### C2

为了判断 `apps-4392` 是否只是偶发 timeout，再做第三次完整 400 题 stability run。

结果：

- `apps-4392` 再次 **passed**；
- C1→C2 除基础设施异常行外，其余 verifier semantics 全部一致；
- 但 C2 在 `taco-1609` 新出现一个 independent `sandbox_error`。

### Final adjudication

根据最终用户裁决：

> **采用 C1 Hidden300 作为最终 scientific result。C2 不进入最终 scoring，只用于佐证 `apps-4392=passed` 的稳定性；C0/C2 gate failure 全部作为 immutable infrastructure history 保留。**

没有跨 run patch 单题，没有删除失败证据，也不再继续做无限 full-400 rerun。

---

## R — Result：实验结果与量化分析

# R1. 完整 checkpoint 结果

最终表中 Hidden300 使用 C1，其余使用 C0 clean result。

| Model / checkpoint | Visible Pass@1 | Train-Hidden Pass@1 | Eval-Hidden Pass@1 | Correct / 400 | Eval-Hidden avg test pass | Runtime error | Timeout | Parse success |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| **B baseline** | 35.50% | 33.50% | **37.75%** | 151 | 45.25% | 11.00% | 1.25% | 98.25% |
| Public 300 | 39.00% | 36.75% | 39.75% | 159 | 47.50% | 11.00% | 1.25% | 98.50% |
| Public 600 | 42.50% | 41.00% | 41.00% | 164 | 47.75% | 8.75% | 1.50% | 97.75% |
| Public 900 | 45.25% | 42.25% | 43.50% | 174 | 50.375% | 9.00% | 0.75% | 97.50% |
| **Public 1200** | **46.25%** | **42.50%** | **44.25%** | **177** | **51.75%** | 9.50% | 0.75% | 97.75% |
| Hidden 300, C1 | 37.00% | 35.00% | 38.00% | 152 | 44.75% | 10.75% | 1.25% | 97.75% |
| Hidden 600 | 43.50% | 39.50% | 41.75% | 167 | 48.875% | 11.00% | 0.50% | 97.00% |
| Hidden 900 | 45.25% | 40.75% | 44.00% | 176 | 51.125% | 9.50% | 0.75% | 98.50% |
| **Hidden 1200** | **47.50%** | **42.00%** | **44.75%** | **179** | **51.50%** | 9.75% | 1.25% | 98.25% |

按预声明 checkpoint selection rule：

> **最终 winner = Hidden step1200，Eval-Hidden Pass@1 = 44.75%。**

完整排序：

```text
Hidden1200 > Public1200 > Hidden900 > Public900
> Hidden600 > Public600 > Public300 > Hidden300
```

---

# R2. 相对 B 的 paired improvement

对同一 400 个 problem IDs 做 paired bootstrap：

- resamples=10,000；
- seed=42；
- 95% confidence interval。

| Candidate | Eval-Hidden Pass@1 Δ vs B | 95% paired CI | Avg eval-hidden test-pass Δ | 95% paired CI |
|---|---:|---:|---:|---:|
| Public300 | +2.00 pp | [-0.75, +4.75] | +2.25 pp | [-0.38, +4.88] |
| Public600 | +3.25 pp | [-0.75, +7.00] | +2.50 pp | [-1.13, +6.13] |
| Public900 | **+5.75 pp** | **[+1.50, +10.00]** | **+5.13 pp** | **[+1.25, +9.00]** |
| Public1200 | **+6.50 pp** | **[+2.25, +10.75]** | **+6.50 pp** | **[+2.63, +10.50]** |
| Hidden300 | +0.25 pp | [-1.75, +2.25] | -0.50 pp | [-2.50, +1.50] |
| Hidden600 | **+4.00 pp** | **[+0.50, +7.50]** | **+3.63 pp** | **[+0.25, +7.00]** |
| Hidden900 | **+6.25 pp** | **[+2.25, +10.25]** | **+5.88 pp** | **[+2.25, +9.63]** |
| Hidden1200 | **+7.00 pp** | **[+2.74, +11.50]** | **+6.25 pp** | **[+2.13, +10.38]** |

Hidden1200 从 151/400 提升到 179/400：

- absolute：`+7.00 pp`；
- net solved problems：`+28`；
- relative improvement：约 `+18.5%`。

Pairwise gain/loss：

- Public1200：51 个 B-fail→A-pass，25 个 B-pass→A-fail，net `+26`；
- Hidden1200：55 个 B-fail→A-pass，27 个 B-pass→A-fail，net `+28`。

因此最终提升并不是由极少数偶然翻转造成，而是有较广泛的 problem-level gain。

---

# R3. Learning curve：主要增益发生在 600–900 以后

Eval-Hidden Pass@1：

```text
step:      300      600      900      1200
Public:   39.75 -> 41.00 -> 43.50 -> 44.25
Hidden:   38.00 -> 41.75 -> 44.00 -> 44.75
```

现象：

- Public300、Hidden300 相对 B 的 paired CI 都包含 0；
- Hidden600 已出现小幅、CI>0 的提升；
- 到 Public900/Hidden900，提升变得明确；
- step1200 仍继续上升，但边际明显下降。

这说明原来的 300-step recipe 很可能确实在“有效学习尚未充分展开”之前就结束了。

---

# R4. 900→1200 已出现平台迹象

两个 arm 从 900 到 1200 都只增加 `+0.75 pp = 3/400`：

- Public1200 − Public900：`+0.75 pp`，95% CI `[-1.25, +3.00] pp`；
- Hidden1200 − Hidden900：`+0.75 pp`，95% CI `[-2.00, +3.50] pp`。

因此：

- formal selection 仍然应该选 1200；
- 但从 compute-efficiency 看，900 已经拿到绝大多数最终收益；
- 当前数据不支持简单假设“再训练到 1800/2400 会继续获得相同比例提升”。

后续更值得做 algorithm ablation，而不是只拉长 max_steps。

---

# R5. Public vs Hidden：没有证据证明 Hidden reward 更强

直接比较同一步数的两个 arm：

| Step | Hidden − Public Eval-Hidden Pass@1 | 95% paired CI |
|---|---:|---:|
| 300 | -1.75 pp | [-3.75, +0.25] |
| 600 | +0.75 pp | [-2.25, +3.75] |
| 900 | +0.50 pp | [-2.50, +3.50] |
| 1200 | +0.50 pp | [-3.00, +4.00] |

1200 endpoint：

- Public1200：44.25%；
- Hidden1200：44.75%；
- 只差 2/400 problems。

而 average eval-hidden test pass：

- Public1200：51.75%；
- Hidden1200：51.50%。

因此不能写成“Hidden reward 显著优于 Public reward”。正确结论是：

> **Public 和 Hidden 最终收敛到几乎相同的能力区间。当前显著信号来自 Recipe A GRPO 本身，而不是 Hidden reward source 的独立优势。**

这个负结论本身具有研究价值：它排除了“只要把 reward 换成 train-hidden tests 就能明显更强”的简单解释。

---

# R6. 没有明显 reward hacking / code-validity collapse

Parse success：

- B：98.25%；
- Public1200：97.75%；
- Hidden1200：98.25%。

Runtime error：

- B：11.00%；
- Public1200：9.50%；
- Hidden1200：9.75%。

Visible vs Eval-Hidden gap：

- Public1200：46.25% vs 44.25%，gap +2.0 pp；
- Hidden1200：47.50% vs 44.75%，gap +2.75 pp。

所以最终提升并不是以大量 parse failure、runtime failure 或极端 visible-test overfit 为代价得到的。

Completion 平均长度从 B 约 201 tokens 上升到 1200 checkpoint 的约 216–218 tokens，属于适度变长，没有伴随明显执行稳定性崩坏。

---

# R7. Policy movement 与 KL

Formal 1200-step training 的 mean KL：

- Public：约 `0.01437`；
- Hidden：约 `0.00655`。

与上一阶段非常小的 KL 相比，这说明 Recipe A 确实产生了更明显的 policy movement，方向上支持 coverage/scheduler hypothesis。

同时需要保留科学警告：

- Public KL 明显高于 Hidden；
- Public 后段 window 超过约 0.01；
- Hidden 后段也接近约 0.01。

它不是当前 training gate blocker，但说明下一阶段值得系统研究 `beta / KL / reward scale` 的能力-稳定性 trade-off。

控制面 closeout 没有保存可用于严格重构 first-4090 总 GPU-hours 的全部 target-only telemetry，因此本报告明确不伪造或估算一个“精确 GPU-hour”数字。

---

# R8. 最终假设检验

## H1：约 1 epoch coverage + sustained LR 能让现有 reward 产生有效学习

**支持。**

两个 arm 的 late checkpoint 都显著超过 B，Hidden1200 达到 +7.0 pp。

## H2：Hidden reward 明显优于 Public reward

**不支持。**

最终差异仅 +0.5 pp，95% paired CI 横跨 0，average eval-hidden test pass 甚至略低于 Public。

## H3：当前 recipe 继续增加 steps 会持续获得大幅收益

**部分支持，但已经出现平台。**

300→900 有明显增益；900→1200 仅 +0.75 pp，且 CI 包含 0。

## H4：提升是否以代码可执行性退化为代价

**当前 benchmark 上不支持该担忧。**

Parse success 基本持平，runtime-error rate 反而略低。

---

# 1. 最终科学结论

最终 selected checkpoint：

```text
Recipe A / Hidden reward / step1200
Eval-Hidden Pass@1 = 44.75% = 179/400
Refreshed B = 37.75% = 151/400
Delta = +7.00 pp
Paired bootstrap 95% CI = [+2.74, +11.50] pp
```

本阶段最终可以严谨地写成：

> **在 Qwen2.5-Coder-1.5B-Instruct 的 SFT baseline 上，通过 verifier-guided GRPO，将 active-pool coverage 从约 0.22 epoch 扩展到约 0.89 epoch，并使用 constant-with-warmup 保持 5e-6 学习率，使 canonical eval400 的 Eval-Hidden Pass@1 从 37.75% 提升到最高 44.75%（+7.0 pp，约 +18.5% relative；paired 95% CI +2.74～+11.50 pp）。Public/Hidden reward arm 在 1200 step 最终仅相差 0.5 pp，说明主要收益来自 GRPO recipe/optimization regime，而非 Hidden reward 本身。**

---

# 2. 研究价值

这个项目不只是“跑通 GRPO”，而是完成了以下闭环：

1. 从前一阶段 negative result 中提出可检验的 optimization hypothesis；
2. 冻结 Public/Hidden paired experiment，控制 reward 以外变量；
3. 设计 executable-code verifier reward；
4. 用 qkvo LoRA + sustained LR + 更高 coverage 实现 policy optimization；
5. 评估多个 checkpoint，而非只看 final checkpoint；
6. 刷新 baseline，保证同 protocol comparison；
7. 用 problem-level paired bootstrap 量化 improvement uncertainty；
8. 将 Piston infrastructure failure 与模型能力严格分离；
9. 得到“GRPO 有效、Hidden reward 未证明更优、900–1200 开始平台”的非平凡结论。

因此它已经具备完整算法实验研究的基本结构。

---

# 3. 局限性

### 3.1 eval400 已被用于模型选择

WP9-d 明确允许使用 eval400 选择 recipe/checkpoint。因此最终结果是：

> **eval400-selected benchmark improvement**

而不是 untouched held-out generalization estimate。

Paired bootstrap 可以量化这 400 个 benchmark problems 的抽样不确定性，但不能修正 adaptive checkpoint selection 带来的 winner's curse。

### 3.2 只有 seed42

当前 formal training 没有 multi-seed replication，无法直接给出 recipe-level seed variance。

### 3.3 缺少独立外部 benchmark

当前可以证明 canonical 400 题上提升，但不能直接推出 HumanEval/MBPP/LiveCodeBench 等独立 benchmark 也会同幅度提升。

### 3.4 Verification infrastructure 有偶发 noise

C0/C2 都观测到 isolated Piston sandbox failure，因此最终采用 C1 的完整 zero-sandbox Hidden300，并保留全部 failure evidence。

### 3.5 缺少严格可重构的总 GPU-hours

Target GPU 的完整成本 telemetry 没有全部同步到 control plane，因此不在 closeout 阶段虚构精确 GPU-hour。

---

# 4. 下一阶段最有价值的算法研究方向

后续不建议单纯把当前 max_steps 从 1200 拉到更高。优先级更高的是：

## 4.1 独立 benchmark validation

先把 selected checkpoint 放到未参与 tuning 的 coding benchmark 上，例如新的 executable-code set / HumanEval / MBPP / LiveCodeBench 合适子集。

目标是区分：

- eval400 adaptive tuning gain；
- 真正跨 benchmark generalization gain。

## 4.2 Reward component ablation

分别研究：

- test pass reward；
- +0.1 executable bonus；
- -0.2 timeout penalty；
- -0.1 parse penalty。

目标是回答“+7 pp 到底由什么 reward component 驱动”。

## 4.3 beta / KL sweep

Public mean KL 明显高于 Hidden，因此可以系统比较：

```text
beta = 0.005 / 0.01 / 0.02 ...
```

研究 capability improvement 与 policy drift 的 trade-off。

## 4.4 Group size / num_generations

比较 `k=4/8/16`，同时尽量控制 rollout-token/compute budget，研究 group-relative advantage 质量与样本效率。

## 4.5 Mixed Public + Hidden reward

由于纯 Hidden 并没有显著优于 Public，后续更合理的是预声明 mixed reward，而不是继续假设 Hidden-only 是正确方向。

## 4.6 LoRA capacity ablation

比较：

- qv vs qkvo；
- rank 8/16/32；

确认这轮提升中 qkvo coverage 的实际贡献。

## 4.7 Early stopping / compute-efficient GRPO

由于 900→1200 的收益已经很小，可根据：

- Eval-Hidden trajectory；
- KL；
- group reward std；
- completion stability；
- compute budget；

设计预声明 early-stopping rule。

## 4.8 更稳健的 verifier execution protocol

目标不是改变 scientific reward，而是降低 rare sandbox noise 对完整 400 题实验的干扰，并继续保持 infrastructure failure 与 candidate verdict 分离。

---

# 5. Provenance anchors

## 5.1 Training

- formal training handoff commit：`7b5e097b448b6c42fb9faf1f27711a65e00d2075`；
- operator：`ai-work/executor/operator/WP9-d/wp9d-recipe-a-formal/C0/run.sh`；
- operator SHA256：`64cd1d6accf7c4a79cbcaa825540bea43d86cf43ec703dd98a5209efdd9867b4`。

## 5.2 Eval generation

- official handoff commit：`f17b4f607daa3bb03b08682bbbd841118d36c4af`；
- run.sh SHA256：`59bed201d6f57025fcbfb22a0afed3a88298fabc04029af71ac23413f224aae4`。

## 5.3 Final local result roots

```text
B + initial clean eval runs:
/home/dzy/wp9d-eval400-verified/evaluation

Final adopted Hidden300 C1:
/home/dzy/wp9d-eval400-repair-c1/evaluation/
  wp9d-A-hidden-step300-eval400-b4-p1-seed42

C2 stability evidence only:
/home/dzy/wp9d-eval400-stability-c2/evaluation/
  wp9d-A-hidden-step300-eval400-b4-p1-seed42
```

关键 hashes：

- B generation records：`9bd47fff5c36216ede0e33c087ea98946198f6d131ff780794135aa655eb9c02`；
- C1 Hidden300 results：`60883c2b8a25c13ac6d92229fab9a74edbac95fc48241f07d48dd073bd82772e`；
- C1 Hidden300 summary：`9bebd5a148c4c6a790b4c2d630d2dc3017f5d5a0b9b944082913e238b454bf28`；
- C2 Hidden300 results：`6340a5612e6a86ed8e0f132a6c0bbc9cc59ee5c1d92e86429162bb997417f1cb`；
- C0 verification evidence：`92966897f3b705b11d95736ae47262d7be1ad6a44387342e4d6cd5a876e183e1`；
- C1 adjudication evidence：`778b18c4f4e797598159609f79ca6444747347a48cc91feb5d0d451720fc6852`；
- C2 stability evidence：`9e2b454c550f88ffd6ec845f9c998e8acaf1cab13b52beeb173c83e0d72df755`。

---

# 6. 对外表述边界

由于 eval400 已用于 checkpoint/model selection，推荐表述：

- “canonical eval400 上的 benchmark improvement”；
- “eval400-selected improvement”；
- “在相同 WP9-d protocol 下相对 refreshed B 的 paired improvement”。

不应表述为：

- “untouched held-out generalization improvement”；
- “independent test-set improvement”。

---

# 7. 一句话结论

> **Verifier-guided Recipe A GRPO 通过增加 active-pool coverage、维持非零 LR 并扩大 qkvo LoRA policy movement，将 Qwen2.5-Coder-1.5B 的 canonical eval400 Eval-Hidden Pass@1 从 37.75% 提升至 44.75%（+7.0 pp，paired 95% CI +2.74～+11.50 pp）；两个 reward arm 最终仅相差 0.5 pp，说明本轮主要收益来自 GRPO optimization regime，而非 Hidden reward source 本身。**
