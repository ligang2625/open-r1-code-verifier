# 计划模板：WP{n} Implementation Plan

> 使用说明：本模板用于产出下一个 WP 的实施计划。把 `{n}` 替换为实际 WP 编号，把 `[方括号]` 占位内容替换为实际内容，最后删除本说明。
> 消费约束：本计划由 executor 的 Codex 内部 agent 工作流消费。计划内容只依赖仓库文件与项目自带 `make` / pytest / CLI，不得把 Codex 编排工具、MCP 或其它 skill 写成实施依赖，也不得包含创建 agent 的步骤；agent 拆分与创建由 executor skill 负责。
> 分支约定：planner 为本阶段创建分支与 worktree（`.worktrees/wp{n}` 或 `.worktrees/wp{n}-{sub}`，分支 `feat/wp{n}` 或 `feat/wp{n}-{sub}`），executor 的主 agent 与 subagent 只在该分支上工作，不在 main 上修改。

# WP{n} 实施计划（[WP 名称，来自规格 §20]）

## 1. 元信息

| 项 | 值 |
|---|---|
| 目标 WP | WP{n}：[名称] |
| 规格依据 | `PROJECT_SPEC_Open-R1_CodeVerifier.md` §20 WP{n} |
| 前置 WP | WP{n-1}（proceedings.md 状态：已完成） |
| 分支 | `feat/wp{n}`（未拆分）或 `feat/wp{n}-{sub}`（拆分子阶段，planner 创建） |
| worktree | `.worktrees/wp{n}` 或 `.worktrees/wp{n}-{sub}` |
| 计划文件 | `ai-work/planner/WP{n}-plan.md` |
| 面向的执行 agent | executor 内部 agent；计划本身仅依赖仓库文件与项目命令 |

> 粒度约束：单个计划实施步骤最多 10 个、新模块最多 8 个；任务过多时拆分为多个阶段计划，每个计划文件视为独立阶段。

## 2. 目标与范围

### 目标（规格原文）

[§20 WP{n} 的“目标”原文]

### 交付（规格原文）

- [§20 交付清单逐条列出]

### 验收（规格原文）

- [§20 验收清单逐条列出]

### 范围内 / 范围外

- 范围内：[仅本 WP 的交付物]
- 范围外：[明确不做的内容，如后续 WP 功能、优化、规格外扩展]

## 3. 前置条件与约束

- proceedings.md 相关未完成项 / 决策 / 已知问题：[…]
- 项目硬性规则：不修改 `third_party/open-r1/`；Open-R1 访问仅经 `code_verifier.training.open_r1_adapter`；业务逻辑不硬编码路径/模型名/seed/密钥；配置走 YAML/CLI；新模块带类型标注 + docstring + 单元测试。
- 假设：[如 proceedings 缺失时的默认选择，或规格歧义处的默认决策，并注明依据]

## 4. 实施步骤

> 步骤按依赖顺序编号（数据 → 解析 → 执行 → 验证 → 奖励 → 评测 → 训练），每步可独立验证。每个步骤必须完整填写以下小节。

### 步骤 N：<一句话动作描述>

**目标文件**：`src/code_verifier/…/xxx.py`（新建 / 修改）

**新增 / 修改的符号**：

```python
def function_name(arg1: Type1, arg2: Type2) -> ReturnType:
    """<主要功能一句话>"""
```

或类形式：

```python
class Xxx:
    def method_a(self, ...) -> ...: ...
```

**主要功能**：说明输入、输出、行为、错误处理，以及被谁调用 / 调用谁，如何与现有代码衔接。

**配置 / CLI 变更**：如涉及，给出新增 YAML 字段（名称、类型、默认值）或 CLI 子命令（命令名、参数、全局参数支持）。

**测试方案**：

- 测试文件：`tests/unit/test_xxx.py`
- 新增测试函数：
  - `test_xxx_<场景>`：断言 …
  - `test_xxx_<场景>`：断言 …
- 覆盖的规格边界（对应 §19.1 / 目标 WP 章节）：[…]

**验证命令与通过标准**：

```bash
make lint
make test
# 如有 CLI 行为，给出具体命令，例如：
.venv/bin/code-verifier xxx --config configs/xxx.yaml --help
```

通过标准：[可测量判定，如“ruff/mypy 全绿；pytest 全绿且新增 N 个用例被收集；CLI 输出 X”]

### 步骤 N+1：…

（重复上述结构）

## 5. 总体验收与测试计划

- 单元测试汇总：[本 WP 全部新增测试文件，及其与 §19.1 的对应关系]
- 集成测试：[必须跑通的端到端场景，对应 §19.2，如 20 题 fixture、mock executor 集成、小模型生成等]
- 数据泄漏检查（如适用）：[§7.4 各项检查的落地方式]
- 最终通过标准：
  - [ ] §20 WP{n} 验收清单逐条通过
  - [ ] `make lint` 全绿（ruff check / ruff format --check / mypy）
  - [ ] `make test` 全绿
  - [ ] [WP 特有的可测量指标，如三层测试无重复、eval hidden 不出现在训练 artifact]

## 6. 风险与注意事项

- [对应 §24 风险清单的条目，如执行器安全、数据质量、泄漏风险]
- [proceedings 记录的已知问题]

## 7. 关联文档索引

- `PROJECT_SPEC_Open-R1_CodeVerifier.md`：§[实际用到的章节，如 6 / 7 / 8 / 10 / 17 / 19 / 20]
- `proceedings.md`：WP{n-1} 小节及与本 WP 相关记录

---

# 风格示例（以 WP1 为例，展示“步骤”应有的颗粒度）

### 示例步骤：新建数据 schema 模块

**目标文件**：`src/code_verifier/data/schema.py`（新建）

**新增 / 修改的符号**：

```python
@dataclass(frozen=True)
class TestCase:
    input: Any
    expected: Any


@dataclass(frozen=True)
class CodeProblem:
    problem_id: str
    source: str
    split: str
    prompt: str
    function_name: str
    function_signature: str
    starter_code: str | None
    visible_tests: list[TestCase]
    train_hidden_tests: list[TestCase]
    eval_hidden_tests: list[TestCase]
    reference_solution: str | None
    sft_response: str | None
    metadata: dict[str, Any]


def validate_problem(problem: CodeProblem) -> None: ...
```

**主要功能**：定义 §7.1 的不可变数据模型；`validate_problem` 校验必填字段、split 枚举值、三层测试约束，并抛出带字段信息的异常；为后续 prepare / leakage 模块提供唯一数据入口。

**测试方案**：

- 测试文件：`tests/unit/data/test_schema.py`
- 新增测试函数：
  - `test_valid_problem_passes`：合法样本不抛异常；
  - `test_missing_problem_id_rejected`：缺字段抛异常；
  - `test_invalid_split_rejected`：非法 split 抛异常；
  - `test_frozen_instances_immutable`：尝试修改字段抛 FrozenInstanceError。

**验证命令与通过标准**：

```bash
make lint
make test
```

通过标准：ruff / mypy / pytest 全绿，新增 4 个用例被收集。

> 示例仅供展示颗粒度；实际计划必须基于规格原文与 proceedings 状态生成，不得照抄示例。
