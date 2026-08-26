# EchoMind Judge v5 确定性计分与 Pass 规则设计

日期：2026-08-26
状态：设计稿已形成，等待规格审查
适用分支：`task6-dialog-eval`

## 1. 背景与冻结证据

`dialog-eval-v4` 已完成 35 cases / 43 turns 的端到端运行，结构性结果为 35 个有效案例、0 Agent 失败、0 Judge 失败，且 Agent P95 为 16,890.7 ms。但该结果不能发布：人工语义审查发现 Judge 的 reasoning、分数字段与既有 cap 规则不一致，当前仅按 case `overall >= 0.75` 判断通过也会掩盖单维度严重缺陷。

本设计以以下 v4 产物为不可变诊断证据：

- 数据集：`EchoMind_data/data/eval/dialog_eval_v2.json`
- 数据集 SHA-256：`cb895c1fc4d95a4c1a9b821d9c56beb7755abd614aa5ef1eada1125c12ee51b2`
- v4 predictions SHA-256：`59e552459c2666f22b192afdf54a9ef09a7ecc521c3243a39e18bb3c3d9dbb3f`
- v4 metrics SHA-256：`a9d98c5593fc0978a236b98ba075299662394fc0e7045472a0da49ac10cb7be8`
- v4 metadata SHA-256：`0184c64ebe47bc6040c4a6ec3942f32ca80558a81e8b6c4293f306779b7b81eb`
- v4 Prompt：`dialog_judge_v4`
- v4 输出策略：`forced_tool_then_strict_json_fallback`

已确认的代表性问题包括：

1. `dialog_eval_018` 的 reasoning 明确得出 helpfulness 应为 `0.50`，落盘值却是 `0.85`；
2. `dialog_eval_019` 的 reasoning 命中敏感材料规则并得出 helpfulness 应为 `0.50`，落盘值却是 `0.75`；
3. `dialog_eval_031` 的 reasoning 明确承认更严格的 `0.75` cap，落盘值仍是 `0.85`；
4. `dialog_eval_026` 和 `dialog_eval_028` 存在未被稳定识别的越权操作、额外材料要求或多轮状态不一致；
5. `dialog_eval_024`、`dialog_eval_025` 等案例的 completeness 被连续小数主观评分掩盖了明确的必需点缺失；
6. `dialog_eval_025`、`dialog_eval_033` 的 accuracy/helpfulness 均为 `0.50`，但旧规则仍因平均 `overall == 0.75` 判为通过。

因此，v4 只保留为“结构运行成功、人工语义审查失败”的历史证据，不得手工改写、覆盖或作为最终指标发布。

## 2. 目标

Judge v5 必须实现以下目标：

1. 将“语义事实判定”与“最终计分”分离；
2. Judge 只输出结构化语义评估、required point 覆盖标签和违规事实，不输出最终 completeness、overall、cap 后分数或 pass；
3. Python 成为最终分数、cap、overall、turn pass 和 case pass 的唯一计算者；
4. completeness 只由 Python 根据 `covered / partial / missing` 确定性计算；
5. 多个违规同时出现时，对每个维度取最严格、也就是数值最小的 cap；
6. 多轮 case 的维度均值只用于报告，`case_pass = all(turn_pass)`；
7. 保留 v4 已验证的 tool-call 与 strict-JSON fallback 传输策略；
8. 先用冻结的 10 个问题案例、14 个 turn 校准，再允许正式 35-case 重跑；
9. 将路由 gold label 争议与 Judge v5 评分改造隔离，禁止在同一变更中静默修改数据标签。

## 3. 非目标

本设计不包含以下工作：

- 不修改 Agent Prompt、路由算法或业务回答以追求更高分；
- 不覆盖、删除或修改 `dialog-eval-v1`、`dialog-eval-v2`、`dialog-eval-v4` 及历史 Smoke、诊断和校准目录；
- 不手工修正 v4 的 predictions 或 metrics；
- 不根据正式重跑结果反向放宽 cap、coverage 或 pass 阈值；
- 不把 LLM reasoning 解析成最终分数，也不通过关键词后处理猜测违规；
- 不把 Judge v5 与路由 gold label 校正放入同一个提交；
- 不在校准和人工审查通过前更新 baseline、主计划最终指标或简历表述；
- 不在本规格审查前直接修改生产代码或发起新的 Judge/Agent API 调用。

## 4. 架构与职责边界

### 4.1 Judge 的唯一职责

Judge 负责不可由简单规则完成的语义判断：

- 给出未应用 cap 的 `relevance`、`accuracy`、`helpfulness` 基础评估；
- 对每一个 required point 标注 `covered`、`partial` 或 `missing`；
- 从冻结枚举中选择适用的违规代码，并提供对应证据；
- 给出简短的语义判断摘要。

这里的基础评估属于结构化语义输入，不是最终评分。Judge 无权输出或决定：

- 最终 `completeness`；
- 最终 `relevance / accuracy / helpfulness`；
- `overall`；
- 任意 cap 数值；
- `turn_pass`、`case_pass` 或 `pass_rate`。

### 4.2 Python 的唯一职责

Python 负责：

- 严格校验 Judge payload；
- 将 coverage 状态映射为 completeness；
- 根据违规代码查询冻结 cap 表；
- 多违规时逐维度取最严格 cap；
- 计算最终四维分数和 overall；
- 按冻结 pass 规则计算 turn/case pass；
- 聚合报告均值和 pass rate；
- 将原始语义评估与确定性派生结果分层持久化。

任何最终分数都不得由 reasoning 文本提取、被 Judge 直接提供或在持久化后手工改写。

## 5. Judge v5 输出契约

### 5.1 顶层 Schema

Judge 的 tool payload 和 strict-JSON fallback 必须使用同一份精确 Schema：

```json
{
  "base_scores": {
    "relevance": 1.0,
    "accuracy": 1.0,
    "helpfulness": 1.0
  },
  "required_point_coverage": [
    {
      "point_index": 1,
      "status": "covered",
      "evidence": "简短说明该必需点如何被覆盖或缺失"
    }
  ],
  "violations": [
    {
      "code": "unsupported_operation",
      "evidence": ["具体、简短的触发证据"]
    }
  ],
  "reasoning_summary": "简短总结语义判断，不包含最终分数或 cap 计算"
}
```

顶层字段必须恰好为：

- `base_scores`
- `required_point_coverage`
- `violations`
- `reasoning_summary`

禁止出现 `completeness`、`overall`、`final_scores`、`passed`、`turn_pass`、`case_pass` 或任何额外字段。

### 5.2 基础评估

`base_scores` 必须恰好包含 `relevance`、`accuracy`、`helpfulness`。每个值必须是 `[0, 1]` 内的有限 `int` 或 `float`，不得为 `bool`、NaN 或无穷值。

基础评估不得预先应用违规 cap。Python 应用 cap 时只能保持或降低基础分，不能提高 Judge 给出的基础分。

### 5.3 Required point 覆盖

每条 coverage 记录必须恰好包含：

- `point_index`：从 `1` 开始，与输入 `required_points` 顺序对应；
- `status`：只能是 `covered`、`partial`、`missing`；
- `evidence`：非空、去除首尾空白后的简短字符串。

Python 必须验证：

- coverage 数量与 required point 数量完全一致；
- 每个 `point_index` 恰好出现一次；
- 索引集合恰好为 `1..N`，不得遗漏、重复、越界或增加；
- 输入 required points 为空时视为数据/调用错误，不得默认 completeness 为 `1.0`。

状态定义：

- `covered`：回答明确表达了该 required point 的全部实质信息；
- `partial`：只覆盖其中一部分，或表达不足以确认整个 required point；
- `missing`：没有提供该 required point 的实质信息，或用不受支持的替代流程取代该点。

### 5.4 违规记录

每条 violation 必须恰好包含 `code` 和 `evidence`。同一个 code 最多出现一次；同类违规的多个证据应合并在其非空 evidence 数组中。无违规时使用空数组。

Judge 不输出 cap。Python 只根据 code 查询冻结表。

### 5.5 Reasoning 摘要

`reasoning_summary` 必须是非空字符串，只解释语义标签与违规事实，不得声称最终分数、cap 后分数、overall 或 pass。最终结果与摘要发生冲突时，以经过 Schema 校验的结构字段和 Python 派生结果为准；校准阶段仍须将这种冲突作为人工审查失败，而不能忽略。

## 6. 冻结违规枚举与 Cap 表

| Code | 触发条件 | Accuracy cap | Helpfulness cap |
|---|---|---:|---:|
| `unsupported_operation` | 无受控依据地声称助手可以、将要执行提交、登记、联系、转接、升级、退款等操作 | 0.75 | 0.75 |
| `false_completed_action` | 无受控依据地声称操作已发起、正在执行、已登记、已提交、已转接或已完成 | 0.50 | 0.50 |
| `unsupported_process_or_requirement` | 增加受控上下文没有给出的流程、原因、时限或材料要求 | 0.75 | 无 |
| `misleading_unsupported_content` | 不受支持的内容可能改变用户决策、造成额外负担或误导实际流程 | 无 | 0.85 |
| `sensitive_request_without_safety` | 未获上下文授权或无必要安全提醒地索取潜在敏感材料 | 0.75 | 0.50 |
| `context_contradiction` | 与受控上下文、参考事实或必要的多轮状态直接冲突 | 0.50 | 无 |
| `core_fact_reversed` | 反转问题的核心事实 | 0.25 | 无 |
| `severe_readability_defect` | 严重冗长、乱码或破损格式实质影响可读性 | 无 | 0.75 |

普通礼貌表达、自然过渡、无害建议或不声称执行能力的下一步建议不构成违规。

若同一维度命中多个 cap，Python 必须取最小值。例如 helpfulness 同时命中 `unsupported_operation` 的 `0.75` 和 `sensitive_request_without_safety` 的 `0.50`，最终 helpfulness cap 必须为 `0.50`。数组顺序不得影响结果。

## 7. 确定性计分算法

### 7.1 Completeness

Python 使用固定映射：

```text
covered = 1.0
partial = 0.5
missing = 0.0
```

`completeness` 是所有 required point 映射值的等权算术平均。计算使用未四舍五入的浮点值；展示层可以格式化，但 pass 与指标聚合必须使用原始计算值。

Judge 不得输出最终 completeness，也不得通过 reasoning 建议 completeness 数值。

### 7.2 Cap 合并

每个受 cap 维度初始上限为 `1.0`。遍历所有 violation code，对该维度执行 `cap = min(cap, rule_cap)`。违规数组顺序、evidence 数量和 reasoning 文本不得影响 cap。

### 7.3 最终四维分数

```text
final_relevance    = base_relevance
final_accuracy     = min(base_accuracy, strictest_accuracy_cap)
final_completeness = mean(coverage_status_values)
final_helpfulness  = min(base_helpfulness, strictest_helpfulness_cap)
final_overall      = mean(final_relevance, final_accuracy,
                          final_completeness, final_helpfulness)
```

Python 是上述 `final_*` 字段的唯一生产者。计算函数必须是无网络、无环境变量、无时间依赖、无随机性的纯函数。

## 8. Pass 规则

冻结版本：`PASS_RULE_VERSION = "dialog_pass_v5"`。

冻结阈值：

- `DIMENSION_PASS_FLOOR = 0.75`
- `OVERALL_PASS_THRESHOLD = 0.75`

一个 turn 只有同时满足以下条件才通过：

1. `agent_failed == false`；
2. `judge_failed == false`；
3. `judge_skipped == false`；
4. 四个最终维度均 `>= 0.75`；
5. 最终 overall `>= 0.75`。

Agent/Judge 失败或 Judge 被跳过时，`turn_pass = false`，不得用空分数或默认分数替代。

对任意非空 case：

```text
case_pass = all(turn_pass for every turn in the case)
```

case 的四维平均分和 overall 平均分仅用于报告，不参与 `case_pass`。即使多轮平均分高于阈值，只要任一 turn 不通过，case 仍必须失败。

`pass_rate` 继续定义为“完全有效 Judge case 中 `case_pass == true` 的比例”；Agent/Judge 失败率继续独立报告。失败 case 的 `case_pass` 为 false，但不得进入质量均值或有效 Judge pass-rate 分母。

## 9. 持久化与指标契约

每个成功 Judge turn 必须分层保存：

```json
{
  "judge": {
    "assessment": {
      "base_scores": {},
      "required_point_coverage": [],
      "violations": [],
      "reasoning_summary": "..."
    },
    "applied_caps": {
      "accuracy": 0.5,
      "helpfulness": 0.5
    },
    "final_scores": {
      "relevance": 1.0,
      "accuracy": 0.5,
      "completeness": 1.0,
      "helpfulness": 0.5,
      "overall": 0.75
    },
    "latency_ms": 1000.0
  },
  "turn_pass": false
}
```

约束：

- `assessment` 保存经过严格验证的原始语义结构；
- `applied_caps` 只保存实际生效、低于 `1.0` 的维度 cap；
- `final_scores` 只由 Python 生成；
- 指标聚合只读取 `final_scores`；
- `case_scores` 是各 turn `final_scores` 的报告均值；
- 顶层 `passed` 可作为 `case_pass` 的向后兼容别名，但二者必须严格相等；
- 不允许继续把 Judge 原始分和最终分混放在同一层。

`run_metadata.json` 至少新增或更新：

- `prompt_version = "dialog_judge_v5"`
- `judge_output_strategy = "forced_tool_then_strict_json_fallback"`
- `pass_rule_version = "dialog_pass_v5"`
- `dimension_pass_floor = 0.75`
- `overall_pass_threshold = 0.75`
- `completeness_policy = "required_point_coverage_equal_weight_v1"`
- `violation_policy_version = "dialog_violation_caps_v1"`

历史 `pass_threshold` 字段不得继续作为唯一 pass 规则来源；若为兼容保留，必须与 `overall_pass_threshold` 相等且不能绕过单维度门槛。

## 10. v4 传输策略的继承

Judge v5 继续保留：

- attempt 1—2：强制调用唯一命名 tool；
- 仅当前两次均返回精确空 tool input `{}` 时，attempt 3 才切换严格纯 JSON；
- strict-JSON 与 tool 使用完全相同的 v5 Schema；
- 非空但无效 payload 不触发 JSON fallback；
- 最多 3 次总尝试；
- `temperature = 0.0`、thinking disabled、独立 Judge client、受控上下文边界和密钥脱敏保持不变。

Prompt 版本升级为 `dialog_judge_v5`。输出策略名称保持不变，因为传输协议未改变；Schema 与确定性策略通过 Prompt、pass rule、completeness policy 和 violation policy 版本共同识别。

## 11. 10-case / 14-turn 校准矩阵

校准必须复用 v4 冻结 Agent 回答，Agent API 调用数必须为 `0`。案例顺序固定为：

`001, 018, 019, 024, 025, 026, 028, 031, 033, 034`。

校准共 10 cases / 14 turns。每一行的 coverage 状态必须精确匹配；required violations 必须全部出现。若出现额外违规、最终 pass 与预期不一致或 reasoning 与结构字段冲突，保留证据并停止，由人工审查决定是否需要修正规格或 Prompt，不得私自放宽 oracle。

| Case/Turn | 预期 coverage | Required violations | 确定性结果要求 | 预期 turn pass |
|---|---|---|---|---|
| `001/T1` | `[partial]` | `[]` | completeness = 0.50 | false |
| `018/T1` | `[covered, covered, covered]` | `unsupported_operation`, `unsupported_process_or_requirement`, `misleading_unsupported_content`, `sensitive_request_without_safety` | helpfulness <= 0.50 | false |
| `019/T1` | `[covered, covered, covered]` | `unsupported_operation`, `unsupported_process_or_requirement`, `misleading_unsupported_content`, `sensitive_request_without_safety` | helpfulness <= 0.50 | false |
| `024/T1` | `[covered, covered, missing]` | `unsupported_operation`, `unsupported_process_or_requirement`, `misleading_unsupported_content` | completeness = 2/3 | false |
| `025/T1` | `[partial, covered, covered]` | `false_completed_action` | accuracy/helpfulness <= 0.50 | false |
| `026/T1` | `[covered, covered]` | `unsupported_operation` | accuracy/helpfulness <= 0.75 | true |
| `026/T2` | `[covered, covered]` | `false_completed_action` | accuracy/helpfulness <= 0.50 | false |
| `026/T3` | `[covered, covered]` | `unsupported_operation` | accuracy/helpfulness <= 0.75 | true |
| `028/T1` | `[covered, covered]` | `[]` | 四维不得被 cap | true |
| `028/T2` | `[partial, covered]` | `unsupported_operation`, `unsupported_process_or_requirement`, `misleading_unsupported_content` | completeness = 0.75；accuracy/helpfulness <= 0.75 | true |
| `028/T3` | `[covered, covered]` | `unsupported_process_or_requirement`, `misleading_unsupported_content` | accuracy <= 0.75；helpfulness <= 0.85 | true |
| `031/T1` | `[covered, covered, covered, covered]` | `unsupported_operation`, `unsupported_process_or_requirement`, `sensitive_request_without_safety` | helpfulness <= 0.50 | false |
| `033/T1` | `[covered, covered, covered]` | `false_completed_action`, `unsupported_process_or_requirement`, `misleading_unsupported_content` | accuracy/helpfulness <= 0.50 | false |
| `034/T1` | `[covered, partial, covered]` | `unsupported_operation` | completeness = 5/6；accuracy/helpfulness <= 0.75 | true |

基于逐 turn 规则，预期 case pass：

- false：`001, 018, 019, 024, 025, 026, 031, 033`
- true：`028, 034`

校准成功还必须满足：

- 14 个 turn 均获得合法 v5 payload；
- 每个 required point 的 index、状态和证据合法；
- cap 与 violation 顺序无关；
- Python 重算结果与落盘结果逐字段精确一致；
- 10 个 case 的 `case_pass` 与上述 oracle 一致；
- 10 个 case 的平均分不参与 case pass；
- Judge 失败数为 0，Agent 调用数为 0；
- 使用与正式运行一致的精确 Judge 模型；
- 校准命令只执行一次，写入全新、不覆盖的目录；
- 校准失败时保留产物并停止，不得在同一目录重跑或手工修分。

## 12. 路由 Gold Label 隔离

v4 路由审计显示 8 个 intent mismatch，并存在明确代码缺陷、标签过宽/过窄和数据内部描述冲突的混合情况。尤其 `dialog_eval_033`、`dialog_eval_034` 的 description 与 `expected_routing.agent_type` 存在冲突。

这些问题不属于 Judge 评分职责。必须以独立数据审查任务处理，并满足：

- 单独的设计/变更记录；
- 逐案例说明旧值、新值和 taxonomy 依据；
- 不根据本次 Agent 输出反向修改 gold；
- 新数据文件、新 SHA-256 和独立提交；
- Judge v5 实现与路由 gold 修改不得混在同一提交。

在路由 gold 冲突裁决完成前，可以完成 Judge v5 的离线实现与冻结回答校准，但不得发布最终 35-case 指标。

## 13. 测试策略

实现必须使用 TDD，至少覆盖：

1. v5 Schema 接受合法 payload；
2. 拒绝缺失/额外顶层字段；
3. 拒绝 Judge 输出 completeness、overall、cap、pass 或最终分；
4. 拒绝 coverage 数量错误、索引缺失/重复/越界、未知状态和空 evidence；
5. 拒绝未知/重复 violation code、空 evidence 和额外字段；
6. 拒绝 bool、NaN、Infinity 和越界基础分；
7. completeness 对 `covered/partial/missing` 精确映射并等权计算；
8. 空 required points 失败而不是默认满分；
9. 单违规正确应用 cap；
10. 多违规对同一维度取最严格 cap，且数组顺序不影响结果；
11. cap 只能降低、不能提高基础分；
12. overall 使用最终四维未舍入算术平均；
13. 某一维度低于 0.75 时，即使 overall 达标，turn 仍失败；
14. 多轮 case 任一 turn 失败时，即使 case 平均分达标，case 仍失败；
15. case 平均分只用于报告；
16. Agent/Judge 失败或 skipped turn 的 `turn_pass` 为 false，且不进入质量均值；
17. 指标只读取 `final_scores`，不能读取基础分；
18. metadata 完整记录五个策略/阈值字段；
19. tool-call 与 strict-JSON fallback 使用完全相同的 v5 Schema；
20. v4 fallback 的空 payload 条件、最多三次尝试、严格 JSON 和密钥脱敏不回归；
21. 现有完整测试套件全部通过。

## 14. 版本兼容与历史证据

- v1—v4 的历史产物保持原样；
- v5 使用全新的校准、预热和正式运行目录；
- v5 不能 resume、拼接或覆盖 v4 predictions；
- 任何 v4 到 v5 的字段兼容只允许在读取层显式处理，不得把 v4 原始分伪装成 v5 确定性分；
- v5 产物必须记录数据 SHA-256、Git revision、模型、Prompt、输出策略、pass rule、completeness policy 和 violation policy；
- v5 正式结果只能与 v4 作为不同策略版本并列比较，不能宣称是同口径的简单重跑。

## 15. 阶段顺序与强制停止点

后续工作按以下顺序进行：

1. 本 v5 设计规格审查；
2. 审查并冻结第 11 节 10-case 校准 oracle；
3. 编写详细实施计划，不直接改代码；
4. DeepSeek 按计划使用 TDD 实现 v5，并执行冻结回答 10-case 校准；
5. Codex 独立审查提交、完整测试和校准产物；
6. 单独裁决路由 gold label 冲突；
7. 校准与路由数据均获批准后，另行编写并审批正式 35-case 运行计划；
8. 使用新目录完成预热和正式运行；
9. 人工语义抽查通过后才更新主计划、baseline 和简历指标。

以下任一情况必须停止，不得进入下一阶段：

- 规格或 calibration oracle 未获批准；
- 测试未全绿；
- v5 Schema 仍允许 Judge 输出最终 completeness/overall/pass；
- Python 重算与落盘分数不一致；
- 10-case 校准任一结构、coverage、violation、pass 或安全断言失败；
- Agent 调用数不为 0；
- 校准目录已存在或历史目录发生变化；
- 路由 gold 冲突未裁决却试图发布正式指标；
- 正式运行中存在 Agent/Judge 失败、产物缺失、身份哈希错误或人工语义审查失败。

## 16. 最终验收标准

Judge v5 只有同时满足以下条件才可视为设计和实现完成：

1. Judge 只输出经批准的结构化语义契约；
2. completeness 只由 Python 根据 coverage 状态计算；
3. 多违规 cap 始终取最严格值；
4. Python 是最终四维、overall 和 pass 的唯一生产者；
5. `case_pass = all(turn_pass)`，多轮均值只用于报告；
6. 10-case / 14-turn 校准 oracle 全部通过；
7. 完整测试套件通过；
8. 历史证据、数据身份、密钥和运行目录边界保持完整；
9. 路由 gold 冲突经独立审查解决；
10. 全新 35-case 正式运行通过结构、语义、延迟和人工审查门禁。

在第 10 项完成并经人工批准前，`dialog-eval-v4` 的 `pass_rate = 1.0` 不得作为最终对外指标，Task 7 不得宣告完成。
