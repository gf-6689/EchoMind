# EchoMind Routing Gold Label 独立审查

日期：2026-08-26
性质：独立数据质量审查。只读分析 `dialog_eval_v2.json` 的 routing gold 与 v4 冻结预测的 mismatch；不根据模型预测反向修改 gold。
数据源（均只读）：`EchoMind_data/data/eval/dialog_eval_v2.json`（gold）、`data/eval/runs/dialog-eval-v4/dialog_predictions.jsonl`（v4 冻结预测，SHA-256 `59e55245…`）。

## Taxonomy 依据（冻结来源）

- Intent 定义与示例：`core/intent_recognizer.py` 的 `IntentCategory` 枚举与 `_EXAMPLES`（19 个 label）。
- Agent 路由表：`agents/agent_orchestrator.py` 的 `_INTENT_ROUTING`：

```text
technical / technical_login / technical_crash          -> technical
billing / refund / invoice / payment_issue /
account / account_security                            -> billing
escalation / human_handoff                            -> escalation
其余全部（query/complaint/request/greeting/feedback/
order_status/logistics/other）                        -> general
```

- 既有 v1→v2 标签校正先例：`docs/superpowers/specs/2026-08-25-echomind-dialog-eval-v2-correction-design.md` §7.1（6 项已批准的修正，其中 033、034 的 agent_type 已改为 escalation）。

## 审查结论总览

- routing mismatch 总数：**8**（v4 预测 vs v2 gold 的首轮 intent/agent 对比，其中 1 个同时含 agent mismatch）。
- 结论分布：**KEEP 6**、**AMBIGUOUS 2**、**CHANGE 0**。
- 额外审查 033/034 的 description 与 routing gold 的内部冲突：routing gold 本身已与 taxonomy 一致（v2 已修正），description 文本为 v2 修正时未同步的陈旧描述 → 记录在案，不属于 routing gold 字段，不在本任务修改范围内。
- **CHANGE = 0，不创建 `dialog_eval_v3.json`。**

## 逐案例审查表

### 1. dialog_eval_001

| 字段 | 内容 |
|---|---|
| user message | 你们人工客服几点下班？ |
| description | 咨询人工客服的在线时间与联系方式 |
| old intent gold | query |
| actual intent prediction | human_handoff |
| proposed intent gold | query（不变） |
| old agent_type gold | general |
| actual agent routing | escalation |
| proposed agent_type gold | general（不变） |
| taxonomy evidence | query = 查询信息；本消息是询问服务时间的纯事实咨询，与 query 定义一致。human_handoff 定义是"转人工"（要求转接），用户并未要求转接。路由表 query → general。 |
| conclusion | **KEEP** |

### 2. dialog_eval_015

| 字段 | 内容 |
|---|---|
| user message | 我明明关了自动续费，怎么还扣费？ |
| description | 关闭自动续费后仍被扣年费的说明与退款 |
| old intent gold | billing |
| actual intent prediction | payment_issue |
| proposed intent gold | 暂不改（billing 保留） |
| old agent_type gold | billing |
| actual agent routing | billing |
| proposed agent_type gold | billing（不变） |
| taxonomy evidence | 本消息是"扣款异常"陈述：payment_issue = 支付/扣款异常（示例"为什么重复扣款？""这个月多扣了钱"）语义贴合；但 billing 示例本身含"为什么扣了两次款？"，与本消息形式几乎一致，taxonomy 内部两个 label 对"意外扣费"场景示例重叠。两解均合理，且 gold billing 未与 taxonomy 明确冲突。agent 路由两 label 均 → billing，无差异。 |
| conclusion | **AMBIGUOUS**（存在合理双解，不强行改） |

### 3. dialog_eval_018

| 字段 | 内容 |
|---|---|
| user message | 下单页面一直报 500，怎么回事？ |
| description | 下单页面 500 错误的说明与重试建议 |
| old intent gold | technical |
| actual intent prediction | technical_crash |
| proposed intent gold | technical（不变） |
| old agent_type gold | technical |
| actual agent routing | technical |
| proposed agent_type gold | technical（不变） |
| taxonomy evidence | technical = 技术问题，其官方示例含"出现500错误"；gold 与 taxonomy 不冲突。technical_crash = 崩溃/错误码，示例也含"页面报500错误"——taxonomy 内部对 500 错误场景示例重叠（两 label 均 → technical agent，路由无差异）。按"只有 gold 与 taxonomy 明确冲突才 CHANGE"原则，technical 保留。 |
| conclusion | **KEEP**（另注：taxonomy 的 technical/technical_crash 示例重叠，属 taxonomy 质量问题，不在本次数据修改范围） |

### 4. dialog_eval_023

| 字段 | 内容 |
|---|---|
| user message | 我的快递 5 天没动了，你们管不管？ |
| description | 物流 5 天无更新的投诉与核查时效 |
| old intent gold | complaint |
| actual intent prediction | logistics |
| proposed intent gold | 暂不改（complaint 保留） |
| old agent_type gold | general |
| actual agent routing | general |
| proposed agent_type gold | general（不变） |
| taxonomy evidence | 内容主体是物流停滞：logistics = 物流配送，示例含"物流一直不更新"，字面贴合；但消息带明显不满语气（"你们管不管"），complaint = 投诉不满（示例"一直没人处理！"），且 case description 明确写"物流 5 天无更新的**投诉**与核查时效"支持 complaint。两解均有依据，agent 路由均 → general，无路由差异。 |
| conclusion | **AMBIGUOUS**（存在合理双解，不强行改） |

### 5. dialog_eval_025

| 字段 | 内容 |
|---|---|
| user message | 把 O-311 和 O-312 合并发货，约明天下午送。 |
| description | 两笔未发货订单合并发货并预约配送时间 |
| old intent gold | request |
| actual intent prediction | logistics |
| proposed intent gold | request（不变） |
| old agent_type gold | general |
| actual agent routing | general |
| proposed agent_type gold | general（不变） |
| taxonomy evidence | request = 请求操作，示例"帮我取消订单""我需要修改地址"是"请求执行操作"的句式，与本消息"把…合并发货，约…送"（要求执行合并+预约操作）结构一致；logistics 的官方示例均为物流信息查询（"快递什么时候到？"），不含操作请求句式。gold request 与 taxonomy 明确一致。 |
| conclusion | **KEEP** |

### 6. dialog_eval_027

| 字段 | 内容 |
|---|---|
| user message | O-405 还没发货，我要把地址改到杭州。 |
| description | 未发货订单改地址后追问发货时间 |
| old intent gold | request |
| actual intent prediction | logistics |
| proposed intent gold | request（不变） |
| old agent_type gold | general |
| actual agent routing | general |
| proposed agent_type gold | general（不变） |
| taxonomy evidence | "我要把地址改到杭州"与 request 的官方示例"我需要修改地址"几乎逐字对应；本消息核心诉求是请求执行改地址操作，而非查询物流状态。gold request 与 taxonomy 明确一致（v1→v2 校正先例已把本 case 定为 request）。 |
| conclusion | **KEEP** |

### 7. dialog_eval_030

| 字段 | 内容 |
|---|---|
| user message | 我用 500 积分换了帆布袋，现在能取消吗？ |
| description | 积分兑换取消、超时与发货时间的三轮咨询 |
| old intent gold | query |
| actual intent prediction | request |
| proposed intent gold | query（不变） |
| old agent_type gold | general |
| actual agent routing | general |
| proposed agent_type gold | general（不变） |
| taxonomy evidence | 本消息是询问"能否取消"的可行性问题（咨询式提问），与 description"三轮咨询"一致；query = 查询信息 可辩护。request 读取（把问句理解为取消诉求）虽有 CS 惯例依据，但按 v1→v2 校正先例"按当前轮实际内容分类"原则，首轮实际内容是咨询，gold query 与 taxonomy 不冲突，且 description 支持。agent 路由均 → general，无路由差异。 |
| conclusion | **KEEP** |

### 8. dialog_eval_032

| 字段 | 内容 |
|---|---|
| user message | 帮我看看那个单子现在什么情况。 |
| description | 无明确指代的模糊请求，期望主路由为 general 并先澄清 |
| old intent gold | other |
| actual intent prediction | order_status |
| proposed intent gold | other（不变） |
| old agent_type gold | general |
| actual agent routing | general |
| proposed agent_type gold | general（不变） |
| taxonomy evidence | "那个单子"没有任何订单指代（无订单号/无上下文锚点），意图无法可靠归类；other = 兜底分类，description 明确说明本 case 的设计意图是"模糊请求→general 澄清"。gold other/general 与 taxonomy 一致，且是数据集的刻意设计（complex_routing 类别），不以模型预测 order_status 反推。 |
| conclusion | **KEEP** |

### 9. dialog_eval_033（description 与 gold 内部冲突审查；routing 本身无 mismatch）

| 字段 | 内容 |
|---|---|
| user message | 别跟机器人说了，我要找真人客服。 |
| description | 用户明确要求人工客服，期望主路由为 general，升级状态由 escalated 字段另行审计 |
| old intent gold | human_handoff |
| actual intent prediction | human_handoff（match） |
| proposed intent gold | human_handoff（不变） |
| old agent_type gold | escalation |
| actual agent routing | escalation（match） |
| proposed agent_type gold | escalation（不变） |
| taxonomy evidence | "我要找真人客服"与 human_handoff 示例"我要找人工"一致；路由表 human_handoff → escalation；v1→v2 校正先例已明确"人工转接由 escalation Agent 承接"。gold 与 taxonomy 完全一致。description 中"期望主路由为 general"是 v2 校正后未同步的陈旧文本，与当前 gold 冲突——description 不是 routing gold 字段，属于独立的文档文本陈旧问题，记录在案但不在此次数据修改范围内。 |
| conclusion | **KEEP**（gold 正确；另注：description 陈旧文本待后续独立修订） |

### 10. dialog_eval_034（description 与 gold 内部冲突审查；routing 本身无 mismatch）

| 字段 | 内容 |
|---|---|
| user message | 退款等了 6 天还没到，我要你们主管处理。 |
| description | 退款超期后要求升级处理，期望主路由为 general，升级状态由 escalated 字段另行审计 |
| old intent gold | escalation |
| actual intent prediction | escalation（match） |
| proposed intent gold | escalation（不变） |
| old agent_type gold | escalation |
| actual agent routing | escalation（match） |
| proposed agent_type gold | escalation（不变） |
| taxonomy evidence | "我要你们主管处理"与 escalation 示例"找你们经理"一致；路由表 escalation → escalation；v1→v2 校正先例已明确"升级处理由 escalation Agent 承接"。gold 与 taxonomy 完全一致。description 中"期望主路由为 general"是 v2 校正后未同步的陈旧文本，与当前 gold 冲突——同上，记录在案，不属于 routing gold 修改范围。 |
| conclusion | **KEEP**（gold 正确；另注：description 陈旧文本待后续独立修订） |

## 结论与后续

1. 8 个 routing mismatch 全部不满足 CHANGE 四条件（无一出现"gold 与 taxonomy 明确冲突"）：KEEP 6、AMBIGUOUS 2（015、023）。
2. 033/034 的 description 陈旧文本与已修正 gold 冲突，属数据集描述字段的文档质量问题，需独立的小型数据修订任务处理（不在本任务范围，本任务只审查 routing gold 字段）。
3. 因 CHANGE = 0，不创建 `dialog_eval_v3.json`，不产生数据变更清单。
4. 待人工审核本审计结论后再决定是否另行启动：a) taxonomy 内部示例重叠（technical vs technical_crash、billing vs payment_issue、escalation vs human_handoff）的 taxonomy 修订；b) 033/034 description 文本同步。
