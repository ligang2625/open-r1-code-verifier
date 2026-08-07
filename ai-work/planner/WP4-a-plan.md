# WP4-a 实施计划（统一验证器与结构化验证结果）

## 1. 元信息

| 项 | 值 |
|---|---|
| 目标 WP | WP4：Verifier 与 Reward（子阶段 a：统一验证器与结构化验证结果） |
| 规格依据 | `PROJECT_SPEC_Open-R1_CodeVerifier.md` §6.2 Verification Layer / Reward Layer、§10.1–§10.6、§16、§19、§20 WP4、§29 |
| 前置 WP | WP3（`proceedings.md` 状态：已完成，验收通过） |
| 计划文件 | `ai-work/planner/WP4-a-plan.md` |
| 面向的执行者 | 仅需仓库文件读写与基础 shell；可运行项目自带的 `make`、pytest 和 CLI；不依赖任何专用工具或其它 skill |
| 计划粒度 | WP4 的第一个子阶段；5 个步骤、3 个新业务模块 |
| 预计配置影响 | 不新增 YAML、CLI 参数或 Python package 依赖；不修改执行器配置与版本 |

> WP4 同时包含 Verification 与 Reward 两层，按规格仓库结构至少涉及 `verification/result_types.py`、`verification/verifier.py`、`rewards/common.py`、`rewards/public_reward.py`、`rewards/hidden_reward.py` 五个业务模块，超过单阶段“新模块不超过 4 个”的粒度约束。因此拆分为：
>
> - **WP4-a（本计划）**：结构化验证结果、completion → parser → executor 的统一验证器、失败状态汇总及 Mock 集成验收；
> - **WP4-b（后续计划）**：`compute_code_rewards()`、Public/Hidden 薄封装、reward 分量日志、TRL batch 对齐、训练测试层隔离与 WP4 整体验收。
>
> 本阶段通过后只能登记“WP4-a 子阶段完成”，不得把 WP4 整体标记为完成。

## 2. 目标与范围

### 2.1 WP4 目标（规格 §20 原文）

实现统一验证器、Public reward 和 Hidden reward。

### 2.2 WP4 交付（规格 §20 原文）

- verifier；
- reward common；
- public reward；
- hidden reward；
- 分量日志；
- reward 测试。

### 2.3 WP4 验收（规格 §20 原文）

- 两种 reward 只在测试来源上不同；
- eval hidden 无法从训练 reward 路径访问；
- reward 数量与 completion 数量一致；
- 所有 reward 有限；
- 失败状态符合规格。

### 2.4 本子阶段目标

建立 WP4 的 Verification Layer，使调用方只需提供一条 completion、一个明确选定的测试列表、目标函数名、资源限制 metadata 和现有 `CodeExecutor`，即可得到可验证、可序列化、失败关闭的 `VerificationResult`。验证器必须：

- 先严格校验函数名、测试列表和资源限制；
- 使用现有 `extract_python_code()` 做唯一解析入口；
- 解析成功后使用现有 `CodeExecutor.execute()` 做唯一执行入口；
- 保持测试顺序，不读取或选择其它测试层；
- 正确处理全通过、部分通过、提前停止、timeout、sandbox error、解析失败和 executor 抛异常；
- 计算稳定的通过率与失败类型计数；
- 不计算 reward，不引入 Public/Hidden 模式分支；
- 不把 completion、测试输入或期望值写入验证结果摘要。

### 2.5 范围内

- 新建 `src/code_verifier/verification/result_types.py`，定义验证结果合同、合同校验和 JSON-safe mapping。
- 新建 `src/code_verifier/verification/verifier.py`，实现输入规范化、资源限制解析、失败汇总和 `verify_completion()`。
- 新建 `src/code_verifier/verification/__init__.py`，仅重导出 WP4-a 公共 API。
- 新增 Verification 单元测试，覆盖规格 §19.1 的通过率、0 测试、提前停止、顺序和错误状态汇总。
- 新增 Mock 集成测试，覆盖 completion → parser → verifier → executor 的完整 CPU 路径。
- 更新 `README.md` 与 `AGENTS.md`，记录验证器边界、当前阶段状态和禁止事项。

### 2.6 范围外

- 不新建或修改 `src/code_verifier/rewards/**`；不实现 `public_code_reward()`、`hidden_code_reward()` 或 `compute_code_rewards()`。
- 不计算 §10.2 的 `executable_reward`、`timeout_penalty`、`invalid_format_penalty`，只提供后续 reward 所需的结构化事实。
- 不从 `CodeProblem`、canonical dataset 或完整 training record 中自行选择测试层；调用方必须只传入当前模式允许的测试列表。
- 不接受 `eval_hidden_tests`、`visible_tests`、`train_hidden_tests` 等多层容器参数；验证器接口中不得出现可切换测试层的字符串字段。
- 不实现 WP5 generation/evaluation、WP6 SFT、WP7/WP8 GRPO。
- 不新增 CLI 子命令或 YAML 配置；WP4 的训练接入由后续阶段处理。
- 不修改 `ExecutionStatus`、`TestCaseResult`、`ExecutionResult`、`CodeExecutor.execute()` 或 parser 的 `ParseResult` / `extract_python_code()` 签名。
- 不修改 `PistonExecutor`、trusted-parent harness、batch/cache 语义或其版本常量。
- 不修改 `third_party/open-r1/**`。
- 执行阶段不修改 `proceedings.md`；只有本子阶段独立审查通过并合并后，审查方才可追加 WP4-a 记录。

## 3. 前置条件、现状与约束

### 3.1 proceedings 与当前实现结论

- `proceedings.md` 已正式登记 WP0、WP1、WP2、WP3 全部完成；WP4 是 §20 顺序中第一个未完成 WP。
- 合并后的 `main` 已通过：
  - `make lint`；
  - `make test`：444 passed，3 个真实 Piston tests 按设计默认 skipped；
  - `make test-piston PISTON_CONFIG=configs/execution/piston-local.yaml`：9 passed，0 failed，0 skipped。
- `src/code_verifier/parsing/code_extractor.py` 已提供规格接口：

```python
def extract_python_code(
    completion: str,
    expected_function_name: str | None = None,
) -> ParseResult:
    ...
```

- `src/code_verifier/execution/base.py` 已提供规格接口：

```python
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

- `ExecutionResult` 已对 `status`、计数、`pass_rate`、runtime 和逐测试结果实施严格合同校验；验证器必须复用 `validate_execution_result()`，不得另造宽松执行结果解释。
- WP1 training artifact 的 metadata 已稳定提供 `time_limit_seconds` 与 `memory_limit_mb`；Public artifact 只有 `visible_tests`，Hidden artifact 有 `visible_tests` 与 `train_hidden_tests`，所有 training artifact 均禁止 `eval_hidden_tests`。
- 当前尚无 `src/code_verifier/verification/` 或 `src/code_verifier/rewards/`。

### 3.2 必须保留的规格契约

#### Verification Layer（§6.2）

- 将题目、代码和某一测试层交给执行器；
- 计算测试通过率；
- 汇总失败类型；
- 不访问不属于当前模式的测试层。

#### Reward 原则中对验证结果的要求（§10.1–§10.2）

- 主要 reward 来自测试通过率；
- Public/Hidden 只改变测试来源；
- 奖励分量必须单独记录；
- reward 异常不能静默变成高分；
- 后续 `executable_reward` 需要区分“解析成功且执行无基础设施失败”；
- timeout 与 invalid format 必须可从验证结果中无歧义识别。

#### Verifier 单元测试要求（§19.1）

- 通过率计算；
- 0 个测试的处理；
- 提前停止；
- 测试顺序；
- 错误状态汇总。

### 3.3 横切硬性规则

- 使用 `uv` 与现有 Makefile 管理环境；不得引入裸 `pip install` 流程。
- 新模块必须使用 `from __future__ import annotations`、完整类型标注、docstring、Ruff 双引号与 119 列，并通过 strict mypy。
- 验证器不得使用 host `exec`、`eval`、`compile`、subprocess 或任何绕过 `CodeExecutor` 的执行路径。
- 验证器不得直接导入 `third_party/open-r1`；本阶段不需要访问 Open-R1。
- 错误信息和 mapping 不得包含 completion 原文、提取出的 code、测试 input/expected、executor 异常文本或 metadata 原值。
- 所有普通 `Exception` 只能在 executor 调用边界被转换为失败关闭的 `SANDBOX_ERROR`；不得捕获 `KeyboardInterrupt`、`SystemExit` 或其它 `BaseException`。
- 本阶段不改变 executor、harness、comparison、mapping 或 stopping policy，因此不得递增 WP3 的 executor/harness/cache version 常量。
- 新包由 `pyproject.toml` 现有 `tool.mypy.files = ["src", "tests"]` 自动覆盖，无需修改 mypy 文件列表。

### 3.4 本阶段明确实现决策

1. **显式单测试层输入**：`verify_completion()` 只接受一个 `tests` 参数，不接受完整题目对象、完整 training record 或测试层名称。测试层选择由后续 Public/Hidden reward 薄封装完成，从接口上阻断验证器自行访问其它层。
2. **0 测试 fail-closed**：空测试列表属于数据/调用合同错误，必须在 parser 和 executor 调用前抛 `VerificationContractError`；不得返回 1.0、0.0 或其它看似有效的 pass rate。
3. **metadata 最小读取**：只读取 `time_limit_seconds` 和 `memory_limit_mb`；允许 metadata 包含 WP1 schema 的其它字段，但不得使用或记录它们。
4. **测试规范化**：每个测试必须是字段恰好为 `input`、`expected` 的 mapping；使用现有 schema JSON 验证与 thaw 工具生成新的 mutable `dict`/`list`，保持测试顺序，禁止宽松类型转换。
5. **解析先于执行**：调用现有 `extract_python_code(completion, expected_function_name=function_name)`；解析失败时 executor 调用次数必须为 0。
6. **解析失败结果**：状态固定为 `ExecutionStatus.PARSE_ERROR`，`parsed=False`、`executed=False`、`infrastructure_failure=False`、`passed_tests=0`、`pass_rate=0.0`、`execution_result=None`；`parse_error_type` 保留 parser taxonomy，但 mapping 不包含 code。
7. **结构化执行成功**：executor 返回后必须调用 `validate_execution_result()`；验证结果中的 status/计数/pass rate 必须与执行结果逐字段一致，并保存防御性复制后的 `ExecutionResult`。
8. **基础设施失败**：executor 返回 `SANDBOX_ERROR` 或 executor 调用抛普通 `Exception` 时，`infrastructure_failure=True`；抛异常路径返回 `executed=False`、`execution_result=None`，且不回显异常类型或文本。
9. **timeout 不是基础设施失败**：`ExecutionStatus.TIMEOUT` 表示候选执行超时，`executed=True`、`infrastructure_failure=False`；这允许 WP4-b 同时给 executable 分量和 timeout penalty。
10. **失败计数守恒**：`failure_counts` 使用按 key 字典序排序的 `tuple[tuple[str, int], ...]`。key 只允许非 `PASSED` 的 `ExecutionStatus.value`；所有 count 为正整数，count 总和必须等于 `total_tests - passed_tests`。
11. **提前停止归因**：若 `ExecutionResult.test_results` 少于 `total_tests`，已返回测试按各自 status 计数，未运行测试全部归入顶层 `ExecutionResult.status`；不得产生额外 `not_run` taxonomy。
12. **解析/抛异常归因**：解析失败时全部测试计入 `parse_error`；executor 抛异常时全部测试计入 `sandbox_error`。
13. **无敏感 mapping**：`verification_result_to_mapping()` 只输出摘要字段、parser error taxonomy、失败计数和可选的现有 `execution_result_to_mapping()`；不输出 completion、code、tests、function name、metadata 或 Python 异常。
14. **无 CLI/配置扩展**：本阶段所有 API 通过 Python 模块调用；CLI 与 YAML 保持不变。

## 4. 目标文件总览

### 4.1 新建

- `src/code_verifier/verification/__init__.py`
- `src/code_verifier/verification/result_types.py`
- `src/code_verifier/verification/verifier.py`
- `tests/unit/verification/__init__.py`
- `tests/unit/verification/test_result_types.py`
- `tests/unit/verification/test_verifier.py`
- `tests/integration/test_wp4a_verifier_pipeline.py`

### 4.2 修改

- `README.md`
- `AGENTS.md`

### 4.3 明确不修改

- `src/code_verifier/data/**`
- `src/code_verifier/parsing/**`
- `src/code_verifier/execution/**`
- `src/code_verifier/rewards/**`（本阶段不得创建）
- `src/code_verifier/training/**`
- `src/code_verifier/cli.py`
- `tests/unit/test_cli.py`
- `configs/**`
- `Makefile`
- `pyproject.toml`
- `third_party/open-r1/**`
- `proceedings.md`

## 5. 实施步骤

### 步骤 1：定义结构化验证结果、合同校验与安全 mapping

**目标文件**：

- `src/code_verifier/verification/result_types.py`（新建）
- `tests/unit/verification/__init__.py`（新建）
- `tests/unit/verification/test_result_types.py`（新建）

**新增 / 修改的符号**：

```python
from dataclasses import dataclass

from code_verifier.execution.base import ExecutionResult, ExecutionStatus


class VerificationContractError(ValueError):
    """Raised when verifier inputs or structured outputs violate the public contract."""


FailureCounts = tuple[tuple[str, int], ...]


@dataclass(frozen=True)
class VerificationResult:
    """Sanitized parser/executor summary used by reward and evaluation consumers."""

    status: ExecutionStatus
    parsed: bool
    executed: bool
    infrastructure_failure: bool
    passed_tests: int
    total_tests: int
    pass_rate: float
    parse_error_type: str | None
    num_code_blocks: int
    failure_counts: FailureCounts
    execution_result: ExecutionResult | None


def validate_verification_result(result: VerificationResult) -> None:
    """Validate all cross-field, finiteness, count, parse, and execution invariants."""


def verification_result_to_mapping(result: VerificationResult) -> dict[str, object]:
    """Return a validated JSON-safe summary without completion, code, tests, or metadata."""
```

**主要功能**：

- `VerificationResult` 是 WP4 Verification Layer 的唯一公共结果类型；不得保存 completion、code、function name、tests 或 metadata。
- `validate_verification_result()` 必须严格验证：
  - `status` 必须为 `ExecutionStatus`；所有 bool 必须是精确 bool；计数必须是非 bool 的非负 int；
  - `total_tests > 0`，`0 <= passed_tests <= total_tests`；
  - `pass_rate` 为有限 float/int，且以 `abs_tol=1e-12` 精确等于 `passed_tests / total_tests`；
  - `num_code_blocks` 为非 bool 的非负 int；
  - `failure_counts` 必须是按 key 严格升序、key 唯一、count 为正整数的 tuple；key 仅允许 `ExecutionStatus` 中除 `passed` 外的 value；
  - `sum(failure_counts.values()) == total_tests - passed_tests`；全通过时 tuple 必须为空；
  - `parsed=False` 时：status 为 `PARSE_ERROR`、`executed=False`、无 infrastructure failure、`parse_error_type` 为非空字符串、`execution_result=None`、passed/pass rate 为 0；
  - `parsed=True` 时 `parse_error_type=None`；
  - `executed=True` 时 `execution_result` 必须存在并先通过 `validate_execution_result()`；summary status/计数/pass rate 必须与嵌套执行结果一致；
  - `executed=False and parsed=True` 只允许 sanitised executor-exception 路径：status 为 `SANDBOX_ERROR`、`infrastructure_failure=True`、`execution_result=None`、passed/pass rate 为 0；
  - `infrastructure_failure` 当且仅当 status 为 `SANDBOX_ERROR`。
- `verification_result_to_mapping()` 输出字段固定为 dataclass 的 11 个字段；enum 用字符串；`failure_counts` 输出为 JSON object；`execution_result` 为 `None` 或调用现有 `execution_result_to_mapping()` 的结果。
- mapping 必须返回新建容器，不能暴露 dataclass 内部 tuple/list 引用；错误统一为不包含 payload 的 `VerificationContractError`。

**配置 / CLI 变更**：无。

**测试方案**：

- 测试文件：`tests/unit/verification/test_result_types.py`
- 新增测试函数：
  - `test_valid_parse_failure_result_maps_without_code_or_tests`：合法 parse failure 可校验与序列化，mapping 无敏感字段。
  - `test_valid_executed_result_matches_execution_contract`：全通过、部分失败、timeout、sandbox result 均保持嵌套字段一致。
  - `test_validation_rejects_zero_tests_non_finite_rate_and_bad_counts`：0 测试、NaN/Inf、bool-as-int、计数越界均拒绝。
  - `test_validation_rejects_unsorted_duplicate_unknown_or_zero_failure_counts`：失败 taxonomy 和排序合同严格。
  - `test_validation_rejects_parse_execution_and_infrastructure_invariant_mismatches`：所有跨字段矛盾均拒绝。
  - `test_mapping_returns_independent_nested_containers`：修改 mapping 不改变原结果。
  - `test_contract_errors_do_not_echo_sentinel_payloads`：异常消息不含测试哨兵或 execution stdout/stderr。
- 覆盖规格边界：§6.2 Verification 结构化汇总；§10.1 有限、失败关闭的事实输入；§19.1 错误状态汇总。

**验证命令与通过标准**：

```bash
.venv/bin/python -m pytest tests/unit/verification/test_result_types.py
make lint
```

通过标准：新增结果类型全部合同测试通过；所有非法组合被拒绝；所有合法 mapping 可被 `json.dumps(..., allow_nan=False)` 序列化且不含 completion/code/tests/metadata。

---

### 步骤 2：实现函数名、测试列表与 metadata 资源限制的严格规范化

**目标文件**：

- `src/code_verifier/verification/verifier.py`（新建，先实现输入辅助函数）
- `tests/unit/verification/test_verifier.py`（新建，先覆盖输入合同）

**新增 / 修改的符号**：

```python
import keyword
from collections.abc import Mapping, Sequence
from typing import Any


def _validate_function_name(function_name: object) -> str:
    """Return one non-keyword Python identifier or raise a sanitized contract error."""


def _normalize_tests(tests: object) -> list[dict[str, Any]]:
    """Validate one non-empty ordered test layer and return a defensive mutable copy."""


def _resource_limits_from_metadata(metadata: object) -> tuple[float, int]:
    """Read and validate only time_limit_seconds and memory_limit_mb from metadata."""
```

**主要功能**：

- `_validate_function_name()` 与现有 execution contract 保持一致：必须是非空、UTF-8 可编码、非 keyword 的 Python identifier；不做 strip 后替换或其它 coercion。
- `_normalize_tests()`：
  - 拒绝 string/bytes、非 sequence、空 sequence；
  - 每项必须是 `Mapping` 且 key 恰好为 `input`、`expected`；key 必须为精确字符串；
  - 对 input/expected 调用现有 `validate_json_value()`，并使用 `json_value_to_mutable()` 生成新的 JSON-safe mutable 值；
  - 捕获 schema/递归/Unicode/内存边界并统一转换为不含 payload 的 `VerificationContractError`；
  - 输出必须是全新的 `list[dict[str, Any]]`，顺序与输入完全一致；不得排序、去重或修改数值类型。
- `_resource_limits_from_metadata()`：
  - metadata 必须为 string-keyed mapping；
  - 必须存在 `time_limit_seconds` 和 `memory_limit_mb`；
  - time 必须为非 bool 的有限正 int/float，返回 float；memory 必须为非 bool 的正 int；
  - 不读取其它 metadata 值，不要求 exact field set，也不把 metadata 写入结果或错误。
- 三个 helper 必须在 parser 或 executor 被调用前完成；任一失败必须零 parser/zero executor side effect（parser 为纯函数，但测试仍通过 monkeypatch 验证未调用）。

**配置 / CLI 变更**：无；metadata 字段复用 WP1 canonical schema，不新增默认值或 override。

**测试方案**：

- 测试文件：`tests/unit/verification/test_verifier.py`
- 新增测试函数：
  - `test_validate_function_name_accepts_identifier_and_rejects_keyword_invalid_utf8_and_wrong_type`。
  - `test_normalize_tests_preserves_order_and_returns_deep_mutable_copy`。
  - `test_normalize_tests_rejects_empty_wrong_shape_unknown_fields_and_non_json_values`。
  - `test_normalize_tests_preserves_bool_int_float_type_distinctions`。
  - `test_resource_limits_accept_wp1_metadata_and_ignore_unrelated_fields`。
  - `test_resource_limits_reject_missing_non_finite_non_positive_and_bool_values`。
  - `test_input_contract_errors_do_not_echo_sentinel_values`。
  - `test_invalid_inputs_do_not_call_parser_or_executor`。
- 覆盖规格边界：§19.1 Verifier 0 测试处理与测试顺序；§6.2 不修改测试数据；WP1 strict JSON/type isolation。

**验证命令与通过标准**：

```bash
.venv/bin/python -m pytest tests/unit/verification/test_verifier.py -k "function_name or normalize_tests or resource_limits or invalid_inputs"
make lint
```

通过标准：空测试及全部畸形输入在任何 parser/executor 调用前失败；合法测试顺序和值类型保持不变；无异常消息泄露哨兵 payload。

---

### 步骤 3：实现 completion → parser → executor 的统一验证器与失败状态汇总

**目标文件**：

- `src/code_verifier/verification/verifier.py`（继续实现公共验证流程）
- `tests/unit/verification/test_verifier.py`（继续补齐行为测试）

**新增 / 修改的符号**：

```python
from code_verifier.execution.base import CodeExecutor, ExecutionResult, ExecutionStatus, TestCaseResult
from code_verifier.verification.result_types import FailureCounts, VerificationResult


def _summarize_failure_counts(
    *,
    status: ExecutionStatus,
    passed_tests: int,
    total_tests: int,
    test_results: Sequence[TestCaseResult],
) -> FailureCounts:
    """Return sorted failure counts, assigning unexecuted tests to the aggregate status."""


def _parse_failure_result(
    *,
    error_type: str,
    num_code_blocks: int,
    total_tests: int,
) -> VerificationResult:
    """Build one validated fail-closed parse result."""


def _executor_exception_result(
    *,
    num_code_blocks: int,
    total_tests: int,
) -> VerificationResult:
    """Build one sanitized sandbox failure for an executor-side ordinary exception."""


def _executed_result(
    *,
    num_code_blocks: int,
    execution_result: ExecutionResult,
) -> VerificationResult:
    """Copy one validated ExecutionResult into the verifier result contract."""


def verify_completion(
    completion: str,
    tests: Sequence[Mapping[str, object]],
    function_name: str,
    metadata: Mapping[str, object],
    executor: CodeExecutor,
) -> VerificationResult:
    """Parse and verify one completion against exactly one caller-selected test layer."""
```

**主要功能**：

- `verify_completion()` 调用顺序固定为：
  1. `_validate_function_name()`；
  2. `_normalize_tests()`；
  3. `_resource_limits_from_metadata()`；
  4. `extract_python_code(completion, expected_function_name=validated_function_name)`；
  5. 解析成功时调用 `executor.execute(code, function_name, tests, timeout_seconds, memory_limit_mb)`；
  6. 构造并调用 `validate_verification_result()` 后返回。
- completion 非字符串不在 helper 中 coercion；直接交给现有 parser，使 parser taxonomy 返回 `invalid_input`，而不是抛 Python 类型错误。
- parser 失败：不得调用 executor；`failure_counts=(("parse_error", total_tests),)`。
- parser 成功：传给 executor 的 code 必须是 parser 返回的 exact code；测试必须是 `_normalize_tests()` 的防御性副本；顺序不变。
- executor 返回：
  - 先调用 `validate_execution_result()`；畸形结果按 executor 普通异常路径 fail closed 为 `SANDBOX_ERROR`，不得被当作模型正确结果；
  - 对合法结果做防御性复制，包括新的 `test_results` list；
  - `_summarize_failure_counts()` 先统计返回的非 passed test status；若 `len(test_results) < total_tests`，将剩余数量加到顶层 status；
  - 若顶层 status 为 `PASSED`，必须无失败 count；其它状态 count 总和必须等于失败测试数；
  - `SANDBOX_ERROR` 设置 infrastructure failure；`TIMEOUT`、`MEMORY_LIMIT`、`OUTPUT_LIMIT` 等候选失败不标记为 infrastructure failure。
- executor 抛任意普通 `Exception`：返回 sanitized `SANDBOX_ERROR`，不传播错误文本，不回显异常类；`failure_counts=(("sandbox_error", total_tests),)`。
- 不捕获 `BaseException`。
- `verify_completion()` 本身不得记录 completion、code、tests 或 metadata；允许调用方记录 `verification_result_to_mapping()`。

**配置 / CLI 变更**：无。

**测试方案**：

- 测试文件：`tests/unit/verification/test_verifier.py`
- 新增测试函数：
  - `test_verify_completion_passes_exact_parser_code_ordered_tests_and_resource_limits_to_executor`。
  - `test_parse_failure_returns_parse_error_and_never_calls_executor`。
  - `test_missing_target_function_preserves_parser_error_taxonomy`。
  - `test_full_partial_and_all_failed_results_compute_monotonic_pass_rates`。
  - `test_early_stop_assigns_unexecuted_tests_to_aggregate_failure_status`。
  - `test_mixed_test_statuses_are_sorted_and_counted_without_passed_entries`。
  - `test_timeout_is_executed_but_not_infrastructure_failure`。
  - `test_returned_sandbox_error_is_infrastructure_failure`。
  - `test_executor_exception_is_sanitized_sandbox_failure`。
  - `test_malformed_execution_result_fails_closed_as_sandbox_failure`。
  - `test_executor_base_exception_is_not_caught`。
  - `test_verifier_does_not_mutate_caller_tests_or_executor_result`。
- 覆盖规格边界：§19.1 通过率、提前停止、测试顺序、错误状态汇总；§10.2 executable/timeout/invalid-format 后续分量所需事实；§10.6 基础设施错误不得当成正确答案。

**验证命令与通过标准**：

```bash
.venv/bin/python -m pytest tests/unit/verification/test_verifier.py
make lint
```

通过标准：全通过/部分通过/全失败 pass rate 分别为 1.0、(0,1) 区间、0.0；解析失败零 executor 调用；timeout 与 sandbox 被准确区分；executor 异常与畸形结果均得到有限 0.0 且失败关闭的 SANDBOX summary；测试顺序严格保持。

---

### 步骤 4：建立 Verification 包公共 API 与 Mock 端到端集成测试

**目标文件**：

- `src/code_verifier/verification/__init__.py`（新建）
- `tests/integration/test_wp4a_verifier_pipeline.py`（新建）

**新增 / 修改的符号**：

```python
# src/code_verifier/verification/__init__.py
from code_verifier.verification.result_types import (
    FailureCounts,
    VerificationContractError,
    VerificationResult,
    validate_verification_result,
    verification_result_to_mapping,
)
from code_verifier.verification.verifier import verify_completion

__all__ = [
    "FailureCounts",
    "VerificationContractError",
    "VerificationResult",
    "validate_verification_result",
    "verification_result_to_mapping",
    "verify_completion",
]
```

**主要功能**：

- 包根只导出稳定公共 API；所有 `_...` helper 保持私有。
- 集成测试使用现有 `MockExecutor` 的 FIFO 结果和调用记录，不执行候选代码。
- 构造至少 5 条独立场景：
  1. 合法 fenced Python completion + 全通过执行结果；
  2. 合法 completion + 部分失败结果；
  3. 合法 completion + timeout 提前停止结果；
  4. 缺少目标函数的解析失败；
  5. 合法 completion + sandbox error。
- 逐条断言 parser → verifier → Mock 的参数与结果：
  - executor 只收到前三/第五条成功解析请求；解析失败不消耗 FIFO result；
  - 每条调用的 code、function、测试顺序、timeout、memory 与输入完全对应；
  - mapping 可严格 JSON 序列化，且没有 completion/code/tests/metadata；
  - 所有 `pass_rate` 有限；
  - failure count 守恒；
  - Mock 始终不执行候选代码。
- 集成测试不得导入或启动 Piston；真实 sandbox 已由 WP3 验收，本阶段只验证层间合同。

**配置 / CLI 变更**：无。

**测试方案**：

- 测试文件：`tests/integration/test_wp4a_verifier_pipeline.py`
- 新增测试函数：
  - `test_wp4a_completion_parser_verifier_mock_pipeline_preserves_contracts`。
  - `test_wp4a_verifier_results_are_finite_json_safe_and_payload_free`。
  - `test_wp4a_parse_failure_does_not_consume_mock_result`。
- 覆盖规格边界：§19.2 reward 前置的 mock verifier 批量调用基础；§6.2 Parsing/Execution/Verification 模块边界。

**验证命令与通过标准**：

```bash
.venv/bin/python -m pytest tests/integration/test_wp4a_verifier_pipeline.py
.venv/bin/python -m pytest tests/unit/verification tests/integration/test_wp4a_verifier_pipeline.py
make lint
```

通过标准：集成场景全部通过；Mock 调用数量与成功解析数一致；FIFO 不被 parse failure 消耗；所有 mapping 可 `json.dumps(..., allow_nan=False)`；无候选代码被执行。

---

### 步骤 5：更新项目边界文档并完成 WP4-a 独立验收

**目标文件**：

- `README.md`（修改）
- `AGENTS.md`（修改）

**新增 / 修改的符号**：无 Python 符号。

**主要功能**：

- README 增加 Verification Layer 简述与最小 Python API 示例，只展示：
  - 从 `code_verifier.verification` 导入 `verify_completion`；
  - 调用方显式传入单一测试列表；
  - 结果通过 `verification_result_to_mapping()` 转为摘要；
  - 当前尚未实现 Public/Hidden reward，不提供训练命令。
- README 必须明确：
  - 解析失败不会执行代码；
  - candidate code 仍只由配置的 `CodeExecutor` 执行；
  - verifier 不选择测试层，不接受完整题目或 eval-hidden 容器；
  - 0 测试是合同错误；
  - mapping 不包含 completion/code/tests/metadata。
- AGENTS 项目结构增加 `verification/{result_types,verifier}.py` 与对应测试路径。
- AGENTS 当前 scope 更新为“WP0–WP3 完成，WP4-a verifier 已实现；WP4-b reward 尚未实现”；禁止执行者提前添加 reward/training/evaluation。
- 不更改 Makefile、CLI help、配置文件、依赖或 Open-R1 submodule。
- 执行者完成后在 `ai-work/executor/WP4-executor.md` 记录实际改动与命令结果；不得写 `proceedings.md`。

**配置 / CLI 变更**：无；必须明确记录“未修改原有配置、未新增依赖”。

**测试方案**：

- 运行全部 Verification 定向测试。
- 运行项目全量 CPU test，确保 WP0–WP3 无回归。
- 运行 lint/type/format 检查。
- 验证 CLI 未扩展：`.venv/bin/code-verifier --help` 仍返回 0，且不出现 WP4 reward/training 子命令。
- 搜索确认：
  - `src/code_verifier/rewards/` 不存在；
  - `third_party/open-r1/**` 无改动；
  - verifier 生产代码中没有 `exec(`、`eval(`、`compile(`、`subprocess`；
  - verifier 公共签名中没有 `eval_hidden_tests` 或测试层 selector。

**验证命令与通过标准**：

```bash
make lint
make test
.venv/bin/python -m pytest tests/unit/verification tests/integration/test_wp4a_verifier_pipeline.py
.venv/bin/code-verifier --help
```

通过标准：

- `make lint` 全绿（Ruff check、Ruff format --check、strict Mypy）；
- `make test` 全绿，只有现有真实 Piston tests 可按既有设计 skip，不得新增 skip/xfail；
- Verification 定向测试 0 failed、0 skipped；
- CLI help 返回 0，未新增 reward/training 命令；
- 没有配置、依赖、execution/parser、third-party 或 proceedings 变更；
- 文档状态准确标为 WP4-a，未宣称 WP4 整体完成。

## 6. 总体验收与测试计划

### 6.1 单元测试汇总

- `tests/unit/verification/test_result_types.py`
  - 结果合同、有限数值、mapping、安全字段、失败 count 守恒。
- `tests/unit/verification/test_verifier.py`
  - 输入校验、0 测试、顺序、通过率、提前停止、parse/timeout/sandbox 状态、异常失败关闭。

对应规格 §19.1：

- 通过率计算：全通过、部分通过、全失败精确断言；
- 0 个测试：调用前抛合同错误、零 executor 调用；
- 提前停止：未运行测试归入顶层失败状态，计数守恒；
- 测试顺序：规范化与 Mock 调用记录保持原顺序；
- 错误状态汇总：parser taxonomy、逐测试 status、aggregate status、sandbox exception 均可区分。

### 6.2 集成测试

- `tests/integration/test_wp4a_verifier_pipeline.py`
  - completion → `extract_python_code()` → `verify_completion()` → `MockExecutor.execute()` → `VerificationResult` → JSON mapping；
  - 覆盖 passed / partial / timeout / parse failure / sandbox error；
  - 不运行真实候选代码，不依赖外部服务。

### 6.3 本阶段最终通过标准

- [ ] §20 WP4 的 `verifier` 交付已完成；Reward 相关交付明确留给 WP4-b。
- [ ] 验证器只接收一个明确测试列表，不能访问完整题目或其它测试层。
- [ ] 0 测试在 parser/executor 前失败。
- [ ] parser 是唯一代码提取入口，executor 是唯一代码执行入口。
- [ ] 解析失败、timeout、sandbox error、executor exception 的结构化状态符合本计划。
- [ ] 通过率和 failure count 守恒，所有数值有限。
- [ ] 所有摘要 mapping 可严格 JSON 序列化且不含 completion/code/tests/metadata。
- [ ] `make lint` 全绿。
- [ ] `make test` 全绿，无新增 skip/xfail。
- [ ] Verification 定向测试 0 failed、0 skipped。
- [ ] 不新增配置、依赖或 CLI；不修改 execution/parser/data/training/third_party。
- [ ] `ai-work/executor/WP4-executor.md` 已记录实际实施与验证结果。
- [ ] `proceedings.md` 未被执行者修改。

## 7. 风险与注意事项

- **测试层泄漏风险**：统一验证器若接收 `CodeProblem` 或完整 record，后续 reward 很容易误读 eval-hidden。本计划强制只接收调用方已选择的一层 tests；WP4-b 再用两个薄封装控制来源。
- **0 测试虚高风险**：数学上空集合可能被错误解释为全部通过；本计划固定为空测试合同错误，禁止生成 reward 输入。
- **异常静默高分风险**：parser/执行合同异常不得默认通过。解析失败为 `PARSE_ERROR`，executor 异常为 `SANDBOX_ERROR`，pass rate 固定 0.0。
- **timeout 语义混淆**：timeout 是候选执行失败，不是基础设施失败；否则 WP4-b 无法按 §10.2 同时应用 executable 分量与 timeout penalty。
- **提前停止统计风险**：executor 可在首个失败后停止，`test_results` 数量小于 `total_tests`。未运行测试必须归入 aggregate status，确保失败计数与未通过测试数一致。
- **可变对象别名风险**：`ExecutionResult.test_results` 是 list；验证结果和 mapping 必须防御性复制，避免 caller/executor 后续修改历史结果。
- **敏感内容风险**：completion、code、tests、stdout/stderr 都可能含用户/模型内容。验证摘要不保存前三者；嵌套 execution mapping 只沿用 WP3 有界 stdout/stderr，后续 reward component log 不应默认复制嵌套结果。
- **过度捕获风险**：仅 executor 调用边界捕获普通 `Exception`，不捕获 `BaseException`；其它程序错误应由测试暴露，而不是被静默吞掉。
- **范围蔓延风险**：本阶段不得顺手实现 rewards、TRL adapter、训练配置、评测 CLI 或真实实验。

## 8. 后续 WP4-b 接口准备

本阶段结果必须足以让后续计划原样实现规格 §10.5 的接口，不得在 WP4-a 改写这些签名：

```python
def public_code_reward(
    completions,
    visible_tests,
    function_name,
    metadata,
    **kwargs,
) -> list[float]:
    ...


def hidden_code_reward(
    completions,
    train_hidden_tests,
    function_name,
    metadata,
    **kwargs,
) -> list[float]:
    ...


def compute_code_rewards(
    completions,
    tests_batch,
    function_names,
    metadata_batch,
    executor,
    mode: str,
) -> tuple[list[float], list[dict]]:
    ...
```

WP4-b 应直接消费 `verify_completion()` 和 `VerificationResult`：

- 主分量读取 `pass_rate`；
- executable 分量读取 `parsed`、`executed`、`infrastructure_failure`；
- timeout penalty 读取 `status is ExecutionStatus.TIMEOUT`；
- invalid-format penalty 读取 `status is ExecutionStatus.PARSE_ERROR`；
- sandbox failure 读取 `infrastructure_failure` 并确保不会得到正确答案分量；
- component log 读取 sanitized summary，不复制 completion/code/tests 或嵌套 stdout/stderr。

## 9. 关联文档索引

- `PROJECT_SPEC_Open-R1_CodeVerifier.md`
  - §6.2：Parsing / Execution / Verification / Reward 模块边界；
  - §10.1–§10.6：reward 原则、辅助分量、Public/Hidden 公式、API 与测试；
  - §16：`verification/` 与 `rewards/` 目标仓库结构；
  - §19.1：Verifier / Reward 单元测试；
  - §19.2：reward 批量集成测试；
  - §20 WP4：目标、交付、验收；
  - §29：函数级 Python、核心 Public-vs-Hidden 对照、非目标。
- `proceedings.md`
  - WP3：安全执行器已完成，WP4 尚未登记。
- `src/code_verifier/parsing/code_extractor.py`
  - `ParseResult`、`extract_python_code()`。
- `src/code_verifier/execution/base.py`
  - `ExecutionStatus`、`TestCaseResult`、`ExecutionResult`、`CodeExecutor`、合同校验与 mapping。
- `src/code_verifier/execution/mock.py`
  - FIFO、non-executing Mock 集成测试入口。
- `src/code_verifier/data/leakage_checks.py`
  - Public/Hidden training artifact 字段白名单与 eval-hidden 禁止规则。
