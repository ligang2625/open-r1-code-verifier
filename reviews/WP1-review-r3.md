# WP1 独立复审报告 R3

## 1. 审查范围与方法

- 复审日期：2026-08-05
- 计划文件：`plans/WP1-plan.md`
- 上一轮报告：`reviews/WP1-review-r2.md`
- executor 修复记录：`proceedings.md` 中“WP1 修复轮次 R2：严格 JSON 绑定”
- 规格依据：`PROJECT_SPEC_Open-R1_CodeVerifier.md` §0、§6.2、§7.1、§7.3、§7.4、§17、§19、§20、§21.1、§21.3
- 审查方式：逐条复核 R2 问题清单；阅读修复后源码与测试；独立运行 `make lint`、`make test`、fresh CLI pipeline、重复 key 攻击、int/float 漂移、HF Dataset 解码；针对 HF 回读路径执行类型漂移与重复 key 探针。
- 审查边界：未修改 `src/`、`tests/` 或 `third_party/open-r1/`；仅新增本复审报告。

### 1.1 审查流程限制

与 R2 相同，当前仍无独立 stage worktree：本阶段代码以 `feat/wp1` 分支形式存在于主仓库工作区（提交 `e76319b`、`5a47ebf`），审查在主仓库的 `feat/wp1` 分支上进行。该限制不影响代码阅读与命令取证；本轮已具备 Git 提交基线，可核对 executor 的提交边界与 main 分支未被改动。

## 2. 上一轮问题核验

| 上一轮问题 | 复审状态 | 证据与结论 |
|---|---|---|
| M1-R2 绕过 A：重复 JSON key 可隐藏 eval-hidden 内容 | **已修复** | `src/code_verifier/data/json_strict.py` 提供公共 `loads_strict()`；raw adapter（`adapters.py:127`）、训练 artifact（`leakage_checks.py:193`）、canonical JSONL（`prepare.py:322`）三条受信任 JSONL 读取路径全部使用。独立 CLI 复现：前一个 `visible_tests` 承载 eval-hidden 内容 → `check-data` 返回 2，错误为 `duplicate JSON key 'visible_tests'`，未打印隐藏测试值；嵌套重复 key 由 `test_load_training_artifact_rejects_nested_duplicate_json_key` 与 raw adapter 测试覆盖。 |
| M1-R2 绕过 B：Python bool/int/float 宽松相等绕过 canonical 绑定 | **已修复** | `json_values_equal()`（`json_strict.py:30`）类型敏感（`True != 1`、`False != 0`、`128 != 128.0`）；`prepare.py:359` 训练记录比较改用该函数。独立复现：`memory_limit_mb` 128→128.0 → `check-data` 返回 2；visible `True/False` 与 eval `1/0` 替换由 `test_check_prepared_data_rejects_bool_int_test_type_drift` 覆盖并通过。 |
| m2：缺少 Git 跟踪基线 | **部分处理** | `feat/wp1` 分支已建，`e76319b`（WP0 脚手架+工具链）、`5a47ebf`（WP1 数据层）两个提交边界清晰；`main` 仍停留在 `a0e0853` 未被改动。R1/R2 修复轮次因无前置基线无法在 Git 层面分离，由 proceedings 与审查报告承担可追溯性——与 executor 声明一致。合并回 main 由本轮复审通过后执行。 |
| 建议项：CLI help 文本、fixture 可信执行验证 | 未处理（符合默认范围） | 非“阻断/主要/次要”范围，executor 未处理属实；其中 CLI help 文本属于低成本建议项，见 4.2。 |

## 3. WP1 交付与验收核验

| 验收项（计划 §5 / §20） | 状态 | 证据 |
|---|---|---|
| fixture 可导出 JSONL/Dataset | 通过 | fresh `prepare-data`/`check-data` 返回 0；canonical 20 行，split 12/4/4；HF raw 20 行，公共 decoder 恢复 20 个 canonical problems。 |
| 三层测试无重复 | 通过 | `make test` 全绿；`check_dataset()` 通过。 |
| 删除或混入字段时测试能失败 | 通过 | 删除字段、混入 `eval_hidden_tests`、普通内容替换、重复 key 隐藏、bool/int 与 int/float 类型漂移均失败（返回 2）。 |
| 训练 artifact 不含 eval hidden 测试 | 通过 | fresh 输出字节级无 `eval_hidden_tests`；重复 key 与类型等价绕过均被 `check-data` 拒绝。 |

## 4. 问题清单

### 4.1 新发现（次要）

#### m3-R3：HF Dataset 回读校验仍使用宽松 Python 相等，编码测试 JSON 未使用严格解析

位置：

- `src/code_verifier/data/prepare.py:211-213`（`_hf_test_case_to_mapping` 使用非严格 `json.loads`）
- `src/code_verifier/data/prepare.py:373-375`（`check_prepared_data` 中 `problem_to_mapping(decoded) != problem_to_mapping(problem)`）

独立探针结果：

```text
loose problem_to_mapping equal: True   # canonical visible=True vs decoded visible=1
strict json_values_equal:      False
hf dup-key decode: {'input': {'a': 2}, 'expected': 0}   # '{"a":1,"a":2}' 静默取后者
```

即：若 HF Dataset 被篡改为类型漂移（bool↔int）或编码 JSON 含重复 key，`check-data` 仍可能判定通过。与已修复的 M1-R2 同属“非严格 JSON 校验”，但影响面不同：HF Dataset 合法包含三层测试（含 eval-hidden），因此**不构成训练/评测隔离泄漏**，仅削弱 HF artifact 与 canonical 的一致性校验。

建议（非本轮阻断）：HF 回读比较改用 `json_values_equal()`，编码测试 JSON 改用 `loads_strict()`，并补 bool/int 漂移负向测试。

### 4.2 建议项（非默认修复范围）

- `prepare-data` / `check-data` 的 `--output-dir` help 文本仍共用“check-data accepts it...”表述（`cli.py` 公共参数）；建议按命令拆分准确说明。
- fixture/reference label 的可信执行验证属 WP3 执行器之后的能力，不构成 WP1 阻断条件。

## 5. 独立测试结果

- `make lint`：通过；Ruff check、Ruff format --check、strict Mypy 全绿，26 个源文件。
- `make test`：**135 passed**。
- fresh `prepare-data`：返回 0；20 problems，split 12/4/4。
- fresh `check-data`：返回 0。
- 重复 key 攻击（前一个 `visible_tests` 承载 eval-hidden）：`check-data` 返回 2，错误 `duplicate JSON key 'visible_tests'`，无隐藏值泄露。
- int/float 漂移（`memory_limit_mb` 128→128.0）：`check-data` 返回 2。
- visible bool 与 eval int 替换：单元/集成测试通过（拒绝）。
- HF Dataset：raw 20 行；`load_hf_dataset()` 解码 20 个 canonical problems。
- 上游边界：`third_party/open-r1` 无 changed files；固定 commit `1416fa0cf21595d2083b399a2a0bbddd7f6e9563` 未变。

## 6. executor 修复声明核验

| `proceedings.md` R2 声明 | 核验状态 | 说明 |
|---|---|---|
| 统一严格 loader 覆盖全部受信任 JSONL 路径 | 核实通过 | 三处 JSONL 读取路径均使用 `loads_strict()`；剩余 `json.loads` 位于 HF 编码字符串解码，非 JSONL 路径。 |
| 类型敏感比较修复绕过 B | 核实通过 | `json_values_equal()` 使用中；两类漂移均拒绝。 |
| 四类负向测试通过 | 核实通过 | 本审查方独立运行全量测试 135 passed。 |
| `make lint` / `make test` 通过 | 核实通过 | 本审查方独立运行。 |
| m2 部分处理（feat/wp1 两提交） | 核实通过 | `git log` 与 `git status` 一致；main 未动。 |
| third_party 未修改、commit 未变 | 核实通过 | 无 diff，commit 匹配。 |
| 未修改测试预期以迁就实现 | 部分可核实 | 新增负向测试断言真实拒绝行为且 `json_values_equal` 测试为类型敏感，未见迁就实现迹象；R1→R2 的测试预期历史因无前置基线仍不可完全比对。 |

## 7. 结论

- 复审结论：**通过，WP1 判定验收通过，可进入 WP2。**
- 依据：上一轮“阻断/主要”问题（M1-R2 两个绕过）均已修复并独立复现验证；无新增“阻断/主要”问题；计划验收项全部通过。
- 残余问题：HF 回读严格化（次要，m3-R3）与两条建议项不阻断验收，建议在 WP2 前或随 WP2 一并处理。
- 合并提交：本审查方在结论为“通过”后执行 `git merge --no-ff feat/wp1` 回主分支；合并 hash 见合并记录（如已执行）。
