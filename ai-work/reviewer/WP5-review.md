# WP5-a 独立审查报告

- **审查计划**：`ai-work/planner/WP5-a-plan.md`
- **目标阶段**：WP5：统一评测（子阶段 a：Deterministic Generation、逐题 Pass@1 与可恢复 JSONL 运行）
- **阶段分支**：`feat/wp5-a`
- **阶段 worktree**：`.worktrees/wp5-a`
- **本轮**：R1（首轮审查）
- **审查日期**：2026-08-07

> 本阶段此前不存在 `ai-work/reviewer/WP5-review.md`，按 `wp-plan-reviewer` 的阶段报告规则，本文件从 WP5-a R1 开始记录。WP5-a 仅是 WP5 的第一个子阶段；即使本子阶段后续通过，也不得将 WP5 整体标记完成，WP5-b 的 metrics/bootstrap/正式 Base 结果仍未实现。

## R1：首轮独立审查

### 1. 审查范围与方法

- 计划文件：`ai-work/planner/WP5-a-plan.md`。
- executor 报告：`ai-work/executor/WP5-executor.md`。
- 规格依据：`PROJECT_SPEC_Open-R1_CodeVerifier.md` §6.2 Generation/Evaluation Layer、§7.2–§7.4、§13.1–§13.4、§17、§18、§19、§20 WP5、§21.1/§21.5，以及 plan §3–§5 的硬性规则和函数级实施合同。
- 审查方式：逐条核对 8 个实施步骤；阅读 generation/evaluation/CLI/environment 源码及 WP5-a 单元、恢复、集成测试；核查 hidden-test 泄漏、frozen deterministic generation、三层 verifier 调用、严格 resume/run identity 与结果字段；独立运行 lint、全量测试、WP5-a 定向测试和 CLI help，并增加一次 GPU/CUDA identity 边界探针。
- 审查纪律：审查期间未修改 `src/`、`tests/` 或 `third_party/open-r1/`；本轮只新增当前阶段审查报告。
- worktree 基线：审查开始时 `feat/wp5-a` 工作树无未提交改动。

### 2. 计划完成度核验（逐条对照 plan）

| 计划步骤 / 交付项 | 计划要求 | 状态 | 证据 |
|---|---|---|---|
| 步骤 1：Evaluation package、generation 合同与固定 prompt | `GenerationError`、`GenerationConfig`、`GenerationResult`、`CompletionGenerator`、deterministic config validation、§7.2 visible-only prompt | 已完成 | `src/code_verifier/evaluation/generate.py:15-121`；`tests/unit/evaluation/test_generate.py:128-221`。Prompt 只读取题面、签名与 `visible_tests`，hidden/reference/SFT sentinel 测试存在。 |
| 步骤 2：Frozen Transformers backend | lazy import torch/transformers；同 model/revision；`trust_remote_code=False`；chat template；`eval()` + inference mode；固定 seed；只 decode 新 token | 已完成 | `generate.py:124-249`；`test_generate.py:224-318`。未直接 import `open_r1.*`，默认测试不下载模型。 |
| 步骤 3：严格 Evaluation config / record schema | exact-field config；`EvaluationRecord` 严格 JSON-safe；finite rates/runtime；known statuses；`execution_status == eval_hidden_execution_status` | 已完成 | `src/code_verifier/evaluation/evaluate.py:41-323`；`tests/unit/evaluation/test_evaluate.py:75-187`；`configs/eval/pass1.yaml:1-11`。 |
| 步骤 4：三层逐题 Pass@1 与错误分类 | 同一 completion 按 visible → train-hidden → eval-hidden 复用 `verify_completion()`；eval-hidden 为主 status；不保存 test/executor payload | 已完成 | `evaluate.py:326-462`；`test_evaluate.py:190-263`。独立全量/定向测试通过；未发现 hidden test 进入 generator。 |
| 步骤 5：run artifacts、严格 append/resume 与可复现 identity | plan 明确定义 `load_evaluation_problems(config)`、`initialize_or_resume_run(...)->tuple[Path,list[EvaluationRecord]]`、`append_evaluation_record(path, record)`；resolved config 保存 config + model id/seed/run id；环境 CPU/no-CUDA identity；exact-prefix resume | **与计划不符 / 部分完成** | 主要运行行为在 `evaluate.py:465-875` 已实现，resume 测试通过；但三个计划函数的实际签名/返回形态与 plan §4/步骤 5 不同（M1）；`resolved_config.yaml` 未写 `run_id`（m3）；`environment.py:107-120` 在 torch 为 CUDA build 但 CUDA unavailable 时仍记录 CUDA version，且计划要求的 CPU/no-torch + mocked CUDA tests 未实现（M2）。 |
| 步骤 6：`evaluate` CLI | required config/model/run；默认 output `outputs`；Piston probe；Transformers generator；runner；脱敏 error exit 2；现有命令兼容 | 已完成 | `src/code_verifier/cli.py:83-106,297-337,421-457`；`tests/unit/test_cli.py:348-474`。独立 `python -m code_verifier.cli evaluate --help` exit 0。 |
| 步骤 7：WP5-a 端到端集成与恢复 | prepared HF → prompt → fake generation → parser → 三层 verifier → JSONL；中断恢复；deterministic repeat；payload isolation | 已完成 | `tests/integration/test_wp5a_evaluation_pipeline.py:65-269`；独立 WP5-a 定向 suite 46 passed。 |
| 步骤 8：文档、静态检查与阶段验收 | README/AGENTS；lint/test/CLI；无 WP5-b/WP6+ 越界；无 third-party 修改 | 部分完成 | README `347-383` 与 AGENTS 的 WP5-a 边界已更新；共享 venv 下 lint/test/CLI 全绿；但步骤 5 的 M1/M2/m3 仍使阶段计划不能判定全部完成。 |
| 新增业务文件 | `evaluation/__init__.py`、`generate.py`、`evaluate.py`、`configs/eval/pass1.yaml` 及 WP5-a tests | 已完成 | 文件均存在；`src/code_verifier/evaluation/` 仅有计划内三个文件。 |
| 明确范围外 | 不创建 `metrics.py`、`bootstrap.py`；不实现 SFT/GRPO；不修改 `third_party/open-r1/**`；executor 不改 proceedings | 已完成 | 当前 evaluation 目录无 `metrics.py`/`bootstrap.py`；未发现后续 WP 业务模块；worktree 基线干净且现有代码未出现 `open_r1.*` 直接 import。 |

### 3. WP5-a 交付与验收核验

| 验收项 | 状态 | 证据 |
|---|---|---|
| deterministic pass@1 generation 已实现 | 通过 | `generate.py:70-97,196-249`；sampling 被拒绝，temperature/top_p 必须为 null。 |
| Prompt 严格只使用 visible examples | 通过 | `generate.py:100-121`；`test_generate.py:153-184`；集成测试也检查 eval-hidden payload 不在 prompt。 |
| 同一 completion 对三层测试分别验证 | 通过 | `evaluate.py:404-416` 固定 visible → train-hidden → eval-hidden；Mock 调用顺序测试通过。 |
| §13.4 逐题 JSONL 字段与 payload 隔离 | 通过 | `EvaluationRecord` exact fields + integration expected-fields 断言；results 之外 artifact 不持久化 completion/code/test payload。 |
| run 具备 config/dataset/model/seed identity | **部分通过** | `run.json` 与 config/dataset hashes 已实现；但 plan 要求 `resolved_config.yaml` 同时记录 `run_id`，实际未写，见 m3。 |
| 合法中断前缀可恢复，错误前缀 fail closed | 通过 | `evaluate.py:653-751,814-874`；`test_runner_resume.py:102-356`；集成中断恢复通过。 |
| 相同 fake model + seed + config + dataset 结果稳定 | 通过 | integration `240-268` 对独立重复 run 比较逐题记录（除 run_id）一致。 |
| Base 错误类型所需原始字段可统计 | 通过 | 三层 rate/status/failure counts、parse error、tokens、generation/execution latency 均进入 record；本阶段未提前聚合。 |
| 环境 identity 满足计划的 CPU/no-CUDA 语义并有对应测试 | **未通过** | `environment.py:107-120` 的 CUDA version 行为与 plan §5 环境约束不一致；`tests/unit/test_environment.py:11-34` 无计划要求的 CPU/no-torch / mocked CUDA identity tests；独立探针确认，见 M2。 |
| `make lint` | 条件通过 | worktree 内直接 `make lint` 因缺 `.venv/bin/python` 失败；按 executor 记录的共享环境运行 `PYTHONPATH=src make VENV=../../.venv lint` 后 Ruff/format/mypy 全绿。 |
| `make test` | 条件通过 | `PYTHONPATH=src make VENV=../../.venv test`：589 passed，3 skipped，0 failed；3 个 skip 均为既有显式启用的真实 Piston tests。 |
| WP5-a unit/integration 定向测试 | 通过 | 46 passed，0 failed。 |
| `evaluate --help` | 通过 | `PYTHONPATH=src ../../.venv/bin/python -m code_verifier.cli evaluate --help` exit 0。 |
| `third_party/open-r1/**` 不修改 | 通过 | 阶段代码通过现有 gitlink identity 使用固定 Open-R1 commit；未发现上游源码改动或直接 import。 |
| 未实现 WP5-b/WP6+ | 通过 | 无 metrics/bootstrap/SFT/GRPO 新业务实现；README 明确 formal Base 留给 WP5-b。 |

### 4. Executor 报告声明核验

| Executor 声明 | 核验状态 | 证据 |
|---|---|---|
| “计划 8 个步骤均已实现” | **与事实部分不符** | 步骤 1–4、6–7 主行为成立，但步骤 5 存在函数级计划合同偏差、CUDA/no-CUDA identity 行为偏差、缺失明确要求的 environment tests，且 resolved config 缺 run_id。 |
| fixed prompt 不含 train/eval hidden/reference/SFT | 核实通过 | generation unit sentinel + integration payload guard 均通过。 |
| frozen Transformers backend：lazy import / eval / inference / deterministic / new tokens only | 核实通过 | `generate.py` 与 fake runtime tests 一致。 |
| strict record schema 与三层 verifier evaluation | 核实通过 | 源码与 Mock tests 一致。 |
| exact-prefix resume 与 identity drift fail closed | 基本核实通过 | model/checkpoint/seed/dataset/prompt/order/corrupt/nonfinite 路径有代码与测试证据；环境 identity 本身的 no-CUDA 表示仍有 M2。 |
| environment 增加 dependency/GPU/CUDA reproducibility fields | 部分核实 | 字段存在，但 no-CUDA 语义与计划不一致，且缺少计划指定的 fallback/mocked CUDA tests。 |
| `make lint` 全绿 | 核实通过（共享 venv 命令） | 独立重跑与报告一致。 |
| `make test` 589 passed / 3 skipped | 核实通过 | 独立重跑得到完全相同计数。 |
| CLI help 可通过 module entrypoint 验收 | 核实通过 | 两个 module help 命令独立 exit 0；直接 worktree `make lint`/console-script 环境问题确实属于当前 worktree 未自带 `.venv`。 |
| 无 metrics/bootstrap、无 third-party/proceedings 越界 | 核实通过 | 代码范围与文档边界一致。 |

### 5. 问题清单

| 严重级别 | 位置 | 问题 | 依据 | 建议 |
|---|---|---|---|---|
| **主要（M1）** | `ai-work/planner/WP5-a-plan.md:593-628`；实际 `src/code_verifier/evaluation/evaluate.py:465-476,754-789,798-811` | Step 5 的函数级实施合同未按 plan 落地。计划要求 `load_evaluation_problems(config: EvaluationConfig)`、`initialize_or_resume_run(...)->tuple[Path,list[EvaluationRecord]]`、`append_evaluation_record(path, record)`；实际分别改成 `(dataset_dir, split)`、额外传入预计算 hash 并返回私有 `_RunContext`、以及 `(context, record, completed=...)`。这不是仅增加私有 helper，而是直接改了计划明确列出的目标函数签名/返回形态。 | `wp-plan-reviewer` 要求逐函数核对计划签名并将偏离标记“与计划不符”；plan 自身也明确函数级接口供 executor 实施。当前测试只验证当前实现，不能证明计划合同完成。 | 要么按 plan 恢复这三个计划函数的签名/返回合同并通过私有 helper 实现现有内部逻辑；要么在进入实现前正式修订 plan 并说明为何这些符号不属于稳定合同。当前阶段不能在 executor 完成后静默以测试通过替代计划变更审批。 |
| **主要（M2）** | `src/code_verifier/environment.py:107-120`；测试缺口 `tests/unit/test_environment.py:11-34` | 环境 identity 的 no-CUDA 合同未完整实现。代码只在 torch 缺失时返回 `(None,None,0)`；若 torch 是 CUDA build（`torch.version.cuda='12.1'`）但 `torch.cuda.is_available()==False`，仍返回 `cuda_version='12.1'`。而 plan Step 5 明确要求“无 torch / 无 CUDA 时 `cuda_version=null`、`gpu_name=null`、`gpu_count=0`”。同时计划明确要求新增 CPU/no-torch fallback 与 mocked CUDA identity tests，当前测试文件仍只有两个通用测试，未覆盖 `_gpu_identity()`。 | 独立边界探针使用 fake torch：`version.cuda='12.1'`、`cuda.is_available()=False`，实际 `_gpu_identity()` 返回 `('12.1', None, 0)`。搜索 tests 无 `_gpu_identity` 覆盖。环境 identity 又被 resume 用于 fail-closed 比较（`evaluate.py:700-714`），属于 WP5-a 可恢复/可复现核心合同。 | 当 CUDA 不可用时按 plan 返回 `cuda_version=None,gpu_name=None,gpu_count=0`；增加明确的 no-torch、torch-without-CUDA、mocked available CUDA identity 单测，并重跑 resume/environment 回归。若希望记录“torch 编译时 CUDA version”而非“可用 CUDA runtime”，则应修改字段语义和 plan，而不是继续使用当前含混值。 |
| **次要（m3）** | `src/code_verifier/evaluation/evaluate.py:596-620` | `resolved_config.yaml` 未包含 `run_id`。实现只把 `model_id` 和 `seed` 添加到 resolved mapping，`run_id` 只写入 `run.json`。 | plan Step 5 `initialize_or_resume_run()` artifact 要求明确写明 `resolved_config.yaml` 保存“最终 config + CLI model id/seed/run id”。当前 resume 因目录名/run.json 仍能工作，但 artifact 不满足计划定义。 | 在 resolved config 中加入 `run_id`，并同步 resume expected mapping；增加断言保证 `run_id/model_id/seed` 三个 CLI identity 均进入 resolved config。 |

### 6. 独立测试与边界探针

- `make lint` → **未按原命令执行成功**：worktree 内不存在 `.venv/bin/python`，实际报 `make: .venv/bin/python: No such file or directory`。这与 executor 报告记录的共享 worktree 环境限制一致。
- `PYTHONPATH=src make VENV=../../.venv lint` → **通过**：Ruff check `All checks passed!`；Ruff format `70 files already formatted`；Mypy `Success: no issues found in 70 source files`。
- `PYTHONPATH=src make VENV=../../.venv test` → **通过**：`589 passed, 3 skipped in 5.32s`；3 个 skip 均为既有真实 Piston tests。
- `PYTHONPATH=src ../../.venv/bin/python -m pytest tests/unit/evaluation/test_generate.py tests/unit/evaluation/test_evaluate.py tests/unit/evaluation/test_runner_resume.py tests/integration/test_wp5a_evaluation_pipeline.py -q` → **通过**：`46 passed in 1.76s`。
- `PYTHONPATH=src ../../.venv/bin/python -m code_verifier.cli --help` → **通过**，exit 0，命令集合包含 `evaluate`。
- `PYTHONPATH=src ../../.venv/bin/python -m code_verifier.cli evaluate --help` → **通过**，exit 0；`--model-id` / `--run-name` / `--config` required，`--seed` / `--output-dir` / `--log-level` 可用。
- M2 边界探针：mock torch 为 `version.cuda='12.1'`、`cuda.is_available()=False`，调用 `_gpu_identity()` 实际输出 `('12.1', None, 0)`，确认 no-CUDA 语义偏离计划可复现。
- 代码范围抽查：evaluation 中未发现宿主 `exec()`、未直接 import `open_r1.*`；未创建 `metrics.py` / `bootstrap.py`。

### 7. 结论

- **结论：需修改**。
- 静态检查、全量默认测试、WP5-a 定向测试、CLI、visible-only prompt、三层 verifier、逐题 JSONL、exact-prefix resume 的主路径均通过，说明实现主体质量较好。
- 但 M1 是明确的函数级计划合同偏离；M2 同时包含核心环境 identity 行为偏差和计划指定测试缺失。依据 `wp-plan-reviewer` 判定规则，计划内实现/测试与 plan 不符时不得判定通过。m3 还存在一个 artifact 合同缺口。
- 本轮**禁止合并** `feat/wp5-a`，**不更新** `proceedings.md`，**不将 WP5-a/WP5 标记完成**，不清理阶段 worktree/分支，不 push。
- 下一轮复审应逐条核验 M1、M2、m3，并再次完整运行 lint、全量测试、WP5-a 定向测试与 CLI；M2 需要重新执行 no-torch / no-CUDA / CUDA-available 三类环境 identity 边界测试。

## R2：R1 修复后复审

### 1. 复审范围与方法

- 复审基准：R1 主要问题 M1、M2 与次要问题 m3。
- 修复声明来源：`ai-work/executor/WP5-executor.md` §7 “R1 代码修复报告”。
- 复审方式：逐条阅读修复代码与新增测试；独立检查三个 Step 5 函数实际签名；重跑 lint、全量测试、WP5-a 定向 suite、CLI help；重新执行 no-torch / no-CUDA / CUDA-available 三类 GPU identity 边界探针。
- 审查期间未修改 `src/`、`tests/` 或 `third_party/open-r1/`。

### 2. 上轮问题核验

| 上轮问题 | 严重级别 | R2 状态 | 证据 |
|---|---|---|---|
| M1：Step 5 三个计划函数签名/返回合同偏离 plan | 主要 | **已修复** | `src/code_verifier/evaluation/evaluate.py:465-476` 现为 `load_evaluation_problems(config: EvaluationConfig) -> list[CodeProblem]`；`:758-795` 现为 plan 的 keyword-only 参数并返回 `tuple[Path, list[EvaluationRecord]]`；`:804-806` 现为 `append_evaluation_record(path: Path, record: EvaluationRecord) -> None`。独立 `inspect.signature()` 输出与 plan 一致。resume 内部仍通过私有 `_RunContext` 实现，不再暴露私有合同。 |
| M2：no-CUDA identity 错误且缺少环境边界测试 | 主要 | **已修复** | `src/code_verifier/environment.py:107-122` 在 torch 缺失或 `cuda.is_available()==False` 时均返回 `(None, None, 0)`，CUDA 可用时才记录版本/name/count。`tests/unit/test_environment.py:41-75` 新增 no-torch、no-CUDA、CUDA-available 三类测试。独立探针分别得到 `(None,None,0)`、`(None,None,0)`、`('12.1','Mock GPU 0',2)`。 |
| m3：`resolved_config.yaml` 缺 `run_id` | 次要 | **已修复** | `evaluate.py:596-620` 新 run 写入 `run_id/model_id/seed`；`:679-688` resume 同步严格验证；`tests/unit/evaluation/test_runner_resume.py:228-247` 直接解析 YAML 并断言三项 CLI identity。 |

### 3. 回归与计划完成度复核

- WP5-a Step 1–4、6–8 的 R1 已通过项保持通过；未发现修复影响 generation prompt、三层 verifier、逐题 record、CLI 或 payload isolation。
- Step 5 现满足计划函数级合同、resolved identity、environment identity 与 exact-prefix resume 要求。
- `src/code_verifier/evaluation/` 仍仅包含 `__init__.py`、`generate.py`、`evaluate.py`；未引入 `metrics.py`、`bootstrap.py` 或 WP6+ 功能。
- 未发现 `third_party/open-r1/**` 修改或直接 `open_r1.*` import。
- 当前 worktree 的未提交状态仅为 `ai-work/reviewer/WP5-review.md`；修复源码/测试本身没有未提交工作区改动。

### 4. 独立测试与边界探针

- 原样 `make lint`：因阶段 worktree 没有本地 `.venv/bin/python`，返回 `No such file or directory`；该环境限制与 R1/executor 已记录情况一致。
- `PYTHONPATH=src make VENV=../../.venv lint`：**通过**；Ruff check 全绿，70 files formatted，strict Mypy 0 issues。
- 原样 `make test`：同样因 worktree 无本地 `.venv` 无法启动 pytest。
- `PYTHONPATH=src make VENV=../../.venv test`：**通过**；`592 passed, 3 skipped, 0 failed`，3 个 skip 均为既有显式启用的真实 Piston tests。
- WP5-a 定向：`51 passed`，0 failed。
- `python -m code_verifier.cli --help`：exit 0。
- `python -m code_verifier.cli evaluate --help`：exit 0。
- M1 签名探针：三个公开函数实际 signature 与 plan 完全一致。
- M2 identity 探针：no-torch → `(None,None,0)`；CUDA build 但 unavailable → `(None,None,0)`；CUDA available → `('12.1','Mock GPU 0',2)`。

### 5. Executor 修复声明核验

- “M1 已恢复 Step 5 函数级合同”：**核实通过**。
- “M2 已修正 no-CUDA identity 并补齐三类测试”：**核实通过**。
- “m3 resolved config 增加 run identity”：**核实通过**。
- “修复后 lint 全绿、定向 51 passed、全仓 592 passed / 3 skipped”：**独立重跑全部核实通过**。
- “未修改 third-party/proceedings，未引入 WP5-b/WP6+”：**核实通过**。

### 6. 新问题检查

- 未发现新增阻断、主要或次要代码问题。
- 未发现 hidden-test payload 新泄漏、resume identity 放宽、测试预期迁就实现或后续 WP 越界实现。
- worktree 缺少独立 `.venv` 仍是既有开发环境布局问题；共享主环境命令可以完整运行相同 Ruff/Mypy/Pytest 验收，不归类为本轮代码缺陷。

### 7. R2 结论

- **结论：通过（WP5-a 子阶段）**。
- R1 的 M1、M2、m3 均已完整处置，且无新增阻断或主要问题；WP5-a 计划内验收项在当前可用共享虚拟环境中全部通过。
- 本结论只完成 **WP5-a**；WP5-b 的聚合指标、bootstrap、正式 Base 模型结果与 WP5 整体验收仍未实现，因此不得将 WP5 整体标记完成。
- 按 `wp-plan-reviewer` 流程，本轮通过后已提交 R2 审查报告，并以 `--no-ff` 将 `feat/wp5-a` 合并回 main；合并提交：`7e5f5dfe68c998336fa4b7122731fb72af3670a9`（`feat: complete WP5-a deterministic evaluation`）。
- 合并后继续在 main 写入并提交简洁的 WP5-a proceedings 子阶段记录，随后清理阶段 worktree/分支；不执行 push。
