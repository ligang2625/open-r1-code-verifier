# WP5-a Executor 执行报告

- **依据计划**：`ai-work/planner/WP5-a-plan.md`
- **目标阶段**：WP5-a：Deterministic Generation、逐题 Pass@1 与可恢复 Evaluation Runner
- **执行分支**：`feat/wp5-a`
- **独立 worktree**：`.worktrees/wp5-a`
- **执行状态**：计划 8 个步骤均已实现并完成默认全仓验收。WP5-b 的 aggregate metrics、bootstrap CI 与正式 Base 结果未实现；真实 Base 运行仍属于下一子阶段。

本报告按 `wp-plan-executor` 的阶段重置规则新建。执行过程未修改 reviewer 报告或 `proceedings.md`，未修改 `third_party/open-r1/**` 内容或 gitlink pin。

## 1. 分步交付与提交

### 步骤 1：确定性 generation 合同与固定 prompt

提交：

```text
b4101d5  feat: add deterministic evaluation generation contract
```

新增 `code_verifier.evaluation.generate` 的 `GenerationConfig`、`GenerationResult`、`CompletionGenerator`、`GenerationError` 与固定 evaluation prompt builder。Prompt 只使用 problem statement、function signature 与 visible examples；train-hidden、eval-hidden、reference solution、SFT response 均不进入 prompt。

专项验证：

```text
PYTHONPATH=src ../../.venv/bin/python -m pytest tests/unit/evaluation/test_generate.py -q
→ 16 passed

PYTHONPATH=src make VENV=../../.venv lint
→ Ruff / format / strict Mypy 全绿
```

### 步骤 2：Frozen Transformers generation backend

提交：

```text
95cb07e  feat: add frozen transformers evaluation backend
```

实现 lazy import 的 Transformers backend：同一 model/revision 加载 tokenizer 与 causal LM、拒绝 remote code、要求 tokenizer chat template、`model.eval()`、`torch.inference_mode()`、固定 seed、`do_sample=false`、不发送 temperature/top_p、只 decode 新生成 token。最小依赖环境缺少 torch/transformers 时返回提示 `make install-full` 的结构化 `GenerationError`，默认单测不下载模型。

专项验证：

```text
PYTHONPATH=src ../../.venv/bin/python -m pytest tests/unit/evaluation/test_generate.py -q
→ 23 passed

PYTHONPATH=src make VENV=../../.venv lint
→ 全绿
```

### 步骤 3：严格 evaluation config 与逐题记录 schema

提交：

```text
ff3f78b  feat: define strict evaluation records
```

新增：

- `configs/eval/pass1.yaml`
- `EvaluationConfig`
- `EvaluationRecord`
- `EvaluationRunSummary`
- exact-field config/record mapping 校验

记录合同拒绝 unknown/missing fields、NaN/Inf、非法 rate、非法 execution status/failure counts，并保证顶层 `execution_status == eval_hidden_execution_status`。逐题 mapping 不保存 tests、reference solution、metadata 或 executor stdout/stderr。

专项验证：

```text
PYTHONPATH=src ../../.venv/bin/python -m pytest tests/unit/evaluation/test_evaluate.py -q
→ 12 passed
```

### 步骤 4：同一 completion 的三层逐题验证

提交：

```text
9c2841d  feat: evaluate completions across test layers
```

`evaluate_completion()` 复用 WP2 parser 与 WP4 `verify_completion()`，按固定 visible → train-hidden → eval-hidden 顺序对同一 completion 验证。Parse failure 保持结构化且 0 executor calls；顶层状态仅取 eval-hidden。新增稳定 coarse error category，并只保存各层 status/rate/failure-count 摘要。

专项验证：

```text
PYTHONPATH=src ../../.venv/bin/python -m pytest tests/unit/evaluation/test_evaluate.py -q
→ 15 passed
```

### 步骤 5：严格 artifact identity 与 exact-prefix resume

提交：

```text
86baac5  feat: add strict resumable evaluation runs
```

实现：

- 只接受通过 WP1 `check_prepared_data()` 验证且包含 `hf_dataset` 的 prepared artifact；
- canonical ordered dataset hash、exact prompt hash 与 resolved config/model/seed/Piston config hash；
- `outputs/evaluation/<run_id>/` 固定 artifact layout；
- `samples/results.jsonl` fsync append；
- 已存在 run 的 exact-prefix resume；
- config/model/checkpoint/seed/dataset/prompt order、repo/submodule、dependency、CUDA/GPU identity drift 均 fail closed；
- corrupt/reordered/non-finite/额外 artifact 均拒绝 resume；
- 已完成 rows 不重新 generation；
- completion/code 只允许存在于 `samples/results.jsonl`。

同时扩展 `environment.json`：记录 dependency lock identity 与可选 CUDA/GPU identity。修复 worktree 中未 checkout submodule 目录时旧 `_git_commit()` 会向父仓库回退的问题，改为直接读取主仓库 `HEAD:third_party/open-r1` gitlink，确保 Open-R1 commit identity 正确且无需修改 submodule。

专项验证：

```text
PYTHONPATH=src ../../.venv/bin/python -m pytest \
  tests/unit/evaluation/test_runner_resume.py tests/unit/test_environment.py -q
→ 9 passed

PYTHONPATH=src make VENV=../../.venv lint
→ 全绿
```

### 步骤 6：`code-verifier evaluate` CLI

提交：

```text
8ee67e0  feat: add resumable evaluation CLI
```

CLI 新增 `evaluate`，支持 required config/model/run identity、默认 `outputs` root、seed/log common args、安全 run name、Piston runtime probe、frozen generator 装配与 runner 调用。既有 configured commands 的 `--output-dir` requirement 保持不变；预期 evaluation/generation 错误返回 exit 2 且不打印 traceback/hidden payload。

专项验证：

```text
PYTHONPATH=src ../../.venv/bin/python -m pytest tests/unit/test_cli.py -q
→ 41 passed

PYTHONPATH=src make VENV=../../.venv lint
→ 全绿
```

### 步骤 7：WP5-a prepared-HF 集成与恢复验收

提交：

```text
ae972f7  test: cover resumable evaluation integration
```

新增 `tests/integration/test_wp5a_evaluation_pipeline.py`。测试从现有 20-problem fixture 临时准备真实 WP1 HF Dataset，选取 4 个 test problems，并使用 deterministic fake generator + `MockExecutor` 覆盖：

- all-pass；
- visible-only success；
- eval-hidden timeout；
- parse error；
- 第 N 题后人为 generation interruption；
- exact-prefix resume，仅生成剩余题；
- 已完成 run 再次调用 0 generation；
- 相同 seed 的独立 fake run 除 run_id 外逐题 identity 一致；
- output order 与 problem order 一致，无 duplicate；
- hidden payload 不进入 prompt、manifest、metrics 或 logs；
- results 具有完整逐题 schema，但不保存 tests。

专项验证：

```text
PYTHONPATH=src ../../.venv/bin/python -m pytest tests/integration/test_wp5a_evaluation_pipeline.py -q
→ 1 passed

PYTHONPATH=src make VENV=../../.venv lint
→ 全绿
```

### 步骤 8：文档与阶段验收

随本步骤提交：

- `README.md`：新增 WP5-a setup/evaluate 命令、artifact layout、resume identity、payload boundary、`model_revision: null` debug-only 与 WP5-b 边界；
- `AGENTS.md`：更新目录、命令、当前 scope 与 WP5-a generation/evaluation/resume 安全规则；
- `ai-work/executor/WP5-executor.md`：本执行报告。

未创建 `metrics.py`、`bootstrap.py`、SFT/GRPO 新实现或正式 Base 结果。

## 2. 最终实际验收结果

### 静态检查

```text
PYTHONPATH=src make VENV=../../.venv lint
→ Ruff check: All checks passed
→ Ruff format --check: 70 files already formatted
→ strict Mypy: Success, no issues found in 70 source files
```

### 默认全仓测试

```text
PYTHONPATH=src make VENV=../../.venv test
→ collected 591 items / 1 skipped during collection
→ 589 passed, 3 skipped, 0 failed
```

3 个 skip 均为既有真实 Piston tests；未显式设置 `CODE_VERIFIER_RUN_PISTON=1` 时按项目规则跳过。WP5-a 默认测试不要求真实模型、GPU 或 Piston。

### CLI 验收

计划中的直接 console script 在当前共享 worktree 环境存在陈旧 shebang（详见第 5 节），因此使用等价 module entrypoint 验收源码：

```text
PYTHONPATH=src ../../.venv/bin/python -m code_verifier.cli --help
→ exit 0
→ commands 包含 evaluate

PYTHONPATH=src ../../.venv/bin/python -m code_verifier.cli evaluate --help
→ exit 0
→ model-id/run-name/config required，seed/output-dir/log-level 可用
```

### 范围检查

- `src/code_verifier/evaluation/` 仅包含 `__init__.py`、`generate.py`、`evaluate.py`；不存在 `metrics.py` 或 `bootstrap.py`。
- 未新增 SFT/GRPO trainer、reward registry 或正式 Base result。
- 未修改 `third_party/open-r1/**`。
- 未修改 reviewer 报告或 `proceedings.md`。
- 当前未提交范围在生成本报告前仅为 `README.md` 与 `AGENTS.md`；源码/测试步骤均已各自提交。

## 3. 关键行为与安全边界

- Prompt 构造不接触 train-hidden/eval-hidden/reference/SFT 字段。
- Generation 只做 frozen deterministic pass@1；evaluation 不修改 checkpoint。
- 三层选择由 evaluator 显式提供给同一个 WP4 verifier；verifier 本身仍不知道 test layer。
- Eval-hidden 仅用于 evaluation，未进入 WP4 Public/Hidden training reward path。
- `results.jsonl` 是唯一允许持久化 completion/extracted code 的 WP5-a artifact；所有其它 run artifacts 均保持 payload-bounded。
- Resume 不是“按 problem_id 找到就跳过”，而是严格验证现有 JSONL 必须是当前 ordered problem list 的精确完成前缀。
- 环境 identity 包含 repo commit、Open-R1 gitlink commit、dependency-lock hash、CUDA version、GPU name/count；硬件或依赖漂移会拒绝 resume。
- 实际 untrusted code 仍只能通过 loopback-only `PistonExecutor` 执行；WP5-a 未增加 host exec/eval/compile 路径。

## 4. 配置与依赖影响

- 新增 `configs/eval/pass1.yaml`；未修改 WP3 Piston/batch 配置。
- 未修改 `pyproject.toml`、Makefile 或 Python dependency declarations。
- 实际 Transformers generation 依赖现有 `make install-full` 环境；默认 `make install`/test path 继续允许没有 torch/transformers。
- `model_revision: null` 仅用于 debug。正式 Base 必须在 WP5-b pin revision，并在 WP5-b 实现 aggregate metrics/bootstrap 后再进行正式验收。
- Environment record 增加 dependency/GPU/CUDA reproducibility fields；Open-R1 identity 改为从 gitlink 读取，可在独立 worktree 未 checkout submodule 时保持正确。

## 5. 环境偏差与限制

本计划示例命令使用 worktree 内 `.venv/bin/...`，但当前 WP5-a worktree 没有独立 `.venv`。实际复用主工作区虚拟环境时发生两个已记录的环境差异：

1. 初始计划命令 `.venv/bin/python ...` 返回 `No such file or directory`；改用 `../../.venv/bin/python`。
2. 直接复用解释器后，worktree 源码未安装到该环境，首次运行出现 `ModuleNotFoundError: code_verifier`；因此所有验收统一加 `PYTHONPATH=src`，确保执行的是 WP5-a worktree 源码。

最终计划中的 console script 还有额外 shebang 问题：

```text
PYTHONPATH=src ../../.venv/bin/code-verifier --help
→ exit 126
→ bad interpreter: .../.worktrees/wp4-b/../../.venv/bin/python
```

这是共享主虚拟环境中既有 console script 的陈旧 shebang，而不是仓库源码回归。使用相同 Python 环境的 `python -m code_verifier.cli` 后两个 help 命令均 exit 0。

可选完整推理依赖 smoke：

```text
PYTHONPATH=src ../../.venv/bin/python -c "import torch, transformers; ..."
→ ModuleNotFoundError: No module named 'torch'
```

因此本机没有执行真实 Transformers 模型 generation，也没有下载 0.5B 模型；这符合 WP5-a 自动验收“不以模型下载为前置”的计划要求。正式 Base generation、真实模型 revision pin、aggregate pass@1、bootstrap CI 与真实 Piston Base 验收均留给 WP5-b。

## 6. 结论

WP5-a 计划内的 deterministic generation contract、frozen Transformers backend、严格逐题 schema、三层 verifier evaluation、prepared-HF input、run identity、exact-prefix resume、artifact payload isolation、environment identity、`evaluate` CLI、端到端 fake integration 与文档均已完成。默认全仓测试与静态检查为 0 failed；当前阶段可提交 `wp-plan-reviewer` 独立审查。

## 7. R1 代码修复报告

修复依据：`ai-work/reviewer/WP5-review.md` R1。R1 共列出 M1、M2、m3 三项需处理问题，本轮全部接受并修复，无异议项；审查报告本身未修改。

### M1：恢复 Step 5 函数级计划合同

修复位置：`src/code_verifier/evaluation/evaluate.py`、`tests/unit/evaluation/test_runner_resume.py`、`tests/integration/test_wp5a_evaluation_pipeline.py`。

- `load_evaluation_problems()` 恢复为计划签名 `load_evaluation_problems(config: EvaluationConfig) -> list[CodeProblem]`，从 config 读取 dataset root 与 selected split。
- `initialize_or_resume_run()` 恢复为计划的 keyword-only 参数集合，并返回 `tuple[Path, list[EvaluationRecord]]`。内部仍通过私有 `_RunContext` 保持现有严格 artifact/resume 实现，但公开合同不再暴露预计算 hash 或私有 context。
- resume 解析现在同时返回已经严格验证过的 completed `EvaluationRecord` 前缀；runner 以其长度继续生成，已完成 run 仍保持零 generation/executor 调用。
- `append_evaluation_record()` 恢复为 `append_evaluation_record(path: Path, record: EvaluationRecord) -> None`，仅负责 durable results JSONL append；安全 progress event 拆到私有 `_append_progress()`，保持 metrics payload 隔离。
- 所有 unit/integration caller 与 monkeypatch 均同步到计划合同。

### M2：修正 no-CUDA environment identity 并补齐边界测试

修复位置：`src/code_verifier/environment.py`、`tests/unit/test_environment.py`。

- `_gpu_identity()` 在 torch 不存在时继续返回 `(None, None, 0)`。
- torch 即使是 CUDA build，只要 `torch.cuda.is_available()` 为 false，也按计划返回 `(None, None,0)`，不再把编译时 `torch.version.cuda` 误记为当前可用 CUDA identity。
- CUDA 可用时才记录 CUDA version、首个 GPU name 和 device count。
- 新增三类明确单测：no-torch fallback、CUDA build 但 CUDA unavailable、mocked CUDA available identity。

### m3：`resolved_config.yaml` 记录 run identity

修复位置：`src/code_verifier/evaluation/evaluate.py`、`tests/unit/evaluation/test_runner_resume.py`。

- 新 run 的 resolved config 现在同时写入 `run_id`、`model_id`、`seed`。
- resume 的 expected resolved mapping 同步要求 `run_id`，因此 run-name/config artifact drift 会 fail closed。
- 单测直接解析 `resolved_config.yaml` 并断言上述三个 CLI identity 字段。

### R1 修复后实际复测

```text
PYTHONPATH=src ../../.venv/bin/python -m pytest \
  tests/unit/evaluation/test_runner_resume.py \
  tests/unit/test_environment.py \
  tests/integration/test_wp5a_evaluation_pipeline.py -q
→ 13 passed

PYTHONPATH=src make VENV=../../.venv lint
→ Ruff check: All checks passed
→ Ruff format --check: 70 files already formatted
→ strict Mypy: Success, no issues found in 70 source files

PYTHONPATH=src ../../.venv/bin/python -m pytest \
  tests/unit/evaluation/test_generate.py \
  tests/unit/evaluation/test_evaluate.py \
  tests/unit/evaluation/test_runner_resume.py \
  tests/unit/test_environment.py \
  tests/integration/test_wp5a_evaluation_pipeline.py -q
→ 51 passed

PYTHONPATH=src make VENV=../../.venv test
→ 592 passed, 3 skipped, 0 failed
```

三个 skip 仍仅为既有、需显式启用的真实 Piston tests；本轮未新增 skip/xfail。

CLI 回归：

```text
PYTHONPATH=src ../../.venv/bin/python -m code_verifier.cli --help
→ exit 0

PYTHONPATH=src ../../.venv/bin/python -m code_verifier.cli evaluate --help
→ exit 0
```

本轮只修改 reviewer 点名的 WP5-a Step 5 contract/environment/artifact 问题及对应测试与 executor 报告；未修改 `third_party/open-r1/**`、`proceedings.md` 或 `ai-work/reviewer/WP5-review.md`，未新增 WP5-b metrics/bootstrap 或后续训练功能。R1 的 M1、M2、m3 均已处置，可提交下一轮 `wp-plan-reviewer` 复审。
