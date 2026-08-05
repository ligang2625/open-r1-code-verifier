# WP1 实施计划（数据 Schema 与三层测试划分）

## 1. 元信息

| 项 | 值 |
|---|---|
| 目标 WP | WP1：数据 Schema 与三层测试划分 |
| 规格依据 | `PROJECT_SPEC_Open-R1_CodeVerifier.md` §0、§4.1、§6.2、§7、§16、§17、§19、§20 WP1、§24 Risk 2 / Risk 7、§29 |
| 前置 WP | WP0（`proceedings.md` 状态：已完成，验收通过） |
| 计划文件 | `plans/WP1-plan.md` |
| 面向的执行者 | 仅需仓库文件读写和基础 shell，可运行项目自带的 `make`、pytest 与 CLI |
| 预计配置影响 | 会修改 `pyproject.toml`、`Makefile`，并新增 `configs/data/smoke.yaml`；不会修改上游 submodule |

## 2. 目标与范围

### 目标（规格 §20 原文）

实现数据结构、测试划分和泄漏检查。

### 交付（规格 §20 原文）

- schema；
- 输入适配器；
- test split；
- hash；
- 去重；
- leakage checks；
- 20 道题 fixture。

### 验收（规格 §20 原文）

- fixture 可导出 JSONL/Dataset；
- 三层测试无重复；
- 删除或混入字段时测试能失败；
- 训练 artifact 不含 eval hidden 测试。

### 范围内

- 实现 §7.1 的函数级 Python 题目数据模型和严格校验。
- 以一个通用 raw JSONL 合同作为 WP1 唯一输入适配器；不绑定外部数据集厂商或网络下载。
- 将每题未划分的测试确定性地拆为 `visible_tests`、`train_hidden_tests`、`eval_hidden_tests`。
- 对文本、JSON 值、测试、题目建立确定性标准化和 SHA-256 hash，并做题目/测试去重。
- 落地 WP1 当前可执行的 §7.4 泄漏检查：测试层交叉重复、跨 split 题目重复、训练 artifact 字段隔离、不同用途输出目录隔离。
- 提供 canonical JSONL、Hugging Face Dataset 和三种最小训练视图的导出。
- 新增 `prepare-data`、`check-data` CLI，并沿用现有 `build_parser()` / `main()` / handler 模式。
- 提供 20 道离线 fixture，覆盖 train / validation / test，供后续集成测试复用。
- 更新与 WP1 直接冲突的 WP0-only 文档表述。

### 范围外

- 不实现 WP2 代码解析器、WP3 安全执行器、WP4 verifier/reward、WP5–WP8 训练评测功能。
- 不运行 fixture 中的 `reference_solution`，也不在宿主机执行任何不可信代码。
- 不生成复杂模糊测试、不接入网络数据源、不做多数据源比较。
- 不修改 `third_party/open-r1/`。
- 不实现 GRPO/SFT dataloader；WP1 只产出字段最小化、可被后续 WP 消费的训练 artifact。
- 不实现 prompt 模板生成；输入 prompt 必须已经包含题面、函数签名和 visible examples 所需的静态文本。
- 不在 WP1 实现日志脱敏、冻结 checkpoint 校验或跨训练流水线检查；这些在相应后续 WP 接入时继续落实 §7.4。

## 3. 前置条件、现状与约束

### 3.1 proceedings 与当前代码结论

- `proceedings.md` 只登记 WP0，且状态为“已完成”、验收为“通过”；没有 WP1 部分完成项、设计决策或已知问题。
- 当前 `src/code_verifier/` 只有 `cli.py`、`environment.py`、`training/open_r1_adapter.py`；当前 `tests/unit/` 只有对应 WP0 测试，因此 WP1 从零增量添加 Data Layer。
- `README.md` 与 `AGENTS.md` 仍写有“WP0 only / WP0 scope only”，实施 WP1 时必须同步修正，避免后续执行者误判范围。
- `proceedings.md` 当前末尾只记录 pinned commit；本计划不修改实施记录。WP1 实际完成且验收后，再单独追加真实命令、结果和配置变更。

### 3.2 项目硬性规则

- Data Layer 只负责读取、规范化、去重、三层测试划分、完整性检查与 JSONL/Dataset 导出；不得推理、训练或执行代码（§6.2）。
- `third_party/open-r1/` 是固定 commit 的只读 submodule；任何 Open-R1 访问只能经 `code_verifier.training.open_r1_adapter`。WP1 无需访问 Open-R1。
- 不硬编码用户路径、数据集位置、模型名、设备、密钥或 seed；数据路径和随机 seed 由 YAML / CLI 提供。
- 所有影响划分的随机过程必须由 seed 控制；不得使用 Python 进程随机化的 `hash()`。
- 新模块必须有 `from __future__ import annotations`、完整类型标注、简洁 docstring、明确错误和单元测试。
- 保持 Ruff 双引号、119 列和 strict mypy；测试继续放在 `tests/unit/test_*.py` 或其子目录。
- 数据/缓存用途必须使用不同路径和文件名；训练文件名不得伪装成 canonical/evaluation artifact。
- 对规格歧义采用 §29 默认：Python、函数级代码生成；Risk 7 下只实现一个通用离线数据源。

### 3.3 WP1 的明确实现假设

1. §7.1 给的是 JSON schema 而非 Python 签名，因此 Python 内部用冻结 dataclass 和 tuple 保证不可变；序列化时字段名及 list/object/null 结构必须与 §7.1 完全一致。
2. §20 的“JSONL/Dataset”按“两种格式均支持”实现：始终导出 JSONL；配置启用时额外调用 Hugging Face `datasets.Dataset.save_to_disk()`。这避免对验收措辞作弱化解释。
3. raw 输入每题包含一个尚未分层的 `tests` 数组；层大小由配置给出，测试数必须恰好等于三层数量之和。输入已经含三层字段、层数不足、层内/层间重复都应显式失败，不做静默修复。
4. “近似去重”的 WP1 MVP 定义为：Unicode NFKC、统一换行、去除行尾空白、折叠普通文本连续空白后再 hash。它能稳定识别格式差异导致的重复，但不承诺语义等价/AST 等价；更复杂近似去重不在本 WP。
5. 20 题 fixture 固定使用 `visible=2`、`train_hidden=2`、`eval_hidden=2`，每题共 6 个唯一测试；题目分布固定为 12 train、4 validation、4 test。
6. canonical/evaluation artifact 可以保存完整三层测试用于审计和最终评测；任何文件名位于 `training/` 的 artifact 必须经过字段白名单投影，绝不从完整记录“删几个 key 后直接写出”。

## 4. 目标文件总览

### 新建

- `configs/data/smoke.yaml`
- `src/code_verifier/config.py`
- `src/code_verifier/data/__init__.py`
- `src/code_verifier/data/schema.py`
- `src/code_verifier/data/adapters.py`
- `src/code_verifier/data/split_tests.py`
- `src/code_verifier/data/deduplicate.py`
- `src/code_verifier/data/leakage_checks.py`
- `src/code_verifier/data/prepare.py`
- `tests/fixtures/wp1/raw_problems.jsonl`
- `tests/unit/test_config.py`
- `tests/unit/data/__init__.py`
- `tests/unit/data/test_schema.py`
- `tests/unit/data/test_adapters.py`
- `tests/unit/data/test_split_tests.py`
- `tests/unit/data/test_deduplicate.py`
- `tests/unit/data/test_leakage_checks.py`
- `tests/unit/data/test_prepare.py`
- `tests/integration/test_wp1_data_pipeline.py`

### 修改

- `src/code_verifier/cli.py`
- `tests/unit/test_cli.py`
- `pyproject.toml`
- `Makefile`
- `.gitignore`
- `README.md`
- `AGENTS.md`

### 明确不修改

- `third_party/open-r1/**`
- `proceedings.md`（只有 WP1 实际完成并人工验收后才追加）
- WP2 及以后模块路径。

## 5. 实施步骤

### 步骤 1：补齐 WP1 运行依赖、配置加载器和 smoke 配置

**目标文件**：

- `pyproject.toml`（修改）
- `Makefile`（修改）
- `src/code_verifier/config.py`（新建）
- `configs/data/smoke.yaml`（新建）

**配置变更**：

- 在 `[project].dependencies` 中保留 `open-r1==0.1.0.dev0`，新增并固定：
  - `PyYAML==6.0.2`
  - `datasets==3.2.0`
- 在 Makefile 将 WP1 最小运行依赖单列为 `DATA_PACKAGES := PyYAML==6.0.2 datasets==3.2.0`；`make install` 在现有双 editable 安装和 dev tools 之外安装 `$(DATA_PACKAGES)`，但仍不安装完整训练栈。不要改动 `make install-full` 语义。
- `configs/data/smoke.yaml` 必须包含且只包含下列受支持字段：

```yaml
input:
  path: tests/fixtures/wp1/raw_problems.jsonl
  format: raw_jsonl
test_split:
  visible_count: 2
  train_hidden_count: 2
  eval_hidden_count: 2
output:
  formats:
    - jsonl
    - hf_dataset
```

- seed 与 output root 由 CLI `--seed`、`--output-dir` 提供，不在业务逻辑硬编码。
- YAML 出现未知字段必须失败，不允许静默忽略。

**新增符号**：

```python
class ConfigError(ValueError):
    """Raised when a project YAML config is missing, malformed, or unsupported."""


def load_yaml_mapping(path: Path) -> dict[str, object]:
    """Load one YAML file and require a top-level mapping."""
```

**主要功能**：

- 使用 `yaml.safe_load`；空文件、非 mapping 顶层、文件不存在、YAML 语法错误均转换为带路径信息的 `ConfigError`。
- 此模块只负责安全加载，不理解 data 字段；Data Layer 在自己的 dataclass parser 中拒绝未知字段。
- 不读取环境变量，不在日志中输出 YAML 原文。

**测试方案**：

- 测试文件：`tests/unit/test_config.py`
- 新增测试函数：
  - `test_load_yaml_mapping_returns_mapping`：合法 YAML 返回普通 dict。
  - `test_load_yaml_mapping_rejects_non_mapping`：list 顶层抛 `ConfigError`。
  - `test_load_yaml_mapping_rejects_invalid_yaml`：语法错误包含配置路径。
  - `test_load_yaml_mapping_rejects_missing_file`：不存在路径得到明确错误。
- `tests/unit/data/test_prepare.py::test_data_config_rejects_unknown_keys` 覆盖 Data 配置未知字段。

**验证命令与通过标准**：

```bash
make install
.venv/bin/python -c "import datasets, yaml; print(datasets.__version__)"
make lint
.venv/bin/python -m pytest tests/unit/test_config.py
```

通过标准：依赖导入成功且 datasets 输出 `3.2.0`；Ruff/Mypy 全绿；上述 4 个配置测试全部通过。

---

### 步骤 2：实现 §7.1 的唯一 canonical schema 与严格转换

**目标文件**：

- `src/code_verifier/data/__init__.py`（新建）
- `src/code_verifier/data/schema.py`（新建）

**新增符号**：

```python
JsonScalar: TypeAlias = str | int | float | bool | None
JsonValue: TypeAlias = JsonScalar | list["JsonValue"] | dict[str, "JsonValue"]


class SchemaError(ValueError):
    """Raised when a record does not satisfy the canonical problem schema."""


@dataclass(frozen=True)
class TestCase:
    input: JsonValue
    expected: JsonValue


@dataclass(frozen=True)
class ProblemMetadata:
    difficulty: Literal["easy", "medium", "hard", "unknown"]
    category: tuple[str, ...]
    time_limit_seconds: float
    memory_limit_mb: int
    license: str
    source_url_hash: str | None


@dataclass(frozen=True)
class CodeProblem:
    problem_id: str
    source: str
    split: Literal["train", "validation", "test"]
    prompt: str
    function_name: str
    function_signature: str
    starter_code: str | None
    visible_tests: tuple[TestCase, ...]
    train_hidden_tests: tuple[TestCase, ...]
    eval_hidden_tests: tuple[TestCase, ...]
    reference_solution: str | None
    sft_response: str | None
    metadata: ProblemMetadata


def validate_json_value(value: object, *, field_path: str) -> JsonValue:
    """Validate and return a JSON-serializable value without coercion."""


def test_case_from_mapping(value: object, *, field_path: str) -> TestCase:
    """Parse one exact {input, expected} mapping into an immutable test case."""


def metadata_from_mapping(value: object) -> ProblemMetadata:
    """Parse and validate the exact §7.1 metadata object."""


def problem_from_mapping(value: object) -> CodeProblem:
    """Parse one exact canonical §7.1 record and validate every field."""


def test_case_to_mapping(test_case: TestCase) -> dict[str, JsonValue]:
    """Serialize a test case with exact §7.1 field names."""


def problem_to_mapping(problem: CodeProblem) -> dict[str, JsonValue]:
    """Serialize an immutable problem to the exact §7.1 JSON structure."""


def validate_problem(problem: CodeProblem) -> None:
    """Validate semantic invariants that are local to one canonical problem."""
```

**主要功能**：

- 必填字段必须存在，未知字段必须拒绝；不得用 `str(value)`、`bool(value)` 等方式静默强制类型。
- `problem_id/source/prompt/function_name/function_signature/license` 去除首尾空白后必须非空；保留正文内部格式。
- `split` 只允许 `train|validation|test`；difficulty 只允许规格枚举。
- `time_limit_seconds > 0`，`memory_limit_mb > 0`，category 每项非空且同一题内不重复。
- 三层测试在 schema 层都必须为非空；WP1 smoke 的具体数量由 split 配置校验。
- JSON 数值拒绝 NaN/Inf，dict key 只能是字符串；拒绝不可 JSON 序列化对象。
- `src/code_verifier/data/__init__.py` 只导出 `CodeProblem`、`ProblemMetadata`、`SchemaError`、`TestCase`，不放业务逻辑。
- 内部 tuple 在 `problem_to_mapping()` 中转回 JSON list，确保外部字段结构逐字匹配 §7.1。

**测试方案**：

- 测试文件：`tests/unit/data/test_schema.py`
- 新增测试函数：
  - `test_problem_round_trip_preserves_spec_fields`：mapping → dataclass → mapping 完全一致。
  - `test_problem_from_mapping_rejects_missing_required_field`：逐个删除顶层必填字段，参数化测试均抛 `SchemaError` 且错误含字段名。
  - `test_problem_from_mapping_rejects_unknown_field`：拼错字段不能被忽略。
  - `test_problem_from_mapping_rejects_invalid_split`：非法 split 失败。
  - `test_metadata_rejects_invalid_limits_and_difficulty`：0/负资源限制、非法枚举失败。
  - `test_json_value_rejects_nan_inf_and_non_string_keys`：不可序列化边界失败。
  - `test_frozen_schema_is_immutable`：修改 dataclass 字段抛 `FrozenInstanceError`。
  - `test_test_case_requires_exact_input_expected_fields`：删除/增加字段均失败。
- 覆盖规格：§7.1、§19.1 Data 的 schema 验证与缺失字段。

**验证命令与通过标准**：

```bash
make lint
.venv/bin/python -m pytest tests/unit/data/test_schema.py
```

通过标准：Ruff/Mypy 全绿；至少 8 组 schema 测试通过；删除任一 §7.1 必填字段必定失败。

---

### 步骤 3：实现确定性标准化、SHA-256 hash 与数据集去重

**目标文件**：`src/code_verifier/data/deduplicate.py`（新建）

**新增符号**：

```python
class DuplicateDataError(ValueError):
    """Raised when duplicate tests or problems would contaminate a dataset."""


def normalize_text(value: str) -> str:
    """Normalize Unicode, newlines, trailing spaces, and ordinary whitespace deterministically."""


def canonical_json(value: JsonValue) -> str:
    """Serialize a JSON value with stable key ordering and separators."""


def stable_json_hash(value: JsonValue) -> str:
    """Return the lowercase SHA-256 hex digest of canonical JSON."""


def test_case_hash(test_case: TestCase) -> str:
    """Hash one test's normalized input and expected value."""


def problem_content_hash(problem: CodeProblem) -> str:
    """Hash normalized task content while excluding ID, source, split, and test-layer assignment."""


def ensure_unique_test_cases(test_cases: Sequence[TestCase], *, context: str) -> None:
    """Reject duplicate normalized test cases in one input collection."""


def ensure_unique_problem_ids(problems: Sequence[CodeProblem]) -> None:
    """Reject repeated problem_id values across the dataset."""


def ensure_no_problem_overlap_across_splits(problems: Sequence[CodeProblem]) -> None:
    """Reject normalized task content appearing in more than one data split."""
```

**主要功能**：

- 只用标准库 `unicodedata`、`json`、`hashlib.sha256`。
- `canonical_json` 固定 `ensure_ascii=False`、`sort_keys=True`、紧凑 separators；稳定性不依赖 dict 插入顺序或 Python `hash()`。
- `test_case_hash` 同时包含 input 与 expected，不能只按 input 去重。
- `problem_content_hash` 至少包含 `normalize_text(prompt)`、`normalize_text(function_signature)`、规范化 starter/reference solution；排除 `problem_id` 和 `split`，从而捕获换 ID 后跨 split 混入的同题。
- 发现重复时错误必须列出冲突索引或 problem IDs；不静默保留第一条。

**测试方案**：

- 测试文件：`tests/unit/data/test_deduplicate.py`
- 新增测试函数：
  - `test_canonical_json_ignores_mapping_insertion_order`。
  - `test_stable_json_hash_has_sha256_shape_and_repeatability`。
  - `test_normalize_text_equates_newline_unicode_and_spacing_variants`。
  - `test_test_case_hash_uses_expected_value`。
  - `test_unique_test_cases_reject_normalized_duplicate`。
  - `test_unique_problem_ids_reject_duplicate_id`。
  - `test_problem_overlap_rejects_same_content_with_different_ids_across_splits`。
  - `test_problem_overlap_allows_distinct_content`。
- 覆盖规格：§7.4(1)(10)、§19.1 的 duplicate ID、split 泄漏、标准化与 hash 稳定性。

**验证命令与通过标准**：

```bash
make lint
.venv/bin/python -m pytest tests/unit/data/test_deduplicate.py
```

通过标准：Ruff/Mypy 全绿；8 个测试通过；同一输入跨进程重复计算 hash 相同（测试可用两个 Python 子进程比较结果）。

---

### 步骤 4：实现唯一 raw JSONL 输入适配器和确定性三层测试划分

**目标文件**：

- `src/code_verifier/data/adapters.py`（新建）
- `src/code_verifier/data/split_tests.py`（新建）

**raw JSONL 合同**：

每行必须是一个 JSON object，字段为 §7.1 canonical 字段的未分层版本：

- 必填：`problem_id`、`source`、`split`、`prompt`、`function_name`、`function_signature`、`tests`、`metadata`；
- 可空但仍必填：`starter_code`、`reference_solution`、`sft_response`；
- 禁止出现 `visible_tests`、`train_hidden_tests`、`eval_hidden_tests`，防止绕过统一 split；
- `tests` 的成员必须满足 `TestCase` 合同。

**新增符号**：

```python
class InputAdapterError(ValueError):
    """Raised when a raw input file or record cannot be adapted."""


@dataclass(frozen=True)
class RawCodeProblem:
    problem_id: str
    source: str
    split: Literal["train", "validation", "test"]
    prompt: str
    function_name: str
    function_signature: str
    starter_code: str | None
    tests: tuple[TestCase, ...]
    reference_solution: str | None
    sft_response: str | None
    metadata: ProblemMetadata


def raw_problem_from_mapping(value: object, *, line_number: int | None = None) -> RawCodeProblem:
    """Parse one exact raw JSONL record and attach line context to errors."""


def load_raw_jsonl(path: Path) -> list[RawCodeProblem]:
    """Load nonblank JSONL lines and reject malformed JSON, duplicate keys, and empty files."""


@dataclass(frozen=True)
class TestSplitConfig:
    visible_count: int
    train_hidden_count: int
    eval_hidden_count: int


def validate_test_split_config(config: TestSplitConfig) -> None:
    """Require positive layer sizes and visible_count within the §7.3 recommendation of 2–5."""


def split_test_cases(
    tests: Sequence[TestCase],
    *,
    problem_id: str,
    seed: int,
    config: TestSplitConfig,
) -> tuple[tuple[TestCase, ...], tuple[TestCase, ...], tuple[TestCase, ...]]:
    """Deterministically shuffle unique tests and return visible/train-hidden/eval-hidden layers."""


def adapt_raw_problem(raw: RawCodeProblem, *, seed: int, config: TestSplitConfig) -> CodeProblem:
    """Split one raw problem and build a validated canonical problem."""
```

**主要功能**：

- JSONL 使用 UTF-8；空行可以跳过，但全空文件失败；JSON parser 使用 `object_pairs_hook` 拒绝同一 object 的重复 key。
- 解析错误包含文件路径和 1-based 行号，不能吞掉原始异常上下文。
- `split_test_cases` 先以 `test_case_hash` 拒绝重复，再要求测试总数严格等于三层 count 之和。
- 每题随机序列使用 `sha256(f"{seed}:{problem_id}")` 派生局部整数 seed，再交给独立 `random.Random`；不得修改全局 random 状态。
- 同一 seed + problem_id + tests 顺序必须得到相同三层；不同 seed 的 fixture 全集至少有一题分配不同。
- 分层后调用 `validate_problem` 和层间泄漏检查；任何失败不输出半成品。
- input 与 expected 原样保留，不对测试语义做猜测。

**测试方案**：

- 测试文件：`tests/unit/data/test_adapters.py`
- 新增测试函数：
  - `test_load_raw_jsonl_reads_valid_records`。
  - `test_load_raw_jsonl_reports_malformed_line_number`。
  - `test_load_raw_jsonl_rejects_duplicate_json_key`。
  - `test_raw_adapter_rejects_missing_or_unknown_fields`。
  - `test_raw_adapter_rejects_pre_split_fields`。
  - `test_load_raw_jsonl_rejects_empty_file`。
- 测试文件：`tests/unit/data/test_split_tests.py`
- 新增测试函数：
  - `test_split_is_deterministic_for_same_seed`。
  - `test_split_changes_for_different_seed`。
  - `test_split_preserves_every_test_exactly_once`。
  - `test_split_rejects_duplicate_tests`。
  - `test_split_rejects_wrong_total_count`。
  - `test_split_config_rejects_invalid_counts`。
  - `test_adapt_raw_problem_produces_valid_canonical_problem`。
- 覆盖规格：§7.3、§7.4(1)、§19.1 Data。

**验证命令与通过标准**：

```bash
make lint
.venv/bin/python -m pytest tests/unit/data/test_adapters.py tests/unit/data/test_split_tests.py
```

通过标准：Ruff/Mypy 全绿；13 个测试通过；每个合法问题的三层并集等于原始 tests 且交集为空。

---

### 步骤 5：实现数据集级泄漏检查和白名单训练视图

**目标文件**：`src/code_verifier/data/leakage_checks.py`（新建）

**新增符号**：

```python
class LeakageError(ValueError):
    """Raised when test layers, splits, or artifacts violate isolation rules."""


class TrainingArtifactKind(str, Enum):
    SFT = "sft"
    PUBLIC_GRPO = "public_grpo"
    HIDDEN_GRPO = "hidden_grpo"


def check_no_test_layer_overlap(problem: CodeProblem) -> None:
    """Reject normalized test reuse within or across the three layers."""


def check_dataset(problems: Sequence[CodeProblem]) -> None:
    """Run schema, ID, cross-split, layer-overlap, and nonempty-split checks."""


def build_training_record(
    problem: CodeProblem,
    *,
    kind: TrainingArtifactKind,
) -> dict[str, JsonValue]:
    """Construct a training record from an explicit per-kind field whitelist."""


def check_training_record(
    record: Mapping[str, object],
    *,
    kind: TrainingArtifactKind,
) -> None:
    """Reject missing, unknown, or forbidden fields for one training view."""


def check_training_artifact(path: Path, *, kind: TrainingArtifactKind) -> int:
    """Validate every JSONL record in one training artifact and return its row count."""
```

**字段白名单（必须逐字实现）**：

| artifact | 允许字段 | 明确禁止 |
|---|---|---|
| SFT | `problem_id,prompt,sft_response,metadata` | 所有三层测试、reference_solution |
| Public GRPO | `problem_id,prompt,function_name,function_signature,visible_tests,metadata` | `train_hidden_tests,eval_hidden_tests,reference_solution,sft_response` |
| Hidden GRPO | `problem_id,prompt,function_name,function_signature,visible_tests,train_hidden_tests,metadata` | `eval_hidden_tests,reference_solution,sft_response` |

**主要功能**：

- 三层重复判断只使用 `test_case_hash`；同一层内重复和不同层交叉重复都失败，错误包含 problem_id 与层名。
- `check_dataset` 要求至少一个 train、validation、test 问题，检查重复 ID 和跨 split 内容重复，并逐题调用 schema/层检查。
- `build_training_record` 必须从空 dict 按白名单逐项构造；禁止先调用 `problem_to_mapping()` 再删除字段。
- `check_training_record` 既检查 key 名，也递归拒绝任何嵌套 key 名为 `eval_hidden_tests`，防止把字段藏入 metadata。
- SFT 的 `sft_response` 必须非空；若 canonical 数据中为空，则准备流程在导出 SFT 时明确失败，不得写 null 训练样本。
- `check_training_artifact` 必须在 CLI 成功退出前回读刚写出的训练 JSONL，确保磁盘内容也通过检查。
- WP1 通过不同子目录 `canonical/`、`hf_dataset/`、`training/` 落实 §7.4(7)；后续 dataloader 只允许读取对应 `training/*.jsonl`。

**测试方案**：

- 测试文件：`tests/unit/data/test_leakage_checks.py`
- 新增测试函数：
  - `test_layer_overlap_rejects_same_case_within_layer`。
  - `test_layer_overlap_rejects_same_case_across_layers`。
  - `test_check_dataset_rejects_duplicate_problem_id`。
  - `test_check_dataset_rejects_cross_split_problem_content`。
  - `test_check_dataset_requires_all_three_splits`。
  - `test_sft_record_contains_no_test_fields`。
  - `test_public_record_contains_visible_tests_only`。
  - `test_hidden_record_contains_no_eval_hidden_tests`。
  - `test_training_record_rejects_deleted_required_field`：参数化删除每个必需 key，检查失败。
  - `test_training_record_rejects_mixed_forbidden_field`：向每种 artifact 混入禁用层，检查失败。
  - `test_training_record_rejects_nested_eval_hidden_key`。
  - `test_sft_record_requires_response`。
- 覆盖规格：§7.4(1)–(5)(7)(9)(10)、§19.1 Data、§20 “删除或混入字段时测试能失败”。

**验证命令与通过标准**：

```bash
make lint
.venv/bin/python -m pytest tests/unit/data/test_leakage_checks.py
```

通过标准：Ruff/Mypy 全绿；至少 12 组泄漏测试通过；对任何 training artifact 加入 `eval_hidden_tests`（包括嵌套）都稳定失败。

---

### 步骤 6：实现准备/检查编排及 JSONL、Dataset、训练 artifact 导出

**目标文件**：`src/code_verifier/data/prepare.py`（新建）

**新增符号**：

```python
class DataPreparationError(RuntimeError):
    """Raised when an all-or-nothing data preparation run cannot complete."""


@dataclass(frozen=True)
class DataPreparationConfig:
    input_path: Path
    input_format: Literal["raw_jsonl"]
    test_split: TestSplitConfig
    output_formats: tuple[Literal["jsonl", "hf_dataset"], ...]


@dataclass(frozen=True)
class PreparationSummary:
    total_problems: int
    split_counts: dict[str, int]
    canonical_jsonl: Path | None
    hf_dataset_dir: Path | None
    training_artifacts: dict[TrainingArtifactKind, Path]


def data_config_from_mapping(value: Mapping[str, object], *, config_path: Path) -> DataPreparationConfig:
    """Parse exact input/test_split/output sections and resolve input relative to repository cwd."""


def load_data_preparation_config(path: Path) -> DataPreparationConfig:
    """Load YAML and return a validated immutable WP1 data config."""


def write_jsonl(records: Iterable[Mapping[str, JsonValue]], path: Path) -> int:
    """Atomically write deterministic UTF-8 JSONL and return the row count."""


def export_canonical_jsonl(problems: Sequence[CodeProblem], path: Path) -> int:
    """Write complete auditable records with all three test layers."""


def export_hf_dataset(problems: Sequence[CodeProblem], output_dir: Path) -> int:
    """Save complete canonical records with datasets.Dataset.save_to_disk()."""


def export_training_artifacts(
    problems: Sequence[CodeProblem],
    output_dir: Path,
) -> dict[TrainingArtifactKind, Path]:
    """Write and revalidate SFT/Public/Hidden JSONL files from field whitelists."""


def prepare_data(
    config: DataPreparationConfig,
    *,
    seed: int,
    output_dir: Path,
) -> PreparationSummary:
    """Adapt, split, check, and atomically publish all requested WP1 artifacts."""


def check_prepared_data(dataset_dir: Path) -> PreparationSummary:
    """Reload canonical and training artifacts and rerun all WP1 invariants."""
```

**主要功能**：

- pipeline 顺序固定：加载 raw → 逐题 split/adapt → `check_dataset` → 写临时目录 → 导出 canonical JSONL → 可选 HF Dataset → 导出三种 training artifact → 回读检查 → 原子 rename 到最终目录。
- 任何错误都不得留下看似成功的最终目录；临时目录必须在异常路径清理。
- 输出布局固定且自解释：

```text
<output-dir>/
├── canonical/
│   └── problems.jsonl
├── hf_dataset/
└── training/
    ├── sft.jsonl
    ├── public_grpo.jsonl
    └── hidden_grpo.jsonl
```

- `canonical/problems.jsonl` 和 `hf_dataset/` 是完整审计/评测数据，不得被称作 training artifact。
- training artifact 只导出 split=train 的 12 道 fixture；canonical/HF Dataset 包含全部 20 道。
- 每次 JSON object 使用 `sort_keys=True`、`ensure_ascii=False`、紧凑 separators；相同输入/seed/config 的输出字节 hash 必须一致。
- `export_hf_dataset` 使用 `Dataset.from_list(...).save_to_disk()`，返回实际 row 数；验收时用 `load_from_disk()` 回读 20 行。
- `check_prepared_data` 检查目录结构、canonical 20 行可反序列化、三 split 完整、training 文件存在且各自通过 `check_training_artifact`；summary 由实际磁盘内容计算，不信任外部 manifest。
- 输入路径来自 YAML，输出根和 seed 来自参数；禁止在函数内默认到用户目录或固定 data 路径。

**测试方案**：

- 测试文件：`tests/unit/data/test_prepare.py`
- 新增测试函数：
  - `test_data_config_parses_exact_supported_shape`。
  - `test_data_config_rejects_unknown_keys`。
  - `test_data_config_rejects_unsupported_format`。
  - `test_write_jsonl_is_deterministic_and_round_trippable`。
  - `test_prepare_data_writes_expected_layout`。
  - `test_prepare_data_training_artifacts_exclude_eval_hidden`。
  - `test_prepare_data_is_byte_deterministic_for_same_seed`。
  - `test_prepare_data_failure_does_not_publish_partial_output`。
  - `test_check_prepared_data_detects_deleted_required_field`。
  - `test_check_prepared_data_detects_mixed_eval_hidden_field`。
  - `test_export_hf_dataset_round_trips_records`。
- 覆盖规格：§4.1 一条命令预处理、§7.4、§16 配置与代码分离、§19.1/§19.2、§20 全部验收条目。

**验证命令与通过标准**：

```bash
make lint
.venv/bin/python -m pytest tests/unit/data/test_prepare.py
```

通过标准：Ruff/Mypy 全绿；至少 11 组 prepare 测试通过；失败路径没有最终输出；相同 seed 两次 canonical JSONL 的 SHA-256 完全相同。

---

### 步骤 7：把 WP1 编排接入现有 CLI，并统一 WP1 所需全局参数

**目标文件**：

- `src/code_verifier/cli.py`（修改）
- `tests/unit/test_cli.py`（修改）

**新增/修改符号**：

```python
def _add_common_arguments(
    parser: argparse.ArgumentParser,
    *,
    config_required: bool = False,
) -> None:
    """Add --config, --seed, --output-dir, and --log-level to one command parser."""


def _configure_logging(level: str) -> None:
    """Validate and configure the requested standard-library log level."""


def _prepare_data(args: argparse.Namespace) -> int:
    """Run the configured WP1 data pipeline and print a non-sensitive summary."""


def _check_data(args: argparse.Namespace) -> int:
    """Validate an existing WP1 prepared dataset and print a summary."""


def build_parser() -> argparse.ArgumentParser:
    """Build the CodeVerifier command-line parser with WP0 and WP1 commands."""


def main(argv: Sequence[str] | None = None) -> int:
    """Run the CLI and return a process exit code."""
```

**CLI 合同**：

```bash
python -m code_verifier.cli prepare-data \
  --config configs/data/smoke.yaml \
  --seed 42 \
  --output-dir data/processed/wp1-smoke \
  --log-level INFO

python -m code_verifier.cli check-data \
  --dataset data/processed/wp1-smoke \
  --seed 42 \
  --output-dir outputs/check-data \
  --log-level INFO
```

- `prepare-data`：`--config` 必填；`--seed` 默认 42；`--output-dir` 必填，拒绝已存在的非空目录，避免覆盖。
- `check-data`：`--dataset Path` 必填；通用 `--config` 可选但 WP1 不读取；`--seed`、`--output-dir` 仅为统一 CLI 合同保留并在 help 中说明 check 不改变数据。
- `record-environment` 继续保留 `--output`，并增加通用参数（均可选）以满足 §17“所有命令必须支持”；不得破坏 WP0 测试和行为。
- 所有子命令 help 必须列出 `--help --config --seed --output-dir --log-level`。
- handler 捕获 `ConfigError|SchemaError|InputAdapterError|DuplicateDataError|LeakageError|DataPreparationError`，向 stderr 输出一行不含隐藏测试内容的错误并返回 2；未知编程错误不得吞掉。
- 成功输出只包含 row count、split count、路径和格式，不打印任何测试内容。

**测试方案**：

- 测试文件：`tests/unit/test_cli.py`
- 保留并更新现有测试，新增：
  - `test_root_help_lists_wp1_commands`。
  - `test_all_subcommands_expose_common_arguments`：参数化三个命令的 help。
  - `test_prepare_data_requires_config_and_output_dir`。
  - `test_prepare_data_handler_forwards_seed_and_paths`：monkeypatch `prepare_data`，不执行真实 pipeline。
  - `test_check_data_handler_reports_summary`。
  - `test_data_error_returns_two_without_hidden_payload`。
  - `test_record_environment_behavior_remains_compatible`。
- 覆盖规格：§17、§19.3 最小 CLI 测试。

**验证命令与通过标准**：

```bash
make lint
.venv/bin/python -m pytest tests/unit/test_cli.py
.venv/bin/python -m code_verifier.cli prepare-data --help
.venv/bin/python -m code_verifier.cli check-data --help
```

通过标准：WP0 CLI 回归通过；两个新命令 help 返回 0；所有命令 help 均出现五个全局参数；错误路径返回 2 且 stderr 不含 `eval_hidden_tests` 的具体内容。

---

### 步骤 8：提供 20 题 fixture、端到端验收测试和直接相关文档更新

**目标文件**：

- `tests/fixtures/wp1/raw_problems.jsonl`（新建）
- `tests/integration/test_wp1_data_pipeline.py`（新建）
- `.gitignore`（修改）
- `README.md`（修改）
- `AGENTS.md`（修改）

**fixture 合同**：

- 恰好 20 行、20 个唯一 `problem_id`；12 train、4 validation、4 test。
- 每题恰好 6 个唯一测试，输入/期望均为 JSON 可序列化值。
- visible 目标数 2，符合 §7.3 的 2–5 建议；其余各 2。
- 题目均为短小函数级 Python 任务，至少覆盖数组、字符串、数学、字典/集合等类别；不引入 stdin/stdout 型任务。
- 每题提供非空 `reference_solution` 和 `sft_response`，但测试不得执行它们。
- prompt 不包含任何 `eval_hidden_tests` 数据；fixture 是人工可审计文本，禁止自动下载或依赖网络。
- 各 split 不得出现同题改写；测试层不得复制同一 input/expected 对。

**集成测试符号**：

```python
def test_wp1_smoke_pipeline_exports_twenty_problems(tmp_path: Path) -> None:
    """Run prepare-data and check-data over the committed 20-problem fixture."""


def test_wp1_training_artifacts_never_contain_eval_hidden_tests(tmp_path: Path) -> None:
    """Scan serialized training bytes and structured records for forbidden eval fields."""


def test_wp1_tampered_training_artifacts_fail_check(tmp_path: Path) -> None:
    """Delete a required field and mix an eval field, then require check-data to fail."""


def test_wp1_same_seed_is_reproducible(tmp_path: Path) -> None:
    """Require two end-to-end exports to have identical canonical JSONL digests."""
```

**文档与忽略规则**：

- `.gitignore` 继续忽略 `data/processed/`，但不能忽略 `tests/fixtures/wp1/raw_problems.jsonl`。
- README 将“WP0 only”改为“WP0 complete; WP1 data layer available”，新增两条 smoke 命令、输出目录说明、完整 canonical 与 training artifact 的安全边界；不宣传尚未实现的训练/执行能力。
- AGENTS 将“WP0 scope only”更新为当前阶段事实：WP0 已完成，WP1 只允许 Data Layer；保留不修改 submodule、strict mypy、测试路径等规则。
- README 明确本阶段修改了项目配置：新增 PyYAML/Datasets 固定依赖和 smoke YAML；没有修改 `third_party/open-r1` 内容或 commit。

**测试方案**：

- 测试文件：`tests/integration/test_wp1_data_pipeline.py`，使用上面 4 个测试。
- 对 fixture 增加 `tests/unit/data/test_adapters.py::test_committed_fixture_has_expected_shape`：断言 20/12/4/4 和每题 6 个测试。
- 集成测试通过调用 `main([...])` 或 subprocess 走真实 CLI；不能直接跳过 CLI handler 调用内部函数。
- tamper 测试先复制到 `tmp_path`，绝不修改仓库 fixture 或生成目录。

**验证命令与通过标准**：

```bash
make lint
make test
.venv/bin/python -m code_verifier.cli prepare-data \
  --config configs/data/smoke.yaml \
  --seed 42 \
  --output-dir data/processed/wp1-smoke \
  --log-level INFO
.venv/bin/python -m code_verifier.cli check-data \
  --dataset data/processed/wp1-smoke \
  --seed 42 \
  --output-dir outputs/check-data \
  --log-level INFO
.venv/bin/python -c "from datasets import load_from_disk; assert len(load_from_disk('data/processed/wp1-smoke/hf_dataset')) == 20"
```

通过标准：

- `make lint` 的 ruff check、ruff format --check、mypy 全部返回 0。
- `make test` 全部返回 0，包含 WP0 回归、WP1 单元测试和 4 个端到端测试。
- `prepare-data`、`check-data` 均返回 0。
- canonical JSONL 恰好 20 行，HF Dataset 恰好 20 行，split 为 12/4/4。
- 三个 training JSONL 各恰好 12 行；其原始字节和递归 key 均不含 `eval_hidden_tests`。
- public artifact 不含 `train_hidden_tests`；SFT artifact 不含任何测试字段。
- tamper 后删除必需字段或混入禁用字段时 `check-data` 返回 2。
- `git diff -- third_party/open-r1` 为空，submodule commit 仍为 `1416fa0cf21595d2083b399a2a0bbddd7f6e9563`。

## 6. 总体验收与测试计划

### 6.1 单元测试汇总

| 测试文件 | 规格覆盖 |
|---|---|
| `tests/unit/test_config.py` | YAML 安全加载、未知/非法配置 |
| `tests/unit/data/test_schema.py` | §7.1 schema、缺失字段、类型和枚举 |
| `tests/unit/data/test_adapters.py` | raw JSONL、输入适配、20 题 fixture |
| `tests/unit/data/test_split_tests.py` | 三层划分、seed、无重复 |
| `tests/unit/data/test_deduplicate.py` | duplicate ID、hash 稳定、跨 split 泄漏 |
| `tests/unit/data/test_leakage_checks.py` | §7.4 字段隔离、删除/混入失败 |
| `tests/unit/data/test_prepare.py` | 导出、原子发布、磁盘回读、Dataset |
| `tests/unit/test_cli.py` | §17 参数和 WP0 回归 |

### 6.2 集成测试

`tests/integration/test_wp1_data_pipeline.py` 必须以提交的 20 题 fixture 跑通：

1. raw JSONL → deterministic split；
2. canonical schema/check；
3. canonical JSONL + HF Dataset 导出；
4. 三种 training artifact 白名单导出；
5. `check-data` 回读；
6. tamper 后失败；
7. 相同 seed 字节级复现。

这对应 §19.2 的“20 道题的数据准备”；真实沙箱、小模型、reward、SFT/GRPO、checkpoint 和统一评测属于后续 WP，不在本计划伪造。

### 6.3 数据泄漏检查落地矩阵

| §7.4 条目 | WP1 落地 |
|---|---|
| 1. 三层标准化表示不得重复 | `check_no_test_layer_overlap` |
| 2. eval hidden 不得序列化到训练文件 | 白名单 `build_training_record` + 磁盘回读 |
| 3. GRPO dataloader 无 eval 列 | WP1 artifact 无该列；dataloader 接入在 WP6 再做 |
| 4. Public dataloader 无 train/eval | public artifact 同时移除二者 |
| 5. Hidden dataloader 无 eval | hidden artifact 移除 eval |
| 6. 日志不输出隐藏测试 | WP1 CLI 只打印计数/路径；训练日志在 WP6 再测 |
| 7. 缓存路径/文件名分离 | canonical/hf_dataset/training 子目录分离 |
| 8. 评测只加载冻结 checkpoint | WP7 范围 |
| 9. 测试题不进入训练 split | training artifact 仅筛选 split=train |
| 10. prompt/参考代码/测试近似去重 | NFKC/空白标准化 hash；跨 split content hash |

### 6.4 最终通过标准

- [ ] §20 WP1 目标、7 项交付与 4 项验收逐条满足。
- [ ] 20 题 fixture 可由一条 `prepare-data` 命令导出 JSONL 和 HF Dataset。
- [ ] 每题三层 tests 两两无重复，三层并集等于 raw tests。
- [ ] 删除必填字段、增加未知字段、混入禁止字段都会使测试或 `check-data` 明确失败。
- [ ] 所有 training artifact 不含 `eval_hidden_tests`；Public 额外不含 `train_hidden_tests`。
- [ ] 不同 data split 无重复 ID 或规范化内容重复。
- [ ] 相同配置与 seed 产生相同 canonical JSONL SHA-256。
- [ ] `make lint` 全绿。
- [ ] `make test` 全绿且 WP0 测试无回归。
- [ ] `third_party/open-r1/` 没有文件变更，submodule pin 未改变。
- [ ] README/AGENTS 不再错误声称仓库只允许 WP0。

## 7. 风险与注意事项

1. **隐藏测试质量不足（§24 Risk 2）**：20 题 fixture 必须人工 review 基本、边界、极值测试是否分散到三层；不得通过复制测试凑数量。WP1 只保证隔离与可审计，不声称覆盖率充分。
2. **数据准备超时（§24 Risk 7）**：只保留通用 raw JSONL 一个输入源，不接网络、不增加厂商适配器；后续真实数据可复用同一合同。
3. **近似去重能力有限**：本 WP 只做确定性文本规范化，不做代码语义等价；必须在 README/实施记录中如实注明。
4. **Hugging Face Dataset 类型推断**：嵌套 JSON 字段必须保持 20 行 schema 一致；若 `Dataset.from_list` 因不一致失败，应修正 fixture/schema，不得把对象 stringify 绕过。
5. **泄漏检查不可只搜字符串**：核心检查必须基于结构化 key 与 hash；原始字节搜索只作为额外验收。
6. **冻结 dataclass 内含可变 JSON 容器**：`validate_json_value` 应深拷贝/规范化 list 与 dict，禁止调用方在构造后通过别名修改；测试需覆盖输入 mapping 后续修改不影响 dataclass。若实现选择递归 tuple 内部表示，序列化时必须恢复 §7.1 JSON list。
7. **CLI 错误信息泄漏**：异常只报告 problem_id、字段路径、层名和行号，不打印具体 hidden input/expected。
8. **配置修改必须留痕**：WP1 实施完成后在 `proceedings.md` 明确记录新增 PyYAML/Datasets、Makefile 安装行为和 smoke YAML；同时明确上游 submodule 未修改。
9. **输出覆盖风险**：默认拒绝覆盖非空 output-dir；若未来需要 `--force`，另立任务，不在 WP1 擅自加入。
10. **SFT fixture 真实性**：`sft_response` 只作为结构/导出 smoke 数据，不用于宣称模型质量；后续训练数据准备需重新审查许可证和答案正确性。

## 8. 实施顺序与提交边界

建议按以下可独立 review 的小提交执行，每个提交先跑对应目标测试：

1. `chore(data): add pinned WP1 data dependencies and YAML loader`
2. `feat(data): add canonical problem schema`
3. `feat(data): add stable hashing and deduplication`
4. `feat(data): add raw JSONL adapter and deterministic test splitting`
5. `feat(data): add leakage checks and training views`
6. `feat(data): add atomic JSONL and Dataset export pipeline`
7. `feat(cli): add prepare-data and check-data commands`
8. `test(data): add twenty-problem fixture and WP1 integration acceptance`
9. `docs(data): document WP1 pipeline and update repository scope`

禁止把 WP2 parser 或 WP3 executor 混入上述提交。

## 9. 关联文档索引

- `PROJECT_SPEC_Open-R1_CodeVerifier.md`
  - §0：实现纪律、配置、seed、测试与错误处理
  - §4.1：一条命令数据预处理、可审计划分、eval hidden 不泄漏
  - §6.2：Data Layer 职责与禁止事项
  - §7.1：canonical schema
  - §7.3：三层测试定义
  - §7.4：泄漏防护
  - §16：仓库结构和配置分离
  - §17：CLI 命令及公共参数
  - §19.1：Data 单元测试
  - §19.2：20 题数据准备集成测试
  - §19.3：CI 数据泄漏和最小 CLI 测试
  - §20：WP1 目标/交付/验收
  - §24 Risk 2 / Risk 7：隐藏测试质量与数据准备回退
  - §29：Python 函数级任务等默认决策
- `proceedings.md`：WP0 已完成记录。
- `AGENTS.md`：项目结构、命令、代码风格、测试规则和 submodule 边界。
- `skills/next-wp-planner/references/plan-template.md`：本计划结构与自检要求。

## 10. 计划自检

- [x] 只覆盖 WP1，没有提前实现后续 WP。
- [x] 每个实现步骤都有仓库根目录相对路径。
- [x] 每个新增/修改代码步骤都给出完整函数/类签名。
- [x] 每步说明输入、输出、错误行为及现有 CLI/配置衔接。
- [x] 每步列出测试文件、测试函数、断言内容。
- [x] 每步列出验证命令和可判定的通过标准。
- [x] §7.1 外部字段名与结构逐字复用，无冲突接口。
- [x] 没有步骤修改 `third_party/open-r1/`。
- [x] 计划只要求文件读写和项目自带 shell 命令。
- [x] 计划不包含创建、启动或指挥执行 agent 的步骤。
- [x] WP1 验收可由命令退出码、行数、字段集合、hash 和测试结果客观判定。
