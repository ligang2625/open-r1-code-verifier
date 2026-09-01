# 计划模板：{stage_id} Implementation Plan

> `{stage_id}` 使用完整阶段标识，例如 `WP5`、`WP5-a`、`WP5-b`。planner-ex 只产出最终正文，不创建/提交 branch/worktree；共用 `stage-lifecycle bootstrap_plan` 负责把该正文写入并 seal 到阶段分支，可由 Web GPT + CodexPro 或 Local Codex 执行。
> Sealed plan 是用户未另行指示时的默认执行基线，不是不可变宗旨。后续用户明确指定新的实现、顺序、scope 或恢复方式时，以用户指令形成 effective execution contract，并在 execution/review 中记录偏差；无需为了 plan SHA 先重写 plan。
> 实施步骤面向只有文件读写与基础 shell 的 execution agent；不得依赖 Codex/MCP/其它 skill。`Execution Routing` 是默认 orchestration metadata，可在用户指令或真实依赖需要时形成不同 effective routing。

# {stage_id} 实施计划（[阶段名称]）

## 1. 元信息

| 项 | 值 |
|---|---|
| stage_id | `{stage_id}` |
| stage_profile | `development` 或 `validation` |
| control_plane_hardware | 固定 `GTX 1660 Ti (6GB)`；planner/reviewer/lifecycle/router/default execution |
| target_hardware | `GTX 1660 Ti (6GB)` 或 `24GB GPU`；仅表示真正 execution target |
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
- 失败处理：判断失败属于可修环境、可修代码还是明确 blocker。若尚未产生业务修改可直接修复后重试；若已有可保留 partial work，则记录 checkpoint 或由 LLM 从 Git/report 恢复。不要为了保持 `HEAD == plan_commit` 而丢弃有效工作，也不要把普通 SHA 漂移当作 retire 理由。

> 这里只放能够在 GTX 1660 Ti control plane 实施前判断的非破坏性 prerequisites，例如 `1660ti-wsl` Piston、必要依赖 import、control-plane data/cache。validation 的 4090 READY、>=22 GiB GPU、target model/cache/data 与 persistent artifact/HF/data roots **不属于 planner/bootstrap preflight**；它们由具体 target-GPU gate 的 portable `run.sh` 在 4090 operator-start preflight 中 fail closed 检查。4090 如需 Piston，当前 canonical transport 是 1660 Ti control plane 主动连接 provider public SSH endpoint，并以 loopback-only reverse forward `-R 127.0.0.1:2000:127.0.0.1:2000` 提供唯一 host `1660ti-wsl` 的 Piston；target preflight 只验证 4090 loopback endpoint 与 exact runtime。

### Operator terminal execution（仅 `validation + target_hardware=24GB GPU`；schema 名称保留，但覆盖所有 target-GPU gates）

```yaml
operator_terminal_execution:
  version: 1
  required: true
  gates:
    - gate_id: <stage-unique-id>
      run_kind: <evaluation|sft|grpo|analysis 等非空描述>
      executor_runs_command: false
      restart_policy: <exact_rerun|trainer_checkpoint>
      expected_artifacts:
        - "$CODE_VERIFIER_ARTIFACT_ROOT/..."
```

对每个 gate 另写：
- **触发点**：哪些代码/config/短测试必须先由 executor 完成并 commit；若不需要 tracked 修改，明确允许 `result_code_commit == plan_commit`（repair 为 `review_commit`）。
- **命令模板**：只使用 `$CODE_VERIFIER_ARTIFACT_ROOT` / `$HF_HOME` / `$CODE_VERIFIER_DATA_ROOT` 等 target-runtime 变量，不硬编码机器路径或密钥；这些变量由 4090 `run.sh` 从 target-local machine record 解析，不要求 1660 Ti router 预先知道其绝对值。
- **Restart policy**：full evaluation 等自身支持 exact-prefix resume 的命令使用 `exact_rerun`；SFT/GRPO 使用 `trainer_checkpoint`，并明确 canonical run dir、`checkpoint-*` 选择规则、无 checkpoint 时的 fail-closed/quarantine+fresh-restart 路径。不得写“训练失败后直接重跑 fresh command”。
- **Operator-start short preflight**：定义每次人工 attempt 真正开始时、取得锁后要重新检查的 GPU/CUDA、Piston（如该 gate 使用）、model/data/cache 与 artifact-root writable/free-bytes/free-inodes 条件。存储阈值按本 stage 预计 output/checkpoint 规模给出可判定规则；失败时不得启动 target command。
- **Operator post-run acceptance**：target command 返回 0 后，立即在 4090 运行 plan-specific 短时 strict loader/completed-status/metrics-schema/artifact-identity 检查。只有 `command_rc=0` 且 `postcheck_rc=0` 才允许 `gate_status=passed`；postcheck 失败时 script 必须非零退出并保留 evidence。
- **Operator handoff**：control-plane executor 生成 tracked、secret-free、immutable `ai-work/executor/operator/<stage>/<gate>/<checkpoint>/run.sh`，记录 handoff checkpoint commit、repo-relative path、script SHA256、target path templates、expected artifacts 与 evidence 接收目录。checkpoint commit 应尽量窄，但普通 parent/result-code SHA 关系不作为硬门槛。用户通过 Git 让**实际 handoff commit**在 4090 可达，在 target checkout/detach 到该 commit、确认 clean、重新计算 script SHA256 后运行。target 端必要 Git 校验只保留“运行的是被 handoff 的 commit + tracked script 内容匹配”；其它 parent/latest/source SHA 作为诊断信息。
- **Evidence / Resume**：`operator-evidence.json` 必须足以证明实际 handoff commit/script、目标运行环境、`command_rc/postcheck_rc/gate_status`、formal run identity 与 required artifact identity。script/evidence/identity metadata 的内容 SHA 继续严格，因为它们证明实际执行对象；plan/review/result-code/workflow-runtime 等普通 commit SHA 可作为审计 anchor，不要求逐字段机械相等。resume 计算 received evidence SHA，结合当前 stage 状态判断 gate 是否仍适用；大型 checkpoint 默认不复制，证据不足时才短时只读 target check。

> `target_hardware=24GB GPU` 时全部 24GB gates 都使用此模式，包括短时 4090-only smoke；`target_hardware=GTX 1660 Ti (6GB)` 的 validation stage 省略整个 block。control-plane lint/unit/CPU/Piston/non-4090 smoke 仍由 executor 自动运行。

### Development Completion Inventory（仅 `development_terminal=true`）

```yaml
development_completion_inventory:
  version: 1
  items:
    - work_package: WP0
      status: finalized  # finalized | covered_by_this_stage
      evidence: "proceedings/finalized stage or current plan step"
    # ... WP1 through WP8，恰好各一项
```

> terminal plan 必须覆盖 WP0–WP8。`DEV-CLOSEOUT` 的所有项都必须是 `finalized`；如果仍有 `covered_by_this_stage` 或缺失 deliverable，应规划实际 development stage，而不是 closeout。

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
- Real training/numerical gate（validation stage）：先说明本 stage 是 `target_hardware=GTX 1660 Ti (6GB)` 的 formal-evidence-only analysis，还是 `target_hardware=24GB GPU` 的新 target execution。前者列出被消费的正式 source identities/hashes；后者列出全部 operator gates、正式数据/checkpoint/metrics 与 target-runtime persistent artifact contract。两者都不得用 synthetic/mock 替代真实 evidence；真实 target-GPU artifacts 不得留在 stage worktree 内。
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

> `DEV-CLOSEOUT` 固定 `mode: single`，因为它是 verification-only stage；允许 execution 在不产生业务代码 commit 的情况下写 completed E0。

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
