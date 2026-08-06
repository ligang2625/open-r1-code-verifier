# WP3-c 实施计划（批量并发、可选缓存、执行 CLI 与 WP3 整体验收）

## 1. 元信息

| 项 | 值 |
|---|---|
| 目标 WP | WP3：安全执行器（子阶段 c：批量并发、可选缓存、执行 CLI 与整体收口） |
| 规格依据 | `PROJECT_SPEC_Open-R1_CodeVerifier.md` §0、§6.2 Execution Layer、§8.3–§8.5、§16、§17、§19、§20 WP3、§24 Risk 3 / Risk 6、§29 |
| 前置阶段 | WP3-b（`proceedings.md` 状态：子阶段已完成；WP3 整体仍为部分完成） |
| 计划文件 | `ai-work/planner/WP3-c-plan.md` |
| 面向的执行者 | 仅需仓库文件读写与基础 shell，可运行项目自带的 `make`、pytest、CLI 和本地 Piston 服务 |
| 计划粒度 | WP3 的第三个且计划中的最终子阶段；6 个步骤、2 个新业务模块 |
| 预计配置影响 | 新增 batch execution YAML；扩展 Makefile Piston 验收目标；不新增 Python package 依赖 |

> WP3-a 已完成公共合同与 Mock，WP3-b 已完成本地 Piston 单请求真实执行和安全限制。本计划只完成 WP3 剩余的批量验证、有限并发、可选缓存、执行调试 CLI 和整体最终验收，不实现 WP4 verifier/reward。

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

在现有 `CodeExecutor` 单请求接口之上建立稳定的批量编排层，使调用方能够：

- 提交带 `problem_id`、测试层和资源限制的批量执行请求；
- 使用配置化、严格有界的并发执行请求；
- 无论任务完成顺序如何，始终按输入顺序返回结构化结果；
- 通过显式策略启用只读或读写缓存；
- 使用包含规格 §8.5 全部必需字段的稳定缓存 key；
- 默认禁止训练模式缓存，只有明确配置时才允许；
- 通过 JSONL CLI 调试批量 Piston 执行，不输出原始代码或测试内容；
- 在 Mock 和真实 Piston 两条路径上完成 WP3 整体最终验收。

### 2.5 范围内

- 新建 `execution/cache.py`：稳定缓存 key、cache Protocol 和 SQLite 持久缓存。
- 新建 `execution/batch.py`：批量请求/结果类型、配置、有限并发和缓存编排。
- 为现有 `ExecutionResult` 增加严格的 mapping 反序列化函数。
- 为现有 Piston executor 增加确定性 executor version/fingerprint，不改变 `CodeExecutor.execute()`。
- 新增 `execute-batch` CLI：严格 JSONL 输入、结构化 JSONL/JSON 输出和明确退出码。
- 新增 Mock batch 集成测试、真实 Piston batch/cache 集成测试和 CLI 集成测试。
- 扩展 `make test-piston`，使 WP3-b 安全探针和 WP3-c 真实批量探针一起运行。
- 更新 README、AGENTS 和本地 Piston 文档，完成 WP3 整体状态收口。

### 2.6 范围外

- 不修改规格 §8.3 的 `ExecutionStatus`、`TestCaseResult`、`ExecutionResult` 字段或 `CodeExecutor.execute()` 签名。
- 不在单个 `PistonExecutor` 内增加并行测试执行；批量并发只发生在多个顶层请求之间。
- 不实现 WP4 的 parser → verifier → reward 编排，不计算 reward，不决定训练可见的测试层。
- 不实现分布式队列、跨机器 worker、Redis、远程数据库或云缓存。
- 不缓存或序列化原始 code、input、expected；cache key 只保存 hash 和非敏感元数据。
- 不把缓存命中作为正确性证据；所有缓存结果必须重新通过结构合同校验。
- 不使用公共 Piston endpoint，不新增账户、密钥或远程服务依赖。
- 不修改 `third_party/open-r1/**`。
- 执行阶段不修改 `proceedings.md`；只有最终独立审查通过并合并后，审查方才可登记 WP3-c 并将 WP3 整体标为完成。

## 3. 前置条件、现状与约束

### 3.1 proceedings 与当前实现结论

- `proceedings.md` 已登记 WP3-b 于 2026-08-06 完成。
- 合并后的 `main` 已通过：
  - `make lint`；
  - `make test`：333 passed，1 个真实 Piston 模块按设计默认 skipped；
  - `make test-piston PISTON_CONFIG=configs/execution/piston-local.yaml`：7 passed，0 failed，0 skipped。
- `src/code_verifier/execution/base.py` 已提供 §8.3 类型、请求/结果合同校验和 `execution_result_to_mapping()`。
- `PistonExecutor.execute()` 已按测试顺序执行，并为每个测试创建独立 Piston job；本阶段不得削弱可信父进程与不可信候选子进程边界。
- 当前尚无 batch request、并发调度、cache key、持久缓存或执行 CLI。

### 3.2 规格 §8.5 必须保留的性能合同

- 支持批量验证；
- 允许有限并发；
- 并发数可配置；
- 相同代码、题目和测试层可选缓存；
- 缓存 key 必须包含：
  - 代码 hash；
  - problem ID；
  - test layer；
  - tests hash；
  - executor version；
- 训练模式中缓存应谨慎使用，防止错误复用。

### 3.3 横切规则

- 模型代码始终是不可信字符串；batch/cache/CLI 不得导入、编译或执行候选代码。
- 真实执行仍只能通过严格本地 `PistonExecutor`。
- 使用 `uv` 和现有 Makefile 管理 Python 环境与依赖；不得引入裸 `pip install` 流程。
- 新模块使用 `from __future__ import annotations`、完整类型标注、docstring、Ruff 双引号与 119 列、strict mypy。
- 所有配置必须严格拒绝未知字段、缺失字段、bool-as-int、NaN/Inf 和宽松类型转换。
- 所有错误不得回显 code、input、expected、Piston response body 或缓存结果原文。
- 任何真实安全探针失败或 skip 都阻断 WP3 最终完成。

### 3.4 本阶段明确实现决策

1. **保持单请求 Protocol 不变**：batch 是独立编排层，接收 `Callable[[], CodeExecutor]` factory；不向 §8.3 Protocol 添加 batch 方法。
2. **测试层枚举**：使用 `ExecutionTestLayer`，值固定为 `visible`、`train_hidden`、`eval_hidden`，与 canonical schema 三层语义一一对应。
3. **请求标识**：每个 batch request 必须有非空且批内唯一的 `request_id`；结果按 request_id 和原始索引关联。
4. **全量预校验**：所有请求、配置和缓存策略必须在创建线程或调用 executor 前验证；任何一个非法请求使整个 batch 以合同错误失败，且零执行副作用。
5. **并发模型**：使用标准库 `ThreadPoolExecutor`；`max_concurrency` 范围为 1–64；每个 miss task 调用 factory 创建自己的 executor 实例，避免共享 transport/marker 状态。
6. **结果顺序**：future 可乱序完成，但 `BatchExecutionResult.items` 必须与输入请求顺序完全一致。
7. **异常隔离**：worker 中未预期的普通 `Exception` 转换为该请求的结构化 `SANDBOX_ERROR`；不捕获 `KeyboardInterrupt`、`SystemExit` 或其他 `BaseException`。
8. **缓存模式**：
   - `disabled`：不读取、不写入；
   - `read_only`：读取命中，miss 执行但不写入；
   - `read_write`：读取命中，miss 执行并写入可缓存结果。
9. **训练缓存默认禁用**：`workload_mode=training` 且 cache mode 非 disabled 时，若配置未显式 `allow_training_cache: true`，必须在执行前失败。
10. **缓存 key 至少包含规格字段，并增加安全字段**：
    - exact UTF-8 code SHA-256；
    - problem ID；
    - test layer；
    - 有序 tests canonical JSON SHA-256；
    - executor version；
    - function name；
    - `timeout_seconds.hex()`；
    - memory limit MB。
11. **不做代码文本归一化**：空白、换行或 Unicode 的任何字节差异都改变 code hash，避免语义变化被错误复用。
12. **executor version**：由实现协议版本、可信 harness 协议版本和 `PistonExecutorConfig` 全部字段共同生成；endpoint、transport limit、runtime、输出上限或停止策略的任何变化都必须使 version 改变。
13. **缓存内容**：只缓存经 `validate_execution_result()` 验证且整体状态不是 `SANDBOX_ERROR` 的结果；不缓存基础设施错误。
14. **缓存文件安全**：SQLite 文件使用用户读写权限 `0600`，拒绝符号链接；数据库不保存 code、tests、input 或 expected。
15. **缓存损坏**：schema/version、key JSON、result JSON 或结果合同损坏时抛 `ExecutionCacheError`，不得静默命中、静默删除或把错误归因于模型。
16. **CLI 输出脱敏**：输出只包含 request/problem/test-layer 标识、cache hit 和结构化 result；不写回请求 code/tests。
17. **CLI 退出码**：
    - 0：batch 基础设施正常完成，模型错误状态允许存在；
    - 1：至少一个 item 为 `SANDBOX_ERROR`；
    - 2：CLI、配置、JSONL、cache、runtime validation 或 I/O 错误。

## 4. 目标文件总览

### 4.1 新建

- `configs/execution/batch-local.yaml`
- `src/code_verifier/execution/cache.py`
- `src/code_verifier/execution/batch.py`
- `tests/unit/execution/test_cache.py`
- `tests/unit/execution/test_batch.py`
- `tests/integration/test_wp3c_batch_execution.py`
- `tests/fixtures/wp3c/batch_requests.jsonl`

### 4.2 修改

- `src/code_verifier/execution/base.py`
- `src/code_verifier/execution/harness.py`
- `src/code_verifier/execution/piston.py`
- `src/code_verifier/execution/__init__.py`
- `src/code_verifier/cli.py`
- `tests/unit/test_cli.py`
- `Makefile`
- `README.md`
- `AGENTS.md`
- `docs/piston-local.md`

### 4.3 明确不修改

- §8.3 dataclass 字段和 `CodeExecutor.execute()` 签名
- `src/code_verifier/execution/mock.py` 的 FIFO/non-executing 语义
- Piston trusted-parent / candidate-child 隔离协议的安全结构
- `src/code_verifier/data/**` 的 canonical schema 和 split 逻辑
- `src/code_verifier/parsing/**`
- `src/code_verifier/training/**`
- `pyproject.toml` 依赖列表
- `third_party/open-r1/**`
- `proceedings.md`

## 5. 实施步骤

### 步骤 1：补齐执行结果反序列化和确定性 executor version

**目标文件**：

- `src/code_verifier/execution/base.py`（修改）
- `src/code_verifier/execution/harness.py`（修改）
- `src/code_verifier/execution/piston.py`（修改）
- `src/code_verifier/execution/__init__.py`（修改）

**新增 / 修改的符号**：

```python
def execution_result_from_mapping(value: object) -> ExecutionResult:
    """Parse one exact JSON-safe mapping and return a validated ExecutionResult."""
```

```python
PYTHON_HARNESS_PROTOCOL_VERSION = "trusted-parent-v1"
```

```python
PISTON_EXECUTOR_IMPLEMENTATION_VERSION = "piston-executor-v1"


def piston_executor_version(config: PistonExecutorConfig) -> str:
    """Return a deterministic version string for all result-affecting Piston semantics."""
```

**主要功能**：

- `execution_result_from_mapping()` 必须要求顶层字段恰好为：
  - `status`；
  - `passed_tests`；
  - `total_tests`；
  - `pass_rate`；
  - `runtime_ms`；
  - `test_results`。
- 每个 test result mapping 字段必须恰好为 §8.3 五个字段；不得 coercion string/int/bool。
- status 字符串必须能精确构造 `ExecutionStatus`；错误统一为不含 payload 的 `ExecutionContractError`。
- 构造结果后必须调用 `validate_execution_result()`；返回新的 list，避免共享可变对象。
- `PYTHON_HARNESS_PROTOCOL_VERSION` 只标识 runner 协议；后续任何影响调用、比较、输出或隔离的变更必须递增。
- `piston_executor_version()` 使用稳定 canonical JSON + SHA-256，输入必须包含：
  - `PISTON_EXECUTOR_IMPLEMENTATION_VERSION`；
  - `PYTHON_HARNESS_PROTOCOL_VERSION`；
  - `config.base_url`；
  - `config.language`；
  - `config.version`；
  - `config.request_timeout_margin_seconds.hex()`；
  - `config.max_response_bytes`；
  - `config.max_output_bytes`；
  - `config.stop_on_first_failure`。
- 返回格式固定为 `piston:<64 lowercase hex>`。
- 请求级 timeout/memory 单独进入 cache key；Piston 配置任一字段变化必须失效旧缓存。
- `execution/__init__.py` 重导出两个新公共函数，不导出内部实现常量以外的私有符号。

**测试方案**：

- 测试文件：`tests/unit/execution/test_base.py`
  - `test_execution_result_from_mapping_round_trips_exact_mapping`。
  - `test_execution_result_from_mapping_rejects_missing_unknown_and_wrong_typed_fields`。
  - `test_execution_result_from_mapping_rejects_invalid_status_and_result_invariants`。
  - `test_execution_result_from_mapping_returns_independent_test_result_list`。
  - `test_execution_result_from_mapping_error_does_not_echo_sentinel`。
- 测试文件：`tests/unit/execution/test_piston.py`
  - `test_piston_executor_version_is_stable_and_well_formed`。
  - `test_piston_executor_version_changes_with_every_piston_config_field`。
  - `test_piston_executor_version_changes_with_harness_and_implementation_protocol_versions`。

**验证命令与通过标准**：

```bash
make lint
.venv/bin/python -m pytest tests/unit/execution/test_base.py tests/unit/execution/test_piston.py -k "from_mapping or executor_version"
```

通过标准：mapping 双向转换保持字段和值；所有畸形 mapping 收敛为 `ExecutionContractError`；version 为稳定 64 位 lowercase SHA-256，语义字段变化必然改变 version。

---

### 步骤 2：实现稳定缓存 key 与安全 SQLite cache

**目标文件**：

- `src/code_verifier/execution/cache.py`（新建）
- `src/code_verifier/execution/__init__.py`（修改）
- `tests/unit/execution/test_cache.py`（新建）

**新增 / 修改的符号**：

```python
class ExecutionCacheError(RuntimeError):
    """Raised when a configured execution cache cannot be used safely."""


class ExecutionTestLayer(str, Enum):
    VISIBLE = "visible"
    TRAIN_HIDDEN = "train_hidden"
    EVAL_HIDDEN = "eval_hidden"


@dataclass(frozen=True)
class ExecutionCacheKey:
    code_hash: str
    problem_id: str
    test_layer: ExecutionTestLayer
    tests_hash: str
    executor_version: str
    function_name: str
    timeout_seconds_hex: str
    memory_limit_mb: int


class ExecutionCache(Protocol):
    def get(self, key: ExecutionCacheKey) -> ExecutionResult | None:
        ...

    def put(self, key: ExecutionCacheKey, result: ExecutionResult) -> None:
        ...

    def close(self) -> None:
        ...


class SQLiteExecutionCache:
    def __init__(self, path: Path) -> None:
        """Open or create a user-private versioned SQLite execution cache."""

    def get(self, key: ExecutionCacheKey) -> ExecutionResult | None:
        """Return one validated cached result or None for a true miss."""

    def put(self, key: ExecutionCacheKey, result: ExecutionResult) -> None:
        """Atomically insert or replace one validated non-sandbox result."""

    def close(self) -> None:
        """Commit pending work and close the SQLite connection."""

    def __enter__(self) -> SQLiteExecutionCache:
        ...

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        ...


def build_execution_cache_key(
    *,
    code: str,
    problem_id: str,
    test_layer: ExecutionTestLayer,
    tests: list[dict[str, Any]],
    executor_version: str,
    function_name: str,
    timeout_seconds: float,
    memory_limit_mb: int,
) -> ExecutionCacheKey:
    """Build one exact cache key containing all required and safety-relevant fields."""


def execution_cache_key_digest(key: ExecutionCacheKey) -> str:
    """Return the SHA-256 digest of the exact canonical cache-key mapping."""
```

**主要功能**：

- code hash 为 exact UTF-8 bytes SHA-256，不调用 `normalize_text()`。
- tests hash 使用现有 `stable_json_hash(tests)`，保留 list 顺序和类型敏感 JSON 表示。
- `problem_id`、`executor_version`、`function_name` 必须为非空字符串；function name 复用请求合同检查。
- timeout 使用 Python float 的 `.hex()`，避免 locale/decimal formatting 差异。
- `ExecutionCacheKey` 的 mapping 字段必须完整保留，不只保存一个不透明 digest。
- SQLite schema：

```sql
CREATE TABLE metadata (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE entries (
    key_digest TEXT PRIMARY KEY,
    key_json TEXT NOT NULL,
    result_json TEXT NOT NULL
);
```

- metadata 必须包含 exact `schema_version=wp3c-execution-cache-v1`；不匹配时失败。
- `key_json` 和 `result_json` 使用 canonical JSON、`allow_nan=False`。
- get 时：
  1. 根据 digest 查询；
  2. 对比 stored key JSON 与当前 exact key JSON；
  3. 使用 `loads_strict()` 拒绝重复 key；
  4. 使用 `execution_result_from_mapping()` 重新校验结果；
  5. 任一损坏抛固定 `ExecutionCacheError`。
- put 时拒绝 `ExecutionStatus.SANDBOX_ERROR`；写入前重新验证结果。
- 数据库只保存 hash、problem ID、test layer、executor version、function name、limits 和结果；不得保存 code/tests。
- 新文件创建后执行 `chmod 0o600`；已有文件必须是 regular file、非 symlink，并拒绝 group/other 权限。
- SQLite 操作只在 batch 调用线程执行，不从 worker threads 访问同一 connection。
- `close()` 幂等；context manager 异常时回滚未提交事务。

**测试方案**：

- 测试文件：`tests/unit/execution/test_cache.py`
  - `test_cache_key_contains_all_spec_required_fields`。
  - `test_cache_key_changes_for_code_problem_layer_tests_and_executor_version`。
  - `test_cache_key_also_changes_for_function_timeout_and_memory`。
  - `test_code_hash_is_exact_and_tests_hash_is_order_sensitive`。
  - `test_sqlite_cache_miss_put_hit_round_trip`。
  - `test_sqlite_cache_rejects_sandbox_error_result`。
  - `test_sqlite_cache_rejects_symlink_and_insecure_permissions`。
  - `test_sqlite_cache_file_is_created_with_user_only_permissions`。
  - `test_sqlite_cache_detects_schema_key_and_result_corruption`。
  - `test_sqlite_cache_database_does_not_contain_code_or_test_sentinels`。
  - `test_sqlite_cache_close_is_idempotent`。
- 使用 `tmp_path` 和标准库 sqlite3；不访问 Piston 或互联网。

**验证命令与通过标准**：

```bash
make lint
.venv/bin/python -m pytest tests/unit/execution/test_cache.py
```

通过标准：cache key 任一必需字段变化都产生不同 digest；SQLite hit 结果通过公共合同；损坏或不安全文件明确失败；数据库原始 bytes 不包含 code/input/expected sentinel。

---

### 步骤 3：实现 batch 类型、严格配置和有限并发编排

**目标文件**：

- `configs/execution/batch-local.yaml`（新建）
- `src/code_verifier/execution/batch.py`（新建）
- `src/code_verifier/execution/__init__.py`（修改）
- `tests/unit/execution/test_batch.py`（新建）

**新增 / 修改的符号**：

```python
class BatchExecutionError(RuntimeError):
    """Raised when batch orchestration cannot proceed without misattributing a failure."""


class ExecutionCacheMode(str, Enum):
    DISABLED = "disabled"
    READ_ONLY = "read_only"
    READ_WRITE = "read_write"


class ExecutionWorkloadMode(str, Enum):
    EVALUATION = "evaluation"
    TRAINING = "training"


@dataclass(frozen=True)
class BatchExecutorConfig:
    max_concurrency: int
    cache_mode: ExecutionCacheMode
    allow_training_cache: bool


@dataclass(frozen=True)
class BatchExecutionConfig:
    piston: PistonExecutorConfig
    batch: BatchExecutorConfig


@dataclass(frozen=True)
class BatchExecutionRequest:
    request_id: str
    problem_id: str
    test_layer: ExecutionTestLayer
    code: str
    function_name: str
    tests: list[dict[str, Any]]
    timeout_seconds: float
    memory_limit_mb: int


@dataclass(frozen=True)
class BatchExecutionItemResult:
    request_id: str
    problem_id: str
    test_layer: ExecutionTestLayer
    cache_hit: bool
    result: ExecutionResult


@dataclass(frozen=True)
class BatchExecutionResult:
    executor_version: str
    max_concurrency: int
    cache_mode: ExecutionCacheMode
    workload_mode: ExecutionWorkloadMode
    total_requests: int
    cache_hits: int
    runtime_ms: float
    items: list[BatchExecutionItemResult]


def batch_execution_request_from_mapping(value: object) -> BatchExecutionRequest:
    """Parse one exact JSON request mapping and validate its single-execution contract."""


def batch_execution_item_to_mapping(item: BatchExecutionItemResult) -> dict[str, object]:
    """Serialize one non-sensitive item result without code or tests."""


def batch_execution_result_to_mapping(result: BatchExecutionResult) -> dict[str, object]:
    """Serialize one batch summary and all item results as JSON-safe mappings."""


def batch_execution_config_from_mapping(value: object) -> BatchExecutionConfig:
    """Parse exact piston and batch mappings and reject unknown fields."""


def load_batch_execution_config(path: Path) -> BatchExecutionConfig:
    """Load one strict WP3-c batch execution YAML."""


class BatchExecutor:
    def __init__(
        self,
        executor_factory: Callable[[], CodeExecutor],
        *,
        executor_version: str,
        config: BatchExecutorConfig,
        cache: ExecutionCache | None = None,
    ) -> None:
        """Create a bounded batch orchestrator over independent executor instances."""

    def execute_batch(
        self,
        requests: Sequence[BatchExecutionRequest],
        *,
        workload_mode: ExecutionWorkloadMode = ExecutionWorkloadMode.EVALUATION,
    ) -> BatchExecutionResult:
        """Validate, cache, execute concurrently, and return results in input order."""
```

**配置合同**：

`configs/execution/batch-local.yaml`：

```yaml
piston:
  base_url: http://127.0.0.1:2000
  language: python
  version: "3.10.0"
  request_timeout_margin_seconds: 2.0
  max_response_bytes: 131072
  max_output_bytes: 4096
  stop_on_first_failure: false

batch:
  max_concurrency: 4
  cache_mode: disabled
  allow_training_cache: false
```

**主要功能**：

- YAML 顶层字段恰好为 `piston` 和 `batch`；batch 字段恰好为三个配置项。
- `max_concurrency` 为 1–64 的 int、非 bool。
- `batch_execution_request_from_mapping()` 要求字段恰好为 dataclass 八个字段；test layer 必须是枚举值；调用现有 `validate_execution_request()`。
- `BatchExecutor.__init__()`：
  - executor version 必须符合非空固定格式；
  - disabled 模式必须不使用 cache；
  - read-only/read-write 模式必须提供 cache；
  - 不创建线程、不调用 executor。
- `execute_batch()`：
  1. 将 Sequence 复制为 list；
  2. 验证每个对象类型和 request_id 批内唯一性；
  3. 深复制 code/tests 之外的可变成员，完成全量预校验；
  4. 检查 training cache 规则；
  5. 在主线程按输入顺序查询 cache；
  6. 只为 cache miss 提交 future；
  7. 每个 future 调用 factory 并执行一个 request；
  8. 捕获普通 Exception，生成固定 stderr `batch executor failed` 的 `SANDBOX_ERROR`；
  9. 在主线程收集 future、验证结果、按策略写 cache；
  10. 按原始索引组装 items。
- synthetic `SANDBOX_ERROR`：
  - `passed_tests=0`；
  - `total_tests=len(request.tests)`；
  - `pass_rate=0.0`；
  - 非空 tests 时包含一个固定的 `TestCaseResult(SANDBOX_ERROR, ...)`；
  - 不回显异常、code 或 tests。
- `runtime_ms` 是整个 batch wall-clock 时间，不是 item runtime 的简单求和。
- `cache_hits` 等于 `cache_hit=True` item 数量。
- read-write 只写非 `SANDBOX_ERROR` 结果；相同 key 在同批出现时不做隐式 in-flight dedup，每个 miss 独立执行，避免训练语义被隐藏改变。
- mapping 输出字段固定；item mapping 不含 code、function input、expected 或 cache key 原文。

**测试方案**：

- 测试文件：`tests/unit/execution/test_batch.py`
  - `test_batch_config_accepts_exact_mapping_and_rejects_unknown_fields`。
  - `test_batch_request_mapping_requires_exact_fields_and_valid_test_layer`。
  - `test_batch_prevalidates_all_requests_before_factory_is_called`。
  - `test_batch_rejects_duplicate_request_ids_without_side_effects`。
  - `test_batch_preserves_input_order_when_futures_finish_out_of_order`。
  - `test_batch_never_exceeds_configured_concurrency`：barrier/counter 观测 active peak。
  - `test_batch_max_concurrency_one_is_sequential`。
  - `test_batch_creates_independent_executor_per_cache_miss`。
  - `test_batch_converts_worker_exception_to_sanitized_sandbox_result`。
  - `test_batch_disabled_cache_never_reads_or_writes`。
  - `test_batch_read_only_uses_hits_and_does_not_write_misses`。
  - `test_batch_read_write_uses_hits_and_writes_non_sandbox_misses`。
  - `test_batch_does_not_cache_sandbox_error`。
  - `test_batch_training_cache_requires_explicit_opt_in`。
  - `test_batch_result_mapping_is_json_serializable_and_omits_request_payload`。
  - `test_batch_result_runtime_is_wall_clock_and_cache_hit_count_is_exact`。
- fake executor 必须只处理固定测试数据，不运行用户代码。

**验证命令与通过标准**：

```bash
make lint
.venv/bin/python -m pytest tests/unit/execution/test_batch.py
```

通过标准：实测 active peak 不超过配置且在 max>1 时确有重叠；乱序 future 仍返回输入顺序；cache 三种模式和 training guard 全部确定；异常不逃逸、不泄漏 payload。

---

### 步骤 4：实现 `execute-batch` CLI 与原子脱敏输出

**目标文件**：

- `src/code_verifier/cli.py`（修改）
- `tests/unit/test_cli.py`（修改）
- `tests/fixtures/wp3c/batch_requests.jsonl`（新建）

**新增 / 修改的符号**：

```python
def _load_batch_requests(path: Path) -> list[BatchExecutionRequest]:
    """Read strict UTF-8 JSONL requests and reject blank, duplicate-key, or malformed records."""


def _write_batch_outputs(result: BatchExecutionResult, output_dir: Path) -> None:
    """Atomically write results.jsonl and summary.json without request payloads."""


def _execute_batch(args: argparse.Namespace) -> int:
    """Run configured local Piston batch execution and emit non-sensitive artifacts."""
```

**CLI 形态**：

```bash
.venv/bin/code-verifier execute-batch \
  --config configs/execution/batch-local.yaml \
  --requests tests/fixtures/wp3c/batch_requests.jsonl \
  --workload-mode evaluation \
  --output-dir outputs/wp3c-batch \
  --log-level INFO
```

新增参数：

```text
--requests PATH                     必填，严格 UTF-8 JSONL
--workload-mode evaluation|training 默认 evaluation
--max-concurrency INT               可选，覆盖 YAML
--cache-mode disabled|read_only|read_write  可选，覆盖 YAML
--cache-path PATH                   cache 非 disabled 时必填
```

同时继续支持公共参数：

```text
--help
--config
--seed
--output-dir
--log-level
```

**主要功能**：

- `build_parser()` docstring 和帮助文本更新为 WP0–WP3。
- `_load_batch_requests()`：
  - 文件必须至少一条记录；
  - 空白行失败；
  - 每行使用 `loads_strict()`，拒绝任意层重复 key；
  - 错误只报告 line number 和固定类别，不回显行内容；
  - 调用 `batch_execution_request_from_mapping()`。
- CLI override 只覆盖对应 batch config，仍执行严格范围校验。
- cache disabled 时禁止 `--cache-path`；cache enabled 时要求该参数。
- `_execute_batch()` 在执行前：
  1. 配置 logging；
  2. 加载 config 和 requests；
  3. 构造一个 PistonExecutor 并调用 `validate_runtime()` 一次；
  4. 计算 `piston_executor_version()`；
  5. 打开可选 SQLite cache；
  6. 使用 factory 构造 batch executor。
- `output_dir` 必须不存在；使用同父目录 temporary directory 完整写入后原子 rename，失败不留下半成品。
- cache path 不得位于 `output_dir` 内部，避免执行期间创建目标目录并破坏原子输出合同。
- `results.jsonl` 每行一个 `batch_execution_item_to_mapping()`。
- `summary.json` 至少包含：
  - executor version；
  - workload/cache mode；
  - max concurrency；
  - total requests；
  - cache hits；
  - status counts；
  - batch runtime；
  - results file basename。
- 输出文件不含 code、tests、input、expected 或完整 cache key。
- stdout 只打印计数和路径，不打印 item stdout/stderr。
- main 新增 execution error tuple，统一将 config/input/cache/runtime/I/O 错误映射为 exit 2。
- batch 返回后存在任一 `SANDBOX_ERROR` 时仍写完整结构化 artifacts，然后返回 1。

**fixture 合同**：

`tests/fixtures/wp3c/batch_requests.jsonl` 提交 4 条固定记录：

- 2 个正确实现；
- 1 个 wrong answer；
- 1 个 runtime error；
- request_id 和 problem_id 唯一；
- 覆盖 visible、train_hidden、eval_hidden 三个 layer；
- 不包含真实隐藏实验数据。

**测试方案**：

- 测试文件：`tests/unit/test_cli.py`
  - `test_execute_batch_help_includes_common_and_batch_arguments`。
  - `test_load_batch_requests_rejects_empty_blank_duplicate_key_and_invalid_record`。
  - `test_load_batch_requests_error_does_not_echo_code_or_test_sentinel`。
  - `test_execute_batch_rejects_cache_path_mode_mismatch`。
  - `test_execute_batch_applies_concurrency_and_cache_overrides`。
  - `test_execute_batch_writes_exact_results_and_summary_artifacts`。
  - `test_execute_batch_outputs_omit_code_input_and_expected`。
  - `test_execute_batch_returns_zero_for_model_failures_one_for_sandbox_error_two_for_infrastructure_error`。
  - `test_execute_batch_refuses_any_existing_output_directory`。
  - `test_execute_batch_rejects_cache_path_inside_output_directory`。
  - `test_execute_batch_partial_write_failure_leaves_no_final_output`。
- monkeypatch Piston runtime/executor/batch boundaries；CLI unit tests不连接真实服务。

**验证命令与通过标准**：

```bash
make lint
.venv/bin/python -m pytest tests/unit/test_cli.py
.venv/bin/code-verifier execute-batch --help
```

通过标准：help 显示全部参数；严格 JSONL 错误稳定且脱敏；输出 artifact 字段精确、可 JSON 解析、无请求 payload；退出码 0/1/2 行为全部通过。

---

### 步骤 5：增加 Mock 与真实 Piston batch/cache 集成验收

**目标文件**：

- `tests/integration/test_wp3c_batch_execution.py`（新建）
- `Makefile`（修改）

**新增测试符号**：

```python
def test_mock_batch_preserves_order_bounds_concurrency_and_reuses_cache(tmp_path: Path) -> None:
    ...


def test_execute_batch_cli_writes_desensitized_artifacts(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    ...


@pytest.mark.piston
def test_real_piston_batch_runs_concurrently_and_reuses_valid_cache(tmp_path: Path) -> None:
    ...


@pytest.mark.piston
def test_real_piston_batch_sandbox_error_is_not_cached_and_service_recovers(tmp_path: Path) -> None:
    ...
```

**Makefile 变更**：

```make
test-piston:
	CODE_VERIFIER_RUN_PISTON=1 CODE_VERIFIER_PISTON_CONFIG=$(PISTON_CONFIG) \
	$(PYTHON) -m pytest -m piston \
	  tests/integration/test_wp3b_piston_execution.py \
	  tests/integration/test_wp3c_batch_execution.py -ra
```

**主要功能**：

- 默认集成测试使用固定 fake/Mock executor，覆盖：
  - 输入顺序；
  - max concurrency；
  - SQLite first-run miss / second-run hit；
  - mapping/JSONL 序列化；
  - 无 code/test 泄漏。
- 真实 Piston 测试仍要求 `CODE_VERIFIER_RUN_PISTON=1`；未显式启用时只 skip piston-marked test，不连接服务。
- 显式运行时缺服务、runtime、cache 或安全状态必须 fail，不得 skip。
- 真实 batch 至少包含：
  - correct；
  - wrong answer；
  - runtime error；
  - timeout；
  - 两个可并发的正确请求。
- 第一轮使用 `read_write`：验证结果顺序、状态和 cache_hits=0。
- 第二轮使用同 cache 的 `read_only`：验证非 sandbox item 全部 cache hit，结果 mapping 与第一轮一致。
- 人为制造一个 transport/sandbox failure，断言它不写 cache；恢复服务/fake transport 后同 key 必须重新执行并成功。
- 真实 batch 后再次运行一个 WP3-b 健康 smoke，证明并发和错误处理未破坏服务。
- 不使用 timing 比较证明并发；并发上限主要由 unit barrier/counter 证明。真实测试只证明多个请求可在 max concurrency >1 配置下正确完成。

**验证命令与通过标准**：

```bash
make lint
make test
make test-piston PISTON_CONFIG=configs/execution/piston-local.yaml
```

通过标准：

- 默认 `make test` 全绿，真实 Piston 测试按设计 skipped 且不连接服务。
- `make test-piston` 同时运行 WP3-b 和 WP3-c，0 failed、0 skipped。
- 第二轮 cache hit 数与可缓存 item 数完全一致。
- `SANDBOX_ERROR` 未被 cache 复用。
- Piston 健康 smoke 通过。

---

### 步骤 6：更新文档并完成 WP3 全量最终验收

**目标文件**：

- `README.md`（修改）
- `AGENTS.md`（修改）
- `docs/piston-local.md`（修改）

**文档要求**：

README：

- 项目状态改为 WP3 整体实现完成；WP4 rewards/verifier 仍未实现。
- 新增 WP3-c batch API 示例：
  - `BatchExecutionRequest`；
  - `BatchExecutor`；
  - `SQLiteExecutionCache`；
  - evaluation/training cache policy。
- 新增 `execute-batch` CLI 示例及输出文件布局。
- 明确缓存 key 不保存原始代码/测试，缓存文件仍可能含模型 stdout/stderr，必须按敏感 artifact 管理。
- 明确训练模式默认禁用缓存，除非实验配置显式开启并记录。
- 当前限制更新为：单机线程池、本地 SQLite、每测试一个 Piston job；不宣称分布式性能。

AGENTS：

- 结构新增 `execution/cache.py`、`execution/batch.py` 和相应测试/config。
- 当前范围改为 WP0–WP3 完成；未经后续计划不得实现 WP4 reward/verifier、训练或评测。
- 增加 cache 安全规则：executor/harness/version 语义变化必须递增 version；不得从 key 移除规格字段。
- 真实 Piston batch 改动仍必须运行 `make test-piston` 且 0 skip。

docs/piston-local.md：

- 增加 batch concurrency 对本地 Piston worker capacity 的影响说明。
- 给出从 1 开始逐步提高 `max_concurrency` 的操作建议，但不写用户特定硬件数值。
- 增加 cache 文件权限、备份/删除和 schema mismatch 处理。
- 明确 cache 不替代 sandbox；cache corruption 或 version mismatch 时停止，不回退到不受控执行。

**WP3 全量最终验证命令**：

```bash
make lint
make test
make test-piston PISTON_CONFIG=configs/execution/piston-local.yaml
.venv/bin/code-verifier --help
.venv/bin/code-verifier execute-batch --help
rm -rf outputs/wp3c-smoke
.venv/bin/code-verifier execute-batch \
  --config configs/execution/batch-local.yaml \
  --requests tests/fixtures/wp3c/batch_requests.jsonl \
  --workload-mode evaluation \
  --output-dir outputs/wp3c-smoke \
  --log-level INFO
.venv/bin/python -c "import json, pathlib; root=pathlib.Path('outputs/wp3c-smoke'); print(json.loads((root/'summary.json').read_text())['total_requests'])"
```

> `rm -rf outputs/wp3c-smoke` 只针对明确的仓库内验收输出目录；执行前确认路径完全一致，不得泛化为变量或用户路径。

**最终通过标准**：

- `make lint` 全绿。
- `make test` 全绿，WP0–WP3-b 无回归。
- `make test-piston` 运行 WP3-b 安全套件与 WP3-c batch 套件，0 failed、0 skipped。
- CLI smoke 返回 0，summary 输出 `4`。
- `results.jsonl` 为 4 行，顺序与 fixture request_id 一致。
- 输出和 cache 数据不含 fixture 中的 code/input/expected sentinel。
- WP3 §20 全部交付已完成：Protocol、Mock、Piston、资源限制、批量执行、测试。
- WP3 §20 全部验收逐项通过：正确、超时、网络、文件越权、输出限制、宿主隔离、结果序列化。
- reviewer 进行高风险人工 Code Review，重点检查：
  - concurrency 上限和线程安全；
  - 全量预校验；
  - cache key 完整性；
  - executor version 失效规则；
  - training cache guard；
  - SQLite 权限/损坏行为；
  - CLI 脱敏和原子输出；
  - WP3-b Piston 安全边界无回归。
- 审查通过并合并后，`proceedings.md` 应追加 WP3-c 记录，并将 WP3 整体明确标为已完成；不得提前记录 WP4 状态。

## 6. 总体验收与测试计划

### 6.1 单元测试汇总

- `tests/unit/execution/test_base.py`
  - ExecutionResult exact mapping 反序列化与合同。
- `tests/unit/execution/test_piston.py`
  - deterministic executor version。
- `tests/unit/execution/test_cache.py`
  - cache key 完整性；
  - SQLite 安全、权限、损坏与脱敏。
- `tests/unit/execution/test_batch.py`
  - batch schema/config；
  - 全量预校验；
  - 有限并发；
  - 顺序；
  - worker 异常；
  - cache 模式；
  - training guard；
  - JSON mapping。
- `tests/unit/test_cli.py`
  - execute-batch 参数、JSONL、artifact、退出码和错误脱敏。

### 6.2 集成测试汇总

- `tests/integration/test_wp3c_batch_execution.py`
  - Mock batch/cache 默认 CI；
  - CLI artifact；
  - 真实 Piston batch/cache；
  - sandbox error 不缓存；
  - 服务恢复。
- `tests/integration/test_wp3b_piston_execution.py`
  - WP3-b 原有全部安全探针继续作为 WP3 总验收的一部分。

### 6.3 数据与泄漏要求

- batch request 可包含任意一层测试，但 Execution Layer 不决定层选择。
- cache key 只存 tests hash，不存 tests 内容。
- CLI artifacts 不存 code/tests。
- cache result 可能含 stdout/stderr，因此文件权限必须为 0600，文档必须标注敏感性。
- 错误文本不得包含 request JSONL 原行、code、input、expected 或 raw cache/Piston body。

### 6.4 WP3 最终验收清单

- [ ] §8.3 公共接口保持不变。
- [ ] MockExecutor 非执行语义保持不变。
- [ ] 本地 Piston 单请求和安全限制无回归。
- [ ] batch validation 支持有限并发且顺序稳定。
- [ ] concurrency 可通过 YAML 和 CLI override 配置，范围严格有界。
- [ ] cache mode 可选，training 默认禁用。
- [ ] cache key 包含 code hash、problem ID、test layer、tests hash、executor version。
- [ ] cache key 额外包含 function/timeout/memory，避免资源语义错误复用。
- [ ] cache 不保存 code/tests，不缓存 SANDBOX_ERROR。
- [ ] cache corruption/version mismatch 明确失败。
- [ ] execute-batch CLI 支持全部公共参数并输出脱敏 artifact。
- [ ] 正确、错误、语法、运行、超时、内存、输出状态均有结构化结果。
- [ ] 网络、root、文件、宿主、清理、PID 安全探针全部通过。
- [ ] 结果与 batch summary 均可 JSON 序列化。
- [ ] `make lint`、`make test`、`make test-piston` 全绿。
- [ ] `third_party/open-r1/**` 未修改。
- [ ] 高风险人工审查通过后，WP3 整体可登记完成。

## 7. 风险与注意事项

- **线程安全**：不得在多个 worker 共享同一 Piston executor/transport；factory-per-task 是本阶段的明确安全边界。
- **并发过载**：max concurrency 必须有 64 上限；真实部署从 1 开始调优，不能以无限 worker 提升吞吐。
- **结果乱序**：future completion order 不得成为输出顺序；所有 item 必须按原始索引回填。
- **部分输入副作用**：全量 request validation 必须在线程/cache 前完成，避免前半 batch 已执行、后半才发现 schema 错误。
- **缓存污染**：key 缺少任一规格字段或资源字段都可能错误复用；测试必须逐字段证明 digest 改变。
- **版本失效遗漏**：harness、Piston 映射、比较或停止策略改变时必须更新版本常量，否则旧 cache 不安全。
- **训练缓存**：训练中复用 stale reward 会直接污染优化；默认 disabled，显式 opt-in 也必须记录在 resolved config。
- **缓存敏感内容**：虽然 key 不含测试，result stdout/stderr 可能含模型输出；SQLite 必须 0600，不应提交 Git。
- **cache infrastructure 误判**：缓存损坏不能转换为模型 `SANDBOX_ERROR`；应作为 batch/CLI 基础设施错误停止。
- **worker 异常归因**：执行器普通异常转为结构化 sandbox error，但异常文本不得进入结果。
- **WP3-b 安全回归**：batch 只包装现有 PistonExecutor；不得为吞吐绕过每测试 job、可信父进程或资源限制。
- **性能范围**：本阶段只实现单机线程池和 SQLite；不扩展为分布式训练系统，符合 §29 非目标。

## 8. 后续阶段边界

WP3-c 审查通过后，WP3 整体完成。下一 WP 应由后续规划根据 `proceedings.md` 和规格 §20 选择 WP4，不得在本计划中提前实现：

- parser/executor verifier 编排；
- public/hidden reward；
- batch reward alignment；
- GRPO/SFT 或评测。

## 9. 关联文档索引

- `PROJECT_SPEC_Open-R1_CodeVerifier.md`
  - §0：安全、配置、类型、测试和范围纪律
  - §6.2：Execution Layer 模块边界
  - §8.3：公共执行接口
  - §8.4：资源、安全、清理和提前停止
  - §8.5：批量、并发、缓存和 cache key
  - §16：execution 包结构
  - §17：CLI 公共参数
  - §19.1 Executor、§19.2 真实沙箱、§19.3 CI
  - §20 WP3：完整目标、交付与验收
  - §24 Risk 3 / Risk 6：执行成本和安全回退
  - §29：本地 Piston、Python 函数级任务和非分布式系统范围
- `proceedings.md`
  - WP3-a：公共合同与 Mock 已完成
  - WP3-b：本地 Piston 单请求执行与安全限制已完成
- 当前实现
  - `src/code_verifier/execution/base.py`
  - `src/code_verifier/execution/mock.py`
  - `src/code_verifier/execution/harness.py`
  - `src/code_verifier/execution/piston.py`
  - `src/code_verifier/data/deduplicate.py`：canonical JSON 与 stable JSON hash
  - `src/code_verifier/data/json_strict.py`：duplicate-key-safe JSON parsing
  - `src/code_verifier/cli.py`：现有 CLI handler/build_parser/main 模式
- 现有真实验收
  - `tests/integration/test_wp3b_piston_execution.py`
  - `docs/piston-local.md`
