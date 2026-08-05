# WP3-b 执行报告

## 基于 plan 的执行结果

- **执行计划**：`ai-work/planner/WP3-b-plan.md`
- **目标阶段**：WP3-b（本地 Piston 单请求执行与安全限制）
- **执行分支**：`feat/wp3`
- **独立 worktree**：`.worktrees/wp3`
- **执行状态**：部分完成，因本机未运行计划要求的回环 Piston 服务而在步骤 4 阻断；本子阶段未通过验收，WP3 整体仍为部分完成。

## 1. 已完成并提交的计划步骤

### 步骤 1：严格本地 Piston 配置与有界 HTTP transport

提交：`2d06916` — `feat: add bounded local piston transport`

已完成：

- 新增 `configs/execution/piston-local.yaml`，固定 `http://127.0.0.1:2000`、Python `3.10.0`、请求余量、响应上限、输出上限与停止策略。
- 新增 `PistonExecutorConfig`、`PistonTransport`、`UrlLibPistonTransport`、配置加载与严格校验。
- `base_url` 仅允许 `localhost`、`127.0.0.1`、`::1`，仅允许 HTTP，不允许 userinfo、非根 path、query 或 fragment。
- urllib transport 禁用代理和 redirect，限制 response bytes，只接受 JSON content type，并将 HTTP、连接、编码和 JSON 错误归一为不包含 response body 的固定错误。
- 新增配置和 transport 单元测试。

实际验证：

```text
make lint
→ Ruff check、Ruff format check、strict Mypy 全部通过

PYTHONPATH=src .venv/bin/python -m pytest tests/unit/execution/test_piston.py -k "config or transport"
→ 9 passed
```

### 步骤 2：可信 Python 函数测试 harness

提交：`bb82e5e` — `feat: add trusted python test harness`

已完成：

- 新增 `PythonTestProgram`、`HarnessReport`、`build_python_test_program()`、`parse_harness_report()`。
- 文件顺序固定为可信 `main.py`、原样 `candidate.py`；候选代码不拼接、不格式化。
- input、expected 和函数名仅经 stdin JSON 传入。
- 实现 list 位置参数、dict 关键字参数、标量单参数调用约定。
- 实现类型敏感递归比较、JSON 可序列化检查、stdout/stderr UTF-8 字节上限。
- 最终结果采用随机 marker 和严格 JSON schema；只接受最后一条非空 marker 行，并拒绝重复 key、未知字段、非有限 runtime 和 spoof。
- harness 不输出 actual、expected、输入内容或 traceback。

实际验证：

```text
make lint
→ Ruff check、Ruff format check、strict Mypy 全部通过

PYTHONPATH=src .venv/bin/python -m pytest tests/unit/execution/test_harness.py
→ 23 passed
```

### 步骤 3：Piston 响应解析与 `PistonExecutor`

提交：`9fda0d5` — `feat: add single-request piston executor`

已完成：

- 新增严格 Piston stage parser 和确定性状态映射。
- 新增 `PistonExecutor`，`execute()` 签名与现有 `CodeExecutor` Protocol 一致。
- `validate_runtime()` 要求 runtime 列表中恰好存在一个精确 Python/version 记录。
- 每个测试构造独立 Piston job，并发送完整 compile/run 时间、CPU、内存和输出边界。
- 实现 harness 状态、Piston `TO`、`OL`、`EL`、`XX`、signal、非零退出和 OOM heuristic 映射。
- 实现配置化 `stop_on_first_failure`；syntax、timeout、memory、output、sandbox failure 始终停止。
- 空测试不访问 transport；整体状态、通过数、总测试数和 pass rate 经过现有 execution contract 校验。
- 对外导出 `PistonExecutor`、`PistonExecutorConfig`、`PistonTransportError`、`load_piston_executor_config`。
- fake transport 单元测试覆盖 payload、runtime、状态映射、停止策略、顺序、序列化和敏感信息不回显。

实际验证：

```text
make lint
→ Ruff check、Ruff format check、strict Mypy 全部通过

PYTHONPATH=src .venv/bin/python -m pytest tests/unit/execution/test_piston.py
→ 38 passed
```

## 2. 步骤 4 当前状态：代码已实现，但真实安全验收失败

当前 worktree 中已实现、但因步骤验收未通过而**尚未提交**：

- `tests/integration/test_wp3b_piston_execution.py`
- `pyproject.toml`
- `Makefile`

实现内容：

- 注册 `piston` pytest marker。
- 新增 `make test-piston`，显式设置 `CODE_VERIFIER_RUN_PISTON=1` 和配置路径。
- 默认测试未显式启用时在 module level 跳过真实 Piston 模块，不连接服务。
- 显式运行时，缺少配置、runtime 或服务均失败，不降级为 skip。
- 真实探针覆盖：正确、错误答案、语法错误、运行错误、无限循环、内存、stdout/stderr 输出上限、网络禁用、非 root、基础文件系统写保护、宿主 sentinel 不可见、跨 job `/tmp` 清理、PID bomb 和恶意探针后的服务健康检查。

静态检查结果：

```text
make lint
→ Ruff check passed
→ 42 files already formatted
→ strict Mypy: Success: no issues found in 42 source files
```

默认全量回归首次运行时，独立 worktree 尚未初始化既有 Open-R1 submodule，导致环境记录测试把当前分支提交误识别为 submodule commit：

```text
PYTHONPATH=src make test
→ 323 passed, 1 skipped, 1 failed
```

未修改业务代码或测试预期。随后仅初始化仓库已有的只读 pinned submodule：

```text
git submodule update --init --recursive
→ third_party/open-r1 checked out 1416fa0cf21595d2083b399a2a0bbddd7f6e9563

PYTHONPATH=src make test
→ 324 passed, 1 skipped
```

真实 Piston 验收实际运行结果：

```text
PYTHONPATH=src make test-piston PISTON_CONFIG=configs/execution/piston-local.yaml
→ collected 6 items
→ 6 errors
```

所有错误均发生在 module fixture 的 `PistonExecutor.validate_runtime()`：本机 `http://127.0.0.1:2000` 无可连接的 Piston 服务，统一返回：

```text
PistonTransportError: piston transport failed
```

这不是测试 skip，也未放宽断言。依据计划步骤 4 的通过标准和 executor skill 的失败处理纪律，步骤 4 未完成，相关改动未提交。

## 3. 未执行的步骤

### 步骤 5：运维文档、README、AGENTS 与阶段总验收

未开始。原因是步骤 4 的真实 Piston 安全验收未通过，计划明确要求安全探针失败时不得继续 WP3-c，也不得将本阶段标记为完成。为避免文档错误声称 WP3-b 已实现，未修改：

- `docs/piston-local.md`
- `README.md`
- `AGENTS.md`

最终 runtime smoke、真实安全套件全绿和阶段总验收因此尚未完成。

## 4. 文件变更汇总

### 已提交新增

- `ai-work/planner/WP3-b-plan.md`
- `configs/execution/piston-local.yaml`
- `src/code_verifier/execution/harness.py`
- `src/code_verifier/execution/piston.py`
- `tests/unit/execution/test_harness.py`
- `tests/unit/execution/test_piston.py`

### 已提交修改

- `src/code_verifier/execution/__init__.py`

### 已实现但未提交

- `tests/integration/test_wp3b_piston_execution.py`
- `pyproject.toml`
- `Makefile`

### 未修改

- `src/code_verifier/execution/base.py`
- `src/code_verifier/execution/mock.py`
- `src/code_verifier/cli.py`
- `src/code_verifier/parsing/**`
- `src/code_verifier/data/**`
- `src/code_verifier/training/**`
- `third_party/open-r1/**` 的源码和 pin
- `proceedings.md`

## 5. 配置与依赖影响

- 新增本地 Piston YAML 配置。
- 步骤 4 的未提交改动会新增 pytest marker 与 `make test-piston` 目标。
- 未新增 Python 依赖；HTTP 仅使用标准库。
- 未配置公共 Piston endpoint、API token 或任意远程 URL。
- 未修改 `third_party/open-r1`；只在独立 worktree 中初始化既有 pinned submodule 检出。

## 6. 环境说明与偏离

- 复用主仓库已有 `.venv`，worktree 内的 `.venv` 仅为未跟踪符号链接，不提交。
- 由于 editable install 指向主工作区，pytest 命令显式使用 `PYTHONPATH=src`，确保导入当前 `feat/wp3` worktree 的源码。
- worktree 位于主仓库内 `.worktrees/wp3`，原因是当前工具工作区边界限制；它仍是独立 Git worktree 和 `feat/wp3` 分支，主工作区未直接修改。
- 除工作区路径与验证命令中的 `PYTHONPATH` 外，无接口、状态映射、测试预期或安全范围偏离。

## 7. 阻断项与继续条件

继续执行前必须在专用本地环境启动仅绑定回环地址的自托管 Piston，并安装配置中精确 runtime `python 3.10.0`。随后需要：

1. 重新运行 `PYTHONPATH=src make test-piston PISTON_CONFIG=configs/execution/piston-local.yaml`，要求 6 passed、0 failed、0 skipped；
2. 若真实探针暴露实现问题，修复并重新运行 `make lint`、默认全量测试和真实 Piston 测试；
3. 步骤 4 全部通过后提交其三个文件；
4. 再执行步骤 5 文档、runtime smoke 和最终验收。

在上述条件满足前，WP3-b 不得标记完成，也不得进入 WP3-c。
