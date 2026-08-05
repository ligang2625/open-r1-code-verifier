# WP1 独立复审报告 R2

## 1. 审查范围与方法

- 复审日期：2026-08-05
- 计划文件：`plans/WP1-plan.md`
- 上一轮报告：`reviews/WP1-review.md`
- executor 修复记录：`proceedings.md` 中“WP1 修复轮次 R1：独立审查问题修复”
- 规格依据：`PROJECT_SPEC_Open-R1_CodeVerifier.md` §0、§6.2、§7.1、§7.3、§7.4、§17、§19、§20、§21.1、§21.3
- 审查方式：逐条复核上一轮 M1、M2、M3、m1、m2；阅读修复后的实现与测试；独立运行 lint、全量测试、fresh CLI pipeline、HF Dataset 解码和针对性负向检查。
- 审查边界：未修改 `src/`、`tests/` 或 `third_party/open-r1/`；仅新增本复审报告。

### 1.1 审查流程限制

当前 CodexPro 工作区为主仓库 `/home/dzy/open-r1-code-verifier`，分支为 `main`，项目文件仍整体处于未跟踪状态。修复内容没有可由 Git 比较的已提交基线，也不存在可完整承载这些未跟踪文件的阶段 worktree。因此本次只能在当前工作区进行只读复审，无法按新版 reviewer skill 完成“独立 worktree、提交报告、审查通过后合并”的流程。

该限制不影响本报告中的代码阅读和命令取证，但以下事项仍无法独立核实：

- 修复前后精确 Git diff；
- 测试预期是否曾被调整以迁就实现；
- WP0、WP1 初始实现和 R1 修复的提交边界。

## 2. 上一轮问题复核

| 上一轮问题 | 复审状态 | 证据与结论 |
|---|---|---|
| M1：训练 artifact 未与 canonical 绑定 | **修复不完整** | `src/code_verifier/data/prepare.py:330-361` 已按 canonical train problems 重建期望记录，并检查 ID、顺序和记录内容；普通字段替换及直接将 eval-hidden 放入 visible 的路径会失败。但 JSON 重复 key 和 Python 数值相等性仍能绕过检查，详见新主要问题 M1-R2。 |
| M2：跨 split 去重只检查完整复合 hash | **已修复** | `src/code_verifier/data/deduplicate.py:72-95` 分离 prompt/signature、reference solution、test set hash；`155-181` 建立独立索引并检查匹配签名的单测试重合。独立复现中，相同 prompt/signature、不同测试和参考实现的跨 split 题目被正确拒绝。 |
| M3：冻结 dataclass 内 JSON 容器仍可变 | **已修复** | `src/code_verifier/data/schema.py:21-31` 在 `TestCase.__post_init__()` 中冻结直接构造输入；`113-147` 将 list 冻结为 tuple、mapping 冻结为 `MappingProxyType`，序列化时恢复 list/dict。独立修改嵌套 mapping 和 tuple 均抛 `TypeError`。 |
| m1：HF Dataset 字段偏离未正式定义 | **已修复** | `src/code_verifier/data/prepare.py:33-34` 定义 `wp1-canonical-json-v1`；`187-257` 写入版本字段并提供 `load_hf_dataset()` 公共解码接口。独立验证 raw 和 decoded 均为 20 行，所有行版本一致。README `77-87` 已记录合同。 |
| m2：缺少 Git 跟踪基线 | **未修复** | 当前所有项目文件仍为未跟踪状态；`proceedings.md:207-209` 也明确记录未处理。该问题继续限制审查可追溯性。 |
| CLI help 文本建议 | **未处理，建议项** | `prepare-data --help` 的 `--output-dir` 说明仍写有 “check-data accepts it...”，不影响核心功能。 |

## 3. WP1 交付与验收核验

### 3.1 交付核验

| 计划交付 | 状态 | 证据 |
|---|---|---|
| schema | 通过 | 严格字段校验、冻结 JSON 内部表示、标准 §7.1 序列化和单元测试均存在。 |
| 输入适配器 | 通过 | raw JSONL 字段、重复 key、空文件、行号错误处理保持有效；全量测试通过。 |
| test split | 通过 | seed + problem_id 局部 PRNG、严格数量、三层唯一性和可复现性测试通过。 |
| hash | 通过（WP1 定义范围） | NFKC/空白规范化、canonical JSON 和 SHA-256 稳定；不声称语义或 AST 等价。 |
| 去重 | 通过（WP1 定义范围） | ID、prompt/signature、reference solution、test set、匹配签名单测试跨 split 检查均已实现。 |
| leakage checks | **未完全通过** | 正常生成文件和普通篡改可检查，但训练 JSON 的重复 key 与 Python 类型宽松相等可绕过 canonical 绑定。 |
| 20 道题 fixture | 通过（结构层面） | fresh pipeline 导出 20 题，12/4/4 split，HF 20 行，训练 artifact 各 12 行。 |

### 3.2 核心验收核验

| 验收项 | 状态 | 证据 |
|---|---|---|
| fixture 可导出 JSONL/Dataset | 通过 | fresh `prepare-data` 返回 0；canonical 20 行；HF raw 20 行，公共 decoder 恢复 20 个 canonical problems。 |
| 三层测试无重复 | 通过 | `make test` 全绿；fresh pipeline 和 `check_dataset()` 通过。 |
| 删除或混入字段时测试能失败 | 部分通过 | 删除字段、直接增加 `eval_hidden_tests`、普通内容替换均失败；重复 key 和 JSON 类型等价绕过仍会成功。 |
| 训练 artifact 不含 eval hidden 测试 | **未通过为通用保证** | fresh 输出本身安全，但针对性构造证明 eval-hidden 内容仍可被序列化进训练文件并通过 `check-data`。 |

## 4. 新问题清单

### 4.1 主要问题

#### M1-R2：训练 artifact 的 canonical 绑定不是严格 JSON 绑定，仍可泄漏 eval-hidden 内容

位置：

- `src/code_verifier/data/leakage_checks.py:182-205`
- `src/code_verifier/data/prepare.py:330-361`
- `tests/unit/data/test_prepare.py:218-251`
- `tests/integration/test_wp1_data_pipeline.py:130-161`

当前实现有两个独立绕过。

##### 绕过 A：重复 JSON key

`load_training_artifact()` 在 `leakage_checks.py:193` 使用普通 `json.loads(line)`。与 raw 输入适配器不同，它没有使用拒绝重复 key 的 `object_pairs_hook`。

独立复现步骤：

1. 对 fresh `public_grpo.jsonl` 第一行增加两个 `visible_tests` key；
2. 第一个 `visible_tests` 保存同题 canonical `eval_hidden_tests`；
3. 第二个 `visible_tests` 保留合法 visible tests；
4. 原始 JSONL 字节中确实存在 eval-hidden 测试内容；
5. Python `json.loads` 只保留后一个合法值；
6. `check-data` 返回 0，并输出 `checked 20 problems`。

影响：

- 直接违反规格 §7.4(2)“eval hidden 不得被序列化到训练数据文件”；
- 不同 JSON 消费器对重复 key 的处理可能不同，不能依赖“最后一个 key 获胜”；
- 当前测试只覆盖解析后的结构，不覆盖原始训练 JSON 的重复 key。

##### 绕过 B：Python 宽松数值相等性

`prepare.py:357-360` 使用 `actual_record != expected_record` 比较解析后的 Python dict。Python 中：

- `True == 1`；
- `False == 0`；
- `1 == 1.0`。

这不是严格的 JSON 类型比较。

独立复现构造了一个合法数据集，其中同一题：

- visible tests 为 `True` / `False`；
- eval-hidden tests 为 `1` / `0`；
- 这些测试具有不同 canonical JSON 和不同测试 hash，因此三层去重允许它们存在；
- 将 `public_grpo.visible_tests` 替换为 eval-hidden 的整数测试后，`check_prepared_data()` 仍正常返回。

实际输出：

```text
accepted_eval_hidden_via_bool_int_equality
visible: True / False
eval-hidden: 1 / 0
```

另一个较轻的复现是将 `metadata.memory_limit_mb` 从整数 `128` 改为浮点 `128.0`，`check-data` 同样返回 0。

影响：

- eval-hidden 测试可以在 JSON 类型不同但 Python 比较相等时替换 visible tests；
- “完整记录内容匹配”和 README `96` 所称的 “exact training-record equivalence” 不成立；
- 类型漂移可能改变后续训练、序列化、执行器或跨语言消费者行为。

建议修复：

1. 在所有受信任 JSONL 读取路径中统一拒绝重复 key，包括嵌套 object；可复用 raw adapter 的 duplicate-key hook，或抽取公共严格 JSON loader。
2. 不使用 Python `dict == dict` 作为严格 JSON 等价判断。应比较：
   - `canonical_json(actual_record) == canonical_json(expected_record)`；或
   - 显式的类型敏感递归比较，确保 bool、int、float 不互相等价。
3. 在比较前对训练记录执行完整字段类型校验，而不仅是 `validate_json_value()` 的“可序列化”校验。
4. 新增负向测试：
   - 允许字段重复 key，前一个承载 eval-hidden 内容；
   - 嵌套 object 重复 key；
   - visible `True/False` 与 eval `1/0` 替换；
   - int 与 float 类型漂移；
   - 确认错误路径返回 2，且错误不打印隐藏测试值。

### 4.2 次要问题

#### m2-R2：版本控制基线仍未建立

当前项目文件仍整体未跟踪。该问题不造成运行时缺陷，但继续导致：

- 无法审计 WP1 的精确增量；
- 无法核实测试预期历史；
- 无法按 reviewer skill 在独立 worktree 中完成提交和合并流程；
- 后续 WP 的回滚和 review 边界不清晰。

建议在 M1-R2 修复并复审通过后，由人工明确授权建立 WP0、WP1 和修复轮次的清晰提交边界。

### 4.3 建议项

- 为 `prepare-data` 和 `check-data` 分别提供准确的 `--output-dir` help 文本。
- 在安全执行器完成后，对 fixture/reference labels 增加可信执行验证；该项不属于 WP1 阻断条件。

## 5. 独立测试结果

### 5.1 静态检查与全量测试

- `make lint`：退出码 0。
  - Ruff check：`All checks passed!`
  - Ruff format：`25 files already formatted`
  - Mypy：`Success: no issues found in 25 source files`
- `make test`：退出码 0。
  - 收集 118 项；
  - 结果：`118 passed in 2.27s`。

### 5.2 fresh pipeline

- `prepare-data`：退出码 0；20 problems；split 为 train=12、validation=4、test=4。
- `check-data`：退出码 0；20 problems；split 为 12/4/4。
- HF Dataset：
  - raw 行数 20；
  - decoded problems 20；
  - schema version 集合为 `{wp1-canonical-json-v1}`。
- 依赖版本：
  - `datasets=3.2.0`；
  - `pyyaml=6.0.2`。
- `prepare-data --help`、`check-data --help`：均返回 0并包含公共参数。

### 5.3 上轮主要问题针对性复现

| 检查 | 预期 | 实际 | 结论 |
|---|---|---|---|
| 普通方式将 canonical eval-hidden 替换进 public visible | 返回 2 | 返回 2 | M1 普通路径已修复 |
| 相同 prompt/signature 跨 split、测试与答案不同 | 拒绝 | 拒绝，报告 `prompt/signature overlaps` | M2 已修复 |
| 修改构造后嵌套 mapping/array | 抛 TypeError | 两项均抛 TypeError | M3 已修复 |
| HF 公共 decoder 和版本字段 | 20 行、版本匹配 | 通过 | m1 已修复 |

### 5.4 新负向检查

| 检查 | 预期 | 实际 | 结论 |
|---|---|---|---|
| 同一训练 record 写两个 `visible_tests` key，前者为 eval-hidden、后者为合法 visible | 返回 2 | 返回 0 | 失败，证明 M1-R2 绕过 A |
| visible 为 bool、eval-hidden 为等值 int，使用 eval 替换 visible | 返回 2 | 返回 0 | 失败，证明 M1-R2 绕过 B |
| `memory_limit_mb` 从 `128` 改为 `128.0` | 返回 2 | 返回 0 | 失败，证明非严格 JSON 类型比较 |

### 5.5 上游边界

- `third_party/open-r1`：无 changed files、无 diff。
- 固定 commit：`1416fa0cf21595d2083b399a2a0bbddd7f6e9563`。

## 6. executor 修复声明核验

| `proceedings.md` R1 声明 | 核验状态 | 说明 |
|---|---|---|
| M1 已修复，eval 内容改名后会失败 | **部分属实** | 普通替换会失败，但重复 key 和 bool/int JSON 类型绕过仍可成功。 |
| M2 已修复 | 核实通过 | 代码、单元测试和独立复现一致。 |
| M3 已修复 | 核实通过 | 嵌套容器不可变。 |
| HF Dataset 已版本化并提供公共解码 | 核实通过 | 版本字段、解码 API、README 和独立运行一致。 |
| `make lint` 通过 | 核实通过 | 本审查方独立运行。 |
| `make test` 为 118 passed | 核实通过 | 本审查方独立运行。 |
| fresh prepare/check、20 行、12/4/4 | 核实通过 | 本审查方独立运行。 |
| 三个主要问题均已完整修复 | 与事实不符 | M1 仍存在两个可复现的严格 JSON 绑定绕过。 |
| 所有 WP1 smoke 验收通过 | 与事实不符 | “训练 artifact 不含 eval hidden 测试”的通用保证仍未满足。 |
| third_party 未修改、commit 未变 | 核实通过 | 无 diff，commit 匹配。 |
| 未修改测试预期以迁就实现 | 无法核实 | 缺少 Git 跟踪基线。 |

## 7. 结论

- 复审结论：**需修改，WP1 当前仍不能判定通过。**
- 上轮 M2、M3 和次要问题 m1 已有效修复；happy-path pipeline、118 项测试、HF Dataset 版本化和普通训练内容篡改检测均正常。
- 上轮 M1 属于**修复不完整**：训练 artifact 的校验仍不是严格 JSON 校验。重复 key 可将 eval-hidden 原始内容写入训练文件而被解析器忽略；Python bool/int/float 宽松相等可让 JSON 层面不同的 eval-hidden 测试替换 visible 后通过检查。
- 根据 reviewer skill 判定规则，上轮主要问题仍未完全修复，且涉及数据/测试层泄漏，因此不得合并、不得将 WP1 标记为验收通过，也不建议进入 WP2。
- 下一次复审 Gate：修复严格 JSON loader 和类型敏感 canonical 比较，补充上述三类负向测试后，重新运行 `make lint`、`make test`、fresh prepare/check、重复 key 攻击、bool/int eval 替换和 HF 解码验证。
