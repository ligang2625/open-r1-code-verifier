# WP3-b 执行报告

## 基于 plan 的执行结果

- **执行计划**：`ai-work/planner/WP3-b-plan.md`
- **目标阶段**：WP3-b（本地 Piston 单请求执行与安全限制）
- **执行分支**：`feat/wp3`
- **独立 worktree**：`.worktrees/wp3`
- **执行状态**：本子阶段全部 5 个步骤已完成并通过验收；WP3 整体仍为部分完成，批量并发、缓存和执行 CLI 留给 WP3-c。

## 1. 已完成事项

### 步骤 1：严格本地 Piston 配置与有界 HTTP transport

- 新增 `configs/execution/piston-local.yaml`。
- 新增 `PistonExecutorConfig`、`PistonTransport`、`UrlLibPistonTransport`、`PistonTransportError`。
- 配置只允许 `http` 和 `localhost`、`127.0.0.1`、`::1`；拒绝 userinfo、非根 path、query、fragment、runtime selector、未知字段和非法资源上限。
- urllib transport 禁用系统代理和 HTTP redirect，只接受 JSON content type，限制 response bytes，并把 HTTP、连接、编码和 JSON 错误转换为固定脱敏错误。

### 步骤 2：可信 Python 函数测试 harness

- 新增 `PythonTestProgram`、`HarnessReport`、`build_python_test_program()`、`parse_harness_report()`。
- 文件顺序固定为可信 `main.py` 和原样 `candidate.py`；候选代码不拼接、不格式化。
- 测试 input、expected、函数名、marker 和输出上限仅通过 stdin JSON 传入。
- 实现 list 位置参数、dict 关键字参数和标量单参数调用约定。
- 实现类型敏感递归比较、JSON 可序列化检查、UTF-8 字节输出上限、随机 marker、最终行解析和严格 report schema。
- 结果不输出 actual、expected、输入内容或 traceback。

### 步骤 3：Piston 响应解析与单请求执行器

- 新增严格 Piston stage parser 和有限 `ExecutionStatus` 映射。
- 新增 `PistonExecutor`，其 `execute()` 签名与现有 `CodeExecutor` Protocol 一致。
- `validate_runtime()` 要求精确 Python/version，并拒绝缺失、重复或 malformed runtime 记录。
- 每个测试创建独立 Piston job，发送完整 wall-time、CPU-time、内存和输出限制。
- 实现 harness、timeout、output、internal error、signal、非零退出和 OOM 状态映射。
- 实现配置化 `stop_on_first_failure`；syntax、timeout、memory、output 和 sandbox failure 始终停止。
- 空测试不访问服务；整体状态、计数、通过率和序列化均通过 WP3-a 公共合同校验。
- 对外导出 `PistonExecutor`、`PistonExecutorConfig`、`PistonTransportError` 和 `load_piston_executor_config`。

### 步骤 4：真实 Piston 集成与安全验收

- 新增 `piston` pytest marker 和 `make test-piston`。
- 默认 `make test` 对真实 Piston 模块执行 module-level skip，不连接服务。
- 显式运行时，缺少配置、runtime 或服务直接失败，不降级为 skip。
- 真实探针覆盖：
  - 正确、错误答案、语法错误、运行错误；
  - 无限循环 timeout；
  - memory limit；
  - stdout/stderr output limit；
  - outbound network blocked；
  - runtime user 非 root；
  - `/etc` 写入失败；
  - 宿主 sentinel 不可读且内容/mtime 不变；
  - 跨 job `/tmp` 清理；
  - PID bomb 被限制；
  - 每个恶意探针后服务健康 smoke。

### 步骤 5：运维文档、公开示例与范围说明

- 新增 `docs/piston-local.md`，记录回环部署、安全边界、固定 source reference、image digest、runtime、健康检查、真实验收和停止/清理命令。
- README 增加 Piston Python API 示例、显式真实测试命令和 WP3-c 未完成范围。
- AGENTS 增加 harness/Piston 模块、测试、配置、文档和安全合并规则。
- 文档明确禁止公共 Piston endpoint、API token、LAN/公网暴露和宿主直接执行模型代码。

## 2. 真实 Piston 部署记录

本次验收使用仓库外部的本地服务：

| 项目 | 实际值 |
|---|---|
| 容器名 | `piston_wp3b` |
| 端口绑定 | `127.0.0.1:2000 -> 2000/tcp` |
| privileged | `true` |
| Piston source reference | `de2b365ac759670a3a0d13ea208a0869a92c7e64` |
| Piston image | `ghcr.io/engineer-man/piston@sha256:2f66b7456189c4d713aa986d98eccd0b6ee16d26c7ec5f21b30e942756fd127a` |
| Piston API package version | `3.1.1` |
| Python runtime | `3.10.0` |
| Docker Engine | `29.6.2` |
| Docker Compose | `5.3.1` |
| cgroup | v2 |

镜像内不包含 `.git` 元数据，因此 source reference 与运行镜像 digest 分别记录；实际安全验收对应上述精确 image digest。

Piston 不是仓库 submodule，未将其源码、runtime package 或容器数据写入项目仓库。

## 3. 真实环境暴露并修复的问题

### 3.1 Runtime record 可省略 `runtime` 字段

实际 `/api/v2/runtimes` 返回：

```json
{
  "language": "python",
  "version": "3.10.0",
  "aliases": ["py", "py3", "python3", "python3.10"]
}
```

Piston 内部 route 对未定义的 `runtime` 值不会序列化该字段。原实现错误地要求四字段对象，导致真实服务被判为 malformed。

修复后严格接受：

- `language/version/aliases`；或
- `language/version/aliases/runtime`，其中 `runtime` 必须为字符串。

未知字段仍被拒绝。

### 3.2 Memory limit 以 `RE + code 137` 返回

32 MiB memory probe 的实际 stage 元数据为：

```text
status=RE
code=137
signal=null
memory=33552000
message=Exited with error status 137
```

原 heuristic 只识别 `SG`、明确 memory message 或 `SIGKILL`。修复后增加确定性规则：`code == 137` 且 reported memory 达到配置上限 95% 时映射为 `MEMORY_LIMIT`。低于阈值的 code 137 或其他 `RE` 仍映射为 `RUNTIME_ERROR`。

## 4. 新增与修改文件

### 新增

- `ai-work/planner/WP3-b-plan.md`
- `configs/execution/piston-local.yaml`
- `src/code_verifier/execution/harness.py`
- `src/code_verifier/execution/piston.py`
- `tests/unit/execution/test_harness.py`
- `tests/unit/execution/test_piston.py`
- `tests/integration/test_wp3b_piston_execution.py`
- `docs/piston-local.md`

### 修改

- `src/code_verifier/execution/__init__.py`
- `pyproject.toml`
- `Makefile`
- `README.md`
- `AGENTS.md`

### 明确未修改

- `src/code_verifier/execution/base.py` 的公共合同和签名
- `src/code_verifier/execution/mock.py`
- `src/code_verifier/cli.py`
- `src/code_verifier/parsing/**`
- `src/code_verifier/data/**`
- `src/code_verifier/training/**`
- `third_party/open-r1/**`
- `proceedings.md`

## 5. 分步提交

- `2d06916` — `feat: add bounded local piston transport`
- `bb82e5e` — `feat: add trusted python test harness`
- `9fda0d5` — `feat: add single-request piston executor`
- `2850e0f` — `test: add real piston safety acceptance`
- `4f69f4f` — `docs: document local piston operations`

`5022726` 是 Docker 尚未就绪时写入的临时阻断报告；本报告已在环境就绪和全部验收通过后将其状态更新为完成。

## 6. 实际验证结果

### 步骤专项测试

```text
PYTHONPATH=src .venv/bin/python -m pytest tests/unit/execution/test_piston.py -k "config or transport"
→ 9 passed

PYTHONPATH=src .venv/bin/python -m pytest tests/unit/execution/test_harness.py
→ 23 passed

PYTHONPATH=src .venv/bin/python -m pytest tests/unit/execution/test_piston.py
→ 38 passed
```

### 最终静态检查

```text
make lint
→ Ruff check: All checks passed
→ Ruff format: 42 files already formatted
→ strict Mypy: Success, no issues found in 42 source files
```

### 默认全量回归

```text
PYTHONPATH=src make test
→ 324 passed, 1 skipped
```

唯一 skip 是未显式设置 `CODE_VERIFIER_RUN_PISTON=1` 时的真实 Piston 模块，符合默认测试不连接服务的计划要求。

### 真实 Piston 安全验收

```text
PYTHONPATH=src make test-piston PISTON_CONFIG=configs/execution/piston-local.yaml
→ 6 passed, 0 failed, 0 skipped
```

### Runtime smoke

```text
PYTHONPATH=src .venv/bin/python -c "from pathlib import Path; from code_verifier.execution import PistonExecutor, load_piston_executor_config; executor = PistonExecutor(load_piston_executor_config(Path('configs/execution/piston-local.yaml'))); print(executor.validate_runtime())"
→ 3.10.0
```

### 安全与范围检查

- `third_party/open-r1` 无 diff。
- 在 `src/code_verifier/execution/` 中搜索 `exec(`、`eval(`、`compile(`，均无匹配。
- Piston 容器检查确认 `privileged=true`，但唯一发布地址是 `127.0.0.1:2000`。
- 未新增 Python 依赖、远程账户、API token 或公共 endpoint。

## 7. 配置与依赖影响

- 新增 `configs/execution/piston-local.yaml`。
- `pyproject.toml` 仅新增 `piston` pytest marker。
- `Makefile` 仅新增 `PISTON_CONFIG` 和显式 `test-piston` 目标。
- 未新增 Python package 依赖。
- Piston image、runtime 和 Docker volume 均为仓库外部本地运行资产。

## 8. 与计划的偏离

- 计划默认建议在主仓库同级目录创建 worktree。受工具工作区边界限制，继续复用 `.worktrees/wp3`；它仍是独立 Git worktree 和 `feat/wp3` 分支。
- worktree 复用主仓库 `.venv` 符号链接；由于 editable install 指向主工作区，pytest 和 smoke 命令显式使用 `PYTHONPATH=src`，确保导入当前 worktree 源码。
- 真实 Piston 部署使用固定官方 image digest和独立 named volume，而不是把 Piston 源码或 compose 文件复制进仓库。另行浅克隆官方仓库只用于记录 source reference。
- 状态映射根据真实 Piston `RE + code 137 + near-limit memory` 行为增加 OOM 规则；这是满足计划“真实内存状态必须精确通过”的必要兼容修复，未放宽测试预期。

无接口签名、功能范围、安全探针或测试通过标准偏离。

## 9. 已知限制与下一步

- 候选模块和可信 harness 在同一 Piston job 的同一 Python interpreter 中运行；随机 marker、可信引用和严格 schema不是完整的高级解释器级防篡改证明。
- 当前每测试一个独立 job，未实现批量请求、有限并发、cache key/cache store 或执行 CLI。
- Piston API container 需要高权限，必须继续保持专用环境、固定 digest和回环绑定。
- WP3-c 完成前，WP3 不得标记整体完成。

下一步由 `wp-plan-reviewer` 独立审查代码、重新运行默认与真实 Piston测试，并重点检查 SSRF/redirect、marker、OOM mapping和安全探针。审查通过后才可合并和更新 `proceedings.md`。

---

# 代码修复报告（WP3-b R1）

## 1. 修复依据

- 审查报告：`ai-work/reviewer/WP3-review.md`
- 审查轮次：WP3-b R1
- 修复范围：全部 P0 阻断问题与 P1 主要问题
- 未处理项：无
- 异议项：无

## 2. P0：隔离候选执行与最终判定

审查证明候选与可信 harness 共享解释器时，可修改 `__main__._strict_equal` 或 `__main__.json.dumps`，把错误答案伪造为 `PASSED`。原报告第 9 节中“同一解释器是已知 MVP 限制”的描述已被本修复取代，不再作为可接受风险保留。

修复提交：

```text
74031ca  fix: isolate candidate verdict execution
```

核心改动：

- `main.py` 现在是可信父进程，独占：
  - `expected`；
  - 类型敏感 comparator；
  - 最终随机 marker；
  - 最终 report JSON 与 stdout 写入。
- 候选代码在新的隔离 Python 子解释器中执行；子进程仅收到 `function_name` 和 `input`，不接收 `expected` 或最终 marker。
- 父进程读取完整原始 stdin 后关闭 fd 0，并通过 Linux `PR_SET_DUMPABLE=0` 禁止候选子进程读取父进程内存。
- 子进程只能通过独立 pipe 返回一个不可信的 claimed actual JSON；父进程严格解析后自行比较，绝不接受子进程提供的 `outcome`。
- 候选 stdout/stderr 由父进程使用 nonblocking selector 独立 drain，按 UTF-8 byte limit 截断和判定；候选无法通过替换 Python stream 或截断文件绕过限制。
- 子进程协议设置独立 8 MiB 上限；超限或 malformed 协议映射为 `harness_error`，不能形成通过结果。
- 子进程被 signal 或非零退出终止时，父进程传播退出状态，使 Piston 的 timeout、memory 和 signal 状态仍可按原映射工作。
- 候选修改自身 `__main__`、JSON 模块、`_emit`、`sys.__stdout__` 或扫描自身 stack frames 均只能影响候选进程，不能改写父进程 verdict。

新增回归：

- `tests/unit/execution/test_harness.py`
  - 5 个固定审计候选覆盖 `_strict_equal`、`json.dumps`、`_emit`、`sys.__stdout__` 和 stack-frame 探测；全部必须为 `wrong_answer`。
- `tests/integration/test_wp3b_piston_execution.py`
  - 在真实 Piston 中执行同样 5 个攻击；每个结果必须精确为 `WRONG_ANSWER`，随后健康 smoke 必须通过。
- `README.md`、`docs/piston-local.md`、`AGENTS.md`
  - 更新为可信父进程 / 不可信子进程架构，并将该边界写入后续修改和合并规则。

## 3. P1：超大 timeout 稳定归一为合同错误

审查发现 `timeout_seconds=1e308` 会在乘以 1000 后变为 infinity，随后 `math.ceil()` 抛出裸 `OverflowError`。

修复提交：

```text
8ecfc42  fix: reject oversized piston timeouts safely
```

修复内容：

- 在毫秒换算前先检查 `timeout_seconds > 3600.0`。
- 所有超过支持上限的有限值统一抛出：

```text
ExecutionContractError: timeout_seconds exceeds the supported Piston limit
```

- 新增回归覆盖：
  - `3600.0001`；
  - `1e308`；
  - 最大有限 IEEE-754 float；
  - 精确边界 `3600.0` 仍生成 `3_600_000` ms payload。
- 被拒绝请求不调用 transport。

## 4. 实际复测结果

### 受影响专项测试

```text
PYTHONPATH=src .venv/bin/python -m pytest \
  tests/unit/execution/test_harness.py \
  tests/unit/execution/test_piston.py
→ 70 passed
```

### 静态检查

```text
make lint
→ Ruff check: All checks passed
→ Ruff format: 42 files already formatted
→ strict Mypy: Success, no issues found in 42 source files
```

### 默认全量回归

```text
PYTHONPATH=src make test
→ 333 passed, 1 skipped
```

唯一 skip 是未显式启用的真实 Piston 模块，符合默认测试不连接服务的既有要求。

### 真实 Piston 与对抗性验收

```text
PYTHONPATH=src make test-piston \
  PISTON_CONFIG=configs/execution/piston-local.yaml
→ 7 passed, 0 failed, 0 skipped
```

真实套件继续精确通过正确、错误、语法、运行、timeout、memory、stdout/stderr output、网络、非 root、基础文件写、宿主隔离、跨 job 清理和 PID containment，并新增 5 类 verdict tampering 探针。

### Runtime smoke

```text
PYTHONPATH=src .venv/bin/python -c "... executor.validate_runtime() ..."
→ 3.10.0
```

## 5. 范围与安全核对

- 未修改 `ai-work/reviewer/WP3-review.md`。
- 未修改 `proceedings.md`。
- `third_party/open-r1` 无 diff。
- 未新增 Python package 依赖、公共 Piston endpoint、token 或远程账户。
- 宿主 `src/code_verifier/execution/` 仍无 `exec(`、`eval(` 或 `compile(` 调用。
- 新增的 `subprocess.Popen` 仅存在于发送到 Piston 的可信 runner 源码中，用于 sandbox job 内的候选进程隔离；宿主进程不运行候选代码。
- WP3-b 修复已完成，但仍需 reviewer 独立复审；WP3 整体继续保持部分完成。
