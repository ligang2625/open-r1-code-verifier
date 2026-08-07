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
