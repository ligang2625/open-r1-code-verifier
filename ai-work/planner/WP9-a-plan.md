# WP9-a 实施计划（Refresh data foundation）

## 1. 元信息

| 项 | 值 |
|---|---|
| stage_id | `WP9-a` |
| stage_profile | `development` |
| control_plane_hardware | `GTX 1660 Ti (6GB)` |
| target_hardware | `GTX 1660 Ti (6GB)` |
| evidence_class | `engineering` |
| development_terminal | `false` |
| 目标 WP | `WP9`：GRPO Refresh data foundation |
| 规格依据 | `PROJECT_SPEC_GRPO_Refresh.md` §6.1–§6.7、§13.1、§14.1、§16、§17.1；`PROJECT_SPEC_Open-R1_CodeVerifier.md` §7、§19、§20.0、§21.3、§29 |
| 前置状态 | `proceedings.md` 最新 decision record 明确 WP0–WP8 已收口，旧 second-seed replication deferred/not cancelled，当前 active track 为 WP9，唯一 next dependency-ready stage 为 `WP9-a` |
| `planning_base_commit` | `8410afe595db32a01a0e7f3b1ab8da4548b4482c` |
| proposed branch | `feat/wp9-a` |
| proposed worktree | `.worktrees/wp9-a` |
| final plan path | `ai-work/planner/WP9-a-plan.md` |
| execution report path | `ai-work/executor/WP9-a-executor.md` |
| review path | `ai-work/reviewer/WP9-a-review.md` |
| plan lifecycle | planner-ex handoff → `stage-lifecycle bootstrap_plan` → committed plan seal |

当前 planning-time guard：main clean，只有主 worktree，`.ai-bridge/current-plan.md` 在 handoff 前不存在；`main` 相对 `origin/main` ahead 82。未合并 archive branches 属历史归档；两个未链接的 `chore/*` workflow/Piston maintenance branches 不是 active stage，不阻塞本 WP9-a。planning-time engineering baseline：`make lint` PASS；数据 focused suite 123/123 PASS；`make test` 1030 passed / 3 个显式 real-Piston opt-in skips。

## 2. 目标与范围

### 目标（Refresh addendum）

在不启动真实 calibration/GRPO/正式 C2/D2 的前提下，为 refreshed GRPO 建立可审计、可重复的数据基础：外部 candidate source ingestion/provenance、跨 source + SFT/evaluation exact/near dedup、SFT/GRPO overlap 控制、canonical 三层测试 materialization，以及严格隔离的 Public/Hidden training views。

### 本 stage 必须交付

- 外部 source/revision/license/provenance 的严格配置与 machine-readable snapshot manifest；
- candidate raw-record identity/fingerprint 与 source-specific schema mapping；
- deterministic exact + near dedup，覆盖 cross-source、SFT、validation、当前 400 project-test、external-eval references；
- canonical refresh candidate pool：默认 10,000 题，其中 7.5%（750）直接从已冻结 SFT train split deterministic 选取作为允许 overlap，92.5%（9,250）来自经 hard-filter 的新外部 candidate；hard max 15% 始终 fail closed；
- 新外部题转换为项目 `CodeProblem` canonical schema，三层测试全部非空；`>=8` 测试题按 2 visible / 3 train-hidden / 其余 eval-hidden 分配；4–7 测试题允许 materialize 但必须标记 `quality_gate_required=true`，不得伪造或合成测试；少于 4 个独立 fixed-output test 的记录拒绝；
- Public/Hidden training JSONL 使用同一 problem IDs、同一 frozen order；Public 只含 visible tests，Hidden 可再含 train-hidden，二者都绝不含 eval-hidden/reference solution/SFT response/starter code；
- exact/near dedup report、SFT overlap report、validation/project-test/external-eval zero-overlap report、test-layer leakage audit、root manifest + artifact hashes；
- `prepare-refresh-data` / `check-refresh-data` CLI 和 deterministic readback；
- 真实 pinned-source engineering materialization evidence，输出放在 control-plane data root/临时数据目录，不把大数据加入 Git。

### 范围外

- 不运行冻结 B 的真实 generation/calibration；
- 不实现/运行 `num_generations=8` GRPO、pilot、正式 C2/D2；
- 不做 400 题重新 evaluation；
- 不生成或修复 synthetic tests；
- 不修改 reward、verifier/executor semantics、GRPO trainer、Open-R1 submodule；
- 不把 WP9-a candidate pool 称为 WP9-c 最终 calibrated active pool；`dual-informative >=70%`、zero-variance gate 属后续 WP9-b/WP9-c。

## 3. 前置条件与约束

- `proceedings.md:831-841` 是 active routing authority：不得把旧 second-seed replication 提前到 WP9-a 之前。
- 必须同时遵守主 spec 和 `PROJECT_SPEC_GRPO_Refresh.md`；WP9 冲突默认以 Refresh addendum 为准。
- `third_party/open-r1/` 只读，本 stage 不需要改它。
- 复用现有 `CodeProblem` / `TestCase`、`build_training_record`、training-field whitelist、JSON strict loader、stable hashes、atomic JSONL writer；不要复制第二套 schema/leakage implementation。
- 外部候选源只在 exact revision、非空 license/provenance、实际 schema 和 verifier semantics 被确认后启用。source card 中“候选”不等于批准导入。
- planning-time 外部 schema probe 已确认：DeepCoder dataset 是 MIT、具有 `primeintellect`/`taco` 等 configs，card 宣称每题至少 5 tests；PrimeIntellect 直接源主要是 stdin/stdout verifier records；OpenThoughts CodeContests 是 Harbor `path + task_binary` archive。为避免在本 stage 引入 Harbor parser/新 sandbox semantics，默认启用源固定为 `agentica-org/DeepCoder-Preview-Dataset@177913a7bd43791646ef6a43645caa3c871ab3db` 的 `primeintellect/train` 与 `taco/train` 两个 config；若真实 post-filter 数量不足 9,250，新 source 不能临时猜 schema/放宽 gate，必须停下并 replan/source-amendment。
- external-eval exclusion 默认至少包含 `evalplus/humanevalplus@aa0d916268b1c17e84e881e9bd460508dd2fd308`（Apache-2.0，164 题）作为 exclusion-only reference；这只建立 leakage exclusion，不在 WP9-a 运行 final metric。
- project SFT/validation/test references 来自 executor 显式传入的已冻结 prepared dataset root；不得在 tracked config 中硬编码机器绝对路径。
- 新 stdio 题只允许 fixed-output、non-interactive、无 special/custom-judge 语义的记录。映射为函数合同 `def solve_io(input_text: str) -> str:`；当前 executor harness 已支持 scalar input → 单参数函数调用，但 WP9-a 不改 harness。原题面必须加明确 interface note：把完整 stdin 文本作为 `input_text`，返回 exact stdout 文本，不调用宿主 stdin/stdout。无法等价映射的 candidate 记录为 reject reason，不做近似猜测。
- near-dedup protocol 本 stage 冻结为：NFKC/whitespace-normalized problem text + normalized function/I/O contract 的 token 5-gram set；Jaccard `>=0.90` 视为 accepted near duplicate。必须使用 deterministic、不会因为输入顺序变化而改变结果的 high-threshold prefix-index + exact-Jaccard verification，不做 O(N^2) 全对全，也不使用 probabilistic-only LSH 作为最终判定。
- hard evaluation overlap 优先级最高：任何 candidate 与 validation/project-test/external-eval exact 或 accepted-near match 都拒绝。外部 candidate 与 SFT exact/near match 也拒绝作为“new”；允许的 7.5% overlap 只从冻结 SFT train canonical records直接 deterministic 选择，因此 overlap 分子完全可审计。

### Execution preflight（首次业务修改/commit 前）

1. `git rev-parse HEAD` 必须等于 lifecycle seal 后的 `plan_commit`，worktree clean；不得在 main 直接实现。
2. `uv run python -c "import datasets, yaml; import code_verifier"` 成功；不新增 dependency 作为默认方案。
3. 读取用户/环境提供的 formal prepared dataset root，`canonical/problems.jsonl` 必须存在并通过现有 canonical loader；train/validation/test 三 split 均存在，train 为 SFT overlap source，test 为当前 project-test exclusion source。
4. 使用 `datasets.load_dataset(..., revision=<full sha>, streaming=True)` 对 DeepCoder `primeintellect/train`、`taco/train` 各读取 bounded 1–3 rows，仅打印字段名/类型，不打印题目/test 内容；revision 必须精确解析，dataset card/license 与计划假设一致。对 HumanEvalPlus exclusion reference 同样验证 revision/schema。
5. 在临时目录验证 control-plane data/cache 可写且有足够空间容纳约 10k canonical pool + manifests；不要创建 tracked data artifacts。
6. 任一 source revision/schema/license、formal reference dataset、import 或存储 prerequisite 不满足：停止 execution，保持 `HEAD == plan_commit`，修复环境或 replan 后重试；不得先提交部分实现。

本 stage 是纯 development/control-plane data work，不存在 24GB operator gate。

## 4. 实施步骤

### 步骤 1：公开 canonical loader，并建立 refresh source/provenance 类型

**目标文件**：
- `src/code_verifier/data/prepare.py`
- 新增 `src/code_verifier/data/refresh_sources.py`
- `tests/unit/data/test_prepare.py`
- 新增 `tests/unit/data/test_refresh_sources.py`

**新增 / 修改符号**：
```python
def load_canonical_jsonl(path: Path) -> list[CodeProblem]:
    ...

@dataclass(frozen=True)
class RefreshSourceSpec:
    source_name: str
    dataset_id: str
    revision: str
    config_name: str | None
    split: str
    declared_license: str
    adapter: Literal["deepcoder"]

@dataclass(frozen=True)
class RefreshSourceSnapshot:
    source_name: str
    dataset_id: str
    revision: str
    config_name: str | None
    split: str
    declared_license: str
    scanned_rows: int
    accepted_rows: int
    projection_fingerprint_sha256: str

@dataclass(frozen=True)
class RefreshCandidate:
    candidate_id: str
    source_name: str
    source_record_id: str
    prompt: str
    function_name: str
    function_signature: str
    tests: tuple[TestCase, ...]
    source_url_hash: str | None
    raw_reference_solution_hash: str | None
    difficulty: Literal["easy", "medium", "hard", "unknown"]
    category: tuple[str, ...]
    raw_record_sha256: str

@dataclass(frozen=True)
class OverlapReference:
    reference_id: str
    reference_class: Literal["sft", "validation", "project_test", "external_eval"]
    prompt: str
    function_signature: str | None
    source_url_hash: str | None
    reference_solution_hash: str | None
    test_fingerprint: str | None

def load_refresh_source(
    spec: RefreshSourceSpec,
    *,
    cache_dir: Path | None,
) -> tuple[RefreshSourceSnapshot, list[RefreshCandidate]]:
    ...

def load_humanevalplus_references(
    *,
    dataset_id: str,
    revision: str,
    cache_dir: Path | None,
) -> tuple[RefreshSourceSnapshot, list[OverlapReference]]:
    ...
```

**主要功能**：
- 把 `prepare.py` 私有 canonical JSONL loader 提升为受测试的公有函数，现有 `check_prepared_data` 改用它，不保留重复 loader。
- DeepCoder adapter 必须对 `primeintellect`/`taco` preflight 实际 schema做 exact mapping；只接纳 fixed-output stdin/stdout tests。`tests` 字段解析必须 strict，duplicate keys/非有限 JSON/无法识别结构直接 reject；不能 `eval()`。
- 每条 accepted candidate 生成稳定 `candidate_id`（source name + pinned dataset/config/split + source record identity/row index 的 canonical hash），保存 raw-record hash；source snapshot 的 projection fingerprint 是按 stable candidate scan order 聚合 raw-record hashes 得到的 SHA256，作为 consumed projection 的 dataset fingerprint。
- source record 的 raw reference solution 只保存 hash/provenance，不把 stdin-style solution错误塞进 canonical function `reference_solution`。
- HumanEvalPlus loader 只提取 dedup 所需 prompt/entry-point/reference hash，不把其 tests 或 solution进入任何训练 artifact。

**测试方案**：source fixture 覆盖合法 DeepCoder 两种 row schema、malformed tests、interactive/special judge、少于 4 tests、unknown keys/schema drift、stable candidate ID/raw hash、license/revision validation、HumanEvalPlus reference extraction。

### 步骤 2：新增 refresh test-layer splitter 与 stdio→function canonicalization

**目标文件**：
- `src/code_verifier/data/split_tests.py`
- `src/code_verifier/data/refresh_sources.py`
- `tests/unit/data/test_split_tests.py`
- `tests/unit/data/test_refresh_sources.py`

**新增符号**：
```python
def split_refresh_test_cases(
    tests: Sequence[TestCase],
    *,
    problem_id: str,
    seed: int,
) -> tuple[tuple[TestCase, ...], tuple[TestCase, ...], tuple[TestCase, ...]]:
    ...

def canonicalize_refresh_candidate(
    candidate: RefreshCandidate,
    *,
    seed: int,
) -> tuple[CodeProblem, bool]:
    """Return canonical train problem plus quality_gate_required."""
```

**主要功能**：
- 复用现有 unique-test hash；同一 candidate 的 normalized test 重复直接拒绝。
- deterministic shuffle namespace 与老 WP1 分离（例如 `wp9a-refresh-tests-v1|seed|problem_id`），避免未来 refactor 改变 layer identity。
- `len(tests) >= 8`：固定 2 visible、3 train-hidden、剩余全部 eval-hidden；满足 addendum 的 2+/3+/3+。
- `4 <= len(tests) < 8`：固定 2 visible，剩余中先保证 train-hidden/eval-hidden 各至少 1，再尽量平衡；返回 `quality_gate_required=true`，后续 WP9-c 在进入 formal active pool 前必须独立 gate。
- `<4`：不得 canonicalize。
- stdio mapping 的 canonical function 固定 `solve_io(input_text: str) -> str`，测试 input/expected 均为 JSON string；prompt 加明确 interface note但 dedup 使用原始 problem text，避免 wrapper boilerplate 导致虚假近重复。
- canonical refresh external problems统一 `split="train"`、`reference_solution=None`、`sft_response=None`；metadata 保留 source/difficulty/license/source_url_hash。

**测试方案**：4/5/7/8/12 tests 的层数、seed repeatability、不同 seed变化、no duplicate layers、quality flag、scalar string input contract、prompt 不含 hidden/eval tests。

### 步骤 3：实现 deterministic exact/near dedup 与 overlap classification

**目标文件**：
- 新增 `src/code_verifier/data/refresh_dedup.py`
- `src/code_verifier/data/deduplicate.py`（只复用/暴露必要已有 hash helper；不要复制 normalize_text）
- 新增 `tests/unit/data/test_refresh_dedup.py`

**新增符号**：
```python
@dataclass(frozen=True)
class RefreshDedupPolicy:
    token_ngram_size: int
    near_jaccard_threshold: float

@dataclass(frozen=True)
class RefreshFingerprint:
    record_id: str
    record_class: Literal["candidate", "sft", "validation", "project_test", "external_eval"]
    normalized_statement_hash: str
    contract_hash: str | None
    source_url_hash: str | None
    reference_solution_hash: str | None
    test_fingerprint: str | None
    token_ngrams: tuple[str, ...]

@dataclass(frozen=True)
class RefreshDedupDecision:
    candidate_id: str
    retained: bool
    rejection_reason: str | None
    overlap_class: str
    matched_record_id: str | None
    similarity: float | None

def build_refresh_fingerprint(...) -> RefreshFingerprint:
    ...

def find_near_duplicate_matches(
    queries: Sequence[RefreshFingerprint],
    references: Sequence[RefreshFingerprint],
    *,
    policy: RefreshDedupPolicy,
) -> dict[str, tuple[str, float]]:
    ...

def classify_refresh_candidates(
    candidates: Sequence[RefreshCandidate],
    *,
    sft_references: Sequence[OverlapReference],
    validation_references: Sequence[OverlapReference],
    project_test_references: Sequence[OverlapReference],
    external_eval_references: Sequence[OverlapReference],
    policy: RefreshDedupPolicy,
) -> list[RefreshDedupDecision]:
    ...
```

**判定顺序/规则**：
1. exact source/in-source identity、normalized statement+contract、source URL、reference-solution hash、test fingerprint 能证明 duplicate 时先 exact classify；
2. near path 对 normalized raw problem statement + contract 建 token 5-grams；阈值固定 `0.90`；使用 deterministic prefix index 做候选 pruning，最终必须 exact Jaccard 复核；
3. validation/project-test/external-eval match（exact 或 near）永远 hard reject；
4. external candidate 与任何 SFT match（exact/near）reject 为 `incidental_sft_overlap`，因为本实验允许 overlap 只由显式 SFT reuse subset提供；
5. external candidates 之间 cross-source exact/near duplicate只保留 deterministic representative，优先级由 tracked source order + candidate_id hash 决定，其余写 matched canonical candidate；
6. 所有 decision 都写 machine-readable reason/class/match/similarity/source identity。

**复杂度要求**：不得实现 30k × 30k 全 pair scan。单测用计数/instrumentation 证明 high-threshold prefix index只对候选 pair做 exact Jaccard，并对输入顺序 permutation 结果不变。

### 步骤 4：实现 deterministic overlap quota、pool selection 与 canonical/Public/Hidden materialization

**目标文件**：
- 新增 `src/code_verifier/data/refresh.py`
- `src/code_verifier/data/leakage_checks.py`（仅在需要公用 helper 时小改）
- 新增 `tests/unit/data/test_refresh.py`

**新增符号**：
```python
@dataclass(frozen=True)
class RefreshSelectionConfig:
    target_size: int
    sft_overlap_fraction: float
    sft_overlap_hard_max: float
    token_ngram_size: int
    near_jaccard_threshold: float

@dataclass(frozen=True)
class RefreshDataConfig:
    sources: tuple[RefreshSourceSpec, ...]
    external_eval_dataset_id: str
    external_eval_revision: str
    selection: RefreshSelectionConfig

@dataclass(frozen=True)
class RefreshPreparationSummary:
    total_candidates_scanned: int
    external_candidates_retained: int
    selected_problems: int
    sft_overlap_count: int
    sft_overlap_fraction: float
    quality_gate_required_count: int
    canonical_jsonl: Path
    public_grpo_jsonl: Path
    hidden_grpo_jsonl: Path
    root_manifest: Path

def load_refresh_data_config(path: Path) -> RefreshDataConfig:
    ...

def deterministic_stratified_select(
    candidates: Sequence[object],
    *,
    count: int,
    seed: int,
    namespace: str,
) -> list[object]:
    ...

def select_refresh_pool(
    *,
    sft_problems: Sequence[CodeProblem],
    new_candidates: Sequence[RefreshCandidate],
    config: RefreshSelectionConfig,
    seed: int,
) -> tuple[list[CodeProblem], list[dict[str, JsonValue]]]:
    ...
```

**选择协议**：
- tracked default：`target_size=10000`、`sft_overlap_fraction=0.075`、`sft_overlap_hard_max=0.15`、5-gram、Jaccard 0.90。
- overlap count = 750；从冻结 formal SFT `train` split 以 source+difficulty strata 的 largest-remainder quota + namespace hash排序 deterministic 选取；绝不从 validation/test选。
- new count = 9,250；仅从 `classify_refresh_candidates` retained external candidates中，以 source+difficulty strata proportional allocation + stable hash排序 deterministic 选取。
- 任一 population 数量不足时 fail closed并报告每个 source/difficulty/rejection reason计数；不得通过放宽 evaluation overlap、near threshold、test-layer isolation或15% hard max凑数。
- canonical problem order用独立 namespace hash冻结，Public/Hidden exact复用该 order；生成 machine-readable `problem_order.jsonl`。
- SFT reuse canonical record可保留审计用 reference_solution/sft_response于 canonical 文件，但 Public/Hidden training views必须由现有 `build_training_record` whitelist生成，确保这些字段不进入训练。为减小误用风险，selection manifest必须标注 `overlap_origin=sft_reuse`。
- external canonical problems的 `sft_response/reference_solution` 均为 null。

### 步骤 5：实现 all-or-nothing refresh artifact pipeline、root manifest 与 strict readback

**目标文件**：
- `src/code_verifier/data/refresh.py`
- `src/code_verifier/data/prepare.py`（复用 `write_jsonl`）
- `tests/unit/data/test_refresh.py`

**新增符号**：
```python
def prepare_refresh_data(
    config: RefreshDataConfig,
    *,
    seed: int,
    reference_dataset_dir: Path,
    source_cache_dir: Path | None,
    output_dir: Path,
) -> RefreshPreparationSummary:
    ...

def check_refresh_data(
    dataset_dir: Path,
    *,
    reference_dataset_dir: Path,
) -> RefreshPreparationSummary:
    ...
```

**输出 contract**（相对 `output_dir`）：
- `manifest/source_snapshots.json`
- `manifest/reference_snapshots.json`
- `manifest/dedup_decisions.jsonl`
- `manifest/selection.jsonl`
- `manifest/problem_order.jsonl`
- `reports/dedup_summary.json`
- `reports/sft_overlap.json`
- `reports/evaluation_overlap.json`
- `reports/test_layer_leakage.json`
- `canonical/problems.jsonl`
- `training/public_grpo.jsonl`
- `training/hidden_grpo.jsonl`
- `refresh_manifest.json`

**root manifest** 必须记录：schema/version、seed、完整 source specs/revisions/licenses/config/split、source projection fingerprints、formal reference canonical SHA256、external-eval identity、dedup policy、selection protocol、artifact relative path/row count/SHA256、selected IDs/order hash、overlap counts、quality-gate-required counts。禁止 absolute path、hostname、timestamp 进入决定性 manifest，以便同输入/seed byte-for-byte reproduce。

**strict readback**：
- 重载 canonical，逐题 `validate_problem` + `check_no_test_layer_overlap`；只允许 `split=train`，IDs unique；不调用旧 `check_dataset` 的“三 split 都必须存在”规则。
- 重载 Public/Hidden artifact，用现有 `check_training_record`；Public/Hidden IDs和顺序必须完全一致并等于 canonical order。
- Public bytes/objects 不得出现 `train_hidden_tests`/`eval_hidden_tests`/`reference_solution`/`sft_response`；Hidden 不得出现 `eval_hidden_tests`/`reference_solution`/`sft_response`。
- 用 reference snapshot + stored fingerprints重算 overlap：selected pool对 validation/project-test/HumanEvalPlus exact/near = 0；SFT overlap只允许 `selection.jsonl`中750个 explicit reuse IDs；总 overlap精确 7.5%，且 <=15%。
- 重算所有 artifact SHA/root manifest；任一 tamper、row reorder、type drift、hash mismatch fail closed。
- 使用 temporary sibling directory + atomic rename；失败不留下半成品 output。

### 步骤 6：增加 WP9-a CLI、tracked protocol config 与最小文档

**目标文件**：
- `src/code_verifier/cli.py`
- 新增 `configs/data/refresh.yaml`
- `tests/unit/test_cli.py`
- `README.md`

**CLI**：
```text
code-verifier prepare-refresh-data \
  --config configs/data/refresh.yaml \
  --reference-dataset-dir <formal-prepared-root> \
  --source-cache-dir <cache-root> \
  --seed 42 \
  --output-dir <fresh-output>

code-verifier check-refresh-data \
  --dataset <fresh-output> \
  --reference-dataset-dir <formal-prepared-root>
```

**新增 handler**：
```python
def _prepare_refresh_data(args: argparse.Namespace) -> int:
    ...

def _check_refresh_data(args: argparse.Namespace) -> int:
    ...

def _print_refresh_summary(action: str, summary: RefreshPreparationSummary) -> None:
    ...
```

- `build_parser()` 文档更新到 WP0–WP9；不改变旧 `prepare-data` / `check-data` 语义。
- `configs/data/refresh.yaml` 固定 DeepCoder两个 enabled source、full revision、MIT license、HumanEvalPlus exclusion identity、10000/0.075/0.15/5/0.90 protocol；机器路径只通过 CLI传入。
- 不新增 `pyproject.toml` dependency；如果实现发现现有 stdlib + datasets 无法可靠完成协议，必须先停下 replan，而不是在 executor 中临时引入包。
- README 只增加 WP9-a data preparation/check命令、artifact说明和“不是 calibration/final active pool”边界，不重写历史 A–D结论。

### 步骤 7：WP9-a 集成 fixture、真实 pinned-source engineering run 与 acceptance evidence

**目标文件**：
- 新增 `tests/fixtures/wp9a/`：小型 DeepCoder-like prime/taco rows、formal reference canonical fixture、HumanEvalPlus-like references，包含 deliberate cross-source dup、near dup、SFT dup、validation/test/external-eval dup、4–7 test reserve、8+ test ready rows。
- 新增 `tests/integration/test_wp9a_refresh_data_pipeline.py`
- execution report `ai-work/executor/WP9-a-executor.md`

**集成断言**：
- fixture pipeline end-to-end prepare→check；same seed两次 canonical/views/manifests byte identical；
- deliberate validation/project-test/external-eval exact/near candidate全部 reject；incidental external-SFT dup reject；允许 overlap只来自 explicit SFT reuse；
- Public/Hidden exact same IDs/order；字段隔离与 eval-hidden byte scan通过；
- tampered manifest/hash/order/hidden field均被 `check-refresh-data` 拒绝；
- no output on failed atomic run。

**真实 engineering materialization**：
- 在 control plane 使用 `configs/data/refresh.yaml`、formal prepared dataset root、pinned DeepCoder/HumanEvalPlus revisions运行一次 fresh `prepare-refresh-data` 到 `$CODE_VERIFIER_DATA_ROOT` 或等价外部数据目录；随后 fresh `check-refresh-data`。
- executor report只提交 secret-free small evidence：source/revision/license/config identities、reference canonical SHA、output root logical name、root-manifest SHA、row/count summary、overlap summary、quality-gate-required count、Public/Hidden order hash、命令与退出码；大 JSONL/data cache不进 Git。
- 如果 post-filter external new pool <9,250 或 source schema/license不满足计划：stage保持未完成并报告 blocker；不得降低 gate。

## 5. 总体验收与测试计划

### 单元/集成

```bash
uv run pytest \
  tests/unit/data/test_refresh_sources.py \
  tests/unit/data/test_refresh_dedup.py \
  tests/unit/data/test_refresh.py \
  tests/unit/data/test_split_tests.py \
  tests/unit/data/test_prepare.py \
  tests/unit/test_cli.py \
  tests/integration/test_wp9a_refresh_data_pipeline.py
make lint
make test
```

### Real data engineering gate（GTX 1660 Ti / CPU）

- pinned source snapshots可解析；
- canonical selected pool恰好 10,000 unique problems；
- explicit SFT reuse = 750 / 10,000 = 7.5%；hard max 15%显式通过；new external = 9,250；
- selected pool与 validation/project-test/HumanEvalPlus exact+near overlap = 0；
- Public/Hidden IDs/order完全相同；训练 artifacts无 eval-hidden，Public无 train-hidden；
- 每题三层非空且层间无 normalized test duplicate；低于8 tests的题被明确计数/标记，不伪装为 quality-ready；
- source revision/license/provenance和 consumed-projection fingerprint完整；
- fresh `check-refresh-data`成功，same seed rerun决定性 artifacts byte-identical；
- 不产生 calibration generations、B numerical metrics、GRPO checkpoints、C2/D2或400题 evaluation数值。

### 最终标准

- [ ] Refresh §6 data design和§13.1中属于 pre-calibration data foundation的 artifacts全部具备
- [ ] SFT overlap exact 7.5%，且 <=15%
- [ ] validation/project-test/external-eval overlap = 0（exact + accepted near）
- [ ] Public/Hidden canonical problem IDs/order相同，field leakage checks全部通过
- [ ] real pinned-source engineering materialization + strict readback通过
- [ ] `make lint` 全绿
- [ ] `make test` 全绿（real-Piston opt-in skips若仍存在只按既有 suite语义记录；本 stage不依赖 Piston）
- [ ] `third_party/open-r1` gitlink、reward/training/evaluation semantics未修改

## 6. Execution Routing

```yaml
execution_routing:
  version: 1
  mode: single
  complexity: normal
  single_class: normal
  parallelizability: medium
  multi_benefit: low
  independent_workstreams: 1
  rationale:
    - "source adapters、dedup fingerprint、selection manifest、canonical materialization共享同一批类型和protocol hashes，函数接口按依赖顺序串联；并行写会增加schema/glue冲突风险。"
    - "规模虽然涉及多个模块，但没有需要独立长耗时GPU/网络worker的并行lane；单executor更容易保持determinism和all-or-nothing artifact contract。"
  workstream_candidates: []
```

## 7. 风险与注意事项

- **source schema drift**：只认 full revision；字段/encoding与 preflight不同立即失败。
- **license/provenance**：记录字符串与上游 identity，不做未有依据的法律推断；非空可审计声明是入池前置。PrimeIntellect direct/OpenThoughts Harbor不因“规格候选”而自动启用。
- **stdio/function semantic mismatch**：只接纳 fixed-output/non-interactive tasks，并用明确 `solve_io` contract；special judge/interactive/multiple-valid-output等拒绝。WP9-a不修改 verifier equality semantics。
- **near-dedup false behavior**：最终 duplicate 判定必须 exact Jaccard，不用随机/approx-only结果；阈值和tokenization写入 root manifest。
- **SFT overlap accounting**：外部 candidate与SFT的 incidental match一律拒绝；允许 overlap仅来自冻结SFT direct reuse，因此避免“重命名算新题”。
- **low-test tasks**：4–7 tests可保留为候选但必须 `quality_gate_required`; `<4`拒绝；没有 test repair/synthesis。后续 WP9-c不得把低-test candidate无审计地塞入 final active pool。
- **large artifacts**：数据/cache在 Git外；tracked executor report只保存 hashes/counts/identities，禁止把题目/hidden tests大量写进日志。
- **scope creep**：任何 calibration/k=8/throughput trainer改造自动属于 WP9-b，真实 B generation/pilot属于 WP9-c。

## 8. 关联文档索引

- `proceedings.md:831-841`：WP9 activation、frozen refresh constraints、dependency order、WP9-a routing。
- `PROJECT_SPEC_GRPO_Refresh.md` §6：problem pool、overlap、external sources、dedup、three-test-layer。
- `PROJECT_SPEC_GRPO_Refresh.md` §13.1 / §14.1 / §16 / §17.1：data artifacts、data gate、defaults、stage scope。
- `PROJECT_SPEC_Open-R1_CodeVerifier.md` §7 / §19 / §20.0 / §21.3 / §29：canonical schema、leakage、development evidence、data review、defaults。
- 现有复用实现：`src/code_verifier/data/{schema,adapters,deduplicate,split_tests,leakage_checks,prepare}.py`、`src/code_verifier/training/grpo_data.py`、`src/code_verifier/cli.py`。

## 9. Handoff

- 下一步运行 `$stage-lifecycle bootstrap_plan`，将本计划正文写入 `ai-work/planner/WP9-a-plan.md`，创建/复用 `feat/wp9-a` + `.worktrees/wp9-a` 并 commit plan seal。
- bootstrap前再次要求 main `HEAD == 8410afe595db32a01a0e7f3b1ab8da4548b4482c`；若 main已变化，必须重新评估 planning base，不得静默用旧 base。
- 在 bootstrap成功并得到 `plan_commit` 前，不得调用 execution-router/implementation agent。
