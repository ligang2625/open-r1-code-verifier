---
name: executor
description: 使用 Codex 内部主 agent 与多个 subagent 执行 WP 计划或审查修复。Use when Codex needs a gpt-5.6-sol main agent with medium reasoning effort to read an ai-work/planner/WP{n}-plan.md file, split it into mutually independent subplans, delegate one subplan each to gpt-5.6-luna subagents with max reasoning effort, integrate and verify their work, commit it, and write ai-work/executor/WP{n}-executor.md.
---

# Executor

## Codex 内部 agent 编排（优先级最高）

入口协调 agent 不直接实施计划。必须先使用 `spawn_agent` 创建一个**主 agent**：

- `model`: `gpt-5.6-sol`
- `reasoning_effort`: `medium`
- `fork_turns`: `none`
- 任务消息：写明仓库与阶段 worktree 的绝对路径、计划/审查报告路径、用户要求，并明确“你是已创建好的主 agent，不是入口协调 agent；不得再次创建主 agent，应从下述主 agent 流程开始”。要求主 agent 完整读取本 `SKILL.md`、`references/execution-workflow.md` 和下述输入。

主 agent 必须执行以下流程；本节与后文冲突时以本节为准：

1. 全文阅读 plan；修复任务同时全文阅读最新 review。读取相关 spec、`AGENTS.md`、`proceedings.md` 和代码基线后，才允许拆分。
2. 按依赖关系、文件所有权与可独立验证边界，把整体 plan 拆成最大化且**相互独立**的子计划。依赖步骤或会修改同一文件/符号的步骤必须合并到同一子计划，禁止伪并行。无法拆成多个独立组时，形成 1 个子计划。
3. 为每个子计划创建且只创建 1 个 subagent；subagent 总数必须等于子计划数。每个 subagent 固定使用：
   - `model`: `gpt-5.6-luna`
   - `reasoning_effort`: `max`
   - `fork_turns`: `none`
4. 每个 subagent 的自包含任务消息必须列明：worktree、plan/review 路径、分配的步骤或问题、唯一可写文件、禁止改动项、定向测试命令与汇报格式。subagent 必须读取完整 plan 和相关项目约束，但只实施自己的子计划；不得继续创建 agent、不得暂存或提交、不得写总执行报告、不得修改 plan/review/`proceedings.md`。
5. 独立子计划应并行派发。受并发槽位限制时分批创建，但最终仍保持“一份子计划对应一个 subagent”，不得合并或省略 agent。
6. 等待全部 subagent 向主 agent 汇报。汇报必须包含：修改文件、实现内容、实际运行的命令与结果、未完成项、风险。失败或不完整时，优先向同一 subagent 发送 follow-up 修正，不另建重复 subagent。
7. 主 agent 检查每份改动是否符合文件所有权与计划，处理集成顺序，运行计划要求的 `make lint`、`make test` 与 WP 特有验收。主 agent 不把 subagent 声称的测试结果当作最终验收证据。
8. 仅由主 agent 显式暂存并按独立子计划依次提交；仅由主 agent 撰写最终 `ai-work/executor/WP{n}-executor.md`，汇总拆分映射、各 subagent 结果、集成验证、提交哈希、偏差与遗留问题。

入口协调 agent 等待主 agent 完成并转述其最终执行结果。若无法创建指定模型的主 agent 或 subagent，明确报告阻塞，不得静默替换模型、effort 或改为入口 agent 直接实施。

## 用途

本 skill 用于执行一份 WP 实施计划（由 planner 产出）：由主 agent 拆分、委派并整合代码实现与测试，逐项验证通过后把执行结果写入阶段报告文件。支持两类任务：

- **实现任务**：按计划新增/修改代码与测试（首次实施）；
- **修复任务**：根据 reviewer 的审查报告修复缺陷并重新验证（修复轮次）。

计划文件与审查报告是执行依据；本 skill 只规定执行流程与纪律，不替代其内容。

执行 agent 的边界：

- 严格按计划/审查结果执行，不擅自扩大或修改范围；发现问题先停下报告，不静默改计划。
- 每个独立子计划由对应 subagent 完成并经主 agent 验收后，即由主 agent 在**独立分支**上提交一次（见“阶段工作区与提交”）；绝不提交到主分支；不自动 push。
- 本阶段所有改动都在 planner 创建的独立 worktree/分支中完成；**不得在主分支（main）内做任何修改或提交**。
- 绝不修改 `third_party/open-r1/`；所有 Open-R1 访问经 `code_verifier.training.open_r1_adapter`。
- 不修改审查报告文件（`ai-work/reviewer/WP{n}-review.md`）——它归审查方所有。
- 不写入 `proceedings.md`——阶段完成记录由最终审查方在审查通过并合并后统一写入。

## 输入

执行前读取以下文件：

1. **计划文件**：任务中给出的路径（如 `ai-work/planner/WP1-plan.md`）。若未给出，取 `ai-work/planner/` 下编号最大的 `WP{n}-plan.md`，并在报告中注明。
2. **审查报告**（仅修复任务）：`ai-work/reviewer/WP{n}-review.md`，取其最新轮次内容；问题清单是修复依据。实现任务无此输入。
3. `PROJECT_SPEC_Open-R1_CodeVerifier.md`：精读计划中引用的章节（至少 §6 模块边界、§7 数据、§8 执行器、§9 解析器、§10 奖励、§17 CLI、§19 测试计划、§20 WP 注册表）。
4. `proceedings.md`：了解前置阶段状态与已记录决策（只读，不修改）。
5. `src/` 与 `tests/` 当前代码：确认改动基线，避免重复实现已存在的能力。

## 阶段报告文件与重置规则

本阶段所有结果写入**同一文件** `ai-work/executor/WP{n}-executor.md`：

- 文件结构：开头是"基于 plan 的执行结果"；之后每次 review 后的"代码修复报告"依次追加在末尾，不覆盖前面的内容。
- **阶段识别**：文件头部记录所依据的计划文件路径。开始任务时，若文件记录的 plan 与当前计划文件不同（或文件不存在），视为进入新阶段——先清空文件，再写入当前阶段内容。
- 每次写文件时，先确认目标目录 `ai-work/executor/` 存在，不存在则创建。

## 阶段工作区与提交

1. **确认阶段工作区**：本阶段工作目录为 planner 创建的分支 worktree（默认 `.worktrees/wp{n}` 或 `.worktrees/wp{n}-{sub}`，以计划元信息为准）。若未指定，运行 `git worktree list` 定位该分支对应的 worktree；找不到则停止并报告——分支与 worktree 由 planner 创建，executor 不自行创建。
2. **分支校验（必须，任务开始与每次提交前）**：运行 `git branch --show-current`，必须等于计划元信息记录的分支名（如 `feat/wp3-c`）；若当前在 `main` 或其它分支，先 `git switch <分支名>`；校验不通过时禁止任何修改与提交。
3. **禁止在主分支修改**：所有代码、测试、配置、报告文件的写入与提交都必须在分支上进行；绝不在 main 上修改或提交。
4. **每子计划提交**：每个 subagent 完成后，由主 agent 检查其改动并通过对应验证，再依次提交：先 `git status` 确认范围，显式 `git add` 该子计划涉及路径（**不用 `git add -A`**），提交消息用 Conventional Commits（如 `feat: add data schema and validation`），提交到当前阶段分支。
5. **报告随提交**：阶段报告文件 `ai-work/executor/WP{n}-executor.md` 随对应实现/修复提交一起（或单独一条 docs 提交）进入分支。
6. **提交失败处理**：hook 拒绝、冲突或误暂存时停下报告，不使用 `--no-verify`、`--force` 等绕过手段。
7. 不自动 push；合并回主分支由 reviewer 在审查通过后执行。

## 执行前检查

通读计划全文，确认每个实施步骤都包含：目标文件、函数/类签名、主要功能、测试方案、验证命令与通过标准。

- 若计划缺失关键信息（如没有目标文件、没有通过标准），**停止并报告缺失项**，不要自行猜测补全。
- 若计划引用了不存在的文件或符号，先对照当前代码核实；确实不存在则停下报告，等待计划修订。
- 修复任务须额外确认审查报告包含问题清单（严重级别、位置、问题、建议）；缺失则停止并报告。

## 执行协议

实现任务按主 agent 生成的独立子计划执行；每个 subagent 对其子计划循环「实现 → 写测试 → 验证 → 修正」，主 agent 负责最终整合与验证：

1. **实现**：只改动该步骤指定的目标文件。新增/修改的符号与签名以计划为准；计划从规格中引用的接口（如 `ExecutionStatus`、`ParseResult`、`CodeExecutor`、`compute_code_rewards`）必须逐字保留，不得改名或改签名。
2. **测试**：按计划的“测试方案”在指定测试文件添加指定测试函数；断言针对规格与计划定义的行为。
3. **验证**：原样运行该步骤的“验证命令与通过标准”（如 `make lint`、`make test`、具体 CLI 调用），核对通过标准后再进入下一步，不跳步。
4. **失败处理**（详见 `references/execution-workflow.md` 的决策表）：
   - 自己的实现或测试写错 → 修正实现，**不得修改测试预期来迁就实现**；
   - 测试预期与规格冲突 → 停止并报告冲突（引用规格章节与测试断言）；
   - 计划本身不可执行 → 停止并报告，不自行改写计划；
   - 外部环境限制（依赖缺失、无 GPU 等）→ 如实记录；若计划给出替代路径则执行，否则停下报告。
5. **横切规则**：业务逻辑不硬编码路径/模型名/设备/密钥/数据位置；训练与评测配置走 YAML 或 CLI；新模块带类型标注、docstring、单元测试；不触碰与本 WP 无关的代码。

## 修复任务流程（根据审查结果修复）

修复任务不重跑全部计划步骤，按审查报告的问题清单逐项处置：

1. **确定修复范围**：默认修复全部“阻断 / 主要 / 次要”问题；“建议”级别只在任务明确要求时处理。未处理的条目必须在报告中写明原因。
2. **逐项定位与修复**：按问题的“位置”定位代码，结合“问题”与“建议”做最小改动；只修改与本 WP 相关且被审查点名的代码，不顺手改其它代码。
3. **异议处理**：认为某条审查意见与规格或代码事实不符时，不静默忽略，也不盲目“修复”：对确实有效的问题照常修复；对存疑条目在报告中记录异议与证据（引用规格章节或代码位置），交人工仲裁——审查方会在下一轮复审中核验；对无法按描述复现的条目，记录复现尝试与证据并标注“无法复现”，同样交下一轮复审核验。
4. **重新验证**：先运行受影响模块的验证命令，再完整运行 `make lint`、`make test` 及计划的总体验收；确认修复未引入回归。
5. **提交**：修复完成并通过复测后，按“阶段工作区与提交”规则提交（`fix: ...`）到同一独立分支。
6. **记录修复**：在阶段报告文件 `ai-work/executor/WP{n}-executor.md` 末尾追加"代码修复报告"（修复的问题清单、改动位置、复测结果、异议项），不覆盖执行结果；**不修改审查报告**。

## 总体验收

两类任务共用同一验收口径：

1. 运行计划的“总体验收与测试计划”（§5 风格）：`make lint` 全绿（ruff check / ruff format --check / mypy）、`make test` 全绿、WP 特有指标达标。
2. 修复任务额外以“审查报告问题清单已全部处置（修复或已记录异议）”为前提。
3. 只记录**实际运行过**的命令与真实结论，不得根据代码阅读推断测试通过。
4. 存在未通过的验收项时不得标记完成：先修复；无法修复则如实报告。

## 收尾与报告

1. 将完成报告写入 `ai-work/executor/WP{n}-executor.md`：实现任务写入“基于 plan 的执行结果”（执行的计划文件、新建/修改的文件清单、新增的函数/类清单、每个验证命令的实际结论、偏离计划的点及原因、已知限制、下一步建议）；修复任务在文件末尾追加"代码修复报告"。
2. 所有报告随独立分支提交；不写入 `proceedings.md`（该文件由最终审查方在阶段通过、合并回主分支后写入简洁记录）。

## 自检清单

完成前逐条核对：

- [ ] 只实现了计划/审查范围内内容，无越界改动；
- [ ] plan 已由主 agent 全文阅读并拆为互不冲突的子计划，每份子计划恰有一个 Luna/max subagent；
- [ ] 计划每个实现步骤都有对应代码与测试；
- [ ] 任务开始与每次提交前均确认当前分支为 planner 创建的分支（`feat/wp{n}` 或 `feat/wp{n}-{sub}`）；
- [ ] 未在主分支（main）上做任何修改或提交；
- [ ] 未修改测试预期来迁就实现；
- [ ] 遇到计划/规格冲突时停止并报告，而非静默偏离；
- [ ] `make lint` 与 `make test` 实际运行且全绿（或如实记录失败）；
- [ ] 未修改 `third_party/open-r1/`；
- [ ] 每个独立子计划均由主 agent 验收后在独立分支提交，未提交到主分支；
- [ ] 提交只含本步骤文件，未用 `git add -A` 混入无关改动；
- [ ] 未自动 push；
- [ ] 最终阶段报告仅由主 agent 写入 `ai-work/executor/WP{n}-executor.md`：含子计划/subagent 映射与结果，执行结果在前、修复报告追加在后；新阶段时已按 plan 覆盖内容清空重写；
- [ ] 未写入 `proceedings.md`；
- [ ] 修复任务：审查报告中的“阻断/主要/次要”问题均已修复，或已记录异议与证据；
- [ ] 修复任务：修复后重新运行了 `make lint` / `make test`，且未修改审查报告文件。
