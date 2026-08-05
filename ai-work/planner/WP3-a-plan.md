# WP3-a 实施计划（安全执行器基础合同与 Mock 基线）

## 1. 元信息

| 项 | 值 |
|---|---|
| 目标 WP | WP3：安全执行器（子阶段 a：基础合同与 Mock 基线） |
| 规格依据 | `PROJECT_SPEC_Open-R1_CodeVerifier.md` §0、§6.2 Execution Layer、§8、§16、§19、§20 WP3、§24 Risk 3 / Risk 6、§29 |
| 前置 WP | WP2（`proceedings.md` 状态：已完成，验收通过） |
| 计划文件 | `ai-work/planner/WP3-a-plan.md` |
| 面向的执行者 | 仅需仓库文件读写和基础 shell，可运行项目自带的 `make` 与 pytest |
| 计划粒度 | WP3 的第一个独立阶段；4 个步骤、2 个新业务模块 |
| 预计配置影响 | 不修改 `pyproject.toml`、Makefile、YAML 或依赖；不启动真实沙箱 |

> WP3 整体同时包含公共接口、Mock、真实沙箱、资源限制、批量执行与缓存，无法在不超过 6 个步骤的单一阶段内安全完成。本计划只覆盖可独立验收的基础合同与 Mock 基线。后续阶段应继续规划：`WP3-b`（本地 Piston 执行与安全限制）和 `WP3-c`（批量并发、可选缓存、CLI 与 WP3 完整验收）。

## 2. 目标与范围

### 2.1 WP3 目标（规格 §20 原文）

安全执行函数级 Python 代码并返回结构化结果。

### 2.2 WP3 交付（规格 §20 原文）

- Executor Protocol；
- MockExecutor；
- Piston 或 DockerExecutor；
- 资源限制；
- 批量执行；
- 测试。

### 2.3 WP3 验收（规格 §20 原文）

- 正确代码通过；
- 无限循环超时；
- 网络访问失败；
- 文件系统越权失败；
- 输出上限生效；
- 不污染宿主环境；
- 结果可序列化。

### 2.4 本子阶段目标

建立后续真实沙箱、验证器和奖励函数共同依赖的稳定执行合同，并提供一个不会运行代码的确定性 `MockExecutor`。本阶段结束时，调用方可以：

- 依赖规格 §8.3 的精确结果类型和 `CodeExecutor` Protocol；
- 在进入真实沙箱前校验执行请求与结构化结果；
- 将 `ExecutionResult` 转为稳定、JSON 可序列化的 mapping；
- 使用 FIFO `MockExecutor` 编写 parser → executor、后续 verifier → executor 的离线测试；
- 明确区分“执行合同已建立”和“真实不可信代码可安全执行”。

### 2.5 范围内

- 新建 `code_verifier.execution` 包。
- 逐字实现规格 §8.3 的：
  - `ExecutionStatus`；
  - `TestCaseResult`；
  - `ExecutionResult`；
  - `CodeExecutor.execute(...)`。
- 增加执行请求和结果的纯数据校验函数，拒绝 NaN/Inf、非法计数、错误状态组合和不符合 `{input, expected}` 合同的测试。
- 增加显式 JSON mapping 序列化函数，所有枚举写为规格中的字符串值。
- 实现只返回预置结果、记录调用且绝不解释或运行代码的 `MockExecutor`。
- 增加 Execution Layer 单元测试和 parser → mock executor 的最小集成测试。
- 更新 README 与 AGENTS，准确标明 WP3-a 仅是基础合同，真实执行仍未实现。

### 2.6 范围外

- 不实现 Piston、Docker、E2B、Morph 或任何真实代码执行。
- 不调用 `exec()`、`eval()`、`compile()` 或宿主机 Python 子进程运行模型代码。
- 不实现网络、文件系统、CPU、wall-clock、内存、PID、输出大小或临时目录限制；这些属于 WP3-b。
- 不实现批量并发、缓存 key、缓存存储或训练模式缓存策略；这些属于 WP3-c。
- 不实现 WP4 verifier/reward，不选择 visible/train-hidden/eval-hidden 测试层。
- 不把 parser 失败自动映射为 `ExecutionStatus.PARSE_ERROR`；该编排职责属于后续 Verification Layer。
- 不新增执行器 CLI 或 YAML 配置。
- 不修改 `third_party/open-r1/**`。
- 不修改 `proceedings.md`；本阶段通过后只能登记为 WP3 部分完成，不能把 WP3 整体标记为完成。

## 3. 前置条件、现状与约束

### 3.1 proceedings 与当前代码结论

- `proceedings.md` 已登记 WP0、WP1、WP2 全部完成；WP2 合并后的 `main` 为 177 tests passed。
- 当前仓库已有 Data Layer 和 Parsing Layer，但尚无 `src/code_verifier/execution/`。
- WP2 的 `extract_python_code()` 已能提供纯代码文本和目标函数检查；本阶段只在集成测试中消费其成功结果，不修改 parser 合同。
- `pyproject.toml` 的 strict mypy 已覆盖整个 `src` 和 `tests`，新增包不需要修改 mypy 文件列表。
- 当前 README 明确“不可信代码执行尚未实现”；WP3-a 后仍必须保留这一安全声明。

### 3.2 固定 Open-R1 provider 的适用性结论

只读检查固定 commit 中的 `open_r1.utils.code_providers` 后确认：

- 当前上游只提供 E2B / Morph provider；
- `CodeExecutionProvider.execute_scripts()` 返回 `list[float]`，没有逐测试结构化结果；
- 上游接口不能表达 §8.3 的 `ExecutionStatus`、stdout/stderr、runtime、测试计数与资源错误；
- 两个 provider 都依赖外部服务或账户，不满足“可本地复现且不把付费沙箱作为唯一实现”的要求。

因此 WP3-a 不包装该 provider。后续 WP3-b 按 §8.2 的下一优先级采用本地 Piston；若后续确需读取 Open-R1 provider，仍必须通过 `code_verifier.training.open_r1_adapter`。

### 3.3 模块边界与硬性安全规则

- Execution Layer 只负责隔离执行和返回结构化结果，不解释 reward（§6.2）。
- 模型代码一律视为不可信；本阶段的 Mock 必须把代码当普通字符串保存，不能解析、导入或运行。
- 禁止宿主机 `exec()` 和无资源限制 Python subprocess（§8.1）。
- 新模块必须有 `from __future__ import annotations`、完整类型标注、简洁 docstring、明确错误处理和单元测试。
- 保持 Ruff 双引号、119 列和 strict mypy。
- 业务逻辑不得硬编码路径、模型名、设备、密钥或数据位置。
- 结果校验必须兼容 §8.4 的“可提前停止”：`test_results` 数量允许少于 `total_tests`，但不得多于它。

### 3.4 本阶段明确实现决策

1. **规格类型保持原样**：§8.3 的枚举成员、字符串值、dataclass 字段顺序与 `CodeExecutor.execute()` 参数必须逐字一致；不把 `list` 改为 tuple，不增加必填字段。
2. **合同错误类型**：新增 `ExecutionContractError(ValueError)`，只表示调用数据或结构化结果违反合同，不表示模型代码执行失败。
3. **请求测试格式**：每个测试必须是普通 `dict`，字段恰好为 `input` 与 `expected`；值必须满足现有 `code_verifier.data.schema.validate_json_value()` 的 JSON 值合同，不做隐式类型转换。
4. **空测试列表**：请求层允许空列表，留给 WP4 verifier 定义“0 个测试”的行为；结果层规定 `total_tests=passed_tests=0` 时 `pass_rate` 必须为 `0.0`。
5. **提前停止兼容**：`len(test_results) <= total_tests`；`passed_tests` 等于已返回结果中 `passed=True` 的数量；`pass_rate` 始终按 `passed_tests / total_tests` 计算，而不是按已执行数量计算。
6. **通过状态一致性**：`TestCaseResult.passed` 当且仅当 `status is ExecutionStatus.PASSED`；整体 `ExecutionStatus.PASSED` 要求所有请求测试都有结果且全部通过。`total_tests > 0` 且所有请求测试都有结果并全部通过时，整体状态必须为 PASSED；`total_tests == 0` 时不在本阶段强制整体状态，由 WP4 定义 0 测试语义。非 PASSED 整体状态允许已有部分测试通过。
7. **运行时间**：所有 runtime 必须是有限且非负的 float/int；bool 不视为合法数字。
8. **序列化**：生产代码提供显式 `execution_result_to_mapping()`，不依赖调用方理解 dataclass/Enum 细节；枚举输出 `.value`，字段名与 §8.3 一致。
9. **Mock 队列语义**：构造时接收 FIFO 结果序列；每次合法调用消费一个结果；结果耗尽时抛 `AssertionError`，明确表示测试配置错误，而非返回 `SANDBOX_ERROR`。
10. **防御性复制**：Mock 记录请求和返回结果时使用深复制，避免调用方后续修改 list/dict 污染历史调用或下一次断言。
11. **不制造安全假象**：任何文档、类名和测试输出均不得声称 Mock 提供沙箱安全；恶意代码字符串测试只证明“没有被执行”，不替代 WP3-b 安全验收。

## 4. 目标文件总览

### 4.1 新建

- `src/code_verifier/execution/__init__.py`
- `src/code_verifier/execution/base.py`
- `src/code_verifier/execution/mock.py`
- `tests/unit/execution/__init__.py`
- `tests/unit/execution/test_base.py`
- `tests/unit/execution/test_mock.py`
- `tests/integration/test_wp3a_mock_execution.py`

### 4.2 修改

- `README.md`
- `AGENTS.md`

### 4.3 明确不修改

- `src/code_verifier/cli.py`
- `tests/unit/test_cli.py`
- `src/code_verifier/parsing/**`
- `src/code_verifier/data/**`
- `src/code_verifier/training/open_r1_adapter.py`
- `pyproject.toml`
- `Makefile`
- `configs/**`
- `third_party/open-r1/**`
- `proceedings.md`

## 5. 实施步骤

### 步骤 1：实现规格 §8.3 的执行结果类型和 Protocol

**目标文件**：

- `src/code_verifier/execution/__init__.py`（新建）
- `src/code_verifier/execution/base.py`（新建）

**新增 / 修改的符号**：

```python
class ExecutionStatus(str, Enum):
    PASSED = "passed"
    WRONG_ANSWER = "wrong_answer"
    SYNTAX_ERROR = "syntax_error"
    RUNTIME_ERROR = "runtime_error"
    TIMEOUT = "timeout"
    MEMORY_LIMIT = "memory_limit"
    OUTPUT_LIMIT = "output_limit"
    SANDBOX_ERROR = "sandbox_error"
    PARSE_ERROR = "parse_error"


@dataclass(frozen=True)
class TestCaseResult:
    status: ExecutionStatus
    passed: bool
    runtime_ms: float
    stdout: str
    stderr: str


@dataclass(frozen=True)
class ExecutionResult:
    status: ExecutionStatus
    passed_tests: int
    total_tests: int
    pass_rate: float
    runtime_ms: float
    test_results: list[TestCaseResult]


class CodeExecutor(Protocol):
    def execute(
        self,
        code: str,
        function_name: str,
        tests: list[dict[str, Any]],
        timeout_seconds: float,
        memory_limit_mb: int,
    ) -> ExecutionResult:
        ...
```

**主要功能**：

- 上述公开类型必须逐字匹配 §8.3，不添加构造副作用。
- `ExecutionStatus` 必须继承 `str, Enum`，确保状态值具有稳定字符串表示。
- dataclass 使用 `frozen=True`，但文档必须说明 `ExecutionResult.test_results` 仍是规格要求的 list，属于浅层冻结；调用边界需防御性复制。
- `CodeExecutor` 只定义同步单请求接口；批量接口不能提前加入本阶段 Protocol，避免与 §8.3 冲突。
- `src/code_verifier/execution/__init__.py` 只重导出 `CodeExecutor`、`ExecutionResult`、`ExecutionStatus`、`TestCaseResult`，不包含业务逻辑。

**配置 / CLI 变更**：无。

**测试方案**：

- 测试文件：`tests/unit/execution/test_base.py`
- 新增测试函数：
  - `test_execution_status_values_match_spec`：断言 9 个成员和值与 §8.3 完全一致，没有额外成员。
  - `test_test_case_result_is_frozen`：修改任一标量字段抛 `FrozenInstanceError`。
  - `test_execution_result_is_frozen`：修改顶层字段抛 `FrozenInstanceError`。
  - `test_mock_implementation_is_assignable_to_code_executor`：以静态类型赋值覆盖 Protocol 的结构兼容性；该测试可在步骤 3 完成后启用。
- 覆盖规格：§8.3 接口、§19.1 Executor 的结构化结果基础。

**验证命令与通过标准**：

```bash
make lint
.venv/bin/python -m pytest tests/unit/execution/test_base.py -k "status or frozen or assignable"
```

通过标准：Ruff / strict Mypy 全绿；公开签名与枚举值测试全部通过；现有包可执行 `from code_verifier.execution import CodeExecutor, ExecutionResult, ExecutionStatus, TestCaseResult`。

---

### 步骤 2：实现执行请求/结果合同校验与显式 JSON mapping

**目标文件**：`src/code_verifier/execution/base.py`（继续修改）

**新增 / 修改的符号**：

```python
class ExecutionContractError(ValueError):
    """Raised when an execution request or structured result violates the public contract."""


def validate_execution_request(
    code: str,
    function_name: str,
    tests: list[dict[str, Any]],
    timeout_seconds: float,
    memory_limit_mb: int,
) -> None:
    """Validate one executor request without executing or transforming code."""


def validate_test_case_result(result: TestCaseResult) -> None:
    """Validate one per-test status, runtime, and captured output record."""


def validate_execution_result(result: ExecutionResult) -> None:
    """Validate counts, pass rate, status consistency, and per-test records."""


def execution_result_to_mapping(result: ExecutionResult) -> dict[str, object]:
    """Return a validated JSON-safe mapping with enum values serialized as strings."""
```

**主要功能**：

- `validate_execution_request()`：
  - `code` 必须为非空字符串，但不得解析或编译；
  - `function_name` 必须为非空合法 Python identifier，且不能是 keyword；
  - `tests` 必须是 list；成员必须是字段恰好为 `input` / `expected` 的 dict；
  - 使用现有 `validate_json_value(..., field_path=...)` 校验嵌套值，不允许 NaN/Inf、非字符串 dict key 或任意对象；
  - `timeout_seconds` 必须是有限正数且不能是 bool；
  - `memory_limit_mb` 必须是正 int 且不能是 bool；
  - 所有错误转换为包含字段路径的 `ExecutionContractError`，不泄漏整个测试 payload。
- `validate_test_case_result()`：
  - status 必须是 `ExecutionStatus`；passed 必须是 bool；
  - runtime 必须有限、非负且不能是 bool；stdout/stderr 必须是 str；
  - `passed` 与 `status is PASSED` 必须一致。
- `validate_execution_result()`：
  - 计数必须是非负 int、非 bool，且 `passed_tests <= total_tests`；
  - `len(test_results) <= total_tests`，兼容提前停止；
  - `passed_tests` 必须等于实际返回记录中的 passed 数量；
  - `pass_rate` 必须有限且在 `[0, 1]`；当 total 为 0 时精确为 0.0，否则与 `passed_tests / total_tests` 的绝对误差不超过 `1e-12`；
  - 总 runtime 有限非负；
  - 整体 PASSED 只允许所有请求测试均有结果且全部通过；当 `total_tests > 0`、结果完整且全部通过时整体必须是 PASSED；`total_tests == 0` 时不强制整体状态。
- `execution_result_to_mapping()` 先校验，再返回字段恰好为：

```python
{
    "status": str,
    "passed_tests": int,
    "total_tests": int,
    "pass_rate": float,
    "runtime_ms": float,
    "test_results": [
        {
            "status": str,
            "passed": bool,
            "runtime_ms": float,
            "stdout": str,
            "stderr": str,
        }
    ],
}
```

- 不提供宽松 coercion；`"1"`、`True`、tuple tests 等均不能被静默转换为合法请求。
- 错误消息只包含索引、字段名和错误类型，不包含完整代码、输入、expected 或 stdout/stderr。

**配置 / CLI 变更**：无。

**测试方案**：

- 测试文件：`tests/unit/execution/test_base.py`
- 新增测试函数：
  - `test_validate_execution_request_accepts_valid_json_tests`。
  - `test_validate_execution_request_allows_empty_test_list`。
  - `test_validate_execution_request_rejects_invalid_code_and_function_name`。
  - `test_validate_execution_request_rejects_unknown_or_missing_test_fields`。
  - `test_validate_execution_request_rejects_non_json_values_without_echoing_payload`。
  - `test_validate_execution_request_rejects_nonfinite_or_nonpositive_limits`。
  - `test_validate_test_case_result_accepts_each_failure_status`：参数化覆盖非 PASSED 状态与 `passed=False`。
  - `test_validate_test_case_result_rejects_passed_status_mismatch`。
  - `test_validate_execution_result_accepts_full_pass`。
  - `test_validate_execution_result_accepts_early_stop_failure`。
  - `test_validate_execution_result_accepts_zero_tests_with_zero_rate`。
  - `test_validate_execution_result_rejects_count_and_result_mismatches`。
  - `test_validate_execution_result_rejects_invalid_pass_rate`。
  - `test_validate_execution_result_rejects_inconsistent_overall_status`。
  - `test_execution_result_to_mapping_is_exact_and_json_serializable`：断言 `json.dumps(..., allow_nan=False)` 成功，enum 均为字符串。
- 覆盖规格：§8.3 结构、§8.4 提前停止、§20 “结果可序列化”。

**验证命令与通过标准**：

```bash
make lint
.venv/bin/python -m pytest tests/unit/execution/test_base.py
```

通过标准：上述合同测试全部通过；非法请求/结果均得到 `ExecutionContractError`；错误文本不含测试中的 sentinel secret；序列化 mapping 可由标准库 JSON 编码且字段无增删。

---

### 步骤 3：实现不会执行代码的 FIFO MockExecutor

**目标文件**：

- `src/code_verifier/execution/mock.py`（新建）
- `src/code_verifier/execution/__init__.py`（修改，增加 Mock 导出）

**新增 / 修改的符号**：

```python
@dataclass(frozen=True)
class MockExecutionCall:
    code: str
    function_name: str
    tests: list[dict[str, Any]]
    timeout_seconds: float
    memory_limit_mb: int


class MockExecutor:
    def __init__(self, results: Sequence[ExecutionResult]) -> None:
        """Create a non-executing FIFO test double from validated results."""

    @property
    def calls(self) -> tuple[MockExecutionCall, ...]:
        """Return defensive copies of all successfully recorded calls."""

    @property
    def remaining_results(self) -> int:
        """Return the number of queued results not yet consumed."""

    def execute(
        self,
        code: str,
        function_name: str,
        tests: list[dict[str, Any]],
        timeout_seconds: float,
        memory_limit_mb: int,
    ) -> ExecutionResult:
        """Validate and record one request, then return the next configured result."""
```

**主要功能**：

- 构造时复制结果队列并调用 `validate_execution_result()`；无效预置结果立即抛 `ExecutionContractError`，不能延迟到随机一次调用。
- `execute()` 的公开签名逐字匹配 `CodeExecutor`：
  1. 调用 `validate_execution_request()`；
  2. 若结果队列为空，抛带固定消息的 `AssertionError`，且不追加 call；
  3. 深复制请求并记录为 `MockExecutionCall`；
  4. FIFO 消费一个结果；
  5. 返回该结果的深复制。
- `calls` 返回新的 tuple 和深复制的 call 内容，调用者修改嵌套 dict/list 不得影响内部历史。
- Mock 不查看代码语法、不按 code/function/tests 选择结果、不 sleep、不访问网络/文件、不创建线程/进程。
- `src/code_verifier/execution/__init__.py` 增加重导出 `ExecutionContractError`、`MockExecutionCall`、`MockExecutor`、三个校验函数和 `execution_result_to_mapping()`。

**配置 / CLI 变更**：无。

**测试方案**：

- 测试文件：`tests/unit/execution/test_mock.py`
- 新增测试函数：
  - `test_mock_executor_consumes_results_in_fifo_order`。
  - `test_mock_executor_records_every_valid_call`。
  - `test_mock_executor_remaining_results_tracks_queue`。
  - `test_mock_executor_rejects_invalid_preconfigured_result`。
  - `test_mock_executor_rejects_invalid_request_without_consuming_result`。
  - `test_mock_executor_exhaustion_raises_without_recording_call`。
  - `test_mock_executor_defensively_copies_request_tests`。
  - `test_mock_executor_defensively_copies_returned_result`。
  - `test_mock_executor_calls_property_cannot_mutate_history`。
  - `test_mock_executor_never_executes_code_string`：传入会写 sentinel 文件的 Python 字符串，调用后文件不存在。
  - `test_mock_executor_satisfies_code_executor_protocol_under_mypy`：通过带 `CodeExecutor` 参数的 helper 接收 Mock。
- 覆盖规格：§8.2 mock 仅用于测试、§19.3 mock executor 集成测试的基础。

**验证命令与通过标准**：

```bash
make lint
.venv/bin/python -m pytest tests/unit/execution/test_mock.py
```

通过标准：Mock 测试全部通过；FIFO、调用记录和防御性复制行为确定；恶意代码字符串未产生任何文件或其他副作用；Mypy 接受 `MockExecutor` 作为 `CodeExecutor`。

---

### 步骤 4：增加 parser → mock executor 集成验证、文档和阶段总验收

**目标文件**：

- `tests/integration/test_wp3a_mock_execution.py`（新建）
- `README.md`（修改）
- `AGENTS.md`（修改）

**集成测试使用的符号**：

```python
def test_parser_output_flows_through_code_executor_contract() -> None:
    """Parse one completion, send its code to a typed MockExecutor, and serialize the result."""
```

**主要功能**：

- 集成测试必须串联现有与本阶段接口：
  1. 构造包含 `def solve(...)` 的 fenced completion；
  2. 调用 `extract_python_code(..., expected_function_name="solve")`；
  3. 通过现有 `TestCase` / `test_case_to_mapping()` 构造一个执行测试 mapping；
  4. 将 `MockExecutor` 赋给 `CodeExecutor` 类型变量；
  5. 调用 `execute()`；
  6. 断言 Mock 收到的 code 与 parser 输出逐字一致；
  7. 调用 `execution_result_to_mapping()` 并用 `json.dumps(..., allow_nan=False)` 编码。
- 集成测试不得执行提取出的代码，也不得尝试把 parser failure 映射为执行结果。
- README 新增“WP3-a execution contract”小节：
  - 给出构造 `ExecutionResult`、`MockExecutor` 和 `CodeExecutor` 类型变量的最小示例；
  - 说明 Mock 只用于测试，不运行代码；
  - 明确 Piston/Docker、资源限制和真实安全验收尚未实现；
  - 项目开头状态改为“WP3 execution contract/mock foundation implemented”，但继续写明不可信代码执行不可用。
- AGENTS 结构新增 `execution/base.py`、`execution/mock.py` 和对应测试；当前范围改为“WP3-a 基础合同已实现，禁止在没有后续计划时加入真实执行、WP4 或更后功能”。
- 不新增 CLI 文档，不声称 WP3 整体完成。

**配置 / CLI 变更**：无。

**测试方案**：

- 测试文件：`tests/integration/test_wp3a_mock_execution.py`
- 新增测试函数：
  - `test_parser_output_flows_through_code_executor_contract`：断言 parser、Data test mapping、Mock、Protocol 和 JSON mapping 的最小闭环。
- 回归测试：现有 WP0–WP2 全部测试。
- 文档核对：README 中必须同时出现 `MockExecutor` 和“does not execute code”或等价明确表述。

**验证命令与通过标准**：

```bash
make lint
.venv/bin/python -m pytest tests/unit/execution tests/integration/test_wp3a_mock_execution.py
make test
.venv/bin/python -c "from code_verifier.execution import CodeExecutor, ExecutionResult, ExecutionStatus, MockExecutor, TestCaseResult; print(ExecutionStatus.PASSED.value)"
```

通过标准：

- Execution Layer 专项测试至少收集 20 个用例并全部通过。
- `make test` 全绿，现有 177 个测试无回归。
- 导入 smoke 输出 `passed`。
- `make lint` 的 Ruff check、Ruff format check、strict Mypy 全绿。
- 仓库中未出现调用 `exec()` / `eval()` 或以宿主机 Python 运行模型代码的新逻辑。
- `third_party/open-r1/**`、配置和依赖无修改。

## 6. 总体验收与测试计划

### 6.1 单元测试汇总

- `tests/unit/execution/test_base.py`
  - 规格枚举与 dataclass；
  - 请求参数和 JSON test mapping 校验；
  - per-test / aggregate 结果一致性；
  - 提前停止和 0 测试结构边界；
  - JSON mapping 可序列化。
- `tests/unit/execution/test_mock.py`
  - FIFO 结果；
  - Protocol 兼容；
  - 调用记录；
  - 防御性复制；
  - 非执行保证；
  - 队列耗尽与无效配置。

### 6.2 集成测试

- `tests/integration/test_wp3a_mock_execution.py`
  - Data test mapping → parser → `CodeExecutor` → Mock → JSON mapping。
- 对应 §19.3 的 mock executor 集成基础。
- §19.2 的“真实沙箱执行”明确留给 WP3-b，不得以本 Mock 集成替代。

### 6.3 数据泄漏与安全判断

- 本阶段不选择或读取任何隐藏测试层，只消费显式传入的测试 mapping。
- 错误消息不得包含测试 payload，降低后续训练日志泄漏风险。
- 本阶段不执行代码，因此无法也不应宣称满足真实网络/文件/资源隔离。

### 6.4 本子阶段最终通过标准

- [ ] `ExecutionStatus`、`TestCaseResult`、`ExecutionResult`、`CodeExecutor` 与 §8.3 逐字一致。
- [ ] 请求和结果校验拒绝非法类型、NaN/Inf、计数及状态不一致。
- [ ] `execution_result_to_mapping()` 产生字段稳定、JSON-safe 的结果。
- [ ] `MockExecutor` 以 FIFO 返回预置结果、记录调用、深复制边界且不执行代码。
- [ ] parser → Mock 集成测试通过。
- [ ] `make lint` 全绿。
- [ ] `make test` 全绿且 WP0–WP2 无回归。
- [ ] 无配置、依赖和 `third_party/open-r1/**` 修改。
- [ ] 文档明确 WP3 仍为部分完成，真实沙箱和安全验收未完成。

### 6.5 WP3 整体仍未通过的项目

完成本计划后，下列 §20 交付/验收仍然未完成，必须进入后续计划：

- [ ] Piston 或 DockerExecutor；
- [ ] 无网络、非 root、只读基础文件系统、临时目录、CPU、wall-clock、内存、PID、输出限制与清理；
- [ ] 正确/错误/语法/运行/超时/内存/输出等真实状态映射；
- [ ] 批量执行、有限并发、可选缓存及完整 cache key；
- [ ] 真实沙箱中网络访问、文件系统越权、无限循环和输出爆炸验收；
- [ ] 不污染宿主环境的独立验证；
- [ ] WP3 高风险人工 Code Review。

## 7. 风险与注意事项

- **Mock 被误当安全执行器**：README、AGENTS、docstring 和 proceedings 必须反复区分 test double 与真实 sandbox；不得把本阶段标记为 WP3 完成。
- **接口提前漂移**：WP4、训练奖励和真实 executor 都将依赖 §8.3；禁止为了方便 Mock 修改公开签名或状态字符串。
- **结果校验过严**：必须保留 early-stop 下 `len(test_results) < total_tests` 的合法空间；不能强制每个失败都返回全部结果。
- **结果校验过松**：passed/count/rate/status 不一致会污染 reward，必须在执行边界立即失败，不能静默修正。
- **浅冻结可变成员**：规格要求 list，因此 dataclass 的 frozen 不能防止嵌套修改；Mock 和序列化边界必须深复制，测试必须证明这一点。
- **错误日志泄漏测试内容**：异常消息只能报告字段路径和原因，不回显 code、input、expected、stdout 或 stderr。
- **上游 provider 能力误判**：固定 Open-R1 provider 只返回 reward float，不能作为本项目结构化 executor；不要为了复用而丢失状态信息。
- **Risk 6 执行器耗时**：通过阶段拆分先冻结低风险合同；真实沙箱优先本地 Piston，不自行实现完整沙箱内核，也不回退到宿主机直接执行。

## 8. 后续阶段边界

### WP3-b：本地 Piston 执行与安全限制

后续计划应覆盖：函数级测试 harness、Piston client、Piston 配置、单请求真实执行、状态映射、网络/文件/进程/输出/超时/内存限制探针、清理与真实沙箱集成测试。该阶段必须独立人工审查。

### WP3-c：批量并发、缓存、CLI 与 WP3 完整验收

后续计划应覆盖：批量请求类型、有限并发、配置化并发数、完整 cache key、默认关闭或审慎启用缓存、调试 CLI、批量/缓存单元测试，以及 §20 WP3 全部验收回归。

## 9. 关联文档索引

- `PROJECT_SPEC_Open-R1_CodeVerifier.md`
  - §0：安全、类型、测试、错误处理与范围纪律
  - §6.2：Execution Layer 职责与禁止事项
  - §8.1：不可信代码安全原则
  - §8.2：provider / Piston / Docker / mock 优先级
  - §8.3：公开接口原文
  - §8.4：资源限制和提前停止要求
  - §8.5：批量、并发与缓存（后续阶段）
  - §16：execution 包目标结构
  - §19.1 Executor、§19.2 真实沙箱、§19.3 mock executor
  - §20 WP3：完整目标、交付与验收
  - §24 Risk 3 / Risk 6：性能和安全实现回退
  - §29：Python 函数级任务与本地沙箱默认决策
- `proceedings.md`
  - WP2：已完成、177 tests passed、未实现 WP3
- 当前实现
  - `src/code_verifier/parsing/code_extractor.py`：集成测试的代码来源
  - `src/code_verifier/data/schema.py`：JSON value 合同
  - `src/code_verifier/training/open_r1_adapter.py`：所有潜在 Open-R1 读取边界
- 固定上游只读参考
  - `third_party/open-r1/src/open_r1/utils/code_providers.py`：当前 provider 仅提供 E2B/Morph 与 float reward 返回值
