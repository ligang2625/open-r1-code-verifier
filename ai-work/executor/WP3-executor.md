# WP3-c Executor 执行报告

- **依据计划**：`ai-work/planner/WP3-c-plan.md`
- **目标阶段**：WP3：安全执行器（子阶段 c：批量并发、可选缓存、执行 CLI 与 WP3 收口）
- **执行分支**：`feat/wp3c`
- **独立 worktree**：`.worktrees/wp3c`
- **执行状态**：计划 6 个步骤已全部实现并通过计划要求的静态、默认、真实 Piston 与 CLI smoke 验收。WP3 代码交付已完整实现；仍需 `wp-plan-reviewer` 独立复审、合并并更新 `proceedings.md` 后，才可在主分支正式登记 WP3 完成。

> 本文件此前对应 `WP3-b-plan.md`。当前 plan 已切换为 `WP3-c-plan.md`，因此按照 executor skill 的阶段重置规则清空并重写。本报告未修改 reviewer 报告或 `proceedings.md`。

## 1. 分步交付与提交

### 步骤 1：ExecutionResult 反序列化与确定性 executor version

提交：

```text
b1d87d7  feat: add execution result parsing and versioning
```

完成内容：

- 新增 `execution_result_from_mapping()`：
  - 要求顶层与 per-test 字段精确匹配；
  - 严格恢复 `ExecutionStatus`；
  - 调用既有 result contract 校验所有计数、状态、pass rate、runtime 和 test-result invariants；
  - 返回独立 `test_results` list；
  - malformed mapping 统一为脱敏 `ExecutionContractError`。
- 新增版本常量：
  - `PYTHON_HARNESS_PROTOCOL_VERSION = "trusted-parent-v1"`；
  - `PISTON_EXECUTOR_IMPLEMENTATION_VERSION = "piston-executor-v1"`。
- 新增 `piston_executor_version()`：
  - 对 implementation、harness protocol 和全部 Piston config 字段构造 canonical JSON；
  - float 使用 `.hex()`；
  - 返回 `piston:<64 lowercase hex>`。
- 更新 execution 公共导出。

专项验证：

```text
PYTHONPATH=src .venv/bin/python -m pytest \
  tests/unit/execution/test_base.py \
  tests/unit/execution/test_piston.py \
  -k "from_mapping or executor_version"
→ 12 passed, 116 deselected
```

### 步骤 2：安全 SQLite execution cache

提交：

```text
a9eb780  feat: add secure execution cache
```

新增：

- `src/code_verifier/execution/cache.py`
- `tests/unit/execution/test_cache.py`

实现：

- `ExecutionTestLayer`、`ExecutionCacheKey`、`ExecutionCache` Protocol、`ExecutionCacheError`。
- cache key 包含：
  - exact code SHA-256；
  - problem ID；
  - visible/train-hidden/eval-hidden layer；
  - order-sensitive canonical tests hash；
  - deterministic executor version；
  - function name；
  - timeout float hex；
  - memory limit。
- versioned SQLite schema，仅保存 key hashes/metadata 与 validated result JSON；不保存 raw code/tests。
- 新文件以 `0600` 创建；拒绝 symlink、非 regular file 和已有宽权限文件。
- schema/version/key/result 损坏均明确失败，不解释为 cache miss。
- `SANDBOX_ERROR` 禁止写入 cache。
- context manager、commit/rollback、idempotent close。

专项验证：

```text
PYTHONPATH=src .venv/bin/python -m pytest tests/unit/execution/test_cache.py
→ 12 passed
```

### 步骤 3：有界 batch 并发与 cache policy

提交：

```text
a879931  feat: add bounded batch execution
```

新增：

- `configs/execution/batch-local.yaml`
- `src/code_verifier/execution/batch.py`
- `tests/unit/execution/test_batch.py`

实现：

- `BatchExecutorConfig`、`BatchExecutionConfig`、request/item/result dataclasses。
- `ExecutionCacheMode`：`disabled`、`read_only`、`read_write`。
- `ExecutionWorkloadMode`：`evaluation`、`training`。
- strict request/config mapping 与 JSON-safe result mapping。
- `max_concurrency` 范围固定为 1–64。
- 所有 request 与重复 request ID 在 cache/factory/thread side effect 前完整校验。
- cache get/put 均在主线程；worker 不共享 SQLite connection。
- 每个 cache miss 调用 factory 创建独立 executor。
- futures 可乱序完成，但结果按原输入索引回填。
- worker 普通异常转换为脱敏 `SANDBOX_ERROR`；cache infrastructure error 不转换为模型结果。
- disabled/read-only/read-write 行为完整实现。
- training cache 默认拒绝，只有显式 `allow_training_cache=true` 才允许。
- batch runtime 使用 wall-clock，而不是 per-item runtime 求和。

专项验证：

```text
PYTHONPATH=src .venv/bin/python -m pytest tests/unit/execution/test_batch.py
→ 16 passed
```

### 步骤 4：execute-batch CLI 与原子脱敏 artifacts

提交：

```text
cb14d15  feat: add batch execution cli
```

新增/修改：

- `src/code_verifier/cli.py`
- `tests/unit/test_cli.py`
- `tests/fixtures/wp3c/batch_requests.jsonl`

实现：

- 新命令 `execute-batch`，保留公共 `--config/--seed/--output-dir/--log-level`，增加：
  - `--requests`；
  - `--workload-mode`；
  - `--max-concurrency`；
  - `--cache-mode`；
  - `--cache-path`。
- strict UTF-8 JSONL：至少一行、禁止 blank line、递归 duplicate-key-safe parse、固定 line-number 错误，不回显原行。
- YAML batch config 可由 CLI override，但仍执行范围校验。
- disabled cache 禁止 path；enabled cache 要求 path；cache path 禁止位于 output directory 内。
- 执行前只做一次 Piston runtime validation，并计算 deterministic executor version。
- `output_dir` 必须不存在；同父目录 temporary directory 完整写入后原子 rename。
- artifacts：
  - `results.jsonl`：输入顺序、仅 item metadata + result；
  - `summary.json`：version、modes、concurrency、total、cache hits、status counts、runtime、results basename。
- artifacts 不包含 code/tests/input/expected/full cache key。
- exit 0：模型 passed/wrong/syntax/runtime/resource 等结构化结果；exit 1：至少一个 `SANDBOX_ERROR`；exit 2：config/input/cache/runtime/I/O infrastructure failure。
- fixture 固定 4 条，覆盖三个 test layer、2 correct、1 wrong、1 runtime，不使用真实隐藏实验数据。

专项验证：

```text
PYTHONPATH=src .venv/bin/python -m pytest tests/unit/test_cli.py \
  -k "execute_batch or load_batch"
→ 11 passed, 21 deselected

PYTHONPATH=src .venv/bin/python -m code_verifier.cli execute-batch --help
→ exit 0，全部参数存在
```

### 步骤 5：Mock 与真实 Piston batch/cache 集成验收

提交：

```text
56cb12a  test: add batch and cache integration acceptance
```

新增/修改：

- `tests/integration/test_wp3c_batch_execution.py`
- `Makefile`

默认集成覆盖：

- fixed fake executor 的输入顺序、并发 peak、first-run miss/second-run hit；
- SQLite cache round trip；
- CLI → real BatchExecutor → artifacts 闭环；
- artifacts 不包含 fixture code/tests。

真实 Piston 覆盖：

- correct、wrong answer、runtime error、timeout；
- 多个请求在 `max_concurrency > 1` 配置下完成；
- read-write 首轮 `cache_hits=0`；
- 同 cache read-only 第二轮所有非-sandbox item 完整命中，result mappings 与首轮一致；
- artificial transport failure 得到 `SANDBOX_ERROR` 且不写 cache；
- 同 key 恢复真实 Piston 后重新执行并通过；
- 再次 read-only 时命中恢复后的 valid entry；
- batch 与 failure 后 WP3-b health smoke 通过。

`make test-piston` 现同时运行 WP3-b 与 WP3-c piston-marked tests。

### 步骤 6：文档与 WP3 最终收口

提交：

```text
35cda12  docs: document complete wp3 execution workflow
```

更新：

- `README.md`
  - 状态更新为 WP3 execution layer 实现完成；
  - 明确 WP4 rewards/verifier、training、evaluation 未实现；
  - 增加 Batch API、SQLite cache、evaluation/training policy 示例；
  - 增加 execute-batch CLI 与 artifact layout；
  - 记录 cache key 不存 raw code/tests，但 result stdout/stderr 仍属敏感 artifact；
  - 当前性能边界为单机线程池、本地 SQLite、每测试一个 Piston job。
- `AGENTS.md`
  - 增加 cache/batch 模块、config、unit/integration tests；
  - 当前范围更新为 WP0–WP3；
  - 增加 version invalidation、cache key 完整性、training cache 和真实 batch 验收规则；
  - 明确未经后续 plan 不实现 WP4。
- `docs/piston-local.md`
  - 增加 batch worker capacity 操作说明，从 concurrency=1 逐步提高；
  - 增加 cache 0600、敏感性、备份/删除、schema/version/corruption fail-closed 说明；
  - 明确 cache 不替代 sandbox。

## 2. 最终实际验收结果

### 静态检查

```text
make lint
→ Ruff check: All checks passed
→ Ruff format: 47 files already formatted
→ strict Mypy: Success, no issues found in 47 source files
```

### 默认全量测试

```text
PYTHONPATH=src make test
→ 386 passed, 3 skipped
```

三个 skip 均为未显式启用的真实 Piston tests：WP3-b module-level 1 项，以及 WP3-c 两项 piston-marked tests。默认测试未连接 Piston，符合计划。

### 显式真实 Piston 总验收

```text
PYTHONPATH=src make test-piston \
  PISTON_CONFIG=configs/execution/piston-local.yaml
→ 9 passed, 2 deselected, 0 failed, 0 skipped
```

两项 deselected 是 WP3-c 文件中的默认 fake/CLI integration tests，不带 `piston` marker；全部 9 个真实选中测试通过。

### CLI help

```text
PYTHONPATH=src .venv/bin/code-verifier --help
→ exit 0，列出 execute-batch

PYTHONPATH=src .venv/bin/code-verifier execute-batch --help
→ exit 0，列出全部 batch/cache/common 参数
```

### 真实 execute-batch smoke

```text
rm -rf outputs/wp3c-smoke

PYTHONPATH=src .venv/bin/code-verifier execute-batch \
  --config configs/execution/batch-local.yaml \
  --requests tests/fixtures/wp3c/batch_requests.jsonl \
  --workload-mode evaluation \
  --output-dir outputs/wp3c-smoke \
  --log-level INFO
→ exit 0
→ executed 4 requests (cache_hits=0)
```

Summary 验证：

```text
summary.json total_requests
→ 4
```

额外实际探针：

```text
results.jsonl lines == 4
request_id order == fixture request_id order
fixture code/tests not present in results.jsonl
→ order-and-redaction-ok
```

验收后已删除 `outputs/wp3c-smoke`，未提交运行产物。

## 3. 配置、依赖与安全影响

- 新增 `configs/execution/batch-local.yaml`。
- 未新增 Python package 依赖；batch、cache、CLI 均使用标准库。
- SQLite cache 为可选本地 artifact；默认 YAML cache mode 为 `disabled`。
- cache file 只在显式启用时创建，权限为 0600。
- 未配置公共 Piston endpoint、token 或远程账户。
- 未修改 `third_party/open-r1/**`；最终 diff 为空。
- 未修改 `src/code_verifier/execution/base.py` 的公开 `CodeExecutor.execute()` 签名。
- 未修改 `MockExecutor` 非执行语义。
- 未修改 reviewer 文件或 `proceedings.md`。

## 4. 环境与计划偏离

- 受工具工作区边界限制，worktree 位于主仓库内部 `.worktrees/wp3c`，但仍为独立 `feat/wp3c` 分支，所有实现与提交均在该 worktree 完成。
- worktree 临时复用主工作区 `.venv` 符号链接；由于 editable install 指向主工作区，pytest/CLI 命令显式使用 `PYTHONPATH=src`，确保加载当前 worktree 源码。该链接不提交。
- 第一次 `git submodule update --init --recursive` 因远程操作超时；随后使用主工作区已有固定 checkout 作为本地 `--reference` 完成只读 submodule 初始化，仍检出仓库既有 pin，未修改 submodule 内容或 pin。
- 计划示例使用 `.venv/bin/...`；本报告命令增加 `PYTHONPATH=src` 仅用于 worktree editable-install 路径隔离，不改变功能或验收标准。
- 无接口、cache key 字段、并发上限、测试预期、安全边界或阶段范围偏离。

## 5. 已知限制

- BatchExecutor 是单机标准库线程池，不是 distributed scheduler。
- SQLite cache 是单进程主线程读写设计；不承诺跨主机共享或高写并发。
- 每个 request 内仍保持每测试一个独立 Piston job，吞吐受本地 Piston/Docker/cgroup capacity 限制。
- Cache result 可能包含 bounded candidate stdout/stderr，必须作为敏感 artifact 管理。
- Training cache 即使显式允许，也需要实验层记录 resolved policy；WP3 不实现 reward 或 training orchestration。
- WP4 parser/executor verifier 编排与 visible/hidden reward 不在本计划范围。

## 6. Reviewer 下一轮重点

独立复审应至少重新验证：

1. 全量 request validation 在 cache/factory/thread side effect 前完成；
2. worker concurrency 上限、独立 executor 与输入顺序回填；
3. cache key 逐字段完整性和 deterministic version invalidation；
4. training cache guard；
5. SQLite symlink/0600/schema/version/corruption fail-closed 行为；
6. CLI strict JSONL、错误脱敏、output atomicity 和 exit 0/1/2；
7. `SANDBOX_ERROR` 不缓存；
8. WP3-b trusted-parent/Piston/network/filesystem/PID/resource 边界无回归；
9. 默认 `make test` 与显式 `make test-piston` 的 skip/selection 行为；
10. `third_party/open-r1` 无修改。

审查通过后，由 reviewer 合并 `feat/wp3c`，向 `proceedings.md` 追加 WP3-c 记录并将 WP3 整体登记为完成。Executor 不执行 push、merge 或 proceedings 更新。
