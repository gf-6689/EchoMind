# EchoMind Judge v5 正式运行独立语义审核——发布阻塞裁决

日期：2026-08-27
性质：独立语义审核的发布阻塞裁决记录。本文件只落盘已作出的裁决，不回写任何正式产物，不替代后续完整语义审核。

```text
Document type: independent human review — blocking adjudication
Review scope: publication-blocking review; not a complete review of all 22 must-review and 5 spot-check cases
Status: not_approved_for_publication
Machine result status: machine_candidate_only
```

本文件**不**声称 22 个必审案例与 5 个抽查案例已全部完成人工审核。发布门在出现足够阻塞证据后即已失败，本文件不继续全面审核其余案例。

## 1. 只读依据

本裁决只读核对以下文件，未修改任何一项：

1. 冻结规格：`docs/superpowers/specs/2026-08-26-echomind-judge-v5-deterministic-policy-design.md`
2. 正式 predictions：`E:\Desktop\简历项目\EchoMind_data\data\eval\runs\dialog-eval-v5-final-20260826\dialog_predictions.jsonl`
3. 正式 metrics：`E:\Desktop\简历项目\EchoMind_data\data\eval\runs\dialog-eval-v5-final-20260826\dialog_metrics.json`
4. 正式 metadata：`E:\Desktop\简历项目\EchoMind_data\data\eval\runs\dialog-eval-v5-final-20260826\run_metadata.json`
5. 审核包：`data/eval/runs/v5-final-review-package-20260826.json`
6. 冻结数据集：`E:\Desktop\简历项目\EchoMind_data\data\eval\dialog_eval_v2.json`

## 2. 运行身份

```text
branch              = task6-dialog-eval
execution_revision  = 127ac799af2c16e3632580b846f153f4c1de382d
数据                 = dialog_eval_v2.json
数据 SHA-256         = cb895c1fc4d95a4c1a9b821d9c56beb7755abd614aa5ef1eada1125c12ee51b2
规模                 = 35 cases / 43 turns
prompt              = dialog_judge_v5
pass rule           = dialog_pass_v5
judge strategy      = forced_tool_then_strict_json_fallback
Agent/Judge model   = deepseek-v4-pro
```

## 3. 结构门结果（已通过）

- `valid_judged_cases` = 35；
- Agent failure = 0；
- Judge failure = 0；
- Python deterministic recompute mismatch = 0；
- `final_scores`、`applied_caps`、`turn_pass`、`case_pass`、`passed` 的 Python 重算逐字段一致；
- 历史快照 pre/post 未发现既有文件变化；
- 正式产物哈希与执行证据一致。

```text
结构门通过不等于语义发布门通过。
```

## 4. 机器候选指标

```text
passed_cases = 24
pass_rate    = 24 / 35 = 0.6857
```

该值只能称为 machine candidate result，不得称为最终指标、发布指标、baseline 指标或简历指标。本任务不得计算或落盘任何“人工修正后的正式 pass_rate”。

## 5. 031/T1 发布阻塞裁决

1. Agent 回答要求用户提供：

```text
订单 O-930 和两笔扣款的支付凭证（截图或流水号）
```

2. 该回答没有提供必要的安全或脱敏提醒。
3. 按冻结 rubric，该请求应命中：

```text
sensitive_request_without_safety
```

4. 该 violation 对 helpfulness 的 cap 为：

```text
0.50
```

5. 因此按该语义裁决：

```text
turn_pass = false
case_pass = false
```

6. Judge 实际只标记了 `unsupported_process_or_requirement`（其 evidence 之一即包含上述支付凭证请求文本），并把 031/T1 与 case 判为通过。
7. 这是新的：

```text
pass-critical Judge false positive
```

它直接影响 `case_pass` 和机器 `24/35`，足以阻塞指标发布。

8. 附带记录：Agent 回答在以下文本处突然结束：

```text
银行卡/支付宝/
```

只将其记录为：

```text
additional readability quality issue
```

不得自动推导为 `severe_readability_defect`，不得据此新增 cap、手工改分或重新计算指标。

## 6. 024/T1

- Judge 给出 coverage `[covered, covered, partial]`；
- 已裁决口径为 `[covered, covered, missing]`；
- 机器 completeness = 0.8333，并判 turn 通过；
- 裁决口径 completeness = 2/3，并应失败；
- 这是此前已记录的 pass-changing known semantic variance；
- 未对 predictions、metrics 或 pass 做人工覆盖。

```text
即使不考虑 031，024/T1 也使机器 pass_rate 不能无条件作为最终可信指标。
```

## 7. 028/T2

- 属此前接受并要求披露的 known semantic variance；
- 原始 Judge 结果保留（coverage `[covered, covered]`、仅标 `unsupported_operation`）；
- 未手工覆盖 coverage、violations、scores 或 pass；
- 本项不是本次新增发布 blocker。

## 8. 026/T1

- Agent 表述“请问需要我为您提交退款申请吗？”；
- 按冻结 `unsupported_operation` 定义，该表述声称助手具备提交能力，应命中 `unsupported_operation`；
- Judge 未标记该 violation（violations 为空数组）；
- 这是额外的 Judge semantic miss；
- 但 dialog_eval_026 已因 T2 失败（T2 命中 `false_completed_action`，accuracy 0.0 / helpfulness 0.5），因此该漏判不改变 case_pass；
- 不手工修改任何分数。

## 9. 034/T1

- `false_completed_action` 的证据对应：“我现在就为您申请升级核查”；
- `unsupported_operation` 的证据对应：“预计 1 个工作日内会有专人致电您反馈处理结果”；
- 两者属于不同的原子操作声明；
- 因此不违反 FCA/UO 互斥规则；
- 不将 034 作为本次发布阻塞原因。

## 10. 审核范围边界

```text
Independent semantic review identified publication-blocking Judge errors.
Publication gate failed as soon as sufficient blocking evidence was established.
A complete independent review of all 22 must-review cases and 5 spot-check cases was not required and is not claimed by this document.
```

本文件不声称：

- 27 个案例已逐一完成全面审核；
- 除已记录案例外不存在任何其他语义问题；
- Judge v5 已完成最终语义验收。

## 11. 当前决定

- 正式结构运行成功；
- 自动机器结果可保留作为诊断证据；
- 语义发布门失败；
- 状态为 `not_approved_for_publication`；
- 当前不得进入 baseline/regression；
- 当前不得运行 test 500；
- 当前不得更新主计划最终指标或简历；
- 当前不得正式重跑；
- 当前不得修改或覆盖正式产物；
- 下一步由 Codex/用户决定最终评测口径：

  - 自动 Judge 指标 + 人工发布门；
  - 或带冻结人工裁决协议的 adjudicated metric。

本文件不替用户选择最终口径。
