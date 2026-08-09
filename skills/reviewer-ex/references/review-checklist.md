# Reviewer Ex checklist / report template

本文件是 `{stage_id}` 的 append-only review artifact 模板。不同 stage 使用不同文件：`ai-work/reviewer/{stage_id}-review.md`。不得因为“重跑同一 stage”清空历史。

## 审查记录 {N}

### Review Record

```yaml
review_record:
  version: 1
  stage_id: WP5-b
  review_round: 1
  source_execution_id: E0
  reviewed_head_commit: <HEAD captured before review file is edited>
  conclusion: needs_repair  # needs_repair | pass
```

### 计划完成度 / 验收核对

| 项 | 状态 | 证据 | issue_id（若需 executor 行动） |
|---|---|---|---|
| Step N / acceptance X | 通过 / 未完成 / 部分完成 / 与计划不符 / 无法核实 | 文件:行号 / 命令输出 | `R1-M1` 或 `—` |

**Coverage invariant**：凡状态要求 executor 行动，必须填写 issue_id，且该 ID 必须进入本轮 `repair_issue_ids`。

### 独立测试

- `make lint` → ...
- `make test` → ...
- stage 特有验收 → ...

### Execution report 声明核验

- <声明>：核实通过 / 与事实不符 / 无法核实；证据：...

### 上一轮问题核验（R2+）

| issue_id | 上轮严重级别 | 状态 | 证据 |
|---|---|---|---|
| R1-M1 | major | 已修复 / 未修复 / 修复不完整 / 引入新问题 | ... |

### 问题列表

| ID | 严重级别 | 位置 | 问题 | 依据 | 建议 | 下一轮需修复 |
|---|---|---|---|---|---|---|
| `R1-M1` | blocker / major / minor / suggestion | `file:line` | ... | ... | ... | yes/no |

未解决旧问题沿用原 ID；当前 round 新问题使用 `R{round}-...`。

### Repair Routing

```yaml
repair_routing:
  version: 1
  required: true
  source_review_round: 1
  mode: single
  complexity: normal
  single_class: normal
  parallelizability: low
  multi_benefit: low
  independent_workstreams: 1
  repair_issue_ids:
    - R1-M1
  rationale:
    - "[当前剩余修复复杂度/依赖/ownership]"
    - "[single/multi 净收益判断]"
  workstream_candidates: []
```

`review_record.conclusion` 与 `repair_routing.required` 必须严格一致：`pass ⇔ false`，`needs_repair ⇔ true`。PASS 时仍保留本节：`required:false`；mode/complexity/single_class/parallelizability/multi_benefit 全部 null；independent_workstreams=0；repair_issue_ids/workstream_candidates 为空；rationale 仅说明无需 repair。

Repair MULTI candidate 格式：

```yaml
workstream_candidates:
  - id: A
    issue_ids: [R1-M1]
    write_scope:
      - src/...
      - tests/...
```

candidate 的 issue_ids 与 tracked write_scope 必须互不重叠，issue_ids 并集恰好等于 repair_issue_ids。

### 结论

- needs_repair / pass
- 理由：...
- 下一步：`stage-lifecycle checkpoint_review`

> Reviewer-ex 到此结束，不 commit、不 merge、不更新 proceedings。checkpoint 后 required=true 才调用 execution-router；PASS 则调用 stage-lifecycle finalize。

## Finalization Record（仅 stage-lifecycle finalize 在 main 上追加）

```yaml
finalization_record:
  version: 1
  stage_id: WP5-b
  review_round: 3
  review_commit: <sha>
  merge_commit: <sha>
  status: finalized
  finalized_at: <timestamp>
```
