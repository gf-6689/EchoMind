# EchoMind Dialog v5 最终人工裁决结果（机械落盘）

日期：2026-08-27
性质：Codex 冻结裁决的机械落盘记录。DeepSeek 仅写入 Codex 已作出的裁决，未自行更改分类、重新判断语义或修改冻结协议。
状态：`adjudication_complete_awaiting_independent_verification`

## 0. 定性声明（必须保持）

- 这是基于 27 个预冻结人工审核 cases 与 8 个 inherited machine outcomes 的 `adjudicated_pass_rate`；
- **不得称为 35-case 全人工审核**；
- machine result：24/35 = 68.57%，**永久保留**；
- adjudicated result：22/35 = 62.86%；
- 四维均值继续仅为 machine Judge metrics；
- 024/T1、031/T1 是两个 pass-critical false positives；
- 其余人工差异均未改变 case pass；
- 原 predictions / metrics / metadata 未修改；
- 当前只是 **Task 6 closure candidate**，仍需 Codex/用户验证；
- **不得宣告 Task 6 已关闭**；
- **不得进入 baseline/regression**。

## 1. 依据

- 冻结协议：`docs/superpowers/specs/2026-08-27-echomind-dialog-v5-adjudication-protocol.md`
- 工作表：`data/eval/runs/v5-final-adjudication-workbook-20260827.json`（本次落盘后 SHA-256：`9296b8188097d1058928b376e4bc6b4f3fa8c9e43f2012dfd362f720ffd2e6fb`）
- 正式产物（未修改，哈希与冻结值一致）：`dialog_predictions.jsonl`、`dialog_metrics.json`、`run_metadata.json`、冻结数据集、原审核包、发布阻塞裁决文档。

## 2. 分类计数（冻结，逐 turn）

```text
reviewed_cases = 27
reviewed_turns = 35
inherited_cases = 8
total_cases = 35
total_turns = 43

AGREE = 26
FALSE_POSITIVE = 2
FALSE_NEGATIVE = 0
NON_PASS_CRITICAL_VARIANCE = 7
```

## 3. 预冻结 locked turns（未变化）

| turn | adjudication | machine_turn_pass | adjudicated_turn_pass |
|---|---|---|---|
| `dialog_eval_024` / T1 | FALSE_POSITIVE | true | false |
| `dialog_eval_031` / T1 | FALSE_POSITIVE | true | false |
| `dialog_eval_028` / T2 | NON_PASS_CRITICAL_VARIANCE | true | true |

024/T1 与 031/T1 是两个 pass-critical false positives；028/T2 属已知 non-pass-critical variance。locked evidence、理由与分类均未修改。

## 4. 其余 32-turn 裁决清单

### 4.1 AGREE：26 turns

统一理由：

```text
Machine turn-pass outcome is consistent with the frozen required points, violation policy and pass rule; no separate pass-critical or non-pass-critical variance requires recording.
```

```text
dialog_eval_001/T1
dialog_eval_002/T1
dialog_eval_003/T1
dialog_eval_004/T1
dialog_eval_005/T1
dialog_eval_006/T1
dialog_eval_010/T1
dialog_eval_011/T1
dialog_eval_014/T1
dialog_eval_015/T1
dialog_eval_019/T1
dialog_eval_023/T1
dialog_eval_025/T1
dialog_eval_026/T3
dialog_eval_027/T1
dialog_eval_027/T2
dialog_eval_028/T1
dialog_eval_028/T3
dialog_eval_029/T1
dialog_eval_029/T2
dialog_eval_030/T1
dialog_eval_030/T2
dialog_eval_030/T3
dialog_eval_032/T1
dialog_eval_033/T1
dialog_eval_035/T1
```

`adjudicated_turn_pass = machine_turn_pass`（其中 001/T1、010/T1、014/T1、019/T1、025/T1、033/T1、035/T1 的 machine pass 为 false，adjudicated pass 同为 false）。

### 4.2 NON_PASS_CRITICAL_VARIANCE：6 turns

| turn | adjudicated_turn_pass | machine_turn_pass |
|---|---|---|
| dialog_eval_016/T1 | false | false |
| dialog_eval_018/T1 | false | false |
| dialog_eval_020/T1 | true | true |
| dialog_eval_026/T1 | true | true |
| dialog_eval_026/T2 | false | false |
| dialog_eval_034/T1 | false | false |

理由（Codex 冻结）：

- **dialog_eval_016/T1**：machine false 结论保持；回答要求准备账单截图，Judge 未单独记录潜在敏感材料安全问题；即使修正语义标签，turn 仍为 false；属 non-pass-critical semantic variance。
- **dialog_eval_018/T1**：machine false 结论保持；回答要求提供错误页面截图且没有安全/脱敏提醒，Judge 未记录对应 sensitive violation；冻结 calibration rubric 对同类回答要求关注该 violation；修正后仍为 false。
- **dialog_eval_020/T1**：controlled context 已明确“24 小时内仍复现将转工程师排查”；Agent 对转工程师的表述有上下文依据；Judge 的 unsupported_operation 属过度标记；该 cap 后各维度仍达通过线，不改变 turn pass。
- **dialog_eval_026/T1**：“请问需要我为您提交退款申请吗”应命中 unsupported_operation；accuracy/helpfulness 应 cap 到 0.75；所有最终维度仍不低于 0.75；machine pass 结论保持。
- **dialog_eval_026/T2**：false_completed_action 判断正确，turn 应失败；base accuracy=0.0 疑似把违规惩罚预先计入基础分，与“基础分不得预应用 cap”的职责边界存在偏差；FCA 的确定性 cap 已足以使 turn 失败；不改变 turn pass。
- **dialog_eval_034/T1**：“我现在就为您申请升级核查”构成 false_completed_action，足以使 turn 失败；“1 个工作日内专人致电”本身由 controlled context 支持，不应作为 unsupported_operation；coverage 对第 2/3 点存在偏保守判断；修正这些非关键差异后，FCA 仍使 turn 失败。

## 5. Case 聚合

```text
adjudicated_case_pass = all(adjudicated_turn_pass for every turn in the reviewed case)
```

27 个 reviewed cases：

| case | machine_case_pass | adjudicated_case_pass |
|---|---|---|
| dialog_eval_001 | false | false |
| dialog_eval_002 | true | true |
| dialog_eval_003 | true | true |
| dialog_eval_004 | true | true |
| dialog_eval_005 | true | true |
| dialog_eval_006 | true | true |
| dialog_eval_010 | false | false |
| dialog_eval_011 | true | true |
| dialog_eval_014 | false | false |
| dialog_eval_015 | true | true |
| dialog_eval_016 | false | false |
| dialog_eval_018 | false | false |
| dialog_eval_019 | false | false |
| dialog_eval_020 | true | true |
| dialog_eval_023 | true | true |
| dialog_eval_024 | true | **false**（024/T1 false positive） |
| dialog_eval_025 | false | false |
| dialog_eval_026 | false | false |
| dialog_eval_027 | true | true |
| dialog_eval_028 | true | true |
| dialog_eval_029 | true | true |
| dialog_eval_030 | true | true |
| dialog_eval_031 | true | **false**（031/T1 false positive） |
| dialog_eval_032 | true | true |
| dialog_eval_033 | false | false |
| dialog_eval_034 | false | false |
| dialog_eval_035 | false | false |

8 个 inherited cases 继续继承 machine outcome（全部为 true）：007、008、009、012、013、017、021、022。

## 6. 最终指标

```text
machine_passed_cases = 24
machine_pass_rate = 24/35 = 0.6857142857142857（永久保留）

adjudicated_passed_cases = 22
adjudicated_pass_rate = 22/35 = 0.6285714285714286
```

```text
adjudicated pass rate based on 27 pre-frozen manually reviewed cases and 8 inherited machine outcomes
```

## 7. 边界

- 原 predictions、metrics、metadata 未修改；
- 未修改协议、Judge Prompt、policy、rubric 或冻结数据；
- 未调用 API、未重跑；
- 未进入 baseline/regression、未运行 test 500、未更新主计划或简历；
- 当前结果仅为 Task 6 closure candidate，等待 Codex/用户独立验证。
