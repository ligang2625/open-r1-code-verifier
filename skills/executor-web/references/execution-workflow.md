# Web execution workflow reference v2

## Dispatch

Use a router dispatch with `backend=web`; stage/worktree/task identity and actual backend are required, while ordinary plan/review/checkpoint commit fields may be recovered from repo state.

- source SINGLE → default `effective_execution_mode=single`
- source MULTI → default `effective_execution_mode=serialized_multi`

Source routing is a default baseline, not immutable. User instructions or real dependencies may change effective topology; record the override/judgment. The current Web GPT + CodexPro is the executor and does not invoke Local Codex execution agents.

## Serialized MULTI

Implementation：用户未覆盖时按 sealed candidates 作为默认 lane 清单；resume/continue 跳过已完成 scope。用户指令或真实依赖可以调整顺序、合并/拆分 lane 或改变 effective mode，记录原因即可，不为 sealed candidate 形式制造假工作。

Repair：默认按 router repair candidates/issues；用户明确重定义 repair scope 时按 effective issues 执行并记录。全局 regression 只验证结果，不自动扩大业务修改范围。

## Commit ordering

1. code/test/config commits
2. global acceptance
3. capture `result_code_commit=HEAD`
4. verify prior committed execution report history is unchanged
5. append exactly one new execution record + summary at EOF
6. docs commit only that report append
7. stop this Web execution conversation; reviewer-ex runs in a fresh Web conversation

New routed Web records include audit metadata:

```yaml
execution_backend: web_codexpro
effective_execution_mode: serialized_multi
```

These fields do not affect provenance.

## Workspace

All implementation, tests and commits occur in the exact stage worktree. Plan/review/proceedings/third_party remain unchanged. No push, review or finalization.
