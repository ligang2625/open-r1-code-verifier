---
name: planner
description: 使用 Codex 内部 agent，根据 PROJECT_SPEC_Open-R1_CodeVerifier.md 与 proceedings.md 生成下一个 Work Package（WP）的函数级实施计划并创建阶段分支/worktree。Use when Codex must delegate WP planning to a dedicated gpt-5.6-sol agent with high reasoning effort and produce a testable plan for the internal executor workflow.
---

# Planner

## Codex 内部 agent 配置

入口协调 agent 不直接执行规划。必须使用 `spawn_agent` 创建一个专用规划 agent，并等待其完成：

- `model`: `gpt-5.6-sol`
- `reasoning_effort`: `high`
- `fork_turns`: `none`
- 任务消息：写明仓库绝对路径、用户要求，并明确“你是已创建好的专用规划 agent，不是入口协调 agent；不得再次执行本节的 spawn 步骤”。要求其先完整读取本 `SKILL.md`、`references/plan-template.md` 与下述全部输入，再直接执行原有 WP 规划流程。

协调 agent 只负责传递任务、等待结果和向用户转述最终结果，不另行修改计划。若 `spawn_agent` 不可用或指定模型无法创建，明确报告阻塞，不得静默改用其它模型或当前 agent 代跑。

## 用途

本 skill 用于生成“下一个 Work Package 的实施计划”文档。计划是给后续执行 agent 使用的工件，因此必须：

- **精确到函数级别**：每个步骤指明要新建/修改的文件路径、函数或类的完整签名、主要功能。
- **高度可执行**：拿到计划的 agent 只需文件读写和基础 shell（运行仓库自带的 Makefile / pytest / CLI），即可逐步实现，无需再向任何人澄清。
- **可验证**：每个步骤都带测试方案与可测量的通过标准。

> 专用规划 agent 不负责创建、启动或指挥任何执行 agent；计划文件只是供后续 executor 消费的产物。

## 输入

从仓库根目录读取以下文件（若仓库结构不同，按实际路径调整）：

1. `PROJECT_SPEC_Open-R1_CodeVerifier.md` —— 项目最高规格。Work Package 注册表（WP0–WP8 的目标、交付、验收）在 §20；相关细节见 §6 模块边界、§7 数据规范、§8 执行器、§9 解析器、§10 奖励、§11 SFT、§12 GRPO、§13 评测、§16 仓库结构、§17 CLI、§19 测试计划、§29 默认决策。
2. `proceedings.md` —— 实施记录。已完成的 WP 在此登记；下一个 WP 是第一个未登记为“已完成”的 WP。
3. `src/` 与 `tests/` 当前源码 —— 只读检查，确保计划在现有代码上增量扩展，而不是重复造轮子。

若上下文允许，通读整份规格；至少必须精读上面列出的章节。

## 工作流程

### 第 1 步：确定下一个 WP

1. 通读 `proceedings.md`，找到最后一个 WP 小节及其状态（已完成/部分完成/受阻）。
2. 阅读 `PROJECT_SPEC_Open-R1_CodeVerifier.md` §20 的 WP 顺序（WP0 → WP8）。
3. 下一个 WP = 按 §20 顺序第一个未被 proceedings 标记为完全完成的 WP。若该 WP 在 proceedings 中被记为部分完成，计划应覆盖其剩余交付物，不得跳档。
4. 把 proceedings 中与下一个 WP 相关的未完成项、决策、已知问题写入计划的“前置条件与约束”。
5. 若 proceedings 缺失或没有 WP 小节，默认取 §20 中 `src/` 尚未实现的首个 WP，并在计划中注明该假设。

### 第 2 步：提取 WP 契约

从规格中提取并原样保留：

1. 目标 WP 的“目标 / 交付 / 验收”（§20 原文）。
2. 该 WP 触及章节中**规格已给出签名**的接口，逐字使用，不得另造冲突签名，例如：
   - §8.3：`ExecutionStatus`、`TestCaseResult`、`ExecutionResult`、`CodeExecutor` Protocol；
   - §9.2：`ParseResult`、`extract_python_code`；
   - §10.5：`public_code_reward`、`hidden_code_reward`、`compute_code_rewards`；
   - §7.1 数据 schema 字段名与结构。
3. §6.2 的模块边界（Data / Generation / Parsing / Execution / Verification / Reward / Training / Evaluation / Analysis 各自的职责与禁止事项）。
4. §17 要求的 CLI 命令形态与全局参数（`--help`、`--config`、`--seed`、`--output-dir`、`--log-level`）。
5. §19 的单元/集成测试要求。
6. §29 默认决策。
7. 横切规则：业务逻辑不得硬编码路径/模型名/设备/密钥/数据位置；训练与评测配置必须走 YAML 或 CLI；新模块必须带类型标注、docstring、单元测试；**绝不修改 `third_party/open-r1/`**；所有 Open-R1 访问必须经 `code_verifier.training.open_r1_adapter`。

### 第 3 步：检查当前代码

读取 `src/code_verifier/` 与 `tests/unit/` 下已有文件，确认：

- 已有内容（WP0 脚手架：`cli.py`、`environment.py`、`training/open_r1_adapter.py` 及对应测试）；
- 代码风格：双引号、119 列、strict mypy、`from __future__ import annotations`；
- CLI 子命令模式：`build_parser()` / `main()` / handler 函数，新命令必须沿用；
- 测试风格：`tests/unit/test_*.py`。

计划只添加目标 WP 要求的改动。

### 第 4 步：创建当前阶段分支

为本阶段创建独立分支与 worktree，供 executor 实施、reviewer 审查：

1. **阶段标识与分支命名**：先定义完整 `stage_id`——未拆分为 `WP{n}`，拆分子阶段为 `WP{n}-{sub}`（如 `WP3-c`）。分支名对应使用 `feat/wp{n}` 或 `feat/wp{n}-{sub}`。
2. 在主仓库根目录运行 `git worktree list` / `git branch --list` 检查：若该分支与 worktree 已存在则复用；不存在则创建：

   ```bash
   git worktree add .worktrees/wp{n}-{sub} -b feat/wp{n}-{sub}
   ```

   worktree 路径默认 `.worktrees/wp{n}`（未拆分）或 `.worktrees/wp{n}-{sub}`（拆分子阶段），可随任务指定调整。
3. **计划写入分支**：把计划文件写到该 worktree 的 `ai-work/planner/{stage_id}-plan.md` 并提交到分支（`docs: add {stage_id} plan`），保证 executor 在分支上直接可取计划。
4. 在计划文件元信息中记录分支名与 worktree 路径。

### 第 5 步：编写计划

在分支 worktree 的 `ai-work/planner/{stage_id}-plan.md`（如 `ai-work/planner/WP1-plan.md`、`ai-work/planner/WP3-c-plan.md`）按 `references/plan-template.md` 的模板产出计划，并提交到当前阶段分支。默认使用中文（与 proceedings/规格一致），代码标识符、签名、文件路径保留英文。若用户另行指定语言或路径，以用户要求为准。

阶段边界以**一个计划文件覆盖的内容**为准：不同计划文件视为不同阶段。

存在不确定信息（如上游 Open-R1/TRL 或 Piston 的实际接口行为）时，写入计划的“前置条件与约束”并要求先验证，不得臆造接口；计划中不得出现未经确认的假设实现。

### 规划粒度约束

一次规划的内容不宜过多，保持"一个可独立验收的阶段"的粒度：

- 单个计划的实施步骤最多 10 个，涉及的新模块最多 8 个；
- 若目标 WP 任务过多（步骤超过 10 个、新模块超过 8 个、跨多个独立模块或存在长依赖链），必须拆分为多个连续阶段计划（如 `WP{n}-a`、`WP{n}-b`，或拆为子计划），每个子计划仍满足函数级精度、测试方案与独立验收标准；
- 拆分后每个计划文件视为独立阶段，按各自计划执行、审查与合并。

### 第 6 步：自检

完成前逐条核对；不满足则修改计划直到全部通过：

- [ ] 只覆盖一个 WP，无后续 WP 范围蔓延；
- [ ] 每个实现步骤都给出仓库根目录相对的文件路径；
- [ ] 每个新增/修改代码的步骤都给出函数/类名与完整签名；
- [ ] 每个步骤都说明主要功能及与现有代码/CLI/配置的衔接；
- [ ] 每个步骤都有测试方案：测试文件路径、测试函数名、断言内容；
- [ ] 每个步骤都有具体验证命令与可测量的通过标准（如 `make lint`、`make test`、具体 CLI 调用）；
- [ ] 规格已给的接口被逐字复用，无冲突签名；
- [ ] 无任何步骤修改 `third_party/open-r1/`；
- [ ] 计划不依赖 Codex 工具、MCP、其它 skill；只涉及仓库文件、项目自带命令与执行 agent 自身的文件/shell 能力；
- [ ] 计划不含创建/启动执行 agent 的步骤；
- [ ] 计划粒度适中（步骤 ≤ 10、新模块 ≤ 8）；任务过多时已拆分为多个阶段计划；
- [ ] 已为本阶段创建/复用分支（名称含主阶段+子阶段）与 worktree，计划已提交到该分支；
- [ ] 计划未提交到 main，未在 main 上留下本阶段改动；
- [ ] 通过标准可判定（通过/失败无需主观判断）。
