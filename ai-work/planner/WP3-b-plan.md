# WP3-b 实施计划（本地 Piston 单请求执行与安全限制）

## 1. 元信息

| 项 | 值 |
|---|---|
| 目标 WP | WP3：安全执行器（子阶段 b：本地 Piston 单请求执行与安全限制） |
| 规格依据 | `PROJECT_SPEC_Open-R1_CodeVerifier.md` §0、§6.2 Execution Layer、§8、§16、§19、§20 WP3、§24 Risk 3 / Risk 6、§29 |
| 前置阶段 | WP3-a（`proceedings.md` 状态：子阶段已完成；WP3 整体部分完成） |
| 计划文件 | `ai-work/planner/WP3-b-plan.md` |
| 面向的执行者 | 仅需仓库文件读写和基础 shell，可运行项目自带的 `make`、pytest 与本地 Piston 服务 |
| 计划粒度 | WP3 的第二个独立阶段；5 个步骤、2 个新业务模块 |
| 预计配置影响 | 新增本地 Piston YAML；修改 pytest marker 与 Makefile 测试目标；不新增 Python 依赖 |

> WP3-a 已冻结公共执行合同和非执行 Mock。本阶段实现单请求真实沙箱与安全验收，但不实现批量并发、缓存和执行 CLI；这些内容留给 WP3-c。完成本计划后，WP3 仍不得标记为整体完成。

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

在 WP3-a 公共合同之上实现一个只连接本机回环地址 Piston 服务的 `PistonExecutor`，逐测试执行函数级 Python 代码，并完成真实沙箱安全探针。阶段结束时必须能够：

- 构造隔离的候选代码文件与可信测试 harness；
- 通过 Piston `/api/v2/runtimes` 验证固定 Python runtime；
- 通过 Piston `/api/v2/execute` 执行单个测试；
- 将 Piston、harness 和传输错误确定性映射为 WP3-a 的 `ExecutionStatus`；
- 执行完整测试列表并支持配置化提前停止；
- 在真实本地 Piston 中验证超时、内存、输出、网络、文件、用户、PID 与清理边界；
- 保持宿主机不直接执行任何模型代码。

### 2.5 范围内

- 新建严格的本地 Piston 配置、stdlib HTTP transport 与响应大小限制。
- 新建 Python 函数测试 harness，明确 JSON input 调用约定和类型敏感比较规则。
- 实现 `PistonExecutor`，其 `execute()` 签名逐字匹配现有 `CodeExecutor` Protocol。
- 每个测试使用独立 Piston job，按原顺序返回 `TestCaseResult`。
- 支持 `run_timeout`、`run_cpu_time`、`run_memory_limit` 和客户端/服务端输出上限映射。
- 支持配置化 `stop_on_first_failure`；基础设施或资源失败必须强制停止。
- 增加 fake transport 单元测试与显式启用的真实 Piston 集成/安全测试。
- 增加 `make test-piston`、pytest marker、本地部署说明与最小 Python API 示例。

### 2.6 范围外

- 不实现 WP3-c 的批量请求类型、线程池/异步并发、缓存 key、缓存存储或执行 CLI。
- 不实现 WP4 verifier/reward，不选择 visible/train-hidden/eval-hidden 测试层。
- 不直接连接公共 Piston API，不处理 API token，不依赖外部账户。
- 不允许配置任意远程 URL；本阶段只接受 `localhost`、`127.0.0.1` 或 `::1`。
- 不在仓库中 vendoring、修改或复制 Piston 源码，不新增 Piston git submodule。
- 不新增 `requests`、`httpx`、Docker SDK 等 Python 依赖；HTTP 使用标准库。
- 不在宿主机调用 `exec()`、`eval()`、`compile()` 或无资源限制 Python subprocess 执行模型代码。
- 不承诺抵御候选代码对同一 sandbox job 内 Python harness 的所有高级解释器级攻击；必须记录为 MVP 限制，后续可升级为多进程/独立 verifier worker。
- 不修改 `third_party/open-r1/**`。
- 不修改 `proceedings.md`；本阶段通过后只能追加 WP3-b 子阶段记录，WP3 仍为部分完成。

## 3. 前置条件、现状与约束

### 3.1 proceedings 与当前代码结论

- `proceedings.md` 已登记 WP3-a 通过，合并后 `main` 为 263 tests passed。
- 当前 `src/code_verifier/execution/base.py` 已提供规格 §8.3 的类型、严格请求/结果校验和 JSON mapping。
- 当前 `src/code_verifier/execution/mock.py` 是测试替身，不执行代码；不得修改其语义来承担真实执行。
- 当前仓库没有真实 executor、execution YAML、Piston transport 或真实沙箱集成测试。
- WP3-a reviewer 已确认合同异常必须稳定、不得回显隐藏测试 payload；WP3-b 所有新增错误也必须遵守同一规则。

### 3.2 Piston API 与部署依据

本计划以 2026-08-05 核对的官方 `engineer-man/piston` README/API 合同为实现依据：

- runtime 列表：`GET /api/v2/runtimes`；
- 执行：`POST /api/v2/execute`；
- 请求字段：`language`、`version`、`files`、`stdin`、`args`、`compile_timeout`、`run_timeout`、`compile_cpu_time`、`run_cpu_time`、`compile_memory_limit`、`run_memory_limit`；
- stage 响应字段：`stdout`、`stderr`、`code`、`signal`、`message`、`status`、`cpu_time`、`wall_time`、`memory`；
- Piston stage status：`RE`、`SG`、`TO`、`OL`、`EL`、`XX`；
- Piston 官方安全模型基于 Docker 内的 Isolate、namespace、chroot、非特权用户、cgroup、网络禁用、进程/文件/时间/内存/输出限制和 job 清理。

公共 Piston API 自 2026-02-15 起不再自由开放，且本项目规格禁止把外部付费/账户沙箱作为唯一实现。因此本阶段只支持自托管、回环绑定的本地 Piston。

### 3.3 模块边界与硬性安全规则

- Execution Layer 只负责隔离执行和结构化结果，不解释 reward（§6.2）。
- 模型代码始终是不可信输入；宿主进程只能把字符串发送给 Piston，不能导入或运行候选代码。
- Piston 服务必须仅绑定回环接口；不得把 2000 端口公开到局域网或公网。
- 本地 Piston 必须使用独立 sandbox job、非 root runtime、禁用网络和清理临时目录。
- 配置不得包含密钥；异常和日志不得回显 code、input、expected 或完整 Piston body。
- 新模块必须包含 `from __future__ import annotations`、完整类型标注、简洁 docstring、明确错误处理和单元测试。
- 保持 Ruff 双引号、119 列和 strict mypy。
- 所有真实安全测试必须在 Piston sandbox 内执行；测试代码即使恶意也不得在宿主 Python 进程中运行。

### 3.4 本阶段明确实现决策

1. **仅回环 endpoint**：`base_url` host 只允许 `localhost`、`127.0.0.1`、`::1`，scheme 只允许 `http`，不得包含 userinfo、query、fragment 或非根 path。transport 禁用代理和 HTTP redirect，避免绕过回环限制。
2. **固定 runtime**：配置必须给出精确 `language: python` 和精确 SemVer `version`，不允许 `*`、`3`、`3.x` 等 selector。`validate_runtime()` 必须在 `/runtimes` 中找到完全一致的 language/version。
3. **每测试一个 job**：`execute()` 按测试顺序为每个 test 发起独立 `/execute` 请求，避免前一个候选运行污染后一个测试。批量优化留到 WP3-c。
4. **input 调用约定**：
   - `input` 为 list：调用 `target(*input)`；
   - `input` 为 dict：调用 `target(**input)`；
   - 其他 JSON 值：调用 `target(input)`。
5. **严格比较**：actual 与 expected 使用类型敏感递归等价；`True`、`1`、`1.0` 不互相等价；list 顺序敏感；dict key 集合和值均必须一致；候选返回非 JSON 值视为 `WRONG_ANSWER`，不回显 actual/expected。
6. **harness 协议**：候选代码保存为 `candidate.py`，可信 runner 保存为第一个文件 `main.py`；测试 input/expected 通过 stdin JSON 传入。runner 在读取 stdin 后才 import candidate，并把最终结构化报告写为 stdout 最后一行的 marker JSON。
7. **输出控制**：runner 用 UTF-8 字节计数的 bounded writer 捕获普通 Python stdout/stderr；超过 `max_output_bytes` 返回 `OUTPUT_LIMIT`。绕过 Python stream 的 fd 写入由 Piston `OL`/`EL` 和客户端 response byte cap 兜底。
8. **状态映射**：
   - harness `passed` → `PASSED`；
   - harness `wrong_answer` → `WRONG_ANSWER`；
   - harness `syntax_error` → `SYNTAX_ERROR`；
   - harness `runtime_error` → `RUNTIME_ERROR`；
   - harness `output_limit` → `OUTPUT_LIMIT`；
   - Piston `TO` → `TIMEOUT`；
   - Piston `OL` / `EL` → `OUTPUT_LIMIT`；
   - Piston `XX`、HTTP/JSON/schema 错误、缺失可信 marker → `SANDBOX_ERROR`；
   - Piston `SG` 且 message 明确包含 memory，或 `SIGKILL` 且 reported memory 达到配置 limit 的 95% → `MEMORY_LIMIT`；其他 signal/nonzero exit → `RUNTIME_ERROR`。
9. **停止策略**：`stop_on_first_failure=true` 时任何非 PASSED 停止；为保护服务，`SYNTAX_ERROR`、`TIMEOUT`、`MEMORY_LIMIT`、`OUTPUT_LIMIT`、`SANDBOX_ERROR` 无论配置为何均停止。`WRONG_ANSWER` / `RUNTIME_ERROR` 在 false 时可继续。
10. **整体状态**：所有测试完整通过为 `PASSED`；否则取请求顺序中第一个非 PASSED 状态。`passed_tests / total_tests` 始终以原始请求测试总数计算，兼容提前停止。
11. **空测试**：不访问 Piston，返回 `status=PASSED`、0/0、`pass_rate=0.0`、空结果；WP4 必须在 verifier 层定义 0 测试是否可接受。
12. **错误脱敏**：transport 和 parser 仅向 `TestCaseResult.stderr` 写固定分类文本，如 `piston transport failed`、`invalid piston response`；不放 URL、response body、候选代码或测试内容。
13. **真实测试隔离**：真实 Piston 测试使用 `piston` marker，不纳入默认 CI；`make test-piston` 必须显式运行，且阶段验收不能以 skipped 测试代替。

## 4. 目标文件总览

### 4.1 新建

- `configs/execution/piston-local.yaml`
- `src/code_verifier/execution/harness.py`
- `src/code_verifier/execution/piston.py`
- `tests/unit/execution/test_harness.py`
- `tests/unit/execution/test_piston.py`
- `tests/integration/test_wp3b_piston_execution.py`
- `docs/piston-local.md`

### 4.2 修改

- `src/code_verifier/execution/__init__.py`
- `pyproject.toml`
- `Makefile`
- `README.md`
- `AGENTS.md`

### 4.3 明确不修改

- `src/code_verifier/execution/base.py` 的 §8.3 公开类型与 `CodeExecutor` 签名
- `src/code_verifier/execution/mock.py`
- `src/code_verifier/parsing/**`
- `src/code_verifier/data/**`
- `src/code_verifier/cli.py`
- `src/code_verifier/training/**`
- `third_party/open-r1/**`
- `proceedings.md`

## 5. 实施步骤

### 步骤 1：实现严格本地 Piston 配置和有界 HTTP transport

**目标文件**：

- `configs/execution/piston-local.yaml`（新建）
- `src/code_verifier/execution/piston.py`（新建）

**新增 / 修改的符号**：

```python
class PistonTransportError(RuntimeError):
    """Raised when the local Piston HTTP boundary cannot return a valid bounded response."""


@dataclass(frozen=True)
class PistonExecutorConfig:
    base_url: str
    language: str
    version: str
    request_timeout_margin_seconds: float
    max_response_bytes: int
    max_output_bytes: int
    stop_on_first_failure: bool


class PistonTransport(Protocol):
    def list_runtimes(
        self,
        *,
        timeout_seconds: float,
        max_response_bytes: int,
    ) -> object:
        ...

    def execute_request(
        self,
        payload: dict[str, object],
        *,
        timeout_seconds: float,
        max_response_bytes: int,
    ) -> object:
        ...


class UrlLibPistonTransport:
    def __init__(self, base_url: str) -> None:
        """Create a no-proxy, no-redirect transport for one validated loopback Piston base URL."""

    def list_runtimes(
        self,
        *,
        timeout_seconds: float,
        max_response_bytes: int,
    ) -> object:
        """GET the bounded local /api/v2/runtimes JSON value."""

    def execute_request(
        self,
        payload: dict[str, object],
        *,
        timeout_seconds: float,
        max_response_bytes: int,
    ) -> object:
        """POST one bounded local /api/v2/execute JSON request."""


def piston_executor_config_from_mapping(value: object) -> PistonExecutorConfig:
    """Parse one exact execution.piston config mapping and reject unknown fields."""


def load_piston_executor_config(path: Path) -> PistonExecutorConfig:
    """Load and strictly validate one local Piston YAML config."""
```

**配置合同**：

`configs/execution/piston-local.yaml` 必须使用：

```yaml
piston:
  base_url: http://127.0.0.1:2000
  language: python
  version: "3.10.0"
  request_timeout_margin_seconds: 2.0
  max_response_bytes: 131072
  max_output_bytes: 4096
  stop_on_first_failure: false
```

**主要功能**：

- 配置顶层字段必须恰好为 `piston`；内部字段必须恰好匹配 dataclass，不允许未知或缺失字段。
- `language` 只允许精确值 `python`；`version` 必须匹配 `MAJOR.MINOR.PATCH`。
- `request_timeout_margin_seconds` 为有限正数；两个 byte limit 为正 int、非 bool；`max_response_bytes` 至少大于 `2 * max_output_bytes + 4096`。
- `base_url` 经 `urllib.parse.urlsplit()` 校验，只允许本地回环 host、默认/显式端口、空 path 或 `/`。
- `UrlLibPistonTransport` 使用 `urllib.request.build_opener(ProxyHandler({}), no-redirect handler)`：
  - 不读取系统 HTTP proxy；
  - 3xx 一律失败；
  - Content-Type 必须为 JSON 或可接受的 `application/*+json`；
  - 最多读取 `max_response_bytes + 1`，超限后关闭连接并抛固定 `PistonTransportError`；
  - HTTP error、URL error、socket timeout、Unicode/JSON error均转换为固定分类消息，不透传 response body。
- POST JSON 使用 `allow_nan=False`、UTF-8、`Content-Type: application/json`。
- transport 不记录 payload、stdin 或 response body。

**测试方案**：

- 测试文件：`tests/unit/execution/test_piston.py`
- 新增测试函数：
  - `test_piston_config_accepts_exact_local_mapping`。
  - `test_piston_config_rejects_missing_and_unknown_fields`。
  - `test_piston_config_rejects_remote_userinfo_query_fragment_and_path`。
  - `test_piston_config_rejects_runtime_selectors_and_non_python_language`。
  - `test_piston_config_rejects_invalid_limits_and_bool_numbers`。
  - `test_transport_builds_exact_runtime_and_execute_paths`。
  - `test_transport_disables_proxy_and_redirects`。
  - `test_transport_rejects_non_json_and_oversized_response`。
  - `test_transport_sanitizes_http_and_json_errors`：response sentinel 不出现在异常文本。
- 测试使用 monkeypatch/fake opener 或本地测试 HTTP server，但不得连接互联网。

**验证命令与通过标准**：

```bash
make lint
.venv/bin/python -m pytest tests/unit/execution/test_piston.py -k "config or transport"
```

通过标准：配置/transport 测试全部通过；remote URL、redirect、proxy 和过大 response 均被拒绝；错误不含 payload/response sentinel；未新增 Python 依赖。

---

### 步骤 2：实现函数级 Python 测试 harness 与可信结果协议

**目标文件**：

- `src/code_verifier/execution/harness.py`（新建）
- `tests/unit/execution/test_harness.py`（新建）

**新增 / 修改的符号**：

```python
HarnessOutcome: TypeAlias = Literal[
    "passed",
    "wrong_answer",
    "syntax_error",
    "runtime_error",
    "output_limit",
    "harness_error",
]


@dataclass(frozen=True)
class PythonTestProgram:
    files: list[dict[str, str]]
    stdin: str
    marker: str


@dataclass(frozen=True)
class HarnessReport:
    outcome: HarnessOutcome
    runtime_ms: float
    stdout: str
    stderr: str


def build_python_test_program(
    code: str,
    function_name: str,
    test: dict[str, Any],
    *,
    marker: str,
    max_output_bytes: int,
) -> PythonTestProgram:
    """Build candidate.py, trusted main.py, and stdin JSON for one isolated function test."""


def parse_harness_report(
    stdout: str,
    *,
    marker: str,
    max_output_bytes: int,
) -> HarnessReport | None:
    """Parse only the final trusted marker line and return a validated bounded report."""
```

**主要功能**：

- `build_python_test_program()` 先调用现有 `validate_execution_request()` 的等价单测试边界，或由调用方保证已验证；自身仍检查 marker 和 byte limit。
- files 顺序固定：
  1. `main.py`：项目生成的可信 runner；
  2. `candidate.py`：原始候选 code，不做格式化或拼接。
- stdin 使用 `json.dumps(..., allow_nan=False, ensure_ascii=False, separators=(",", ":"))` 序列化：
  - `function_name`；
  - `input`；
  - `expected`；
  - marker；
  - `max_output_bytes`。
- `main.py` 必须完全自包含，只使用 Python 标准库，不能 import `code_verifier`。
- runner 行为：
  1. 一次性读取并解析 stdin，然后使 stdin 到 EOF；
  2. 保存可信的 JSON/时间/输出引用；
  3. 使用 bounded text writer 捕获 candidate import 和函数调用的普通 stdout/stderr；
  4. import `candidate.py`，精确查找模块顶层目标 callable；
  5. 按 §3.4 调用约定执行；
  6. 用内嵌类型敏感递归 comparator 比较 actual/expected；
  7. 输出一条最终 marker JSON，不输出 actual、expected、traceback 或输入内容。
- syntax import 错误为 `syntax_error`；缺函数、候选异常、非 callable 为 `runtime_error`；比较失败/非 JSON actual 为 `wrong_answer`；bounded writer 超限为 `output_limit`；runner 自身协议错误为 `harness_error`。
- marker 格式固定为 `__CODE_VERIFIER_RESULT__:{marker}:{compact_json}`，只解析 stdout 最后一条非空行；earlier spoof line 必须忽略。
- `parse_harness_report()` 严格要求字段恰好为 `outcome/runtime_ms/stdout/stderr`，runtime 有限非负，输出 UTF-8 byte 长度不超过 limit，outcome 属于枚举。
- 任何 malformed、重复 key、未知字段、错误 marker 或超大 report 返回 `None`，不抛用户可见 payload 异常。

**测试方案**：

- 测试文件：`tests/unit/execution/test_harness.py`
- 新增测试函数：
  - `test_build_program_uses_main_then_candidate_files`。
  - `test_build_program_keeps_candidate_code_exact`。
  - `test_build_program_serializes_test_only_in_stdin`：candidate/main 文件均不出现 expected sentinel。
  - `test_harness_list_input_uses_positional_arguments`。
  - `test_harness_dict_input_uses_keyword_arguments`。
  - `test_harness_scalar_input_uses_single_argument`。
  - `test_harness_comparison_is_type_sensitive`：bool/int/float 不等价。
  - `test_harness_reports_syntax_runtime_wrong_answer_and_passed`。
  - `test_harness_rejects_non_json_actual_as_wrong_answer`。
  - `test_harness_bounded_stdout_and_stderr_report_output_limit`。
  - `test_parse_report_uses_only_final_matching_marker`。
  - `test_parse_report_rejects_spoof_malformed_duplicate_key_unknown_field_and_nonfinite_runtime`。
  - `test_reports_do_not_contain_input_expected_or_traceback_sentinels`。
- harness 单元测试允许在测试进程中运行**仅项目生成的可信 runner fixture**，但禁止把任意用户输入直接交给宿主 `exec()`；候选 fixture 必须是测试源码中固定、审计过的短字符串。真实恶意代码只在步骤 4 的 Piston 集成中运行。

**验证命令与通过标准**：

```bash
make lint
.venv/bin/python -m pytest tests/unit/execution/test_harness.py
```

通过标准：调用约定、严格比较、marker、防 spoof、输出限制与脱敏测试全部通过；候选文件保持逐字一致；报告不包含 hidden sentinel 或 traceback。

---

### 步骤 3：实现 Piston 响应解析与 `PistonExecutor`

**目标文件**：

- `src/code_verifier/execution/piston.py`（继续修改）
- `src/code_verifier/execution/__init__.py`（修改）
- `tests/unit/execution/test_piston.py`（继续修改）

**新增 / 修改的符号**：

```python
@dataclass(frozen=True)
class _PistonStageResult:
    stdout: str
    stderr: str
    code: int | None
    signal: str | None
    message: str | None
    status: str | None
    cpu_time_ms: float
    wall_time_ms: float
    memory_bytes: int | None


def _parse_piston_stage(value: object) -> _PistonStageResult:
    """Parse one exact bounded compile/run stage without coercing malformed fields."""


def _map_piston_stage_failure(
    stage: _PistonStageResult,
    *,
    memory_limit_bytes: int,
) -> ExecutionStatus | None:
    """Map a failed Piston stage to one deterministic public execution status."""


class PistonExecutor:
    def __init__(
        self,
        config: PistonExecutorConfig,
        *,
        transport: PistonTransport | None = None,
        marker_factory: Callable[[], str] | None = None,
    ) -> None:
        """Create a synchronous single-request executor backed by one local Piston service."""

    def validate_runtime(self) -> str:
        """Require the configured exact Python runtime to be installed and return its version."""

    def execute(
        self,
        code: str,
        function_name: str,
        tests: list[dict[str, Any]],
        timeout_seconds: float,
        memory_limit_mb: int,
    ) -> ExecutionResult:
        """Execute tests in request order using one isolated Piston job per test."""
```

**主要功能**：

- `PistonExecutor` 必须结构兼容现有 `CodeExecutor`，不得改变 §8.3 签名。
- constructor 不发网络请求；默认 transport 为 `UrlLibPistonTransport(config.base_url)`；marker factory 默认为 `secrets.token_hex(16)`。
- `validate_runtime()`：
  - runtime response 必须是 list of exact objects；
  - 找到 `language == python` 且 `version == config.version`；
  - 缺失、重复、malformed 或 transport failure 抛固定 `PistonTransportError`；
  - 错误不回显完整 runtime response。
- 每个 test 的 Piston payload 精确包含：

```python
{
    "language": config.language,
    "version": config.version,
    "files": program.files,
    "stdin": program.stdin,
    "args": [],
    "compile_timeout": timeout_ms,
    "run_timeout": timeout_ms,
    "compile_cpu_time": timeout_ms,
    "run_cpu_time": timeout_ms,
    "compile_memory_limit": memory_limit_bytes,
    "run_memory_limit": memory_limit_bytes,
}
```

- `timeout_ms` 使用 `ceil(timeout_seconds * 1000)` 并检查不会超过合理上限；HTTP timeout 为 `timeout_seconds + request_timeout_margin_seconds`。
- response 必须是 object，`run` 必须存在；Python response 出现失败 compile stage 时视为 `SANDBOX_ERROR`，因为候选语法由 harness import 分类。
- `_parse_piston_stage()` 严格检查类型、非负有限时间和 memory；不使用 `str(value)` / `int(value)` coercion。
- 单测试映射顺序：
  1. transport/response schema failure → `SANDBOX_ERROR`；
  2. Piston stage failure status → §3.4 映射；
  3. stage code 0 时解析最终 harness marker；
  4. marker 缺失/malformed → `SANDBOX_ERROR`；
  5. harness outcome →对应 `ExecutionStatus`。
- `TestCaseResult.stdout/stderr` 只使用 harness 捕获输出；Piston wrapper marker、message 和 response body不得进入公开结果。资源/transport failure 只保留按 byte limit 截断的 stage stdout/stderr，且不得包含 stdin test JSON。
- `execute()`：
  - 首先调用 `validate_execution_request()`；
  - 深复制 tests；
  - 空测试返回 §3.4 约定结果；
  - 顺序执行并累计 wall time；
  - 应用停止策略；
  - 构造 `ExecutionResult` 后调用 `validate_execution_result()`；
  - 防御性复制 `test_results` 后返回。
- `src/code_verifier/execution/__init__.py` 增加导出：`PistonExecutor`、`PistonExecutorConfig`、`PistonTransportError`、`load_piston_executor_config`；transport 和内部 stage 类型不作为稳定公共 API。

**测试方案**：

- 测试文件：`tests/unit/execution/test_piston.py`
- 使用确定性 fake transport，不运行代码。
- 新增测试函数：
  - `test_validate_runtime_requires_exact_installed_python_version`。
  - `test_validate_runtime_rejects_duplicate_and_malformed_runtime_records`。
  - `test_execute_payload_contains_exact_files_stdin_and_resource_limits`。
  - `test_execute_maps_harness_pass_wrong_answer_syntax_runtime_and_output_limit`。
  - `test_execute_maps_piston_timeout_output_internal_and_signal_statuses`。
  - `test_execute_maps_memory_signal_only_with_message_or_threshold`。
  - `test_execute_missing_or_spoofed_marker_is_sandbox_error`。
  - `test_execute_transport_error_is_sanitized_sandbox_error`。
  - `test_execute_empty_tests_does_not_call_transport`。
  - `test_execute_stop_on_first_failure_controls_wrong_answer_and_runtime_error`。
  - `test_execute_always_stops_on_resource_and_infrastructure_failures`。
  - `test_execute_preserves_test_order_and_pass_rate_denominator`。
  - `test_execute_returns_result_accepted_by_execution_contract_and_json_mapping`。
  - `test_piston_executor_satisfies_code_executor_protocol_under_mypy`。
  - `test_result_and_errors_do_not_echo_code_input_expected_marker_or_response_sentinels`。

**验证命令与通过标准**：

```bash
make lint
.venv/bin/python -m pytest tests/unit/execution/test_piston.py
```

通过标准：fake transport 单元测试全绿；所有状态映射、停止策略、payload、脱敏和 Protocol 合同可判定通过；`execution_result_to_mapping()` 可用 `allow_nan=False` JSON 编码。

---

### 步骤 4：建立显式真实 Piston 集成与安全验收套件

**目标文件**：

- `tests/integration/test_wp3b_piston_execution.py`（新建）
- `pyproject.toml`（修改）
- `Makefile`（修改）

**新增 / 修改的测试符号**：

```python
@pytest.fixture(scope="module")
def piston_executor() -> PistonExecutor:
    """Load the configured local Piston executor and validate the exact runtime once."""


def test_piston_correct_wrong_syntax_and_runtime_statuses(piston_executor: PistonExecutor) -> None:
    ...


def test_piston_infinite_loop_times_out_and_service_recovers(piston_executor: PistonExecutor) -> None:
    ...


def test_piston_memory_limit_and_output_limits(piston_executor: PistonExecutor) -> None:
    ...


def test_piston_blocks_network_root_and_base_filesystem_write(piston_executor: PistonExecutor) -> None:
    ...


def test_piston_cannot_read_host_sentinel_and_cleans_job_temp_state(
    piston_executor: PistonExecutor,
    tmp_path: Path,
) -> None:
    ...


def test_piston_pid_limit_contains_process_bomb_and_service_recovers(piston_executor: PistonExecutor) -> None:
    ...
```

**pytest / Makefile 变更**：

- `pyproject.toml [tool.pytest.ini_options]` 新增 marker：

```toml
markers = ["piston: requires an explicitly enabled self-hosted loopback Piston service"]
```

- `Makefile` 新增：

```make
PISTON_CONFIG ?= configs/execution/piston-local.yaml

.PHONY: test-piston

test-piston:
	CODE_VERIFIER_RUN_PISTON=1 CODE_VERIFIER_PISTON_CONFIG=$(PISTON_CONFIG) \
	$(PYTHON) -m pytest -m piston tests/integration/test_wp3b_piston_execution.py -ra
```

**主要功能与安全探针**：

- module 必须标记 `pytestmark = pytest.mark.piston`。
- 未设置 `CODE_VERIFIER_RUN_PISTON=1` 时，测试必须 module-level skip；默认 `make test` 不连接服务。
- 显式运行时缺少 config、runtime 或服务必须失败，不得 skip。
- 使用固定、可审计的候选代码执行以下真实探针：
  - 正确实现 → `PASSED`；
  - 错误实现 → `WRONG_ANSWER`；
  - 语法错误 → `SYNTAX_ERROR`；
  - 抛异常 → `RUNTIME_ERROR`；
  - `while True` → `TIMEOUT`；
  - 超过 memory limit 的分配 → `MEMORY_LIMIT`；若当前 Piston 版本不能可靠区分，测试必须失败并在 review 中记录，不得降级为宽松断言；
  - stdout 与 stderr 爆炸 → `OUTPUT_LIMIT`；
  - socket outbound connect → 无法建立连接，候选捕获异常并返回 `blocked`；
  - `os.geteuid()` → 非 0；
  - 写 `/etc/code_verifier_probe` → 失败；
  - 读取宿主随机 sentinel 绝对路径 → 失败，且宿主文件内容不变；
  - job A 写 sandbox `/tmp` token，job B 读取不到 → job 清理与隔离；
  - 并发创建超过 PID cap 的进程 bomb → 非 PASSED 且在 timeout 内结束；
  - 每个恶意探针后执行一个正确 smoke，证明 Piston 服务仍可用。
- 测试不得假定候选能访问项目仓库、用户 home 或 Docker socket。
- 每个测试 timeout 应保持小而确定，整个真实套件应在 120 秒内完成。
- 运行前后检查宿主 `tmp_path` sentinel 的存在、内容和 mtime；不能仅根据 Piston status 推断“不污染宿主”。

**验证命令与通过标准**：

```bash
make lint
make test
make test-piston PISTON_CONFIG=configs/execution/piston-local.yaml
```

通过标准：

- 默认 `make test` 全绿；真实 Piston 文件只显示 skip 或被 marker 排除，不连接服务。
- `make test-piston` 输出必须是所有 piston 测试 passed、0 failed、0 skipped。
- 正确/错误/语法/运行/超时/内存/输出状态逐项精确匹配。
- 网络、root、基础文件写、宿主 sentinel 读取、跨 job temp 与 PID bomb 探针全部通过。
- 每个恶意探针后的健康 smoke 通过。
- 宿主 sentinel 内容与 mtime 未变化，仓库没有新增 sandbox 产物。

---

### 步骤 5：补充本地 Piston 运维文档、公开示例与阶段总验收

**目标文件**：

- `docs/piston-local.md`（新建）
- `README.md`（修改）
- `AGENTS.md`（修改）

**文档内容**：

`docs/piston-local.md` 必须包含：

1. Piston 是仓库外部的本地服务，不是本项目 submodule。
2. 只允许回环绑定；禁止局域网/公网暴露。
3. 按官方说明自托管并安装与 YAML 完全一致的 Python runtime。
4. 固定并记录 Piston git commit、容器 image digest、Python runtime version、Docker/cgroup 版本。
5. Piston API container 可能需要高权限，必须在专用开发环境部署；不要把 Docker socket 挂入执行 job。
6. 运行 `/runtimes` 健康检查、`make test-piston` 和停止服务的命令框架；不得写入用户特定绝对路径。
7. 安全验收失败时的处理：不得继续 WP3-c，不得回退到宿主机执行，不得放宽测试预期。
8. 当前已知限制：同一 Piston job 内 Python harness 与候选共享解释器进程；高级 harness tampering 不属于本阶段完全解决范围。

README 必须：

- 将状态更新为 WP3-a + WP3-b 已实现，但 WP3 整体仍部分完成。
- 明确默认 `make test` 不运行真实 Piston，真实安全验收使用 `make test-piston`。
- 给出最小 Python API 示例：加载 config、构造 `PistonExecutor`、`validate_runtime()`、`execute()`、序列化结果。
- 明确不可使用公共 Piston endpoint，且不能直接执行模型代码。
- 指向 `docs/piston-local.md`，不复制大量部署细节。

AGENTS 必须：

- 结构中新增 `execution/harness.py`、`execution/piston.py`、Piston tests 和 config。
- 当前范围改为：WP3-b 单请求真实执行已实现；未经后续计划不得加入批量/缓存、WP4、训练或评测。
- 增加规则：真实 Piston 测试必须显式运行；任何安全探针失败都阻断合并。

**最终验证命令与通过标准**：

```bash
make lint
make test
make test-piston PISTON_CONFIG=configs/execution/piston-local.yaml
.venv/bin/python -c "from pathlib import Path; from code_verifier.execution import PistonExecutor, load_piston_executor_config; executor = PistonExecutor(load_piston_executor_config(Path('configs/execution/piston-local.yaml'))); print(executor.validate_runtime())"
```

通过标准：

- `make lint` 全绿：Ruff check、Ruff format check、strict Mypy 无错误。
- `make test` 全绿，WP0–WP3-a 无回归。
- `make test-piston` 全部通过且无 skip。
- runtime smoke 输出 YAML 中的精确版本。
- README/文档不声称 WP3 整体完成，不提供公共 API token 或远程 endpoint 示例。
- `git diff -- third_party/open-r1` 为空；无候选代码在宿主机执行。
- reviewer 必须进行高风险人工审查，重点检查 transport SSRF/redirect、harness marker、状态映射和真实安全探针。

## 6. 总体验收与测试计划

### 6.1 单元测试汇总

- `tests/unit/execution/test_harness.py`
  - 调用约定；
  - 类型敏感比较；
  - syntax/runtime/wrong/pass；
  - bounded output；
  - marker 与 spoof 防护；
  - report schema 与脱敏。
- `tests/unit/execution/test_piston.py`
  - 严格 YAML；
  - loopback-only URL；
  - no-proxy/no-redirect transport；
  - bounded HTTP/JSON；
  - runtime 校验；
  - payload 和资源限制；
  - 全状态映射；
  - 停止策略与总结果；
  - Protocol、序列化和脱敏。

### 6.2 真实集成测试

- `tests/integration/test_wp3b_piston_execution.py`
  - 正确、错误、语法、运行；
  - 无限循环；
  - 内存；
  - stdout/stderr 爆炸；
  - 网络禁用；
  - 非 root；
  - 基础文件系统写保护；
  - 宿主文件不可见；
  - 跨 job 清理；
  - PID 限制；
  - 恶意探针后服务健康。

### 6.3 数据泄漏检查

- transport、harness parser、异常和公开结果不得回显 input/expected。
- candidate 自己打印的内容允许进入受限 stdout/stderr，但默认日志不得自动打印这些字段。
- 真实集成使用 sentinel，断言异常、README smoke 和测试输出均不包含 sentinel。
- 本阶段不选择隐藏测试层，不接触训练 artifact。

### 6.4 本子阶段最终通过标准

- [ ] `PistonExecutor.execute()` 与 §8.3 `CodeExecutor` 签名完全一致。
- [ ] 配置只允许回环、自托管、精确 Python runtime。
- [ ] HTTP transport 禁用 proxy/redirect并限制 response bytes。
- [ ] 函数调用约定和类型敏感比较有明确测试。
- [ ] Piston/harness/transport 错误稳定映射为有限 `ExecutionStatus`。
- [ ] 正确、错误、语法、运行、超时、内存、输出真实状态全部精确通过。
- [ ] 网络、root、文件系统、宿主文件、清理和 PID 安全探针通过。
- [ ] 恶意探针后服务仍健康，宿主 sentinel 未变化。
- [ ] `make lint`、`make test`、`make test-piston` 全绿。
- [ ] 未新增远程账户依赖、宿主执行路径或 `third_party/open-r1` 修改。
- [ ] 文档明确 WP3 仍为部分完成。

### 6.5 WP3 整体仍未通过的项目

完成本计划后，以下内容仍留给 WP3-c：

- [ ] 批量执行请求/结果类型；
- [ ] 有限并发和配置化并发数；
- [ ] cache key 包含 code hash、problem ID、test layer、tests hash、executor version；
- [ ] 默认关闭/审慎启用的缓存策略；
- [ ] 执行调试 CLI 与公共参数；
- [ ] 批量/缓存/CLI 测试；
- [ ] WP3 所有子阶段的最终回归、审查和整体完成记录。

## 7. 风险与注意事项

- **Piston 服务自身高权限**：Piston API container 的部署权限是高风险运维边界；必须回环绑定、固定版本、专机运行，不能把 Docker socket 或用户目录暴露给 job。
- **SSRF / redirect**：即使 YAML 是项目配置，也必须在代码层拒绝 remote URL、proxy 和 redirect，防止后续 CLI 参数扩展引入远程访问。
- **harness spoof**：候选可打印 marker 文本；parser 只能接受最后一条、随机 marker、严格 schema 的可信 report。marker 缺失不能猜测通过。
- **同进程 harness tampering**：候选与 runner 共享 Python interpreter；保存可信引用和最终 marker可降低普通篡改，但不是完整安全证明。不得把该限制隐藏在文档外。
- **memory 状态歧义**：Piston 可能用 `SG/SIGKILL` 表示 OOM；必须使用 message + reported memory 的确定规则，并以真实集成结果为准。无法精确分类时阶段不通过。
- **内部 pipe/output 风险**：不得用无界 `subprocess(..., capture_output=True)` 在 harness 内收集候选输出；本计划使用 bounded writer + Piston server cap + HTTP response cap。
- **测试诱发资源压力**：PID bomb、memory bomb、output bomb必须设置小 limit、短 timeout，并在专用本地服务运行；每个探针后验证服务健康。
- **错误日志泄漏**：Piston response 和 candidate output可能包含隐藏数据；异常、transport logs 和默认测试输出不得自动打印 raw body。
- **Risk 3 性能**：每测试一个 job开销较高，但本阶段优先正确性与隔离；批量/并发优化必须留到 WP3-c，不能削弱安全边界。
- **Risk 6 回退纪律**：若 Piston 无法满足安全验收，可后续规划 DockerExecutor；不得改为宿主机直接执行。

## 8. 后续阶段边界

### WP3-c：批量并发、缓存、CLI 与 WP3 完整验收

后续计划应覆盖：

- 批量 request/result 数据类型；
- 有限线程池或异步并发；
- 配置化 `max_concurrency`；
- 完整 cache key 和 executor version；
- 默认关闭、训练模式审慎启用的缓存；
- 执行调试 CLI；
- mock + Piston 批量测试；
- WP3 全部交付和验收的最终独立审查。

## 9. 关联文档索引

- `PROJECT_SPEC_Open-R1_CodeVerifier.md`
  - §0：安全、配置、类型、测试和范围纪律
  - §6.2：Execution Layer 模块边界
  - §8.1：不可信代码安全原则
  - §8.2：本地 Piston 推荐顺序
  - §8.3：公共执行接口
  - §8.4：网络、用户、文件、时间、内存、PID、输出和清理限制
  - §8.5：批量、并发和缓存（WP3-c）
  - §16：`execution/piston.py` 目标结构
  - §19.1 Executor、§19.2 真实沙箱、§19.3 CI
  - §20 WP3：完整目标、交付和验收
  - §24 Risk 3 / Risk 6：性能和执行器回退
  - §29：Python 函数级任务与本地沙箱默认决策
- `proceedings.md`
  - WP3-a：子阶段已完成；真实沙箱、资源限制、批量、缓存仍未实现
- 当前实现
  - `src/code_verifier/execution/base.py`：公共合同、验证与 JSON mapping
  - `src/code_verifier/execution/mock.py`：非执行 Mock
  - `src/code_verifier/config.py`：严格 YAML loader
  - `src/code_verifier/data/schema.py`：JSON value 合同
- 外部实现参考
  - 官方 `engineer-man/piston` README/API：本地安装、`/runtimes`、`/execute`、请求/响应字段、status 和安全模型
