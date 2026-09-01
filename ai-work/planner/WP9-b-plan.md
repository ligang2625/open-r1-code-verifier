# WP9-b 实施计划（Calibration / k=8 / throughput engineering）

## 1. 元信息

| 项 | 值 |
|---|---|
| stage_id | `WP9-b` |
| stage_profile | `development` |
| control_plane_hardware | `GTX 1660 Ti (6GB)` |
| target_hardware | `GTX 1660 Ti (6GB)`（本 stage 只关闭 engineering evidence；后续 WP9-c 才进入 24GB 真实 B calibration / pilot operator boundary） |
| evidence_class | `engineering` |
| development_terminal | `false` |
| 目标 WP | `WP9`：Calibration / k=8 / throughput engineering |
| 规格依据 | `PROJECT_SPEC_GRPO_Refresh.md` §7–§13、§16、§17.2；`PROJECT_SPEC_Open-R1_CodeVerifier.md` §19、§20、§21、§29；`proceedings.md` 最新 WP9 routing/decision records |
| planning_base_commit | `f779d08c3ff30d66bf2d5ec5111ab69c91b9c2d8` |
| proposed branch | `feat/wp9-b` |
| proposed worktree | `.worktrees/wp9-b` |
| final plan path | `ai-work/planner/WP9-b-plan.md` |
| execution report path | `ai-work/executor/WP9-b-executor.md` |
| review path | `ai-work/reviewer/WP9-b-review.md` |
| plan lifecycle | planner-ex handoff → `$stage-lifecycle bootstrap_plan` → committed plan seal → execution-router/executor |

Planning-time guard：`main` clean，只有主 worktree；`.ai-bridge/current-plan.md` 不存在，`git ls-files .ai-bridge` 为空。未合并 `archive/*` 均为历史归档；两个 `chore/*` 分支没有 sealed stage plan/worktree，不构成 active stage。`proceedings.md` 已记录 WP9-a 最终通过并明确当前唯一 dependency-ready next stage 为 **WP9-b development**。Planning-time focused baseline：`.venv/bin/python -m pytest tests/unit/training/test_grpo.py tests/unit/evaluation/test_generate.py tests/unit/evaluation/test_staged.py tests/unit/execution/test_batch.py` → **172 passed**；`make lint` → Ruff/format/mypy 全部 PASS。直接 `uv run pytest` 在当前环境因临时 uv 环境未安装 pytest 而无法 spawn，不能把这个环境问题当代码失败；仓库 Makefile/.venv 是 acceptance authority。

## 2. Stage 目标与范围

### 2.1 本 stage 的目标

在 **不运行真实冻结 B inference/calibration、不启动真实 GRPO、不产出 C2/D2、不跑正式 400 题 evaluation** 的前提下，把 WP9-c/d 所需的代码路径和严格 artifact contracts 全部实现并以 fixture/mock/synthetic engineering evidence 关闭：

1. 冻结 B 的 offline calibration 输入/生成/双 verifier scoring/retry/classification/active-pool 工具链；
2. C2/D2 的 `num_generations=8` 配置与 calibration-manifest / benchmark-report hash binding；
3. GRPO per-group reward informativeness、rolling zero-variance、verifier wall-time、backward/optimizer timing telemetry；
4. Public/Hidden reward verification bounded concurrency，最多支持 protocol candidate `64`，并严格保持 completion→reward ordering / fail-closed semantics；
5. deterministic pass@1 evaluation batched generation（candidate `[1,2,4,8,16]`）与 verification concurrency 扩展到 `[8,16,32,64]`；
6. 只从真实 run artifacts 取数的 throughput benchmark/parity/report harness，使 WP9-c 能在 24GB 4090 上做真实 benchmark 后冻结 C2/D2 runtime choices；
7. 对历史 A/B/C/D 路径保持 backward compatibility；特别是 **不修改**现有 `configs/grpo/public.yaml` / `hidden.yaml` 的 k=4 scientific identity，而是新增 refresh C2/D2 configs。

### 2.2 本 stage 必须交付

- 一个严格、可 resume/校验的 **calibration prompt/input bundle**：由已通过 `check_refresh_data()` 的 WP9-a artifact 生成，只包含 B inference 所需的 Public-safe prompt projection 与 source/difficulty/overlap/quality flags，不把 train-hidden/eval-hidden 复制到 4090 generation bundle；
- 一个 target-ready **sampled B generation bundle**：初始每题 8 completions，温度 `0.8`、`top_p=0.95`、`max_new_tokens=512`，稳定 per-problem/per-block seed；可按 retry manifest 对 `both 0/8` problem 追加第二块 8 completions；
- 一个 control-plane **dual scoring**：完全相同的 completion bytes 分别按 Public visible tests 与 Hidden train-hidden tests评分；输出 test reward、total reward、均值/std、all-correct、all-zero-test、full-pass、parse/execution/timeout、completion length/truncation等；
- calibration class：`dual_informative` / `public_only` / `hidden_only` / `dual_uninformative`；informativeness 以 **test reward std > 0** 为主，不把 auxiliary reward variance 误当 verifier informativeness；
- retry rule：初始 8 个样本若 Public/Hidden test reward 都 `0/8`，生成 retry manifest；只允许这些 problem 进入第二块 8 样本；累计 16 仍 dual-uninformative → hard pool。两边初始都 `8/8` → easy/saturated，默认不 retry；
- active pool builder：formal target `3000`，SFT reuse target继续固定 `7.5%`（`225/3000`，且 hard max `15%`），`dual_informative >=70%`、`public_only <=15%`、`hidden_only <=15%`、`dual_uninformative=0`；`quality_gate_required=true` 默认 fail-closed **不得进入 active pool**，除非未来有独立 quality-gate artifact，WP9-b 不临时发明/伪造该证据；
- final calibration manifest hash-bind：WP9-a root manifest、prompt bundle、B checkpoint identity、initial/retry generation bundles、scoring records、active/reserve/hard/easy lists、active Public/Hidden training hashes/order hash；
- refresh C2/D2 k=8 configs；formal refresh train path必须显式绑定 calibration manifest 与 throughput benchmark report，并使用同一个 verification worker count；legacy k=4 configs/legacy run hash语义保持不变；
- GRPO group/rolling telemetry和 concurrent reward path；
- generation bundle batch schema/backward-compatible loader、`generate-eval --batch-size`、`verify-eval --workers` max 64；
- refresh throughput report builder：从 actual run/bundle artifacts 读取数值，不接受手填 scientific metrics；对 eval batch做 exact parity check；same-GPU C2/D2 concurrent trial只在 >=15% paired wall-clock gain且无不稳定时推荐，否则明确推荐 sequential；
- CLI、README最小增量、unit/integration fixture evidence；
- development execution report明确声明：本 stage 的 calibration/throughput 数值只来自 engineering fixtures/mock/synthetic or optional debug smoke，**不能称为 B calibration result / C2/D2 result / final batch selection**。

### 2.3 明确范围外

- 不运行真实 frozen B 的 10k candidate sampled generation；
- 不用真实 B 数值选择 formal active 3000；
- 不运行 k=8 real GRPO pilot/full C2/D2；
- 不在本 stage 冻结真实 4090 eval generation batch size、真实 GRPO verifier concurrency、same-GPU C2/D2 concurrency结论；这些由 WP9-c validation 真实 benchmark 决定；
- 不运行正式 400 problem A/B/C2/D2 evaluation；
- 不改 Public/Hidden reward公式、Piston execution semantics、test-layer definitions、WP9-a source/dedup protocol；
- 不改 `third_party/open-r1`；如需适配 pinned TRL/Open-R1，只在本仓库 adapter/runtime layer完成；
- 不把历史 `configs/grpo/public.yaml` / `hidden.yaml` 从 k=4 改成 k=8；
- 不创建 branch/worktree/commit 于 planning 阶段；bootstrap_plan 后才进入 execution lifecycle。

## 3. 冻结约束与实现原则

1. **WP9-a 是唯一 data authority**：formal calibration input必须从通过 production `check_refresh_data()` 的 WP9-a root 派生。planning-time latest accepted evidence：10,000 selected、750 SFT reuse、9,250 external-new、1,086 `quality_gate_required`、root manifest SHA256 `98a0fb8192661f6358c29819d8a70eb4039397cc2a3ec5444f0581cfbcb81625`、selected IDs/order SHA256 `355cfec302a38c3c05e4237be178c5f34207cabb432d2b65f1b4a027cf42d001`。不要硬编码机器绝对路径；hash只作为 provenance anchor/acceptance reference。
2. **B-only calibration**：generation source必须是 completed SFT checkpoint B (`load_completed_sft_checkpoint`)；calibration API不得接受 GRPO C/D source。
3. **same completions, two verifiers**：Public/Hidden calibration scoring必须读取同一 generation record identity/completion bytes/sample order；禁止为两个 arm独立采样。
4. **no eval-hidden**：calibration generation bundle只携带 Public-safe prompt projection；scoring在 control plane 从 WP9-a public/hidden training views取 tests；eval-hidden绝不进入 generation/scoring input。
5. **deterministic seed namespace**：建议固定 `wp9b-calibration-v1|base_seed|problem_id|block_index` 经 SHA256 派生到 transformers seed范围；初始 block=`0`，retry block=`1`，sample indices严格 `0..7` / `8..15`。
6. **retry仅 both 0/8**：不能看到其它统计后任意增加采样；retry manifest必须被 initial scoring artifact hash绑定，retry generation只能包含该 exact ordered ID list。
7. **test reward variance是 informativeness主判据**：`std(test_reward)>0`；total reward std另行记录但不能替代 verifier variance。
8. **quality-gate fail closed**：WP9-a 4–7-test reserve不自动进入 formal pool。WP9-b默认将 `quality_gate_required=true` 送 reserve；不要把 calibration variance本身偷换成“独立 data-quality gate”。
9. **legacy compatibility**：当 refresh binding 未提供时，现有 k=4 config parsing、config hash、paired definition、resume schema、single-executor reward path和旧 evaluation generation bundle必须继续读/跑；refresh fields不得无条件改写旧 run identity。
10. **runtime tuning是 paired evidence**：formal refresh C2/D2 calibration manifest、benchmark report、verification worker count必须进入 pair identity/run provenance；Public/Hidden除了 reward source/run_name/dataset view外保持一致。
11. **并发 fail closed**：任何 infrastructure failure仍必须在 optimizer step前终止；并发只改变 wall time，不改变 completion order/reward vector/test layer/retry semantics。
12. **batch eval parity first**：batch size候选必须与 batch=1 对相同 model/checkpoint/config/problem order得到 exact completion/token/truncation parity；无法证明 parity的 candidate不得被正式选择。
13. **benchmark numbers必须源自 artifacts**：throughput report builder不接受用户填写 tokens/s、walltime、VRAM等最终数字；只接受 actual run/bundle paths + hashes，并从 `run.json`/`metrics.jsonl`/generation/verification artifacts推导。
14. **development evidence boundaries**：1660 Ti/CPU/mock/fixture可以证明代码路径、artifact schema、ordering、concurrency、selection logic；不能证明 4090 capacity或真实 B reward distribution。

## 4. Execution preflight（第一次业务修改/commit 前）

1. lifecycle bootstrap 后，stage worktree `HEAD` 必须等于 sealed `plan_commit`，branch=`feat/wp9-b`，worktree clean；`git ls-files .ai-bridge` 为空；不得在 main直接实现。
2. `planning_base_commit` seal前必须仍为 `f779d08c3ff30d66bf2d5ec5111ab69c91b9c2d8`；若 bootstrap 前 main已变化，先 replan，不静默沿用旧 base。
3. 使用仓库环境：`.venv/bin/python` / Makefile；验证 `import code_verifier, torch, transformers, datasets, yaml`。不要因为当前 `uv run pytest` console script缺失而改依赖；真正 dependency install只按现有 `make install*`/uv lock流程。
4. 读取并记录 pinned runtime/API：当前 TRL/Open-R1/Transformers版本、`GRPOTrainer` 本 stage计划 hook 的方法是否仍存在（`_generate_and_score_completions`, `_get_per_token_logps`, `training_step`, `_maybe_log_save_evaluate`, `create_optimizer_and_scheduler`/optimizer step或等价 pinned接口）。若 pinned API与计划不符，停止并 replan，不靠宽泛 monkeypatch猜行为。
5. WP9-a formal artifact若在本机可用：先 `check-refresh-data` production strict readback并确认 root manifest/order hashes与最新 accepted evidence相符；若 formal外部 root不在本机，WP9-b development仍可用 production-shadow fixture关闭，但 executor report必须明确“未消费真实 10k calibration data”，绝不生成 B scientific claims。
6. 本 stage不要求 24GB operator gate；任何真实 frozen-B/4090 command在 WP9-b execution中都必须跳过。若 executor尝试真实 B 10k sampling或real GRPO，属于 scope violation，应停止。
7. baseline：重复 focused 172 tests与 `make lint`；若 pre-existing baseline已变红，先记录/定位，不把无关失败混入 WP9-b实现。

## 5. 实施步骤

### 步骤 1：抽出可复用的 Transformers generation primitives，并增加 deterministic evaluation batch API

**目标文件**：
- `src/code_verifier/evaluation/generate.py`
- `tests/unit/evaluation/test_generate.py`

**新增/修改符号（命名可小幅调整，但职责不可合并丢失）**：
```python
@dataclass(frozen=True)
class SamplingGenerationConfig:
    temperature: float
    top_p: float
    max_new_tokens: int
    dtype: str = "auto"

class BatchedCompletionGenerator(Protocol):
    def generate_batch(
        self,
        prompts: Sequence[str],
        *,
        seeds: Sequence[int],
    ) -> list[GenerationResult]: ...

class GroupSamplingGenerator(Protocol):
    def generate_group(
        self,
        prompt: str,
        *,
        seed: int,
        num_generations: int,
    ) -> list[GenerationResult]: ...

class TransformersCompletionGenerator:
    def generate_batch(...): ...

class TransformersSamplingCompletionGenerator:
    @classmethod
    def from_peft_checkpoint(...): ...
    def generate_group(...): ...
```

**实现要求**：
- 保持现有 `GenerationConfig` 的 deterministic pass@1 contract完全不变（`do_sample=False`, `temperature/top_p=None`）；不要放宽 evaluator validation。
- 复用现有 `_load_transformers_runtime`, `_load_base_transformers_model`, `_load_identity_checked_peft_config`, `_attach_peft_adapter`, `_initialize_inference_model`，不要复制第二套 model loading / PEFT identity逻辑。
- `TransformersSamplingCompletionGenerator`只需支持 completed SFT adapter B；WP9-b calibration不允许 GRPO source。
- sampled group固定使用 `do_sample=True`，配置必须严格 `temperature=0.8`, `top_p=0.95`, `max_new_tokens=512` when loaded through production calibration config；`num_generations=8`；一个 problem/block一次 `model.generate(..., num_return_sequences=8)`，输出顺序就是 sample index顺序。
- deterministic batch path要正确处理 padding/attention mask/device；`generate(prompt, seed)`继续作为 batch size 1 wrapper，确保旧 evaluator无行为变化。
- batch path必须返回与输入 prompts一一对应且顺序一致的 `GenerationResult`；空 batch、长度不齐 seeds、unsupported batch size等 fail closed。
- unit fake tokenizer/model覆盖：batch 1行为不变、batch order、per-item decode/token/truncation、sample group 8、seed repeatability、sampling config严格性、PEFT identity rejection。

### 步骤 2：实现 calibration input/prompt bundle 与 sampled B generation bundle（初始/重试）

**目标文件**：
- 新增 `src/code_verifier/training/calibration.py`
- `src/code_verifier/training/grpo_data.py`
- `src/code_verifier/training/__init__.py`
- 新增 `configs/grpo/refresh-calibration.yaml`
- 新增 `tests/unit/training/test_calibration.py`

**建议公共符号**：
```python
class CalibrationError(RuntimeError): ...

class CalibrationClass(str, Enum):
    DUAL_INFORMATIVE = "dual_informative"
    PUBLIC_ONLY = "public_only"
    HIDDEN_ONLY = "hidden_only"
    DUAL_UNINFORMATIVE = "dual_uninformative"

@dataclass(frozen=True)
class CalibrationConfig:
    initial_generations: int
    retry_generations: int
    temperature: float
    top_p: float
    max_new_tokens: int
    active_pool_size: int
    sft_overlap_fraction: float
    sft_overlap_hard_max: float
    dual_informative_min_fraction: float
    public_only_max_fraction: float
    hidden_only_max_fraction: float

@dataclass(frozen=True)
class CalibrationInputRecord:
    problem_id: str
    prompt: str
    source_name: str
    difficulty: str
    overlap_origin: str
    quality_gate_required: bool

@dataclass(frozen=True)
class CalibrationGenerationRecord:
    problem_id: str
    block_index: int
    sample_index: int
    sample_seed: int
    completion: str
    completion_tokens: int
    generation_latency_ms: float
    hit_max_new_tokens: bool

@dataclass(frozen=True)
class CalibrationGenerationSummary: ...

def calibration_problem_seed(base_seed: int, problem_id: str, block_index: int) -> int: ...

def prepare_calibration_input_bundle(
    *,
    refresh_dataset_dir: Path,
    reference_dataset_dir: Path,
    output_dir: Path,
    seed: int,
) -> ...: ...

def run_calibration_generation(
    *,
    input_bundle_dir: Path,
    sft_run_dir: Path,
    generator: GroupSamplingGenerator,
    output_dir: Path,
    block_index: int,
    retry_manifest: Path | None = None,
) -> CalibrationGenerationSummary: ...

def load_completed_calibration_generation(...) -> ...: ...
```

**input bundle contract**：
- producer首先执行 production `check_refresh_data(refresh_dataset_dir, reference_dataset_dir=...)`；
- prompt必须由 WP9-a Public training view走与 `build_grpo_dataset()`完全相同的 prompt builder。为避免 drift，把 `grpo_data.py` 中 prompt-row construction抽成受测试 helper，training/calibration共同复用；
- bundle只包含 Public-safe prompt + non-sensitive strata metadata；不得出现 `train_hidden_tests`, `eval_hidden_tests`, reference solution, SFT response, starter code；
- root manifest记录 WP9-a `refresh_manifest.json` SHA、Public/Hidden training SHA、selected order SHA、seed、record count、prompt JSONL SHA；无机器绝对路径/hostname/timestamp参与 deterministic identity；
- production bundle必须恰好 10,000 unique ordered problems；fixture允许显式 test schema/version，不得让 production checker默认认证小 fixture。

**generation bundle contract**：
- source必须 `load_completed_sft_checkpoint(sft_run_dir)`，记录 B run/checkpoint/model/revision/config/dataset/dependency hashes；
- initial block固定 8 samples/problem，block_index=0；retry block固定8，block_index=1；sample indices不得重叠；
- generation过程只读 prompt bundle，不读取 Hidden/eval tests；
- append/resume只允许 exact prefix；现有 rows、B identity、config、input bundle hash、block identity不匹配立即拒绝；terminal bundle记录 records SHA/order SHA/gpu count/gpu-hours semantics；
- retry generation必须读取由步骤3 initial scoring生成的 immutable retry manifest；IDs/order/hash必须完全一致，禁止任意 `--problem-id` 手选；
- fixture fake generator证明 same seed -> same exact rows、resume prefix、tamper rejection、retry subset enforcement；本 stage不真实加载 B跑10k。

`configs/grpo/refresh-calibration.yaml` production值必须冻结为 addendum defaults：initial/retry `8/8`、`0.8/0.95/512`、active size `3000`、SFT overlap `0.075`、hard max `0.15`、dual min `0.70`、public-only/hidden-only max各 `0.15`。不提供“临时放宽”CLI override；变 protocol必须 replan/spec amendment。

### 步骤 3：实现 concurrent Public/Hidden calibration scoring、informativeness metrics 与 retry manifest

**目标文件**：
- `src/code_verifier/rewards/common.py`
- `src/code_verifier/training/calibration.py`
- `src/code_verifier/execution/piston_resilience.py`
- `tests/unit/training/test_calibration.py`
- `tests/unit/execution/test_piston_resilience.py`

**新增公共 helper**：
```python
def compute_code_rewards_concurrent(
    completions: object,
    tests_batch: object,
    function_names: object,
    metadata_batch: object,
    *,
    executor_factory: Callable[[], CodeExecutor],
    mode: str,
    max_concurrency: int,
) -> tuple[list[float], list[dict[str, object]]]: ...

@dataclass(frozen=True)
class CalibrationScoreRecord: ...

def score_calibration_generation(
    *,
    refresh_dataset_dir: Path,
    reference_dataset_dir: Path,
    generation_run_dir: Path,
    output_dir: Path,
    executor_factory: Callable[[], CodeExecutor],
    workers: int,
) -> ...: ...
```

**concurrent reward invariant**：
- 与 `compute_code_rewards()` 一样，所有 batch alignment / completion parsing输入先完整验证，再发生 executor side effect；
- 每个 future持有独立 executor instance，结果通过原始 index回填；completion order/reward order必须与输入完全一致，不按 completion finish order append；
- workers支持 `1..64`；workers=1与现有 serial helper exact reward/component parity；
- exception/infrastructure failure不得被吞为普通 reward。若 executor返回 infrastructure failure component，scoring可记录并使 calibration run `failed`；GRPO路径在步骤6进一步保证 optimizer前 abort；
- 如果共享 `PistonTransportTelemetry` 给多个 PistonExecutor factory，先把 telemetry mutation/snapshot做 thread-safe（`RLock`或等价），callback snapshot也必须序列化；serialization schema不得包含 lock，也不得改历史 counter字段。

**calibration scoring contract**：
- 严格加载 WP9-a Public/Hidden training views，require same problem IDs/order；generation records按 problem/sample exact join；
- 对每一个 completion byte-identical地调用 Public visible tests与 Hidden train-hidden tests；不得为 Hidden另采样；
- 每 problem/block记录数组及 summary：
  - `public_test_rewards`, `hidden_test_rewards`；
  - `public_total_rewards`, `hidden_total_rewards`；
  - test/total mean + population std；
  - `public_informative`, `hidden_informative`（**test std > 0**）；
  - `all_test_correct`, `all_test_zero`, `full_pass_count` for each verifier；
  - parse/execution/timeout/infrastructure counts；
  - completion token mean/max、truncation count；
  - source/difficulty/overlap/quality flag；
  - exact generation bundle hash / problem/sample identity。
- class规则：both informative→dual；only public→public_only；only hidden→hidden_only；neither→dual_uninformative。
- initial block且两边 `all_test_zero=True` → append problem ID到 canonical sorted `retry_problem_ids.jsonl`；其它 dual-uninformative不自动 retry；两边 `all_test_correct=True`标 easy/saturated。
- scoring run terminal时 hash-bind generation bundle、WP9-a manifest、Public/Hidden view hashes、workers、Piston config/transport policy identities；payload不写 stdout/telemetry。
- tests包含 delayed/out-of-order executor、public/hidden deliberately different tests、same completions byte identity、serial/concurrent parity、retry exact rule、component/test-variance distinction、infra failure fail closed。

### 步骤 4：合并初始/重试 scoring并构建 formal-ready active/reserve/hard/easy pool artifact

**目标文件**：
- `src/code_verifier/training/calibration.py`
- `tests/unit/training/test_calibration.py`
- 新增 `tests/integration/test_wp9b_refresh_engineering.py`

**新增符号**：
```python
@dataclass(frozen=True)
class CalibrationPoolSummary:
    selected_problems: int
    dual_informative: int
    public_only: int
    hidden_only: int
    sft_overlap_count: int
    active_order_sha256: str
    calibration_manifest: Path
    public_grpo_jsonl: Path
    hidden_grpo_jsonl: Path


def build_calibrated_active_pool(
    *,
    config: CalibrationConfig,
    refresh_dataset_dir: Path,
    reference_dataset_dir: Path,
    input_bundle_dir: Path,
    initial_scoring_dir: Path,
    retry_scoring_dir: Path | None,
    output_dir: Path,
    seed: int,
) -> CalibrationPoolSummary: ...


def check_calibrated_active_pool(
    pool_dir: Path,
    *,
    refresh_dataset_dir: Path,
    reference_dataset_dir: Path,
) -> CalibrationPoolSummary: ...
```

**merge/final classification**：
- retry scoring只能出现 initial retry manifest IDs；对这些 problem将初始8 + retry8按 sample_index合并为16，重新算 final test/total stats/class；
- initial both-zero但缺 retry scoring时，production pool builder fail closed；
- cumulative 16仍 dual-uninformative → `hard_problem_ids.jsonl`，不得进 active；
- initial both all-correct → `easy_problem_ids.jsonl`，默认不得进 active；
- informative但没选中 → reserve；
- `quality_gate_required=true`无独立 future quality artifact时强制 reserve reason=`quality_gate_required`。

**active selection protocol**：
- target exact 3000；SFT reuse exact 225 (`7.5%`)，actual必须 `<=15%`；selection only来自 WP9-a frozen 10k IDs；
- dual_informative priority最高并要求最终 `>=2100/3000`；public-only/hidden-only各不得超过450；dual-uninformative=0；
- 不强行制造 70/15/15。实现 deterministic constrained selector：在 overlap/non-overlap两个 quota bucket内，以 class priority `dual > single-arm`，再按 source+difficulty strata largest-remainder / stable hash排序，尽量最大化 dual coverage；只有 dual不足以填 strata/target时才用 single-arm并受15% cap；若 constraints不能同时满足则 fail closed并报告每 class/source/difficulty/overlap population，不放宽阈值；
- active order使用独立 namespace hash冻结；Public/Hidden output由 WP9-a training views **subset/copy**，不能重新构造 tests；IDs/order完全一致；
- selected row metadata增加/确认 `calibration_class`、calibration record hash、overlap origin等 non-secret fields，Public仍无 train-hidden，双方均无 eval-hidden/reference/sft_response/starter code。

**artifact tree（相对 pool output）**：
- `records/calibration.jsonl`（final cumulative record/problem）；
- `manifest/retry_problem_ids.jsonl`；
- `manifest/active_selection.jsonl`；
- `manifest/problem_order.jsonl`；
- `manifest/reserve_problem_ids.jsonl`；
- `manifest/hard_problem_ids.jsonl`；
- `manifest/easy_problem_ids.jsonl`；
- `reports/classification_summary.json`；
- `reports/pool_composition.json`；
- `training/public_grpo.jsonl`；
- `training/hidden_grpo.jsonl`；
- `calibration_manifest.json`。

`calibration_manifest.json`必须记录并 cross-bind：schema/version、config、WP9-a root manifest SHA/order SHA、input bundle SHA、B identity、initial/retry generation+scoring SHAs、records SHA、active/reserve/hard/easy SHAs、active Public/Hidden training SHAs、active order SHA、class counts/fractions、SFT overlap count/fraction、quality exclusion counts。绝不信任 report里的派生值；`check_calibrated_active_pool()`从原始 records/training views重算并拒绝 self-consistent tamper/reorder/hash drift。

### 步骤 5：新增 refresh C2/D2 k=8 configs、calibration/benchmark binding 与 richer GRPO group/rolling timing telemetry

**目标文件**：
- `configs/grpo/refresh-public.yaml`
- `configs/grpo/refresh-hidden.yaml`
- `src/code_verifier/training/grpo.py`
- `src/code_verifier/training/grpo_data.py`
- `tests/unit/training/test_grpo.py`
- `tests/unit/training/test_grpo_resume_lineage.py`

**关键边界**：
- **不要改** `configs/grpo/public.yaml` / `hidden.yaml` 的 `num_generations: 4`；它们是历史 C/D protocol references。
- 新 refresh configs固定 `num_generations: 8`, `temperature:0.8`, `top_p:0.95`, `max_completion_length:512`；其它 scientific hyperparameters沿 addendum/current baseline保持 paired相同。现有 `per_device_train_batch_size=1`, `gradient_accumulation_steps=8` 的 effective group batch与k=8兼容，但代码必须继续显式验证 `effective generation batch % num_generations == 0`。
- dataset path只是 tracked placeholder；formal WP9-c用现有 `--dataset-dir <active-pool-root>` override到 `training/public_grpo.jsonl` / `hidden_grpo.jsonl`。

**新增 refresh binding（建议）**：
```python
@dataclass(frozen=True)
class GRPORefreshBinding:
    calibration_manifest_path: Path
    calibration_manifest_sha256: str
    active_order_sha256: str
    public_training_sha256: str
    hidden_training_sha256: str
    benchmark_report_path: Path
    benchmark_report_sha256: str
    verification_workers: int
```

提供 loader从 `check_calibrated_active_pool()` + throughput report严格构造，不接受 caller直接填写 hashes。

`run_grpo_training()` 保持 legacy调用兼容；可以新增可选 `refresh_binding` / `executor_factory`，但：
- `refresh_binding is None` 时旧 config hash / paired definition / resolved config语义必须 byte-compatible，旧 run resume tests必须继续过；verification workers固定 legacy serial语义；
- `refresh_binding is not None` 时要求 `num_generations==8`、active dataset hashes等于 binding、Public/Hidden同 calibration manifest/order、benchmark report推荐的 verifier workers等于 runtime；paired-definition schema使用显式 newer version而不是偷偷改变 legacy v2；resume严格读取相同 binding hashes；
- formal refresh run metadata要持久化 binding（relative/logical path + SHA，不允许把本机绝对路径作为 portable pair identity）。

**group metrics升级**：现有 `group_metrics.jsonl` 保留 legacy aliases `mean/std/all_equal`（作为 total reward aliases，避免旧 analysis消费者突然坏），同时对 refresh/新 runs新增：
- `problem_id`, `reward_mode`, `calibration_class`, `sample_count`；
- `test_reward_mean`, `test_reward_std`；
- `total_reward_mean`, `total_reward_std`；
- `all_test_correct`, `all_test_zero`, `all_total_reward_equal`；
- `verifier_runtime_seconds`；
- optional completion/truncation summary若 pinned TRL callback能可靠提供；不能猜。

`calibration_class`从 active training row metadata传进 reward callback；refresh binding存在时缺失/不匹配直接 fail，legacy run允许 absent。

**rolling/timing telemetry**：
- 新建内部 thread-safe `GRPORollingTelemetry`（或等价）维护最近固定 window（把 window size写入 resolved runtime/provenance）：all-correct frac、all-zero frac、total-reward-zero-variance frac、mean/median group reward std、effective non-zero-variance group count、verifier wall time；
- 复用/扩展 `_install_grpo_runtime_telemetry()` 当前 generation/rollout/no-grad/step timing；对 pinned Trainer通过受测试 wrapper timing `accelerator.backward` 与 optimizer `.step()`（必要时wrap `create_optimizer_and_scheduler`后安装），分别累计 backward/optimizer runtime；若 pinned API不存在，preflight fail/replan，不静默输出0；
- `metrics.jsonl`/trainer log history必须能导出 rollout generation time、verifier time、backward time、optimizer time、step time；non-finite/negative全部 reject；
- 保留当前 gradient-checkpointing generation/no-grad保护、checkpoint log snapshots/resume lineage。

### 步骤 6：把 GRPO reward verification改造成 bounded concurrent、ordered、fail-closed runtime

**目标文件**：
- `src/code_verifier/training/grpo.py`
- `src/code_verifier/rewards/common.py`
- `src/code_verifier/execution/piston_resilience.py`
- `src/code_verifier/cli.py`
- `tests/unit/training/test_grpo.py`
- `tests/unit/training/test_grpo_transport_failure.py`
- `tests/unit/execution/test_piston_resilience.py`

**API/CLI方向**：
- `train-grpo`新增 `--calibration-manifest`, `--benchmark-report`, `--verification-workers`；legacy invocation不提供前三者时仍是现有serial path；
- refresh formal invocation要求三个binding参数成组存在，`verification-workers`范围 `1..64`，且必须等于 benchmark report selected value；Public/Hidden运行都用同值；
- CLI不要共享一个非线程安全 `PistonExecutor` 实例：提供 factory构造独立 executor，底层共享经过步骤3 thread-safe化的 transport telemetry/sidecar；
- sidecar writes必须原子且在并发callback下串行，不丢counter增量。

**reward callback**：
- `build_grpo_reward_callback()`增加 `executor_factory`/`verification_workers` 或等价 runtime abstraction；workers=1走 legacy serial exact path；workers>1调用 `compute_code_rewards_concurrent()`；
- `_TrainingExecutorCircuitBreaker`不能被多个 threads不安全共享；为每个 execution task构建独立 breaker，retry counters汇总到 thread-safe run telemetry；
- bounded retry policy、safe/ambiguous transport distinction、infra fail rules全部保持；
- reward logs只在整个 aligned batch成功且无 infra failure后append；任何一个 completion出现 infra failure都必须在 trainer optimizer step前raise，不能部分写“正常reward”再继续；
- delayed executor regression证明 future completion顺序变化不改变 rewards/components/group logs；Public/Hidden test source不可混；
- benchmark candidates `[8,16,32,64]`只是 runtime capability，WP9-b不声称哪个是formal最优。

### 步骤 7：升级 staged evaluation 为 deterministic batched generation + max64 verification，并实现 artifact-derived throughput/parity harness

**目标文件**：
- `src/code_verifier/evaluation/staged.py`
- `src/code_verifier/evaluation/generate.py`
- 新增 `src/code_verifier/throughput.py`
- `src/code_verifier/cli.py`
- `tests/unit/evaluation/test_staged.py`
- `tests/unit/evaluation/test_generate.py`
- 新增 `tests/unit/test_throughput.py`

**staged generation**：
- `run_generation_bundle(..., batch_size: int = 1)`；production allowed batch sizes严格 `{1,2,4,8,16}`；batch=1 old behavior不变；
- `generate-eval`新增 `--batch-size`，default=1；
- generation bundle schema显式 version bump（例如 v2），loader必须继续读v1 historical bundle；不要 silently reinterpret v1 latency/gpu-hour semantics；
- v2 persist batch provenance：batch size、batch index/record span、batch wall latency、attributed per-record latency或其它明确且总和等于 actual generation walltime的 accounting。不要把 full batch walltime复制到每 row造成 GPU-hours乘batch size；
- records仍严格按 problem order落盘/resume exact prefix；最后一个partial batch正确处理；
- deterministic batch每 item completion/token/truncation必须能和 batch=1 exact比较。

**verification**：
- `run_verification_from_generation_bundle(..., workers)`上限从32提升64，候选仍由 benchmark决定；
- `verify-eval --workers` help/validation同步；现有 ordered append、hash/provenance、Piston concurrent verification semantics不变；
- v1/v2 generation bundle都能 verification，且 v2 batch operational metadata进入 verification provenance。

**throughput module（不得接收手填结果数值）**：
```python
@dataclass(frozen=True)
class RefreshBenchmarkManifest: ...
@dataclass(frozen=True)
class RefreshBenchmarkSummary: ...

def compare_generation_bundle_parity(
    baseline_run_dir: Path,
    candidate_run_dir: Path,
) -> ...: ...

def summarize_refresh_benchmarks(
    manifest_path: Path,
    *,
    output_dir: Path,
) -> RefreshBenchmarkSummary: ...
```

manifest只声明 artifact paths/roles（k4 reference run、k8 candidates、verifier worker candidates、eval batch1/batch candidates、eval verification candidates、optional same-GPU Public/Hidden paired trial）；module从各 artifact的 strict loader读取 walltime/GPU-hours/VRAM/tokens/request/errors/retries/order hashes等，并把每 source artifact SHA写入 report。

**selection rules**：
- eval generation batch candidate必须：same model/checkpoint/dataset/config/seed/problem order；exact completion bytes、completion_tokens、hit_max_new_tokens parity vs batch1；无 OOM；peak VRAM安全；throughput不低于baseline。选择满足条件中 throughput最优；tie用较小batch；
- eval verification worker候选 `[8,16,32,64]`：结果 JSONL/aggregate identity必须 exact parity，0 payload/order mismatch，infra failure不可隐藏；选择 stable throughput最优；
- GRPO verifier worker候选 `[8,16,32,64]`：只从实际 benchmark run读取，要求 same k8 scientific config/pool/B/seed，最终 reward/group record parity，0 infra semantic drift；
- k4 vs k8是 benchmark comparison，不允许通过减少 optimizer steps/缩短completion/改reward获得“提速”；
- same-GPU C2/D2 concurrent trial：计算 sequential wall-clock基线与 concurrent envelope。只有 `concurrent_wall <= 0.85 * sequential_wall`（>=15% gain）、两 arm无 OOM/infra spike/variance instability、scientific config完全对称时才推荐 concurrent；否则 report recommendation=`sequential`；
- report输出 selected `grpo_verification_workers`, `eval_generation_batch_size`, `eval_verification_workers`, `paired_grpo_mode`，但 WP9-b fixture report必须 `evidence_class=engineering`，不能拿它当 WP9-c formal recommendation。

如可无新 dependency完成，GPU utilization sampler使用 stdlib受控 `nvidia-smi --query-gpu=utilization.gpu,memory.used --format=csv,noheader,nounits` 周期采样或等价现有环境接口；其采样器必须 injectable/fakeable、记录命令失败为 unavailable而不是伪造0。Formal report若 spec要求的 GPU-util field unavailable则不得宣称 throughput benchmark complete；WP9-b engineering fixture可测试 unavailable path。

### 步骤 8：CLI/文档、production-shadow integration 与 development acceptance evidence

**目标文件**：
- `src/code_verifier/cli.py`
- `tests/unit/test_cli.py`
- `README.md`
- `tests/fixtures/wp9b/`（新增 small Public/Hidden problems + deterministic fake sampled completions/benchmark artifacts；不得含 formal hidden secrets）
- `tests/integration/test_wp9b_refresh_engineering.py`
- `ai-work/executor/WP9-b-executor.md`

**新增 CLI（建议命名固定，避免一条巨型命令隐藏阶段边界）**：
```text
code-verifier prepare-refresh-calibration \
  --config configs/grpo/refresh-calibration.yaml \
  --dataset-dir <wp9a-root> \
  --reference-dataset-dir <formal-reference-root> \
  --seed 42 \
  --output-dir <prompt-bundle-root>

code-verifier generate-refresh-calibration \
  --config configs/grpo/refresh-calibration.yaml \
  --input-bundle-dir <prompt-bundle-root> \
  --sft-run-dir <B-run> \
  --block initial|retry \
  [--retry-manifest <initial-score/retry_problem_ids.jsonl>] \
  --output-dir <generation-root>

code-verifier score-refresh-calibration \
  --dataset-dir <wp9a-root> \
  --reference-dataset-dir <formal-reference-root> \
  --generation-run-dir <completed-generation> \
  --workers <1..64> \
  --output-dir <score-root>

code-verifier build-refresh-active-pool \
  --config configs/grpo/refresh-calibration.yaml \
  --dataset-dir <wp9a-root> \
  --reference-dataset-dir <formal-reference-root> \
  --input-bundle-dir <prompt-bundle-root> \
  --initial-scoring-dir <score0> \
  [--retry-scoring-dir <score1>] \
  --seed 42 \
  --output-dir <active-pool-root>

code-verifier summarize-refresh-benchmark \
  --manifest <actual-artifact-manifest.yaml> \
  --output-dir <benchmark-report-root>
```

`generate-refresh-calibration` production command在 WP9-b executor中只能用 fake/injected test generator或不执行；CLI wiring/production generator由 unit tests/fake runtime验证，真实 B invocation留到 WP9-c operator boundary。

**integration fixture必须覆盖完整 engineering flow**：
1. small WP9-a production-shadow Public/Hidden views → prepare calibration prompt bundle；
2. fake B initial k=8 outputs：至少包含 dual, public-only, hidden-only, both-zero-retry, saturated-easy, quality-gate-required cases；
3. same completion bytes双 verifier concurrent scoring；
4. retry manifest只列 both-zero；fake retry8后分别覆盖“变 informative”和“累计16仍hard”；
5. active pool用 test-only小 target/config直接调用内部 validated dataclass（production tracked config仍冻结3000），验证 composition caps、overlap quota、quality reserve、order/hash、Public/Hidden isolation；
6. calibration manifest tamper/reorder/hash/class/count/hidden-field全部被 strict checker拒绝；
7. refresh k8 Public/Hidden config pair加载通过，legacy k4 configs仍为4且旧 config/hash/resume tests不漂；
8. concurrent reward delayed completion与serial exact parity；infra failure abort；
9. eval batch fake model batch1 vs 2/4 exact parity、resume、partial last batch、v1 loader compatibility；verify workers=64 ordering parity；
10. throughput fixture由 actual fixture run artifacts生成，不能用手填 numeric result；bad parity candidate被淘汰；same-GPU gain 14%→sequential、15%及以上且稳定→concurrent；
11. executor report明确 engineering evidence，不出现真实 B reward数值、C2/D2 checkpoint、formal 400 eval claim。

README只增加 WP9-b tooling和边界，明确“commands implemented / formal values pending WP9-c validation”；不要改写历史 A–D结论。

## 6. 测试与验收计划

### 6.1 Focused unit/integration

```bash
.venv/bin/python -m pytest \
  tests/unit/training/test_calibration.py \
  tests/unit/training/test_grpo.py \
  tests/unit/training/test_grpo_resume_lineage.py \
  tests/unit/training/test_grpo_transport_failure.py \
  tests/unit/evaluation/test_generate.py \
  tests/unit/evaluation/test_staged.py \
  tests/unit/execution/test_batch.py \
  tests/unit/execution/test_piston_resilience.py \
  tests/unit/test_throughput.py \
  tests/unit/test_cli.py \
  tests/integration/test_wp9b_refresh_engineering.py
```

### 6.2 全局 gates

```bash
make lint
make test
```

若本机已有 local Piston，可额外运行一个 **engineering-only** opt-in concurrency smoke（不是 formal benchmark），例如对 fixture completion同时跑 workers 8/16/32/64并确认 exact ordered result parity；Piston不可用不允许伪造PASS，但 planner不把真实Piston作为 development hard gate，因为 sealed stage evidence class为 engineering fixture/mock/synthetic。

### 6.3 最终 acceptance checklist

- [ ] prompt/input bundle只含 Public-safe generation material，hash-bind WP9-a production identity；
- [ ] sampled generation contract固定 B-only、k=8、0.8/0.95/512、per-problem/per-block deterministic seed；
- [ ] initial/retry generation resume/tamper/subset contracts通过；
- [ ] Public/Hidden对 exact same completions评分，test reward variance分类正确；
- [ ] both-zero 0/8 retry rule、16-sample hard pool、saturated easy规则正确；
- [ ] formal active-pool selector production defaults冻结 3000 / 225 overlap / >=70% dual / <=15% single-arm / 0 dual-uninformative；quality-gate-required默认排除；
- [ ] calibration manifest严格可重算、tamper fail closed；
- [ ] 新 refresh Public/Hidden configs为 k=8；旧 `public.yaml`/`hidden.yaml` 保持 k=4；legacy run hash/resume compatibility测试通过；
- [ ] refresh GRPO formal path hash-bind calibration manifest + benchmark report + same verifier workers；
- [ ] group metrics含 test/total variance、all-correct/all-zero/zero-var、calibration class，rolling telemetry和 verifier/backward/optimizer/step timing均有限非负；
- [ ] concurrent GRPO verification保序、serial parity、infra fail optimizer前abort；
- [ ] Piston transport/retry telemetry在共享并发使用时 thread-safe、sidecar无丢计数；
- [ ] evaluation generation batch sizes 1/2/4/8/16受支持，batch1 backward-compatible；v1 generation bundle仍可读；
- [ ] verify-eval支持到64 workers且结果顺序/provenance不变；
- [ ] throughput report只从真实 artifact fields派生；eval batch exact parity gate和 >=15% same-GPU recommendation rule受测试；
- [ ] focused suite全绿；`make lint`全绿；`make test`全绿（现有 opt-in skips按仓库既有语义记录）；
- [ ] `third_party/open-r1` gitlink未修改；spec/proceedings/sealed plan未被 executor改写；
- [ ] WP9-b executor report没有真实 B calibration/C2/D2/400-eval scientific claim。

## 7. Execution Routing

```yaml
execution_routing:
  version: 1
  mode: single
  complexity: difficult_serial
  single_class: difficult_serial
  parallelizability: medium
  multi_benefit: low
  independent_workstreams: 1
  rationale:
    - "表面上 calibration、GRPO、evaluation throughput 可拆成多个 lane，但三者共享 generation primitives、reward concurrency、Piston telemetry、CLI 和最终 benchmark/calibration hash binding；先并行各自定义 schema会显著增加 artifact/version/glue 冲突与 legacy compatibility 风险。"
    - "本 stage 的核心不是三套独立功能，而是一条需要按依赖顺序冻结的 evidence chain：safe prompt bundle → sampled generation/scoring/classification → active pool manifest → k=8 runtime binding/telemetry → batched eval/benchmark report。单 executor difficult_serial 更容易保持 old-run compatibility 与 Public/Hidden identity。"
  workstream_candidates: []
```

## 8. 风险与注意事项

- **Transformers batching parity**：decoder-only padding方向/position IDs可能导致 batch与single输出不同。不要以“通常等价”假设通过；fake regression + WP9-c真实 parity artifact是 formal gate。
- **sampled seed semantics**：不同 Transformers版本对 `num_return_sequences`随机流处理可能变化；bundle记录 pinned dependency identity + seed namespace，WP9-c不能跨dependency silently compare。
- **legacy identity drift**：最危险的工程回归之一是给 `GRPOTrainingConfig`无条件加field导致历史 `_config_hash`/resume mismatch。Refresh binding必须条件化/versioned；legacy tests应包含固定 known hash或旧 fixture readback。
- **parallel telemetry races**：当前 `PistonTransportTelemetry`是普通可变dataclass；并发前必须真正同步增量+callback，不要依赖 GIL 作为 durable counter guarantee。
- **circuit breaker sharing**：不要共享带 `_tripped` mutable state的单 breaker到多个 threads；每 request/task独立 breaker，run-level retry telemetry集中同步。
- **partial reward writes**：并发 future完成顺序不能导致提前append；只有完整 aligned batch确定无 infra failure后再写 canonical reward/group logs。
- **quality reserve**：1,086个 low-test candidates 不能因为active pool不足临时放宽 gate；若排除后无法满足3000+class+overlap constraints，WP9-c必须报告 blocker/replan。
- **active selector overfitting**：只按 calibration class/冻结 strata和稳定hash选，不看最终400题，不用 eval-hidden，不根据后续 C2/D2表现回头换题。
- **throughput optimization不能改科学实验**：不得用 fewer optimizer steps、较短 completion、不同 pool、不同 reward、不同 model/dtype来换“更快”；benchmark harness必须比对 semantic identity。
- **same-GPU并发只是候选**：4090 24GB上是否fit/是否>=15%必须 WP9-c真实测；WP9-b只实现判断逻辑。
- **GPU util unavailable**：不能把 unavailable写成0%并参与正式推荐；formal throughput report缺 required measurement就 incomplete。
- **artifact规模**：10k × 8/16 calibration completions很大；真实 bundle都在 Git外。tracked report只留 schema/hashes/counts/commands/exit codes，不提交 completion payload。
- **scope boundary**：任何真实 B inference、k=8 real training、C2/D2 checkpoint、formal 400 eval一旦在 WP9-b出现，立即停止并转到正确 validation/operator lifecycle。

## 9. 关联文档/代码索引

- `proceedings.md`：WP9 activation/frozen constraints；WP9-a finalized；next dependency-ready=`WP9-b`。
- `PROJECT_SPEC_GRPO_Refresh.md` §7：offline B calibration、8+8 retry、informativeness/classes/active pool；§8–§10：k=8/GRPO telemetry/throughput/concurrency；§11：batched evaluation；§12–§13：benchmark/artifacts；§17.2：WP9-b development scope。
- `PROJECT_SPEC_Open-R1_CodeVerifier.md` §19/§20/§21/§29：development evidence、WP9 registry、review、k=8 defaults。
- WP9-a provenance：`ai-work/planner/WP9-a-plan.md`, `ai-work/executor/WP9-a-executor.md`, `ai-work/reviewer/WP9-a-review.md`。
- current code anchors：
  - `src/code_verifier/data/refresh.py::check_refresh_data`
  - `src/code_verifier/training/grpo_data.py::build_grpo_dataset`
  - `src/code_verifier/rewards/common.py::compute_code_rewards`
  - `src/code_verifier/training/grpo.py::{build_grpo_reward_callback,_install_grpo_runtime_telemetry,run_grpo_training}`
  - `src/code_verifier/execution/piston_resilience.py::PistonTransportTelemetry`
  - `src/code_verifier/evaluation/generate.py::TransformersCompletionGenerator`
  - `src/code_verifier/evaluation/staged.py::{run_generation_bundle,run_verification_from_generation_bundle}`
  - `src/code_verifier/cli.py::{_generate_eval,_verify_eval,_train_grpo,build_parser}`。

## 10. Handoff / lifecycle

1. 下一步只能运行 `$stage-lifecycle bootstrap_plan`：把本 plan正文写入 `ai-work/planner/WP9-b-plan.md`，创建/复用 `feat/wp9-b` + `.worktrees/wp9-b`，并 commit plan seal。
2. bootstrap 前再次要求 primary `HEAD == f779d08c3ff30d66bf2d5ec5111ab69c91b9c2d8`、worktree set未变化、`.ai-bridge/current-plan.md`仍是本 plan、`.ai-bridge/**` untracked。任何不一致 → 停止/replan。
3. bootstrap得到 `plan_commit` 后，才调用 execution-router；本 plan routing为 `single / difficult_serial`。
4. executor只做 development implementation + engineering evidence；不得越过 WP9-c validation/operator boundary。
5. WP9-b review PASS/finalized并合并 main 后，`proceedings.md`再把 next dependency-ready route推进到 WP9-c；planner/executor不得提前修改 proceedings宣称 WP9-b完成。

## Implementation contract

- Work from this plan in small, reviewable steps.
- Keep edits scoped to the requested task and existing project conventions.
- Run focused verification before handing work back.
- Update .ai-bridge/agent-status.md with files touched, checks run, results, blockers, and review notes.
- Save the final review diff to .ai-bridge/implementation-diff.patch when practical.
- Append notable execution events to .ai-bridge/execution-log.jsonl when the implementation agent supports logging.
