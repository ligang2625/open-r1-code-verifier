# 项目实施记录（Proceedings）

> **文件功能**
>
> 本文件用于持续记录 Open-R1 Code Verifier 项目各阶段（Work Package）的实施与验收结论，作为项目开发过程的可追溯记录。
>
> **内容与格式要求**
>
> 1. 按阶段（Work Package / 计划）分节记录；阶段边界以 `ai-work/planner/WP{n}-plan.md` 覆盖内容为准。
> 2. 每阶段记录保持简洁：阶段状态、验收结论、实施范围、完成的功能概述、相关文件、验收结论；不写入中间多次 review 与 execution 的细节（细节见 `ai-work/planner`、`ai-work/executor`、`ai-work/reviewer` 报告）。
> 3. 必须明确说明是否修改了项目原有配置。
> 4. 必须区分本项目代码变更与 `third_party/open-r1` 上游依赖变更。
> 5. 测试结果应记录实际执行的命令和最终结论，不得仅根据代码内容推断通过。
> 6. 如果存在未完成项或外部环境限制，应如实记录，不得将阶段标记为完成。
> 7. 记录由最终审查方在阶段全部通过、独立分支合并回主分支后写入，并在文件末尾追加、保留已有内容。

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
