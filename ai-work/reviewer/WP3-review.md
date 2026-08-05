# WP3-a 独立审查报告

- **计划文件**：`ai-work/planner/WP3-a-plan.md`
- **executor 报告**：`ai-work/executor/WP3-executor.md`
- **审查轮次**：R1
- **审查日期**：2026-08-05
- **审查分支 / worktree**：`feat/wp3` / `.worktrees/wp3`
- **审查方式**：计划与规格核对、源码与测试阅读、独立静态检查、全量回归、额外恶意输入探针

## 1. 审查范围与基准

本轮仅审查 WP3-a“安全执行器基础合同与 Mock 基线”，不把真实沙箱、资源隔离、批量执行或完整 WP3 验收纳入本子阶段通过条件。审查基准为：

- `PROJECT_SPEC_Open-R1_CodeVerifier.md` §8.1–§8.5、§20、§21；
- `ai-work/planner/WP3-a-plan.md` 的公开接口、合同校验、Mock 行为、测试与文档验收项；
- `skills/wp-plan-reviewer/references/review-checklist.md` 的通用与执行器检查项。

审查期间未修改 `src/`、`tests/`、`third_party/open-r1/` 或 `proceedings.md`。

## 2. 交付与验收核验

| 验收项 | 状态 | 证据 |
|---|---|---|
| `ExecutionStatus`、`TestCaseResult`、`ExecutionResult`、`CodeExecutor` 与规格 §8.3 一致 | 通过 | `src/code_verifier/execution/base.py:14-64` 与规格 `PROJECT_SPEC_Open-R1_CodeVerifier.md:638-678` 一致；枚举、字段顺序和 Protocol 签名均匹配。 |
| 请求与结果合同校验拒绝非法输入，并统一抛出 `ExecutionContractError` | **未通过** | `src/code_verifier/execution/base.py:71-72` 直接对任意大小整数调用 `math.isfinite()`；`base.py:101-105` 仅捕获 `SchemaError`。独立探针中循环 JSON 值抛 `RecursionError`，超大正整数 timeout 抛 `OverflowError`。 |
| 合同异常不回显代码、测试输入、expected、stdout/stderr | **未通过** | `src/code_verifier/execution/base.py:101-105` 原样转发 `SchemaError` 文本；探针 `{"input": {"HIDDEN_SECRET_KEY": object()}}` 的异常文本包含 `HIDDEN_SECRET_KEY`，违反计划 `WP3-a-plan.md:315,526,560` 的隐藏测试内容保护要求。 |
| `execution_result_to_mapping()` 字段稳定且可 JSON 序列化 | 部分通过 | 常规合法结果通过 `tests/unit/execution/test_base.py:295-320` 与专项测试；但其前置校验仍受上述超大整数未处理异常影响，不能视为所有合同边界已完成。 |
| `MockExecutor` FIFO、调用记录、防御性复制、耗尽行为与不执行代码 | 通过 | `src/code_verifier/execution/mock.py:29-74`；专项测试 80 项全部通过；源码未发现 `exec(`、`eval(`、`compile(` 或 `subprocess`。 |
| parser → Data mapping → Mock → JSON mapping 集成闭环 | 通过 | `tests/integration/test_wp3a_mock_execution.py:23-59`；专项测试通过。 |
| README / AGENTS 明确 Mock 不提供真实沙箱安全 | 通过 | `README.md:3-5,135-174`；`AGENTS.md:18-20,85-89`。未声称 WP3 整体完成。 |
| 静态检查与全量回归 | 通过（使用现有主仓库虚拟环境覆盖 `VENV`） | `make lint VENV=/home/dzy/open-r1-code-verifier/.venv`：Ruff、format、strict Mypy 全绿；`PYTHONPATH=src make test VENV=/home/dzy/open-r1-code-verifier/.venv`：257 passed。 |
| 计划原样命令 `make lint` / `make test` 可在当前 worktree 直接运行 | 无法按原样复现 | 当前 worktree 无 `.venv/bin/python`，两条命令均以 Error 127 失败。该项是当前审查环境状态说明；使用显式 `VENV` 后代码检查与测试可复现。 |
| 配置、依赖与固定上游未变 | 通过 | 分支 worktree 无未提交修改；固定上游 `git -C third_party/open-r1 rev-parse HEAD` 输出 `1416fa0cf21595d2083b399a2a0bbddd7f6e9563`；计划范围内未发现配置或依赖修改。 |

## 3. executor 报告声明核验

| executor 声明 | 状态 | 核验结果 |
|---|---|---|
| 公开合同、Mock、集成测试和文档已实现 | 核实通过 | 文件、接口和常规测试与报告一致。 |
| `make lint`、专项 80 tests、全量 257 tests、导入 smoke 通过 | 部分核实 | 使用显式主仓库 `VENV` 与 `PYTHONPATH=src` 可复现对应结果；当前 worktree 缺少 `.venv`，原样 `make lint` / `make test` 不可运行。 |
| “严格执行请求与结构化结果校验”已完成，且无计划偏离 | **与事实不符** | 循环 JSON 值和超大整数不会收敛为 `ExecutionContractError`；隐藏测试对象键名会出现在错误文本。核心合同验收仍有缺口。 |
| Mock 不执行代码，未新增宿主机执行逻辑 | 核实通过 | 源码检索无直接执行 API；恶意代码字符串测试通过。 |
| WP3 整体仍为部分完成 | 核实通过 | README、AGENTS 与 executor 报告均保持该边界。 |

## 4. 问题清单

### P1 — 主要：非法请求可逃逸为未处理的 `RecursionError` / `OverflowError`

- **位置**：`src/code_verifier/execution/base.py:71-72,101-108,121-122,159-165`
- **现象**：
  - 自引用 list 作为 `tests[0].input` 时，`validate_json_value()` 递归直至抛出 `RecursionError`；`validate_execution_request()` 只捕获 `SchemaError`，未转换为 `ExecutionContractError`。
  - `timeout_seconds=10**1000` 时，`math.isfinite()` 抛出 `OverflowError`，同样逃逸公共合同。
  - 同一 `_is_finite_number()` 也用于 per-test/aggregate runtime 与 pass rate，因此结果合同存在相同异常面。
- **依据**：计划 `WP3-a-plan.md:274-281,282-292,314-315,347` 要求非法请求/结果统一得到 `ExecutionContractError`，不得产生未处理 traceback。
- **影响**：调用方无法只处理公开合同异常；畸形或极端输入可以中断 verifier/reward 编排，破坏执行边界的确定性。
- **建议**：
  1. 对 JSON 校验增加循环/深度保护，至少捕获并转换 `RecursionError`，更稳妥的做法是使用显式 visited/path 或限定最大嵌套深度；
  2. 重写有限数判断，避免对任意大小 int 直接调用 `math.isfinite()`，并明确超出可表示范围时统一抛 `ExecutionContractError`；
  3. 为 request timeout、per-test runtime、aggregate runtime、pass rate 增加超大整数与递归结构回归测试。

### P2 — 主要：合同错误文本泄漏隐藏测试中的用户自定义对象键名

- **位置**：`src/code_verifier/execution/base.py:101-105`；上游消息来源 `src/code_verifier/data/schema.py:127-134`
- **现象**：execution 层将 `SchemaError` 文本原样包装。对于 `tests[0].input={"HIDDEN_SECRET_KEY": object()}`，实际异常为：

  ```text
  ExecutionContractError tests[0].input.HIDDEN_SECRET_KEY contains unsupported JSON value type object
  ```

- **依据**：计划 `WP3-a-plan.md:315,526,560` 明确要求异常仅包含索引、固定字段名和错误类型，不包含 input / expected 内容；隐藏测试层属于敏感实验资产。
- **影响**：一旦该异常进入训练或调试日志，测试输入中的键名可被逐步泄漏。按照审查规则，测试内容泄漏不能判定通过。
- **建议**：execution 边界不要透传包含用户控制路径片段的 `SchemaError`。将错误净化为固定格式，例如 `tests[0].input contains an invalid JSON value`，并为字符串值、嵌套键名、expected 路径分别加入“不回显 sentinel”测试。

## 5. 独立测试结果

### 5.1 原样计划命令

```text
make lint
→ 失败：make: .venv/bin/python: No such file or directory（Error 127）

make test
→ 失败：make: .venv/bin/python: No such file or directory（Error 127）
```

### 5.2 使用现有虚拟环境复现代码检查

```text
make lint VENV=/home/dzy/open-r1-code-verifier/.venv
→ All checks passed
→ 37 files already formatted
→ Success: no issues found in 37 source files

PYTHONPATH=src /home/dzy/open-r1-code-verifier/.venv/bin/python -m pytest \
  tests/unit/execution tests/integration/test_wp3a_mock_execution.py
→ 80 passed

PYTHONPATH=src make test VENV=/home/dzy/open-r1-code-verifier/.venv
→ 257 passed

PYTHONPATH=src /home/dzy/open-r1-code-verifier/.venv/bin/python -c \
  "from code_verifier.execution import CodeExecutor, ExecutionResult, ExecutionStatus, MockExecutor, TestCaseResult; print(ExecutionStatus.PASSED.value)"
→ passed
```

### 5.3 额外合同边界探针

```text
cycle RecursionError maximum recursion depth exceeded while calling a Python object
huge_timeout OverflowError int too large to convert to float
secret_key ExecutionContractError tests[0].input.HIDDEN_SECRET_KEY contains unsupported JSON value type object
```

## 6. 结论

- **审查结论：不通过**。
- 常规接口、Mock 行为、文档、静态检查和 257 项回归均表现正常，但 WP3-a 的核心交付之一是稳定、无泄漏的执行合同边界。当前存在两个“主要”问题：非法输入可逃逸公开异常类型，且异常文本可泄漏隐藏测试键名。
- executor 应修复 P1、P2，增加对应回归测试，并重新运行 `make lint`、专项测试和 `make test` 后申请复审。
- 本轮禁止合并 `feat/wp3`，不修改 `proceedings.md`，不把 WP3-a 或 WP3 标记为完成。

---

# WP3-a 独立复审报告 R2

- **复审日期**：2026-08-05
- **修复报告**：`ai-work/executor/WP3-executor.md`“代码修复报告（R1）”
- **修复提交**：`2bcd2ab` — `fix: harden execution contract validation`
- **复审方式**：逐条核验 R1 问题、源码与测试检查、静态检查、专项测试、全量回归和独立恶意输入探针

## 7. 上轮问题核验

| 上轮问题 | 严重级别 | 状态 | 证据 |
|---|---|---|---|
| P1：循环 JSON 和超大整数可逃逸为 `RecursionError` / `OverflowError` | 主要 | **已修复** | `src/code_verifier/execution/base.py:71-85,117-118,131-132,169-175`：有限数检查安全处理 `OverflowError`，JSON 校验将 `RecursionError` / `SchemaError` 归一为 `ExecutionContractError`。独立探针覆盖循环 input、超大 timeout、per-test runtime、pass rate 和 aggregate runtime，全部得到预期的 `ExecutionContractError`。 |
| P2：错误文本泄漏隐藏测试中的自定义键名或 sibling 值 | 主要 | **已修复** | `src/code_verifier/execution/base.py:80-85,114-115` 使用固定错误消息；`tests/unit/execution/test_base.py:138-169` 覆盖 input / expected、嵌套 sentinel key、sibling sentinel value 和循环结构。独立探针仅输出 `tests[0].input|expected contains an invalid JSON value`，未回显 sentinel。 |

## 8. 回归与新问题检查

- `ExecutionStatus`、两个 dataclass 和 `CodeExecutor` 的规格 §8.3 公开合同未变化。
- `MockExecutor` FIFO、调用记录、防御性复制和不执行代码的行为未变化。
- `src/code_verifier/execution/` 未发现 `exec(`、`eval(`、`compile(` 或 `subprocess`。
- 未发现新增阻断、主要或次要问题。
- `third_party/open-r1` 固定 commit 仍为 `1416fa0cf21595d2083b399a2a0bbddd7f6e9563`。
- 未修改项目配置、依赖、Makefile、YAML 或真实沙箱范围。

## 9. 独立测试结果

```text
make lint
→ 当前 worktree 无 .venv/bin/python，Error 127

make test
→ 当前 worktree 无 .venv/bin/python，Error 127

make lint VENV=/home/dzy/open-r1-code-verifier/.venv
→ Ruff check passed
→ 37 files already formatted
→ strict Mypy: Success, no issues found in 37 source files

PYTHONPATH=src /home/dzy/open-r1-code-verifier/.venv/bin/python -m pytest \
  tests/unit/execution tests/integration/test_wp3a_mock_execution.py
→ 86 passed

PYTHONPATH=src make test VENV=/home/dzy/open-r1-code-verifier/.venv
→ 263 passed

导入 smoke
→ passed
```

原样 `make` 命令失败仅因独立 worktree 没有复制 gitignored 的虚拟环境；显式使用主仓库同一固定依赖环境并设置 `PYTHONPATH=src` 后，检查与测试均针对本 worktree 源码执行并全部通过。该环境差异不涉及源码、配置或验收行为缺陷。

## 10. R2 结论

- **审查结论：通过**。
- R1 的两个主要问题均已完整修复；计划验收项、静态检查、专项测试、全量回归、无泄漏探针和不执行代码检查均通过。
- 本结论仅表示 **WP3-a 基础合同与 Mock 基线通过**；真实沙箱、资源隔离、批量执行和完整 WP3 验收仍属于 WP3-b / WP3-c，WP3 整体不得标记为完成。
- 合并提交：待完成最终合并后补充。
