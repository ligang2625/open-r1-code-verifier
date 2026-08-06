# WP3-b 独立审查报告

- **计划文件**：`ai-work/planner/WP3-b-plan.md`
- **executor 报告**：`ai-work/executor/WP3-executor.md`
- **审查轮次**：R1
- **审查日期**：2026-08-06
- **审查分支 / worktree**：`feat/wp3` / `.worktrees/wp3`
- **审查方式**：计划与规格核对、源码与测试阅读、独立静态检查、默认回归、真实 Piston 安全套件、额外对抗性 harness 与合同边界探针

> 同一阶段报告文件此前记录的是 `WP3-a-plan.md`。按照 reviewer skill 的阶段重置规则，当前计划已变更为 `WP3-b-plan.md`，因此本文件从 WP3-b R1 重新开始记录。

## 1. 审查范围与基准

本轮只审查 WP3-b“本地 Piston 单请求执行与安全限制”。批量并发、缓存、执行 CLI 和 WP3 整体完成仍属于 WP3-c，不纳入本轮通过条件。

审查基准：

- `PROJECT_SPEC_Open-R1_CodeVerifier.md` §6.2、§8.1–§8.5、§19、§20、§21；
- `ai-work/planner/WP3-b-plan.md` 的 loopback transport、可信 harness、状态映射、真实安全探针与最终验收要求；
- `skills/wp-plan-reviewer/references/review-checklist.md` 的通用与执行器安全清单。

审查期间未修改 `src/`、`tests/`、`third_party/open-r1/`、配置或 `proceedings.md`。

## 2. 交付与验收核验

| 验收项 | 状态 | 证据 |
|---|---|---|
| 严格本地 Piston 配置与 loopback-only endpoint | 通过 | `src/code_verifier/execution/piston.py:159-230` 严格校验 schema、HTTP scheme、loopback host、userinfo/path/query/fragment 和端口；`configs/execution/piston-local.yaml` 使用 `127.0.0.1:2000`。 |
| transport 禁用 proxy/redirect、限制响应大小并脱敏错误 | 通过 | `piston.py:79-156` 使用空 `ProxyHandler`、拒绝 redirect、JSON content type 与 bounded read；相关单元测试及全量测试通过。 |
| 函数调用约定、类型敏感比较和状态分类 | 常规路径通过 | `harness.py:249-309` 与 23 项 harness 单元测试覆盖 list/dict/scalar、严格类型比较、syntax/runtime/wrong/pass 和输出限制。 |
| 可信 harness 不可被不可信候选伪造 | **未通过** | 候选导入后可直接修改 runner 的 `__main__._strict_equal` 或 `__main__.json.dumps`。真实 Piston 探针中候选返回错误值，但 `PistonExecutor` 返回 `PASSED`。详见问题 P0。 |
| `PistonExecutor.execute()` 稳定遵守公共合同 | **未通过** | `piston.py:420-423` 在检查上限前计算 `math.ceil(timeout_seconds * 1000.0)`；`timeout_seconds=1e308` 抛裸 `OverflowError`，未归一为 `ExecutionContractError`。详见问题 P1。 |
| 正确、错误、语法、运行、超时、内存、输出真实状态 | 表面通过但结论不可信 | `make test-piston` 为 6 passed；但 harness 可伪造 pass，因此正常状态套件不能证明恶意候选下结果可信。 |
| 网络、非 root、基础文件写保护、宿主文件不可见、跨 job 清理、PID containment | 通过 | 真实 Piston 集成套件 6 项全部通过；恶意探针后的 service health smoke 通过。 |
| 结果可序列化、停止策略和 pass-rate denominator | 通过 | fake transport 单元测试通过；默认全量 324 passed、1 skipped。 |
| 默认测试不连接 Piston，显式测试不允许 skip | 通过 | 默认 `make test`：324 passed、1 module-level skipped；显式 `make test-piston`：6 passed、0 skipped。 |
| 文档保持 WP3 部分完成并记录本地服务限制 | 通过 | `README.md:184-220` 与 `docs/piston-local.md` 明确 loopback、自托管、显式测试及 WP3-c 未完成范围。 |
| 未新增宿主直接执行路径或上游修改 | 通过 | `src/code_verifier/execution/` 未发现 `exec(`、`eval(`、`compile(` 或 `subprocess`；`third_party/open-r1` 无 diff。 |
| 计划原样 `make lint` / `make test` 可在 worktree 运行 | 无法原样复现 | 当前 worktree 无 `.venv/bin/python`，原样 `make lint` 返回 Error 127；使用主仓库固定虚拟环境并设置 `PYTHONPATH=src` 后全部检查可复现。 |

## 3. executor 报告声明核验

| executor 声明 | 状态 | 核验结果 |
|---|---|---|
| 5 个实施步骤与文件交付完成 | 核实通过 | 目标模块、配置、测试、Makefile marker/target 和文档均存在。 |
| 静态检查、默认回归、真实 Piston 套件、runtime smoke 通过 | 核实通过（环境路径有差异） | 使用 `VENV=/home/dzy/open-r1-code-verifier/.venv` 与 `PYTHONPATH=src` 独立复现：lint 全绿、324 passed/1 skipped、Piston 6 passed、runtime `3.10.0`。当前 worktree 中报告所述 `.venv` 链接已不存在。 |
| 随机 marker、可信引用和严格 schema 能提供可信结果协议 | **与事实不符** | 候选只需 `import __main__` 并替换 `_strict_equal` 或 `json.dumps`，即可把错误答案改写成通过。无需猜测 marker，也无需高级内存攻击。 |
| 所有请求限制均稳定映射为公共合同错误 | **与事实不符** | 极大但有限的 `timeout_seconds` 在乘法后变成 infinity，`math.ceil()` 抛出 `OverflowError`。 |
| WP3 整体仍为部分完成 | 核实通过 | 报告和文档均保留 WP3-c 边界。 |

## 4. 问题清单

### P0 — 阻断：候选代码可直接篡改可信 harness 并把错误答案伪造为 `PASSED`

- **位置**：`src/code_verifier/execution/harness.py:172-314`，重点为：
  - `_strict_equal()` 定义于 `211-218`；
  - `_emit()` 在 `238-246` 运行时通过全局 `json.dumps` 序列化；
  - 候选模块在 `277` 被导入；
  - 候选执行后在 `290` 通过全局 `_strict_equal` 判断；
  - 最终调用的 `trusted_emit` 虽保存了函数对象，但该函数仍读取可变的 module globals。
- **独立真实 Piston 证据 1**：候选代码执行：

  ```python
  import __main__
  __main__._strict_equal = lambda actual, expected: True

  def target(value):
      return value + 999
  ```

  请求为 `input=1, expected=2`，实际返回值为 `1000`，但公开结果为：

  ```text
  passed passed
  ```

- **独立真实 Piston 证据 2**：候选修改 `__main__.json.dumps`，只在最终 report 序列化时把 `outcome` 改为 `passed`，公开结果为：

  ```text
  passed 1 1.0 passed
  ```

- **依据**：
  - 规格 §8.1 要求模型代码始终视为不可信；
  - 计划 §3.3 要求候选不能破坏可信执行结果；§3.4 / 步骤 2 将 marker、可信引用和严格 schema 作为结果可信边界；
  - reviewer 执行器清单要求检查“测试输入是否可能注入 runner”。
- **影响**：模型生成代码可主动欺骗 hidden-test verifier，将任意错误答案计为通过，直接污染 reward、训练信号和评测结果。这比 sandbox escape 更贴近本项目核心完整性风险，必须阻断合并。
- **建议**：
  1. 不要在同一 Python interpreter 中由候选与最终判定逻辑共享 module globals；
  2. 在 Piston job 内使用可信父进程执行比较与 report 生成，候选放入独立子进程，仅返回受限、严格解析的 actual 值；候选进程不得接触 expected、marker 或父进程内存；
  3. 若暂不引入子进程，至少将 comparator、JSON serializer、emit writer 和 payload引用全部封装为候选无法通过 `__main__` 修改的局部闭包，但这仍不能替代进程隔离；
  4. 新增真实 Piston 回归测试，覆盖修改 `__main__._strict_equal`、`__main__.json.dumps`、`_emit`、`sys.__stdout__` 以及 stack-frame marker 窃取；任何错误候选均不得返回 `PASSED`。

### P1 — 主要：极大有限 timeout 泄漏未处理 `OverflowError`

- **位置**：`src/code_verifier/execution/piston.py:420-423`
- **现象**：`validate_execution_request()` 接受有限正浮点数 `1e308`，随后：

  ```python
  timeout_ms = math.ceil(timeout_seconds * 1000.0)
  ```

  乘法得到 infinity，`math.ceil()` 抛出：

  ```text
  OverflowError cannot convert float infinity to integer
  ```

  对照探针 `3600.0001` 会得到预期的 `ExecutionContractError`，说明问题仅在上限检查顺序。
- **依据**：计划步骤 3 明确要求 `ceil(timeout_seconds * 1000)` 后检查合理上限，并保持执行合同异常稳定；WP3-a 已确立非法数值不得泄漏裸 `OverflowError`。
- **影响**：调用方无法只捕获 `ExecutionContractError`；极端配置可中断 verifier/reward 编排并产生未处理 traceback。
- **建议**：在乘法和 `ceil()` 前先比较秒级上限，或使用显式 overflow guard；所有超过 3600 秒或转换不可表示的值统一抛 `ExecutionContractError`。新增 `1e308`、最大有限 float 和边界值回归测试。

## 5. 独立测试结果

### 5.1 静态检查与默认回归

```text
make lint
→ 失败：.venv/bin/python 不存在，Error 127

make lint VENV=/home/dzy/open-r1-code-verifier/.venv
→ Ruff check: All checks passed
→ Ruff format: 42 files already formatted
→ strict Mypy: no issues found in 42 source files

PYTHONPATH=src make test VENV=/home/dzy/open-r1-code-verifier/.venv
→ 324 passed, 1 skipped
```

唯一 skip 为未显式启用的真实 Piston 模块，符合默认测试不连接服务的计划。

### 5.2 真实 Piston 验收与 runtime

```text
PYTHONPATH=src make test-piston \
  VENV=/home/dzy/open-r1-code-verifier/.venv \
  PISTON_CONFIG=configs/execution/piston-local.yaml
→ 6 passed, 0 failed, 0 skipped

runtime smoke
→ 3.10.0
```

### 5.3 对抗性与合同边界探针

```text
candidate replaces __main__._strict_equal; actual=1000, expected=2
→ passed passed

candidate replaces __main__.json.dumps; actual=1000, expected=2
→ passed 1 1.0 passed

timeout_seconds=1e308
→ OverflowError cannot convert float infinity to integer

timeout_seconds=3600.0001
→ ExecutionContractError timeout_seconds exceeds the supported Piston limit
```

## 6. 结论

- **审查结论：不通过**。
- 常规功能、loopback transport、资源限制和现有真实安全探针均通过，但 P0 证明候选代码可以在真实 Piston 中伪造 `PASSED`，直接破坏 verifier/reward 的可信性；P1 说明公共异常合同仍有未处理边界。
- executor 必须修复 P0、P1，增加对应单元与真实 Piston 回归测试，并重新运行 `make lint`、`make test`、`make test-piston` 和对抗性探针后申请复审。
- 本轮禁止合并 `feat/wp3`，不更新 `proceedings.md`，不把 WP3-b 或 WP3 标记为完成。
