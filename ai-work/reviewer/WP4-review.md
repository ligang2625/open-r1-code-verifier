# WP4-a 独立审查报告

- **审查计划**：`ai-work/planner/WP4-a-plan.md`
- **阶段分支**：`feat/wp4`
- **阶段 worktree**：`.worktrees/wp4`
- **本轮**：R1（首轮审查）
- **审查日期**：2026-08-06

## R1：首轮独立审查

### 1. 审查范围与方法

- 计划文件：`ai-work/planner/WP4-a-plan.md`
- executor 报告：`ai-work/executor/WP4-executor.md`
- 规格依据：`PROJECT_SPEC_Open-R1_CodeVerifier.md` §6.2、§10.1–§10.6、§19、§20、§21，以及计划中列出的 WP4-a 明确实现决策与通过标准。
- 审查方式：逐条核对计划、阅读 Verification 源码与测试、核查分支提交范围、独立运行静态检查/全量测试/定向测试/CLI，并使用一次性只读命令验证边界状态。
- 审查纪律：未修改 `src/`、`tests/` 或 `third_party/open-r1/`；本轮只新增本审查报告。

### 2. 计划完成度核验（逐条对照 plan）

| 计划步骤 / 交付项 | 计划要求 | 状态 | 证据 |
|---|---|---|---|
| 步骤 1：结构化验证结果 | 新建 `VerificationResult`、合同校验、安全 mapping 与单元测试 | 部分完成 | `src/code_verifier/verification/result_types.py:17-181` 与 `tests/unit/verification/test_result_types.py:100-306` 已实现主体；但 `validate_verification_result()` 未禁止 `parsed=True/executed=True/status=PARSE_ERROR`，见问题 M1。 |
| 步骤 2：输入规范化 | 严格校验函数名、单测试层与资源限制；输入失败不得调用 parser/executor | 已完成 | `src/code_verifier/verification/verifier.py:27-104`；`tests/unit/verification/test_verifier.py:118-276`。空测试、非法 JSON、UTF-8、bool-as-int 与副作用顺序均有有效断言。 |
| 步骤 3：统一验证器与失败汇总 | parser/executor 唯一入口、异常 fail-closed、timeout/sandbox 区分、提前停止归因 | 部分完成 | `src/code_verifier/verification/verifier.py:107-252` 与 `tests/unit/verification/test_verifier.py:279-518` 覆盖主要路径；但 executor 返回 `PARSE_ERROR` 时未 fail-closed，破坏 parser taxonomy 唯一性，见问题 M1。 |
| 步骤 4：公共 API 与 Mock 集成 | 仅导出稳定 API；覆盖 passed/partial/timeout/parse/sandbox 五种场景 | 已完成 | `src/code_verifier/verification/__init__.py:3-19`；`tests/integration/test_wp4a_verifier_pipeline.py:60-207`。集成测试验证调用顺序、FIFO、不执行候选代码、JSON-safe mapping 与 payload 字段隔离。 |
| 步骤 5：文档与独立验收 | 更新 README/AGENTS；不扩展 CLI/配置/依赖；运行全部验收 | 部分完成 | `README.md:284-306`、`AGENTS.md:115` 与独立命令结果均符合阶段边界；但新生产模块 `src/code_verifier/verification/__init__.py` 缺少计划硬性要求的 future annotations import，见问题 m1。 |
| 新增文件清单 | Verification 源码、单元测试、Mock 集成测试 | 已完成 | 分支提交记录仅新增计划列出的 `src/code_verifier/verification/**`、`tests/unit/verification/**`、`tests/integration/test_wp4a_verifier_pipeline.py` 及阶段报告。 |
| 修改文件清单 | 仅修改 `README.md`、`AGENTS.md` | 已完成 | `git log --oneline --name-status main..HEAD` 显示生产/测试范围外仅修改上述两个文档。 |
| 明确不修改项 | 不修改 execution/parser/data/training/config/Makefile/pyproject/third-party/proceedings，不创建 rewards | 已完成 | 分支提交范围无这些路径；`src/code_verifier/rewards/` 不存在；Verification 源码搜索无 `eval_hidden_tests`、`test_layer`、`exec(` 或 `subprocess`。 |

### 3. 交付与验收核验

| 验收项 | 状态 | 证据 |
|---|---|---|
| §20 WP4 的 verifier 子交付 | 部分通过 | 统一 API、结果类型和测试已交付，但 M1 使 parse-error 状态合同仍不闭合。 |
| 只接收一个调用方选择的测试列表 | 通过 | `verify_completion()` 签名为单一 `tests` 参数，`src/code_verifier/verification/verifier.py:210-216`；无测试层 selector。 |
| 0 测试在 parser/executor 前失败 | 通过 | `_normalize_tests()` 在 `verifier.py:58-81` fail-closed；`test_verifier.py:244-276` 验证 parser/executor 调用均为 0。 |
| parser 是唯一提取入口，executor 是唯一执行入口 | 未完全通过 | 调用路径本身符合 `verifier.py:218-239`；但 executor 可返回 `PARSE_ERROR` 并被接受为 executed result，导致 parser taxonomy 不再唯一，见 M1。 |
| parse/timeout/sandbox/exception 状态符合计划 | 未通过 | 正常覆盖均通过；executor-returned `PARSE_ERROR` 产生自相矛盾状态，见 M1 实证。 |
| 通过率、failure count 守恒且数值有限 | 通过 | `result_types.py:94-112`、`verifier.py:107-131`；独立 34 项定向测试通过。 |
| mapping 严格 JSON-safe 且无 completion/code/tests/metadata 字段 | 通过 | `result_types.py:164-181`；`test_result_types.py:100-122,238-255,291-306` 与集成测试 `test_wp4a_verifier_pipeline.py:164-175`。嵌套 stdout/stderr 按计划沿用 WP3 有界执行结果合同。 |
| `make lint` | 通过 | 恢复 worktree 本地忽略的 `.venv -> ../../.venv` 链接后，Ruff check/format 与 strict mypy 全绿，54 个源文件无问题。 |
| `make test` | 通过 | `478 passed, 3 skipped`；3 个 skip 均为既有真实 Piston 测试。 |
| Verification 定向测试 | 通过 | `34 passed, 0 failed, 0 skipped`。 |
| CLI 未扩展 | 通过 | `.venv/bin/code-verifier --help` exit 0，仅有 `record-environment`、`prepare-data`、`check-data`、`parse-code`、`execute-batch`。 |
| 无新增配置、依赖或越界代码 | 通过 | 分支文件范围与计划一致；未修改 `pyproject.toml`、Makefile、configs、execution/parser/data/training/third-party/proceedings。 |
| executor 阶段报告已记录 | 通过 | `ai-work/executor/WP4-executor.md` 存在且覆盖 5 个步骤、命令结果、配置影响与后续边界。 |
| executor 未修改 `proceedings.md` | 通过 | 分支提交记录无 `proceedings.md`。 |

### 4. Executor 报告声明核验

| Executor 声明 | 核验状态 | 证据 |
|---|---|---|
| 5 个步骤全部实现 | 部分核实 | 文件与测试均存在，但状态合同存在 M1，不能认定功能完整。 |
| `make lint` 全绿 | 核实通过 | 独立重跑全绿。首次原命令因 worktree `.venv` 链接缺失未启动；恢复 executor 报告所述本地链接后通过。 |
| `make test` 为 478 passed、3 skipped | 核实通过 | 独立重跑得到相同结果。 |
| Verification 定向测试 34 passed | 核实通过 | 独立重跑得到 `34 passed`。 |
| CLI 未新增命令 | 核实通过 | 独立运行 help，命令集合与报告一致。 |
| parser/executor 唯一入口及失败状态准确 | 与事实部分不符 | 代码没有旁路执行，但 executor-returned `PARSE_ERROR` 被接受为 parsed/executed 状态，见 M1。 |
| 无越界改动 | 核实通过 | 分支提交路径符合计划。 |

### 5. 问题清单

| 严重级别 | 位置 | 问题 | 依据 | 建议 |
|---|---|---|---|---|
| 主要（M1） | `src/code_verifier/verification/result_types.py:114-161`；`src/code_verifier/verification/verifier.py:183-207,232-252` | 验证合同允许 executor 返回 `ExecutionStatus.PARSE_ERROR` 后生成 `status=parse_error, parsed=True, executed=True, parse_error_type=None` 的合法 `VerificationResult`。这使 parse error 不再只代表 parser 失败，并会使 WP4-b 按 `status is PARSE_ERROR` 读取 invalid-format penalty 时误判已成功解析和执行的样本。当前测试未覆盖此 executor 状态。 | 计划要求 parser 是唯一解析入口（plan `429-447`），parse failure 固定为 `parsed=False/executed=False`（plan `264-268`），WP4-b 的 invalid-format 分量直接读取 `status is PARSE_ERROR`（plan `699-706`）。独立实证命令构造合法 `ExecutionResult(PARSE_ERROR)` 后输出：`{'status': 'parse_error', 'parsed': True, 'executed': True, ...}`。 | 在 Verification 边界拒绝任何执行结果中的 `PARSE_ERROR`（顶层及逐测试状态），将其视为畸形 executor result 并 fail-closed 为 sanitized `SANDBOX_ERROR`；同时在 `validate_verification_result()` 强制 `status is PARSE_ERROR` 当且仅当 `parsed=False`，并新增直接合同测试与 `verify_completion()` 回归测试。 |
| 次要（m1） | `src/code_verifier/verification/__init__.py:1-3` | 新生产模块未包含 `from __future__ import annotations`。当前文件没有本地注解，因此无运行时缺陷，但不符合本计划的横切硬性规则。 | plan `146-153` 明确要求新模块使用 future annotations；同阶段 `result_types.py` 与 `verifier.py` 已遵守。 | 在模块 docstring 后添加 `from __future__ import annotations`，并保持格式检查通过。 |

### 6. 独立测试结果

- 初始命令：`make lint` → 未实际运行检查，原因是阶段 worktree 缺少 executor 报告中所述的本地忽略 `.venv` 链接，报错 `.venv/bin/python: No such file or directory`。
- 环境恢复：创建本地忽略链接 `.venv -> ../../.venv`，未修改仓库跟踪文件。
- 命令：`make VENV=../../.venv lint` → Ruff check passed；54 files formatted；strict mypy success。
- 命令：`make VENV=../../.venv test` → `478 passed, 3 skipped in 3.85s`。
- 命令：`../../.venv/bin/python -m pytest tests/unit/verification tests/integration/test_wp4a_verifier_pipeline.py` → `34 passed in 0.06s`。
- 命令：`.venv/bin/code-verifier --help` → exit 0；未出现 verifier/reward/training/evaluation 新 CLI。
- 边界实证：构造 executor 返回合法 `ExecutionResult(status=PARSE_ERROR, ...)`，`verify_completion()` 返回 `parsed=True, executed=True, status=parse_error`，确认 M1 可复现。
- 范围核查：`git log --oneline --name-status main..HEAD` 仅显示计划内源码、测试、文档和阶段报告；Verification 生产代码搜索无 host execution/subprocess/test-layer selector。

### 7. 结论

- **结论：需修改**。
- 理由：独立静态检查和全部测试均通过，但 M1 是面向后续 reward 的主要状态合同缺陷，违反 parser taxonomy 唯一性，并可导致 invalid-format 分量误判。根据审查规则，存在主要问题不得判定通过。
- 本轮未合并 `feat/wp4`，未更新 `proceedings.md`，未清理 worktree，未 push。
- 后续复审必须逐条核验 M1 与 m1，完整重跑 lint、全量测试、Verification 定向测试及 CLI。
- 另需在最终通过并合并前处理主工作区的未跟踪 `ai-work/planner/WP4-a-plan.md`；该路径与分支新增文件重叠，即使内容相同，也可能阻止 merge 覆盖未跟踪文件。

## R2：修复后复审

### 1. 复审范围与方法

- 复审基准：R1 问题 M1、m1，以及 R1 中标记为“部分完成 / 未完全通过”的计划与验收项。
- 修复声明来源：`ai-work/executor/WP4-executor.md` 的“代码修复报告（WP4-a R1）”。
- 独立方法：代码阅读、回归测试、原 M1 一次性复现命令、CLI 验证，以及修复提交范围核查。

### 2. 上轮问题核验

| 上轮问题 | 严重级别 | 状态 | 证据 |
|---|---|---|---|
| M1：executor 可注入 `PARSE_ERROR`，产生 `parsed=True/executed=True/status=parse_error` | 主要 | 已修复 | `src/code_verifier/verification/result_types.py:131-148` 强制 parsed result 不得为 `PARSE_ERROR`，且 executed result 的顶层/逐测试状态不得含 `PARSE_ERROR`；`src/code_verifier/verification/verifier.py:232-251` 在 executor 接收边界拒绝同类状态并 fail-closed。新增测试见 `tests/unit/verification/test_result_types.py:238-254`、`tests/unit/verification/test_verifier.py:466-487`。独立复现原 M1 时现返回 `status=sandbox_error, parsed=True, executed=False, infrastructure_failure=True`。 |
| m1：Verification 包缺少 future annotations | 次要 | 已修复 | `src/code_verifier/verification/__init__.py:1-5` 已在模块 docstring 后加入 `from __future__ import annotations`。 |

### 3. 计划完成度与验收复核

| R1 未通过项 | R2 状态 | 证据 |
|---|---|---|
| 步骤 1：结构化验证结果合同 | 已完成 | parse-error 跨字段合同现闭合；直接合同回归测试通过。 |
| 步骤 3：统一验证器失败状态汇总 | 已完成 | parser-only taxonomy 恢复；executor-side `PARSE_ERROR` 统一转为 sanitized `SANDBOX_ERROR`。 |
| 步骤 5：新模块横切规则 | 已完成 | `verification/__init__.py` 已符合 future annotations 要求。 |
| parser 是唯一解析入口 / parse 状态语义 | 通过 | 原 M1 独立复现已无法产生 executed parse error；parser failure 仍保持 `parsed=False/executed=False/PARSE_ERROR`。 |
| WP4-a 最终测试标准 | 通过 | lint、全量 CPU 回归、37 项 Verification 定向测试与 CLI 均独立通过。 |

### 4. 新问题与范围检查

- 未发现修复引入的新阻断、主要或次要问题。
- 修复只涉及 Verification 结果合同、verifier、对应单元测试、包 future import 与 executor 修复报告。
- 分支中额外存在若干 `docs: sync skills with main updates` 提交；逐文件内容哈希核对确认这些 skill 文件与当前 main 完全一致，因此不存在净越界内容变化。
- `third_party/open-r1/**`、execution/parser/data/training、配置、依赖、CLI 定义和 `proceedings.md` 均未因本轮修复改变。

### 5. 独立测试结果

- `make VENV=../../.venv lint` → Ruff check passed；54 files already formatted；strict mypy success。
- `make VENV=../../.venv test` → `481 passed, 3 skipped`；3 个 skip 均为既有真实 Piston 测试。
- `../../.venv/bin/python -m pytest tests/unit/verification tests/integration/test_wp4a_verifier_pipeline.py` → `37 passed, 0 failed, 0 skipped`。
- `../../.venv/bin/python -m code_verifier.cli --help` → exit 0；仍仅有 `record-environment`、`prepare-data`、`check-data`、`parse-code`、`execute-batch`。
- 原 M1 一次性复现：executor 返回顶层/逐测试 `PARSE_ERROR` 后，验证结果为 sanitized `SANDBOX_ERROR`，`parsed=True`、`executed=False`、`pass_rate=0.0`、`execution_result=None`。

### 6. 结论

- **结论：通过**。
- R1 的主要问题 M1 与次要问题 m1 均已完整处置；无新增阻断或主要问题，计划内验收项全部通过。
- 按 `wp-plan-reviewer` 流程，本轮审查提交后可将 `feat/wp4` 合并回 main，并只登记 **WP4-a 子阶段完成**；WP4-b reward 仍未实现，不得将 WP4 整体标记为完成。
- 最终合并提交：`5e6f590caa31631c046d3107f1d1edcf1d623c66`（`feat: complete WP4-a unified verifier`）。
- 合并后 main 再次通过 `make lint` 与 `make test`（`481 passed, 3 skipped`）。
