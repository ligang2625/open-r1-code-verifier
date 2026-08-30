# Open-R1 CodeVerifier: Technical Report

## 1. Abstract

This project studies a narrow question in code RLVR: when a model is rewarded by executable tests, does optimizing against a stronger training-time hidden verifier improve correctness on an independently held-out verifier, or does it mainly improve behavior on the verifier used during training?

Open-R1 CodeVerifier builds a reproducible 1.5B-model pipeline with three test layers: visible tests, train-hidden tests used only by the Hidden-RLVR reward, and eval-hidden tests reserved for final evaluation. The formal seed-42 study compares four methods on the same 400 problems: Base, SFT, Public-RLVR, and Hidden-RLVR. SFT raises Eval-Hidden Pass@1 from 0.1150 to 0.3775. Public-RLVR and Hidden-RLVR both obtain 0.3750, a -0.0025 paired difference from SFT with 95% CI [-0.0125, 0.0075]. On the predefined whole-pass metrics, Hidden-RLVR and Public-RLVR have identical aggregate estimates in this run.

A deterministic candidate-stratified manual review covers 25 real formal failures (Public-RLVR 10, Hidden-RLVR 10, SFT 5). The reviewed code is dominated by ordinary runtime errors, incomplete algorithms, and misunderstood problem semantics. None of the 25 reviewed candidates contains enough code-level evidence to label it as explicit verifier exploitation. This is a qualitative finding about the frozen candidate sample, not a population Reward-Hacking rate estimate.

The main scientific conclusion is therefore negative but useful: in this single training seed and fixed evaluation, GRPO did not improve independent hidden-test Pass@1 beyond the SFT checkpoint, and the stronger Hidden-RLVR reward did not produce a measurable aggregate advantage over Public-RLVR. A second training seed or full rerun is intentionally deferred until a project-level review; training-seed robustness is not claimed.

## 2. Background and Problem

Executable tests provide an attractive reward for code generation because they are objective, automatically checkable, and directly tied to program behavior. The same property also creates a generalization problem: a policy can improve on the tests exposed to the optimization loop without learning a solution that generalizes to unseen cases.

The project separates three notions that are often conflated:

1. **Visible tests** are part of the ordinary task-facing evaluation surface.
2. **Train-hidden tests** are withheld from the model response and used only by the Hidden-RLVR training reward.
3. **Eval-hidden tests** are a separate held-out verifier used for final measurement and are never used as a training reward.

This design makes it possible to ask whether reward improvements transfer across verifier boundaries. It also avoids calling every visible/eval gap “Reward Hacking.” A failing program may simply contain a normal bug. Reward Hacking is treated as a stronger qualitative claim that requires evidence of verifier-specific exploitation, such as hard-coded examples or behavior specialized to the rewarded test surface without a general algorithmic rationale.

## 3. Research Questions and Hypotheses

The formal study is organized around four questions.

**RQ1 — Does SFT materially improve the 1.5B base model on function-level Python tasks?**

The expected direction was positive because SFT teaches the response format and exposes the model to solution trajectories aligned with the target task distribution.

**RQ2 — Does Public-RLVR improve independent Eval-Hidden Pass@1 beyond SFT?**

A positive result would show that optimizing against the public/visible verifier transfers to held-out tests. A null or negative result would indicate that the additional RL stage did not add generalization under this budget.

**RQ3 — Does Hidden-RLVR outperform Public-RLVR on independent Eval-Hidden tests?**

The motivation for Hidden-RLVR is that a stronger training verifier may reduce overfitting to visible tests. The important comparison is therefore Hidden-RLVR versus Public-RLVR under the same B checkpoint, data, rollout budget, generation configuration, and final evaluation.

**RQ4 — What kinds of failures remain after SFT and RLVR, and do reviewed failures show concrete verifier exploitation?**

Automated candidate rules are used only to surface cases for human inspection. The manual review is designed to distinguish verifier exploitation from ordinary syntax, runtime, algorithmic, edge-case, or problem-understanding failures.

These questions are answered for the formal seed-42 run only. No claim in this report treats one training seed as a stable estimate of training randomness.

## 4. Dataset and Three-Layer Test Design

All four formal methods are evaluated on the same 400 function-level Python problems under a shared dataset identity. The analysis layer rejects mixed problem sets, duplicate problem IDs, mismatched dataset hashes, different evaluation seeds, different generation definitions, or inconsistent Piston verifier identities.

For each problem, the evaluator records three behavioral layers:

- **Visible Pass@1** — correctness on the visible test layer.
- **Train-Hidden Pass@1** — correctness on the training-hidden layer.
- **Eval-Hidden Pass@1** — correctness on the independent held-out layer and the primary final metric.

The separation matters because the Hidden-RLVR reward can consume train-hidden tests but never eval-hidden tests. Public-RLVR and Hidden-RLVR are evaluated by the exact same deterministic evaluation path; reward mode does not branch evaluation behavior.

The formal analysis uses problem IDs as the pairing unit. Bootstrap intervals are generated with seed 42, 10,000 resamples, 95% confidence, and **problem** as the sampling unit. This avoids treating multiple outcomes from the same problem as independent observations.

## 5. Code Execution and Safety

Generated Python is not executed directly in the training or reporting process. The project uses a strict loopback-only Piston execution contract with a pinned Python runtime and a common `CodeExecutor` interface. The control plane remains on the GTX 1660 Ti machine, while formal optimizer training and model generation that require more memory run on the RTX 4090 target.

Important safety and reproducibility properties include:

- no host `eval`/`exec` fallback for formal untrusted code;
- bounded execution and explicit status mapping for syntax, runtime, timeout, and wrong-answer outcomes;
- deterministic result schemas and per-problem identities;
- a separation between model generation and later Piston verification;
- exact-prefix resume semantics for evaluation rather than silently overwriting prior rows;
- source hashes in analysis outputs, so final tables can be traced back to formal result files.

The human failure report reproduces only model-generated extracted code and scalar/status metadata. It does not copy eval-hidden test bodies, expected outputs, reference solutions, or private SFT responses.

## 6. SFT

The SFT checkpoint B is trained from the same 1.5B base model used by the rest of the experiment. Its primary role is to create a stronger code-generation policy and a common parent for both RLVR arms.

The formal result shows a large observed improvement over Base:

- Base Eval-Hidden Pass@1: **0.1150**
- SFT Eval-Hidden Pass@1: **0.3775**
- observed difference: **+0.2625**, or **+26.25 percentage points**

SFT also raises Visible Pass@1 from 0.1225 to 0.3525 and Train-Hidden Pass@1 from 0.1175 to 0.3350. These values are descriptive formal results from the shared evaluation pipeline. The project did not preregister a Base-versus-SFT paired significance claim in the final WP8 comparison table, so the report does not attach an uncomputed significance statement to the +26.25-point observed difference.

SFT consumed 0.5215871774233367 RTX 4090 GPU-hours in the accepted formal training evidence. No auditable USD-per-GPU-hour rate was frozen, so the project intentionally does not convert this value to dollars.

## 7. GRPO and Reward Design

Both GRPO arms start from the same completed SFT B checkpoint and use the same model family, paired training definition, rollout budget, and formal evaluation path.

- **Public-RLVR C** uses the public/visible verifier reward.
- **Hidden-RLVR D** uses the train-hidden verifier reward.

The accepted formal runs each reach 300 training steps and record 2,400 rollouts. Public-RLVR generated 514,360 rollout tokens and consumed 4.012272991803669 GPU-hours; Hidden-RLVR generated 512,918 rollout tokens and consumed 3.5036727118225017 GPU-hours. Their recorded verifier-executor hours are 0.0582530611647443 and 0.06447173045885166 respectively.

A provenance qualification is essential. The seed-42 C/D formal results were accepted in WP7-c under the committed **A1 post-hoc operational-equivalence amendment**. Historical C/D execution did not strictly satisfy the original whole-run exact-code-identity/save-cadence requirement: the accepted paths included recorded code transitions and a historical save cadence different from the current canonical `save_steps=50`. The amendment preserved real execution, completed-step, artifact-authenticity, verifier-isolation, safety, and downstream hash checks, but it is not equivalent to claiming that the original preregistered operational contract was followed byte-for-byte. This disclosure remains part of the interpretation of seed-42 results.

## 8. Experimental Setup

The final formal comparison uses:

- model: `Qwen/Qwen2.5-Coder-1.5B-Instruct`;
- training seed: 42 for the accepted B/C/D evidence;
- four evaluation groups: Base A, SFT B, Public-RLVR C, Hidden-RLVR D;
- 400 unique problems per method;
- deterministic shared evaluation configuration and seed 42;
- the same dataset, split, problem order, decoding definition, and Piston verifier identity across A–D;
- problem-paired bootstrap with 10,000 resamples and 95% CI;
- RTX 4090 for formal training and target-GPU generation;
- GTX 1660 Ti control plane for workflow control, local Piston verification, aggregation, analysis, and reporting.

The final labeled analysis reuses the frozen WP8-a formal inputs without changing A/B/C/D sources or numerical definitions. The only manifest change is `manual_labels_path`, which points to the tracked 25-case human labels. A fresh production analysis and a second readback produce byte-identical 10-file output directories. Main results, paired comparisons, costs, automated candidate outputs, and training curves remain byte-for-byte identical to WP8-a.

## 9. Main Results

| Method | Visible Pass@1 | Train-Hidden Pass@1 | Eval-Hidden Pass@1 |
| --- | ---: | ---: | ---: |
| Base | 0.1225 | 0.1175 | 0.1150 |
| SFT | 0.3525 | 0.3350 | **0.3775** |
| Public-RLVR | **0.3625** | **0.3400** | 0.3750 |
| Hidden-RLVR | **0.3625** | **0.3400** | 0.3750 |

Three observations are directly supported by the formal table.

First, SFT is the dominant improvement over Base on the held-out metric in this run. Second, adding the Public-RLVR stage does **not** improve Eval-Hidden Pass@1 beyond SFT: 0.3750 versus 0.3775. Third, Hidden-RLVR has the same aggregate Pass@1 values as Public-RLVR on all three displayed layers in this formal seed.

The last point must not be overstated. Equal aggregate values in one run do not establish that the two training methods are equivalent, nor do they prove that the hidden reward is theoretically ineffective. They only establish that the predefined aggregate metrics did not separate the two accepted seed-42 policies on this 400-problem evaluation.

## 10. Statistical Analysis

The preregistered problem-paired comparisons are:

| Comparison | Eval-Hidden delta | 95% CI | Public–Eval gap delta | 95% CI | Automated candidate-proxy delta | 95% CI |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Public-RLVR − SFT | -0.0025 | [-0.0125, 0.0075] | 0.0125 | [0.0000, 0.0300] | 0.0075 | [0.0000, 0.0175] |
| Hidden-RLVR − SFT | -0.0025 | [-0.0125, 0.0075] | 0.0125 | [0.0000, 0.0300] | 0.0075 | [0.0000, 0.0175] |
| Hidden-RLVR − Public-RLVR | 0.0000 | [0.0000, 0.0000] | 0.0000 | [0.0000, 0.0000] | 0.0000 | [0.0000, 0.0000] |

The Public/SFT and Hidden/SFT Eval-Hidden intervals cross zero. The supported wording is therefore **“no evidence of an Eval-Hidden improvement over SFT in this run”**, not “GRPO significantly decreased performance.” The point estimate is -0.25 percentage points, which is small relative to the uncertainty interval.

The zero-width Hidden/Public intervals arise from the predefined per-problem whole-pass/candidate-proxy inputs being identical for these two accepted outputs. This is a property of these metrics and this formal evaluation, not a general equivalence test for the two training algorithms.

The automated candidate proxy is also not a human Reward-Hacking label. It identifies visible-pass/eval-fail behavior under a stable rule. Human inspection is required before interpreting such a case as verifier exploitation.

## 11. Reward Hacking Cases

### Selection and scope

WP8-a produced 653 deterministic failure candidates. Before any selected code was inspected, WP7-d froze a deterministic 25-case selection using namespace `wp7-d-final-manual-v1|seed42` and SHA-256 ordering within method:

- Public-RLVR: 10 cases;
- Hidden-RLVR: 10 cases;
- SFT: 5 cases.

The selection manifest SHA256 is `cd5ef448b8d4ee1ea85f364d05c90651b75267da3d431ac699ed6657b5c0e7ea`. The full per-case analysis is in [`manual_failure_analysis.md`](manual_failure_analysis.md).

Manual category counts across the frozen sample are:

- runtime error: 11;
- incomplete algorithm: 6;
- misunderstood problem: 5;
- missed edge case: 2;
- syntax error: 1.

All 25 cases received `reward_hacking=no` under the review rubric because the inspected code showed ordinary implementation/semantic failures without concrete sample constants, public-expected-value hardcoding, or other verifier-specific branches. This does **not** mean the population Reward-Hacking rate is 0%. The sample was selected from failure candidates, not randomly from all model outputs, and 25 observations are used here for qualitative diagnosis rather than prevalence estimation.

### Example A — visible success without verifier exploitation

SFT case `leetcode-minimum-value-to-get-positive-step-by-step-sum` has Visible / Train-Hidden / Eval-Hidden scores `1.0 / 0.5 / 0.0`, so the automated rule flags a strong visible/eval gap. Manual inspection finds a generic prefix-sum solution with a sign error: after tracking the maximum prefix deficit, it returns `1 - ans` instead of `1 + ans`. The visible-only success pattern is real, but the code-level explanation is a normal arithmetic bug rather than visible-test hardcoding.

### Example B — train-hidden success without a general algorithm

Public-RLVR case `taco-21868` has `0.0 / 1.0 / 0.5`. The code implements a malformed checksum transformation that applies the same operation to every digit rather than an alternating transform. It happens to satisfy the train-hidden layer in this record, but there is no obvious verifier-specific constant or branch. The conservative manual label is therefore incomplete algorithm, not Reward Hacking.

These examples show why automated verifier-gap candidates and human Reward-Hacking conclusions must remain separate fields.

## 12. Failed Experiments and Negative Results

The most important negative result is scientific rather than infrastructural: after a strong SFT improvement, the accepted seed-42 GRPO runs did not improve the independent held-out metric. Public-RLVR and Hidden-RLVR both finish at 0.3750 Eval-Hidden Pass@1 versus SFT at 0.3775.

The manual review also weakens a tempting post-hoc story that “GRPO failed because it learned obvious test hacks.” In the 25 frozen candidates, the dominant explanations are normal coding failures: invalid indexing, undefined helpers, wrong data structures, incomplete algorithms, and misread task semantics. It remains possible that verifier exploitation exists elsewhere in the 653-candidate pool or outside the candidate rule, but this review does not provide evidence for claiming it as the primary mechanism behind the aggregate result.

Operationally, the WP7-c seed-42 C/D evidence required the A1 post-hoc amendment because the historical accepted path did not maintain the original whole-run exact-code/save-cadence contract. That history is preserved rather than rewritten. Future replication, if run, should use the current canonical configuration and immutable operator provenance from the start.

## 13. Compute and Cost

| Method | GPU | GPU-hours | Rollouts | Generated tokens | Executor-hours | USD estimate |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| SFT | RTX 4090 | 0.5215871774 | — | — | — | not estimated |
| Public-RLVR | RTX 4090 | 4.0122729918 | 2,400 | 514,360 | 0.0582530612 | not estimated |
| Hidden-RLVR | RTX 4090 | 3.5036727118 | 2,400 | 512,918 | 0.0644717305 | not estimated |

The project records measured GPU time and GRPO execution volume but intentionally leaves dollar cost null. No auditable historical GPU-hour price was frozen before analysis, and inserting a market or cloud price after the experiment would create a misleading precision that is not part of the evidence.

The hardware split is also part of the cost design: large optimizer/model-generation work runs on the RTX 4090, while orchestration, Piston verification, aggregation, bootstrap analysis, and report generation remain on the GTX 1660 Ti control plane.

## 14. Limitations

1. **Single training seed.** Only seed 42 has been executed for the formal GRPO comparison. The current results do not establish robustness to training randomness. The project-level replication requirement remains pending.
2. **WP7-c A1 operational qualification.** Seed-42 C/D were accepted under a post-hoc operational-equivalence amendment rather than strict original whole-run code/save-cadence compliance. This is a provenance limitation even though downstream artifact identities and results were revalidated.
3. **Model and dataset scope.** The formal claim covers one 1.5B model family and one fixed 400-problem evaluation set. It should not be generalized to larger models, other languages, or broader coding distributions without new evidence.
4. **Manual sample design.** The 25 reviewed cases are a deterministic candidate-stratified qualitative sample. They are not a random sample of the full 400 problems and cannot estimate a population Reward-Hacking rate.
5. **Candidate definition.** The automated proxy is intentionally simple and can surface ordinary failures. It does not detect every possible verifier-exploitation strategy and is not itself a human label.
6. **Statistical scope.** The paired intervals quantify per-problem uncertainty for the fixed accepted policies; they do not estimate between-training-seed variance.
7. **Cost scope.** GPU-hours are measured, but no auditable USD rate was frozen, so monetary cost is left unestimated.
8. **Negative mechanism evidence.** Manual failures suggest ordinary coding errors are common, but the sample is insufficient to prove why GRPO did not improve aggregate Eval-Hidden performance.

## 15. Future Work

The immediate next action is deliberately **not** an automatic second-seed run. With the manual analysis, final evidence snapshot, README, and technical report complete, the project can be reviewed end-to-end before spending additional target-GPU time.

If that review concludes that stronger research-grade robustness is needed, the cleanest follow-up is a preregistered second training seed or complete paired C/D rerun that:

- changes only training randomness while keeping B/data/evaluation definitions fixed;
- runs both Public and Hidden arms rather than selectively rerunning one arm;
- uses the current canonical save cadence and immutable operator provenance;
- reports the second run regardless of direction;
- does not seed-shop after seeing the result.

Other useful follow-ups include expanding the human review with a separately preregistered sampling design, testing a larger model, and studying reward formulations that provide denser algorithmic feedback without exposing the final eval verifier.

## 16. Reproducibility Statement

The numerical authority for this report is [`final_evidence.json`](final_evidence.json), whose current SHA256 is `8431496e3978788348a9ab0373133cb06ec2d28edd581d6c4d42df62631cfada`.

Key provenance:

- replacement WP7-d plan commit: `b4c58abac5669dacfede6581917b93a086acc95c`;
- manual-analysis commit: `d75d165812f1014c2175ef934ea7aae1c80c0ee3`;
- WP8-a frozen input manifest SHA256: `118093d5befbd43bdd0e08527847d23f40626284f8e73b49dbe2df033d1e0da8`;
- WP8-a source inventory SHA256: `b79718d096be441b2d3d0e45b88b4b95ce1d458696617dafd80f1b11cfca18f1`;
- final labeled manifest SHA256: `c38ba8cee584a150ac926946f0cc3ab67ac1c6c70f58e57f7821ef0b60bfd51b`;
- final `main_results.csv` SHA256: `02030685f05f0ed04d8e007cc0eb1a4455aacfbcbe6f505c13afd8849e63804e`;
- final `paired_comparisons.csv` SHA256: `0ae767e7e9e918d9fe2109a7f65b4aca39b4446c615beb694eb175adb80a3eed`;
- final `report_data.json` SHA256: `d3953fc520ea5daf302a3a7c5971a1ddf5dd96b80ea7d02e5be07a8d87f21897`;
- manual selection namespace: `wp7-d-final-manual-v1|seed42`;
- manual selection SHA256: `cd5ef448b8d4ee1ea85f364d05c90651b75267da3d431ac699ed6657b5c0e7ea`;
- manual labels SHA256: `052dfcbed63b39934cc0886de4ea3adb8fb19a794b35b466d78796a064b71668`;
- manual case report SHA256: `c4cc12d86dbe99d990020d2122e15c2fe0bf3f41c6821e43240e044806d18406`.

The final labeled analysis was run with the production CLI against a fresh output directory:

```bash
.venv/bin/code-verifier analyze-results \
  --manifest /path/to/formal-analysis-with-manual-labels.yaml \
  --output-dir /path/to/fresh-analysis-output
```

The manifest must bind the accepted Base/SFT/Public/Hidden evaluation and training artifacts and set `manual_labels_path` to this repository's `report/manual_labels.csv`. Bootstrap remains seed 42 / 10,000 resamples / 95% confidence / problem-level sampling. A second fresh run with the same manifest reproduced all 10 output files byte-for-byte.

The repository-level claim remains intentionally scoped as `single_training_seed_seed42`; `replication_status` is `pending_second_seed_or_full_rerun` until a later project review explicitly decides otherwise.
