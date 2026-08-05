# WP1 独立审查报告

## 1. 审查范围与方法

- 审查日期：2026-08-05
- 计划文件：`plans/WP1-plan.md`
- executor 完成报告：`proceedings.md` 中“WP1：数据 Schema 与三层测试划分（完成记录）”
- 规格依据：`PROJECT_SPEC_Open-R1_CodeVerifier.md` §0、§6.2、§7.1、§7.3、§7.4、§17、§19、§20、§21.1、§21.3
- 审查方式：逐项对照计划与规格阅读代码和测试；独立运行 lint、全量测试、CLI 与 Dataset 验证；在 `/tmp` 中构造一次性篡改样本验证未覆盖边界。
- 审查边界：未修改 `src/`、`tests/` 或 `third_party/open-r1/`；仅新增本报告。

当前仓库相对根提交 `a0e0853f42dd17a4edce7ba765cc82904c26c02d` 的项目文件均处于未跟踪状态，无法通过 Git diff 独立还原 WP1 的精确增量，也无法核实“测试预期未被调整以迁就实现”。该项在本报告中标记为审查限制，不默认视为通过。

## 2. 交付核验

| 计划交付 | 状态 | 证据与说明 |
|---|---|---|
| canonical schema | 部分通过 | `src/code_verifier/data/schema.py:17-53` 提供冻结 dataclass，`178-258` 提供严格解析、序列化和局部语义校验；但 JSON 容器仍可通过对象本身直接修改，未达到计划要求的深层不可变语义。 |
| 输入适配器 | 通过 | `src/code_verifier/data/adapters.py:72-142` 严格校验 raw JSONL、字段集合、重复 JSON key、行号和空文件。相关单元测试通过。 |
| test split | 通过 | `src/code_verifier/data/split_tests.py:24-85` 使用 `seed + problem_id` 派生局部 PRNG，校验层大小、测试总数和重复测试；当前 fixture 三层并集与互斥性通过。 |
| hash | 部分通过 | `src/code_verifier/data/deduplicate.py:17-72` 提供确定性标准化、canonical JSON 和 SHA-256；但跨 split 题目 hash 将题面、测试和参考实现组合为单个整体，导致相同题面只要测试或答案不同就不会被识别。 |
| 去重 | 部分通过 | 重复 ID、完全相同复合内容和测试重复可被拒绝；题面/签名级近似重复不能可靠拒绝，不满足规格 §7.4(10) 和数据 Review 的题面近似重复检查。 |
| leakage checks | 未完全通过 | 字段白名单与顶层/递归 key 检查已实现，但 `check-data` 不将训练文件内容与 canonical train 记录逐条绑定，eval-hidden 内容可改名后进入训练 artifact 并通过检查。 |
| 20 道题 fixture | 通过（结构层面） | `tests/fixtures/wp1/raw_problems.jsonl` 恰好 20 行、20 个唯一 ID，12/4/4 split，每题 6 个测试；独立 pipeline 成功导出。WP1 按计划不执行参考实现，因此测试标签正确性只进行了人工抽查，未由可信执行器自动验证。 |

## 3. 核心验收核验

| 验收项（规格 §20 / 计划 §6.4） | 状态 | 证据 |
|---|---|---|
| fixture 可导出 JSONL 和 Hugging Face Dataset | 通过，但存在已记录的接口偏离 | 独立 `prepare-data` 返回 0，导出 20 行、12/4/4；`load_from_disk()` 返回 20 行。`src/code_verifier/data/prepare.py:183-238` 将测试值编码为 `input_json` / `expected_json`，不是计划要求的原始 §7.1 测试对象，但 `check-data` 能可逆解码并与 canonical 对比。 |
| 三层测试无重复 | 通过（当前 fixture 与实现覆盖范围） | `check_no_test_layer_overlap()` 使用标准化测试 hash；全量测试和 fresh pipeline 通过，每题三层各 2 项且共 6 个唯一测试。 |
| 删除或混入字段时测试能失败 | 部分通过 | 删除必填字段和直接增加禁用字段会失败；但将 eval-hidden 内容放入允许的 `visible_tests` 字段后仍通过，说明只检查字段名，未检查内容来源。 |
| 训练 artifact 不含 eval hidden 测试 | 未通过为通用保证 | fresh 输出的三个训练文件当前均为 12 行，原始文本无 `eval_hidden_tests` 字段；但针对性篡改证明 `check-data` 无法识别被改名或替换后的 eval-hidden 内容，不能建立规格要求的自动隔离保证。 |

## 4. 问题清单

### 4.1 主要问题

#### M1：训练 artifact 校验未与 canonical 数据绑定，可接受被改名的 eval-hidden 内容

- 位置：
  - `src/code_verifier/data/leakage_checks.py:156-205`
  - `src/code_verifier/data/prepare.py:311-325`
  - `tests/unit/data/test_prepare.py:165-188`
  - `tests/integration/test_wp1_data_pipeline.py:128-148`
- 问题：`check_training_record()` 只核对字段集合、递归 `eval_hidden_tests` key、SFT 非空值和 JSON 可序列化性；`check_prepared_data()` 只核对每种训练文件的行数。它没有验证：
  - 每行 `problem_id` 是否恰好来自 canonical 的 train split；
  - prompt、metadata、函数签名是否与 canonical 对应题一致；
  - `visible_tests` 是否确实来自 canonical visible 层；
  - `train_hidden_tests` 是否确实来自 canonical train-hidden 层；
  - 是否存在重复、遗漏或替换的训练题。
- 独立复现：将 fresh 输出中第一条 `public_grpo.visible_tests` 替换为同题 canonical 的 `eval_hidden_tests`，字段名仍保持 `visible_tests`。随后运行 `check-data`，退出码为 0，并输出 `checked 20 problems`。
- 影响：eval-hidden 内容能够在不出现禁用字段名的情况下进入 Public/Hidden 训练文件，直接破坏规格 §7.4(2)(4)(5)(9) 和 WP1 核心验收。
- 建议：在 `check_prepared_data()` 中从 canonical train problems 使用 `build_training_record()` 重新构造每种期望记录，并对磁盘记录进行确定性逐条或按 `problem_id` 的完整结构比较；同时拒绝重复 ID、缺失 ID、额外 ID、非 train ID 和顺序/内容异常。新增至少以下负向测试：eval 内容改名为 visible、validation/test 题替换 train 题、重复一行并删除另一行、修改 prompt、修改允许层中的测试内容。

#### M2：跨 split 去重只检测“整个复合记录相同”，不能识别相同题面污染

- 位置：
  - `src/code_verifier/data/deduplicate.py:54-72`
  - `src/code_verifier/data/deduplicate.py:98-109`
  - `tests/unit/data/test_deduplicate.py:85-99`
- 问题：`problem_content_hash()` 将规范化题面、函数名、函数签名、starter、reference solution 和全部测试 hash 合并为一个 hash。任一组成部分变化都会改变最终 hash。因此，相同题面和函数签名跨 split 出现时，只要测试或参考实现略有不同，就不会被判定为重复。
- 独立复现：构造 train 与 validation 两题，保持相同规范化 prompt 和函数签名，但使用不同测试与等价写法的 reference solution；`check_dataset()` 正常返回并打印 `accepted_same_prompt_across_splits`。
- 影响：不能可靠落实规格 §7.4(10) 的 prompt、参考代码、测试近似去重，也不能满足 §21.3 的题面近似重复审查要求。真实数据中同一道题通常会因测试集或答案格式不同而逃过当前检查。
- 建议：为不同污染信号建立独立索引，而不是只使用一个全量复合 hash。至少分别检查：规范化 `prompt + function_signature`、规范化 reference solution、单个测试 hash/测试集合 hash；错误中列出冲突 problem IDs、split 和冲突类型。新增“相同题面但测试不同”“相同参考实现但题面轻微改写”“跨 split 测试子集重合”等测试。

#### M3：冻结 dataclass 内的 JSON 容器仍可变，校验与 hash 可在构造后失效

- 位置：
  - `src/code_verifier/data/schema.py:9-22`
  - `src/code_verifier/data/schema.py:104-123`
  - `tests/unit/data/test_schema.py:89-112`
- 问题：`validate_json_value()` 会深拷贝输入 list/dict，避免外部别名修改，但返回值本身仍是可变 list/dict。`@dataclass(frozen=True)` 只禁止字段重新赋值，不能禁止 `problem.visible_tests[0].input.append(...)` 或修改嵌套 dict。
- 独立复现：解析合法问题后执行 `p.visible_tests[0].input.append(99)`，操作成功，结果为 `[1, 2, 99]`。
- 影响：对象在通过 schema、泄漏检查或 hash 后仍可被原地修改，导致已验证状态、去重结果和序列化结果不一致。该行为与计划 §3.3、步骤 2 和风险 6 中的不可变数据语义要求冲突。
- 建议：采用递归不可变内部表示，例如 JSON array 转 tuple、object 转只读映射/不可变键值 tuple，并在序列化边界恢复 JSON list/object；或使用专门的 frozen JSON value 类型。测试必须直接尝试修改嵌套 list/dict，而不只测试字段赋值和输入别名复制。

### 4.2 次要问题

#### m1：HF Dataset 的公开字段结构偏离计划中的 canonical §7.1 结构

- 位置：`src/code_verifier/data/prepare.py:183-238`
- 问题：HF Dataset 中测试项使用 `input_json` 和 `expected_json` 字符串，而 canonical JSONL 使用 `input` 和 `expected` JSON 值。该偏离已在 `proceedings.md` 和 `README.md:77-86` 记录，且内部回读可逆，因此不构成当前数据丢失；但它使 HF Dataset 不能被按 §7.1 schema 直接消费，并依赖私有解码函数。
- 建议：将该表示定义为显式、版本化的 Dataset schema，并提供公开加载/解码 API；或者调整实现以输出与 canonical 字段一致的可消费 Dataset。若保留当前方案，应正式更新计划/接口文档，而不只作为实施偏离记录。

#### m2：仓库缺少可审查的跟踪基线

- 位置：Git 工作区整体状态
- 问题：当前项目文件均为未跟踪状态，无法用 Git diff 区分 WP0、WP1、计划外变更和测试预期调整。
- 影响：不影响本次运行结果，但削弱后续 review、回滚和实验可追溯性；“未修改测试预期以迁就实现”无法独立核实。
- 建议：在修复主要问题并再次验收后，按清晰提交边界纳入版本控制；至少将 WP0 基线与 WP1 增量分离。

### 4.3 建议项

- `src/code_verifier/cli.py:56-60` 的 `--output-dir` help 文本在 `prepare-data --help` 中也显示“check-data accepts it...”，语义不准确。建议按子命令提供独立 help 文本。
- 当前 fixture 的来源和许可证字段已记录为自建 fixture / MIT，但参考实现与 expected 未执行验证。进入真实训练数据阶段前，应在安全执行器可用后增加标签正确性检查；此项属于 WP3 以后能力，不阻断 WP1 结构测试。

## 5. 独立测试结果

### 5.1 静态检查与全量测试

- 命令：`make lint`
  - 退出码：0
  - Ruff check：`All checks passed!`
  - Ruff format check：`25 files already formatted`
  - Mypy：`Success: no issues found in 25 source files`
- 命令：`make test`
  - 退出码：0
  - 结果：`108 passed in 1.93s`

### 5.2 依赖与 CLI 验收

- 依赖版本：`datasets=3.2.0`，`pyyaml=6.0.2`。
- fresh `prepare-data`：退出码 0；20 problems，split 为 train=12、validation=4、test=4。
- fresh `check-data`：退出码 0；20 problems，split 为 12/4/4。
- HF Dataset：`load_from_disk()` 行数为 20。
- `prepare-data --help`：退出码 0，包含公共参数。
- `check-data --help`：退出码 0，包含公共参数。
- fresh training artifacts：
  - `sft.jsonl`：12 行；字段为 `metadata,problem_id,prompt,sft_response`；无 `eval_hidden_tests` 文本。
  - `public_grpo.jsonl`：12 行；字段包含 visible，不含 train/eval hidden 字段；无 `eval_hidden_tests` 文本。
  - `hidden_grpo.jsonl`：12 行；字段包含 visible/train hidden，不含 eval hidden 字段；无 `eval_hidden_tests` 文本。

### 5.3 上游边界

- `third_party/open-r1`：无 changed files、无 diff。
- 固定 commit：`1416fa0cf21595d2083b399a2a0bbddd7f6e9563`。

### 5.4 针对性负向检查

| 检查 | 预期 | 实际 | 结论 |
|---|---|---|---|
| 将 canonical eval-hidden 测试内容替换进 `public_grpo.visible_tests` 后运行 `check-data` | 返回 2 | 返回 0 | 失败，证明 M1 |
| 相同 prompt/signature 跨 split，但测试和参考实现不同 | 拒绝污染 | 接受 | 失败，证明 M2 |
| 构造后直接修改 `TestCase.input` 内部 list | 应不可变 | 修改成功 | 失败，证明 M3 |

## 6. executor 报告声明核验

| `proceedings.md` 声明 | 核验状态 | 说明 |
|---|---|---|
| WP1 文件和主要符号均已实现 | 核实通过 | 计划列出的模块、CLI 和测试文件存在。 |
| `make lint` 通过 | 核实通过 | 本审查方独立运行，退出码 0。 |
| `make test` 为 108 passed | 核实通过 | 本审查方独立运行，108 passed。 |
| prepare/check CLI、20 行、12/4/4、HF 20 行 | 核实通过 | 本审查方使用 fresh 临时目录独立运行。 |
| 三种训练文件各 12 行且当前输出不含 eval-hidden 字段 | 核实通过 | fresh 输出直接核对。 |
| 训练 artifact 隔离检查已完整实现 | 与事实不符 | 只验证字段名和行数；eval 内容改名后可通过。 |
| 跨 split 内容去重已完整实现 | 与事实不符 | 只拒绝完整复合 hash 相同，不能拒绝相同题面但测试/答案不同。 |
| canonical schema 具有不可变数据语义 | 与事实不符 | 嵌套 JSON list/dict 可直接修改。 |
| WP1 的 4 项验收均满足 | 与事实不符 | 至少训练 artifact 隔离的通用保证未满足，删除/混入字段验收只部分满足。 |
| 未修改 `third_party/open-r1`，commit 未变 | 核实通过 | 无 diff，commit 匹配。 |
| 未修改测试预期以迁就实现 | 无法核实 | 项目文件均未跟踪，缺少可比较基线。 |

## 7. 结论

- 审查结论：**需修改，当前不能判定 WP1 验收通过。**
- 完成度判断：WP1 的模块、happy-path pipeline、CLI、20 题 fixture、确定性划分和基础字段白名单已经落地，独立 lint、108 项测试和 fresh 导出均通过；但核心泄漏防护仍存在 3 个主要缺陷，其中 M1 可直接让 eval-hidden 内容进入训练 artifact 后通过 `check-data`，属于 WP1 验收级问题。
- 建议 Gate：修复 M1、M2、M3，补充对应负向测试，重新运行 `make lint`、`make test`、fresh prepare/check 和三项针对性篡改检查后，再将 `proceedings.md` 的 WP1 状态恢复为“已完成/通过”。
