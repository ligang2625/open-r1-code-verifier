# 计划模板：{stage_id} Implementation Plan

> `{stage_id}` 使用完整阶段标识，例如 `WP5`、`WP5-a`、`WP5-b`。planner-ex 只产出最终正文，不创建/提交 branch/worktree；共用 `stage-lifecycle bootstrap_plan` 负责把该正文写入并 seal 到阶段分支，可由 Web GPT + CodexPro 或 Local Codex 执行。
> 实施步骤面向只有文件读写与基础 shell 的 execution agent；不得依赖 Codex/MCP/其它 skill。`Execution Routing` 是 orchestration metadata。

# {stage_id} 实施计划（[阶段名称]）

## 1. 元信息

| 项 | 值 |
|---|---|
| stage_id | `{stage_id}` |
| stage_profile | `development` 或 `validation` |
| target_hardware | `GTX 1660 Ti (6GB)` 或 `24GB GPU` |
| evidence_class | `engineering` 或 `real-training/numerical` |
| development_terminal | `true` 或 `false`；validation 固定 `false` |
| 目标 WP | `WP{n}`：[名称]；纯开发收口可为 `Development Closeout` |
| 规格依据 | `PROJECT_SPEC_Open-R1_CodeVerifier.md` §[...] |
| 前置状态 | `proceedings.md`：[...] |
| `planning_base_commit` | `<main HEAD sha at planning time>` |
| proposed branch | `feat/wp{n}` / `feat/wp{n}-{sub}`；`DEV-CLOSEOUT` 用 `chore/dev-closeout` |
| proposed worktree | `.worktrees/wp{n}` / `.worktrees/wp{n}-{sub}`；`DEV-CLOSEOUT` 用 `.worktrees/dev-closeout` |
| final plan path | `ai-work/planner/{stage_id}-plan.md` |
| execution report path | `ai-work/executor/{stage_id}-executor.md` |
| review path | `ai-work/reviewer/{stage_id}-review.md` |
| plan lifecycle | planner-ex handoff → `stage-lifecycle bootstrap_plan` → committed plan seal |

> 不得让两个不同 `stage_id` 共用 execution/review 文件。

## 2. 目标与范围

### 目标（规格原文）
[原文]

### 交付（规格原文）
- [...]

### 验收（规格原文）
- [...]

### 范围内 / 范围外
- 范围内：...
- 范围外：...

## 3. 前置条件与约束

- proceedings 相关决策/未完成项：...
- 不修改 `third_party/open-r1/`；Open-R1 访问仅经 adapter。
- 外部接口/运行时不确定项：先验证，不能臆造。
- 其它项目硬约束：...

### Execution preflight（首次业务修改/commit 前）

- 检查：...
- 命令：`...`
- 通过标准：...
- 失败处理：停止本次 execution，保持 `HEAD == plan_commit`，修复环境后可重新调用 execution-router；不得先提交部分实现。

> 只放能够在实施前判断的非破坏性环境 prerequisites，例如 Piston 可达性、必要依赖 import、模型缓存/CUDA 可用性。validation 的 24GB GPU 与持久 artifact root 由 execution-router 另做统一 preflight。

## 4. 实施步骤

### 步骤 N：<动作>

**目标文件**：`src/code_verifier/...`

**新增 / 修改的符号**：
```python
def function_name(arg: Type) -> ReturnType:
    ...
```

**主要功能**：输入、输出、错误处理、调用关系、与既有代码衔接。

**配置 / CLI 变更**：...

**测试方案**：
- 测试文件：`tests/...`
- 测试函数：`test_...`
- 断言：...

**验证命令与通过标准**：
```bash
make lint
make test
```
通过标准：...

（按依赖顺序重复；单 stage 通常 ≤10 步、新模块 ≤8。）

## 5. 总体验收与测试计划

- 单元测试：...
- Development integration（development stage）：说明 GTX 1660 Ti/CPU/Piston/GPU-smoke/fixture evidence；不得要求真实训练。若 `development_terminal=true`，必须包含 `make lint`、`make test`、`make test-gpu`、真实 `make test-piston`（0 failed/0 skipped）和生产关键路径无 stub/TODO/fake implementation 的 closeout 检查。
- Real training/numerical gate（validation stage）：说明 24GB GPU、正式数据、真实 checkpoint/metrics；不得用 synthetic/mock 替代。真实 artifacts 必须写入 execution-router 提供的持久 `artifact_root`，不得留在 stage worktree 内。
- 数据泄漏/安全检查（如适用）：...
- 最终标准：
  - [ ] 规格验收逐条通过
  - [ ] `make lint` 全绿
  - [ ] `make test` 全绿
  - [ ] stage 特有可测量标准通过

## 6. Execution Routing

```yaml
execution_routing:
  version: 1
  mode: single
  complexity: normal
  single_class: normal
  parallelizability: low
  multi_benefit: low
  independent_workstreams: 1
  rationale:
    - "[复杂度/依赖/调试风险的具体依据]"
    - "[为什么 single/multi 的净收益更合适]"
  workstream_candidates: []
```

约束：
- `mode`: `single | multi`
- `complexity`: `very_simple | normal | difficult_serial`
- single 时 `single_class == complexity`；multi 时 `single_class: null`
- `parallelizability`、`multi_benefit`: `low | medium | high`
- SINGLE 可有多个独立 lane，但 `workstream_candidates: []`
- MULTI 必须 `complexity != very_simple`、`parallelizability=high`、`multi_benefit=high`、至少 2 个 substantive lane；candidate 含唯一 `id`、互不重叠 `steps`、互不重叠 tracked `write_scope`
- plan/routing 不写具体 model/effort/backend；backend 由 execution-router 每次运行时选择

## 7. 风险与注意事项
- ...

## 8. 关联文档索引
- `PROJECT_SPEC_Open-R1_CodeVerifier.md`：§...
- `proceedings.md`：...

## 9. Handoff

- 下一步：运行 `$stage-lifecycle bootstrap_plan`，使用本计划正文创建/复用 proposed stage worktree 并 commit plan seal；同一个 lifecycle skill 可在 Web GPT + CodexPro 或 Local Codex 中执行。
- 在 bootstrap 成功并得到 `plan_commit` 前，不得调用 execution-router。
