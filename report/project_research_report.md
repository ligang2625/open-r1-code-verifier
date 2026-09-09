# Open-R1 CodeVerifier 项目研究报告

## Verifier-Guided Code Post-Training：从 Base / SFT 到三轮 GRPO 的完整研究闭环

**项目：** Open-R1 CodeVerifier  
**模型：** `Qwen/Qwen2.5-Coder-1.5B-Instruct`  
**核心任务：** 函数级 Python 代码生成  
**训练范式：** LoRA SFT → Verifier-Guided GRPO / RLVR  
**主评测：** canonical 400-problem Eval-Hidden Pass@1  
**最终项目状态：** 已完成 Base、SFT、两轮负结果 GRPO 诊断、数据/奖励信号重构、Recipe A GRPO 优化与最终 checkpoint 分析  
**报告定位：** 面向算法研究、简历与技术面试的项目终版；历史 `report/technical_report.md` 保留为 WP0–WP8 阶段报告，`report/wp9d_recipe_a_research_report.md` 保留为最终 Recipe A 阶段报告。

---

# 0. Executive Summary

Open-R1 CodeVerifier 是一个围绕 **Code RLVR / verifier-guided post-training** 构建的完整算法研究项目。项目不把“训练 reward 上升”直接等价为“代码能力提升”，而是从一开始就把测试信号拆成三层：

1. `visible_tests`：可出现在题目/训练表面；
2. `train_hidden_tests`：模型不可见，可作为 Hidden-RLVR 训练奖励；
3. `eval_hidden_tests`：训练和 reward 均不可访问，仅用于能力评测。

项目选用 `Qwen2.5-Coder-1.5B-Instruct` 作为主模型，在单张 RTX 4090 的 24GB 资源约束下使用 LoRA 完成 SFT 和 GRPO，并通过本地 Piston 对模型生成代码执行真实测试。

整个项目最重要的结果不是一次“调参命中”，而是一条完整的 **失败 → 诊断 → 算法/数据修正 → 再失败 → 再诊断 → 最终成功** 的研究链路：

```text
Base A
11.50% Eval-Hidden Pass@1
    |
    | LoRA SFT
    v
SFT B
37.75%      (+26.25 pp vs Base)
    |
    | GRPO Round 1: k=4, 300 steps
    | 100% SFT/GRPO problem overlap
    | ~32% zero-variance groups
    v
Public / Hidden GRPO
37.50% / 37.50%       # 无增益
    |
    | Data + reward-informativeness refresh
    | 10k refresh pool -> calibrated active1354
    | k=8, no dual-uninformative problems
    v
GRPO Round 2
B / Public / Hidden = 37.50% / 37.50% / 37.50%
    |                  # 仍无 held-out 增益
    | Diagnosis: 300 steps ~= 0.22 epoch
    | cosine LR -> ~0, mean KL ~1.2e-4
    v
GRPO Round 3 / Recipe A
1200 steps ~= 0.89 epoch
5e-6 constant_with_warmup
fresh q/k/v/o LoRA, k=8
    |
    v
Public1200 = 44.25%
Hidden1200 = 44.75%
```

最终严格同协议下，刷新后的 SFT B 为 **37.75% = 151/400**；Recipe A Public1200 达到 **44.25% = 177/400**，Hidden1200 达到 **44.75% = 179/400**。

同题 problem-level paired bootstrap（10,000 resamples，seed 42）：

- **Public1200 − B：+6.50 pp，95% CI `[+2.25, +10.75] pp`**；
- **Hidden1200 − B：+7.00 pp，95% CI `[+2.74, +11.50] pp`**；
- **Hidden1200 − Public1200：+0.50 pp，95% CI `[-3.00, +4.00] pp`**。

因此项目最终支持两个核心结论：

> **第一，Verifier-Guided GRPO 本身能够在充分 coverage 和持续 policy update 下继续提升强 SFT policy；第二，当前证据并不支持 Hidden reward source 相比 Public reward source 有明确独立优势。**

从项目轨迹看，Eval-Hidden Pass@1 描述性地从 Base 的 `11.50%` 提升到 SFT 的 `37.75%`，最终达到 `44.75%`。其中最严格的最终 GRPO 因果比较是 **37.75% → 44.75%，+7.0 pp，约 +18.5% relative**。

---

# STAR 项目叙事

# S — Situation：研究背景、模型选择与问题定义

## S1. 为什么研究 Code RLVR

代码生成天然适合 Reinforcement Learning with Verifiable Rewards：模型输出可以通过真实程序执行和单元测试自动判断，不需要额外训练通用 Reward Model，也不依赖 LLM-as-a-Judge。

但 executable reward 也存在明显风险：

- 模型可能只适配公开样例；
- reward verifier 覆盖不充分时，训练 reward 上升但真实程序正确率不升；
- visible tests 上的优化可能形成 verifier overfitting；
- 高 reward 可能来自 partial / brittle solution，而不是完整算法能力。

所以项目的核心问题不是“GRPO 能不能把 reward 拉高”，而是：

> **执行测试作为训练奖励时，模型学到的是可泛化的代码能力，还是对 reward verifier 的局部适应？**

这决定了后续所有数据和评测设计。

---

## S2. 为什么选择函数级 Python 代码任务

项目主动把任务限定为 **function-level Python generation**，而不是多轮 Agent、Shell 工具调用或复杂 repository-level coding，原因是：

1. **奖励可验证**：给定 target function 和输入输出测试，可以直接执行并得到 pass rate；
2. **credit 更干净**：失败可以被分类为 parse、runtime、timeout、wrong answer，而不是混合工具调用失败；
3. **便于三层 verifier 隔离**：同一道题可以构造 visible / train-hidden / eval-hidden 三套独立测试；
4. **适合单 GPU post-training**：prompt/completion 长度、执行成本和 rollout 成本都可控；
5. **适合研究 Reward Hacking / verifier overfitting**：可以直接检查模型代码是否只适配测试表面。

模型 prompt 被约束为输出单个 Python code block，并通过 AST 检查目标函数是否存在，再交给执行器。

---

## S3. 模型选择：为什么是 Qwen2.5-Coder-1.5B-Instruct

项目没有做多基座模型 leaderboard sweep，而是采用 **研究目标 + 资源约束驱动的模型选择**：

- 主模型：`Qwen/Qwen2.5-Coder-1.5B-Instruct`；
- immutable revision：`2e1fd397ee46e1388853d2af2c993145b0f1098a`；
- debug 模型：同系列 0.5B，仅用于工程 smoke；
- 正式 optimizer-based SFT / GRPO 只在 24GB RTX 4090 上运行。

选择 1.5B 规模的主要考虑：

1. **代码专用预训练 / instruct 能力**，适合函数级 Python；
2. **单张 24GB GPU 可完整跑 SFT + GRPO**，无需量化主模型；
3. **能使用 LoRA + gradient checkpointing 做真实 optimizer training**；
4. **训练成本足够低**，允许多轮失败诊断和 checkpoint sweep，而不是只能跑一次昂贵大模型实验；
5. 与 Open-R1 / TRL / PEFT 技术栈兼容。

因此模型选择强调的是 **可完成一套真实算法研究闭环**，而不是“选一个最强 benchmark model”。

---

## S4. 三层测试设计：把 reward 与 evaluation 隔离

每个 `CodeProblem` 持有三层独立测试：

```text
visible_tests
train_hidden_tests
eval_hidden_tests
```

定义：

- **Visible**：普通任务表面，可用于 Public reward；
- **Train-Hidden**：模型不可见，只允许 Hidden-RLVR reward 读取；
- **Eval-Hidden**：训练数据、模型 prompt、SFT、GRPO reward 全部禁止访问，只用于评测。

项目实现 deterministic test split、normalized hash、cross-layer dedup、严格字段白名单和 leakage checker；训练 artifacts 中任何 eval-hidden payload 都会 fail closed。

这一设计把研究问题从“训练 reward 有没有涨”升级为：

> **reward-source improvement 是否能够跨 verifier boundary 迁移到独立测试？**

---

## S5. 安全执行和评测基础设施

模型生成代码不能直接在宿主 Python 进程中 `eval/exec`。项目构建了：

- AST parser / code extractor；
- loopback-only `PistonExecutor`；
- timeout / memory / output / filesystem / network isolation；
- bounded concurrency；
- strict execution status taxonomy；
- deterministic evaluation JSONL；
- exact-prefix resume；
- problem-level bootstrap；
- generation 与 Piston verification 解耦。

硬件分工：

- GTX 1660 Ti：control plane、Piston、数据处理、verification、aggregation、统计分析；
- RTX 4090：正式 SFT / GRPO optimizer training 与大模型 generation。

这使算法实验能够区分 **模型失败** 和 **sandbox / transport / infrastructure failure**。

---

# T — Task：研究问题、实验设计与成功标准

项目最终需要回答以下问题。

## T1. Base → SFT 是否能建立足够强的代码 policy

定义：

```text
A = Base model
B = LoRA SFT from A
```

SFT 的角色不仅是提高正确率，还要：

- 学会稳定代码输出格式；
- 提高 parse / execute 成功率；
- 建立 Public / Hidden GRPO 的共同 parent；
- 避免两个 RL arm 因初始化不同导致不可比较。

---

## T2. Public-RLVR 是否能超过 SFT

定义：

```text
C = GRPO from B, reward uses visible_tests
```

如果 C 只提高 visible verifier 而不提高 Eval-Hidden，则可能存在 verifier-local adaptation。

---

## T3. Hidden-RLVR 是否优于 Public-RLVR

定义：

```text
D = GRPO from the same B, reward uses train_hidden_tests
```

Public 和 Hidden 必须：

- 同一个 B；
- 同一个 training problem order；
- 同一个 seed；
- 同一组非 reward hyperparameters；
- 同一个 final evaluation protocol。

唯一科学差异是 reward test source。

---

## T4. 若 GRPO 失败，能否定位具体机制并改进 recipe

项目明确允许负结果。真正要求是：

- 保存全部 checkpoint 和失败 evidence；
- 分析 data overlap、reward variance、KL、coverage、scheduler、runtime stability；
- 不用“reward hacking”解释所有失败；
- 把诊断转化成下一轮可检验的算法假设。

这最终形成三轮 GRPO 迭代。

---

## T5. 评测和统计标准

Primary metric：

> **Eval-Hidden Pass@1**

Secondary metrics：

- Visible Pass@1；
- Train-Hidden Pass@1；
- Eval-Hidden average test pass rate；
- parse success；
- runtime / timeout / wrong-answer rate；
- completion length；
- trainer reward / reward std；
- KL / clipping；
- rollout efficiency。

Canonical evaluation 使用 400 个 problem IDs；paired bootstrap：

- seed 42；
- 10,000 resamples；
- 95% CI；
- sampling unit = problem。

---

# A — Action：完整算法与实验流程

# A1. 原始数据集与 formal evaluation foundation

项目最初冻结一套 3,200 题 canonical data：

```text
train       2500
validation   300
test         400
```

数据层完成：

- deterministic problem split；
- deterministic three-test-layer split；
- exact / normalized dedup；
- cross-split leakage check；
- SFT / Public GRPO / Hidden GRPO 独立 training views；
- eval-hidden payload isolation。

Formal evaluation 固定在 400 个 test problems 上，Base / SFT / GRPO 使用相同 problem IDs 和 verifier definitions。

---

# A2. Base A：建立模型能力下限

Base：

```text
Qwen2.5-Coder-1.5B-Instruct
seed = 42
deterministic generation
max_new_tokens = 512
```

Formal Base A：

| Metric | Base A |
|---|---:|
| Visible Pass@1 | 12.25% |
| Train-Hidden Pass@1 | 11.75% |
| Eval-Hidden Pass@1 | **11.50%** |
| Eval-Hidden 95% bootstrap CI | `[8.5%, 14.75%]` |

这个结果说明原始 1.5B instruct model 在目标函数级 benchmark 上仍有较大提升空间。

---

# A3. SFT B：先建立强 parent policy

## A3.1 SFT 数据

Formal SFT：

- train：2,500；
- validation：300；
- visible-only training artifact；
- 全部通过 prevalidation；
- 最大 token count `1519 <= max_seq_length 1536`。

SFT 不读取 train-hidden / eval-hidden tests。

## A3.2 SFT 训练参数

| 参数 | 值 |
|---|---:|
| Model | Qwen2.5-Coder-1.5B-Instruct |
| Epochs | 2 |
| Global step | 314 |
| max_seq_length | 1536 |
| Batch size | 1 |
| Gradient accumulation | 16 |
| Learning rate | `2e-4` |
| Warmup | 0.05 |
| Scheduler | cosine |
| Precision | BF16 |
| Gradient checkpointing | true |
| LoRA rank | 16 |
| LoRA alpha | 32 |
| LoRA dropout | 0.05 |
| Save/eval cadence | 100 steps |
| Seed | 42 |

Formal training：

- final train loss：`0.2153632591`；
- accepted training GPU-hours：`0.521587`；
- checkpoints：100 / 200 / 300 / 314。

## A3.3 SFT 结果

| Metric | Base A | SFT B | Observed Δ |
|---|---:|---:|---:|
| Visible Pass@1 | 12.25% | 35.25% | +23.00 pp |
| Train-Hidden Pass@1 | 11.75% | 33.50% | +21.75 pp |
| Eval-Hidden Pass@1 | **11.50%** | **37.75%** | **+26.25 pp** |

SFT 把 Eval-Hidden 从 46/400 量级提高到约 151/400，绝对提升 **26.25 pp**，相对 Base 约 **+228%**。

这个阶段建立了后续所有 GRPO 的共同强 parent B。

---

# A4. 为什么选择 GRPO，而不是直接继续 SFT

SFT 已经获得最大一段能力提升，但它依赖固定正确 trajectory。Code RLVR 的优势是能够直接用模型自己 rollout 的执行结果作为训练信号。

选择 GRPO 的核心原因：

1. **天然适配同 prompt 多 completion**：可以对一个问题采样多个 candidate，并用组内 reward 做 relative advantage；
2. **不需要单独 value / critic model**，相比 PPO 更适合单 24GB GPU；
3. **reward 可以直接来自 deterministic code verifier**，不需要 learned Reward Model；
4. 能直接研究 test pass partial credit、execution shaping 与 policy update 的关系；
5. Open-R1 / TRL 已有稳定 GRPO trainer contract，项目主要扩展 reward、数据与执行系统，而不是重写 trainer。

---

# A5. Verifier reward 设计

每个 completion 通过 parser + Piston verifier，得到：

```text
total_reward
  = test_reward
  + executable_reward
  + timeout_penalty
  + invalid_format_penalty
```

其中：

```text
test_reward            = selected test pass rate
executable_reward      = +0.1 if parsed and executed
timeout_penalty        = -0.2 on genuine timeout
invalid_format_penalty = -0.1 on parse error
```

Public / Hidden：

```text
Public: selected tests = visible_tests
Hidden: selected tests = train_hidden_tests
```

`eval_hidden_tests` 在训练 reward 路径中不可见。

Infrastructure failure 不被普通记成 0 reward；正式训练路径对 sandbox/infrastructure failure fail closed，避免污染 optimizer update。

---

# A6. GRPO Round 1：第一次负结果

## A6.1 配置

第一轮正式 Public / Hidden GRPO 从同一个 SFT B 分叉。

主要参数：

| 参数 | Round 1 |
|---|---:|
| num_generations | 4 |
| max_steps | 300 |
| max_prompt_length | 1024 |
| max_completion_length | 512 |
| train batch | 1 |
| grad accumulation | 8 |
| LR | `5e-6` |
| scheduler | cosine |
| warmup | 0.05 |
| temperature | 0.8 |
| top_p | 0.95 |
| beta | 0.01 |
| LoRA | r16 / alpha32 / dropout0.05 |
| precision | BF16 |
| seed | 42 |

每个 arm：

- 300 optimizer steps；
- 2,400 rollouts；
- Public generated tokens：514,360；
- Hidden generated tokens：512,918；
- Public GPU-hours：4.0123；
- Hidden GPU-hours：3.5037。

## A6.2 Round 1 结果

| Method | Visible | Train-Hidden | Eval-Hidden |
|---|---:|---:|---:|
| SFT B | 35.25% | 33.50% | **37.75%** |
| Public GRPO | 36.25% | 34.00% | 37.50% |
| Hidden GRPO | 36.25% | 34.00% | 37.50% |

Paired Eval-Hidden：

```text
Public - SFT = -0.25 pp
95% CI = [-1.25, +0.75] pp

Hidden - SFT = -0.25 pp
95% CI = [-1.25, +0.75] pp
```

结论：**没有 evidence 表明第一轮 GRPO 超过 SFT。**

## A6.3 第一次失败原因分析

项目没有把负结果简单归因于“GRPO 不适合代码”，而是做了 post-hoc pipeline audit。

发现两个关键问题。

### 1. GRPO 数据与 SFT 数据完全重合

第一轮真正进入 GRPO 的约 600 problem groups 全部来自已经接受过 SFT supervision 的 2,500 train split。

即：

```text
GRPO problem overlap with SFT ~= 100%
```

对已经被 SFT 学过的题继续做 RL，新增 exploration / learning signal 可能不足。

### 2. 大量 group 没有有效相对 reward variance

k=4 的正式 rollout 中：

- Public total-reward zero-variance group ≈ **32.17%**；
- Hidden total-reward zero-variance group ≈ **31.83%**。

对于 GRPO，如果一个 group 的 candidate reward 基本相同，组内 relative advantage 很弱，rollout 计算并没有转化成有效 policy gradient。

因此 Round 1 的核心诊断是：

> **训练数据重复度过高 + group informativeness 不足，导致大量 rollout 的有效学习密度偏低。**

这促使项目启动 WP9 GRPO Refresh，而不是无脑增加 steps。

---

# A7. 数据刷新：从 100% overlap 到独立、可校准的 GRPO pool

## A7.1 新数据源

WP9 data refresh 引入 pinned external code-problem snapshots，包括：

- DeepCoder / PrimeIntellect projection；
- DeepCoder / TACO projection；
- 独立 evaluation references 用于去污染检查。

一次正式 source materialization 中：

```text
rows scanned                 23,688
adapter-accepted candidates  13,965
```

项目执行：

- source provenance / revision / license freeze；
- exact statement / solution / test fingerprint dedup；
- near-duplicate detection；
- SFT overlap audit；
- validation / project-test overlap hard exclusion；
- evaluation reference decontamination；
- deterministic three-layer test materialization。

## A7.2 10k refresh pool

最终数据协议冻结为：

```text
10,000 train candidates
  = 750 frozen-SFT explicit reuse
  + 9,250 new external problems
```

SFT overlap：

```text
750 / 10,000 = 7.5%
```

低于 15% hard max。

最终 accepted refresh authority 中 external dedup retained pool 为 9,565；validation/project-test/evaluation-overlap 均 fail closed。

这一步直接修复 Round 1 的 “100% SFT overlap” 问题。

---

# A8. Reward-informativeness calibration：active1354

仅减少数据 overlap 还不够，因为 GRPO 需要组内 reward variance。

因此项目先使用 frozen B 对 candidate problems 做多样本 calibration，再决定哪些问题值得进入 GRPO。

最终 C29 calibration：

```text
pre-calibration viable problems = 1602
base sample size                = k=8
borderline retry                = additional 8 -> total 16 samples
```

Informativeness 不使用 auxiliary reward variance，而是直接根据 **test reward population std > 0** 分类：

```text
dual_informative   = 1123
public_only        =   88
hidden_only        =  143
dual_uninformative =  248
```

所有 `248 dual_uninformative` 被剔除且不 backfill：

```text
active pool = 1123 + 88 + 143 = 1354
```

因此 active1354 的关键性质是：

> **每个进入 GRPO 的问题在 frozen-B calibration 时，至少在 Public 或 Hidden 某一个 reward source 上具有非零 test-reward variance；不存在 calibration 时两侧同时 zero-variance 的 problem。**

注意：`public_only` 在 Hidden 侧仍可能 zero-variance，`hidden_only` 在 Public 侧仍可能 zero-variance，所以不能描述成“每道题两侧都非零方差”。

这一步已经完成 static reward-informativeness filtering。

---

# A9. GRPO Round 2：数据问题修复后仍然失败

## A9.1 配置

Round 2 使用 active1354：

| 参数 | Round 2 |
|---|---:|
| num_generations | **8** |
| max_steps | 300 |
| max_prompt_length | 2048 |
| max_completion_length | 512 |
| train batch | 1 |
| grad accumulation | 8 |
| LR | `5e-6` |
| scheduler | **cosine** |
| warmup | 0.05 |
| temperature | 0.8 |
| top_p | 0.95 |
| beta | 0.01 |
| LoRA | r16 / alpha32 / dropout0.05，历史 PEFT q/v default |
| precision | BF16 |
| seed | 42 |

由于 `num_generations=8` 且 effective generation batch=8，每个 optimizer step 对应 **一个 8-completion problem group**。

所以 300 steps 只覆盖：

```text
300 / 1354 ~= 0.2216 epoch
```

## A9.2 Round 2 结果

同 WP9-c frozen eval protocol：

| Method | Eval-Hidden Pass@1 |
|---|---:|
| B | **37.50% = 150/400** |
| Public GRPO | **37.50% = 150/400** |
| Hidden GRPO | **37.50% = 150/400** |

Paired primary delta：

```text
Public - B = 0.00 pp, 95% CI [-1.00, +1.00] pp
Hidden - B = 0.00 pp, 95% CI [-1.00, +1.00] pp
```

Hidden 相对 B 的 Train-Hidden Pass@1：

```text
+1.25 pp
95% CI [+0.25, +2.50] pp
```

这说明 Hidden reward 确实产生了 **reward-source-local adaptation**，但没有迁移到 Eval-Hidden。

## A9.3 第二次失败原因分析

这一轮已经解决：

- SFT overlap；
- dual-uninformative problem；
- k=4 group-size limitation；

但仍没有 Eval-Hidden improvement。

训练 dynamics 给出了更强的诊断：

```text
steps                   300
active-pool coverage     ~0.2216 epoch
LR schedule              cosine
LR at end                ~0
Public mean KL           ~1.227e-4
Hidden mean KL           ~1.255e-4
clip-region mean         0
completion clipped ratio <0.75%
reward variance          healthy
```

核心现象是：

> **reward signal 有方差，但 policy 几乎没有移动。**

300 steps 只看到 active1354 的约 22%，而 cosine scheduler 又在这 300 steps 内把完整 `5e-6` budget 衰减到接近 0。

因此 Round 2 的失败机制被归纳为：

> **coverage / scheduler / update-budget mismatch，而不是 reward collapse。**

项目还做了一个 supplemental SFT-only active1354 continuation，Eval-Hidden 只有 **34.25% = 137/400**，作为负对照说明“继续普通 SFT”也不是当前正确方向。

---

# A10. GRPO Round 3 / Recipe A：把失败诊断转成算法修正

## A10.1 设计目标

Round 3 不再继续盲目搜索 recipe，而是直接针对 Round 2 的诊断：

1. **增加 active-pool coverage**；
2. **避免 LR 在训练未覆盖足够数据前衰减到 0**；
3. **扩大 fresh GRPO adapter 的 attention projection coverage**；
4. 保持 reward、k、active pool 和 Public/Hidden fairness。

项目同时采用 capability-first runtime：colocated vLLM rollout generation。

因此 Round 3 是一套 Recipe A package，而不是严格的单变量 ablation；其主要科学假设是 coverage/scheduler correction，但 qkvo LoRA 与 rollout backend 也在 Recipe A 前被明确冻结为新的统一 baseline。

---

## A10.2 Policy 初始化

每个 arm 都独立构造：

```text
Base model
  -> load completed SFT B adapter read-only
  -> safe merge B
  -> attach fresh GRPO LoRA
```

Round 3 将 GRPO LoRA 从历史 Qwen2 PEFT auto q/v 扩展为：

```text
q_proj
k_proj
v_proj
o_proj
```

参数：

```text
r = 16
alpha = 32
dropout = 0.05
```

Public / Hidden 仍从同一个 frozen B 独立初始化，不共享 mutable adapter state。

---

## A10.3 Recipe A formal parameters

| 类别 | 参数 | Recipe A |
|---|---|---:|
| Data | active problems | 1354 |
| Sampling | num_generations | 8 |
| Sampling | temperature | 0.8 |
| Sampling | top_p | 0.95 |
| Length | max_prompt_length | 2048 |
| Length | max_completion_length | 512 |
| Optimizer | learning_rate | `5e-6` |
| Optimizer | scheduler | **constant_with_warmup** |
| Optimizer | warmup_ratio | 0.05 |
| Training | max_steps | **1200** |
| Training | batch | 1 |
| Training | gradient accumulation | 8 |
| GRPO | beta | 0.01 |
| Precision | BF16 | true |
| Memory | gradient checkpointing | true / non-reentrant |
| LoRA | r / alpha / dropout | 16 / 32 / 0.05 |
| LoRA | targets | **q/k/v/o** |
| Runtime | vLLM | colocate |
| Runtime | vLLM memory utilization | 0.4 |
| Reward | verification workers | 8 |
| Checkpoint | save_steps | 50 |
| Evaluation | measured checkpoints | 300/600/900/1200 |
| Seed | seed | 42 |

Coverage：

```text
1200 / 1354 ~= 0.886 epoch
```

每个 arm：

```text
1200 groups * 8 completions ~= 9,600 rollouts
```

Public + Hidden 合计约 19,200 training rollouts。

---

# A11. Recipe A evaluation protocol

Canonical eval400：

- 400 fixed problem IDs；
- deterministic decoding；
- `do_sample=false`；
- max new tokens 512；
- logical generation batch 4；
- float16 generation；
- seed 42；
- local Piston verification；
- 64 verification workers；
- problem-level paired bootstrap 10,000 resamples。

WP9-d 使用新的 frozen evaluation runtime，因此先重新生成 / 验证 SFT B，再解释 GRPO delta。

最终 scientific set：

```text
B                       1 * 400
Public checkpoints      4 * 400
Hidden checkpoints      4 * 400
--------------------------------
Total                   9 bundles / 3600 results
```

---

# A12. Round 3 learning curve

## Public arm

```text
step 300   39.75%
step 600   41.00%
step 900   43.50%
step 1200  44.25%
```

## Hidden arm

```text
step 300   38.00%
step 600   41.75%
step 900   44.00%
step 1200  44.75%
```

两个 arm 都不是早期 spike，而是随着 coverage 增加持续上升。

---

# A13. Round 3 最终统计结果

刷新后的 B：

```text
Eval-Hidden Pass@1 = 37.75% = 151/400
```

最终：

```text
Public1200 = 44.25% = 177/400
Hidden1200 = 44.75% = 179/400
```

Paired bootstrap：

| Comparison | Δ Eval-Hidden Pass@1 | 95% CI |
|---|---:|---:|
| Public1200 − B | **+6.50 pp** | **[+2.25, +10.75] pp** |
| Hidden1200 − B | **+7.00 pp** | **[+2.74, +11.50] pp** |
| Hidden1200 − Public1200 | +0.50 pp | [-3.00, +4.00] pp |

Hidden1200 相对 B：

- net +28 solved problems；
- absolute +7.0 pp；
- relative improvement ≈ +18.5%。

---

# A14. 900→1200：开始出现平台

两个 arm 从 900 到 1200 都只提升：

```text
+0.75 pp = +3/400
```

Paired CI：

```text
Public1200 - Public900
= +0.75 pp
95% CI [-1.25, +3.00] pp

Hidden1200 - Hidden900
= +0.75 pp
95% CI [-2.00, +3.50] pp
```

因此：

- 按预声明 selection rule，1200 是 formal winner；
- 但 900 已经拿到绝大多数收益；
- 不支持简单推断“再训练到 1800/2400 还会线性涨”。

---

# A15. Public vs Hidden：reward source 不是主要增益来源

每个 checkpoint 的 Hidden − Public：

| Step | Δ Eval-Hidden | 95% CI |
|---|---:|---:|
| 300 | -1.75 pp | [-3.75, +0.25] |
| 600 | +0.75 pp | [-2.25, +3.75] |
| 900 | +0.50 pp | [-2.50, +3.50] |
| 1200 | +0.50 pp | [-3.00, +4.00] |

最终只有 2/400 problems 的差异。

因此不能写：

> Hidden reward 显著优于 Public reward。

正确结论：

> **GRPO recipe / optimization regime 的效果远强于 reward source 本身的差异。**

---

# A16. Policy movement：为什么 Round 3 与 Round 2 不同

Round 2：

```text
mean KL ~1.2e-4
```

Round 3：

```text
Public mean KL ~0.01437
Hidden mean KL ~0.00655
```

按 mean KL 量级计算，Round 3 的 policy movement 相比 Round 2 约增大 **50–100×**（不同 reward arm 幅度不同）。

同时 Eval-Hidden 也从“无变化”变成 +6.5 / +7.0 pp。

这与 coverage / sustained-LR hypothesis 在方向上高度一致。

需要保留的科学限制：Public KL 高于 Hidden，后段 window 也达到 >0.01；它提示下一阶段应该研究 beta / KL control，而不是无限扩大 update。

---

# A17. Code validity / reward-hacking 检查

Final endpoint：

| Metric | B | Public1200 | Hidden1200 |
|---|---:|---:|---:|
| Parse success | 98.25% | 97.75% | 98.25% |
| Runtime error | 11.00% | 9.50% | 9.75% |
| Eval-Hidden Pass@1 | 37.75% | 44.25% | 44.75% |

提升没有伴随明显 parse/runtime collapse。

早期项目还冻结了 25 个 failure candidates 做人工 review：

```text
runtime error         11
incomplete algorithm   6
misunderstood problem  5
missed edge case       2
syntax error           1
```

在该 25-case candidate-stratified sample 中，没有发现足够代码证据标记为 explicit reward hacking。

这不是“Reward Hacking rate = 0%”的总体估计，只说明当时失败主要表现为普通代码错误，而不是明显 verifier-specific hardcoding。

---

# A18. Infrastructure failure 与 scientific result 分离

最终 eval400 verification 还暴露了真实工程问题：Piston 偶发 `sandbox_error`。

Hidden300：

- C0：2 个 sandbox errors；
- C1：完整重跑 400 题，0 sandbox；
- C2：确认一个 timeout 边界题的 C1 结果，但新出现另一个独立 sandbox error。

最终采用：

> **C1 作为 Hidden300 scientific result；C2 只作为稳定性佐证。**

项目没有把单个失败行 patch 到另一轮，也没有为了“跑绿”覆盖失败 evidence。

这部分虽然不属于算法创新，但体现了研究结果可审计性：基础设施噪声不会被错误解释为模型能力变化。

---

# R — Result：全项目量化结论

# R1. 能力演化总表

不同阶段的 evaluation runtime 有历史演化，因此**严格科学比较应使用各阶段内部同协议 baseline**；下表用于展示项目轨迹，而不是把所有跨阶段数字当成同一严格 paired experiment。

| Stage | Policy | Eval-Hidden Pass@1 | 严格阶段内结论 |
|---|---|---:|---|
| Base | Qwen2.5-Coder-1.5B | **11.50%** | 原始能力基线 |
| SFT | B | **37.75%** | Base → SFT +26.25 pp |
| GRPO Round 1 | Public | 37.50% | vs SFT -0.25 pp，CI crossing 0 |
| GRPO Round 1 | Hidden | 37.50% | vs SFT -0.25 pp，CI crossing 0 |
| GRPO Round 2 | B | 37.50% | WP9-c 同协议 baseline |
| GRPO Round 2 | Public | 37.50% | vs B 0.00 pp |
| GRPO Round 2 | Hidden | 37.50% | vs B 0.00 pp |
| GRPO Round 3 | refreshed B | **37.75%** | WP9-d 同协议 baseline |
| GRPO Round 3 | Public1200 | **44.25%** | +6.50 pp，CI > 0 |
| GRPO Round 3 | Hidden1200 | **44.75%** | +7.00 pp，CI > 0 |

项目描述性 trajectory：

```text
11.50%  Base
   |
   +26.25 pp
   v
37.75%  SFT
   |
   +7.00 pp  # final strict GRPO delta vs refreshed B
   v
44.75%  final selected checkpoint
```

---

# R2. 三轮 GRPO 的失败/成功机制对照

| 轮次 | 数据 | k | Steps / coverage | LR | 关键现象 | Eval-Hidden 结论 |
|---|---|---:|---|---|---|---|
| Round 1 | 100% 与 SFT train 重叠 | 4 | 300 / ~600 groups | cosine | ~32% zero-variance groups | 无增益 |
| Round 2 | active1354，剔除 dual-uninformative | 8 | 300 / ~0.22 epoch | cosine | reward variance healthy，但 KL ~1.2e-4 | 无增益 |
| Round 3 | 同 active1354 | 8 | 1200 / ~0.89 epoch | constant_with_warmup | KL 明显增大，learning curve 持续上升 | **+6.5/+7.0 pp** |

这个表是整个项目最重要的研究总结。

它说明：

1. **只换 RL 算法名没有意义，数据是否产生 informative relative reward 很重要；**
2. **修复数据也不够，如果 scheduler / coverage 让 policy 几乎不移动，GRPO 仍然无效；**
3. **当 informative data、group size、coverage 和持续 LR 同时合理时，GRPO 才真正产生可测的能力提升。**

---

# R3. 第一次 GRPO 为什么失败

最高置信度解释：

```text
100% SFT/GRPO overlap
+
k=4 group informativeness 不足
+
~32% zero-variance groups
=
有效 RL signal density 过低
```

Round 1 不是证据证明“GRPO 无效”，而是暴露了 dataset/reward-design 问题。

---

# R4. 第二次 GRPO 为什么失败

Round 2 已修复数据：

```text
low SFT overlap
+
k=8
+
active1354 static informativeness filtering
```

但训练配置仍然：

```text
300 steps
cosine LR
```

结果只覆盖 active1354 的约 22%，同时 LR 已在 300 steps 内衰减到近 0；mean KL 约 `1.2e-4`。

因此最高置信度解释是：

> **有效 policy update budget 不足，而不是 reward collapse。**

这也是为什么 Round 3 优先修 scheduler / coverage，而不是立即换 reward formula。

---

# R5. 第三轮为什么成功

Recipe A 做了三个关键动作：

1. `300 → 1200 steps`，coverage `0.22 → 0.89 epoch`；
2. `cosine → constant_with_warmup`，warmup 后持续保持 `5e-6`；
3. fresh GRPO LoRA 从历史 q/v 扩为 q/k/v/o，同时采用统一 colocated-vLLM runtime。

最终：

- policy KL 从 Round 2 的 `~1.2e-4` 上升到 `~1e-2` 量级；
- Public / Hidden learning curve 都持续提高；
- Eval-Hidden 相对刷新 B 分别 +6.5 / +7.0 pp；
- parse/runtime stability 没有崩坏。

因此可以说：

> **Round 3 成功的核心不是“训练更久”四个字，而是把 coverage、scheduler、adapter capacity 和 rollout runtime 重新设计成能够产生持续有效 policy movement 的完整 recipe。**

但由于 qkvo 和 rollout backend 也一起成为新 baseline，不能把 +7pp 严格归因于单一 scheduler 变量。

---

# R6. Hidden reward 假设的最终结论

项目一开始的重要假设之一是：

> Hidden reward 是否会比 Public reward 更能提高独立 Eval-Hidden？

三轮实验没有提供支持：

- Round 1：Public = Hidden；
- Round 2：Hidden 只在 Train-Hidden 出现 local adaptation，但 Eval-Hidden 不升；
- Round 3：Hidden1200 只比 Public1200 高 0.5 pp，95% CI `[-3.0,+4.0]`。

因此最终结论是：

> **当前最强证据支持“GRPO optimization regime 有效”，而不是“Hidden reward source 更有效”。**

这类负结论很重要，因为它排除了一个看似直觉但未被数据支持的假设。

---

# R7. 对简历最有价值的量化结果

可以压缩成以下四个数字：

```text
Base Eval-Hidden Pass@1        11.50%
SFT Eval-Hidden Pass@1         37.75%   (+26.25 pp)
Final GRPO Eval-Hidden Pass@1  44.75%   (+7.00 pp vs refreshed SFT)
Final GRPO paired 95% CI                  [+2.74, +11.50] pp
```

以及：

```text
final Public vs Hidden difference = +0.50 pp
95% CI = [-3.00, +4.00] pp
```

说明项目不仅有正向结果，也有严格的负结论。

---

# R8. 面向简历的项目价值

这个项目体现的不只是“会跑 SFT/GRPO”，而是四种算法研究能力。

## 1. 能构造可验证的 RL objective

从 Python code execution 构造：

```text
pass-rate reward
+ executable shaping
- timeout penalty
- parse penalty
```

并严格隔离 Public / Train-Hidden / Eval-Hidden verifier。

## 2. 能做数据和 reward-signal engineering

从：

```text
100% SFT-overlap + ~32% zero-variance
```

重构成：

```text
10k refresh pool
7.5% SFT overlap
k=8 calibration
active1354
0 dual-uninformative problems
```

## 3. 能从负结果诊断 optimization dynamics

不是看到 GRPO flat 就盲扫超参，而是根据：

- coverage；
- LR trajectory；
- KL；
- reward std；
- group variance；
- clipping；

定位 `coverage/scheduler/update-budget mismatch`。

## 4. 能用严格统计和 failure analysis 支撑结论

- 400 problem paired comparison；
- 10,000-resample bootstrap；
- 95% CI；
- 25-case manual failure review；
- infrastructure failure 与 model verdict 分离。

---

# 1. 可直接用于简历的 STAR 表述

## Situation

在 Code RLVR 中，公开测试奖励容易出现 verifier overfitting，且训练 reward 提升不一定代表真实代码正确率提升；同时单张 24GB GPU 限制了可用模型规模和 RL 算法复杂度。

## Task

基于 Open-R1 搭建 1.5B Code LLM 的 Base → LoRA SFT → Public/Hidden GRPO 全流程，引入可执行 Python verifier 和三层测试隔离，研究不同 reward source、数据 informativeness 和 GRPO optimization budget 对独立代码正确率的影响。

## Action

- 选择 `Qwen2.5-Coder-1.5B-Instruct`，在单 RTX 4090 上采用 LoRA SFT / GRPO；
- 构建 visible / train-hidden / eval-hidden 三层 verifier，使用 Piston 执行代码并设计 pass-rate + execution-shaping reward；
- 将 SFT Eval-Hidden Pass@1 从 11.50% 提升到 37.75%；
- 对第一次 GRPO 的 100% SFT overlap 和约 32% zero-variance groups 做失败诊断，随后重构 10k GRPO data pool，将 SFT overlap 降到 7.5%，再通过 k=8 calibration 得到 1,354 个 informative active problems；
- 第二次 GRPO 仍无提升后，根据 `0.22 epoch coverage + cosine LR→0 + KL≈1.2e-4` 定位 policy under-update；
- 设计 Recipe A：1200 steps、constant-with-warmup `5e-6`、fresh qkvo LoRA、k=8，并对 300/600/900/1200 checkpoint 统一评估。

## Result

- Final Hidden1200 Eval-Hidden Pass@1 **44.75%**，相对同协议 SFT B **+7.0 pp / +18.5% relative**；
- problem-level paired bootstrap 95% CI **[+2.74,+11.50] pp**；
- Public1200 44.25%，Hidden vs Public 仅 +0.5 pp、CI 跨 0，说明主要收益来自 GRPO recipe 而非 Hidden reward source；
- Parse success 保持约 98%，runtime-error rate 未恶化；
- 完整保留两轮负结果并给出 data/reward informativeness 和 optimization-budget 两类失败机制。

---

# 2. 简历 bullet 版本

推荐写法：

- **搭建 Code LLM verifier-guided post-training pipeline**：基于 Qwen2.5-Coder-1.5B + Open-R1/TRL 实现 LoRA SFT → GRPO，设计 visible/train-hidden/eval-hidden 三层测试隔离与 Piston executable reward，将 Base Eval-Hidden Pass@1 从 **11.5% 提升至 SFT 37.75%**。
- **系统诊断两轮 GRPO 负结果并重构数据/训练 recipe**：识别首轮 `100% SFT/GRPO overlap + ~32% zero-variance groups`，构建 10k refresh pool、将 SFT overlap 降至 **7.5%**，通过 k=8 reward calibration 筛得 **1,354** 个 informative training problems；第二轮进一步通过 coverage/LR/KL telemetry 定位 policy under-update。
- **设计 Recipe A 将 SFT 后能力继续提升**：采用 `1200-step + 5e-6 constant_with_warmup + k=8 + qkvo LoRA`，在 canonical 400-problem benchmark 上将 Eval-Hidden Pass@1 从 **37.75% 提升至 44.75%（+7.0pp，+18.5% relative）**，problem-paired bootstrap 95% CI **[+2.74,+11.50]pp**。
- **完成严谨对照与负结论分析**：Public/Hidden reward 最终仅差 **0.5pp**（95% CI `[-3.0,+4.0]pp`），表明收益主要来自 GRPO optimization regime 而非 Hidden reward source；结合 25-case 人工 failure analysis 和 sandbox/infrastructure adjudication 分离模型错误与执行噪声。

---

# 3. 项目局限性

1. **Single training seed**：主要 formal training 使用 seed 42；paired bootstrap 量化的是 problem uncertainty，不是 training-seed variance。
2. **Final eval400 被用于 WP9-d checkpoint selection**：最终 +7pp 应描述为 canonical/eval400-selected benchmark improvement，不是 untouched held-out estimate。
3. **Round 3 不是严格单变量 ablation**：coverage/scheduler 是主要研究假设，但 qkvo LoRA 与 vLLM runtime 也在 Recipe A 前改变并冻结。
4. **独立 external benchmark 不再作为当前项目待办**：当前报告只对 canonical 400-problem benchmark 做强结论。
5. **Piston execution 存在低概率基础设施噪声**：最终通过 full-run C1 adjudication 明确隔离，不把 sandbox error 当模型错误。

---

# 4. 后续最有价值的算法方向

在 active1354 已经完成 static informativeness filtering 的前提下，不再重复“筛掉 zero-variance 问题”。

优先方向：

## 4.1 Verifier reward geometry / credit assignment

比较：

```text
Dense pass-rate + shaping        # current
Dense pass-rate only
Binary all-tests-pass + shaping
Binary all-tests-pass only
```

回答 partial test credit 与 executable/timeout/parse shaping 的真实贡献。

## 4.2 KL-controlled GRPO

先做 fixed beta：

```text
0.005 / 0.01 / 0.02
```

再测试 adaptive beta / target-KL controller，研究不同 reward landscape 下的 policy-movement / capability trade-off。

---

# 5. Final Takeaway

整个 Open-R1 CodeVerifier 项目的最终价值可以概括为：

> **从一个 11.5% Eval-Hidden Pass@1 的 1.5B code model 出发，通过 LoRA SFT 建立 37.75% 的强 parent，再经历两轮 GRPO 负结果：第一次定位到 SFT/GRPO 数据 100% overlap 与约 32% zero-variance groups，第二次在重构 active1354 后进一步定位到 0.22-epoch coverage、cosine LR 衰减和极低 KL 导致的 policy under-update；最终将诊断转化为 1200-step constant-LR qkvo Recipe A，把同协议 SFT 的 Eval-Hidden Pass@1 提升至 44.75%（+7.0pp，paired 95% CI +2.74～+11.50pp），并证明 Hidden reward source 本身并没有显著优于 Public reward。**

这份结果体现的核心能力不是“调出了一个高分”，而是：

> **能设计可验证 RL objective、构建无泄漏数据和 verifier、分析负实验、使用训练 dynamics 定位优化瓶颈，并把诊断转化为能够通过统计检验的 post-training 改进。**

---

# 6. Provenance / 相关报告

历史主报告：

- `report/technical_report.md`：Base / SFT / 第一轮 Public/Hidden GRPO、WP8 统计与人工 failure analysis；
- `docs/wp9c-stage-closeout.md`：active1354 与第二轮 GRPO 负结果；
- `report/wp9d_recipe_a_research_report.md`：Recipe A 1200-step GRPO、checkpoint curve 与最终 +7pp 分析；
- `docs/wp9d-stage-closeout.md`：WP9-d final scientific closeout；
- `proceedings.md`：全项目阶段/协议/验收历史。

关键 identities：

```text
Model:
Qwen/Qwen2.5-Coder-1.5B-Instruct
revision 2e1fd397ee46e1388853d2af2c993145b0f1098a

Open-R1:
1416fa0cf21595d2083b399a2a0bbddd7f6e9563

Final eval400 dataset SHA256:
770b772c738514888c5900f815fc074ddb3f6c3c5f67fc5346073565536138ae

Final ordered IDs SHA256:
2d811d62613c122da6ee73f372008e44a40464ec9ad7c8df628ae01de4a234c9

Piston definition SHA256:
f049f4ea344285e2b732bb2a602e7c8888ae3ac449320039144c8a0dff62657e
```
