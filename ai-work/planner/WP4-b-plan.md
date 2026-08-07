# WP4-b 实施计划（Reward Layer、测试层隔离与 WP4 整体验收）

## 1. 元信息

| 项 | 值 |
|---|---|
| 目标 WP | WP4：Verifier 与 Reward（子阶段 b：Reward Layer、测试层隔离与整体收口） |
| 规格依据 | `PROJECT_SPEC_Open-R1_CodeVerifier.md` §6.2 Reward Layer、§10.1–§10.6、§12.3、§16、§19、§20 WP4、§29 |
| 前置阶段 | WP4-a（`proceedings.md` 状态：已完成，验收通过） |
| 分支 | `feat/wp4-b` |
| worktree | `.worktrees/wp4-b` |
| 计划文件 | `ai-work/planner/WP4-b-plan.md` |
| 面向的执行 agent | 仅文件读写 + 基础 shell；可运行项目自带的 `make`、pytest、CLI；不依赖专用工具、MCP 或其它 skill |
| 计划粒度 | WP4 的第二个且最终子阶段；6 个步骤、4 个新业务模块 |
| 预计配置影响 | 不新增 YAML、CLI 参数或 Python package 依赖；不修改 Open-R1 submodule、parser、executor 或 verifier 公共合同 |

> WP4-a 已完成统一 Verification Layer。本计划只完成剩余 Reward Layer，并在本阶段末对 WP4 §20 的全部交付与验收做整体收口。执行者不得把工作扩展到 WP5 统一评测、WP6 SFT 或 WP7 GRPO 集成。

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

在 WP4-a `verify_completion()` 之上实现统一 Reward Layer：

- 逐字保留规格 §10.5 的三个公共函数名、参数顺序与返回形态；
- Public reward 只使用 `visible_tests`，Hidden reward 只使用 `train_hidden_tests`；
- 两个薄封装共用同一个 `compute_code_rewards()` 核心，辅助项完全一致；
- 对 TRL/Open-R1 按列批量输入做严格长度对齐检查，禁止 `zip` 静默截断；
- 将 Open-R1 当前固定 commit 的 chat-style completion payload 严格转换为 parser 所需文本，同时保留直接传字符串的测试/本地调用路径；
- 使用 WP4-a 的结构化验证结果计算测试分量、可执行分量、timeout penalty 与 invalid-format penalty；
- 为每条 completion 生成可 JSON 序列化、无敏感 payload 的 reward component record，供 WP7 真正接入训练日志；
- 对 parser failure、timeout、sandbox/infrastructure failure、executor exception 和输入合同错误采用 fail-closed 语义；
- 最终完成 WP4 全部单元/集成测试和总体验收。

### 2.5 范围内

- 新建 `src/code_verifier/rewards/__init__.py`。
- 新建 `src/code_verifier/rewards/common.py`：batch 对齐、completion 提取、reward 分量计算、`compute_code_rewards()`、component record。
- 新建 `src/code_verifier/rewards/public_reward.py`：规格 `public_code_reward()` 薄封装与 Public 测试层防泄漏 guard。
- 新建 `src/code_verifier/rewards/hidden_reward.py`：规格 `hidden_code_reward()` 薄封装与 eval-hidden guard。
- 新增 Reward 单元测试，覆盖规格 §10.6 / §19.1 全部要求。
- 新增 Mock 集成测试，验证 training artifact 形态、completion payload、Public/Hidden 测试来源和 component records。
- 更新 `README.md`、`AGENTS.md`，记录 WP4 完成后的稳定 API、边界与后续 WP7 接入方式。
- 本阶段 reviewer 最终通过后，才允许把 WP4 整体登记为完成。

### 2.6 范围外

- 不修改 WP4-a 的 `VerificationResult`、`verify_completion()` 公共签名或 parser/executor 语义，除非 reviewer 发现阻断级真实合同缺陷；普通便利性需求不得作为修改理由。
- 不把 reward 逻辑放进 Verification Layer；verifier 继续只返回事实，不解释 reward。
- 不实现 WP5 generation、pass@1、bootstrap、evaluation CLI 或 Base 模型结果。
- 不实现 WP6 SFT。
- 不修改 `third_party/open-r1/**`，不把本项目 reward 注册进上游 `REWARD_FUNCS_REGISTRY`；正式 GRPO/Open-R1 adapter 接入属于 WP7。
- 不新增 `train-grpo` CLI、GRPO YAML、W&B 初始化、trainer callback、checkpoint 或训练循环。
- 不持久化 reward 日志文件；WP4-b 负责生成稳定 component records，WP7 负责将其接到 rollout/reward 日志与实验追踪。
- 不使用 `eval_hidden_tests` 计算任何训练 reward。
- 不增加长度奖励、推理格式奖励或规格外 penalty。
- 不直接调用 Piston/Open-R1 code provider；reward 只能经调用方注入的现有 `CodeExecutor` → WP4-a verifier 路径执行。
- 执行阶段不得修改 `proceedings.md`；只有最终 reviewer 通过并合并后才能登记 WP4 完成。

## 3. 前置条件、现状与约束

### 3.1 proceedings 与当前实现状态

- `proceedings.md` 已登记 WP4-a 于 2026-08-06 完成，明确写明 Public/Hidden reward、分量日志与训练接入仍待 WP4-b。
- WP4-a 最终审查 `ai-work/reviewer/WP4-review.md` R2 结论为通过；合并后的 main：
  - `make lint` 全绿；
  - `make test`：481 passed，3 个既有真实 Piston tests 默认 skipped；
  - Verification 定向测试：37 passed，0 failed，0 skipped。
- `src/code_verifier/verification/verifier.py` 已提供：

```python
def verify_completion(
    completion: str,
    tests: Sequence[Mapping[str, object]],
    function_name: str,
    metadata: Mapping[str, object],
    executor: CodeExecutor,
) -> VerificationResult:
    ...
```

- `VerificationResult` 已保证：
  - `pass_rate` 有限且等于 `passed_tests / total_tests`；
  - parser failure 唯一表现为 `status=PARSE_ERROR, parsed=False, executed=False`；
  - executor-side `PARSE_ERROR` 会 fail-closed 为 `SANDBOX_ERROR`；
  - `infrastructure_failure` 与 `SANDBOX_ERROR` 一致；
  - timeout 是已解析、已进入执行路径、非 infrastructure failure；
  - 0 tests 在 verifier 调用前作为合同错误拒绝。
- WP1 training artifacts 已提供：
  - Public GRPO：`problem_id`、`prompt`、`function_name`、`function_signature`、`visible_tests`、`metadata`；
  - Hidden GRPO：上述字段 + `train_hidden_tests`；
  - 所有 training artifact 均由字段白名单和递归检查禁止 `eval_hidden_tests`。
- 当前 `src/code_verifier/rewards/` 不存在。

### 3.2 规格 §10 固定 reward 公式

公共辅助项不得改写：

```text
executable_reward =
    0.1  if code was parsed and executed without infrastructure failure
    0.0  otherwise

timeout_penalty =
   -0.2  if execution timed out
    0.0  otherwise

invalid_format_penalty =
   -0.1  if no valid Python code block or target function is missing
    0.0  otherwise
```

Public：

```text
public_test_reward = visible_tests_pass_rate

R_public =
    public_test_reward
    + executable_reward
    + timeout_penalty
    + invalid_format_penalty
```

Hidden：

```text
hidden_test_reward = train_hidden_tests_pass_rate

R_hidden =
    hidden_test_reward
    + executable_reward
    + timeout_penalty
    + invalid_format_penalty
```

### 3.3 规格 §10.5 公共 API：参数名、顺序与返回形态必须保留

执行实现可增加类型标注，但不得更名、重排、删除参数，不得改变返回形态：

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
```

内部公共核心：

```python
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

> 计划中的实现签名必须保留以上参数名和位置。为满足 strict mypy，可给未标注参数补充 `Sequence[object]` / `CodeExecutor` / `object` 等兼容类型注解，但不得改变调用语义。

### 3.4 已验证的固定 Open-R1 completion callback 行为

本仓库固定的 `third_party/open-r1` commit 为 `1416fa0cf21595d2083b399a2a0bbddd7f6e9563`。只读检查已确认：

- `src/open_r1/grpo.py` 会把 dataset prompt 转成 chat conversation 后传给 `GRPOTrainer`；
- `src/open_r1/rewards.py` 中现有 reward functions 把 `completions` 当作批量 chat message 列表读取，例如 `completion[-1]["content"]`；
- 当前上游 reward callback 也通过 `**kwargs` 接收 dataset 的其它列。

因此 WP4-b 必须支持两种 completion item：

1. `str`：本项目直接调用、单元测试与后续非 chat consumer；
2. Open-R1 chat-style sequence：取最后一条 mapping 的精确字符串 `content`。

不得支持未验证的第三种隐式 coercion；payload 结构错误属于 reward 调用合同错误，而不是模型 invalid-format failure。

### 3.5 横切硬性规则

- 使用 `uv` 与现有 Makefile 管理环境；不得裸 `pip install`。
- 新模块使用 `from __future__ import annotations`、完整类型标注、docstring、Ruff 双引号、119 列、strict mypy。
- Reward Layer 不得读取完整 `CodeProblem`，只接收明确列；不得自行打开 dataset、JSONL 或缓存文件。
- Reward Layer 不得解析或执行代码；解析/执行必须唯一委托给 `verify_completion()`。
- 不捕获 `BaseException`。
- 输入/配置合同错误不得被转换成高 reward 或默认 reward；应抛脱敏 `RewardContractError`。
- 模型产生的正常 parse failure、timeout、wrong answer、runtime error 等必须返回有限 reward，而不是抛出训练级异常。
- component record 不得包含 completion、code、tests、function name、metadata、stdout、stderr 或嵌套 `execution_result`。
- 不硬编码 executor endpoint、路径、模型、设备、seed 或密钥。
- 不修改 `third_party/open-r1/**`；WP7 以后若需要上游接入，只能经 `code_verifier.training.open_r1_adapter`。

### 3.6 本阶段明确实现决策

1. **公共核心只接收已选择测试列**：`compute_code_rewards()` 只有一个 `tests_batch`，不接收 `visible_tests`/`train_hidden_tests`/`eval_hidden_tests` 多层容器；Public/Hidden 差异只发生在薄封装传哪一列。
2. **mode 仅允许 `public` / `hidden`**：其它字符串在执行任何 completion 前抛 `RewardContractError`。mode 只影响 component record 标签，不改变公式或辅助项。
3. **严格 batch 对齐**：先读取四列长度，必须 `len(completions) == len(tests_batch) == len(function_names) == len(metadata_batch)`；禁止使用 `zip` 作为对齐机制。全空 batch 允许返回 `([], [])`，且零 executor 调用。
4. **completion payload 全量预解析**：在任何 verifier/executor 调用前，把整批 completion items 转为 `list[str]`。chat-style item 必须是非空 sequence，最后一项必须是 mapping，且 `content` 必须是精确字符串。结构错误抛脱敏 `RewardContractError`；空字符串本身允许进入 parser，作为模型 invalid-format failure 正常计分。
5. **executor 从 wrapper 的 `**kwargs` 注入**：Public/Hidden wrapper 必须要求 `kwargs["executor"]` 存在且具有 callable `execute` 属性；缺失/无效 executor 是配置错误，执行前抛 `RewardContractError`。WP7 可通过闭包/partial/adapter 绑定 executor，本阶段不决定训练生命周期。
6. **Public 泄漏 guard**：`public_code_reward()` 若 `kwargs` 中出现 `train_hidden_tests` 或 `eval_hidden_tests`，必须在任何验证执行前拒绝。这样即使误把 Hidden/full record 喂给 Public callback，也不会静默读取或忽略隐藏测试列。
7. **Hidden 泄漏 guard**：`hidden_code_reward()` 必须拒绝 `eval_hidden_tests`。Hidden artifact 合法包含 `visible_tests`，因此 wrapper 可以忽略 `kwargs["visible_tests"]`，但绝不能用其计分。
8. **其它 dataset kwargs**：`problem_id`、`prompt`、`function_signature` 等与 reward 无关的列可忽略；不得写入 component record。
9. **测试主分量**：`test_reward = verification.pass_rate`。Public/Hidden 不各自实现不同计算函数。
10. **可执行分量**：仅当 `verification.parsed is True`、`verification.executed is True` 且 `verification.infrastructure_failure is False` 时为 `0.1`，否则 `0.0`。
11. **timeout penalty**：仅当 `verification.status is ExecutionStatus.TIMEOUT` 时为 `-0.2`，否则 `0.0`。
12. **invalid-format penalty**：仅当 `verification.status is ExecutionStatus.PARSE_ERROR`（合同等价于 `parsed=False`）时为 `-0.1`，否则 `0.0`。
13. **sandbox/infrastructure failure**：测试主分量使用 verifier 的 0.0；可执行分量为 0；不得额外给正分。总 reward 因而为 0.0，除非未来规格明确增加负 infrastructure penalty；本阶段不得自造 penalty。
14. **总分公式唯一**：`total_reward = test_reward + executable_reward + timeout_penalty + invalid_format_penalty`。不得加入 rounding、clamp、长度项或其它 reward。
15. **有限值双重校验**：每个分量和 total 在 append 前均用 `math.isfinite()` 校验。出现非有限值抛 `RewardContractError`，不得替换为 0 或其它默认值。
16. **验证合同错误**：`verify_completion()` 因 tests/function/metadata 输入不合法抛出的 `VerificationContractError` 要转换为脱敏 `RewardContractError("reward item violates verification input contract")`；不得包含 payload。
17. **模型执行异常**：executor 普通异常已由 WP4-a verifier 转为 sanitized `SANDBOX_ERROR`，Reward Layer应正常生成 0.0 test reward / 0.0 executable reward，不再次抛训练级异常。
18. **component record 字段固定**：每条记录至少包含：`mode`、`test_reward`、`executable_reward`、`timeout_penalty`、`invalid_format_penalty`、`total_reward`、`status`、`parsed`、`executed`、`infrastructure_failure`、`passed_tests`、`total_tests`、`parse_error_type`、`failure_counts`。不得包含 `execution_result`。
19. **component records 即 WP4 的“分量日志”工件**：`compute_code_rewards()` 第二返回值与 rewards 严格一一对齐，JSON-safe、字段稳定、可直接由 WP7 写入 rollout/reward logger；WP4-b 不负责持久化 transport。
20. **wrapper 返回合同**：Public/Hidden wrapper 必须仅返回 `list[float]`，丢弃 common core 的 component records，以严格保持 §10.5 TRL reward callback 返回形态；需要分量日志的 WP7 adapter 应调用/包装公共 core，而不是修改 wrapper 返回类型。
21. **无共享可变状态**：Reward 模块不得维护全局 executor、last batch、component history 或 mutable cache；所有结果由当前调用返回。

## 4. 目标文件总览

### 4.1 新建

- `src/code_verifier/rewards/__init__.py`
- `src/code_verifier/rewards/common.py`
- `src/code_verifier/rewards/public_reward.py`
- `src/code_verifier/rewards/hidden_reward.py`
- `tests/unit/rewards/__init__.py`
- `tests/unit/rewards/test_common.py`
- `tests/unit/rewards/test_public_reward.py`
- `tests/unit/rewards/test_hidden_reward.py`
- `tests/integration/test_wp4b_reward_pipeline.py`

### 4.2 修改

- `README.md`
- `AGENTS.md`

### 4.3 明确不修改

- `src/code_verifier/data/**`
- `src/code_verifier/parsing/**`
- `src/code_verifier/execution/**`
- `src/code_verifier/verification/**`
- `src/code_verifier/training/**`
- `src/code_verifier/cli.py`
- `configs/**`
- `Makefile`
- `pyproject.toml`
- `third_party/open-r1/**`
- `proceedings.md`（executor 阶段）

## 5. 实施步骤

### 步骤 1：建立 Reward common 的输入合同、completion 提取与 batch 对齐

**目标文件**：

- `src/code_verifier/rewards/common.py`（新建，先实现输入/辅助合同）
- `tests/unit/rewards/__init__.py`（新建）
- `tests/unit/rewards/test_common.py`（新建，先覆盖输入合同）

**新增 / 修改的符号**：

```python
from collections.abc import Mapping, Sequence
from typing import Any

from code_verifier.execution.base import CodeExecutor


class RewardContractError(ValueError):
    """Raised when reward callback inputs or computed components violate the public contract."""


def _batch_length(value: object, *, field_name: str) -> int:
    """Return the length of one non-string batch sequence or raise a sanitized contract error."""


def _extract_completion_text(item: object) -> str:
    """Extract exact completion text from a raw string or pinned Open-R1 chat-style item."""


def _completion_texts(completions: object) -> list[str]:
    """Validate and extract every completion before any verifier/executor side effect."""


def _validate_batch_alignment(
    completions: object,
    tests_batch: object,
    function_names: object,
    metadata_batch: object,
) -> int:
    """Require four equal batch lengths without zip-based truncation."""


def _require_executor(value: object) -> CodeExecutor:
    """Return an executor-like object with callable execute, or raise before scoring."""
```

**主要功能**：

- `_batch_length()` 必须拒绝 `str`/`bytes`/`bytearray` 作为 batch，拒绝无 `Sequence` 语义的对象；不通过 iterator 消耗数据。
- `_validate_batch_alignment()` 显式比较四个长度，不得写 `for ... in zip(...)` 来决定 item 数量；不一致时错误消息只指出字段名/长度，不打印内容。
- `_extract_completion_text()`：
  - `str` 原样返回；
  - chat-style completion 必须是非 string sequence；末项必须 `Mapping`；必须存在 `content` 且值为 `str`；
  - 不要求非空 content，让 parser 负责 `empty_completion` taxonomy；
  - 不拼接多条 message、不 strip、不做 Unicode 正规化；
  - 不接受 dict 直接作为 completion item，也不调用 `str(value)` coercion。
- `_completion_texts()` 必须先对整批完成上述转换并返回新的 `list[str]`，使第 N 条结构错误不会发生前 N-1 条 executor side effect。
- `_require_executor()` 只做配置级结构 guard：对象必须有 callable `execute`；不执行探测请求。
- 全空四列合法；completion extraction 返回空 list。

**配置 / CLI 变更**：无。

**测试方案**：

- 测试文件：`tests/unit/rewards/test_common.py`
- 新增测试函数：
  - `test_batch_alignment_accepts_equal_lengths_and_empty_batch`：等长与全空合法。
  - `test_batch_alignment_rejects_each_length_mismatch_without_zip_truncation`：分别让 tests/function/metadata 短一项或长一项，全部抛 `RewardContractError`。
  - `test_completion_text_accepts_raw_string_without_normalization`：CRLF/Unicode/空格原样保留。
  - `test_completion_text_accepts_pinned_open_r1_chat_shape_and_uses_last_message_content`：与固定 Open-R1 当前读取方式一致。
  - `test_completion_text_rejects_empty_chat_missing_content_non_string_content_and_direct_mapping`：结构错误 fail-fast。
  - `test_completion_batch_is_fully_validated_before_any_verifier_call`：monkeypatch verifier/counter，后项 payload 错误时调用数为 0。
  - `test_require_executor_rejects_missing_and_non_callable_execute`。
  - `test_input_errors_do_not_echo_completion_or_dataset_sentinels`。
- 覆盖规格边界：§10.5 TRL 按列 batch 对齐、禁止 zip 静默截断；固定 Open-R1 callback completion 兼容。

**验证命令与通过标准**：

```bash
../../.venv/bin/python -m pytest tests/unit/rewards/test_common.py -k "batch or completion or executor"
make VENV=../../.venv lint
```

通过标准：所有 mismatch 在任何 verifier/executor 调用前失败；raw/chat completion 文本提取确定；错误不含 payload；strict mypy 通过。

---

### 步骤 2：实现统一 reward 分量映射、component record 与 `compute_code_rewards()`

**目标文件**：

- `src/code_verifier/rewards/common.py`（继续实现）
- `tests/unit/rewards/test_common.py`（继续补齐公式与失败语义）

**新增 / 修改的符号**：

```python
import math

from code_verifier.execution.base import CodeExecutor, ExecutionStatus
from code_verifier.verification import VerificationContractError, VerificationResult, verify_completion


def _reward_components_from_verification(
    result: VerificationResult,
    *,
    mode: str,
) -> dict[str, object]:
    """Map one validated verification result to the exact §10 reward components."""


def _validate_component_record(record: Mapping[str, object]) -> None:
    """Require exact component fields, finite numeric values, and total=sum(components)."""


def compute_code_rewards(
    completions,
    tests_batch,
    function_names,
    metadata_batch,
    executor,
    mode: str,
) -> tuple[list[float], list[dict]]:
    """Compute aligned code rewards and sanitized component records for one selected test source."""
```

实现时可增加兼容 strict mypy 的参数类型标注，但参数名、顺序、`mode: str` 和返回形态不得改变。

**主要功能**：

- 调用顺序固定：
  1. 验证 `mode in {"public", "hidden"}`；
  2. `_validate_batch_alignment(...)`；
  3. `_completion_texts(completions)` 全批预解析；
  4. 空 batch 直接返回 `([], [])`；
  5. 使用索引 `for index in range(batch_size)` 读取四列，不使用 zip；
  6. 对每项调用 `verify_completion(completion_texts[index], tests_batch[index], function_names[index], metadata_batch[index], executor)`；
  7. 将 `VerificationContractError` 转为统一脱敏 `RewardContractError`；
  8. `_reward_components_from_verification()`；
  9. `_validate_component_record()`；
  10. append `float(total_reward)` 与新的 component dict。
- `_reward_components_from_verification()` 严格按 §10：
  - `test_reward = float(result.pass_rate)`；
  - `executable_reward = 0.1` iff parsed + executed + not infrastructure failure；
  - `timeout_penalty = -0.2` iff top-level status `TIMEOUT`；
  - `invalid_format_penalty = -0.1` iff top-level status `PARSE_ERROR`；
  - `total_reward` 为四项直接相加。
- component record exact fields：
  - `mode`；
  - `test_reward`；
  - `executable_reward`；
  - `timeout_penalty`；
  - `invalid_format_penalty`；
  - `total_reward`；
  - `status`（`ExecutionStatus.value`）；
  - `parsed`；
  - `executed`；
  - `infrastructure_failure`；
  - `passed_tests`；
  - `total_tests`；
  - `parse_error_type`；
  - `failure_counts`（新 dict）。
- `_validate_component_record()` 必须：
  - exact field set；
  - 四个分量和 total 均为非 bool finite number；
  - `total_reward` 以 `abs_tol=1e-12` 等于四分量和；
  - mode/status/flags/counts 结构可 JSON 序列化；
  - 不允许 `execution_result`、completion、code、tests、metadata 等额外字段。
- 不 round/clamp reward。
- 普通模型失败必须稳定返回：
  - 全错但可执行：`0.0 + 0.1 = 0.1`；
  - parser failure：`0.0 - 0.1 = -0.1`；
  - timeout 且 0 pass：`0.0 + 0.1 - 0.2 = -0.1`；
  - sandbox/infrastructure failure：`0.0`；
  - 全通过：`1.0 + 0.1 = 1.1`。
- 若 timeout 前已有部分测试通过，则保留实际 `pass_rate + 0.1 - 0.2`；不得把 timeout 强制覆盖为固定分数。

**配置 / CLI 变更**：无。

**测试方案**：

- 测试文件：`tests/unit/rewards/test_common.py`
- 新增测试函数：
  - `test_reward_formula_all_pass_partial_fail_and_all_fail_is_monotonic`：同测试总数下 1.1 > partial+0.1 > 0.1。
  - `test_parse_failure_has_invalid_format_penalty_and_no_executable_reward`：总分 -0.1。
  - `test_missing_target_function_uses_same_invalid_format_penalty`。
  - `test_timeout_keeps_pass_rate_adds_executable_and_applies_minus_point_two`。
  - `test_runtime_and_wrong_answer_keep_executable_reward_without_extra_penalty`。
  - `test_sandbox_error_and_executor_exception_receive_no_positive_executable_or_test_reward`。
  - `test_all_reward_numbers_are_finite_and_component_total_matches_sum`。
  - `test_component_record_is_json_safe_payload_free_and_aligned_with_rewards`。
  - `test_invalid_mode_fails_before_verifier_or_executor_calls`。
  - `test_verification_input_contract_error_becomes_sanitized_reward_contract_error`。
  - `test_compute_returns_exactly_one_reward_and_component_record_per_completion`。
  - `test_compute_uses_indexing_not_silent_zip_truncation`：配合不等长输入确认零调用。
- 覆盖规格边界：§10.1–§10.6 全部公式、异常不静默高分、有限数值、batch 对齐、基础设施错误；§19.1 Reward。

**验证命令与通过标准**：

```bash
../../.venv/bin/python -m pytest tests/unit/rewards/test_common.py
make VENV=../../.venv lint
```

通过标准：公式精确；全通过 > 部分 > 全失败；timeout/parse/sandbox 语义符合规格；component records 数量与 rewards 完全一致且 JSON-safe；所有数值 finite。

---

### 步骤 3：实现 Public reward 薄封装和 hidden/eval 泄漏 guard

**目标文件**：

- `src/code_verifier/rewards/public_reward.py`（新建）
- `tests/unit/rewards/test_public_reward.py`（新建）

**新增 / 修改的符号**：

```python
def public_code_reward(
    completions,
    visible_tests,
    function_name,
    metadata,
    **kwargs,
) -> list[float]:
    """Compute Public-RLVR rewards using visible_tests as the only test source."""
```

实现时可增加兼容 strict mypy 的类型标注，但不得更改规格参数名、参数顺序或返回类型。

**主要功能**：

- 在任何 common/verifier 调用前：
  - 若 `"train_hidden_tests" in kwargs`，抛 `RewardContractError`；
  - 若 `"eval_hidden_tests" in kwargs`，抛 `RewardContractError`；
  - 通过 common helper 从 `kwargs["executor"]` 取得 executor；缺失/无效则失败。
- 调用必须严格为语义等价：

```python
rewards, _ = compute_code_rewards(
    completions,
    visible_tests,
    function_name,
    metadata,
    executor,
    mode="public",
)
return rewards
```

- 不读取 `visible_tests` 以外的测试列；不从 metadata / kwargs 嵌套寻找测试。
- `problem_id`、`prompt`、`function_signature` 等非测试 kwargs 可忽略。
- 不复制 common 公式；Public 文件不得出现 `0.1`、`-0.2`、`-0.1` 的独立 reward 计算逻辑。

**配置 / CLI 变更**：无。

**测试方案**：

- 测试文件：`tests/unit/rewards/test_public_reward.py`
- 新增测试函数：
  - `test_public_reward_passes_visible_tests_to_common_with_public_mode`：monkeypatch common，确认 source/mode/executor 参数精确。
  - `test_public_reward_rejects_train_hidden_tests_before_any_execution`。
  - `test_public_reward_rejects_eval_hidden_tests_before_any_execution`。
  - `test_public_reward_ignores_non_test_dataset_columns`。
  - `test_public_reward_requires_bound_executor`。
  - `test_public_reward_returns_only_float_list_and_preserves_batch_length`。
  - `test_public_reward_forbidden_field_error_does_not_echo_hidden_payload`。
- 覆盖规格边界：§10.3、§10.5、§10.6 Public 不读取 hidden tests；§20 eval hidden 不可进入训练 reward 路径。

**验证命令与通过标准**：

```bash
../../.venv/bin/python -m pytest tests/unit/rewards/test_public_reward.py
make VENV=../../.venv lint
```

通过标准：Public wrapper 只有 visible source；任何 hidden/eval-hidden 列注入均在零 verifier/executor 调用下失败；返回数量严格对齐 completion。

---

### 步骤 4：实现 Hidden reward 薄封装，并证明辅助项与 Public 完全一致

**目标文件**：

- `src/code_verifier/rewards/hidden_reward.py`（新建）
- `tests/unit/rewards/test_hidden_reward.py`（新建）

**新增 / 修改的符号**：

```python
def hidden_code_reward(
    completions,
    train_hidden_tests,
    function_name,
    metadata,
    **kwargs,
) -> list[float]:
    """Compute Hidden-RLVR rewards using train_hidden_tests as the only scoring test source."""
```

实现时可增加兼容 strict mypy 的类型标注，但不得更改规格参数名、参数顺序或返回类型。

**主要功能**：

- 在任何 common/verifier 调用前，若 `"eval_hidden_tests" in kwargs`，抛 `RewardContractError`。
- 合法 Hidden artifact 会同时带 `visible_tests`；该字段只能被忽略，不得加入、fallback 或混合到 `train_hidden_tests`。
- 从 `kwargs["executor"]` 获取 executor，调用必须严格为语义等价：

```python
rewards, _ = compute_code_rewards(
    completions,
    train_hidden_tests,
    function_name,
    metadata,
    executor,
    mode="hidden",
)
return rewards
```

- Hidden 文件不得复制 reward 公式。
- 使用相同 completion + 相同 selected tests + 相同 verification result 时，Public/Hidden 的 `test_reward`、三个辅助分量和 total 必须数值完全一致，唯一允许不同的是 component record 的 `mode` 标签。

**配置 / CLI 变更**：无。

**测试方案**：

- 测试文件：`tests/unit/rewards/test_hidden_reward.py`
- 新增测试函数：
  - `test_hidden_reward_passes_train_hidden_tests_to_common_with_hidden_mode`。
  - `test_hidden_reward_rejects_eval_hidden_tests_before_any_execution`。
  - `test_hidden_reward_ignores_visible_tests_column_and_never_uses_it_for_scoring`：visible sentinel 与 hidden source 冲突时 Mock 调用只出现 hidden tests。
  - `test_hidden_reward_requires_bound_executor`。
  - `test_hidden_reward_returns_only_float_list_and_preserves_batch_length`。
  - `test_public_and_hidden_common_auxiliary_components_are_identical_for_same_verification_result`：直接调用 common 两个 mode，比较除 mode 外全字段。
  - `test_hidden_reward_eval_hidden_error_does_not_echo_payload`。
- 覆盖规格边界：§10.4–§10.6 Hidden 不读 eval tests、辅助项完全一致；§20 两种 reward 只在来源上不同。

**验证命令与通过标准**：

```bash
../../.venv/bin/python -m pytest tests/unit/rewards/test_hidden_reward.py tests/unit/rewards/test_public_reward.py
make VENV=../../.venv lint
```

通过标准：Hidden 只使用 train-hidden；visible 列不影响其 executor 调用或分数；eval-hidden 注入零执行失败；Public/Hidden 共用公式无漂移。

---

### 步骤 5：建立 Rewards 公共 API 与 WP4-b Mock 集成测试

**目标文件**：

- `src/code_verifier/rewards/__init__.py`（新建）
- `tests/integration/test_wp4b_reward_pipeline.py`（新建）

**新增 / 修改的符号**：

```python
# src/code_verifier/rewards/__init__.py
from code_verifier.rewards.common import RewardContractError, compute_code_rewards
from code_verifier.rewards.hidden_reward import hidden_code_reward
from code_verifier.rewards.public_reward import public_code_reward

__all__ = [
    "RewardContractError",
    "compute_code_rewards",
    "hidden_code_reward",
    "public_code_reward",
]
```

**主要功能**：

- Rewards 包根只导出稳定公共 API；内部 helper 不导出。
- 集成测试不得启动真实 Piston；使用 WP3 `MockExecutor` + WP4-a verifier 验证完整路径。
- 构造最少以下批量场景：
  1. chat-style completion + visible tests 全通过；
  2. chat-style completion + selected tests 部分通过；
  3. raw string completion + timeout；
  4. invalid fenced format / missing function parser failure；
  5. sandbox error；
  6. executor 普通异常可使用专用 test double，确认 WP4-a fail-closed 后 reward 不为高分。
- Public 集成：
  - 输入模拟 Public training artifact 列；
  - Mock 调用只出现 `visible_tests`；
  - reward/component record 对齐。
- Hidden 集成：
  - 输入模拟 Hidden training artifact 列，合法包含 `visible_tests` 额外 kwargs；
  - Mock 调用只出现 `train_hidden_tests`；
  - visible sentinel 不影响 reward。
- 隔离集成：
  - 向 Public 注入 `train_hidden_tests` / `eval_hidden_tests`；向 Hidden 注入 `eval_hidden_tests`；全部在 executor call count 0 时失败。
- common component record 必须 `json.dumps(..., allow_nan=False)` 成功；records 中不得出现字符串哨兵 completion/code/test input/expected/stdout/stderr。
- 验证 reward 单调性和失败状态：全通过 > 部分 > 全失败；timeout 比同 pass rate 无 timeout 低 0.2；parse failure 为 -0.1；sandbox 不获得测试/可执行正分。

**配置 / CLI 变更**：无。

**测试方案**：

- 测试文件：`tests/integration/test_wp4b_reward_pipeline.py`
- 新增测试函数：
  - `test_wp4b_public_reward_chat_completion_visible_test_pipeline`。
  - `test_wp4b_hidden_reward_uses_train_hidden_and_ignores_visible_column`。
  - `test_wp4b_reward_failure_statuses_and_component_records_match_spec`。
  - `test_wp4b_training_reward_paths_reject_eval_hidden_before_execution`。
  - `test_wp4b_rewards_and_component_records_align_exactly_with_batch`。
  - `test_wp4b_component_records_are_finite_json_safe_and_payload_free`。
- 覆盖规格边界：§10.6 全项；§19.2 reward 函数批量调用；§20 WP4 全部 reward 验收。

**验证命令与通过标准**：

```bash
../../.venv/bin/python -m pytest tests/unit/rewards tests/integration/test_wp4b_reward_pipeline.py
make VENV=../../.venv lint
```

通过标准：Reward 定向 suite 0 failed、0 skipped；Public/Hidden source isolation 可由 Mock call records 直接证明；所有 rewards finite 且 batch 严格对齐；component records 无敏感 payload。

---

### 步骤 6：更新文档并完成 WP4 整体验收

**目标文件**：

- `README.md`（修改）
- `AGENTS.md`（修改）
- `ai-work/executor/WP4-executor.md`（执行过程中追加 WP4-b 实施/验证记录；同一 WP 沿用该文件）

**新增 / 修改的符号**：无 Python 符号。

**主要功能**：

- README 增加 WP4 Reward Layer：
  - Public/Hidden API 名称；
  - `compute_code_rewards()` 同时返回 reward 与 component records；
  - reward 公式和固定辅助值；
  - wrapper 需要调用方绑定 executor；
  - Open-R1 当前 chat completion 兼容，但正式 trainer 接入仍属于 WP7；
  - 明确 Public 只 visible、Hidden 只 train-hidden、eval-hidden 禁止；
  - 不宣称已有 GRPO 训练命令。
- AGENTS 项目结构增加 `rewards/{common,public_reward,hidden_reward}.py` 与 tests。
- AGENTS scope 更新为“WP0–WP4 已实现；WP5+ 未实现”，并保留：
  - Reward 只能经 verifier → executor；
  - Public/Hidden 共享 core；
  - eval-hidden 绝不能进入训练 reward；
  - 不允许把 WP7 adapter/GRPO 配置提前塞进 WP4。
- Executor 报告必须明确：
  - 本阶段未修改 YAML、CLI、Makefile、`pyproject.toml`、Open-R1、verification/execution/parser/data/training；
  - 新增 4 个 Reward 业务模块；
  - 实际执行测试数量和结果；
  - component record 字段；
  - WP4 整体是否达到交付，但不得自行修改 proceedings。

**配置 / CLI 变更**：无；必须在报告注明“无配置/依赖/CLI 变化”。

**测试方案**：

- Reward 定向 suite。
- Verification + Reward 联合定向 suite，确认 WP4-a 无回归。
- 全量 CPU tests。
- lint/type/format。
- CLI help 确认未新增训练/评测命令。
- 范围检查确认 `third_party/open-r1/**`、configs、training、execution、verification、parser、data 无净修改。

**验证命令与通过标准**：

```bash
make VENV=../../.venv lint
make VENV=../../.venv test
../../.venv/bin/python -m pytest \
  tests/unit/verification \
  tests/unit/rewards \
  tests/integration/test_wp4a_verifier_pipeline.py \
  tests/integration/test_wp4b_reward_pipeline.py
../../.venv/bin/python -m code_verifier.cli --help
```

通过标准：

- `make lint` 全绿；
- `make test` 全绿；仅既有真实 Piston tests 可按既有机制默认 skipped，不得新增 skip/xfail；
- Verification + Reward WP4 定向 suite：0 failed、0 skipped；
- CLI help 返回 0，命令集合仍无 WP5+/training reward 新命令；
- 无配置、依赖、上游 submodule 或其它模块越界变更；
- `ai-work/executor/WP4-executor.md` 已追加 WP4-b 真实执行结果；
- executor 未修改 `proceedings.md`。

## 6. 总体验收与测试计划

### 6.1 单元测试汇总

- `tests/unit/rewards/test_common.py`
  - batch 对齐、completion payload、公式、有限值、component record、sandbox/timeout/parser 失败。
- `tests/unit/rewards/test_public_reward.py`
  - Public visible-only、hidden/eval-hidden guard、executor binding。
- `tests/unit/rewards/test_hidden_reward.py`
  - Hidden train-hidden-only、visible ignored、eval-hidden guard、Public/Hidden 辅助项一致。

必须逐条覆盖规格 §10.6：

- [ ] 全部通过 reward 高于部分通过；
- [ ] 部分通过高于全部失败；
- [ ] timeout 有 -0.2 penalty；
- [ ] 解析失败有 -0.1 penalty；
- [ ] Public reward 不读取 hidden tests；
- [ ] Hidden reward 不读取 eval tests；
- [ ] batch 长度不一致抛异常；
- [ ] executor infrastructure error 不当成正确答案；
- [ ] reward 数量与 completion 数量严格一致；
- [ ] 所有 reward finite，无 NaN/Inf；
- [ ] Public/Hidden 公共辅助项完全一致。

### 6.2 集成测试

`tests/integration/test_wp4b_reward_pipeline.py` 必须覆盖：

- 当前固定 Open-R1 chat-style completion payload；
- raw string completion；
- MockExecutor 参数记录；
- Public artifact 形态；
- Hidden artifact 形态（含 visible 列但只使用 train-hidden）；
- eval-hidden 注入 fail-before-execution；
- passed / partial / wrong / timeout / parse / sandbox；
- reward + component record 一一对齐；
- JSON-safe、finite、payload-free component records。

### 6.3 数据泄漏检查

WP4-b 不改变 WP1 artifact 构造，但必须在 Reward 入口做第二道防线：

- Public wrapper：拒绝 `train_hidden_tests`、`eval_hidden_tests` 出现在 `kwargs`；
- Hidden wrapper：拒绝 `eval_hidden_tests`；
- common core：只有一个已选择的 tests 列，无访问其它 layer 的 API；
- component record：不保存 tests 或 metadata；
- 集成测试用独特 sentinel 证明错误测试层从未进入 `MockExecutor.calls`。

### 6.4 WP4 最终通过标准

- [ ] WP4-a verifier 仍全部通过，无回归。
- [ ] `reward common` 已实现。
- [ ] `public_code_reward()` 已实现且只使用 visible tests。
- [ ] `hidden_code_reward()` 已实现且只使用 train-hidden tests。
- [ ] `compute_code_rewards()` 参数顺序/返回形态符合 §10.5。
- [ ] 两个 wrapper 参数名/顺序/返回形态符合 §10.5。
- [ ] Public/Hidden 只在测试来源与 component `mode` 标签上不同；公式、辅助项、失败解释完全相同。
- [ ] eval hidden 无法通过已知 training reward 字段进入 Public/Hidden 计分路径。
- [ ] batch 不一致在执行前失败，无 zip 静默截断。
- [ ] reward 数量与 completion 数量完全一致。
- [ ] component record 数量与 reward 数量完全一致。
- [ ] 所有 reward/component 数值有限。
- [ ] parser failure、timeout、sandbox/infrastructure failure 符合 §10 / WP4-a 状态合同。
- [ ] component records 可 JSON 序列化且不含敏感 payload / execution_result。
- [ ] `make lint` 全绿。
- [ ] `make test` 全绿，无新增 skip/xfail。
- [ ] WP4 定向 suite 0 failed、0 skipped。
- [ ] 不修改 `third_party/open-r1/**`、配置、依赖或后续 WP 功能。
- [ ] reviewer 独立通过并合并 `feat/wp4-b` 后，才把 proceedings 中 WP4-a 子阶段记录整合/扩展为 WP4 整体完成记录。

## 7. 风险与注意事项

- **TRL/Open-R1 completion 形态漂移**：本计划只兼容已从固定 commit 验证的 chat-style `completion[-1]["content"]` 与直接字符串。上游若升级，必须先通过 adapter/测试确认，不能静默猜测新形态。
- **batch 静默截断**：Python `zip` 会掩盖 dataset 列长度错误；核心必须显式比较长度并用索引遍历。
- **Public/Hidden 漂移**：复制两套公式很容易让辅助项逐渐不同；公式只能存在于 `common.py`。
- **eval-hidden 泄漏**：即使 WP1 artifact 已禁止，Reward Layer仍必须拒绝已知 eval-hidden 字段，形成 defense in depth。
- **Hidden artifact 的 visible 列**：Hidden record 合法含 `visible_tests`，因此不能简单拒绝；必须证明它被忽略而非参与混合计分。
- **基础设施错误伪高分**：executor exception / `SANDBOX_ERROR` 不得得到 0.1 executable 或测试正分。
- **invalid-format 与输入合同混淆**：模型输出为空、无 fence、缺目标函数属于 parser failure → -0.1；而 callback payload 结构错误、metadata/tests 列损坏属于调用合同错误 → 抛异常。两者不得混为同一 reward。
- **timeout 部分通过**：timeout penalty 不能丢掉已真实通过的测试分量；总分必须按公式直接相加。
- **component log 泄漏**：component records 只保存标量/状态；不得为调试方便加入 completion、code、tests、metadata、stdout/stderr。
- **executor 生命周期**：WP4-b 只接受注入对象，不创建全局 Piston/Mock；WP7 决定每 worker/训练进程如何创建和绑定 executor。
- **范围蔓延**：不要在本阶段修改 Open-R1 reward registry、GRPO config、trainer、W&B 或 evaluation。

## 8. 后续 WP7 接入约束

WP4-b 完成后，WP7 应复用本阶段 API，而不是重写 reward：

- trainer/adapter 负责构造并绑定合适的 `CodeExecutor`；
- Public run 将 dataset `visible_tests` 列传给 `public_code_reward()`；
- Hidden run 将 `train_hidden_tests` 列传给 `hidden_code_reward()`；
- rollout/reward logging 应消费 `compute_code_rewards()` 的 component records 或等价的 common-core hook；
- WP7 必须保持 C/D 除测试来源外配置一致；
- WP7 仍不得把 `eval_hidden_tests` 加进训练 dataset 或 reward callback kwargs。

本阶段不得提前实现上述训练集成。

## 9. 关联文档索引

- `PROJECT_SPEC_Open-R1_CodeVerifier.md`
  - §6.2：Verification / Reward / Training 模块边界；
  - §10.1–§10.6：reward 原则、公式、API、batch 对齐与单元测试；
  - §12.3：后续训练必须记录总 reward 与各分量；
  - §16：`rewards/{common,public_reward,hidden_reward}.py` 目标结构；
  - §19.1：Reward 单元测试；
  - §19.2：reward 函数批量集成测试；
  - §20 WP4：目标、交付、验收；
  - §29：Public-RLVR vs Hidden-RLVR 核心对照与非目标。
- `proceedings.md`
  - WP4-a：Verification Layer 已完成；Reward Layer 明确待 WP4-b。
- `ai-work/reviewer/WP4-review.md`
  - R2：WP4-a 最终通过；parser taxonomy 与 sandbox fail-closed 合同已闭合。
- `src/code_verifier/verification/result_types.py`
  - Reward 所依赖的 `VerificationResult` 状态与有限 pass-rate 合同。
- `src/code_verifier/verification/verifier.py`
  - `verify_completion()` 唯一 parser/executor orchestration 入口。
- `src/code_verifier/data/leakage_checks.py`
  - Public/Hidden training artifact 字段白名单和 eval-hidden 禁止规则。
- `third_party/open-r1/src/open_r1/grpo.py`（只读参考）
  - 当前固定 commit 的 chat conversation 构造与 `GRPOTrainer` reward callback 上下文。
- `third_party/open-r1/src/open_r1/rewards.py`（只读参考）
  - 当前固定 commit reward functions 的 chat-style completion 读取方式；不得修改。
