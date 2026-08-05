# 项目实施记录（Proceedings）

> **文件功能**
>
> 本文件用于持续记录 Open-R1 Code Verifier 项目各 Work Package 的实际实施情况、验收结果、配置变更、设计决策、已知问题和 Code Review 重点，作为项目开发过程的可追溯记录。
>
> **内容与格式要求**
>
> 1. 按 Work Package 分节记录，不覆盖已经完成的历史记录。
> 2. 每个阶段应包含：阶段状态、完成范围、文件变更、配置影响、验收结果、设计决策、已知问题和 Review 重点。
> 3. 必须明确说明是否修改了项目原有配置。
> 4. 必须区分本项目代码变更与 `third_party/open-r1` 上游依赖变更。
> 5. 测试结果应记录实际执行的命令和最终结论，不得仅根据代码内容推断通过。
> 6. 如果存在未完成项或外部环境限制，应如实记录，不得将阶段标记为完成。
> 7. 后续阶段应在文件末尾追加记录，并保留已有内容。

---

## WP0：项目脚手架

- **完成日期**：2026-08-04
- **阶段状态**：已完成
- **验收结论**：通过
- **实施范围**：仅完成 WP0 项目脚手架，未提前实现 WP1 或后续 Work Package 的业务功能。

### 1. 本阶段完成事项

WP0 已完成以下工作：

1. 建立独立的 Python 项目结构。
2. 创建 `src/code_verifier` Python 包。
3. 建立基础 CLI 入口及子命令框架。
4. 建立 Open-R1 适配层：
   - `src/code_verifier/training/open_r1_adapter.py`
5. 所有对 Open-R1 的直接访问均通过适配层进行。
6. 配置本项目与 `third_party/open-r1` 的本地 editable 安装。
7. 配置 Ruff、Mypy 和 Pytest 等代码质量与测试工具。
8. 建立 WP0 单元测试。
9. 增加环境信息采集功能。
10. 生成并保存 `environment.json`。
11. 增加 Makefile，统一安装、代码检查、测试和环境记录命令。
12. 完善 README 中的安装、验收和完整训练环境说明。
13. 检查并记录 Open-R1 submodule 的固定 commit。
14. 完成 CLI、导入、静态检查和单元测试验收。
15. 修正 Ruff 检出的 import 排序问题。

### 2. Open-R1 Submodule 状态

`third_party/open-r1` 作为只读 Git Submodule 使用。




固定 commit：

```text
1416fa0cf21595d2083b399a2a0bbddd7f6e9563

```

---

## WP1：数据 Schema 与三层测试划分（完成记录）

- **完成日期**：2026-08-05
- **阶段状态**：已完成
- **验收结论**：通过
- **执行计划**：`plans/WP1-plan.md`
- **实施范围**：完成 WP1 Data Layer；未实现 WP2 解析器、WP3 执行器或后续训练、奖励和评测功能。

### 1. 本阶段完成事项

1. 实现严格 YAML 加载与 WP1 数据配置解析，未知字段、缺失字段、非法类型和不支持格式均明确失败。
2. 实现 §7.1 canonical schema，包括不可变 `CodeProblem`、`ProblemMetadata`、`TestCase`，以及严格 mapping 转换和 JSON 值校验。
3. 实现 Unicode/空白标准化、canonical JSON、SHA-256 hash、测试去重、problem ID 去重和跨 split 内容去重。
4. 实现唯一 raw JSONL 输入适配器，拒绝重复 JSON key、预分层字段、空文件和非法记录。
5. 实现 seed + problem_id 驱动的确定性三层测试划分，并保证每个测试恰好进入一层。
6. 实现数据集级泄漏检查和 SFT/Public GRPO/Hidden GRPO 三种训练字段白名单。
7. 实现原子数据准备流程、canonical JSONL 导出、Hugging Face Dataset 导出、训练 artifact 导出和磁盘回读检查。
8. 实现 `prepare-data`、`check-data` CLI，并为所有现有子命令提供公共参数。
9. 提交 20 道离线函数级 fixture：12 train、4 validation、4 test，每题 6 个唯一测试。
10. 新增 WP1 端到端测试，覆盖真实 CLI、HF Dataset、训练字段隔离、篡改失败和同 seed 字节级复现。
11. 更新 README、AGENTS 和忽略规则，移除“仅 WP0”的过期表述并记录 WP1 安全边界。

### 2. 文件变更

#### 本项目新增

- `configs/data/smoke.yaml`
- `src/code_verifier/config.py`
- `src/code_verifier/data/__init__.py`
- `src/code_verifier/data/schema.py`
- `src/code_verifier/data/adapters.py`
- `src/code_verifier/data/split_tests.py`
- `src/code_verifier/data/deduplicate.py`
- `src/code_verifier/data/leakage_checks.py`
- `src/code_verifier/data/prepare.py`
- `tests/fixtures/wp1/raw_problems.jsonl`
- `tests/unit/test_config.py`
- `tests/unit/data/__init__.py`
- `tests/unit/data/test_schema.py`
- `tests/unit/data/test_adapters.py`
- `tests/unit/data/test_split_tests.py`
- `tests/unit/data/test_deduplicate.py`
- `tests/unit/data/test_leakage_checks.py`
- `tests/unit/data/test_prepare.py`
- `tests/integration/test_wp1_data_pipeline.py`

#### 本项目修改

- `src/code_verifier/cli.py`
- `tests/unit/test_cli.py`
- `pyproject.toml`
- `Makefile`
- `.gitignore`
- `README.md`
- `AGENTS.md`
- `proceedings.md`

#### 上游依赖

- `third_party/open-r1/**`：未修改。
- submodule commit 仍为 `1416fa0cf21595d2083b399a2a0bbddd7f6e9563`。

### 3. 配置影响

本阶段**修改了项目原有配置**：

1. `pyproject.toml` 新增固定运行依赖 `PyYAML==6.0.2`、`datasets==3.2.0`。
2. 开发依赖新增 `types-PyYAML==6.0.12.20241230`，用于满足 strict Mypy；这是计划外但必要的类型桩依赖。
3. `Makefile` 新增 `DATA_PACKAGES`，`make install` 会安装 WP1 最小数据依赖；`make install-full` 语义未改变。
4. 新增 `configs/data/smoke.yaml`，固定输入格式、fixture 路径、三层数量和输出格式；seed 与 output root 仍由 CLI 提供。
5. `.gitignore` 忽略生成的 `data/processed/` 与 `outputs/`，不会忽略提交的 WP1 fixture。
6. 未修改 Open-R1 上游配置、文件或固定 commit。

### 4. 实际验收结果

以下命令均为实际执行结果：

1. `make install`：成功；`datasets` 版本为 `3.2.0`（前序部分实施记录）。
2. `.venv/bin/python -m pytest tests/unit/data/test_prepare.py`：14 passed。
3. `.venv/bin/python -m pytest tests/unit/test_cli.py`：12 passed。
4. `.venv/bin/python -m pytest tests/unit/data/test_prepare.py tests/integration/test_wp1_data_pipeline.py`：18 passed。
5. `make lint`：通过；Ruff check、Ruff format check、strict Mypy 全绿，Mypy 检查 25 个源文件无问题。
6. `make test`：108 passed，包含 WP0 回归、WP1 单元测试和 4 个端到端测试。
7. `.venv/bin/python -m code_verifier.cli prepare-data --config configs/data/smoke.yaml --seed 42 --output-dir data/processed/wp1-smoke --log-level INFO`：返回 0；导出 20 题，split 为 12/4/4。
8. `.venv/bin/python -m code_verifier.cli check-data --dataset data/processed/wp1-smoke --seed 42 --output-dir outputs/check-data --log-level INFO`：返回 0。
9. HF/JSONL/训练 artifact 独立磁盘核对：HF Dataset 20 行、canonical JSONL 20 行、三种 training JSONL 各 12 行；所有训练文件不含 `eval_hidden_tests`，Public 不含 `train_hidden_tests`，SFT 不含任何测试字段。
10. `prepare-data --help` 与 `check-data --help`：均返回 0，并显示公共参数。
11. `git -C third_party/open-r1 rev-parse HEAD`：`1416fa0cf21595d2083b399a2a0bbddd7f6e9563`。
12. CodexPro 对 `third_party/open-r1` 的变更检查：无 changed files、无 diff。

### 5. 设计决策与计划偏离

1. canonical JSONL 始终保持 §7.1 的原始 JSON 结构，是审计和后续评测的唯一权威格式。
2. 20 题 fixture 的测试值包含整数、字符串、列表、字典和嵌套结构。Apache Arrow 不支持在同一列中直接保存任意异构 JSON union，原计划的直接 `Dataset.from_list(problem_to_mapping(...))` 会失败并报 `cannot mix list and non-list, non-null values`。
3. 为保留 fixture 语义且不伪造同构测试，HF Dataset 对每个测试的 `input`/`expected` 使用确定性 canonical JSON 文本作为可逆表示。`check-data` 会逐行解码并与 canonical JSONL 完整比对；任何不一致都会失败。该偏离已在 README 明确记录。
4. 训练 artifact 从空字典按每种用途的显式白名单构造，不从完整 canonical 记录删字段，降低隐藏测试误序列化风险。
5. 所有影响测试分层的随机性只使用 seed 和 problem_id 派生的局部 PRNG，不修改全局随机状态。

### 6. 已知限制

1. 近似去重只覆盖 Unicode NFKC、换行、行尾空白和普通空白规范化，不检测语义或 AST 等价。
2. WP1 不执行 fixture 中的 `reference_solution` 或 `sft_response`；这些内容仅用于结构和导出 smoke 验证。
3. HF Dataset 中测试值需先从 canonical JSON 文本解码；后续消费者应优先使用 Data Layer 提供的读取/检查路径，而不是假设 Arrow 原生 union。
4. 未实现训练 dataloader、代码解析、安全执行、奖励或评测；这些属于后续 WP。

### 7. Code Review 重点

1. 审查 `schema.py` 的严格字段集合、类型边界和不可变数据语义。
2. 审查 `split_tests.py` 的 seed 派生与三层并集/交集不变量。
3. 审查 `leakage_checks.py` 的三种字段白名单和递归 `eval_hidden_tests` 检查。
4. 审查 `prepare.py` 的临时目录清理、原子发布、训练文件回读和 HF 可逆编码/比对。
5. 确认 `third_party/open-r1` 无变更，且本阶段未混入 WP2 及以后功能。
6. 确认生成目录 `data/processed/wp1-smoke/` 与 `outputs/` 仅为本地验收产物并被 `.gitignore` 排除。

### 8. 阶段结论

WP1 的目标、7 项交付和 4 项验收均已满足。阶段状态由“未完成”更新为“已完成”，可以进入人工 Code Review 和下一 WP 规划；本次未执行 git commit 或 push。

---

## WP1 修复轮次 R1：独立审查问题修复

- **修复日期**：2026-08-05
- **修复依据**：`reviews/WP1-review.md`
- **执行计划**：`plans/WP1-plan.md`
- **阶段状态**：修复完成，待独立复审
- **代码验收结论**：通过

### 1. 审查问题处置

1. **M1：训练 artifact 未与 canonical 绑定——已修复。**
   - 新增 `load_training_artifact()`，在结构校验后返回磁盘记录。
   - `check_prepared_data()` 现在从 canonical train problems 使用 `build_training_record()` 重建三种期望视图，并核对问题 ID 类型、重复、缺失、额外、顺序和完整记录内容。
   - eval-hidden 内容即使改名为 `visible_tests`，以及非 train 题替换、重复/遗漏、prompt 或允许测试字段篡改，均会失败。
2. **M2：跨 split 去重只检查完整复合 hash——已修复。**
   - 分别建立规范化 `prompt + function_signature`、reference solution、完整测试集合和匹配函数签名的单测试索引。
   - 错误信息包含冲突类型、problem IDs 和 split。
3. **M3：冻结 dataclass 内 JSON 容器仍可变——已修复。**
   - JSON array 递归冻结为 tuple，JSON object 递归冻结为只读 mapping proxy。
   - `TestCase.__post_init__()` 同时覆盖 parser 与直接构造路径；序列化边界恢复标准 list/dict §7.1 结构。
4. **m1：HF Dataset 字段结构偏离但未正式定义——已修复。**
   - 定义版本 `wp1-canonical-json-v1` 和字段 `code_verifier_schema`。
   - 新增公开 `load_hf_dataset()` 解码 API，拒绝未知版本并恢复 canonical `input` / `expected`。
   - README 已记录编码合同与公共加载方式。
5. **m2：缺少 Git 跟踪基线——未在本轮执行。**
   - 原因：executor 规则禁止在用户未明确授权时执行 git commit / push；当前任务未授权提交。
   - 该项是版本控制与审查流程限制，不影响本轮代码和运行验收；仍需人工按 WP0/WP1/修复轮次建立清晰提交边界。
6. 审查报告中的 CLI help 和未来 reference label 执行属于建议项，本轮未处理；后者明确属于 WP3 以后能力。

### 2. 本轮文件变更

- `src/code_verifier/data/schema.py`
- `src/code_verifier/data/deduplicate.py`
- `src/code_verifier/data/leakage_checks.py`
- `src/code_verifier/data/prepare.py`
- `tests/unit/data/test_schema.py`
- `tests/unit/data/test_deduplicate.py`
- `tests/unit/data/test_leakage_checks.py`
- `tests/unit/data/test_prepare.py`
- `tests/integration/test_wp1_data_pipeline.py`
- `README.md`
- `proceedings.md`

### 3. 配置影响

- 本轮**未修改** `pyproject.toml`、`Makefile`、YAML 配置或依赖版本。
- HF Dataset 的磁盘行结构新增显式 schema version 字段，属于数据接口版本化，不是项目安装配置变更。
- `third_party/open-r1/**` 未修改，固定 commit 未改变。

### 4. 新增或修改的主要符号

- `FrozenJsonValue`
- `JsonInputValue`
- `TestCase.__post_init__()`
- `json_value_to_mutable()`
- `problem_prompt_signature_hash()`
- `problem_reference_solution_hash()`
- `problem_test_set_hash()`
- `load_training_artifact()`
- `HF_DATASET_SCHEMA_VERSION`
- `HF_DATASET_SCHEMA_FIELD`
- `load_hf_dataset()`
- `_check_training_artifact_matches_canonical()`

### 5. 实际验证结果

1. `.venv/bin/python -m pytest tests/unit/data/test_schema.py tests/unit/data/test_deduplicate.py tests/unit/data/test_prepare.py`：59 passed。
2. `.venv/bin/python -m pytest tests/integration/test_wp1_data_pipeline.py tests/unit/data/test_prepare.py tests/unit/data/test_deduplicate.py tests/unit/data/test_schema.py`：63 passed。
3. `make lint`：通过；Ruff check、Ruff format check、strict Mypy 全绿，25 个源文件无问题。
4. `make test`：118 passed。
5. fresh `prepare-data`：返回 0，导出 20 problems，split 为 12/4/4。
6. fresh `check-data`：返回 0，验证 20 problems，split 为 12/4/4。
7. 针对性 M1 复现：将 canonical eval-hidden 内容放入 `public_grpo.visible_tests` 后，`check-data` 返回 2，错误为记录不匹配 canonical training view。
8. 针对性 M2 复现：相同 prompt/signature、不同测试与 reference solution 的跨 split 题目被拒绝。
9. 针对性 M3 复现：直接修改构造后嵌套 JSON 容器抛出 `TypeError`。
10. HF Dataset：schema version 为 `wp1-canonical-json-v1`，raw 20 行，公开 decoder 恢复 20 个 canonical problems。
11. `third_party/open-r1` 变更检查：无 changed files、无 diff；commit 为 `1416fa0cf21595d2083b399a2a0bbddd7f6e9563`。

### 6. 已知限制与复审重点

1. 去重仍是确定性规范化 hash，不检测语义或 AST 等价；但已分离主要污染信号，避免复合 hash 掩盖单项重复。
2. 单测试跨 split 检查以规范化函数签名为上下文，避免不同任务共享通用边界值造成大量误报。
3. Git 跟踪基线问题仍需人工建立；本轮未执行 commit、stage 或 push。
4. 复审应重点重复 M1/M2/M3 的三项针对性负向检查，并核对版本化 HF Dataset 公共解码接口。

### 7. 修复结论

`reviews/WP1-review.md` 中 3 个主要问题与可由代码处理的次要问题 m1 已完成修复，所有代码验收和 WP1 smoke 验收通过。次要问题 m2 已记录为需要人工授权的版本控制收尾事项。WP1 当前状态为“修复完成，待独立复审”，不得将本记录替代 reviewer 的复审结论。

---

## WP1 修复轮次 R2：严格 JSON 绑定（依据 reviews/WP1-review-r2.md）

- **修复日期**：2026-08-05
- **修复依据**：`reviews/WP1-review-r2.md`
- **执行计划**：`plans/WP1-plan.md`
- **阶段状态**：修复完成，待独立复审（R2 复审结论为“需修改”，不得视为验收通过）

### 1. 审查问题处置

1. **M1-R2 绕过 A：重复 JSON key 可隐藏 eval-hidden 内容——已修复。**
   - 新增公共严格 JSON loader `src/code_verifier/data/json_strict.py`，所有受信任 JSONL 读取路径（raw adapter、canonical JSONL、训练 artifact）统一拒绝重复 key，包括嵌套 object。
   - `load_training_artifact()` 与 `_load_canonical()` 均改用 `loads_strict()`；raw adapter 复用同一 loader，删除本地重复 hook。
2. **M1-R2 绕过 B：Python bool/int/float 宽松相等绕过 canonical 绑定——已修复。**
   - 新增类型敏感的 `json_values_equal()`；训练记录与 canonical 期望视图的比较从 `dict != dict` 改为严格 JSON 等价（`True != 1`、`False != 0`、`128 != 128.0`）。
   - 期望视图由 `build_training_record()` 从已完整校验的 canonical 问题生成，严格比较同时覆盖字段类型校验，故无需重复的独立类型校验层。
3. **新增负向测试（全部通过）**：
   - 顶层重复 JSON key、嵌套 object 重复 key；
   - 重复 key 前一个承载 eval-hidden 内容（错误路径返回 2 且错误信息不打印隐藏测试值）；
   - visible `True/False` 与 eval-hidden `1/0` 类型等价替换被拒绝；
   - `memory_limit_mb` 128 → 128.0 类型漂移被拒绝；
   - `json_values_equal()` 类型敏感性单元测试。
4. **m2：Git 跟踪基线——本轮部分处理。**
   - 本轮建立 `feat/wp1` 分支并提交，形成 WP0 脚手架与 WP1 实施两个提交边界；合并回主分支待复审通过后由 reviewer 执行。
   - 由于此前不存在任何已提交基线，R1 与 R2 修复在 Git 层面无法分离为独立提交，轮次边界以本文件与审查报告记录为准。
5. 审查报告中的 CLI help 文本与 fixture 可信执行验证属于建议项，非默认修复范围，本轮未处理。

### 2. 本轮文件变更

#### 本项目新增

- `src/code_verifier/data/json_strict.py`

#### 本项目修改

- `src/code_verifier/data/adapters.py`
- `src/code_verifier/data/leakage_checks.py`
- `src/code_verifier/data/prepare.py`
- `tests/unit/data/test_adapters.py`
- `tests/unit/data/test_leakage_checks.py`
- `tests/unit/data/test_prepare.py`
- `tests/integration/test_wp1_data_pipeline.py`
- `proceedings.md`

#### 上游依赖

- `third_party/open-r1/**`：未修改；submodule commit 仍为 `1416fa0cf21595d2083b399a2a0bbddd7f6e9563`。

### 3. 配置影响

- 本轮**未修改** `pyproject.toml`、`Makefile`、YAML 配置、依赖版本或 CLI 参数。

### 4. 新增或修改的主要符号

- `code_verifier.data.json_strict.StrictJsonError`
- `code_verifier.data.json_strict.loads_strict()`
- `code_verifier.data.json_strict.json_values_equal()`
- `load_training_artifact()`（改用严格 loader）
- `_load_canonical()`（改用严格 loader）
- `_check_training_artifact_matches_canonical()`（改用类型敏感比较）

### 5. 实际验证结果（均为真实执行命令）

1. `make lint`：通过；ruff check、ruff format --check、strict Mypy 全绿，26 个源文件。
2. `make test`：135 passed。
3. fresh `prepare-data`：返回 0，20 problems，split 12/4/4。
4. fresh `check-data`：返回 0，20 problems。
5. 重复 key 攻击（前一个 `visible_tests` 承载 eval-hidden 内容）：`check-data` 返回 2，错误为 `duplicate JSON key 'visible_tests'`，未打印隐藏测试值。
6. int/float 类型漂移（`memory_limit_mb` 128 → 128.0）：`check-data` 返回 2。
7. visible bool 与 eval-hidden int 替换：单元/集成测试通过（错误路径拒绝）。
8. HF Dataset：raw 20 行，`load_hf_dataset()` 解码 20 个 canonical problems。
9. `third_party/open-r1` 变更检查：无 changed files、无 diff；commit 为 `1416fa0cf21595d2083b399a2a0bbddd7f6e9563`。

### 6. 已知限制与 Review 重点

1. 严格 JSON 绑定针对已命名 key 的重复与类型漂移；不同 JSON 消费器对重复 key 的语义差异已被统一拒绝。
2. 本轮提交边界为 WP0 脚手架 + WP1 实施两层；修复轮次边界由审查报告与本记录承担可追溯性。
3. 复审应重点重复：重复 key 攻击、bool/int 替换、int/float 漂移、fresh prepare/check、HF 解码，并核对严格 loader 覆盖全部受信任 JSONL 路径。

### 7. 修复结论

M1-R2 的两个绕过均已修复并通过负向测试，R2 报告中的可代码处理项已全部处置；本记录不替代 reviewer 的复审结论，WP1 是否通过以下一轮复审为准。
