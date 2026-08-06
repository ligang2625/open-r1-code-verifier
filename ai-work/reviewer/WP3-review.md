# WP3-c 独立审查报告

- **计划文件**：`ai-work/planner/WP3-c-plan.md`
- **executor 报告**：`ai-work/executor/WP3-executor.md`
- **审查轮次**：R1
- **审查日期**：2026-08-06
- **审查分支 / worktree**：`feat/wp3c` / `.worktrees/wp3c`
- **审查基线提交**：`5fa39c342eff2557f6794681749761501a898ba6`
- **审查方式**：逐步骤计划完成度核验、源码与测试阅读、独立静态检查、默认回归、真实 Piston 总验收、CLI smoke，以及缓存策略、Unicode、异常合同和副作用顺序的额外对抗性探针

> 同一报告文件此前记录的是 `WP3-b-plan.md`。当前计划已切换为 `WP3-c-plan.md`，按照 reviewer skill 的阶段重置规则，本文件从 WP3-c R1 重新开始记录。

## 1. 审查范围与基准

本轮审查 WP3 的最终子阶段：批量并发、可选缓存、`execute-batch` CLI 与 WP3 整体收口。审查基准包括：

- `PROJECT_SPEC_Open-R1_CodeVerifier.md` §6.2、§8.3–§8.5、§17、§19、§20、§21；
- `ai-work/planner/WP3-c-plan.md` 的 6 个实施步骤、总体验收清单与高风险审查项；
- `skills/wp-plan-reviewer/references/review-checklist.md` 的通用和执行器审查清单。

审查期间未修改 `src/`、`tests/`、`third_party/open-r1/`、项目配置或 `proceedings.md`。CLI smoke 生成的 `outputs/wp3c-smoke` 已在审查结束前删除。

## 2. 计划完成度核验

| 计划步骤 / 交付项 | 计划要求 | 状态 | 证据 |
|---|---|---|---|
| 步骤 1：ExecutionResult 反序列化与 executor version | `execution_result_from_mapping()`、harness protocol version、确定性 Piston version、公共导出 | **已完成** | `base.py:206-270`、`harness.py:21`、`piston.py:213-229`、`execution/__init__.py:3-88`；专项和全量测试通过。 |
| 步骤 2：稳定 cache key 与安全 SQLite cache | 规格字段完整 key、0600、拒绝 symlink/宽权限、损坏 fail-closed、不缓存 `SANDBOX_ERROR` | **部分完成** | 正常 key/权限/结构损坏路径由 `cache.py` 和 12 项单测覆盖；但读取路径允许合法结构的 `SANDBOX_ERROR` 命中并被 batch 复用，且 UTF-8 不可编码字符串可泄漏裸 `UnicodeEncodeError`。详见 P1、P3。 |
| 步骤 3：batch 类型、配置和有限并发 | 全量预校验、1–64 并发、独立 executor、输入顺序、cache policy、training guard、脱敏异常 | **部分完成** | `batch.py:377-517` 的并发、顺序、独立 executor 和普通 worker 异常行为通过测试；但 cache hit 未拒绝 `SANDBOX_ERROR`，公共 mapping 对极大整数 runtime 泄漏 `OverflowError`。详见 P1、P4。 |
| 步骤 4：`execute-batch` CLI 与原子输出 | strict JSONL、override、cache/path 检查、执行前 runtime validation、原子 artifact、退出码 0/1/2、零敏感 payload | **部分完成** | 常规 CLI、help、artifact、退出码和原子失败清理通过；但非法 training-cache policy 会在失败前访问 Piston 并创建 cache 文件，违反“策略全量预校验、零执行副作用”。详见 P2。escaped lone surrogate 也未在 JSONL/request 边界统一拒绝，受 P3 影响。 |
| 步骤 5：Mock 与真实 Piston batch/cache 集成 | 默认 fake/CLI 集成，真实 batch/cache、sandbox error 不写 cache、服务恢复，Makefile 同时运行 WP3-b/c | **常规路径已完成** | 默认回归 386 passed/3 skipped；真实 Piston 9 passed/0 skipped；Makefile 同时选择 WP3-b 与 WP3-c。现有测试只覆盖“miss 产生的 sandbox error 不写入”，未覆盖“cache get 返回 sandbox error 不得复用”。 |
| 步骤 6：文档与 WP3 最终收口 | README、AGENTS、Piston 文档更新，记录单机限制、cache 敏感性和 WP4 边界 | **已完成** | README 声明 WP3 execution layer 已实现并保留 WP4 边界；AGENTS 和 `docs/piston-local.md` 包含 batch/cache/version/training policy 与运维限制。由于代码验收未通过，WP3 尚不能在 proceedings 中登记整体完成。 |
| 新增文件清单 | batch YAML、cache/batch 模块、两类单测、集成测试、fixture | **已完成** | 计划列出的新增文件均存在。 |
| 修改文件清单 | base/harness/piston/init/CLI/tests/Makefile/docs | **已完成** | 计划列出的修改文件均有对应实现；未发现 WP4 reward/training 范围蔓延。 |
| 明确不修改项 | §8.3 字段/Protocol、Mock 语义、数据/解析/训练、依赖列表、上游 | **通过** | `CodeExecutor.execute()` 签名未变；Mock 非执行语义未变；未新增 package 依赖；`third_party/open-r1` commit 仍为 `1416fa0cf21595d2083b399a2a0bbddd7f6e9563`。 |

## 3. 交付与验收核验

| 验收项 | 状态 | 证据 |
|---|---|---|
| §8.3 公共接口保持不变 | 通过 | `base.py:14-64` 与规格一致。 |
| MockExecutor 非执行语义保持不变 | 通过 | 既有 Mock 测试全绿；execution 宿主源码未新增候选 `exec`/`eval` 路径。 |
| WP3-b Piston 安全边界无回归 | 通过 | 显式真实 Piston 总验收 9 passed，其中 WP3-b 7 项全部通过。 |
| batch 有限并发、独立 executor、输入顺序 | 通过 | `batch.py:449-476`；barrier/counter、顺序和 factory-per-miss 单测通过。 |
| YAML/CLI concurrency override 严格限制 1–64 | 通过 | `batch.py:282-294`、`cli.py:225-242`；相关单测通过。 |
| cache mode 和 training 默认禁用 | **未通过完整验收** | `BatchExecutor` 内部 guard 在 cache/factory/thread 前执行；但 CLI 在 guard 之前已调用 runtime probe 并打开 cache。详见 P2。 |
| cache key 包含规格字段和 function/timeout/memory | 通过（正常 UTF-8 输入） | `cache.py:83-109`、`112-137`；逐字段 digest 变化测试通过。 |
| cache 不保存 raw code/tests | 通过（正常路径） | 数据库 sentinel 单测通过；key 只保存 hash 和元数据。result stdout/stderr 仍按文档作为敏感 artifact。 |
| `SANDBOX_ERROR` 不缓存且不复用 | **未通过** | put/miss 路径拒绝或跳过写入，但 get/hit 路径接受并复用 `SANDBOX_ERROR`。详见 P1。 |
| cache corruption/version mismatch fail-closed | 部分通过 | malformed schema/key/result 会抛 `ExecutionCacheError`；但合法结构的 `SANDBOX_ERROR` result 可被读取并复用，违反状态级 fail-closed policy。 |
| strict UTF-8 / 稳定异常合同 | **未通过** | lone surrogate 被 request validation 接受，随后在 code hash、tests hash、SQLite write 或 transport encoding 处产生模式依赖结果和裸 `UnicodeEncodeError`。详见 P3。 |
| batch mapping 可稳定 JSON 序列化 | **未通过完整边界** | 正常结果可序列化；极大有限整数 `runtime_ms` 在 `float()` 转换处泄漏裸 `OverflowError`。详见 P4。 |
| CLI 原子脱敏 artifact 与退出码 | 常规路径通过 | smoke exit 0；summary total_requests=4；results 4 行且顺序正确；单测覆盖 existing output/partial write/exit 0/1/2。 |
| 默认测试不连接 Piston | 通过 | 386 passed，3 个真实 Piston tests 按设计 skipped。 |
| 显式 Piston 总验收无失败无 skip | 通过 | 9 passed，2 个非-piston tests deselected，0 failed，0 skipped。 |
| WP3 §20 全部交付和验收可登记完成 | **未通过** | 缓存错误复用、策略副作用和公共异常合同仍有主要缺陷，不能登记 WP3 整体完成。 |

## 4. executor 报告声明核验

| executor 声明 | 状态 | 核验结果 |
|---|---|---|
| 6 个实施步骤和目标文件均已实现 | 部分核实 | 文件与常规功能均存在，但步骤 2–4 的明确安全/合同要求存在缺口。 |
| `make lint`、默认测试、真实 Piston、CLI smoke 通过 | 核实通过（环境路径有差异） | 使用主仓库 VENV 与 `PYTHONPATH=src` 独立复现：lint 全绿、386 passed/3 skipped、Piston 9 passed、CLI 4 requests。当前 worktree 的 `.venv` 已不存在，原样 `make lint`/`make test` 为 Error 127。 |
| `SANDBOX_ERROR` 禁止缓存 | 写入路径核实；读取复用声明不成立 | `SQLiteExecutionCache.put()` 和 read-write miss 均不写 sandbox error；但 cache get 返回的 sandbox result 会被标记为 hit 并直接返回。 |
| training cache 默认拒绝且零执行副作用 | **与事实不符（CLI 路径）** | CLI 会先 `validate_runtime()` 和创建 cache，再由 `execute_batch()` 抛 training opt-in 错误。 |
| 所有错误稳定脱敏并归一 | **与事实不符** | Unicode cache/hash/write 边界和极大 batch runtime mapping 分别泄漏 `UnicodeEncodeError`、`OverflowError`。 |
| 无接口、cache key、并发、安全边界或范围偏离 | **与事实不符** | cache error reuse 和 CLI prevalidation 顺序偏离计划明确决策与最终验收清单。 |
| `third_party/open-r1` 未修改 | 核实通过 | 固定 commit 与既有 pin 一致。 |

## 5. 问题清单

### P1 — 主要：cache get 可复用 `SANDBOX_ERROR`，违反基础设施错误不得缓存/复用的硬性策略

- **位置**：
  - `src/code_verifier/execution/cache.py:230-262`：get 只做结构合同校验，不拒绝 `ExecutionStatus.SANDBOX_ERROR`；
  - `src/code_verifier/execution/cache.py:268-287`：put 明确拒绝 sandbox error，读写策略不对称；
  - `src/code_verifier/execution/batch.py:428-447`：任何 cache hit 都直接构造 `cache_hit=True` item，未检查 status。
- **独立证据 1（Protocol cache）**：固定 cache 返回合法 `SANDBOX_ERROR`，factory 可返回 PASSED，但实际 batch 输出：

  ```text
  cache_hits=1 cache_hit=True status=sandbox_error
  ```

  executor 未被调用。
- **独立证据 2（SQLite）**：将已有 entry 的 `result_json` 修改为结构合法的 sandbox result 后，`SQLiteExecutionCache.get()` 返回：

  ```text
  sandbox_error
  ```

- **依据**：计划 §3.4 决策 13、步骤 2、步骤 3、步骤 5 与最终清单均要求 `SANDBOX_ERROR` 不缓存、不复用；规格 §8.4 要求记录沙箱错误且不得错误归因。
- **影响**：一次基础设施故障可被已有/损坏/自定义 cache 持久复用，后续服务恢复后仍不重新执行，破坏 recovery 语义和 cache 正确性。
- **建议**：
  1. `SQLiteExecutionCache.get()` 对 sandbox result 抛固定 `ExecutionCacheError`；
  2. `BatchExecutor` 在 cache boundary 再做防御性检查，遇到 sandbox hit 作为 cache infrastructure error 失败，不能当作 miss 静默忽略，也不能复用；
  3. 新增 SQLite 注入和自定义 cache 回归测试，断言 factory 不应被 sandbox cache hit 绕过。

### P2 — 主要：CLI 在非法 training-cache policy 失败前访问 Piston 并创建 cache 文件

- **位置**：
  - `src/code_verifier/cli.py:245-280`：完成 mode/path 检查后立即创建 Piston probe、调用 `validate_runtime()` 并打开 SQLite cache；
  - `src/code_verifier/execution/batch.py:419-424`：training opt-in guard 直到 `execute_batch()` 才执行。
- **独立探针**：YAML `allow_training_cache=false`，CLI override `cache_mode=read_only`、`workload_mode=training`，使用计数 fake boundary：

  ```text
  exit 2
  seen ['piston-init', 'runtime-network', ('cache-open', False), 'cache-close']
  cache_exists True
  error: training cache requires explicit opt-in
  ```

- **依据**：计划 §3.4 决策 4 要求所有请求、配置和缓存策略在调用 executor/cache/thread 前全量预校验，非法 batch 零执行副作用；决策 9 要求训练缓存未显式允许时执行前失败。
- **影响**：无效配置仍产生网络访问和本地持久文件，违反可预测性与 fail-fast 安全边界；在 Piston 不可用时，用户甚至可能先得到 runtime error，而不是实际的 policy error。
- **建议**：在 `_execute_batch()` runtime probe/cache open 之前验证 `workload_mode`、resolved cache mode 和 `allow_training_cache`；最好提取共享 policy validator，供 CLI 和 `BatchExecutor.execute_batch()` 同时调用。新增测试断言 Piston constructor/runtime、cache constructor、factory 均为零调用且 cache path 不存在。

### P3 — 主要：UTF-8 不可编码字符串未在合同边界拒绝，导致 cache mode 依赖的错误归因和裸 `UnicodeEncodeError`

- **位置**：
  - `src/code_verifier/execution/base.py:88-120`：code 和 JSON string 只检查类型/非空，未检查 UTF-8 可编码性；
  - `src/code_verifier/execution/cache.py:95-108,127-137`：code/tests/key canonical text 在后续 UTF-8 encode 时可失败；
  - `src/code_verifier/execution/cache.py:268-287`：SQLite 参数编码的 `UnicodeEncodeError` 未归一为 `ExecutionCacheError`；
  - `src/code_verifier/execution/piston.py:121-124`：request body encode 的 `UnicodeEncodeError` 未转换为 `PistonTransportError`，随后单请求层将其误记为 transport sandbox error。
- **独立证据**：含 lone surrogate `\ud800` 的非空 code：

  ```text
  validate_execution_request → accepted
  cache mode read_only → UnicodeEncodeError: surrogates not allowed
  cache mode disabled + real PistonExecutor → sandbox_error / piston transport failed
  ```

  合法 `ExecutionResult` 的 stdout 含 lone surrogate 时：

  ```text
  SQLiteExecutionCache.put → UnicodeEncodeError: surrogates not allowed
  ```

- **依据**：计划要求 exact UTF-8 code hash、strict UTF-8 JSONL、全量预校验、稳定脱敏错误；同一个非法请求不应因 cache mode 改变公共结果类别。
- **影响**：公共 batch API 可泄漏未处理内置异常；同一请求在缓存关闭时被错误归因成模型/沙箱失败，在缓存开启时变成基础设施 traceback，破坏缓存透明性和错误分类。
- **建议**：
  1. 在公共 execution request/result 字符串边界递归验证 UTF-8 可编码性，统一抛脱敏 `ExecutionContractError`；至少覆盖 code、request/problem ID、tests 中字符串和 stdout/stderr；
  2. `_canonical_json`、digest、SQLite get/put 和 transport encoding仍应防御性捕获 `UnicodeEncodeError` 并归一为对应 cache/transport error；
  3. 增加 escaped lone-surrogate JSONL、code/test/problem ID、cached result stdout/stderr 回归测试，并断言所有 cache mode 行为一致且零执行副作用。

### P4 — 主要：`batch_execution_result_to_mapping()` 对极大整数 runtime 泄漏裸 `OverflowError`

- **位置**：`src/code_verifier/execution/batch.py:256-260`
- **独立探针**：构造 `runtime_ms=10**1000` 的 `BatchExecutionResult` 后调用 mapping：

  ```text
  OverflowError int too large to convert to float
  ```

- **依据**：WP3-a 已确立非法数值必须归一为 `ExecutionContractError`；WP3-c 横切规则要求严格类型和有限数校验，batch mapping 是公开 JSON-safe serialization boundary。
- **影响**：调用方无法只处理公开合同异常，畸形公共结果可产生未处理 traceback。
- **建议**：使用与 `base._is_finite_number()` 等价的 overflow-safe 检查，或在 `float()` 周围捕获 `OverflowError` 并统一抛 `ExecutionContractError`；增加最大有限值、超大 int、NaN/Inf/bool 回归测试。

## 6. 独立测试结果

### 6.1 原样 worktree 命令

```text
make lint
→ 失败：.venv/bin/python 不存在，Error 127

make test
→ 失败：.venv/bin/python 不存在，Error 127
```

该差异是当前 worktree 环境状态；使用主仓库固定虚拟环境并设置 `PYTHONPATH=src` 后，检查针对本 worktree 源码执行。

### 6.2 静态检查与默认回归

```text
make lint VENV=/home/dzy/open-r1-code-verifier/.venv
→ Ruff check: All checks passed
→ Ruff format: 47 files already formatted
→ strict Mypy: no issues found in 47 source files

PYTHONPATH=src make test VENV=/home/dzy/open-r1-code-verifier/.venv
→ 386 passed, 3 skipped
```

三个 skip 均为未显式启用的真实 Piston tests，默认测试未连接服务。

### 6.3 真实 Piston 总验收

```text
PYTHONPATH=src make test-piston \
  VENV=/home/dzy/open-r1-code-verifier/.venv \
  PISTON_CONFIG=configs/execution/piston-local.yaml
→ 9 passed, 2 deselected, 0 failed, 0 skipped
```

WP3-b 安全套件和 WP3-c batch/cache 两项真实测试均通过。

### 6.4 CLI smoke

```text
code-verifier --help
→ exit 0，列出 execute-batch

code-verifier execute-batch --help
→ exit 0，列出全部 common/batch/cache 参数

execute-batch fixture smoke
→ exit 0
→ executed 4 requests (cache_hits=0)
→ summary total_requests=4
→ results.jsonl 4 行，request_id 顺序与 fixture 一致
→ 2 passed / 1 wrong_answer / 1 runtime_error
```

验收输出已删除，worktree 未保留运行产物。

### 6.5 额外对抗性探针

```text
cached SANDBOX_ERROR via ExecutionCache Protocol
→ cache_hits=1, cache_hit=True, status=sandbox_error

SQLite entry changed to structurally valid SANDBOX_ERROR
→ cache.get() returns sandbox_error

invalid training cache policy through CLI
→ runtime probe called
→ cache file created
→ then exit 2 with training opt-in error

lone-surrogate code
→ request validation accepted
→ read_only cache path: UnicodeEncodeError
→ disabled + real Piston: sandbox_error / piston transport failed

lone-surrogate cached stdout
→ SQLiteExecutionCache.put: UnicodeEncodeError

BatchExecutionResult runtime_ms=10**1000
→ OverflowError: int too large to convert to float
```

## 7. 结论

- **审查结论：不通过**。
- 6 个实施步骤的文件和常规功能基本落地，静态检查、386 项默认回归、9 项真实 Piston 验收和 CLI smoke 均通过。
- 但 P1–P4 均属于计划明确安全/合同边界：基础设施错误可被 cache 复用、非法训练缓存策略产生执行副作用、UTF-8 非法字符串造成模式依赖错误和裸异常、batch mapping 泄漏 `OverflowError`。按照 reviewer 判定规则，存在主要问题且最终验收项未通过，不能合并或登记 WP3 完成。
- executor 应修复全部主要问题并增加相应单元/CLI/SQLite 回归测试，再重新运行 `make lint`、`make test`、`make test-piston`、CLI smoke 和本报告中的对抗性探针后申请复审。
- 本轮不合并 `feat/wp3c`，不更新 `proceedings.md`，不将 WP3 整体标记为完成。

---

# WP3-c 独立复审报告 R2

- **复审日期**：2026-08-06
- **修复报告**：`ai-work/executor/WP3-executor.md`“代码修复报告（WP3-c R1）”
- **复审基线提交**：`2857f1a372706b3e53736becb480b84f418bb520`
- **修复提交**：`de52d06`、`c2360ec`、`7ac5266`、`35f7525`、`dce13b0`
- **复审方式**：逐条复核 R1 P1–P4、源码与新增测试检查、静态检查、默认回归、真实 Piston 总验收、CLI smoke，以及相邻公共 mapping/cache-key 合同探针

## 8. R1 问题逐条核验

| R1 问题 | 严重级别 | 状态 | 证据 |
|---|---|---|---|
| P1：cache get 可复用 `SANDBOX_ERROR` | 主要 | **已修复** | `cache.py:236-274` 在反序列化和公共结果校验后拒绝 sandbox result；`batch.py:443-455` 在通用 cache Protocol 边界先调用 `_copy_execution_result()`，再拒绝 sandbox hit。独立 custom-cache 探针得到 `BatchExecutionError: execution cache returned a sandbox error`，factory 调用数为 0；SQLite 注入回归通过。 |
| P2：非法 training-cache policy 失败前访问 Piston 并创建 cache | 主要 | **已修复** | `batch.py:304-317` 新增共享 `validate_batch_cache_policy()`；`cli.py:246-271` 在 Piston constructor、runtime probe 和 SQLite open 之前调用。独立探针结果：`exit 2`、`seen=[]`、cache/output 均不存在。 |
| P3：UTF-8 不可编码字符串导致模式依赖错误与裸异常 | 主要 | **已修复** | `base.py:81-108,111-160` 对 code/function/tests/stdout/stderr 做 UTF-8 校验；`batch.py:126-133,191-214` 校验 request/problem ID 并在任何 cache/factory 前复制请求；`cache.py:77-83,131-143,236-295` 和 `piston.py:121-124` 防御性归一编码错误。三种 cache mode 的 lone-surrogate 请求均得到脱敏 `ExecutionContractError`，cache/factory 调用数均为 0。 |
| P4：batch runtime 极大整数泄漏 `OverflowError` | 主要 | **已修复** | `batch.py:260-267` 捕获 float conversion overflow，并统一抛 `ExecutionContractError`。`runtime_ms=10**1000` 独立探针返回 `ExecutionContractError: runtime_ms must be a finite non-negative number`；最大有限 float 回归通过。 |

R1 的四个主要问题均已完整处置，新增测试断言与修复目标一致，未发现通过削弱原计划预期来迁就实现的情况。

## 9. 回归与原计划验收复核

| 验收项 | 状态 | 证据 |
|---|---|---|
| cache sandbox failure 不写入、不读取、不复用 | 通过 | SQLite 与 custom cache 两层均 fail-closed；定向测试与独立探针通过。 |
| training cache 默认禁用且非法策略零执行副作用 | 通过 | CLI 和 BatchExecutor 共用 policy validator；Piston/cache/factory 零调用。 |
| UTF-8 请求、结果、cache 和 transport 边界稳定 | 通过 | 36 项联合定向测试通过；三种 cache mode 行为一致。 |
| batch 并发、顺序、独立 executor、cache 模式 | 通过 | 既有 unit/integration 回归全绿。 |
| WP3-b 安全边界无回归 | 通过 | 真实 Piston 总验收中 WP3-b 7 项全部通过。 |
| CLI help、artifact、顺序和脱敏 | 通过 | `execute-batch` smoke exit 0；summary 为 4；results 4 行，2 passed / 1 wrong / 1 runtime，顺序正确且未包含请求 payload。 |
| `third_party/open-r1/**` 未修改 | 通过 | 固定 commit 仍为 `1416fa0cf21595d2083b399a2a0bbddd7f6e9563`。 |
| 公共 batch/cache mapping 与 key 边界全部稳定归一 | **未通过** | 发现两个新增主要问题 N1、N2，详见下一节。 |

## 10. 新问题清单

### N1 — 主要：`batch_execution_result_to_mapping()` 在验证 items 之前访问容器和元素，泄漏内置异常

- **位置**：`src/code_verifier/execution/batch.py:234-276`，重点是 `256-259`。
- **现象**：函数先执行 `len(result.items)` 和 `sum(item.cache_hit for item in result.items)`，随后才通过 `batch_execution_item_to_mapping()` 验证每个 item。
- **独立探针**：

  ```text
  BatchExecutionResult(total_requests=1, items=[object()])
  → AttributeError: 'object' object has no attribute 'cache_hit'

  BatchExecutionResult(items=None)
  → TypeError: object of type 'NoneType' has no len()
  ```

- **依据**：该函数是公开 JSON-safe serialization boundary；R1 P4 已确认畸形 batch result 必须稳定归一为 `ExecutionContractError`，不得泄漏 Python 内置异常。计划步骤 3 也要求固定 mapping 合同与严格结构化结果。
- **影响**：外部调用方、cache/文件反序列化层或后续 verifier 编排传入畸形 batch result 时，无法只捕获公开合同异常，可能产生未处理 traceback。
- **建议**：先明确验证 `items` 为 list；逐项调用 `batch_execution_item_to_mapping()` 得到已验证 mappings，再计算 cache-hit 数并组装输出。所有畸形容器/元素应统一抛脱敏 `ExecutionContractError`。新增 `None`、非 list、非 item 元素和错误 item 字段回归测试。

### N2 — 主要：cache-key 公共边界未完整验证，合法整数 timeout 和畸形 key 可泄漏异常或形成无效 digest

- **位置**：
  - `src/code_verifier/execution/cache.py:87-113`：builder 在 `validate_execution_request()` 接受 timeout 后直接调用 `timeout_seconds.hex()`；
  - `src/code_verifier/execution/cache.py:116-143`：`_cache_key_mapping()` 未验证 key 各字段类型/格式；
  - `src/code_verifier/execution/cache.py:236-295`：SQLite get/put 依赖该未验证 mapping。
- **独立证据 1**：整数 timeout 是 `validate_execution_request()` 接受的有限正数，且 Python typing 允许 int 传给 float 参数，但 builder 结果为：

  ```text
  request-accepted
  AttributeError: 'int' object has no attribute 'hex'
  ```

- **独立证据 2**：对公开 `ExecutionCacheKey` 使用 `replace(key, test_layer="visible")`：

  ```text
  execution_cache_key_digest(...)
  → AttributeError: 'str' object has no attribute 'value'

  SQLiteExecutionCache.get(...)
  → AttributeError: 'str' object has no attribute 'value'
  ```

  同时，`memory_limit_mb=True` 或任意 `timeout_seconds_hex="bad"` 会被直接序列化并生成 digest，而不是 fail-closed。
- **依据**：计划步骤 2 要求稳定、完整且安全相关字段精确的 cache key；横切规则要求严格拒绝 bool-as-int 和宽松类型；cache corruption/invalid state 必须归一为 `ExecutionCacheError`，不得产生内置异常或无效缓存身份。
- **影响**：公开 cache-key API 对类型正确的整数 timeout 不可用；手工构造或外部恢复的畸形 key 可能中断 cache，或生成不符合计划语义的持久 entry，削弱 cache identity 可信性。
- **建议**：新增单一 `_validate_execution_cache_key()`，精确验证 hash 格式、非空 UTF-8 文本、枚举、timeout hex 可解析且有限正、memory 正整数非 bool；在 mapping/digest/get/put 全部调用。builder 对已接受的数值应使用 `float(timeout_seconds).hex()`，或在公共请求合同中一致地拒绝 int，但不得保留当前不一致行为。

## 11. 独立测试结果 R2

### 11.1 原样 worktree 命令

```text
make lint
→ 失败：.venv/bin/python 不存在，Error 127

make test
→ 失败：.venv/bin/python 不存在，Error 127
```

### 11.2 使用主仓库固定 VENV 验证当前 worktree 源码

```text
make lint VENV=/home/dzy/open-r1-code-verifier/.venv
→ Ruff check passed
→ 47 files already formatted
→ strict Mypy: no issues found in 47 source files

PYTHONPATH=src make test VENV=/home/dzy/open-r1-code-verifier/.venv
→ 422 passed, 3 skipped
```

三个 skip 均为默认模式下未显式启用的真实 Piston tests。

### 11.3 真实 Piston 总验收

```text
PYTHONPATH=src make test-piston \
  VENV=/home/dzy/open-r1-code-verifier/.venv \
  PISTON_CONFIG=configs/execution/piston-local.yaml
→ 9 passed, 2 deselected, 0 failed, 0 skipped
```

### 11.4 R1 定向联合回归

```text
pytest test_cache.py test_batch.py test_base.py test_piston.py test_cli.py \
  -k "structurally_valid_cached_sandbox_error or returned_by_custom_cache \
      or rejects_training_cache_before or custom_cache or non_utf8 or lone_surrogate \
      or invalid_runtime_without_builtin_overflow or maximum_finite_float_runtime"
→ 36 passed, 188 deselected
```

### 11.5 CLI smoke

```text
code-verifier --help
→ exit 0，列出 execute-batch

code-verifier execute-batch --help
→ exit 0，列出全部 batch/cache/common 参数

execute-batch fixture smoke
→ exit 0
→ executed 4 requests (cache_hits=0)
→ summary total_requests=4
→ results.jsonl 4 行，顺序与 fixture 一致
→ 2 passed / 1 wrong_answer / 1 runtime_error
```

Smoke 输出已删除，worktree 未保留运行产物。

## 12. R2 结论

- **复审结论：需修改**。
- R1 P1–P4 均已完整修复，常规回归、真实 Piston、CLI smoke 和定向对抗性测试全部通过。
- 但新增 N1、N2 均属于公开 batch/cache 合同与 cache identity 的主要问题。按照复审判定规则，存在新增主要问题时不能给出“通过”。
- executor 应修复 N1、N2，增加相应 malformed batch result、整数 timeout 和畸形 cache key 回归，并重新运行完整验收后申请 R3。
- 本轮不合并 `feat/wp3c`，不更新 `proceedings.md`，不将 WP3 整体标记为完成。

---

# WP3-c 独立复审报告 R3

- **复审日期**：2026-08-06
- **修复报告**：`ai-work/executor/WP3-executor.md`“代码修复报告（WP3-c R2）”
- **复审基线提交**：`ee62df1ff96e37da501d24328f5534422de6c539`
- **修复提交**：`afae99e`、`43fb74c`
- **复审方式**：逐条核验 R2 N1/N2、源码与新增测试检查、独立边界探针、静态检查、默认全量回归、真实 Piston 总验收和 CLI smoke

## 13. R2 问题逐条核验

| R2 问题 | 严重级别 | 状态 | 证据 |
|---|---|---|---|
| N1：batch result mapping 在验证 items 前泄漏内置异常 | 主要 | **已修复** | `src/code_verifier/execution/batch.py:234-280` 先要求 `items` 为 list，再逐项调用 `batch_execution_item_to_mapping()`，只使用已验证 mapping 计算 cache-hit 数。独立探针对 `None`、tuple、普通 object 和非法 item 字段均得到 `ExecutionContractError`。 |
| N2：cache-key 边界未完整验证，整数 timeout 与畸形 key 行为不稳定 | 主要 | **已修复** | `src/code_verifier/execution/cache.py:90-181` 新增统一 key validator；builder 使用 `float(timeout_seconds).hex()`；digest 在访问字段前验证 enum、hash、UTF-8、canonical timeout hex 和 memory；SQLite get/put 将畸形 key 归一为固定 `ExecutionCacheError`。整数 timeout 探针成功生成 canonical key，三类畸形 key 均按公开合同失败。 |

R2 的两个主要问题均已完整处置。新增测试直接覆盖原始失败输入及相邻非法字段，未通过修改预期削弱计划要求。

## 14. 计划完成度与最终验收复核

| 项目 | R3 状态 | 证据 |
|---|---|---|
| 步骤 1：ExecutionResult mapping 与 executor version | 通过 | 既有实现和全量测试无回归。 |
| 步骤 2：稳定 cache key 与安全 SQLite cache | 通过 | 必需字段完整、整数/浮点 timeout 一致、畸形 key fail-closed、sandbox error 不写入或复用。 |
| 步骤 3：有限并发 batch 与公开 mapping | 通过 | 并发、顺序、独立 executor、三种 cache mode、training guard 和畸形 result mapping 全部通过。 |
| 步骤 4：`execute-batch` CLI 与原子脱敏输出 | 通过 | help 和真实 smoke exit 0；4 条结果顺序正确，artifact 不包含 code/tests。 |
| 步骤 5：Mock 与真实 Piston 集成 | 通过 | 显式 Piston 总验收 9 passed、0 failed、0 skipped。 |
| 步骤 6：文档与 WP3 收口 | 通过 | README、AGENTS 与 Piston 文档保持单机边界、缓存敏感性和 WP4 范围说明。 |
| 上游与范围 | 通过 | `third_party/open-r1` 固定 commit 为 `1416fa0cf21595d2083b399a2a0bbddd7f6e9563`，未发现 WP4 越界实现。 |

## 15. 独立测试结果 R3

### 15.1 原样 worktree 命令

```text
make lint
→ 失败：.venv/bin/python 不存在，Error 127

make test
→ 失败：.venv/bin/python 不存在，Error 127
```

### 15.2 使用主仓库固定 VENV 验证当前 worktree 源码

```text
make lint VENV=/home/dzy/open-r1-code-verifier/.venv
→ Ruff check: All checks passed
→ Ruff format: 47 files already formatted
→ strict Mypy: no issues found in 47 source files

PYTHONPATH=src make test VENV=/home/dzy/open-r1-code-verifier/.venv
→ 444 passed, 3 skipped
```

三个 skip 均为默认模式下未显式启用的真实 Piston tests。

### 15.3 R2 定向回归与独立探针

```text
pytest test_batch.py test_cache.py -k <R2 边界集合>
→ 22 passed, 54 deselected

build_execution_cache_key(timeout_seconds=1)
→ canonical timeout hex 0x1.0000000000000p+0
→ digest 正常生成

malformed cache keys: invalid test_layer / bad timeout hex / bool memory
→ digest: ExecutionContractError
→ SQLite get/put: ExecutionCacheError: execution cache key is invalid

batch items: None / tuple / object / invalid fields
→ ExecutionContractError，未泄漏 TypeError 或 AttributeError
```

### 15.4 真实 Piston 与 CLI

```text
PYTHONPATH=src make test-piston \
  VENV=/home/dzy/open-r1-code-verifier/.venv \
  PISTON_CONFIG=configs/execution/piston-local.yaml
→ 9 passed, 2 deselected, 0 failed, 0 skipped

code-verifier --help
→ exit 0

code-verifier execute-batch --help
→ exit 0

execute-batch fixture smoke
→ exit 0
→ executed 4 requests (cache_hits=0)
→ summary total_requests=4
→ results.jsonl 4 行，顺序正确
→ 2 passed / 1 wrong_answer / 1 runtime_error
```

Smoke 输出已删除，worktree 未保留运行产物。

## 16. R3 结论

- **复审结论：通过**。
- R2 N1、N2 均已修复；此前 R1 P1–P4 继续保持修复状态。
- 计划六个实施步骤、静态检查、444 项默认回归、真实 Piston 总验收、CLI smoke 和额外边界探针全部通过。
- 未发现新增阻断、主要或次要问题；WP3-c 及 WP3 整体验收通过。
- 审查报告提交后进入 reviewer 最终处理：核对 worktree/main 状态，执行 `--no-ff` 合并，整合 WP3 proceedings，并记录最终合并提交。

## 17. 最终合并与完成状态

- 阶段审查提交：`07cfff3`（`docs: add WP3-c review round r3`）。
- 主分支原有未跟踪 `ai-work/planner/WP3-c-plan.md` 与阶段分支内容完全一致；为避免同路径未跟踪文件阻塞合并，原样提交为 `cdec437`（`docs: add WP3-c implementation plan`）。
- 合并提交：`020af935db0b483d4bf76b03963b842f7ddce4c6`。
- 合并消息：`feat: complete WP3 batch execution and cache`。
- 合并方式：`git merge --no-ff feat/wp3c`；合并成功且未产生冲突。
- 合并后的 `main` 独立复验：`make lint` 通过；`make test` 为 444 passed、3 skipped；`make test-piston PISTON_CONFIG=configs/execution/piston-local.yaml` 为 9 passed、0 failed、0 skipped。
- 合并后的 CLI 验收：`code-verifier --help` 与 `execute-batch --help` 返回 0；fixture smoke 处理 4 条请求，summary 为 4，结果顺序和脱敏要求通过。
- `proceedings.md` 已将 WP3-a、WP3-b 与 WP3-c 整合为一条 `WP3：安全执行器` 完成记录。
- 清理阶段 worktree 时，`git worktree remove .worktrees/wp3c` 在 submodule deinit 前后均被 Git 拒绝，错误为 `fatal: working trees containing submodules cannot be moved or removed`。
- 已执行非强制 `git -C .worktrees/wp3c submodule deinit --all`；未使用 `git worktree remove --force`。因此 `.worktrees/wp3c` 暂时保留，但不影响 WP3-c 合并、验收和 WP3 完成记录。
- 未执行 push；阶段分支按项目约定保留。
