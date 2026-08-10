# Web execution workflow reference v2

## Dispatch

Only consume a complete router dispatch with `backend=web`.

- source SINGLE → `effective_execution_mode=single`
- source MULTI → `effective_execution_mode=serialized_multi`

Source routing is immutable. The current Web GPT + CodexPro is the executor; it does not invoke Local Codex execution agents.

## Serialized MULTI

Implementation：依次执行每个 sealed `workstream_candidate`，每 lane 完成定向验证与显式 commit 后再进入下一 lane。默认按 plan 顺序；必要依赖可以调整执行顺序，但不能改 routing/candidate，且必须记录原因。

Repair：依次执行每个 repair candidate；candidate issue_ids 必须完整且仅覆盖 router `repair_issue_ids`。全局 regression 只验证结果，不扩大 repair scope。

## Commit ordering

1. code/test/config commits
2. global acceptance
3. capture `result_code_commit=HEAD`
4. append normal stage execution report
5. docs commit report

New routed Web records include audit metadata:

```yaml
execution_backend: web_codexpro
effective_execution_mode: serialized_multi
```

These fields do not affect provenance.

## Workspace

All implementation, tests and commits occur in the exact stage worktree. Plan/review/proceedings/third_party remain unchanged. No push, review or finalization.
