# EchoMind Task 7：Smoke Judge 校准设计

日期：2026-08-25  
状态：设计已确认，等待规格审核

## 1. 背景

Task 6 已实现受控上下文下的对话质量评测管线。Task 7 首次真实 Smoke 运行已在 `data/eval/runs/dialog-smoke-v1` 生成 5 个 case、7 个 turn 的完整产物，Agent 和 Judge 均无调用失败。

人工复核发现，`dialog_judge_v1` 对必答点覆盖较敏感，但没有充分惩罚以下问题：

- 回答加入受控上下文未提供的排查流程、原因或材料要求；
- Agent 声称已经登记、提交或执行实际操作；
- 回答要求用户提供潜在敏感材料，却没有上下文授权或安全边界；
- 严重冗长、乱码或破损 Markdown 降低可读性；
- Judge 在上述问题存在时仍给出全项 `1.0`。

此外，Smoke Case 004 的回答和实际路由均合理，但冻结数据将期望路由写为 `account -> billing`。经人工审核，正确标签应为 `logistics -> general`。

因此，Task 7 暂停正式 35-case，先校准 Judge、修正 Case 004 标签并完成第二轮真实 Smoke。

## 2. 目标

本次校准必须实现：

1. 将评分规则升级为 `dialog_judge_v2`，明确评分锚点和封顶规则；
2. 修正 Smoke Case 004 的期望路由为 `logistics -> general`；
3. 保持现有结果 Schema 和统计口径兼容；
4. 保留 `dialog-smoke-v1`，把新结果写入独立的 `dialog-smoke-v2`；
5. 通过离线测试、完整测试和真实 Smoke 验证 Judge 校准效果；
6. 在正式 35-case 前识别并处理异常 Agent 延迟。

## 3. 非目标

本次校准不做以下工作：

- 不修改生产 Agent 的 Prompt 或回答逻辑来改善评测分数；
- 不用关键词规则在代码中覆盖 Judge 分数；
- 不更换 Judge 模型或服务商；
- 不改变 `dialog_predictions.jsonl`、`dialog_metrics.json` 或 `run_metadata.json` 的结构；
- 不覆盖、删除或改写 `dialog-smoke-v1`；
- 不创建 `dialog_eval.json`，不运行正式 35-case；
- 不将受控上下文评测描述为真实 RAG retrieval 评测。

## 4. 方案选择

采用方案 A：Prompt 评分规则升级、数据标签校正和独立 v2 Smoke。

未采用的方案：

- **代码后处理强制封顶**：虽然执行稳定，但需要用脆弱的关键词或额外分类器识别语义缺陷，会重复 Judge 职责并可能误伤正常回答。
- **更换 Judge 模型**：可能降低同模型偏差，但不能解决当前 rubric 含糊的问题，并会增加配置、成本和实验变量。

## 5. 架构与变更范围

### 5.1 Judge

`evaluation/dialog_judge.py` 中的固定 system rubric 升级为 v2，并将 `PROMPT_VERSION` 更新为 `dialog_judge_v2`。

Judge 继续：

- 使用独立 client 和固定 system message；
- 将被评估内容作为有边界的不可信 JSON 数据；
- 使用强制结构化 tool 输出；
- 输出 `relevance`、`accuracy`、`completeness`、`helpfulness`、`overall` 和 `reasoning`；
- 使用 `[0, 1]` 有限数值；
- 在失败时遵循现有重试与失败审计语义。

本次不增加新的结果字段。评分规则通过 system rubric 执行，真实 Smoke 人工复核是语义规则是否生效的最终校准门。

### 5.2 Smoke 数据

外部数据文件 `EchoMind_data/data/eval/dialog_smoke.json` 中，Case 004 的期望路由改为：

```json
{
  "intent": "logistics",
  "agent_type": "general"
}
```

除该标签外，不修改 Case 004 的上下文、用户问题、参考答案或必答点，也不修改其他 Smoke case。

### 5.3 运行产物

- v1：`data/eval/runs/dialog-smoke-v1`，保持不可变；
- v2：`data/eval/runs/dialog-smoke-v2`，必须是新目录或空目录；
- v2 仍输出 `dialog_predictions.jsonl`、`dialog_metrics.json` 和 `run_metadata.json`；
- `run_metadata.json` 必须记录 `prompt_version = dialog_judge_v2` 和新的数据集 SHA-256。

## 6. 评分锚点与封顶规则

`1.0` 表示该维度不存在实质性缺陷。仅覆盖全部必答点不足以获得全项满分。

| 问题类型 | 强制评分规则 |
|---|---|
| 普通礼貌、自然衔接 | 不扣分 |
| 受控上下文未提供的流程、原因、时限或材料要求 | `accuracy <= 0.75`；若可能误导用户，`helpfulness <= 0.85` |
| 虚构已经执行操作，例如“已登记”“已提交”“已发起退款” | `accuracy <= 0.5` 且 `helpfulness <= 0.5` |
| 要求提供支付凭证等潜在敏感信息，但上下文没有授权或安全说明 | `accuracy <= 0.75` 且 `helpfulness <= 0.5` |
| 与受控上下文明显矛盾 | 一般矛盾 `accuracy <= 0.5`；核心事实相反 `accuracy <= 0.25` |
| 严重冗长、乱码或破损 Markdown，显著降低可读性 | `helpfulness <= 0.75` |
| 必答点遗漏 | 按遗漏程度降低 `completeness` |
| 必答点全部覆盖，但存在额外无依据内容 | `completeness` 可以保持高分，主要降低 `accuracy` 和 `helpfulness` |

补充要求：

- `overall` 必须反映主要缺陷，不能在 `accuracy` 或 `helpfulness` 被封顶时仍无理由给出满分；
- `reasoning` 必须指出遗漏的必答点、无依据的具体表述、虚构执行能力以及触发的封顶规则；
- 多条规则同时触发时，每个维度采用最严格的适用上限；
- 不因自然礼貌表达、合理转述或无害衔接机械扣分。

## 7. 数据流

校准后的执行顺序为：

1. 修正 Case 004 标签并运行 Smoke 数据校验；
2. 先增加能够证明 v2 合约尚未满足的失败测试；
3. 更新 Judge rubric 和 `PROMPT_VERSION`；
4. 运行 Judge、CLI、数据校验相关测试；
5. 运行完整测试集；
6. 使用真实 Agent 和真实 Judge 执行 5-case Smoke v2；
7. 校验三个产物、case 数量、失败统计、元数据和路由审计；
8. 逐条人工对比 v1/v2 的回答、分数和 reasoning；
9. 只有 v2 与延迟门均通过后，才进入正式 35-case。

## 8. 错误处理和历史证据

- 继续沿用 Task 6 的 Agent/Judge 失败隔离、重试、JSONL 持久化和 finalization 语义；
- v2 运行失败时保留已完整落盘的 case，不用 v1 结果补齐；
- 失败运行不得覆盖 v1 或已存在的 v2 目录；
- 如果 v2 Judge 仍未通过人工校准，修改 Prompt 版本并使用新的运行目录，不覆盖已有证据；
- API Key、Authorization header 和完整环境变量不得写入测试、日志或运行元数据。

## 9. 测试策略

实现采用 TDD，至少覆盖：

1. `PROMPT_VERSION` 等于 `dialog_judge_v2`；
2. system rubric 包含全部评分锚点和封顶规则；
3. system rubric 要求 reasoning 指出具体问题和适用规则；
4. 用户输入中的伪指令仍被视为不可信评估数据，不能覆盖 system rubric；
5. 离线运行元数据记录 `dialog_judge_v2`；
6. Case 004 校验后的期望路由为 `logistics -> general`；
7. 原有评分解析、失败语义、聚合、持久化和安全测试不回归；
8. 完整项目测试集通过；
9. 真实 v2 Smoke 的 5 个 case 全部生成有效结果。

离线测试只验证 Prompt 合约和程序行为，不能证明 LLM 一定遵守语义规则。真实 Smoke 和人工复核共同构成 Judge 校准验收。

## 10. v2 Smoke 验收标准

v2 必须同时满足：

- 5 个 case、7 个 turn 全部生成有效结果；
- `agent_failed_count = 0` 且 `judge_failed_count = 0`；
- Case 004 的 `routing_audit.intent_match` 和 `agent_match` 均为 `true`；
- Case 002 的额外排查流程和显著格式问题被识别，不再全项 `1.0`；
- Case 003 的支付凭证要求被识别，`accuracy <= 0.75` 且 `helpfulness <= 0.5`；
- Case 005 中任何“已登记”“已提交”等虚构执行能力被识别，对应 turn 的 `accuracy <= 0.5` 且 `helpfulness <= 0.5`；
- Judge reasoning 引用具体问题并说明适用规则；
- Case 001、004 不因礼貌表达或合理措辞受到机械扣分；
- `run_metadata.json` 的版本、数据集哈希、case 数量和模型信息完整且不含密钥。

若 Agent 的随机回答没有再次产生 Case 002、003 或 005 中的原缺陷，则不能用“未触发缺陷”证明 Judge 已校准。此时需使用固定回答的真实 Judge 校准用例验证相应封顶规则，且仍保留该次 Smoke 结果。

## 11. 延迟质量门

v1 中存在约 176 秒的 Agent 首次调用异常值。BGE 模型下载和首次运行发生在同一次命令中，但现有证据不足以断言它就是该 turn 延迟的原因。

v2 必须记录并比较每个 turn 的 Agent 延迟：

- 任一 `agent_latency_ms > 30000` 记为延迟异常；
- 延迟异常不改变 Judge 分数，也不把成功请求改记为 Agent 失败；
- 若出现延迟异常，先定位是模型 API、重试、路由/Agent 调用还是本地初始化造成；
- 原因未查明前，不运行正式 35-case；
- 若无 turn 超过 30 秒，则本轮延迟门通过，但仍保留 v1 异常值记录。

## 12. 正式评测放行条件

只有以下条件全部满足，才允许创建并校验 `dialog_eval.json`、运行 35-case：

1. 离线相关测试与完整测试集通过；
2. v2 三个运行产物完整且一致；
3. v2 Judge 人工校准通过；
4. Case 004 路由审计通过；
5. 延迟质量门通过或异常原因已明确并有可接受的处理结论；
6. 用户明确批准从 Smoke 阶段进入正式评测阶段。

在此之前，Task 7 保持进行中，不生成正式结论，也不把 5-case Smoke 分数用于简历指标。
