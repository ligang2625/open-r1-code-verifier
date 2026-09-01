# 项目实施记录（Proceedings）

> **文件功能**
>
> 本文件用于持续记录 Open-R1 Code Verifier 项目各阶段（Work Package）的实施与验收结论，作为项目开发过程的可追溯记录。
>
> **内容与格式要求**
>
> 1. 按阶段（Work Package / 计划）分节记录；阶段边界以 `ai-work/planner/WP{n}-plan.md` 覆盖内容为准。拆分的子阶段（如 WP1-a、WP1-b）先各自分节记录，整个 WP 所有子阶段完成后由最终审查方整合为一条 WP 记录。
> 2. 每阶段记录保持简洁：阶段状态、验收结论、实施范围、完成的功能概述、相关文件、验收结论；不写入中间多次 review 与 execution 的细节（细节见 `ai-work/planner`、`ai-work/executor`、`ai-work/reviewer` 报告）。
> 3. 必须明确说明是否修改了项目原有配置。
> 4. 必须区分本项目代码变更与 `third_party/open-r1` 上游依赖变更。
> 5. 测试结果应记录实际执行的命令和最终结论，不得仅根据代码内容推断通过。
> 6. 如果存在未完成项或外部环境限制，应如实记录，不得将阶段标记为完成。
> 7. 记录由最终审查方在阶段全部通过、独立分支合并回主分支后写入，并在文件末尾追加、保留已有内容；整个 WP 整合时以一条 WP 记录替换其子阶段记录。

---

## WP0：项目脚手架

- **完成日期**：2026-08-04
- **阶段状态**：已完成
- **验收结论**：通过
- **实施范围**：仅完成 WP0 项目脚手架，未提前实现 WP1 或后续 Work Package 的业务功能。

### 1. 本阶段完成事项

WP0 已完成以下工作：

1. 建立独立的 Python 项目结构。
2. 创建 `src/code_verifier` Python 包。
3. 建立基础 CLI 入口及子命令框架。
4. 建立 Open-R1 适配层：
   - `src/code_verifier/training/open_r1_adapter.py`
5. 所有对 Open-R1 的直接访问均通过适配层进行。
6. 配置本项目与 `third_party/open-r1` 的本地 editable 安装。
7. 配置 Ruff、Mypy 和 Pytest 等代码质量与测试工具。
8. 建立 WP0 单元测试。
9. 增加环境信息采集功能。
10. 生成并保存 `environment.json`。
11. 增加 Makefile，统一安装、代码检查、测试和环境记录命令。
12. 完善 README 中的安装、验收和完整训练环境说明。
13. 检查并记录 Open-R1 submodule 的固定 commit。
14. 完成 CLI、导入、静态检查和单元测试验收。
15. 修正 Ruff 检出的 import 排序问题。

### 2. Open-R1 Submodule 状态

`third_party/open-r1` 作为只读 Git Submodule 使用。





固定 commit：

```text
1416fa0cf21595d2083b399a2a0bbddd7f6e9563

```

---

## WP1：数据 Schema 与三层测试划分

- **完成日期**：2026-08-05
- **阶段状态**：已完成
- **验收结论**：通过（依据 `ai-work/reviewer/WP1-review-r3.md` 最终轮次）
- **执行计划**：`ai-work/planner/WP1-plan.md`
- **实施范围**：完成 WP1 Data Layer（数据 Schema 与三层测试划分）；未实现 WP2 解析器、WP3 执行器或后续训练、奖励和评测功能。

### 本阶段完成的功能

- 实现 §7.1 canonical schema（不可变 `CodeProblem` / `ProblemMetadata` / `TestCase`）与严格 JSON 校验：所有受信任 JSONL 读取路径拒绝重复 key，训练记录与 canonical 视图采用类型敏感的严格等价比较（bool/int/float 不互相等价）。
- 实现确定性三层测试划分（seed + problem_id）与规范化 hash、测试/题目去重、跨 split 内容去重。
- 实现数据集级泄漏检查与 SFT / Public GRPO / Hidden GRPO 训练字段白名单视图；训练 artifact 不含 eval-hidden 内容。
- 实现 `prepare-data` / `check-data` CLI，导出 canonical JSONL、版本化 Hugging Face Dataset 与训练 artifact；提交 20 题 fixture（12 train / 4 validation / 4 test）。

### 相关文件

- 新增：`src/code_verifier/data/{schema,adapters,split_tests,deduplicate,leakage_checks,prepare,json_strict}.py`、`src/code_verifier/config.py`、`configs/data/smoke.yaml`、`tests/unit/data/*`、`tests/integration/test_wp1_data_pipeline.py`、`tests/fixtures/wp1/raw_problems.jsonl`
- 修改：`src/code_verifier/cli.py`、`tests/unit/test_cli.py`、`pyproject.toml`、`Makefile`、`.gitignore`、`README.md`、`AGENTS.md`
- 上游：`third_party/open-r1/**` 未修改；固定 commit `1416fa0cf21595d2083b399a2a0bbddd7f6e9563`。

### 配置影响

- `pyproject.toml` 新增固定运行依赖 `PyYAML==6.0.2`、`datasets==3.2.0` 与类型桩依赖 `types-PyYAML`；未修改其它项目配置。

### 验收结论

- `make lint` 全绿（Ruff check / Ruff format --check / strict Mypy，26 个源文件）。
- `make test`：135 passed。
- fresh `prepare-data` / `check-data` 返回 0，20 problems（12/4/4）；HF Dataset 解码 20 行。
- 三层测试无重复；训练 artifact 不含 eval-hidden；删除/混入字段、重复 key 隐藏与 bool/int/float 类型漂移篡改均被拒绝。

---

## WP2：代码解析器

- **完成日期**：2026-08-05
- **阶段状态**：已完成
- **验收结论**：通过（依据 `ai-work/reviewer/WP2-review.md` 最终轮次）
- **执行计划**：`ai-work/planner/WP2-plan.md`
- **实施范围**：完成 WP2 Parsing Layer；未实现 WP3 执行器、奖励、训练或评测功能。

### 本阶段完成的功能

- 实现冻结的 `ParseResult` 与确定性 `extract_python_code()`，按固定优先级提取最后一个 Python fenced block，或在无 Python block 时提取最后一个无语言标记 block。
- 支持反引号/波浪号 fence、3+ fence 长度、LF/CRLF/CR、未闭合与空 block 分类，并通过 AST 验证模块顶层同步或异步目标函数。
- 实现有限、可统计的 parser error taxonomy；NUL、Unicode、语法、内存复杂度和递归边界均返回结构化失败，不产生未处理 traceback。
- 新增 `parse-code` CLI，支持 UTF-8 文件或 stdin 输入，成功、结构化失败和 I/O 错误分别使用退出码 0、1、2，并输出机器可读 JSON。

### 相关文件

- 新增：`src/code_verifier/parsing/{__init__,code_extractor}.py`、`tests/unit/parsing/*`
- 修改：`src/code_verifier/cli.py`、`tests/unit/test_cli.py`、`README.md`、`AGENTS.md`
- 上游：`third_party/open-r1/**` 未修改；固定 commit `1416fa0cf21595d2083b399a2a0bbddd7f6e9563`。

### 配置影响

- 未修改 `pyproject.toml`、Makefile、YAML 配置或依赖版本。

### 验收结论

- 独立 worktree 与合并后的 `main` 均通过 `make lint`。
- `make test`：177 passed。
- 正常解析、NUL、lone surrogate、深层一元表达式及额外 AST 复杂度探针均符合结构化结果合同。
- 合并提交：`3f6d4415b503fd03032244ae354cbba2badbaae5`。

---

## WP3：安全执行器

- **完成日期**：2026-08-06
- **阶段状态**：已完成
- **验收结论**：通过（依据 `ai-work/reviewer/WP3-review.md` R3）
- **执行计划**：`ai-work/planner/WP3-a-plan.md`、`ai-work/planner/WP3-b-plan.md`、`ai-work/planner/WP3-c-plan.md`
- **实施范围**：完成 Execution Layer 的公共合同、非执行 Mock、本地 Piston 安全执行、资源限制、批量并发、可选 SQLite 缓存和执行 CLI；未实现 WP4 verifier/reward、训练或评测编排。

### 本 WP 完成的功能

- 建立 `CodeExecutor`、结构化执行结果、严格请求/结果校验和稳定 JSON mapping，并提供 FIFO、非执行的 `MockExecutor`。
- 实现 loopback-only `PistonExecutor` 与可信父进程/不可信候选子进程 harness，覆盖 timeout、memory、output、network、filesystem、PID、非 root、清理和结果防伪安全边界。
- 实现配置化有限并发 batch 编排，按输入顺序返回结果，每个 cache miss 使用独立 executor，并对 worker、cache 和训练缓存策略采用脱敏、fail-closed 错误处理。
- 实现包含 code/tests hash、problem/test layer、executor version、function、timeout 和 memory 的稳定 cache key，以及 0600、拒绝 symlink、版本化、损坏即失败的 SQLite cache。
- 新增 `execute-batch` CLI，支持严格 UTF-8 JSONL、配置/CLI override、原子脱敏 artifact 和退出码 0/1/2。

### 子阶段

#### 子阶段 WP3-a：公共合同与 Mock

- 完成功能：公共执行接口、严格合同校验、JSON mapping、调用记录与非执行 Mock。
- 相关文件：`src/code_verifier/execution/{__init__,base,mock}.py`、`tests/unit/execution/*`、`tests/integration/test_wp3a_mock_execution.py`。

#### 子阶段 WP3-b：本地 Piston 单请求执行与安全限制

- 完成功能：可信 harness、单测试 Piston job、资源/隔离限制、结构化状态映射和真实安全验收。
- 相关文件：`src/code_verifier/execution/{harness,piston}.py`、`configs/execution/piston-local.yaml`、`docs/piston-local.md`、`tests/integration/test_wp3b_piston_execution.py`。

#### 子阶段 WP3-c：批量并发、缓存与执行 CLI

- 完成功能：有限并发 batch、稳定 cache identity、安全 SQLite cache、training cache guard、`execute-batch` CLI 和 WP3 整体收口。
- 相关文件：`src/code_verifier/execution/{batch,cache}.py`、`configs/execution/batch-local.yaml`、`tests/unit/execution/{test_batch,test_cache}.py`、`tests/integration/test_wp3c_batch_execution.py`、`tests/fixtures/wp3c/batch_requests.jsonl`。

### 相关文件（汇总）

- 新增：`src/code_verifier/execution/{base,mock,harness,piston,batch,cache}.py`、`configs/execution/{piston-local,batch-local}.yaml`、`docs/piston-local.md`、执行层单元与集成测试。
- 修改：`src/code_verifier/execution/__init__.py`、`src/code_verifier/cli.py`、`Makefile`、`pyproject.toml`、`README.md`、`AGENTS.md`。
- 上游：`third_party/open-r1/**` 未修改；固定 commit `1416fa0cf21595d2083b399a2a0bbddd7f6e9563`。

### 配置影响

- 新增本地 Piston 与 batch execution YAML；Makefile 增加并扩展 `test-piston`；`pyproject.toml` 仅增加 `piston` pytest marker；未新增 Python package 依赖。

### 验收结论

- 合并后的 `main` 通过 `make lint`。
- `make test`：444 passed，3 个真实 Piston tests 按设计默认 skipped。
- `make test-piston PISTON_CONFIG=configs/execution/piston-local.yaml`：9 passed，0 failed，0 skipped。
- `code-verifier` 与 `execute-batch --help` 返回 0；真实 CLI smoke 处理 4 条请求并输出 2 passed / 1 wrong answer / 1 runtime error，顺序与脱敏要求通过。
- WP3 §20 的 Protocol、Mock、Piston、资源限制、批量执行与测试交付全部完成；正确、超时、网络、文件越权、输出限制、宿主隔离和结果序列化验收全部通过。
- 最终合并提交：`020af935db0b483d4bf76b03963b842f7ddce4c6`（`feat: complete WP3 batch execution and cache`）。

---

## WP4：Verifier 与 Reward

- **完成日期**：2026-08-07
- **阶段状态**：已完成
- **验收结论**：通过（依据 `ai-work/reviewer/WP4-review.md` 最终 R3）
- **执行计划**：`ai-work/planner/WP4-a-plan.md`、`ai-work/planner/WP4-b-plan.md`
- **实施范围**：完成统一 Verification Layer、Reward common、Public/Hidden reward、测试层隔离与结构化 reward component records。

### 本 WP 完成的功能

- 新增统一 `verify_completion()` 与严格 `VerificationResult` 合同，固定 parser → executor 验证路径并对 parser/executor 异常执行 fail-closed 状态归一化。
- 新增共享 `compute_code_rewards()`，Public reward 仅使用 `visible_tests`，Hidden reward 仅使用 `train_hidden_tests`，已知 eval-hidden 字段无法进入训练 reward 路径。
- 固定 reward 公式与 component record；支持 raw/Open-R1 chat completion、严格 batch 对齐、有限值校验和 JSON-safe/payload-free 分量记录。
- 正确处理 parser failure、timeout 与 sandbox/infrastructure failure，包括 Piston 多失败聚合下的 nested timeout/sandbox：基础设施失败不获得正 reward，timeout penalty 不被早先普通失败掩盖。

### 子阶段

#### 子阶段 WP4-a：统一验证器与结构化验证结果

- 完成功能：Verification Layer、结构化结果、parser-only `PARSE_ERROR` taxonomy 与 Mock 集成回归。
- 相关文件：`src/code_verifier/verification/{__init__,result_types,verifier}.py`、`tests/unit/verification/*`、`tests/integration/test_wp4a_verifier_pipeline.py`。

#### 子阶段 WP4-b：Reward Layer 与测试层隔离

- 完成功能：Reward common、Public/Hidden wrappers、component records、测试源隔离及 Piston 聚合失败语义回归。
- 相关文件：`src/code_verifier/rewards/{__init__,common,public_reward,hidden_reward}.py`、`tests/unit/rewards/*`、`tests/integration/test_wp4b_reward_pipeline.py`。

### 相关文件（汇总）

- 新增：`src/code_verifier/verification/**`、`src/code_verifier/rewards/**`、`tests/unit/verification/**`、`tests/unit/rewards/**`、`tests/integration/test_wp4a_verifier_pipeline.py`、`tests/integration/test_wp4b_reward_pipeline.py`。
- 修改：`README.md`、`AGENTS.md`。
- 上游：`third_party/open-r1/**` 未修改；固定 commit `1416fa0cf21595d2083b399a2a0bbddd7f6e9563`。

### 配置影响

- 未新增或修改 YAML、Makefile、`pyproject.toml`、CLI 参数或 Python package 依赖；未加入 WP5+ evaluation/training/GRPO 功能。

### 验收结论

- 合并后的 main 通过 `make lint`；Ruff check/format 与 strict mypy 全绿。
- `make test`：536 passed，3 个既有真实 Piston tests 按设计默认 skipped。
- WP4 Verification + Reward 联合定向测试：92 passed，0 failed，0 skipped。
- Public/Hidden 测试源隔离、batch 数量对齐、有限 reward、payload-free component records、parse/timeout/sandbox 失败状态均通过独立审查。
- WP4-a 合并提交：`5e6f590caa31631c046d3107f1d1edcf1d623c66`（`feat: complete WP4-a unified verifier`）。
- WP4 最终合并提交：`588e78e`（`feat: complete WP4 verifier and rewards`）。

---

## WP5-a：Deterministic Generation、逐题 Pass@1 与可恢复评测运行

- **完成日期**：2026-08-07
- **阶段状态**：已完成
- **验收结论**：通过（依据 `ai-work/reviewer/WP5-review.md` R2）
- **执行计划**：`ai-work/planner/WP5-a-plan.md`
- **实施范围**：完成 WP5 的第一子阶段：确定性生成、三层逐题 Pass@1、严格 JSONL 结果、run identity 与 exact-prefix resume；未实现 WP5-b 的指标聚合、bootstrap、正式 Base 模型结果，也未实现 WP6+ 训练功能。

### 本阶段完成的功能

- 实现 evaluation generation contract 与 visible-only 固定 prompt，禁止 hidden/reference/SFT 内容进入模型输入；固定 `do_sample=false`、`temperature=null`、`top_p=null`、`max_new_tokens=512`。
- 实现 frozen Transformers completion backend：lazy import、固定 model/revision、`trust_remote_code=False`、chat template、`eval()`/inference mode、固定 seed，仅解码新生成 token。
- 实现严格 `EvaluationConfig` / `EvaluationRecord`，同一 completion 依次复用 `verify_completion()` 验证 visible、train-hidden、eval-hidden，并保存结构化状态、失败计数、时延与 token 统计。
- 实现 `outputs/evaluation/{run_id}/` 标准 artifact、模型/数据/config/seed/environment identity、durable JSONL append 与 exact-prefix resume；identity 漂移、损坏、顺序/题目不匹配均 fail closed。
- 新增 `evaluate` CLI，并通过现有 Piston executor 与 deterministic generator 执行评测；配置、模型和执行基础设施错误采用脱敏退出码 2。
- 环境记录新增稳定 CUDA/GPU identity：无 torch 或 CUDA 不可用时记录 null/0，CUDA 可用时记录版本、首个 GPU 名称和数量。

### 相关文件

- 新增：`src/code_verifier/evaluation/{__init__,generate,evaluate}.py`、`configs/eval/pass1.yaml`、`tests/unit/evaluation/*`、`tests/integration/test_wp5a_evaluation_pipeline.py`、`ai-work/{planner,executor,reviewer}/WP5*`。
- 修改：`src/code_verifier/cli.py`、`src/code_verifier/environment.py`、`tests/unit/test_cli.py`、`tests/unit/test_environment.py`、`README.md`、`AGENTS.md`。
- 上游：`third_party/open-r1/**` 未修改；固定 commit `1416fa0cf21595d2083b399a2a0bbddd7f6e9563`。

### 配置影响

- 新增 `configs/eval/pass1.yaml` 作为 WP5-a deterministic pass@1 评测配置。
- 未修改 `pyproject.toml`、Makefile 或依赖版本；未新增 WP5-b metrics/bootstrap 配置。

### 验收结论

- `PYTHONPATH=src make VENV=../../.venv lint`：Ruff check、format check、strict Mypy 全部通过。
- `PYTHONPATH=src make VENV=../../.venv test`：592 passed，3 个既有真实 Piston tests 按设计默认 skipped。
- WP5-a 定向测试：51 passed，0 failed。
- `code_verifier.cli --help` 与 `code_verifier.cli evaluate --help` 均返回 0。
- no-torch、no-CUDA、CUDA-available 三类环境 identity 边界验证通过；Step 5 三个公开函数签名与计划一致。
- WP5-a 合并提交：`7e5f5dfe68c998336fa4b7122731fb72af3670a9`（`feat: complete WP5-a deterministic evaluation`）。

---

## WP5-b：聚合指标、Bootstrap 与 Base 正式验收

- **完成日期**：2026-08-09
- **阶段状态**：已完成
- **验收结论**：通过（依据 `ai-work/reviewer/WP5-b-review.md` R2）
- **执行计划**：`ai-work/planner/WP5-b-plan.md`
- **实施范围**：完成 WP5 的第二子阶段：严格评测记录读取、问题级聚合指标、Bootstrap 置信区间、summary/CSV 派生结果、immutable Base 配置与正式 Base 工程验收；未实现 WP6+ 训练功能。

### 本阶段完成的功能

- 新增严格 `EvaluationRecord` JSONL 读取与 completed-run 派生 artifact resume guard；JSONL 按物理 LF 分隔，支持 U+2028/U+2029 合法 UTF-8 记录往返。
- 新增无第三方统计依赖的问题级 deterministic bootstrap 与 paired bootstrap difference。
- 新增 parse/target/executable、错误率、三层 pass@1、平均测试通过率、public-eval gap、错误分类与 execution status 聚合指标。
- 完成 `summary.json` 与单行 `main_results.csv` 原子生成，并保持 completion/code/tests 仅存在于 `samples/results.jsonl`。
- 新增正式 Base 配置：`Qwen/Qwen2.5-Coder-1.5B-Instruct` immutable revision、CUDA、FP16、deterministic pass@1。

### 验收结论

- `make lint`：Ruff check、format check、strict Mypy 全绿。
- `make test`：660 passed，3 个真实 Piston 用例按设计显式 skipped。
- `make test-piston`：9 passed，0 failed，0 skipped。
- `make test-gpu`：3 passed，0 failed，0 skipped。
- Base smoke split：4 题；Eval-Hidden Pass@1 `0.5`，95% CI `[0.0, 1.0]`。
- 同 run resume：`generated=0`；独立 deterministic run 的逐题 correctness records 与 metrics 完全一致。
- R1-M1 修复后，严格 JSONL、全局回归、Piston、GPU 与 Base gates 均通过。
- WP5-b 合并提交：`03eb5b73f5cd6ea8bce4fae5297b96017e87a435`（`feat: complete WP5-b metrics, bootstrap, and Base acceptance`）。

### WP5 聚合状态

WP5-a 与 WP5-b 均已完成。当前 WP5 已具备确定性生成、逐题三层 Pass@1、可恢复运行、聚合指标、问题级 Bootstrap 与 Base 工程验收；Base 数值仍仅代表当前四题 smoke split 的工程基线，不是最终研究 benchmark。

---

## WP6-a：SFT 数据合同与 LoRA 训练控制面

- **完成日期**：2026-08-09
- **阶段状态**：已完成
- **验收结论**：通过（依据 `ai-work/reviewer/WP6-a-review.md` R3）
- **执行计划**：`ai-work/planner/WP6-a-plan.md`
- **实施范围**：完成 SFT visible-only 数据合同、共享 code-generation prompt、trajectory quality gate、pinned PEFT/TRL/Open-R1 runtime、LoRA 配置与硬件保护、payload-free run artifacts、`train-sft` CLI/resume 控制面及非训练集成验证；未执行真实 SFT、checkpoint reload、B 组评测或成本验收，这些 gate 保留给 WP6-b。

### 验收结论

- `make lint` 通过；`make test`：713 passed、3 个既有显式 Piston tests 按设计 skipped；GPU smoke：3 passed。
- `train-sft` 在 GTX 1660 Ti 上于模型加载前按不可下调的 20 GiB 硬件门槛 fail closed，未启动真实 SFT。
- SFT artifact、trainer/eval dataset 保持 visible-only 与 hidden/reference isolation；raw、canonical、training JSONL 均遵守 physical-LF contract，并覆盖 U+2028/U+2029 round-trip。
- pinned runtime：Open-R1 `0.1.0.dev0`、TRL `0.18.0`、Transformers `4.52.3`、Accelerate `1.4.0`、PEFT `0.14.0`。
- 上游 `third_party/open-r1/**` 未修改；WP6-b 的 24GB GPU、至少 50 条 validated SFT examples、checkpoint reload、B 组评测与成本 gate 未提前伪造通过。

---

## 环境与硬件迁移准备：GPU 开发/冒烟机适配

- **完成日期**：2026-08-07
- **阶段状态**：迁移准备（非 Work Package 阶段）
- **验收结论**：通过（CPU 机器上 lint 与默认测试全绿；真实 CUDA 冒烟需在迁移后的 1660 Ti 开发机上执行）
- **实施范围**：仅修改项目描述、构建与测试入口，为开发/冒烟迁移到 GTX 1660 Ti 机器做准备；未新增 WP 功能；SFT/GRPO 训练硬件维持 spec 原定 24GB GPU（如 RTX 4090）。

### 1. 本阶段完成事项

1. 规格说明明确硬件分工：开发、构建与 smoke test 在单张 GTX 1660 Ti（6GB VRAM，Turing/sm_75）机器上进行；SFT/GRPO 训练仍在 24GB GPU（如 RTX 4090）机器上执行。1660 Ti 冒烟使用 fp16（Turing 不支持 bf16）与 0.5B debug 模型，不执行训练。
2. 默认测试套件自动适配 CPU/GPU：无 GPU 机器只运行 CPU 测试，GPU 必需测试自动跳过并明确提示需要 GPU；有 CUDA 的机器（1660 Ti 开发机）`make test` 自动运行完整套件（含 GPU 冒烟）；`make test-gpu` 用于单独运行 GPU 冒烟子集。
3. README/AGENTS 增加硬件分工、GPU 机器安装（`make install-full`）、`record-environment` 记录 CUDA/GPU identity 与 `make test-gpu` 说明。
4. 新增自动检测的 GPU 冒烟测试（`tests/integration/test_wp5a_gpu_smoke.py`，`pytest.mark.gpu`）：无 CUDA 机器自动跳过并输出明确提示（需要 GPU 与 `make install-full`），GPU 机器上自动运行；验证环境 identity 记录 CUDA/GPU，并以 `device: cuda` 跑一次冻结 pass@1 小模型生成。
5. Makefile 新增 `test-gpu`；`pyproject.toml` 注册 `gpu` marker。

### 2. 相关文件

- 修改：`PROJECT_SPEC_Open-R1_CodeVerifier.md`、`README.md`、`AGENTS.md`、`Makefile`、`pyproject.toml`、`proceedings.md`
- 新增：`tests/integration/test_wp5a_gpu_smoke.py`
- 上游：`third_party/open-r1/**` 未修改；固定 commit `1416fa0cf21595d2083b399a2a0bbddd7f6e9563`。

### 3. 配置影响

- `pyproject.toml` 仅新增 `gpu` pytest marker；Makefile 仅新增 `test-gpu` target；未修改依赖版本或实验配置。

### 4. 验收结论

- `make lint` 全绿。
- `make test`：592 passed，5 skipped（3 个 Piston 显式跳过 + 2 个 GPU 用例自动跳过，均明确提示需要 GPU）。
- 当前机器无 CUDA：`make test-gpu` 报告 2 skipped（自动跳过并提示需要 GPU），退出码 0，符合设计。
- 迁移后的 1660 Ti 开发机需执行：`make install-full` → `record-environment`（确认 `cuda_version`/`gpu_name`/`gpu_count`）→ `make test-piston`（若继续使用本地 Piston）→ `make test`（GPU 冒烟自动包含，0 failed、0 skipped），也可单独运行 `make test-gpu`。训练阶段回到 24GB GPU（如 RTX 4090）机器进行。

---

## 环境维护：迁移后 GTX 1660 Ti GPU 环境实际验收（最终收口）

- **完成日期**：2026-08-08
- **阶段状态**：环境维护（非 Work Package 阶段）
- **验收结论**：通过（真实 GPU 验收在 GTX 1660 Ti 开发机上完成）
- **实施范围**：仅收口已确认的环境遗漏，并完成最后一轮审查修复（`dtype=auto` 向后兼容、`pass1.yaml` 明确 fp16、离线缓存 GPU smoke）；未新增 WP 功能；未升级固定 Open-R1 dependency stack；未修改 `third_party/open-r1/**`；未安装系统 CUDA Toolkit。

### 1. 实际环境 identity

```text
GPU: NVIDIA GeForce GTX 1660 Ti
VRAM: 6144 MiB（6GB）
compute capability: 7.5（sm_75 / Turing）
torch: 2.6.0+cu124
torch CUDA: 12.4
native BF16: false（torch.cuda.is_bf16_supported(including_emulation=False)）
```

说明：PyTorch 2.6 默认 `is_bf16_supported()` 在 Turing 上因软件/模拟 BF16 tensor 返回 True，这不等于原生硬件支持；`environment.json` 的 `bf16_supported` 现改为仅记录 native/hardware 支持（`including_emulation=False`），在 GTX 1660 Ti 上记录 `false`。本地 GPU smoke 明确使用 fp16 加载 0.5B debug 模型并断言实际 dtype。

### 2. 本阶段完成事项

1. `make install-gpu` 已落地（`uv sync --extra dev --extra gpu`，torch==2.6.0 来自 PyTorch cu124 index）；`make install-full` 为其 alias，语义一致。
2. `GenerationConfig` 新增 `dtype`（auto / float16 / bfloat16 / float32）：`dtype=auto` 保持旧行为（**不**向 `from_pretrained` 传 `torch_dtype`，与修复前等价），仅 `float16`/`bfloat16`/`float32` 显式传 `torch_dtype`。
3. `configs/eval/pass1.yaml` 使用 `generation.dtype: float16`（符合 §5.2 的 1660 Ti debug 评测规格：6GB / fp16 / 0.5B）；GPU smoke 显式 `dtype: float16` 并通过公开属性 `generator.model_dtype` 断言模型真实以 FP16 加载。
4. GPU smoke 模型加载使用 `local_files_only=True`（离线缓存契约）：模型已缓存且网络不可达时不再因 Hugging Face retry 长时间阻塞；模型未缓存时快速失败并明确提示先下载/缓存。普通 `code-verifier evaluate` 仍默认允许联网下载模型。
5. 新增极小 CUDA autograd smoke（256×256 tensor，forward+backward，真实 CUDA 执行、不加载模型、不 mock）。
6. `environment.json` 的 `bf16_supported` 语义修正为 native-only（`including_emulation=False`），并补充 7.5/原生 BF16 false 的 fake-runtime 单元测试；`bf16_supported=false` 保持。
7. README/AGENTS 明确 `make install-gpu` 是“当前 Open-R1 inference/GPU dependency stack”，不是 training stack 验收。

### 3. 真实验收结果（GTX 1660 Ti）

- `make lint`：PASS（ruff check / ruff format / strict mypy 全绿）。
- `make test`（GPU 可见）：606 passed，3 skipped，0 failed（仅真实 Piston 用例显式跳过）。GPU 冒烟真实执行（非 skip）。
- `make test-gpu`：3 passed（CUDA identity、Qwen 0.5B fp16 CUDA 生成、CUDA autograd forward/backward）；模型已缓存且网络不可用时不再发生 Hugging Face 网络重试。
- Qwen/Qwen2.5-Coder-0.5B-Instruct CUDA inference：PASS，模型实际 dtype 为 FP16。
- CUDA autograd：PASS（`x.grad is not None`，device=cuda）。
- `make test-piston`：9 passed，0 failed，0 skipped（本地 loopback Piston 服务已部署，Python 3.10.0 runtime）。
- `make record-environment`：environment.json 已重生成，包含 cuda_version=12.4、gpu_name、gpu_count=1、compute_capability=7.5、bf16_supported=false、uv.lock hash。
- `make lint` 与全部单元/集成测试均在最终轮修复后重跑；`dtype=auto` 单元测试验证 `torch_dtype` 不再传入，`dtype=float16/bfloat16/float32` 验证显式传入。

### 4. 能力边界

- 1660 Ti 验收覆盖：CUDA runtime、fp16 inference、CUDA autograd、Qwen 0.5B 生成。
- 1660 Ti 验收不覆盖：LoRA/SFT、GRPO、PEFT training、DeepSpeed training、最终 BF16 training —— 全部留给 RTX 4090 训练机重新做 GPU training integration acceptance。
- PEFT 当前未进入 inference 环境（`peft=null`），在 SFT/LoRA WP 前必须正式引入并固定。
- DeepSpeed 已随固定 Open-R1 栈安装，但其 GPU training 集成未在 1660 Ti 上验证，也不作为本机 acceptance 项；不因此安装系统 CUDA Toolkit。

### 5. 配置影响与文件

- 修改：`pyproject.toml`（gpu extra）、`uv.lock`（新增）、`Makefile`（install-gpu）、`src/code_verifier/environment.py`、`src/code_verifier/evaluation/generate.py`（dtype=auto 兼容 + local_files_only）、`src/code_verifier/evaluation/evaluate.py`、`configs/eval/pass1.yaml`（dtype: float16）、`tests/unit/test_environment.py`、`tests/unit/evaluation/test_generate.py`、`tests/unit/evaluation/test_evaluate.py`、`tests/integration/test_wp5a_gpu_smoke.py`（local_files_only）、`README.md`、`AGENTS.md`、`environment.json`、`proceedings.md`
- 上游：`third_party/open-r1/**` 未修改；固定 commit `1416fa0cf21595d2083b399a2a0bbddd7f6e9563`。

---

## 开发流程规范调整：1660 Ti development-first / 4090 final validation

- **决定日期**：2026-08-13
- **性质**：项目级流程/验收规范调整，不是新的功能 Work Package
- **原因**：原先 WP6-b 把 checkpoint/evaluation 开发工作与“>=50 真实 SFT 数据 + 24GB GPU + 真实训练/数值验收”绑定在同一个 execution completion gate。实际执行证明前半部分代码能够在 GTX 1660 Ti 上完成并通过工程测试，但 stage 会因为最终训练 prerequisites 缺失而无法产生 completed E0，从而错误阻塞后续 WP7/WP8 的可独立代码开发。

### 新流程

1. **Development track（GTX 1660 Ti）**：先完成所有 dependency-ready 的生产代码，包括 SFT/GRPO adapter 与 control plane、checkpoint/resume、统一评测接入、aggregation/reporting/error-analysis tooling；使用 unit/integration、真实 Piston、小模型 FP16 GPU smoke 和严格 fixture/mock/synthetic evidence 验证代码可行性。开发阶段不执行 optimizer-based SFT/GRPO。
2. **Development-complete gate**：开发代码、配置、CLI、artifact schema 与测试全部完成，`make lint` / `make test` / 适用的 `make test-piston` / `make test-gpu` 全绿，训练入口在 1660 Ti 上按硬件 guard 正确 fail closed。缺少 24GB GPU、正式规模数据或真实 checkpoint 不属于 development blocker。
3. **Validation track（RTX 4090 / 24GB）**：开发完成后集中执行真实 Base A 数值、SFT B 训练/重载/评测、Public/Hidden GRPO C/D 训练/重载/评测，以及最终 A–D 聚合、成本和错误分析。synthetic/mock 不得替代任何真实训练或 numerical gate。
4. 4090 真实运行若暴露实现 bug，返回正常 development/repair 流程修复并重新通过开发机测试，再重跑受影响的 validation；不边训练边扩展功能或改变实验定义。

### 对原 WP6-b blocked stage 的处理

- 旧 `feat/wp6-b` 在 blocked execution 中已产生开发 commit：`c214d57`（SFT checkpoint identity）、`dc86e1f`（PEFT reload）、`44c262f`（SFT evaluate 接入）、`e8b2257`（文档/工程验证），随后 `eacfd31` 记录 blocked execution；没有 completed E0、没有 review/finalize、没有真实 SFT/checkpoint/B 数值。
- 为避免旧 validation-heavy plan 继续触发 active-stage guard，原 branch/worktree 已退役；完整历史保存在 `archive/wp6-b-blocked-20260810`。该 archive 只是可审计/可复用的开发历史，**不代表这些代码已经被 main 接受**。
- 后续 planner 应按新规则先规划 development stage。可以在独立 plan/review 下选择性复用上述 archive commit 的实现思路或 diff，但必须重新以当前 main/spec 为基线验收；不得把旧 blocked report 当作 completed execution。
- 后续 planner 不得再因为 WP6 的 24GB/真实数据 gate 未完成而直接停在 validation；只要仍有 development deliverable 未完成，应继续规划 development track。validation 解锁条件以后续记录定义的严格 machine-readable completion block 为准。

---

## 开发流程加固：closeout、incomplete recovery、persistent artifacts 与 validation preflight

- **决定日期**：2026-08-13
- **性质**：项目级 workflow hardening；细化上一条 development-first 决策，不改变研究问题、A–D 实验定义或指标口径
- **基线**：`7c12c943ef1dc27871eb8364e80dc0c7db2a8505`
- **适用范围**：后续所有新 stage；本记录中的新状态/marker 语义覆盖上一条记录中笼统的 `development-complete` 表述

### 解决的五个常见流程问题

1. **Development Complete 生成机制（旧说明，已由后续规则收紧）**：最后一个 development stage 必须通过完整 closeout；validation 只能由 lifecycle finalize 写入的严格 machine-readable completion block 解锁。本文这样的自然语言说明本身不是 completion marker。
2. **Incomplete execution 恢复**：每个 plan 增加首次业务修改/commit 前的 `Execution preflight`，提前检查可判定的 Piston/import/model-cache/CUDA 等 prerequisites。若仍在后续形成“已有部分 commit、无 completed E0/review”的 `INCOMPLETE` stage，使用显式 `stage-lifecycle retire_incomplete` 原样 archive branch、记录 retirement，再重新 planner；不自动重跑、不手工丢历史。
3. **真实 artifact 持久化**：validation 的 checkpoint/metrics/results 必须位于 stage worktree 外。`execution-router` 将 `CODE_VERIFIER_ARTIFACT_ROOT` 解析为绝对持久目录；未设置时默认 primary checkout 的 `outputs/`。`evaluate` / `train-sft` 的默认输出已支持该环境变量，后续 `train-grpo` 必须沿用同一合同。
4. **开发机依赖与训练行为分离**：GTX 1660 Ti 允许并推荐 `make install-train`，用于真实 pinned PEFT/TRL/Transformers/Accelerate API/import/integration 开发；这不授权 optimizer-based SFT/GRPO，训练仍由 validation profile 与运行时显存 guard 禁止在 1660 Ti 上启动。
5. **Validation dispatch 硬件 preflight**：router 使用项目 pinned PyTorch 的 CUDA runtime（而非强依赖 `nvidia-smi`）读取 GPU identity/total memory；可见显存低于 `22528 MiB`（22 GiB）时在 dispatch 前拒绝 validation。训练入口原有 `>=20 GiB` guard 保留为第二层保护；同时 router 验证 persistent artifact root 可写且不在 stage worktree 内。

### 本次工程验证

- `.venv/bin/python -m pytest tests/unit/test_cli.py -q`：47 passed。
- `make lint`：Ruff check / format / mypy strict 全部通过。
- `make test`：714 passed、3 skipped；3 个 skip 均为需要显式启用的 real Piston tests。
- `make test-gpu`：3 passed，真实 CUDA generation smoke 在 GTX 1660 Ti 上通过。
- 训练依赖导入：PEFT `0.14.0`、TRL `0.18.0`、Transformers `4.52.3`、Accelerate `1.4.0`、torch `2.6.0+cu124` 全部成功。
- PyTorch GPU 探测：`NVIDIA GeForce GTX 1660 Ti`，总显存约 `6143 MiB`；因此该开发机应被 validation router 正确拒绝，但仍可执行开发/GPU smoke。
- 当前 shell 无 `nvidia-smi` 命令，但 PyTorch CUDA 可正常工作，因此 router 的硬件真值改为 pinned PyTorch runtime；`nvidia-smi` 仅作为可选审计信息。
- 本次 workflow hardening **未运行 real `make test-piston`**；这不是本次规范变更的完成条件。真实 Piston 0 failed/0 skipped 被明确保留为 terminal development closeout 的强制 gate，不能由当前默认测试 skip 冒充。

---

## 流程加固：严格 completion marker、一次性 4090 交接、全量 inventory 与 zero-code closeout

- **决定日期**：2026-08-13
- **性质**：针对上一轮独立审查的四项 common-case 修复；不改变研究实验定义
- **基线**：`48303412709bc99ddb13e87df847c6b990f1baac`

### 新规则

1. **Completion marker 防假阳性**：自然语言中出现 Development Complete 相关词句不再具有状态语义。只有 terminal PASS stage 的 `stage-lifecycle finalize` 才能在 proceedings 写精确标题加紧随 YAML 的 machine-readable completion block；validation planner/bootstrap 必须严格解析该结构，当前本文档中的流程说明不构成 marker。
2. **一次性 1660 Ti → 4090 交接**：terminal finalize 的 finalization docs commit 成功后，把当前 `main HEAD` 作为 `development_complete_commit` 报告。1660 Ti 到此停止；用户只需把这个 exact main commit 通过正常 Git 同步到 4090，安装 pinned training environment，再从 4090 重新运行 planner-ex。validation plan/worktree 不从 1660 Ti 搬运，此后完整 validation track 都留在 4090。
3. **Terminal 全量 inventory**：`development_terminal=true` 不再由“没有 dependency-ready 工作”决定。terminal plan 必须以 Development Completion Inventory 逐项覆盖 WP0–WP8；每项需有 finalized evidence 或由本 stage 明确完成。`DEV-CLOSEOUT` 只有在九项 development deliverables 都已经 finalized 时才合法，不能用于补开发缺口。
4. **Zero-code DEV-CLOSEOUT**：`DEV-CLOSEOUT` 固定 SINGLE、verification-only。它不得为了产生 commit 修改业务代码/测试/config；closeout gates 全部通过时，允许 `result_code_commit == plan_commit`，然后只追加并提交 completed E0 execution report。reviewer 必须把“无业务 diff”视为该 stage 的合法预期状态。

### 当前状态

- 本记录只是 workflow 决策说明，**不是**项目开发完成证明。
- 当前尚未产生 terminal development finalize 写出的 machine-readable completion block，因此 validation 仍保持锁定。
- 上一轮独立审查实际执行 `make test-piston` 时本地 Piston service 不可达；在真实 terminal closeout 前必须先恢复 Piston 并取得 0 failed / 0 skipped。

## Incomplete Stage Retirement Record

- stage_id: `WP6-c`
- plan_commit: `fb14c8c0f5e534aff9838eb3b9e9d06f3dc58eae`
- archived_head: `9b4fa5fa9d781a4f869b107ead1489e4f043bad6`
- archive_branch: `archive/wp6-c-incomplete-20260813-192343`
- reason: `ruff` 缺失导致总验收失败
- retired_at: `2026-08-13T19:23:43+08:00`
- stage 没有 completed E0，也没有 review；上述提交未被 `main` 接受。

---

## WP6-c：SFT checkpoint 重载与 B 组统一评测开发

- **完成日期**：2026-08-14
- **阶段状态**：已完成
- **验收结论**：通过（依据 `ai-work/reviewer/WP6-c-review.md` R2）
- **执行计划**：`ai-work/planner/WP6-c-plan.md`
- **实施范围**：完成 strict completed-SFT checkpoint identity、pinned PEFT inference reload、`evaluate --sft-run-dir` 显式 B 组入口、与 Base 共用 evaluator/aggregator 的 evaluation/resume contract，以及 fixture/fake runtime 工程验证；本 stage 未执行 optimizer-based SFT、未产生真实 B checkpoint/数值/成本。

### 验收结论

- completed SFT run 仅在 `status=completed`、artifact layout/identity/adapter 完整且 checkpoint 直接属于同一 run 时可加载；checkpoint identity 不携带训练 payload。
- B 组通过现有 `run_pass1_evaluation()` 与 `aggregate_evaluation_run()`，并把 completed run 的 model revision 与实际 adapter checkpoint 路径纳入现有 evaluation identity / exact-prefix resume；Base 与 B 未复制 evaluator、aggregator 或结果 schema。
- pinned TRL `0.18.0` / PEFT `0.14.0` 的真实语义已纳入合同：adapter config 可合法保持 `revision=None`，此时 completed run 的 non-null `model_revision` 继续作为 base tokenizer/model loading 的真值；若 adapter 显式携带 revision，则 mismatch 仍 fail closed；`base_model_name_or_path` 始终严格匹配。
- prompt 与非-sample artifact 继续保持 hidden/reference/SFT-response payload boundary；fixture checkpoint 明确仅为 engineering evidence，不冒充正式 B evidence。
- R2 独立验收：WP6-c focused suite `125 passed`；`make lint` 全绿；`make test`：737 passed、3 个既有显式 real-Piston opt-in tests skipped；`make test-gpu`：3 passed（GTX 1660 Ti）。
- `third_party/open-r1/**`、`pyproject.toml`、`uv.lock` 未修改；没有依赖升级或真实训练。
- WP6-c merge commit：`2f57e67911850861f73e247c09bc0a87612210d1`。

### WP6 development 聚合状态

WP6-a 与 WP6-c 已覆盖当前 development track 的 SFT 数据/训练控制面、completed checkpoint identity、PEFT reload 与统一 B 组评测接入。真实 SFT optimizer run、正式 B checkpoint/数值/成本仍属于后续 24GB validation track，不能由本 development stage 视为完成。当前 stage 的 `development_terminal=false`，因此本次 finalize **不会**写 `Development Complete Record`；项目仍需继续完成 WP7/WP8 development 与 terminal closeout 后才能解锁 validation。

---

## WP7-a：GRPO control-plane 与奖励日志开发

- **完成日期**：2026-08-14
- **阶段状态**：已完成
- **验收结论**：通过（依据 `ai-work/reviewer/WP7-a-review.md` R1）
- **执行计划**：`ai-work/planner/WP7-a-plan.md`
- **实施范围**：完成 Public/Hidden GRPO 的共享 prompt 与 payload-minimal dataset、exact config 与 C/D fairness guard、pinned TRL reward callback、sanitized rollout/reward/group artifacts、completed B → merged policy → new GRPO LoRA 的 runtime construction、strict run/resume identity、20 GiB hardware guard 与 paired `train-grpo` CLI；本 stage 仅提供 engineering evidence，不执行 optimizer-based GRPO，也不产生正式 C/D checkpoint、研究数值或成本。

### 验收结论

- Public/Hidden trainer dataset 共用 §7.2 prompt；Public 仅携带 visible reward payload，Hidden 仅额外携带 `train_hidden_tests`，`eval_hidden_tests`、reference solution、starter code 与 SFT response 均被训练路径和日志边界拒绝。
- C/D production preflight 在创建 selected run 或加载 trainer runtime 前同时验证两份 config、两份 completed-SFT B definition 与 ordered artifact pair；config drift、不同 B identity 或 artifact drift 均 fail closed。
- pinned TRL `0.18.0` / PEFT `0.14.0` 路径严格执行 `base A → load completed B adapter read-only → safe merge B → new GRPO LoRA`，避免 reference policy 回退到 A；`num_generations` cross-field 约束与 pinned constructor error normalization 已纳入项目边界。
- reward callback 继续复用 `compute_code_rewards()` / verifier / configured CodeExecutor，并产出可复算且不泄漏测试 payload 的 rollout、reward 与 group metrics artifacts。
- strict resume 绑定 parent B、dataset/config、dependency/environment、seed、reward mode 与同一 run 下的 `checkpoint-N`；GTX 1660 Ti 在 model load 前因 20 GiB gate 正确 fail closed。
- R1 独立验收：WP7-a focused suite `117 passed`；recovered-contract 定向检查 `7 passed`；`make lint` 全绿；`make test`：803 passed、3 个既有显式 real-Piston opt-in tests skipped；`make test-gpu`：3 passed；real loopback Piston validation 返回 `3.10.0`。
- `third_party/open-r1/**`、`pyproject.toml`、`uv.lock` 未修改；没有依赖升级或真实 GRPO 训练。
- WP7-a merge commit：`fee3cd3c883418ee2028519f41505db099c34145`。

### WP7 development 状态

WP7-a 已完成当前 development track 的 GRPO control-plane、reward wiring、artifact/resume 与 C/D fairness 工程合同。completed C/D checkpoint identity、从 merged B + C/D adapter 的独立 reload、统一 C/D evaluation/aggregation 接入等后续 WP7 development 工作仍未完成；真实 C/D optimizer run、正式 checkpoint/数值/成本继续属于 24GB validation track。当前 stage 的 `development_terminal=false`，因此本次 finalize **不会**写 `Development Complete Record`。

---

## WP7-b：GRPO checkpoint 重载与 C/D 统一评测开发

- **完成日期**：2026-08-14
- **阶段状态**：已完成
- **验收结论**：通过（依据 `ai-work/reviewer/WP7-b-review.md` R1）
- **执行计划**：`ai-work/planner/WP7-b-plan.md`
- **实施范围**：完成 strict completed-GRPO checkpoint identity、parent completed-SFT B 重新验证与强绑定、`base A → B read-only → safe merge → C/D read-only` 的独立 inference reload、`evaluate --grpo-run-dir` 显式 C/D 入口、与 A/B 共用 deterministic evaluator/aggregator 的 exact-resume contract，以及 fixture/fake runtime 工程验证；本 stage 未执行 optimizer-based GRPO、未产生正式 C/D checkpoint、研究数值或成本。

### 验收结论

- completed GRPO run 仅在 `status=completed`、strict artifact layout、final adapter artifact、GRPO identity 与 parent B identity 全部有效时可加载；parent B 必须重新通过 `load_completed_sft_checkpoint()` 验证，并与 GRPO run 中记录的 parent metadata 逐字段一致。
- C/D inference 严格重建为 `base A → attach completed B read-only → merge_and_unload(safe_merge=True) → attach C/D read-only`；不会把 C/D 直接挂到 A，也不会保留 B 作为 active PEFT adapter。
- C/D evaluation 继续复用 `run_pass1_evaluation()` 与 `aggregate_evaluation_run()`；`EvaluationConfig.checkpoint` 的 canonical identity 同时绑定 C/D run/checkpoint 与 parent B identity，切换 C/D、parent B、data/config/seed 后 exact-prefix resume 均 fail closed。
- prompt 与 non-sample artifacts 继续保持 hidden/reference/starter/SFT-response payload boundary；Public/Hidden fixture 仅作为 engineering evidence，不冒充正式 C/D checkpoint、metric、loss 或 cost。
- R1 独立验收：WP7-b focused suite `160 passed`；`make lint` 全绿；`make test`：833 passed、3 个既有显式 real-Piston opt-in tests skipped；`make test-gpu`：3 passed；real loopback Piston validation 返回 `3.10.0`。
- `third_party/open-r1/**`、`pyproject.toml`、`uv.lock` 未修改；没有依赖升级、实验定义变化或真实 GRPO 训练。
- WP7-b merge commit：`adc0490f72d28e78b87f7cde9ae6bcb62e3d589e`。

### WP7 development 聚合状态

WP7-a 与 WP7-b 已覆盖当前 development track 的 GRPO control-plane/reward/artifact/resume/fairness，以及 completed C/D checkpoint identity、parent B binding、stacked inference reload 与统一 C/D evaluation/aggregation 接入。真实 C/D optimizer run、正式 checkpoint/研究数值/成本仍属于 Development Complete Record 之后的 24GB validation track，不能由本 development stage 视为完成。WP8 development 仍未完成；本 stage 的 `development_terminal=false`，因此本次 finalize **不会**写 `Development Complete Record`。

---

## WP8：实验聚合、错误分析与 development closeout

- **完成日期**：2026-08-14
- **阶段状态**：已完成
- **验收结论**：通过（依据 `ai-work/reviewer/WP8-review.md` R2）
- **执行计划**：`ai-work/planner/WP8-plan.md`
- **实施范围**：完成 project-owned reward/SFT scalar logging、严格 A–D analysis manifest/source identity/provenance 校验、problem-level paired comparison/bootstrap、failure candidate 与人工标注数据合同、training-curve/cost 汇总、原子化 report artifacts、`analyze-results` CLI 与 deterministic synthetic integration fixture，并执行 terminal development closeout；本 stage 未运行真实 SFT/GRPO optimizer，也未产生或宣称正式 A–D 研究数值、真实成本结论或人工案例结论。

### 验收结论

- R2 独立验收确认 R1 的 5 个 analysis contract 问题全部修复：resolved evaluation definition 重新绑定 canonical `config_hash`，A–D source provenance 写入 derived report，large public→eval gap candidate 被覆盖，train-hidden-specific reason 仅属于 Hidden-RLVR，fixture 输出显式标记为 synthetic engineering evidence。
- WP8 focused gate：`227 passed`；`make lint` 全绿；`make test`：`881 passed`、3 个显式 real-Piston opt-in tests 按设计 skipped；`make test-gpu`：`3 passed`、0 skipped；`make test-piston`：`9 passed`、0 skipped。
- production critical path 未发现 `TODO`、`FIXME`、`NotImplementedError`、`stub` 或 `fake` implementation；`pyproject.toml`、`uv.lock` 与 `third_party/open-r1` gitlink 未改变。
- WP0–WP8 Development Completion Inventory 已由 R2 独立核验完整满足；真实 SFT/GRPO、正式 B/C/D checkpoints、最终 A–D 数值与成本/人工分析继续严格属于 24GB validation track。
- WP8 merge commit：`b1d3eb45a60dc5462dc45e25c7bcf50b4e1d9c1a`。

### Development track 聚合状态

WP0–WP8 的 development track 已全部完成并通过当前工程验收。GTX 1660 Ti 上的开发到此结束；后续 validation 必须以本次 finalization 后的精确 `development_complete_commit` 为基线迁移到 24GB-class GPU，重新安装 pinned training environment，并重新运行 planner-ex 规划 validation stage。不得在当前 1660 Ti checkout 上直接 bootstrap validation。

## Development Complete Record
```yaml
development_complete_record:
  version: 1
  terminal_stage_id: WP8
  review_commit: 9003c953bbce2fcda7aefa535883ba22fbbe01d0
  merge_commit: b1d3eb45a60dc5462dc45e25c7bcf50b4e1d9c1a
  finalized_at: "2026-08-14T20:07:35+08:00"
  completion_inventory_verified: true
  development_complete: true
```

## Post-development migration infrastructure amendment（2026-08-16）

4090 算力平台实机确认其 Ubuntu 22.04 环境为普通非特权 Docker 容器：PID 1 为 `docker-init`，无宿主 Docker socket，且不能依赖 `systemd`/nested privileged Docker。为避免因为 GPU 平台拓扑重做 WP3–WP8，正式迁移基础设施调整为：

- RTX 4090 节点允许使用普通非特权 GPU 容器；该节点不要求 Docker daemon、Docker socket、`systemd`、`--privileged` 或本地 Piston container；
- 固定 Piston image/runtime 改在独立 CPU Linux 主机/VM 上运行，该主机继续承担 Docker/cgroup/特权容器安全边界；
- Piston API 在 Piston 主机上仍仅绑定 `127.0.0.1:2000`，4090 容器通过 SSH local forward 将其映射为本机 `127.0.0.1:2000`；项目 YAML 与 `PistonExecutor` 的 strict loopback contract 不变；
- 禁止把 Piston 公网/LAN 地址直接写入配置，也禁止因 4090 容器缺少 Docker 而回退到宿主 Python `exec`/`eval`/无约束 `subprocess`；
- 4090 validation bootstrap 必须在 tunnel 建立后验证 exact Python `3.10.0`，并从 4090 容器通过 tunnel 完整运行真实 `make test-piston`，要求 0 failed / 0 skipped；
- tunneled deployment 的机器级 provenance 需要在 persistent artifact root 记录 `piston-runtime-identity.json`，至少包含 deployment mode、loopback endpoint、固定 Piston source/image identity、Python runtime、非敏感 Piston host id 与 real-Piston acceptance 结果；
- 该调整不改变 `CodeExecutor` 接口、Piston request/response 语义、executor version/hash、SFT/GRPO/evaluation 业务流程或 formal dataset/model identity，因此无需重做 WP3–WP8 development；但旧的 4090 migration manifest/bootstrap 若仍 pin 原 handoff commit 或假设 4090 本机 Docker，必须在正式传输前按本 amendment 重新生成/同步，不能直接作为新的 authoritative bootstrap 使用。

## Validation machine-state hardening amendment（2026-08-16）

第二轮迁移审查发现：仅在 `bootstrap-4090.sh` 子进程内 `export CODE_VERIFIER_ARTIFACT_ROOT/HF_HOME` 不能保证新 shell、Local Codex 或已运行的 Web/CodexPro connector 继续继承相同路径；若 router 退回 primary repo `outputs/`，会破坏 persistent validation artifact contract。为此进一步收紧为：

- 成功的 4090 bootstrap 必须在 restored primary repo 写 gitignored `.ai-bridge/validation-machine.json`，记录 absolute `artifact_root`、`hf_home`、`formal_data_root`、READY/Piston identity record 路径以及 bootstrap commit/host identity；
- `stage-lifecycle bootstrap_plan` 对 validation 在创建 branch/worktree 前必须验证该 machine record、persistent READY/Piston identity、bootstrap baseline 为当前 `main` 祖先以及 >=22528 MiB GPU；缺失或不一致 fail closed；
- `execution-router` 每次 validation dispatch 重新读取同一 machine record，不再对 formal validation 静默回退 repo-local `outputs/`，并把 `artifact_root/hf_home/formal_data_root` 传给 executor；
- validation executor 对真实命令显式设置 `CODE_VERIFIER_ARTIFACT_ROOT`、`HF_HOME`、`CODE_VERIFIER_DATA_ROOT`，因此 Web/Local workflow 不依赖调用进程是否继承用户 shell 的 export；
- `.ai-bridge/validation-machine.json` 仍是 ignored machine-local runtime state，不是 stage provenance，不得 tracked/staged/commit；正式 stage provenance 仍只在 `ai-work/`；
- 该 hardening 只修改迁移/workflow 控制面，不改变训练、评测、数据、模型、Piston executor/result semantics，因此同样无需重做 WP3–WP8。

## Validation operator-terminal execution amendment（2026-08-17）

4090 validation 已进入正式长任务阶段。为避免 Base 全量评测、SFT/GRPO optimizer run、B/C/D 全量评测等任务依赖 Web GPT/CodexPro 或 Local Codex 的长时间 tool call，后续 validation workflow 固定采用 operator-terminal checkpoint：

- planner 对预计长时间占用 GPU/Piston 的正式命令写 `operator_terminal_execution` gate；短时 preflight、lint/test、GPU/Piston smoke 继续由 executor 自动执行；
- executor 先完成并提交 gate 前所需的代码/config/test，随后在 persistent `artifact_root` 生成无密钥、包含固定 machine roots 与 exact command 的 `run.sh`，并将 script path/SHA256/status/log/expected artifacts 写入 append-only `execution_checkpoint`；
- operator checkpoint 使用 `interruption_class=operator`、`resume_allowed=true`、`status=awaiting_operator`。它是有意的人机交接，不是环境故障；若 gate 前无 tracked 修改，允许 `result_code_commit` 仍等于 plan/review baseline；
- 用户在普通终端（可用 tmux）运行 exact script，完成或失败后显式调用 `$execution-router resume`。resume 必须读取 persistent 状态/日志并重新核验真实 checkpoint/results/metrics；只有所有 stage acceptance 通过后才能写 completed E0；
- 若运行失败需要 tracked 代码/config 修复，executor 在同一 stage execution/repair 中最小修复并 commit，然后生成下一 operator checkpoint/script 让用户重跑；若只是外部环境问题且无需 tracked 修改，修好环境后可继续使用当前 checkpoint；
- 该变更只改变长任务的执行控制面，不改变 A–D 数据、模型、seed、训练预算、Piston 安全边界、metric 定义或 real-training/numerical evidence 标准。

### Operator-terminal robustness hardening（2026-08-17）

独立复核长时间任务恢复链路后进一步收紧：

- 每个 operator gate 增加 `restart_policy=exact_rerun|trainer_checkpoint`；SFT/GRPO 固定为 `trainer_checkpoint`，同一 immutable script 在再次运行时必须自动选择 latest valid same-run `checkpoint-*` 并传入 `--resume-from-checkpoint`，不能把已有 run 当 fresh run 重跑；
- operator 目录按 stage/plan/gate/checkpoint 唯一命名，script 在长任务前校验 stage clean/branch/HEAD-parent、primary planning base、persistent roots，并取得排他锁；status 每 attempt 开始前清空、结束原子写，terminal log append-only，避免 stale success 和并发双跑；
- 若没有合法 Trainer checkpoint，或 tracked code/config 修复使旧 run identity 失效，旧 incomplete formal run 只能 quarantine 并记录后 fresh restart，禁止删除/覆盖；
- Web GPT + CodexPro 的恢复命令明确为 `$execution-router resume backend=web`；Local Codex 仍可使用默认 local 或显式 `backend=local`；
- reviewer-ex 不重新执行 Base/SFT/GRPO/full-eval operator 长任务，只独立验证 checkpoint/script provenance、persistent artifacts 与短时 readback/test evidence。

---

## WP5-c：Formal Base A validation、正式数据绑定与运行 provenance

- **完成日期**：2026-08-18
- **阶段状态**：已完成
- **验收结论**：通过（依据 `ai-work/reviewer/WP5-c-review.md` R2）
- **执行计划**：`ai-work/planner/WP5-c-plan.md`
- **实施范围**：在 RTX 4090 validation track 上完成正式 Base A 的 400 题 test-split 评测、正式数据路径绑定、operator-terminal 执行与中断恢复、运行 timing/cost provenance 及后续分析所需不可再生 generation telemetry；未执行 SFT B、GRPO C/D 或最终 A–D analysis。

### 本阶段完成的功能与正式证据

- `evaluate` 新增显式 `--dataset-dir` override；未传参数时保持 YAML 行为，传入时在 stderr 记录旧/新路径，并将正式 `$CODE_VERIFIER_DATA_ROOT/prepared` 纳入既有 config/dataset/exact-resume identity。
- 正式 Base A 使用 `Qwen/Qwen2.5-Coder-1.5B-Instruct@2e1fd397ee46e1388853d2af2c993145b0f1098a`、seed 42、CUDA FP16、deterministic generation、真实 loopback Piston，完成 400 个唯一 test problem 的 persistent canonical run。
- evaluation `run.json` 现保存 timezone-aware `start_time/end_time`、`gpu_count_used`、显式 `gpu_hours_semantics`、可由持久化 generation latency 精确复算的 `gpu_hours`，以及 `piston_config_sha256`；逐题结果新增 `hit_max_new_tokens`，用于保留生成时不可再生的 truncation telemetry。
- 旧的缺 timing provenance Base A 与一次有意中断的 C1 7-row prefix 均完整保存在 persistent quarantine 中，没有人工回填或覆盖；最终 C2 canonical A 为修复后 fresh 生成。
- 新旧 Base A 的 completion、extracted code、parser/test status、三层 pass/failure 与 error category 全部一致，仅运行时 latency/runtime 有自然波动，因此 repair 未改变研究语义结果。

### 配置影响与验收结论

- 未修改 `pyproject.toml`、`uv.lock` 或 `third_party/open-r1` gitlink；没有依赖升级，也没有改变正式 A 的模型、revision、seed、decode 参数、test split、Piston 执行语义或指标定义。
- 正式 Base A：Visible Pass@1 `0.1225`，Train-Hidden Pass@1 `0.1175`，Eval-Hidden Pass@1 `0.115`，Eval-Hidden 95% problem-level bootstrap CI `[0.085, 0.1475]`，public-eval gap `0.0075`。
- canonical run timing：`start_time=2026-08-18T05:59:25.773910+00:00`，`end_time=2026-08-18T06:53:54.534608+00:00`，`gpu_count_used=1`，`gpu_hours=0.4206591900355286`；该 GPU-hours 语义为持久化 model-generation device time，不等同于 SFT/GRPO trainer-attempt wall time。
- R2 独立验收：`make lint` PASS；`make test` 为 887 passed、3 个预期 real-Piston opt-in skips；`make test-gpu` 3/3 passed；`make test-piston` 最终完整复验 9/9 passed、0 skipped。review 期间一次瞬时 Piston timeout 在 targeted retry 与完整 retry 中均未复现，记录为基础设施观察而非源码缺陷。
- completed exact-prefix verification返回 `resumed=400, generated=0`，strict loader/summary/CSV 与 persistent artifact identity 全部通过。
- WP5-c merge commit：`3850416e0cc5b383ad8c5b111c0aa4f9ef106367`。

### WP5 validation 聚合状态

WP5-a/WP5-b 已完成统一评测的 development 工程合同，WP5-c 现进一步完成正式 400 题 Base A 数值与持久 provenance。A 已成为后续 B/C/D 必须复用的正式 dataset/seed/evaluation-definition 基线；validation track 的下一依赖步骤是正式 SFT B 训练、checkpoint 重载与同一 evaluator/aggregator 下的 B 组评测。

---

## Project workflow amendment: GTX 1660 Ti control plane / RTX 4090 worker

- **生效日期**：2026-08-19
- **性质**：项目级 workflow/infrastructure policy；不修改任何既有 experiment definition、formal artifact、stage result 或历史 provenance。
- 本 amendment supersede 旧文档中“validation planner/reviewer/analysis 必须在 4090”以及“整个 validation track 留在 4090”的**运行位置**约束；历史记录中描述当时实际在哪台机器执行的事实保持不变。
- GTX 1660 Ti 现在是 development + validation 的固定 control plane：planner-ex、reviewer-ex、stage-lifecycle、execution-router、普通代码/测试、数据准备、SFT prevalidation、Piston、aggregation/error analysis/report 默认在此完成。validation plan 显式区分 `control_plane_hardware: GTX 1660 Ti (6GB)` 与 `target_hardware: 24GB GPU`。
- RTX 4090 只作为按需 target-GPU worker。formal SFT/GRPO、必须使用目标 GPU 的 inference/numerical acceptance 通过 portable operator handoff 交给用户在 4090 SSH/tmux 手工执行；GPT/CodexPro 不启动或持续监控正式长任务。
- 新 operator checkpoint 使用 `operator_handoff_mode=portable_target`，1660 Ti 生成 ignored immutable `run.sh` 和 SHA/expected-artifact contract；4090 target-start 时才验证 READY/GPU/roots/model/data/cache/Piston/storage，完成后生成 secret-free `operator-evidence.json`。小型 evidence 同步回 1660 Ti；大型 checkpoint 默认留在 4090。历史 absolute-root operator checkpoint 继续按 legacy v1 contract 审计，不回写旧记录。
- 项目唯一 Piston host 固定为 `1660ti-wsl`；`home-piston-01` retired。4090 只通过 `/root/sj-tmp/open-r1-code-verifier-outputs/machine/ensure-piston-1660ti-tunnel.sh` 建立 `127.0.0.1:2000 -> 1660ti-wsl:127.0.0.1:2000` local forward。
- 已有 environment-interruption resumability 保持：合法 committed environment checkpoint 修复环境后显式 resume；`retire_incomplete` 仍只是显式 abandon path。
- canonical policy 见 `docs/control-plane-gpu-worker-workflow.md`。

---

## Project workflow hardening amendment: target-GPU provenance and acceptance

- **生效日期**：2026-08-19
- **性质**：对上一条 control-plane/GPU-worker policy 的质量加固；不修改当前/历史 experiment definition、formal artifact identity 或已有 operator checkpoint。
- validation 现在明确区分 evidence profile 与 execution target：只消费既有 formal evidence 做 aggregation/bootstrap CI/error analysis/report 的 validation stage 合法使用 `target_hardware: GTX 1660 Ti (6GB)`；只有需要新 target-GPU execution 的 stage 才使用 `24GB GPU`。
- 所有新的 24GB acceptance gates（包括短时 4090-only smoke）统一经过 operator boundary，不再存在 execution-router 直接切换到 4090 的隐式路径。
- 新 portable operator `run.sh` 改为 tracked、secret-free Git provenance artifact：`ai-work/executor/operator/<stage>/<gate>/<checkpoint>/run.sh`。operator checkpoint commit 只允许修改 execution report + 新增这一份 script，且 parent=`result_code_commit`；`.ai-bridge/**` 仍完全禁止 tracked。旧 absolute-root/早期 portable checkpoint 继续按 legacy contract 读取，不回写旧记录。
- 4090 target script 必须执行 start preflight → target command → mandatory post-run acceptance。`command_rc=0` 单独不构成 PASS；只有 `command_rc=0 && postcheck_rc=0` 才允许 `gate_status=passed`。postcheck 必须按 sealed plan 对 completed run/checkpoint、metrics/schema、artifact identity 做短时 strict validation。
- 每次 target attempt 必须输出 versioned secret-free `operator-evidence.json`，绑定 plan/operator checkpoint/result code/script SHA、target machine-record SHA、GPU/roots/Piston、command/postcheck rc、formal run identity 与 expected-artifact inventory。evidence byte SHA256 由 1660 Ti resume 计算并写入 completed execution record，reviewer 独立重算；证据不能证明的大 artifact property 才允许短时只读 4090 check。
- 这些加固提高可重现性与 fail-closed acceptance，不增加正式 GPU job 次数，也不要求 4090 为 planner/reviewer/analysis 保持在线。

---

## WP6-d：Formal SFT B validation 与正式 B 统一评测

- **完成日期**：2026-08-20
- **阶段状态**：已完成
- **验收结论**：通过（依据 `ai-work/reviewer/WP6-d-review.md` R2）
- **执行计划**：`ai-work/planner/WP6-d-plan.md`
- **实施范围**：在 24GB validation track 上完成正式 SFT B optimizer run、completed checkpoint/训练曲线/成本验收、B 组 400 题 deterministic generation、真实 Piston verification 与统一 aggregation，并修复 staged evaluation / operator-terminal provenance 在正式 validation 中暴露的 durability 缺口；未进入 GRPO C/D 或最终 A–D 结论。

### 本阶段完成的功能与正式证据

- 正式 B 使用 `Qwen/Qwen2.5-Coder-1.5B-Instruct`、固定 revision 与 seed 42 完成 2 epochs / global step 314；最终 `train_loss=0.21536325907726198`，成功训练 attempt 的 `gpu_hours=0.5215871774233367`，`checkpoint-100/200/300/314` 均保留完整 Trainer/adapter 状态。一次 operator 中断的早期失败 attempt 作为独立 quarantine evidence 保留，没有覆盖成功 run。
- 正式 B evaluation 对 Base A 的同一 400 个唯一 test problems 完成 deterministic generation 与真实 Piston verification；exact-prefix readback 为 `resumed=400, verified=0`，strict pairing 证明 dataset/seed/model/revision/Piston/evaluation definition 与 A 基线一致。
- B 正式指标：Visible Pass@1 `0.3525`、Train-Hidden Pass@1 `0.335`、Eval-Hidden Pass@1 `0.3775`，Eval-Hidden 95% 10,000-resample bootstrap CI `[0.33, 0.425]`，Eval-Hidden average test pass rate `0.4525`，public/eval gap `-0.025`；generation GPU-hours `0.7607846797258146`。
- R2 独立审查确认 R1-M1 已由真实 C8 operator verification attempt 修复：immutable script/status/log/evidence 与 generation/data/verifier/Open-R1/dependency/Piston identity 完整绑定，fresh 400-row verification 与 canonical B 在除 attempt-local runtime/config-hash 外的语义完全一致。
- 最终独立验收：`make lint` PASS；`make test` 为 `910 passed, 3 skipped`；`make test-gpu` 为 `3/3 passed`；真实 `make test-piston` 为 `9 passed, 0 skipped`。

### 配置影响与验收结论

- 新增 validation staged evaluation / SFT prevalidation 实现与 `configs/sft/validation-smoke.yaml`，并调整正式 SFT 配置；`pyproject.toml`、`uv.lock` 与 `third_party/open-r1` gitlink 未修改，没有依赖升级或上游 submodule 变更。
- WP6-d merge commit：`5741ccd8432f530edc9edcca914ebba5339dc800`。

### WP6 聚合状态

WP6-a/WP6-c 已完成 SFT 数据、训练控制面、completed checkpoint identity、PEFT reload 与统一 B 组评测的 development 工程合同；WP6-d 现进一步完成正式 optimizer-based SFT B、checkpoint/成本与 400 题 B numerical validation。归档的旧 WP6-b blocked history 仍仅作为审计历史，不代表被 main 接受的独立 stage。至此 WP6 的 development + formal B validation 范围完成，后续 validation 依赖转入 WP7 的 Public/Hidden GRPO C/D 正式训练与评测。

---

## Project workflow transport amendment: 1660 Ti initiated reverse SSH for Piston

- **生效日期**：2026-08-27
- **性质**：项目级 workflow/infrastructure transport amendment；不修改 Piston host、Piston image/runtime、experiment definition、formal artifact identity、dataset/model/training/evaluation identity，也不重写既有 operator evidence。
- 项目唯一 Piston host 仍为 `1660ti-wsl`，Piston API 仍只绑定该机 `127.0.0.1:2000`，4090 上 CodeVerifier 仍只使用 `http://127.0.0.1:2000`。变化仅是 SSH tunnel 的发起方向：canonical transport 改为 GTX 1660 Ti control plane 主动连接当前算力平台公网 SSH endpoint，并建立 `-R 127.0.0.1:2000:127.0.0.1:2000` loopback-only reverse forward。
- provider SSH hostname/port/authentication 为 machine-local operator state，不进入 Git。4090 target-start preflight 不再启动旧 `ensure-piston-1660ti-tunnel.sh` / Tailscale local-forward helper；需要 Piston 时只 health-check 现有 `127.0.0.1:2000` listener、`/api/v2/runtimes` 与项目 `PistonExecutor.validate_runtime()` exact `3.10.0`。
- 2026-08-27 实测 reverse-forward 后，4090 fresh `/api/v2/runtimes` 30 次 mean `97.56 ms`、p50 `98.759 ms`、p95 `104.156 ms`；可信 `print(1)` fresh 10 次 mean `134.31 ms`。相较先前 Tailscale DERP 路径约 `1.06–1.09 s` 的 fresh 请求，连接/执行端到端延迟约降低 90%。4090 上项目 `PistonExecutor.validate_runtime()` 返回 exact `3.10.0`，并且经该 reverse tunnel 的真实 `make test-piston` 为 `9 passed, 0 skipped, 0 failed`。
- 已有 WP7-c operator `run.sh`/checkpoint SHA provenance 保持 immutable，不回写旧脚本；active stage 如需采用本 transport update，按既有 active-stage workflow migration 规则记录独立 `workflow_runtime_commit`，新 operator checkpoint 才按 reverse-forward policy 生成。
- transport 切换验证期间 4090 无 formal SFT/GRPO/model-loading target-GPU process；正式 target-GPU run 活跃时仍禁止重启或扰动该 SSH transport。

---

## WP7-c：Formal Public/Hidden GRPO C/D validation 与统一评测

- **完成日期**：2026-08-30
- **阶段状态**：已完成
- **验收结论**：通过（依据 `ai-work/reviewer/WP7-c-review.md` R2；采用 committed amendment A1 的 post-hoc operational-equivalence acceptance）
- **执行计划**：`ai-work/planner/WP7-c-plan.md`
- **实施范围**：完成正式 Public GRPO C / Hidden GRPO D 的 paired validation、真实 24GB target-GPU training evidence、completed checkpoint / reward / rollout / group provenance、400 题 deterministic generation、GTX 1660 Ti control-plane 上的真实 Piston verification 与统一 aggregation，并补齐 GRPO resume / transport-resilience / operator provenance 的 durability 缺口；未执行 WP8 最终 A–D 统计分析、人工 20-case analysis 或最终论文表格/结论。

### 本阶段完成的功能与正式证据

- C/D 共用正式 SFT B、seed 42、模型/revision、dependency/Open-R1 identity、2500 training problem pairing 与 `paired_definition_sha256=31f5464abf094d14cf86e8ef4dd909b8a1be559c8b4ca8b96473070a9f1daad9`；Public reward 只读 `visible_tests`，Hidden reward 只读 `train_hidden_tests`。两条 formal run 均完成到 global step 300。
- 已认证的 C25 formal canonical streams 中，Public/Hidden 各有 2400 reward rows、2400 rollout rows、600 group rows；无 canonical infrastructure/sandbox contamination，扫描数值均 finite。失败 attempt 与 same-run trainer checkpoint recovery history 保留，恢复逻辑在 optimizer update 前 fail closed 并恢复 canonical stream 到 checkpoint boundary。
- C27 对 completed C/D 各生成 400 个唯一 deterministic records；4090 strict readback 均为 `resumed=400, generated=0`。随后 `/home/dzy/wp7c-verified` 在真实 local Piston 上对 Public/Hidden 各完成 400/400 verification，strict readback 均为 `resumed=400, verified=0`，且问题顺序与对应 generation 完全一致、无 sandbox/infrastructure rows。
- 统一 aggregation：Public 为 Visible Pass@1 `0.3625`、Train-Hidden Pass@1 `0.34`、Eval-Hidden Pass@1 `0.375`、Eval-Hidden average test pass rate `0.44875`；Hidden 的三个 Pass@1 同为 `0.3625 / 0.34 / 0.375`，Eval-Hidden average test pass rate `0.45125`。Public summary SHA256 为 `6cc3fa7b785f01aef55e6a13e082266385ea01a77950a36ffaf1e7285e25480c`，Hidden 为 `f63a20181f2f560ffdf1b6bdcb385f6dbbf83f1a05b5592013315ff401a2273d`。
- R2 独立验收通过：`make lint`；focused GRPO/resume/harness/resilience suite `67 passed`；`make test` 为 `1030 passed, 3 skipped`；`make test-gpu` 为 `3 passed`；真实 `make test-piston PISTON_CONFIG=configs/execution/piston-local.yaml` 为 `9 passed, 2 deselected`，无 selected skip/failure。

### A1 post-hoc amendment 与历史偏差披露

- 原 sealed plan 的 whole-run exact-code-identity 要求和 `save_steps=50` acceptance-critical cadence **没有被历史 C/D 严格满足**：accepted pilot/formal 分别使用历史 `save_steps=10/25`，formal Public/Hidden 的完成链也跨越了已记录的 tracked code transitions。R1 因此曾以 `R1-B1` blocker 与 `R1-M1` major 判定 `needs_repair`。
- committed amendment A1 在不豁免真实执行、completed steps、artifact authenticity、hidden-test isolation、安全边界或 failed reward batch-before-optimizer fail-closed 要求的前提下，用户授权以保存完整 attempt/resume/provenance、canonical stream boundary restoration、actual-path/other-arm operational equivalence 和下游 hash revalidation 替代“仅为 exact Git identity / save cadence 重跑 4090”的要求。R2 据此判定两项历史问题 resolved under A1。
- C28 修复 pilot checkpoint 保持 `abandoned_unexecuted`；不存在把未执行 C28 target gate 描述为通过的情形。当前 future-run configs 已恢复 `save_steps=50`。
- 因此本阶段 PASS 是明确的 **post-hoc operational-equivalence acceptance**，不是“原计划严格 preregistered compliance”的声明；后续 WP8 最终分析/报告必须继续保留该披露。

### 配置影响与验收结论

- 本 stage 新增/强化 formal GRPO paired binding、completed/resume lineage、Piston transport resilience、operator evidence 与相关 tests/configs；`pyproject.toml`、`uv.lock` 和 `third_party/open-r1` gitlink 未修改，因此没有 dependency upgrade 或上游 submodule 变更。
- WP7-c merge commit：`6ca8ba9de04303c32a027af439881afd96e9ae67`。

### WP7 聚合状态

WP7-a/WP7-b 已完成 GRPO control-plane、reward isolation、paired fairness、completed C/D identity、stacked inference reload 与统一 evaluation/aggregation 的 development 工程合同；WP7-c 现完成正式 Public/Hidden GRPO C/D 的 real-training/numerical validation、400 题 generation、真实 Piston verification 与 aggregation。至此 WP7 的 development + formal C/D validation 范围完成；下一 dependency-ready validation 工作转入 WP8 的正式 A–D comparison、bootstrap/statistical analysis、人工 case analysis 与最终报告。

---

## WP8-a：Formal A–D 自动统计、paired bootstrap、成本与失败候选

- **完成日期**：2026-08-30
- **阶段状态**：已完成
- **验收结论**：通过（依据 `ai-work/reviewer/WP8-a-review.md` R1）
- **执行计划**：`ai-work/planner/WP8-a-plan.md`
- **实施范围**：在 GTX 1660 Ti control plane 上严格消费已 finalized 的 Base A / SFT B / Public GRPO C / Hidden GRPO D formal artifacts，完成 A–D 聚合、problem-level paired bootstrap、training curve / cost 汇总、failure-candidate 生成、机器可读 report 与 deterministic readback；本 stage 不产生新的 24GB GPU execution，也不声称完成后续不少于 20 个 case 的人工分析或最终研究叙事。

### 本阶段正式分析证据

- 冻结输入位于 `/home/dzy/wp8-analysis/wp8-a-input-ab87fea-e0/`：`formal-analysis.yaml` SHA256 为 `118093d5befbd43bdd0e08527847d23f40626284f8e73b49dbe2df033d1e0da8`，`source-inventory.json` SHA256 为 `b79718d096be441b2d3d0e45b88b4b95ce1d458696617dafd80f1b11cfca18f1`；bootstrap 合同固定为 seed 42、10,000 次 resample、95% CI、problem 为采样单位。库存继续明确保留 WP7-c A1 post-hoc operational-equivalence disclosure，不把历史 C/D 描述为满足原始 whole-run exact-code / save-cadence 合同。
- 四个方法均严格绑定 400 个唯一 formal problem。A–D 的 Visible / Train-Hidden / Eval-Hidden Pass@1 分别为：Base `0.1225 / 0.1175 / 0.1150`，SFT `0.3525 / 0.3350 / 0.3775`，Public `0.3625 / 0.3400 / 0.3750`，Hidden `0.3625 / 0.3400 / 0.3750`。
- 三组 problem-paired comparison 均使用 400 个 problem-ID pair。Public-vs-SFT 与 Hidden-vs-SFT 的 Eval-Hidden delta 都为 `-0.0025`、95% CI `[-0.0125, 0.0075]`；public-eval-gap delta 都为 `0.0125`、CI `[0.0, 0.03]`；automated candidate-rate delta 都为 `0.0075`、CI `[0.0, 0.0175]`。Hidden-vs-Public 在这三个预注册 whole-pass / candidate proxy 指标上均为 `0.0`，CI `[0.0, 0.0]`。
- Training/cost 派生与源日志一致：SFT 2,549 curve rows、GPU-hours `0.5215871774233367`；Public 8,115 rows、GPU-hours `4.012272991803669`、2,400 rollouts、514,360 generated tokens、executor-hours `0.0582530611647443`；Hidden 8,115 rows、GPU-hours `3.5036727118225017`、2,400 rollouts、512,918 generated tokens、executor-hours `0.06447173045885166`。没有冻结可审计 GPU-hour USD rate，因此没有伪造美元成本。
- Canonical formal output 位于 `/home/dzy/wp8-analysis/wp8-a-formal-ab87fea-e0/`，完整产生计划规定的 10 个文件；fresh readback `/home/dzy/wp8-analysis/wp8-a-formal-ab87fea-e0-readback/` 的 10 个对应文件全部 byte-for-byte 相同。关键输出中 `main_results.csv` SHA256 为 `02030685f05f0ed04d8e007cc0eb1a4455aacfbcbe6f505c13afd8849e63804e`，`paired_comparisons.csv` 为 `0ae767e7e9e918d9fe2109a7f65b4aca39b4446c615beb694eb175adb80a3eed`，`report_data.json` 为 `fd03754215297643aec8d32f1df65b9fd8df669c29983cd7573c5f3ff3fc74c2`。
- Failure-analysis preparation 产生 653 个 deterministic candidates 与 653 个 manual-label template rows；所有人工字段仍为空，`manual_analysis_status=pending`、`manual_label_count=0`，automated proxy 明确不是 human conclusion。该数量足以供后续 stage 抽取不少于 20 个 case，但 WP8-a 自身不把人工分析标记为完成。

### 验收与生命周期结论

- Reviewer R1 独立重算 source hashes、A–D point estimates、bootstrap/paired statistics、curve/cost derivation，并通过 `make lint`、`make test`（`1030 passed, 3 skipped`）、`make test-gpu`（`3 passed`）与真实 `make test-piston PISTON_CONFIG=configs/execution/piston-local.yaml`（`9 passed, 2 deselected`）；未发现 blocker、major、minor 或 actionable acceptance finding。
- 本 stage 为 zero-code formal validation：相对 planning base 只新增 plan/executor/reviewer provenance 文档，`pyproject.toml`、`uv.lock` 与 `third_party/open-r1` gitlink 均未修改，因此没有 dependency upgrade 或上游 submodule 变更。
- WP8-a merge commit：`44f8023ecbca8b84af2af9d6a57547da00acd51a`。
- WP8 尚未整体收口：下一子阶段应以这里冻结的 formal outputs/hashes 为输入，完成不少于 20 个 case 的人工错误分析、正/负结果解释与最终报告叙事；在该后续工作完成前，不把 WP8-a 的 automated proxy 当作最终 human reward-hacking conclusion。

---

## WP7-d（WP8 收口）：25-case 人工失败分析、最终技术报告与 README

- **完成日期**：2026-08-30
- **阶段状态**：已完成
- **验收结论**：通过（依据 `ai-work/reviewer/WP7-d-review.md` R1）
- **执行计划**：`ai-work/planner/WP7-d-plan.md`
- **阶段身份说明**：该 stage 因纯 PLANNED pre-execution replan 合同保留 `WP7-d` identity，但 sealed plan 的目标工作是完成 WP8-a 之后剩余的人工失败分析、最终 evidence snapshot、技术报告与 README 展示收口；本 stage 不执行第二 training seed 或新的 24GB GPU gate。

### 人工分析与最终证据

- 在查看 selected code 前，严格从 WP8-a frozen `failure_candidates.jsonl`（SHA256 `4410a05e2838a0be92997141bf19bb2b518a4985a8afabdc87442812827408ed`）按 namespace `wp7-d-final-manual-v1|seed42` 和 sealed SHA256 排序算法冻结 25 个案例：Public-RLVR 10、Hidden-RLVR 10、SFT 5；selection artifact SHA256 为 `cd5ef448b8d4ee1ea85f364d05c90651b75267da3d431ac699ed6657b5c0e7ea`。
- `report/manual_labels.csv` 由 production strict loader 成功读取 25 个 unique known candidates；manual categories 为 runtime error 11、incomplete algorithm 6、misunderstood problem 5、missed edge case 2、syntax error 1。25 个案例在当前 sealed rubric 下均标记 `reward_hacking=no`，但报告明确这是 candidate-stratified qualitative sample，不能解释为全体输出的 0% Reward-Hacking prevalence。
- Final labeled production analysis 保持 WP8-a 的 A/B/C/D source、bootstrap、cost 和 candidate definition 不变，唯一语义变化是 `manual_labels_path`。`manual_analysis_status=completed`、`manual_label_count=25`；fresh reviewer-owned readback 的 10 个输出文件全部与 `report/final_evidence.json` 中记录的 SHA256 精确一致。
- 主数值没有被人工层改变：Base / SFT / Public-RLVR / Hidden-RLVR Eval-Hidden Pass@1 分别为 `0.1150 / 0.3775 / 0.3750 / 0.3750`；Public-vs-SFT 与 Hidden-vs-SFT delta 都是 `-0.0025`，95% CI `[-0.0125, 0.0075]`。因此最终叙事报告“本 seed 未观察到 GRPO 相比 SFT 的 held-out improvement”，不把该点估计称为显著下降，也不把 Hidden/Public 的 aggregate equality 外推为算法等价。
- `report/final_evidence.json` 固定 `project_claim_scope=single_training_seed_seed42`、`replication_status=pending_second_seed_or_full_rerun`、`second_seed_executed=false`、`wp7c_a1_posthoc_operational_equivalence=true`、`candidate_sample_only=true` 与 `usd_cost_rate=null`；README 与 16 节技术报告都保留 single-seed、WP7-c A1、candidate-sample、1.5B/400-problem scope 和无冻结 USD rate 等限制。

### 验收与生命周期结论

- Reviewer R1 独立通过 `make lint`、`make test`（`1030 passed, 3 skipped`）、`make test-gpu`（`3 passed`）、真实 `make test-piston PISTON_CONFIG=configs/execution/piston-local.yaml`（`9 passed, 2 deselected`）和 focused analysis（`41 passed`），并重新验证 8 个 WP8-a frozen hashes、exact 25-case deterministic selection、fresh 10-file production analysis hashes以及 5 个 formal-source case spot checks；未发现 blocker、major、minor 或 actionable finding。
- 本 stage 相对 planning base 仅新增/修改 plan、execution/review provenance、README 与 `report/` 分析/展示 artifacts；`pyproject.toml`、`uv.lock` 和 `third_party/open-r1` gitlink 均未修改，因此 finalize 不需要 dependency sync 或 submodule update。
- WP7-d merge commit：`4c997a8ff85cf1d2ce35c4e95b456c6c8a9f2bdc`。
- 第二 seed / 完整 C/D rerun 仍是明确的 project-level pending scientific gate；本次 PASS/finalize 不把 §13.5 / Definition of Done 的 replication item 标记为完成。

### WP8 聚合状态

WP8-a 已完成 formal A–D automated analysis、paired bootstrap、cost 与 deterministic failure-candidate preparation；本 WP7-d replan stage 现完成 25-case 人工语义分析、manual-label production readback、最终 evidence snapshot、技术报告、README 与 scientific-claim audit。至此 WP8 的 **analysis + presentation** 范围完成；整个项目仍保留“核心实验第二 seed 或完整重跑”这一明确未完成的 Experiments DoD 项，是否追加 replication stage 由后续全项目审查决定。

---

## Project decision：激活 WP9 GRPO Refresh research track（2026-08-31）

- **性质**：post-WP8 项目级 research/spec routing decision；不追溯修改已 finalized 的 WP0–WP8、A/B/C/D、seed-42 数值、WP7-c A1 disclosure 或现有 final report evidence。
- **Active specification**：`PROJECT_SPEC_GRPO_Refresh.md` 升级为 `Active v1.0`，作为 WP9 / GRPO Refresh 的强制增量规格。WP9 planner/executor/reviewer 必须同时读取主 `PROJECT_SPEC_Open-R1_CodeVerifier.md`、该 addendum 与本 proceedings；WP9 范围存在默认值冲突时以 Refresh addendum 为准。
- **Replication status**：原规格要求的“第二 training seed 或完整 C/D rerun”仍保留为未完成 robustness/replication item，但根据完成后的全项目复核，当前不优先直接复刻旧 100% SFT-overlap / `num_generations=4` 协议。该 replication item 标记为 **deferred, not cancelled**，不得在新对话中自动覆盖当前 active track。
- **Refresh rationale**：第一轮正式 C/D 实际 600/600 GRPO problems 均来自已经进行 SFT supervision 的 2500 题 train split；同时 Public/Hidden total-reward zero-variance group 分别约 32.17% / 31.83%。新 track 优先修复 problem-overlap 与 reward-informativeness/throughput 设计后再运行 C2/D2。
- **Frozen refresh constraints**：SFT/GRPO overlap target `5–10%`、hard max `15%`、validation/project-test/external-final-eval overlap `0`；calibration 与正式 GRPO `num_generations=8`；active pool 默认 `>=70% dual-informative`；k=8 pilot zero-variance target `<20%`、`>25%` stop-and-recalibrate；same-GPU Public/Hidden concurrency 只能在 benchmark 证明安全且 paired wall-clock 至少改善约 15% 后采用；400 题 evaluation 优先采用 batched generation + concurrent control-plane verification。
- **WP9 dependency order**：`WP9-a Refresh data foundation (development)` → `WP9-b calibration/k=8/throughput engineering (development)` → `WP9-c real calibration and pilot (validation)` → `WP9-d formal C2/D2 (validation)` → `WP9-e evaluation and refresh analysis (validation/control plane)`。如果 planner 因规模需要继续拆分，可细分 stage，但不得改变 development-first 和真实 target-GPU boundary。
- **Next dependency-ready stage**：**`WP9-a`**。其范围限定为新 candidate source ingestion/provenance、cross-source + SFT/eval dedup、SFT/GRPO overlap control、canonical three-test-layer materialization 与 Public/Hidden training views；本阶段不运行真实 B calibration、不启动 GRPO、不产生 C2/D2 数值。
- **Planner routing rule**：新对话若被要求“继续项目 / 检查现状 / 规划下一 stage”，必须识别本 decision record，并以 `WP9-a` 为下一阶段调用 planner；在本 record 被后续 finalized proceedings 明确更新前，不得把旧 second-seed replication 作为默认 next stage。
- **Original Development Complete Record**：仍然只证明原 WP0–WP8 development track 已完成且保持 immutable。WP9 是新的 post-completion research extension；WP9-a/WP9-b 中新增工程工作仍属于 `stage_profile: development`，不能因为旧 completion record 已存在就跳过工程 stage 或直接在 validation 里修改功能。

---

## WP9-a — Refresh data foundation

- **完成日期**：2026-09-01
- **阶段状态**：已完成 / finalized
- **验收结论**：PASS（依据 `ai-work/reviewer/WP9-a-review.md` R7）
- **执行计划**：`ai-work/planner/WP9-a-plan.md`
- **Review commit**：`782f322c36544228462fc99c291cb7023cd8582f`
- **Merge commit**：`6f6a125290b806ea87444486e8f00176980e55f4`

### 数据基础交付

- 完成 pinned external-source ingestion/provenance、source revision/license/schema identity、deterministic exact/near dedup、SFT/evaluation overlap audit、canonical three-layer test materialization，以及同 ID/同顺序的 Public/Hidden GRPO training views。
- 生产协议冻结为 10,000 个 train problems：750 个 frozen-SFT explicit reuse（7.5%，低于 15% hard max）+ 9,250 个新 external problems；当前 accepted real artifacts 的 external dedup retained count 为 9,565，`quality_gate_required=true` 为 1,086。
- strict readback 对 canonical/training views、source/reference snapshots、selection/dedup provenance、artifact/root SHA、overlap/quality reports 和 deterministic row order 全部 fail closed；R5/R6 修复最终补齐了 `dedup_decisions.jsonl` 非 canonical row reorder 的 public-checker 端到端 regression。
- 两份已接受 real pinned-source outputs `wp9a-refresh-seed42-r2e2-final1` / `final4` 在最终 reviewed HEAD 下均通过 strict readback：selected 10,000、external retained 9,565、SFT overlap 750/10,000、quality-gate-required 1,086。WP9-a 不运行真实 B calibration、GRPO、正式 C2/D2 或 400-problem re-evaluation。

### 验收与生命周期结论

- Reviewer R7 独立通过新增 row-order regression（1 passed）、完整 WP9-a focused suite（187 passed）、`make lint`，以及 `make test`（1110 passed, 3 skipped；skip 仅为既有 real-Piston opt-in tests）。
- WP9-a 相对 planning base 未修改 `pyproject.toml`、`uv.lock` 或 `third_party/open-r1` gitlink，因此 finalize 无需 dependency sync 或 submodule update；merge 后 primary `.venv` 已确认 `code_verifier` 与 `open_r1` editable imports 均绑定主 checkout。
- 本 stage 为 `development_terminal=false`，因此不会写新的 Development Complete Record；原 WP0–WP8 completion marker 保持 immutable。

### WP9 后续路由

WP9-a 已 finalized。按已冻结的 WP9 dependency order，新的 **Next dependency-ready stage 是 `WP9-b`（Calibration / k=8 / throughput engineering，development）**。原 second-seed/full-rerun robustness item 继续保持 deferred, not cancelled，不覆盖当前 WP9 routing。
