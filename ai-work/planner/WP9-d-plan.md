# WP9-d Plan — Optimized GRPO Runtime then Recipe A

## Status

Prepared on 2026-09-07 from integrated `main` commit `11d48b244ed9fa6b2556e1970755992fc6b8827a` on branch `feat/wp9-d`.

WP9-d is capability-first. Runtime throughput is optimized before Recipe A; exact trajectory/output parity with WP9-c is not required.

## P0 — Runtime implementation

1. GRPO rollout backend: TRL v0.18 colocated vLLM.
   - `use_vllm=true`
   - `vllm_mode=colocate`
   - `vllm_gpu_memory_utilization=0.4`
   - tensor parallel size 1
   - retain `num_generations=8`, train batch 1, grad accumulation 8, reward workers 8.
2. Eval generation: retain logical `batch_size=4`, load two independent model instances, give each a dedicated CUDA stream, execute two b4 chunks concurrently, and persist results in canonical problem order.
3. Verification remains controller/Piston with 64 workers.

## P1 — 4090 bounded systems validation before full training

Do not start the 1200-step run until all of the following pass on the RTX 4090. Use the paired one-step systems configs `configs/grpo/wp9d-runtime-smoke-{public,hidden}.yaml`; they are not capability-result arms.

- vLLM colocate initializes from the frozen B lineage;
- one bounded GRPO optimizer update completes with reward execution and current-policy weight synchronization;
- checkpoint save/load path remains valid;
- no CUDA OOM and adequate memory headroom is recorded;
- rollout wall time, GPU utilization, and peak memory are recorded;
- dual-b4 eval generation completes a bounded subset with two concurrent workers, correct total/order, no generation errors, and recorded wall time/utilization/memory.

Exact output parity with WP9-c is diagnostic only, not a gate.

## P2 — Freeze WP9-d runtime and refresh benchmark baseline

After P1 succeeds:

- freeze exact handoff commit/runtime parameters;
- regenerate and verify frozen B on canonical eval400 using `batch_size=4`, `parallel_generators=2`, seed 42, deterministic Pass@1;
- this becomes the WP9-d B comparison baseline;
- historical WP9-c B/C/D remain context only.

## P3 — Recipe A

Run paired Public/Hidden arms independently from frozen B with:

- 1200 optimizer steps;
- LR `5e-6`;
- `constant_with_warmup`, warmup ratio 0.05;
- beta 0.01;
- LoRA r16 / alpha32 / dropout0.05;
- k=8, train batch1, grad accumulation8;
- vLLM colocate runtime from P0/P1;
- checkpoint every 100 steps.

Evaluate canonical eval400 at steps 300/600/900/1200 using the frozen WP9-d dual-b4 runtime. Select checkpoint by Eval-Hidden Pass@1, then average hidden-test pass, runtime error, parse error, then earlier step.

## P4 — Sequential optimization after A

Use eval400 directly for selection. If A remains weak:

1. Recipe B: LR `1e-5`, otherwise frozen A runtime/recipe.
2. Recipe C: beta `0.005` with LR `1e-5`, otherwise frozen.
3. Only after A/B/C consider LoRA rank or larger effective generation/update batches.

Every attempted recipe/checkpoint remains in the report; eval400 is explicitly a reused tuning benchmark.
