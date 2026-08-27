# EchoMind Judge v5 第一次校准失败 — 只读根因诊断

日期：2026-08-26
性质：只读诊断。不修改生产代码、测试、spec 或任何冻结产物；不调用 Judge/Agent API；不重跑校准。
诊断对象：`EchoMind_data/data/eval/runs/dialog-judge-calibration-v5-20260826/`（冻结失败产物）
对照材料：`dialog_eval_v2.json`（冻结数据集）、`dialog-eval-v4/dialog_predictions.jsonl`（冻结 Agent 回答）、v5 design spec、当前实现（`dialog_judge.py` / `dialog_policy.py` / `run_dialog_judge_calibration.py`）。

## 1. 执行摘要

第一次校准 `oracle_failed_turns = 9`、`manual_review_failed_turns = 1`、case_pass 预期 3 处不符（018/026/031）。本诊断对全部 9 个失败 turn 逐一比对冻结输入、v5 实际输出与冻结 oracle，结论：

- **0 个失败点归因于实现错误（D）**：`Python recompute mismatch = 0`、190 tests 全绿、Schema/Prompt/传参与冻结规则一致。
- **0 个失败点需要修改 oracle（B）**：全部 oracle 行在冻结定义的文字层面有充分文本依据（个别行如 018 的敏感材料、034 的 partial 属"依据存在但判定较紧"，仍可保留）。
- **9 个失败点 + 1 个 reasoning 冲突全部属于 Prompt/rubric 表达不足（A）**：冻结规则本身在 rubric 中均已出现，但关键语义边界（敏感材料示例、两种操作 code 的时态映射、多轮能力声明不因重复而获授权、复合 required point 的子事实规则、misleading 的升级判据、reasoning 禁提 cap 的字面范围）未操作化，导致 Judge 在这些边界上系统性漏判/误判。
- 次要发现：028/T2 存在输入数据歧义（C，次级）：用户输入中的税号为掩码占位符 `91330100MA2XXXXX1Q`，加剧了"确认税号"的判定分歧，但主因仍是 rubric 未规定复合 required point 的子事实规则。

证据强度佐证：通过的对照 turn（025/T1、026/T1、028/T3、001/T1）显示 Judge 在边界清晰时会正确应用规则——001/T1 用了子事实推理判 partial、026/T1 正确遵守了互斥规则并只标一个 code、028/T3 正确识别了 misleading。这说明失败不是能力缺失，而是规则边界未写清。

## 2. 根因矩阵（总览）

| Turn | Failure | 根因类别 | Oracle 是否保留 | 是否需改 Prompt | 是否需改 Spec | 是否需改代码 |
| --- | --- | --- | --- | --- | --- | --- |
| 018/T1 | 缺 `sensitive_request_without_safety` | A | 保留 | 是 | 否 | 否 |
| 019/T1 | 缺 `misleading_unsupported_content` | A | 保留 | 是 | 否 | 否 |
| 024/T1 | coverage P3 判 partial（应 missing）；缺 `misleading_unsupported_content` | A | 保留 | 是 | 否 | 否 |
| 026/T2 | 缺 `false_completed_action` | A | 保留 | 是 | 否 | 否 |
| 026/T3 | 缺 `unsupported_operation` | A | 保留 | 是 | 否 | 否 |
| 028/T2 | coverage P1 判 covered（应 partial）；缺全部 3 个 violations | A（次级 C） | 保留 | 是 | 否 | 否 |
| 031/T1 | 缺 `sensitive_request_without_safety` | A | 保留 | 是 | 否 | 否 |
| 031/T1 reasoning | "no penalty cap is pre-applied" 触发 conflict | A | 保留（标记行为正确） | 是 | 否 | 否（可选优化启发式，非必须） |
| 033/T1 | "正在为您转接" 误标 `unsupported_operation`（应 `false_completed_action`）；缺 `misleading_unsupported_content` | A | 保留 | 是 | 否 | 否 |
| 034/T1 | coverage P2 判 covered（应 partial） | A | 保留 | 是 | 否 | 否 |

## 3. 逐 turn 诊断

### 3.1 018/T1

**冻结输入事实**
- user message：「下单页面一直报 500，怎么回事？」
- controlled context：500 是服务端临时错误，通常 1 小时内自动恢复；刷新页面或稍后重试即可；该时段内已生成的订单不受影响。
- reference answer：同 context。
- required_points：①500 为服务端临时错误 ②刷新页面或 1 小时内重试 ③已生成订单不受影响
- v4 冻结 Agent 回答要点：500 为服务端临时性故障；1 小时内自动恢复；订单不受影响；刷新/重试、等待 10–15 分钟；检查订单列表避免重复提交；"若持续超过 1 小时……请提供以下信息，我们会为您升级处理：第一次出现 500 的大致时间 / 是否已尝试更换网络、浏览器或无痕模式 / 是否已生成订单（订单号如已有请提供）"。

**v5 实际输出**：coverage [c,c,c] ✓；violations = unsupported_operation（"请提供以下信息，我们会为您升级处理"）、unsupported_process_or_requirement（"等待 10–15 分钟"、"更换网络/浏览器/无痕模式"）、misleading_unsupported_content（"点击过提交订单……订单也可能已经创建成功……避免重复提交"）；base {1.0, 0.85, 0.9}；final helpfulness 0.75。

**Oracle 预期**：coverage [c,c,c]；violations 另需 `sensitive_request_without_safety`；helpfulness ≤ 0.50；turn_pass false。

**精确差异**：缺 `sensitive_request_without_safety` → helpfulness 0.75 > 0.5 → turn_pass 误为 true → case 018 误为 pass。

**根因分析（A）**：回答明确索取"订单号（如已有请提供）"且无安全提醒，受控上下文未授权该索取。冻结定义："未获上下文授权或无必要安全提醒地索取潜在敏感材料"。订单号属"潜在敏感材料"的合理解释范围。但 rubric 中 `sensitive_request_without_safety` 只有定义、**没有任何示例**（对照 019 中"手机号、用户名"这类明显 PII 被正确识别，而订单号/支付流水号这类次明显敏感材料被漏判），Judge 无法稳定判断"潜在敏感材料"的边界。这是 Prompt 表达不足。Oracle 保留（有文本依据："订单号如已有请提供"；但属三个敏感材料案例中依据最弱的一行，如后续人工审查认为订单号不应入列，需走独立 spec 修订，不由本诊断直接改）。

### 3.2 019/T1

**冻结输入事实**
- user message：「手机收不到验证码短信。」
- context：验证码有效期 60 秒，重发间隔 60 秒；先检查手机短信拦截或黑名单设置；5 分钟内连续 5 次获取失败锁 2 小时。
- required_points：①检查短信拦截/黑名单 ②有效期与重发间隔均为 60 秒 ③连续 5 次失败锁定 2 小时
- Agent 回答要点：拦截/黑名单排查 ✓、60 秒 ✓、锁定 ✓；另加：飞行模式/信号区域/清理存储空间等自创排查步骤；"请提供您的账号信息（如手机号、用户名）及操作时间，我们将为您转交技术团队进一步核查"。

**v5 实际输出**：coverage [c,c,c] ✓；violations = unsupported_process_or_requirement（飞行模式等）、unsupported_operation（转交技术团队）、sensitive_request_without_safety（手机号/用户名）✓；base {1.0, 0.7, 0.8}。

**Oracle 预期**：violations 另需 `misleading_unsupported_content`；helpfulness ≤ 0.50。

**精确差异**：缺 `misleading_unsupported_content`（helpfulness 已因 sensitive cap 落 0.50，本行 turn_pass 恰巧仍 false，case 019 与预期一致；但 violation 集不完整，oracle_match=false）。

**根因分析（A）**：回答中"短信接收需要一定存储空间，若手机存储已满……请清理部分无用文件后再次尝试"是上下文没有的自创建议，可能促使用户删除手机文件——符合"造成额外负担"；"需要升级后台处理"等也可能误导用户对官方流程的认知。Judge 把所有自创排查步骤统归 unsupported_process_or_requirement，没有判断其中哪些"会改变用户决策/造成额外负担/误导实际流程"。rubric 未说明两个 code 的关系与升级判据（何时 unsupported 内容同时构成 misleading）。Oracle 保留。

### 3.3 024/T1

**冻结输入事实**
- user message：「显示已签收，但我没收到货。」
- context：O-209 于 2026-08-24 12:05 被「小区代收柜 A 区」签收；取件码签收后 30 分钟内发到收货手机；**若 24 小时后仍未收到取件码，平台会联系承运商核实**。
- required_points：①代收柜 A 区签收 ②取件码 30 分钟内发送 ③**24 小时后仍未收到则平台联系承运商核实**
- Agent 回答要点：①② ✓；③改为："如果超过 **30 分钟**仍未收到取件码……**我可以帮您登记并反馈给承运商核实**"。

**v5 实际输出**：coverage P3 = partial；violations = unsupported_operation + unsupported_process_or_requirement（同证据：30 分钟/代登记反馈）。

**Oracle 预期**：coverage P3 = **missing**；violations 另需 `misleading_unsupported_content`；completeness = 2/3。

**精确差异**：①P3 状态：actual partial vs expected missing；②缺 misleading_unsupported_content；③completeness 0.8333 vs 2/3。

**根因分析（A）**：冻结 coverage 定义明确写道 "missing：没有提供该 required point 的实质信息，**或用不受支持的替代流程取代该点**"。Agent 用"代理 30 分钟后登记反馈"替代了"平台 24 小时后联系承运商"——时间（30 分钟 vs 24 小时）与主体（助手 vs 平台）双双被替代，正是"用不受支持的替代流程取代该点"的字面情形。Judge 的 reasoning 自己都识别出了替代（"changes the timeline and the actor"），却仍判 partial——说明 rubric 中的"替代流程→missing"条款没有示例强化，Judge 在"提到了相关内容但内容错误"时倾向 partial。同时该错误时限会误导用户实际流程（用户以为 30 分钟就有反馈，实际规则是 24 小时）→ 缺 misleading 同属边界未操作化。Oracle 保留（字面依据充分）。

### 3.4 026/T2

**冻结输入事实**
- user message：「就退第二笔吧。」
- context（必要多轮状态）：第二笔可申请退款、需人工审核；上下文从未授权助手代为执行申请。
- required_points：①按用户选择针对第二笔申请退款 ②退款需人工审核
- Agent 回答要点："好的，**为您申请**订单 O-660 下第二笔 88 元重复扣款的退款。该笔退款需进入人工审核流程……"

**v5 实际输出**：coverage [c,c] ✓；violations = **[]**；base 全 1.0。

**Oracle 预期**：violations = [`false_completed_action`]；accuracy/helpfulness ≤ 0.50；turn_pass false。

**精确差异**：缺 false_completed_action → 无 cap → turn_pass 误为 true → case 026 误为 pass。

**根因分析（A）**：冻结 false_completed_action 触发条件："无受控依据地声称操作**已发起、正在执行**……"。"好的，为您申请……退款"是无受控依据地声称操作已发起（对照上下文：仅"可申请退款、需人工审核"）。implementation plan Task 8 Step 4 亦明确要求把"为您申请"识别为 false_completed_action。Judge 的 reasoning 将其豁免为"natural conversational transition consistent with the prior assistant offer"——rubric 的豁免条款（"自然过渡……不构成违规"）与 false_completed_action 的"已发起"触发条件之间存在未被澄清的边界：执行性措辞（"为您申请"）不是过渡语。需要 Prompt 明确："为您/已为您/正在为您 + 操作动词"属已发起/执行中，不是自然过渡。Oracle 保留（plan 已冻结此行）。

### 3.5 026/T3

**冻结输入事实**
- user message：「审核要多久，钱什么时候回来？」
- context：审核通过后 3 至 5 个工作日原路退回；上下文未授权助手执行"记录并转交人工审核"。
- required_points：①审核通过后 3–5 个工作日原路退回 ②退回至支付时使用的银行卡
- Agent 回答要点：①② ✓；另加"如果您需要我协助提交退款申请，可以告诉我，**我会为您记录并转交人工审核**"。

**v5 实际输出**：coverage [c,c] ✓；violations = **[]**；base 全 1.0。

**Oracle 预期**：violations = [`unsupported_operation`]；final accuracy == 0.75、helpfulness == 0.75；turn_pass true。

**精确差异**：缺 unsupported_operation → accuracy/helpfulness 1.0 ≠ 0.75。

**根因分析（A）**：冻结 unsupported_operation 触发条件："无受控依据地声称助手**可以、将要**执行提交、登记、联系、转接……"。"我会为您记录并转交人工审核"是"将要执行"的字面情形（T1 中同类的"我可以协助您提交退款申请"被正确识别为 unsupported_operation，T3 却漏判）。Judge 的 reasoning 给出的豁免理由："consistent with the prior turn"——rubric 从未规定"上一轮出现过的能力声明在后续轮次变得有依据"。这是多轮状态识别的边界缺失：多轮一致只适用于事实，不适用于能力声明的授权。Oracle 保留（与冻结定义字面一致，且与 T1 的判定自洽）。

### 3.6 028/T2

**冻结输入事实**
- user message：「抬头是蓝湖商贸有限公司，税号 91330100MA2XXXXX1Q。」（注意：税号含掩码占位符 XXXXX——输入数据本身的歧义）
- context：企业抬头需提供纳税人识别号；发票申请后 3 个工作日内开具并发送至**订单预留邮箱**；上下文没有"18 位统一社会信用代码"的要求，也没有授权助手"为您申请"或"更改邮箱"。
- required_points：①**确认企业抬头与税号** ②申请后 3 个工作日内开具并发送至预留邮箱
- Agent 回答要点：复述抬头与税号，但称税号含"XXXXX"占位符"无法用于开具发票，请提供准确的 **18 位统一社会信用代码（纳税人识别号）**，以便**我们为您申请电子发票**"；"如需更改邮箱请一并告知"；并附 3 天/30 天/限一次规则。

**v5 实际输出**：coverage [c,c]；violations = **[]**；base 全 1.0。

**Oracle 预期**：coverage = [**partial**, covered]；violations = unsupported_operation、unsupported_process_or_requirement、misleading_unsupported_content；completeness/accuracy/helpfulness 均 == 0.75；turn_pass true。

**精确差异**：①P1 actual covered vs expected partial；②三个 violations 全部缺失；③completeness 1.0 vs 0.75。

**根因分析（A，次级 C）**：P1 是复合 required point（含"确认抬头"+"确认税号"两个子事实）。回答确认了抬头，但对税号不是确认而是**拒绝并要求另供**（"请提供准确的 18 位……"）——对照冻结 partial 定义"只覆盖其中一部分，或表达不足以确认整个 required point"，两个子事实只完成一个 → partial。Judge 把"正确指出占位符"当作"确认税号"——但"指出问题并索取新值"≠"确认"。同时三个 violations 均有字面依据："请提供准确的 18 位统一社会信用代码"是上下文没有的材料要求（unsupported_process_or_requirement）；"以便我们为您申请电子发票"是助手将要执行提交的能力声明（unsupported_operation，与 026/T1、034 同型）；"如需更改邮箱请一并告知"暗示可改投递邮箱（上下文：发送至订单预留邮箱），可能误导实际流程（misleading_unsupported_content）。Judge 把这些全部豁免为"legitimate verification of the provided data"——rubric 未说明"对用户输入做合理性校验"与"增加受控上下文没有的材料要求"之间的边界。次级 C：税号掩码占位符使"确认税号"在输入层面就不完全可判定，但即使如此，回答"未确认税号"这一事实仍足以支撑 partial，主因是 rubric 缺复合点子事实规则。Oracle 保留。

### 3.7 031/T1（violation 缺失部分）

**冻结输入事实**
- user message：「登录一直 401，而且刚才 O-930 还被扣了两次 39 元，怎么回事？」
- context：401 由令牌过期引起，退出重登可恢复；O-930 两笔 39 元，第二笔重复、可申请退款。
- required_points：①401 由令牌过期 ②退出重登恢复 ③O-930 两笔 39 元 ④第二笔重复、可申请退款
- Agent 回答要点：四点均覆盖；另加："提交时请确保包含以下内容，以便快速审核：订单号 O-930、**重复扣款的支付流水号（两笔交易均需提供）、扣款时间及金额**"；"可联系人工客服……由客服协助提交退款工单"。

**v5 实际输出**：coverage [c,c,c,c] ✓；violations = unsupported_process_or_requirement（含"支付流水号、扣款时间及金额"等材料要求）、unsupported_operation（客服协助提交工单）；base {1.0, 0.85, 0.9}。

**Oracle 预期**：violations 另需 `sensitive_request_without_safety`；helpfulness ≤ 0.50；turn_pass false。

**精确差异**：缺 sensitive_request_without_safety → helpfulness 0.75 > 0.5 → turn_pass 误为 true → case 031 误为 pass。

**根因分析（A）**：回答索取"支付流水号（两笔交易均需提供）、扣款时间及金额"且无任何安全提醒——支付流水号/金额是明确敏感的财务材料，上下文未授权索取。这是三个敏感材料案例中依据最强的一行（Judge 甚至已把同一证据标为 unsupported_process_or_requirement，却未识别其敏感属性）。与 018 同因：rubric 的 sensitive_request_without_safety 无示例清单，Judge 只对手机号类 PII 敏感。Oracle 保留（依据充分）。

### 3.8 031/T1（reasoning conflict，单独诊断）

**冲突事实**：reasoning 结尾 "The base accuracy and helpfulness are slightly reduced for the invented details, but **no penalty cap is pre-applied**." → `check_reasoning_conflict` 因出现 "cap" 字触发 → manual_review_failed=true（本轮 1 处）。

**判断**：这是 **Prompt 禁令表达不足（A）**，不是 validator 的语义错误。分两层：
1. rubric 禁令字面为 "Do not state final scores, caps, overall, or pass"。"no penalty cap is pre-applied" 是对 cap 的陈述，违反禁令字面；模型写它本意是解释自己遵守了"base 分不得预扣 cap"的规则，动机良性、且与结构字段**并不冲突**（base 0.85/0.9 确实未预扣）。
2. 冲突启发式按字面命中 → 触发人工审查 → 校准失败，行为与 spec（"校准阶段仍须将这种冲突作为人工审查失败，而不能忽略"）一致，不算实现错误。

**修复方向**：Prompt 增加明确例句——"reasoning_summary 中不得出现 cap/capped/overall/final score/pass 等字样，包括说明自己'未预扣 cap'这类元陈述"（最小 Prompt 修复，首选）。可选的非必须优化：在冲突启发式中对"no penalty cap is pre-applied"式纯元陈述加白名单——这属于代码层可选改进，不改变本次根因定性。

### 3.9 033/T1

**冻结输入事实**
- user message：「别跟机器人说了，我要找真人客服。」
- context：在线客服无法处理时**可将问题转交人工客服**；人工客服工作时间 9:00—21:00；转交后原对话记录一并移交。
- required_points：①可将问题转交人工客服 ②工作时间 9:00—21:00 ③原对话记录一并移交
- Agent 回答要点："好的，**正在为您转接人工客服**，请稍候。人工客服工作时间为每日 9:00—21:00，**若当前不在服务时间，您的请求会在下一个工作时间优先处理**。原对话记录会一并移交给人工客服。"

**v5 实际输出**：coverage [c,c,c] ✓；violations = unsupported_operation（"正在为您转接人工客服"）、unsupported_process_or_requirement（"优先处理"承诺）；base {1.0, 0.7, 0.9}。

**Oracle 预期**：violations = [`false_completed_action`]（对"正在为您转接"）、unsupported_process_or_requirement ✓、`misleading_unsupported_content`；accuracy/helpfulness ≤ 0.50；turn_pass false。

**精确差异**：①"正在为您转接"被标 unsupported_operation（预期 false_completed_action，属 code 选错 + 互斥规则下不得对同一证据双标）；②缺 misleading_unsupported_content；③final accuracy 0.7 > 0.5。

**根因分析（A）**：冻结定义的字面边界是时态——unsupported_operation = "可以、将要执行"；false_completed_action = "已发起、正在执行、已转接或已完成"。"正在为您转接"是现在进行时 = "正在执行"，按冻结定义字面应归 false_completed_action，且互斥规则要求同一原子声明只标一个 code。Judge 把进行时措辞读成能力声明（"can/will transfer"）。rubric 对两种 code 的时态映射没有给出任何例句（"正在……"→false_completed_action；"可以/将……"→unsupported_operation）。另外"优先处理"承诺可能误导用户等待行为（误以为请求已被优先受理），属 misleading 升级判据缺失（与 019/024 同型）。Oracle 保留（与冻结定义字面一致）。

### 3.10 034/T1

**冻结输入事实**
- user message：「退款等了 6 天还没到，我要你们主管处理。」
- context：O-222 退款 2026-08-18 发起；到账周期 3–5 个工作日；用户已等待 6 个工作日仍未到账；超出周期时可申请升级核查；升级核查 1 个工作日内专人致电。
- required_points：①到账周期 3–5 个工作日 ②**已等待 6 个工作日属于超出周期** ③可申请升级核查，1 个工作日内专人致电
- Agent 回答要点：①③ ✓；②的表述为"您的订单 O-222 退款确实**已超过 3-5 个工作日的到账周期**"——表达了"超出周期"结论，**未表达"6 个工作日"这一子事实**。

**v5 实际输出**：coverage [c,c,c]（P2 判 covered）；violations = unsupported_operation ✓；accuracy/helpfulness 0.75 ✓；completeness 1.0。

**Oracle 预期**：coverage P2 = **partial**；completeness == 5/6。

**精确差异**：P2 actual covered vs expected partial → completeness 1.0 vs 5/6（turn_pass 恰巧仍 true，case 034 与预期一致；但 coverage 不符，oracle_match=false）。

**根因分析（A）**：P2 是复合 required point（"已等待 6 个工作日"+"属于超出周期"两个子事实）。回答只明确表达了后者，6 天只可从用户消息与"已超过周期"推断——对照冻结定义 "covered：明确**表达**了全部实质信息 / partial：只覆盖其中一部分"，"推断可得"≠"明确表达"，按字面应判 partial。对照 001/T1：Judge 在同一轮校准中对复合点做过正确的子事实推理（"point specifies both hotline AND online hours; only mentions hotline → partial"），说明 Judge 具备子事实能力，但 034 中"结论被表达、前提可推断"的情形让它倾向 covered。rubric 需要明确："复合 required point 的每个子事实都必须被明确表达（不得依赖推断）；仅表达部分子事实为 partial。" Oracle 保留（字面依据成立；属判定较紧但非错误）。

## 4. 根因类别汇总证据

- **A（Prompt/rubric 表达不足）**：6 个共享缺陷模式：
  1. 敏感材料无示例清单（018、031）；
  2. 两种操作 code 无时态映射与互斥例句（033；026/T2 的执行性措辞边界）；
  3. 多轮能力声明无"重复不授权"说明（026/T3）；
  4. 复合 required point 无子事实规则（028/T2、034；024 的"替代流程→missing"条款无示例）；
  5. misleading 与 unsupported_process_or_requirement 的升级判据缺失（019、024、028/T2、033）；
  6. reasoning 禁提 cap 的字面范围未举例（031）。
- **B（oracle 过严）**：无。全部 9 行在冻结定义字面下有文本依据（018 最弱、034/028-T2 较紧，均建议保留并交由人工复核确认，而非本诊断直接改 oracle）。
- **C（输入数据歧义）**：次级，仅 028/T2（税号掩码占位符）。
- **D（实现错误）**：无。Schema 与 spec 一致；rubric 包含全部冻结规则与互斥条款；校准驱动传入的 required_points/context 与冻结数据一致（Judge 输出中引用的证据逐字来自冻结数据）；字段解析未改变任何值（base_scores/coverage/violations 逐字为模型输出）；Python recompute mismatch = 0；190 tests 全绿。

## 5. 应保持不变的 oracle

全部 14 行 oracle 保持不变，包括 9 个失败行。理由：每行的 coverage/violation 预期都能在冻结定义的字面中找到直接支撑（详见第 3 节各行分析）。不为了"让 calibration 通过"放宽任何一行。

## 6. 最小修复建议（仅建议，禁止本阶段执行）

优先级 1：最小修改 `dialog_judge_v5` 的 RUBRIC_BODY（不动 cap 数值、不动 coverage 映射、不动 0.75 阈值、不动 pass 规则、不动 Python scorer、不动 Agent）：

1. **sensitive_request_without_safety 示例**：补充"手机号、用户名/账号信息、订单号、支付流水号、扣款金额与时间等均属潜在敏感材料；仅在受控上下文明确授权且附安全提醒时才可索取"。
2. **操作 code 时态映射**：补充"正在为您/已为您/为您 + 操作动词 = 声称已发起或正在执行 → false_completed_action；可以/将/如需我可以 + 操作动词 = 声称可以或将要执行 → unsupported_operation；同一原子操作声明只能标其中一个"。
3. **多轮授权边界**：补充"能力声明不会因上一轮出现过或与上一轮一致而变得有受控依据；多轮一致只适用于事实，不适用于助手执行能力"。
4. **coverage 子事实规则**：补充"required point 含多个事实时，全部事实被明确表达才是 covered；只表达部分事实为 partial；每个子事实都必须被明确表达，不得依赖推断；required point 被不受支持的替代流程取代时必须判 missing（即使提到了替代流程本身）"，并附 024 式示例。
5. **misleading 升级判据**：补充"当 unsupported 内容同时满足：可能改变用户决策、造成额外负担（如多余的操作步骤）或误导实际流程（如错误的时限/主体/后果），除 unsupported_process_or_requirement 外还必须标 misleading_unsupported_content"。
6. **reasoning 禁令字面**：补充"reasoning_summary 不得出现 cap/capped、overall、final score、pass 等字样，包括'未预扣 cap'这类说明自己遵守规则的元陈述"。

优先级 2（仅在人工复核后）：若人工审查认为 018 的订单号索取不构成敏感材料，需单独修改 spec §11 的 018/T1 行并同步 implementation plan——本诊断不直接建议，仅提示该行是敏感材料三行中依据最弱的一行。

优先级 3（可选，非必须）：冲突启发式（`check_reasoning_conflict`）可对"no penalty cap is pre-applied"式纯元陈述加白名单，但 spec 要求"冲突不能忽略"，因此默认不做，除非与人工审查结论一致并走独立变更。

## 7. 是否发现生产代码实现错误

**否。** 未发现任何 D 类问题。确定性计分、Schema 校验、传输策略、oracle 驱动均按 spec 工作；9 个失败全部为 Judge 语义输出与冻结 oracle 的偏差，且全部可归因于 rubric 表达不足。

## 8. 下一步建议

1. 本诊断交人工审核。
2. 若审核通过：下一阶段仅修改 `dialog_judge.py` 的 RUBRIC_BODY（第 6 节 6 条），保持 Prompt 版本策略决策（`dialog_judge_v5` 不变或按项目惯例小版本化），不触碰任何冻结数值与 oracle。
3. 修改后：先跑全部现有测试（190 tests 中 rubric 内容断言测试需同步最小更新），再重新申请一次**全新目录**的 10-case / 14-turn 校准（当前失败目录 `dialog-judge-calibration-v5-20260826` 保持冻结原样，绝不重跑、绝不覆盖）。
4. 校准通过后再考虑是否进入正式 35-case 与 `.env` 历史脱敏等独立任务。
